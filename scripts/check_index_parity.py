"""Parity check comparing retrieval on persistent Chroma store vs zero-API imported export store."""

import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.shared_index import ensure_shared_index
from src.vectorstore import VectorStore, embed_texts


def run_parity_check() -> bool:
    print("=" * 80)
    print(" INDEX PARITY CHECK: PERSISTENT CHROMA VS ZERO-API EXPORT IMPORT")
    print("=" * 80)

    # 1. Load questions
    q_file = PROJECT_ROOT / "eval" / "questions.json"
    with open(q_file, "r", encoding="utf-8") as f:
        questions: List[Dict[str, Any]] = json.load(f)

    print(f"Loaded {len(questions)} evaluation benchmark questions.")

    # 2. Persistent store
    persistent_store = VectorStore()
    p_count = persistent_store.count()
    print(f"Persistent VectorStore chunks: {p_count}")

    # 3. Create temp store and load from export
    import chromadb
    temp_dir = tempfile.mkdtemp(prefix="docmind_parity_")
    try:
        temp_client = chromadb.PersistentClient(path=temp_dir)
        temp_store = VectorStore(client=temp_client)
        loaded = ensure_shared_index(temp_store)
        assert loaded, "ensure_shared_index failed to load export!"
        t_count = temp_store.count()
        print(f"Temporary VectorStore chunks loaded from export: {t_count} (0 API calls)")
        assert p_count == t_count, f"Chunk count mismatch: {p_count} vs {t_count}"

        # 4. Embed all 38 questions in at most 2 batch requests
        print("Embedding 38 questions in at most 2 batches (batch_size=20)...")
        q_texts = [q["question"] for q in questions]
        all_embeddings = embed_texts(q_texts, task_type="RETRIEVAL_QUERY", batch_size=20, sleep_seconds=0.5)
        print(f"Successfully obtained {len(all_embeddings)} query embeddings.")

        # 5. Query both stores and compare top-1
        all_passed = True
        results_rows = []

        for idx, (q, q_vec) in enumerate(zip(questions, all_embeddings), start=1):
            qid = q["id"]
            aud = q["audience"]
            vis = {"client"} if aud == "client" else None

            p_res = persistent_store.query_by_vector(q_vec, k=1, allowed_visibility=vis)
            t_res = temp_store.query_by_vector(q_vec, k=1, allowed_visibility=vis)

            p_src = p_res[0]["source"] if p_res else "(empty)"
            t_src = t_res[0]["source"] if t_res else "(empty)"
            p_score = p_res[0]["score"] if p_res else 0.0
            t_score = t_res[0]["score"] if t_res else 0.0

            src_match = (p_src == t_src)
            score_diff = abs(p_score - t_score)
            score_match = (score_diff < 0.005)

            is_match = src_match and score_match
            if not is_match:
                all_passed = False

            results_rows.append({
                "id": qid,
                "audience": aud,
                "p_src": p_src,
                "t_src": t_src,
                "p_score": p_score,
                "t_score": t_score,
                "diff": score_diff,
                "match": is_match,
            })

        # 6. Print parity table
        print("\n" + "=" * 90)
        print(f"{'ID':<15} | {'Audience':<8} | {'Persistent Top-1':<32} | {'Diff':<8} | {'Parity':<6}")
        print("-" * 90)
        for r in results_rows:
            parity_str = "MATCH" if r["match"] else "MISMATCH"
            print(f"{r['id']:<15} | {r['audience']:<8} | {r['p_src']:<32} | {r['diff']:<8.4f} | {parity_str:<6}")
        print("=" * 90)

        matches = sum(1 for r in results_rows if r["match"])
        print(f"\nParity Outcome: {matches}/{len(results_rows)} MATCHED ({matches/len(results_rows)*100:.1f}%)")
        print(f"Max score difference observed: {max(r['diff'] for r in results_rows):.6f}")

        if all_passed:
            print("\nALL 38 QUESTIONS ACHIEVED 100% RETRIEVAL PARITY!")
        else:
            print("\nWARNING: Some questions exhibited parity mismatches!")

        return all_passed
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    ok = run_parity_check()
    sys.exit(0 if ok else 1)
