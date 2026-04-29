"""All Keywords page — every keyword across all statuses with filtering."""

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


ALL_STATUSES = ["raw", "news_sampled", "enriched", "expired", "failed"]

DATE_PRESETS = {
    "Last 24h": 1,
    "Last 48h": 2,
    "Last 7d": 7,
    "All time": None,
}


def render():
    inject_theme()
    st.title("All Keywords")
    st.caption("Every keyword across every status — including archived/expired. Use filters to narrow down.")

    # ── Filters ────────────────────────────────────────────────────────────────
    c_status, c_date, c_src, c_search = st.columns([2, 2, 1, 2])

    with c_status:
        selected_statuses = st.multiselect(
            "Status",
            ALL_STATUSES,
            default=ALL_STATUSES,
        )
    with c_date:
        date_preset = st.selectbox("Time range", list(DATE_PRESETS.keys()))
    with c_src:
        source = st.selectbox("Source", ["All", "trends24", "google_trends"])
    with c_search:
        search = st.text_input("Search keyword", "")

    since = None
    if DATE_PRESETS[date_preset]:
        since = (
            datetime.now(timezone.utc) - timedelta(days=DATE_PRESETS[date_preset])
        ).isoformat()

    src_filter = source if source != "All" else None
    status_param = ",".join(selected_statuses) if selected_statuses else "all"

    # ── Fetch ─────────────────────────────────────────────────────────────────
    with st.spinner("Loading all keywords…"):
        items, fetched_at = get_all_keywords(
            status=status_param,
            limit=500,
            since=since,
            source=src_filter,
            search=search if search else None,
            include_relevant=True,
        )

    render_freshness_indicator(fetched_at)

    # ── Aggregate stats ───────────────────────────────────────────────────────
    total = len(items)
    by_status: dict[str, int] = {}
    for s in ALL_STATUSES:
        by_status[s] = sum(1 for it in items if _infer_status(it) == s)

    s1, s2, s3, s4, s5, s6 = st.columns(6)
    s1.metric("Total", total)
    s2.metric("Raw", by_status.get("raw", 0))
    s3.metric("Sampled", by_status.get("news_sampled", 0))
    s4.metric("Enriched", by_status.get("enriched", 0))
    s5.metric("Expired", by_status.get("expired", 0))
    s6.metric("Failed", by_status.get("failed", 0))

    st.divider()

    # ── Table ─────────────────────────────────────────────────────────────────
    if items:
        rows = []
        for it in items:
            inf_status = _infer_status(it)
            rows.append({
                "Keyword": it.keyword,
                "Source": it.source,
                "Rank": it.rank or "—",
                "Status": inf_status,
                "Relevant": ("YES" if it.is_relevant is True else
                             "NO" if it.is_relevant is False else "—"),
                "Scraped At (WIB)": format_wib(it.scraped_at),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)

        st.markdown("**Click a keyword to expand details**")
        for it in items:
            render_keyword_detail_expander(it.id, it.keyword)
    else:
        st.info("No keywords match the current filters.")


def _infer_status(item) -> str:
    return item.status or "unknown"