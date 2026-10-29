"""Step 2: talk to the LLM from code.

    python step2_chat.py
    python step2_chat.py "Where is my order A1003?"

Notice: the model has no access to your orders yet. Ask about a
specific order and see whether it admits that or makes something up.
"""

import sys
import time

import ollama

from config import MODEL, SYSTEM_PROMPT

DEFAULT_MESSAGE = "Hi, my lamp arrived broken. Can I get my money back?"


def main():
    customer_message = " ".join(sys.argv[1:]) or DEFAULT_MESSAGE

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": customer_message},
    ]

    print(f"Customer: {customer_message}\n")
    print(f"Agent ({MODEL}): ", end="", flush=True)

    start = time.time()
    # stream=True prints words as the model produces them,
    # one guess at a time, the "next word" idea in action.
    for chunk in ollama.chat(model=MODEL, messages=messages, stream=True):
        print(chunk.message.content, end="", flush=True)

    print(f"\n\n[{time.time() - start:.1f}s]")


if __name__ == "__main__":
    main()
