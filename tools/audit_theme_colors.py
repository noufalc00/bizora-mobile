"""
Audit UI modules for hardcoded color literals and missing refresh_theme hooks.

Run: python tools/audit_theme_colors.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "ui", ROOT / "components")
SKIP_PARTS = {"archive_unused_files", "tools", "__pycache__"}

# Common dark-theme literals that usually mismatch in light mode.
SUSPECT_HEX = re.compile(
    r"#(?:"
    r"0[fF]172[aA]|111827|1[fF]2937|334155|374151|"
    r"60[aA]5[fF][aA]|3[bB]82[fF]6|2563[eE][bB]|"
    r"[fF]3[fF]4[fF]6|[fF]bbf24|9[cC][aA]3[aA][fF]|"
    r"[eE]0[eE]0[eE]0|2[dD]2[dD]2[dD]|"
    r"0[fF]1722|243041"
    r")\b"
)

SET_STYLE_RE = re.compile(r"setStyleSheet\s*\(")
REFRESH_THEME_RE = re.compile(r"def\s+refresh_theme\s*\(")
LEGACY_DIALOG_PATTERNS = (
    "_login_dialog_stylesheet",
    "background-color: #000000",
    "color: #FFD700",
)
DIRECT_MSG_BOX_STYLE_RE = re.compile(
    r"(?:message_box|msg_box)\.setStyleSheet\s*\(",
    re.IGNORECASE,
)


def iter_py_files(base: Path):
    for path in base.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        yield path


def audit_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = path.relative_to(ROOT).as_posix()
    hardcoded = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "setStyleSheet" in line or 'setStyleSheet("""' in text:
            if SUSPECT_HEX.search(line) and not line.strip().startswith("#"):
                hardcoded.append((line_no, line.strip()[:120]))
    dialog_issues = []
    if DIRECT_MSG_BOX_STYLE_RE.search(text) and "message_boxes" not in text:
        if "message_box_style_for_icon" not in text and "apply_message_box_theme" not in text:
            dialog_issues.append("direct QMessageBox.setStyleSheet (use ui.message_boxes)")
    for pattern in LEGACY_DIALOG_PATTERNS:
        if pattern in text:
            dialog_issues.append(f"legacy dialog styling: {pattern}")
    return {
        "path": rel,
        "hardcoded": hardcoded,
        "dialog_issues": dialog_issues,
        "has_refresh_theme": bool(REFRESH_THEME_RE.search(text)),
        "is_widget_module": "QWidget" in text or "QDialog" in text or "QMessageBox" in text,
    }


def main() -> int:
    results = [audit_file(path) for base in SCAN_DIRS for path in iter_py_files(base)]
    hardcoded_files = [r for r in results if r["hardcoded"]]
    dialog_issue_files = [r for r in results if r.get("dialog_issues")]
    widget_modules = [r for r in results if r["is_widget_module"]]
    missing_refresh = [
        r for r in widget_modules
        if not r["has_refresh_theme"]
        and not r["path"].endswith(("theme.py", "checkbox_style.py", "scrollbar_style.py"))
        and "delegate" not in r["path"]
        and "popup" not in r["path"]
        and "_ui.py" not in r["path"]
    ]

    print("=== Theme Color Audit ===\n")
    print(f"Files scanned: {len(results)}")
    print(f"Files with suspect hardcoded colors in setStyleSheet lines: {len(hardcoded_files)}")
    print(f"Files with legacy/themed-dialog issues: {len(dialog_issue_files)}")
    print(f"Widget-like modules missing refresh_theme(): {len(missing_refresh)}\n")

    if hardcoded_files:
        print("-- Suspect hardcoded colors (review manually) --")
        for entry in sorted(hardcoded_files, key=lambda x: x["path"]):
            print(f"\n{entry['path']} ({len(entry['hardcoded'])} hits)")
            for line_no, snippet in entry["hardcoded"][:8]:
                print(f"  L{line_no}: {snippet}")
            if len(entry["hardcoded"]) > 8:
                print(f"  ... +{len(entry['hardcoded']) - 8} more")
    else:
        print("No suspect hardcoded colors found.")

    if dialog_issue_files:
        print("\n-- Dialog/message-box issues --")
        for entry in sorted(dialog_issue_files, key=lambda x: x["path"]):
            print(f"\n{entry['path']}")
            for issue in entry["dialog_issues"]:
                print(f"  - {issue}")
    else:
        print("\nNo legacy dialog/message-box styling issues found.")

    print("\n-- Widget modules without refresh_theme (may still inherit shell QSS) --")
    for entry in sorted(missing_refresh, key=lambda x: x["path"])[:40]:
        print(f"  {entry['path']}")
    if len(missing_refresh) > 40:
        print(f"  ... +{len(missing_refresh) - 40} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
