"""
Company-scoped application settings with hardcoded system defaults.

The defaults in this module are intentionally plain strings because the
company_settings table stores user overrides as text. Callers remain
responsible for parsing JSON values into richer Python objects where needed.
"""

import json
from typing import Any, Dict, Optional

try:
    from config import active_company_manager
except Exception:
    active_company_manager = None


DEFAULT_BARCODE_ELEMENT_OFFSETS = {
    "company_x": 0,
    "company_y": 0,
    "product_x": 0,
    "product_y": 0,
    "barcode_graphic_x": 0,
    "barcode_graphic_y": 0,
    "barcode_graphic_w": 0,
    "barcode_graphic_h": 0,
    "barcode_number_x": 0,
    "barcode_number_y": 0,
    "price_x": 0,
    "price_y": 0,
    "cipher_x": 0,
    "cipher_y": 0,
    "batch_index_x": 0,
    "batch_index_y": 0,
    "supplier_code_x": 0,
    "supplier_code_y": 0,
}

DEFAULT_BARCODE_TYPOGRAPHY = {
    "company_size": 7,
    "company_bold": True,
    "company_thickness": "Extra Bold",
    "product_size": 6,
    "product_bold": False,
    "product_thickness": "Normal",
    "barcode_text_size": 5,
    "barcode_text_bold": False,
    "barcode_text_thickness": "Normal",
    "mrp_size": 7,
    "mrp_bold": True,
    "mrp_thickness": "Extra Bold",
    "cipher_size": 5,
    "cipher_bold": False,
    "cipher_thickness": "Normal",
    "batch_index_size": 6,
    "batch_index_bold": False,
    "batch_index_thickness": "Normal",
    "supplier_size": 5,
    "supplier_bold": True,
    "supplier_thickness": "Extra Bold",
}

SUPPORTED_PRINT_FORMATS = ("Thermal_80mm", "A4", "A3", "Custom")
DEFAULT_PRINT_FORMAT = "A4"

DEFAULT_SYSTEM_SETTINGS = {
    "enable_cash_tender": "1",
    "invoice_prefix": "",
    "invoice_prefix_sales": "",
    "invoice_prefix_purchase": "",
    "invoice_prefix_sales_return": "",
    "invoice_prefix_purchase_return": "",
    "invoice_prefix_quotation": "",
    "invoice_prefix_purchase_order": "",
    "default_entry_type": "Cash",
    "default_entry_type_sales": "Cash",
    "default_entry_type_purchase": "Cash",
    "default_entry_type_sales_return": "Cash",
    "default_entry_type_purchase_return": "Cash",
    "enable_debug_mode": "0",
    "confirm_before_delete": "1",
    "default_print_format": DEFAULT_PRINT_FORMAT,
    "barcode_company_name": "",
    "barcode_cipher_string": "RCNXZYBQWM",
    "barcode_default_size": '2.00" x 1.00" (50x25mm Single)',
    "barcode_default_gap": "With Gap (Standard 3mm spacing)",
    "barcode_default_printer": "",
    "barcode_padding": "No Padding",
    "barcode_font_thickness": "Extra Bold",
    "barcode_element_offsets": json.dumps(DEFAULT_BARCODE_ELEMENT_OFFSETS),
    "barcode_typography_settings": json.dumps(DEFAULT_BARCODE_TYPOGRAPHY),
}


def resolve_company_id(company_id: Optional[int] = None) -> Optional[int]:
    """Resolve an explicit or active company ID without querying global settings."""
    if company_id:
        try:
            return int(company_id)
        except (TypeError, ValueError):
            return None
    if active_company_manager is None:
        return None
    try:
        active_id = active_company_manager.get_active_company_id()
        return int(active_id) if active_id else None
    except Exception:
        return None


def ensure_company_settings_table(db) -> None:
    """Ask the database layer to create company_settings when available."""
    try:
        if hasattr(db, "ensure_company_settings_table"):
            db.ensure_company_settings_table()
    except Exception as exc:
        print(f"Company settings table ensure error: {exc}")


def get_settings(db, company_id: int) -> Dict[str, str]:
    """Return defaults overlaid with settings for exactly one company."""
    settings = dict(DEFAULT_SYSTEM_SETTINGS)
    resolved_company_id = resolve_company_id(company_id)
    if not resolved_company_id:
        return settings

    ensure_company_settings_table(db)
    ph = db._get_placeholder()
    query = f"""
        SELECT setting_key, setting_value
        FROM company_settings
        WHERE company_id = {ph}
    """
    try:
        rows = db.execute_query(query, (resolved_company_id,))
        for row in rows or []:
            if isinstance(row, dict):
                key = row.get("setting_key")
                value = row.get("setting_value")
            else:
                key = row[0] if len(row) > 0 else None
                value = row[1] if len(row) > 1 else None
            if key:
                settings[str(key)] = "" if value is None else str(value)
    except Exception as exc:
        print(f"Company settings fetch error: {exc}")
    return settings


def save_setting(db, company_id: int, key: str, value: Any) -> bool:
    """Insert or update one setting row for exactly the requested company."""
    resolved_company_id = resolve_company_id(company_id)
    setting_key = str(key or "").strip()
    if not resolved_company_id or not setting_key:
        return False

    ensure_company_settings_table(db)
    ph = db._get_placeholder()
    setting_value = "" if value is None else str(value)
    try:
        existing = db.execute_query(
            f"""
            SELECT company_id, setting_key
            FROM company_settings
            WHERE company_id = {ph} AND setting_key = {ph}
            """,
            (resolved_company_id, setting_key),
        )
        if existing:
            return db.execute_update(
                f"""
                UPDATE company_settings
                SET setting_value = {ph}
                WHERE company_id = {ph} AND setting_key = {ph}
                """,
                (setting_value, resolved_company_id, setting_key),
            )
        return db.execute_update(
            f"""
            INSERT INTO company_settings (
                company_id, setting_key, setting_value
            ) VALUES ({ph}, {ph}, {ph})
            """,
            (resolved_company_id, setting_key, setting_value),
        )
    except Exception as exc:
        print(f"Company setting save error: {exc}")
        return False


def save_settings(db, company_id: int, values: Dict[str, Any]) -> bool:
    """Persist several settings for one company using the canonical save path."""
    try:
        for key, value in (values or {}).items():
            if not save_setting(db, company_id, key, value):
                return False
        return True
    except Exception as exc:
        print(f"Company settings batch save error: {exc}")
        return False


def is_truthy_setting(value: str) -> bool:
    """Interpret common truthy company_settings string values."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_debug_mode_enabled(db, company_id: int) -> bool:
    """Return whether debug mode is enabled for the active company."""
    try:
        settings = get_settings(db, company_id)
        return is_truthy_setting(settings.get("enable_debug_mode", "0"))
    except Exception:
        return False


def is_confirm_delete_enabled(db, company_id: int) -> bool:
    """Return whether delete actions should ask for confirmation."""
    try:
        settings = get_settings(db, company_id)
        return is_truthy_setting(settings.get("confirm_before_delete", "1"))
    except Exception:
        return True


def confirm_before_delete_transaction(
    parent,
    title: str,
    message: str,
    db=None,
    company_id: Optional[int] = None,
) -> bool:
    """Return True when delete should proceed (confirmed or confirmation disabled)."""
    from PySide6.QtWidgets import QMessageBox

    resolved_company_id = resolve_company_id(company_id)
    active_db = db or getattr(parent, "db", None)
    if resolved_company_id and active_db is not None:
        if not is_confirm_delete_enabled(active_db, resolved_company_id):
            return True

    reply = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return reply == QMessageBox.Yes
