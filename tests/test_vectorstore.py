"""Unit tests for ChromaDB vector store in src/vectorstore.py (offline with mock embeddings)."""

import hashlib
from pathlib import Path
import pytest
import chromadb

from src.loaders import DocUnit
from src.vectorstore import VectorStore


def fake_embed_fn(texts, task_type="RETRIEVAL_DOCUMENT"):
    """Deterministic, offline embedding function for testing."""
    embeddings = []
    for text in texts:
        # Generate 16-dimensional deterministic float vector
        md5_bytes = hashlib.md5(text.encode("utf-8")).digest()
        vec = [float(b) / 255.0 for b in md5_bytes]
        # Normalize
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        embeddings.append([x / norm for x in vec])
    return embeddings


@pytest.fixture
def temp_vstore(tmp_path):
    """Provide a fresh isolated VectorStore backed by a temporary directory."""
    chroma_path = str(tmp_path / "chroma_test_db")
    vstore = VectorStore(persist_directory=chroma_path, collection_name="test_collection")
    yield vstore
    vstore.reset()


def test_empty_collection_returns_empty(temp_vstore):
    """Verify querying an empty collection returns an empty list without error."""
    assert temp_vstore.count() == 0
    results = temp_vstore.query("consultation fee", k=5, embed_fn=fake_embed_fn)
    assert results == []


def test_index_and_retrieve_units(temp_vstore):
    """Verify indexing units stores chunks and semantic query returns scored results."""
    units = [
        DocUnit(
            text="Initial consultation fee is PKR 5,000 for 45 minutes.",
            source="Fee_Schedule_2026.pdf",
            page=1,
            file_type="pdf",
        ),
        DocUnit(
            text="Office hours are Monday to Friday 9:30 to 17:30.",
            source="Brochure.pdf",
            page=3,
            file_type="pdf",
        ),
    ]
    file_hashes = {
        "Fee_Schedule_2026.pdf": "hash_fee_1",
        "Brochure.pdf": "hash_brochure_1",
    }

    report = temp_vstore.index_units(units, file_hashes, embed_fn=fake_embed_fn)
    assert report["total_chunks_added"] == 2
    assert temp_vstore.count() == 2

    results = temp_vstore.query("consultation fee", k=2, embed_fn=fake_embed_fn)
    assert len(results) == 2
    assert results[0]["score"] >= 0.0
    assert results[0]["score"] <= 1.0
    assert results[0]["citation"] in ("Fee_Schedule_2026.pdf, p. 1", "Brochure.pdf, p. 3")


def test_reindex_unchanged_file_adds_nothing(temp_vstore):
    """Verify that re-indexing a file with unchanged hash skips indexing and makes 0 calls."""
    units = [
        DocUnit(
            text="Clause 1: Scope of representation.",
            source="Agreement.docx",
            section="Clause 1",
            file_type="docx",
        )
    ]
    file_hashes = {"Agreement.docx": "unchanged_hash_123"}

    # Initial index
    r1 = temp_vstore.index_units(units, file_hashes, embed_fn=fake_embed_fn)
    assert r1["total_chunks_added"] == 1
    assert "Agreement.docx" in r1["indexed_files"]

    # Second index with identical hash
    r2 = temp_vstore.index_units(units, file_hashes, embed_fn=fake_embed_fn)
    assert r2["total_chunks_added"] == 0
    assert "Agreement.docx" in r2["skipped_files"]
    assert temp_vstore.count() == 1


def test_changed_file_hash_replaces_old_chunks(temp_vstore):
    """Verify that when a file hash changes, old chunks are deleted and replaced."""
    old_units = [
        DocUnit(
            text="Old consultation fee was PKR 3,000.",
            source="Fee_Schedule.pdf",
            page=1,
            file_type="pdf",
        )
    ]
    temp_vstore.index_units(old_units, {"Fee_Schedule.pdf": "old_hash"}, embed_fn=fake_embed_fn)
    assert temp_vstore.count() == 1

    # New modified file with changed hash
    new_units = [
        DocUnit(
            text="New consultation fee is PKR 5,000 for 45 minutes.",
            source="Fee_Schedule.pdf",
            page=1,
            file_type="pdf",
        )
    ]
    r_updated = temp_vstore.index_units(new_units, {"Fee_Schedule.pdf": "new_hash"}, embed_fn=fake_embed_fn)

    assert r_updated["total_chunks_added"] == 1
    assert temp_vstore.count() == 1

    # Verify query finds new text
    results = temp_vstore.query("consultation fee", k=1, embed_fn=fake_embed_fn)
    assert "5,000" in results[0]["text"]


def test_delete_source_and_reset(temp_vstore):
    """Verify delete_source removes chunks for that source and reset clears everything."""
    units = [
        DocUnit(text="Family law retainer PKR 75,000", source="A.pdf", page=1, file_type="pdf"),
        DocUnit(text="Property retainer PKR 100,000", source="B.pdf", page=1, file_type="pdf"),
    ]
    temp_vstore.index_units(units, {"A.pdf": "hA", "B.pdf": "hB"}, embed_fn=fake_embed_fn)
    assert temp_vstore.count() == 2

    # Delete A.pdf
    temp_vstore.delete_source("A.pdf")
    assert temp_vstore.count() == 1
    sources = temp_vstore.list_sources()
    assert len(sources) == 1
    assert sources[0]["name"] == "B.pdf"

    # Reset
    temp_vstore.reset()
    assert temp_vstore.count() == 0
    assert temp_vstore.list_sources() == []
