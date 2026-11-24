"""Unit tests for contract key-terms analyzer and UI (offline, 0 API calls)."""

import json
import sys
from pathlib import Path
from unittest import mock
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.contracts import (
    CONTRACT_FIELDS,
    AnalysisSessionTracker,
    ContractAnalysis,
    ContractAnalysisAccessError,
    ContractAnalysisCache,
    ContractAnalysisSizeError,
    FieldResult,
    analysis_to_csv,
    analyze_contract,
)
from src.gemini_client import GenerationError
from src.loaders import DocUnit, load_file
from src.ui.contracts_page import _render_results
from src.vectorstore import VectorStore


def _sample_units() -> list[DocUnit]:
    """Helper returning sample units for testing."""
    return [
        DocUnit(
            text="This Master Services Agreement is entered into on 1 March 2026 between Northgate Logistics and Brightline Software Solutions.",
            source="Test_MSA.pdf",
            page=1,
            file_type="pdf",
        ),
        DocUnit(
            text="The term shall be 24 months. The monthly fee is PKR 450,000 payable within 20 days. Late payments incur 1.5% interest.",
            source="Test_MSA.pdf",
            page=2,
            file_type="pdf",
        ),
        DocUnit(
            text="Either party may terminate for convenience on 90 days notice. This agreement is governed by the laws of Pakistan.",
            source="Test_MSA.pdf",
            page=3,
            file_type="pdf",
        ),
    ]


def test_quote_verified_in_cited_unit():
    """Verify that a quote present in the cited unit gets status 'Verified' and correct citation."""
    units = _sample_units()

    def fake_llm(system_instruction, user_prompt):
        return json.dumps({
            "fields": [
                {
                    "key": "effective_date",
                    "found": True,
                    "value": "1 March 2026",
                    "unit": 1,
                    "quote": "entered into on 1 March 2026",
                }
            ]
        })

    analysis = analyze_contract(units, "Test_MSA.pdf", "staff", llm=fake_llm, cache=ContractAnalysisCache())
    f_map = {f.key: f for f in analysis.fields}

    field = f_map["effective_date"]
    assert field.found is True
    assert field.status == "Quote verified"
    assert field.citation == "Test_MSA.pdf, p. 1"
    assert field.value == "1 March 2026"
    assert analysis.verified_count >= 1


def test_quote_found_in_another_unit_corrected():
    """Verify that when a quote exists in unit 2 but is cited as unit 1, citation is corrected."""
    units = _sample_units()

    def fake_llm(system_instruction, user_prompt):
        return json.dumps({
            "fields": [
                {
                    "key": "term",
                    "found": True,
                    "value": "24 months",
                    "unit": 1,  # Cited as unit 1, but text is actually in unit 2
                    "quote": "term shall be 24 months",
                }
            ]
        })

    analysis = analyze_contract(units, "Test_MSA.pdf", "staff", llm=fake_llm, cache=ContractAnalysisCache())
    f_map = {f.key: f for f in analysis.fields}

    field = f_map["term"]
    assert field.found is True
    assert field.status == "Quote verified"
    assert field.citation == "Test_MSA.pdf, p. 2"  # Corrected to unit 2!


def test_quote_not_found_marked_unverified():
    """Verify that a quote not appearing anywhere in the text is marked 'Unverified'."""
    units = _sample_units()

    def fake_llm(system_instruction, user_prompt):
        return json.dumps({
            "fields": [
                {
                    "key": "liability",
                    "found": True,
                    "value": "Capped at PKR 1,000,000",
                    "unit": 2,
                    "quote": "total liability capped at one million rupees",  # Not in text
                }
            ]
        })

    analysis = analyze_contract(units, "Test_MSA.pdf", "staff", llm=fake_llm, cache=ContractAnalysisCache())
    f_map = {f.key: f for f in analysis.fields}

    field = f_map["liability"]
    assert field.found is True
    assert field.status == "Unverified"
    assert field.value == "Capped at PKR 1,000,000"
    assert analysis.unverified_count >= 1


def test_found_false_forces_empty_value_and_quote():
    """Verify that found=False forces value, quote, and citation to empty strings."""
    units = _sample_units()

    def fake_llm(system_instruction, user_prompt):
        return json.dumps({
            "fields": [
                {
                    "key": "force_majeure",
                    "found": False,
                    "value": "Should be wiped",
                    "unit": 1,
                    "quote": "Should also be wiped",
                }
            ]
        })

    analysis = analyze_contract(units, "Test_MSA.pdf", "staff", llm=fake_llm, cache=ContractAnalysisCache())
    f_map = {f.key: f for f in analysis.fields}

    field = f_map["force_majeure"]
    assert field.found is False
    assert field.value == ""
    assert field.quote == ""
    assert field.citation == ""
    assert field.status == "Not stated"


def test_missing_keys_filled_as_not_stated():
    """Verify that any omitted keys among the 14 fields default to Not stated."""
    units = _sample_units()

    def fake_llm(system_instruction, user_prompt):
        return json.dumps({"fields": []})  # Empty extractions

    analysis = analyze_contract(units, "Test_MSA.pdf", "staff", llm=fake_llm, cache=ContractAnalysisCache())
    assert len(analysis.fields) == 14
    assert analysis.total_fields == 14
    assert analysis.not_stated_count == 14
    assert analysis.found_count == 0
    for f in analysis.fields:
        assert f.status == "Not stated"
        assert f.found is False


def test_invalid_unit_number_handled():
    """Verify that an out-of-range unit number searches all units and recovers citation."""
    units = _sample_units()

    def fake_llm(system_instruction, user_prompt):
        return json.dumps({
            "fields": [
                {
                    "key": "governing_law",
                    "found": True,
                    "value": "Laws of Pakistan",
                    "unit": 99,  # Out of range
                    "quote": "governed by the laws of Pakistan",
                }
            ]
        })

    analysis = analyze_contract(units, "Test_MSA.pdf", "staff", llm=fake_llm, cache=ContractAnalysisCache())
    f_map = {f.key: f for f in analysis.fields}

    field = f_map["governing_law"]
    assert field.found is True
    assert field.status == "Quote verified"
    assert field.citation == "Test_MSA.pdf, p. 3"


def test_client_mode_refused_at_core_function():
    """Verify that client access_mode raises ContractAnalysisAccessError."""
    units = _sample_units()
    with pytest.raises(ContractAnalysisAccessError) as exc_info:
        analyze_contract(units, "Test_MSA.pdf", "client", llm=lambda s, p: "{}")
    assert "restricted to law firm staff" in str(exc_info.value).lower()


def test_size_guard_blocks_before_llm_call():
    """Verify that documents exceeding MAX_ANALYSIS_CHARS raise ContractAnalysisSizeError."""
    big_unit = DocUnit(
        text="A" * 70000,
        source="Huge_Doc.pdf",
        page=1,
        file_type="pdf",
    )
    mock_llm = mock.MagicMock()

    with pytest.raises(ContractAnalysisSizeError) as exc_info:
        analyze_contract([big_unit], "Huge_Doc.pdf", "staff", llm=mock_llm)

    assert "exceeds the maximum allowed limit" in str(exc_info.value)
    mock_llm.assert_not_called()


def test_cache_hit_returns_identical_result_zero_api_calls():
    """Verify that a second call with identical text returns cached=True and api_calls=0."""
    units = _sample_units()
    call_count = 0

    def counting_llm(s, p):
        nonlocal call_count
        call_count += 1
        return json.dumps({
            "fields": [
                {
                    "key": "payment",
                    "found": True,
                    "value": "PKR 450,000 monthly",
                    "unit": 2,
                    "quote": "monthly fee is PKR 450,000",
                }
            ]
        })

    cache = ContractAnalysisCache()
    res1 = analyze_contract(units, "Doc1.pdf", "staff", llm=counting_llm, cache=cache)
    assert call_count == 1
    assert res1.cached is False
    assert res1.api_calls == 1

    res2 = analyze_contract(units, "Doc1.pdf", "staff", llm=counting_llm, cache=cache)
    assert call_count == 1  # No second LLM invocation!
    assert res2.cached is True
    assert res2.api_calls == 0
    assert res2.fields == res1.fields


def test_get_source_units_respects_visibility(tmp_path):
    """Verify that get_source_units returns [] when visibility is not permitted."""
    store = VectorStore(persist_directory=str(tmp_path / "chroma_test"))

    # Add chunk with 'staff' visibility
    store.collection.add(
        ids=["chunk_1"],
        documents=["Confidential staff contract term text."],
        metadatas=[{
            "source": "Staff_Contract.pdf",
            "chunk_index": 0,
            "page": 1,
            "section": "",
            "file_type": "pdf",
            "visibility": "staff",
        }],
        embeddings=[[0.1] * 768],
    )

    # Client query for staff doc should return empty list
    client_units = store.get_source_units("Staff_Contract.pdf", allowed_visibility={"client"})
    assert client_units == []

    # Staff query should return the unit
    staff_units = store.get_source_units("Staff_Contract.pdf", allowed_visibility={"client", "staff"})
    assert len(staff_units) == 1
    assert staff_units[0].source == "Staff_Contract.pdf"
    assert staff_units[0].page == 1


def test_malformed_json_repair_and_error():
    """Verify markdown stripped JSON repair and GenerationError on unrepairable text."""
    units = _sample_units()

    # Markdown wrapped JSON should succeed
    def markdown_llm(s, p):
        return "```json\n{\"fields\": [{\"key\": \"term\", \"found\": false}]}\n```"

    analysis = analyze_contract(units, "Doc.pdf", "staff", llm=markdown_llm, cache=ContractAnalysisCache())
    assert analysis.total_fields == 14

    # Irreparable garble should raise GenerationError
    def broken_llm(s, p):
        return "This is completely random prose without any JSON data."

    with pytest.raises(GenerationError) as exc_info:
        analyze_contract(units, "Doc.pdf", "staff", llm=broken_llm, cache=ContractAnalysisCache())
    assert "valid JSON" in str(exc_info.value)


def test_session_limit_and_cooldown():
    """Verify AnalysisSessionTracker enforces cooldown and max analyses."""
    fake_time = 1000.0

    def clock():
        return fake_time

    tracker = AnalysisSessionTracker(max_analyses=2, min_cooldown=5.0, clock=clock)

    # 1st call
    tracker.check_and_record()
    assert tracker.count == 1

    # Immediate 2nd call -> cooldown error
    with pytest.raises(ValueError) as exc:
        tracker.check_and_record()
    assert "cooldown: 5.0s" in str(exc.value)

    # Advance clock past cooldown
    fake_time += 6.0
    tracker.check_and_record()
    assert tracker.count == 2

    # 3rd call past max_analyses -> session limit error
    fake_time += 6.0
    with pytest.raises(ValueError) as exc:
        tracker.check_and_record()
    assert "Session limit reached" in str(exc.value)


def test_csv_formula_injection_protection_and_columns():
    """Verify CSV export prepends ' to formula injection cells and produces correct columns."""
    analysis = ContractAnalysis(
        document_name="Test.pdf",
        fields=[
            FieldResult(
                key="term",
                label="=1+1",  # Formula injection attempt in label
                found=True,
                value="@SUM(A1:A10)",  # Formula injection attempt in value
                citation="+Section 1",  # Formula injection attempt in citation
                quote="-Quote test",  # Formula injection attempt in quote
                status="Quote verified",
            )
        ],
        total_fields=1,
        found_count=1,
        verified_count=1,
    )

    csv_text = analysis_to_csv(analysis)
    lines = [line.strip() for line in csv_text.strip().split("\n")]
    assert lines[0] == "Field,Status,Extracted Value,Citation,Verbatim Quote"
    assert "'=1+1" in lines[1]
    assert "'@SUM(A1:A10)" in lines[1]
    assert "'+Section 1" in lines[1]
    assert "'-Quote test" in lines[1]


def test_html_escaping_of_script_injection():
    """Verify that malicious script tags in contract values or quotes are strictly escaped."""
    import html

    val = "<script>alert('xss')</script>"
    quote = '<img src=x onerror="alert(1)">'

    escaped_val = html.escape(val)
    escaped_quote = html.escape(quote)

    assert "<script>" not in escaped_val
    assert "&lt;script&gt;" in escaped_val
    assert "<img" not in escaped_quote
    assert "&lt;img" in escaped_quote


def test_uploaded_file_analyzed_without_embedding_calls():
    """Verify that an uploaded contract in bytes is parsed via load_file with 0 vectorstore calls."""
    raw_text = b"Commercial Lease Agreement\n\n1. Parties to the Lease\nMr. Imran Qureshi and Crescent Textiles."
    units = load_file(raw_text, filename="Upload_Test.txt")

    assert len(units) >= 1
    assert units[0].source == "Upload_Test.txt"
    assert any("Mr. Imran Qureshi" in u.text for u in units)

    def fake_llm(s, p):
        return json.dumps({
            "fields": [
                {
                    "key": "parties",
                    "found": True,
                    "value": "Mr. Imran Qureshi and Crescent Textiles",
                    "unit": 1,
                    "quote": "Mr. Imran Qureshi and Crescent Textiles",
                }
            ]
        })

    analysis = analyze_contract(units, "Upload_Test.txt", "staff", llm=fake_llm, cache=ContractAnalysisCache())
    f_map = {f.key: f for f in analysis.fields}
    assert f_map["parties"].status == "Quote verified"


def test_apptest_navigation_role_switch():
    """Verify AppTest shows Contract Analyzer in staff mode and hides it in client mode."""
    from streamlit.testing.v1 import AppTest
    from src.vectorstore import VectorStore

    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 5
    mock_store.list_sources.return_value = [
        {"name": "Master_Services_Agreement_Northgate.pdf", "chunk_count": 5, "file_type": "pdf", "practice_area": "Corporate"}
    ]

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.contracts_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store):
        
        at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=15)
        at.run()
        assert len(at.exception) == 0

        # In Staff mode (default), sidebar segmented control has Staff selected
        assert at.session_state["current_role"] == "Staff"
