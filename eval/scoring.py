"""Pure scoring and evaluation functions for DocMind evaluation harness."""

import re
from typing import Any, Dict, List, Optional, Set

# Staff-only documents that must NEVER appear in client-mode retrieval/citations
STAFF_ONLY_DOCUMENTS: Set[str] = {
    "Commercial_Lease_Agreement_Gulberg_Office.docx",
    "Master_Services_Agreement_Northgate.pdf",
    "Client_Intake_SOP.pdf",
    "Confidentiality_and_Data_Policy.pdf",
}

# Standard phrases indicating not-found answers
NOT_FOUND_PHRASES: List[str] = [
    "couldn't find this in the uploaded documents",
    "could not find this in the uploaded documents",
    "not found in the uploaded documents",
    "not mentioned in the provided documents",
    "not stated in the uploaded documents",
    "does not contain information",
    "no information",
    "not found in the provided context",
]


def normalize(text: str) -> str:
    """Normalize text for robust substring matching: lowercase, strip punctuation, collapse whitespace."""
    if not text:
        return ""
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("—", " ").replace("–", " ")
    text = re.sub(r"\.{2,}", " ", text)
    text = re.sub(r"[^\w\s%.,]", " ", text)
    return " ".join(text.split())


def is_not_found_answer(answer: str) -> bool:
    """Check if an answer indicates that the information was not found in the documents."""
    norm = normalize(answer)
    return any(phrase in norm for phrase in NOT_FOUND_PHRASES)


def found_ok(expected_found: bool, answer: str, rag_found: Optional[bool] = None) -> bool:
    """Check whether the found status matches expectation."""
    is_nf = is_not_found_answer(answer)
    if rag_found is not None:
        if expected_found:
            return rag_found and not is_nf
        else:
            return (not rag_found) or is_nf
    else:
        if expected_found:
            return not is_nf
        else:
            return is_nf


def facts_ok(expected_facts: List[str], answer: str) -> bool:
    """Check whether all expected factual substrings are present in the answer text.
    
    Supports alternative substrings separated by '|' (e.g., '14:00|2:00|2 pm').
    """
    if not expected_facts:
        return True
    norm_answer = normalize(answer)
    for fact in expected_facts:
        if "|" in fact:
            alts = fact.split("|")
            if not any(normalize(alt) in norm_answer for alt in alts):
                return False
        else:
            norm_fact = normalize(fact)
            if norm_fact not in norm_answer:
                return False
    return True


def forbidden_ok(forbidden_strings: List[str], answer: str) -> bool:
    """Check that NONE of the forbidden strings appear in the answer text."""
    if not forbidden_strings:
        return True
    norm_answer = normalize(answer)
    for forbidden in forbidden_strings:
        norm_forbidden = normalize(forbidden)
        if norm_forbidden in norm_answer:
            return False
    return True


def citation_ok(expected_citations: List[str], used_sources: List[str], answer: str = "") -> bool:
    """Check that citations match expected document sources."""
    if not expected_citations:
        return True
    
    # Check used_sources list
    all_sources = " ".join(used_sources or []).lower() + " " + (answer or "").lower()
    for exp in expected_citations:
        if exp.lower() in all_sources:
            return True
    return False


def top1_ok(expected_top1: Optional[str], actual_top1: Optional[str]) -> bool:
    """Check whether the top-1 retrieved source matches expected top source."""
    if not expected_top1:
        return True
    if not actual_top1:
        return False
    return expected_top1.lower() in actual_top1.lower()


def access_ok(category: str, forbidden_strings: List[str], answer: str, sources: List[str]) -> bool:
    """Verify role-based access isolation for access_control category."""
    if category != "access_control":
        return True
    
    # 1. No forbidden strings leaked in answer
    if not forbidden_ok(forbidden_strings, answer):
        return False
    
    # 2. No staff-only document in retrieved/used sources
    sources_str = " ".join(sources or [])
    for staff_doc in STAFF_ONLY_DOCUMENTS:
        if staff_doc in sources_str:
            return False
            
    return True


def score_item(item: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
    """Score a single question response against its benchmark specification.
    
    Args:
        item: Benchmark question dictionary from questions.json.
        response: System response dictionary containing:
            - answer (str)
            - found (bool)
            - sources (list of str or dicts)
            - top_score (float)
            - top_source (str)
            - error (str, optional)
            
    Returns:
        Scored result dictionary with pass/fail and per-check boolean flags.
    """
    if response.get("error"):
        return {
            "id": item["id"],
            "category": item["category"],
            "pass": False,
            "outcome": "ERROR",
            "error_message": response["error"],
            "checks": {
                "found_ok": False,
                "facts_ok": False,
                "forbidden_ok": False,
                "citation_ok": False,
                "top1_ok": False,
                "access_ok": False,
            },
            "details": {
                "question": item["question"],
                "answer": response.get("answer", f"ERROR: {response['error']}"),
                "found": False,
                "sources": [],
                "top_score": 0.0,
                "top_source": None,
                "latency_ms": 0.0,
                "model_used": "",
            },
        }

    answer = response.get("answer", "")
    rag_found = response.get("found")
    sources = response.get("sources", [])
    used_source_strings: List[str] = []
    for s in sources:
        if isinstance(s, dict):
            used_source_strings.append(s.get("citation") or s.get("source") or "")
        else:
            used_source_strings.append(str(s))

    actual_top1 = response.get("top_source", "")
    if not actual_top1 and used_source_strings:
        actual_top1 = used_source_strings[0]

    # Evaluate individual checks
    ch_found = found_ok(item["expected_found"], answer, rag_found)
    ch_facts = facts_ok(item.get("expected_facts", []), answer)
    ch_forbidden = forbidden_ok(item.get("forbidden_strings", []), answer)
    ch_citation = citation_ok(item.get("expected_citations", []), used_source_strings, answer)
    ch_top1 = top1_ok(item.get("expected_top1_source"), actual_top1)
    ch_access = access_ok(item["category"], item.get("forbidden_strings", []), answer, used_source_strings)

    # All applicable checks must pass
    all_pass = ch_found and ch_facts and ch_forbidden and ch_citation and ch_top1 and ch_access
    outcome = "PASS" if all_pass else "FAIL"

    return {
        "id": item["id"],
        "category": item["category"],
        "pass": all_pass,
        "outcome": outcome,
        "checks": {
            "found_ok": ch_found,
            "facts_ok": ch_facts,
            "forbidden_ok": ch_forbidden,
            "citation_ok": ch_citation,
            "top1_ok": ch_top1,
            "access_ok": ch_access,
        },
        "details": {
            "question": item["question"],
            "answer": answer,
            "found": rag_found,
            "sources": used_source_strings,
            "top_score": response.get("top_score", 0.0),
            "top_source": actual_top1,
            "latency_ms": response.get("latency_ms", 0.0),
            "model_used": response.get("model_used", ""),
        },
    }


def summarize_results(scored_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-item scores into category breakdowns and overall metrics."""
    total = len(scored_items)
    passed = sum(1 for it in scored_items if it["pass"])
    errors = sum(1 for it in scored_items if it["outcome"] == "ERROR")
    failures = total - passed - errors

    categories: Dict[str, Dict[str, Any]] = {}
    for it in scored_items:
        cat = it["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0, "failed": 0, "errors": 0}
        categories[cat]["total"] += 1
        if it["pass"]:
            categories[cat]["passed"] += 1
        elif it["outcome"] == "ERROR":
            categories[cat]["errors"] += 1
        else:
            categories[cat]["failed"] += 1

    category_summary = {}
    for cat, counts in categories.items():
        rate = (counts["passed"] / counts["total"] * 100.0) if counts["total"] > 0 else 0.0
        category_summary[cat] = {
            "total": counts["total"],
            "passed": counts["passed"],
            "failed": counts["failed"],
            "errors": counts["errors"],
            "pass_rate": round(rate, 1),
        }

    overall_pass_rate = (passed / total * 100.0) if total > 0 else 0.0

    return {
        "total_questions": total,
        "passed": passed,
        "failed": failures,
        "errors": errors,
        "overall_pass_rate": round(overall_pass_rate, 1),
        "categories": category_summary,
    }
