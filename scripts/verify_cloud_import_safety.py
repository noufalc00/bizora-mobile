#!/usr/bin/env python3
"""
Simulate the cloud environment by blocking `db` (and MobileWebService)
from importing, then confirm that:

    1. `import bizora_core.mobile_supabase_desktop_bridge` still succeeds
       (module scope must never touch the desktop `db` module).
    2. `run_report_via_desktop_bridge(...)` returns a graceful
       `success=False` payload with `bridge_available=False` instead of
       crashing the worker.

This is exactly the failure mode described in the incident:

    ModuleNotFoundError: No module named 'db'

Run:
    python scripts/verify_cloud_import_safety.py
"""

from __future__ import annotations

import os
import sys
import importlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _BlockedImport:
    """A meta-path finder that pretends specific top-level modules do not exist."""

    def __init__(self, blocked: set[str]) -> None:
        self._blocked = blocked

    def find_module(self, fullname: str, path=None):  # noqa: D401 - meta finder API
        if fullname.split(".", 1)[0] in self._blocked:
            return self
        return None

    def find_spec(self, fullname: str, path=None, target=None):  # noqa: D401
        if fullname.split(".", 1)[0] in self._blocked:
            raise ModuleNotFoundError(f"cloud simulation: '{fullname}' is unavailable")
        return None


def main() -> int:
    print("=" * 70)
    print("Cloud simulation: block 'db' + evict bridge module")
    print("=" * 70)

    for module_name in list(sys.modules.keys()):
        if module_name == "db" or module_name.startswith("db."):
            sys.modules.pop(module_name, None)
        if module_name.startswith("bizora_core.mobile_supabase_desktop_bridge"):
            sys.modules.pop(module_name, None)
        if module_name.startswith("bizora_core.mobile_web_service"):
            sys.modules.pop(module_name, None)

    blocker = _BlockedImport({"db", "bizora_core.mobile_web_service"})
    sys.meta_path.insert(0, blocker)

    try:
        bridge = importlib.import_module("bizora_core.mobile_supabase_desktop_bridge")
        print(f"  ok: bridge module imported without touching `db`")
    except Exception as exc:
        print(f"  FAIL: bridge failed to import: {exc}")
        return 1

    class _StubService:
        def resolve_company_id(self, cid):
            return cid or 25

    result = bridge.run_report_via_desktop_bridge(
        _StubService(),
        "trial-balance",
        {"from_date": "2024-04-01", "to_date": "2026-06-30"},
        25,
    )
    ok = (
        isinstance(result, dict)
        and result.get("success") is False
        and result.get("bridge_available") is False
    )
    print()
    print("  bridge run result: ", {k: result.get(k) for k in ("success", "message", "bridge_available", "data_source", "rows")})
    print()

    if ok:
        print("PASS: cloud-safe fallback (no ModuleNotFoundError raised)")
        return 0
    print("FAIL: bridge did not gracefully signal unavailability")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
