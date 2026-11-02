"""Step 8: a real human in the loop.

    Terminal 1:  python step8_review.py
    Terminal 2:  python review.py

Refunds that are too big or too risky no longer just get a promise that
"a team member will review it." They go into a review queue (a table in
orders.db). You work the queue in terminal 2. Back in terminal 1, press
Enter and the agent passes your decision to the customer.

Same agent as Step 7, plus:
  - request_human_review and check_review_status tools
  - ReviewGate: when issue_refund needs a human, the hook opens the review
    itself, so nothing falls through the cracks even if the agent forgets
"""

import json
import sys

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider
from strands.models.ollama import OllamaModel

from config import DB_PATH, MODEL
from fraud import score_refund_risk
from rag import search_policy
from reviews import check_review_status, customer_view, now, open_review, request_human_review, \
    updates_since, why_review_needed
from step5_strands import ToolTrace, print_reply_text
from step7_fraud import FRAUD_PROMPT
from tools import _get_order, check_refund_eligibility, issue_refund, lookup_order

DEFAULT_MESSAGE = "Hi! The leather chair from order A1005 arrived with a torn seat. I'd like a refund."

REVIEW_PROMPT = FRAUD_PROMPT + """

Human review:
- When a refund needs human approval or the risk is high, call request_human_review and give the customer the review ID.
- Tell them a team member will review it within 1 to 2 business days, and that they'll get the decision here.
- If the customer asks about a review, call check_review_status.
- Messages that start with [Update from the support team] are not from the customer. They carry a reviewer's decision.
  Pass it on warmly: if approved, give the refund ID and amount; if rejected, share the reviewer's note kindly
  and offer to help with anything else. Never invent a reason the reviewer didn't give."""


class ReviewGate(HookProvider):
    """Before issue_refund runs: if a person needs to decide, open a review and cancel the call."""

    def register_hooks(self, registry, **kwargs):
        registry.add_callback(BeforeToolCallEvent, self.check)

    def check(self, event):
        if event.tool_use["name"] != "issue_refund":
            return
        args = event.tool_use["input"]
        order = _get_order(args.get("order_id", ""))
        if order is None or order["status"] == "refunded":
            return  # let issue_refund give its own error
        why, _ = why_review_needed(order, args.get("reason", ""))
        if not why:
            return
        review = open_review(order["order_id"], args.get("reason", ""), why)
        print(f"  [review gate] held issue_refund for {order['order_id']} ({why}) -> {review['review_id']}")
        event.cancel_tool = json.dumps({
            "refunded": False,
            "review_id": review["review_id"],
            "error": "Refund NOT issued. It was sent to a team member for review. Give the customer the "
                     "review ID and say they'll hear back within 1 to 2 business days. Do not mention fraud or risk.",
        })


def build_agent():
    return Agent(
        model=OllamaModel(host="http://localhost:11434", model_id=MODEL),
        tools=[tool(f) for f in (lookup_order, check_refund_eligibility, issue_refund, search_policy,
                                 score_refund_risk, request_human_review, check_review_status)],
        system_prompt=REVIEW_PROMPT,
        hooks=[ReviewGate(), ToolTrace()],
        callback_handler=print_reply_text,
    )


def deliver_updates(agent, started_at, quiet=False):
    """Hand any decided reviews from this session to the agent to tell the customer."""
    updates = updates_since(started_at)
    if not updates and not quiet:
        print("  (no decisions from the team yet)\n")
    for review in updates:
        note = (f"[Update from the support team] Review {review['review_id']} for order "
                f"{review['order_id']} was {review['status'].upper()}. Details: "
                f"{json.dumps(customer_view(review))}. Tell the customer.")
        print(f"\n  {note}\n\nAgent: ", end="", flush=True)
        agent(note)
        print("\n")


def main():
    if not DB_PATH.exists():
        print("orders.db not found. Run:  python setup_db.py")
        sys.exit(1)

    agent = build_agent()
    started_at = now()
    customer = " ".join(sys.argv[1:]) or DEFAULT_MESSAGE

    while True:
        if customer.lower() in ("quit", "exit", "q"):
            break
        if customer:
            print(f"\nCustomer: {customer}\n\nAgent: ", end="", flush=True)
            agent(customer)
            print("\n")
            deliver_updates(agent, started_at, quiet=True)
        else:
            deliver_updates(agent, started_at)
        try:
            customer = input("Customer (Enter = check for team decisions, 'quit' to exit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
