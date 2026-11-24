"""Research memo export module for DocMind (Staff and Client).

Generates professional Word documents (.docx) summarizing the active session's
findings and open items with full source citations, relevance ratings, and disclaimers.
"""

from datetime import datetime, timezone
import io
import re
from typing import Any, Dict, List, Optional
import zoneinfo

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from src.config import APP_TIMEZONE
from src.rag import check_small_talk


class MemoGenerationError(Exception):
    """Raised when memo generation fails or has no answered turns."""


def strip_invalid_xml_chars(text: Optional[str]) -> str:
    """Remove characters that are illegal in XML 1.0."""
    if not text:
        return ""
    # XML 1.0 legal characters: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    return re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]", "", str(text))


def memo_filename(dt: Optional[datetime] = None) -> str:
    """Generate standard memo export filename in APP_TIMEZONE (e.g. docmind-memo-20261124.docx)."""
    tz = zoneinfo.ZoneInfo(APP_TIMEZONE)
    now = dt or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_now = now.astimezone(tz)
    return f"docmind-memo-{local_now.strftime('%Y%m%d')}.docx"


def _add_page_number_to_run(run: Any) -> None:
    """Append a dynamic Word PAGE field code to a run element."""
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = "PAGE"
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")

    r = run._r
    r.append(fldChar1)
    r.append(instrText)
    r.append(fldChar2)
    r.append(fldChar3)


def build_memo_docx(
    messages: List[Dict[str, Any]],
    access_mode: str,
    firm_name: str = "Sterling & Rauf Law Associates",
    generated_on: Optional[datetime] = None,
) -> bytes:
    """Build a research memo DOCX file from in-session chat messages.

    Args:
        messages: In-session conversation messages list.
        access_mode: Active access mode ("staff" or "client").
        firm_name: Firm title used in headers/disclaimers.
        generated_on: Timestamp for generation and document properties.

    Returns:
        Raw DOCX file bytes.

    Raises:
        MemoGenerationError: If there are no answered questions to include.
    """
    tz = zoneinfo.ZoneInfo(APP_TIMEZONE)
    now = generated_on or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_now = now.astimezone(tz)

    # 1. Truncate conversation to the last 40 turns
    limited_messages = messages[-40:] if len(messages) > 40 else messages

    # 2. Extract Q&A turns
    answered_turns: List[Dict[str, Any]] = []
    open_items: List[str] = []

    last_user_query: Optional[str] = None
    for msg in limited_messages:
        role = msg.get("role", "")
        raw_content = strip_invalid_xml_chars(msg.get("content", ""))[:4000]

        if role == "user":
            last_user_query = raw_content
        elif role == "assistant":
            found = msg.get("found", True)
            q_text = msg.get("question") or last_user_query or "Query"
            q_text = strip_invalid_xml_chars(q_text)[:4000]

            # Check if this was a small-talk turn
            is_st = False
            if check_small_talk(q_text) is not None:
                is_st = True

            if is_st:
                continue

            sources = msg.get("sources", [])
            if found and sources:
                answered_turns.append({
                    "question": q_text,
                    "answer": raw_content,
                    "sources": sources,
                })
            elif not found:
                open_items.append(q_text)

    if not answered_turns:
        raise MemoGenerationError("No answered questions to include in the research memo.")

    # 3. Create python-docx document
    doc = docx.Document()

    # Core Properties
    core_props = doc.core_properties
    core_props.title = "Research Memo"
    core_props.author = "DocMind"
    core_props.created = now

    # Page Margins: 1 inch all sides
    for s in doc.sections:
        s.top_margin = Inches(1.0)
        s.bottom_margin = Inches(1.0)
        s.left_margin = Inches(1.0)
        s.right_margin = Inches(1.0)

    # Title
    title_p = doc.add_heading("Research Memo", level=1)
    title_p.paragraph_format.space_after = Pt(8)

    # Subtitle / Firm Notice
    sub_p = doc.add_paragraph()
    sub_run = sub_p.add_run(f"{firm_name} • Knowledge & Research Assistance")
    sub_run.font.size = Pt(11)
    sub_run.font.color.rgb = RGBColor(100, 116, 139)
    sub_p.paragraph_format.space_after = Pt(16)

    # Info Table (4 rows, 2 columns)
    table = doc.add_table(rows=4, cols=2)
    table.style = "Table Grid"
    table_data = [
        ("Date", local_now.strftime("%B %d, %Y")),
        ("Prepared by", "DocMind assistant (draft)"),
        ("View", f"{access_mode.capitalize()} view"),
        ("Questions answered", str(len(answered_turns))),
    ]
    for row_idx, (k, v) in enumerate(table_data):
        c0 = table.cell(row_idx, 0)
        c1 = table.cell(row_idx, 1)
        c0.text = k
        c1.text = v
        # Style label column in bold
        if c0.paragraphs and c0.paragraphs[0].runs:
            c0.paragraphs[0].runs[0].bold = True
        c0.width = Inches(2.2)
        c1.width = Inches(4.3)

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Findings Section
    doc.add_heading("Findings", level=2)

    for i, item in enumerate(answered_turns, start=1):
        q_heading = doc.add_heading(f"Q{i}. {item['question']}", level=3)
        q_heading.paragraph_format.space_before = Pt(12)
        q_heading.paragraph_format.space_after = Pt(4)

        ans_p = doc.add_paragraph(strip_invalid_xml_chars(item["answer"])[:4000])
        ans_p.paragraph_format.space_after = Pt(6)

        sources_label = doc.add_paragraph()
        sources_label.paragraph_format.space_after = Pt(2)
        lbl_run = sources_label.add_run("Sources:")
        lbl_run.bold = True
        lbl_run.font.size = Pt(9.5)

        for src in item.get("sources", []):
            citation_label = strip_invalid_xml_chars(
                src.get("label") or src.get("citation") or src.get("source", "Document")
            )
            score_val = float(src.get("score", 0.0))
            score_pct = f"{score_val * 100:.0f}% match" if score_val > 0 else ""
            relevance_str = f" ({score_pct})" if score_pct else ""

            snippet_text = strip_invalid_xml_chars(src.get("snippet", "")).strip()[:4000]

            bullet_p = doc.add_paragraph(style="List Bullet")
            bullet_p.paragraph_format.space_after = Pt(3)

            b_run1 = bullet_p.add_run(f"{citation_label}{relevance_str}: ")
            b_run1.bold = True
            b_run1.font.size = Pt(9.5)

            if snippet_text:
                b_run2 = bullet_p.add_run(f'"{snippet_text}"')
                b_run2.italic = True
                b_run2.font.size = Pt(9.0)
                b_run2.font.color.rgb = RGBColor(71, 85, 105)

    # Open Items Section
    if open_items:
        doc.add_paragraph().paragraph_format.space_after = Pt(8)
        doc.add_heading("Open items", level=2)
        for open_q in open_items:
            bp = doc.add_paragraph(style="List Bullet")
            bp.paragraph_format.space_after = Pt(3)
            r1 = bp.add_run(f"{open_q}")
            r1.bold = True
            r2 = bp.add_run(" — Not found in the uploaded documents")
            r2.italic = True
            r2.font.color.rgb = RGBColor(148, 163, 184)

    # Closing Disclaimer Paragraph
    doc.add_paragraph().paragraph_format.space_after = Pt(16)
    disc_p = doc.add_paragraph()
    disc_run = disc_p.add_run(
        "Generated by DocMind from the uploaded documents to support staff review. "
        "Verify against the source documents. This is not legal advice. Fictional demo data."
    )
    disc_run.italic = True
    disc_run.font.size = Pt(9.0)
    disc_run.font.color.rgb = RGBColor(100, 116, 139)

    # Footer Setup
    footer = doc.sections[0].footer
    footer_p = footer.paragraphs[0]
    footer_p.text = f"{firm_name} • DocMind Demo Memo • Fictional data only | Page "
    footer_p.runs[0].font.size = Pt(8.5)
    footer_p.runs[0].font.color.rgb = RGBColor(148, 163, 184)
    _add_page_number_to_run(footer_p.runs[0])

    # Save to BytesIO
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
