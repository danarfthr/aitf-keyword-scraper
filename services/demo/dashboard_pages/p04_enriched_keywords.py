"""Enriched Keywords page — enriched keywords with expanded term chips."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import pandas as pd
import streamlit as st

from datetime import datetime, timedelta, timezone

from dashboard_pages._api import get_enriched, format_wib
from dashboard_pages._theme import inject_theme, COLORS
from dashboard_pages.components._freshness_indicator import render_freshness_indicator
from dashboard_pages.components._status_badge import render_source_badge
from dashboard_pages.components._detail_expander import render_keyword_detail_expander


DATE_PRESETS = {
    "Last 24h": 1,
    "Last 48h": 2,
    "Last 7d": 7,
    "All time": None,
}


def render():
    inject_theme()
    st.title("Enriched Keywords")

    # ── Filters ────────────────────────────────────────────────────────────────
    c_src, c_date, c_search = st.columns([1, 2, 2])
    with c_src:
        source = st.selectbox("Source", ["All", "trends24", "google_trends"])
    with c_date:
        date_preset = st.selectbox("Time range", list(DATE_PRESETS.keys()))
    with c_search:
        search = st.text_input("Search keyword", "")

    since = None
    if DATE_PRESETS[date_preset]:
        since = (
            datetime.now(timezone.utc) - timedelta(days=DATE_PRESETS[date_preset])
        ).isoformat()

    src_filter = source if source != "All" else None

    # ── Fetch ─────────────────────────────────────────────────────────────────
    with st.spinner("Loading enriched keywords…"):
        items, fetched_at = get_enriched(limit=300, since=since, source=src_filter)

    render_freshness_indicator(fetched_at)

    # ── Aggregate stats ───────────────────────────────────────────────────────
    total = len(items)
    total_expanded = sum(len(it.expanded_keywords) for it in items)
    avg_expanded = total_expanded / total if total > 0 else 0
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    new_today = sum(
        1 for it in items
        if it.scraped_at and datetime.fromisoformat(it.scraped_at.replace("Z", "+00:00")) >= today_start
    )

    s1, s2, s3 = st.columns(3)
    s1.metric("Total Enriched", total)
    s2.metric("Avg Expanded Terms", f"{avg_expanded:.1f}")
    s3.metric("New Today", new_today)

    st.divider()

    # ── Table ─────────────────────────────────────────────────────────────────
    if items:
        rows = []
        for it in items:
            if search and search.lower() not in it.keyword.lower():
                continue
            rows.append({
                "Keyword": it.keyword,
                "Source": it.source,
                "Rank": it.rank or "—",
                "Expanded Terms": len(it.expanded_keywords),
                "Scraped At (WIB)": format_wib(it.scraped_at),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)

        st.markdown("**Click a keyword to expand details**")
        for it in items:
            if search and search.lower() not in it.keyword.lower():
                continue
            render_keyword_detail_expander(it.id, it.keyword)
    else:
        st.info("No enriched keywords found yet. LLM enrichment may still be running.")
