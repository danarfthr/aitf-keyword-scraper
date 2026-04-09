"""
Page 5: Expand Keywords
Expand selected keywords into search query variants via OpenRouter.
"""
import streamlit as st
import requests
import pandas as pd
from services.openrouter import DEFAULT_MODEL, QUALITY_MODEL

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Expand Keywords", page_icon="🔀", layout="wide")
st.title("🔀 Expand Keywords")
st.caption("Generate search query variants for selected keywords via AI")

# --- Load Fresh Keywords ---
try:
    fresh_keywords = requests.get(f"{API_BASE}/keywords/fresh", timeout=10).json()
except requests.exceptions.ConnectionError:
    st.error("❌ Cannot connect to API server.")
    fresh_keywords = []
except Exception as e:
    st.error(f"Failed to load: {e}")
    fresh_keywords = []

# Get selected IDs from session or default to top 5
expand_ids = st.session_state.get("expand_ids", [kw["id"] for kw in fresh_keywords[:5]])
selected = [kw for kw in fresh_keywords if kw["id"] in expand_ids]

if not selected:
    st.info("No keywords selected for expansion. Go to **Fresh Keywords** page to select some.")
    st.stop()

# --- Selected Keywords ---
st.subheader(f"📋 Keywords to Expand ({len(selected)})")

for kw in selected:
    trigger = "🔥 high_trend" if kw["rank"] <= 5 and kw["source"] != "MANUAL" else "✋ manual"
    st.markdown(f"- **{kw['keyword']}** (#{kw['rank']}, {kw['source']}) — trigger: `{trigger}`")

st.divider()

# --- Model Selection ---
model = st.selectbox(
    "AI Model",
    [DEFAULT_MODEL, QUALITY_MODEL],
    format_func=lambda x: x.split("/")[-1],
    help="Select the AI model for expansion",
)

# --- Expand ---
if st.button("▶️ Expand Selected Keywords", type="primary", use_container_width=True):
    with st.spinner(f"Expanding {len(selected)} keywords via {model.split('/')[-1]}…"):
        try:
            response = requests.post(
                f"{API_BASE}/keywords/expand/batch",
                json={"keyword_ids": expand_ids, "model": model},
                timeout=300,
            )
            response.raise_for_status()
            result = response.json()
            st.success(
                f"✅ Expanded **{result['expanded']}** keywords "
                f"into **{result['variants_created']}** variants"
            )
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to API server.")
        except requests.exceptions.HTTPError as e:
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            st.error(f"❌ Expansion failed: {detail}")
        except Exception as e:
            st.error(f"❌ Expansion failed: {e}")

# --- Show Expanded Keywords ---
st.divider()
st.subheader("📊 Expanded Keywords")

try:
    expanded = requests.get(f"{API_BASE}/keywords?status=expanded", timeout=10).json()
    if expanded:
        df = pd.DataFrame(expanded)
        st.metric("Total Expanded", len(df))
        st.dataframe(
            df[["keyword", "source", "rank", "expand_trigger", "parent_id"]],
            use_container_width=True,
            height=400,
        )
    else:
        st.info("No expanded keywords yet.")
except Exception:
    pass
