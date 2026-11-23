"""Chunking module for segmenting DocUnits into searchable, overlapping Chunks with citation metadata."""

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional

from src.config import CHUNK_OVERLAP, CHUNK_SIZE
from src.loaders import DocUnit


@dataclass
class Chunk:
    """A granular chunk of text derived from a DocUnit for vector indexing."""

    id: str
    text: str
    source: str
    page: Optional[int]
    section: Optional[str]
    file_type: str
    citation: str
    chunk_index: int


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences, supporting English punctuation (.!?) and Urdu punctuation (۔ ؟)."""
    sentence_endings = re.compile(r"([.!?۔؟]+(?:\s+|\Z))")
    parts = sentence_endings.split(text)

    sentences: List[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        current += part
        if sentence_endings.match(part):
            stripped = current.strip()
            if stripped:
                sentences.append(stripped)
            current = ""
    if current.strip():
        sentences.append(current.strip())

    return sentences or [text.strip()]


def _split_long_text(text: str, max_size: int, overlap: int) -> List[str]:
    """Split a text block larger than max_size on sentence or word boundaries with overlap."""
    sentences = _split_into_sentences(text)
    chunks: List[str] = []
    current_sentences: List[str] = []
    current_len = 0

    for sent in sentences:
        sent_len = len(sent)

        # If a single sentence exceeds max_size, split by words without cutting words
        if sent_len > max_size:
            if current_sentences:
                chunks.append(" ".join(current_sentences))
                current_sentences = []
                current_len = 0

            words = sent.split()
            word_chunk: List[str] = []
            word_len = 0
            for w in words:
                if word_len + len(w) + 1 > max_size and word_chunk:
                    chunks.append(" ".join(word_chunk))
                    # Retain trailing overlap words
                    overlap_words: List[str] = []
                    ov_len = 0
                    for ow in reversed(word_chunk):
                        if ov_len + len(ow) + 1 <= overlap:
                            overlap_words.insert(0, ow)
                            ov_len += len(ow) + 1
                        else:
                            break
                    word_chunk = overlap_words + [w]
                    word_len = sum(len(x) + 1 for x in word_chunk)
                else:
                    word_chunk.append(w)
                    word_len += len(w) + 1
            if word_chunk:
                chunks.append(" ".join(word_chunk))
            continue

        if current_len + sent_len + 1 > max_size and current_sentences:
            chunk_str = " ".join(current_sentences)
            chunks.append(chunk_str)

            # Build sentence overlap from the end of current chunk
            overlap_sentences: List[str] = []
            overlap_len = 0
            for s in reversed(current_sentences):
                if overlap_len + len(s) + 1 <= overlap:
                    overlap_sentences.insert(0, s)
                    overlap_len += len(s) + 1
                else:
                    break

            current_sentences = overlap_sentences + [sent]
            current_len = sum(len(s) + 1 for s in current_sentences)
        else:
            current_sentences.append(sent)
            current_len += sent_len + 1

    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks


def _generate_chunk_id(source: str, page: Optional[int], section: Optional[str], chunk_index: int, text: str) -> str:
    """Generate a deterministic, reproducible hash ID for a chunk."""
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    loc = f"p{page}" if page is not None else (section or "sec")
    raw_key = f"{source}::{loc}::{chunk_index}::{content_hash}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]


def chunk_units(
    units: List[DocUnit],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Chunk]:
    """Segment DocUnits into clean, overlapping Chunks with citation metadata.

    Rules:
        - Units shorter than chunk_size stay as a single chunk (e.g. FAQ Q&As).
        - Units longer than chunk_size split on paragraph/sentence boundaries (including Urdu "۔" and "؟").
        - Chunks never cross page boundaries (page number is preserved per chunk).
        - Drop empty chunks.
        - Never split mid-word.
        - Chunk IDs are deterministic.
    """
    chunks: List[Chunk] = []

    for unit in units:
        clean_text = unit.text.strip()
        if not clean_text:
            continue

        # Rule 1: If unit text is <= chunk_size, keep it intact as a single chunk
        if len(clean_text) <= chunk_size:
            text_splits = [clean_text]
        else:
            # Rule 2: Split longer unit into overlapping chunks
            if "\n\n" in clean_text:
                paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]
                text_splits = []
                for p in paragraphs:
                    if len(p) <= chunk_size:
                        text_splits.append(p)
                    else:
                        text_splits.extend(_split_long_text(p, chunk_size, chunk_overlap))
            else:
                text_splits = _split_long_text(clean_text, chunk_size, chunk_overlap)

        # Generate Chunk objects
        citation = unit.citation_label()
        for idx, text_part in enumerate(text_splits):
            part_clean = text_part.strip()
            if not part_clean:
                continue

            chunk_id = _generate_chunk_id(
                source=unit.source,
                page=unit.page,
                section=unit.section,
                chunk_index=idx,
                text=part_clean,
            )

            chunks.append(Chunk(
                id=chunk_id,
                text=part_clean,
                source=unit.source,
                page=unit.page,
                section=unit.section,
                file_type=unit.file_type,
                citation=citation,
                chunk_index=idx,
            ))

    return chunks
