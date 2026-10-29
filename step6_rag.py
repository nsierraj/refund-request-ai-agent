"""Step 6: the agent gets a rulebook.

    ollama pull nomic-embed-text      # once: the embedding model
    python step6_rag.py
    python step6_rag.py "My espresso machine stopped working, it's been about two months. Order A1008"

Same Strands agent as Step 5, plus one tool: search_policy. Before
answering a policy question, the agent searches policies/ and answers from
what it finds. Edit a file in policies/ and the next search picks it up.
"""

import sys

from strands import Agent, tool
from strands.models.ollama import OllamaModel

from config import DB_PATH, MODEL, STORE_NAME
from rag import search_policy
from step5_strands import ToolTrace, print_reply_text
from tools import check_refund_eligibility, issue_refund, lookup_order

DEFAULT_MESSAGE = "Hi! My lamp from order A1001 arrived cracked. Do I have to mail it back, and when will I see the money?"

RAG_PROMPT = f"""You are a customer support agent for {STORE_NAME}, an online store.
Be friendly, short, and clear. Greet the customer warmly. Add emojis to make the conversation friendly.

Order details:
- Only state order details (items, prices, dates, status) that a tool returned in this conversation. Never guess or invent them.
- If the customer mentions an order but you don't have its ID, ask for the order ID before looking anything up.
- If a lookup finds no order, say so and ask the customer to check the ID.

Store policy:
- For ANY question about what the store allows, timelines, return shipping, warranty, gifts or how refunds work, call search_policy first.
- Answer policy questions only from what search_policy returned, and mention which policy you used (for example "per our refunds policy").
- If search_policy doesn't cover the question, say you're not sure and offer to pass it to the team. Don't make up policy.

Refunds:
- You can issue refunds, but only when the customer asks for one.
- Before any refund, call check_refund_eligibility for that order.
- If it is eligible and needs no human approval, call issue_refund and give the customer the refund ID and amount.
- If it needs human approval, do NOT call issue_refund. Tell the customer a team member will review it.
- If it is not eligible, explain the reason kindly. Don't promise exceptions."""


def build_agent():
    return Agent(
        model=OllamaModel(host="http://localhost:11434", model_id=MODEL),
        tools=[tool(f) for f in (lookup_order, check_refund_eligibility, issue_refund, search_policy)],
        system_prompt=RAG_PROMPT,
        hooks=[ToolTrace()],
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
