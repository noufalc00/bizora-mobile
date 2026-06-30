#!/usr/bin/env python3
"""Compatibility wrapper. Use commercial calculation engine test."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.test_commercial_calculation_engine import run

if __name__ == "__main__":
    raise SystemExit(run())
