"""
Page 2a: Rule Filter
- Chip/toggle list of governance signals (default all ON)
- User can add/remove signals per session
- Button: "Apply Filter" → applies to all RAW keywords
"""
import streamlit as st
import requests
from keyword_scraper.filters import governance_signals

API_BASE = "http://localhost:8000"

st.title("Rule Filter")

if "selected_signals" not in st.session_state:
    st.session_state.selected_signals = set(governance_signals)

st.subheader("Governance Signals (toggle off to exclude)")
cols = st.columns(4)
for i, signal in enumerate(sorted(governance_signals)):
    with cols[i % 4]:
        checked = st.checkbox(signal, value=True, key=f"signal_{i}")

active_signals = [s for s in governance_signals if st.session_state.get(f"signal_{governance_signals.index(s)}", True)]
st.write(f"**Active signals:** {len(active_signals)}")

if st.button("Apply Filter to RAW Keywords"):
    with st.spinner("Applying rule filter..."):
        try:
            response = requests.post(f"{API_BASE}/keywords/filter", timeout=30)
            response.raise_for_status()
            result = response.json()
            st.success(f"Filtered {result['total']} RAW keywords — {result['passed']} passed, {result['filtered']} removed")
        except Exception as e:
            st.error(f"Filter failed: {e}")

try:
    raw = requests.get(f"{API_BASE}/keywords?status=raw", timeout=10).json()
    filtered = requests.get(f"{API_BASE}/keywords?status=filtered", timeout=10).json()
    st.metric("RAW keywords", len(raw))
    st.metric("Filtered (passed) keywords", len(filtered))
except Exception:
    pass
