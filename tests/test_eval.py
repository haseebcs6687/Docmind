"""Unit tests for DocMind evaluation scoring, harness, and benchmark answer keys."""

import json
from pathlib import Path
import pytest

from eval.run_eval import generate_threshold_sweep_table, validate_benchmark_offline
from eval.scoring import (
    access_ok,
    citation_ok,
    facts_ok,
    forbidden_ok,
    found_ok,
    normalize,
    score_item,
    summarize_results,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_normalization():
    """Verify text normalization strips punctuation, lowercases, and collapses whitespace."""
    raw = "  PKR 5,000 for 45 minutes! -- Waived within 7 days...  "
    norm = normalize(raw)
    assert norm == "pkr 5,000 for 45 minutes waived within 7 days"
    assert normalize("") == ""


def test_found_ok_logic():
    """Verify found_ok truth table for positive, negative, and adversarial questions."""
    # Positive question: expected_found=True
    assert found_ok(True, "The fee is PKR 5,000.", rag_found=True) is True
    assert found_ok(True, "I couldn't find this in the uploaded documents.", rag_found=False) is False
    assert found_ok(True, "There is no information in the provided context.", rag_found=True) is False

    # Negative question: expected_found=False
    assert found_ok(False, "I couldn't find this in the uploaded documents.", rag_found=False) is True
    assert found_ok(False, "The parking is on 2nd floor.", rag_found=True) is False


def test_facts_ok_logic():
    """Verify facts_ok requires all substrings to be present in normalized answer."""
    answer = "The preliminary consultation fee is PKR 5,000 for a 45-minute consultation."
    assert facts_ok(["5,000", "45"], answer) is True
    assert facts_ok(["5,000", "waived"], answer) is False
    assert facts_ok([], answer) is True


def test_forbidden_ok_logic():
    """Verify forbidden_ok rejects any leaked strings."""
    answer = "The office is in Gulberg, Lahore. The rent is PKR 380,000 per month."
    assert forbidden_ok(["380,000", "northgate"], answer) is False
    assert forbidden_ok(["northgate", "brightline"], answer) is True
    assert forbidden_ok([], answer) is True


def test_citation_ok_logic():
    """Verify citation_ok requires at least one expected citation."""
    used_sources = ["Fee_Schedule_2026.pdf, p. 1"]
    assert citation_ok(["Fee_Schedule_2026.pdf"], used_sources) is True
    assert citation_ok(["Client_FAQ.txt"], used_sources) is False
    assert citation_ok([], used_sources) is True


def test_access_ok_isolation():
    """Verify access_ok ensures client mode never sees staff documents or forbidden strings."""
    # Safe client answer
    assert access_ok(
        category="access_control",
        forbidden_strings=["380,000"],
        answer="I couldn't find this in the uploaded documents.",
        sources=["Client_FAQ.txt, Q&A 1"],
    ) is True

    # Leaked staff document in citations
    assert access_ok(
        category="access_control",
        forbidden_strings=[],
        answer="I couldn't find this in the uploaded documents.",
        sources=["Commercial_Lease_Agreement_Gulberg_Office.docx, p. 1"],
    ) is False

    # Leaked forbidden string
    assert access_ok(
        category="access_control",
        forbidden_strings=["380,000"],
        answer="The rent is 380,000 per month.",
        sources=["Client_FAQ.txt"],
    ) is False


def test_score_item_pass_and_fail():
    """Verify score_item produces correct boolean outcome and structured report."""
    item = {
        "id": "c_fact_01",
        "category": "fact_client",
        "expected_found": True,
        "expected_facts": ["5,000"],
        "expected_citations": ["Fee_Schedule_2026.pdf"],
        "expected_top1_source": "Fee_Schedule_2026.pdf",
        "forbidden_strings": [],
        "question": "What is the consultation fee?",
    }

    # Passing response
    resp_pass = {
        "answer": "The initial consultation fee is PKR 5,000.",
        "found": True,
        "sources": [{"citation": "Fee_Schedule_2026.pdf, p. 1"}],
        "top_score": 0.88,
        "top_source": "Fee_Schedule_2026.pdf, p. 1",
        "latency_ms": 1200.0,
        "model_used": "gemini-3.5-flash-lite",
    }
    res = score_item(item, resp_pass)
    assert res["pass"] is True
    assert res["outcome"] == "PASS"
    assert res["checks"]["facts_ok"] is True

    # Failing response (missing fact)
    resp_fail = {
        "answer": "The initial consultation fee is unknown.",
        "found": True,
        "sources": [{"citation": "Fee_Schedule_2026.pdf, p. 1"}],
        "top_score": 0.88,
        "top_source": "Fee_Schedule_2026.pdf, p. 1",
    }
    res_f = score_item(item, resp_fail)
    assert res_f["pass"] is False
    assert res_f["outcome"] == "FAIL"
    assert res_f["checks"]["facts_ok"] is False


def test_summarize_results():
    """Verify summarize_results aggregates categories and calculates pass rates correctly."""
    scored = [
        {"category": "fact_client", "pass": True, "outcome": "PASS"},
        {"category": "fact_client", "pass": False, "outcome": "FAIL"},
        {"category": "not_in_docs", "pass": True, "outcome": "PASS"},
    ]
    summary = summarize_results(scored)
    assert summary["total_questions"] == 3
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["overall_pass_rate"] == 66.7
    assert summary["categories"]["fact_client"]["pass_rate"] == 50.0
    assert summary["categories"]["not_in_docs"]["pass_rate"] == 100.0


def test_benchmark_offline_validation():
    """Verify validate_benchmark_offline passes on questions.json with 0 API calls."""
    q_path = PROJECT_ROOT / "eval" / "questions.json"
    assert validate_benchmark_offline(q_path) is True


def test_threshold_sweep_table_generation():
    """Verify threshold sweep table format and default marker."""
    scored = [
        {
            "id": "c_fact_01",
            "category": "fact_client",
            "pass": True,
            "details": {"top_score": 0.72},
        },
        {
            "id": "c_nf_01",
            "category": "not_in_docs",
            "pass": True,
            "details": {"top_score": 0.58},
        },
    ]
    table = generate_threshold_sweep_table(scored, start_th=0.60, end_th=0.70, step=0.05)
    assert "| Threshold | Simulated Pass Rate |" in table
    assert "0.65" in table
    assert "(Default)" in table
