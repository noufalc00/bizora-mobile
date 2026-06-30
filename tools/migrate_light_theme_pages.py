"""One-off helper: patch legacy hardcoded dark page backgrounds to theme helpers."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ui"

IMPORT_SNIPPET = """from ui.book_report_common import (
    page_background_style,
    report_compound_entry_page_style,
    report_filter_frame_style,
    report_page_shell_style,
)
"""

SIMPLE_BG = 'self.setStyleSheet("background-color: #111827; color: #f3f4f6;")'
SIMPLE_BG_REPL = "self.setStyleSheet(page_background_style())"

SHELL_PATTERNS = [
    (
        re.compile(
            r'self\.setStyleSheet\(\s*"""\s*QWidget\s*\{\s*background-color:\s*#111827;\s*color:\s*#f3f4f6;\s*\}\s*"""',
            re.MULTILINE,
        ),
        "self.setStyleSheet(report_page_shell_style())",
    ),
    (
        re.compile(
            r'self\.setStyleSheet\(\s*f?"""\s*QWidget#[\w]+\s*\{\s*background-color:\s*#111827;\s*color:\s*#f3f4f6;\s*\}',
            re.MULTILINE,
        ),
        "self.setStyleSheet(report_page_shell_style(self.objectName()) if hasattr(self, 'objectName') and self.objectName() else report_page_shell_style())",
    ),
]

COMPOUND_START = re.compile(
    r'self\.setStyleSheet\(\s*"""\s*QWidget\s*\{\s*background-color:\s*#111827',
    re.MULTILINE,
)

FILES_SIMPLE = [
    "daily_stock_register_page.py",
    "collection_report.py",
    "profit_loss_page.py",
    "balance_sheet_page.py",
    "opening_balance_page.py",
    "standalone_window.py",
    "bill_history_page.py",
    "credit_debit_note_page.py",
    "stock_checker_page.py",
    "price_list_page.py",
    "journal_entry_page.py",
]

FILES_COMPOUND = [
    "pdc_page.py",
    "gstr1_page.py",
    "gst_purchase_report_page.py",
    "gst_sales_report_page.py",
    "credit_debit_note_page.py",
    "quotation_entry.py",
    "ledger_page.py",
    "ledger_statement_page.py",
    "monthly_analysis_page.py",
]


def _ensure_imports(text: str) -> str:
    if "page_background_style" in text or "report_compound_entry_page_style" in text:
        return text
    if "from ui.book_report_common import" in text:
        if "page_background_style" not in text:
            text = text.replace(
                "from ui.book_report_common import",
                "from ui.book_report_common import page_background_style, report_compound_entry_page_style, report_filter_frame_style, report_page_shell_style,",
                1,
            )
        return text
    # Insert after last import block line
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, "from ui.book_report_common import page_background_style, report_compound_entry_page_style, report_filter_frame_style, report_page_shell_style")
    return "\n".join(lines)


def _replace_compound_block(text: str) -> str:
    """Replace multi-line compound dark stylesheet with report_compound_entry_page_style()."""
    marker = 'self.setStyleSheet("""'
    idx = text.find('QWidget { background-color: #111827')
    if idx == -1:
        return text
    start = text.rfind("self.setStyleSheet", 0, idx)
    if start == -1:
        return text
    end = text.find('""")', idx)
    if end == -1:
        return text
    end += 4
    return text[:start] + "self.setStyleSheet(report_compound_entry_page_style())" + text[end:]


def patch_file(path: Path, mode: str) -> bool:
    original = path.read_text(encoding="utf-8")
    text = original
    if mode == "simple":
        if SIMPLE_BG in text:
            text = text.replace(SIMPLE_BG, SIMPLE_BG_REPL)
        text = text.replace(
            'self.setStyleSheet("background-color: #111827; color: #E0E0E0;")',
            "self.setStyleSheet(page_background_style())",
        )
    elif mode == "compound":
        if "#111827" in text and "report_compound_entry_page_style" not in text:
            text = _replace_compound_block(text)
    if text != original:
        text = _ensure_imports(text)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = []
    for name in FILES_SIMPLE:
        p = ROOT / name
        if p.exists() and patch_file(p, "simple"):
            changed.append(name)
    for name in FILES_COMPOUND:
        p = ROOT / name
        if p.exists() and patch_file(p, "compound"):
            changed.append(name)
    print("Updated:", ", ".join(changed) if changed else "(none)")


if __name__ == "__main__":
    main()
