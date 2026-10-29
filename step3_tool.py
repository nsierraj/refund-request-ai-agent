"""Step 3: give the LLM its first tool.

    python step3_tool.py
    python step3_tool.py "Has order A1006 shipped yet?"

The model is told a lookup_order function exists. It decides on its own
whether to call it and with what order ID. Our code runs the function
and hands the result back. This is one round only; the repeating loop
comes in Step 4.
"""

import json
import sqlite3
import sys

import ollama

from config import DB_PATH, MODEL, SYSTEM_PROMPT

DEFAULT_MESSAGE = "Hi, my order A1001 arrived broken. Can I get a refund?"


# --- The tool -------------------------------------------------------------
# The docstring matters: Ollama turns it into the description the model
# reads to decide when and how to use this tool.

def lookup_order(order_id: str) -> str:
    """Look up a customer's order by its order ID.

    Args:
        order_id: The order ID, for example 'A1001'

    Returns:
        The order details as JSON, or an error if no order has that ID.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM orders WHERE order_id = ?", (order_id.strip().upper(),)
    ).fetchone()
    con.close()
    if row is None:
        return json.dumps({"error": f"No order found with ID {order_id}"})
    return json.dumps(dict(row))


TOOLS = {"lookup_order": lookup_order}


# --- One round of tool use -------------------------------------------------

def main():
    if not DB_PATH.exists():
        print("orders.db not found. Run:  python setup_db.py")
        sys.exit(1)

    customer_message = " ".join(sys.argv[1:]) or DEFAULT_MESSAGE
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": customer_message},
    ]
    print(f"Customer: {customer_message}\n")

    # 1. Ask the model, and tell it which tools exist.
    response = ollama.chat(model=MODEL, messages=messages, tools=[lookup_order])

    if not response.message.tool_calls:
        print("[The model answered without using a tool]\n")
        print(f"Agent: {response.message.content}")
        return

    # 2. The model asked for a tool. Keep its request in the conversation.
    messages.append(response.message)

    # 3. Run each tool it asked for and give it the result.
    for call in response.message.tool_calls:
        name = call.function.name
        args = call.function.arguments
        print(f"[Model decided to call {name}({args})]")

        func = TOOLS.get(name)
        result = func(**args) if func else json.dumps({"error": f"Unknown tool {name}"})
        print(f"[Tool returned: {result}]\n")

        messages.append({"role": "tool", "tool_name": name, "content": result})

    # 4. Ask again, now that it has the real data.
    final = ollama.chat(model=MODEL, messages=messages)
    print(f"Agent: {final.message.content}")


if __name__ == "__main__":
    main()
