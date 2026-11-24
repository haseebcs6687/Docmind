"""Unit tests for document loaders in src/loaders.py."""

import io
from pathlib import Path
import pytest

from src.loaders import DocUnit, DocumentLoadError, load_directory, load_file

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_docs"


def test_load_all_sample_docs():
    """Verify all 6 demo documents in data/sample_docs load successfully."""
    units, report = load_directory(SAMPLE_DIR)

    expected_files = {
        "Fee_Schedule_2026.pdf",
        "Practice_Areas_Brochure.pdf",
        "Client_Intake_SOP.pdf",
        "Confidentiality_and_Data_Policy.pdf",
        "Client_Engagement_Letter_Template.docx",
        "Client_FAQ.txt",
    }
    loaded = set(report["loaded_files"])
    assert expected_files.issubset(loaded), f"Missing files in loaded set: {expected_files - loaded}"
    assert report["total_units"] > 0
    assert not report["skipped_files"]


def test_pdf_page_counts():
    """Verify that each PDF extracts exactly the expected number of page units."""
    units, report = load_directory(SAMPLE_DIR)

    # Expected page counts per task requirements
    expected_pages = {
        "Fee_Schedule_2026.pdf": 4,
        "Practice_Areas_Brochure.pdf": 3,
        "Client_Intake_SOP.pdf": 4,
        "Confidentiality_and_Data_Policy.pdf": 3,
    }

    for pdf_name, expected_count in expected_pages.items():
        pdf_units = [u for u in units if u.source == pdf_name]
        assert len(pdf_units) == expected_count, (
            f"{pdf_name}: expected {expected_count} pages, got {len(pdf_units)}"
        )
        # Verify 1-based sequential page numbering
        page_numbers = [u.page for u in pdf_units]
        assert page_numbers == list(range(1, expected_count + 1))


def test_fee_schedule_fact_and_page():
    """Verify '5,000' appears in Fee_Schedule Page 1 unit, matching eval/dataset_facts.md."""
    fee_file = SAMPLE_DIR / "Fee_Schedule_2026.pdf"
    units = load_file(fee_file)

    p1_units = [u for u in units if u.page == 1]
    assert len(p1_units) == 1
    p1 = p1_units[0]

    assert "5,000" in p1.text
    assert p1.citation_label() == "Fee_Schedule_2026.pdf, p. 1"


def test_docx_multiple_sections():
    """Verify DOCX splits into multiple units corresponding to document headings."""
    docx_file = SAMPLE_DIR / "Client_Engagement_Letter_Template.docx"
    units = load_file(docx_file)

    assert len(units) >= 5, f"Expected multiple sections, got {len(units)}"
    for u in units:
        assert u.file_type == "docx"
        assert u.section is not None
        assert u.source == "Client_Engagement_Letter_Template.docx"
        assert u.citation_label().startswith("Client_Engagement_Letter_Template.docx, ")


def test_faq_units_load():
    """Verify Client_FAQ.txt loads expected Q&A units with accurate citation labels."""
    faq_file = SAMPLE_DIR / "Client_FAQ.txt"
    units = load_file(faq_file)

    # Verify key fact in Q&A 2
    found = any("preliminary consultation fee is PKR 5,000" in u.text for u in units)
    assert found, "Expected consultation fee text was not found in FAQ units"

    # Verify Q&A citation labels
    qa_units = [u for u in units if u.section and u.section.startswith("Q&A")]
    assert len(qa_units) == 18
    assert any(u.citation_label() == "Client_FAQ.txt, Q&A 7" for u in units)


def test_unsupported_extension_error():
    """Verify loading an unsupported file extension raises DocumentLoadError."""
    with pytest.raises(DocumentLoadError, match="Unsupported file format"):
        load_file(b"some content", filename="test.invalid_ext")


def test_empty_file_error(tmp_path):
    """Verify loading an empty file raises DocumentLoadError."""
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(DocumentLoadError, match="is empty"):
        load_file(empty_file)

    with pytest.raises(DocumentLoadError, match="is empty"):
        load_file(b"", filename="empty.pdf")


def test_bytes_input_works():
    """Verify passing in-memory bytes or BytesIO stream works identically to file paths."""
    sample_text = (
        "Q1: What are your office hours?\n"
        "A1: Monday to Friday 9:30 to 17:30.\n\n"
        "Q2: How much is consultation?\n"
        "A2: PKR 5,000 for 45 minutes.\n"
    )
    raw_bytes = sample_text.encode("utf-8")

    # Bytes input
    units_bytes = load_file(raw_bytes, filename="virtual_test.txt")
    assert len(units_bytes) == 2
    assert units_bytes[0].section == "Q&A 1"
    assert units_bytes[0].citation_label() == "virtual_test.txt, Q&A 1"

    # BytesIO input
    stream = io.BytesIO(raw_bytes)
    units_stream = load_file(stream, filename="stream_test.txt")
    assert len(units_stream) == 2
    assert units_stream[1].section == "Q&A 2"
    assert "5,000" in units_stream[1].text


def test_txt_citation_never_includes_page():
    """Verify that TXT units never produce 'p. X' in citation_label(), even if page is set."""
    # Direct DocUnit creation with page=1 explicitly passed
    u_txt_manual = DocUnit(source="Test_Policy.txt", text="Some text", file_type="txt", page=1)
    assert u_txt_manual.page is None
    assert u_txt_manual.citation_label() == "Test_Policy.txt"

    # TXT with section
    u_txt_sec = DocUnit(source="Test_Policy.txt", text="Some text", file_type="txt", section="Overview", page=1)
    assert u_txt_sec.page is None
    assert u_txt_sec.citation_label() == "Test_Policy.txt, Overview"

    # DOCX preserves section
    u_docx = DocUnit(source="Agreement.docx", text="Rent", file_type="docx", section="4. Monthly Rent")
    assert u_docx.citation_label() == "Agreement.docx, 4. Monthly Rent"

    # PDF preserves page
    u_pdf = DocUnit(source="Policy.pdf", text="Policy text", file_type="pdf", page=3)
    assert u_pdf.citation_label() == "Policy.pdf, p. 3"

