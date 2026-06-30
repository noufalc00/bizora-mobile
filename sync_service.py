#!/usr/bin/env python3
"""
Supabase sync bridge for Faizan Pro Accounting.

Pushes desktop records to Supabase in the background without blocking or
crashing the PySide6 application when the network is unavailable.

Required .env variables:
    SUPABASE_URL   - Project REST URL, e.g. https://xxxx.supabase.co
    SERVICE_KEY    - Supabase service role key (or SUPABASE_SERVICE_KEY)

Install:
    pip install supabase python-dotenv

Example (after a successful local sale save):
    from sync_service import sync_data

    if result.get("success"):
        sync_data(
            "sales",
            {
                "company_id": active_company["id"],
                "invoice_number": sale_data["invoice_number"],
                "grand_total": sale_data["grand_total"],
            },
        )
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, MutableMapping, Optional

from dotenv import load_dotenv

load_dotenv()

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - optional until pip install
    Client = Any  # type: ignore[misc, assignment]
    create_client = None  # type: ignore[assignment]

_supabase_client: Optional[Client] = None
_supabase_column_cache: dict[str, frozenset[str]] = {}


def _get_env_value(*keys: str) -> str:
    """Return the first non-empty environment variable from keys."""
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return ""


def get_supabase_client() -> Optional[Client]:
    """
    Initialize and cache the Supabase client from .env credentials.

    Returns:
        Configured Supabase client, or None when credentials are missing.
    """
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    if create_client is None:
        print(
            "Sync skipped: supabase package is not installed. "
            "Run: pip install supabase"
        )
        return None

    supabase_url = _get_env_value("SUPABASE_URL")
    service_key = _get_env_value(
        "SERVICE_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_KEY",
    )

    if not supabase_url or not service_key:
        print(
            "Sync skipped: SUPABASE_URL and SERVICE_KEY must be set in .env"
        )
        return None

    if supabase_url.startswith(("postgresql://", "postgres://")):
        print(
            "Sync skipped: SUPABASE_URL must be the REST API URL "
            "(https://<project-ref>.supabase.co), not a PostgreSQL URI."
        )
        return None

    try:
        _supabase_client = create_client(supabase_url, service_key)
        return _supabase_client
    except Exception as exc:
        print(f"Supabase client initialization failed: {exc}")
        return None


def _serialize_sync_value(value: Any) -> Any:
    """Convert desktop/Python values into JSON-safe Supabase payload values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _serialize_sync_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_serialize_sync_value(item) for item in value]
    return str(value)


def _prepare_payload(data_dict: Mapping[str, Any]) -> dict[str, Any]:
    """Build a clean insert payload from a desktop record dictionary."""
    payload: dict[str, Any] = {}
    for key, value in data_dict.items():
        if value is None:
            continue
        payload[str(key)] = _serialize_sync_value(value)
    return payload


def get_supabase_table_columns(table_name: str) -> frozenset[str]:
    """Return column names available on the Supabase/PostgreSQL table."""
    table = (table_name or "").strip()
    if not table:
        return frozenset()

    cached = _supabase_column_cache.get(table)
    if cached is not None:
        return cached

    database_url = _get_env_value(
        "DATABASE_URL",
        "SUPABASE_DATABASE_URL",
        "SUPABASE_CONNECTION_STRING",
    )
    if not database_url:
        return frozenset()

    try:
        import psycopg2
    except ImportError:
        return frozenset()

    try:
        connection = psycopg2.connect(database_url)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    """,
                    (table,),
                )
                columns = frozenset(str(row[0]) for row in cursor.fetchall())
        finally:
            connection.close()
    except Exception as exc:
        print(f"Could not read Supabase columns for {table}: {exc}")
        return frozenset()

    _supabase_column_cache[table] = columns
    return columns


def _filter_row_for_supabase(table_name: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only columns that exist on the remote Supabase table."""
    allowed = get_supabase_table_columns(table_name)
    if not allowed:
        return _prepare_payload(row)
    return _prepare_payload({key: value for key, value in row.items() if str(key) in allowed})


def upsert_records(
    table_name: str,
    rows: list[Mapping[str, Any]],
    on_conflict: str,
    *,
    batch_size: int = 75,
) -> tuple[int, int]:
    """
    Upsert many rows into one Supabase table.

    Returns:
        Tuple of (synced_row_count, failed_batch_count).
    """
    table = (table_name or "").strip()
    if not table or not rows:
        return 0, 0

    client = get_supabase_client()
    if client is None:
        return 0, 1

    synced = 0
    failed_batches = 0
    for start in range(0, len(rows), batch_size):
        chunk = [_filter_row_for_supabase(table, row) for row in rows[start : start + batch_size]]
        chunk = [row for row in chunk if row]
        if not chunk:
            continue
        try:
            client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
            synced += len(chunk)
        except Exception as exc:
            failed_batches += 1
            print(f"Upsert failed for {table} batch starting at {start}: {exc}")
    return synced, failed_batches


def sync_data(table_name: str, data_dict: Mapping[str, Any]) -> bool:
    """
    Push one record to a Supabase table.

    Args:
        table_name: Target Supabase table name, e.g. "sales".
        data_dict: Column/value mapping to insert.

    Returns:
        True when the cloud insert succeeds, otherwise False.
    """
    table = (table_name or "").strip()
    if not table:
        print("Sync failed: table_name is required")
        return False

    if not data_dict:
        print(f"Sync failed: no data provided for table '{table}'")
        return False

    client = get_supabase_client()
    if client is None:
        return False

    payload = _prepare_payload(data_dict)

    try:
        client.table(table).insert(payload).execute()
        print(f"Successfully synced to {table}")
        return True
    except Exception as exc:
        conflict_key = _table_conflict_key(table)
        if conflict_key and "duplicate" in str(exc).lower():
            try:
                client.table(table).upsert(payload, on_conflict=conflict_key).execute()
                print(f"Successfully upserted to {table}")
                return True
            except Exception as upsert_exc:
                print(f"Sync failed for {table}: {upsert_exc}")
                return False
        print(f"Sync failed for {table}: {exc}")
        return False


def _table_conflict_key(table_name: str) -> str:
    """Return the Supabase upsert conflict key for known tables."""
    mapping = {
        "companies": "id",
        "parties": "id",
        "products": "id",
        "sales": "company_id,invoice_number",
        "purchases": "company_id,purchase_number",
    }
    return mapping.get((table_name or "").strip(), "")


def sync_sale_after_save(
    company_id: int,
    sale_data: Mapping[str, Any],
    sale_id: Optional[int] = None,
) -> bool:
    """
    Convenience wrapper for syncing a sale header after a local save.

    Args:
        company_id: Active company registry ID.
        sale_data: Sale header dictionary from the desktop form/logic layer.
        sale_id: Local SQLite sale ID when available.

    Returns:
        True when Supabase accepts the insert, otherwise False.
    """
    payload: MutableMapping[str, Any] = dict(sale_data)
    payload["company_id"] = company_id
    if sale_id is not None:
        payload["id"] = sale_id
        payload["local_sale_id"] = sale_id
    synced, failed = upsert_records("sales", [payload], "company_id,invoice_number")
    return synced > 0 and failed == 0


def sync_purchase_after_save(
    company_id: int,
    purchase_data: Mapping[str, Any],
    purchase_id: Optional[int] = None,
) -> bool:
    """
    Convenience wrapper for syncing a purchase header after a local save.

    Args:
        company_id: Active company registry ID.
        purchase_data: Purchase header dictionary from the desktop form/logic layer.
        purchase_id: Local SQLite purchase ID when available.

    Returns:
        True when Supabase accepts the insert, otherwise False.
    """
    payload: MutableMapping[str, Any] = dict(purchase_data)
    payload["company_id"] = company_id
    if purchase_id is not None:
        payload["id"] = purchase_id
        payload["local_purchase_id"] = purchase_id
    synced, failed = upsert_records("purchases", [payload], "company_id,purchase_number")
    return synced > 0 and failed == 0


# ---------------------------------------------------------------------------
# Integration example for the desktop application
# ---------------------------------------------------------------------------
#
# Place this immediately after a successful local save in ui/sales_entry.py:
#
#     result = self.sales_logic.save_sale(
#         active_company["id"],
#         sale_data,
#         sale_items,
#         self.current_sale_id,
#     )
#
#     if result.get("success"):
#         from sync_service import sync_sale_after_save
#
#         saved_sale_id = None
#         result_data = result.get("data") or {}
#         if isinstance(result_data, dict):
#             saved_sale_id = result_data.get("sale_id")
#
#         sync_sale_after_save(
#             company_id=active_company["id"],
#             sale_data=sale_data,
#             sale_id=saved_sale_id,
#         )
#
# The sync call is non-blocking for the UI only in the sense that failures are
# swallowed safely. For heavy usage, wrap it in a background QThread later.


if __name__ == "__main__":
    demo_ok = sync_data(
        "sales",
        {
            "company_id": 1,
            "invoice_number": "DEMO-0001",
            "grand_total": 1500.0,
            "payment_mode": "Cash",
        },
    )
    print("Demo sync result:", demo_ok)
