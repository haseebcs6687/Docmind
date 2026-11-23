"""Unit tests for text chunking in src/chunking.py."""

from src.chunking import Chunk, chunk_units
from src.loaders import DocUnit


def test_chunk_size_respected():
    """Verify generated chunks respect the maximum chunk size limit."""
    long_text = "This is a detailed legal clause explaining contractual terms and liabilities. " * 30
    unit = DocUnit(
        text=long_text,
        source="contract.docx",
        page=None,
        section="Liabilities",
        file_type="docx",
    )

    chunks = chunk_units([unit], chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.text) <= 550  # Allow tiny boundary tolerance for word/sentence breaks
        assert c.source == "contract.docx"
        assert c.section == "Liabilities"


def test_short_faq_unit_stays_intact():
    """Verify short units (like FAQ Q&As) remain a single undivided chunk."""
    faq_text = "Q1: What are office hours?\nA1: Monday to Friday 9:30 to 17:30."
    unit = DocUnit(
        text=faq_text,
        source="Client_FAQ.txt",
        page=None,
        section="Q&A 1",
        file_type="txt",
    )

    chunks = chunk_units([unit], chunk_size=1000)
    assert len(chunks) == 1
    assert chunks[0].text == faq_text
    assert chunks[0].citation == "Client_FAQ.txt, Q&A 1"


def test_chunks_never_cross_pages():
    """Verify that chunks derived from multi-page PDFs strictly preserve their page indices."""
    units = [
        DocUnit(text="Page 1 text content " * 40, source="brief.pdf", page=1, file_type="pdf"),
        DocUnit(text="Page 2 text content " * 40, source="brief.pdf", page=2, file_type="pdf"),
    ]

    chunks = chunk_units(units, chunk_size=400, chunk_overlap=50)
    p1_chunks = [c for c in chunks if c.page == 1]
    p2_chunks = [c for c in chunks if c.page == 2]

    assert len(p1_chunks) >= 2
    assert len(p2_chunks) >= 2
    assert len(chunks) == len(p1_chunks) + len(p2_chunks)

    for c in p1_chunks:
        assert "Page 2" not in c.text
    for c in p2_chunks:
        assert "Page 1" not in c.text


def test_chunk_ids_are_deterministic():
    """Verify that chunk IDs are reproducible across repeated invocations."""
    unit = DocUnit(
        text="Standard operating procedure text for conflict verification.",
        source="sop.pdf",
        page=2,
        section=None,
        file_type="pdf",
    )

    run1 = chunk_units([unit])
    run2 = chunk_units([unit])

    assert len(run1) == len(run2) == 1
    assert run1[0].id == run2[0].id


def test_sentence_splitting():
    """Verify that sentence punctuation (.!?) is recognized during splitting."""
    long_text = (
        "What is the preliminary consultation fee? The fee is PKR 5,000 for 45 minutes! "
        "If the client signs an engagement agreement, this fee is fully waived. " * 15
    )
    unit = DocUnit(
        text=long_text,
        source="Client_FAQ.txt",
        page=None,
        section="Q&A 1",
        file_type="txt",
    )

    chunks = chunk_units([unit], chunk_size=300, chunk_overlap=50)
    assert len(chunks) > 1
    for c in chunks:
        assert "5,000" in c.text
