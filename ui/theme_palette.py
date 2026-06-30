"""Named color palette for legacy pages that still use BG/PANEL/YELLOW constants."""

from __future__ import annotations


def palette() -> dict[str, str]:
    """Return theme-aware aliases used by van entry and similar legacy modules."""
    from ui import theme

    c = theme._theme_colors()
    return {
        "BG": c["app_bg"],
        "PANEL": c["panel_bg"],
        "PANEL_2": c.get("surface_alt", c["panel_bg"]),
        "INPUT": c["input_bg"],
        "BORDER": c["border"],
        "HEADER": c["table_header_bg"],
        "BLUE": c["button_primary"],
        "YELLOW": c["accent_label"],
        "TEXT": c["input_text"],
        "MUTED": c["muted_text"],
        "GREEN": c["button_success"],
        "RED": c["button_danger"],
        "LABEL": c["accent_label"],
        "ACCENT": c["accent_label"],
        "FOCUS": c["focus_border"],
    }