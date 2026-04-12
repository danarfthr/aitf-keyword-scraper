"""Freshness indicator component."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import time

import streamlit as st

from dashboard_pages._theme import inject_theme


def render_freshness_indicator(fetched_at: float) -> None:
    """Render 'Updated Xs ago' text with color coding."""
    inject_theme()
    age = int(time.time() - fetched_at)
    if age < 30:
        color_class = "fresh-green"
        label = "just now"
    elif age < 60:
        color_class = "fresh-green"
        label = f"{age}s ago"
    elif age < 120:
        color_class = "fresh-yellow"
        label = f"{age}s ago"
    else:
        color_class = "fresh-red"
        label = f"{age}s ago"

    st.markdown(
        f'<span class="freshness {color_class}">Updated {label}</span>',
        unsafe_allow_html=True,
    )
