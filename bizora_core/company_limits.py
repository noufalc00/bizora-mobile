"""
Company registry limits for normal and secret company pools.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing

from config import (
    COMPANY_VISIBILITY_NORMAL,
    COMPANY_VISIBILITY_SECRET,
    MAX_NORMAL_COMPANIES,
    MAX_SECRET_COMPANIES,
)


def normalize_company_visibility(value: str | None) -> str:
    """Return a canonical visibility slug for registry rows."""
    visibility = (value or COMPANY_VISIBILITY_NORMAL).strip().lower()
    if visibility == COMPANY_VISIBILITY_SECRET:
        return COMPANY_VISIBILITY_SECRET
    return COMPANY_VISIBILITY_NORMAL


def is_secret_company(company_data: dict | None) -> bool:
    """Return True when a company row belongs to the secret registry pool."""
    if not company_data:
        return False
    return normalize_company_visibility(company_data.get("visibility")) == COMPANY_VISIBILITY_SECRET


def count_companies(db_path: str, visibility: str = COMPANY_VISIBILITY_NORMAL) -> int:
    """Count registry rows for one visibility pool."""
    if not db_path:
        return 0
    pool = normalize_company_visibility(visibility)
    try:
        with closing(sqlite3.connect(db_path, timeout=30.0)) as connection:
            connection.execute("PRAGMA busy_timeout = 5000;")
            with closing(connection.cursor()) as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(id)
                    FROM companies
                    WHERE COALESCE(visibility, ?) = ?
                    """,
                    (COMPANY_VISIBILITY_NORMAL, pool),
                )
                row = cursor.fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error as error:
        print(f"[COMPANY LIMITS] Count failed for '{pool}': {error}")
        return MAX_NORMAL_COMPANIES if pool == COMPANY_VISIBILITY_NORMAL else MAX_SECRET_COMPANIES


def company_limit_reached(
    db_path: str,
    visibility: str = COMPANY_VISIBILITY_NORMAL,
) -> bool:
    """Return True when a visibility pool has reached its configured cap."""
    pool = normalize_company_visibility(visibility)
    current_count = count_companies(db_path, pool)
    if pool == COMPANY_VISIBILITY_SECRET:
        return current_count >= MAX_SECRET_COMPANIES
    return current_count >= MAX_NORMAL_COMPANIES


def company_limit_message(visibility: str = COMPANY_VISIBILITY_NORMAL) -> str:
    """Return a user-facing limit message for one company pool."""
    pool = normalize_company_visibility(visibility)
    if pool == COMPANY_VISIBILITY_SECRET:
        return (
            "Secret company limit reached. "
            f"You cannot create more than {MAX_SECRET_COMPANIES} secret companies."
        )
    return (
        "System limit reached. "
        f"You cannot create more than {MAX_NORMAL_COMPANIES} companies in this version."
    )
