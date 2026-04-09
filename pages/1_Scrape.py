"""
Page 1: Scrape
- Button: "Run Scrape"
- On click: scrape GTR + T24 → store in DB
- Table: keyword | source | rank | status
- Show scrape result summary
"""
import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.title("Scrape Keywords")

if st.button("Run Scrape"):
    with st.spinner("Scraping Google Trends and Trends24 Indonesia..."):
        try:
            response = requests.post(f"{API_BASE}/scrape", timeout=60)
            response.raise_for_status()
            result = response.json()
            st.success(f"Scrape complete!")
            st.json(result)
        except Exception as e:
            st.error(f"Scrape failed: {e}")

st.header("All Keywords")
try:
    keywords = requests.get(f"{API_BASE}/keywords", timeout=10).json()
    if keywords:
        import pandas as pd
        df = pd.DataFrame(keywords)
        st.dataframe(df[["keyword", "source", "rank", "status"]])
    else:
        st.info("No keywords yet. Click 'Run Scrape' to start.")
except Exception as e:
    st.error(f"Failed to load keywords: {e}")
