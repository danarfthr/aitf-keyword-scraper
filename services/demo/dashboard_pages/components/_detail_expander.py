"""Keyword detail expander component."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import streamlit as st

from dashboard_pages._api import get_keyword_detail, format_wib
from dashboard_pages._theme import inject_theme, COLORS, STATUS_COLORS, RELEVANCE_COLORS, SOURCE_COLORS
from dashboard_pages.components._status_badge import render_status_badge, render_source_badge

_STATUS_HINTS = {
    "raw": "Scraped from Google Trends or Trends24 — awaiting news sampling.",
    "news_sampled": "News articles sampled from detik/kompas/tribun — awaiting LLM processing.",
    "enriched": "Enrichment complete — keyword is ready for Team 4.",
    "failed": "LLM processing failed — will auto-retry after 30 min cooldown.",
    "expired": "No longer trending — archived after 24h of inactivity.",
}


def render_keyword_detail_expander(keyword_id: int, keyword_label: str) -> None:
    """Lazy-load and render full keyword detail on expand."""
    inject_theme()

    with st.expander(f" {keyword_label}", expanded=False):
        detail = get_keyword_detail(keyword_id)
        if detail is None:
            st.error("Could not load keyword details.")
            return

        # Keyword meta
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Source:** `{detail.source}`")
        c2.markdown(f"**Rank:** `{detail.rank}`")
        c3.markdown(
            f"**Status:** {render_status_badge(detail.status)}",
            unsafe_allow_html=True,
        )

        if detail.failure_reason:
            st.error(f"**Failure reason:** {detail.failure_reason}")

        st.divider()

        # Tabs: Overview | Articles | Justification | Enrichment
        tabs = st.tabs(["Overview", "Articles", "Justification", "Enrichment"])

        with tabs[0]:
            _render_overview(detail)

        with tabs[1]:
            _render_articles(detail)

        with tabs[2]:
            _render_justification(detail)

        with tabs[3]:
            _render_enrichment(detail)


def _render_overview(detail) -> None:
    st.markdown(f"**Keyword:** `{detail.keyword}`")
    st.markdown(f"**Scraped at:** `{format_wib(detail.scraped_at)}`")
    st.markdown(f"**Last updated:** `{format_wib(detail.updated_at)}`")
    st.markdown(f"**Status:** {render_status_badge(detail.status)}", unsafe_allow_html=True)
    st.caption(_STATUS_HINTS.get(detail.status, ""))
    if detail.failure_reason:
        st.error(f"**Failure:** {detail.failure_reason}")


def _render_articles(detail) -> None:
    if not detail.articles:
        st.info("No articles sampled for this keyword.")
        return
    for art in detail.articles:
        with st.container():
            col1, col2 = st.columns([4, 1])
            col1.markdown(f"**[{art.title or '(no title)'}]({art.url})**")
            col1.caption(f"{art.source_site} · {format_wib(art.crawled_at)}")
            st.divider()


def _render_justification(detail) -> None:
    if not detail.justification:
        st.info("No justification available yet.")
        return
    just = detail.justification
    color = RELEVANCE_COLORS.get(just.is_relevant, "#94a3b8")
    badge = "RELEVANT" if just.is_relevant else "NOT RELEVANT"
    st.markdown(
        f'<span style="color:{color}; font-weight:700; font-size:1.1rem;">{badge}</span>',
        unsafe_allow_html=True,
    )
    if just.justification:
        st.markdown(f"> {just.justification}")
    st.caption(f"Model: `{just.llm_model}` · Processed: {format_wib(just.processed_at)}")


def _render_enrichment(detail) -> None:
    if not detail.enrichment:
        st.info("No enrichment data available yet.")
        return
    enrich = detail.enrichment
    st.markdown(f"**Expanded keywords ({len(enrich.expanded_keywords)}):**")
    chips_html = " ".join(
        f'<span class="kw-chip">{kw}</span>' for kw in enrich.expanded_keywords
    )
    st.markdown(chips_html, unsafe_allow_html=True)
    st.caption(f"Model: `{enrich.llm_model}` · Processed: {format_wib(enrich.processed_at)}")
