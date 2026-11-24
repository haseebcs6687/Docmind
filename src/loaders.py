"""Document loaders for ingesting PDF, DOCX, and TXT files with rich citation metadata."""

import io
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Tuple, Union

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph
import pypdf
from pypdf.errors import PdfReadError

from src.config import MAX_UPLOAD_MB

logger = logging.getLogger(__name__)


class DocumentLoadError(Exception):
    """Raised when a document cannot be parsed due to format, encryption, or corruption."""
    pass


@dataclass
class DocUnit:
    """A granular unit of text extracted from a document with citation metadata."""

    text: str
    source: str
    page: Optional[int] = None
    section: Optional[str] = None
    file_type: str = ""

    def __post_init__(self) -> None:
        # Text files do not have page numbers
        is_txt = (self.file_type.lower() == "txt") or self.source.lower().endswith(".txt")
        if is_txt:
            self.page = None

    def citation_label(self) -> str:
        """Return a human-readable citation label.

        Examples:
            - "Fee_Schedule_2026.pdf, p. 2"
            - "Client_Engagement_Letter_Template.docx, 3. Professional Fee Schedule & Hourly Rates"
            - "Client_FAQ.txt, Q&A 7"
        """
        is_txt = (self.file_type.lower() == "txt") or self.source.lower().endswith(".txt")
        if self.page is not None and not is_txt:
            return f"{self.source}, p. {self.page}"
        elif self.section:
            return f"{self.source}, {self.section}"
        return self.source


def _normalize_whitespace(text: str) -> str:
    """Normalize excessive whitespace while preserving line structure."""
    # Collapse multiple inline spaces and tabs
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse three or more newlines into double newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _load_pdf(stream: BinaryIO, filename: str) -> List[DocUnit]:
    """Extract text from a PDF stream into per-page DocUnits."""
    try:
        reader = pypdf.PdfReader(stream)
    except PdfReadError as e:
        raise DocumentLoadError(f"Failed to read corrupted PDF file '{filename}': {e}")
    except Exception as e:
        raise DocumentLoadError(f"Invalid or corrupted PDF file '{filename}': {e}")

    if reader.is_encrypted:
        try:
            # Attempt empty-password decrypt
            decrypted = reader.decrypt("")
            if decrypted == 0:
                raise DocumentLoadError(f"PDF file '{filename}' is password-protected and cannot be read.")
        except Exception:
            raise DocumentLoadError(f"PDF file '{filename}' is password-protected and cannot be read.")

    units: List[DocUnit] = []
    empty_pages: List[int] = []

    for page_num, page in enumerate(reader.pages, start=1):
        try:
            extracted = page.extract_text() or ""
        except Exception as e:
            logger.warning("Error extracting page %d of '%s': %s", page_num, filename, e)
            extracted = ""

        cleaned = _normalize_whitespace(extracted)
        if cleaned:
            units.append(DocUnit(
                text=cleaned,
                source=filename,
                page=page_num,
                section=None,
                file_type="pdf",
            ))
        else:
            empty_pages.append(page_num)

    if not units:
        raise DocumentLoadError(f"PDF file '{filename}' contains no extractable text (scanned PDF? OCR not supported).")

    if empty_pages:
        logger.info("PDF '%s' had %d empty/unextractable page(s): %s", filename, len(empty_pages), empty_pages)

    return units


def _load_docx(stream: BinaryIO, filename: str) -> List[DocUnit]:
    """Extract text from a DOCX stream, splitting into DocUnits by heading or block grouping."""
    try:
        doc = docx.Document(stream)
    except Exception as e:
        raise DocumentLoadError(f"Invalid or corrupted DOCX file '{filename}': {e}")

    # Extract elements in sequential order using iter_inner_content
    blocks: List[Tuple[str, str, str]] = []  # (kind, style_name, text)

    for item in doc.iter_inner_content():
        if isinstance(item, Paragraph):
            style_name = (item.style.name if item.style else "") or ""
            text = item.text.strip()
            if text:
                blocks.append(("paragraph", style_name, text))
        elif isinstance(item, Table):
            table_lines: List[str] = []
            for row in item.rows:
                row_cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if row_cells:
                    # De-duplicate adjacent identical cells from merged tables
                    deduped: List[str] = []
                    for cell in row_cells:
                        if not deduped or deduped[-1] != cell:
                            deduped.append(cell)
                    table_lines.append(" | ".join(deduped))
            if table_lines:
                blocks.append(("table", "Table", "\n".join(table_lines)))

    if not blocks:
        raise DocumentLoadError(f"DOCX file '{filename}' contains no text content.")

    # Check if headings exist to guide splitting
    has_headings = any("heading" in style.lower() or style.lower() in ("title", "subtitle") for _, style, _ in blocks)

    units: List[DocUnit] = []

    if has_headings:
        current_section = "Overview"
        current_texts: List[str] = []

        for kind, style, text in blocks:
            is_heading = "heading" in style.lower() or style.lower() in ("title", "subtitle")
            if is_heading:
                # Flush previous section if it contains text
                if current_texts:
                    combined = _normalize_whitespace("\n\n".join(current_texts))
                    if combined:
                        units.append(DocUnit(
                            text=combined,
                            source=filename,
                            page=None,
                            section=current_section,
                            file_type="docx",
                        ))
                    current_texts = []
                current_section = text
                current_texts.append(text)
            else:
                current_texts.append(text)

        if current_texts:
            combined = _normalize_whitespace("\n\n".join(current_texts))
            if combined:
                units.append(DocUnit(
                    text=combined,
                    source=filename,
                    page=None,
                    section=current_section,
                    file_type="docx",
                ))
    else:
        # Fallback: group every N blocks together
        n_blocks = 5
        for i in range(0, len(blocks), n_blocks):
            group = blocks[i : i + n_blocks]
            combined = _normalize_whitespace("\n\n".join(t for _, _, t in group))
            if combined:
                section_idx = (i // n_blocks) + 1
                units.append(DocUnit(
                    text=combined,
                    source=filename,
                    page=None,
                    section=f"Section {section_idx}",
                    file_type="docx",
                ))

    return units


def _load_txt(stream: BinaryIO, filename: str) -> List[DocUnit]:
    """Extract text from a TXT stream, parsing Q&A blocks or blank-line delimited sections."""
    raw_bytes = stream.read()
    if not raw_bytes:
        raise DocumentLoadError(f"Text file '{filename}' is empty.")

    # Decode with UTF-8 BOM awareness, falling back safely
    try:
        content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decoding failed for '%s'. Falling back to latin-1.", filename)
        try:
            content = raw_bytes.decode("latin-1")
        except Exception as e:
            raise DocumentLoadError(f"Failed to decode text file '{filename}': {e}")

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.strip():
        raise DocumentLoadError(f"Text file '{filename}' contains no readable text.")

    # Detect Q&A patterns (e.g. Q1:, Q:, Question 1:)
    qa_pattern = re.compile(r"^(?:Q\d*[:.]|Question\s*\d*[:.])", re.MULTILINE)
    matches = list(qa_pattern.finditer(content))

    units: List[DocUnit] = []

    if matches:
        # Extract preamble if text exists before the first question
        preamble = content[: matches[0].start()].strip()
        preamble_clean = "\n".join(
            line for line in preamble.splitlines() if not re.match(r"^[=\-]{5,}$", line.strip())
        ).strip()
        if preamble_clean:
            units.append(DocUnit(
                text=_normalize_whitespace(preamble_clean),
                source=filename,
                page=None,
                section="Overview",
                file_type="txt",
            ))

        for idx, m in enumerate(matches, start=1):
            start = m.start()
            end = matches[idx].start() if idx < len(matches) else len(content)
            chunk = content[start:end]

            # Clean trailing separator lines or banner partitions
            cleaned_lines: List[str] = []
            for line in chunk.splitlines():
                trimmed = line.strip()
                if re.match(r"^[=\-]{5,}$", trimmed) or re.match(r"^PART\s+[I|V|X]+:", trimmed, re.IGNORECASE):
                    continue
                cleaned_lines.append(line)

            chunk_text = _normalize_whitespace("\n".join(cleaned_lines))
            if chunk_text:
                units.append(DocUnit(
                    text=chunk_text,
                    source=filename,
                    page=None,
                    section=f"Q&A {idx}",
                    file_type="txt",
                ))
    else:
        # Standard text file: split on blank lines
        blocks = re.split(r"\n\s*\n+", content)
        for idx, block in enumerate(blocks, start=1):
            cleaned = _normalize_whitespace(block)
            if cleaned:
                units.append(DocUnit(
                    text=cleaned,
                    source=filename,
                    page=None,
                    section=f"Block {idx}",
                    file_type="txt",
                ))

    if not units:
        raise DocumentLoadError(f"Text file '{filename}' contained no valid text blocks.")

    return units


def load_file(
    path_or_file: Union[str, Path, BinaryIO, bytes],
    filename: Optional[str] = None,
) -> List[DocUnit]:
    """Load a single document from a path, file-like object, or bytes into DocUnits.

    Args:
        path_or_file: Path to file, open binary stream, or raw bytes.
        filename: Optional filename override (required for bytes or un-named streams).

    Returns:
        List of DocUnit objects containing extracted text and metadata.

    Raises:
        DocumentLoadError: If the file is missing, empty, exceeds MAX_UPLOAD_MB,
                           is encrypted, corrupted, or unsupported.
    """
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    stream: BinaryIO
    actual_filename: str

    if isinstance(path_or_file, (str, Path)):
        file_path = Path(path_or_file)
        if not file_path.exists():
            raise DocumentLoadError(f"File not found: '{file_path}'")
        if not file_path.is_file():
            raise DocumentLoadError(f"Path is not a regular file: '{file_path}'")

        file_size = file_path.stat().st_size
        actual_filename = filename or file_path.name

        if file_size == 0:
            raise DocumentLoadError(f"File '{actual_filename}' is empty.")
        if file_size > max_bytes:
            raise DocumentLoadError(
                f"File '{actual_filename}' ({file_size / (1024 * 1024):.1f} MB) exceeds maximum upload limit of {MAX_UPLOAD_MB} MB."
            )

        with open(file_path, "rb") as f:
            stream = io.BytesIO(f.read())

    elif isinstance(path_or_file, bytes):
        if not filename:
            raise DocumentLoadError("Filename must be specified when passing raw bytes to load_file.")
        actual_filename = filename

        if len(path_or_file) == 0:
            raise DocumentLoadError(f"File '{actual_filename}' is empty.")
        if len(path_or_file) > max_bytes:
            raise DocumentLoadError(
                f"File '{actual_filename}' ({len(path_or_file) / (1024 * 1024):.1f} MB) exceeds maximum upload limit of {MAX_UPLOAD_MB} MB."
            )

        stream = io.BytesIO(path_or_file)

    else:
        # File-like object (e.g. io.BytesIO, Streamlit UploadedFile)
        stream_name = getattr(path_or_file, "name", None)
        actual_filename = filename or (Path(stream_name).name if stream_name else "uploaded_document")

        raw = path_or_file.read()
        if not raw:
            raise DocumentLoadError(f"File '{actual_filename}' is empty.")
        if len(raw) > max_bytes:
            raise DocumentLoadError(
                f"File '{actual_filename}' ({len(raw) / (1024 * 1024):.1f} MB) exceeds maximum upload limit of {MAX_UPLOAD_MB} MB."
            )

        stream = io.BytesIO(raw)

    ext = Path(actual_filename).suffix.lower()

    if ext == ".pdf":
        return _load_pdf(stream, actual_filename)
    elif ext == ".docx":
        return _load_docx(stream, actual_filename)
    elif ext == ".txt":
        return _load_txt(stream, actual_filename)
    else:
        raise DocumentLoadError(
            f"Unsupported file format '{ext}' for file '{actual_filename}'. Supported formats are .pdf, .docx, and .txt."
        )


def load_directory(dir_path: Union[str, Path]) -> Tuple[List[DocUnit], Dict[str, Any]]:
    """Scan and load all supported documents in a directory.

    Args:
        dir_path: Directory path containing documents.

    Returns:
        Tuple of (all_units, report_dict) where report_dict details loaded and skipped files.
    """
    directory = Path(dir_path)
    if not directory.exists() or not directory.is_dir():
        raise DocumentLoadError(f"Directory not found: '{directory}'")

    units: List[DocUnit] = []
    report: Dict[str, Any] = {
        "loaded_files": [],
        "units_per_file": {},
        "total_units": 0,
        "skipped_files": {},
    }

    # Sort files for deterministic loading order
    for item in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        # Skip directories, metadata files, and hidden/placeholder files
        if item.is_dir() or item.name.startswith(".") or item.name == "manifest.json":
            continue

        ext = item.suffix.lower()
        if ext not in (".pdf", ".docx", ".txt"):
            report["skipped_files"][item.name] = f"Unsupported file format '{ext}'"
            continue

        try:
            file_units = load_file(item)
            units.extend(file_units)
            report["loaded_files"].append(item.name)
            report["units_per_file"][item.name] = len(file_units)
        except DocumentLoadError as e:
            report["skipped_files"][item.name] = str(e)
            logger.warning("Skipped file '%s': %s", item.name, e)
        except Exception as e:
            report["skipped_files"][item.name] = f"Unexpected processing error: {e}"
            logger.exception("Unexpected error loading '%s'", item.name)

    report["total_units"] = len(units)
    return units, report
