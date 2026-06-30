"""
SQLite persistence for global barcode label preferences (row id=1).

Replaces direct UI reads during PDF generation; the print queue loads this
record at runtime via fetch_barcode_preferences().
"""

import json
import os
import re

from .settings_logic import (
    DEFAULT_SYSTEM_SETTINGS,
    get_settings as get_company_settings,
    resolve_company_id,
    save_settings as save_company_settings,
)

try:
    from config import active_company_manager, CURRENCY_SYMBOL
except Exception:
    active_company_manager = None
    CURRENCY_SYMBOL = "Rs"

def _barcode_module():
    """Lazy import to avoid circular dependency with ui.barcode_manager."""
    from ui import barcode_manager
    return barcode_manager

BARCODE_SETTINGS_ROW_ID = 1

DEFAULT_COMPANY_NAME = "My Company"
DEFAULT_CIPHER_STRING = "RCNXZYBQWM"
DEFAULT_SIZE_TEXT = '2.00" x 1.00" (50x25mm Single)'
DEFAULT_GAP_TEXT = "With Gap (Standard 3mm spacing)"
DEFAULT_PADDING_TEXT = "No Padding"
DEFAULT_FONT_THICKNESS = "Extra Bold"
BARCODE_SETTINGS_TABLE = "barcode_settings"
_PRAGMA_TABLE_WHITELIST = {BARCODE_SETTINGS_TABLE}
MEDIA_GAP_COMBO_TEXTS = (
    "With Gap (Standard 3mm spacing)",
    "Continuous (No Gap)",
)


def barcode_padding_width(padding_text) -> int:
    """Return the configured new-barcode zero-padding width, or zero if disabled."""
    try:
        match = re.search(r"(\d+)\s*Digits", str(padding_text or ""))
        if match:
            width = int(match.group(1))
            if 2 <= width <= 5:
                return width
    except Exception:
        pass
    return 0


def apply_barcode_padding_for_new_code(barcode_value, padding_text) -> str:
    """Pad only newly generated numeric barcode strings using the saved setting."""
    text = str(barcode_value or "").strip()
    width = barcode_padding_width(padding_text)
    if not text or width <= 0 or not text.isdigit():
        return text
    try:
        return text.zfill(width)
    except Exception:
        return text


def _json_settings_path() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "barcode_settings.json")


def _cipher_string_from_map(price_map: dict) -> str:
    """Serialize the cipher row as a 10-letter string (digit order 1-9, then 0)."""
    try:
        mapping = price_map or _barcode_module().default_price_map()
        digits = _barcode_module().DEFAULT_PRICE_DIGITS
        letters = []
        for digit in digits:
            letters.append(str(mapping.get(digit, "")).strip().upper()[:1])
        combined = "".join(letters)
        if len(combined) >= 10:
            return combined[:10]
        return DEFAULT_CIPHER_STRING
    except Exception:
        return DEFAULT_CIPHER_STRING


def _sticker_size_options():
    """Return the canonical sticker size combo labels."""
    return list(_barcode_module().STICKER_SIZE_OPTIONS)


def _size_index_from_stored(value) -> int:
    """Map a stored size (combo text, legacy index, or seed label) to combo index."""
    options = _sticker_size_options()
    if value is None or value == "":
        return 0
    try:
        if isinstance(value, int) or (
            isinstance(value, str) and str(value).strip().isdigit()
        ):
            idx = int(value)
            if 0 <= idx < len(options):
                return idx
    except Exception:
        pass
    text = str(value).strip()
    for idx, option in enumerate(options):
        if text == option:
            return idx
    lowered = text.lower()
    if "4.00" in text and "6.00" in text:
        return _index_for_option_substr(options, "4.00")
    if "3.00" in text and "1.00" in text:
        return _index_for_option_substr(options, "3.00")
    if "0.50" in text or "jewelry" in lowered:
        return _index_for_option_substr(options, "0.50")
    if "1.50" in text or "dual" in lowered or "2-up" in lowered:
        return _index_for_option_substr(options, "1.50")
    if "2.00" in text or "single" in lowered:
        return _index_for_option_substr(options, "2.00")
    return 0


def _index_for_option_substr(options, needle: str) -> int:
    """Find first combo option containing needle, else 0."""
    for idx, option in enumerate(options):
        if needle in option:
            return idx
    return 0


def _gap_index_from_stored(value) -> int:
    """Map a stored gap (combo text, legacy index, or seed label) to combo index."""
    if value is None or value == "":
        return 0
    try:
        if isinstance(value, int) or (
            isinstance(value, str) and str(value).strip().isdigit()
        ):
            idx = int(value)
            if 0 <= idx < len(MEDIA_GAP_COMBO_TEXTS):
                return idx
    except Exception:
        pass
    text = str(value).strip()
    for idx, option in enumerate(MEDIA_GAP_COMBO_TEXTS):
        if text == option:
            return idx
    lowered = text.lower()
    if "continuous" in lowered or "no gap" in lowered:
        return 1
    return 0


def _stored_size_text(value) -> str:
    """Normalize persisted size to combo text for UPDATE storage."""
    options = _sticker_size_options()
    idx = _size_index_from_stored(value)
    if 0 <= idx < len(options):
        return options[idx]
    return options[1] if len(options) > 1 else options[0]


def _stored_gap_text(value) -> str:
    """Normalize persisted gap to combo text for UPDATE storage."""
    idx = _gap_index_from_stored(value)
    return MEDIA_GAP_COMBO_TEXTS[idx]


def _cipher_map_from_string(cipher_string: str) -> dict:
    """Deserialize cipher_string column into a digit->letter dict."""
    if not cipher_string:
        return _barcode_module().default_price_map()
    try:
        data = json.loads(cipher_string)
        if isinstance(data, dict) and data:
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    text = (cipher_string or "").strip().upper()
    if len(text) >= 10:
        digits = _barcode_module().DEFAULT_PRICE_DIGITS
        return {digit: text[idx] for idx, digit in enumerate(digits)}
    return _barcode_module().default_price_map()


def ensure_barcode_settings_table(db) -> None:
    """Create barcode_settings table if missing and seed row id=1."""
    try:
        db.execute_update(
            """
            CREATE TABLE IF NOT EXISTS barcode_settings (
                id INTEGER PRIMARY KEY,
                company_name TEXT DEFAULT '',
                cipher_string TEXT DEFAULT '',
                default_size TEXT DEFAULT '',
                default_gap TEXT DEFAULT '',
                default_printer TEXT DEFAULT '',
                element_offsets TEXT DEFAULT '',
                typography_settings TEXT DEFAULT ''
            )
            """
        )
        _ensure_barcode_padding_column(db)
        _ensure_font_thickness_column(db)
        rows = db.execute_query(
            "SELECT id FROM barcode_settings WHERE id = ?",
            (BARCODE_SETTINGS_ROW_ID,),
        )
        if not rows:
            legacy = _load_legacy_json_settings()
            size_idx = int(legacy.get("sticker_size_index", 0) or 0)
            gap_idx = int(legacy.get("media_gap_index", 0) or 0)
            db.execute_update(
                """
                INSERT INTO barcode_settings (
                    id, company_name, cipher_string, default_size, default_gap,
                    default_printer, element_offsets, typography_settings,
                    barcode_padding, font_thickness
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    BARCODE_SETTINGS_ROW_ID,
                    legacy.get("company_name") or DEFAULT_COMPANY_NAME,
                    _cipher_string_from_map(legacy.get("price_key_map")),
                    _stored_size_text(size_idx),
                    _stored_gap_text(gap_idx),
                    str(legacy.get("printer_name", "") or ""),
                    json.dumps(
                        _barcode_module().normalize_element_offsets(
                            legacy.get("element_offsets")
                        )
                    ),
                    json.dumps(
                        legacy.get("typography_settings")
                        or _barcode_module().default_typography_settings()
                    ),
                    str(legacy.get("barcode_padding", "") or DEFAULT_PADDING_TEXT),
                    str(legacy.get("font_thickness", "") or DEFAULT_FONT_THICKNESS),
                ),
            )
    except Exception:
        pass


def _safe_pragma_table_name(table_name: str) -> str:
    """Return a quoted PRAGMA table identifier after strict table validation."""
    if table_name not in _PRAGMA_TABLE_WHITELIST:
        raise ValueError(f"Unsafe PRAGMA table name: {table_name}")
    return f'"{table_name}"'


def _column_exists(db, table_name: str, column_name: str) -> bool:
    """Check SQLite table metadata before running additive barcode migrations."""
    try:
        safe_table = _safe_pragma_table_name(table_name)
        rows = db.execute_query(f"PRAGMA table_info({safe_table})")
        for row in rows or []:
            if isinstance(row, dict):
                existing_name = row.get("name")
            else:
                existing_name = row[1] if len(row) > 1 else None
            if str(existing_name or "") == column_name:
                return True
    except Exception as exc:
        print(f"Barcode settings migration metadata error: {exc}")
        return True
    return False


def _ensure_barcode_padding_column(db) -> None:
    """Add barcode_padding without disturbing existing barcode settings rows."""
    try:
        if _column_exists(db, BARCODE_SETTINGS_TABLE, "barcode_padding"):
            return
        db.execute_update(
            """
            ALTER TABLE barcode_settings
            ADD COLUMN barcode_padding TEXT DEFAULT 'No Padding'
            """
        )
    except Exception as exc:
        print(f"Barcode settings migration error adding barcode_padding: {exc}")


def _ensure_font_thickness_column(db) -> None:
    """Add font_thickness without disturbing existing barcode settings rows."""
    try:
        if _column_exists(db, BARCODE_SETTINGS_TABLE, "font_thickness"):
            return
        db.execute_update(
            """
            ALTER TABLE barcode_settings
            ADD COLUMN font_thickness TEXT DEFAULT 'Extra Bold (Thermal)'
            """
        )
    except Exception as exc:
        print(f"Barcode settings migration error adding font_thickness: {exc}")


def _load_legacy_json_settings() -> dict:
    """Read barcode_settings.json for first-time migration into SQLite."""
    payload = {
        "company_name": "",
        "price_key_map": _barcode_module().default_price_map(),
        "sticker_size_index": 0,
        "media_gap_index": 0,
        "printer_name": "",
        "barcode_padding": DEFAULT_PADDING_TEXT,
        "font_thickness": DEFAULT_FONT_THICKNESS,
        "element_offsets": _barcode_module().default_element_offsets(),
        "typography_settings": _barcode_module().default_typography_settings(),
    }
    try:
        path = _json_settings_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                payload.update(data)
    except Exception:
        pass
    if not payload.get("company_name") and active_company_manager is not None:
        try:
            payload["company_name"] = (
                active_company_manager.get_active_company_name() or ""
            )
        except Exception:
            pass
    return payload


def fetch_barcode_preferences(db, company_id: int = None) -> dict:
    """
    Load barcode preferences for one company from company_settings.

    Returns keys: company_name, cipher_string, default_size, default_gap,
    default_printer, barcode_padding, font_thickness, price_key_map,
    element_offsets, typography_settings.
    """
    resolved_company_id = resolve_company_id(company_id)
    settings = dict(DEFAULT_SYSTEM_SETTINGS)
    if resolved_company_id:
        settings = get_company_settings(db, resolved_company_id)
    try:
        company_name = settings.get("barcode_company_name", "")
        if not company_name and active_company_manager is not None:
            try:
                company_name = active_company_manager.get_active_company_name() or ""
            except Exception:
                company_name = ""
        cipher_string = settings.get("barcode_cipher_string", DEFAULT_CIPHER_STRING)
        default_size = settings.get("barcode_default_size", DEFAULT_SIZE_TEXT) or ""
        default_gap = settings.get("barcode_default_gap", DEFAULT_GAP_TEXT) or ""
        default_printer = settings.get("barcode_default_printer", "") or ""
        offsets_raw = settings.get("barcode_element_offsets", "") or ""
        typo_raw = settings.get("barcode_typography_settings", "") or ""
        barcode_padding = (
            settings.get("barcode_padding", DEFAULT_PADDING_TEXT)
            or DEFAULT_PADDING_TEXT
        )
        font_thickness = (
            settings.get("barcode_font_thickness", DEFAULT_FONT_THICKNESS)
            or DEFAULT_FONT_THICKNESS
        )

        offsets = _barcode_module().default_element_offsets()
        try:
            if offsets_raw:
                parsed = json.loads(offsets_raw)
                if isinstance(parsed, dict):
                    offsets = _barcode_module().normalize_element_offsets(parsed)
        except Exception:
            pass

        typo = _barcode_module().default_typography_settings()
        try:
            if typo_raw:
                parsed_typo = json.loads(typo_raw)
                if isinstance(parsed_typo, dict):
                    typo.update(parsed_typo)
        except Exception:
            pass

        return {
            "company_name": company_name or "",
            "cipher_string": cipher_string or "",
            "default_size": _stored_size_text(default_size),
            "default_gap": _stored_gap_text(default_gap),
            "default_size_index": _size_index_from_stored(default_size),
            "default_gap_index": _gap_index_from_stored(default_gap),
            "default_printer": default_printer or "",
            "barcode_padding": barcode_padding or DEFAULT_PADDING_TEXT,
            "font_thickness": font_thickness or DEFAULT_FONT_THICKNESS,
            "price_key_map": _cipher_map_from_string(cipher_string),
            "element_offsets": offsets,
            "typography_settings": typo,
        }
    except Exception:
        return {
            "company_name": settings.get("barcode_company_name", ""),
            "cipher_string": settings.get("barcode_cipher_string", DEFAULT_CIPHER_STRING),
            "default_size": _stored_size_text(
                settings.get("barcode_default_size", DEFAULT_SIZE_TEXT)
            ),
            "default_gap": _stored_gap_text(
                settings.get("barcode_default_gap", DEFAULT_GAP_TEXT)
            ),
            "default_size_index": _size_index_from_stored(
                settings.get("barcode_default_size", DEFAULT_SIZE_TEXT)
            ),
            "default_gap_index": _gap_index_from_stored(
                settings.get("barcode_default_gap", DEFAULT_GAP_TEXT)
            ),
            "default_printer": settings.get("barcode_default_printer", "") or "",
            "barcode_padding": settings.get("barcode_padding", DEFAULT_PADDING_TEXT)
            or DEFAULT_PADDING_TEXT,
            "font_thickness": settings.get(
                "barcode_font_thickness", DEFAULT_FONT_THICKNESS
            ) or DEFAULT_FONT_THICKNESS,
            "price_key_map": _cipher_map_from_string(
                settings.get("barcode_cipher_string", DEFAULT_CIPHER_STRING)
            ),
            "element_offsets": _barcode_module().default_element_offsets(),
            "typography_settings": _barcode_module().default_typography_settings(),
        }


def save_barcode_preferences(db, data: dict, company_id: int = None) -> bool:
    """Persist barcode preferences for one company in company_settings."""
    try:
        resolved_company_id = resolve_company_id(company_id)
        if not resolved_company_id:
            return False
        bm = _barcode_module()
        price_map = data.get("price_key_map") or bm.default_price_map()
        offsets = bm.normalize_element_offsets(data.get("element_offsets"))
        typo = data.get("typography_settings") or bm.default_typography_settings()
        size_raw = data.get("default_size", data.get("sticker_size_index", 0))
        gap_raw = data.get("default_gap", data.get("media_gap_index", 0))
        barcode_padding = str(
            data.get("barcode_padding", DEFAULT_PADDING_TEXT) or DEFAULT_PADDING_TEXT
        ).strip()
        font_thickness = str(
            data.get("font_thickness", DEFAULT_FONT_THICKNESS)
            or DEFAULT_FONT_THICKNESS
        ).strip()
        cipher_raw = data.get("cipher_string")
        if cipher_raw:
            cipher_value = str(cipher_raw).strip().upper()[:10]
        else:
            cipher_value = _cipher_string_from_map(price_map)

        return save_company_settings(
            db,
            resolved_company_id,
            {
                "barcode_company_name": str(data.get("company_name", "") or "").strip(),
                "barcode_cipher_string": cipher_value,
                "barcode_default_size": _stored_size_text(size_raw),
                "barcode_default_gap": _stored_gap_text(gap_raw),
                "barcode_default_printer": str(
                    data.get("default_printer", data.get("printer_name", "")) or ""
                ).strip(),
                "barcode_element_offsets": json.dumps(offsets),
                "barcode_typography_settings": json.dumps(typo),
                "barcode_padding": barcode_padding,
                "barcode_font_thickness": font_thickness,
            },
        )
    except Exception:
        return False


def preferences_to_barcode_settings(prefs: dict):
    """Build a BarcodeSettings instance from a fetch_barcode_preferences dict."""
    settings = _barcode_module().BarcodeSettings()
    settings.company_name = prefs.get("company_name", "") or ""
    settings.price_key_map = prefs.get("price_key_map") or _barcode_module().default_price_map()
    settings.sticker_size_index = int(
        prefs.get("default_size_index", _size_index_from_stored(prefs.get("default_size")))
        or 0
    )
    settings.media_gap_index = int(
        prefs.get("default_gap_index", _gap_index_from_stored(prefs.get("default_gap")))
        or 0
    )
    settings.printer_name = prefs.get("default_printer", "") or ""
    settings.barcode_padding = (
        prefs.get("barcode_padding") or _barcode_module().BARCODE_PADDING_OPTIONS[0]
    )
    settings.font_thickness = (
        prefs.get("font_thickness")
        or getattr(_barcode_module(), "DEFAULT_FONT_THICKNESS", DEFAULT_FONT_THICKNESS)
    )
    settings.element_offsets = _barcode_module().normalize_element_offsets(
        prefs.get("element_offsets")
    )
    settings.typography_settings = (
        prefs.get("typography_settings")
        or _barcode_module().default_typography_settings()
    )
    return settings


def build_calibration_profile_from_prefs(prefs: dict, calibration: dict = None) -> dict:
    """Merge sticker_config.json with DB sticker size text (no int casts on labels)."""
    bm = _barcode_module()
    cfg = bm.calibration_profile_from_size_text(
        str(prefs.get("default_size", "") or ""),
        calibration or bm.load_calibration_config(),
    )
    offsets = prefs.get("element_offsets") or cfg.get("element_offsets")
    if isinstance(offsets, dict):
        cfg["element_offsets"] = bm.normalize_element_offsets(offsets)
    return cfg
