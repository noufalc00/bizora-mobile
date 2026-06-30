"""Patch remaining report/book pages that still use hardcoded dark-theme hex colors."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ui"

IMPORT_LINE = (
    "from ui.book_report_common import page_background_style, report_filter_frame_style, "
    "report_detail_dialog_style, report_compound_entry_page_style, report_page_shell_style"
)

SIMPLE_REPLACEMENTS = [
    (
        'self.setStyleSheet("background-color: #111827; color: #f3f4f6;")',
        "self.setStyleSheet(page_background_style())",
    ),
    (
        'self.setStyleSheet("background-color: #111827; color: #E0E0E0;")',
        "self.setStyleSheet(page_background_style())",
    ),
    (
        'setStyleSheet("background-color: #111827; border: 1px solid #374151; border-radius: 6px;")',
        "setStyleSheet(report_filter_frame_style())",
    ),
    (
        '"background-color: #111827; border: 1px solid #374151; border-radius: 6px;"',
        "report_filter_frame_style()",
    ),
    (
        '"QDialog { background-color: #111827; color: #f3f4f6; }"',
        "report_detail_dialog_style()",
    ),
    (
        '"QDialog { background-color: #111827; color: #f3f4f6; } QLabel { color: #f3f4f6; }"',
        "report_detail_dialog_style()",
    ),
    (
        ' + "QDialog { background-color: #111827; color: #f3f4f6; } QLabel { color: #f3f4f6; }"',
        "",
    ),
    (
        'summary_widget.setStyleSheet("background-color: #1e293b; padding: 10px; border-radius: 6px;")',
        "summary_widget.setStyleSheet(report_filter_frame_style())",
    ),
]

FILES = [
    "ledger_page.py",
    "ledger_statement_page.py",
    "monthly_analysis_page.py",
    "journal_entry_page.py",
    "quotation_entry.py",
    "opening_balance_page.py",
    "balance_sheet_page.py",
    "profit_loss_page.py",
    "daily_stock_register_page.py",
    "collection_report.py",
    "gst_sales_report_page.py",
    "gst_purchase_report_page.py",
    "gstr1_page.py",
    "credit_debit_note_page.py",
    "pdc_page.py",
    "trial_balance_page.py",
    "net_sales_book.py",
    "journal_book_page.py",
    "pdc_book_page.py",
    "day_book_page.py",
    "stock_checker_page.py",
    "stock_value_page.py",
    "stock_adjustment_page.py",
    "price_list_page.py",
    "best_sellers_report.py",
    "purchase_order_book.py",
    "bill_history_page.py",
    "standalone_window.py",
    "company_gateway.py",
    "purchase_po_import.py",
    "diagnostic_view.py",
    "report_preview_utils.py",
]


def ensure_imports(text: str) -> str:
    if "page_background_style" in text:
        return text
    if "from ui.book_report_common import" in text:
        return re.sub(
            r"from ui\.book_report_common import[^\n]+",
            IMPORT_LINE,
            text,
            count=1,
        )
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, IMPORT_LINE)
    return "\n".join(lines)


def replace_compound_shell(text: str) -> str:
    pattern = re.compile(
        r'self\.setStyleSheet\(\s*"""\s*QWidget\s*\{\s*background-color:\s*#111827',
        re.MULTILINE,
    )
    if pattern.search(text) and "report_compound_entry_page_style()" not in text:
        idx = text.find("QWidget { background-color: #111827")
        if idx == -1:
            return text
        start = text.rfind("self.setStyleSheet", 0, idx)
        end = text.find('""")', idx)
        if start == -1 or end == -1:
            return text
        end += 4
        return text[:start] + "self.setStyleSheet(report_compound_entry_page_style())" + text[end:]
    return text


def patch_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    text = original
    for old, new in SIMPLE_REPLACEMENTS:
        text = text.replace(old, new)
    text = replace_compound_shell(text)
    if text != original:
        text = ensure_imports(text)
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = []
    for name in FILES:
        path = ROOT / name
        if path.exists() and patch_file(path):
            changed.append(name)
    print("Updated:", ", ".join(changed) if changed else "(none)")


if __name__ == "__main__":
    main()
