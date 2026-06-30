from pathlib import Path

text = Path("db.py").read_text(encoding="utf-8", errors="ignore")

required = [
    "def _create_companies_table",
    "def _create_parties_table",
    "def _create_settings_table",
    "def _get_placeholder",
    "def _safe_identifier",
]

for item in required:
    print(item, "FOUND" if item in text else "MISSING")
