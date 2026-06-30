"""
Audit QCompleter and QComboBox popup theming across UI modules.

Flags files that call setCompleter() without applying the shared popup theme,
which causes dark/unstyled dropdown lists in light theme.

Usage (from project root):
    python scripts/audit_completer_theme.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"

THEME_MARKERS = (
    "apply_completer_popup_theme",
    "wire_line_edit_completer",
    "wire_editable_combo_completer",
    "completer_popup_list_style",
    "apply_combo_dropdown_theme",
    "style_filter_combo",
)

EXEMPT_FILES = {
    "purchase_entry_popup.py",
    "sales_entry_popup.py",
    "voucher_common.py",
    "account_creation_page.py",
    "voucher_grid_common.py",
    "global_search_bar.py",
    "products.py",
}


def _audit_file(path: Path) -> list[str]:
    """Return warning messages for one UI source file."""
    text = path.read_text(encoding="utf-8")
    if "setCompleter(" not in text:
        return []

    rel = path.relative_to(ROOT).as_posix()
    if path.name in EXEMPT_FILES:
        return []

    issues: list[str] = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        if "setCompleter(" not in line:
            continue
        if "setCompleter(None)" in line.replace(" ", ""):
            continue
        window = "\n".join(lines[max(0, index - 8): min(len(lines), index + 8)])
        if not any(marker in window for marker in THEME_MARKERS):
            issues.append(f"{rel}:{index}: setCompleter without popup theme helper nearby")
    return issues


def main() -> int:
    """Scan ui/*.py for unthemed completer popups."""
    all_issues: list[str] = []
    for path in sorted(UI_ROOT.rglob("*.py")):
        all_issues.extend(_audit_file(path))

    if not all_issues:
        print("OK  All setCompleter call sites appear themed.")
        return 0

    print(f"FAIL {len(all_issues)} unthemed completer call site(s):")
    for issue in all_issues:
        print(f"  - {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
