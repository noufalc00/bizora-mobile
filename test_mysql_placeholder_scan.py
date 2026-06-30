from pathlib import Path

targets = [
    "db.py",
    "logic/day_book_logic.py",
    "ui/day_book_page.py",
    "tools/diagnose_day_book.py",
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
