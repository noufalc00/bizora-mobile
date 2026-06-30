"""
Audit trail persistence helpers.

This module records human-readable accounting actions without owning caller
transactions unless it opened the database connection itself.
"""

import logging
from datetime import datetime
from typing import Optional

from db import Database


LOGGER = logging.getLogger(__name__)
VALID_ACTION_TYPES = {"CREATE", "UPDATE", "DELETE"}


def _placeholder_for_connection(conn) -> str:
    """Return the parameter placeholder matching the active connection."""
    module_name = conn.__class__.__module__.lower()
    if "mysql" in module_name:
        return "%s"
    return "?"


def log_action(company_id: int, user_id: Optional[int], module: str,
               action_type: str, reference_id: str, description: str,
               conn=None, cursor=None) -> bool:
    """Insert one audit trail row and return whether it succeeded.

    Args:
        company_id: Company that owns the audited action.
        user_id: Optional user identifier; pass None when unavailable.
        module: Human-readable module name such as Sales or Journal.
        action_type: One of CREATE, UPDATE, or DELETE.
        reference_id: Voucher or document number visible to the user.
        description: Exact human-readable action details.
        conn: Optional caller-owned database connection. When provided, this
            function does not commit, rollback, or close the connection.
        cursor: Optional caller-owned cursor. When provided, this function
            reuses the active transaction cursor and does not close it.

    Returns:
        True when the audit row was inserted, otherwise False.
    """
    normalized_action = str(action_type or "").upper()
    if normalized_action not in VALID_ACTION_TYPES:
        LOGGER.error("Audit log rejected invalid action_type: %s", action_type)
        return False

    owns_connection = conn is None
    db = None
    owns_cursor = cursor is None
    try:
        if owns_connection:
            db = Database()
            conn = db.connect()
            placeholder = db._get_placeholder()
        else:
            placeholder = _placeholder_for_connection(conn)

        action_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if cursor is None:
            cursor = conn.cursor()
        cursor.execute(
            f"""
            INSERT INTO audit_logs
                (company_id, user_id, action_date, module, action_type,
                 reference_id, description)
            VALUES
                ({placeholder}, {placeholder}, {placeholder}, {placeholder},
                 {placeholder}, {placeholder}, {placeholder})
            """,
            (
                company_id,
                user_id,
                action_date,
                module,
                normalized_action,
                reference_id,
                description,
            ),
        )

        if owns_connection:
            conn.commit()
        return True
    except Exception as exc:
        LOGGER.exception("Audit log database error: %s", exc)
        if owns_connection and conn is not None:
            try:
                conn.rollback()
            except Exception as rollback_exc:
                LOGGER.exception("Audit log rollback error: %s", rollback_exc)
        return False
    finally:
        if owns_cursor and cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if owns_connection and db is not None:
            db.force_disconnect()
