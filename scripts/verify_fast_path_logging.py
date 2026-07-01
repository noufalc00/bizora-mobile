#!/usr/bin/env python3
"""
Exercise every RPC failure category to prove the new logging emits
the right classification tag for each one.

For each simulated failure this script constructs an exception that
mimics what supabase-py / httpx would raise, runs it through
`_classify_rpc_error` + `_describe_rpc_failure`, and prints the log line
that `_call_rpc` would produce. Additionally invokes `try_run_fast_report`
with a stub client that raises the exception so you can see the
outer log line too.

Run:
    python scripts/verify_fast_path_logging.py
"""

from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _APIError(Exception):
    """Mimic supabase-py's postgrest.exceptions.APIError shape."""

    def __init__(self, payload: dict):
        super().__init__(payload)
        for key, value in payload.items():
            setattr(self, key, value)


class _HttpxResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _HttpError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.response = _HttpxResponse(status_code)


class _RaisingClient:
    """Stub Supabase client whose `.rpc(...).execute()` always raises."""

    def __init__(self, exc: BaseException):
        self._exc = exc

    def rpc(self, *_args, **_kwargs):
        return self

    def execute(self):
        raise self._exc


SCENARIOS = [
    (
        "TIMEOUT",
        TimeoutError("request timed out after 30s"),
    ),
    (
        "UNAUTHORIZED (401)",
        _APIError({"code": None, "message": "Invalid API key", "status": 401}),
    ),
    (
        "UNAUTHORIZED (JWT)",
        _APIError({"code": "PGRST301", "message": "JWT expired"}),
    ),
    (
        "FORBIDDEN (RLS)",
        _APIError(
            {"code": "42501", "message": "new row violates row-level security policy"}
        ),
    ),
    (
        "NOT_INSTALLED (PGRST202)",
        _APIError({"code": "PGRST202", "message": "Could not find the function"}),
    ),
    (
        "DB_ERROR (5xx)",
        _HttpError("Internal Server Error", 500),
    ),
    (
        "DB_ERROR (SQLSTATE)",
        _APIError(
            {"code": "42P01", "message": "relation \"missing_table\" does not exist"}
        ),
    ),
    (
        "DB_ERROR (structure mismatch)",
        _APIError(
            {
                "code": "42804",
                "message": "structure of query does not match function result type",
            }
        ),
    ),
    (
        "NETWORK (connection refused)",
        ConnectionError("connection refused"),
    ),
    (
        "UNKNOWN (weird)",
        RuntimeError("something we've never seen before"),
    ),
]


def main() -> int:
    from bizora_core.mobile_supabase_fast_reports import (
        _classify_rpc_error,
        _describe_rpc_failure,
        try_run_fast_report,
    )

    print("=" * 78)
    print("RPC failure classification matrix")
    print("=" * 78)
    for label, exc in SCENARIOS:
        category = _classify_rpc_error(exc)
        detail = _describe_rpc_failure("f_trial_balance", {"p_company_id": 25}, exc)
        marker = "OK  " if category == label.split()[0] or label.startswith(category) else "??  "
        print(f"{marker} {label:34} -> category={category}")
        print(f"        {detail}")
        print()

    print("=" * 78)
    print("try_run_fast_report end-to-end (captured stdout + log)")
    print("=" * 78)
    for label, exc in SCENARIOS:
        buf = io.StringIO()
        client_factory = lambda e=exc: _RaisingClient(e)
        with redirect_stdout(buf):
            result = try_run_fast_report(
                client_factory,
                "trial-balance",
                25,
                {"from_date": "2024-04-01", "to_date": "2026-06-30"},
            )
        print(f"[{label}] result={result}")
        for line in buf.getvalue().splitlines():
            print(f"    {line}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
