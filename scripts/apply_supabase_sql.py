#!/usr/bin/env python3
"""
Apply sql/supabase_views_functions.sql to the connected Supabase project.

Uses the DATABASE_URL from .env (same variable setup_supabase.py uses).
Drops any conflicting hand-authored versions first, then executes the
whole master SQL file in a single transaction so a syntax error rolls
everything back cleanly.

Usage:
    python scripts/apply_supabase_sql.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

import psycopg2

SQL_FILE = ROOT / "sql" / "supabase_views_functions.sql"

# Any function signature we know might collide with the hand-authored
# copies currently installed. Dropping first avoids ambiguity errors
# when CREATE OR REPLACE hits a different return-shape.
DROP_STATEMENTS = (
    "DROP FUNCTION IF EXISTS public.f_trial_balance(int, date, date, text, text)",
    "DROP FUNCTION IF EXISTS public.f_monthly_analysis(int, date, date)",
    "DROP FUNCTION IF EXISTS public.f_day_book_entries(int, date, date)",
    "DROP FUNCTION IF EXISTS public.f_trial_balance_debug(int, date, date)",
    "DROP FUNCTION IF EXISTS public.f_cash_book(int, date, date)",
    "DROP FUNCTION IF EXISTS public.is_row_active(anyelement)",
    "DROP VIEW IF EXISTS public.v_ledger_monthly_totals CASCADE",
    "DROP VIEW IF EXISTS public.v_ledger_daily_totals CASCADE",
    "DROP VIEW IF EXISTS public.v_ledger_entries_enriched CASCADE",
)


def _connection_string() -> str:
    for key in ("DATABASE_URL", "SUPABASE_DATABASE_URL", "SUPABASE_CONNECTION_STRING"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    raise RuntimeError("No DATABASE_URL set in .env")


def main() -> int:
    if not SQL_FILE.exists():
        print(f"SQL file missing: {SQL_FILE}")
        return 2

    dsn = _connection_string()
    sql_body = SQL_FILE.read_text(encoding="utf-8")

    print(f"Connecting via {dsn.split('@', 1)[-1] if '@' in dsn else '?'}")

    connection = psycopg2.connect(dsn)
    connection.autocommit = False
    try:
        with connection.cursor() as cursor:
            print("Dropping any pre-existing views/functions...")
            for statement in DROP_STATEMENTS:
                cursor.execute(statement)
                print(f"  ok: {statement}")

            print()
            print(f"Executing {SQL_FILE.name} ({sql_body.count(chr(10))} lines)...")
            cursor.execute(sql_body)
            print("  ok: master SQL body executed")

            print()
            print("Verifying installed objects...")
            cursor.execute(
                """
                SELECT proname,
                       pg_get_function_arguments(oid) AS args,
                       pg_get_function_result(oid)   AS returns
                FROM pg_proc
                WHERE proname IN (
                    'is_row_active',
                    'f_trial_balance',
                    'f_monthly_analysis',
                    'f_day_book_entries',
                    'f_cash_book'
                )
                ORDER BY proname
                """
            )
            rows = cursor.fetchall()
            for name, args, returns in rows:
                print(f"  {name:22} args=({args}) returns={returns[:80]}...")

            missing = {
                "is_row_active",
                "f_trial_balance",
                "f_monthly_analysis",
                "f_day_book_entries",
                "f_cash_book",
            } - {r[0] for r in rows}
            if missing:
                print(f"MISSING functions: {missing}")
                connection.rollback()
                return 1

            cursor.execute("NOTIFY pgrst, 'reload schema'")
            print()
            print("  ok: NOTIFY pgrst 'reload schema' fired")

        connection.commit()
        print()
        print("Committed. Fast-path SQL is now aligned with the repo.")
        return 0
    except Exception as exc:
        connection.rollback()
        print(f"Rolled back due to error: {exc}")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
