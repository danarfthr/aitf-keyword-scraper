"""LLM Decisions & Enriched — unified view of all LLM-processed keywords."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import pandas as pd
import streamlit as st

from datetime import datetime, timedelta, timezone

from dashboard_pages._api import get_all_keywords, format_wib
from dashboard_pages._theme import inject_theme, COLORS
from dashboard_pages.components._freshness_indicator import render_freshness_indicator
from dashboard_pages.components._detail_expander import render_keyword_detail_expander


DATE_PRESETS = {
    "Last 24h": 1,
    "Last 48h": 2,
    "Last 7d": 7,
    "All time": None,
}


def render():
    inject_theme()
    st.title("LLM Decisions & Enriched")
    st.caption(
        "All keywords that have passed through LLM processing — relevant (enriched) and not-relevant (expired) outcomes in one unified view."
    )

    # ── Filters ────────────────────────────────────────────────────────────────
    c_status, c_relevance, c_date, c_src = st.columns([1, 1, 2, 1])

    with c_status:
        status_filter = st.selectbox(
            "Status",
            ["All", "news_sampled", "enriched", "expired", "failed"],
        )
    with c_relevance:
        relevance_filter = st.selectbox(
            "Relevance",
            ["All", "Relevant only", "Not relevant"],
        )
    with c_date:
        date_preset = st.selectbox("Time range", list(DATE_PRESETS.keys()))
    with c_src:
        source = st.selectbox("Source", ["All", "trends24", "google_trends"])

    since = None
    if DATE_PRESETS[date_preset]:
        since = (
            datetime.now(timezone.utc) - timedelta(days=DATE_PRESETS[date_preset])
        ).isoformat()

    src_filter = source if source != "All" else None

    # Determine status param for API call
    if status_filter == "All":
        status_param = "news_sampled,enriched,expired,failed"
    else:
        status_param = status_filter

    # ── Fetch ─────────────────────────────────────────────────────────────────
    with st.spinner("Loading LLM decisions…"):
        items, fetched_at = get_all_keywords(
            status=status_param,
            limit=500,
            since=since,
            source=src_filter,
            include_relevant=True,
        )

    render_freshness_indicator(fetched_at)

    # ── Stats ────────────────────────────────────────────────────────────────
    total = len(items)
    relevant_count = sum(1 for it in items if it.is_relevant is True)
    not_relevant_count = sum(1 for it in items if it.is_relevant is False)
    pending_count = sum(1 for it in items if it.is_relevant is None)

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Total Decisions", total)
    s2.metric("Relevant", relevant_count)
    s3.metric("Not Relevant", not_relevant_count)
    s4.metric("Pending", pending_count)

    st.divider()

    # ── Apply relevance filter ────────────────────────────────────────────────
    if relevance_filter == "Relevant only":
        items = [it for it in items if it.is_relevant is True]
    elif relevance_filter == "Not relevant":
        items = [it for it in items if it.is_relevant is False]

    # ── Table ─────────────────────────────────────────────────────────────────
    if items:
        rows = []
        for it in items:
            rows.append({
                "Keyword": it.keyword,
                "Source": it.source,
                "Rank": it.rank or "—",
                "Status": it.status or "unknown",
                "Relevant": (
                    "YES" if it.is_relevant is True else
                    "NO" if it.is_relevant is False else "—"
                ),
                "Scraped At (WIB)": format_wib(it.scraped_at),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)

        st.markdown("**Click a keyword to expand details**")
        for it in items:
            render_keyword_detail_expander(it.id, it.keyword)
    else:
        st.info("No LLM decisions found yet. Sampler may still be collecting articles.")