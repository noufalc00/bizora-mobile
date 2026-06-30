"""
Company-scoped invoice print settings for saved default print behavior.

The table is intentionally separate from company_settings so future invoice UI
can evolve without disturbing existing application preferences.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from typing import Any, Dict, Optional

from db import Database


LOGGER = logging.getLogger(__name__)

DEFAULT_PRINT_SETTINGS = {
    "default_format": "A4",
    "default_theme": "Classic",
    "printer_name": "",
    "printer_type": "Regular",
    "paper_size": "A4",
    "header_quote": "",
    "footer_terms": "Thank you for your business.",
    "layout_coordinates": "",
    "show_item_barcode": "0",
}


def _resolve_db_and_company(db_or_company_id: Any, company_id: Optional[int]) -> tuple:
    """Return a Database object and validated company id for flexible callers."""
    if company_id is None:
        return Database(), int(db_or_company_id)
    return db_or_company_id, int(company_id)


def ensure_print_settings_table(db: Database) -> None:
    """Ask the database layer to create print_settings when available."""
    try:
        if hasattr(db, "ensure_print_settings_table"):
            if not db.ensure_print_settings_table():
                raise sqlite3.Error("print_settings table could not be initialized")
    except sqlite3.Error as exc:
        print(f"Database Error: {exc}")
        LOGGER.exception("Print settings table ensure failed: %s", exc)
        raise
    except Exception as exc:
        LOGGER.exception("Print settings table ensure failed: %s", exc)
        raise


def _bool_text(value: Any) -> str:
    """Return a database-safe checkbox value as 1 or 0 text."""
    if isinstance(value, str):
        return "1" if value.strip().lower() in {"1", "true", "yes", "on"} else "0"
    return "1" if bool(value) else "0"


def _rollback_if_supported(db: Database) -> None:
    """Rollback an open transaction when the injected database supports it."""
    connection = getattr(db, "connection", None)
    rollback = getattr(connection, "rollback", None)
    if callable(rollback):
        rollback()


def _row_to_dict(cursor: Any, row: Any) -> Dict[str, Any]:
    """Convert a DB-API cursor row into a dictionary."""
    if row is None:
        return {}
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    columns = [column[0] for column in cursor.description or ()]
    return dict(zip(columns, row))


def get_print_settings(
    db_or_company_id: Any,
    company_id: Optional[int] = None,
) -> Dict[str, str]:
    """Return saved print settings for one company overlaid on defaults."""
    settings = dict(DEFAULT_PRINT_SETTINGS)
    settings["_print_settings_found"] = "0"
    try:
        db, resolved_company_id = _resolve_db_and_company(db_or_company_id, company_id)
    except (TypeError, ValueError) as exc:
        LOGGER.exception("Invalid print settings company id: %s", exc)
        return settings

    ensure_print_settings_table(db)
    ph = db._get_placeholder()
    conn = None
    try:
        conn = db.connect()
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                f"""
                SELECT
                    default_format,
                    default_theme,
                    printer_name,
                    printer_type,
                    paper_size,
                    header_quote,
                    footer_terms,
                    layout_coordinates,
                    show_item_barcode
                FROM print_settings
                WHERE company_id = {ph}
                """,
                (resolved_company_id,),
            )
            row = _row_to_dict(cursor, cursor.fetchone())
        if not row:
            return settings

        settings["_print_settings_found"] = "1"
        for key in settings:
            value = row.get(key)
            if value is not None:
                settings[key] = str(value)
    except sqlite3.Error as exc:
        print(f"Database Error: {exc}")
        LOGGER.exception("Print settings fetch failed: %s", exc)
        raise
    except Exception as exc:
        LOGGER.exception("Print settings fetch failed: %s", exc)
        raise
    finally:
        try:
            db.disconnect()
        except Exception as disconnect_exc:
            LOGGER.exception("Print settings disconnect failed: %s", disconnect_exc)
    return settings


def save_print_settings(
    db_or_company_id: Any,
    company_id: Optional[int] = None,
    default_format: str = DEFAULT_PRINT_SETTINGS["default_format"],
    default_theme: str = DEFAULT_PRINT_SETTINGS["default_theme"],
    printer_name: str = DEFAULT_PRINT_SETTINGS["printer_name"],
    printer_type: str = DEFAULT_PRINT_SETTINGS["printer_type"],
    paper_size: str = DEFAULT_PRINT_SETTINGS["paper_size"],
    header_quote: str = DEFAULT_PRINT_SETTINGS["header_quote"],
    footer_terms: str = DEFAULT_PRINT_SETTINGS["footer_terms"],
    layout_coordinates: str = DEFAULT_PRINT_SETTINGS["layout_coordinates"],
    show_item_barcode: Any = DEFAULT_PRINT_SETTINGS["show_item_barcode"],
) -> bool:
    """Insert or update one company's global invoice print settings."""
    try:
        db, resolved_company_id = _resolve_db_and_company(db_or_company_id, company_id)
    except (TypeError, ValueError) as exc:
        LOGGER.exception("Invalid print settings save company id: %s", exc)
        return False

    ensure_print_settings_table(db)
    ph = db._get_placeholder()
    values = (
        str(default_format or DEFAULT_PRINT_SETTINGS["default_format"]),
        str(default_theme or DEFAULT_PRINT_SETTINGS["default_theme"]),
        "" if printer_name is None else str(printer_name),
        str(printer_type or DEFAULT_PRINT_SETTINGS["printer_type"]),
        str(paper_size or DEFAULT_PRINT_SETTINGS["paper_size"]),
        "" if header_quote is None else str(header_quote),
        "" if footer_terms is None else str(footer_terms),
        "" if layout_coordinates is None else str(layout_coordinates),
        _bool_text(show_item_barcode),
    )
    conn = None
    try:
        conn = db.connect()
        with closing(conn.cursor()) as cursor:
            cursor.execute(
                f"""
                SELECT company_id
                FROM print_settings
                WHERE company_id = {ph}
                """,
                (resolved_company_id,),
            )
            existing = cursor.fetchone()
            if existing:
                cursor.execute(
                    f"""
                    UPDATE print_settings
                    SET default_format = {ph},
                        default_theme = {ph},
                        printer_name = {ph},
                        printer_type = {ph},
                        paper_size = {ph},
                        header_quote = {ph},
                        footer_terms = {ph},
                        layout_coordinates = {ph},
                        show_item_barcode = {ph}
                    WHERE company_id = {ph}
                    """,
                    (*values, resolved_company_id),
                )
            else:
                cursor.execute(
                    f"""
                    INSERT INTO print_settings (
                        company_id,
                        default_format,
                        default_theme,
                        printer_name,
                        printer_type,
                        paper_size,
                        header_quote,
                        footer_terms,
                        layout_coordinates,
                        show_item_barcode
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (resolved_company_id, *values),
                )
        conn.commit()
        return True
    except sqlite3.Error as exc:
        print(f"Database Error: {exc}")
        LOGGER.exception("Print settings save failed: %s", exc)
        try:
            _rollback_if_supported(db)
        except Exception as rollback_exc:
            LOGGER.exception("Print settings rollback failed: %s", rollback_exc)
        raise
    except Exception as exc:
        LOGGER.exception("Print settings save failed: %s", exc)
        try:
            _rollback_if_supported(db)
        except Exception as rollback_exc:
            LOGGER.exception("Print settings rollback failed: %s", rollback_exc)
        raise
    finally:
        try:
            db.disconnect()
        except Exception as disconnect_exc:
            LOGGER.exception("Print settings disconnect failed: %s", disconnect_exc)
