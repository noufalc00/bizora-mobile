#!/usr/bin/env python3
"""
Bulk push local SQLite accounting data to Supabase for mobile web.

Run once on the desktop PC after setup_supabase.py:

    python setup_supabase.py
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


SYNC_PLAN: tuple[tuple[str, str, str], ...] = (
    ("companies", "SELECT * FROM companies {company_filter}", "id"),
    (
        "parties",
        "SELECT * FROM parties WHERE company_id IN ({company_ids})",
        "id",
    ),
    (
        "products",
        "SELECT * FROM products WHERE company_id IN ({company_ids})",
        "id",
    ),
    (
        "ledger_accounts",
        "SELECT * FROM ledger_accounts WHERE company_id IN ({company_ids})",
        "id",
    ),
    (
        "sales",
        "SELECT * FROM sales WHERE company_id IN ({company_ids})",
        "company_id,invoice_number",
    ),
    (
        "sales_items",
        "SELECT si.* FROM sales_items si INNER JOIN sales s ON s.id = si.sale_id "
        "WHERE s.company_id IN ({company_ids})",
        "id",
    ),
    (
        "sales_returns",
        "SELECT * FROM sales_returns WHERE company_id IN ({company_ids})",
        "company_id,return_no",
    ),
    (
        "sales_return_items",
        "SELECT sri.* FROM sales_return_items sri INNER JOIN sales_returns sr ON sr.id = sri.sales_return_id "
        "WHERE sr.company_id IN ({company_ids})",
        "id",
    ),
    (
        "purchases",
        "SELECT * FROM purchases WHERE company_id IN ({company_ids})",
        "company_id,purchase_number",
    ),
    (
        "purchase_items",
        "SELECT pi.* FROM purchase_items pi INNER JOIN purchases p ON p.id = pi.purchase_id "
        "WHERE p.company_id IN ({company_ids})",
        "id",
    ),
    (
        "purchase_returns",
        "SELECT * FROM purchase_returns WHERE company_id IN ({company_ids})",
        "company_id,return_no",
    ),
    (
        "purchase_return_items",
        "SELECT pri.* FROM purchase_return_items pri INNER JOIN purchase_returns pr ON pr.id = pri.purchase_return_id "
        "WHERE pr.company_id IN ({company_ids})",
        "id",
    ),
    (
        "ledger_entries",
        "SELECT * FROM ledger_entries WHERE company_id IN ({company_ids})",
        "id",
    ),
    (
        "quotations",
        "SELECT * FROM quotations WHERE company_id IN ({company_ids})",
        "company_id,quotation_no",
    ),
    (
        "quotation_items",
        "SELECT qi.* FROM quotation_items qi INNER JOIN quotations q ON q.id = qi.quotation_id "
        "WHERE q.company_id IN ({company_ids})",
        "id",
    ),
    (
        "purchase_orders",
        "SELECT * FROM purchase_orders WHERE company_id IN ({company_ids})",
        "company_id,po_number",
    ),
    (
        "purchase_order_items",
        "SELECT poi.* FROM purchase_order_items poi INNER JOIN purchase_orders po ON po.id = poi.po_id "
        "WHERE po.company_id IN ({company_ids})",
        "id",
    ),
    (
        "pdc_register",
        "SELECT * FROM pdc_register WHERE company_id IN ({company_ids})",
        "id",
    ),
    (
        "stock_movements",
        "SELECT * FROM stock_movements WHERE company_id IN ({company_ids})",
        "id",
    ),
)


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
    Upsert core business tables into Supabase for mobile cloud mode.

    Args:
        company_id: Optional company filter. When omitted, sync all companies.

    Returns:
        True when no batch failures occur.
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
    company_ids_sql = placeholders

    print(f"Local database: {db_path}")
    print(f"Companies selected: {len(companies)} -> ids {company_ids}")

    total_failed = 0
    for table_name, query_template, conflict in SYNC_PLAN:
        if table_name == "companies":
            query = query_template.format(company_filter=company_filter)
            rows = _fetch_rows(db_path, query, params)
        else:
            query = query_template.format(company_ids=company_ids_sql)
            rows = _fetch_rows(db_path, query, tuple(company_ids))

        synced, failed = upsert_records(table_name, rows, conflict)
        total_failed += failed
        print(f"  {table_name}: synced {synced} row(s), failed batches {failed}")

    active = next((row for row in companies if row.get("is_active")), companies[0])
    active_id = active.get("id")
    active_name = active.get("business_name", "")
    print("")
    print("Bulk sync complete.")
    print(f"Active company for mobile: id={active_id}, name={active_name}")
    print("Render env: MOBILE_COMPANY_ID=%s (or leave empty for auto-detect)" % active_id)
    return total_failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk sync local DB data to Supabase")
    parser.add_argument("--company-id", type=int, default=None, help="Sync one company only")
    args = parser.parse_args()
    ok = bulk_sync_to_supabase(args.company_id)
    raise SystemExit(0 if ok else 1)
