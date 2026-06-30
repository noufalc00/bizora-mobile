"""One-shot patcher for centralized dd/MM/yyyy display format."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"

IMPORT_LINE = (
    "from ui.date_formats import configure_qdate_edit, format_display_date, "
    "qdate_to_db, qdate_to_display\n"
)

SKIP = {"date_formats.py"}


def add_import(text: str) -> str:
    if "from ui.date_formats import" in text:
        return text
    for anchor in (
        "from ui.ui_memory import",
        "from ui.book_report_common import",
        "from bizora_core.book_report_common import",
    ):
        if anchor in text:
            return text.replace(anchor, IMPORT_LINE + anchor, 1)
    lines = text.splitlines(True)
    for index, line in enumerate(lines):
        if line.startswith("from PySide6.QtWidgets import"):
            lines.insert(index + 1, IMPORT_LINE)
            return "".join(lines)
    return text


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    if "dd-MM-yyyy" not in text and "yyyy-MM-dd" not in text:
        return False

    text = add_import(text)
    text = text.replace(".setDisplayFormat('dd-MM-yyyy')", "")
    text = text.replace('.setDisplayFormat("dd-MM-yyyy")', "")
    text = text.replace(".setDisplayFormat('yyyy-MM-dd')", "")
    text = text.replace('.setDisplayFormat("yyyy-MM-dd")', "")
    text = re.sub(
        r"([\w\.]+)\.date\(\)\.toString\('dd-MM-yyyy'\)",
        r"qdate_to_display(\1.date())",
        text,
    )
    text = re.sub(
        r"([\w\.]+)\.date\(\)\.toString\('yyyy-MM-dd'\)",
        r"qdate_to_db(\1.date())",
        text,
    )
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    patched = []
    for path in sorted(UI.glob("*.py")):
        if path.name in SKIP:
            continue
        if patch_file(path):
            patched.append(path.name)
    print(f"Patched {len(patched)} file(s):")
    for name in patched:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
