"""Reusable HTML UI components with strict HTML escaping and accessible contrast."""

import html
from typing import List


def page_header(title: str, subtitle: str) -> str:
    """Render a clean, modern page header with a title and one-line subtitle."""
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    return (
        f'<div class="docmind-page-header">'
        f'  <h1 class="page-title">{safe_title}</h1>'
        f'  <p class="page-subtitle">{safe_subtitle}</p>'
        f'</div>'
    )


def brand_header() -> str:
    """Render the sidebar brand header with logo glyph, title, and tagline."""
    svg_icon = (
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<path d="M14 2H6C4.89543 2 4 2.89543 4 4V20C4 21.1046 4.89543 22 6 22H18C19.1046 22 20 21.1046 20 20V8L14 2Z" '
        'stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M14 2V8H20" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M16 13H8" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M16 17H8" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M10 9H8" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        '</svg>'
    )
    return (
        f'<div class="brand-block">'
        f'  <div class="brand-icon">{svg_icon}</div>'
        f'  <div class="brand-text">'
        f'    <div class="brand-title">DocMind</div>'
        f'    <div class="brand-tagline">Chat with your documents</div>'
        f'  </div>'
        f'</div>'
    )


def sidebar_status_chip(doc_count: int, chunk_count: int) -> str:
    """Render the sidebar bottom status chip and demo disclaimer."""
    safe_docs = html.escape(str(doc_count))
    safe_chunks = html.escape(str(chunk_count))
    return (
        f'<div class="sidebar-status-container">'
        f'  <div class="sidebar-status-chip">'
        f'    <span class="status-dot"></span>'
        f'    <span>{safe_docs} documents &nbsp;|&nbsp; {safe_chunks} chunks</span>'
        f'  </div>'
        f'  <div class="sidebar-demo-caption">Demo — fictional law firm data</div>'
        f'</div>'
    )


def stat_card(label: str, value: str, icon: str, tone: str = "blue") -> str:
    """Render a pastel tinted stat card with an icon, label, and large number/text.

    Supported tones: 'mint', 'peach', 'blue', 'pink'.
    """
    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_icon = html.escape(icon)
    safe_tone = html.escape(tone.lower())

    return (
        f'<div class="stat-card stat-card-{safe_tone}">'
        f'  <div class="stat-card-header">'
        f'    <div class="stat-card-icon">{safe_icon}</div>'
        f'    <div class="stat-card-label">{safe_label}</div>'
        f'  </div>'
        f'  <div class="stat-card-value">{safe_value}</div>'
        f'</div>'
    )


def stat_cards_grid(cards_html: List[str]) -> str:
    """Wrap stat cards in a responsive grid container."""
    return f'<div class="stat-cards-grid">{"".join(cards_html)}</div>'


def source_mini_card(citation: str, score: float, snippet: str) -> str:
    """Render a styled mini card for a single source citation with relevance chip."""
    score_pct = int(score * 100)
    if score_pct >= 75:
        chip_class = "chip-green"
    elif score_pct >= 65:
        chip_class = "chip-amber"
    else:
        chip_class = "chip-muted"

    safe_citation = html.escape(citation)
    safe_snippet = html.escape(snippet)

    return (
        f'<div class="source-mini-card">'
        f'  <div class="source-header">'
        f'    <span class="source-label">{safe_citation}</span>'
        f'    <span class="relevance-chip {chip_class}">{score_pct}% Match</span>'
        f'  </div>'
        f'  <div class="source-snippet">"{safe_snippet}"</div>'
        f'</div>'
    )


def not_found_card(message: str) -> str:
    """Render a not-found answer in a soft amber card with an info icon."""
    safe_msg = html.escape(message)
    return (
        f'<div class="callout-card-amber">'
        f'  <div class="callout-icon">ℹ️</div>'
        f'  <div class="callout-text">{safe_msg}</div>'
        f'</div>'
    )


def demo_callout_card(text: str) -> str:
    """Render a soft amber callout card for demo/disclaimer notices."""
    safe_text = html.escape(text)
    return (
        f'<div class="callout-card-amber">'
        f'  <div class="callout-icon">ℹ️</div>'
        f'  <div class="callout-text">{safe_text}</div>'
        f'</div>'
    )


def file_type_chip(file_type: str) -> str:
    """Render a colored file format chip (PDF=red-ish, DOCX=blue, TXT=grey)."""
    ftype = (file_type or "DOC").upper().strip(".")
    if "PDF" in ftype:
        css_class = "type-chip-pdf"
    elif "DOC" in ftype:
        css_class = "type-chip-docx"
    elif "TXT" in ftype:
        css_class = "type-chip-txt"
    else:
        css_class = "type-chip-generic"

    return f'<span class="type-chip {css_class}">{html.escape(ftype)}</span>'
