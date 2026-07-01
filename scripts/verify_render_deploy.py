#!/usr/bin/env python3
"""Smoke-test a deployed BIZORA mobile API (Render or any public URL)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DEFAULT_BASE = (
    (os.getenv("MOBILE_PUBLIC_URL") or "").strip()
    or (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    or "https://bizora-mobile.onrender.com"
).rstrip("/")

COMPANY_ID = int(os.getenv("MOBILE_COMPANY_ID") or os.getenv("QA_COMPANY_ID") or 25)
FROM_DATE = os.getenv("QA_FROM_DATE") or "2024-04-01"
TO_DATE = os.getenv("QA_TO_DATE") or "2026-06-30"


def _post(path: str, body: dict[str, object]) -> tuple[int, dict[str, object]]:
    """POST JSON to one API path and return status + parsed body."""
    request = urllib.request.Request(
        f"{DEFAULT_BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Bizora-Company-Id": str(COMPANY_ID),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return int(response.status), payload
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"detail": exc.reason}
        return int(exc.code), payload


def _get(path: str) -> tuple[int, dict[str, object]]:
    """GET one API path and return status + parsed body."""
    request = urllib.request.Request(f"{DEFAULT_BASE}{path}", method="GET")
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return int(response.status), payload


def main() -> int:
    print("=" * 72)
    print("BIZORA deployed API verification")
    print("=" * 72)
    print(f"base_url     : {DEFAULT_BASE}")
    print(f"company_id   : {COMPANY_ID}")
    print(f"date range   : {FROM_DATE} .. {TO_DATE}")
    print("-" * 72)

    failures = 0
    status_code, status_payload = _get("/api/status")
    data_source = str(status_payload.get("data_source") or "")
    ok = status_code == 200 and data_source == "supabase"
    print(f"{'PASS' if ok else 'FAIL'}  /api/status -> data_source={data_source!r}")
    if not ok:
        failures += 1

    filters = {
        "from_date": FROM_DATE,
        "to_date": TO_DATE,
        "ledger_view": "General",
        "account_type": "All",
    }
    checks = [
        ("cash-book", "/api/reports/cash-book/run"),
        ("trial-balance", "/api/reports/trial-balance/run"),
        ("day-book", "/api/reports/day-book/run"),
        ("ledger", "/api/reports/ledger/run"),
    ]
    for slug, legacy_path in checks:
        status_code, payload = _post(legacy_path, {"filters": filters})
        success = bool(payload.get("success"))
        rows = len(payload.get("rows") or [])
        message = str(payload.get("message") or "")[:90]
        bridge_blocked = "SQLite hydration bridge is disabled" in message
        ok = status_code == 200 and success and rows > 0
        label = "PASS" if ok else "FAIL"
        print(f"{label}  {slug:14} rows={rows:4} http={status_code} {message}")
        if bridge_blocked:
            print(
                "       ^ Deploy is still on OLD code. Push latest main to GitHub "
                "and redeploy Render."
            )
        if not ok:
            failures += 1

    print("-" * 72)
    print(f"Failures: {failures}")
    if failures:
        print(
            "Fix: commit local changes, git push origin main, wait for Render "
            "deploy to finish, then run this script again."
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
