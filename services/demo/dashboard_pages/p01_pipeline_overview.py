"""Pipeline Overview page — KPIs, throughput, stuck alerts."""

import os
import sys as _sys

# Allow pages package to import its own submodules
_d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard_pages._api import get_health, get_stuck, trigger_scrape, format_wib
from dashboard_pages._theme import inject_theme, COLORS, STATUS_COLORS, ALERT_COLORS
from dashboard_pages.components._freshness_indicator import render_freshness_indicator
from dashboard_pages.components._status_badge import render_status_badge


def render():
    inject_theme()

    st.title("Pipeline Overview")
    render_freshness_indicator(st.session_state.get("_health_fetched_at", 0))

    # Auto-refresh every 30s (non-blocking)
    st_autorefresh(interval=30_000, key="pipeline_refresh")

    health = get_health()
    stuck = get_stuck()
    st.session_state["_health_fetched_at"] = health.fetched_at

    # ── KPI row ────────────────────────────────────────────────────────────────
    total = sum(health.counts.values())
    enriched = health.counts.get("enriched", 0)
    failed = health.counts.get("failed", 0)
    in_progress = total - enriched - failed - health.counts.get("expired", 0)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total Keywords", total)
    k2.metric("In Progress", in_progress, help="Keywords in active stages: raw + news_sampled. Not yet enriched, expired, or failed.")
    k3.metric("Enriched", enriched, help="Ready for Team 4 — passed LLM justification and enrichment.")
    k4.metric("Failed", failed, help="Auto-retry after 30 min cooldown. Check service logs if failures persist.")
    k5.metric("Expired", health.counts.get("expired", 0), help="No longer trending — archived automatically after 24h inactivity.")

    st.divider()

    # ── Throughput + Stuck row ─────────────────────────────────────────────────
    col_thru, col_stuck = st.columns([1, 1])

    with col_thru:
        st.subheader("Throughput (24h)")
        if stuck:
            tp = stuck.throughput
            t1, t2 = st.columns(2)
            t1.metric("KW/min (last run)", f"{tp.keywords_per_minute:.1f}")
            t2.metric("Avg cycle", f"{tp.avg_cycle_duration_seconds:.0f}s")
            t3, t4 = st.columns(2)
            t3.metric("Runs 24h", tp.total_runs_24h)
            t4.metric("KW inserted 24h", tp.total_keywords_24h)
        else:
            st.info("No throughput data available yet.")

    with col_stuck:
        st.subheader("Stuck Keywords")
        if stuck and stuck.stuck_keywords:
            for alert in stuck.stuck_keywords:
                color = ALERT_COLORS.get(alert.level, "#94a3b8")
                st.markdown(
                    f'<div class="alert-{alert.level}">'
                    f'<strong style="color:{color};">{alert.level.upper()}</strong> '
                    f' — {alert.message}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.success("No stuck keywords detected. Pipeline is healthy!")

    st.divider()

    # ── Last scrape run ────────────────────────────────────────────────────────
    st.subheader("Last Scrape Run")
    if health.last_scrape and health.last_scrape.scrape_run_id:
        run = health.last_scrape
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Run ID", run.scrape_run_id)
        r2.metric("Source", run.source or "—")
        r3.metric("Status", run.status or "—")
        r4.metric("KW Inserted", run.keywords_inserted)

        started = format_wib(run.started_at)
        finished = format_wib(run.finished_at)
        st.caption(f"Started: {started} | Finished: {finished}")
    else:
        st.info("No scrape run recorded yet. Trigger a scrape to get started.")

    # ── Trigger scrape ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Trigger Scrape")
    with st.container():
        t1, t2 = st.columns([1, 2])
        with t1:
            source = st.selectbox(
                "Source",
                ["all", "trends24", "google_trends"],
                label_visibility="collapsed",
            )
        with t2:
            if st.button("Run Scrapers", type="primary", use_container_width=True):
                with st.spinner("Triggering..."):
                    result = trigger_scrape(source)
                if result.get("ok"):
                    st.success(f"Scrape triggered! Run ID: {result['data'].get('scrape_run_id')}")
                else:
                    st.error(f"Failed: {result.get('error', 'Unknown error')}")

    st.divider()

    # ── Status distribution bar chart ─────────────────────────────────────────
    st.subheader("Status Distribution")
    if health.counts:
        df = pd.DataFrame(
            list(health.counts.items()), columns=["Status", "Count"]
        ).sort_values("Count", ascending=False)
        st.bar_chart(df.set_index("Status"), color=["#6c8ef5"])
    else:
        st.info("No data to display.")
