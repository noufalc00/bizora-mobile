"""
Product / Service page settings helpers.

Persists per-company preferences in company_settings using plain string
values so the storage layer stays portable for a future MySQL migration.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from bizora_core.settings_logic import get_settings, save_settings

PRODUCT_ALLOW_DUPLICATE_KEY = "product_allow_duplicate"
PRODUCT_SHOW_NAME_LIST_KEY = "product_show_name_list"
PRODUCT_ENTER_JUMP_FIELDS_KEY = "product_enter_jump_fields"

PRODUCT_ENTER_FIELD_DEFINITIONS: List[tuple[str, str]] = [
    ("name", "Product Name"),
    ("barcode", "Barcode"),
    ("hsn", "HSN"),
    ("color", "Color"),
    ("size", "Size"),
    ("unit", "Unit"),
    ("category", "Category"),
    ("purchase_rate", "Purchase Rate"),
    ("sale_price", "Sale Price"),
    ("wholesale_rate", "Wholesale Rate"),
    ("mrp", "MRP"),
    ("cgst", "CGST"),
    ("sgst", "SGST"),
    ("igst", "IGST"),
    ("cess", "CESS"),
    ("reorder_level", "Reorder Level"),
    ("description", "Description"),
    ("qty", "Quantity"),
]

DEFAULT_ENTER_JUMP_FIELDS: List[str] = [key for key, _ in PRODUCT_ENTER_FIELD_DEFINITIONS]

_FIELD_LABELS = dict(PRODUCT_ENTER_FIELD_DEFINITIONS)


def parse_enter_jump_fields(raw_value: str | None) -> List[str]:
    """Parse stored JSON field keys, falling back to the full default order."""
    if not raw_value:
        return list(DEFAULT_ENTER_JUMP_FIELDS)
    try:
        parsed = json.loads(raw_value)
        if not isinstance(parsed, list):
            return list(DEFAULT_ENTER_JUMP_FIELDS)
        valid_keys = {key for key, _ in PRODUCT_ENTER_FIELD_DEFINITIONS}
        ordered = [str(key) for key in parsed if str(key) in valid_keys]
        return ordered or list(DEFAULT_ENTER_JUMP_FIELDS)
    except (TypeError, ValueError, json.JSONDecodeError):
        return list(DEFAULT_ENTER_JUMP_FIELDS)


def get_product_page_settings(db, company_id: int) -> Dict[str, Any]:
    """Load product page settings for one company with safe defaults."""
    settings = get_settings(db, company_id)
    return {
        "allow_duplicate": settings.get(PRODUCT_ALLOW_DUPLICATE_KEY, "0") == "1",
        "show_name_list": settings.get(PRODUCT_SHOW_NAME_LIST_KEY, "0") == "1",
        "enter_jump_fields": parse_enter_jump_fields(
            settings.get(PRODUCT_ENTER_JUMP_FIELDS_KEY)
        ),
    }


def save_product_page_settings(db, company_id: int, values: Dict[str, Any]) -> bool:
    """Persist product page settings for one company."""
    enter_fields = values.get("enter_jump_fields") or list(DEFAULT_ENTER_JUMP_FIELDS)
    valid_keys = {key for key, _ in PRODUCT_ENTER_FIELD_DEFINITIONS}
    ordered_fields = [str(key) for key in enter_fields if str(key) in valid_keys]
    if not ordered_fields:
        ordered_fields = list(DEFAULT_ENTER_JUMP_FIELDS)

    payload = {
        PRODUCT_ALLOW_DUPLICATE_KEY: "1" if values.get("allow_duplicate") else "0",
        PRODUCT_SHOW_NAME_LIST_KEY: "1" if values.get("show_name_list") else "0",
        PRODUCT_ENTER_JUMP_FIELDS_KEY: json.dumps(ordered_fields),
    }
    return save_settings(db, company_id, payload)


def enter_field_label(field_key: str) -> str:
    """Return a human-readable label for one enter-jump field key."""
    return _FIELD_LABELS.get(field_key, field_key.replace("_", " ").title())
