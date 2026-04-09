"""
Page 4: Fresh Keywords
View all FRESH keywords, add manual keywords, select for expansion.
"""
import streamlit as st
import requests
import pandas as pd

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Fresh Keywords", page_icon="🌱", layout="wide")
st.title("🌱 Fresh Keywords")
st.caption("Keywords that passed AI classification — ready for expansion or scraping")

# --- Manual Keyword Entry ---
with st.expander("➕ Add Manual Keywords", expanded=False):
    st.caption("Enter keywords separated by commas. They will be added directly as FRESH.")
    with st.form("add_manual", clear_on_submit=True):
        manual_input = st.text_area(
            "Keywords (comma-separated)",
            placeholder="keyword 1, keyword 2, keyword 3…",
            height=100,
        )
        submitted = st.form_submit_button("Add Keywords", type="primary")
        if submitted and manual_input.strip():
            kw_list = [k.strip() for k in manual_input.split(",") if k.strip()]
            if not kw_list:
                st.warning("No valid keywords entered.")
            else:
                try:
                    r = requests.post(
                        f"{API_BASE}/keywords",
                        json={"keywords": kw_list},
                        timeout=10,
                    )
                    r.raise_for_status()
                    result = r.json()
                    if result["added"] > 0:
                        st.success(f"✅ Added **{result['added']}** keywords")
                    if result["duplicates"] > 0:
                        st.warning(f"⚠️ {result['duplicates']} duplicates skipped")
                    if result["added"] > 0:
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to add keywords: {e}")

st.divider()

# --- Load Fresh Keywords ---
try:
    keywords = requests.get(f"{API_BASE}/keywords/fresh", timeout=10).json()
except requests.exceptions.ConnectionError:
    st.error("❌ Cannot connect to API server.")
    keywords = []
except Exception as e:
    st.error(f"Failed to load fresh keywords: {e}")
    keywords = []

if not keywords:
    st.info("No fresh keywords yet. Run the **AI Filter** step or add keywords manually above.")
    st.stop()

st.metric("🌱 Fresh Keywords", len(keywords))

# --- Top 5 High-Trend Candidates ---
st.subheader("🔥 Top 5 High-Trend Candidates")
top5 = [kw for kw in keywords if kw.get("source") != "MANUAL"][:5]
if top5:
    cols = st.columns(min(len(top5), 5))
    for i, kw in enumerate(top5):
        with cols[i]:
            st.markdown(f"**{kw['keyword']}**")
            st.caption(f"Rank #{kw['rank']} · {kw['source']}")
else:
    st.caption("No scraped keywords yet — only manual entries.")

st.divider()

# --- Keywords Table with Selection ---
st.subheader("📋 All Fresh Keywords")

select_all = st.toggle("Select All for Expansion", value=True, key="fresh_select_all")

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
    key="fresh_kw_editor",
)

selected_mask = edited_df["selected"].tolist()
selected_ids = [keywords[i]["id"] for i, sel in enumerate(selected_mask) if sel]

st.info(f"**{len(selected_ids)}** of {len(keywords)} keywords selected for expansion")

st.divider()

# --- Send to Expander ---
if st.button("▶️ Send to Expander", type="primary", use_container_width=True):
    if not selected_ids:
        st.warning("No keywords selected.")
    else:
        st.session_state["expand_ids"] = selected_ids
        st.success(f"✅ {len(selected_ids)} keywords sent to Expander!")
        st.switch_page("pages/5_Expand.py")
