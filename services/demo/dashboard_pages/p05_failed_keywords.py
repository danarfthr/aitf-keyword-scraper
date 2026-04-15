"""Failed Keywords page — failed keywords with retry controls."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import pandas as pd
import streamlit as st

from datetime import datetime, timedelta, timezone

from dashboard_pages._api import get_keywords_by_status, format_wib
from dashboard_pages._theme import inject_theme, COLORS
from dashboard_pages.components._freshness_indicator import render_freshness_indicator
from dashboard_pages.components._status_badge import render_source_badge
from dashboard_pages.components._detail_expander import render_keyword_detail_expander


RETRY_COOLDOWN_SECONDS = 30 * 60  # 30 minutes


def render():
    inject_theme()
    st.title("Failed Keywords")
    st.caption("Keywords that failed LLM processing — auto-retry after 30 min cooldown. Persistent failures may indicate an API or scraper issue.")
    st.button("Retry Now", type="secondary")

    # ── Fetch ─────────────────────────────────────────────────────────────────
    with st.spinner("Loading failed keywords…"):
        items, fetched_at = get_keywords_by_status(
            "failed", limit=200, include_relevant=False
        )

    render_freshness_indicator(fetched_at)

    # ── Stats ─────────────────────────────────────────────────────────────────
    total = len(items)
    now = datetime.now(timezone.utc)

    # Compute retry countdown based on oldest failure
    countdown_seconds = None
    if items:
        oldest_updated = None
        for it in items:
            if it.scraped_at:
                try:
                    updated = datetime.fromisoformat(it.scraped_at.replace("Z", "+00:00"))
                    if oldest_updated is None or updated < oldest_updated:
                        oldest_updated = updated
                except ValueError:
                    pass
        if oldest_updated:
            elapsed = (now - oldest_updated).total_seconds()
            remaining = RETRY_COOLDOWN_SECONDS - elapsed
            if remaining > 0:
                countdown_seconds = int(remaining)

    failed_today = sum(
        1 for it in items
        if it.scraped_at and
        datetime.fromisoformat(it.scraped_at.replace("Z", "+00:00")).date() == now.date()
    )

    s1, s2, s3 = st.columns(3)
    s1.metric("Total Failed", total)
    s2.metric("Failed Today", failed_today)
    if countdown_seconds is not None:
        mins = countdown_seconds // 60
        secs = countdown_seconds % 60
        s3.metric("Auto-retry in", f"{mins}m {secs}s")
    else:
        s3.metric("Auto-retry", "Available")

    st.divider()

    # ── Table ─────────────────────────────────────────────────────────────────
    if items:
        rows = []
        for it in items:
            rows.append({
                "Keyword": it.keyword,
                "Source": it.source,
                "Rank": it.rank or "—",
                "Failed At (WIB)": format_wib(it.scraped_at),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)

        st.markdown("**Click a keyword to expand details**")
        for it in items:
            render_keyword_detail_expander(it.id, it.keyword)
    else:
        st.success("No failed keywords. All processing successful so far!")
