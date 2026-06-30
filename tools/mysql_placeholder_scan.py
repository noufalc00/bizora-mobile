from pathlib import Path

targets = [
    "ui/sales_entry.py",
    "ui/sales_entry_calculations.py",
    "logic/sales_logic.py",
    "logic/ledger_logic.py",
    "logic/voucher_posting_engine.py",
    "ui/ledger_page.py",
    "tools/test_sales_reset_and_paid_ledger.py",
]

bad = []
for target in targets:
    p = Path(target)
    if not p.exists():
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        stripped = line.strip()
        allowed = (
            'return "?" if' in line
            or stripped.startswith("#")
            or "question mark" in line.lower()
            or "SQLite placeholders" in line
        )
        if "?" in line and not allowed:
            bad.append((target, i, line))

print("QUESTION_MARK_LINES:", len(bad))
for target, i, line in bad:
    print(f"{target}:{i}: {line}")
