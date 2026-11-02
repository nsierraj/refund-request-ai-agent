"""Step 9: the Step 8 agent, with tracing and a usage line after every turn.

    docker run -d --name phoenix -p 6006:6006 -p 4317:4317 arizephoenix/phoenix:14.9.1
    python step9_traced.py             # terminal 1
    python review.py                   # terminal 2, same as Step 8
    open http://localhost:6006         # the traces

Strands creates spans for the agent, each model call and each tool call
on its own. This file adds two things:
  - one span of our own, "review_gate", so the gate's decision shows up
    in the trace next to the tools
  - a session ID, so every turn of this conversation groups together in
    Phoenix's Sessions view

Optional: see what a turn would cost in the cloud. Look up the current
per-million-token prices for the model you'd use, then:
    PRICE_IN=3 PRICE_OUT=15 python step9_traced.py
"""

import json
import os
import sys
import time
import uuid

from strands import Agent, tool
from strands.models.ollama import OllamaModel

from config import DB_PATH, MODEL
from fraud import score_refund_risk
from rag import search_policy
from reviews import check_review_status, now, request_human_review
from step5_strands import ToolTrace, print_reply_text
from step8_review import DEFAULT_MESSAGE, REVIEW_PROMPT, ReviewGate, deliver_updates
from tools import check_refund_eligibility, issue_refund, lookup_order
from tracing import setup_tracing, tracer

PRICE_IN = float(os.environ.get("PRICE_IN", 0))    # dollars per million input tokens
PRICE_OUT = float(os.environ.get("PRICE_OUT", 0))  # dollars per million output tokens


class TracedReviewGate(ReviewGate):
    """Step 8's gate, wrapped in a span of our own."""

    def check(self, event):
        if event.tool_use["name"] != "issue_refund":
            return
        with tracer.start_as_current_span("review_gate") as span:
            span.set_attribute("openinference.span.kind", "GUARDRAIL")  # Phoenix shows it as a guardrail
            span.set_attribute("input.value", json.dumps(event.tool_use["input"]))
            super().check(event)
            held = bool(event.cancel_tool)
            span.set_attribute("refund.held_for_review", held)
            span.set_attribute("output.value", "held for human review" if held else "allowed")


def build_agent(session_id):
    return Agent(
        model=OllamaModel(host="http://localhost:11434", model_id=MODEL),
        tools=[tool(f) for f in (lookup_order, check_refund_eligibility, issue_refund, search_policy,
                                 score_refund_risk, request_human_review, check_review_status)],
        system_prompt=REVIEW_PROMPT,
        hooks=[TracedReviewGate(), ToolTrace()],
        callback_handler=print_reply_text,
        trace_attributes={"session.id": session_id},  # added to every span this agent makes
    )


def ask(agent, message):
    """One agent turn, then a one-line usage summary."""
    start = time.time()
    result = agent(message)
    seconds = time.time() - start
    turn = result.metrics.latest_agent_invocation
    tokens_in, tokens_out = turn.usage.get("inputTokens", 0), turn.usage.get("outputTokens", 0)
    line = (f"[usage] {len(turn.cycles)} model call(s), {tokens_in:,} tokens in, "
            f"{tokens_out:,} out, {seconds:.1f}s")
    if PRICE_IN or PRICE_OUT:
        line += f", about ${(tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6:.4f} in the cloud"
    print(f"\n\n  {line}")
    return result


def main():
    if not DB_PATH.exists():
        print("orders.db not found. Run:  python setup_db.py")
        sys.exit(1)

    setup_tracing()
    session_id = "chat-" + uuid.uuid4().hex[:8]
    print(f"  Session {session_id}")
    agent = build_agent(session_id)
    started_at = now()
    customer = " ".join(sys.argv[1:]) or DEFAULT_MESSAGE

    while True:
        if customer.lower() in ("quit", "exit", "q"):
            break
        if customer:
            print(f"\nCustomer: {customer}\n\nAgent: ", end="", flush=True)
            ask(agent, customer)
            print()
            deliver_updates(lambda m: ask(agent, m), started_at, quiet=True)
        else:
            deliver_updates(lambda m: ask(agent, m), started_at)
        try:
            customer = input("Customer (Enter = check for team decisions, 'quit' to exit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
