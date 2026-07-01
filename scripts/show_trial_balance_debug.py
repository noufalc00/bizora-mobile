#!/usr/bin/env python3
"""One-shot helper: prints f_trial_balance_debug funnel counts."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

from bizora_core.mobile_supabase_service import MobileSupabaseService


def main() -> int:
    svc = MobileSupabaseService()
    try:
        response = svc._client().rpc(
            "f_trial_balance_debug",
            {"p_company_id": 25, "p_from_date": "2024-04-01", "p_to_date": "2026-06-30"},
        ).execute()
    except Exception as exc:
        print(f"RPC error: {exc}")
        return 1

    rows = response.data or []
    print(f"{'stage':45}  {'count':>7}  example")
    print("-" * 100)
    for row in rows:
        example = json.dumps(row.get("example_json") or {}, default=str)[:60]
        print(f"{row['stage']:45}  {row['row_count']:>7}  {example}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
