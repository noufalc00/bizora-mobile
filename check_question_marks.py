from pathlib import Path

db_py_path = Path("h:/Shared drives/My Drive/App making/apps with windsurf/accounting_app/db.py")
with open(db_py_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if "?" in line:
        print(f"{i}: {line.rstrip()}")
