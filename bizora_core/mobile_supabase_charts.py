"""
Dashboard chart series for Supabase-backed mobile web.

Matches desktop DashboardLogic month labels (e.g. Jan 25) and voided exclusion.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

_MONTH_LABELS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_DASHBOARD_CHART_MONTH_COUNT = 6


def build_month_window(month_count: int = _DASHBOARD_CHART_MONTH_COUNT) -> tuple[list[str], list[tuple[int, int]]]:
    """Build display labels and (year, month) keys for the last N months."""
    today = date.today()
    labels: list[str] = []
    keys: list[tuple[int, int]] = []
    year = today.year
    month = today.month

    for offset in range(month_count - 1, -1, -1):
        target_month = month - offset
        target_year = year
        while target_month <= 0:
            target_month += 12
            target_year -= 1
        labels.append(f"{_MONTH_LABELS[target_month - 1]} {str(target_year)[-2:]}")
        keys.append((target_year, target_month))

    return labels, keys


def build_monthly_chart_series(
    rows: Iterable[Mapping[str, Any]],
    *,
    date_column: str,
    amount_column: str = "grand_total",
    month_count: int = _DASHBOARD_CHART_MONTH_COUNT,
) -> list[dict[str, Any]]:
    """Aggregate voucher rows into desktop-style monthly chart buckets."""
    labels, month_keys = build_month_window(month_count)
    if not month_keys:
        return []

    start_year, start_month = month_keys[0]
    start_date = date(start_year, start_month, 1)
    totals_by_key: dict[tuple[int, int], float] = {key: 0.0 for key in month_keys}

    for row in rows:
        if str(row.get("status") or "Active").lower() == "voided":
            continue
        parsed = _parse_row_month(row.get(date_column))
        if parsed is None or parsed < start_date:
            continue
        key = (parsed.year, parsed.month)
        if key not in totals_by_key:
            continue
        totals_by_key[key] += float(row.get(amount_column) or 0.0)

    return [
        {
            "label": label,
            "year": year,
            "month": month,
            "total": round(totals_by_key.get((year, month), 0.0), 2),
        }
        for label, (year, month) in zip(labels, month_keys)
    ]


def _parse_row_month(value: Any) -> date | None:
    """Parse a voucher date column into a calendar date."""
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
