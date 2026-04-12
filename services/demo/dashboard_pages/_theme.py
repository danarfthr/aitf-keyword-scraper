"""Theme constants and CSS for the dashboard."""

import streamlit as st

# ── Color palette ─────────────────────────────────────────────────────────────

COLORS = {
    "bg": "#0f1117",
    "surface": "#1a1d27",
    "surface2": "#252836",
    "border": "#2e3142",
    "text": "#e8e9ed",
    "text_muted": "#8b8fa3",
    "accent": "#6c8ef5",
    "accent2": "#a078f5",
    "success": "#4ade80",
    "warning": "#fbbf24",
    "error": "#f87171",
    "info": "#38bdf8",
}

STATUS_COLORS = {
    "raw": "#94a3b8",          # slate
    "news_sampled": "#38bdf8", # sky blue
    "llm_justified": "#a07ef5",# purple
    "enriched": "#4ade80",     # green
    "expired": "#fbbf24",      # amber
    "failed": "#f87171",       # red
}

RELEVANCE_COLORS = {
    True: "#4ade80",   # green — relevant
    False: "#f87171",  # red — not relevant
}

ALERT_COLORS = {
    "critical": "#f87171",
    "warning": "#fbbf24",
    "info": "#38bdf8",
}

SOURCE_COLORS = {
    "trends24": "#6c8ef5",
    "google_trends": "#38bdf8",
}


# ── CSS injection ──────────────────────────────────────────────────────────────

INJECTED = False


def inject_theme():
    global INJECTED
    if INJECTED:
        return
    INJECTED = True

    css = f"""
    <style>
    /* Base */
    :root {{
        --bg: {COLORS["bg"]};
        --surface: {COLORS["surface"]};
        --surface2: {COLORS["surface2"]};
        --border: {COLORS["border"]};
        --text: {COLORS["text"]};
        --text-muted: {COLORS["text_muted"]};
        --accent: {COLORS["accent"]};
        --accent2: {COLORS["accent2"]};
    }}
    [data-testid="stApp"] {{
        background-color: var(--bg);
        color: var(--text);
    }}
    /* Sidebar */
    [data-testid="stSidebar"] {{
        background-color: var(--surface);
        border-right: 1px solid var(--border);
    }}
    /* Cards / containers */
    .metric-card {{
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 12px 16px;
    }}
    /* Status pill */
    .status-pill {{
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }}
    /* Source badge */
    .source-badge {{
        display: inline-block;
        padding: 1px 8px;
        border-radius: 6px;
        font-size: 0.7rem;
        font-weight: 500;
    }}
    /* Alert banner */
    .alert-critical {{ background: rgba(248,113,113,0.15); border-left: 3px solid #f87171; padding: 8px 12px; border-radius: 4px; }}
    .alert-warning  {{ background: rgba(251,191,36,0.15);  border-left: 3px solid #fbbf24; padding: 8px 12px; border-radius: 4px; }}
    .alert-info     {{ background: rgba(56,189,248,0.15);  border-left: 3px solid #38bdf8; padding: 8px 12px; border-radius: 4px; }}
    /* Freshness */
    .freshness {{ font-size: 0.7rem; color: var(--text-muted); }}
    .fresh-green {{ color: #4ade80; }}
    .fresh-yellow {{ color: #fbbf24; }}
    .fresh-red {{ color: #f87171; }}
    /* Keyword chip */
    .kw-chip {{
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 2px 8px;
        font-size: 0.75rem;
        margin: 2px;
        display: inline-block;
    }}
    /* Table rows */
    [data-testid="stDataFrame"] tr:hover {{ background-color: rgba(108,142,245,0.08) !important; }}
    /* Expanders */
    details {{ border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; }}
    summary {{ padding: 8px 12px; cursor: pointer; }}
    /* Divider */
    hr {{ border-color: var(--border); }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
