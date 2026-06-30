#!/usr/bin/env python3
"""
Bulk push local SQLite accounting data to Supabase for mobile web.

Run once on the desktop PC after setup_supabase.py:

    python sync_bulk_to_supabase.py

Optional:
    python sync_bulk_to_supabase.py --company-id 25
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import Any, Optional

from db import get_default_database_path
from sync_service import get_supabase_client, upsert_records


def _fetch_rows(db_path: str, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Fetch rows from SQLite as dictionaries."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def bulk_sync_to_supabase(company_id: Optional[int] = None) -> bool:
    """
    Upsert companies, parties, sales, and purchases into Supabase.

    Args:
        company_id: Optional company filter. When omitted, sync all companies.

    Returns:
        True when at least one table syncs without batch failures.
    """
    client = get_supabase_client()
    if client is None:
        print("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env")
        return False

    db_path = get_default_database_path()
    company_filter = ""
    params: tuple[Any, ...] = ()
    if company_id is not None:
        company_filter = "WHERE id = ?"
        params = (company_id,)

    companies = _fetch_rows(db_path, f"SELECT * FROM companies {company_filter}", params)
    if not companies:
        print("No companies found in local database.")
        return False

    company_ids = [int(row["id"]) for row in companies if row.get("id") is not None]
    placeholders = ",".join("?" for _ in company_ids)

    parties = _fetch_rows(
        db_path,
        f"SELECT * FROM parties WHERE company_id IN ({placeholders})",
        tuple(company_ids),
    )
    sales = _fetch_rows(
        db_path,
        f"SELECT * FROM sales WHERE company_id IN ({placeholders})",
        tuple(company_ids),
    )
    purchases = _fetch_rows(
        db_path,
        f"SELECT * FROM purchases WHERE company_id IN ({placeholders})",
        tuple(company_ids),
    )

    print(f"Local database: {db_path}")
    print(
        f"Preparing sync -> companies: {len(companies)}, parties: {len(parties)}, "
        f"sales: {len(sales)}, purchases: {len(purchases)}"
    )

    total_failed = 0
    for table_name, rows, conflict in (
        ("companies", companies, "id"),
        ("parties", parties, "id"),
        ("sales", sales, "company_id,invoice_number"),
        ("purchases", purchases, "company_id,purchase_number"),
    ):
        synced, failed = upsert_records(table_name, rows, conflict)
        total_failed += failed
        print(f"  {table_name}: synced {synced} row(s), failed batches {failed}")

    active = next((row for row in companies if row.get("is_active")), companies[0])
    active_id = active.get("id")
    active_name = active.get("business_name", "")
    print("")
    print("Bulk sync complete.")
    print(f"Active company for mobile: id={active_id}, name={active_name}")
    print("Set Render env MOBILE_COMPANY_ID to this id, or leave empty for auto-detect.")
    return total_failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk sync local DB data to Supabase")
    parser.add_argument("--company-id", type=int, default=None, help="Sync one company only")
    args = parser.parse_args()
    ok = bulk_sync_to_supabase(args.company_id)
    raise SystemExit(0 if ok else 1)
