#!/usr/bin/env python3
"""Verify all Books/Reports routes via Supabase desktop bridge."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()
os.environ["MOBILE_DATA_SOURCE"] = "supabase"

from bizora_core.mobile_supabase_service import MobileSupabaseService
from bizora_core.mobile_web_registry import ROUTE_DEFINITIONS


def _resolve_ledger_account(svc, company_id):
    try:
        rows = svc._fetch_table("ledger_accounts", company_id, select="id", limit=1, order_col="id")
        if rows:
            return rows[0].get("id")
    except Exception:
        pass
    return None


DEFAULT_FILTERS = {
    "from_date": "2024-04-01",
    "to_date": "2026-06-30",
    "as_of_date": "2026-06-30",
    "report_mode": "Bill Wise",
    "summarize_entries": True,
    "ledger_view": "General",
}


def main() -> int:
    svc = MobileSupabaseService()
    company_id = 25
    account_id = _resolve_ledger_account(svc, company_id)
    failures = []
    for slug in sorted(ROUTE_DEFINITIONS):
        definition = ROUTE_DEFINITIONS[slug]
        filters = dict(DEFAULT_FILTERS)
        if definition.get("handler") == "sales_profit_book":
            filters["report_mode"] = "Bill Wise Profit"
        if slug == "ledger-statement" and account_id:
            filters["account_id"] = account_id
        try:
            result = svc.run_report(slug, filters, company_id=company_id)
            ok = bool(result.get("success"))
            rows = len(result.get("rows") or [])
            cols = len(result.get("columns") or [])
            status = "OK" if ok else "FAIL"
            print(f"{status:4} {slug:30} rows={rows:4} cols={cols:2} {result.get('message','')[:50]}")
            if not ok:
                failures.append(slug)
        except Exception as exc:
            print(f"ERR  {slug:30} {exc}")
            failures.append(slug)
    print("")
    print(f"Failed: {len(failures)} -> {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
