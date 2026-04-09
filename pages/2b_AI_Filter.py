"""
Page 2b: AI Filter
- Select multiple keywords via checkbox
- Dropdown: model selection
- Button: "Classify via OpenRouter"
- Progress indicator during API call
- Results: relevant → FRESH, not relevant → deleted
"""
import streamlit as st
import requests
from services.openrouter import DEFAULT_MODEL, QUALITY_MODEL

API_BASE = "http://localhost:8000"

st.title("AI Filter (OpenRouter)")

model = st.selectbox("Model", [DEFAULT_MODEL, QUALITY_MODEL], format_func=lambda x: x.split("/")[1])

try:
    keywords = requests.get(f"{API_BASE}/keywords?status=filtered", timeout=10).json()
    if not keywords:
        keywords = requests.get(f"{API_BASE}/keywords?status=raw", timeout=10).json()
except Exception as e:
    st.error(f"Failed to load keywords: {e}")
    keywords = []

if keywords:
    st.subheader(f"Select keywords to classify ({len(keywords)} available)")
    selected = []
    cols = st.columns(3)
    for i, kw in enumerate(keywords[:50]):
        with cols[i % 3]:
            if st.checkbox(f"{kw['keyword']}", key=f"ai_kw_{kw['id']}"):
                selected.append(kw["id"])

    st.write(f"**Selected:** {len(selected)} keywords")

    if st.button("Classify via OpenRouter") and selected:
        with st.spinner("Classifying..."):
            try:
                response = requests.post(
                    f"{API_BASE}/keywords/classify",
                    json={"keyword_ids": selected, "model": model},
                    timeout=120,
                )
                response.raise_for_status()
                result = response.json()
                st.success(f"Done! {result['fresh']} marked FRESH, {result['deleted']} removed")
            except Exception as e:
                st.error(f"Classification failed: {e}")
else:
    st.info("No keywords available. Run scrape and apply rule filter first.")
