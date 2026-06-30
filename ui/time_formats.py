"""
Central time display helpers and global 12/24-hour preference storage.
"""

from __future__ import annotations

import os
from contextlib import closing
from datetime import datetime
from typing import Optional

TIME_FORMAT_SETTING_KEY = "app_time_format"
TIME_FORMAT_12H = "12"
TIME_FORMAT_24H = "24"
DEFAULT_TIME_FORMAT = TIME_FORMAT_12H
VALID_TIME_FORMATS = frozenset({TIME_FORMAT_12H, TIME_FORMAT_24H})


def normalize_time_format(value: object) -> str:
    """Normalize saved or user-facing values to a supported time format key."""
    normalized = str(value or "").strip().lower()
    if normalized in {"12", "12h", "12hr", "12 hour", "12-hour", "ampm", "am/pm"}:
        return TIME_FORMAT_12H
    if normalized in {"24", "24h", "24hr", "24 hour", "24-hour"}:
        return TIME_FORMAT_24H
    if normalized in VALID_TIME_FORMATS:
        return normalized
    return DEFAULT_TIME_FORMAT


def get_time_format_preference(master_db_path: str | None = None) -> str:
    """Read the saved 12/24-hour preference from the master global_settings table."""
    from utils.theme_manager import ThemeManager

    resolved_path = ThemeManager.resolve_master_db_path(master_db_path)
    if not resolved_path or not os.path.isfile(resolved_path):
        return DEFAULT_TIME_FORMAT

    try:
        with closing(ThemeManager._connect(resolved_path)) as connection:
            ThemeManager._ensure_global_settings_table(connection)
            row = connection.execute(
                """
                SELECT setting_value
                FROM global_settings
                WHERE setting_key = ?
                """,
                (TIME_FORMAT_SETTING_KEY,),
            ).fetchone()
            if row:
                return normalize_time_format(row[0])
    except Exception as exc:
        print(f"Error loading time format preference: {exc}")

    return DEFAULT_TIME_FORMAT


def save_time_format_preference(master_db_path: str | None, time_format: str) -> bool:
    """Persist the global 12/24-hour preference in global_settings."""
    from utils.theme_manager import ThemeManager

    normalized = normalize_time_format(time_format)
    resolved_path = ThemeManager.resolve_master_db_path(master_db_path)
    if not resolved_path:
        print("Master database path is required to save time format preference.")
        return False

    db_dir = os.path.dirname(os.path.abspath(resolved_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    try:
        with closing(ThemeManager._connect(resolved_path)) as connection:
            ThemeManager._ensure_global_settings_table(connection)
            connection.execute(
                """
                INSERT INTO global_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (TIME_FORMAT_SETTING_KEY, normalized),
            )
            connection.commit()
        return True
    except Exception as exc:
        print(f"Error saving time format preference: {exc}")
        return False


def format_display_time(
    value: Optional[datetime] = None,
    *,
    time_format: str | None = None,
    master_db_path: str | None = None,
    include_seconds: bool = False,
) -> str:
    """Format a datetime using the saved or explicit 12/24-hour preference."""
    moment = value or datetime.now()
    resolved_format = normalize_time_format(
        time_format or get_time_format_preference(master_db_path)
    )
    if resolved_format == TIME_FORMAT_24H:
        pattern = "%H:%M:%S" if include_seconds else "%H:%M"
        return moment.strftime(pattern)

    hour = moment.hour % 12 or 12
    if include_seconds:
        return f"{hour}:{moment.strftime('%M:%S %p')}"
    return f"{hour}:{moment.strftime('%M %p')}"
