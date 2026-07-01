#!/usr/bin/env python3
"""
Diagnose why f_monthly_analysis returns zero buckets for company 25.

Prints:
  1. Full response from f_monthly_analysis for FY 2026-27.
  2. v_ledger_monthly_totals rows for the same company/window (income + expense).
  3. Which desktop-side accounts drove the bridge total for May 2026.

Run:
    python scripts/diagnose_monthly_analysis.py
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

COMPANY_ID = int(os.getenv("MOBILE_COMPANY_ID") or 25)
FROM_DATE = "2026-04-01"
TO_DATE = "2027-03-31"


def main() -> int:
    from sync_service import get_supabase_client

    client = get_supabase_client()

    print("=" * 74)
    print("1. RPC f_monthly_analysis (FY 2026-27, all rows)")
    print("=" * 74)
    try:
        rpc = client.rpc(
            "f_monthly_analysis",
            {"p_company_id": COMPANY_ID, "p_from_date": FROM_DATE, "p_to_date": TO_DATE},
        ).execute()
        rpc_rows = rpc.data or []
        print(f"  rows returned: {len(rpc_rows)}")
        for row in rpc_rows:
            print(json.dumps(row, default=str, indent=2))
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print()
    print("=" * 74)
    print("2. v_ledger_monthly_totals for the same company/window")
    print("=" * 74)
    try:
        view = (
            client.table("v_ledger_monthly_totals")
            .select("account_id,account_name,account_type,group_name,fy_year,fy_month,debit_total,credit_total,signed_impact")
            .eq("company_id", COMPANY_ID)
            .in_("account_type", ["income", "expense", "Income", "Expense"])
            .gte("fy_year", 2026)
            .limit(200)
            .execute()
        )
        rows = view.data or []
        print(f"  rows returned: {len(rows)}")
        for row in rows:
            print(f"  {row.get('fy_year')}-{row.get('fy_month'):02d} | "
                  f"acc={row.get('account_id')} '{row.get('account_name')}' "
                  f"type={row.get('account_type')} group='{row.get('group_name')}' | "
                  f"dr={row.get('debit_total')} cr={row.get('credit_total')} signed={row.get('signed_impact')}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print()
    print("=" * 74)
    print("3. All income/expense accounts for company 25 (from ledger_accounts)")
    print("=" * 74)
    try:
        accs = (
            client.table("ledger_accounts")
            .select("id,account_name,account_type,group_name,is_active")
            .eq("company_id", COMPANY_ID)
            .in_("account_type", ["income", "expense", "Income", "Expense"])
            .limit(200)
            .execute()
        )
        rows = accs.data or []
        print(f"  rows returned: {len(rows)}")
        for row in rows:
            print(f"  id={row.get('id')} '{row.get('account_name')}' "
                  f"type='{row.get('account_type')}' group='{row.get('group_name')}' "
                  f"active={row.get('is_active')}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print()
    print("=" * 74)
    print("4. Sample ledger_entries in May 2026 that hit income/expense accounts")
    print("=" * 74)
    try:
        entries = (
            client.table("ledger_entries")
            .select("id,account_id,voucher_type,voucher_date,debit,credit")
            .eq("company_id", COMPANY_ID)
            .gte("voucher_date", "2026-05-01")
            .lte("voucher_date", "2026-05-31")
            .limit(500)
            .execute()
        )
        rows = entries.data or []
        income_ids = {a["id"] for a in (accs.data or [])}
        touched = [r for r in rows if r.get("account_id") in income_ids]
        print(f"  entries in May 2026 total: {len(rows)}")
        print(f"  entries hitting income/expense accounts: {len(touched)}")
        for row in touched[:15]:
            print(f"  {row}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
