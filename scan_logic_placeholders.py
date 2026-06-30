from pathlib import Path

targets = [
    "logic/stock_logic.py",
    "logic/ledger_logic.py",
    "logic/trial_balance_logic.py",
]

bad = []
for target in targets:
    path = Path(target)
    if not path.exists():
        continue
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        stripped = line.strip()
        if "?" in line and not stripped.startswith("#"):
            bad.append((target, i, line))

print("QUESTION_MARK_LINES_IN_TARGET_LOGIC:", len(bad))
for target, i, line in bad:
    print(f"{target}:{i}: {line}")
