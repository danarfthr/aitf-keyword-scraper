"""Metric card component."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

import streamlit as st

from dashboard_pages._theme import inject_theme, COLORS


def render_metric_card(
    label: str,
    value: str | int | float,
    delta: str | None = None,
    help_text: str | None = None,
    color: str | None = None,
) -> None:
    """Render a styled metric card using st.metric."""
    inject_theme()
    st.metric(label=label, value=value, delta=delta, help=help_text)
