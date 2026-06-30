"""
Qt-free semantic color tokens shared by desktop and cloud mobile web.
"""

from __future__ import annotations

VALID_THEMES = frozenset({"dark", "light"})
DEFAULT_THEME = "dark"

LIGHT_APP_BG = "#B9E9E9"
LIGHT_PANEL_BG = "#D2F2F2"
LIGHT_CARD_BG = "#E5F8F8"
LIGHT_INPUT_BG = "#FFFFFF"
LIGHT_SURFACE_ALT = "#C0E8E8"
LIGHT_TABLE_BG = "#E8FAFA"
LIGHT_TABLE_HEADER_BG = "#C8EDED"
LIGHT_BORDER = "#7FB8B8"
LIGHT_INPUT_TEXT = "#1B3333"
LIGHT_LABEL_TEXT = "#2D4A4A"
LIGHT_HEADING_TEXT = "#0B7070"
LIGHT_ACCENT_LABEL = "#D97706"
LIGHT_MUTED_TEXT = "#4F6666"
LIGHT_FOCUS_BORDER = "#0E7490"
LIGHT_BUTTON_PRIMARY = "#0E7490"
LIGHT_NAV_HEADER_HOVER = "#C0E8E8"
LIGHT_NAV_ITEM_HOVER = "#D2F2F2"
LIGHT_SCROLLBAR_TRACK = "#C0E8E8"

COLOR_TOKENS: dict[str, dict[str, str]] = {
    "dark": {
        "app_bg": "#121212",
        "panel_bg": "#1E1E1E",
        "card_bg": "#1E1E1E",
        "input_bg": "#2D2D2D",
        "input_text": "#ffffff",
        "label_text": "#ffffff",
        "heading_text": "#60a5fa",
        "border": "#404040",
        "focus_border": "#2196F3",
        "table_bg": "#1E1E1E",
        "table_header_bg": "#2D2D2D",
        "table_text": "#ffffff",
        "button_primary": "#2196F3",
        "button_success": "#10b981",
        "button_danger": "#ef4444",
        "button_warning": "#f59e0b",
        "accent": "#2196F3",
        "scrollbar_track": "#141c2b",
        "scrollbar_handle": "#4a6fa5",
        "scrollbar_handle_hover": "#60a5fa",
        "scrollbar_handle_pressed": "#3b82f6",
        "nav_header_bg": "#111827",
        "nav_header_text": "#ffffff",
        "nav_header_hover": "#1e3a5f",
        "nav_header_active": "#1d4ed8",
        "nav_item_bg": "#0f172a",
        "nav_item_text": "#d1d5db",
        "nav_item_hover_bg": "#1f2937",
        "nav_item_hover_text": "#ffffff",
        "nav_item_active_bg": "#243041",
        "nav_accent": "#60a5fa",
        "nav_divider_bg": "#111827",
        "nav_divider_text": "#93c5fd",
        "accent_label": "#fbbf24",
        "accent_highlight": "#10b981",
        "muted_text": "#94a3b8",
        "surface_alt": "#2D2D2D",
        "logo_stage_bg": "#F0F4FA",
        "logo_stage_border": "#60a5fa",
    },
    "light": {
        "app_bg": LIGHT_APP_BG,
        "panel_bg": LIGHT_PANEL_BG,
        "card_bg": LIGHT_CARD_BG,
        "input_bg": LIGHT_INPUT_BG,
        "surface_alt": LIGHT_SURFACE_ALT,
        "input_text": LIGHT_INPUT_TEXT,
        "label_text": LIGHT_LABEL_TEXT,
        "heading_text": LIGHT_HEADING_TEXT,
        "border": LIGHT_BORDER,
        "focus_border": LIGHT_FOCUS_BORDER,
        "table_bg": LIGHT_TABLE_BG,
        "table_header_bg": LIGHT_TABLE_HEADER_BG,
        "table_text": LIGHT_INPUT_TEXT,
        "button_primary": LIGHT_BUTTON_PRIMARY,
        "button_success": "#2E7D32",
        "button_danger": "#C62828",
        "button_warning": "#E65100",
        "accent": LIGHT_FOCUS_BORDER,
        "scrollbar_track": LIGHT_SCROLLBAR_TRACK,
        "scrollbar_handle": "#6FA3A3",
        "scrollbar_handle_hover": LIGHT_FOCUS_BORDER,
        "scrollbar_handle_pressed": "#0B5F6B",
        "nav_header_bg": LIGHT_CARD_BG,
        "nav_header_text": LIGHT_INPUT_TEXT,
        "nav_header_hover": "#9ECACA",
        "nav_header_active": LIGHT_BUTTON_PRIMARY,
        "nav_item_bg": LIGHT_CARD_BG,
        "nav_item_text": LIGHT_LABEL_TEXT,
        "nav_item_hover_bg": LIGHT_NAV_ITEM_HOVER,
        "nav_item_hover_text": LIGHT_INPUT_TEXT,
        "nav_item_active_bg": LIGHT_BUTTON_PRIMARY,
        "nav_accent": LIGHT_FOCUS_BORDER,
        "nav_divider_bg": LIGHT_SURFACE_ALT,
        "nav_divider_text": LIGHT_HEADING_TEXT,
        "accent_label": LIGHT_ACCENT_LABEL,
        "accent_highlight": "#2E7D32",
        "muted_text": LIGHT_MUTED_TEXT,
        "logo_stage_bg": "#F0F4FA",
        "logo_stage_border": "#0E7490",
    },
}


def get_theme_colors(theme_name: str | None = None) -> dict[str, str]:
    """Return semantic color tokens for one theme."""
    normalized = str(theme_name or DEFAULT_THEME).strip().lower()
    return dict(COLOR_TOKENS.get(normalized, COLOR_TOKENS[DEFAULT_THEME]))


def build_theme_payload(theme_name: str | None = None, currency_symbol: str = "₹") -> dict[str, str | dict[str, str]]:
    """Build the mobile theme API payload without Qt or SQLite."""
    resolved = str(theme_name or DEFAULT_THEME).strip().lower()
    if resolved not in VALID_THEMES:
        resolved = DEFAULT_THEME
    return {
        "theme": resolved,
        "colors": get_theme_colors(resolved),
        "currency_symbol": currency_symbol,
    }
