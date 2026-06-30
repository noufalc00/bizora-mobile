"""Shared helpers for optional print-time display on invoice bills."""

from __future__ import annotations

from typing import Any, Mapping

PRINT_TIME_KEY = "print_time"
A4_PRINT_TIME_KEY = "a4_print_time"


def _saved_bool(value: Any) -> bool:
    """Return a boolean from saved print-setting values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "checked"}


def print_time_enabled(settings: Mapping[str, Any], *keys: str, default: bool = False) -> bool:
    """Resolve whether print time is enabled from one or more setting keys."""
    for key in keys:
        if key in settings:
            return _saved_bool(settings.get(key))
    return default


def current_print_time_text(master_db_path: str | None = None) -> str:
    """Return the current local time formatted for bill printing."""
    from ui.time_formats import format_display_time

    return format_display_time(master_db_path=master_db_path)


def append_print_time_to_date(date_value: Any, *, include_time: bool) -> str:
    """Append the current print time to a bill date string when enabled."""
    date_text = "" if date_value is None else str(date_value).strip()
    if not include_time:
        return date_text
    time_text = current_print_time_text()
    if date_text:
        return f"{date_text} {time_text}"
    return time_text
