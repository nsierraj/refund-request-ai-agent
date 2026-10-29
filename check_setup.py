"""Step 1 check: is Ollama running, and is the model downloaded?"""

import sys

import ollama

from config import MODEL


def main():
    try:
        installed = [m.model for m in ollama.list().models]
    except Exception:
        print("Can't reach Ollama. Start it in another terminal tab with:  ollama serve")
        sys.exit(1)

    print("Ollama is running. Models on this Mac:")
    for name in installed or ["(none yet)"]:
        print(f"  {name}")

    if not any(name == MODEL or name.startswith(MODEL + ":") for name in installed):
        print(f"\n{MODEL} isn't downloaded yet. Run:  ollama pull {MODEL}")
        sys.exit(1)

    print(f"\nReady. Steps 2 and 3 will use {MODEL}.")


if __name__ == "__main__":
    main()
