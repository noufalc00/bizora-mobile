"""Audit report/book top-bar date fields for dd-MM-yyyy clipping."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"

NARROW_WIDTH_PATTERN = re.compile(
    r"\.setFixedWidth\(\s*(90|95|100|105|110)\s*\)|\.setMinimumWidth\(\s*(90|95|100|105|110)\s*\)"
)


def main() -> int:
    """Return non-zero when any UI file still uses a narrow date field width."""
    failures: list[str] = []
    for path in sorted(UI.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "QDateEdit" not in text:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "QDateEdit" in line or "date_edit" in line or "from_date" in line or "to_date" in line:
                if NARROW_WIDTH_PATTERN.search(line) and "get_barcode" not in line:
                    failures.append(f"{path.name}:{line_no}: {line.strip()}")
    if failures:
        print("Potential narrow report date fields:")
        for item in failures:
            print(f"  {item}")
        return 1
    print("No narrow fixed-width date patterns found in ui/*.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
