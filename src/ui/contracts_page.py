"""Contract Analyzer page for law firm staff to extract and verify key contract terms."""

import html
from pathlib import Path
from typing import List, Optional
import streamlit as st

from src.contracts import (
    ContractAnalysis,
    ContractAnalysisAccessError,
    ContractAnalysisSizeError,
    analyze_contract,
    analysis_to_csv,
)
from src.loaders import DocUnit, DocumentLoadError, load_file
from src.ui.components import not_found_card, page_header, stat_card, stat_cards_grid
from src.ui.state import get_store


def _render_results(analysis: ContractAnalysis) -> None:
    """Render the 4 stat cards, results table, download button, and disclaimer."""
    # 1. Stat Cards
    found_str = f"{analysis.found_count} / {analysis.total_fields}"
    c1 = stat_card(label="Fields Found", value=found_str, icon="📋", tone="blue")
    c2 = stat_card(label="Verified", value=str(analysis.verified_count), icon="✓", tone="mint")
    c3 = stat_card(label="Not Stated", value=str(analysis.not_stated_count), icon="—", tone="peach")
    c4 = stat_card(label="Unverified", value=str(analysis.unverified_count), icon="⚠️", tone="pink")

    st.markdown(stat_cards_grid([c1, c2, c3, c4]), unsafe_allow_html=True)
    st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)

    # 2. Table Header
    rows_html: List[str] = []
    for f in analysis.fields:
        safe_label = html.escape(f.label)
        safe_val = html.escape(f.value)
        safe_quote = html.escape(f.quote)
        safe_cit = html.escape(f.citation)

        # Status badge styling
        if f.status == "Verified":
            status_badge = (
                '<span style="background-color: #DCFCE7; color: #166534; border: 1px solid #BBF7D0; '
                'padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; '
                'display: inline-block;">Verified</span>'
            )
            row_style = ""
        elif f.status == "Not stated":
            status_badge = (
                '<span style="background-color: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; '
                'padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; '
                'display: inline-block;">Not stated</span>'
            )
            row_style = 'style="background-color: #FFFDF5;"'
        else:
            status_badge = (
                '<span style="background-color: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; '
                'padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; '
                'display: inline-block;">Unverified</span>'
            )
            row_style = ""

        # Value cell
        if f.found:
            quote_block = ""
            if safe_quote:
                quote_block = (
                    f'<div style="color: #6B7280; font-size: 0.8rem; margin-top: 4px; font-style: italic;">'
                    f'"{safe_quote}"</div>'
                )
            value_html = f'<div style="font-weight: 600; color: #111827;">{safe_val}</div>{quote_block}'
        else:
            value_html = '<span style="color: #9CA3AF; font-style: italic;">Not stated in document</span>'

        # Citation cell
        if f.citation:
            cit_html = (
                f'<span style="background-color: #EEF2FF; color: #4338CA; border: 1px solid #C7D2FE; '
                f'padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 500;">'
                f'{safe_cit}</span>'
            )
        else:
            cit_html = '<span style="color: #9CA3AF;">—</span>'

        rows_html.append(
            f'<tr {row_style}>'
            f'  <td style="padding: 10px 14px; font-weight: 600; color: #1E1B4B; width: 18%; vertical-align: top;">{safe_label}</td>'
            f'  <td style="padding: 10px 14px; vertical-align: top;">{value_html}</td>'
            f'  <td style="padding: 10px 14px; vertical-align: top; width: 22%;">{cit_html}</td>'
            f'  <td style="padding: 10px 14px; vertical-align: top; width: 14%; text-align: center;">{status_badge}</td>'
            f'</tr>'
        )

    table_html = (
        '<div style="border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden; '
        'background-color: #FFFFFF; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04); margin-bottom: 1.25rem;">'
        '  <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 0.88rem;">'
        '    <thead>'
        '      <tr style="background-color: #F8FAFC; border-bottom: 1px solid #E5E7EB; color: #475569; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em;">'
        '        <th style="padding: 10px 14px;">Field</th>'
        '        <th style="padding: 10px 14px;">Extracted Value & Quote</th>'
        '        <th style="padding: 10px 14px;">Source Citation</th>'
        '        <th style="padding: 10px 14px; text-align: center;">Status</th>'
        '      </tr>'
        '    </thead>'
        '    <tbody style="divide-y: 1px solid #F1F5F9;">'
        + "".join(rows_html)
        + '    </tbody>'
        '  </table>'
        '</div>'
    )
    st.markdown(table_html, unsafe_allow_html=True)

    # 3. Actions & Metadata
    col_dl, col_meta = st.columns([1, 2])
    with col_dl:
        csv_data = analysis_to_csv(analysis)
        clean_name = Path(analysis.document_name).stem
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"{clean_name}_key_terms.csv",
            mime="text/csv",
            type="secondary",
        )

    with col_meta:
        cached_label = "Yes" if analysis.cached else "No"
        st.caption(
            f"Latency: {analysis.latency_ms:.1f} ms | Model: {analysis.model} | "
            f"Cached: {cached_label} | API calls: {analysis.api_calls}"
        )

    # 4. Disclaimer Callout
    disclaimer_html = (
        '<div class="callout-card-amber" style="margin-top: 1rem;">'
        '  <div class="callout-icon">ℹ️</div>'
        '  <div class="callout-text">'
        '    <b>Disclaimer:</b> This automated contract key-terms extraction is generated by AI for preliminary '
        '    review purposes only and does not constitute formal legal advice or a binding legal opinion. '
        '    Always verify terms against original executed agreements.'
        '  </div>'
        '</div>'
    )
    st.markdown(disclaimer_html, unsafe_allow_html=True)


def render_contracts_page(role: str = "Staff") -> None:
    """Render the Contract Analyzer page."""
    # Strict role verification
    if (role or "").strip().lower() != "staff":
        st.markdown(
            not_found_card(
                "Access Restricted: Contract Analyzer is available to Law Firm Staff only. "
                "Please switch to Staff mode in the sidebar to access this tool."
            ),
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        page_header(
            "Contract Key Terms Analyzer",
            "Extract, cross-reference, and verify 14 critical contractual terms with verbatim citations.",
        ),
        unsafe_allow_html=True,
    )

    store = get_store()
    sources = store.list_sources(allowed_visibility={"client", "staff"})

    # Sort sources so Corporate, Property, or Contracts documents are preferred first
    contract_keywords = ("agreement", "lease", "contract", "corporate", "property")
    sorted_sources = sorted(
        sources,
        key=lambda s: (
            0 if any(k in s["name"].lower() or k in s.get("practice_area", "").lower() for k in contract_keywords) else 1,
            s["name"].lower(),
        ),
    )
    source_names = [s["name"] for s in sorted_sources]

    col_select, col_upload = st.columns([1, 1], gap="large")

    with col_select:
        st.markdown("#### Select Indexed Contract")
        selected_doc = st.selectbox(
            "Select an indexed document to analyze",
            options=source_names if source_names else ["No documents found"],
            index=0 if source_names else 0,
            label_visibility="collapsed",
            key="contract_selected_doc",
        )
        st.caption("Analyzes the full document text directly from the firm's indexed knowledge base.")

    with col_upload:
        st.markdown("#### Or Upload New Contract")
        uploaded_file = st.file_uploader(
            "Upload contract (.pdf, .docx, .txt)",
            type=["pdf", "docx", "txt"],
            label_visibility="collapsed",
            key="contract_uploaded_file",
        )
        st.caption("Processed entirely in-memory for instant analysis. Not indexed or stored in the database.")

    st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)

    if st.button("Analyze contract", type="primary", use_container_width=False, key="btn_run_contract_analysis"):
        try:
            with st.spinner("Extracting 14 contractual terms and verifying citations..."):
                if uploaded_file is not None:
                    # In-memory load from raw bytes
                    file_bytes = uploaded_file.getvalue()
                    doc_units = load_file(file_bytes, filename=uploaded_file.name)
                    doc_name = uploaded_file.name
                else:
                    if not source_names or selected_doc == "No documents found":
                        st.error("Please select a valid indexed document or upload a contract file.")
                        return
                    # Retrieve from vector store
                    doc_units = store.get_source_units(selected_doc, allowed_visibility={"staff", "client"})
                    doc_name = selected_doc

                if not doc_units:
                    st.error(f"Could not load content units for document '{doc_name}'.")
                    return

                analysis = analyze_contract(
                    units=doc_units,
                    document_name=doc_name,
                    access_mode="staff",
                )
                st.session_state["active_contract_analysis"] = analysis

        except ContractAnalysisAccessError as e:
            st.error(f"Access Denied: {e}")
        except ContractAnalysisSizeError as e:
            st.error(f"Document Size Error: {e}")
        except DocumentLoadError as e:
            st.error(f"Document Loading Error: {e}")
        except Exception as e:
            st.error(f"Analysis failed: {e}")

    # Display active analysis if present in session state
    if "active_contract_analysis" in st.session_state:
        st.markdown("---")
        analysis = st.session_state["active_contract_analysis"]
        st.markdown(f"### Analysis Results: `{analysis.document_name}`")
        _render_results(analysis)
