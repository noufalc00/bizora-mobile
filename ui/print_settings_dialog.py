"""
Popup dialog for company-scoped invoice print designer settings.
"""
from __future__ import annotations
import base64
import html
import json
import logging
import os
import sqlite3
from typing import Any, Callable, Iterable, Optional
from PySide6.QtCore import QRectF, QSizeF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPageSize, QPainter, QPen, QPixmap, QTextBlockFormat, QTextCursor, QTransform
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFrame, QFileDialog, QGraphicsItem, QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsTextItem, QGraphicsView, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QStackedWidget, QTextEdit, QVBoxLayout, QWidget
from config import COLORS, active_company_manager
from ui.checkbox_style import CheckBox3D, create_checkbox
from db import Database
from bizora_core.print_settings_logic import get_print_settings, save_print_settings
from utils.print_time_format import append_print_time_to_date
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
LOGGER = logging.getLogger(__name__)
A4_PAPER_SIZE = 'A4'
THERMAL_PAPER_SIZE = 'Thermal 80mm'
A4_DIMENSIONS = (794, 1123)
THERMAL_DIMENSIONS = (576, 1600)
THERMAL_ALIASES = {'80mm/3-inch', 'Thermal', THERMAL_PAPER_SIZE}
THERMAL_DPI = 203.0
THERMAL_WIDTH_MM = 80.0
THERMAL_CUT_MARGIN_MM = 10.0
THERMAL_HARDWARE_FEED_BUFFER_PX = 120.0
LAYOUT_IMAGE_PREFIX = 'image_'
SIGNATURE_IMAGE_BLOCK_ID = 'signature_image'
SIGNATURE_PLACEHOLDER_BLOCK_ID = 'signature_placeholder'
COMPOSITION_SUBHEADING_BLOCK_ID = 'invoice_subheading'
LAYOUT_SETTINGS_BLOCK_ID = '__settings__'
SHOW_ITEM_BARCODE_BELOW_NAME_KEY = 'show_item_barcode_below_name'
BOLD_GRAND_TOTAL_KEY = 'bold_grand_total'
PAPER_ROLL_SIZE_KEY = 'paper_roll_size'
THEME_KEY = 'theme'
THERMAL_THEME_KEY = 'thermal_theme'
THERMAL_PAPER_SIZE_KEY = 'thermal_paper_size'
THERMAL_CUSTOM_WIDTH_PX_KEY = 'thermal_custom_width_px'
THERMAL_WIDTH_MM_KEY = 'thermal_width_mm'
THERMAL_TEXT_SIZE_KEY = 'thermal_text_size'
THERMAL_USER_FONT_SIZE_KEY = 'thermal_user_font_size'
PRINT_GST_SUMMARY_TABLE_KEY = 'print_gst_summary_table'
SHOW_TOTAL_ITEMS_COUNT_KEY = 'show_total_items_count'
TERMS_CONDITIONS_FOOTER_KEY = 'terms_conditions_footer'
SHOW_COMPANY_NAME_KEY = 'show_company_name'
SHOW_COMPANY_ADDRESS_KEY = 'show_company_address'
SHOW_COMPANY_LOGO_KEY = 'show_company_logo'
SHOW_PHONE_NUMBER_KEY = 'show_phone_number'
SHOW_GSTIN_KEY = 'show_gstin'
PAPER_CUT_BUFFER_PX_KEY = 'paper_cut_buffer_px'
PRINT_BARCODE_COL_KEY = 'print_barcode_col'
TAX_SUMMARY_FONT_SIZE_KEY = 'tax_summary_font_size'
ITEM_NAME_BOLD_KEY = 'item_name_bold'
DEFAULT_PAPER_ROLL_SIZE = '3 Inch (80mm)'
THERMAL_PAPER_SIZE_OPTIONS = (DEFAULT_PAPER_ROLL_SIZE, '4 Inch (100mm)', 'Custom Size')
PAPER_ROLL_SIZE_OPTIONS = THERMAL_PAPER_SIZE_OPTIONS
BOLD_TOTAL_THEME = 'Bold Total'
THERMAL_THEME_OPTIONS = ('Classic POS', 'Compact Retail', 'Elegant Bill', 'Modern Invoice')
THERMAL_TEXT_SIZE_OPTIONS = ('Small', 'Large', 'Extra Large', 'User Defined')
DEFAULT_THERMAL_THEME = THERMAL_THEME_OPTIONS[0]
DEFAULT_THERMAL_TEXT_SIZE = 'Large'
DEFAULT_THERMAL_USER_FONT_SIZE = 12
DEFAULT_PRINT_MODE_KEY = 'default_print_mode'
DEFAULT_PRINT_MODE_OPTIONS = ('Thermal Receipt', 'A4/A5 Invoice')
DEFAULT_PRINT_MODE = DEFAULT_PRINT_MODE_OPTIONS[0]
A4_PAPER_SIZE_KEY = 'a4_paper_size'
A4_THEME_KEY = 'a4_theme'
A4_THEME_COLOR_KEY = 'a4_theme_color'
A4_SHOW_LOGO_KEY = 'a4_show_logo'
A4_SHOW_COMPANY_NAME_KEY = 'a4_show_company_name'
A4_SHOW_ADDRESS_KEY = 'a4_show_address'
A4_SHOW_PHONE_KEY = 'a4_show_phone'
A4_SHOW_EMAIL_KEY = 'a4_show_email'
A4_SHOW_GSTIN_KEY = 'a4_show_gstin'
A4_SHOW_HSN_SAC_KEY = 'a4_show_hsn_sac'
A4_SHOW_MRP_KEY = 'a4_show_mrp'
A4_SHOW_DISCOUNT_KEY = 'a4_show_discount'
A4_SHOW_TAX_RATE_KEY = 'a4_show_tax_rate'
A4_BANK_DETAILS_KEY = 'a4_bank_details'
A4_TERMS_CONDITIONS_KEY = 'a4_terms_conditions'
A4_SHOW_AUTHORIZED_SIGNATORY_KEY = 'a4_show_authorized_signatory'
A4_SHOW_COMPANY_NAME_TEXT_KEY = 'a4_show_company_name_text'
A4_LOGO_BASE64_KEY = 'a4_logo_base64'
A4_SIGNATURE_BASE64_KEY = 'a4_signature_base64'
PRINT_TIME_KEY = 'print_time'
A4_PRINT_TIME_KEY = 'a4_print_time'
THERMAL_PRINTER_NAME_KEY = 'thermal_printer_name'
NORMAL_PRINTER_NAME_KEY = 'normal_printer_name'
A4_PAPER_SIZE_OPTIONS = ('A4', 'A5')
A4_THEME_OPTIONS = ('GST Standard', 'Modern Clean', 'Elegant Serif', 'Compact Wholesale', 'Bold Corporate', 'Bill of Supply', 'Color Block Header', 'Vibrant Accent', 'Modern Gradient')
DEFAULT_A4_PAPER_SIZE = A4_PAPER_SIZE_OPTIONS[0]
DEFAULT_A4_THEME = A4_THEME_OPTIONS[0]
DEFAULT_A4_THEME_COLOR = '#E63946'
ITEM_BARCODE_PLACEHOLDER_BLOCK_ID = 'item_barcode_placeholder'
TOTALS_BLOCK_ID = 'totals_block'
TOTAL_ITEMS_BLOCK_ID = 'total_items'
FOOTER_TAX_SUMMARY_BLOCK_ID = 'footer_tax_summary'
HEADER_BILL_NO_BLOCK_ID = 'header_bill_no'
HEADER_DATE_BLOCK_ID = 'header_date'
LEGACY_HEADER_ANCHOR_ALIASES = {'bill_no': HEADER_BILL_NO_BLOCK_ID, 'date': HEADER_DATE_BLOCK_ID}
REMOVED_LAYOUT_BLOCK_IDS = {'footer_grand_total_val'}
COMPOSITION_SUBHEADING_TEXT = '(Composition Taxable Person, Not Eligible To Collect Taxes)'
THERMAL_ITEM_HEADER_TEXT = 'SN   Item          Qty    Price    Total'
THERMAL_ITEM_NAME_INDENT = '     '
THERMAL_ITEM_BARCODE_WIDTH = 16
THERMAL_ITEM_NAME_WIDTH = 36
SNAP_GUIDE_BLOCK_ID = '__snap_guide__'
SNAP_THRESHOLD_PX = 5.0
PREVIEW_SHIFTED_ROLE = 10
PREVIEW_SAVED_X_ROLE = 11
PREVIEW_SAVED_Y_ROLE = 12
PREVIEW_X_ROLE = 13
PREVIEW_Y_ROLE = 14
ITEM_COLUMN_ANCHORS = {'col_sn': 'SN', 'col_barcode': 'Bcd', 'col_qty': 'Qty', 'col_price': 'Price', 'col_total': 'Total', 'col_product_name': 'Item'}
ITEM_COLUMN_ANCHOR_IDS = tuple(ITEM_COLUMN_ANCHORS.keys())
BCD_HEADER_TEXT = 'Bcd'
BCD_HEADER_BLOCK_IDS = {'col_bcd', 'col_barcode'}
PREFERRED_BARCODE_COLUMN_ID = 'col_bcd'
LEGACY_BARCODE_COLUMN_ID = 'col_barcode'
BARCODE_COLUMN_BLOCK_IDS = (PREFERRED_BARCODE_COLUMN_ID, LEGACY_BARCODE_COLUMN_ID)
BARCODE_DATA_TEXT = '32651'
SAMPLE_ITEM_ROW_ELEMENTS = {'sample_sn': ('col_sn', '1'), PREFERRED_BARCODE_COLUMN_ID: ('col_product_name', BARCODE_DATA_TEXT), 'sample_barcode': (LEGACY_BARCODE_COLUMN_ID, BARCODE_DATA_TEXT), 'sample_product_name': ('col_product_name', 'Sample Item'), 'sample_qty': ('col_qty', '1.00'), 'sample_price': ('col_price', '150.00'), 'sample_total': ('col_total', '150.00')}
SAMPLE_ITEM_ROW_IDS = tuple(SAMPLE_ITEM_ROW_ELEMENTS.keys())
SAMPLE_ITEM_ROW_Y_OFFSET = 42.0
LEGACY_SAMPLE_ITEM_ROW_ALIASES = {'sample_bcd': PREFERRED_BARCODE_COLUMN_ID}
THERMAL_SAMPLE_ROW_PRIORITY = ('sample_sn', PREFERRED_BARCODE_COLUMN_ID, 'sample_barcode', 'sample_bcd', 'sample_product_name')
THERMAL_TOTAL_FIELD_IDS = ('subtotal', 'discount', 'tax', 'grand_total', 'amount_received', 'balance')
THERMAL_TOTALS_SAMPLE_TEXT = 'Subtotal: Rs. 150.00\nDiscount: Rs. 0.00\nTax: Rs. 19.50\nGrand Total: Rs. 170.00\nAmount Received: Rs. 170.00\nBalance: Rs. 0.00'
GRAND_TOTAL_TOP_PADDING = 10.0
GRAND_TOTAL_LINE_PADDING = 4.0
GRAND_TOTAL_BOTTOM_PADDING = 6.0
GRAND_TOTAL_LEFT_MARGIN = 10.0
GRAND_TOTAL_RIGHT_MARGIN = 10.0
GST_TAX_TABLE_TOP_PADDING = 10.0
GST_TAX_TABLE_LINE_PADDING = 5.0
GST_TAX_TABLE_BOTTOM_PADDING = 4.0
GST_TAX_TABLE_COLUMNS_INTRASTATE = (('GST%', 0.0, 58.0, 'left'), ('Net Amt', 84.0, 82.0, 'right'), ('CGST', 192.0, 82.0, 'right'), ('SGST', 304.0, 82.0, 'right'), ('Cess', 422.0, 82.0, 'right'))
GST_TAX_TABLE_COLUMNS_INTERSTATE = (('GST%', 0.0, 58.0, 'left'), ('Net Amt', 84.0, 82.0, 'right'), ('IGST', 224.0, 96.0, 'right'), ('Cess', 370.0, 96.0, 'right'))

def _plain_text(value: Any) -> str:
    """Return a display-safe string without leaking None/default artifacts."""
    return '' if value is None else str(value).strip()

def _money(value: Any) -> str:
    """Format numeric invoice values consistently for scene text."""
    try:
        return f'{float(value or 0.0):.2f}'
    except (TypeError, ValueError):
        return '0.00'

def _to_float(value: Any) -> float:
    """Convert nullable numeric values to float for print calculations."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0

def _truthy_setting(value: Any) -> bool:
    """Return True for persisted checkbox values saved as text or numbers."""
    return _plain_text(value).lower() in {'1', 'true', 'yes', 'on', 'checked'}

def _layout_quote_metadata(saved_layout_coordinates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return non-positional quote metadata stored inside layout JSON."""
    metadata = saved_layout_coordinates.get(LAYOUT_SETTINGS_BLOCK_ID, {})
    return metadata if isinstance(metadata, dict) else {}

def _deleted_layout_block_ids(saved_layout_coordinates: dict[str, dict[str, Any]]) -> set[str]:
    """Return layout block ids explicitly removed in the designer."""
    return {block_id for block_id, values in saved_layout_coordinates.items() if isinstance(values, dict) and _plain_text(values.get('type')) == 'deleted'}

def _quote_values_from_settings(settings: dict[str, Any]) -> tuple[str, str]:
    """Return header and footer quote values with layout JSON fallback."""
    saved_coordinates = parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
    metadata = _layout_quote_metadata(saved_coordinates)
    header_quote = _plain_text(settings.get('header_quote')) or _plain_text(metadata.get('header_quote'))
    footer_quote = _plain_text(settings.get('footer_terms')) or _plain_text(metadata.get('footer_quote')) or _plain_text(metadata.get('footer_terms'))
    return (header_quote, footer_quote)

def _layout_row_spacing(saved_layout_coordinates: dict[str, dict[str, Any]]) -> float:
    """Return the saved dynamic item row spacing from layout metadata."""
    metadata = _layout_quote_metadata(saved_layout_coordinates)
    try:
        row_spacing = float(metadata.get('row_spacing', 5))
    except (TypeError, ValueError):
        row_spacing = 5.0
    return max(0.0, row_spacing)

def _show_item_barcode_below_name_from_settings(settings: dict[str, Any]) -> bool:
    """Return whether item barcodes should print below item names."""
    saved_coordinates = parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
    metadata = _layout_quote_metadata(saved_coordinates)
    if SHOW_ITEM_BARCODE_BELOW_NAME_KEY in metadata:
        return _saved_bool(metadata.get(SHOW_ITEM_BARCODE_BELOW_NAME_KEY))
    if SHOW_ITEM_BARCODE_BELOW_NAME_KEY in settings:
        return _saved_bool(settings.get(SHOW_ITEM_BARCODE_BELOW_NAME_KEY))
    if 'show_item_barcode' in settings:
        return _saved_bool(settings.get('show_item_barcode'))
    return False

def _print_barcode_col_from_settings(settings: dict[str, Any]) -> bool:
    """Return whether the thermal barcode column should be printed."""
    saved_coordinates = parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
    metadata = _layout_quote_metadata(saved_coordinates)
    if PRINT_BARCODE_COL_KEY in metadata:
        return _saved_bool(metadata.get(PRINT_BARCODE_COL_KEY))
    if PRINT_BARCODE_COL_KEY in settings:
        return _saved_bool(settings.get(PRINT_BARCODE_COL_KEY))
    return True

def _item_name_bold_from_settings(settings: dict[str, Any]) -> bool:
    """Return whether printed item names should use bold row text."""
    saved_coordinates = parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
    metadata = _layout_quote_metadata(saved_coordinates)
    if ITEM_NAME_BOLD_KEY in metadata:
        return _saved_bool(metadata.get(ITEM_NAME_BOLD_KEY))
    if ITEM_NAME_BOLD_KEY in settings:
        return _saved_bool(settings.get(ITEM_NAME_BOLD_KEY))
    return False

def _layout_setting_bool(saved_layout_coordinates: dict[str, dict[str, Any]], key: str, default: bool) -> bool:
    """Return a boolean value from layout metadata with a safe default."""
    metadata = _layout_quote_metadata(saved_layout_coordinates)
    if key not in metadata:
        return default
    return _saved_bool(metadata.get(key))

def _preview_header_date_text(raw_date_text: str, include_time: bool) -> str:
    """Build designer preview text for the bill date block."""
    text = _plain_text(raw_date_text)
    if text.lower().startswith('date:'):
        date_part = text[5:].strip()
        formatted_date = append_print_time_to_date(date_part, include_time=include_time)
        return f'Date: {formatted_date}'
    return append_print_time_to_date(text, include_time=include_time)

def _bold_grand_total_from_settings(settings: dict[str, Any], saved_layout_coordinates: dict[str, dict[str, Any]]) -> bool:
    """Return whether the Grand Total amount should use the larger bold font."""
    metadata = _layout_quote_metadata(saved_layout_coordinates)
    if BOLD_GRAND_TOTAL_KEY in saved_layout_coordinates:
        return _saved_bool(saved_layout_coordinates.get(BOLD_GRAND_TOTAL_KEY))
    if BOLD_GRAND_TOTAL_KEY in metadata:
        return _saved_bool(metadata.get(BOLD_GRAND_TOTAL_KEY))
    if BOLD_GRAND_TOTAL_KEY in settings:
        return _saved_bool(settings.get(BOLD_GRAND_TOTAL_KEY))
    legacy_theme_values = (saved_layout_coordinates.get(THEME_KEY), metadata.get(THEME_KEY), metadata.get(THERMAL_THEME_KEY), settings.get(THEME_KEY), settings.get(THERMAL_THEME_KEY))
    return any((_plain_text(theme_value) == BOLD_TOTAL_THEME for theme_value in legacy_theme_values))

def _thermal_column_render_ids() -> tuple[str, ...]:
    """Return thermal columns with preferred barcode anchor before legacy fallback."""
    column_ids = [PREFERRED_BARCODE_COLUMN_ID]
    column_ids.extend((block_id for block_id in ITEM_COLUMN_ANCHOR_IDS if block_id != PREFERRED_BARCODE_COLUMN_ID))
    return tuple(dict.fromkeys(column_ids))

def _active_barcode_column_id(anchors: dict[str, dict[str, Any]]) -> str:
    """Return the barcode column id, preferring the restored col_bcd anchor."""
    if isinstance(anchors.get(PREFERRED_BARCODE_COLUMN_ID), dict):
        return PREFERRED_BARCODE_COLUMN_ID
    return LEGACY_BARCODE_COLUMN_ID

def _layout_setting_text(saved_layout_coordinates: dict[str, dict[str, Any]], key: str, default: str) -> str:
    """Return text from layout metadata or a conservative default."""
    metadata = _layout_quote_metadata(saved_layout_coordinates)
    return _plain_text(metadata.get(key)) or default

def _layout_setting_int(saved_layout_coordinates: dict[str, dict[str, Any]], key: str, default: int, minimum: int, maximum: int) -> int:
    """Return a clamped integer value from layout metadata."""
    metadata = _layout_quote_metadata(saved_layout_coordinates)
    try:
        value = int(metadata.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))

def _layout_setting_float(saved_layout_coordinates: dict[str, dict[str, Any]], key: str, default: float) -> float:
    """Return a persisted float layout value without shrinking valid sizes."""
    metadata = _layout_quote_metadata(saved_layout_coordinates)
    try:
        return float(metadata.get(key, default))
    except (TypeError, ValueError):
        return float(default)

def _layout_setting_choice(saved_layout_coordinates: dict[str, dict[str, Any]], key: str, choices: tuple[str, ...], default: str) -> str:
    """Return a saved metadata choice when it matches the allowed values."""
    value = _plain_text(_layout_quote_metadata(saved_layout_coordinates).get(key))
    return value if value in choices else default

def _active_thermal_theme(saved_layout_coordinates: dict[str, dict[str, Any]], settings: Optional[dict[str, Any]]=None) -> str:
    """Return the selected thermal theme from current and legacy metadata."""
    metadata = _layout_quote_metadata(saved_layout_coordinates)
    settings = settings or {}
    theme_candidates = (saved_layout_coordinates.get(THEME_KEY), metadata.get(THEME_KEY), metadata.get(THERMAL_THEME_KEY), settings.get(THEME_KEY), settings.get(THERMAL_THEME_KEY))
    for candidate in theme_candidates:
        theme_name = _plain_text(candidate)
        if theme_name:
            return theme_name
    return DEFAULT_THERMAL_THEME

def _thermal_width_px_from_metadata(saved_layout_coordinates: dict[str, dict[str, Any]]) -> int:
    """Return the persisted thermal paper width in designer pixels."""
    paper_size = _layout_setting_choice(saved_layout_coordinates, THERMAL_PAPER_SIZE_KEY, THERMAL_PAPER_SIZE_OPTIONS, _plain_text(_layout_quote_metadata(saved_layout_coordinates).get(PAPER_ROLL_SIZE_KEY)) or DEFAULT_PAPER_ROLL_SIZE)
    if paper_size == '4 Inch (100mm)':
        return 800
    if paper_size == 'Custom Size':
        return _layout_setting_int(saved_layout_coordinates, THERMAL_CUSTOM_WIDTH_PX_KEY, THERMAL_DIMENSIONS[0], 300, 1200)
    return THERMAL_DIMENSIONS[0]

def _thermal_width_mm_from_px(width_px: int) -> float:
    """Convert thermal designer pixels to physical millimeters at 203 DPI."""
    return max(1.0, float(width_px) / THERMAL_DPI * 25.4)

def _clip_monospace_field(value: Any, width: int) -> str:
    """Return a string clipped to a fixed monospace column width."""
    clean_value = _plain_text(value)
    if width <= 0:
        return clean_value
    return clean_value[:width]

def _item_barcode_text(item: dict[str, Any]) -> str:
    """Return the barcode value exposed by an item record."""
    return _plain_text(item.get('barcode'))

def _total_items_text(items: list[dict[str, Any]]) -> str:
    """Return the footer total item count, preferring quantity totals."""
    if not items:
        return 'Total Items: 0'
    quantities: list[float] = []
    for item in items:
        raw_quantity = item.get('quantity')
        if raw_quantity in (None, ''):
            quantities = []
            break
        try:
            quantities.append(float(raw_quantity))
        except (TypeError, ValueError):
            quantities = []
            break
    total_items = sum(quantities) if quantities else float(len(items))
    if total_items.is_integer():
        count_text = str(int(total_items))
    else:
        count_text = f'{total_items:.2f}'.rstrip('0').rstrip('.')
    return f'Total Items: {count_text}'

def _apply_font_rendering_hints(font: QFont) -> QFont:
    """Disable device hinting so preview and printer text metrics stay tight."""
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font

def _line_height_type(name: str, fallback: int) -> int:
    """Return a QTextBlockFormat line-height enum value across PySide builds."""
    line_height_types = getattr(QTextBlockFormat, 'LineHeightTypes', None)
    enum_value = getattr(line_height_types, name, None) if line_height_types else None
    if enum_value is None:
        enum_value = getattr(QTextBlockFormat, name, fallback)
    return int(getattr(enum_value, 'value', enum_value))

def _apply_tight_text_document(item: QGraphicsTextItem, align_center: bool=False, line_height_percent: float=100.0) -> None:
    """Remove document padding and apply explicit compact text line spacing."""
    document = item.document()
    document.setDocumentMargin(0.0)
    text_option = document.defaultTextOption()
    if align_center:
        text_option.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    document.setDefaultTextOption(text_option)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    block_format = QTextBlockFormat()
    block_format.setLineHeight(float(line_height_percent), _line_height_type('ProportionalHeight', 1))
    cursor.mergeBlockFormat(block_format)

def _font_from_block(block: dict[str, Any], fallback_family: str='Consolas') -> QFont:
    """Build the print font used for deterministic row-height calculations."""
    font_family = str(block.get('font_family', fallback_family) or fallback_family)
    font_size = int(float(block.get('font_size', 18) or 18))
    font = QFont(font_family, font_size)
    if font_family.lower() in {'consolas', 'courier', 'courier new'}:
        font.setStyleHint(QFont.StyleHint.Monospace)
    font.setBold(bool(block.get('bold', False)))
    return _apply_font_rendering_hints(font)

def _thermal_item_row_text(sl_no: Any, barcode: Any, quantity: Any, rate: Any, total: Any, item_name: Any, show_item_barcode: bool) -> str:
    """Return the two-line thermal item grid row used by preview and printing."""
    serial_text = _clip_monospace_field(sl_no, 4)
    barcode_text = _clip_monospace_field(barcode, THERMAL_ITEM_BARCODE_WIDTH) if show_item_barcode else ''
    item_name_text = _clip_monospace_field(item_name, THERMAL_ITEM_NAME_WIDTH)
    detail_line = f'{serial_text:<5}{barcode_text:<16}{_plain_text(quantity):>7}{_plain_text(rate):>9}{_plain_text(total):>9}'
    name_line = f'{THERMAL_ITEM_NAME_INDENT}{item_name_text}'
    return f'{detail_line}\n{name_line}'

def _is_bill_of_supply_invoice(invoice_data: dict[str, Any]) -> tuple[bool, bool]:
    """Return Bill of Supply state and whether it is forced by Composition GST."""
    company = invoice_data.get('company') or {}
    invoice = invoice_data.get('invoice') or {}
    gst_type = _plain_text(company.get('gst_type')).lower()
    sales_type = _plain_text(invoice.get('sales_type')).lower()
    is_composition = gst_type == 'composition'
    is_non_taxable = 'bill of supply' in sales_type or 'non-taxable' in sales_type or 'non taxable' in sales_type or _truthy_setting(invoice.get('non_taxable')) or _truthy_setting(invoice.get('is_non_taxable'))
    return (is_composition or is_non_taxable, is_composition)

def _is_interstate_invoice(invoice_data: dict[str, Any]) -> bool:
    """Return whether invoice metadata represents interstate supply."""
    invoice = invoice_data.get('invoice') or {}
    for value in (invoice.get('is_interstate'), invoice_data.get('is_interstate')):
        if isinstance(value, bool):
            return value
        if _truthy_setting(value):
            return True
    for field_name in ('nature', 'sale_type', 'sales_type', 'supply_type', 'form_of_sale'):
        normalized = _plain_text(invoice.get(field_name)).lower()
        compact = normalized.replace('-', '').replace('_', '').replace(' ', '')
        if not compact:
            continue
        if 'intra' in compact or 'local' in compact:
            return False
        if 'interstate' in compact or 'inter' in compact:
            return True
    return False

def _amount_to_words(value: Any) -> str:
    """Convert a numeric invoice amount into simple Indian currency words."""
    ones = ('Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen')
    tens = ('', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety')

    def below_hundred(number: int) -> str:
        """Return words for a number below one hundred."""
        if number < 20:
            return ones[number]
        return tens[number // 10] if number % 10 == 0 else f'{tens[number // 10]} {ones[number % 10]}'

    def below_thousand(number: int) -> str:
        """Return words for a number below one thousand."""
        if number < 100:
            return below_hundred(number)
        suffix = number % 100
        words = f'{ones[number // 100]} Hundred'
        return words if suffix == 0 else f'{words} {below_hundred(suffix)}'
    amount = round(_to_float(value), 2)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    parts = []
    for divisor, label in ((10000000, 'Crore'), (100000, 'Lakh'), (1000, 'Thousand')):
        chunk = rupees // divisor
        if chunk:
            parts.append(f'{below_thousand(chunk)} {label}')
            rupees %= divisor
    if rupees:
        parts.append(below_thousand(rupees))
    if not parts:
        parts.append('Zero')
    rupee_words = ' '.join(parts)
    if paise:
        return f'{rupee_words} Rupees and {below_hundred(paise)} Paise Only'
    return f'{rupee_words} Rupees Only'

def parse_layout_coordinates(raw_coordinates: str) -> dict[str, dict[str, Any]]:
    """Return saved layout coordinates or an empty mapping if invalid."""
    if not raw_coordinates:
        return {}
    try:
        parsed = json.loads(raw_coordinates)
    except (TypeError, json.JSONDecodeError) as exc:
        LOGGER.exception('Invalid print layout JSON: %s', exc)
        return {}
    if not isinstance(parsed, dict):
        return {}
    coordinates: dict[str, dict[str, Any]] = {}
    for block_id, values in parsed.items():
        if isinstance(block_id, str) and isinstance(values, dict):
            coordinates[block_id] = values
    return _migrate_header_anchor_coordinates(_purge_removed_layout_blocks(_purge_bcd_header_blocks(coordinates)))

def _migrate_header_anchor_coordinates(saved_layout_coordinates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map legacy Bill No/Date anchors onto stable header anchor ids."""
    coordinates = dict(saved_layout_coordinates)
    for legacy_block_id, canonical_block_id in LEGACY_HEADER_ANCHOR_ALIASES.items():
        if canonical_block_id in coordinates:
            continue
        legacy_values = coordinates.get(legacy_block_id)
        if isinstance(legacy_values, dict):
            coordinates[canonical_block_id] = dict(legacy_values)
    return coordinates

def is_thermal_print_settings(settings: dict[str, Any]) -> bool:
    """Return whether saved settings target an 80mm thermal printer."""
    printer_type = _plain_text(settings.get('printer_type'))
    default_format = _plain_text(settings.get('default_format'))
    paper_size = _plain_text(settings.get('paper_size'))
    return printer_type == 'Thermal' or default_format == 'Thermal' or paper_size in THERMAL_ALIASES

def _saved_bool(value: Any) -> bool:
    """Return a persisted boolean from native or text JSON values."""
    if isinstance(value, bool):
        return value
    return _truthy_setting(value)

def _ignore_value_control_wheel(widget: QWidget) -> None:
    """Allow parent scrolling without changing focused value controls."""

    def ignore_wheel_event(event: Any) -> None:
        event.ignore()
    widget.wheelEvent = ignore_wheel_event

def _is_bcd_header_block(block_id: str, values: dict[str, Any]) -> bool:
    """Return whether a saved layout entry is the removed BCD column header."""
    text = _plain_text(values.get('text'))
    if block_id == PREFERRED_BARCODE_COLUMN_ID:
        return text in {'', BCD_HEADER_TEXT}
    if block_id == LEGACY_BARCODE_COLUMN_ID:
        return True
    return text == BCD_HEADER_TEXT

def _purge_bcd_header_blocks(saved_layout_coordinates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Remove legacy BCD header blocks while preserving barcode data samples."""
    cleaned_coordinates: dict[str, dict[str, Any]] = {}
    barcode_sample: Optional[dict[str, Any]] = None
    for block_id, values in saved_layout_coordinates.items():
        if _is_bcd_header_block(block_id, values):
            if barcode_sample is None and _plain_text(values.get('type')) != 'deleted' and (PREFERRED_BARCODE_COLUMN_ID not in saved_layout_coordinates or block_id == PREFERRED_BARCODE_COLUMN_ID):
                barcode_sample = dict(values)
                barcode_sample['text'] = BARCODE_DATA_TEXT
                if 'y' in barcode_sample:
                    barcode_sample['y'] = _to_float(barcode_sample.get('y')) + SAMPLE_ITEM_ROW_Y_OFFSET
            continue
        cleaned_coordinates[block_id] = values
    if barcode_sample is not None:
        cleaned_coordinates[PREFERRED_BARCODE_COLUMN_ID] = barcode_sample
    return cleaned_coordinates

def _purge_removed_layout_blocks(saved_layout_coordinates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Remove retired designer anchors from persisted layout data."""
    return {block_id: values for block_id, values in saved_layout_coordinates.items() if block_id not in REMOVED_LAYOUT_BLOCK_IDS}

def _column_anchor_saved_coordinates(saved_layout_coordinates: dict[str, dict[str, Any]], defaults: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return saved coordinates with runtime defaults for new thermal columns."""
    coordinates = _purge_removed_layout_blocks(_purge_bcd_header_blocks({block_id: dict(values) for block_id, values in saved_layout_coordinates.items() if isinstance(values, dict)}))
    if any((block_id in coordinates for block_id in _thermal_column_render_ids())):
        return coordinates
    old_label = coordinates.get('item_table_label', {})
    old_header = coordinates.get('item_header', {})
    has_legacy_item_block = bool(old_label or old_header)
    if not has_legacy_item_block:
        return coordinates
    base_x = _to_float(old_header.get('x', old_label.get('x', 28)))
    header_y = _to_float(old_header.get('y', 386))
    row_y = _to_float(old_label.get('y', defaults.get('item_table', {}).get('y', 468)))
    font_size = _to_float(old_header.get('font_size', old_label.get('font_size', 20))) or 20
    anchor_offsets = {'col_sn': 0.0, 'col_product_name': 118.0, 'col_qty': 260.0, 'col_price': 335.0, 'col_total': 430.0}
    for block_id, x_offset in anchor_offsets.items():
        coordinates[block_id] = {'x': round(base_x + x_offset, 2), 'y': round(header_y, 2), 'font_size': round(font_size, 2), 'is_bold': True}
    if 'item_table' not in coordinates:
        table_default = defaults.get('item_table', {})
        coordinates['item_table'] = {'x': round(base_x, 2), 'y': round(row_y, 2), 'width': table_default.get('width', 520), 'height': table_default.get('height', 280)}
    return coordinates

def _thermal_saved_layout_coordinates(saved_layout_coordinates: dict[str, dict[str, Any]], defaults: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return thermal saved coordinates with legacy anchors safely migrated."""
    coordinates = _column_anchor_saved_coordinates(saved_layout_coordinates, defaults)
    if TOTALS_BLOCK_ID in coordinates:
        return coordinates
    legacy_totals = [coordinates.get(block_id) for block_id in THERMAL_TOTAL_FIELD_IDS if isinstance(coordinates.get(block_id), dict)]
    if not legacy_totals:
        return coordinates
    totals_default = defaults.get(TOTALS_BLOCK_ID, {})
    first_total = legacy_totals[0]
    grand_total = coordinates.get('grand_total', {})
    coordinates[TOTALS_BLOCK_ID] = {'x': first_total.get('x', totals_default.get('x', 28)), 'y': first_total.get('y', totals_default.get('y', 798)), 'font_size': first_total.get('font_size', totals_default.get('font_size', 20)), 'is_bold': _saved_bool(grand_total.get('is_bold', grand_total.get('bold', False)))}
    return coordinates

def _mark_preview_position(block: dict[str, Any], saved_x: Any=None, saved_y: Any=None) -> dict[str, Any]:
    """Tag a temporary canvas position so unchanged saves keep stored coordinates."""
    adjusted_block = dict(block)
    adjusted_block['_preview_shifted'] = True
    adjusted_block['_saved_x'] = block.get('x') if saved_x is None else saved_x
    adjusted_block['_saved_y'] = block.get('y') if saved_y is None else saved_y
    return adjusted_block

def _barcode_column_left_x(blocks: dict[str, dict[str, Any]]) -> float:
    """Return the left x-position used when the barcode column is hidden."""
    for block_id in BARCODE_COLUMN_BLOCK_IDS:
        block = blocks.get(block_id)
        if isinstance(block, dict) and 'x' in block:
            return _to_float(block.get('x'))
    product_block = blocks.get('col_product_name', {})
    return _to_float(product_block.get('x', 28.0))

def _apply_barcode_column_visibility(blocks: dict[str, dict[str, Any]], print_barcode_col: bool) -> dict[str, dict[str, Any]]:
    """Return blocks with barcode column hidden and item text shifted at render time."""
    if print_barcode_col:
        return blocks
    adjusted_blocks = {block_id: dict(block) for block_id, block in blocks.items() if block_id not in BARCODE_COLUMN_BLOCK_IDS}
    for sample_id, (anchor_id, _sample_text) in SAMPLE_ITEM_ROW_ELEMENTS.items():
        if anchor_id in BARCODE_COLUMN_BLOCK_IDS:
            adjusted_blocks.pop(sample_id, None)
    product_block = adjusted_blocks.get('col_product_name')
    if isinstance(product_block, dict):
        shifted_block = _mark_preview_position(product_block)
        shifted_block['x'] = _barcode_column_left_x(blocks)
        adjusted_blocks['col_product_name'] = shifted_block
    sample_product_block = adjusted_blocks.get('sample_product_name')
    if isinstance(sample_product_block, dict):
        shifted_sample = _mark_preview_position(sample_product_block)
        shifted_sample['x'] = _barcode_column_left_x(blocks)
        adjusted_blocks['sample_product_name'] = shifted_sample
    return adjusted_blocks

def _header_logo_bottom(saved_coordinates: dict[str, dict[str, Any]], item_table_y: float) -> Optional[float]:
    """Return the bottom edge of any header logo image in saved coordinates."""
    logo_bottom: Optional[float] = None
    for block_id, block in _image_layout_blocks(saved_coordinates).items():
        if block_id == SIGNATURE_IMAGE_BLOCK_ID:
            continue
        image_y = _to_float(block.get('y'))
        if image_y >= item_table_y:
            continue
        pixmap = QPixmap(_plain_text(block.get('path')))
        image_width = _to_float(block.get('width'))
        image_height = _to_float(block.get('height'))
        if image_height <= 0 and (not pixmap.isNull()) and (image_width > 0):
            image_height = float(pixmap.height()) * (image_width / max(1.0, float(pixmap.width())))
        if image_height <= 0:
            image_height = 80.0
        image_scale = max(0.1, min(5.0, _to_float(block.get('scale', 1.0)) or 1.0))
        bottom = image_y + image_height * image_scale
        logo_bottom = bottom if logo_bottom is None else max(logo_bottom, bottom)
    return logo_bottom

def _apply_logo_header_offset(blocks: dict[str, dict[str, Any]], saved_coordinates: dict[str, dict[str, Any]], show_company_logo: bool) -> dict[str, dict[str, Any]]:
    """Return blocks with header text shifted below a visible logo image."""
    if not show_company_logo:
        return blocks
    item_table_y = _to_float(blocks.get('item_table', {}).get('y', 0))
    logo_bottom = _header_logo_bottom(saved_coordinates, item_table_y)
    if logo_bottom is None:
        return blocks
    header_ids = ('company_name', 'address', 'phone', 'gstin', 'invoice_title', COMPOSITION_SUBHEADING_BLOCK_ID, 'header_quote', HEADER_BILL_NO_BLOCK_ID, HEADER_DATE_BLOCK_ID, 'customer_name')
    header_blocks = [blocks.get(block_id) for block_id in header_ids if isinstance(blocks.get(block_id), dict)]
    if not header_blocks:
        return blocks
    padding = 10.0
    min_header_y = min((_to_float(block.get('y')) for block in header_blocks))
    required_top = logo_bottom + padding
    if min_header_y >= required_top:
        return blocks
    y_offset = required_top - min_header_y
    adjusted_blocks = {block_id: dict(block) for block_id, block in blocks.items()}
    for block_id in header_ids:
        block = adjusted_blocks.get(block_id)
        if not isinstance(block, dict):
            continue
        shifted_block = _mark_preview_position(block)
        shifted_block['y'] = _to_float(block.get('y')) + y_offset
        adjusted_blocks[block_id] = shifted_block
    return adjusted_blocks

def _apply_tax_summary_font_size(blocks: dict[str, dict[str, Any]], saved_coordinates: dict[str, dict[str, Any]], settings: Optional[dict[str, Any]]=None) -> dict[str, dict[str, Any]]:
    """Return blocks with explicit tax-summary font size restored from metadata."""
    tax_block = blocks.get(FOOTER_TAX_SUMMARY_BLOCK_ID)
    if not isinstance(tax_block, dict):
        return blocks
    font_size = _layout_setting_float(saved_coordinates, TAX_SUMMARY_FONT_SIZE_KEY, _to_float(tax_block.get('font_size', 10.0)) or 10.0)
    if settings and TAX_SUMMARY_FONT_SIZE_KEY in settings:
        font_size = _to_float(settings.get(TAX_SUMMARY_FONT_SIZE_KEY)) or font_size
    adjusted_blocks = {block_id: dict(block) for block_id, block in blocks.items()}
    adjusted_blocks[FOOTER_TAX_SUMMARY_BLOCK_ID]['font_size'] = font_size
    adjusted_blocks[FOOTER_TAX_SUMMARY_BLOCK_ID][TAX_SUMMARY_FONT_SIZE_KEY] = font_size
    return adjusted_blocks

def _company_header_text_blocks(company: dict[str, Any]) -> dict[str, str]:
    """Return display text for company header anchors from one company record."""
    company_name = _plain_text(company.get('company_name')) or _plain_text(company.get('business_name')) or 'Company Name'
    address = _plain_text(company.get('address')) or 'Company Address'
    phone = _plain_text(company.get('phone')) or _plain_text(company.get('phone_number'))
    gstin = _plain_text(company.get('gstin'))
    return {'company_name': company_name, 'address': address, 'phone': f'Phone: {phone}' if phone else 'Phone:', 'gstin': f'GSTIN: {gstin}' if gstin else 'GSTIN:'}

def default_layout_blocks(paper_size: str, paper_dimensions: tuple[int, int], company_data: Optional[dict[str, Any]]=None) -> dict[str, dict[str, Any]]:
    """Return default WYSIWYG block positions for a paper size."""
    width, _height = paper_dimensions
    company_header = _company_header_text_blocks(company_data or {})
    if paper_size == THERMAL_PAPER_SIZE:
        content_width = width - 56
        thermal_font = 'Consolas'
        return {'company_name': {'text': company_header['company_name'], 'x': 28, 'y': 28, 'font_size': 24, 'text_width': content_width, 'bold': True, 'align_center': True, 'font_family': thermal_font}, 'address': {'text': company_header['address'], 'x': 28, 'y': 66, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': thermal_font}, 'phone': {'text': company_header['phone'], 'x': 28, 'y': 98, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': thermal_font}, 'gstin': {'text': company_header['gstin'], 'x': 28, 'y': 130, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': thermal_font}, 'invoice_title': {'text': 'TAX INVOICE', 'x': 28, 'y': 168, 'font_size': 24, 'text_width': content_width, 'bold': True, 'align_center': True, 'font_family': thermal_font}, COMPOSITION_SUBHEADING_BLOCK_ID: {'text': '', 'x': 28, 'y': 200, 'font_size': 16, 'text_width': content_width, 'align_center': True, 'font_family': thermal_font}, 'header_quote': {'text': '', 'x': 28, 'y': 214, 'font_size': 18, 'text_width': content_width, 'align_center': True, 'font_family': thermal_font}, HEADER_BILL_NO_BLOCK_ID: {'text': 'Bill No: 1001', 'x': 28, 'y': 238, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, HEADER_DATE_BLOCK_ID: {'text': 'Date: 09-Jun-2026', 'x': 28, 'y': 270, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, 'customer_name': {'text': 'Customer: Cash Customer', 'x': 28, 'y': 302, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, 'item_table': {'x': 28, 'y': 468, 'width': content_width, 'height': 280}, 'separator_above_items': {'text': '--------------------------------', 'x': 28, 'y': 354, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, 'col_sn': {'text': ITEM_COLUMN_ANCHORS['col_sn'], 'x': 28, 'y': 386, 'font_size': 20, 'bold': True, 'font_family': thermal_font}, 'col_qty': {'text': ITEM_COLUMN_ANCHORS['col_qty'], 'x': 288, 'y': 386, 'font_size': 20, 'bold': True, 'font_family': thermal_font}, 'col_price': {'text': ITEM_COLUMN_ANCHORS['col_price'], 'x': 362, 'y': 386, 'font_size': 20, 'bold': True, 'font_family': thermal_font}, 'col_total': {'text': ITEM_COLUMN_ANCHORS['col_total'], 'x': 456, 'y': 386, 'font_size': 20, 'bold': True, 'font_family': thermal_font}, 'col_product_name': {'text': ITEM_COLUMN_ANCHORS['col_product_name'], 'x': 146, 'y': 386, 'font_size': 18, 'text_width': content_width, 'font_family': thermal_font}, PREFERRED_BARCODE_COLUMN_ID: {'text': BARCODE_DATA_TEXT, 'x': 58, 'y': 428, 'font_size': 18, 'font_family': thermal_font}, 'separator_below_items': {'text': '--------------------------------', 'x': 28, 'y': 418, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, ITEM_BARCODE_PLACEHOLDER_BLOCK_ID: {'text': '32651', 'x': 58, 'y': 526, 'font_size': 18, 'text_width': content_width - 30, 'font_family': thermal_font}, 'separator_above_totals': {'text': '--------------------------------', 'x': 28, 'y': 760, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, TOTAL_ITEMS_BLOCK_ID: {'text': 'Total Items: 2', 'x': 28, 'y': 798, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, TOTALS_BLOCK_ID: {'text': THERMAL_TOTALS_SAMPLE_TEXT, 'x': 28, 'y': 830, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, FOOTER_TAX_SUMMARY_BLOCK_ID: {'text': 'GST% | Net Amt | CGST | SGST | Cess', 'x': 28, 'y': 980, 'font_size': 10, 'text_width': content_width, 'font_family': thermal_font}, 'amount_in_words': {'text': 'Amount in Words: Five Hundred Rupees Only', 'x': 28, 'y': 1012, 'font_size': 20, 'text_width': content_width, 'font_family': thermal_font}, 'footer_terms': {'text': 'Thank you for your business.', 'x': 28, 'y': 1100, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': thermal_font}, SIGNATURE_PLACEHOLDER_BLOCK_ID: {'text': '[Signature / Stamp]', 'x': 318, 'y': 1180, 'font_size': 20, 'text_width': 220, 'align_center': True, 'font_family': thermal_font}}
    content_width = width - 120
    return {'company_name': {'text': company_header['company_name'], 'x': 60, 'y': 50, 'font_size': 20, 'text_width': content_width, 'bold': True, 'align_center': True}, 'address': {'text': company_header['address'], 'x': 60, 'y': 88, 'font_size': 12, 'text_width': content_width, 'align_center': True}, 'phone': {'text': company_header['phone'], 'x': 60, 'y': 116, 'font_size': 12, 'text_width': content_width, 'align_center': True}, 'gstin': {'text': company_header['gstin'], 'x': 60, 'y': 144, 'font_size': 12, 'text_width': content_width, 'align_center': True}, 'invoice_title': {'text': 'TAX INVOICE', 'x': 60, 'y': 178, 'font_size': 15, 'text_width': content_width, 'bold': True, 'align_center': True}, COMPOSITION_SUBHEADING_BLOCK_ID: {'text': '', 'x': 60, 'y': 208, 'font_size': 10, 'text_width': content_width, 'align_center': True}, 'header_quote': {'text': '', 'x': 60, 'y': 212, 'font_size': 11, 'text_width': content_width, 'align_center': True}, HEADER_BILL_NO_BLOCK_ID: {'text': 'Bill No: 1001', 'x': 60, 'y': 230, 'font_size': 12, 'text_width': 260}, HEADER_DATE_BLOCK_ID: {'text': 'Date: 09-Jun-2026', 'x': 470, 'y': 230, 'font_size': 12, 'text_width': 260}, 'customer_name': {'text': 'Customer: Cash Customer', 'x': 60, 'y': 262, 'font_size': 12, 'text_width': 360}, 'item_table': {'x': 60, 'y': 330, 'width': content_width, 'height': 330}, 'separator_above_items': {'text': '--------------------------------', 'x': 60, 'y': 300, 'font_size': 11, 'text_width': content_width, 'font_family': 'Consolas'}, 'item_header': {'text': 'SL  Item                         HSN       Qty      Rate      Total', 'x': 60, 'y': 330, 'font_size': 11, 'text_width': content_width, 'bold': True, 'font_family': 'Consolas'}, 'separator_below_items': {'text': '--------------------------------', 'x': 60, 'y': 360, 'font_size': 11, 'text_width': content_width, 'font_family': 'Consolas'}, 'item_table_label': {'text': '1   Sample Item                 HSN001       2.00     250.00     500.00', 'x': 60, 'y': 398, 'font_size': 11, 'text_width': content_width, 'font_family': 'Consolas'}, ITEM_BARCODE_PLACEHOLDER_BLOCK_ID: {'text': '123456789012', 'x': 85, 'y': 424, 'font_size': 10, 'text_width': content_width - 25, 'font_family': 'Consolas'}, 'separator_above_totals': {'text': '--------------------------------', 'x': 470, 'y': 720, 'font_size': 11, 'text_width': 260, 'font_family': 'Consolas'}, TOTAL_ITEMS_BLOCK_ID: {'text': 'Total Items: 2', 'x': 470, 'y': 750, 'font_size': 12, 'text_width': 260}, 'subtotal': {'text': 'Subtotal: Rs. 500.00', 'x': 470, 'y': 778, 'font_size': 12, 'text_width': 260}, 'discount': {'text': 'Discount: Rs. 0.00', 'x': 470, 'y': 806, 'font_size': 12, 'text_width': 260}, 'tax': {'text': 'Tax: Rs. 0.00', 'x': 470, 'y': 834, 'font_size': 12, 'text_width': 260}, 'grand_total': {'text': 'Grand Total: Rs. 500.00', 'x': 470, 'y': 868, 'font_size': 13, 'text_width': 260, 'bold': True}, 'amount_received': {'text': 'Amount Received: Rs. 500.00', 'x': 470, 'y': 900, 'font_size': 12, 'text_width': 260}, 'balance': {'text': 'Balance: Rs. 0.00', 'x': 470, 'y': 928, 'font_size': 12, 'text_width': 260}, FOOTER_TAX_SUMMARY_BLOCK_ID: {'text': 'GST% | Net Amt | CGST | SGST | Cess', 'x': 60, 'y': 948, 'font_size': 8, 'text_width': content_width, 'font_family': 'Consolas'}, 'amount_in_words': {'text': 'Amount in Words: Five Hundred Rupees Only', 'x': 60, 'y': 968, 'font_size': 12, 'text_width': content_width}, 'footer_terms': {'text': 'Thank you for your business.', 'x': 60, 'y': 1010, 'font_size': 12, 'text_width': content_width, 'align_center': True}, SIGNATURE_PLACEHOLDER_BLOCK_ID: {'text': '[Signature / Stamp]', 'x': 560, 'y': 1055, 'font_size': 12, 'text_width': 170, 'align_center': True}}

def thermal_theme_layout_templates(paper_dimensions: tuple[int, int]) -> dict[str, dict[str, dict[str, Any]]]:
    """Return thermal layout templates keyed by the user-facing theme name."""
    width, _height = paper_dimensions
    content_x = 28.0
    content_width = max(1.0, float(width) - content_x * 2)
    col_total_x = max(content_x, float(width) - 120.0)
    col_price_x = max(content_x, col_total_x - 100.0)
    col_qty_x = max(content_x, col_price_x - 74.0)
    col_product_x = min(content_x + 118.0, max(content_x, col_qty_x - 118.0))
    signature_x = max(content_x, float(width) - 258.0)

    def settings(theme_name: str, row_spacing: int) -> dict[str, Any]:
        """Return metadata stored with a theme without clearing user options."""
        return {THEME_KEY: theme_name, THERMAL_THEME_KEY: theme_name, 'row_spacing': row_spacing}

    def centered_header(y_start: float, title_y: float) -> dict[str, dict[str, Any]]:
        """Return centered company header anchors used by receipt themes."""
        return {'company_name': {'x': content_x, 'y': y_start, 'font_size': 24, 'text_width': content_width, 'is_bold': True, 'align_center': True, 'font_family': 'Consolas'}, 'address': {'x': content_x, 'y': y_start + 38, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'phone': {'x': content_x, 'y': y_start + 70, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'gstin': {'x': content_x, 'y': y_start + 102, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'invoice_title': {'x': content_x, 'y': title_y, 'font_size': 24, 'text_width': content_width, 'is_bold': True, 'align_center': True, 'font_family': 'Consolas'}, COMPOSITION_SUBHEADING_BLOCK_ID: {'x': content_x, 'y': title_y + 32, 'font_size': 16, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'header_quote': {'x': content_x, 'y': title_y + 46, 'font_size': 18, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}}

    def item_columns(y_pos: float, font_size: float=20.0) -> dict[str, dict[str, Any]]:
        """Return standard thermal column anchors for a receipt theme."""
        return {'col_sn': {'x': content_x, 'y': y_pos, 'font_size': font_size, 'is_bold': True, 'font_family': 'Consolas'}, 'col_product_name': {'x': col_product_x, 'y': y_pos, 'font_size': max(8.0, font_size - 2.0), 'text_width': content_width, 'font_family': 'Consolas'}, 'col_qty': {'x': col_qty_x, 'y': y_pos, 'font_size': font_size, 'is_bold': True, 'font_family': 'Consolas'}, 'col_price': {'x': col_price_x, 'y': y_pos, 'font_size': font_size, 'is_bold': True, 'font_family': 'Consolas'}, 'col_total': {'x': col_total_x, 'y': y_pos, 'font_size': font_size, 'is_bold': True, 'font_family': 'Consolas'}}
    classic_theme = {LAYOUT_SETTINGS_BLOCK_ID: settings('Classic POS', 6), 'company_name': {'x': content_x, 'y': 26, 'font_size': 24, 'text_width': content_width, 'is_bold': True, 'align_center': False, 'font_family': 'Consolas'}, 'address': {'x': content_x, 'y': 64, 'font_size': 20, 'text_width': content_width, 'align_center': False, 'font_family': 'Consolas'}, 'phone': {'x': content_x, 'y': 96, 'font_size': 20, 'text_width': content_width, 'align_center': False, 'font_family': 'Consolas'}, 'gstin': {'x': content_x, 'y': 128, 'font_size': 20, 'text_width': content_width, 'align_center': False, 'font_family': 'Consolas'}, 'invoice_title': {'x': content_x, 'y': 168, 'font_size': 24, 'text_width': content_width, 'is_bold': True, 'align_center': False, 'font_family': 'Consolas'}, COMPOSITION_SUBHEADING_BLOCK_ID: {'x': content_x, 'y': 200, 'font_size': 16, 'text_width': content_width, 'align_center': False, 'font_family': 'Consolas'}, 'header_quote': {'x': content_x, 'y': 214, 'font_size': 18, 'text_width': content_width, 'align_center': False, 'font_family': 'Consolas'}, HEADER_BILL_NO_BLOCK_ID: {'x': content_x, 'y': 238, 'font_size': 20, 'font_family': 'Consolas'}, HEADER_DATE_BLOCK_ID: {'x': content_x, 'y': 270, 'font_size': 20, 'font_family': 'Consolas'}, 'customer_name': {'x': content_x, 'y': 302, 'font_size': 20, 'font_family': 'Consolas'}, 'item_table': {'x': content_x, 'y': 468, 'width': content_width, 'height': 280}, 'separator_above_items': {'x': content_x, 'y': 354, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, **item_columns(386), 'separator_below_items': {'x': content_x, 'y': 418, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, ITEM_BARCODE_PLACEHOLDER_BLOCK_ID: {'x': content_x + 30, 'y': 526, 'font_size': 18, 'font_family': 'Consolas'}, 'separator_above_totals': {'x': content_x, 'y': 760, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, TOTAL_ITEMS_BLOCK_ID: {'x': content_x, 'y': 798, 'font_size': 20, 'font_family': 'Consolas'}, TOTALS_BLOCK_ID: {'x': content_x, 'y': 830, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, FOOTER_TAX_SUMMARY_BLOCK_ID: {'x': content_x, 'y': 980, 'font_size': 10, 'text_width': content_width, 'font_family': 'Consolas'}, 'amount_in_words': {'x': content_x, 'y': 1012, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, 'footer_terms': {'x': content_x, 'y': 1100, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, SIGNATURE_PLACEHOLDER_BLOCK_ID: {'x': signature_x, 'y': 1180, 'font_size': 20, 'text_width': 220, 'align_center': True, 'font_family': 'Consolas'}}
    elegant_theme = {LAYOUT_SETTINGS_BLOCK_ID: settings('Elegant Bill', 14), **centered_header(30, 178), HEADER_BILL_NO_BLOCK_ID: {'x': content_x, 'y': 238, 'font_size': 20, 'font_family': 'Consolas'}, HEADER_DATE_BLOCK_ID: {'x': content_x, 'y': 272, 'font_size': 20, 'font_family': 'Consolas'}, 'customer_name': {'x': content_x, 'y': 306, 'font_size': 20, 'font_family': 'Consolas'}, 'item_table': {'x': content_x, 'y': 504, 'width': content_width, 'height': 300}, 'separator_above_items': {'x': content_x, 'y': 370, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, **item_columns(406), 'separator_below_items': {'x': content_x, 'y': 444, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, ITEM_BARCODE_PLACEHOLDER_BLOCK_ID: {'x': content_x + 30, 'y': 572, 'font_size': 18, 'font_family': 'Consolas'}, 'separator_above_totals': {'x': content_x, 'y': 840, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, TOTAL_ITEMS_BLOCK_ID: {'x': content_x, 'y': 882, 'font_size': 20, 'font_family': 'Consolas'}, TOTALS_BLOCK_ID: {'x': content_x, 'y': 918, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, FOOTER_TAX_SUMMARY_BLOCK_ID: {'x': content_x, 'y': 1088, 'font_size': 10, 'text_width': content_width, 'font_family': 'Consolas'}, 'amount_in_words': {'x': content_x, 'y': 1122, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, 'footer_terms': {'x': content_x, 'y': 1216, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, SIGNATURE_PLACEHOLDER_BLOCK_ID: {'x': signature_x, 'y': 1300, 'font_size': 20, 'text_width': 220, 'align_center': True, 'font_family': 'Consolas'}}
    compact_theme = {LAYOUT_SETTINGS_BLOCK_ID: settings('Compact Retail', 2), 'company_name': {'x': content_x, 'y': 16, 'font_size': 22, 'text_width': content_width, 'is_bold': True, 'align_center': True, 'font_family': 'Consolas'}, 'address': {'x': content_x, 'y': 48, 'font_size': 17, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'phone': {'x': content_x, 'y': 74, 'font_size': 17, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'gstin': {'x': content_x, 'y': 100, 'font_size': 17, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'invoice_title': {'x': content_x, 'y': 130, 'font_size': 22, 'text_width': content_width, 'is_bold': True, 'align_center': True, 'font_family': 'Consolas'}, COMPOSITION_SUBHEADING_BLOCK_ID: {'x': content_x, 'y': 158, 'font_size': 14, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, 'header_quote': {'x': content_x, 'y': 172, 'font_size': 16, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, HEADER_BILL_NO_BLOCK_ID: {'x': content_x, 'y': 194, 'font_size': 18, 'font_family': 'Consolas'}, HEADER_DATE_BLOCK_ID: {'x': content_x, 'y': 220, 'font_size': 18, 'font_family': 'Consolas'}, 'customer_name': {'x': content_x, 'y': 246, 'font_size': 18, 'font_family': 'Consolas'}, 'item_table': {'x': content_x, 'y': 354, 'width': content_width, 'height': 250}, 'separator_above_items': {'x': content_x, 'y': 286, 'font_size': 18, 'text_width': content_width, 'font_family': 'Consolas'}, **item_columns(314, 18), 'separator_below_items': {'x': content_x, 'y': 342, 'font_size': 18, 'text_width': content_width, 'font_family': 'Consolas'}, ITEM_BARCODE_PLACEHOLDER_BLOCK_ID: {'x': content_x + 30, 'y': 404, 'font_size': 16, 'font_family': 'Consolas'}, 'separator_above_totals': {'x': content_x, 'y': 678, 'font_size': 18, 'text_width': content_width, 'font_family': 'Consolas'}, TOTAL_ITEMS_BLOCK_ID: {'x': content_x, 'y': 708, 'font_size': 18, 'font_family': 'Consolas'}, TOTALS_BLOCK_ID: {'x': content_x, 'y': 736, 'font_size': 18, 'text_width': content_width, 'font_family': 'Consolas'}, FOOTER_TAX_SUMMARY_BLOCK_ID: {'x': content_x, 'y': 884, 'font_size': 9, 'text_width': content_width, 'font_family': 'Consolas'}, 'amount_in_words': {'x': content_x, 'y': 914, 'font_size': 18, 'text_width': content_width, 'font_family': 'Consolas'}, 'footer_terms': {'x': content_x, 'y': 988, 'font_size': 18, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, SIGNATURE_PLACEHOLDER_BLOCK_ID: {'x': signature_x, 'y': 1046, 'font_size': 18, 'text_width': 220, 'align_center': True, 'font_family': 'Consolas'}}
    modern_theme = {LAYOUT_SETTINGS_BLOCK_ID: settings('Modern Invoice', 8), **centered_header(24, 164), HEADER_BILL_NO_BLOCK_ID: {'x': content_x, 'y': 226, 'font_size': 20, 'font_family': 'Consolas'}, HEADER_DATE_BLOCK_ID: {'x': max(content_x, float(width) - 246.0), 'y': 226, 'font_size': 20, 'font_family': 'Consolas'}, 'customer_name': {'x': content_x, 'y': 264, 'font_size': 20, 'font_family': 'Consolas'}, 'item_table': {'x': content_x, 'y': 454, 'width': content_width, 'height': 286}, 'separator_above_items': {'x': content_x, 'y': 332, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, **item_columns(368), 'separator_below_items': {'x': content_x, 'y': 402, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, ITEM_BARCODE_PLACEHOLDER_BLOCK_ID: {'x': content_x + 30, 'y': 514, 'font_size': 18, 'font_family': 'Consolas'}, 'separator_above_totals': {'x': content_x, 'y': 750, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, TOTAL_ITEMS_BLOCK_ID: {'x': content_x, 'y': 788, 'font_size': 20, 'font_family': 'Consolas'}, TOTALS_BLOCK_ID: {'x': content_x, 'y': 820, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, FOOTER_TAX_SUMMARY_BLOCK_ID: {'x': content_x, 'y': 972, 'font_size': 10, 'text_width': content_width, 'font_family': 'Consolas'}, 'amount_in_words': {'x': content_x, 'y': 1006, 'font_size': 20, 'text_width': content_width, 'font_family': 'Consolas'}, 'footer_terms': {'x': content_x, 'y': 1092, 'font_size': 20, 'text_width': content_width, 'align_center': True, 'font_family': 'Consolas'}, SIGNATURE_PLACEHOLDER_BLOCK_ID: {'x': signature_x, 'y': 1172, 'font_size': 20, 'text_width': 220, 'align_center': True, 'font_family': 'Consolas'}}
    return {'Classic POS': classic_theme, 'Elegant Bill': elegant_theme, 'Compact Retail': compact_theme, 'Modern Invoice': modern_theme}

def merge_layout_block(block_id: str, defaults: dict[str, Any], saved_layout_coordinates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Overlay saved coordinates and font size onto one default block."""
    merged = dict(defaults)
    saved = saved_layout_coordinates.get(block_id, {})
    if not isinstance(saved, dict):
        return merged
    coordinate_keys = ('x', 'y', 'font_size')
    if 'text' not in defaults:
        coordinate_keys = ('x', 'y', 'font_size', 'width', 'height')
    for key in coordinate_keys:
        if key not in saved:
            continue
        try:
            merged[key] = float(saved[key])
        except (TypeError, ValueError):
            continue
    if 'is_bold' in saved:
        merged['bold'] = _saved_bool(saved.get('is_bold'))
    elif 'bold' in saved:
        merged['bold'] = _saved_bool(saved.get('bold'))
    if 'scale' in saved:
        try:
            merged['scale'] = max(0.1, min(5.0, float(saved['scale'])))
        except (TypeError, ValueError):
            pass
    for key in ('align_center', 'font_family'):
        if key in saved:
            merged[key] = saved[key]
    if 'text_width' in saved:
        try:
            merged['text_width'] = max(1.0, float(saved['text_width']))
        except (TypeError, ValueError):
            pass
    text_persisted_blocks = {SIGNATURE_PLACEHOLDER_BLOCK_ID, PREFERRED_BARCODE_COLUMN_ID}
    if block_id in text_persisted_blocks and 'text' in saved:
        merged['text'] = _plain_text(saved.get('text')) or defaults.get('text', '')
    return merged

def _saved_thermal_column_blocks(saved_layout_coordinates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return legacy/saved thermal column anchors absent from defaults."""
    column_blocks: dict[str, dict[str, Any]] = {}
    for block_id in _thermal_column_render_ids():
        saved = saved_layout_coordinates.get(block_id)
        if not isinstance(saved, dict):
            continue
        column_blocks[block_id] = merge_layout_block(block_id, {'text': BARCODE_DATA_TEXT if block_id == PREFERRED_BARCODE_COLUMN_ID else ITEM_COLUMN_ANCHORS.get(block_id, ''), 'font_family': 'Consolas'}, saved_layout_coordinates)
    return column_blocks

def _thermal_sample_row_blocks(blocks: dict[str, dict[str, Any]], saved_layout_coordinates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return independent draggable sample-row blocks under thermal headers."""
    sample_blocks: dict[str, dict[str, Any]] = {}
    for sample_id, (anchor_id, sample_text) in SAMPLE_ITEM_ROW_ELEMENTS.items():
        anchor = blocks.get(anchor_id, {})
        existing_sample = blocks.get(sample_id, {})
        if not anchor and (not isinstance(saved_layout_coordinates.get(sample_id), dict)):
            continue
        default_block = {'text': sample_text, 'x': anchor.get('x', 28), 'y': float(anchor.get('y', 386)) + SAMPLE_ITEM_ROW_Y_OFFSET, 'font_size': anchor.get('font_size', 18), 'font_family': anchor.get('font_family', 'Consolas')}
        if isinstance(existing_sample, dict):
            default_block.update(existing_sample)
            default_block['text'] = sample_text
        sample_blocks[sample_id] = merge_layout_block(sample_id, default_block, saved_layout_coordinates)
    return sample_blocks

def _sample_block_for_column(block_id: str, sample_anchors: dict[str, dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return the saved sample-row block that represents one thermal column."""
    for sample_id, (anchor_id, _sample_text) in SAMPLE_ITEM_ROW_ELEMENTS.items():
        if anchor_id == block_id and isinstance(sample_anchors.get(sample_id), dict):
            return sample_anchors[sample_id]
    if block_id in BARCODE_COLUMN_BLOCK_IDS and isinstance(sample_anchors.get(PREFERRED_BARCODE_COLUMN_ID), dict):
        return sample_anchors[PREFERRED_BARCODE_COLUMN_ID]
    if block_id in BARCODE_COLUMN_BLOCK_IDS and isinstance(sample_anchors.get('sample_bcd'), dict):
        return sample_anchors['sample_bcd']
    return None

def _base_sample_row_reference(sample_anchors: dict[str, dict[str, Any]]) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    """Return the preferred saved sample anchor used as the first item-row Y."""
    for sample_id in THERMAL_SAMPLE_ROW_PRIORITY:
        canonical_id = LEGACY_SAMPLE_ITEM_ROW_ALIASES.get(sample_id, sample_id)
        sample = sample_anchors.get(sample_id) or sample_anchors.get(canonical_id)
        if isinstance(sample, dict) and 'y' in sample:
            return (canonical_id, sample)
    return (None, None)

def _paper_size_from_settings(settings: dict[str, Any]) -> str:
    """Map saved settings to the designer paper size label."""
    if is_thermal_print_settings(settings):
        return THERMAL_PAPER_SIZE
    return A4_PAPER_SIZE

def _selected_dimensions_for_paper(paper_size: str) -> tuple[int, int]:
    """Return scene dimensions for a normalized paper size label."""
    if paper_size == THERMAL_PAPER_SIZE:
        return THERMAL_DIMENSIONS
    return A4_DIMENSIONS

def _add_text_item(scene: QGraphicsScene, text: Any, x_pos: float, y_pos: float, font_size: float, text_width: Optional[float]=None, bold: bool=False, block_id: str='', font_family: str='Arial', align_center: bool=False, word_wrap: bool=False) -> Optional[QGraphicsTextItem]:
    """Add non-empty visible text to a graphics scene."""
    clean_text = _plain_text(text)
    if not clean_text:
        return None
    item = QGraphicsTextItem(clean_text)
    font = QFont(font_family or 'Arial', int(font_size or 12))
    if (font_family or '').lower() in {'consolas', 'courier', 'courier new'}:
        font.setStyleHint(QFont.StyleHint.Monospace)
    font.setBold(bool(bold))
    _apply_font_rendering_hints(font)
    item.setFont(font)
    item.setDefaultTextColor(QColor('#111827'))
    if word_wrap and text_width is not None:
        try:
            item.setTextWidth(max(1.0, float(text_width)))
        except (TypeError, ValueError):
            item.setTextWidth(-1.0)
    else:
        item.setTextWidth(-1.0)
    _apply_tight_text_document(item, align_center)
    item.setPos(float(x_pos), float(y_pos))
    if block_id:
        item.setData(0, block_id)
    scene.addItem(item)
    return item

def _add_footer_separator_line(scene: QGraphicsScene, paper_width: float, y_pos: float, block_id: str='grand_total_separator') -> QGraphicsLineItem:
    """Draw a strong paper-width separator for emphasized footer totals."""
    right_edge = max(10.0, float(paper_width) - 10.0)
    item = QGraphicsLineItem(10.0, float(y_pos), right_edge, float(y_pos))
    item.setPen(QPen(QColor('#111827'), 1.4, Qt.PenStyle.SolidLine))
    item.setData(0, block_id)
    scene.addItem(item)
    return item

def _add_gst_tax_separator_line(scene: QGraphicsScene, paper_width: float, y_pos: float, block_id: str) -> QGraphicsLineItem:
    """Draw a dashed receipt-width separator for the GST breakdown table."""
    right_edge = max(10.0, float(paper_width) - 10.0)
    item = QGraphicsLineItem(10.0, float(y_pos), right_edge, float(y_pos))
    item.setPen(QPen(QColor('#111827'), 1.0, Qt.PenStyle.DashLine))
    item.setData(0, block_id)
    scene.addItem(item)
    return item

def _tax_summary_amounts(item: dict[str, Any]) -> tuple[float, float]:
    """Return taxable and stored tax values, deriving net only when needed."""
    net_amt = _to_float(item.get('net_value') or item.get('taxable_amount') or item.get('taxable_value') or item.get('net_amt'))
    tax_amt = _to_float(item.get('tax_amount') or item.get('gst_amount') or item.get('tax'))
    split_gst_amt = sum((_to_float(item.get(field_name)) for field_name in ('cgst_amount', 'sgst_amount', 'igst_amount', 'cess_amount')))
    if tax_amt <= 0.0 and split_gst_amt > 0.0:
        tax_amt = split_gst_amt
    gst_rate, cess_rate = _tax_summary_rates(item)
    total_rate = gst_rate + cess_rate
    grand_total = _to_float(item.get('grand_total') or item.get('line_total'))
    if net_amt <= 0.0 and grand_total > 0.0 and (tax_amt > 0.0):
        net_amt = max(0.0, grand_total - tax_amt)
    if net_amt <= 0.0 and grand_total > 0.0 and (total_rate > 0.0):
        net_amt = grand_total / (1.0 + total_rate / 100.0)
    if net_amt <= 0.0 and grand_total > 0.0 and (total_rate <= 0.0):
        net_amt = grand_total
    return (max(0.0, net_amt), max(0.0, tax_amt))

def _tax_summary_rates(item: dict[str, Any]) -> tuple[float, float]:
    """Return explicit GST and cess percentages without splitting totals."""
    gst_rate = _to_float(item.get('gst_rate') or item.get('gst_percent'))
    split_gst_rate = sum((_to_float(item.get(field_name)) for field_name in ('cgst', 'sgst', 'igst')))
    if gst_rate <= 0.0 and split_gst_rate > 0.0:
        gst_rate = split_gst_rate
    if gst_rate <= 0.0:
        gst_rate = _to_float(item.get('tax_percent'))
    cess_rate = _to_float(item.get('cess_rate') or item.get('cess_percent') or item.get('cess'))
    return (max(0.0, round(gst_rate, 2)), max(0.0, round(cess_rate, 2)))

def _build_tax_summary(items: list[dict[str, Any]]) -> dict[tuple[float, float], dict[str, float]]:
    """Group taxable values by base GST rate and cess rate."""
    tax_summary: dict[tuple[float, float], dict[str, float]] = {}
    for item in items:
        gst_rate, cess_rate = _tax_summary_rates(item)
        net_amt, tax_amt = _tax_summary_amounts(item)
        if net_amt <= 0.0 and tax_amt <= 0.0:
            continue
        cgst_amt = _to_float(item.get('cgst_amount'))
        sgst_amt = _to_float(item.get('sgst_amount'))
        igst_amt = _to_float(item.get('igst_amount'))
        base_gst_amt = cgst_amt + sgst_amt + igst_amt
        if base_gst_amt <= 0.0 and net_amt > 0.0 and (gst_rate > 0.0):
            base_gst_amt = net_amt * (gst_rate / 100.0)
            if igst_amt > 0.0:
                igst_amt = base_gst_amt
            else:
                cgst_amt = base_gst_amt / 2.0
                sgst_amt = base_gst_amt / 2.0
        cess_amt = _to_float(item.get('cess_amount'))
        if cess_amt <= 0.0 and net_amt > 0.0 and (cess_rate > 0.0):
            cess_amt = net_amt * (cess_rate / 100.0)
        tax_key = (gst_rate, cess_rate)
        summary_row = tax_summary.setdefault(tax_key, {'net_amt': 0.0, 'base_gst_rate': gst_rate, 'cess_rate': cess_rate, 'cgst_amt': 0.0, 'sgst_amt': 0.0, 'igst_amt': 0.0, 'cess_amt': 0.0, 'total_tax': 0.0})
        summary_row['net_amt'] += net_amt
        summary_row['cgst_amt'] += cgst_amt
        summary_row['sgst_amt'] += sgst_amt
        summary_row['igst_amt'] += igst_amt
        summary_row['cess_amt'] += cess_amt
        summary_row['total_tax'] += base_gst_amt + cess_amt
    return tax_summary

def _format_gst_rate(value: float) -> str:
    """Format a GST percentage without noisy trailing zeroes."""
    return f'{value:.2f}'.rstrip('0').rstrip('.')

def _add_tax_table_text_item(scene: QGraphicsScene, text: Any, x_pos: float, y_pos: float, width: float, align: str, font_size: float, font_family: str, bold: bool, block_id: str) -> Optional[QGraphicsTextItem]:
    """Add a GST table cell at a fixed tab position with optional right align."""
    clean_text = _plain_text(text)
    if not clean_text:
        return None
    font = QFont(font_family or 'Consolas')
    font.setPointSizeF(max(1.0, float(font_size or 10)))
    if (font_family or '').lower() in {'consolas', 'courier', 'courier new'}:
        font.setStyleHint(QFont.StyleHint.Monospace)
    font.setBold(bool(bold))
    _apply_font_rendering_hints(font)
    if align == 'right':
        text_width = float(QFontMetrics(font).horizontalAdvance(clean_text))
        x_pos = max(float(x_pos), float(x_pos) + float(width) - text_width)
    item = QGraphicsTextItem(clean_text)
    item.setFont(font)
    item.setDefaultTextColor(QColor('#111827'))
    item.setTextWidth(-1.0)
    _apply_tight_text_document(item)
    item.setPos(float(x_pos), float(y_pos))
    item.setData(0, block_id)
    scene.addItem(item)
    return item

def _add_gst_tax_breakdown_table(scene: QGraphicsScene, tax_summary: dict[tuple[float, float], dict[str, float]], block: dict[str, Any], current_y: float, paper_width: float, row_spacing: float, is_interstate: bool=False) -> tuple[list[QGraphicsItem], float]:
    """Draw the thermal footer GST breakdown table and return the next Y."""
    if not tax_summary:
        return ([], float(current_y))
    added_items: list[QGraphicsItem] = []
    table_columns = GST_TAX_TABLE_COLUMNS_INTERSTATE if is_interstate else GST_TAX_TABLE_COLUMNS_INTRASTATE
    table_scale = max(0.1, min(5.0, _to_float(block.get('scale', 1.0)) or 1.0))
    saved_font_size = _to_float(block.get(TAX_SUMMARY_FONT_SIZE_KEY)) or _to_float(block.get('font_size', 10)) or 10.0
    font_size = max(1.0, saved_font_size * table_scale)
    font_family = str(block.get('font_family', 'Consolas') or 'Consolas')
    table_x = max(0.0, _to_float(block.get('x', 28.0)))
    current_y = float(current_y) + GST_TAX_TABLE_TOP_PADDING
    top_line = _add_gst_tax_separator_line(scene, paper_width, current_y, 'gst_tax_breakdown_separator_top')
    added_items.append(top_line)
    current_y += GST_TAX_TABLE_LINE_PADDING
    header_items: list[QGraphicsItem] = []
    for header, x_offset, width, align in table_columns:
        header_item = _add_tax_table_text_item(scene, header, table_x + x_offset, current_y, width, align, font_size, font_family, True, 'gst_tax_breakdown_header')
        if header_item:
            header_items.append(header_item)
            added_items.append(header_item)
    if header_items:
        current_y = max((float(item.sceneBoundingRect().bottom()) for item in header_items))
    current_y += GST_TAX_TABLE_LINE_PADDING
    header_line = _add_gst_tax_separator_line(scene, paper_width, current_y, 'gst_tax_breakdown_separator_header')
    added_items.append(header_line)
    current_y += GST_TAX_TABLE_LINE_PADDING
    for tax_key in sorted(tax_summary):
        row = tax_summary[tax_key]
        base_gst_rate = row.get('base_gst_rate', tax_key[0])
        net_amt = row.get('net_amt', 0.0)
        cgst_amt = row.get('cgst_amt', 0.0)
        sgst_amt = row.get('sgst_amt', 0.0)
        igst_amt = row.get('igst_amt', 0.0)
        base_gst_amt = cgst_amt + sgst_amt + igst_amt
        cess_amt = row.get('cess_amt', 0.0)
        if is_interstate:
            values = (_format_gst_rate(base_gst_rate), _money(net_amt), _money(base_gst_amt), _money(cess_amt))
        else:
            values = (_format_gst_rate(base_gst_rate), _money(net_amt), _money(cgst_amt), _money(sgst_amt), _money(cess_amt))
        row_items: list[QGraphicsItem] = []
        for value, (_header, x_offset, width, align) in zip(values, table_columns):
            row_item = _add_tax_table_text_item(scene, value, table_x + x_offset, current_y, width, align, font_size, font_family, False, 'gst_tax_breakdown_row')
            if row_item:
                row_items.append(row_item)
                added_items.append(row_item)
        if row_items:
            current_y = max((float(item.sceneBoundingRect().bottom()) for item in row_items))
        current_y += row_spacing
    return (added_items, current_y + GST_TAX_TABLE_BOTTOM_PADDING)

def _larger_bold_font_from_block(block: dict[str, Any], fallback_family: str='Arial') -> QFont:
    """Return the Bold Total amount font without mutating the base font."""
    base_font = _font_from_block(block, fallback_family)
    grand_total_font = QFont(base_font)
    point_size = grand_total_font.pointSize()
    if point_size <= 0:
        point_size = int(round(grand_total_font.pointSizeF() or 12.0))
    grand_total_font.setPointSize(max(1, point_size + 6))
    grand_total_font.setWeight(QFont.Weight.Bold)
    return _apply_font_rendering_hints(grand_total_font)

def _add_grand_total_text_item(scene: QGraphicsScene, text: Any, block: dict[str, Any], y_pos: float, text_width: Optional[float], align_center: bool, word_wrap: bool) -> Optional[QGraphicsTextItem]:
    """Add the Grand Total using an isolated larger bold font."""
    clean_text = _plain_text(text)
    if not clean_text:
        return None
    item = QGraphicsTextItem(clean_text)
    font_family = str(block.get('font_family', 'Arial') or 'Arial')
    item.setFont(_larger_bold_font_from_block(block, font_family))
    item.setDefaultTextColor(QColor('#111827'))
    if word_wrap and text_width is not None:
        try:
            item.setTextWidth(max(1.0, float(text_width)))
        except (TypeError, ValueError):
            item.setTextWidth(-1.0)
    else:
        item.setTextWidth(-1.0)
    _apply_tight_text_document(item, align_center)
    item.setPos(float(block.get('x', 0)), float(y_pos))
    item.setData(0, 'grand_total')
    scene.addItem(item)
    return item

def _split_grand_total_parts(text: Any) -> tuple[str, str]:
    """Return Grand Total label and amount for separate receipt rendering."""
    clean_text = _plain_text(text)
    label = 'Grand Total:'
    if clean_text.lower().startswith(label.lower()):
        amount = clean_text[len(label):].strip()
    else:
        amount = clean_text
    return (label, amount)

def _add_split_grand_total_items(scene: QGraphicsScene, text: Any, block: dict[str, Any], y_pos: float, paper_width: float, is_bold_total: bool=False) -> tuple[list[QGraphicsItem], float]:
    """Draw Grand Total label and amount on one footer baseline."""
    label_text, amount_text = _split_grand_total_parts(text)
    if not amount_text:
        return ([], float(y_pos))
    font_family = str(block.get('font_family', 'Arial') or 'Arial')
    label_item = _add_text_item(scene, label_text, GRAND_TOTAL_LEFT_MARGIN, y_pos, block.get('font_size', 12), None, False, 'grand_total_label', font_family, False, False)
    if is_bold_total:
        total_font = _larger_bold_font_from_block(block, font_family)
    else:
        total_font = _font_from_block(block, font_family)
    amount_item = QGraphicsTextItem(amount_text)
    amount_item.setFont(total_font)
    amount_item.setDefaultTextColor(QColor('#111827'))
    amount_item.setTextWidth(-1.0)
    _apply_tight_text_document(amount_item)
    amount_width = float(QFontMetrics(total_font).horizontalAdvance(amount_text))
    if amount_width <= 0:
        amount_width = float(amount_item.boundingRect().width())
    amount_x = max(GRAND_TOTAL_LEFT_MARGIN, float(paper_width) - amount_width - GRAND_TOTAL_RIGHT_MARGIN)
    amount_y = float(y_pos)
    amount_item.setPos(amount_x, amount_y)
    amount_item.setData(0, 'grand_total_amount')
    scene.addItem(amount_item)
    added_items: list[QGraphicsItem] = [amount_item]
    if label_item:
        added_items.insert(0, label_item)
    bottom_y = max((float(item.sceneBoundingRect().bottom()) for item in added_items))
    return (added_items, bottom_y)

def _add_flowing_footer_text_item(scene: QGraphicsScene, text: Any, block: dict[str, Any], block_id: str, current_y: float, paper_width: float, row_spacing: float, word_wrap: bool) -> tuple[Optional[QGraphicsTextItem], float]:
    """Add a footer text item and advance by its rendered wrapped height."""
    text_width = max(1.0, float(paper_width) - 20.0) if word_wrap else block.get('text_width')
    item = _add_text_item(scene, text, block.get('x', 0), current_y, block.get('font_size', 12), text_width, bool(block.get('bold', False)), block_id, str(block.get('font_family', 'Arial')), bool(block.get('align_center', False)), word_wrap)
    if not item:
        return (None, float(current_y))
    _apply_saved_item_scale(item, block)
    next_y = float(item.sceneBoundingRect().bottom()) + row_spacing
    return (item, next_y)

def _apply_saved_item_scale(item: QGraphicsItem, config: dict[str, Any]) -> None:
    """Apply a persisted visual scale without changing the item's scene position."""
    try:
        scale = float(config.get('scale', 1.0) or 1.0)
    except (TypeError, ValueError):
        scale = 1.0
    item.setScale(max(0.1, min(5.0, scale)))

def _image_layout_blocks(saved_coordinates: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return persisted image/signature blocks from layout JSON."""
    return {block_id: block for block_id, block in saved_coordinates.items() if (block_id.startswith(LAYOUT_IMAGE_PREFIX) or block_id == SIGNATURE_IMAGE_BLOCK_ID) and isinstance(block, dict) and (_plain_text(block.get('type')) == 'image') and _plain_text(block.get('path'))}

def _add_image_item(scene: QGraphicsScene, block_id: str, config: dict[str, Any], y_offset: float=0.0) -> Optional[QGraphicsPixmapItem]:
    """Add a saved image/signature block to a graphics scene."""
    image_path = _plain_text(config.get('path'))
    if not image_path:
        return None
    pixmap = QPixmap(image_path)
    if pixmap.isNull():
        return None
    width = _to_float(config.get('width'))
    height = _to_float(config.get('height'))
    if width <= 0:
        width = min(float(pixmap.width()), 200.0)
    if height <= 0:
        height = float(pixmap.height()) * (width / max(1.0, float(pixmap.width())))
    scaled = pixmap.scaled(max(1, int(round(width))), max(1, int(round(height))), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    item = QGraphicsPixmapItem(scaled)
    item.setPos(float(config.get('x', 0)), float(config.get('y', 0)) + y_offset)
    _apply_saved_item_scale(item, config)
    item.setData(0, block_id)
    item.setData(1, image_path)
    scene.addItem(item)
    return item

def _company_signature_config(company: dict[str, Any], saved_coordinates: dict[str, dict[str, Any]], defaults: dict[str, dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return a visible company signature image config when printing is enabled."""
    if not _truthy_setting(company.get('print_signature', '1')):
        return None
    signature_path = _plain_text(company.get('signature_path'))
    if not signature_path:
        return None
    if QPixmap(signature_path).isNull():
        return None
    placeholder = defaults.get(SIGNATURE_PLACEHOLDER_BLOCK_ID, {})
    config: dict[str, Any] = {'type': 'image', 'path': signature_path, 'x': placeholder.get('x', 0), 'y': placeholder.get('y', 0), 'width': placeholder.get('text_width', 180), 'height': 0}
    saved = saved_coordinates.get(SIGNATURE_IMAGE_BLOCK_ID)
    if isinstance(saved, dict):
        if _plain_text(saved.get('type')) == 'deleted':
            return None
        config.update(saved)
        config['path'] = signature_path
    return config

def _draw_paper_rect(scene: QGraphicsScene, width: int, height: int) -> QGraphicsRectItem:
    """Draw the paper background rectangle used by designer and print scenes."""
    margin = 80
    scene.setSceneRect(QRectF(-margin, -margin, width + margin * 2, height + margin * 2))
    paper_rect = scene.addRect(0, 0, width, height, QPen(Qt.PenStyle.NoPen), QBrush(QColor('#ffffff')))
    paper_rect.setPen(QPen(Qt.PenStyle.NoPen))
    paper_rect.setZValue(-10)
    return paper_rect

class PrintPreviewGraphicsView(QGraphicsView):
    """Graphics view that keeps the full print scene visible inside the canvas."""

    def __init__(self, scene: QGraphicsScene, parent: Optional[QWidget]=None) -> None:
        """Initialize the preview view and bind scene-size changes to fitting."""
        super().__init__(scene, parent)
        self._auto_fit_enabled = True
        scene.sceneRectChanged.connect(self.fit_scene_rect)

    def resizeEvent(self, event: Any) -> None:
        """Refit the receipt preview whenever the available canvas size changes."""
        super().resizeEvent(event)
        if self._auto_fit_enabled and not getattr(self, '_suppress_resize_fit', False):
            self.fit_scene_rect()

    def set_auto_fit_enabled(self, enabled: bool) -> None:
        """Toggle automatic fit transforms during view resize or scene changes."""
        self._auto_fit_enabled = enabled

    def fit_scene_rect(self, *_args: Any, force: bool=False) -> None:
        """Scale the view transform so the full scene rect remains visible."""
        if not self._auto_fit_enabled and (not force):
            return
        scene = self.scene()
        if scene is None:
            return
        scene_rect = scene.sceneRect()
        if scene_rect.isNull() or scene_rect.isEmpty():
            return
        if self.viewport().width() <= 0 or self.viewport().height() <= 0:
            return
        self.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

class PrintDesignerScene(QGraphicsScene):
    """Graphics scene with temporary snap guides for movable layout items."""

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        """Initialize the scene-level snap state."""
        super().__init__(parent)
        self.paper_width = float(THERMAL_DIMENSIONS[0])
        self.paper_height = float(THERMAL_DIMENSIONS[1])
        self._guide_items: list[QGraphicsLineItem] = []

    def set_paper_size(self, width: float, height: float) -> None:
        """Store the visible canvas size used for full-length guide lines."""
        self.paper_width = float(width)
        self.paper_height = float(height)

    def clear_snap_guides(self) -> None:
        """Remove temporary guide lines so they are never saved or printed."""
        for guide_item in list(self._guide_items):
            if guide_item.scene() is self:
                self.removeItem(guide_item)
        self._guide_items.clear()

    def mouseMoveEvent(self, event: Any) -> None:
        """Snap a dragged layout item to nearby peer coordinates."""
        super().mouseMoveEvent(event)
        moved_item = self.mouseGrabberItem()
        if moved_item is not None:
            self._snap_layout_item(moved_item)

    def mouseReleaseEvent(self, event: Any) -> None:
        """Clear transient snap guides when a drag interaction finishes."""
        super().mouseReleaseEvent(event)
        self.clear_snap_guides()

    def _is_real_layout_item(self, item: QGraphicsItem) -> bool:
        """Return whether an item participates in designer snapping."""
        block_id = item.data(0)
        if block_id == SNAP_GUIDE_BLOCK_ID:
            return False
        if not isinstance(block_id, str) or not block_id:
            return False
        if item.zValue() < 0:
            return False
        return bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def _snap_layout_item(self, moved_item: QGraphicsItem) -> None:
        """Apply x/y snapping and redraw matching temporary guide lines."""
        if not self._is_real_layout_item(moved_item):
            return
        self.clear_snap_guides()
        position = moved_item.pos()
        snapped_x = float(position.x())
        snapped_y = float(position.y())
        draw_vertical = False
        draw_horizontal = False
        for peer_item in self.items():
            if peer_item is moved_item or not self._is_real_layout_item(peer_item):
                continue
            peer_position = peer_item.pos()
            peer_x = float(peer_position.x())
            peer_y = float(peer_position.y())
            if abs(snapped_x - peer_x) <= SNAP_THRESHOLD_PX:
                snapped_x = peer_x
                draw_vertical = True
            if abs(snapped_y - peer_y) <= SNAP_THRESHOLD_PX:
                snapped_y = peer_y
                draw_horizontal = True
        if snapped_x != float(position.x()) or snapped_y != float(position.y()):
            moved_item.setPos(snapped_x, snapped_y)
        if draw_vertical:
            self._add_snap_guide(snapped_x, 0.0, snapped_x, self.paper_height)
        if draw_horizontal:
            self._add_snap_guide(0.0, snapped_y, self.paper_width, snapped_y)

    def _add_snap_guide(self, x1: float, y1: float, x2: float, y2: float) -> None:
        """Draw one temporary dashed alignment guide."""
        pen = QPen(QColor('#38bdf8'), 1, Qt.PenStyle.DashLine)
        guide_item = self.addLine(x1, y1, x2, y2, pen)
        guide_item.setZValue(10000)
        guide_item.setData(0, SNAP_GUIDE_BLOCK_ID)
        guide_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        guide_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._guide_items.append(guide_item)

def _invoice_text_blocks(invoice_data: dict[str, Any], settings: dict[str, Any]) -> dict[str, str]:
    """Build real invoice text for the saved WYSIWYG layout blocks."""
    company = invoice_data.get('company') or {}
    invoice = invoice_data.get('invoice') or {}
    items = invoice_data.get('items') or []
    total_items_text = _total_items_text(items)
    customer_name = _plain_text(invoice.get('customer_name')) or 'Cash Customer'
    bill_of_supply, is_composition = _is_bill_of_supply_invoice(invoice_data)
    sub_total = _to_float(invoice.get('sub_total'))
    discount_total = _to_float(invoice.get('discount_total'))
    grand_total = max(0.0, sub_total - discount_total) if bill_of_supply else _to_float(invoice.get('grand_total'))
    amount_received = _to_float(invoice.get('amount_received'))
    if invoice.get('printed_balance') is not None:
        balance = _to_float(invoice.get('printed_balance'))
    else:
        balance = grand_total - amount_received
    header_quote, footer_terms = _quote_values_from_settings(settings)
    saved_coordinates = parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
    show_total_items = _layout_setting_bool(saved_coordinates, SHOW_TOTAL_ITEMS_COUNT_KEY, True)
    show_print_time = _layout_setting_bool(saved_coordinates, PRINT_TIME_KEY, False)
    footer_terms = _layout_setting_text(saved_coordinates, TERMS_CONDITIONS_FOOTER_KEY, footer_terms)
    invoice_title = _plain_text(invoice.get('invoice_title')) or 'TAX INVOICE'
    invoice_subheading = ''
    if bill_of_supply:
        invoice_title = 'BILL OF SUPPLY'
        if is_composition:
            invoice_subheading = COMPOSITION_SUBHEADING_TEXT
    totals_lines = []
    if show_total_items:
        totals_lines.append(total_items_text)
    totals_lines.extend([f'Subtotal: Rs. {_money(sub_total)}', f'Discount: Rs. {_money(discount_total)}'])
    if not bill_of_supply:
        totals_lines.append(f"Tax: Rs. {_money(invoice.get('tax_total'))}")
    totals_lines.extend((f'Grand Total: Rs. {_money(grand_total)}', f'Amount Received: Rs. {_money(amount_received)}', f'Balance: Rs. {_money(balance)}'))
    company_header = _company_header_text_blocks(company)
    invoice_date_text = append_print_time_to_date(
        invoice.get('invoice_date'),
        include_time=show_print_time,
    )
    return {'company_name': company_header['company_name'], 'address': company_header['address'], 'phone': company_header['phone'], 'gstin': company_header['gstin'], 'invoice_title': invoice_title, COMPOSITION_SUBHEADING_BLOCK_ID: invoice_subheading, 'header_quote': header_quote, HEADER_BILL_NO_BLOCK_ID: f"Bill No: {_plain_text(invoice.get('invoice_number'))}", HEADER_DATE_BLOCK_ID: f"Date: {_plain_text(invoice_date_text)}", 'customer_name': f'Customer: {customer_name}', 'separator_above_items': '--------------------------------', 'item_header': THERMAL_ITEM_HEADER_TEXT, 'separator_below_items': '--------------------------------', 'item_table_label': f'{len(items)} item(s)', 'separator_above_totals': '--------------------------------', TOTAL_ITEMS_BLOCK_ID: total_items_text, 'subtotal': f'Subtotal: Rs. {_money(sub_total)}', 'discount': f'Discount: Rs. {_money(discount_total)}', 'tax': '' if bill_of_supply else f"Tax: Rs. {_money(invoice.get('tax_total'))}", 'grand_total': f'Grand Total: Rs. {_money(grand_total)}', 'amount_received': f'Amount Received: Rs. {_money(amount_received)}', 'balance': f'Balance: Rs. {_money(balance)}', TOTALS_BLOCK_ID: '\n'.join(totals_lines), 'amount_in_words': f'Amount in Words: {_amount_to_words(grand_total)}', 'footer_terms': footer_terms}

def _add_invoice_items(scene: QGraphicsScene, items: list[dict[str, Any]], item_table: dict[str, Any], thermal: bool, show_item_barcode: bool=False, print_barcode_col: bool=True, item_name_bold: bool=False, bill_of_supply: bool=False, column_anchors: Optional[dict[str, dict[str, Any]]]=None, sample_anchors: Optional[dict[str, dict[str, Any]]]=None, row_spacing: float=5.0) -> tuple[list[QGraphicsItem], float]:
    """Draw real sales item rows from the saved item-table position downward."""
    added_items: list[QGraphicsItem] = []
    x_pos = float(item_table.get('x', 0))
    current_y = float(item_table.get('y', 0))
    width = float(item_table.get('width', 300))
    default_font_size = 18 if thermal else 10
    font_size = float(item_table.get('font_size', default_font_size) or default_font_size)
    font_family = str(item_table.get('font_family', 'Consolas' if thermal else 'Arial'))
    if not items:
        empty_text = 'No items found'
        if thermal and column_anchors:
            x_pos = float(column_anchors.get('col_sn', item_table).get('x', x_pos))
        empty_item = _add_text_item(scene, empty_text, x_pos, current_y, font_size, width, font_family=font_family)
        if empty_item:
            maximum_font_height = float(empty_item.boundingRect().height())
            current_y += maximum_font_height + row_spacing
            return ([empty_item], current_y)
        return ([], current_y)
    if thermal and column_anchors:
        return _add_thermal_invoice_items_from_columns(scene, items, item_table, column_anchors, show_item_barcode, print_barcode_col, item_name_bold, bill_of_supply, sample_anchors, row_spacing)
    for index, item in enumerate(items, start=1):
        item_name = _plain_text(item.get('item_name')) or f'Item {index}'
        sl_no = _plain_text(item.get('sl_no')) or str(index)
        quantity = _money(item.get('quantity'))
        rate = _money(item.get('rate'))
        total_value = _to_float(item.get('quantity')) * _to_float(item.get('rate')) - _to_float(item.get('discount')) if bill_of_supply else _to_float(item.get('grand_total'))
        total = _money(total_value)
        hsn = _plain_text(item.get('hsn'))
        barcode = _item_barcode_text(item)
        if thermal:
            row_text = _thermal_item_row_text(sl_no, barcode, quantity, rate, total, item_name, show_item_barcode and print_barcode_col)
        elif bill_of_supply:
            row_text = f'{sl_no:<3} {item_name:<28} {quantity:>7} x {rate:>9} = {total:>10}'
            if show_item_barcode and barcode:
                row_text = f'{row_text}\n    {barcode}'
        else:
            row_text = f'{sl_no:<3} {item_name:<28} {hsn:<8} {quantity:>7} {rate:>9} {total:>10}'
            if show_item_barcode and barcode:
                row_text = f'{row_text}\n    {barcode}'
        row_item = _add_text_item(scene, row_text, x_pos, current_y, font_size, width, font_family=font_family)
        if row_item:
            added_items.append(row_item)
            maximum_font_height = float(row_item.boundingRect().height())
            current_y += maximum_font_height + row_spacing
    return (added_items, current_y)

def _add_thermal_invoice_items_from_columns(scene: QGraphicsScene, items: list[dict[str, Any]], item_table: dict[str, Any], column_anchors: dict[str, dict[str, Any]], show_item_barcode: bool, print_barcode_col: bool, item_name_bold: bool, bill_of_supply: bool, sample_anchors: Optional[dict[str, dict[str, Any]]]=None, row_spacing: float=5.0) -> tuple[list[QGraphicsItem], float]:
    """Draw thermal item rows from independent saved column anchors."""
    added_items: list[QGraphicsItem] = []
    sample_anchors = sample_anchors or {}
    anchors = {block_id: column_anchors[block_id] for block_id in _thermal_column_render_ids() if isinstance(column_anchors.get(block_id), dict)}
    barcode_sample = sample_anchors.get(PREFERRED_BARCODE_COLUMN_ID) or sample_anchors.get('sample_barcode') or sample_anchors.get('sample_bcd')
    if print_barcode_col and (not any((block_id in anchors for block_id in BARCODE_COLUMN_BLOCK_IDS))) and isinstance(barcode_sample, dict):
        anchors[PREFERRED_BARCODE_COLUMN_ID] = dict(barcode_sample)
    barcode_column_id = _active_barcode_column_id(anchors)
    base_anchor = anchors.get('col_sn') or anchors.get(barcode_column_id) or item_table
    base_sample_id, base_sample = _base_sample_row_reference(sample_anchors)
    if base_sample_id and base_sample:
        base_sample_column = SAMPLE_ITEM_ROW_ELEMENTS.get(base_sample_id, ('col_sn', ''))[0]
        if base_sample_id == 'sample_bcd':
            base_sample_column = PREFERRED_BARCODE_COLUMN_ID
        base_anchor = anchors.get(base_sample_column) or base_anchor
        base_anchor_saved_y = _to_float(base_anchor.get('y', item_table.get('y', 0)))
        current_row_base_y = _to_float(base_sample.get('y', base_anchor_saved_y))
    else:
        base_anchor_saved_y = _to_float(base_anchor.get('y', item_table.get('y', 0)))
        current_row_base_y = base_anchor_saved_y
    row_layout: dict[str, dict[str, float]] = {}
    for block_id in _thermal_column_render_ids():
        if block_id == LEGACY_BARCODE_COLUMN_ID and barcode_column_id == PREFERRED_BARCODE_COLUMN_ID:
            continue
        anchor = anchors.get(block_id)
        if not anchor:
            continue
        font_metrics = QFontMetrics(_font_from_block(anchor))
        anchor_saved_y = _to_float(anchor.get('y', base_anchor_saved_y))
        sample_block = _sample_block_for_column(block_id, sample_anchors)
        if base_sample_id and sample_block is not None:
            offset_y = _to_float(sample_block.get('y', current_row_base_y)) - current_row_base_y
        else:
            offset_y = anchor_saved_y - base_anchor_saved_y
        row_layout[block_id] = {'x': _to_float(anchor.get('x')), 'offset_y': offset_y, 'font_size': _to_float(anchor.get('font_size', item_table.get('font_size', 18))), 'height': float(font_metrics.lineSpacing())}
    if not row_layout:
        row_layout['col_sn'] = {'x': _to_float(base_anchor.get('x')), 'offset_y': 0.0, 'font_size': _to_float(base_anchor.get('font_size', item_table.get('font_size', 18))), 'height': float(QFontMetrics(_font_from_block(base_anchor)).lineSpacing())}
    min_offset = min(0.0, *(metrics['offset_y'] for metrics in row_layout.values()))
    height_metrics = [metrics for block_id, metrics in row_layout.items() if block_id not in BARCODE_COLUMN_BLOCK_IDS] or list(row_layout.values())
    maximum_font_height = max((metrics['offset_y'] + metrics['height'] for metrics in height_metrics)) - min_offset
    for index, item in enumerate(items, start=1):
        quantity = _money(item.get('quantity'))
        rate = _money(item.get('rate'))
        total_value = _to_float(item.get('quantity')) * _to_float(item.get('rate')) - _to_float(item.get('discount')) if bill_of_supply else _to_float(item.get('grand_total'))
        barcode = _item_barcode_text(item)
        product_name = _plain_text(item.get('item_name')) or f'Item {index}'
        row_values = {'col_sn': _plain_text(item.get('sl_no')) or str(index), PREFERRED_BARCODE_COLUMN_ID: barcode if print_barcode_col and barcode else '', LEGACY_BARCODE_COLUMN_ID: barcode if print_barcode_col and barcode else '', 'col_qty': quantity, 'col_price': rate, 'col_total': _money(total_value), 'col_product_name': product_name}
        row_bottom = current_row_base_y + maximum_font_height
        product_name_layout = row_layout.get('col_product_name')
        product_name_y = current_row_base_y + product_name_layout['offset_y'] if product_name_layout else current_row_base_y
        for block_id in _thermal_column_render_ids():
            anchor = anchors.get(block_id)
            layout = row_layout.get(block_id)
            if not anchor or not layout:
                continue
            base_font = _font_from_block(anchor)
            row_font = QFont(base_font.family(), base_font.pointSize())
            row_font.setBold(False)
            if base_font.family().lower() in {'consolas', 'courier', 'courier new'}:
                row_font.setStyleHint(QFont.StyleHint.Monospace)
            row_font = _apply_font_rendering_hints(row_font)
            row_bold = block_id == 'col_product_name' and item_name_bold
            y_pos = product_name_y if block_id in BARCODE_COLUMN_BLOCK_IDS and row_values[block_id] else current_row_base_y + layout['offset_y']
            text_item = _add_text_item(scene, row_values[block_id], layout['x'], y_pos, row_font.pointSize() if row_font.pointSize() > 0 else layout['font_size'], anchor.get('text_width'), row_bold, font_family=str(anchor.get('font_family', item_table.get('font_family', 'Consolas'))), word_wrap=block_id == 'col_product_name')
            if text_item:
                added_items.append(text_item)
                if block_id not in BARCODE_COLUMN_BLOCK_IDS:
                    row_bottom = max(row_bottom, float(text_item.sceneBoundingRect().bottom()))
        current_row_base_y = row_bottom + row_spacing
    return (added_items, current_row_base_y)

def build_invoice_wysiwyg_scene(settings: dict[str, Any], invoice_data: dict[str, Any], parent: Optional[QWidget]=None) -> dict[str, Any]:
    """Build a physical invoice QGraphicsScene from saved designer coordinates."""
    paper_size = _paper_size_from_settings(settings)
    saved_coordinates = parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
    raw_saved_coordinates = dict(saved_coordinates)
    dimensions = _selected_dimensions_for_paper(paper_size)
    if paper_size == THERMAL_PAPER_SIZE:
        dimensions = (_thermal_width_px_from_metadata(saved_coordinates), dimensions[1])
    deleted_block_ids = _deleted_layout_block_ids(saved_coordinates)
    defaults = default_layout_blocks(paper_size, dimensions)
    if paper_size == THERMAL_PAPER_SIZE:
        saved_coordinates = _thermal_saved_layout_coordinates(saved_coordinates, defaults)
    blocks = {block_id: merge_layout_block(block_id, block, saved_coordinates) for block_id, block in defaults.items()}
    if paper_size == THERMAL_PAPER_SIZE:
        blocks.update(_saved_thermal_column_blocks(saved_coordinates))
    scene = QGraphicsScene(parent)
    paper_rect_item = _draw_paper_rect(scene, *dimensions)
    if paper_size == THERMAL_PAPER_SIZE:
        scene.setProperty(THERMAL_WIDTH_MM_KEY, _thermal_width_mm_from_px(dimensions[0]))
    company = invoice_data.get('company') or {}
    block_text = _invoice_text_blocks(invoice_data, settings)
    content_items: list[QGraphicsItem] = []
    thermal = paper_size == THERMAL_PAPER_SIZE
    bill_of_supply, _is_composition = _is_bill_of_supply_invoice(invoice_data)
    is_interstate = _is_interstate_invoice(invoice_data)
    show_item_barcode = _show_item_barcode_below_name_from_settings(settings)
    print_barcode_col = _print_barcode_col_from_settings(settings)
    item_name_bold = _item_name_bold_from_settings(settings)
    show_gst_summary = _layout_setting_bool(saved_coordinates, PRINT_GST_SUMMARY_TABLE_KEY, True)
    show_total_items = _layout_setting_bool(saved_coordinates, SHOW_TOTAL_ITEMS_COUNT_KEY, True)
    show_company_logo = _layout_setting_bool(saved_coordinates, SHOW_COMPANY_LOGO_KEY, True)
    show_phone_number = _layout_setting_bool(saved_coordinates, SHOW_PHONE_NUMBER_KEY, True)
    paper_cut_buffer_px = _layout_setting_int(saved_coordinates, PAPER_CUT_BUFFER_PX_KEY, int(THERMAL_HARDWARE_FEED_BUFFER_PX), 0, 300)
    scene.setProperty(PAPER_CUT_BUFFER_PX_KEY, paper_cut_buffer_px)
    row_spacing = _layout_row_spacing(saved_coordinates)
    is_bold_total = _bold_grand_total_from_settings(settings, raw_saved_coordinates)
    paper_width = float(dimensions[0])
    if thermal:
        blocks = _apply_tax_summary_font_size(blocks, saved_coordinates, settings)
        blocks = _apply_barcode_column_visibility(blocks, print_barcode_col)
    blocks = _apply_logo_header_offset(blocks, saved_coordinates, show_company_logo)
    wrapped_block_ids = {COMPOSITION_SUBHEADING_BLOCK_ID, 'header_quote', 'tax', TOTALS_BLOCK_ID, 'amount_in_words', 'footer_terms'}
    header_block_ids = ['company_name', 'address', 'phone', 'gstin', 'invoice_title', COMPOSITION_SUBHEADING_BLOCK_ID, 'header_quote', HEADER_BILL_NO_BLOCK_ID, HEADER_DATE_BLOCK_ID, 'customer_name', 'separator_above_items', 'separator_below_items']
    if thermal:
        header_block_ids.extend(ITEM_COLUMN_ANCHOR_IDS)
    else:
        header_block_ids.append('item_header')
    if thermal:
        footer_block_ids = ('separator_above_totals', TOTALS_BLOCK_ID, 'amount_in_words', 'footer_terms', SIGNATURE_PLACEHOLDER_BLOCK_ID)
    else:
        footer_block_ids = ('separator_above_totals', TOTAL_ITEMS_BLOCK_ID, 'subtotal', 'discount', 'tax', 'grand_total', 'amount_received', 'balance', 'amount_in_words', 'footer_terms', SIGNATURE_PLACEHOLDER_BLOCK_ID)
    sample_anchors = _thermal_sample_row_blocks(blocks, saved_coordinates) if thermal else None
    if thermal and (not print_barcode_col) and sample_anchors:
        sample_anchors = {sample_id: sample for sample_id, sample in sample_anchors.items() if sample_id not in BARCODE_COLUMN_BLOCK_IDS and sample_id not in {'sample_barcode', 'sample_bcd'}}
    signature_config = _company_signature_config(company, saved_coordinates, blocks)
    header_image_ids: set[str] = set()
    if show_company_logo:
        item_table_y = _to_float(blocks.get('item_table', {}).get('y', 0))
        for block_id, image_config in _image_layout_blocks(saved_coordinates).items():
            if block_id == SIGNATURE_IMAGE_BLOCK_ID:
                continue
            if _to_float(image_config.get('y', 0)) >= item_table_y:
                continue
            image_item = _add_image_item(scene, block_id, dict(image_config))
            if image_item:
                content_items.append(image_item)
                header_image_ids.add(block_id)
    for block_id in header_block_ids:
        if block_id in deleted_block_ids:
            continue
        if block_id not in blocks:
            continue
        if block_id == 'phone' and (not show_phone_number):
            continue
        if block_id == 'company_name' and (not _layout_setting_bool(saved_coordinates, SHOW_COMPANY_NAME_KEY, True)):
            continue
        if block_id == 'address' and (not _layout_setting_bool(saved_coordinates, SHOW_COMPANY_ADDRESS_KEY, True)):
            continue
        if block_id == 'gstin' and (not _layout_setting_bool(saved_coordinates, SHOW_GSTIN_KEY, True)):
            continue
        block = blocks[block_id]
        text_value = block_text.get(block_id, block.get('text', ''))
        if block_id == 'item_header' and (not thermal) and (not bill_of_supply):
            text_value = block.get('text', '')
        if block_id in BCD_HEADER_BLOCK_IDS and _plain_text(text_value).lower() == BCD_HEADER_TEXT.lower():
            continue
        word_wrap = block_id in wrapped_block_ids
        text_width = max(1.0, paper_width - float(block.get('x', 0)) - 10.0) if word_wrap else block.get('text_width')
        item = _add_text_item(scene, text_value, block.get('x', 0), block.get('y', 0), block.get('font_size', 12), text_width, bool(block.get('bold', False)), block_id, str(block.get('font_family', 'Arial')), bool(block.get('align_center', False)), word_wrap)
        if item:
            _apply_saved_item_scale(item, block)
            content_items.append(item)
    rect_block = blocks['item_table']
    if thermal:
        row_anchor = dict(rect_block)
        row_anchor['font_size'] = blocks.get('col_sn', {}).get('font_size', 18)
        row_anchor['font_family'] = blocks.get('col_sn', {}).get('font_family', 'Consolas')
        column_anchors = {block_id: blocks[block_id] for block_id in _thermal_column_render_ids() if block_id in blocks}
    else:
        row_anchor = rect_block
        column_anchors = None
        if 'item_table' not in deleted_block_ids:
            rect_item = QGraphicsRectItem(0, 0, float(rect_block.get('width', 200)), float(rect_block.get('height', 120)))
            rect_item.setPen(QPen(QColor('#374151'), 1, Qt.PenStyle.SolidLine))
            rect_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            rect_item.setPos(float(rect_block.get('x', 0)), float(rect_block.get('y', 0)))
            _apply_saved_item_scale(rect_item, rect_block)
            rect_item.setData(0, 'item_table')
            scene.addItem(rect_item)
            content_items.append(rect_item)
    invoice_items = list(invoice_data.get('items') or [])
    tax_summary = {} if bill_of_supply else _build_tax_summary(invoice_items)
    tax_summary_block = blocks.get(FOOTER_TAX_SUMMARY_BLOCK_ID, blocks.get(TOTALS_BLOCK_ID, {}))
    dynamic_item_rows, item_flow_y = _add_invoice_items(scene, invoice_items, row_anchor, thermal, show_item_barcode, print_barcode_col, item_name_bold, bill_of_supply, column_anchors, sample_anchors, row_spacing)
    content_items.extend(dynamic_item_rows)
    item_bottom = max((float(row_item.sceneBoundingRect().bottom()) for row_item in dynamic_item_rows if row_item is not None), default=float(row_anchor.get('y', 0)))
    footer_current_y = max(float(item_flow_y), item_bottom)
    for block_id in footer_block_ids:
        if block_id not in blocks:
            continue
        if block_id in deleted_block_ids:
            continue
        if block_id == TOTAL_ITEMS_BLOCK_ID and (not show_total_items):
            continue
        block = blocks[block_id]
        if block_id == SIGNATURE_PLACEHOLDER_BLOCK_ID and signature_config is not None:
            continue
        word_wrap = block_id in wrapped_block_ids
        if block_id == TOTALS_BLOCK_ID and thermal:
            totals_text = block_text.get(block_id, block.get('text', ''))
            saved_totals_line_y = float(block.get('y', footer_current_y))
            for line in _plain_text(totals_text).splitlines():
                if not _plain_text(line):
                    continue
                if line.strip().lower().startswith('grand total:'):
                    footer_current_y += GRAND_TOTAL_TOP_PADDING
                    separator_item = _add_footer_separator_line(scene, paper_width, footer_current_y, 'grand_total_separator_top')
                    content_items.append(separator_item)
                    footer_current_y += GRAND_TOTAL_LINE_PADDING
                    grand_total_items, grand_total_bottom = _add_split_grand_total_items(scene, line, block, footer_current_y, paper_width, is_bold_total)
                    if grand_total_items:
                        content_items.extend(grand_total_items)
                        footer_current_y = grand_total_bottom + GRAND_TOTAL_BOTTOM_PADDING
                    separator_item = _add_footer_separator_line(scene, paper_width, footer_current_y, 'grand_total_separator_bottom')
                    content_items.append(separator_item)
                    footer_current_y += GRAND_TOTAL_LINE_PADDING + row_spacing
                    continue
                saved_line_y = saved_totals_line_y
                item, footer_current_y = _add_flowing_footer_text_item(scene, line, block, block_id, footer_current_y, paper_width, row_spacing, word_wrap)
                if item:
                    content_items.append(item)
                    saved_totals_line_y = saved_line_y + float(item.sceneBoundingRect().height()) + row_spacing
                if line.strip().lower().startswith('balance:'):
                    if not show_gst_summary:
                        continue
                    tax_table_items, footer_current_y = _add_gst_tax_breakdown_table(scene, tax_summary, tax_summary_block, footer_current_y, paper_width, row_spacing, is_interstate)
                    content_items.extend(tax_table_items)
            continue
        if block_id == 'grand_total':
            footer_current_y += GRAND_TOTAL_TOP_PADDING
            separator_item = _add_footer_separator_line(scene, paper_width, footer_current_y, 'grand_total_separator_top')
            content_items.append(separator_item)
            footer_current_y += GRAND_TOTAL_LINE_PADDING
            grand_total_items, grand_total_bottom = _add_split_grand_total_items(scene, block_text.get(block_id, block.get('text', '')), block, footer_current_y, paper_width, is_bold_total)
            if grand_total_items:
                content_items.extend(grand_total_items)
                footer_current_y = grand_total_bottom + GRAND_TOTAL_BOTTOM_PADDING
            separator_item = _add_footer_separator_line(scene, paper_width, footer_current_y, 'grand_total_separator_bottom')
            content_items.append(separator_item)
            footer_current_y += GRAND_TOTAL_LINE_PADDING + row_spacing
            continue
        item, footer_current_y = _add_flowing_footer_text_item(scene, block_text.get(block_id, block.get('text', '')), block, block_id, footer_current_y, paper_width, row_spacing, word_wrap)
        if item:
            content_items.append(item)
    if signature_config is not None:
        sequential_signature_config = dict(signature_config)
        sequential_signature_config['y'] = footer_current_y
        signature_item = _add_image_item(scene, SIGNATURE_IMAGE_BLOCK_ID, sequential_signature_config)
        if signature_item:
            content_items.append(signature_item)
            footer_current_y = float(signature_item.sceneBoundingRect().bottom()) + row_spacing
    for block_id, block in _image_layout_blocks(saved_coordinates).items():
        if block_id == SIGNATURE_IMAGE_BLOCK_ID:
            continue
        if block_id in header_image_ids:
            continue
        if not show_company_logo:
            continue
        image_config = dict(block)
        footer_image = float(image_config.get('y', 0)) > float(rect_block.get('y', 0))
        if footer_image:
            image_config['y'] = footer_current_y
        image_item = _add_image_item(scene, block_id, image_config)
        if image_item:
            content_items.append(image_item)
            if footer_image:
                footer_current_y = float(image_item.sceneBoundingRect().bottom()) + row_spacing
    if thermal:
        scene.itemsBoundingRect()
    return {'scene': scene, 'paper_rect_item': paper_rect_item, 'content_items': content_items, 'paper_size': paper_size, 'paper_cut_buffer_px': paper_cut_buffer_px}

def _content_bounding_rect(scene: QGraphicsScene, content_items: Optional[Iterable[QGraphicsItem]]=None) -> QRectF:
    """Return a scene bounding rect excluding the visual paper background."""
    items = list(content_items or [])
    if not items:
        items = [item for item in scene.items() if item.isVisible() and item.zValue() >= 0]
    content_rect: Optional[QRectF] = None
    for item in items:
        if item is None or not item.isVisible():
            continue
        item_rect = item.sceneBoundingRect()
        content_rect = QRectF(item_rect) if content_rect is None else content_rect.united(item_rect)
    return content_rect or QRectF(0, 0, 1, 1)

def _prepare_scene_text_for_print(scene: QGraphicsScene) -> None:
    """Apply final text metrics tuning before painting to a physical printer."""
    for item in scene.items():
        if not isinstance(item, QGraphicsTextItem):
            continue
        font = item.font()
        _apply_font_rendering_hints(font)
        item.setFont(font)
        _apply_tight_text_document(item)

def render_wysiwyg_scene_to_printer(scene: QGraphicsScene, printer: QPrinter, thermal: bool, content_items: Optional[Iterable[QGraphicsItem]]=None, paper_rect_item: Optional[QGraphicsRectItem]=None, hardware_feed_buffer_px: Optional[float]=None) -> float:
    """Render a WYSIWYG scene to a printer and return thermal page height in mm."""
    printer.setFullPage(True)
    _prepare_scene_text_for_print(scene)
    if thermal:
        scene.itemsBoundingRect()
        content_rect = _content_bounding_rect(scene, content_items)
        paper_width = float(paper_rect_item.rect().width()) if paper_rect_item is not None else float(THERMAL_DIMENSIONS[0])
        feed_buffer_px = THERMAL_HARDWARE_FEED_BUFFER_PX
        raw_buffer_px = hardware_feed_buffer_px if hardware_feed_buffer_px is not None else scene.property(PAPER_CUT_BUFFER_PX_KEY)
        if raw_buffer_px not in (None, ''):
            try:
                feed_buffer_px = max(0.0, min(300.0, float(raw_buffer_px)))
            except (TypeError, ValueError):
                feed_buffer_px = THERMAL_HARDWARE_FEED_BUFFER_PX
        thermal_width_mm = THERMAL_WIDTH_MM
        raw_width_mm = scene.property(THERMAL_WIDTH_MM_KEY)
        if raw_width_mm not in (None, ''):
            try:
                thermal_width_mm = max(1.0, min(160.0, float(raw_width_mm)))
            except (TypeError, ValueError):
                thermal_width_mm = THERMAL_WIDTH_MM
        content_height_px = max(1.0, float(content_rect.bottom()), float(content_rect.height())) + feed_buffer_px
        dynamic_height_mm = content_height_px / THERMAL_DPI * 25.4
        printer.setPageSize(QPageSize(QSizeF(thermal_width_mm, dynamic_height_mm + THERMAL_CUT_MARGIN_MM), QPageSize.Unit.Millimeter))
        source = QRectF(0, 0, paper_width, content_height_px)
    else:
        dynamic_height_mm = 0.0
        source = scene.itemsBoundingRect()
    target_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
    if thermal:
        dpi_scale = max(0.1, float(printer.logicalDpiX()) / 96.0)
        target_width = max(1.0, float(target_rect.width()) / dpi_scale)
        target_scale = target_width / max(1.0, float(source.width()))
        target = QRectF(0, 0, target_width, float(source.height()) * target_scale)
    else:
        dpi_scale = 1.0
        target = QRectF(0, 0, float(target_rect.width()), float(target_rect.height()))
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError('Could not start printer painter for designer scene.')
    try:
        if thermal:
            painter.scale(dpi_scale, dpi_scale)
        scene.render(painter, target=target, source=source, aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio if thermal else Qt.AspectRatioMode.KeepAspectRatio)
    finally:
        painter.end()
    return dynamic_height_mm

def _print_settings_checkbox(text: str) -> CheckBox3D:
    """Create a Sales Entry-style 3D checkbox for print designer toggles."""
    return create_checkbox(text, label_color=COLORS['text_primary'], font_size=13, spacing=8)

class PrintSettingsWidget(QWidget):
    """Print designer page for printer selection and WYSIWYG invoice layout defaults."""
    A4_PAPER_SIZE = A4_PAPER_SIZE
    THERMAL_PAPER_SIZE = THERMAL_PAPER_SIZE
    PAPER_SIZES = (A4_PAPER_SIZE, THERMAL_PAPER_SIZE)
    A4_DIMENSIONS = A4_DIMENSIONS
    THERMAL_DIMENSIONS = THERMAL_DIMENSIONS
    THERMAL_ALIASES = THERMAL_ALIASES

    def __init__(self, parent: Optional[QWidget]=None, db: Optional[Database]=None, company_id: Optional[int]=None) -> None:
        """Initialize the print designer page for the active company."""
        super().__init__(parent)
        self._initial_load_complete = False
        self.db = db or Database()
        self._explicit_company_id = company_id
        self.company_id = company_id or active_company_manager.get_active_company_id()
        self.layout_items: dict[str, QGraphicsItem] = {}
        self.saved_layout_coordinates: dict[str, dict[str, Any]] = {}
        self.deleted_layout_item_ids: set[str] = set()
        self.saved_header_quote = ''
        self.saved_footer_terms = ''
        self.saved_show_item_barcode = False
        self.saved_print_barcode_col = True
        self.saved_paper_roll_size = DEFAULT_PAPER_ROLL_SIZE
        self.saved_print_gst_summary = True
        self.saved_show_total_items = True
        self.saved_bold_grand_total = False
        self.saved_show_company_name = True
        self.saved_show_company_address = True
        self.saved_show_company_logo = True
        self.saved_show_phone_number = True
        self.saved_show_gstin = True
        self.saved_paper_cut_buffer_px = int(THERMAL_HARDWARE_FEED_BUFFER_PX)
        self.saved_default_print_mode = DEFAULT_PRINT_MODE
        self._loading_settings = False
        self._a4_preview_browser_ready = False
        self._a4_preview_initial_present_complete = False
        self.current_company_data: dict[str, Any] = {}
        self.current_gst_type = 'Regular'
        self.paper_rect_item: Optional[QGraphicsRectItem] = None
        self.paper_dimensions = self.A4_DIMENSIONS
        self.a4_theme_color = DEFAULT_A4_THEME_COLOR
        self.a4_logo_base64 = ''
        self.a4_signature_base64 = ''
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._saved_normal_printer_mode: bool | None = None
        self._build_ui()
        self._connect_signals()
        if self._is_normal_printer_saved():
            self._ensure_a4_preview_browser(allow_hidden=True)

    def _is_normal_printer_saved(self) -> bool:
        """Return whether saved company settings use the Normal printer section."""
        if self._saved_normal_printer_mode is not None:
            return self._saved_normal_printer_mode
        saved_normal = False
        if self.company_id:
            try:
                settings = get_print_settings(self.db, self.company_id)
                saved_normal = self._normalize_paper_size(settings) != self.THERMAL_PAPER_SIZE
            except Exception as exc:
                LOGGER.exception('Normal printer mode probe failed: %s', exc)
        self._saved_normal_printer_mode = saved_normal
        return saved_normal

    def _close_host_window(self) -> None:
        """Close the StandaloneModuleWindow shell hosting this page."""
        host = self.window()
        if host is not None and host is not self:
            host.close()

    def complete_initial_load(
        self,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Load persisted settings and build the designer preview once."""
        if self._initial_load_complete:
            if on_ready is not None:
                QTimer.singleShot(0, on_ready)
            return

        def _finish_initial_load() -> None:
            """Mark the page ready and notify the host window it may be shown."""
            if self._initial_load_complete:
                if on_ready is not None:
                    on_ready()
                return
            self._initial_load_complete = True
            if on_ready is not None:
                on_ready()

        def _schedule_ready_fallback() -> None:
            """Guarantee the host window opens if preview callbacks stall."""
            if on_ready is None:
                return
            QTimer.singleShot(4500, on_ready)

        self.setUpdatesEnabled(False)
        if hasattr(self, 'canvas_view') and self.canvas_view is not None:
            self.canvas_view._suppress_resize_fit = True
            self.canvas_view.set_auto_fit_enabled(False)
        try:
            self._load_settings()
            self.thermal_button.show()
            self.normal_button.show()
            self.section_stack.show()
            if self.section_stack.currentIndex() == 0:
                self.populate_canvas()
                self._fit_canvas_view_to_scene()
                _finish_initial_load()
            else:
                self._show_a4_preview_cover()
                _schedule_ready_fallback()
                self.update_a4_preview(on_ready=_finish_initial_load)
        except Exception as exc:
            LOGGER.exception("Print settings initial load failed: %s", exc)
            if on_ready is not None:
                QTimer.singleShot(0, on_ready)
            raise
        finally:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._suppress_resize_fit = False
                self.canvas_view.set_auto_fit_enabled(True)
            self.setUpdatesEnabled(True)

    def _build_ui(self) -> None:
        """Create the split controls and graphics-scene preview layout."""
        self.setObjectName('PrintSettingsWidget')
        self.setStyleSheet(f"\n            QWidget#PrintSettingsWidget {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n            }}\n            QLabel {{\n                color: {COLORS['text_primary']};\n                font-size: 13px;\n            }}\n        ")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        title = QLabel('Print Designer')
        title.setStyleSheet(f"color: {COLORS['primary']}; font-size: 22px; font-weight: bold;")
        root.addWidget(title)
        default_mode_layout = QHBoxLayout()
        default_mode_layout.setSpacing(10)
        default_mode_layout.addWidget(QLabel('Global Default Print Mode:'))
        self.default_mode_combo = self._combo(list(DEFAULT_PRINT_MODE_OPTIONS))
        self.default_mode_combo.setCurrentText(DEFAULT_PRINT_MODE)
        default_mode_layout.addWidget(self.default_mode_combo)
        default_mode_layout.addStretch()
        root.addLayout(default_mode_layout)
        default_mode_separator = QFrame()
        default_mode_separator.setFrameShape(QFrame.Shape.HLine)
        default_mode_separator.setFrameShadow(QFrame.Shadow.Sunken)
        default_mode_separator.setStyleSheet(f"color: {COLORS['border']};")
        root.addWidget(default_mode_separator)
        toggle_layout = QHBoxLayout()
        toggle_layout.setSpacing(10)
        self.thermal_button = QPushButton('Thermal Printer')
        self.normal_button = QPushButton('Normal Printer (A4/A5)')
        self.section_button_group = QButtonGroup(self)
        self.section_button_group.setExclusive(True)
        toggle_button_style = f"\n            QPushButton {{\n                background-color: {COLORS['surface']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 8px 16px;\n                font-weight: bold;\n            }}\n            QPushButton:checked {{\n                background-color: {COLORS['primary']};\n                color: white;\n            }}\n        "
        for button in (self.thermal_button, self.normal_button):
            button.setCheckable(True)
            button.setMinimumHeight(34)
            button.setStyleSheet(toggle_button_style)
            button.hide()
            toggle_layout.addWidget(button)
            self.section_button_group.addButton(button)
        toggle_layout.addStretch()
        root.addLayout(toggle_layout)
        self.section_stack = QStackedWidget()
        self.section_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.section_stack, 1)
        self.thermal_page = QWidget()
        thermal_layout = QHBoxLayout(self.thermal_page)
        thermal_layout.setContentsMargins(0, 0, 0, 0)
        thermal_layout.setSpacing(16)
        controls_frame = self._panel_frame()
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(14, 14, 14, 14)
        controls_layout.setSpacing(12)
        blue_button_style = '\n            QPushButton {\n                background-color: #0056b3;\n                color: white;\n                font-weight: bold;\n                border-radius: 4px;\n                padding: 6px 12px;\n            }\n            QPushButton:hover {\n                background-color: #004494;\n                color: white;\n            }\n            QPushButton:pressed {\n                background-color: #003a7a;\n                color: white;\n            }\n            QPushButton:disabled {\n                background-color: #9ca3af;\n                color: #f3f4f6;\n            }\n        '
        self.paper_size_combo = self._combo(list(self.PAPER_SIZES))
        self.paper_size_combo.setCurrentText(self.THERMAL_PAPER_SIZE)
        self.paper_size_combo.hide()
        self.thermal_printer_combo = self._combo([])
        self.normal_printer_combo = self._combo([])
        self.printer_combo = self.thermal_printer_combo
        self.theme_combo = self._combo(list(THERMAL_THEME_OPTIONS))
        self.paper_roll_size_combo = self._combo(list(THERMAL_PAPER_SIZE_OPTIONS))
        self.thermal_custom_width_spin = QSpinBox()
        self.thermal_custom_width_spin.setRange(300, 1200)
        self.thermal_custom_width_spin.setValue(self.THERMAL_DIMENSIONS[0])
        self.thermal_custom_width_spin.setSuffix(' px')
        self.thermal_custom_width_spin.setMinimumHeight(34)
        _ignore_value_control_wheel(self.thermal_custom_width_spin)
        self.thermal_custom_width_spin.setStyleSheet(f"\n            QSpinBox {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        self.thermal_text_size_combo = self._combo(list(THERMAL_TEXT_SIZE_OPTIONS))
        self.thermal_user_font_size_spin = QSpinBox()
        self.thermal_user_font_size_spin.setRange(6, 48)
        self.thermal_user_font_size_spin.setValue(DEFAULT_THERMAL_USER_FONT_SIZE)
        self.thermal_user_font_size_spin.setSuffix(' pt')
        self.thermal_user_font_size_spin.setMinimumHeight(34)
        _ignore_value_control_wheel(self.thermal_user_font_size_spin)
        self.thermal_user_font_size_spin.setStyleSheet(f"\n            QSpinBox {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        self.header_quote_input = self._line_edit()
        self.footer_quote_input = self._line_edit()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 48)
        self.font_size_spin.setValue(12)
        self.font_size_spin.setEnabled(False)
        self.font_size_spin.setMinimumHeight(34)
        _ignore_value_control_wheel(self.font_size_spin)
        self.font_size_spin.setStyleSheet(f"\n            QSpinBox {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        self.item_size_spin = QDoubleSpinBox()
        self.item_size_spin.setRange(0.1, 5.0)
        self.item_size_spin.setSingleStep(0.1)
        self.item_size_spin.setDecimals(1)
        self.item_size_spin.setValue(1.0)
        self.item_size_spin.setEnabled(False)
        self.item_size_spin.setMinimumHeight(34)
        _ignore_value_control_wheel(self.item_size_spin)
        self.item_size_spin.setStyleSheet(f"\n            QDoubleSpinBox {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        self.row_spacing_spin = QSpinBox()
        self.row_spacing_spin.setRange(0, 50)
        self.row_spacing_spin.setValue(5)
        self.row_spacing_spin.setMinimumHeight(34)
        _ignore_value_control_wheel(self.row_spacing_spin)
        self.row_spacing_spin.setStyleSheet(f"\n            QSpinBox {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        theme_group = QGroupBox('Themes')
        theme_layout = QGridLayout(theme_group)
        theme_layout.setHorizontalSpacing(10)
        theme_layout.setVerticalSpacing(10)
        theme_layout.addWidget(self._field_label('Select Theme'), 0, 0)
        theme_layout.addWidget(self.theme_combo, 0, 1)
        controls_layout.addWidget(theme_group)
        printer_group = QGroupBox('Printer')
        printer_layout = QGridLayout(printer_group)
        printer_layout.setHorizontalSpacing(10)
        printer_layout.setVerticalSpacing(10)
        printer_layout.addWidget(self._field_label('Select Printer'), 0, 0)
        printer_layout.addWidget(self.thermal_printer_combo, 0, 1)
        self.thermal_add_printer_button = QPushButton('Add New Printer (OS)')
        self.thermal_add_printer_button.setMinimumHeight(34)
        self.thermal_add_printer_button.setStyleSheet(blue_button_style)
        printer_layout.addWidget(self.thermal_add_printer_button, 1, 1)
        controls_layout.addWidget(printer_group)
        paper_group = QGroupBox('Paper Size')
        paper_layout = QGridLayout(paper_group)
        paper_layout.setHorizontalSpacing(10)
        paper_layout.setVerticalSpacing(10)
        paper_layout.addWidget(self._field_label('Paper Size'), 0, 0)
        paper_layout.addWidget(self.paper_roll_size_combo, 0, 1)
        self.custom_width_label = self._field_label('Custom Width')
        paper_layout.addWidget(self.custom_width_label, 1, 0)
        paper_layout.addWidget(self.thermal_custom_width_spin, 1, 1)
        controls_layout.addWidget(paper_group)
        text_size_group = QGroupBox('Invoice Text Size')
        text_size_layout = QGridLayout(text_size_group)
        text_size_layout.setHorizontalSpacing(10)
        text_size_layout.setVerticalSpacing(10)
        text_size_layout.addWidget(self._field_label('Text Size'), 0, 0)
        text_size_layout.addWidget(self.thermal_text_size_combo, 0, 1)
        self.user_font_size_label = self._field_label('User Font Size')
        text_size_layout.addWidget(self.user_font_size_label, 1, 0)
        text_size_layout.addWidget(self.thermal_user_font_size_spin, 1, 1)
        controls_layout.addWidget(text_size_group)
        header_group = QGroupBox('Company Info/Header Toggles')
        header_layout = QVBoxLayout(header_group)
        self.show_company_name_checkbox = _print_settings_checkbox('Show Company Name')
        self.show_company_name_checkbox.setChecked(True)
        self.show_company_address_checkbox = _print_settings_checkbox('Show Company Address')
        self.show_company_address_checkbox.setChecked(True)
        self.show_phone_number_checkbox = _print_settings_checkbox('Show Phone Number')
        self.show_phone_number_checkbox.setChecked(True)
        self.show_gstin_checkbox = _print_settings_checkbox('Show GSTIN')
        self.show_gstin_checkbox.setChecked(True)
        self.show_company_logo_checkbox = _print_settings_checkbox('Show Company Logo/Image')
        self.show_company_logo_checkbox.setChecked(True)
        for checkbox in (self.show_company_name_checkbox, self.show_company_address_checkbox, self.show_phone_number_checkbox, self.show_gstin_checkbox, self.show_company_logo_checkbox):
            header_layout.addWidget(checkbox)
        controls_layout.addWidget(header_group)
        designer_controls_group = QGroupBox('Thermal Designer Controls')
        form_layout = QGridLayout(designer_controls_group)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(12)
        form_layout.addWidget(self._field_label('Selected Font Size'), 0, 0)
        form_layout.addWidget(self.font_size_spin, 0, 1)
        self.bold_toggle_button = QPushButton('Toggle Bold')
        self.bold_toggle_button.setMinimumHeight(34)
        self.bold_toggle_button.setEnabled(False)
        self.bold_toggle_button.setStyleSheet(blue_button_style)
        form_layout.addWidget(self.bold_toggle_button, 1, 1)
        form_layout.addWidget(self._field_label('Header Quote (Top of Bill)'), 2, 0)
        form_layout.addWidget(self.header_quote_input, 2, 1)
        form_layout.addWidget(self._field_label('Footer Quote (Bottom of Bill)'), 3, 0)
        form_layout.addWidget(self.footer_quote_input, 3, 1)
        form_layout.addWidget(self._field_label('Image/Item Size'), 4, 0)
        form_layout.addWidget(self.item_size_spin, 4, 1)
        form_layout.addWidget(self._field_label('Row Spacing (pixels)'), 5, 0)
        form_layout.addWidget(self.row_spacing_spin, 5, 1)
        controls_layout.addWidget(designer_controls_group)
        self.show_item_barcode_checkbox = _print_settings_checkbox('Show Item Barcode Below Name')
        controls_layout.addWidget(self.show_item_barcode_checkbox)
        self.print_barcode_col_checkbox = _print_settings_checkbox('Print Barcode Column')
        self.print_barcode_col_checkbox.setChecked(True)
        controls_layout.addWidget(self.print_barcode_col_checkbox)
        self.print_gst_summary_checkbox = _print_settings_checkbox('Print GST Summary Table')
        self.print_gst_summary_checkbox.setChecked(True)
        controls_layout.addWidget(self.print_gst_summary_checkbox)
        self.show_total_items_checkbox = _print_settings_checkbox('Show Total Items Count')
        self.show_total_items_checkbox.setChecked(True)
        controls_layout.addWidget(self.show_total_items_checkbox)
        self.print_time_checkbox = _print_settings_checkbox('Print Time')
        controls_layout.addWidget(self.print_time_checkbox)
        self.bold_grand_total_checkbox = _print_settings_checkbox('Print Grand Total in Large/Bold Font')
        controls_layout.addWidget(self.bold_grand_total_checkbox)
        hardware_group = QGroupBox('Hardware')
        hardware_form = QGridLayout(hardware_group)
        hardware_form.setHorizontalSpacing(10)
        hardware_form.setVerticalSpacing(12)
        self.paper_cut_buffer_spin = QSpinBox()
        self.paper_cut_buffer_spin.setRange(0, 300)
        self.paper_cut_buffer_spin.setValue(int(THERMAL_HARDWARE_FEED_BUFFER_PX))
        self.paper_cut_buffer_spin.setMinimumHeight(34)
        _ignore_value_control_wheel(self.paper_cut_buffer_spin)
        self.paper_cut_buffer_spin.setStyleSheet(f"\n            QSpinBox {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        hardware_form.addWidget(self._field_label('Paper Cut Buffer (px)'), 0, 0)
        hardware_form.addWidget(self.paper_cut_buffer_spin, 0, 1)
        controls_layout.addWidget(hardware_group)
        self.add_image_button = QPushButton('Add Image / Signature')
        self.add_image_button.setMinimumHeight(34)
        self.add_image_button.setStyleSheet(blue_button_style)
        controls_layout.addWidget(self.add_image_button)
        self.delete_item_button = QPushButton('Delete Selected Item')
        self.delete_item_button.setMinimumHeight(34)
        self.delete_item_button.setEnabled(False)
        self.delete_item_button.setStyleSheet(blue_button_style)
        controls_layout.addWidget(self.delete_item_button)
        self.reset_layout_button = QPushButton('Reset to Default Layout')
        self.reset_layout_button.setMinimumHeight(34)
        self.reset_layout_button.setStyleSheet(blue_button_style)
        controls_layout.addWidget(self.reset_layout_button)
        self.test_print_button = QPushButton('Test Print Layout')
        self.test_print_button.setMinimumHeight(34)
        self.test_print_button.setStyleSheet(blue_button_style)
        controls_layout.addWidget(self.test_print_button)
        designer_frame = self._panel_frame()
        designer_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        designer_layout = QVBoxLayout(designer_frame)
        designer_layout.setContentsMargins(12, 12, 12, 12)
        designer_layout.setSpacing(10)
        preview_title = QLabel('WYSIWYG Print Designer')
        preview_title.setStyleSheet('font-size: 16px; font-weight: bold;')
        self.scene = PrintDesignerScene(self)
        self.canvas_view = PrintPreviewGraphicsView(self.scene)
        self.canvas_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas_view.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.canvas_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas_view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.canvas_view.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.canvas_view.setStyleSheet(f"\n            QGraphicsView {{\n                background-color: #d1d5db;\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n            }}\n        ")
        designer_layout.addWidget(preview_title)
        zoom_layout = QHBoxLayout()
        zoom_layout.setSpacing(8)
        zoom_label = QLabel('Zoom:')
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fit_to_view_button = QPushButton('Fit to View')
        self.fit_to_view_button.setMinimumHeight(30)
        self.fit_to_view_button.setStyleSheet(blue_button_style)
        zoom_layout.addWidget(zoom_label)
        zoom_layout.addWidget(self.zoom_slider, 1)
        zoom_layout.addWidget(self.fit_to_view_button)
        designer_layout.addLayout(zoom_layout)
        designer_layout.addWidget(self.canvas_view, 1)
        controls_scroll = self._make_side_controls_scroll(controls_frame)
        thermal_layout.addWidget(controls_scroll)
        thermal_layout.addWidget(designer_frame, 3)
        thermal_layout.setStretch(0, 0)
        thermal_layout.setStretch(1, 3)
        self.section_stack.addWidget(self.thermal_page)
        self.normal_page = QWidget()
        a4_layout = QHBoxLayout(self.normal_page)
        a4_layout.setContentsMargins(0, 0, 0, 0)
        a4_layout.setSpacing(16)
        a4_controls_frame = self._panel_frame()
        a4_controls_layout = QVBoxLayout(a4_controls_frame)
        a4_controls_layout.setContentsMargins(14, 14, 14, 14)
        a4_controls_layout.setSpacing(12)
        normal_title = QLabel('Normal Printer (A4/A5)')
        normal_title.setStyleSheet('font-size: 18px; font-weight: bold;')
        a4_controls_layout.addWidget(normal_title)
        self.a4_paper_size_combo = self._combo(list(A4_PAPER_SIZE_OPTIONS))
        normal_printer_group = QGroupBox('Printer')
        normal_printer_layout = QGridLayout(normal_printer_group)
        normal_printer_layout.setHorizontalSpacing(10)
        normal_printer_layout.setVerticalSpacing(10)
        normal_printer_layout.addWidget(self._field_label('Select Printer'), 0, 0)
        normal_printer_layout.addWidget(self.normal_printer_combo, 0, 1)
        self.normal_add_printer_button = QPushButton('Add New Printer (OS)')
        self.normal_add_printer_button.setMinimumHeight(34)
        self.normal_add_printer_button.setStyleSheet(blue_button_style)
        normal_printer_layout.addWidget(self.normal_add_printer_button, 1, 1)
        a4_controls_layout.addWidget(normal_printer_group)
        page_setup_group = QGroupBox('Page Setup')
        page_setup_layout = QGridLayout(page_setup_group)
        page_setup_layout.setHorizontalSpacing(10)
        page_setup_layout.setVerticalSpacing(10)
        page_setup_layout.addWidget(self._field_label('Paper Size'), 0, 0)
        page_setup_layout.addWidget(self.a4_paper_size_combo, 0, 1)
        a4_controls_layout.addWidget(page_setup_group)
        self.a4_theme_combo = self._combo(list(A4_THEME_OPTIONS))
        a4_theme_group = QGroupBox('Themes')
        a4_theme_layout = QGridLayout(a4_theme_group)
        a4_theme_layout.setHorizontalSpacing(10)
        a4_theme_layout.setVerticalSpacing(10)
        a4_theme_layout.addWidget(self._field_label('Themes'), 0, 0)
        a4_theme_layout.addWidget(self.a4_theme_combo, 0, 1)
        self.a4_theme_color_button = QPushButton('Select Theme Color')
        self.a4_theme_color_button.setMinimumHeight(34)
        self._apply_a4_theme_color_button_style()
        a4_theme_layout.addWidget(self._field_label('Theme Color'), 1, 0)
        a4_theme_layout.addWidget(self.a4_theme_color_button, 1, 1)
        a4_controls_layout.addWidget(a4_theme_group)
        header_toggles_group = QGroupBox('Header Toggles')
        header_toggles_layout = QVBoxLayout(header_toggles_group)
        self.a4_show_logo_checkbox = _print_settings_checkbox('Show Logo')
        self.a4_show_company_name_checkbox = _print_settings_checkbox('Show Company Name')
        self.a4_show_company_name_text_checkbox = _print_settings_checkbox('Show Company Name Text')
        self.a4_show_address_checkbox = _print_settings_checkbox('Show Address')
        self.a4_show_phone_checkbox = _print_settings_checkbox('Show Phone')
        self.a4_show_email_checkbox = _print_settings_checkbox('Show Email')
        self.a4_show_gstin_checkbox = _print_settings_checkbox('Show GSTIN')
        for checkbox in (self.a4_show_logo_checkbox, self.a4_show_company_name_checkbox, self.a4_show_company_name_text_checkbox, self.a4_show_address_checkbox, self.a4_show_phone_checkbox, self.a4_show_email_checkbox, self.a4_show_gstin_checkbox):
            checkbox.setChecked(True)
            header_toggles_layout.addWidget(checkbox)
        self.a4_print_time_checkbox = _print_settings_checkbox('Print Time')
        header_toggles_layout.addWidget(self.a4_print_time_checkbox)
        self.a4_select_logo_button = QPushButton('Select Logo Image')
        self.a4_select_logo_button.setMinimumHeight(34)
        self.a4_select_logo_button.setStyleSheet(blue_button_style)
        self.a4_logo_status_label = QLabel('Not uploaded')
        self.a4_logo_status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        logo_upload_layout = QHBoxLayout()
        logo_upload_layout.addWidget(self.a4_select_logo_button)
        logo_upload_layout.addWidget(self.a4_logo_status_label)
        header_toggles_layout.addLayout(logo_upload_layout)
        self.a4_select_signature_button = QPushButton('Select Signature Image')
        self.a4_select_signature_button.setMinimumHeight(34)
        self.a4_select_signature_button.setStyleSheet(blue_button_style)
        self.a4_signature_status_label = QLabel('Not uploaded')
        self.a4_signature_status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        signature_upload_layout = QHBoxLayout()
        signature_upload_layout.addWidget(self.a4_select_signature_button)
        signature_upload_layout.addWidget(self.a4_signature_status_label)
        header_toggles_layout.addLayout(signature_upload_layout)
        a4_controls_layout.addWidget(header_toggles_group)
        column_toggles_group = QGroupBox('Column Toggles')
        column_toggles_layout = QVBoxLayout(column_toggles_group)
        self.a4_show_hsn_sac_checkbox = _print_settings_checkbox('Show HSN/SAC')
        self.a4_show_mrp_checkbox = _print_settings_checkbox('Show MRP')
        self.a4_show_discount_checkbox = _print_settings_checkbox('Show Discount')
        self.a4_show_tax_rate_checkbox = _print_settings_checkbox('Show Tax Rate')
        self.a4_show_hsn_sac_checkbox.setChecked(True)
        self.a4_show_tax_rate_checkbox.setChecked(True)
        for checkbox in (self.a4_show_hsn_sac_checkbox, self.a4_show_mrp_checkbox, self.a4_show_discount_checkbox, self.a4_show_tax_rate_checkbox):
            column_toggles_layout.addWidget(checkbox)
        a4_controls_layout.addWidget(column_toggles_group)
        footer_details_group = QGroupBox('Footer Details')
        footer_details_layout = QVBoxLayout(footer_details_group)
        self.a4_bank_details_input = QTextEdit()
        self.a4_bank_details_input.setMinimumHeight(80)
        self.a4_bank_details_input.setPlaceholderText('Account No, IFSC')
        self.a4_bank_details_input.setStyleSheet(self._text_edit_style())
        self.terms_conditions_input = QTextEdit()
        self.terms_conditions_input.setMinimumHeight(110)
        self.terms_conditions_input.setPlaceholderText('Enter footer terms for A4 invoices.')
        self.terms_conditions_input.setStyleSheet(self._text_edit_style())
        self.a4_show_authorized_signatory_checkbox = _print_settings_checkbox('Show Authorized Signatory Line')
        self.a4_show_authorized_signatory_checkbox.setChecked(True)
        footer_details_layout.addWidget(self._field_label('Bank Details (Account No, IFSC)'))
        footer_details_layout.addWidget(self.a4_bank_details_input)
        footer_details_layout.addWidget(self._field_label('Terms & Conditions'))
        footer_details_layout.addWidget(self.terms_conditions_input)
        footer_details_layout.addWidget(self.a4_show_authorized_signatory_checkbox)
        a4_controls_layout.addWidget(footer_details_group)
        a4_controls_scroll = self._make_side_controls_scroll(a4_controls_frame)
        self.a4_preview_host = QFrame()
        self.a4_preview_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.a4_preview_host.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['input_text']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        preview_host_layout = QVBoxLayout(self.a4_preview_host)
        preview_host_layout.setContentsMargins(12, 12, 12, 12)
        self.a4_preview_stack = QStackedWidget()
        self.a4_preview_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.a4_preview_cover_page = QFrame()
        self.a4_preview_cover_page.setStyleSheet(
            f"QFrame {{ background-color: {COLORS['panel_bg']}; border: none; }}"
        )
        self.a4_preview_stack.addWidget(self.a4_preview_cover_page)
        preview_host_layout.addWidget(self.a4_preview_stack)
        self.a4_preview_placeholder = None
        self.a4_preview_browser = None
        a4_layout.addWidget(a4_controls_scroll)
        a4_layout.addWidget(self.a4_preview_host, 4)
        a4_layout.setStretch(0, 0)
        a4_layout.setStretch(1, 4)
        self.section_stack.addWidget(self.normal_page)
        self.section_stack.hide()
        self._sync_thermal_paper_size_controls()
        self._sync_thermal_text_size_controls()
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.save_button = QPushButton('Save Settings')
        self.cancel_button = QPushButton('Cancel')
        self.save_button.setMinimumHeight(34)
        self.cancel_button.setMinimumHeight(34)
        self.save_button.setStyleSheet(blue_button_style)
        self.cancel_button.setStyleSheet(blue_button_style)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        root.addLayout(button_layout)

    def _make_side_controls_scroll(self, panel: QFrame) -> QScrollArea:
        """Return a vertically scrollable left controls column with full content height."""
        from ui import theme

        scroll = QScrollArea()
        scroll.setObjectName('printSettingsControlsScroll')
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        scroll.setMinimumWidth(370)
        scroll.setMaximumWidth(370)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(theme.scrollbar_stylesheet())
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        panel.setMinimumWidth(340)
        panel.setMaximumWidth(340)
        scroll.setWidget(panel)
        panel.adjustSize()
        return scroll

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Keep scrollable control panels wide enough for their contents."""
        super().resizeEvent(event)
        for scroll in self.findChildren(QScrollArea, 'printSettingsControlsScroll'):
            panel = scroll.widget()
            if panel is not None:
                panel.adjustSize()

    def _panel_frame(self) -> QFrame:
        """Return a styled panel frame used by both sides of the split."""
        frame = QFrame()
        frame.setStyleSheet(f"\n            QFrame {{\n                background-color: {COLORS['surface']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 8px;\n            }}\n        ")
        return frame

    def _field_label(self, text: str) -> QLabel:
        """Return a consistent form label."""
        label = QLabel(text)
        label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-weight: bold;")
        return label

    def _combo(self, items: list[str]) -> QComboBox:
        """Return a styled dropdown with optional initial items."""
        combo = QComboBox()
        combo.addItems(items)
        combo.setMinimumHeight(34)
        _ignore_value_control_wheel(combo)
        combo.setStyleSheet(f"\n            QComboBox {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        return combo

    def _line_edit(self) -> QLineEdit:
        """Return a styled single-line print settings input."""
        line_edit = QLineEdit()
        line_edit.setMinimumHeight(34)
        line_edit.setStyleSheet(f"\n            QLineEdit {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        ")
        return line_edit

    def _text_edit_style(self) -> str:
        """Return common styling for multi-line print setting editors."""
        return f"\n            QTextEdit {{\n                background-color: {COLORS['background']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border']};\n                border-radius: 6px;\n                padding: 7px;\n            }}\n        "

    def _connect_signals(self) -> None:
        """Connect field changes to canvas redraw and save/cancel actions."""
        self.thermal_button.clicked.connect(lambda _checked: self._on_section_changed(0))
        self.normal_button.clicked.connect(lambda _checked: self._on_section_changed(1))
        self.paper_size_combo.currentTextChanged.connect(lambda _text: self._on_paper_size_changed())
        self.paper_roll_size_combo.currentTextChanged.connect(lambda _text: self._sync_thermal_paper_size_controls())
        self.paper_roll_size_combo.currentTextChanged.connect(lambda _text: self.populate_canvas())
        self.thermal_custom_width_spin.valueChanged.connect(lambda _value: self.populate_canvas())
        self.thermal_text_size_combo.currentTextChanged.connect(lambda _text: self._sync_thermal_text_size_controls())
        self.theme_combo.currentIndexChanged.connect(lambda _index: self.apply_theme_to_canvas())
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        self.item_size_spin.valueChanged.connect(self._on_item_size_changed)
        self.row_spacing_spin.valueChanged.connect(self._on_row_spacing_changed)
        self.zoom_slider.valueChanged.connect(self.apply_zoom)
        self.fit_to_view_button.clicked.connect(self.fit_preview_to_view)
        self.scene.selectionChanged.connect(self._on_canvas_selection_changed)
        self.bold_toggle_button.clicked.connect(self._toggle_selected_text_bold)
        self.show_item_barcode_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.print_barcode_col_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.print_gst_summary_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.show_total_items_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.print_time_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.bold_grand_total_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.show_company_name_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.show_company_address_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.show_phone_number_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.show_gstin_checkbox.toggled.connect(lambda _checked: self.populate_canvas())
        self.footer_quote_input.textEdited.connect(self._sync_terms_from_footer_quote)
        self.terms_conditions_input.textChanged.connect(self.populate_canvas)
        self.a4_paper_size_combo.currentTextChanged.connect(lambda _text: self.update_a4_preview())
        self.a4_theme_combo.currentTextChanged.connect(self.refresh_preview)
        self.a4_theme_color_button.clicked.connect(self._select_a4_theme_color)
        self.a4_show_logo_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_company_name_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_company_name_text_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_address_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_phone_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_email_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_gstin_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_print_time_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_hsn_sac_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_mrp_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_discount_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_show_tax_rate_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_bank_details_input.textChanged.connect(self.update_a4_preview)
        self.terms_conditions_input.textChanged.connect(self.update_a4_preview)
        self.a4_show_authorized_signatory_checkbox.toggled.connect(lambda _checked: self.update_a4_preview())
        self.a4_select_logo_button.clicked.connect(lambda _checked=False: self._select_a4_image(A4_LOGO_BASE64_KEY))
        self.a4_select_signature_button.clicked.connect(lambda _checked=False: self._select_a4_image(A4_SIGNATURE_BASE64_KEY))
        self.add_image_button.clicked.connect(self._add_image_from_file)
        self.delete_item_button.clicked.connect(self._delete_selected_items)
        self.reset_layout_button.clicked.connect(self._reset_to_default_layout)
        self.test_print_button.clicked.connect(self._test_print_layout)
        self.thermal_add_printer_button.clicked.connect(self._open_os_printer_settings)
        self.normal_add_printer_button.clicked.connect(self._open_os_printer_settings)
        self.save_button.clicked.connect(self._save_settings)
        self.cancel_button.clicked.connect(self._close_host_window)

    def _load_available_printers(self) -> None:
        """Populate the hardware printer dropdown from Qt's system printer list."""
        self.populate_printers()

    def populate_printers(self) -> None:
        """Populate thermal and normal printer dropdowns from local OS printers."""
        current_thermal = self._selected_thermal_printer_name()
        current_normal = self._selected_normal_printer_name()
        for combo in (self.thermal_printer_combo, self.normal_printer_combo):
            combo.blockSignals(True)
            combo.clear()
        try:
            printers = [printer.printerName() for printer in QPrinterInfo.availablePrinters() if printer.printerName()]
        except Exception as exc:
            LOGGER.exception('Printer enumeration failed: %s', exc)
            printers = []
        printer_names = sorted(set(printers), key=str.lower)
        default_name = ''
        try:
            default_name = QPrinterInfo.defaultPrinter().printerName()
        except Exception as exc:
            LOGGER.exception('Default printer lookup failed: %s', exc)
        for combo in (self.thermal_printer_combo, self.normal_printer_combo):
            if printer_names:
                combo.addItems(printer_names)
            else:
                combo.addItem('No installed printers found', '')
            combo.blockSignals(False)
        self._select_printer_combo(self.thermal_printer_combo, current_thermal or default_name)
        self._select_printer_combo(self.normal_printer_combo, current_normal or default_name)

    def _select_printer_combo(self, combo: QComboBox, printer_name: str) -> None:
        """Select a printer in a combo only when it is currently available."""
        clean_name = (printer_name or '').strip()
        if not clean_name:
            return
        index = combo.findText(clean_name, Qt.MatchFlag.MatchFixedString)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _open_os_printer_settings(self) -> None:
        """Open the Windows printer settings page for installing local printers."""
        try:
            startfile = getattr(os, 'startfile', None)
            if startfile is None:
                QMessageBox.information(self, 'Add Printer', 'Please open your operating system printer settings manually.')
                return
            startfile('ms-settings:printers')
            self.populate_printers()
        except Exception as exc:
            LOGGER.exception('Could not open OS printer settings: %s', exc)
            QMessageBox.warning(self, 'Add Printer', f'Could not open Windows printer settings.\nError: {exc}')

    def _refresh_active_company_state(self) -> None:
        """Read the current company GST and signature state from the database."""
        active_company_id = active_company_manager.get_active_company_id()
        self.company_id = self._explicit_company_id or active_company_id
        self.current_company_data = {}
        self.current_gst_type = 'Regular'
        if not self.company_id:
            return
        try:
            company = None
            if hasattr(self.db, 'get_company_by_id'):
                company = self.db.get_company_by_id(int(self.company_id))
            if not company and hasattr(self.db, 'get_active_company'):
                company = self.db.get_active_company()
            if isinstance(company, dict):
                self.current_company_data = company
                self.current_gst_type = _plain_text(company.get('gst_type')) or 'Regular'
        except Exception as exc:
            LOGGER.exception('Active company state refresh failed: %s', exc)

    def _load_settings(self) -> None:
        """Load persisted print settings into the dialog fields."""
        self._loading_settings = True
        self._refresh_active_company_state()
        if not self.company_id:
            self._loading_settings = False
            return
        try:
            settings = get_print_settings(self.db, self.company_id)
        except sqlite3.Error as e:
            print(f'Database Error: {e}')
            LOGGER.exception('Print settings load failed: %s', e)
            QMessageBox.critical(self, 'Load Error', f'Failed to load print settings.\nError: {str(e)}')
            self._loading_settings = False
            return
        except Exception as e:
            LOGGER.exception('Print settings load failed: %s', e)
            QMessageBox.critical(self, 'Load Error', f'Failed to load print settings.\nError: {str(e)}')
            self._loading_settings = False
            return
        self.saved_layout_coordinates = self._parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
        self.saved_layout_coordinates = _purge_removed_layout_blocks(_purge_bcd_header_blocks(self.saved_layout_coordinates))
        self.deleted_layout_item_ids = _deleted_layout_block_ids(self.saved_layout_coordinates)
        self.saved_header_quote, self.saved_footer_terms = _quote_values_from_settings(settings)
        self.saved_show_item_barcode = _show_item_barcode_below_name_from_settings(settings)
        self.saved_print_barcode_col = _print_barcode_col_from_settings(settings)
        self.header_quote_input.setText(self.saved_header_quote)
        self.footer_quote_input.setText(self.saved_footer_terms)
        layout_metadata = _layout_quote_metadata(self.saved_layout_coordinates)
        self.saved_default_print_mode = _plain_text(layout_metadata.get(DEFAULT_PRINT_MODE_KEY)) or _plain_text(settings.get(DEFAULT_PRINT_MODE_KEY)) or DEFAULT_PRINT_MODE
        if self.saved_default_print_mode not in DEFAULT_PRINT_MODE_OPTIONS:
            self.saved_default_print_mode = DEFAULT_PRINT_MODE
        self.default_mode_combo.blockSignals(True)
        self.default_mode_combo.setCurrentText(self.saved_default_print_mode)
        self.default_mode_combo.blockSignals(False)
        saved_theme = _active_thermal_theme(self.saved_layout_coordinates, settings)
        self.saved_bold_grand_total = _bold_grand_total_from_settings(settings, self.saved_layout_coordinates)
        if saved_theme == BOLD_TOTAL_THEME:
            self.saved_bold_grand_total = True
            saved_theme = DEFAULT_THERMAL_THEME
        if saved_theme not in THERMAL_THEME_OPTIONS:
            saved_theme = DEFAULT_THERMAL_THEME
        self.saved_paper_roll_size = _plain_text(layout_metadata.get(THERMAL_PAPER_SIZE_KEY)) or _plain_text(layout_metadata.get(PAPER_ROLL_SIZE_KEY)) or DEFAULT_PAPER_ROLL_SIZE
        if self.saved_paper_roll_size not in PAPER_ROLL_SIZE_OPTIONS:
            self.saved_paper_roll_size = DEFAULT_PAPER_ROLL_SIZE
        saved_custom_width = _layout_setting_int(self.saved_layout_coordinates, THERMAL_CUSTOM_WIDTH_PX_KEY, self.THERMAL_DIMENSIONS[0], 300, 1200)
        saved_text_size = _plain_text(layout_metadata.get(THERMAL_TEXT_SIZE_KEY))
        if saved_text_size not in THERMAL_TEXT_SIZE_OPTIONS:
            saved_text_size = DEFAULT_THERMAL_TEXT_SIZE
        saved_user_font_size = _layout_setting_int(self.saved_layout_coordinates, THERMAL_USER_FONT_SIZE_KEY, DEFAULT_THERMAL_USER_FONT_SIZE, 6, 48)
        self.saved_print_gst_summary = _layout_setting_bool(self.saved_layout_coordinates, PRINT_GST_SUMMARY_TABLE_KEY, True)
        self.saved_show_total_items = _layout_setting_bool(self.saved_layout_coordinates, SHOW_TOTAL_ITEMS_COUNT_KEY, True)
        self.saved_show_company_name = _layout_setting_bool(self.saved_layout_coordinates, SHOW_COMPANY_NAME_KEY, True)
        self.saved_show_company_address = _layout_setting_bool(self.saved_layout_coordinates, SHOW_COMPANY_ADDRESS_KEY, True)
        self.saved_show_company_logo = _layout_setting_bool(self.saved_layout_coordinates, SHOW_COMPANY_LOGO_KEY, True)
        self.saved_show_phone_number = _layout_setting_bool(self.saved_layout_coordinates, SHOW_PHONE_NUMBER_KEY, True)
        self.saved_show_gstin = _layout_setting_bool(self.saved_layout_coordinates, SHOW_GSTIN_KEY, True)
        self.saved_print_time = _layout_setting_bool(self.saved_layout_coordinates, PRINT_TIME_KEY, False)
        self.saved_paper_cut_buffer_px = _layout_setting_int(self.saved_layout_coordinates, PAPER_CUT_BUFFER_PX_KEY, int(THERMAL_HARDWARE_FEED_BUFFER_PX), 0, 300)
        terms_footer = _layout_setting_text(self.saved_layout_coordinates, TERMS_CONDITIONS_FOOTER_KEY, self.saved_footer_terms)
        a4_paper_size = _layout_setting_choice(self.saved_layout_coordinates, A4_PAPER_SIZE_KEY, A4_PAPER_SIZE_OPTIONS, DEFAULT_A4_PAPER_SIZE)
        saved_default_theme = _plain_text(settings.get('default_theme'))
        a4_theme_default = saved_default_theme if saved_default_theme in A4_THEME_OPTIONS else DEFAULT_A4_THEME
        a4_theme = _layout_setting_choice(self.saved_layout_coordinates, A4_THEME_KEY, A4_THEME_OPTIONS, a4_theme_default)
        a4_theme_color = self._normalize_a4_theme_color(_layout_setting_text(self.saved_layout_coordinates, A4_THEME_COLOR_KEY, _plain_text(settings.get(A4_THEME_COLOR_KEY)) or DEFAULT_A4_THEME_COLOR))
        a4_bank_details = _layout_setting_text(self.saved_layout_coordinates, A4_BANK_DETAILS_KEY, '')
        a4_terms_conditions = _layout_setting_text(self.saved_layout_coordinates, A4_TERMS_CONDITIONS_KEY, terms_footer)
        self.a4_logo_base64 = _layout_setting_text(self.saved_layout_coordinates, A4_LOGO_BASE64_KEY, _plain_text(settings.get(A4_LOGO_BASE64_KEY)))
        self.a4_signature_base64 = _layout_setting_text(self.saved_layout_coordinates, A4_SIGNATURE_BASE64_KEY, _plain_text(settings.get(A4_SIGNATURE_BASE64_KEY)))
        self.a4_paper_size_combo.blockSignals(True)
        self.a4_paper_size_combo.setCurrentText(a4_paper_size)
        self.a4_paper_size_combo.blockSignals(False)
        self.a4_theme_combo.blockSignals(True)
        self.a4_theme_combo.setCurrentText(a4_theme)
        self.a4_theme_combo.blockSignals(False)
        self.a4_theme_color = a4_theme_color
        self._apply_a4_theme_color_button_style()
        self._set_checkbox_checked(self.a4_show_logo_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_LOGO_KEY, True))
        self._set_checkbox_checked(self.a4_show_company_name_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_COMPANY_NAME_KEY, True))
        self._set_checkbox_checked(self.a4_show_company_name_text_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_COMPANY_NAME_TEXT_KEY, True))
        self._set_checkbox_checked(self.a4_show_address_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_ADDRESS_KEY, True))
        self._set_checkbox_checked(self.a4_show_phone_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_PHONE_KEY, True))
        self._set_checkbox_checked(self.a4_show_email_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_EMAIL_KEY, True))
        self._set_checkbox_checked(self.a4_show_gstin_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_GSTIN_KEY, True))
        self._set_checkbox_checked(self.a4_print_time_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_PRINT_TIME_KEY, False))
        self._set_checkbox_checked(self.a4_show_hsn_sac_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_HSN_SAC_KEY, True))
        self._set_checkbox_checked(self.a4_show_mrp_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_MRP_KEY, False))
        self._set_checkbox_checked(self.a4_show_discount_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_DISCOUNT_KEY, False))
        self._set_checkbox_checked(self.a4_show_tax_rate_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_TAX_RATE_KEY, True))
        self.a4_bank_details_input.blockSignals(True)
        self.a4_bank_details_input.setPlainText(a4_bank_details)
        self.a4_bank_details_input.blockSignals(False)
        self.terms_conditions_input.blockSignals(True)
        self.terms_conditions_input.setPlainText(a4_terms_conditions)
        self.terms_conditions_input.blockSignals(False)
        self._set_checkbox_checked(self.a4_show_authorized_signatory_checkbox, _layout_setting_bool(self.saved_layout_coordinates, A4_SHOW_AUTHORIZED_SIGNATORY_KEY, True))
        self._update_a4_image_status_labels()
        try:
            row_spacing = int(layout_metadata.get('row_spacing', 5))
        except (TypeError, ValueError):
            row_spacing = 5
        self.row_spacing_spin.setValue(max(0, min(50, row_spacing)))
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(saved_theme)
        self.theme_combo.blockSignals(False)
        self.paper_roll_size_combo.blockSignals(True)
        self.paper_roll_size_combo.setCurrentText(self.saved_paper_roll_size)
        self.paper_roll_size_combo.blockSignals(False)
        self.thermal_custom_width_spin.blockSignals(True)
        self.thermal_custom_width_spin.setValue(saved_custom_width)
        self.thermal_custom_width_spin.blockSignals(False)
        self.thermal_text_size_combo.blockSignals(True)
        self.thermal_text_size_combo.setCurrentText(saved_text_size)
        self.thermal_text_size_combo.blockSignals(False)
        self.thermal_user_font_size_spin.blockSignals(True)
        self.thermal_user_font_size_spin.setValue(saved_user_font_size)
        self.thermal_user_font_size_spin.blockSignals(False)
        self._sync_thermal_paper_size_controls()
        self._sync_thermal_text_size_controls()
        self.show_item_barcode_checkbox.blockSignals(True)
        self.show_item_barcode_checkbox.setChecked(self.saved_show_item_barcode)
        self.show_item_barcode_checkbox.blockSignals(False)
        self.print_barcode_col_checkbox.blockSignals(True)
        self.print_barcode_col_checkbox.setChecked(self.saved_print_barcode_col)
        self.print_barcode_col_checkbox.blockSignals(False)
        self.print_gst_summary_checkbox.blockSignals(True)
        self.print_gst_summary_checkbox.setChecked(self.saved_print_gst_summary)
        self.print_gst_summary_checkbox.blockSignals(False)
        self.show_total_items_checkbox.blockSignals(True)
        self.show_total_items_checkbox.setChecked(self.saved_show_total_items)
        self.show_total_items_checkbox.blockSignals(False)
        self.bold_grand_total_checkbox.blockSignals(True)
        self.bold_grand_total_checkbox.setChecked(self.saved_bold_grand_total)
        self.bold_grand_total_checkbox.blockSignals(False)
        self.show_company_name_checkbox.blockSignals(True)
        self.show_company_name_checkbox.setChecked(self.saved_show_company_name)
        self.show_company_name_checkbox.blockSignals(False)
        self.show_company_address_checkbox.blockSignals(True)
        self.show_company_address_checkbox.setChecked(self.saved_show_company_address)
        self.show_company_address_checkbox.blockSignals(False)
        self.show_company_logo_checkbox.blockSignals(True)
        self.show_company_logo_checkbox.setChecked(self.saved_show_company_logo)
        self.show_company_logo_checkbox.blockSignals(False)
        self.show_phone_number_checkbox.blockSignals(True)
        self.show_phone_number_checkbox.setChecked(self.saved_show_phone_number)
        self.show_phone_number_checkbox.blockSignals(False)
        self.show_gstin_checkbox.blockSignals(True)
        self.show_gstin_checkbox.setChecked(self.saved_show_gstin)
        self.show_gstin_checkbox.blockSignals(False)
        self.print_time_checkbox.blockSignals(True)
        self.print_time_checkbox.setChecked(self.saved_print_time)
        self.print_time_checkbox.blockSignals(False)
        self.paper_cut_buffer_spin.blockSignals(True)
        self.paper_cut_buffer_spin.setValue(self.saved_paper_cut_buffer_px)
        self.paper_cut_buffer_spin.blockSignals(False)
        paper_size = self._normalize_paper_size(settings)
        self.paper_size_combo.blockSignals(True)
        self.paper_size_combo.setCurrentText(paper_size)
        self.paper_size_combo.blockSignals(False)
        section_index = 0 if paper_size == self.THERMAL_PAPER_SIZE else 1
        self.thermal_button.blockSignals(True)
        self.normal_button.blockSignals(True)
        self.thermal_button.setChecked(section_index == 0)
        self.normal_button.setChecked(section_index == 1)
        self.thermal_button.blockSignals(False)
        self.normal_button.blockSignals(False)
        self.section_stack.setCurrentIndex(section_index)
        self.printer_combo = self.thermal_printer_combo if section_index == 0 else self.normal_printer_combo
        legacy_printer_name = settings.get('printer_name', '') or ''
        thermal_printer_name = _plain_text(layout_metadata.get(THERMAL_PRINTER_NAME_KEY)) or _plain_text(settings.get(THERMAL_PRINTER_NAME_KEY))
        normal_printer_name = _plain_text(layout_metadata.get(NORMAL_PRINTER_NAME_KEY)) or _plain_text(settings.get(NORMAL_PRINTER_NAME_KEY))
        if not thermal_printer_name and section_index == 0:
            thermal_printer_name = legacy_printer_name
        if not normal_printer_name and section_index == 1:
            normal_printer_name = legacy_printer_name
        self.populate_printers()
        self._select_printer_combo(self.thermal_printer_combo, thermal_printer_name)
        self._select_printer_combo(self.normal_printer_combo, normal_printer_name)
        self._loading_settings = False

    def _show_a4_preview_cover(self) -> None:
        """Show a solid preview panel while the A4 HTML is rendering."""
        if hasattr(self, 'a4_preview_stack'):
            self.a4_preview_stack.setCurrentWidget(self.a4_preview_cover_page)

    def _show_a4_preview_browser_panel(self) -> None:
        """Reveal the rendered A4 web preview."""
        if (
            hasattr(self, 'a4_preview_stack')
            and self.a4_preview_browser is not None
            and self._a4_preview_browser_ready
        ):
            self.a4_preview_stack.setCurrentWidget(self.a4_preview_browser)

    def _present_a4_preview_html(
        self,
        raw_html: str,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        """Load A4 HTML and reveal the browser only after the first paint."""
        self._ensure_a4_preview_browser(allow_hidden=True)
        browser = self.a4_preview_browser
        if browser is None:
            if on_ready is not None:
                on_ready()
            return

        use_cover = not self._a4_preview_initial_present_complete
        if use_cover:
            self._show_a4_preview_cover()

        fallback = QTimer(self)
        fallback.setSingleShot(True)
        state = {'done': False}

        def _finish() -> None:
            if state['done']:
                return
            state['done'] = True
            fallback.stop()
            try:
                browser.loadFinished.disconnect(_on_finished)
            except (RuntimeError, TypeError):
                pass
            if use_cover:
                self._a4_preview_initial_present_complete = True
                self._show_a4_preview_browser_panel()
            if on_ready is not None:
                on_ready()

        def _on_finished(ok: bool) -> None:
            if ok:
                QTimer.singleShot(0, _finish)
            else:
                _finish()

        browser.loadFinished.connect(_on_finished)
        fallback.timeout.connect(_finish)
        fallback.start(2500)
        browser.setHtml(raw_html)

    def _ensure_a4_preview_browser(self, *, allow_hidden: bool = False) -> None:
        """Create the A4 web preview only when Normal Printer is first needed."""
        if self._a4_preview_browser_ready:
            return
        if not allow_hidden and not self.isVisible():
            QTimer.singleShot(150, self._ensure_a4_preview_browser)
            return
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:
            LOGGER.exception("QWebEngineView import failed: %s", exc)
            return
        browser = QWebEngineView()
        browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        browser.setStyleSheet(f"""
            QWebEngineView {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['input_text']};
                border: none;
            }}
        """)
        self.a4_preview_stack.addWidget(browser)
        self.a4_preview_stack.setCurrentWidget(self.a4_preview_cover_page)
        self.a4_preview_browser = browser
        self._a4_preview_browser_ready = True

    def _refresh_a4_preview_lazy(self) -> None:
        """Initialize the web preview engine once, then render the sample invoice."""
        self.update_a4_preview()

    def _set_checkbox_checked(self, checkbox: QCheckBox, checked: bool) -> None:
        """Update a checkbox without firing live preview refresh signals."""
        checkbox.blockSignals(True)
        checkbox.setChecked(checked)
        checkbox.blockSignals(False)

    def _normalize_a4_theme_color(self, value: Any) -> str:
        """Return a valid A4 theme hex color or the configured default."""
        color = QColor(_plain_text(value) or DEFAULT_A4_THEME_COLOR)
        if not color.isValid():
            color = QColor(DEFAULT_A4_THEME_COLOR)
        return color.name().upper()

    def _apply_a4_theme_color_button_style(self) -> None:
        """Paint the A4 theme color button with the active color."""
        color_hex = self._normalize_a4_theme_color(self.a4_theme_color)
        self.a4_theme_color = color_hex
        if not hasattr(self, 'a4_theme_color_button'):
            return
        self.a4_theme_color_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex};
                color: #ffffff;
                border: 1px solid {color_hex};
                border-radius: 6px;
                font-weight: bold;
                padding: 7px;
            }}
            QPushButton:hover {{
                border: 1px solid {COLORS['border']};
            }}
        """)
        self.a4_theme_color_button.setText(f'Select Theme Color ({color_hex})')

    def _select_a4_theme_color(self) -> None:
        """Open a color picker and refresh the A4 preview when changed."""
        selected_color = QColorDialog.getColor(QColor(self.a4_theme_color), self, 'Select A4 Theme Color')
        if not selected_color.isValid():
            return
        self.a4_theme_color = selected_color.name().upper()
        self._apply_a4_theme_color_button_style()
        self.update_a4_preview()

    def _update_a4_image_status_labels(self) -> None:
        """Refresh upload status text for Normal Printer image settings."""
        if hasattr(self, 'a4_logo_status_label'):
            self.a4_logo_status_label.setText('Uploaded' if self.a4_logo_base64 else 'Not uploaded')
        if hasattr(self, 'a4_signature_status_label'):
            self.a4_signature_status_label.setText('Uploaded' if self.a4_signature_base64 else 'Not uploaded')

    def _select_a4_image(self, image_key: str) -> None:
        """Read a selected image into base64 Normal Printer settings state."""
        file_path, _selected_filter = QFileDialog.getOpenFileName(self, 'Select Image', '', 'Images (*.png *.jpg *.jpeg)')
        if not file_path:
            return
        try:
            with open(file_path, 'rb') as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode('ascii')
        except (OSError, ValueError) as exc:
            LOGGER.exception('A4 image upload failed for %s: %s', image_key, exc)
            QMessageBox.critical(self, 'Image Upload Error', f'Could not read the selected image file.\nError: {exc}')
            return
        if image_key == A4_LOGO_BASE64_KEY:
            self.a4_logo_base64 = encoded_image
        elif image_key == A4_SIGNATURE_BASE64_KEY:
            self.a4_signature_base64 = encoded_image
        else:
            return
        self._update_a4_image_status_labels()
        self.update_a4_preview()

    def _normalize_paper_size(self, settings: dict[str, str]) -> str:
        """Map saved print settings onto the designer paper section."""
        printer_type = _plain_text(settings.get('printer_type'))
        default_format = _plain_text(settings.get('default_format'))
        paper_size = _plain_text(settings.get('paper_size'))
        layout_metadata = _layout_quote_metadata(
            self._parse_layout_coordinates(settings.get('layout_coordinates', '') or '')
        )
        saved_mode = _plain_text(layout_metadata.get(DEFAULT_PRINT_MODE_KEY))
        if printer_type == 'Thermal':
            return self.THERMAL_PAPER_SIZE
        if printer_type == 'Regular':
            return self.A4_PAPER_SIZE
        if default_format == 'Thermal' or saved_mode == 'Thermal Receipt':
            return self.THERMAL_PAPER_SIZE
        if default_format in {self.A4_PAPER_SIZE, 'A4', 'A5'} or saved_mode == 'A4/A5 Invoice':
            return self.A4_PAPER_SIZE
        if paper_size in self.THERMAL_ALIASES:
            return self.THERMAL_PAPER_SIZE
        if paper_size in {self.A4_PAPER_SIZE, 'A4', 'A5'}:
            return self.A4_PAPER_SIZE
        return self.A4_PAPER_SIZE

    def _parse_layout_coordinates(self, raw_coordinates: str) -> dict[str, dict[str, Any]]:
        """Return saved layout coordinates or an empty mapping if invalid."""
        return parse_layout_coordinates(raw_coordinates)

    def _selected_printer_name(self) -> str:
        """Return the active section's selected hardware printer name."""
        if self._selected_printer_type() == 'Thermal':
            return self._selected_thermal_printer_name()
        return self._selected_normal_printer_name()

    def _selected_printer_combo_name(self, combo: QComboBox) -> str:
        """Return a combo's selected hardware printer name or an empty string."""
        data = combo.currentData()
        if data == '':
            return ''
        return combo.currentText().strip()

    def _selected_thermal_printer_name(self) -> str:
        """Return the selected thermal printer name or an empty string."""
        return self._selected_printer_combo_name(self.thermal_printer_combo)

    def _selected_normal_printer_name(self) -> str:
        """Return the selected normal printer name or an empty string."""
        return self._selected_printer_combo_name(self.normal_printer_combo)

    def _selected_printer_type(self) -> str:
        """Return the legacy printer type value implied by the paper choice."""
        if self.paper_size_combo.currentText() == self.THERMAL_PAPER_SIZE:
            return 'Thermal'
        return 'Regular'

    def _selected_paper_dimensions(self) -> tuple[int, int]:
        """Return canvas dimensions for the selected paper size."""
        if self.paper_size_combo.currentText() == self.THERMAL_PAPER_SIZE:
            if self.paper_roll_size_combo.currentText() == '4 Inch (100mm)':
                return (800, self.THERMAL_DIMENSIONS[1])
            if self.paper_roll_size_combo.currentText() == 'Custom Size':
                return (int(self.thermal_custom_width_spin.value()), self.THERMAL_DIMENSIONS[1])
            return self.THERMAL_DIMENSIONS
        return self.A4_DIMENSIONS

    def _theme_preserved_layout_entries(self) -> dict[str, dict[str, Any]]:
        """Return custom image entries that should survive theme changes."""
        preserved: dict[str, dict[str, Any]] = {}
        for block_id, values in self.saved_layout_coordinates.items():
            if not isinstance(values, dict) or block_id == LAYOUT_SETTINGS_BLOCK_ID:
                continue
            is_image_block = block_id == SIGNATURE_IMAGE_BLOCK_ID or block_id.startswith(LAYOUT_IMAGE_PREFIX) or _plain_text(values.get('type')) == 'image'
            if is_image_block:
                preserved[block_id] = dict(values)
                continue
            is_deleted_image_marker = _plain_text(values.get('type')) == 'deleted' and (block_id == SIGNATURE_IMAGE_BLOCK_ID or block_id.startswith(LAYOUT_IMAGE_PREFIX))
            if is_deleted_image_marker:
                preserved[block_id] = {'type': 'deleted'}
        return preserved

    def apply_theme_to_canvas(self) -> None:
        """Apply the selected thermal theme template to the live designer scene."""
        if self._loading_settings:
            return
        if self.paper_size_combo.currentText() != self.THERMAL_PAPER_SIZE:
            return
        theme_name = self.theme_combo.currentText().strip() or DEFAULT_THERMAL_THEME
        templates = thermal_theme_layout_templates(self._selected_paper_dimensions())
        template = templates.get(theme_name)
        if template is None:
            return
        current_metadata = dict(_layout_quote_metadata(self.saved_layout_coordinates))
        template_metadata = dict(template.get(LAYOUT_SETTINGS_BLOCK_ID, {}))
        current_metadata.update(template_metadata)
        current_metadata[THEME_KEY] = theme_name
        current_metadata[THERMAL_THEME_KEY] = theme_name
        themed_coordinates: dict[str, dict[str, Any]] = {LAYOUT_SETTINGS_BLOCK_ID: current_metadata}
        signature_text = _plain_text(self.saved_layout_coordinates.get(SIGNATURE_PLACEHOLDER_BLOCK_ID, {}).get('text'))
        for block_id, values in template.items():
            if block_id == LAYOUT_SETTINGS_BLOCK_ID or not isinstance(values, dict):
                continue
            themed_coordinates[block_id] = dict(values)
            if block_id == SIGNATURE_PLACEHOLDER_BLOCK_ID and signature_text:
                themed_coordinates[block_id]['text'] = signature_text
        themed_coordinates.update(self._theme_preserved_layout_entries())
        self.saved_layout_coordinates = themed_coordinates
        self.deleted_layout_item_ids = _deleted_layout_block_ids(self.saved_layout_coordinates)
        try:
            row_spacing = int(current_metadata.get('row_spacing', self.row_spacing_spin.value()))
        except (TypeError, ValueError):
            row_spacing = int(self.row_spacing_spin.value())
        self.row_spacing_spin.blockSignals(True)
        self.row_spacing_spin.setValue(max(0, min(50, row_spacing)))
        self.row_spacing_spin.blockSignals(False)
        self.populate_canvas()

    def _on_section_changed(self, row: int) -> None:
        """Switch between thermal and normal printer sections."""
        section_index = max(0, min(1, int(row)))
        self.section_stack.setCurrentIndex(section_index)
        target_paper_size = self.THERMAL_PAPER_SIZE if section_index == 0 else self.A4_PAPER_SIZE
        self.printer_combo = self.thermal_printer_combo if section_index == 0 else self.normal_printer_combo
        self.paper_size_combo.blockSignals(True)
        self.paper_size_combo.setCurrentText(target_paper_size)
        self.paper_size_combo.blockSignals(False)
        self.populate_canvas()
        if section_index == 1:
            if not self._a4_preview_browser_ready:
                self._show_a4_preview_cover()
            QTimer.singleShot(50, self._refresh_a4_preview_lazy)

    def _sync_thermal_paper_size_controls(self) -> None:
        """Show custom width only for thermal custom paper size."""
        is_custom = self.paper_roll_size_combo.currentText() == 'Custom Size'
        self.custom_width_label.setVisible(is_custom)
        self.thermal_custom_width_spin.setVisible(is_custom)
        self.thermal_custom_width_spin.setEnabled(is_custom)

    def _sync_thermal_text_size_controls(self) -> None:
        """Show exact font size only for user-defined thermal text size."""
        is_user_defined = self.thermal_text_size_combo.currentText() == 'User Defined'
        self.user_font_size_label.setVisible(is_user_defined)
        self.thermal_user_font_size_spin.setVisible(is_user_defined)
        self.thermal_user_font_size_spin.setEnabled(is_user_defined)

    def _on_paper_size_changed(self) -> None:
        """Redraw the paper canvas immediately when paper size changes."""
        self.populate_canvas()

    def _footer_terms_text(self) -> str:
        """Return footer terms from the multi-line editor with legacy fallback."""
        terms_text = self.terms_conditions_input.toPlainText().strip()
        if terms_text:
            return terms_text
        return self.footer_quote_input.text().strip()

    def update_a4_preview(self, on_ready: Callable[[], None] | None = None) -> None:
        """Render the Normal Printer A4/A5 preview through the A4 engine."""
        if self._loading_settings:
            if on_ready is not None:
                QTimer.singleShot(0, on_ready)
            return
        if hasattr(self, 'section_stack') and self.section_stack.currentIndex() == 1:
            self._ensure_a4_preview_browser(allow_hidden=True)
        if not self._a4_preview_browser_ready or self.a4_preview_browser is None:
            if on_ready is not None:
                on_ready()
            return

        def preview_error(message: str) -> str:
            """Return simple HTML for non-fatal A4 preview failures."""
            safe_message = html.escape(str(message), quote=True)
            return f'\n            <html>\n                <body style="font-family: Arial, sans-serif; color: #374151;">\n                    <h3>A4 Preview Unavailable</h3>\n                    <p>{safe_message}</p>\n                </body>\n            </html>\n            '
        try:
            from utils.a4_print_engine import generate_a4_html
        except Exception as exc:
            print(f'A4 preview engine import failed: {exc}')
            LOGGER.exception('A4 preview engine import failed: %s', exc)
            self._present_a4_preview_html(
                preview_error('The A4 print engine could not be loaded.'),
                on_ready=on_ready,
            )
            return
        current_theme = self.a4_theme_combo.currentText().strip() or DEFAULT_A4_THEME
        current_settings = {'default_format': self.A4_PAPER_SIZE, 'paper_size': self.a4_paper_size_combo.currentText() or DEFAULT_A4_PAPER_SIZE, A4_PAPER_SIZE_KEY: self.a4_paper_size_combo.currentText() or DEFAULT_A4_PAPER_SIZE, 'a4_preview_mode': True, 'printer_type': 'Regular', 'printer_name': self._selected_normal_printer_name(), NORMAL_PRINTER_NAME_KEY: self._selected_normal_printer_name(), 'theme': current_theme, A4_THEME_KEY: current_theme, 'theme_color': self.a4_theme_color, A4_THEME_COLOR_KEY: self.a4_theme_color, 'default_theme': current_theme, 'header_quote': self.header_quote_input.text().strip(), 'footer_terms': self._footer_terms_text(), 'terms_conditions_footer': self._footer_terms_text(), 'header_toggles': {'show_logo': self.a4_show_logo_checkbox.isChecked(), 'show_company_name': self.a4_show_company_name_checkbox.isChecked(), 'show_address': self.a4_show_address_checkbox.isChecked(), 'show_phone': self.a4_show_phone_checkbox.isChecked(), 'show_email': self.a4_show_email_checkbox.isChecked(), 'show_gstin': self.a4_show_gstin_checkbox.isChecked()}, 'show_company_logo': self.a4_show_logo_checkbox.isChecked(), 'show_company_name': self.a4_show_company_name_checkbox.isChecked(), A4_SHOW_COMPANY_NAME_TEXT_KEY: self.a4_show_company_name_text_checkbox.isChecked(), 'show_company_address': self.a4_show_address_checkbox.isChecked(), 'show_phone_number': self.a4_show_phone_checkbox.isChecked(), 'show_email': self.a4_show_email_checkbox.isChecked(), 'show_gstin': self.a4_show_gstin_checkbox.isChecked(), 'column_toggles': {'show_sl_no': True, 'show_item': True, 'show_hsn': self.a4_show_hsn_sac_checkbox.isChecked(), 'show_hsn_sac': self.a4_show_hsn_sac_checkbox.isChecked(), 'show_mrp': self.a4_show_mrp_checkbox.isChecked(), 'show_quantity': True, 'show_rate': True, 'show_discount': self.a4_show_discount_checkbox.isChecked(), 'show_tax_rate': self.a4_show_tax_rate_checkbox.isChecked(), 'show_taxable': True, 'show_cgst': True, 'show_sgst': True, 'show_igst': False, 'show_total': True}, 'show_bank_details': True, 'bank_details': self.a4_bank_details_input.toPlainText().strip(), A4_BANK_DETAILS_KEY: self.a4_bank_details_input.toPlainText().strip(), 'show_terms': True, A4_TERMS_CONDITIONS_KEY: self.terms_conditions_input.toPlainText().strip(), 'show_logo': self.a4_show_logo_checkbox.isChecked(), A4_SHOW_LOGO_KEY: self.a4_show_logo_checkbox.isChecked(), A4_SHOW_COMPANY_NAME_KEY: self.a4_show_company_name_checkbox.isChecked(), A4_SHOW_COMPANY_NAME_TEXT_KEY: self.a4_show_company_name_text_checkbox.isChecked(), 'show_address': self.a4_show_address_checkbox.isChecked(), A4_SHOW_ADDRESS_KEY: self.a4_show_address_checkbox.isChecked(), 'show_phone': self.a4_show_phone_checkbox.isChecked(), A4_SHOW_PHONE_KEY: self.a4_show_phone_checkbox.isChecked(), A4_SHOW_EMAIL_KEY: self.a4_show_email_checkbox.isChecked(), A4_SHOW_GSTIN_KEY: self.a4_show_gstin_checkbox.isChecked(), A4_SHOW_HSN_SAC_KEY: self.a4_show_hsn_sac_checkbox.isChecked(), A4_SHOW_MRP_KEY: self.a4_show_mrp_checkbox.isChecked(), A4_SHOW_DISCOUNT_KEY: self.a4_show_discount_checkbox.isChecked(), A4_SHOW_TAX_RATE_KEY: self.a4_show_tax_rate_checkbox.isChecked(), 'show_authorized_signatory': self.a4_show_authorized_signatory_checkbox.isChecked(), A4_SHOW_AUTHORIZED_SIGNATORY_KEY: self.a4_show_authorized_signatory_checkbox.isChecked(), A4_PRINT_TIME_KEY: self.a4_print_time_checkbox.isChecked(), 'show_signatory': self.a4_show_authorized_signatory_checkbox.isChecked(), 'signatory': 'Authorized Signatory', A4_LOGO_BASE64_KEY: self.a4_logo_base64, A4_SIGNATURE_BASE64_KEY: self.a4_signature_base64}
        current_settings.update(current_settings['column_toggles'])
        company_data = {'company_name': 'Faizan Pro Accounting Demo', 'business_name': 'Faizan Pro Accounting Demo', 'name': 'Faizan Pro Accounting Demo', 'company_address': '12 Market Road, Kozhikode, Kerala - 673001', 'address': '12 Market Road, Kozhikode, Kerala - 673001', 'company_gstin': '32ABCDE1234F1Z5', 'gstin': '32ABCDE1234F1Z5', 'phone': '98765 43210', 'phone_number': '98765 43210', 'email': 'accounts@example.com', 'state': 'Kerala'}
        cart_data = [{'sl_no': 1, 'product_name': 'Premium Basmati Rice 25kg', 'name': 'Premium Basmati Rice 25kg', 'description': 'Premium Basmati Rice 25kg', 'hsn': '1006', 'quantity': 2, 'qty': 2, 'rate': 900.0, 'gross': 1800.0, 'discount': 90.0, 'net_value': 1710.0, 'taxable_value': 1710.0, 'tax_percent': 5.0, 'cgst': 42.75, 'sgst': 42.75, 'cgst_amount': 42.75, 'sgst_amount': 42.75, 'igst_amount': 0.0, 'tax_amount': 85.5, 'total': 1795.5, 'grand_total': 1795.5}, {'sl_no': 2, 'product_name': 'Cold Pressed Mustard Oil', 'name': 'Cold Pressed Mustard Oil', 'description': 'Cold Pressed Mustard Oil', 'hsn': '1514', 'quantity': 5, 'qty': 5, 'rate': 250.0, 'gross': 1250.0, 'discount': 0.0, 'net_value': 1250.0, 'taxable_value': 1250.0, 'tax_percent': 18.0, 'cgst': 112.5, 'sgst': 112.5, 'cgst_amount': 112.5, 'sgst_amount': 112.5, 'igst_amount': 0.0, 'tax_amount': 225.0, 'total': 1475.0, 'grand_total': 1475.0}, {'sl_no': 3, 'product_name': 'Reusable Cotton Shopping Bag', 'name': 'Reusable Cotton Shopping Bag', 'description': 'Reusable Cotton Shopping Bag', 'hsn': '4202', 'quantity': 3, 'qty': 3, 'rate': 320.0, 'gross': 960.0, 'discount': 60.0, 'net_value': 900.0, 'taxable_value': 900.0, 'tax_percent': 12.0, 'cgst': 54.0, 'sgst': 54.0, 'cgst_amount': 54.0, 'sgst_amount': 54.0, 'igst_amount': 0.0, 'tax_amount': 108.0, 'total': 1008.0, 'grand_total': 1008.0}]
        dummy_totals = {'bill_type': 'TAX_INVOICE', 'invoice_number': 'A4-DEMO-0001', 'bill_no': 'A4-DEMO-0001', 'invoice_date': '2026-06-11', 'bill_date': '2026-06-11', 'customer_name': 'ABC Retail Stores', 'party_name': 'ABC Retail Stores', 'customer_gstin': '32AAECA1234F1Z2', 'party_gstin': '32AAECA1234F1Z2', 'customer_address': 'Near Civil Station, Kochi, Kerala - 682030', 'party_address': 'Near Civil Station, Kochi, Kerala - 682030', 'mobile': '91234 56780', 'state': 'Kerala', 'sales_type': 'Tax Invoice', 'payment_mode': 'Credit', 'subtotal': 3860.0, 'sub_total': 3860.0, 'taxable_total': 3860.0, 'discount': 150.0, 'discount_total': 150.0, 'cgst': 209.25, 'sgst': 209.25, 'cgst_total': 209.25, 'sgst_total': 209.25, 'igst_total': 0.0, 'tax_total': 418.5, 'round_off': 0.5, 'grand_total': 4279.0, 'total': 4279.0, 'total_amount': 4279.0, 'amount_received': 1000.0, 'balance': 3279.0, 'amount_in_words': 'Four Thousand Two Hundred Seventy Nine Rupees Only', 'total_items': 10, 'narration': 'Sample A4 preview invoice.', 'bank_details': current_settings['bank_details'], 'footer_terms': current_settings['footer_terms'], 'terms_conditions': current_settings['terms_conditions_footer'], 'signatory': current_settings['signatory']}
        try:
            raw_html = str(generate_a4_html(company_data, cart_data, 'TAX_INVOICE', dummy_totals, current_settings, theme_name=current_theme) or '')
            self._present_a4_preview_html(raw_html, on_ready=on_ready)
        except Exception as exc:
            print(f'A4 preview generation failed: {exc}')
            LOGGER.exception('A4 preview generation failed: %s', exc)
            self._present_a4_preview_html(
                preview_error(f'The preview could not be generated: {exc}'),
                on_ready=on_ready,
            )

    def refresh_preview(self, *_args: Any) -> None:
        """Refresh the visible A4 preview after theme or option changes."""
        self.update_a4_preview()

    def _sync_terms_from_footer_quote(self, footer_quote: str) -> None:
        """Keep legacy footer edits flowing into the multi-line terms field."""
        self.terms_conditions_input.blockSignals(True)
        self.terms_conditions_input.setPlainText(footer_quote)
        self.terms_conditions_input.blockSignals(False)
        self.populate_canvas()
        self.update_a4_preview()

    def _selected_text_item(self) -> Optional[QGraphicsTextItem]:
        """Return the first selected text item on the designer canvas."""
        for item in self.scene.selectedItems():
            if isinstance(item, QGraphicsTextItem):
                return item
        return None

    def _selected_layout_item(self) -> Optional[QGraphicsItem]:
        """Return the first selected item tracked by the designer layout."""
        for item in self.scene.selectedItems():
            block_id = item.data(0)
            if isinstance(block_id, str) and self.layout_items.get(block_id) is item:
                return item
        return None

    def _is_deletable_layout_item(self, item: QGraphicsItem) -> bool:
        """Return whether the selected item is tracked by the designer layout."""
        block_id = item.data(0)
        if not isinstance(block_id, str):
            return False
        return self.layout_items.get(block_id) is item

    def _is_image_layout_item(self, item: QGraphicsItem) -> bool:
        """Return whether the item is a custom/logo/signature image block."""
        block_id = item.data(0)
        return isinstance(block_id, str) and self.layout_items.get(block_id) is item and isinstance(item, QGraphicsPixmapItem) and (block_id.startswith(LAYOUT_IMAGE_PREFIX) or block_id == SIGNATURE_IMAGE_BLOCK_ID)

    def _is_core_layout_anchor(self, item: QGraphicsItem) -> bool:
        """Return whether the item is a built-in invoice layout anchor."""
        block_id = item.data(0)
        if not isinstance(block_id, str):
            return False
        if self.layout_items.get(block_id) is not item:
            return False
        if self._is_image_layout_item(item):
            return False
        if block_id == 'company_name':
            return False
        return block_id in self._default_layout_blocks() or block_id in ITEM_COLUMN_ANCHOR_IDS or block_id in SAMPLE_ITEM_ROW_IDS

    def _on_canvas_selection_changed(self) -> None:
        """Sync edit controls with the currently selected designer item."""
        self._sync_font_size_control(self._selected_text_item())
        self._sync_item_size_control(self._selected_layout_item())

    def _sync_font_size_control(self, item: Optional[QGraphicsTextItem]) -> None:
        """Enable and update the font-size control for selectable text blocks."""
        self.font_size_spin.blockSignals(True)
        self.bold_toggle_button.blockSignals(True)
        if item is None:
            self.font_size_spin.setEnabled(False)
            self.bold_toggle_button.setEnabled(False)
            self.bold_toggle_button.setText('Toggle Bold')
        else:
            font_size = item.font().pointSizeF()
            if font_size <= 0:
                font_size = float(item.font().pointSize())
            self.font_size_spin.setValue(max(6, min(48, int(round(font_size)))))
            self.font_size_spin.setEnabled(True)
            self.bold_toggle_button.setEnabled(True)
            self.bold_toggle_button.setText('Bold: On' if item.font().bold() else 'Bold: Off')
            self.bold_toggle_button.setChecked(item.font().bold())
        self.font_size_spin.blockSignals(False)
        self.bold_toggle_button.blockSignals(False)

    def _sync_item_size_control(self, item: Optional[QGraphicsItem]) -> None:
        """Enable and update the scale control for selectable layout items."""
        self.item_size_spin.blockSignals(True)
        if item is None:
            self.item_size_spin.setValue(1.0)
            self.item_size_spin.setEnabled(False)
            self.delete_item_button.setEnabled(False)
        else:
            self.item_size_spin.setValue(max(0.1, min(5.0, float(item.scale()))))
            self.item_size_spin.setEnabled(True)
            self.delete_item_button.setEnabled(any((self._is_deletable_layout_item(selected) for selected in self.scene.selectedItems())))
        self.item_size_spin.blockSignals(False)

    def _on_font_size_changed(self, font_size: int) -> None:
        """Apply the selected font size immediately to the selected text item."""
        item = self._selected_text_item()
        if item is None:
            return
        font = item.font()
        font.setPointSize(int(font_size))
        _apply_font_rendering_hints(font)
        item.setFont(font)
        self._sync_font_size_control(item)

    def _on_item_size_changed(self, scale: float) -> None:
        """Apply the selected scale to all selected tracked layout items."""
        selected_items = list(self.scene.selectedItems())
        for item in selected_items:
            block_id = item.data(0)
            if isinstance(block_id, str) and self.layout_items.get(block_id) is item:
                item.setScale(max(0.1, min(5.0, float(scale))))

    def _on_row_spacing_changed(self, spacing: int) -> None:
        """Move thermal sample rows to preview row spacing immediately."""
        for sample_id, (anchor_id, _sample_text) in SAMPLE_ITEM_ROW_ELEMENTS.items():
            sample_item = self.layout_items.get(sample_id)
            anchor_item = self.layout_items.get(anchor_id)
            if not isinstance(sample_item, QGraphicsTextItem) or anchor_item is None:
                continue
            font_metrics = QFontMetrics(sample_item.font())
            sample_y = float(anchor_item.pos().y()) + float(font_metrics.lineSpacing()) + float(spacing)
            sample_item.setY(sample_y)

    def _toggle_selected_text_bold(self) -> None:
        """Toggle bold formatting for the selected designer text item."""
        item = self._selected_text_item()
        if item is None:
            return
        font = item.font()
        font.setBold(not font.bold())
        _apply_font_rendering_hints(font)
        item.setFont(font)
        self._sync_font_size_control(item)

    def _delete_selected_items(self) -> None:
        """Remove selected layout items from the scene and save registry."""
        selected_items = list(self.scene.selectedItems())
        if not selected_items:
            return
        if any((self._is_core_layout_anchor(item) for item in selected_items)):
            QMessageBox.warning(self, 'Restricted', 'Core layout anchors cannot be deleted. You may only move them.')
            return
        for item in selected_items:
            block_id = item.data(0)
            if not self._is_deletable_layout_item(item):
                continue
            try:
                self.layout_items.pop(block_id, None)
                self.saved_layout_coordinates.pop(block_id, None)
                if block_id == 'company_name':
                    self.deleted_layout_item_ids.add(block_id)
                elif block_id == SIGNATURE_IMAGE_BLOCK_ID:
                    self.deleted_layout_item_ids.add(block_id)
                elif isinstance(block_id, str) and block_id.startswith(LAYOUT_IMAGE_PREFIX):
                    self.deleted_layout_item_ids.discard(block_id)
                if item.scene() is self.scene:
                    self.scene.removeItem(item)
            except Exception as exc:
                LOGGER.exception('Designer item deletion failed: %s', exc)
        self._sync_font_size_control(self._selected_text_item())
        self._sync_item_size_control(self._selected_layout_item())

    def _reset_to_default_layout(self) -> None:
        """Clear saved coordinates and rebuild the designer from defaults."""
        company_id = self.company_id or active_company_manager.get_active_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Print Settings', 'Please open a company first.')
            return
        try:
            current_settings = get_print_settings(self.db, company_id)
            success = save_print_settings(self.db, company_id, default_format=current_settings.get('default_format', self.A4_PAPER_SIZE), default_theme=current_settings.get('default_theme', 'Classic'), printer_name=current_settings.get('printer_name', ''), printer_type=current_settings.get('printer_type', 'Regular'), paper_size=current_settings.get('paper_size', self.A4_PAPER_SIZE), header_quote=current_settings.get('header_quote', ''), footer_terms=current_settings.get('footer_terms', ''), layout_coordinates='', show_item_barcode=current_settings.get('show_item_barcode', '0'))
        except sqlite3.Error as exc:
            print(f'Database Error: {exc}')
            LOGGER.exception('Layout reset failed: %s', exc)
            QMessageBox.critical(self, 'Print Settings', f'Could not reset layout.\nError: {str(exc)}')
            return
        except Exception as exc:
            LOGGER.exception('Layout reset failed: %s', exc)
            success = False
        if not success:
            QMessageBox.critical(self, 'Print Settings', 'Could not reset layout.')
            return
        self.saved_layout_coordinates = {}
        self.deleted_layout_item_ids.clear()
        self.row_spacing_spin.setValue(5)
        self.populate_canvas()
        QMessageBox.information(self, 'Print Settings', 'Layout reset to defaults. Please click Save.')

    def draw_paper_canvas(self) -> QGraphicsRectItem:
        """Draw and return the visual white paper rectangle on the scene."""
        width, height = self._selected_paper_dimensions()
        self.paper_dimensions = (width, height)
        if isinstance(self.scene, PrintDesignerScene):
            self.scene.set_paper_size(width, height)
            if self.paper_size_combo.currentText() == self.THERMAL_PAPER_SIZE:
                self.scene.setProperty(THERMAL_WIDTH_MM_KEY, _thermal_width_mm_from_px(width))
        paper_rect = _draw_paper_rect(self.scene, width, height)
        self.paper_rect_item = paper_rect
        self.canvas_view.centerOn(paper_rect)
        self._fit_canvas_view_to_scene()
        return paper_rect

    def populate_canvas(self) -> None:
        """Populate the graphics scene with draggable invoice layout blocks."""
        self.scene.clear()
        self.layout_items.clear()
        self.saved_layout_coordinates = _purge_removed_layout_blocks(_purge_bcd_header_blocks(self.saved_layout_coordinates))
        self.deleted_layout_item_ids.difference_update(BCD_HEADER_BLOCK_IDS)
        self.draw_paper_canvas()
        defaults = self._default_layout_blocks()
        thermal = self.paper_size_combo.currentText() == self.THERMAL_PAPER_SIZE
        if thermal:
            self.saved_layout_coordinates = _thermal_saved_layout_coordinates(self.saved_layout_coordinates, defaults)
        blocks = {block_id: self._merged_block(block_id, default_config) for block_id, default_config in defaults.items()}
        if thermal:
            blocks.update(_saved_thermal_column_blocks(self.saved_layout_coordinates))
            blocks = _apply_tax_summary_font_size(blocks, self.saved_layout_coordinates)
            blocks.update(_thermal_sample_row_blocks(blocks, self.saved_layout_coordinates))
            blocks = _apply_barcode_column_visibility(blocks, self.print_barcode_col_checkbox.isChecked())
        blocks = _apply_logo_header_offset(blocks, self.saved_layout_coordinates, self.show_company_logo_checkbox.isChecked())
        is_composition = self.current_gst_type.strip().lower() == 'composition'
        signature_config = _company_signature_config(self.current_company_data, self.saved_layout_coordinates, blocks)
        for block_id, config in blocks.items():
            if block_id in self.deleted_layout_item_ids:
                continue
            if block_id == 'item_table':
                if not thermal:
                    self._add_rect_block(block_id, config)
                continue
            if thermal and block_id in {'item_header', 'item_table_label'}:
                continue
            if thermal and block_id in THERMAL_TOTAL_FIELD_IDS:
                continue
            if block_id == 'invoice_title':
                config = dict(config)
                config['text'] = 'BILL OF SUPPLY' if is_composition else 'TAX INVOICE'
            if block_id == COMPOSITION_SUBHEADING_BLOCK_ID:
                if not is_composition:
                    continue
                config = dict(config)
                config['text'] = COMPOSITION_SUBHEADING_TEXT
            if block_id == 'header_quote':
                header_quote = self.header_quote_input.text().strip()
                if not header_quote:
                    continue
                config = dict(config)
                config['text'] = header_quote
            if block_id == HEADER_DATE_BLOCK_ID:
                config = dict(config)
                config['text'] = _preview_header_date_text(
                    _plain_text(config.get('text', '')),
                    self.print_time_checkbox.isChecked(),
                )
            if block_id == 'company_name' and (not self.show_company_name_checkbox.isChecked()):
                continue
            if block_id == 'address' and (not self.show_company_address_checkbox.isChecked()):
                continue
            if block_id == 'phone' and (not self.show_phone_number_checkbox.isChecked()):
                continue
            if block_id == 'gstin' and (not self.show_gstin_checkbox.isChecked()):
                continue
            if block_id == TOTAL_ITEMS_BLOCK_ID and (not self.show_total_items_checkbox.isChecked()):
                continue
            if block_id == FOOTER_TAX_SUMMARY_BLOCK_ID and (not self.print_gst_summary_checkbox.isChecked()):
                continue
            if block_id == 'footer_terms':
                config = dict(config)
                config['text'] = self._footer_terms_text()
            if block_id == ITEM_BARCODE_PLACEHOLDER_BLOCK_ID:
                if thermal or not self.show_item_barcode_checkbox.isChecked():
                    continue
            if thermal and block_id == 'sample_product_name' and self.show_item_barcode_checkbox.isChecked() and ('col_barcode' not in blocks):
                config = dict(config)
                config['text'] = 'Sample Item\n32651'
            if block_id == SIGNATURE_PLACEHOLDER_BLOCK_ID and signature_config is not None:
                continue
            self._add_text_block(block_id, config)
        if signature_config is not None:
            self._add_image_block(SIGNATURE_IMAGE_BLOCK_ID, signature_config)
        for block_id, config in _image_layout_blocks(self.saved_layout_coordinates).items():
            if block_id == SIGNATURE_IMAGE_BLOCK_ID:
                continue
            if not self.show_company_logo_checkbox.isChecked():
                continue
            self._add_image_block(block_id, config)
        self._on_row_spacing_changed(self.row_spacing_spin.value())
        self._sync_font_size_control(None)
        self._sync_item_size_control(None)
        self.canvas_view.centerOn(self.paper_rect_item)
        self._fit_canvas_view_to_scene()

    def _fit_canvas_view_to_scene(self, *, allow_deferred: bool = True) -> None:
        """Fit the complete scene into the print preview without moving items."""
        if not hasattr(self, 'canvas_view') or self.canvas_view is None:
            return
        viewport = self.canvas_view.viewport()
        if viewport.width() <= 0 or viewport.height() <= 0:
            if allow_deferred:
                QTimer.singleShot(0, lambda: self._fit_canvas_view_to_scene(allow_deferred=False))
            return
        set_auto_fit_enabled = getattr(self.canvas_view, 'set_auto_fit_enabled', None)
        if callable(set_auto_fit_enabled):
            set_auto_fit_enabled(True)
        if hasattr(self, 'zoom_slider'):
            previous_block_state = self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(100)
            self.zoom_slider.blockSignals(previous_block_state)
        self.canvas_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fit_scene_rect = getattr(self.canvas_view, 'fit_scene_rect', None)
        if callable(fit_scene_rect):
            fit_scene_rect(force=True)
            return
        scene_rect = self.scene.sceneRect()
        if scene_rect.isNull() or scene_rect.isEmpty():
            return
        self.canvas_view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def apply_zoom(self, value: int) -> None:
        """Apply a manual view transform without changing scene item positions."""
        set_auto_fit_enabled = getattr(self.canvas_view, 'set_auto_fit_enabled', None)
        if callable(set_auto_fit_enabled):
            set_auto_fit_enabled(False)
        scale_factor = value / 100.0
        self.canvas_view.setTransform(QTransform().scale(scale_factor, scale_factor))
        scrollbar_policy = Qt.ScrollBarPolicy.ScrollBarAsNeeded if value > 100 else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        self.canvas_view.setHorizontalScrollBarPolicy(scrollbar_policy)
        self.canvas_view.setVerticalScrollBarPolicy(scrollbar_policy)

    def fit_preview_to_view(self) -> None:
        """Restore the preview to the automatic whole-scene fit state."""
        scene_rect = self.scene.sceneRect()
        if scene_rect.isNull() or scene_rect.isEmpty():
            return
        if self.canvas_view.viewport().width() <= 0 or self.canvas_view.viewport().height() <= 0:
            return
        set_auto_fit_enabled = getattr(self.canvas_view, 'set_auto_fit_enabled', None)
        if callable(set_auto_fit_enabled):
            set_auto_fit_enabled(True)
        previous_block_state = self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(100)
        self.zoom_slider.blockSignals(previous_block_state)
        self.canvas_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas_view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _default_layout_blocks(self) -> dict[str, dict[str, Any]]:
        """Return sensible default block positions for the selected paper."""
        return default_layout_blocks(self.paper_size_combo.currentText(), self.paper_dimensions, self.current_company_data)

    def _merged_block(self, block_id: str, defaults: dict[str, Any]) -> dict[str, Any]:
        """Overlay saved coordinates and font size onto one default block."""
        return merge_layout_block(block_id, defaults, self.saved_layout_coordinates)

    def _item_flags(self) -> QGraphicsItem.GraphicsItemFlag:
        """Return movable/selectable flags for designer layout items."""
        return QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable

    def _add_text_block(self, block_id: str, config: dict[str, Any]) -> QGraphicsTextItem:
        """Add a draggable text item to the scene and item registry."""
        item = QGraphicsTextItem(str(config.get('text', '')))
        font_size = int(config.get('font_size', 12) or 12)
        font_family = str(config.get('font_family', 'Arial') or 'Arial')
        font = QFont(font_family, font_size)
        if font_family.lower() in {'consolas', 'courier', 'courier new'}:
            font.setStyleHint(QFont.StyleHint.Monospace)
        font.setBold(bool(config.get('bold', False)))
        _apply_font_rendering_hints(font)
        item.setFont(font)
        item.setDefaultTextColor(QColor('#111827'))
        text_width = config.get('text_width')
        if bool(config.get('align_center', False)) and text_width is not None:
            try:
                item.setTextWidth(max(1.0, float(text_width)))
            except (TypeError, ValueError):
                item.setTextWidth(-1.0)
        else:
            item.setTextWidth(-1.0)
        _apply_tight_text_document(item, bool(config.get('align_center', False)))
        item.setPos(float(config.get('x', 0)), float(config.get('y', 0)))
        _apply_saved_item_scale(item, config)
        item.setFlags(self._item_flags())
        if block_id == SIGNATURE_PLACEHOLDER_BLOCK_ID:
            item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setData(0, block_id)
        if bool(config.get('_preview_shifted', False)):
            item.setData(PREVIEW_SHIFTED_ROLE, True)
            item.setData(PREVIEW_SAVED_X_ROLE, config.get('_saved_x'))
            item.setData(PREVIEW_SAVED_Y_ROLE, config.get('_saved_y'))
            item.setData(PREVIEW_X_ROLE, float(config.get('x', 0)))
            item.setData(PREVIEW_Y_ROLE, float(config.get('y', 0)))
        self.scene.addItem(item)
        self.layout_items[block_id] = item
        return item

    def _add_rect_block(self, block_id: str, config: dict[str, Any]) -> QGraphicsRectItem:
        """Add a draggable rectangle item to the scene and item registry."""
        item = QGraphicsRectItem(0, 0, float(config.get('width', 200)), float(config.get('height', 120)))
        item.setPen(QPen(QColor('#374151'), 1, Qt.PenStyle.DashLine))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setPos(float(config.get('x', 0)), float(config.get('y', 0)))
        _apply_saved_item_scale(item, config)
        item.setFlags(self._item_flags())
        item.setData(0, block_id)
        self.scene.addItem(item)
        self.layout_items[block_id] = item
        return item

    def _next_image_block_id(self) -> str:
        """Return a stable id for a newly added image block."""
        index = 1
        while f'{LAYOUT_IMAGE_PREFIX}{index}' in self.layout_items:
            index += 1
        return f'{LAYOUT_IMAGE_PREFIX}{index}'

    def _add_image_block(self, block_id: str, config: dict[str, Any]) -> Optional[QGraphicsPixmapItem]:
        """Add a movable image/signature block to the designer scene."""
        item = _add_image_item(self.scene, block_id, config)
        if item is None:
            return None
        item.setFlags(self._item_flags())
        item.setData(1, _plain_text(config.get('path')))
        self.deleted_layout_item_ids.discard(block_id)
        self.layout_items[block_id] = item
        return item

    def _add_image_from_file(self) -> None:
        """Prompt for an image file and place it on the designer canvas."""
        file_path, _selected_filter = QFileDialog.getOpenFileName(self, 'Add Image / Signature', '', 'Images (*.png *.jpg *.jpeg)')
        if not file_path:
            return
        block_id = self._next_image_block_id()
        config = {'type': 'image', 'path': file_path, 'x': 40, 'y': 40, 'width': 200, 'height': 0, 'scale': 1.0}
        item = self._add_image_block(block_id, config)
        if item is None:
            QMessageBox.warning(self, 'Add Image', 'Could not load the selected image file.')
            return
        item.setSelected(True)

    def _serialize_layout_coordinates(self) -> str:
        """Serialize designer item positions and font sizes as JSON."""
        if isinstance(self.scene, PrintDesignerScene):
            self.scene.clear_snap_guides()
        coordinates: dict[str, dict[str, Any]] = {}
        for registered_block_id, item in self.layout_items.items():
            item_block_id = item.data(0)
            block_id = item_block_id if isinstance(item_block_id, str) and item_block_id else registered_block_id
            if isinstance(block_id, str) and block_id != PREFERRED_BARCODE_COLUMN_ID and _is_bcd_header_block(block_id, {}):
                continue
            if block_id in REMOVED_LAYOUT_BLOCK_IDS:
                continue
            position = item.pos()
            x_value = round(float(position.x()), 2)
            y_value = round(float(position.y()), 2)
            if bool(item.data(PREVIEW_SHIFTED_ROLE)):
                preview_x = _to_float(item.data(PREVIEW_X_ROLE))
                preview_y = _to_float(item.data(PREVIEW_Y_ROLE))
                if abs(float(position.x()) - preview_x) < 0.01 and abs(float(position.y()) - preview_y) < 0.01:
                    saved_x = item.data(PREVIEW_SAVED_X_ROLE)
                    saved_y = item.data(PREVIEW_SAVED_Y_ROLE)
                    x_value = round(_to_float(saved_x), 2)
                    y_value = round(_to_float(saved_y), 2)
            values: dict[str, Any] = {'x': x_value, 'y': y_value, 'scale': round(max(0.1, min(5.0, float(item.scale()))), 2)}
            if isinstance(item, QGraphicsTextItem):
                if _plain_text(item.toPlainText()) == BCD_HEADER_TEXT:
                    continue
                font_size = item.font().pointSizeF()
                if font_size <= 0:
                    font_size = float(item.font().pointSize())
                values['font_size'] = round(float(font_size), 2)
                if block_id == FOOTER_TAX_SUMMARY_BLOCK_ID:
                    values[TAX_SUMMARY_FONT_SIZE_KEY] = values['font_size']
                values['is_bold'] = bool(item.font().bold())
                if block_id in {SIGNATURE_PLACEHOLDER_BLOCK_ID, PREFERRED_BARCODE_COLUMN_ID}:
                    values['text'] = item.toPlainText().strip()
            if isinstance(item, QGraphicsRectItem):
                rect = item.rect()
                values['width'] = round(float(rect.width()), 2)
                values['height'] = round(float(rect.height()), 2)
            if isinstance(item, QGraphicsPixmapItem):
                rect = item.boundingRect()
                values['type'] = 'image'
                values['path'] = _plain_text(item.data(1))
                values['width'] = round(float(rect.width()), 2)
                values['height'] = round(float(rect.height()), 2)
            saved_values = self.saved_layout_coordinates.get(block_id, {})
            if isinstance(saved_values, dict):
                for metadata_key in ('align_center', 'font_family', 'text_width'):
                    if metadata_key in saved_values:
                        values[metadata_key] = saved_values[metadata_key]
            coordinates[block_id] = values
        if not self.print_barcode_col_checkbox.isChecked():
            for block_id in (*BARCODE_COLUMN_BLOCK_IDS, 'sample_barcode', 'sample_bcd'):
                saved_values = self.saved_layout_coordinates.get(block_id)
                if isinstance(saved_values, dict) and _plain_text(saved_values.get('type')) != 'deleted':
                    coordinates.setdefault(block_id, dict(saved_values))
        tax_summary_values = coordinates.get(FOOTER_TAX_SUMMARY_BLOCK_ID, self.saved_layout_coordinates.get(FOOTER_TAX_SUMMARY_BLOCK_ID, {}))
        if not isinstance(tax_summary_values, dict):
            tax_summary_values = {}
        tax_summary_font_size = _to_float(tax_summary_values.get(TAX_SUMMARY_FONT_SIZE_KEY)) or _to_float(tax_summary_values.get('font_size')) or 10.0
        for block_id in self.deleted_layout_item_ids:
            if block_id in REMOVED_LAYOUT_BLOCK_IDS:
                continue
            coordinates[block_id] = {'type': 'deleted'}
        coordinates[LAYOUT_SETTINGS_BLOCK_ID] = {'header_quote': self.header_quote_input.text().strip(), 'footer_quote': self._footer_terms_text(), 'footer_terms': self._footer_terms_text(), 'row_spacing': int(self.row_spacing_spin.value()), DEFAULT_PRINT_MODE_KEY: self.default_mode_combo.currentText() or DEFAULT_PRINT_MODE, PAPER_ROLL_SIZE_KEY: self.paper_roll_size_combo.currentText(), THEME_KEY: self.theme_combo.currentText(), THERMAL_THEME_KEY: self.theme_combo.currentText(), THERMAL_PAPER_SIZE_KEY: self.paper_roll_size_combo.currentText(), THERMAL_CUSTOM_WIDTH_PX_KEY: int(self.thermal_custom_width_spin.value()), THERMAL_WIDTH_MM_KEY: round(_thermal_width_mm_from_px(self._selected_paper_dimensions()[0]), 2), THERMAL_TEXT_SIZE_KEY: self.thermal_text_size_combo.currentText(), THERMAL_USER_FONT_SIZE_KEY: int(self.thermal_user_font_size_spin.value()), PRINT_GST_SUMMARY_TABLE_KEY: bool(self.print_gst_summary_checkbox.isChecked()), SHOW_TOTAL_ITEMS_COUNT_KEY: bool(self.show_total_items_checkbox.isChecked()), BOLD_GRAND_TOTAL_KEY: bool(self.bold_grand_total_checkbox.isChecked()), TERMS_CONDITIONS_FOOTER_KEY: self._footer_terms_text(), SHOW_COMPANY_NAME_KEY: bool(self.show_company_name_checkbox.isChecked()), SHOW_COMPANY_ADDRESS_KEY: bool(self.show_company_address_checkbox.isChecked()), SHOW_COMPANY_LOGO_KEY: bool(self.show_company_logo_checkbox.isChecked()), SHOW_PHONE_NUMBER_KEY: bool(self.show_phone_number_checkbox.isChecked()), SHOW_GSTIN_KEY: bool(self.show_gstin_checkbox.isChecked()), PRINT_TIME_KEY: bool(self.print_time_checkbox.isChecked()), PAPER_CUT_BUFFER_PX_KEY: int(self.paper_cut_buffer_spin.value()), PRINT_BARCODE_COL_KEY: bool(self.print_barcode_col_checkbox.isChecked()), THERMAL_PRINTER_NAME_KEY: self._selected_thermal_printer_name(), NORMAL_PRINTER_NAME_KEY: self._selected_normal_printer_name(), TAX_SUMMARY_FONT_SIZE_KEY: round(float(tax_summary_font_size), 2), SHOW_ITEM_BARCODE_BELOW_NAME_KEY: bool(self.show_item_barcode_checkbox.isChecked()), A4_PAPER_SIZE_KEY: self.a4_paper_size_combo.currentText(), A4_THEME_KEY: self.a4_theme_combo.currentText(), A4_THEME_COLOR_KEY: self.a4_theme_color, A4_SHOW_LOGO_KEY: bool(self.a4_show_logo_checkbox.isChecked()), A4_SHOW_COMPANY_NAME_KEY: bool(self.a4_show_company_name_checkbox.isChecked()), A4_SHOW_COMPANY_NAME_TEXT_KEY: bool(self.a4_show_company_name_text_checkbox.isChecked()), A4_SHOW_ADDRESS_KEY: bool(self.a4_show_address_checkbox.isChecked()), A4_SHOW_PHONE_KEY: bool(self.a4_show_phone_checkbox.isChecked()), A4_SHOW_EMAIL_KEY: bool(self.a4_show_email_checkbox.isChecked()), A4_SHOW_GSTIN_KEY: bool(self.a4_show_gstin_checkbox.isChecked()), A4_SHOW_HSN_SAC_KEY: bool(self.a4_show_hsn_sac_checkbox.isChecked()), A4_SHOW_MRP_KEY: bool(self.a4_show_mrp_checkbox.isChecked()), A4_SHOW_DISCOUNT_KEY: bool(self.a4_show_discount_checkbox.isChecked()), A4_SHOW_TAX_RATE_KEY: bool(self.a4_show_tax_rate_checkbox.isChecked()), A4_BANK_DETAILS_KEY: self.a4_bank_details_input.toPlainText().strip(), A4_TERMS_CONDITIONS_KEY: self.terms_conditions_input.toPlainText().strip(), A4_SHOW_AUTHORIZED_SIGNATORY_KEY: bool(self.a4_show_authorized_signatory_checkbox.isChecked()), A4_PRINT_TIME_KEY: bool(self.a4_print_time_checkbox.isChecked()), A4_LOGO_BASE64_KEY: self.a4_logo_base64, A4_SIGNATURE_BASE64_KEY: self.a4_signature_base64}
        return json.dumps(coordinates, sort_keys=True)

    def render_scene_to_printer(self, printer: QPrinter) -> None:
        """Render the designer scene onto an already configured QPrinter."""
        render_wysiwyg_scene_to_printer(self.scene, printer, self._selected_printer_type() == 'Thermal', self.layout_items.values(), self.paper_rect_item, self.paper_cut_buffer_spin.value())

    def _test_print_layout(self) -> None:
        """Print the live designer canvas to the selected hardware printer."""
        printer_name = self._selected_printer_name()
        if not printer_name:
            QMessageBox.warning(self, 'Test Print Layout', 'No hardware printer is selected. Please install or select a printer first.')
            return
        if isinstance(self.scene, PrintDesignerScene):
            self.scene.clear_snap_guides()
        self.scene.clearSelection()
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setPrinterName(printer_name)
            if not printer.isValid():
                QMessageBox.warning(self, 'Test Print Layout', f"Printer '{printer_name}' could not be found or is not ready.")
                return
            self.render_scene_to_printer(printer)
        except Exception as exc:
            LOGGER.exception('Designer test print failed: %s', exc)
            QMessageBox.critical(self, 'Test Print Layout', f'Test print failed: {exc}')
            return
        QMessageBox.information(self, 'Test Print Layout', f"Test layout sent to '{printer_name}' successfully.")

    def _save_settings(self) -> None:
        """Persist dialog selections and designer coordinates for the company."""
        company_id = self.company_id or active_company_manager.get_active_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Print Settings', 'Please open a company first.')
            return
        printer_name = self._selected_printer_name()
        if not printer_name:
            QMessageBox.warning(self, 'Print Settings', 'No hardware printer is available to save. Please install or select a printer.')
            return
        paper_size = self.paper_size_combo.currentText()
        printer_type = self._selected_printer_type()
        default_format = 'Thermal' if printer_type == 'Thermal' else self.A4_PAPER_SIZE
        try:
            if printer_type == 'Thermal':
                default_theme = self.theme_combo.currentText() or DEFAULT_THERMAL_THEME
            else:
                default_theme = self.a4_theme_combo.currentText() or DEFAULT_A4_THEME
            header_quote = self.header_quote_input.text().strip()
            footer_quote = self._footer_terms_text()
            success = save_print_settings(self.db, company_id, default_format=default_format, default_theme=default_theme, printer_name=printer_name, printer_type=printer_type, paper_size=paper_size, header_quote=header_quote, footer_terms=footer_quote, layout_coordinates=self._serialize_layout_coordinates(), show_item_barcode=self.show_item_barcode_checkbox.isChecked())
        except sqlite3.Error as e:
            print(f'Database Error: {e}')
            LOGGER.exception('Print settings save failed: %s', e)
            QMessageBox.critical(self, 'Save Error', f'Failed to save settings.\nError: {str(e)}')
            return
        except Exception as e:
            LOGGER.exception('Print settings save failed: %s', e)
            QMessageBox.critical(self, 'Save Error', f'Failed to save settings.\nError: {str(e)}')
            return
        if success:
            QMessageBox.information(self, 'Print Settings', 'Print settings saved successfully.')
            self._close_host_window()
            return
        QMessageBox.critical(self, 'Print Settings', 'Could not save print settings.')

PrintSettingsDialog = PrintSettingsWidget