#!/usr/bin/env python3
"""
Focused audit for a single ledger account (default: id=211).

Prints the raw row exactly as Supabase returns it, the Python type of
every column, and the boolean result of the Postgres helper
`is_row_active(is_active)`. Then reports whether the account passes each
of the four filters that decide inclusion:

    1. Desktop SQLite:     WHERE is_active = 1              (strict int)
    2. Fast-path RPC:      WHERE is_row_active(is_active)   (tolerant)
    3. Bridge default:     column absent in row -> SQLite DEFAULT 1
    4. Any ledger entries: whether the account has voucher rows in period

Usage:
    python scripts/inspect_account_211.py                  # id=211, co=25
    python scripts/inspect_account_211.py 211 25
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

DEFAULT_ACCOUNT_ID = 211
DEFAULT_COMPANY_ID = int(os.getenv("MOBILE_COMPANY_ID") or 25)
DEFAULT_FROM = os.getenv("QA_FROM_DATE") or "2024-04-01"
DEFAULT_TO = os.getenv("QA_TO_DATE") or "2026-06-30"


def _describe(value: Any) -> str:
    """Return a compact <type>: <repr> string for a Python value."""
    return f"{type(value).__name__} :: {value!r}"


def _run_rpc(client: Any, name: str, params: dict[str, Any]) -> Any:
    """Return response.data or an Exception object so we can dump it."""
    try:
        response = client.rpc(name, params).execute()
        return response.data
    except Exception as exc:
        return exc


def main() -> int:
    account_id = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ACCOUNT_ID
    company_id = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_COMPANY_ID
    from_date = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_FROM
    to_date = sys.argv[4] if len(sys.argv) > 4 else DEFAULT_TO

    print("=" * 74)
    print(f"AUDIT :: ledger_accounts.id={account_id} (company_id={company_id})")
    print(f"Date window: {from_date} .. {to_date}")
    print("=" * 74)

    from sync_service import get_supabase_client

    client = get_supabase_client()
    if client is None:
        print("get_supabase_client() returned None. Check .env.")
        return 2

    account_rows = (
        client.table("ledger_accounts")
        .select("*")
        .eq("id", account_id)
        .limit(1)
        .execute()
        .data
        or []
    )

    if not account_rows:
        print(f"No ledger_accounts row with id={account_id}.")
        return 1

    row = account_rows[0]
    print("--- Raw row ---")
    print(json.dumps(row, default=str, indent=2))
    print()
    print("--- Column types ---")
    for key in ("id", "company_id", "account_name", "account_type",
                "is_active", "is_system", "opening_balance",
                "opening_balance_type", "group_name"):
        if key in row:
            print(f"  {key:20}: {_describe(row[key])}")
    print()

    is_active_raw = row.get("is_active")
    print("--- Filter outcomes ---")
    print(f"  is_active raw value             : {_describe(is_active_raw)}")

    strict_pass = is_active_raw == 1 or is_active_raw is True
    print(f"  Desktop `is_active = 1`         : {'PASS' if strict_pass else 'FAIL'}")

    default_pass = "is_active" not in row or is_active_raw is None
    print(f"  Bridge NULL -> SQLite DEFAULT 1 : {'PASS (falls through to default 1)' if default_pass else 'not triggered'}")

    rpc_result = _run_rpc(
        client,
        "is_row_active",
        {"v": None if is_active_raw is None else str(is_active_raw)},
    )
    if isinstance(rpc_result, Exception):
        print(f"  is_row_active(...) RPC          : ERROR - {rpc_result}")
    else:
        print(f"  is_row_active({is_active_raw!r})      : returns {rpc_result}")

    print()
    print("--- Distinct is_active storage across the company ---")
    scan_rows = (
        client.table("ledger_accounts")
        .select("is_active")
        .eq("company_id", company_id)
        .limit(5000)
        .execute()
        .data
        or []
    )
    buckets: dict[str, int] = {}
    for scan in scan_rows:
        key = f"{type(scan.get('is_active')).__name__} :: {scan.get('is_active')!r}"
        buckets[key] = buckets.get(key, 0) + 1
    if not buckets:
        print("  (no accounts for this company)")
    else:
        for key, count in sorted(buckets.items(), key=lambda kv: -kv[1]):
            print(f"  {count:5d}  {key}")

    print()
    print("--- Trial Balance rows returned by f_trial_balance ---")
    tb_data = _run_rpc(
        client,
        "f_trial_balance",
        {
            "p_company_id": company_id,
            "p_from_date": from_date,
            "p_to_date": to_date,
            "p_account_type": "All",
            "p_search": None,
        },
    )
    if isinstance(tb_data, Exception):
        print(f"  ERROR: {tb_data}")
    else:
        matches = [row for row in tb_data if int(row.get("account_id") or 0) == account_id]
        print(f"  total rows returned  : {len(tb_data)}")
        print(f"  account_id={account_id} present in RPC output: {'YES' if matches else 'NO'}")
        if matches:
            print(json.dumps(matches[0], default=str, indent=2))

    print()
    print("--- Ledger entries touching this account in window ---")
    entries = (
        client.table("ledger_entries")
        .select("id,voucher_date,voucher_type,debit,credit")
        .eq("company_id", company_id)
        .eq("account_id", account_id)
        .gte("voucher_date", from_date)
        .lte("voucher_date", to_date)
        .limit(20)
        .execute()
        .data
        or []
    )
    print(f"  entries in window (sample <=20): {len(entries)}")
    for entry in entries[:5]:
        print(f"    {entry}")

    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
