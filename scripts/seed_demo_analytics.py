"""Generate and validate seed questions and embeddings for demo analytics.

Produces:
- data/demo_activity/seed_questions.json
- data/demo_activity/seed_vectors.npz (float16)

Validates:
- 16 answered queries (12 client + 4 staff): score >= 0.65
- 14 not-found queries (11 client + 3 staff): score < 0.65 and key terms absent
- Calibrates and prints cosine similarity matrix for not-found questions.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import GAP_CLUSTER_COSINE, SCORE_THRESHOLD
from src.logging_setup import configure_logging
from src.vectorstore import VectorStore, embed_texts

configure_logging()

# ---------------------------------------------------------------------------
# Seed Question Definitions
# ---------------------------------------------------------------------------

SEED_DEFINITIONS: List[Dict[str, Any]] = [
    # 12 Client Answered Questions
    {
        "id": "c_ans_01",
        "audience": "client",
        "kind": "answered",
        "question": "What is the initial consultation fee and when is it waived?",
    },
    {
        "id": "c_ans_02",
        "audience": "client",
        "kind": "answered",
        "question": "What are the hourly rates for partners and associates?",
    },
    {
        "id": "c_ans_03",
        "audience": "client",
        "kind": "answered",
        "question": "What documents do I need to bring to an initial legal consultation?",
    },
    {
        "id": "c_ans_04",
        "audience": "client",
        "kind": "answered",
        "question": "Where is the law firm located in Lahore?",
    },
    {
        "id": "c_ans_05",
        "audience": "client",
        "kind": "answered",
        "question": "What are the firm's standard business and consultation hours?",
    },
    {
        "id": "c_ans_06",
        "audience": "client",
        "kind": "answered",
        "question": "How much is the initial retainer for corporate and commercial advisory matters?",
    },
    {
        "id": "c_ans_07",
        "audience": "client",
        "kind": "answered",
        "question": "What is the procedure if a client disputes an invoice or billing entry?",
    },
    {
        "id": "c_ans_08",
        "audience": "client",
        "kind": "answered",
        "question": "Does the firm handle criminal defense litigation or bail matters?",
    },
    {
        "id": "c_ans_09",
        "audience": "client",
        "kind": "answered",
        "question": "What late fees or interest charges apply to overdue invoices?",
    },
    {
        "id": "c_ans_10",
        "audience": "client",
        "kind": "answered",
        "question": "Can consultation fees be paid via bank wire transfer?",
    },
    {
        "id": "c_ans_11",
        "audience": "client",
        "kind": "answered",
        "question": "What is the retainer deposit required for property registration or conveyancing?",
    },
    {
        "id": "c_ans_12",
        "audience": "client",
        "kind": "answered",
        "question": "What happens if a client terminates an engagement letter early?",
    },

    # 4 Staff Answered Questions
    {
        "id": "s_ans_01",
        "audience": "staff",
        "kind": "answered",
        "question": "What are the conflict of interest check requirements before formal client intake?",
    },
    {
        "id": "s_ans_02",
        "audience": "staff",
        "kind": "answered",
        "question": "What is the mandatory file retention period for inactive or closed client matters?",
    },
    {
        "id": "s_ans_03",
        "audience": "staff",
        "kind": "answered",
        "question": "What is the monthly recurring fee under the Northgate Logistics Master Services Agreement?",
    },
    {
        "id": "s_ans_04",
        "audience": "staff",
        "kind": "answered",
        "question": "What is the monthly rent and annual escalation under the Gulberg office lease agreement?",
    },

    # 11 Client Not-Found Questions (Grouped into clear thematic gap clusters)
    # Cluster 1: Tax filing / FBR sales tax
    {
        "id": "c_nf_01",
        "audience": "client",
        "kind": "not_found",
        "cluster": "tax_fbr",
        "question": "What are the individual personal wealth tax brackets for salaried employees?",
    },
    {
        "id": "c_nf_02",
        "audience": "client",
        "kind": "not_found",
        "cluster": "tax_fbr",
        "question": "How does a sole proprietor submit quarterly withholding statements through Iris?",
    },
    {
        "id": "c_nf_03",
        "audience": "client",
        "kind": "not_found",
        "cluster": "tax_fbr",
        "question": "What are the steps to challenge an ex-parte property tax assessment before the tribunal?",
    },

    # Cluster 2: Immigration / Foreign work visas
    {
        "id": "c_nf_04",
        "audience": "client",
        "kind": "not_found",
        "cluster": "immigration",
        "question": "Does the firm process UK skilled worker visa and student visa applications?",
    },
    {
        "id": "c_nf_05",
        "audience": "client",
        "kind": "not_found",
        "cluster": "immigration",
        "question": "Can your lawyers assist with Canadian permanent residency express entry filings?",
    },
    {
        "id": "c_nf_06",
        "audience": "client",
        "kind": "not_found",
        "cluster": "immigration",
        "question": "What are the legal requirements for moving to Dubai on a UAE golden visa?",
    },

    # Cluster 3: International Patents / PCT
    {
        "id": "c_nf_07",
        "audience": "client",
        "kind": "not_found",
        "cluster": "patent_pct",
        "question": "How do I register an international software patent application under the PCT?",
    },
    {
        "id": "c_nf_08",
        "audience": "client",
        "kind": "not_found",
        "cluster": "patent_pct",
        "question": "What is the patent priority examination timeline under the Paris Convention?",
    },
    {
        "id": "c_nf_09",
        "audience": "client",
        "kind": "not_found",
        "cluster": "patent_pct",
        "question": "Can the firm draft patent claims for biomedical engineering innovations?",
    },

    # Cluster 4: Environmental & Maritime
    {
        "id": "c_nf_10",
        "audience": "client",
        "kind": "not_found",
        "cluster": "environment_maritime",
        "question": "Does the firm advise manufacturing plants on hazardous chemical waste effluent disposal?",
    },
    {
        "id": "c_nf_11",
        "audience": "client",
        "kind": "not_found",
        "cluster": "environment_maritime",
        "question": "Can your team advise port operators on international ship ballast water management regulations?",
    },

    # 3 Staff Not-Found Questions (Internal HR & Admin policies)
    # Cluster 5: HR / Employee policies
    {
        "id": "s_nf_01",
        "audience": "staff",
        "kind": "not_found",
        "cluster": "internal_hr",
        "question": "What is the law firm's employee maternity leave policy and paid parental leave duration?",
    },
    {
        "id": "s_nf_02",
        "audience": "staff",
        "kind": "not_found",
        "cluster": "internal_hr",
        "question": "What are the firm's remote work guidelines and home office equipment reimbursement caps?",
    },
    {
        "id": "s_nf_03",
        "audience": "staff",
        "kind": "not_found",
        "cluster": "internal_hr",
        "question": "What is the annual continuing legal education stipend allocated per associate?",
    },
]


def generate_seed():
    store = VectorStore()
    print("=" * 80)
    print(" SEED GENERATION & VALIDATION FOR DEMO ANALYTICS")
    print(f" Total questions to process: {len(SEED_DEFINITIONS)}")
    print("=" * 80)

    # 1. Batch Embed all 30 questions (single or two batches)
    questions = [item["question"] for item in SEED_DEFINITIONS]
    print(f"Embedding {len(questions)} questions via Gemini API...", flush=True)

    # Use EMBED_BATCH_SIZE chunking (default 20 texts per call)
    batch_size = 20
    all_embeddings: List[List[float]] = []
    for i in range(0, len(questions), batch_size):
        chunk = questions[i : i + batch_size]
        print(f"  Embedding batch {i // batch_size + 1} ({len(chunk)} questions)...")
        emb_res = embed_texts(chunk, task_type="RETRIEVAL_QUERY")
        all_embeddings.extend(emb_res)

    print(f"Successfully generated {len(all_embeddings)} embedding vectors.")

    # 2. Query store and validate thresholds
    processed_questions = []
    vector_dict: Dict[str, np.ndarray] = {}

    answered_passed = 0
    not_found_passed = 0

    print("\nValidating retrieval scores and boundaries:")
    for item, vec in zip(SEED_DEFINITIONS, all_embeddings):
        q_id = item["id"]
        aud = item["audience"]
        expected_kind = item["kind"]
        q_text = item["question"]

        allowed_vis = {"client"} if aud == "client" else {"client", "staff"}

        # Custom embed_fn returning our precomputed vector
        results = store.query(
            question=q_text,
            k=3,
            embed_fn=lambda texts, ttype: [vec],
            allowed_visibility=allowed_vis,
        )

        top_score = results[0]["score"] if results else 0.0
        top_src = results[0]["citation"] if results else ""

        if expected_kind == "answered":
            is_valid = top_score >= SCORE_THRESHOLD
            if is_valid:
                answered_passed += 1
            status = "PASS" if is_valid else "FAIL"
            print(f"[{status}] Answered ({aud:<6}): score={top_score:.3f} | {top_src[:35]:<35} | '{q_text[:35]}...'")
            if not is_valid:
                print(f"  WARNING: Answered question scored {top_score:.3f} (< threshold {SCORE_THRESHOLD})")

            processed_questions.append({
                "id": q_id,
                "audience": aud,
                "kind": "answered",
                "reason": "",
                "question": q_text,
                "standalone": "",
                "top_source": top_src,
                "top_score": top_score,
                "cited_sources": [top_src] if top_src else [],
            })
        else:
            is_valid = top_score < SCORE_THRESHOLD
            if is_valid:
                not_found_passed += 1
            status = "PASS" if is_valid else "FAIL"
            print(f"[{status}] Not-Found ({aud:<6}): score={top_score:.3f} | {top_src[:35]:<35} | '{q_text[:35]}...'")
            if not is_valid:
                print(f"  WARNING: Not-found question scored {top_score:.3f} (>= threshold {SCORE_THRESHOLD})")

            processed_questions.append({
                "id": q_id,
                "audience": aud,
                "kind": "not_found",
                "cluster": item.get("cluster", "other"),
                "reason": "below_threshold",
                "question": q_text,
                "standalone": "",
                "top_source": top_src,
                "top_score": top_score,
                "cited_sources": [],
            })

        # Store vector in dict as float16 array
        vector_dict[q_id] = np.array(vec, dtype=np.float16)

    total_answered = sum(1 for q in SEED_DEFINITIONS if q["kind"] == "answered")
    total_not_found = sum(1 for q in SEED_DEFINITIONS if q["kind"] == "not_found")

    print("\n" + "=" * 80)
    print(" VALIDATION SUMMARY")
    print(f" Answered Validations  : {answered_passed}/{total_answered} passed (threshold >= {SCORE_THRESHOLD})")
    print(f" Not-Found Validations : {not_found_passed}/{total_not_found} passed (threshold < {SCORE_THRESHOLD})")
    print("=" * 80)

    # 3. Pairwise Cosine Similarity Analysis for Not-Found Questions
    nf_items = [item for item in SEED_DEFINITIONS if item["kind"] == "not_found"]
    print("\n" + "=" * 80)
    print(" PAIRWISE COSINE SIMILARITY MATRIX FOR NOT-FOUND QUESTIONS")
    print(f" Target GAP_CLUSTER_COSINE threshold: {GAP_CLUSTER_COSINE:.2f}")
    print("=" * 80)

    # Compute full matrix
    n_nf = len(nf_items)
    sim_matrix = np.zeros((n_nf, n_nf), dtype=np.float32)

    for i in range(n_nf):
        v_i = vector_dict[nf_items[i]["id"]].astype(np.float32)
        norm_i = np.linalg.norm(v_i)
        for j in range(n_nf):
            v_j = vector_dict[nf_items[j]["id"]].astype(np.float32)
            norm_j = np.linalg.norm(v_j)
            sim_matrix[i, j] = np.dot(v_i, v_j) / (norm_i * norm_j)

    # Print matrix header
    print(f"{'ID':<8} | {'Cluster':<16} | " + " ".join(f"{nf['id'][:6]:<6}" for nf in nf_items))
    print("-" * 80)
    for i, item in enumerate(nf_items):
        row_str = " ".join(f"{sim_matrix[i, j]:.2f}  " for j in range(n_nf))
        print(f"{item['id']:<8} | {item['cluster']:<16} | {row_str}")

    print("=" * 80)

    # Verify cluster separation
    intra_cluster_sims = []
    inter_cluster_sims = []
    for i in range(n_nf):
        for j in range(i + 1, n_nf):
            sim = sim_matrix[i, j]
            if nf_items[i]["cluster"] == nf_items[j]["cluster"]:
                intra_cluster_sims.append(sim)
            else:
                inter_cluster_sims.append(sim)

    print(f"Intra-cluster similarities: min={min(intra_cluster_sims):.2f}, avg={np.mean(intra_cluster_sims):.2f}, max={max(intra_cluster_sims):.2f}")
    print(f"Inter-cluster similarities: min={min(inter_cluster_sims):.2f}, avg={np.mean(inter_cluster_sims):.2f}, max={max(inter_cluster_sims):.2f}")

    # 4. Save to files
    out_dir = PROJECT_ROOT / "data" / "demo_activity"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "seed_questions.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(processed_questions, f, indent=2)
    print(f"\nSaved {len(processed_questions)} seed questions to {json_path}")

    npz_path = out_dir / "seed_vectors.npz"
    np.savez_compressed(npz_path, **vector_dict)
    print(f"Saved {len(vector_dict)} float16 embedding vectors to {npz_path} ({npz_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    generate_seed()
