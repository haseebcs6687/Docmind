"""Scripted multi-turn conversational demo for DocMind ChatSession."""

import os
import sys
import time

# Ensure proper stdout encoding on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.logging_setup import configure_logging
from src.rag import ChatSession

configure_logging()

CONVERSATION_TURNS = [
    "What are the hourly rates for each lawyer level?",
    "And what about the paralegal?",
    "What retainer do you require for family law matters?",
    "Is it refundable if unused?",
    "thanks!",
    "Do you handle immigration cases?",
    "And parking?",
]


def main() -> None:
    session = ChatSession()

    print("=" * 80)
    print(" DOCMIND MULTI-TURN CHAT SESSION DEMO")
    print("=" * 80)
    print(f"Total turns: {len(CONVERSATION_TURNS)} | Pause between turns: 6.0s\n")

    for idx, question in enumerate(CONVERSATION_TURNS, start=1):
        print("=" * 80)
        print(f"Turn {idx}")
        print(f"Question: {question}")

        try:
            resp = session.ask(question)
        except Exception as e:
            print(f"\n[Error] Chat turn failed with exception: {e.__class__.__name__}: {e}")
            sys.exit(1)

        print(f"Standalone Question: {resp.standalone_question}")
        print(f"Found: {'Yes' if resp.found else 'No'}")
        print(f"\nAnswer:\n{resp.answer}\n")

        if resp.found and resp.sources:
            print("Citations:")
            for s in resp.sources:
                citation_label = s.get("citation", "Unknown")
                print(f"  - [{citation_label}]")
        elif not resp.found:
            print("Citations: None (Answer not found in documents)")
        else:
            print("Citations: None (Small-talk response)")

        print(f"\nAPI Calls: {resp.api_calls} | Latency: {resp.latency_ms:.1f} ms")
        print("=" * 80)
        print()

        # Pause between turns to respect rate limits
        if idx < len(CONVERSATION_TURNS):
            time.sleep(6.0)


if __name__ == "__main__":
    main()
