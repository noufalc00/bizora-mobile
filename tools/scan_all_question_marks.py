from pathlib import Path

targets = [
    "logic/ledger_logic.py",
    "logic/stock_logic.py",
    "logic/trial_balance_logic.py",
    "ui/ledger_page.py",
    "ui/stock_report_page.py",
    "tools/rebuild_ledger_for_active_company.py",
    "tools/diagnose_old_voucher_ledger_backfill.py",
    "db.py",
]

bad = []
for target in targets:
    path = Path(target)
    if not path.exists():
        continue
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        stripped = line.strip()
        # Exclude _get_placeholder() method which correctly returns "?" for SQLite
        if "?" in line and not stripped.startswith("#") and "return \"?\"" not in line:
            bad.append((target, i, line))

print("QUESTION_MARK_LINES:", len(bad))
for target, i, line in bad:
    print(f"{target}:{i}: {line}")
