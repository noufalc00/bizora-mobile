from pathlib import Path

path = Path("db.py")
print("SCANNING:", path.resolve())

bad = []
for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
    stripped = line.strip()
    allowed = (
        'return "?" if' in line
        or stripped.startswith("#")
        or "SQLite placeholders" in line
        or "question mark" in line.lower()
    )
    if "?" in line and not allowed:
        bad.append((i, line))

print("ROOT_DB_ACTIVE_QUESTION_MARK_LINES:", len(bad))
for i, line in bad:
    print(f"{i}: {line}")
