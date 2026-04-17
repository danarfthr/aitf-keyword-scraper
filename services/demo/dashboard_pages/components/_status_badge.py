"""Status badge component."""

import os
import sys as _sys
_d = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _d not in _sys.path:
    _sys.path.insert(0, _d)

from dashboard_pages._theme import STATUS_COLORS, SOURCE_COLORS, inject_theme


def render_status_badge(status: str) -> str:
    """Return HTML string for a status badge pill."""
    inject_theme()
    color = STATUS_COLORS.get(status, "#94a3b8")
    label = status.replace("_", " ").upper()
    return (
        f'<span class="status-pill" '
        f'style="background:{color}22; color:{color}; border:1px solid {color}44;">'
        f'{label}</span>'
    )


def render_source_badge(source: str) -> str:
    """Return HTML string for a source badge."""
    inject_theme()
    color = SOURCE_COLORS.get(source, "#94a3b8")
    label = source.replace("_", " ").upper()
    return (
        f'<span class="source-badge" '
        f'style="background:{color}22; color:{color}; border:1px solid {color}44;">'
        f'{label}</span>'
    )
