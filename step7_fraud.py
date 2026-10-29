"""Step 7: the agent gets a fraud check.

    python make_refund_history.py     # once: fake past refunds to learn from
    python train_fraud_model.py       # once: train and save the model
    python step7_fraud.py
    python step7_fraud.py "My espresso machine from A1008 isn't what was described, refund please"

Same agent as Step 6, plus:
  - a new tool, score_refund_risk, so the agent can check risk itself
  - a hook, FraudGate, that scores every issue_refund call before it runs
    and cancels it if the risk is high, whether or not the agent checked

The prompt asks the agent to check. The hook makes sure.
"""

import json
import sys

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider
from strands.models.ollama import OllamaModel

from config import DB_PATH, MODEL
from fraud import assess, score_refund_risk
from rag import search_policy
from step5_strands import ToolTrace, print_reply_text
from step6_rag import RAG_PROMPT
from tools import check_refund_eligibility, issue_refund, lookup_order

DEFAULT_MESSAGE = "Hi, the espresso machine from order A1008 arrived dented. I'd like a refund please."

FRAUD_PROMPT = RAG_PROMPT + """

Risk checks:
- Before issue_refund, call score_refund_risk with the order ID and the customer's reason.
- If risk_level is high, do NOT call issue_refund. Tell the customer their request has been passed to a team member who will review it within 1 to 2 business days.
- Never mention fraud, risk scores, or that the request was checked. Treat every customer with the same warmth."""


class FraudGate(HookProvider):
    """Runs before every tool call. Only acts on issue_refund."""

    def register_hooks(self, registry, **kwargs):
        registry.add_callback(BeforeToolCallEvent, self.check)

    def check(self, event):
        if event.tool_use["name"] != "issue_refund":
            return
        args = event.tool_use["input"]
        try:
            result = assess(args.get("order_id", ""), args.get("reason", ""))
        except Exception as e:  # no model, bad input...: fail closed, not open
            print(f"  [fraud gate] couldn't score ({e}); blocking to be safe")
            event.cancel_tool = "Refund NOT issued: the automatic check is unavailable. A team member will review it."
            return
        if result and result["risk_level"] == "high":
            print(f"  [fraud gate] BLOCKED issue_refund: score {result['risk_score']} ({'; '.join(result['signals'])})")
            event.cancel_tool = json.dumps({
                "refunded": False,
                "error": "Refund NOT issued. This request needs review by a team member. Tell the customer "
                         "a team member will review it within 1 to 2 business days. Do not mention fraud or risk.",
            })


def build_agent():
    return Agent(
        model=OllamaModel(host="http://localhost:11434", model_id=MODEL),
        tools=[tool(f) for f in (lookup_order, check_refund_eligibility, issue_refund,
                                 search_policy, score_refund_risk)],
        system_prompt=FRAUD_PROMPT,
        hooks=[FraudGate(), ToolTrace()],
        callback_handler=print_reply_text,
    )


def main():
    if not DB_PATH.exists():
        print("orders.db not found. Run:  python setup_db.py")
        sys.exit(1)

    agent = build_agent()
    customer = " ".join(sys.argv[1:]) or DEFAULT_MESSAGE

    while customer:
        print(f"\nCustomer: {customer}\n\nAgent: ", end="", flush=True)
        agent(customer)
        print("\n")
        try:
            customer = input("Customer (Enter to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
