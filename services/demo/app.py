"""Streamlit demo dashboard — read-only, calls FastAPI only."""

import os
import time
from loguru import logger

import streamlit as st

API = os.environ.get("API_BASE_URL", "http://localhost:8000")


def get(path: str, params: dict = None) -> dict:
    """GET from FastAPI. Returns empty dict on failure."""
    import httpx
    try:
        r = httpx.get(f"{API}{path}", params=params, timeout=10.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return {}


st.set_page_config(
    page_title="AITF Keyword Manager",
    layout="wide",
)

st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to",
    [
        "Pipeline Overview",
        "Trending Keywords",
        "Relevance Results",
        "Enriched Keywords",
        "Failed Keywords",
    ],
)

st.sidebar.markdown("---")
st.sidebar.caption("AITF Tim 1 — Keyword Manager v2")

if page == "Pipeline Overview":
    st.title("Pipeline Overview")

    health = get("/pipeline/health")
    if not health:
        st.error("Could not fetch pipeline health. Is the API running?")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Keyword Counts by Status")
            counts = health.get("counts", {})
            st.bar_chart(counts)

        with col2:
            st.subheader("Counts")
            for status, count in counts.items():
                st.metric(label=status.replace("_", " ").title(), value=count)

        st.subheader("Last Scrape Run")
        last = health.get("last_scrape")
        if last:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Run ID", last.get("scrape_run_id"))
            c2.metric("Source", last.get("source"))
            c3.metric("Status", last.get("status"))
            c4.metric("Keywords Inserted", last.get("keywords_inserted"))
            st.caption(
                f"Started: {last.get('started_at', 'N/A')} | "
                f"Finished: {last.get('finished_at', 'N/A')}"
            )
        else:
            st.info("No scrape run has been executed yet.")

    st.info("Auto-refreshes every 30 seconds.")
    time.sleep(30)
    st.rerun()


elif page == "Trending Keywords":
    st.title("Trending Keywords")

    source_filter = st.selectbox("Filter by source", ["All", "trends24", "google_trends"])

    raw = get("/keywords/status/raw", {"limit": 200})
    sampled = get("/keywords/status/news_sampled", {"limit": 200})

    items = []
    if raw:
        items.extend(raw.get("items", []))
    if sampled:
        items.extend(sampled.get("items", []))

    if source_filter != "All":
        items = [kw for kw in items if kw.get("source") == source_filter.lower()]

    if items:
        import pandas as pd
        df = pd.DataFrame(items)
        st.dataframe(
            df[["keyword", "source", "rank", "scraped_at", "status"]],
            use_container_width=True,
        )
        st.caption(f"Total: {len(items)} keywords")
    else:
        st.info("No trending keywords found. Trigger a scrape cycle first.")


elif page == "Relevance Results":
    st.title("Relevance Results")

    justified = get("/keywords/status/llm_justified", {"limit": 200})
    items = justified.get("items", []) if justified else []

    if items:
        import pandas as pd

        def color_relevant(val):
            return "background-color: #90EE90" if val else "background-color: #FFB6C1"

        df = pd.DataFrame(items)
        # We don't have is_relevant in the list response — show status-based
        st.dataframe(
            df[["keyword", "source", "rank", "scraped_at"]],
            use_container_width=True,
        )
        st.caption(
            "Green rows = is_relevant=true. "
            "Click a keyword for full details including justification."
        )
    else:
        st.info("No justified keywords found yet.")


elif page == "Enriched Keywords":
    st.title("Enriched Keywords")

    enriched = get("/keywords/enriched", {"limit": 200})
    items = enriched.get("items", []) if enriched else []

    if items:
        import pandas as pd

        df = pd.DataFrame(items)
        display = df.copy()
        display["expanded_keywords"] = display["expanded_keywords"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else ""
        )
        st.dataframe(
            display[["keyword", "source", "rank", "expanded_keywords", "scraped_at"]],
            use_container_width=True,
        )
        st.caption(f"Total enriched: {len(items)}")
    else:
        st.info("No enriched keywords found yet. LLM processing may still be running.")


elif page == "Failed Keywords":
    st.title("Failed Keywords")

    failed = get("/keywords/status/failed", {"limit": 200})
    items = failed.get("items", []) if failed else []

    if items:
        import pandas as pd

        df = pd.DataFrame(items)
        st.dataframe(
            df[["keyword", "source", "rank", "updated_at"]],
            use_container_width=True,
        )
        st.caption(f"Total failed: {len(items)}. Auto-retry after 30 minutes.")
    else:
        st.success("No failed keywords. All processing successful so far.")
