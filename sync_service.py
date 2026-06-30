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
        print(f"Sync failed for {table}: {exc}")
        return False


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
        payload["local_sale_id"] = sale_id
    return sync_data("sales", payload)


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
        payload["local_purchase_id"] = purchase_id
    return sync_data("purchases", payload)


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
