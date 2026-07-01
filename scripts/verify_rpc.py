#!/usr/bin/env python3
"""
Standalone RPC verification: only touches Supabase, never triggers any
schema migrations or heavy imports.

Prints the environment (URL, project ref, key fingerprint), then pings
each fast-path RPC (f_trial_balance, f_monthly_analysis,
f_trial_balance_debug, f_day_book_entries) and reports the exact
response so we can distinguish "not installed" from "installed but
broken" from "installed and returning rows".
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()

COMPANY_ID = int(os.getenv("MOBILE_COMPANY_ID") or 25)
FROM_DATE = os.getenv("QA_FROM_DATE") or "2024-04-01"
TO_DATE = os.getenv("QA_TO_DATE") or "2026-06-30"


def _fingerprint(secret: str | None) -> str:
    """Return a short SHA-256 prefix so we can identify a key without leaking it."""
    if not secret:
        return "(missing)"
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"{digest[:12]} ({len(secret)} chars)"


def _project_ref(url: str | None) -> str:
    """Extract the Supabase project ref from a project URL for a quick eye-check."""
    if not url:
        return "(missing)"
    stripped = url.replace("https://", "").replace("http://", "")
    return stripped.split(".")[0]


def _summarize(response_or_exc: Any) -> str:
    """One-line description of what came back from the RPC call."""
    if isinstance(response_or_exc, Exception):
        text = str(response_or_exc)
        if "PGRST202" in text or "Could not find the function" in text:
            return "MISSING (not installed on this project)"
        return f"ERROR: {text[:140]}"
    rows = response_or_exc.data or []
    example = json.dumps(rows[0], default=str)[:140] if rows else "(empty)"
    return f"INSTALLED, {len(rows)} row(s), first={example}"


def main() -> int:
    url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    service_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SERVICE_KEY")

    print("=" * 72)
    print("Supabase RPC verification (no migrations, no bridge)")
    print("=" * 72)
    print(f"SUPABASE_URL           : {url or '(missing)'}")
    print(f"project ref            : {_project_ref(url)}")
    print(f"anon key fingerprint   : {_fingerprint(anon_key)}")
    print(f"service key fingerprint: {_fingerprint(service_key)}")
    print(f"MOBILE_COMPANY_ID      : {COMPANY_ID}")
    print(f"date range             : {FROM_DATE} .. {TO_DATE}")
    print("-" * 72)

    if not url:
        print("SUPABASE_URL is empty; abort. Check .env in the repo root.")
        return 2

    from sync_service import get_supabase_client

    client = get_supabase_client()
    if client is None:
        print("get_supabase_client() returned None; check SUPABASE_URL/key envs.")
        return 2

    ping_specs = [
        (
            "f_trial_balance",
            {
                "p_company_id": COMPANY_ID,
                "p_from_date": FROM_DATE,
                "p_to_date": TO_DATE,
                "p_account_type": "All",
                "p_search": None,
            },
        ),
        (
            "f_monthly_analysis",
            {"p_company_id": COMPANY_ID, "p_from_date": FROM_DATE, "p_to_date": TO_DATE},
        ),
        (
            "f_trial_balance_debug",
            {"p_company_id": COMPANY_ID, "p_from_date": FROM_DATE, "p_to_date": TO_DATE},
        ),
        (
            "f_day_book_entries",
            {"p_company_id": COMPANY_ID, "p_from_date": FROM_DATE, "p_to_date": TO_DATE},
        ),
    ]

    failed = 0
    for name, params in ping_specs:
        try:
            response = client.rpc(name, params).execute()
            outcome = _summarize(response)
        except Exception as exc:
            outcome = _summarize(exc)
            failed += 1 if "MISSING" not in outcome else 0
        print(f"{name:26}: {outcome}")

    print("-" * 72)
    print("Done.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
