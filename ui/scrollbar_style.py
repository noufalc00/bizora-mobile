"""Shared scrollbar styling for the Accounting Desktop application."""

from __future__ import annotations


def scrollbar_stylesheet() -> str:
    """Return application-wide QScrollBar stylesheet."""
    try:
        from ui.theme_manager import get_theme_manager
        colors = get_theme_manager().get_colors()
    except Exception:
        from config import COLORS
        colors = COLORS

    track = colors.get("scrollbar_track", colors.get("app_bg", "#B9E9E9"))
    handle = colors["scrollbar_handle"]
    handle_hover = colors["scrollbar_handle_hover"]
    handle_pressed = colors["scrollbar_handle_pressed"]

    return f"""
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {track};
            border: none;
            margin: 0px;
        }}
        QScrollBar:vertical {{
            width: 10px;
        }}
        QScrollBar:horizontal {{
            height: 10px;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {handle};
            border-radius: 5px;
            min-height: 28px;
            min-width: 28px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: {handle_hover};
        }}
        QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{
            background: {handle_pressed};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0px;
            height: 0px;
            border: none;
            background: none;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
        }}
    """