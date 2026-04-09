"""
Page 2: Rule Filter
Apply governance signal regex filter to RAW keywords.
Signals are editable via a comma-separated text area.
Non-matching keywords are marked REJECTED (not deleted).
"""
import streamlit as st
import requests
import pandas as pd
from keyword_scraper.filters import GOVERNANCE_SIGNALS

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Rule Filter", page_icon="📏", layout="wide")
st.title("📏 Rule Filter")
st.caption("Apply governance signal matching to filter RAW keywords")

# --- Current Stats ---
try:
    raw = requests.get(f"{API_BASE}/keywords?status=raw", timeout=10).json()
    fresh = requests.get(f"{API_BASE}/keywords/fresh", timeout=10).json()
    rejected = requests.get(f"{API_BASE}/keywords?status=rejected", timeout=10).json()

    col1, col2, col3 = st.columns(3)
    col1.metric("⬜ RAW (pending)", len(raw))
    col2.metric("🌱 Fresh (passed)", len(fresh))
    col3.metric("❌ Rejected", len(rejected))
except requests.exceptions.ConnectionError:
    st.error("❌ Cannot connect to API server.")
    raw = []
except Exception:
    raw = []

st.divider()

# --- Governance Signals Editor ---
st.subheader("🏷️ Governance Signals")
st.caption("Edit the signals below. Separate each signal with a comma. Add new ones or remove existing ones freely.")

default_signals = ", ".join(sorted(GOVERNANCE_SIGNALS))

if "custom_signals" not in st.session_state:
    st.session_state.custom_signals = default_signals

custom_signals = st.text_area(
    "Governance signals (comma-separated)",
    value=st.session_state.custom_signals,
    height=200,
    key="signals_editor",
    help="Each signal is matched as a standalone word using word-boundary regex. Case-insensitive.",
)

# Parse and display count
active_signals = [s.strip() for s in custom_signals.split(",") if s.strip()]
unique_signals = list(dict.fromkeys(active_signals))  # deduplicate preserving order

col1, col2 = st.columns(2)
with col1:
    st.info(f"**{len(unique_signals)}** active signals")
with col2:
    if st.button("↩️ Reset to Defaults", use_container_width=True):
        st.session_state.custom_signals = default_signals
        st.rerun()

st.divider()

# --- Apply Filter ---
if st.button("▶️ Apply Filter to RAW Keywords", type="primary", use_container_width=True):
    if not raw:
        st.warning("No RAW keywords to filter. Run a scrape first.")
    else:
        with st.spinner(f"Applying rule filter with {len(unique_signals)} signals…"):
            try:
                response = requests.post(
                    f"{API_BASE}/keywords/filter",
                    json={"signals": unique_signals},
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()
                st.success(
                    f"✅ Filtered **{result['total']}** RAW keywords — "
                    f"**{result['passed']}** passed, **{result['rejected']}** rejected"
                )
                st.rerun()
            except Exception as e:
                st.error(f"❌ Filter failed: {e}")
