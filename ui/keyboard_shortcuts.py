"""
Central keyboard shortcut definitions for module navigation and global actions.
"""

from __future__ import annotations

from typing import Dict, Optional

# Sidebar route name -> shortcut sequence
MODULE_ROUTE_SHORTCUTS: Dict[str, str] = {
    "Sales": "Ctrl+L",
    "Sales Return": "Ctrl+R",
    "Purchase": "Ctrl+B",
    "Purchase Return": "Ctrl+U",
    "Quotation": "Ctrl+Q",
    "Purchase Order": "Ctrl+K",
    "Cash Payment": "Ctrl+M",
    "Cash Receipt": "Ctrl+T",
    "Bank Payment": "Ctrl+Y",
    "Bank Receipt": "Ctrl+I",
    "Journal Entry": "Ctrl+J",
    "Post Dated Cheque": "Ctrl+D",
    "Credit/Debit Note": "Ctrl+H",
    "Van Entry": "Ctrl+W",
    "Van Return Entry": "Ctrl+E",
    "Ledger": "F5",
    "Day Book": "F6",
    "Cash Book": "F7",
    "Price List": "F8",
    "Stock Report": "F9",
}

GLOBAL_ACTION_SHORTCUTS: Dict[str, str] = {
    "save": "Ctrl+S",
    "print": "Ctrl+P",
    "search": "Ctrl+F",
    "new_record": "Ctrl+N",
}


def shortcut_for_route(route_name: str) -> Optional[str]:
    """Return the shortcut sequence for a sidebar route, if configured."""
    return MODULE_ROUTE_SHORTCUTS.get(route_name)


def format_route_button_text(display_name: str, route_name: str | None = None) -> str:
    """Return sidebar button text with an optional shortcut suffix."""
    key = route_name if route_name is not None else display_name
    shortcut = shortcut_for_route(key)
    if not shortcut:
        return display_name
    return f"{display_name} ({shortcut})"