"""
Keyword Scraper — Streamlit entry point.
Configures page layout and redirects to the Scrape page.
"""
import streamlit as st

st.set_page_config(
    page_title="Keyword Scraper",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Page 1: Scrape Keywords (inline — this is the home page) ---
import requests
import pandas as pd

API_BASE = "http://localhost:8000"

st.title("🔍 Scrape Keywords")
st.caption("Fetch trending keywords from Google Trends and Trends24 Indonesia")

# --- Scrape Action ---
col1, col2 = st.columns([1, 3])
with col1:
    scrape_btn = st.button("▶️ Run Scrape", use_container_width=True, type="primary")

if scrape_btn:
    with st.spinner("Scraping Google Trends and Trends24 Indonesia…"):
        try:
            response = requests.post(f"{API_BASE}/scrape", timeout=300)
            response.raise_for_status()
            result = response.json()
            st.success(
                f"✅ Scrape complete! "
                f"Google Trends: **{result['gtr_count']}** · "
                f"Trends24: **{result['t24_count']}** · "
                f"Total new: **{result['total']}**"
            )
            if result.get("errors"):
                for err in result["errors"]:
                    st.warning(err)
            st.rerun()
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to API server. Make sure FastAPI is running on port 8000.")
        except Exception as e:
            st.error(f"❌ Scrape failed: {e}")

# --- Keywords Table ---
st.divider()
st.subheader("📋 All Keywords")

try:
    keywords = requests.get(f"{API_BASE}/keywords", timeout=10).json()
    if keywords:
        df = pd.DataFrame(keywords)

        # Summary metrics
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        status_counts = df["status"].value_counts()
        col1.metric("Total", len(df))
        col2.metric("Raw", status_counts.get("raw", 0))
        col3.metric("Filtered", status_counts.get("filtered", 0))
        col4.metric("Rejected", status_counts.get("rejected", 0))
        col5.metric("Fresh", status_counts.get("fresh", 0))
        col6.metric("Expanded", status_counts.get("expanded", 0))

        st.dataframe(
            df[["keyword", "source", "rank", "status"]],
            use_container_width=True,
            height=400,
        )
    else:
        st.info("No keywords yet. Click **Run Scrape** to start.")
except requests.exceptions.ConnectionError:
    st.error("❌ Cannot connect to API server. Make sure FastAPI is running on port 8000.")
except Exception as e:
    st.error(f"Failed to load keywords: {e}")
