from pathlib import Path

db_py_path = Path("h:/Shared drives/My Drive/App making/apps with windsurf/accounting_app/db.py")
with open(db_py_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

bad = []
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if "?" in line and 'return "?" if' not in line and not stripped.startswith("#"):
        bad.append((i, line))

print("QUESTION_MARK_LINES:", len(bad))
for i, line in bad:
    print(f"{i}: {line}")
