#!/usr/bin/env python3
"""
Provision core Faizan Pro Accounting tables on Supabase (PostgreSQL).

Reads CREATE TABLE definitions from db.py, translates SQLite-style DDL to
PostgreSQL, and executes them against the connection string in .env.

Required .env variable (first match wins):
    DATABASE_URL
    SUPABASE_DATABASE_URL
    SUPABASE_CONNECTION_STRING

Dependencies:
    pip install python-dotenv psycopg2-binary
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load environment variables before any other imports or path setup.
load_dotenv()

import re
import sys
from pathlib import Path

import psycopg2
from psycopg2 import errors as pg_errors

ROOT_DIR = Path(__file__).resolve().parent
DB_PY_PATH = ROOT_DIR / "db.py"

# Parent tables required by foreign keys on the main business tables.
TABLE_ORDER = (
    "companies",
    "parties",
    "products",
    "ledger_accounts",
    "sales",
    "sales_items",
    "sales_returns",
    "purchases",
    "purchase_items",
    "purchase_returns",
    "ledger_entries",
    "quotations",
    "quotation_items",
    "purchase_orders",
    "purchase_order_items",
    "pdc_register",
    "stock_movements",
)

# f-string placeholders used inside db.py CREATE TABLE blocks.
PLACEHOLDER_REPLACEMENTS = {
    "{pk_autoinc}": "SERIAL PRIMARY KEY",
    "{pk_autoinc_2}": "INTEGER",
    "{timestamp_default}": "CURRENT_TIMESTAMP",
    "{varchar_255}": "VARCHAR(255)",
    "{varchar_100}": "VARCHAR(100)",
    "{varchar_50}": "VARCHAR(50)",
    "{varchar_20}": "VARCHAR(20)",
    "{invoice_number_type}": "VARCHAR(100)",
    "{sales_type_type}": "VARCHAR(50)",
    "{bill_series_type}": "VARCHAR(50)",
    "{nature_type}": "VARCHAR(50)",
    "{gstin_type}": "VARCHAR(15)",
    "{state_type}": "VARCHAR(100)",
    "{sales_rate_type}": "VARCHAR(50)",
    "{purchase_number_type}": "VARCHAR(100)",
    "{purchase_type_type}": "VARCHAR(50)",
    "{purchase_rate_type}": "VARCHAR(50)",
    "{account_name_type}": "VARCHAR(255)",
    "{account_type_type}": "VARCHAR(50)",
    "{voucher_type_type}": "VARCHAR(50)",
    "{voucher_no_type}": "VARCHAR(100)",
    "{reference_type_type}": "VARCHAR(50)",
    "{name_type}": "VARCHAR(255)",
    "{barcode_type}": "VARCHAR(100)",
    "{hsn_type}": "VARCHAR(50)",
    "{unit_type}": "VARCHAR(50)",
    "{category_type}": "VARCHAR(100)",
    "{color_type}": "VARCHAR(50)",
    "{size_type}": "VARCHAR(50)",
    "{setting_key_type}": "VARCHAR(255)",
    "{module_type}": "VARCHAR(100)",
    "{action_type}": "VARCHAR(20)",
    "{reference_type}": "VARCHAR(100)",
}


def _redact_connection_string(value: str) -> str:
    """Mask credentials before printing connection strings in debug output."""
    text = (value or "").strip()
    if "://" not in text or "@" not in text:
        return text[:20] + "..." if len(text) > 20 else text
    scheme, remainder = text.split("://", 1)
    credentials, host_part = remainder.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host_part}"


def _debug_env_file_contents(env_path: str) -> str | None:
    """
    Manually read .env and report whether DATABASE_URL is present.

    Also supports a bare postgresql:// line with no KEY= prefix.
    """
    print("--- Checking file contents manually ---")
    if not os.path.isfile(env_path):
        print(f"[DEBUG] .env file not found at: {env_path}")
        return None

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            content = env_file.read()
    except OSError as exc:
        print(f"[DEBUG] Could not read .env: {exc}")
        return None

    preview = content.strip().replace("\n", "\\n")
    if preview:
        print(f"[DEBUG] File content preview: {_redact_connection_string(preview)}")
    else:
        print("[DEBUG] File content is empty")

    if "DATABASE_URL" in content:
        print("SUCCESS: File contains DATABASE_URL")
    else:
        print("FAILURE: File does NOT contain DATABASE_URL. Check for typos.")

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("DATABASE_URL="):
            return stripped.split("=", 1)[1].strip().strip('"').strip("'")
        if stripped.startswith(("postgresql://", "postgres://")):
            print(
                "[DEBUG] Found bare connection URL without DATABASE_URL= prefix; "
                "using it as a fallback."
            )
            return stripped.strip('"').strip("'")

    return None


def load_connection_string() -> str:
    """Load the Supabase/PostgreSQL connection string from .env."""
    env_cwd_path = os.path.join(os.getcwd(), ".env")
    env_script_path = str(ROOT_DIR / ".env")

    print("[DEBUG] Current working directory:", os.getcwd())
    print("[DEBUG] Script directory:", ROOT_DIR)
    print("[DEBUG] Looking for .env at:", env_cwd_path)
    print("[DEBUG] Looking for .env at:", env_script_path)
    print("[DEBUG] os.path.exists('.env') in cwd:", os.path.exists(".env"))
    print("[DEBUG] .env exists next to script:", os.path.isfile(env_script_path))

    manual_value = _debug_env_file_contents(env_script_path)
    if not manual_value and env_cwd_path != env_script_path:
        manual_value = _debug_env_file_contents(env_cwd_path)

    # Reload from explicit paths in case the script was launched elsewhere.
    load_dotenv(env_script_path)
    load_dotenv(env_cwd_path)

    database_url = os.getenv("DATABASE_URL")
    if not (database_url or "").strip():
        print("[DEBUG] DATABASE_URL is None or empty after load_dotenv()")
        print("[DEBUG] Environment keys loaded:")
        for key in sorted(os.environ.keys()):
            print(f"  - {key}")

    for key in (
        "DATABASE_URL",
        "SUPABASE_DATABASE_URL",
        "SUPABASE_CONNECTION_STRING",
    ):
        value = (os.getenv(key) or "").strip()
        if value:
            return value

    if manual_value:
        print("[DEBUG] Using connection string from manual .env file read")
        return manual_value

    raise RuntimeError(
        "No database connection string found. Set DATABASE_URL (or "
        "SUPABASE_DATABASE_URL / SUPABASE_CONNECTION_STRING) in .env"
    )


def _extract_parenthesized_body(text: str, open_paren_index: int) -> str:
    """
    Return the SQL inside a balanced (...) block starting at open_paren_index.

    Handles nested parentheses and single-quoted string literals so CHECK
    constraints like IN ('Debitor', 'Creditor', 'Both') are not truncated.
    """
    if open_paren_index < 0 or open_paren_index >= len(text) or text[open_paren_index] != "(":
        raise ValueError("Expected '(' at the start of a CREATE TABLE column list")

    depth = 0
    in_single_quote = False
    content_start = open_paren_index + 1

    for index in range(open_paren_index, len(text)):
        char = text[index]

        if in_single_quote:
            if char == "'" and text[index - 1] != "\\":
                in_single_quote = False
            continue

        if char == "'":
            in_single_quote = True
            continue

        if char == "(":
            depth += 1
            continue

        if char == ")":
            depth -= 1
            if depth == 0:
                return text[content_start:index]

    raise ValueError("Unbalanced parentheses while extracting CREATE TABLE body")


def _find_create_table_open_paren(db_py_text: str, table_name: str) -> tuple[int, bool] | None:
    """Locate the opening '(' of a CREATE TABLE statement for table_name."""
    patterns = (
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table_name)}\s*\(",
        rf"CREATE TABLE {re.escape(table_name)}\s*\(",
    )
    for pattern in patterns:
        match = re.search(pattern, db_py_text, flags=re.IGNORECASE)
        if match:
            return match.end() - 1, "IF NOT EXISTS" in match.group(0).upper()
    return None


def extract_create_table_sql(db_py_text: str, table_name: str) -> str:
    """
    Extract the first CREATE TABLE statement for table_name from db.py.

    Prefers `CREATE TABLE IF NOT EXISTS`; falls back to plain `CREATE TABLE`.
    """
    located = _find_create_table_open_paren(db_py_text, table_name)
    if located is None:
        raise ValueError(f"Could not find CREATE TABLE definition for '{table_name}' in db.py")

    open_paren_index, _uses_if_not_exists = located
    body = _extract_parenthesized_body(db_py_text, open_paren_index)
    body = re.sub(r"\s+", " ", body.strip())
    return f"CREATE TABLE {table_name} ({body})"


def _assert_balanced_parentheses(sql: str, table_name: str) -> None:
    """Raise when CREATE TABLE SQL contains unbalanced parentheses."""
    depth = 0
    in_single_quote = False
    for index, char in enumerate(sql):
        if in_single_quote:
            if char == "'" and sql[index - 1] != "\\":
                in_single_quote = False
            continue
        if char == "'":
            in_single_quote = True
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(f"Unbalanced parentheses in {table_name} DDL")

    if depth != 0:
        raise ValueError(f"Unbalanced parentheses in {table_name} DDL")


def resolve_placeholders(sql: str) -> str:
    """Replace db.py f-string placeholders with concrete PostgreSQL types."""
    resolved = sql
    for placeholder, replacement in PLACEHOLDER_REPLACEMENTS.items():
        resolved = resolved.replace(placeholder, replacement)

    # Any remaining {foo_type} placeholders default to VARCHAR(255).
    resolved = re.sub(r"\{[a-z0-9_]+_type\}", "VARCHAR(255)", resolved, flags=re.I)
    resolved = re.sub(r"\{[a-z0-9_]+\}", "TEXT", resolved, flags=re.I)
    return resolved


def translate_sqlite_to_postgresql(sql: str) -> str:
    """Convert SQLite-oriented DDL extracted from db.py into PostgreSQL syntax."""
    translated = resolve_placeholders(sql)

    replacements = (
        (r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "SERIAL PRIMARY KEY"),
        (r"\bINT\s+AUTO_INCREMENT\s+PRIMARY\s+KEY\b", "SERIAL PRIMARY KEY"),
        (r"\bINTEGER\s+PRIMARY\s+KEY\b", "SERIAL PRIMARY KEY"),
        (r"\bAUTOINCREMENT\b", ""),
        (r"\bAUTO_INCREMENT\b", ""),
        (r"\bREAL\b", "DECIMAL(18, 4)"),
        (r"\bDOUBLE\b", "DECIMAL(18, 4)"),
        (r"\bDATETIME\b", "TIMESTAMP"),
        (r"\bBOOLEAN\s+DEFAULT\s+1\b", "BOOLEAN DEFAULT TRUE"),
        (r"\bBOOLEAN\s+DEFAULT\s+0\b", "BOOLEAN DEFAULT FALSE"),
        (r"\bINTEGER\s+DEFAULT\s+1\b", "INTEGER DEFAULT 1"),
        (r"\bINTEGER\s+DEFAULT\s+0\b", "INTEGER DEFAULT 0"),
    )
    for pattern, replacement in replacements:
        translated = re.sub(pattern, replacement, translated, flags=re.IGNORECASE)

    translated = re.sub(r",\s*,", ",", translated)
    translated = re.sub(r"\s+", " ", translated).strip()
    return translated


def enhance_sales_table(sql: str) -> str:
    """Add columns present in db.py migrations but absent from the base CREATE."""
    if "form_of_sale" in sql:
        return sql
    return sql.replace(
        "salesman TEXT,",
        "salesman TEXT, form_of_sale TEXT DEFAULT 'B2CS',",
        1,
    )


def enhance_sales_items_table(sql: str) -> str:
    """Prefer the full sales_items column set from db.py rebuild logic."""
    if "cgst_amount" in sql:
        return sql
    extra_columns = (
        "cgst DECIMAL(18, 4) DEFAULT 0.0, "
        "sgst DECIMAL(18, 4) DEFAULT 0.0, "
        "igst DECIMAL(18, 4) DEFAULT 0.0, "
        "cess DECIMAL(18, 4) DEFAULT 0.0, "
        "cgst_amount DECIMAL(18, 4) DEFAULT 0.0, "
        "sgst_amount DECIMAL(18, 4) DEFAULT 0.0, "
        "igst_amount DECIMAL(18, 4) DEFAULT 0.0, "
        "cess_amount DECIMAL(18, 4) DEFAULT 0.0, "
        "cost_price DECIMAL(18, 4) DEFAULT 0.0, "
        "cost_value DECIMAL(18, 4) DEFAULT 0.0, "
    )
    return sql.replace(
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,",
        f"created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, {extra_columns}",
        1,
    )


def build_table_statements() -> list[tuple[str, str]]:
    """Extract and translate CREATE TABLE statements from db.py."""
    if not DB_PY_PATH.is_file():
        raise FileNotFoundError(f"db.py not found at {DB_PY_PATH}")

    db_py_text = DB_PY_PATH.read_text(encoding="utf-8")
    statements: list[tuple[str, str]] = []

    for table_name in TABLE_ORDER:
        raw_sql = extract_create_table_sql(db_py_text, table_name)
        pg_sql = translate_sqlite_to_postgresql(raw_sql)

        if table_name == "sales":
            pg_sql = enhance_sales_table(pg_sql)
        elif table_name == "sales_items":
            pg_sql = enhance_sales_items_table(pg_sql)

        _assert_balanced_parentheses(pg_sql, table_name)
        statements.append((table_name, pg_sql))

    return statements


def table_exists(cursor, table_name: str) -> bool:
    """Return True when table_name already exists in the public schema."""
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        )
        """,
        (table_name,),
    )
    return bool(cursor.fetchone()[0])


def execute_create_table(cursor, table_name: str, create_sql: str) -> None:
    """Execute one CREATE TABLE statement with safe duplicate handling."""
    if table_exists(cursor, table_name):
        print(f"Table already exists: {table_name}")
        return

    try:
        cursor.execute(create_sql)
        print(f"Created table: {table_name}")
    except pg_errors.DuplicateTable:
        print(f"Table already exists: {table_name}")
    except pg_errors.DuplicateObject:
        print(f"Table already exists: {table_name}")


def main() -> int:
    """Connect to Supabase and create the core accounting tables."""
    try:
        connection_string = load_connection_string()
        statements = build_table_statements()
    except Exception as exc:
        print(f"Setup failed during preparation: {exc}", file=sys.stderr)
        return 1

    connection = None
    try:
        connection = psycopg2.connect(connection_string)
        connection.autocommit = True
        cursor = connection.cursor()

        print("Starting Supabase schema setup...")
        for table_name, create_sql in statements:
            execute_create_table(cursor, table_name, create_sql)

        print("Database setup complete!")
        return 0
    except psycopg2.Error as exc:
        print(f"Database error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
