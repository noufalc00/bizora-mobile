from pathlib import Path
import zipfile

zip_path = Path("accounting_app_verified_2026_04_30.zip")
print("ZIP_PATH:", zip_path.resolve())

with zipfile.ZipFile(zip_path, "r") as z:
    names = z.namelist()
    db_candidates = [n for n in names if n.endswith("/db.py") or n == "db.py"]
    print("DB_CANDIDATES_IN_ZIP:", db_candidates)

    # Prefer root db.py or accounting_app/db.py, but print all candidates.
    for name in db_candidates:
        data = z.read(name).decode("utf-8", errors="ignore").splitlines()
        bad = []
        for i, line in enumerate(data, 1):
            stripped = line.strip()
            allowed = (
                'return "?" if' in line
                or stripped.startswith("#")
                or "SQLite placeholders" in line
                or "question mark" in line.lower()
            )
            if "?" in line and not allowed:
                bad.append((i, line))

        print("ZIP_DB_FILE:", name)
        print("ZIP_DB_QUESTION_MARK_LINES:", len(bad))
        for i, line in bad[:50]:
            print(f"{i}: {line}")
