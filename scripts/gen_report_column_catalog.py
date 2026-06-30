"""Generate bizora_core/report_column_catalog.py from desktop UI definitions."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "ui" / "book_report_common.py"
TARGET = ROOT / "bizora_core" / "report_column_catalog.py"


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    match = re.search(r"^REPORT_COLUMNS = (\{.*?\})\nAMOUNT_KEYS", text, re.M | re.S)
    if not match:
        raise SystemExit("REPORT_COLUMNS not found")

    columns = ast.literal_eval(match.group(1))
    lines = [
        '"""',
        "Desktop report column definitions shared by mobile web tables.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any",
        "",
        "VOUCHER_REPORT_COLUMNS: dict[str, list[tuple[str, str]]] = {",
    ]
    for mode, pairs in columns.items():
        lines.append(f'    "{mode}": [')
        for label, key in pairs:
            lines.append(f'        ("{label}", "{key}"),')
        lines.append("    ],")
    lines.extend(
        [
            "}",
            "",
            'MODE_LABEL_ALIASES: dict[str, str] = {"Credit / Pending": "Credit"}',
            "",
            "",
            "def normalize_report_mode(mode: str | None) -> str:",
            '    """Map mobile filter labels to desktop report column keys."""',
            '    label = str(mode or "Bill Wise").strip()',
            "    return MODE_LABEL_ALIASES.get(label, label)",
            "",
            "",
            "def columns_for_voucher_mode(mode: str | None) -> list[dict[str, str]]:",
            '    """Return ordered column metadata for one voucher book mode."""',
            "    key = normalize_report_mode(mode)",
            '    pairs = VOUCHER_REPORT_COLUMNS.get(key) or VOUCHER_REPORT_COLUMNS["Bill Wise"]',
            '    return [{"label": label, "key": data_key} for label, data_key in pairs]',
            "",
            "",
            "def build_voucher_table_payload(",
            "    rows: list[dict[str, Any]],",
            "    mode: str | None,",
            ") -> dict[str, Any]:",
            '    """Build mobile table payload using desktop voucher column order."""',
            "    from bizora_core.mobile_report_display import format_rows_for_display",
            "",
            "    cleaned = format_rows_for_display(rows)",
            "    column_meta = columns_for_voucher_mode(mode)",
            "    return {",
            '        "rows": cleaned,',
            '        "columns": column_meta,',
            '        "row_count": len(cleaned),',
            "    }",
            "",
        ]
    )
    TARGET.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
