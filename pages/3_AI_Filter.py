"""
Page 3: AI Filter (Optional)
Optionally refine FRESH keywords using AI classification.
Non-relevant keywords are marked REJECTED.
This step is optional — keywords are already FRESH after Rule Filter.
"""
import streamlit as st
import requests
import pandas as pd
from services.openrouter import DEFAULT_MODEL, QUALITY_MODEL

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="AI Filter", page_icon="🤖", layout="wide")
st.title("🤖 AI Filter")
st.caption("Optional — refine fresh keywords using AI to remove non-governance topics")

st.info("💡 This step is **optional**. Keywords are already marked FRESH after Rule Filter. "
        "Use this to further refine by removing false positives via AI classification.")

# --- Load Keywords ---
try:
    keywords = requests.get(f"{API_BASE}/keywords/fresh", timeout=10).json()
except requests.exceptions.ConnectionError:
    st.error("❌ Cannot connect to API server.")
    keywords = []
except Exception as e:
    st.error(f"Failed to load keywords: {e}")
    keywords = []

if not keywords:
    st.info("No fresh keywords available. Run the **Rule Filter** step first, or add keywords manually on the **Fresh Keywords** page.")
    st.stop()

# --- Model Selection ---
st.subheader("⚙️ Settings")
model = st.selectbox(
    "AI Model",
    [DEFAULT_MODEL, QUALITY_MODEL],
    format_func=lambda x: x.split("/")[-1],
    help="Select the AI model for classification",
)

st.divider()

# --- Keywords Selection ---
st.subheader(f"📋 Fresh Keywords ({len(keywords)} available)")

# Select All toggle
select_all = st.toggle("Select All", value=True, key="ai_select_all")

# Build dataframe
df = pd.DataFrame(keywords)
df["selected"] = select_all

edited_df = st.data_editor(
    df[["selected", "keyword", "source", "rank"]],
    column_config={
        "selected": st.column_config.CheckboxColumn("Select", default=select_all),
        "keyword": st.column_config.TextColumn("Keyword", disabled=True),
        "source": st.column_config.TextColumn("Source", disabled=True),
        "rank": st.column_config.NumberColumn("Rank", disabled=True),
    },
    hide_index=True,
    use_container_width=True,
    height=400,
    key="ai_keyword_editor",
)

# Get selected IDs
selected_mask = edited_df["selected"].tolist()
selected_ids = [keywords[i]["id"] for i, sel in enumerate(selected_mask) if sel]

st.info(f"**{len(selected_ids)}** of {len(keywords)} keywords selected")

st.divider()

# --- Classify ---
if st.button("▶️ Classify Selected Keywords", type="primary", use_container_width=True):
    if not selected_ids:
        st.warning("No keywords selected. Toggle 'Select All' or check individual keywords.")
    else:
        with st.spinner(f"Classifying {len(selected_ids)} keywords via {model.split('/')[-1]}…"):
            try:
                response = requests.post(
                    f"{API_BASE}/keywords/classify",
                    json={"keyword_ids": selected_ids, "model": model},
                    timeout=300,
                )
                response.raise_for_status()
                result = response.json()
                st.success(
                    f"✅ Classification complete! "
                    f"**{result['fresh']}** kept FRESH, "
                    f"**{result['rejected']}** marked REJECTED"
                )
                st.rerun()
            except requests.exceptions.ConnectionError:
                st.error("❌ Cannot connect to API server.")
            except requests.exceptions.HTTPError as e:
                try:
                    detail = e.response.json().get("detail", str(e))
                except Exception:
                    detail = str(e)
                st.error(f"❌ Classification failed: {detail}")
            except Exception as e:
                st.error(f"❌ Classification failed: {e}")
