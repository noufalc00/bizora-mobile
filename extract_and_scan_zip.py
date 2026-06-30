import zipfile
from pathlib import Path

zip_path = Path(r"h:\Shared drives\My Drive\App making\apps with windsurf\accounting_app\accounting_app_fresh.zip")
extract_dir = Path(r"h:\Shared drives\My Drive\App making\apps with windsurf\accounting_app\temp_extract")

# Extract db.py from zip
with zipfile.ZipFile(zip_path, 'r') as zipf:
    zipf.extract('db.py', extract_dir)

# Scan the extracted db.py
db_py_path = extract_dir / 'db.py'
with open(db_py_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

q_lines = []
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if "?" in line and 'return "?" if' not in line and not stripped.startswith("#"):
        q_lines.append((i, line))

print(f"db.py inside zip - Lines with ?: {len(q_lines)}")
for i, line in q_lines:
    print(f"{i}: {line.rstrip()}")

# Clean up
db_py_path.unlink()
