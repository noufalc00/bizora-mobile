#!/usr/bin/env python3
"""
Exercise every fast-path dispatch branch and print the two DEBUG lines
that will appear in Render/uvicorn logs, so we can confirm:

  1. `DEBUG: Fast-Path Check -> ...`  shows env flags + SERVICE_ACTIVE.
  2. `DEBUG: Falling back to Bridge ...`  fires with the correct
     `bridge_reason=` tag (or is suppressed on the happy path).

Scenarios covered:
    A. Happy path: SUPABASE_URL set, RPC installed, mapped slug.
    B. Fast-path miss (RPC error): mapped slug, service raises.
    C. Slug not on fast-path allow list: unmapped slug goes to bridge.
    D. No company id resolvable: dispatcher skips fast-path entirely.
    E. Missing SUPABASE_URL / SERVICE_KEY: SERVICE_ACTIVE=False in log.

The bridge module is monkey-patched to a no-op so we don't need Supabase
credentials to run this offline. This is purely a log-format sanity test.
"""

from __future__ import annotations

import io
import os
import sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _install_stubs() -> None:
    """Replace the bridge + fast-path with in-memory doubles.

    The doubles let us drive each branch without touching Supabase and
    without importing the desktop `db` module.
    """
    from bizora_core import mobile_supabase_desktop_bridge as bridge_mod
    from bizora_core import mobile_supabase_fast_reports as fast_mod

    def _stub_bridge(service, slug, filters, company_id):
        return {"success": True, "rows": [], "data_source": "stub_bridge"}

    bridge_mod.run_report_via_desktop_bridge = _stub_bridge

    def _stub_fast(client_factory, slug, company_id, filters):
        marker = os.environ.get("_STUB_FAST_RESULT", "hit")
        if marker == "hit":
            return {"success": True, "rows": [{"n": 1}], "data_source": "supabase_view"}
        if marker == "miss":
            return None
        if marker == "raise":
            raise RuntimeError("simulated RPC blow-up")
        return None

    fast_mod.try_run_fast_report = _stub_fast


def _run(label: str, env: dict[str, str], slug: str, stub_result: str,
         company_id_override) -> None:
    print("=" * 78)
    print(f"SCENARIO: {label}")
    print("=" * 78)

    for key in ("SUPABASE_URL", "SERVICE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY",
                "MOBILE_DATA_SOURCE", "_STUB_FAST_RESULT"):
        os.environ.pop(key, None)
    for key, value in env.items():
        os.environ[key] = value
    os.environ["_STUB_FAST_RESULT"] = stub_result

    from bizora_core.mobile_supabase_service import MobileSupabaseService
    from bizora_core.mobile_web_registry import get_route_definition

    if get_route_definition(slug) is None:
        print(f"  SKIP: slug '{slug}' is not a registered route in this build")
        print()
        return

    service = MobileSupabaseService()
    # Force resolve_company_id to return whatever the caller wants without
    # hitting Supabase.
    service.resolve_company_id = lambda override_id=None: company_id_override

    buf = io.StringIO()
    with redirect_stdout(buf):
        result = service.run_report(slug, {}, company_id=company_id_override)

    for line in buf.getvalue().splitlines():
        print(f"    {line}")
    print(f"    -> result.data_source = {result.get('data_source')!r}, "
          f"rows = {len(result.get('rows') or [])}")
    print()


def main() -> int:
    _install_stubs()

    _run(
        label="A. Happy path (fast-path returns a result)",
        env={
            "SUPABASE_URL": "https://example.supabase.co",
            "SERVICE_KEY": "sk_test_XXXXX",
            "MOBILE_DATA_SOURCE": "supabase",
        },
        slug="trial-balance",
        stub_result="hit",
        company_id_override=25,
    )

    _run(
        label="B. Fast-path miss (mapped slug, RPC returned None)",
        env={
            "SUPABASE_URL": "https://example.supabase.co",
            "SERVICE_KEY": "sk_test_XXXXX",
            "MOBILE_DATA_SOURCE": "supabase",
        },
        slug="trial-balance",
        stub_result="miss",
        company_id_override=25,
    )

    _run(
        label="C. Slug not on fast-path allow list",
        env={
            "SUPABASE_URL": "https://example.supabase.co",
            "SERVICE_KEY": "sk_test_XXXXX",
        },
        slug="day-book",  # not in FAST_PATH_HANDLERS
        stub_result="miss",
        company_id_override=25,
    )

    _run(
        label="D. No company id resolvable",
        env={
            "SUPABASE_URL": "https://example.supabase.co",
            "SERVICE_KEY": "sk_test_XXXXX",
        },
        slug="trial-balance",
        stub_result="miss",
        company_id_override=None,
    )

    _run(
        label="E. Missing SUPABASE_URL and SERVICE_KEY (SERVICE_ACTIVE=False)",
        env={},
        slug="trial-balance",
        stub_result="miss",
        company_id_override=25,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
