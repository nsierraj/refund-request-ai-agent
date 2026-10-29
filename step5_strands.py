"""Step 5: the same agent, rebuilt with Strands Agents.

    python step5_strands.py
    python step5_strands.py "My order A1005 has a torn seat, refund please"

Same model, same tools, same prompt as Step 4. The difference: you no
longer write the loop. Strands runs think -> call tool -> read result ->
repeat for you, keeps the conversation history, and builds the tool
schemas from your docstrings.

Strands is AWS's open-source agent SDK. An agent written like this is
what teams deploy to Amazon Bedrock AgentCore; there you'd swap
OllamaModel for a Bedrock model and keep everything else.
"""

import json
import sys

from strands import Agent, tool
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider
from strands.models.ollama import OllamaModel

from config import DB_PATH, MODEL
from step4_agent import AGENT_PROMPT, DEFAULT_MESSAGE
from tools import check_refund_eligibility, issue_refund, lookup_order


# Hooks let you watch (or block) what the agent does without touching the
# loop. This one prints every tool call, like Step 4's [step N] lines.
class ToolTrace(HookProvider):
    def register_hooks(self, registry, **kwargs):
        registry.add_callback(BeforeToolCallEvent, self.before_tool)
        registry.add_callback(AfterToolCallEvent, self.after_tool)

    def before_tool(self, event):
        t = event.tool_use
        print(f"\n  [tool] {t['name']}({json.dumps(t['input'])})")

    def after_tool(self, event):
        text = " ".join(c.get("text", "") for c in event.result.get("content", []))
        print(f"  [tool] returns {text}")


# Callback handlers see the raw stream. Strands' default one also prints
# "Tool #1: ..." lines; this one prints only the reply text, since the
# hooks above already show the tools.
def print_reply_text(**event):
    if "data" in event:
        print(event["data"], end="", flush=True)


def build_agent():
    return Agent(
        model=OllamaModel(host="http://localhost:11434", model_id=MODEL),
        # tool() reads each function's type hints and docstring, the same
        # thing Ollama did for you in Step 4. tools.py is unchanged.
        tools=[tool(f) for f in (lookup_order, check_refund_eligibility, issue_refund)],
        system_prompt=AGENT_PROMPT,
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
        agent(customer)  # the whole loop is this one call; the reply streams as it's written
        print("\n")
        try:
            customer = input("Customer (Enter to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
