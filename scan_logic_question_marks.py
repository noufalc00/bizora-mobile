from pathlib import Path

skip_dirs = {
    "archive_unused_files",
    "archive_unused_files_pending_delete",
    "__pycache__",
    ".git",
    "venv",
    "env",
    "build",
    "dist",
}

logic_dir = Path("h:/Shared drives/My Drive/App making/apps with windsurf/accounting_app/logic")
bad = []

for path in logic_dir.rglob("*.py"):
    if any(part in skip_dirs for part in path.parts):
        continue
    text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for i, line in enumerate(text, 1):
        stripped = line.strip()
        if "?" in line and not stripped.startswith("#"):
            bad.append((path, i, line))

print("QUESTION_MARK_LINES_IN_ACTIVE_LOGIC:", len(bad))
for path, i, line in bad:
    print(f"{path}:{i}: {line}")
