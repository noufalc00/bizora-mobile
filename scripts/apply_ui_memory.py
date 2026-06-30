"""
One-shot helper to add UiMemoryMixin wiring across ui/*.py modules.

Run from the project root:
    python scripts/apply_ui_memory.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"

SKIP_FILES = {
    "ui_memory.py",
    "theme.py",
    "theme_manager.py",
    "theme_palette.py",
    "qt_pump.py",
    "keyboard_shortcuts.py",
    "scrollbar_style.py",
    "checkbox_style.py",
    "form_style_standard.py",
    "startup_handoff.py",
    "loading_indicator.py",
    "sales_entry_delegate.py",
    "purchase_entry_delegate.py",
    "sales_return_delegate.py",
    "purchase_return_delegate.py",
    "stock_adjustment_delegate.py",
    "sales_entry_calculations.py",
    "purchase_entry_calculations.py",
    "sales_return_calculations.py",
    "purchase_return_calculations.py",
    "sales_entry_helpers.py",
    "purchase_entry_helpers.py",
    "sales_return_helpers.py",
    "purchase_return_helpers.py",
    "sales_entry_popup.py",
    "purchase_entry_popup.py",
    "purchase_return_popup.py",
    "sales_return_popup.py",
    "party_display.py",
    "report_preview_utils.py",
    "financial_year_guard.py",
    "__init__.py",
}

SKIP_CLASS_SUFFIXES = ("Worker", "Mixin", "Filter", "Delegate", "Canvas")
SKIP_CLASS_NAMES = {
    "MainWindow",
    "StandaloneModuleWindow",
    "BookReportPageWidget",
    "VoucherTopBar",
    "LoadingCurtainWidget",
    "LoadingRunnerWidget",
    "LabelPreviewCanvas",
    "JournalBookWorker",
    "DayBookWorker",
    "CashBookWorker",
    "BookReportWorker",
    "CompanySetupView",
}

WIDGET_BASES = ("QWidget", "QDialog", "QMainWindow")


def _needs_patch(source: str, class_name: str) -> bool:
    if class_name in SKIP_CLASS_NAMES:
        return False
    if any(class_name.endswith(suffix) for suffix in SKIP_CLASS_SUFFIXES):
        return False
    if "UiMemoryMixin" in source and f"class {class_name}" in source:
        return True
    if "QTableWidget" not in source and "QDialog" not in source and "QMainWindow" not in source:
        return False
    class_pattern = re.compile(rf"^class\s+{re.escape(class_name)}\s*\(([^)]*)\)\s*:", re.M)
    match = class_pattern.search(source)
    if not match:
        return False
    bases = match.group(1)
    if not any(base in bases for base in WIDGET_BASES):
        return False
    if "UiMemoryMixin" in bases:
        return False
    if class_name.endswith("PageWidget") and "BookReportPageWidget" in bases:
        return False
    if class_name.endswith("PageWidget") and "VoucherGridPage" in bases:
        return False
    return True


def _insert_import(source: str) -> str:
    if "from ui.ui_memory import UiMemoryMixin" in source:
        return source
    if "from .ui_memory import UiMemoryMixin" in source:
        return source

    lines = source.splitlines(keepends=True)
    insert_at = 0
    for index, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            insert_at = index + 1
    lines.insert(insert_at, "from ui.ui_memory import UiMemoryMixin\n")
    return "".join(lines)


def _patch_class_bases(source: str, class_name: str) -> str:
    pattern = re.compile(
        rf"(^class\s+{re.escape(class_name)}\s*\()([^)]*)(\)\s*:)",
        re.M,
    )

    def replacer(match: re.Match[str]) -> str:
        bases = match.group(2)
        if "UiMemoryMixin" in bases:
            return match.group(0)
        return f"{match.group(1)}{bases.rstrip()}, UiMemoryMixin{match.group(3)}"

    return pattern.sub(replacer, source, count=1)


def _patch_init(source: str, class_name: str) -> str:
    marker = f"class {class_name}"
    class_pos = source.find(marker)
    if class_pos < 0:
        return source

    init_match = re.search(rf"class\s+{re.escape(class_name)}[^{{]*:\s*.*?def\s+__init__\s*\(", source[class_pos:], re.S)
    if not init_match:
        return source

    init_start = class_pos + init_match.end()
    # Find the body of __init__ by tracking indentation.
    lines = source[init_start:].splitlines(keepends=True)
    if not lines:
        return source

    first_body = lines[0]
    indent_match = re.match(r"(\s*)", first_body)
    body_indent = len(indent_match.group(1)) if indent_match else 8
    end_index = 0
    for index in range(1, len(lines)):
        line = lines[index]
        if line.strip() == "":
            continue
        current_indent = len(re.match(r"(\s*)", line).group(1))
        if current_indent < body_indent:
            end_index = index
            break
    else:
        end_index = len(lines)

    init_body = "".join(lines[:end_index])
    if "_init_ui_memory(" in init_body:
        return source

    call_indent = " " * body_indent
    init_call = f"{call_indent}self._init_ui_memory()\n"
    patched_init = init_body + init_call
    return source[:init_start] + patched_init + "".join(lines[end_index:])


def patch_file(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    class_names = re.findall(r"^class\s+(\w+)\s*\(", source, re.M)
    if not class_names:
        return False

    original = source
    changed = False
    for class_name in class_names:
        if not _needs_patch(source, class_name):
            continue
        new_source = _patch_class_bases(source, class_name)
        if new_source != source:
            source = new_source
            changed = True
        new_source = _patch_init(source, class_name)
        if new_source != source:
            source = new_source
            changed = True

    if not changed:
        return False

    source = _insert_import(source)
    if source != original:
        path.write_text(source, encoding="utf-8")
        return True
    return False


def main() -> None:
    patched: list[str] = []
    for path in sorted(UI_DIR.glob("*.py")):
        if path.name in SKIP_FILES:
            continue
        if patch_file(path):
            patched.append(path.name)
    print(f"Patched {len(patched)} file(s):")
    for name in patched:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
