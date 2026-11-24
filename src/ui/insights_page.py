"""Knowledge Insights & Analytics dashboard for law firm staff."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
import streamlit as st

from src.analytics import AnalyticsAccessError, gaps_to_csv
from src.config import DEMO_MODE
from src.ui.components import page_header, stat_card, stat_cards_grid
from src.ui.state import get_analytics, get_store, get_browser_session_id


def render_insights_page(role: str = "Staff") -> None:
    """Render the Knowledge Insights telemetry dashboard."""
    # Strict role access check: Staff only
    if (role or "").strip().lower() != "staff":
        st.markdown(
            page_header(
                title="Knowledge Insights",
                subtitle="Law firm knowledge base gaps and query telemetry",
            ),
            unsafe_allow_html=True,
        )
        st.error(
            "Staff Access Required: Knowledge Insights and telemetry are restricted to law firm "
            "staff members only. Please switch to Staff mode in the sidebar."
        )
        return

    st.markdown(
        page_header(
            title="Knowledge Insights",
            subtitle="Law firm knowledge base gaps, query trends, and document utilization",
        ),
        unsafe_allow_html=True,
    )

    analytics = get_analytics()
    store = get_store()
    sess_id = get_browser_session_id() if DEMO_MODE else None

    if DEMO_MODE:
        st.markdown(
            """
            <div style="display: inline-flex; align-items: center; gap: 0.5rem; background: #EEF2FF; color: #4F46E5; padding: 0.35rem 0.75rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 500; margin-bottom: 1rem; border: 1px solid #C7D2FE;">
                <span>🔒 Demo activity + your session</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        from src.demo_limits import is_generation_budget_near_limit
        near_limit, limit_notice = is_generation_budget_near_limit()
        if near_limit:
            st.info(f"ℹ️ {limit_notice}")

    # Filter Bar
    col_period, col_aud, _ = st.columns([2, 2, 4])
    with col_period:
        period_choice = st.segmented_control(
            "Time Period",
            options=["7 days", "14 days", "30 days"],
            default="14 days",
            key="insights_period",
        )
    with col_aud:
        aud_choice = st.segmented_control(
            "Audience",
            options=["All", "Clients", "Staff"],
            default="All",
            key="insights_audience",
        )

    period_days = int((period_choice or "14 days").split()[0])
    audience_filter = "all" if aud_choice in ("All", None) else ("client" if aud_choice == "Clients" else "staff")

    known_sources = [s["name"] for s in store.list_sources()]

    try:
        summary = analytics.summary(
            access_mode="staff",
            period_days=period_days,
            audience=audience_filter,
            known_sources=known_sources,
            session_id=sess_id,
        )
    except AnalyticsAccessError as exc:
        st.error(str(exc))
        return

    # Empty State Handling
    if summary.total_queries == 0:
        st.markdown(
            """
            <div style="background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 14px;
                        padding: 2.5rem 1.5rem; text-align: center; margin: 1.5rem 0;">
                <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">📊</div>
                <div style="font-size: 1.15rem; font-weight: 600; color: #111827; margin-bottom: 0.5rem;">
                    No Query Telemetry Recorded
                </div>
                <div style="font-size: 0.875rem; color: #6B7280; max-width: 480px; margin: 0 auto 1.5rem auto;">
                    No searches have been recorded in the selected period and audience filter.
                    You can populate synthetic demo activity to preview the analytics dashboard.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚀 Load Demo Activity", type="primary", use_container_width=False):
            try:
                loaded = analytics.load_seed("data/demo_activity")
                st.success(f"Successfully loaded {loaded} synthetic queries across the past 14 business days!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to load demo seed: {e}")
        return

    # 1. Four Stat Cards Grid
    c1 = stat_card(label="Total Queries", value=str(summary.total_queries), icon="📊", tone="blue")
    c2 = stat_card(label="Answer Rate", value=f"{summary.answer_rate:.1f}%", icon="✓", tone="mint")
    gap_cnt = len(summary.gaps)
    c3 = stat_card(label="Knowledge Gaps", value=f"{gap_cnt} clusters", icon="⚠️", tone="peach")
    lat_sec = summary.avg_latency_ms / 1000.0
    lat_str = f"{lat_sec:.1f}s avg" if lat_sec > 0 else "0.0s"
    c4 = stat_card(label="Avg Latency", value=lat_str, icon="⚡", tone="pink")

    st.markdown(stat_cards_grid([c1, c2, c3, c4]), unsafe_allow_html=True)
    st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

    # 2. Daily Query Activity (Stacked Bar Chart)
    if summary.daily_series:
        st.markdown(
            '<div style="font-size: 1.1rem; font-weight: 600; color: #111827; margin-bottom: 0.5rem;">'
            'Daily Query Activity'
            '</div>',
            unsafe_allow_html=True,
        )
        chart_data = []
        for day in summary.daily_series:
            chart_data.append({
                "Date": day["date"],
                "Answered": day["answered"],
                "Knowledge Gaps": day["not_found"],
                "Errors": day["errors"],
            })
        df_chart = pd.DataFrame(chart_data)
        st.bar_chart(
            df_chart,
            x="Date",
            y=["Answered", "Knowledge Gaps", "Errors"],
            color=["#4F46E5", "#F59E0B", "#EF4444"],
            height=280,
        )
        st.markdown("<div style='margin-top: 1.75rem;'></div>", unsafe_allow_html=True)

    # 3. Knowledge Gaps Section
    st.markdown(
        '<div style="font-size: 1.1rem; font-weight: 600; color: #111827; margin-bottom: 0.25rem;">'
        'Knowledge Gaps (Unanswered Questions)'
        '</div>'
        '<div style="font-size: 0.85rem; color: #6B7280; margin-bottom: 1rem;">'
        'Questions where the document collection lacked sufficient coverage (similarity score &lt; 0.65 or below threshold).'
        '</div>',
        unsafe_allow_html=True,
    )

    if summary.gaps:
        # Render Knowledge Gaps Table
        gaps_rows = []
        for g in summary.gaps:
            safe_cid = html.escape(str(g["cluster_id"]))
            safe_rep = html.escape(str(g["representative_query"]))
            safe_count = html.escape(str(g["count"]))
            safe_src = html.escape(str(g["top_source"]))
            safe_score = f"{g['avg_top_score']:.2f}"
            action = g["suggested_action"]

            if action == "Add new content":
                action_badge = (
                    '<span style="background-color: #FEE2E2; color: #991B1B; border: 1px solid #FECACA; '
                    'padding: 3px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600;">'
                    'Add new content</span>'
                )
            else:
                action_badge = (
                    '<span style="background-color: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; '
                    'padding: 3px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600;">'
                    'Expand existing doc</span>'
                )

            samples_html = "".join(f"<li style='margin-bottom: 2px;'>{html.escape(s)}</li>" for s in g.get("sample_queries", []))

            gaps_rows.append(
                f'<tr>'
                f'  <td style="padding: 10px 12px; font-weight: 600; color: #4F46E5; text-align: center;">#{safe_cid}</td>'
                f'  <td style="padding: 10px 12px; font-weight: 500; color: #111827;">'
                f'    <div>{safe_rep}</div>'
                f'    <ul style="margin: 4px 0 0 16px; padding: 0; font-size: 0.8rem; color: #6B7280;">{samples_html}</ul>'
                f'  </td>'
                f'  <td style="padding: 10px 12px; text-align: center; font-weight: 600; color: #1F2937;">{safe_count}</td>'
                f'  <td style="padding: 10px 12px; font-size: 0.825rem; color: #4B5563;">{safe_src}<br><span style="color: #9CA3AF;">(sim: {safe_score})</span></td>'
                f'  <td style="padding: 10px 12px; text-align: center;">{action_badge}</td>'
                f'</tr>'
            )

        table_html = (
            f'<div style="overflow-x: auto; border: 1px solid #E5E7EB; border-radius: 12px; background: #FFFFFF; margin-bottom: 1rem;">'
            f'<table style="width: 100%; border-collapse: collapse; font-size: 0.875rem; text-align: left;">'
            f'  <thead>'
            f'    <tr style="background-color: #F9FAFB; border-bottom: 1px solid #E5E7EB; color: #4B5563;">'
            f'      <th style="padding: 10px 12px; width: 60px; text-align: center;">ID</th>'
            f'      <th style="padding: 10px 12px;">Representative Topic & Sample Questions</th>'
            f'      <th style="padding: 10px 12px; width: 80px; text-align: center;">Count</th>'
            f'      <th style="padding: 10px 12px; width: 220px;">Closest Match</th>'
            f'      <th style="padding: 10px 12px; width: 160px; text-align: center;">Suggested Action</th>'
            f'    </tr>'
            f'  </thead>'
            f'  <tbody style="divide-y: 1px solid #F3F4F6;">'
            f'    {"".join(gaps_rows)}'
            f'  </tbody>'
            f'</table>'
            f'</div>'
        )
        st.markdown(table_html, unsafe_allow_html=True)

        # Download CSV Button
        csv_data = gaps_to_csv(summary.gaps)
        today_str = datetime.now().strftime("%Y%m%d")
        st.download_button(
            label="📥 Download Knowledge Gaps Report (CSV)",
            data=csv_data,
            file_name=f"docmind_knowledge_gaps_{today_str}.csv",
            mime="text/csv",
            use_container_width=False,
        )
    else:
        st.info("No knowledge gaps identified in this window.")

    st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)

    # 4. Two Column Layout: Top Questions & Document Usage
    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.markdown(
            '<div style="font-size: 1.1rem; font-weight: 600; color: #111827; margin-bottom: 0.25rem;">'
            'Most Asked Questions'
            '</div>'
            '<div style="font-size: 0.85rem; color: #6B7280; margin-bottom: 0.75rem;">'
            'High-frequency queries across clients and staff.'
            '</div>',
            unsafe_allow_html=True,
        )
        if summary.top_questions:
            q_rows = []
            for item in summary.top_questions[:7]:
                safe_q = html.escape(item["question"])
                safe_cnt = html.escape(str(item["count"]))
                safe_aud = html.escape(item["audience"])
                q_rows.append(
                    f'<div style="background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;">'
                    f'  <div style="font-weight: 500; font-size: 0.875rem; color: #111827;">{safe_q}</div>'
                    f'  <div style="font-size: 0.75rem; color: #6B7280; margin-top: 4px; display: flex; justify-content: space-between;">'
                    f'    <span>Asked <strong>{safe_cnt}</strong> times</span>'
                    f'    <span>Audience: <strong>{safe_aud}</strong></span>'
                    f'  </div>'
                    f'</div>'
                )
            st.markdown("".join(q_rows), unsafe_allow_html=True)
        else:
            st.caption("No queries recorded.")

    with col_right:
        st.markdown(
            '<div style="font-size: 1.1rem; font-weight: 600; color: #111827; margin-bottom: 0.25rem;">'
            'Document Utilization'
            '</div>'
            '<div style="font-size: 0.85rem; color: #6B7280; margin-bottom: 0.75rem;">'
            'Documents cited or retrieved to answer questions.'
            '</div>',
            unsafe_allow_html=True,
        )
        if summary.doc_usage:
            u_rows = []
            for item in summary.doc_usage[:6]:
                safe_doc = html.escape(item["source"])
                safe_cit = html.escape(str(item["citation_count"]))
                safe_qry = html.escape(str(item["query_count"]))
                u_rows.append(
                    f'<div style="background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;">'
                    f'  <div style="font-weight: 500; font-size: 0.85rem; color: #111827;">{safe_doc}</div>'
                    f'  <div style="font-size: 0.75rem; color: #6B7280; margin-top: 4px;">'
                    f'    Cited in <strong>{safe_cit}</strong> answers &nbsp;|&nbsp; Top match for <strong>{safe_qry}</strong> queries'
                    f'  </div>'
                    f'</div>'
                )
            st.markdown("".join(u_rows), unsafe_allow_html=True)

        if summary.unused_docs:
            st.markdown(
                '<div style="margin-top: 1rem; font-size: 0.875rem; font-weight: 600; color: #4B5563;">'
                'Unreferenced Indexed Documents:'
                '</div>',
                unsafe_allow_html=True,
            )
            unused_html = "".join(
                f'<span style="background: #F3F4F6; border: 1px solid #E5E7EB; padding: 3px 8px; '
                f'border-radius: 6px; font-size: 0.75rem; color: #4B5563; margin-right: 6px; display: inline-block; margin-bottom: 4px;">'
                f'{html.escape(d)}</span>'
                for d in summary.unused_docs
            )
            st.markdown(f'<div style="margin-top: 6px;">{unused_html}</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 2.5rem;'></div>", unsafe_allow_html=True)

    # 5. Footer Analytics Data Management Expander
    with st.expander("⚙️ Analytics Data Management", expanded=False):
        counts = analytics.count()
        c_tot, c_liv, c_syn = st.columns(3)
        c_tot.metric("Total Events", counts["total"])
        c_liv.metric("Live Organic Queries", counts["live"])
        c_syn.metric("Synthetic Demo Queries", counts["synthetic"])

        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
        if DEMO_MODE:
            st.caption("Analytics reset and seeding controls are disabled in public demo mode.")
        else:
            b_col1, b_col2, b_col3, _ = st.columns([2, 2, 2, 4])
            with b_col1:
                if st.button("Reload Demo Activity", use_container_width=True):
                    try:
                        loaded = analytics.load_seed("data/demo_activity")
                        st.success(f"Loaded {loaded} synthetic events.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error loading seed: {e}")
            with b_col2:
                if st.button("Clear Demo Activity", use_container_width=True):
                    deleted = analytics.clear_synthetic()
                    st.info(f"Removed {deleted} synthetic events.")
                    st.rerun()
            with b_col3:
                if st.button("Clear All Data", type="secondary", use_container_width=True):
                    analytics.clear_all()
                    st.warning("All analytics events cleared.")
                    st.rerun()
