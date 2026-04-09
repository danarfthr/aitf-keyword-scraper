"""
Page 3: Fresh Keywords
- Table of all FRESH keywords
- Checkbox selection + "Send to Expander" button
- Visual flag for top 5 (high trend candidates)
"""
import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.title("Fresh Keywords")

try:
    keywords = requests.get(f"{API_BASE}/keywords/fresh", timeout=10).json()
except Exception as e:
    st.error(f"Failed to load fresh keywords: {e}")
    keywords = []

if keywords:
    st.metric("Fresh keywords", len(keywords))

    st.subheader("Top 5 High-Trend Candidates")
    top5 = keywords[:5]
    for kw in top5:
        st.markdown(f"**{kw['keyword']}** (rank #{kw['rank']}, source: {kw['source']})")

    st.subheader("Select keywords to expand")
    selected = []
    for kw in keywords:
        if st.checkbox(f"{kw['keyword']}", key=f"fresh_kw_{kw['id']}"):
            selected.append(kw["id"])

    st.write(f"**Selected for expansion:** {len(selected)}")

    if st.button("Send to Expander") and selected:
        st.session_state["expand_ids"] = selected
        st.success("Keywords sent! Go to the Expand page.")
        st.switch_page("pages/4_Expand.py")
else:
    st.info("No fresh keywords yet. Classify some keywords first.")
