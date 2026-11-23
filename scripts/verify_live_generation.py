"""Execute the 3 live generation calls and verify live caching (Parts D3 and D4)."""

import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_setup import configure_logging
from src.rag import ChatSession

configure_logging()


def print_response(label: str, resp) -> None:
    print(f"\n{'=' * 30} {label} {'=' * 30}")
    print(f"Found: {resp.found}")
    print(f"Answer: {resp.answer}")
    print(f"Sources ({len(resp.sources)}):")
    for s in resp.sources:
        print(f"  - Citation: {s.get('citation')} | Score: {s.get('score', 0.0):.4f} | Vis: {s.get('visibility')} | Area: {s.get('practice_area')}")
        snippet = s.get('snippet', '').strip().replace('\n', ' ')
        print(f"    Snippet: {snippet[:120]}...")
    print(f"Latency: {resp.latency_ms:.1f}ms | API calls: {resp.api_calls} | Cached: {getattr(resp, 'cached', False)} | Model: {getattr(resp, 'model_used', '')}")


def main():
    canary_question = "What encryption standard is used for client data at rest?"
    fee_question = "What is the initial consultation fee?"

    # -------------------------------------------------------------
    # Call 1: Canary in Client Mode (Should be NOT FOUND / no staff docs)
    # -------------------------------------------------------------
    print("\n--- Executing Call 1: Canary in Client Mode ---")
    client_session = ChatSession(access_mode="client")
    r1 = client_session.ask(canary_question)
    print_response("Call 1: Canary in Client Mode", r1)

    print("\nPausing 6 seconds to protect Gemini free-tier rate limits...")
    time.sleep(6)

    # -------------------------------------------------------------
    # Call 2: Canary in Staff Mode (Should be FOUND citing staff doc)
    # -------------------------------------------------------------
    print("\n--- Executing Call 2: Canary in Staff Mode ---")
    staff_session = ChatSession(access_mode="staff")
    r2 = staff_session.ask(canary_question)
    print_response("Call 2: Canary in Staff Mode", r2)

    print("\nPausing 6 seconds to protect Gemini free-tier rate limits...")
    time.sleep(6)

    # -------------------------------------------------------------
    # Call 3: Consultation fee in Client Mode (Should be FOUND)
    # -------------------------------------------------------------
    print("\n--- Executing Call 3: Consultation fee in Client Mode ---")
    r3 = client_session.ask(fee_question)
    print_response("Call 3: Fee in Client Mode", r3)

    # -------------------------------------------------------------
    # Call 4: Live Cache Hit Test (Repeated fee question in Client Mode)
    # -------------------------------------------------------------
    print("\n--- Executing Call 4: Live Cache Verification (0 API calls) ---")
    r4 = client_session.ask("  what is the initial consultation fee?  ")
    print_response("Call 4: Cache Hit (Same question, normalized)", r4)

    # Verification assertions
    print("\n" + "=" * 70)
    print("LIVE VERIFICATION CHECKS SUMMARY")
    print("=" * 70)

    # Check 1: Client mode did not return staff documents
    client_sources = [s.get("source") for s in r1.sources]
    assert "Confidentiality_and_Data_Policy.pdf" not in client_sources, "Staff doc leaked into client response!"
    print("✓ Check 1: Canary in Client mode is properly gated / no staff document returned.")

    # Check 2: Staff mode found the canary fact and cited staff doc
    staff_sources = [s.get("source") for s in r2.sources]
    assert r2.found is True, "Staff mode failed to find canary!"
    assert "Confidentiality_and_Data_Policy.pdf" in staff_sources, "Staff mode failed to cite Confidentiality_and_Data_Policy.pdf!"
    print("✓ Check 2: Canary in Staff mode found and cited Confidentiality_and_Data_Policy.pdf.")

    # Check 3: Consultation fee in Client mode found
    assert r3.found is True, "Consultation fee failed in client mode!"
    assert any("5,000" in s.get("snippet", "") or "5,000" in r3.answer for s in r3.sources), "Fee PKR 5,000 not in answer/sources!"
    print("✓ Check 3: Consultation fee found in Client mode.")

    # Check 4: Cache hit properties
    assert r4.cached is True, "Live repeat query did NOT hit cache!"
    assert r4.api_calls == 0, f"Expected 0 api_calls on cache hit, got {r4.api_calls}"
    assert r4.latency_ms == 0.0, f"Expected 0.0 ms latency on cache hit, got {r4.latency_ms}"
    assert r4.answer == r3.answer, "Cached answer text differed from initial answer!"
    assert r4.sources == r3.sources, "Cached sources differed from initial sources!"
    print("✓ Check 4: Live cache hit succeeded with identical answer text, identical sources, api_calls=0, latency=0.0ms.")

    print("\nALL LIVE VERIFICATION CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
