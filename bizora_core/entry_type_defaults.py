"""
Default Cash/Credit entry type settings for commercial voucher pages.

Per-entry settings mirror invoice prefix configuration. Quotation and purchase
order are excluded because they do not use cash/credit entry modes.
"""

from __future__ import annotations

from typing import Optional

from bizora_core.invoice_numbering import VOUCHER_PREFIX_LABELS
from bizora_core.settings_logic import get_settings, save_setting

DEFAULT_ENTRY_TYPE_KEY = "default_entry_type"

ENTRY_TYPE_VOUCHERS = (
    "sales",
    "purchase",
    "sales_return",
    "purchase_return",
)

ENTRY_TYPE_SETTINGS = {
    "sales": "default_entry_type_sales",
    "purchase": "default_entry_type_purchase",
    "sales_return": "default_entry_type_sales_return",
    "purchase_return": "default_entry_type_purchase_return",
}

ENTRY_TYPE_VOUCHER_LABELS = {
    voucher_type: VOUCHER_PREFIX_LABELS[voucher_type]
    for voucher_type in ENTRY_TYPE_VOUCHERS
}


def normalize_entry_type(value: str) -> str:
    """Return a canonical Cash/Credit label from stored or UI text."""
    return "Credit" if str(value or "").strip().lower() == "credit" else "Cash"


def get_default_entry_type(
    db,
    company_id: Optional[int],
    voucher_type: str = "",
) -> str:
    """Read the configured default entry type for one company and voucher."""
    if not company_id:
        return "Cash"
    try:
        settings = get_settings(db, company_id)
        if voucher_type:
            specific_key = ENTRY_TYPE_SETTINGS.get(voucher_type)
            if specific_key:
                specific_value = str(settings.get(specific_key, "") or "").strip()
                if specific_value:
                    return normalize_entry_type(specific_value)
        return normalize_entry_type(settings.get(DEFAULT_ENTRY_TYPE_KEY, "Cash"))
    except Exception:
        return "Cash"


def save_default_entry_type(
    db,
    company_id: Optional[int],
    entry_type: str,
    voucher_type: str = "",
) -> bool:
    """Persist one default entry type value for a company."""
    if not company_id:
        return False
    try:
        setting_key = (
            ENTRY_TYPE_SETTINGS.get(voucher_type, DEFAULT_ENTRY_TYPE_KEY)
            if voucher_type
            else DEFAULT_ENTRY_TYPE_KEY
        )
        return save_setting(db, company_id, setting_key, normalize_entry_type(entry_type))
    except Exception:
        return False


def get_active_company_default_entry_type(db, voucher_type: str) -> str:
    """Read the default entry type for the active company and voucher."""
    try:
        from config import active_company_manager

        active_company = active_company_manager.get_active_company()
        company_id = active_company.get("id") if active_company else None
        return get_default_entry_type(db, company_id, voucher_type)
    except Exception:
        return "Cash"


def apply_entry_type_combo(combo, entry_type: str) -> None:
    """Set a Cash/Credit combo box to the requested default entry type."""
    if combo is None:
        return
    text = normalize_entry_type(entry_type)
    try:
        from PySide6.QtCore import Qt

        index = combo.findText(text, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setCurrentText(text)
    except Exception:
        combo.setCurrentText(text)
