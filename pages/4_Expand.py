"""
Page 4: Expand
- Shows selected keywords from Fresh page (or auto top-5)
- Button: "Expand Selected"
- Table: original keyword | expanded variants | trigger reason
"""
import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.title("Expand Keywords")

try:
    fresh_keywords = requests.get(f"{API_BASE}/keywords/fresh", timeout=10).json()
except Exception as e:
    st.error(f"Failed to load: {e}")
    fresh_keywords = []

expand_ids = st.session_state.get("expand_ids", [kw["id"] for kw in fresh_keywords[:5]])
st.session_state.expand_ids = expand_ids

selected = [kw for kw in fresh_keywords if kw["id"] in expand_ids]

if selected:
    st.subheader("Keywords to expand")
    for kw in selected:
        trigger = "high_trend" if kw["rank"] <= 5 else "manual"
        st.markdown(f"- **{kw['keyword']}** (#{kw['rank']}, {kw['source']}) — trigger: `{trigger}`")

    model = st.selectbox("Model", ["google/gemma-4-26b-a4b-it:free", "qwen/qwen3.6-plus"])

    if st.button("Expand Selected"):
        with st.spinner("Expanding..."):
            try:
                response = requests.post(
                    f"{API_BASE}/keywords/expand/batch",
                    json={"keyword_ids": expand_ids, "model": model},
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()
                st.success(f"Expanded {result['expanded']} keywords into {result['variants_created']} variants")
            except Exception as e:
                st.error(f"Expansion failed: {e}")
else:
    st.info("No keywords selected. Go to Fresh Keywords page to select some.")
