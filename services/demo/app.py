"""Streamlit demo dashboard — read-only, calls FastAPI only.

Radio-button navigation (works on all Streamlit versions).
Auto-refresh via st_autorefresh (non-blocking).
"""

import os
import sys as _sys

# Add services/demo to path so dashboard_pages package imports work
_d = os.path.dirname(os.path.abspath(__file__))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard_pages._theme import inject_theme, COLORS
from dashboard_pages._api import set_api_base

# Configure API base URL
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")
set_api_base(API_BASE)

st.set_page_config(
    page_title="AITF Keyword Manager",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme injection ─────────────────────────────────────────────────────────
inject_theme()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("AITF Keyword Manager")
st.sidebar.caption("Tim 1 — Keyword Manager v2")
st.sidebar.markdown("---")

# Pipeline health dot
try:
    from dashboard_pages._api import get_health
    health = get_health()
    failed = health.counts.get("failed", 0)
    if failed > 10:
        dot_color, health_label = "#f87171", "Degraded"
    elif failed > 0:
        dot_color, health_label = "#fbbf24", "Warning"
    else:
        dot_color, health_label = "#4ade80", "Healthy"
    st.sidebar.markdown(
        f'<p style="font-size:0.75rem; color:{COLORS["text_muted"]};">'
        f'<span style="color:{dot_color}; font-size:1rem;">●</span> '
        f"Pipeline {health_label}</p>",
        unsafe_allow_html=True,
    )
except Exception:
    pass

# Navigation via radio
selected_name = st.sidebar.radio(
    "Navigate",
    [
        "Pipeline Overview",
        "Trending Keywords",
        "Relevance Results",
        "Enriched Keywords",
        "Failed Keywords",
    ],
    index=0,
)

# ── Page rendering ───────────────────────────────────────────────────────────
if selected_name == "Pipeline Overview":
    from dashboard_pages import p01_pipeline_overview as m
    m.render()
elif selected_name == "Trending Keywords":
    from dashboard_pages import p02_trending_keywords as m
    m.render()
elif selected_name == "LLM Decisions":
    from dashboard_pages import p03_llm_decisions as m
    m.render()
elif selected_name == "Enriched Keywords":
    from dashboard_pages import p04_enriched_keywords as m
    m.render()
elif selected_name == "Failed Keywords":
    from dashboard_pages import p05_failed_keywords as m
    m.render()
