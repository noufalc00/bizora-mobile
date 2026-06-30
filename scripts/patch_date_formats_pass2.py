"""Second pass: wire configure_qdate_edit and format table date cells."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"

IMPORT_LINE = (
    "from ui.date_formats import configure_qdate_edit, format_display_date, "
    "qdate_to_db, qdate_to_display, db_to_qdate\n"
)

DATE_EDIT_RE = re.compile(
    r"^(\s*)(self\.[\w]+)\s*=\s*QDateEdit\(([^\)]*)\)\s*$"
)


def ensure_import(text: str) -> str:
    if "from ui.date_formats import" in text:
        if "configure_qdate_edit" not in text:
            text = text.replace(
                "from ui.date_formats import",
                "from ui.date_formats import configure_qdate_edit, format_display_date, "
                "qdate_to_db, qdate_to_display, db_to_qdate, ",
                1,
            )
        return text
    for anchor in (
        "from ui.ui_memory import",
        "from ui.book_report_common import",
        "from bizora_core.book_report_common import",
    ):
        if anchor in text:
            return text.replace(anchor, IMPORT_LINE + anchor, 1)
    return text


def inject_configure_calls(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    for index, line in enumerate(lines):
        output.append(line)
        match = DATE_EDIT_RE.match(line)
        if not match:
            continue
        indent, var_name, _args = match.groups()
        window = "\n".join(lines[index + 1 : index + 4])
        if "configure_qdate_edit(" in window:
            continue
        output.append(f"{indent}configure_qdate_edit({var_name})")
    return "\n".join(lines) if len(output) == len(lines) else "\n".join(output)


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    text = ensure_import(text)
    text = inject_configure_calls(text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    patched = []
    for path in sorted(UI.glob("*.py")):
        if path.name == "date_formats.py":
            continue
        if patch_file(path):
            patched.append(path.name)
    print(f"Configured QDateEdit in {len(patched)} file(s):")
    for name in patched:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
