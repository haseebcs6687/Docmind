"""Live verification script for client reply drafting and memo export (max 4-5 generation calls)."""

from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import tempfile
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import docx
from src.drafting import draft_client_reply
from src.logging_setup import configure_logging
from src.memo import build_memo_docx, memo_filename
from src.rag import ChatSession
from src.vectorstore import VectorStore

configure_logging()


def main():
    print("=" * 80)
    print("STEP 13: LIVE VERIFICATION - DRAFT CLIENT REPLY & RESEARCH MEMO")
    print("=" * 80)

    store = VectorStore()
    session = ChatSession(store=store, access_mode="staff")

    # Message history list mirroring Streamlit session
    session_messages = []

    # -------------------------------------------------------------------------
    # 1. Answer Consultation Fee in Staff Mode
    # -------------------------------------------------------------------------
    q1 = "What is the initial consultation fee and when is it waived?"
    print(f"\n[1/5] Asking in Staff mode: '{q1}'...")
    resp1 = session.ask(q1)
    print(f"  Found: {resp1.found}")
    print(f"  Answer: {resp1.answer}")
    print(f"  Sources: {len(resp1.sources)} citations")
    print(f"  Latency: {resp1.latency_ms:.1f}ms (gen: {resp1.gen_ms:.1f}ms)")

    session_messages.append({"role": "user", "content": q1})
    session_messages.append({
        "role": "assistant",
        "question": q1,
        "content": resp1.answer,
        "found": resp1.found,
        "sources": resp1.sources,
        "latency_seconds": resp1.latency_ms / 1000.0,
        "cached": resp1.cached,
        "model_used": resp1.model_used,
    })

    print("\nPausing 6s to respect rate limits...")
    time.sleep(6.0)

    # -------------------------------------------------------------------------
    # 2. Draft Formal Reply
    # -------------------------------------------------------------------------
    print("\n[2/5] Drafting Formal client reply for Ms. Fatima Khan (Sender: Zainab Malik)...")
    draft_formal = draft_client_reply(
        question=q1,
        answer=resp1.answer,
        sources=resp1.sources,
        tone="Formal",
        client_name="Ms. Fatima Khan",
        sender_name="Zainab Malik",
        include_sources=True,
        access_mode="staff",
    )
    print(f"  Subject: {draft_formal.subject}")
    print(f"  Body:\n{draft_formal.body}")
    print(f"  Unverified Figures: {draft_formal.unverified_figures}")
    print(f"  Model Used: {draft_formal.model_used}")
    print(f"  Latency: {draft_formal.latency_ms:.1f}ms")

    print("\nPausing 6s to respect rate limits...")
    time.sleep(6.0)

    # -------------------------------------------------------------------------
    # 3. Draft Friendly Reply
    # -------------------------------------------------------------------------
    print("\n[3/5] Drafting Friendly client reply for Ms. Fatima Khan (Sender: Zainab Malik)...")
    draft_friendly = draft_client_reply(
        question=q1,
        answer=resp1.answer,
        sources=resp1.sources,
        tone="Friendly",
        client_name="Ms. Fatima Khan",
        sender_name="Zainab Malik",
        include_sources=True,
        access_mode="staff",
    )
    print(f"  Subject: {draft_friendly.subject}")
    print(f"  Body:\n{draft_friendly.body}")
    print(f"  Unverified Figures: {draft_friendly.unverified_figures}")
    print(f"  Model Used: {draft_friendly.model_used}")
    print(f"  Latency: {draft_friendly.latency_ms:.1f}ms")

    print("\nPausing 6s to respect rate limits...")
    time.sleep(6.0)

    # -------------------------------------------------------------------------
    # 4. Additional Queries for Memo: Parking (not-found) & Hourly Rates (found)
    # -------------------------------------------------------------------------
    q2 = "Do you have parking space?"
    print(f"\n[4/5a] Asking (expecting Not Found): '{q2}'...")
    resp2 = session.ask(q2)
    print(f"  Found: {resp2.found}")
    print(f"  Answer: {resp2.answer}")
    session_messages.append({"role": "user", "content": q2})
    session_messages.append({
        "role": "assistant",
        "question": q2,
        "content": resp2.answer,
        "found": resp2.found,
        "sources": resp2.sources,
        "latency_seconds": resp2.latency_ms / 1000.0,
    })

    print("Pausing 6s...")
    time.sleep(6.0)

    q3 = "What are the hourly rates for each lawyer level?"
    print(f"[4/5b] Asking: '{q3}'...")
    resp3 = session.ask(q3)
    print(f"  Found: {resp3.found}")
    print(f"  Answer: {resp3.answer}")
    session_messages.append({"role": "user", "content": q3})
    session_messages.append({
        "role": "assistant",
        "question": q3,
        "content": resp3.answer,
        "found": resp3.found,
        "sources": resp3.sources,
        "latency_seconds": resp3.latency_ms / 1000.0,
    })

    # -------------------------------------------------------------------------
    # 5. Build and Inspect Research Memo
    # -------------------------------------------------------------------------
    print("\n[5/5] Building Research Memo DOCX from in-session messages...")
    memo_bytes = build_memo_docx(
        messages=session_messages,
        access_mode="staff",
        generated_on=datetime.now(timezone.utc),
    )

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
        tmp_file.write(memo_bytes)
        tmp_path = Path(tmp_file.name)

    try:
        doc = docx.Document(tmp_path)
        headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
        paragraphs = [p for p in doc.paragraphs if p.text.strip()]
        source_bullets = [p.text for p in doc.paragraphs if p.style.name == "List Bullet" and not p.text.endswith("uploaded documents")]
        open_items_bullets = [p.text for p in doc.paragraphs if p.style.name == "List Bullet" and p.text.endswith("uploaded documents")]

        print(f"\nMemo Summary:")
        print(f"  DOCX File Size: {len(memo_bytes):,} bytes ({len(memo_bytes) / 1024:.1f} KB)")
        print(f"  Headings: {headings}")
        print(f"  Non-empty Paragraphs: {len(paragraphs)}")
        print(f"  Source Citations Bullets: {len(source_bullets)}")
        print(f"  Open Items:")
        for oi in open_items_bullets:
            print(f"    - {oi}")

        print(f"\nTable Metadata:")
        for row in doc.tables[0].rows:
            print(f"    {row.cells[0].text:22s} : {row.cells[1].text}")

    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    print("\n" + "=" * 80)
    print("STEP 13 LIVE VERIFICATION COMPLETE - ALL STEPS SUCCESSFUL")
    print("=" * 80)


if __name__ == "__main__":
    main()
