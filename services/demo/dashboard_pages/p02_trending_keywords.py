"""Trending Keywords page — raw + news_sampled with filters and detail expander."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import pandas as pd
import streamlit as st

from datetime import datetime, timedelta, timezone

from dashboard_pages._api import get_keywords_by_status, format_wib
from dashboard_pages._theme import inject_theme, COLORS, STATUS_COLORS
from dashboard_pages.components._freshness_indicator import render_freshness_indicator
from dashboard_pages.components._status_badge import render_status_badge, render_source_badge
from dashboard_pages.components._detail_expander import render_keyword_detail_expander


DATE_PRESETS = {
    "Last 24h": 1,
    "Last 48h": 2,
    "Last 7d": 7,
    "All time": None,
}


def render():
    inject_theme()
    st.title("Trending Keywords")

    # ── Filters ────────────────────────────────────────────────────────────────
    c_src, c_date = st.columns([1, 2])
    with c_src:
        source = st.selectbox("Source", ["All", "trends24", "google_trends"])
    with c_date:
        date_preset = st.selectbox("Time range", list(DATE_PRESETS.keys()))

    since = None
    if DATE_PRESETS[date_preset]:
        delta = DATE_PRESETS[date_preset]
        since = (datetime.now(timezone.utc) - timedelta(days=delta)).isoformat()

    src_filter = source if source != "All" else None

    # ── Fetch raw + news_sampled ───────────────────────────────────────────────
    with st.spinner("Loading trending keywords…"):
        raw_items, raw_fetched = get_keywords_by_status(
            "raw", limit=200, since=since, source=src_filter
        )
        sampled_items, sampled_fetched = get_keywords_by_status(
            "news_sampled", limit=200, since=since, source=src_filter
        )

    all_items = raw_items + sampled_items
    fetched_at = max(raw_fetched, sampled_fetched)
    render_freshness_indicator(fetched_at)

    # ── Aggregate stats ────────────────────────────────────────────────────────
    total_raw = sum(1 for it in all_items if it.status == "raw")
    total_sampled = sum(1 for it in all_items if it.status == "news_sampled")
    total = total_raw + total_sampled

    s1, s2, s3 = st.columns(3)
    s1.metric("Total Keywords", total)
    s2.metric("Raw (awaiting sampler)", total_raw)
    s3.metric("News Sampled", total_sampled)

    st.divider()

    # ── Table ──────────────────────────────────────────────────────────────────
    if all_items:
        rows = []
        for it in all_items:
            rows.append({
                "Keyword": it.keyword,
                "Source": it.source,
                "Rank": it.rank or "—",
                "Status": it.status,
                "Scraped At (WIB)": format_wib(it.scraped_at),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)

        st.markdown("**Click a keyword to expand details**")
        for it in all_items:
            render_keyword_detail_expander(it.id, it.keyword)
    else:
        st.info("No trending keywords found. Trigger a scrape cycle first.")
