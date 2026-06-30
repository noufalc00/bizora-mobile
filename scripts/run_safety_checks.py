"""
Run UI regression safety checks after any page or theme change.

Default (fast, ~3-8 min):
    python scripts/run_safety_checks.py

Full audit before release (~10-20 min):
    python scripts/run_safety_checks.py --full

Linked flows only (quickest):
    python scripts/run_safety_checks.py --linked-only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _run_step(name: str, script: str, extra_args: list[str] | None = None) -> int:
    """Run one safety script and print a clear section header."""
    args = extra_args or []
    command = [PYTHON, str(ROOT / "scripts" / script), *args]
    print(f"\n{'=' * 60}", flush=True)
    print(f"STEP: {name}", flush=True)
    print(f"CMD:  {' '.join(command)}", flush=True)
    print("=" * 60, flush=True)
    result = subprocess.run(command, cwd=str(ROOT))
    return int(result.returncode)


def main() -> int:
    """Execute the configured safety-check pipeline."""
    parser = argparse.ArgumentParser(description="Faizan Pro UI regression safety checks")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run the slower audit_page_open.py full page audit",
    )
    parser.add_argument(
        "--linked-only",
        action="store_true",
        help="Run only cross-page linked-flow smoke tests",
    )
    parser.add_argument(
        "--skip-linked",
        action="store_true",
        help="Skip linked-flow smoke tests",
    )
    args = parser.parse_args()

    steps: list[tuple[str, int]] = []

    if not args.skip_linked:
        code = _run_step("Linked cross-page flows", "smoke_linked_flows.py")
        steps.append(("Linked flows", code))
        if code != 0:
            print("\n[SAFETY] Stopping early: fix linked-flow failures first.")
            return code

    code = _run_step("Completer popup theme audit", "audit_completer_theme.py")
    steps.append(("Completer theme audit", code))
    if code != 0:
        print("\n[SAFETY] Completer popup theme audit failed.")
        return code

    if args.linked_only:
        return 0

    code = _run_step("Fast page open audit", "audit_pages_fast.py")
    steps.append(("Fast page audit", code))
    if code != 0:
        print("\n[SAFETY] Fast page audit failed.")
        return code

    if args.full:
        code = _run_step("Full page open audit", "audit_page_open.py")
        steps.append(("Full page audit", code))
        if code != 0:
            return code

    print("\n" + "=" * 60)
    print("ALL SAFETY CHECKS PASSED")
    for name, code in steps:
        print(f"  - {name}: OK")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
