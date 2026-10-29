"""Step 4: the agent loop.

    python step4_agent.py
    python step4_agent.py "My order A1002 is falling apart, I want my money back"

Step 3 ran one round. This runs a loop:

    think -> call a tool -> read the result -> think again -> ...

until the model answers without asking for a tool. After it answers you
can keep chatting as the customer. Press Enter on an empty line to quit.

Refunds really happen here: orders.db gets updated. Run
`python setup_db.py` to reset everything.
"""

import json
import sys

import ollama

from config import DB_PATH, MODEL, STORE_NAME
from tools import AUTO_REFUND_LIMIT, RETURN_WINDOW_DAYS, TOOLS

MAX_STEPS = 8  # safety net: stop a confused agent from looping forever

DEFAULT_MESSAGE = "Hi, my order A1001 arrived broken. Can I get a refund?"

AGENT_PROMPT = f"""You are a customer support agent for {STORE_NAME}, an online store.
Be friendly, short, and clear. Greet the customer warmly. Add emojis to make the conversation friendly.

Order details:
- Only state order details (items, prices, dates, status) that a tool returned in this conversation. Never guess or invent them.
- If the customer mentions an order but you don't have its ID, ask for the order ID before looking anything up.
- If a lookup finds no order, say so and ask the customer to check the ID.

Refunds:
- You can issue refunds, but only when the customer asks for one.
- Before any refund, call check_refund_eligibility for that order.
- If it is eligible and needs no human approval, call issue_refund and give the customer the refund ID and amount.
- If it needs human approval, do NOT call issue_refund. Tell the customer a team member will review it.
- If it is not eligible, explain the reason kindly. Don't promise exceptions.
- Store policy: refunds within {RETURN_WINDOW_DAYS} days of delivery; refunds over ${AUTO_REFUND_LIMIT:.0f} need human approval.

Tools:
- Use your tools to get facts. If you don't have a tool for something, say so instead of guessing."""


def run_agent(messages):
    """The loop. Keeps going until the model replies with plain text."""
    for step in range(1, MAX_STEPS + 1):
        response = ollama.chat(model=MODEL, messages=messages,
                               tools=list(TOOLS.values()))
        msg = response.message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content  # no tool requested: this is the final answer

        for call in msg.tool_calls:
            name, args = call.function.name, call.function.arguments
            print(f"  [step {step}] model calls {name}({json.dumps(args)})")

            func = TOOLS.get(name)
            try:
                result = func(**args) if func else json.dumps({"error": f"Unknown tool {name}"})
            except TypeError as e:  # model sent wrong or missing arguments
                result = json.dumps({"error": f"Bad arguments: {e}"})

            print(f"  [step {step}] tool returns {result}")
            messages.append({"role": "tool", "tool_name": name, "content": result})

    return f"(Stopped after {MAX_STEPS} steps without a final answer.)"


def main():
    if not DB_PATH.exists():
        print("orders.db not found. Run:  python setup_db.py")
        sys.exit(1)

    messages = [{"role": "system", "content": AGENT_PROMPT}]
    customer = " ".join(sys.argv[1:]) or DEFAULT_MESSAGE

    while customer:
        print(f"\nCustomer: {customer}")
        messages.append({"role": "user", "content": customer})
        print(f"\nAgent: {run_agent(messages)}\n")
        try:
            customer = input("Customer (Enter to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
