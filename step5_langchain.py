"""Step 5b: the same agent, rebuilt with LangChain.

    python step5_langchain.py
    python step5_langchain.py "My order A1005 has a torn seat, refund please"

Same model, same tools, same prompt as Steps 4 and 5. Compare it with
step5_strands.py:

- create_agent() runs the loop for you, like Strands' Agent(). Under the
  hood it's a LangGraph graph: a model node and a tools node, with an
  edge back to the model while it keeps asking for tools. That's Step 4's
  for-loop, drawn as a graph.
- State is explicit. Strands kept the conversation inside the Agent
  object. Here you pass the message list in and get the full list back,
  so this file holds the history.
- The plain functions from tools.py go in as they are. LangChain reads
  the type hints and docstrings to build the tool schemas.
"""

import json
import sys

from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langgraph.errors import GraphRecursionError

from config import DB_PATH, MODEL
from step4_agent import AGENT_PROMPT, DEFAULT_MESSAGE, MAX_STEPS
from tools import check_refund_eligibility, issue_refund, lookup_order

# Step 4 counted loop rounds. LangGraph counts node runs, and one round is
# two nodes (model, then tools), plus the final model answer.
RECURSION_LIMIT = 2 * MAX_STEPS + 1


def build_agent():
    # init_chat_model(f"ollama:{MODEL}") would also work. ChatOllama is
    # used for one Ollama-specific setting: reasoning=True moves qwen3's
    # <think>...</think> text out of the reply and into
    # additional_kwargs["reasoning_content"].
    model = ChatOllama(model=MODEL, reasoning=True)
    return create_agent(
        model,
        tools=[lookup_order, check_refund_eligibility, issue_refund],
        system_prompt=AGENT_PROMPT,
    )


def print_trace(new_messages):
    """Print this turn's tool calls, like Step 4's [step N] lines."""
    for m in new_messages:
        if m.type == "ai" and m.tool_calls:
            for call in m.tool_calls:
                print(f"  [tool] {call['name']}({json.dumps(call['args'])})")
        elif m.type == "tool":
            print(f"  [tool] returns {m.content}")


def main():
    if not DB_PATH.exists():
        print("orders.db not found. Run:  python setup_db.py")
        sys.exit(1)

    agent = build_agent()
    messages = []  # the conversation lives here, not inside the agent
    customer = " ".join(sys.argv[1:]) or DEFAULT_MESSAGE

    while customer:
        print(f"\nCustomer: {customer}\n")
        messages.append({"role": "user", "content": customer})
        start = len(messages)

        try:
            result = agent.invoke({"messages": messages},
                                  config={"recursion_limit": RECURSION_LIMIT})
        except GraphRecursionError:
            print(f"Agent: (Stopped after {MAX_STEPS} steps without a final answer.)\n")
            break

        messages = result["messages"]  # full history: yours plus everything new
        print_trace(messages[start:])
        print(f"\nAgent: {messages[-1].content}\n")

        try:
            customer = input("Customer (Enter to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
