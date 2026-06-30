"""
Barcode Printing Management module for the Accounting Desktop Application.

Reads master product / purchase data records and prints customised thermal
sticky labels (2 x 1 inch retail rolls) using a real-world text + barcode
tracking layout. The module is fully self-contained:

    * BarcodeSettings        - persisted shop name + numeric->letter price cipher.
    * encode_price_cipher()  - converts a purchase price into a hidden letter code.
    * LabelRenderEngine      - pixel-perfect ReportLab label rendering engine.
    * dispatch_to_printer()  - Windows spooler / cross-platform print dispatch.
    * BarcodeManagerWindow   - the operator workspace screen (top bar, grid, actions).

All database, PDF and hardware spooler interactions are wrapped in explicit
try-except barriers so a failure can never crash the host application.
"""
import os
import json
import re
import tempfile
try:
    import fitz
except Exception:
    fitz = None
try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except Exception:
    pdfmetrics = None
    TTFont = None
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox, QFrame, QSizePolicy, QTabWidget, QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QCheckBox, QFormLayout, QGroupBox, QApplication, QToolButton, QLayout, QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PySide6.QtCore import Qt, QCoreApplication, QSizeF, QMarginsF, QTimer, Signal, QEvent, QRect, QRectF, QPoint
from PySide6.QtGui import QDoubleValidator, QIntValidator, QPainter, QImage, QPixmap, QPageSize, QPageLayout, QBrush, QPen, QColor, QFont, QFontMetrics, QPalette
from PySide6.QtPrintSupport import QPrinter
from ui.table_header_utils import apply_adjustable_table_columns
from ui.checkbox_style import create_checkbox
from ui import theme
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin
try:
    from config import active_company_manager, CURRENCY_SYMBOL
except Exception:
    active_company_manager = None
    CURRENCY_SYMBOL = 'Rs'
DEFAULT_PRICE_DIGITS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
DEFAULT_PRICE_LETTERS = ['R', 'C', 'N', 'X', 'Z', 'Y', 'B', 'Q', 'W', 'M']
PRICE_KEY_COL_WIDTH = 34
PRICE_KEY_COL_COUNT = 10
DEFAULT_PRICE_KEY = 'RCNXZYBQWM'
BARCODE_PADDING_OPTIONS = ['No Padding', '2 Digits (00)', '3 Digits (000)', '4 Digits (0000)', '5 Digits (00000)']
FONT_THICKNESS_OPTIONS = ['Normal', 'Bold', 'Extra Bold']
LEGACY_EXTRA_BOLD_THICKNESS = 'Extra Bold (Thermal)'
DEFAULT_FONT_THICKNESS = 'Extra Bold'
REPORTLAB_NATIVE_FONT_CACHE = None
FONT_SIZE_MIN = 4
FONT_SIZE_MAX = 72
BARCODE_WIDTH_MIN = -100
BARCODE_WIDTH_MAX = 500
BARCODE_HEIGHT_MIN = -10
BARCODE_HEIGHT_MAX = 500
BARCODE_SIZE_STEP = 5
CODE39_QUIET_ZONE_MODULES = 10
CODE39_WIDE_MODULES = 3
CODE39_NARROW_MODULES = 1
CODE39_PATTERNS = {'0': 'nnnwwnwnn', '1': 'wnnwnnnnw', '2': 'nnwwnnnnw', '3': 'wnwwnnnnn', '4': 'nnnwwnnnw', '5': 'wnnwwnnnn', '6': 'nnwwwnnnn', '7': 'nnnwnnwnw', '8': 'wnnwnnwnn', '9': 'nnwwnnwnn', 'A': 'wnnnnwnnw', 'B': 'nnwnnwnnw', 'C': 'wnwnnwnnn', 'D': 'nnnnwwnnw', 'E': 'wnnnwwnnn', 'F': 'nnwnwwnnn', 'G': 'nnnnnwwnw', 'H': 'wnnnnwwnn', 'I': 'nnwnnwwnn', 'J': 'nnnnwwwnn', 'K': 'wnnnnnnww', 'L': 'nnwnnnnww', 'M': 'wnwnnnnwn', 'N': 'nnnnwnnww', 'O': 'wnnnwnnwn', 'P': 'nnwnwnnwn', 'Q': 'nnnnnnwww', 'R': 'wnnnnnwwn', 'S': 'nnwnnnwwn', 'T': 'nnnnwnwwn', 'U': 'wwnnnnnnw', 'V': 'nwwnnnnnw', 'W': 'wwwnnnnnn', 'X': 'nwnnwnnnw', 'Y': 'wwnnwnnnn', 'Z': 'nwwnwnnnn', '-': 'nwnnnnwnw', '.': 'wwnnnnwnn', ' ': 'nwwnnnwnn', '$': 'nwnwnwnnn', '/': 'nwnwnnnwn', '+': 'nwnnnwnwn', '%': 'nnnwnwnwn', '*': 'nwnnwnwnn'}
CODE39_SUPPORTED_CHARS = set(CODE39_PATTERNS) - {'*'}

def register_reportlab_native_fonts() -> tuple:
    """Register native Windows TrueType fonts for crisp thermal PDF text."""
    global REPORTLAB_NATIVE_FONT_CACHE
    if REPORTLAB_NATIVE_FONT_CACHE is not None:
        return REPORTLAB_NATIVE_FONT_CACHE
    body_font = 'Helvetica'
    bold_font = 'Helvetica-Bold'
    black_font = 'Helvetica-Bold'
    if pdfmetrics is None or TTFont is None:
        REPORTLAB_NATIVE_FONT_CACHE = (body_font, bold_font, black_font)
        return REPORTLAB_NATIVE_FONT_CACHE

    def ensure_font(font_name: str, font_path: str) -> bool:
        """Return True when font_name is available to ReportLab."""
        try:
            pdfmetrics.getFont(font_name)
            return True
        except Exception:
            pass
        try:
            if not os.path.exists(font_path):
                return False
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            return True
        except Exception:
            return False
    if ensure_font('Arial-Native', 'C:\\Windows\\Fonts\\arial.ttf'):
        body_font = 'Arial-Native'
    elif ensure_font('SegoeUI-Native', 'C:\\Windows\\Fonts\\segoeui.ttf'):
        body_font = 'SegoeUI-Native'
    if ensure_font('Arial-Native-Bold', 'C:\\Windows\\Fonts\\arialbd.ttf'):
        bold_font = 'Arial-Native-Bold'
    elif ensure_font('SegoeUI-Native-Bold', 'C:\\Windows\\Fonts\\segoeuib.ttf'):
        bold_font = 'SegoeUI-Native-Bold'
    black_font = bold_font
    if ensure_font('Arial-Native-Black', 'C:\\Windows\\Fonts\\ariblk.ttf'):
        black_font = 'Arial-Native-Black'
    REPORTLAB_NATIVE_FONT_CACHE = (body_font, bold_font, black_font)
    return REPORTLAB_NATIVE_FONT_CACHE

def normalize_font_thickness(value, fallback='Normal') -> str:
    """Return a supported per-element font thickness value."""
    text = str(value or '').strip()
    if text == LEGACY_EXTRA_BOLD_THICKNESS:
        return 'Extra Bold'
    if text in FONT_THICKNESS_OPTIONS:
        return text
    return fallback if fallback in FONT_THICKNESS_OPTIONS else 'Normal'

def default_price_map() -> dict:
    """Return the default digit-character -> capital-letter cipher mapping."""
    return {d: l for d, l in zip(DEFAULT_PRICE_DIGITS, DEFAULT_PRICE_LETTERS)}

def encode_price_cipher(value, key_map=None) -> str:
    """Translate a numeric purchase price into a hidden alphabetical cipher.

    ``key_map`` is a dict mapping each digit character ('0'-'9') to a capital
    letter; the decimal point becomes a forward slash. A legacy 10-character
    string (indexed by digit value) is also accepted for backward compatibility.
    Keeps supplier costs hidden from retail buyers on the printed tag.
    """
    if not key_map:
        key_map = default_price_map()
    elif isinstance(key_map, str):
        safe = (key_map + DEFAULT_PRICE_KEY)[:10]
        key_map = {str(i): safe[i] for i in range(10)}
    try:
        text = f'{float(value):.2f}'
    except (TypeError, ValueError):
        text = str(value or '')
    out = []
    for ch in text:
        if ch.isdigit():
            out.append(key_map.get(ch, ch))
        elif ch == '.':
            out.append('/')
        else:
            out.append(ch)
    return ''.join(out)
SAMPLE_LABEL_COMPANY = 'FAIZAN TEXTILES'
SAMPLE_LABEL_PRODUCT = 'Dhothi Premium Gold'
SAMPLE_LABEL_BARCODE = '1000016'
SAMPLE_LABEL_MRP = 450.0
SAMPLE_LABEL_MRP_TEXT = '₹ 450.00'
SAMPLE_LABEL_PURCHASE_PRICE = 250.75
SAMPLE_LABEL_CIPHER = encode_price_cipher(SAMPLE_LABEL_PURCHASE_PRICE, default_price_map())
SAMPLE_LABEL_SUPPLIER = 'CFNCT'
SAMPLE_LABEL_BATCH_INDEX = '1/12'
SAMPLE_LABEL_ASSOCIATED_CODE = 'CFNCT'

class BarcodeSettings:
    """Persisted configuration for the barcode module (shop name + price key)."""

    def __init__(self):
        self.company_name = ''
        self.price_key_map = default_price_map()
        self.currency_symbol = CURRENCY_SYMBOL
        self.sticker_size_index = 0
        self.media_gap_index = 0
        self.element_offsets = default_element_offsets()
        self.typography_settings = default_typography_settings()
        self.printer_name = ''
        self.barcode_padding = BARCODE_PADDING_OPTIONS[0]
        self.font_thickness = DEFAULT_FONT_THICKNESS

    @staticmethod
    def _settings_path() -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, 'barcode_settings.json')

    def load(self) -> 'BarcodeSettings':
        """Load settings from disk, falling back to the active company name."""
        try:
            path = self._settings_path()
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as handle:
                    data = json.load(handle)
                self.company_name = data.get('company_name', '') or ''
                self.currency_symbol = data.get('currency_symbol', CURRENCY_SYMBOL) or CURRENCY_SYMBOL
                saved_map = data.get('price_key_map')
                if isinstance(saved_map, dict) and saved_map:
                    self.price_key_map = {str(k): str(v) for k, v in saved_map.items()}
                else:
                    legacy = data.get('price_key')
                    if isinstance(legacy, str) and len(legacy) >= 10:
                        self.price_key_map = {str(i): legacy[i] for i in range(10)}
                self.sticker_size_index = int(data.get('sticker_size_index', 0) or 0)
                self.media_gap_index = int(data.get('media_gap_index', 0) or 0)
                self.printer_name = str(data.get('printer_name', '') or '')
                padding = str(data.get('barcode_padding', '') or '')
                if padding in BARCODE_PADDING_OPTIONS:
                    self.barcode_padding = padding
                font_thickness = normalize_font_thickness(data.get('font_thickness', ''), DEFAULT_FONT_THICKNESS)
                self.font_thickness = font_thickness
                offsets = data.get('element_offsets')
                if isinstance(offsets, dict):
                    self.element_offsets = normalize_element_offsets(offsets)
                typo = data.get('typography_settings')
                if isinstance(typo, dict):
                    merged_typo = default_typography_settings()
                    merged_typo.update(typo)
                    self.typography_settings = merged_typo
        except Exception:
            pass
        if not self.company_name and active_company_manager is not None:
            try:
                self.company_name = active_company_manager.get_active_company_name() or ''
            except Exception:
                self.company_name = ''
        return self

    def save(self, extra: dict=None) -> bool:
        """Persist current settings to disk. Returns True on success."""
        try:
            self.element_offsets = normalize_element_offsets(self.element_offsets)
            payload = {'company_name': self.company_name, 'price_key_map': self.price_key_map, 'currency_symbol': self.currency_symbol, 'sticker_size_index': self.sticker_size_index, 'media_gap_index': self.media_gap_index, 'element_offsets': self.element_offsets, 'typography_settings': self.typography_settings, 'printer_name': self.printer_name, 'barcode_padding': self.barcode_padding, 'font_thickness': self.font_thickness}
            if extra:
                payload.update(extra)
            with open(self._settings_path(), 'w', encoding='utf-8') as handle:
                json.dump(payload, handle, indent=2)
            return True
        except Exception:
            return False

def default_element_offsets() -> dict:
    """Default alignment offsets and barcode size deltas."""
    return {'company_x': 0, 'company_y': 0, 'product_x': 0, 'product_y': 0, 'barcode_graphic_x': 0, 'barcode_graphic_y': 0, 'barcode_graphic_w': 0, 'barcode_graphic_h': 0, 'barcode_number_x': 0, 'barcode_number_y': 0, 'price_x': 0, 'price_y': 0, 'cipher_x': 0, 'cipher_y': 0, 'batch_index_x': 0, 'batch_index_y': 0, 'supplier_code_x': 0, 'supplier_code_y': 0}
ELEMENT_ID_ALIASES = {'barcode_text': 'barcode_num', 'barcode_number': 'barcode_num', 'mrp': 'price', 'supplier': 'supplier_code'}
ELEMENT_OFFSET_PREFIXES = {'company': 'company', 'product': 'product', 'barcode': 'barcode_graphic', 'barcode_num': 'barcode_number', 'price': 'price', 'cipher': 'cipher', 'batch_index': 'batch_index', 'supplier_code': 'supplier_code'}
ELEMENT_OFFSET_KEY_MAP = {'company': ('company_x', 'company_y'), 'product': ('product_x', 'product_y'), 'barcode': ('barcode_graphic_x', 'barcode_graphic_y'), 'barcode_num': ('barcode_number_x', 'barcode_number_y'), 'supplier_code': ('supplier_code_x', 'supplier_code_y'), 'price': ('price_x', 'price_y'), 'cipher': ('cipher_x', 'cipher_y'), 'batch_index': ('batch_index_x', 'batch_index_y')}
CANONICAL_LAYOUT_ELEMENTS = ('company', 'product', 'barcode', 'barcode_num', 'supplier_code', 'price')
ELEMENT_TYPOGRAPHY_PREFIXES = {'barcode_num': 'barcode_text', 'price': 'mrp', 'supplier_code': 'supplier'}
BARCODE_OFFSET_ALIASES = {'barcode_graphic_x': 'barcode_x', 'barcode_graphic_y': 'barcode_y', 'barcode_graphic_w': 'barcode_w', 'barcode_graphic_h': 'barcode_h', 'barcode_number_x': 'barcode_text_x', 'barcode_number_y': 'barcode_text_y', 'price_x': 'mrp_x', 'price_y': 'mrp_y', 'supplier_code_x': 'supplier_x', 'supplier_code_y': 'supplier_y'}
LEGACY_ELEMENT_OFFSET_KEYS = set(BARCODE_OFFSET_ALIASES.values())

def normalize_element_offsets(offsets: dict=None) -> dict:
    """Return canonical element offsets, migrating legacy keys safely."""
    merged = default_element_offsets()
    if not isinstance(offsets, dict):
        return merged
    for key, value in offsets.items():
        if key not in LEGACY_ELEMENT_OFFSET_KEYS:
            merged[key] = value
    for canonical_key, legacy_key in BARCODE_OFFSET_ALIASES.items():
        if canonical_key not in offsets and legacy_key in offsets:
            merged[canonical_key] = offsets.get(legacy_key)
    return merged

def canonical_element_id(element: str):
    """Return the canonical selectable label element id, or None if unknown."""
    key = str(element or '').strip()
    if not key:
        return None
    return ELEMENT_ID_ALIASES.get(key, key)

def offset_key_prefix(element: str) -> str:
    """Map UI element ids to independent persisted offset prefixes."""
    return ELEMENT_OFFSET_PREFIXES.get(canonical_element_id(element))

def element_offset_keys(element: str):
    """Return the dedicated X/Y offset keys for a selectable element."""
    key = canonical_element_id(element)
    if not key:
        return None
    return ELEMENT_OFFSET_KEY_MAP.get(key)

def typography_key_prefix(element: str) -> str:
    """Map canonical element ids to typography keys retained for compatibility."""
    key = canonical_element_id(element)
    if not key:
        return ''
    return ELEMENT_TYPOGRAPHY_PREFIXES.get(key, key)

def element_supports_typography(element: str) -> bool:
    """Return True only when the canonical selectable element has text settings."""
    key = canonical_element_id(element)
    return bool(key and EDITABLE_LABEL_ELEMENTS.get(key, ('', False))[1])

def default_typography_settings() -> dict:
    """Default font size, legacy bold flags, and per-element thickness."""
    return {'company_size': 7, 'company_bold': True, 'company_thickness': 'Extra Bold', 'product_size': 6, 'product_bold': False, 'product_thickness': 'Normal', 'barcode_text_size': 5, 'barcode_text_bold': False, 'barcode_text_thickness': 'Normal', 'mrp_size': 7, 'mrp_bold': True, 'mrp_thickness': 'Extra Bold', 'cipher_size': 5, 'cipher_bold': False, 'cipher_thickness': 'Normal', 'batch_index_size': 6, 'batch_index_bold': False, 'batch_index_thickness': 'Normal', 'supplier_size': 5, 'supplier_bold': True, 'supplier_thickness': 'Extra Bold'}

def default_calibration_config() -> dict:
    """Default millimetre layout for a standard 38x25 mm 2-UP roll."""
    return {'roll_width': 76.2, 'roll_height': 25.4, 'label_width': 38.0, 'label_height': 25.0, 'columns': 2, 'center_gap': 0.2, 'element_offsets': default_element_offsets()}

def sticker_config_path() -> str:
    """Path to sticker_config.json in the application root directory."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'sticker_config.json')

def load_calibration_config() -> dict:
    """Load sticker calibration from local JSON, or return defaults."""
    config = default_calibration_config()
    try:
        path = sticker_config_path()
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as handle:
                saved = json.load(handle)
            if isinstance(saved, dict):
                for key in config:
                    if key in saved:
                        config[key] = saved[key]
                offsets = saved.get('element_offsets')
                if isinstance(offsets, dict):
                    config['element_offsets'] = normalize_element_offsets(offsets)
    except Exception:
        pass
    return config
OFFSET_MM_PER_UNIT = 0.5
PREVIEW_PX_PER_MM = 4.0
PREVIEW_PX_PER_INCH = 100.0
INCH_TO_MM = 25.4
STICKER_SIZE_OPTIONS = ('1.50" x 1.00" (38x25mm Dual 2-Up)', '2.00" x 1.00" (50x25mm Single)', '2.00" x 0.50" (50x12mm Jewelry)', '3.00" x 1.00" (75x25mm Single)', '4.00" x 6.00" (100x150mm Shipping)')

def parse_sticker_size_text(size_text: str) -> dict:
    """
    Parse a sticker size combo label into inch/mm calibration fields.

    Returns width_in, height_in, label_width, label_height, roll_width,
    roll_height, and columns (2 for dual 2-Up rolls).
    """
    text = str(size_text or '').strip()
    lowered = text.lower()
    match = re.search('(\\d+(?:\\.\\d+)?)\\s*["\\\']?\\s*x\\s*(\\d+(?:\\.\\d+)?)', text, re.IGNORECASE)
    width_in = float(match.group(1)) if match else 2.0
    height_in = float(match.group(2)) if match else 1.0
    columns = 1
    if 'dual' in lowered or '2-up' in lowered or '2 up' in lowered:
        columns = 2
    label_width_mm = round(width_in * INCH_TO_MM, 2)
    label_height_mm = round(height_in * INCH_TO_MM, 2)
    roll_width_mm = label_width_mm * columns if columns > 1 else label_width_mm
    roll_height_mm = label_height_mm
    return {'width_in': width_in, 'height_in': height_in, 'label_width': label_width_mm, 'label_height': label_height_mm, 'roll_width': roll_width_mm, 'roll_height': roll_height_mm, 'columns': columns}

def preview_gap_mm_from_combo(gap_text: str) -> float:
    """Return vertical gap height in mm for live preview (0 = continuous)."""
    lowered = str(gap_text or '').lower()
    if 'continuous' in lowered or 'no gap' in lowered:
        return 0.0
    if 'with gap' in lowered or '3mm' in lowered:
        return 2.79
    return 0.0

def preview_roll_layout(size_text: str, gap_text: str='') -> dict:
    """
    Compute roll/label pixel dimensions for the live preview canvas.

    Uses PREVIEW_PX_PER_INCH so UI pixels align with 72 pt/inch PDF math.
    """
    profile = parse_sticker_size_text(size_text)
    gap_mm = preview_gap_mm_from_combo(gap_text)
    gap_in = gap_mm / INCH_TO_MM
    columns = int(profile.get('columns', 1) or 1)
    label_w_in = float(profile['width_in'])
    label_h_in = float(profile['height_in'])
    roll_w_in = label_w_in * columns if columns > 1 else label_w_in
    roll_h_in = label_h_in + gap_in
    return {'columns': columns, 'label_width_in': label_w_in, 'label_height_in': label_h_in, 'roll_width_in': roll_w_in, 'roll_height_in': roll_h_in, 'gap_mm': gap_mm, 'has_gap': gap_mm > 0.0, 'label_width_px': label_w_in * PREVIEW_PX_PER_INCH, 'label_height_px': label_h_in * PREVIEW_PX_PER_INCH, 'roll_width_px': roll_w_in * PREVIEW_PX_PER_INCH, 'roll_height_px': roll_h_in * PREVIEW_PX_PER_INCH, 'gap_height_px': gap_in * PREVIEW_PX_PER_INCH}

def calibration_profile_from_size_text(size_text: str, base_cfg: dict=None) -> dict:
    """Build a full calibration dict for PDF/preview from the size combo string."""
    cfg = dict(base_cfg or load_calibration_config())
    profile = parse_sticker_size_text(size_text)
    cfg['columns'] = profile['columns']
    cfg['roll_width'] = profile['roll_width']
    cfg['roll_height'] = profile['roll_height']
    cfg['label_width'] = profile['label_width']
    cfg['label_height'] = profile['label_height']
    cfg['width_in'] = profile['width_in']
    cfg['height_in'] = profile['height_in']
    return cfg

def spin_to_reportlab_offset(spin_value: int):
    """Convert a spinbox integer to a ReportLab length offset."""
    from reportlab.lib.units import mm
    return int(spin_value) * OFFSET_MM_PER_UNIT * mm

def spin_to_preview_pixels(spin_value: int) -> float:
    """Convert a spinbox integer to preview-canvas pixels."""
    return int(spin_value) * OFFSET_MM_PER_UNIT * PREVIEW_PX_PER_MM

def pdf_scale_from_preview_label(width_in: float, height_in: float) -> tuple:
    """
    Return (scale_x, scale_y) mapping live-preview pixels to PDF points.

    Preview uses PREVIEW_PX_PER_INCH; PDF uses 72 points per inch on each label cell.
    """
    label_w_px = max(width_in * PREVIEW_PX_PER_INCH, 1.0)
    label_h_px = max(height_in * PREVIEW_PX_PER_INCH, 1.0)
    label_w_pt = width_in * 72.0
    label_h_pt = height_in * 72.0
    return (label_w_pt / label_w_px, label_h_pt / label_h_px)

def spin_offset_to_pdf_length(spin_value: int, scale_pt_per_px: float):
    """Convert stored spin offset to ReportLab length using preview-to-PDF scale."""
    from reportlab.lib.units import mm
    preview_px = spin_to_preview_pixels(spin_value)
    points = preview_px * scale_pt_per_px
    return points * (25.4 / 72.0) * mm

def preview_spin_x_delta(offsets: dict, element: str) -> float:
    """Horizontal nudge in preview pixels (positive spin moves right)."""
    offset_keys = element_offset_keys(element)
    if not offset_keys:
        return 0.0
    x_key, _y_key = offset_keys
    return spin_to_preview_pixels(int(offsets.get(x_key, 0) or 0))

def preview_spin_y_delta(offsets: dict, element: str) -> float:
    """Vertical nudge in preview pixels (positive spin moves up, matching the canvas)."""
    offset_keys = element_offset_keys(element)
    if not offset_keys:
        return 0.0
    _x_key, y_key = offset_keys
    return -spin_to_preview_pixels(int(offsets.get(y_key, 0) or 0))

class CoordinateTranslator:
    """
    Translate label element coordinates between preview and physical PDF space.

    Saved element coordinates are generic top-left UI coordinates: PySide6 preview
    uses them directly with Y=0 at the top of the sticker. ReportLab draws with
    Y=0 at the physical bottom of the sticker, so PDF Y must be inverted in one
    place before drawString, drawOn, or rectangle calls.

    Bottom-anchored controls should still calculate an explicit top-origin box Y
    first, for example ``label_height - bottom_offset - element_height``. That
    keeps preview controls intuitive while avoiding two meanings for saved Y.
    """

    def __init__(self, preview_origin_x: float=0.0, preview_origin_y: float=0.0, pdf_origin_x: float=0.0, label_height_pt: float=0.0, scale_x: float=1.0, scale_y: float=1.0):
        """Store preview origin, PDF origin, and preview-pixel to point scale."""
        self.preview_origin_x = float(preview_origin_x)
        self.preview_origin_y = float(preview_origin_y)
        self.pdf_origin_x = float(pdf_origin_x)
        self.label_height_pt = float(label_height_pt)
        self.scale_x = float(scale_x)
        self.scale_y = float(scale_y)

    def preview_x(self, x_coordinate: float) -> float:
        """Return a PySide6 X coordinate from a top-left label-relative X."""
        return self.preview_origin_x + float(x_coordinate)

    def preview_y(self, y_coordinate: float) -> float:
        """Return a PySide6 Y coordinate from a top-left label-relative Y."""
        return self.preview_origin_y + float(y_coordinate)

    def pdf_x(self, x_coordinate: float) -> float:
        """Return a ReportLab X coordinate from a left-origin label-relative X."""
        return self.pdf_origin_x + float(x_coordinate) * self.scale_x

    def pdf_y_from_top(self, y_coordinate: float, element_height_pt: float=0.0) -> float:
        """
        Return ReportLab Y for a top-origin UI coordinate.

        ``element_height_pt`` is already in PDF points. For text this is the
        baseline drop (usually font size or font ascent). For bottom-left
        primitives like barcode ``drawOn`` and ``rect``, pass the top coordinate
        plus the element height and leave ``element_height_pt`` as zero, or use
        ``pdf_rect_y_from_top``.
        """
        return self.label_height_pt - float(y_coordinate) * self.scale_y - float(element_height_pt)

    def pdf_text_baseline_from_top(self, y_coordinate: float, font_pt: float, font_name: str='', use_font_ascent: bool=False) -> float:
        """Return a ReportLab text baseline that mirrors preview text-box top Y."""
        baseline_drop = pdf_font_ascent(font_name, font_pt) if use_font_ascent else float(font_pt)
        return self.pdf_y_from_top(y_coordinate, baseline_drop)

    def pdf_text_baseline_from_bottom(self, y_coordinate: float, font_pt: float, font_name: str='') -> float:
        """Return a ReportLab baseline for a bottom-anchored preview text box."""
        box_bottom_y = self.pdf_y_from_top(y_coordinate, 0.0)
        return box_bottom_y - pdf_font_descent(font_name, font_pt)

    def pdf_rect_y_from_top(self, top_y: float, height_px: float) -> float:
        """Return ReportLab bottom Y for a top-origin preview rectangle."""
        return self.pdf_y_from_top(float(top_y) + float(height_px), 0.0)

def pdf_y_from_ui_top(label_height_pt: float, ui_from_top_px: float, scale_y: float, font_pt: float=0.0) -> float:
    """
    Map a Qt top-origin distance to a ReportLab baseline Y inside one label cell.

    ReportLab uses a bottom-left origin; the live preview uses top-left.
    """
    return CoordinateTranslator(label_height_pt=label_height_pt, scale_y=scale_y).pdf_y_from_top(ui_from_top_px, font_pt)

def pdf_font_ascent(font_name: str, font_pt: float) -> float:
    """Return the ReportLab baseline ascent for a font, falling back safely."""
    try:
        from reportlab.pdfbase import pdfmetrics
        return float(pdfmetrics.getAscent(font_name, font_pt))
    except Exception:
        return float(font_pt)

def pdf_font_descent(font_name: str, font_pt: float) -> float:
    """Return the ReportLab baseline descent for bottom-anchored text."""
    try:
        from reportlab.pdfbase import pdfmetrics
        return float(pdfmetrics.getDescent(font_name, font_pt))
    except Exception:
        return 0.0

def pdf_y_from_ui_text_top(label_height_pt: float, ui_from_top_px: float, scale_y: float, font_name: str, font_pt: float) -> float:
    """
    Convert a Qt text top coordinate to a ReportLab baseline coordinate.

    Qt drawText is positioned by baseline after adding fontMetrics().ascent();
    ReportLab also draws from a baseline, so use the PDF font ascent rather
    than the full point size when mirroring preview text.
    """
    return CoordinateTranslator(label_height_pt=label_height_pt, scale_y=scale_y).pdf_text_baseline_from_top(ui_from_top_px, font_pt, font_name, use_font_ascent=True)

def pdf_x_from_ui_left(x_start_pt: float, ui_from_left_px: float, scale_x: float) -> float:
    """Map a Qt left-origin distance to ReportLab X inside one label cell."""
    return CoordinateTranslator(pdf_origin_x=x_start_pt, scale_x=scale_x).pdf_x(ui_from_left_px)

def reportlab_snap_pt(value) -> int:
    """Snap ReportLab drawing positions to full points for thermal printers."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0

def sanitize_code39_value(value) -> str:
    """Return uppercase Code 39 payload text, dropping unsupported characters safely."""
    safe_chars = []
    for char in str(value or '').upper():
        if char in CODE39_SUPPORTED_CHARS:
            safe_chars.append(char)
    return ''.join(safe_chars)

def encode_code39_modules(value) -> str:
    """
    Encode value as a standard Code 39 binary module string.

    The returned string contains ``1`` for black modules and ``0`` for white
    modules. It includes start/stop ``*`` sentinels, narrow inter-character
    spaces, and quiet zones so both preview and physical printing share one
    deterministic barcode pattern.
    """
    payload = sanitize_code39_value(value)
    if not payload:
        return ''
    encoded_chars = f'*{payload}*'
    modules = ['0' * CODE39_QUIET_ZONE_MODULES]
    for char_index, char in enumerate(encoded_chars):
        pattern = CODE39_PATTERNS.get(char)
        if not pattern:
            continue
        for element_index, width_code in enumerate(pattern):
            module_count = CODE39_WIDE_MODULES if width_code == 'w' else CODE39_NARROW_MODULES
            color_module = '1' if element_index % 2 == 0 else '0'
            modules.append(color_module * module_count)
        if char_index < len(encoded_chars) - 1:
            modules.append('0' * CODE39_NARROW_MODULES)
    modules.append('0' * CODE39_QUIET_ZONE_MODULES)
    return ''.join(modules)

def barcode_module_metrics(pattern: str, available_width: float, min_module_width: float=0.0) -> tuple:
    """
    Return (module_width, final_width) for deterministic module rendering.

    The configured graphic width controls one uniform module width. A minimum
    module width is only used when it still fits the configured box, preventing
    preview or PDF overflow while keeping bar and gap ratios exact.
    """
    module_count = len(str(pattern or ''))
    try:
        width = max(0.0, float(available_width))
    except (TypeError, ValueError):
        width = 0.0
    if module_count <= 0 or width <= 0.0:
        return (0.0, 0.0)
    module_width = width / float(module_count)
    try:
        requested_min = max(0.0, float(min_module_width))
    except (TypeError, ValueError):
        requested_min = 0.0
    if requested_min > module_width and requested_min * module_count <= width:
        module_width = requested_min
    final_width = module_width * module_count
    return (module_width, min(final_width, width))

def barcode_module_bar_rects(pattern: str, left: float, top: float, width: float, height: float) -> list:
    """
    Return clamped black module rectangles for tight barcode drawing.

    The supplied ``left``/``top``/``width``/``height`` rectangle is the complete
    barcode graphic box. Bars start at ``left`` and are clipped at ``left + width``
    so neither preview nor PDF rendering can bleed outside sticker margins.
    """
    module_width, _final_width = barcode_module_metrics(pattern, width)
    try:
        box_left = float(left)
        box_top = float(top)
        box_width = max(0.0, float(width))
        box_height = max(0.0, float(height))
    except (TypeError, ValueError):
        return []
    if module_width <= 0.0 or box_width <= 0.0 or box_height <= 0.0:
        return []
    right_edge = box_left + box_width
    rectangles = []
    for index, module in enumerate(str(pattern or '')):
        bar_left = box_left + index * module_width
        if bar_left >= right_edge:
            break
        if module != '1':
            continue
        bar_right = min(bar_left + module_width, right_edge)
        bar_width = max(0.0, bar_right - bar_left)
        if bar_width > 0.0:
            rectangles.append((bar_left, box_top, bar_width, box_height))
    return rectangles

def draw_reportlab_barcode_modules(pdf, pattern: str, left_pt: float, bottom_pt: float, height_pt: float, available_width_pt: float) -> float:
    """
    Draw encoded barcode modules with ReportLab rectangles and return final width.

    Only black modules are painted. White modules advance by the exact same
    module width, which keeps scanner-visible ratios independent of label size.
    """
    rectangles = barcode_module_bar_rects(pattern, left_pt, bottom_pt, available_width_pt, height_pt)
    if not rectangles:
        return 0.0
    pdf.setFillColorRGB(0, 0, 0)
    for rect_left, rect_bottom, rect_width, rect_height in rectangles:
        pdf.rect(rect_left, rect_bottom, rect_width, rect_height, stroke=0, fill=1)
    _module_width, final_width = barcode_module_metrics(pattern, available_width_pt)
    return final_width

def cipher_preview_endpoint(cell_w_px: float, cell_h_px: float, offsets: dict) -> tuple:
    """Return the preview right-aligned cipher endpoint and text top."""
    right_px = cell_w_px - 8.0 + preview_spin_x_delta(offsets, 'cipher')
    top_px = cell_h_px - 14.0 + preview_spin_y_delta(offsets, 'cipher')
    return (right_px, top_px)

def supplier_preview_anchor(cell_w_px: float, cell_h_px: float, offsets: dict) -> tuple:
    """Return the independent preview anchor for the rotated supplier shortcode."""
    x_px = cell_w_px * 0.92 + preview_spin_x_delta(offsets, 'supplier_code')
    y_px = cell_h_px * 0.49 + preview_spin_y_delta(offsets, 'supplier_code')
    return (x_px, y_px)

def normalized_supplier_code(*sources) -> str:
    """Return the first clean supplier shortcode from row/product payloads."""
    aliases = ('supplier_code', 'supplier_short_code', 'supplier_shortcode', 'party_code', 'vendor_code', 'code')
    for source in sources:
        try:
            if isinstance(source, dict):
                values = [source.get(alias) for alias in aliases]
            else:
                values = [source]
            for value in values:
                text = str(value or '').strip().upper()
                if text:
                    return text[:10]
        except Exception:
            continue
    return ''

def barcode_preview_layout(cell_w_px: float, cell_h_px: float, offsets: dict):
    """
    Return barcode graphic box (top, left, width, height) in preview pixels.

    Mirrors LabelPreviewCanvas._paint_label_cell so PDF placement stays aligned.
    """
    normalized_offsets = normalize_element_offsets(offsets)
    bar_top = cell_h_px * 0.38 + preview_spin_y_delta(normalized_offsets, 'barcode')
    bar_left = cell_w_px * 0.08 + preview_spin_x_delta(normalized_offsets, 'barcode')
    bar_w = max(4.0, cell_w_px * 0.84 + spin_to_preview_pixels(normalized_offsets.get('barcode_graphic_w', 0)))
    bar_h = max(1.0, cell_h_px * 0.22 + spin_to_preview_pixels(normalized_offsets.get('barcode_graphic_h', 0)))
    return (bar_top, bar_left, bar_w, bar_h)

def barcode_number_preview_top(cell_h_px: float, offsets: dict) -> float:
    """Return independent top-origin Y for human-readable barcode number text."""
    normalized_offsets = normalize_element_offsets(offsets)
    return cell_h_px * 0.62 + preview_spin_y_delta(normalized_offsets, 'barcode_num')

def save_calibration_config(config: dict) -> bool:
    """Persist sticker calibration to sticker_config.json."""
    try:
        with open(sticker_config_path(), 'w', encoding='utf-8') as handle:
            json.dump(config, handle, indent=2)
        return True
    except Exception:
        return False

def column_x_offset(col, columns, label_width, center_gap, page_width):
    """Horizontal offset for label column col (ReportLab point units)."""
    if columns <= 1:
        return (page_width - label_width) / 2.0
    total = columns * label_width + (columns - 1) * center_gap
    start_x = (page_width - total) / 2.0
    return start_x + col * (label_width + center_gap)

class LabelRenderEngine:
    """Render thermal labels onto a multi-page PDF using ReportLab primitives."""
    LABEL_WIDTH_PT = 2 * 72
    LABEL_HEIGHT_PT = 1 * 72

    def __init__(self, settings: BarcodeSettings):
        self.settings = settings

    def render(self, rows, out_path: str, calibration: dict=None, element_offsets: dict=None, typography_settings: dict=None, preview_canvas_size=None):
        """Render every grid row (honouring Print Qty) into a PDF at out_path.

        Page and label dimensions come from sticker_config.json so the PDF canvas
        matches the QPrinter hardware boundaries exactly. Returns
        (success: bool, message: str).
        """
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import inch
        except Exception as exc:
            return (False, f'ReportLab is not available: {exc}')
        if not rows:
            return (False, 'There are no labels to render.')
        cfg = calibration or load_calibration_config()
        offsets = normalize_element_offsets(element_offsets or cfg.get('element_offsets') or default_element_offsets())
        typo = typography_settings or default_typography_settings()
        width_in = float(cfg.get('width_in', 2.0) or 2.0)
        height_in = float(cfg.get('height_in', 1.0) or 1.0)
        columns_per_page = max(1, int(cfg.get('columns', 1) or 1))
        label_w_px = max(width_in * PREVIEW_PX_PER_INCH, 1.0)
        label_h_px = max(height_in * PREVIEW_PX_PER_INCH, 1.0)
        scale_x = width_in * 72.0 / label_w_px
        scale_y = height_in * 72.0 / label_h_px
        label_width = width_in * inch
        label_height = height_in * inch
        col_step = width_in * inch
        if columns_per_page > 1:
            page_width = width_in * columns_per_page * inch
        else:
            page_width = width_in * inch
        page_height = height_in * inch
        company = (self.settings.company_name or '').strip()
        key_map = self.settings.price_key_map or default_price_map()
        body_font, price_font, extra_bold_font = register_reportlab_native_fonts()
        currency = '₹'
        try:
            doc_canvas = canvas.Canvas(out_path, pagesize=(page_width, page_height))
        except Exception as exc:
            return (False, f'Unable to create the PDF stream: {exc}')
        queued_labels_payload = []
        for row in rows:
            try:
                qty_raw = row.get('print_qty')
                loop_count = int(float(str(qty_raw).strip()))
            except (TypeError, ValueError):
                continue
            if loop_count < 1:
                continue
            item_index = row.get('sl_no') or row.get('item_index') or row.get('item_index_display') or ''
            for _copy_idx in range(loop_count):
                label_data = dict(row)
                sample_batch_index = ''
                if label_data.get('__sample_label'):
                    sample_batch_index = str(label_data.get('batch_index', '') or '').strip()
                if sample_batch_index:
                    label_data['batch_index'] = sample_batch_index
                elif item_index not in (None, ''):
                    label_data['batch_index'] = f'{item_index}/{loop_count}'
                else:
                    label_data['batch_index'] = f'/{loop_count}'
                if not label_data.get('batch_tag') and item_index not in (None, ''):
                    label_data['batch_tag'] = f'{item_index}-{loop_count}'
                queued_labels_payload.append(label_data)
        if not queued_labels_payload:
            return (False, 'There are no printable labels with Print Qty above zero.')
        try:
            label_count = 0
            current_col = 0
            for label_data in queued_labels_payload:
                x_coordinate = current_col * col_step
                batch_tag = str(label_data.get('batch_tag', '') or '')
                self._draw_single_label(doc_canvas, label_width, label_height, x_coordinate, company, key_map, label_data, batch_tag, body_font, price_font, extra_bold_font, currency, element_offsets=offsets, typography_settings=typo, offset_scale_x=scale_x, offset_scale_y=scale_y, label_w_px=label_w_px, label_h_px=label_h_px)
                current_col += 1
                label_count += 1
                if current_col >= columns_per_page:
                    doc_canvas.showPage()
                    current_col = 0
                if label_count % 10 == 0:
                    QCoreApplication.processEvents()
            if current_col == 1:
                doc_canvas.showPage()
            doc_canvas.save()
        except Exception as exc:
            return (False, f'Label rendering failed: {exc}')
        return (True, f'Rendered {label_count} label(s).')

    def _draw_single_label(self, pdf, label_width, label_height, x_coordinate, company, key_map, row, batch_tag, body_font='Helvetica', price_font='Helvetica-Bold', extra_bold_font='Helvetica-Bold', currency='₹', element_offsets=None, typography_settings=None, offset_scale_x=1.0, offset_scale_y=1.0, label_w_px=200.0, label_h_px=100.0):
        """
        Draw one label inside a calibrated cell.

        X/Y positions mirror LabelPreviewCanvas using saved spin offsets and
        Y-axis inversion for ReportLab's bottom-left origin.
        """
        offsets = normalize_element_offsets(element_offsets or default_element_offsets())
        typo = typography_settings or default_typography_settings()
        cell_w_px = max(float(label_w_px), 1.0)
        cell_h_px = max(float(label_h_px), 1.0)
        scale_x = float(offset_scale_x)
        scale_y = float(offset_scale_y)
        translator = CoordinateTranslator(pdf_origin_x=x_coordinate, label_height_pt=label_height, scale_x=scale_x, scale_y=scale_y)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setStrokeColorRGB(0, 0, 0)

        def element_thickness(element_key, bold_default=False):
            """Resolve per-element thickness from typography JSON."""
            legacy_default = 'Extra Bold' if bool(bold_default) else 'Normal'
            return normalize_font_thickness(typo.get(f'{element_key}_thickness'), legacy_default)

        def pick_font(element_key, bold_default=False):
            thickness = element_thickness(element_key, bold_default)
            if thickness == 'Extra Bold':
                return extra_bold_font
            if thickness == 'Bold':
                return price_font
            return body_font

        def font_size(key, default_pt):
            return int(typo.get(key, default_pt))

        def draw_label_text(text, x_pos, y_pos, font_name, font_pt, element_key, align='left'):
            """Draw text using native Normal/Bold font selection only."""
            safe_text = str(text or '')
            if not safe_text:
                return
            try:
                draw_x = reportlab_snap_pt(x_pos)
                draw_y = reportlab_snap_pt(y_pos)
                pdf.setFillColorRGB(0, 0, 0)
                if align == 'center':
                    pdf.setFont(font_name, font_pt)
                    pdf.drawCentredString(draw_x, draw_y, safe_text)
                    return
                elif align == 'right':
                    pdf.setFont(font_name, font_pt)
                    pdf.drawRightString(draw_x, draw_y, safe_text)
                    return
                pdf.setFont(font_name, font_pt)
                pdf.drawString(draw_x, draw_y, safe_text)
            except Exception:
                try:
                    pdf.setFillColorRGB(0, 0, 0)
                    pdf.setFont(font_name, font_pt)
                    pdf.drawString(reportlab_snap_pt(x_pos), reportlab_snap_pt(y_pos), safe_text)
                except Exception:
                    pass
        product_name = str(row.get('product_name', '') or '')
        barcode_value = str(row.get('barcode', '') or '').strip()
        supplier_code = normalized_supplier_code(row)[:5]
        mrp = row.get('mrp', 0)
        purchase_price = row.get('purchase_price', 0)
        cipher = encode_price_cipher(purchase_price, key_map)
        if company:
            company_pt = font_size('company_size', 7)
            company_top_px = 4.0 + preview_spin_y_delta(offsets, 'company')
            company_bold = typo.get('company_bold', True)
            company_font = pick_font('company', company_bold)
            draw_label_text(company[:32], translator.pdf_x(cell_w_px / 2.0 + preview_spin_x_delta(offsets, 'company')), translator.pdf_text_baseline_from_top(company_top_px, company_pt), company_font, company_pt, 'company', align='center')
        if product_name:
            product_pt = font_size('product_size', 6)
            product_top_px = 14.0 + preview_spin_y_delta(offsets, 'product')
            product_bold = typo.get('product_bold', False)
            product_font = pick_font('product', product_bold)
            draw_label_text(product_name[:36], translator.pdf_x(cell_w_px / 2.0 + preview_spin_x_delta(offsets, 'product')), translator.pdf_text_baseline_from_top(product_top_px, product_pt), product_font, product_pt, 'product', align='center')
        bar_top_px, bar_left_px, bar_w_px, bar_h_px = barcode_preview_layout(cell_w_px, cell_h_px, offsets)
        if barcode_value:
            try:
                bar_height_pt = bar_h_px * scale_y
                available_pt = bar_w_px * scale_x
                encoded_pattern = encode_code39_modules(barcode_value)
                module_width, _final_width = barcode_module_metrics(encoded_pattern, available_pt)
                bx = translator.pdf_x(bar_left_px)
                by = translator.pdf_rect_y_from_top(bar_top_px, bar_h_px)
                if module_width > 0.0:
                    draw_reportlab_barcode_modules(pdf, encoded_pattern, bx, by, bar_height_pt, available_pt)
            except Exception:
                pass
            barcode_text_pt = font_size('barcode_text_size', 5)
            barcode_text_top_px = barcode_number_preview_top(cell_h_px, offsets)
            barcode_text_bold = typo.get('barcode_text_bold', False)
            barcode_text_font = pick_font('barcode_text', barcode_text_bold)
            draw_label_text(barcode_value[:24], translator.pdf_x(cell_w_px / 2.0 + preview_spin_x_delta(offsets, 'barcode_num')), translator.pdf_text_baseline_from_top(barcode_text_top_px, barcode_text_pt), barcode_text_font, barcode_text_pt, 'barcode_text', align='center')
        try:
            sale_text = f'{currency} {float(mrp):.2f}'
        except (TypeError, ValueError):
            sale_text = f'{currency} 0.00'
        mrp_pt = font_size('mrp_size', 7)
        mrp_bold = typo.get('mrp_bold', True)
        mrp_font_name = pick_font('mrp', mrp_bold)
        mrp_bottom_px = cell_h_px - 22.0 + preview_spin_y_delta(offsets, 'price')
        draw_label_text(sale_text, translator.pdf_x(5.0 + preview_spin_x_delta(offsets, 'price')), translator.pdf_text_baseline_from_bottom(mrp_bottom_px, mrp_pt, mrp_font_name), mrp_font_name, mrp_pt, 'mrp')
        cipher_pt = font_size('cipher_size', 5)
        cipher_right_px, cipher_top_px = cipher_preview_endpoint(cell_w_px, cell_h_px, offsets)
        cipher_bold = typo.get('cipher_bold', False)
        cipher_font_name = pick_font('cipher', cipher_bold)
        draw_label_text(cipher, translator.pdf_x(cipher_right_px), translator.pdf_text_baseline_from_top(cipher_top_px, cipher_pt, cipher_font_name, use_font_ascent=True), cipher_font_name, cipher_pt, 'cipher', align='right')
        batch_index = str(row.get('batch_index', '') or '').strip()
        if batch_index:
            batch_pt = font_size('batch_index_size', 6)
            batch_bold = typo.get('batch_index_bold', False)
            batch_font_name = pick_font('batch_index', batch_bold)
            batch_bottom_px = cell_h_px - 6.0 + preview_spin_y_delta(offsets, 'batch_index')
            draw_label_text(batch_index, translator.pdf_x(5.0 + preview_spin_x_delta(offsets, 'batch_index')), translator.pdf_text_baseline_from_bottom(batch_bottom_px, batch_pt, batch_font_name), batch_font_name, batch_pt, 'batch_index')
        elif batch_tag:
            fallback_pt = 5
            fallback_font_name = pick_font('batch_index', False)
            draw_label_text(batch_tag, translator.pdf_x(5.0), translator.pdf_text_baseline_from_bottom(cell_h_px - 6.0, fallback_pt, fallback_font_name), fallback_font_name, fallback_pt, 'batch_index')
        if supplier_code:
            try:
                supplier_pt = font_size('supplier_size', 5)
                supplier_x_px, supplier_y_px = supplier_preview_anchor(cell_w_px, cell_h_px, offsets)
                supplier_bold = typo.get('supplier_bold', True)
                supplier_font_name = pick_font('supplier', supplier_bold)
                supplier_ascent_pt = pdf_font_ascent(supplier_font_name, supplier_pt)
                pdf.saveState()
                pdf.setFillColorRGB(0, 0, 0)
                pdf.setStrokeColorRGB(0, 0, 0)
                pdf.translate(reportlab_snap_pt(translator.pdf_x(supplier_x_px)), reportlab_snap_pt(translator.pdf_y_from_top(supplier_y_px)))
                pdf.rotate(90)
                draw_label_text(supplier_code, 0, supplier_ascent_pt, supplier_font_name, supplier_pt, 'supplier', align='center')
                pdf.restoreState()
            except Exception:
                try:
                    pdf.restoreState()
                except Exception:
                    pass

def list_system_printers():
    """Return available printer names (Qt first, win32print fallback)."""
    names = []
    try:
        from PySide6.QtPrintSupport import QPrinterInfo
        names = [p.printerName() for p in QPrinterInfo.availablePrinters()]
    except Exception:
        names = []
    if not names:
        try:
            import win32print
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            names = [p[2] for p in win32print.EnumPrinters(flags)]
        except Exception:
            names = []
    return names

def _apply_pdf_calibration_from_db_text(calibration: dict, default_size: str, default_gap: str) -> dict:
    """
    Map persisted TEXT sticker size / gap labels to ReportLab calibration (mm).

    Avoids int() casts on descriptive combo strings from SQLite.
    """
    cfg = calibration_profile_from_size_text(default_size, calibration)
    gap_text = str(default_gap or '')
    gap_lower = gap_text.lower()
    if 'continuous' in gap_lower or 'no gap' in gap_lower:
        cfg['center_gap'] = 0.0
        cfg['vertical_gap_spacing'] = 0.0
    elif 'with gap' in gap_lower or '3mm' in gap_lower:
        cfg['vertical_gap_spacing'] = 2.79
    else:
        cfg['vertical_gap_spacing'] = 0.0
    return cfg

def compile_pdf_document_stream(db, rows, out_path: str, preview_canvas_size=None, element_offsets=None, typography_settings=None):
    """
    Render labels to a PDF using barcode_settings row id=1 (no UI widgets).

    Loads company name, cipher matrix, sticker size, media gap, and layout
    offsets from SQLite at runtime, then drives LabelRenderEngine (which builds
    queued_labels_payload with batch_index and locks thermal pagesize).

    Callers may pass element_offsets / typography_settings to force a strict
    WYSIWYG match with the live preview (overriding the persisted DB values).
    Returns (success: bool, message: str).
    """
    from bizora_core.barcode_db import fetch_barcode_preferences, preferences_to_barcode_settings, build_calibration_profile_from_prefs
    try:
        prefs = fetch_barcode_preferences(db)
        settings = preferences_to_barcode_settings(prefs)
        calibration = build_calibration_profile_from_prefs(prefs, load_calibration_config())
        default_size = str(prefs.get('default_size', '') or '')
        default_gap = str(prefs.get('default_gap', '') or '')
        calibration = _apply_pdf_calibration_from_db_text(calibration, default_size, default_gap)
        offsets = element_offsets or prefs.get('element_offsets') or default_element_offsets()
        typo = typography_settings or prefs.get('typography_settings') or default_typography_settings()
        engine = LabelRenderEngine(settings)
        ok, message = engine.render(rows, out_path, calibration=calibration, element_offsets=offsets, typography_settings=typo, preview_canvas_size=preview_canvas_size)
        if not ok:
            try:
                QMessageBox.critical(None, 'Barcode PDF', message or 'PDF generation failed.')
            except Exception:
                pass
        return (ok, message)
    except Exception as exc:
        error_text = f'PDF compile error: {exc}'
        try:
            QMessageBox.critical(None, 'Barcode PDF', error_text)
        except Exception:
            pass
        return (False, error_text)

def _default_printer_name(prefs: dict) -> str:
    """Resolve target printer from DB prefs or OS default."""
    name = (prefs or {}).get('default_printer', '') or ''
    if name:
        return name.strip()
    try:
        from PySide6.QtPrintSupport import QPrinterInfo
        return QPrinterInfo.defaultPrinter().printerName() or ''
    except Exception:
        return ''

class LabelPreviewCanvas(QWidget):
    """Real-time sticker preview with antialiased QPainter rendering."""
    element_selected = Signal(str)
    HIGHLIGHT_COLOR = QColor('#0288D1')
    STANDARD_TEXT_COLOR = QColor('#0f172a')
    DUMMY_COMPANY = SAMPLE_LABEL_COMPANY
    DUMMY_PRODUCT = SAMPLE_LABEL_PRODUCT
    DUMMY_BARCODE = SAMPLE_LABEL_BARCODE
    DUMMY_MRP = SAMPLE_LABEL_MRP_TEXT
    DUMMY_CIPHER = SAMPLE_LABEL_CIPHER
    DUMMY_SUPPLIER = SAMPLE_LABEL_SUPPLIER

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.hitboxes = {}
        self.setMinimumSize(80, 40)
        from ui import theme

        colors = theme._theme_colors()
        self.setStyleSheet(
            f"background-color: {colors['panel_bg']}; border: 1px solid {colors['border']};"
        )
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        """Emit element_selected when the user clicks a drawn label element."""
        try:
            point = event.position().toPoint()
            for element_id, rect in self.hitboxes.items():
                if rect.contains(point):
                    self.element_selected.emit(element_id)
                    return
        except Exception:
            pass
        super().mousePressEvent(event)

    def paintEvent(self, event):
        """Paint thermal roll preview: 2-Up when dual, with optional media gap strip."""
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        size_text = ''
        gap_text = ''
        if hasattr(self.manager, 'size_combo'):
            size_text = self.manager.size_combo.currentText()
        if hasattr(self.manager, 'gap_combo'):
            gap_text = self.manager.gap_combo.currentText()
        layout = preview_roll_layout(size_text, gap_text)
        margin = 4.0
        roll_w_px = min(layout['roll_width_px'], max(1.0, self.width() - 2 * margin))
        roll_h_px = min(layout['roll_height_px'], max(1.0, self.height() - 2 * margin))
        scale = min(roll_w_px / max(layout['roll_width_px'], 1.0), roll_h_px / max(layout['roll_height_px'], 1.0), 1.0)
        roll_w_px = layout['roll_width_px'] * scale
        roll_h_px = layout['roll_height_px'] * scale
        label_w_px = layout['label_width_px'] * scale
        label_h_px = layout['label_height_px'] * scale
        gap_h_px = layout['gap_height_px'] * scale
        columns = layout['columns']
        origin_x = (self.width() - roll_w_px) / 2.0
        origin_y = (self.height() - roll_h_px) / 2.0
        painter.setPen(QPen(QColor('#64748b'), 1))
        painter.setBrush(QBrush(QColor('#334155')))
        painter.drawRect(0, 0, self.width(), self.height())
        painter.setPen(QPen(QColor('#94a3b8'), 1))
        painter.setBrush(QBrush(QColor('#e2e8f0')))
        painter.drawRect(int(origin_x), int(origin_y), int(roll_w_px), int(roll_h_px))
        label_area_h = label_h_px
        if layout['has_gap'] and gap_h_px > 0:
            gap_top = origin_y + label_area_h
            painter.setPen(QPen(QColor('#f59e0b'), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor('#422006')))
            painter.drawRect(int(origin_x), int(gap_top), int(roll_w_px), int(gap_h_px))
            painter.setPen(QPen(QColor('#fbbf24')))
            gap_label = 'Media Gap (~3mm)'
            painter.drawText(int(origin_x + 4), int(gap_top + gap_h_px / 2.0 + 4), gap_label)
        else:
            painter.setPen(QPen(QColor('#475569'), 1, Qt.PenStyle.DotLine))
            painter.drawLine(int(origin_x), int(origin_y + label_area_h), int(origin_x + roll_w_px), int(origin_y + label_area_h))
            painter.setPen(QPen(QColor('#64748b')))
            painter.drawText(int(origin_x + 4), int(origin_y + label_area_h - 12), 'Continuous (no gap)')
        self.hitboxes = {}
        offsets = normalize_element_offsets(self.manager.get_element_offsets())
        for col in range(columns):
            cell_x = origin_x + col * label_w_px
            cell_y = origin_y
            self._paint_label_cell(painter, cell_x, cell_y, label_w_px, label_h_px, offsets, register_hitboxes=col == 0)
            if columns > 1 and col == 0:
                painter.setPen(QPen(QColor('#0288D1'), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(cell_x + label_w_px), int(cell_y), int(cell_x + label_w_px), int(cell_y + label_h_px))
        painter.end()

    def _is_element_active(self, element_id: str) -> bool:
        """True when this element is the current click-to-edit selection."""
        active_key = canonical_element_id(getattr(self.manager, '_active_element_key', None))
        return active_key == canonical_element_id(element_id)

    def _text_pen(self, element_id: str) -> QPen:
        """Pen for label text; active elements render in highlight blue."""
        color = self.HIGHLIGHT_COLOR if self._is_element_active(element_id) else self.STANDARD_TEXT_COLOR
        return QPen(color)

    @staticmethod
    def _register_text_hitbox(hitboxes, element_id, text_rect):
        """Store a screen-space QRect for click detection from preview text bounds."""
        hitboxes[element_id] = text_rect.toAlignedRect()

    def _draw_preview_text(self, painter, element_id, text, font, anchor_x, top_y, align='left', register_hitboxes=False):
        """
        Draw preview text from the shared top-origin label coordinate.

        ReportLab drawString uses a bottom-left baseline, while this preview uses
        a top-left text box. CoordinateTranslator owns that PDF conversion; the
        preview path paints the same top Y directly.
        """
        safe_text = str(text or '')
        if not safe_text:
            return QRect()
        fm = QFontMetrics(font)
        text_width = max(1, fm.horizontalAdvance(safe_text))
        box_height = max(1.0, float(font.pointSizeF() or font.pointSize() or fm.height()) * PREVIEW_PX_PER_INCH / 72.0)
        if align == 'center':
            rect_x = float(anchor_x) - text_width / 2.0
            flags = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
        elif align == 'right':
            rect_x = float(anchor_x) - text_width
            flags = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight
        else:
            rect_x = float(anchor_x)
            flags = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft
        text_rect = QRectF(rect_x, float(top_y), float(text_width), box_height)
        painter.save()
        painter.setPen(self._text_pen(element_id))
        painter.setFont(font)
        painter.drawText(text_rect, int(flags), safe_text)
        painter.restore()
        if register_hitboxes:
            self._register_text_hitbox(self.hitboxes, element_id, text_rect)
        return text_rect

    def _draw_preview_text_bottom_anchored(self, painter, element_id, text, font, anchor_x, bottom_y, register_hitboxes=False):
        """
        Draw preview text with ``bottom_y`` as the exact bottom-left anchor.

        Price and batch index must share this bottom-anchor meaning with the
        physical ReportLab path to avoid baseline drift between preview/PDF.
        """
        safe_text = str(text or '')
        if not safe_text:
            return QRect()
        fm = QFontMetrics(font)
        text_width = max(1, fm.horizontalAdvance(safe_text))
        box_height = max(1.0, float(font.pointSizeF() or font.pointSize() or fm.height()) * PREVIEW_PX_PER_INCH / 72.0)
        text_rect = QRectF(float(anchor_x), float(bottom_y) - box_height, float(text_width), box_height)
        painter.save()
        painter.setPen(self._text_pen(element_id))
        painter.setFont(font)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft), safe_text)
        painter.restore()
        if register_hitboxes:
            self._register_text_hitbox(self.hitboxes, element_id, text_rect)
        return text_rect

    def _paint_label_cell(self, painter, x0, y0, w, h, offsets, register_hitboxes=False):
        """Draw one dummy label cell at pixel coordinates (top-left origin)."""
        painter.setPen(QPen(QColor('#334155'), 1))
        painter.setBrush(QBrush(QColor('#FFFFFF')))
        painter.drawRect(int(x0), int(y0), int(w), int(h))
        typo = self.manager.get_typography_settings()
        translator = CoordinateTranslator(preview_origin_x=x0, preview_origin_y=y0)

        def preview_font(element_key):
            typo_key = typography_key_prefix(element_key)
            font = QFont('Arial') if typo_key == 'mrp' else QFont()
            font.setPointSize(int(typo.get(f'{typo_key}_size', 6)))
            thickness = normalize_font_thickness(typo.get(f'{typo_key}_thickness'), 'Extra Bold' if bool(typo.get(f'{typo_key}_bold', False)) else 'Normal')
            if thickness == 'Extra Bold':
                font.setWeight(QFont.Weight.Black)
            elif thickness == 'Bold':
                font.setBold(True)
            return font
        company_font = preview_font('company')
        company_text = self.DUMMY_COMPANY
        self._draw_preview_text(painter, 'company', company_text, company_font, translator.preview_x(w / 2.0 + preview_spin_x_delta(offsets, 'company')), translator.preview_y(4.0 + preview_spin_y_delta(offsets, 'company')), align='center', register_hitboxes=register_hitboxes)
        product_font = preview_font('product')
        product_text = self.DUMMY_PRODUCT
        self._draw_preview_text(painter, 'product', product_text, product_font, translator.preview_x(w / 2.0 + preview_spin_x_delta(offsets, 'product')), translator.preview_y(14.0 + preview_spin_y_delta(offsets, 'product')), align='center', register_hitboxes=register_hitboxes)
        bar_top_px, bar_left_px, bar_w, bar_h = barcode_preview_layout(w, h, offsets)
        bar_top = translator.preview_y(bar_top_px)
        bar_left = translator.preview_x(bar_left_px)
        self._paint_barcode_modules(painter, self.DUMMY_BARCODE, bar_left, bar_top, bar_w, bar_h)
        if self._is_element_active('barcode'):
            painter.save()
            painter.setPen(QPen(self.HIGHLIGHT_COLOR, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            outline_left = int(round(bar_left))
            outline_top = int(round(bar_top))
            outline_w = max(0, int(round(bar_w)) - 1)
            outline_h = max(0, int(round(bar_h)) - 1)
            painter.drawRect(outline_left, outline_top, outline_w, outline_h)
            painter.restore()
        if register_hitboxes:
            self.hitboxes['barcode'] = QRect(int(round(bar_left)), int(round(bar_top)), max(0, int(round(bar_w))), max(0, int(round(bar_h))))
        barcode_font = preview_font('barcode_num')
        self._draw_preview_text(painter, 'barcode_num', self.DUMMY_BARCODE, barcode_font, translator.preview_x(w / 2.0 + preview_spin_x_delta(offsets, 'barcode_num')), translator.preview_y(barcode_number_preview_top(h, offsets)), align='center', register_hitboxes=register_hitboxes)
        batch_font = preview_font('batch_index')
        batch_text = SAMPLE_LABEL_BATCH_INDEX
        self._draw_preview_text_bottom_anchored(painter, 'batch_index', batch_text, batch_font, translator.preview_x(5.0 + preview_spin_x_delta(offsets, 'batch_index')), translator.preview_y(h - 6.0 + preview_spin_y_delta(offsets, 'batch_index')), register_hitboxes=register_hitboxes)
        mrp_font = preview_font('price')
        mrp_text = self.DUMMY_MRP
        self._draw_preview_text_bottom_anchored(painter, 'price', mrp_text, mrp_font, translator.preview_x(5.0 + preview_spin_x_delta(offsets, 'price')), translator.preview_y(h - 22.0 + preview_spin_y_delta(offsets, 'price')), register_hitboxes=register_hitboxes)
        cipher_font = preview_font('cipher')
        cipher_text = self.DUMMY_CIPHER
        cipher_right, cipher_top = cipher_preview_endpoint(w, h, offsets)
        self._draw_preview_text(painter, 'cipher', cipher_text, cipher_font, translator.preview_x(cipher_right), translator.preview_y(cipher_top), align='right', register_hitboxes=register_hitboxes)
        supplier_font = preview_font('supplier_code')
        supplier_fm = QFontMetrics(supplier_font)
        supplier_text = self.DUMMY_SUPPLIER[:5]
        supplier_anchor_x, supplier_anchor_y = supplier_preview_anchor(w, h, offsets)
        supplier_x = translator.preview_x(supplier_anchor_x)
        supplier_y = translator.preview_y(supplier_anchor_y)
        painter.save()
        painter.translate(supplier_x, supplier_y)
        painter.rotate(90)
        painter.setPen(self._text_pen('supplier_code'))
        painter.setFont(supplier_font)
        supplier_w = supplier_fm.horizontalAdvance(supplier_text)
        supplier_bx = int(-supplier_w / 2)
        supplier_by = supplier_fm.ascent()
        painter.drawText(supplier_bx, supplier_by, supplier_text)
        if register_hitboxes:
            br = supplier_fm.boundingRect(supplier_text)
            local_hit = QRect(supplier_bx + br.left(), supplier_by + br.top(), br.width(), br.height())
            self.hitboxes['supplier_code'] = painter.transform().mapRect(local_hit)
        painter.restore()

    @staticmethod
    def _paint_barcode_modules(painter, barcode_value, bar_left, bar_top, bar_width, bar_height):
        """Paint the preview barcode from real Code 39 modules with fixed spacing."""
        pattern = encode_code39_modules(barcode_value)
        rectangles = barcode_module_bar_rects(pattern, bar_left, bar_top, bar_width, bar_height)
        if not rectangles:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for rect_left, rect_top, rect_width, rect_height in rectangles:
            painter.fillRect(QRectF(rect_left, rect_top, rect_width, rect_height), QColor('#000000'))
        painter.restore()
EDITABLE_LABEL_ELEMENTS = {'company': ('Company Name', True), 'product': ('Product Name', True), 'barcode': ('Barcode Graphic', False), 'barcode_num': ('Barcode Number', True), 'price': ('Price / MRP Text', True), 'cipher': ('Cipher Code', True), 'batch_index': (SAMPLE_LABEL_BATCH_INDEX, True), 'supplier_code': (SAMPLE_LABEL_SUPPLIER, True)}
QUICK_SELECT_LABEL_OVERRIDES = {'batch_index': 'Batch Index (1/QTY)', 'supplier_code': 'Supplier Code'}
COL_SL = 0
COL_BARCODE = 1
COL_NAME = 2
COL_SUPPLIER = 3
COL_PURCHASE = 4
COL_MRP = 5
COL_INDEX = 6
COL_PRINT_QTY = 7
PURCHASE_PRICE_ROLE = Qt.ItemDataRole.UserRole


class PriceKeyCipherDelegate(QStyledItemDelegate):
    """Cipher-row editor: one click selects all, typing stays uppercase live."""

    def createEditor(self, parent, option, index):
        """Only row 1 (cipher letters) is editable."""
        if index.row() != 1:
            return None
        editor = QLineEdit(parent)
        editor.setMaxLength(1)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setStyleSheet(theme.barcode_manager_active_button_style())
        editor.setContentsMargins(0, 0, 0, 0)
        editor.textEdited.connect(lambda _text, ed=editor: self._force_uppercase(ed))
        editor.installEventFilter(self)
        return editor

    def updateEditorGeometry(self, editor, option, index):
        """Fill the cell so the letter is not clipped by grid borders or padding."""
        try:
            rect = option.rect
            editor.setGeometry(rect.adjusted(0, 0, -1, -1))
        except Exception:
            super().updateEditorGeometry(editor, option, index)

    def setEditorData(self, editor, index):
        """Open the cell with the current letter already uppercased."""
        try:
            value = str(index.data() or '').strip().upper()[:1]
        except Exception:
            value = ''
        editor.setText(value)

    def setModelData(self, editor, model, index):
        """Commit a single uppercase cipher letter back to the table."""
        model.setData(index, (editor.text() or '').strip().upper()[:1], Qt.ItemDataRole.EditRole)

    def _force_uppercase(self, editor: QLineEdit):
        """Rewrite keystrokes to uppercase while the user is still typing."""
        try:
            raw = editor.text() or ''
            cleaned = raw.upper()[:1]
            if raw == cleaned:
                return
            editor.blockSignals(True)
            editor.setText(cleaned)
            editor.blockSignals(False)
            editor.setCursorPosition(len(cleaned))
        except Exception:
            pass

    def eventFilter(self, obj, event):
        """Select all cell text on focus or single mouse click."""
        if isinstance(obj, QLineEdit):
            if event.type() == QEvent.Type.FocusIn:
                QTimer.singleShot(0, obj.selectAll)
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    QTimer.singleShot(0, obj.selectAll)
                    return True
        return super().eventFilter(obj, event)

class BarcodePrintQueueDelegate(QStyledItemDelegate):
    """Inline editor for Supplier Code and Print Qty columns in the print queue."""

    EDITABLE_COLUMNS = frozenset({COL_SUPPLIER, COL_PRINT_QTY})

    def __init__(self, table, host=None):
        """Attach optional host window for Enter-key navigation between fields."""
        super().__init__(table)
        self._host = host
        self._current_editor = None
        self._current_index = None
        self._navigation_busy = False

    def createEditor(self, parent, option, index):
        """Create a flush billing-style editor for editable queue columns."""
        if index.column() not in self.EDITABLE_COLUMNS:
            return None
        row = index.row()
        col = index.column()
        editor = QLineEdit(parent)
        editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        theme.prepare_barcode_queue_cell_editor(editor)
        self._current_editor = editor
        self._current_index = index
        if col == COL_PRINT_QTY:
            editor.setValidator(QIntValidator(0, 99999, editor))
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.returnPressed.connect(
            lambda ed=editor, target_row=row, target_col=col: self.handle_enter_navigation(
                ed,
                target_row,
                target_col,
            )
        )
        editor.installEventFilter(self)
        if self._host is not None:
            editor.installEventFilter(self._host)
        QTimer.singleShot(0, editor.selectAll)
        return editor

    def destroyEditor(self, editor, index):
        """Clear active editor tracking when the cell editor closes."""
        if self._current_editor is editor:
            self._current_editor = None
            self._current_index = None
        super().destroyEditor(editor, index)

    def updateEditorGeometry(self, editor, option, index):
        """Fill the cell so edited values are not clipped by thick borders."""
        try:
            editor.setGeometry(option.rect.adjusted(1, 1, -1, -1))
        except Exception:
            super().updateEditorGeometry(editor, option, index)

    def setEditorData(self, editor, index):
        """Load the current cell text and force readable edit colors."""
        theme.prepare_barcode_queue_cell_editor(editor)
        editor.setText(str(index.data() or ''))

    def setModelData(self, editor, model, index):
        """Commit edited supplier code or print quantity back to the grid."""
        if index.column() == COL_PRINT_QTY:
            text = (editor.text() or '').strip()
            model.setData(index, text, Qt.ItemDataRole.EditRole)
            return
        model.setData(index, (editor.text() or '').strip(), Qt.ItemDataRole.EditRole)

    def paint(self, painter, option, index):
        """Show editable cells with input-style background and dark text when selected."""
        if index.column() in self.EDITABLE_COLUMNS:
            colors = theme._theme_colors()
            opt = QStyleOptionViewItem(option)
            painter.save()
            painter.fillRect(option.rect, QColor(colors["input_bg"]))
            painter.restore()
            if opt.state & QStyle.StateFlag.State_Selected:
                opt.state &= ~QStyle.StateFlag.State_Selected
            opt.palette.setColor(QPalette.ColorRole.Text, QColor(colors["input_text"]))
            opt.palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["input_text"]))
            super().paint(painter, opt, index)
            return
        super().paint(painter, option, index)

    def eventFilter(self, obj, event):
        """Enter/Escape navigation and select-all on focus or click."""
        if obj is self._current_editor and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                row = self._current_index.row() if self._current_index is not None else -1
                col = self._current_index.column() if self._current_index is not None else -1
                self.handle_enter_navigation(obj, row, col)
                return True
            if key == Qt.Key.Key_Escape:
                self.closeEditor.emit(obj, QStyledItemDelegate.EndEditHint.RevertModelCache)
                return True
        if isinstance(obj, QLineEdit):
            if event.type() == QEvent.Type.FocusIn:
                QTimer.singleShot(0, obj.selectAll)
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    QTimer.singleShot(0, obj.selectAll)
                    return True
        return super().eventFilter(obj, event)

    def handle_enter_navigation(self, editor: QLineEdit, row: int, col: int) -> None:
        """Supplier Code -> Print Qty -> product lookup search field."""
        if self._navigation_busy or self._host is None:
            return
        if row < 0 or col not in self.EDITABLE_COLUMNS:
            return
        self._navigation_busy = True
        try:
            self.commitData.emit(editor)
            self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.SubmitModelCache)
        except Exception:
            self._navigation_busy = False
            return

        host = self._host

        def _move_focus() -> None:
            try:
                if col == COL_SUPPLIER:
                    host.move_to_queue_cell(row, COL_PRINT_QTY)
                elif col == COL_PRINT_QTY:
                    host.focus_search_input()
            finally:
                self._navigation_busy = False

        QTimer.singleShot(0, _move_focus)

class BarcodeManagerWindow(UiMemoryMixin, QDialog):
    """Operator workspace for building and printing thermal barcode labels."""

    def __init__(self, parent=None, db=None, rows=None):
        super().__init__(parent)
        self.db = db
        self.barcode_settings = BarcodeSettings().load()
        if self.db is not None:
            try:
                from bizora_core.barcode_db import fetch_barcode_preferences, preferences_to_barcode_settings
                self.barcode_settings = preferences_to_barcode_settings(fetch_barcode_preferences(self.db))
            except Exception:
                pass
        self.calibration = load_calibration_config()
        self.engine = LabelRenderEngine(self.barcode_settings)
        self._product_popup = None
        self._product_popup_table = None
        self._product_selection_dialog = None
        self._product_selection_table = None
        self._suppress_product_popup = False
        self._active_element_key = None
        self.current_active_element = None
        self.setWindowTitle('Barcode Print Queue')
        self.setMinimumSize(900, 520)
        self.setStyleSheet(self._window_style())
        self._build_ui()
        self._disable_button_auto_defaults()
        if rows:
            self.load_rows(rows)
        self._init_ui_memory()

    def showEvent(self, event):
        """Place keyboard focus on the first sensible queue field when opened."""
        super().showEvent(event)
        if not hasattr(self, "table"):
            return
        if getattr(self, '_queue_focus_initialized', False):
            return
        self._queue_focus_initialized = True
        QTimer.singleShot(0, self._initialize_queue_focus)

    def _initialize_queue_focus(self) -> None:
        """Focus search on an empty queue, otherwise the last row Supplier Code."""
        if not hasattr(self, "table"):
            return
        if self.table.rowCount() > 0:
            self._focus_supplier_on_last_row()
        else:
            self.focus_search_input()

    def move_to_queue_cell(self, row: int, col: int) -> None:
        """Open an editable queue cell for keyboard entry."""
        if row < 0 or col not in BarcodePrintQueueDelegate.EDITABLE_COLUMNS:
            return
        item = self.table.item(row, col)
        if item is None:
            return
        self.table.setCurrentCell(row, col)
        self.table.scrollToItem(item)
        self.table.setFocus(Qt.FocusReason.OtherFocusReason)
        self.table.editItem(item)
        QTimer.singleShot(0, self._select_queue_cell_editor)
        QTimer.singleShot(100, self._select_queue_cell_editor)

    def focus_queue_cell(self, row: int, col: int) -> None:
        """Backward-compatible alias for queue cell focus."""
        self.move_to_queue_cell(row, col)

    def _select_queue_cell_editor(self) -> None:
        """Select all text in the active queue cell editor."""
        editor = self.table.focusWidget()
        if isinstance(editor, QLineEdit):
            editor.setFocus(Qt.FocusReason.OtherFocusReason)
            editor.selectAll()

    def focus_search_input(self) -> None:
        """Move keyboard focus to the product lookup field."""
        self.search_product_input.setFocus(Qt.FocusReason.OtherFocusReason)
        self.search_product_input.selectAll()

    def _focus_supplier_on_last_row(self) -> None:
        """Jump to Supplier Code on the most recently added queue row."""
        row = self.table.rowCount() - 1
        if row >= 0:
            self.focus_queue_cell(row, COL_SUPPLIER)
        else:
            self.focus_search_input()

    def _after_product_added(self) -> None:
        """Clear lookup text and continue entry on the new row Supplier Code."""
        self._suppress_product_popup = True
        try:
            self.search_product_input.clear()
        finally:
            self._suppress_product_popup = False
        QTimer.singleShot(0, self._focus_supplier_on_last_row)
        self._schedule_live_preview()

    def _build_ui(self):
        """Lightweight print queue: search, item grid, and dispatch actions."""
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        search_frame = QFrame()
        search_frame.setStyleSheet(self._strip_style())
        search_row = QHBoxLayout(search_frame)
        search_row.setContentsMargins(10, 8, 10, 8)
        search_row.addWidget(self._label('Add Product Lookup'))
        self.search_input = QLineEdit()
        self.search_input.setStyleSheet(self._input_style())
        self.search_input.setPlaceholderText('Type product name or barcode...')
        self.search_product_input = self.search_input
        self.search_product_input.setMaximumWidth(350)
        self.search_product_input.installEventFilter(self)
        search_row.addWidget(self.search_input, 1)
        self.settings_btn = QPushButton('⚙ Barcode Settings')
        self.settings_btn.setStyleSheet(self._button_style("primary"))
        self.settings_btn.setFixedHeight(32)
        self.settings_btn.setMinimumWidth(160)
        self.settings_btn.clicked.connect(self.open_barcode_settings)
        search_row.addWidget(self.settings_btn)
        root.addWidget(search_frame)
        self.items_table = self._build_grid()
        self.table = self.items_table
        root.addWidget(self.items_table, 1)
        root.addWidget(self._build_action_panel())

    @staticmethod
    def _make_button_non_default(button):
        """Prevent Enter from activating dialog buttons while editing fields."""
        if button is None:
            return
        try:
            button.setAutoDefault(False)
        except Exception:
            pass
        try:
            button.setDefault(False)
        except Exception:
            pass

    def _disable_button_auto_defaults(self):
        """Apply non-default behavior to every QPushButton on this dialog."""
        try:
            for button in self.findChildren(QPushButton):
                self._make_button_non_default(button)
        except Exception:
            pass

    def open_barcode_settings(self):
        """Open barcode configuration using the hosting window as dialog parent."""
        if getattr(self, '_barcode_settings_dialog_open', False):
            return
        self._barcode_settings_dialog_open = True
        try:
            from ui.barcode_settings import open_barcode_settings_dialog

            host = self.window()
            open_barcode_settings_dialog(parent=host, db=self.db)
        except Exception as exc:
            QMessageBox.warning(self, 'Barcode Settings', f'Could not open settings: {exc}')
        finally:
            self._barcode_settings_dialog_open = False
            QTimer.singleShot(0, self._restore_queue_after_settings)

    def _restore_queue_after_settings(self):
        """Return focus to the print queue after the settings dialog closes."""
        try:
            host = self.window()
            if host is not None:
                if host.isMinimized():
                    host.showNormal()
                host.raise_()
                host.activateWindow()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            if self.table.rowCount() > 0:
                self._focus_supplier_on_last_row()
            else:
                self.focus_search_input()
        except Exception:
            pass

    def _build_settings_tab(self) -> QWidget:
        """Hardware (left), company/cipher/preview/active-element editor (right)."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(12)
        hardware_col = QVBoxLayout()
        hardware_col.setContentsMargins(0, 0, 0, 0)
        hardware_col.setSpacing(8)
        hardware_frame = QFrame()
        hardware_frame.setStyleSheet(self._strip_style())
        hardware_form = QFormLayout(hardware_frame)
        hardware_form.setContentsMargins(10, 10, 10, 10)
        hardware_form.setHorizontalSpacing(12)
        hardware_form.setVerticalSpacing(8)
        hardware_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hardware_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        printer_hbox_widget = QWidget()
        printer_hbox = QHBoxLayout(printer_hbox_widget)
        printer_hbox.setContentsMargins(0, 0, 0, 0)
        printer_hbox.setSpacing(10)
        self.printer_combo = QComboBox()
        self.printer_combo.setStyleSheet(self._input_style())
        self.printer_combo.setMinimumWidth(160)
        self.printer_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        printer_hbox.addWidget(self.printer_combo, 1)
        self.refresh_printers_btn = QPushButton('Refresh Printers')
        self.refresh_printers_btn.setStyleSheet(self._button_style("primary"))
        self.refresh_printers_btn.setFixedHeight(30)
        self.refresh_printers_btn.setMinimumWidth(120)
        self.refresh_printers_btn.clicked.connect(self.load_system_printers)
        printer_hbox.addWidget(self.refresh_printers_btn)
        add_printer_btn = QPushButton('Add Printer')
        add_printer_btn.setStyleSheet(self._button_style("primary"))
        add_printer_btn.setFixedHeight(30)
        add_printer_btn.setMinimumWidth(120)
        add_printer_btn.clicked.connect(self.open_windows_printer_settings)
        printer_hbox.addWidget(add_printer_btn)
        hardware_form.addRow(self._form_row_label('Printer'), printer_hbox_widget)
        QTimer.singleShot(0, self.load_system_printers)
        self.size_combo = QComboBox()
        self.size_combo.setStyleSheet(self._input_style())
        self.size_combo.addItems(list(STICKER_SIZE_OPTIONS))
        hardware_form.addRow(self._form_row_label('Sticker Size'), self.size_combo)
        gap_row_widget = QWidget()
        gap_row = QHBoxLayout(gap_row_widget)
        gap_row.setContentsMargins(0, 0, 0, 0)
        gap_row.setSpacing(8)
        self.gap_combo = QComboBox()
        self.gap_combo.setStyleSheet(self._input_style())
        self.gap_combo.addItems(['With Gap (Standard 3mm spacing)', 'Continuous (No Gap)'])
        gap_row.addWidget(self.gap_combo, 1)
        self.sticker_setup_btn = QPushButton('Sticker Setup')
        self.sticker_setup_btn.setStyleSheet(self._button_style("primary"))
        self.sticker_setup_btn.setFixedHeight(30)
        self.sticker_setup_btn.setMinimumWidth(120)
        self.sticker_setup_btn.clicked.connect(self.open_sticker_calibration)
        gap_row.addWidget(self.sticker_setup_btn)
        hardware_form.addRow(self._form_row_label('Media Gap'), gap_row_widget)
        self.padding_combo = QComboBox()
        self.padding_combo.setStyleSheet(self._input_style())
        self.padding_combo.addItems(BARCODE_PADDING_OPTIONS)
        hardware_form.addRow(self._form_row_label('Barcode Padding'), self.padding_combo)
        hardware_col.addWidget(hardware_frame)
        hardware_col.addWidget(self._build_quick_select_panel())
        hardware_col.addStretch(1)
        columns.addLayout(hardware_col, 0)
        data_col = QVBoxLayout()
        data_col.setContentsMargins(0, 0, 0, 0)
        data_col.setSpacing(6)
        data_frame = QFrame()
        data_frame.setStyleSheet(self._strip_style())
        data_layout = QVBoxLayout(data_frame)
        data_layout.setContentsMargins(8, 6, 8, 6)
        data_layout.setSpacing(4)
        company_container = QWidget()
        company_container.setFixedWidth(180)
        company_container.setFixedHeight(42)
        company_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        company_block = QVBoxLayout(company_container)
        company_block.setContentsMargins(0, 0, 0, 0)
        company_block.setSpacing(0)
        company_lbl = self._compact_field_label('Company Name')
        company_lbl.setFixedHeight(14)
        company_block.addWidget(company_lbl)
        self.company_input = QLineEdit(self.barcode_settings.company_name)
        self.company_input.setStyleSheet(self._compact_input_style())
        self.company_input.setFixedSize(180, 26)
        self.company_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.company_input.editingFinished.connect(self._on_company_changed)
        self.company_input.installEventFilter(self)
        company_block.addWidget(self.company_input)
        data_layout.addWidget(company_container, 0, Qt.AlignmentFlag.AlignLeft)
        price_row = QHBoxLayout()
        price_row.setContentsMargins(0, 2, 0, 0)
        price_row.setSpacing(8)
        price_key_lbl = self._compact_field_label('Price Key')
        price_key_lbl.setFixedHeight(14)
        price_key_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        price_row.addWidget(price_key_lbl, 0, Qt.AlignmentFlag.AlignTop)
        self.price_key_matrix = self._build_price_key_matrix()
        self.price_key_host = QWidget()
        self.price_key_host.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        price_host_layout = QHBoxLayout(self.price_key_host)
        price_host_layout.setContentsMargins(0, 0, 0, 0)
        price_host_layout.setSpacing(0)
        price_host_layout.addWidget(self.price_key_matrix)
        host_w = self._price_key_pixel_width(self.price_key_matrix)
        self.price_key_host.setFixedSize(host_w, 74)
        price_row.addWidget(self.price_key_host, 0, Qt.AlignmentFlag.AlignLeft)
        price_row.addStretch(1)
        data_layout.addLayout(price_row)
        data_col.addWidget(data_frame)
        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.setSpacing(8)
        preview_heading = QLabel('Live Label Preview (Dummy Data) - Click an element to edit')
        preview_heading.setStyleSheet(theme.barcode_manager_label_style())
        preview_row.addWidget(preview_heading)
        preview_row.addStretch(1)
        self.sample_print_btn = QPushButton('Print Sample')
        self.sample_print_btn.setStyleSheet(self._button_style("success"))
        self.sample_print_btn.setFixedHeight(28)
        self.sample_print_btn.setMinimumWidth(110)
        self.sample_print_btn.clicked.connect(self.print_sample_label)
        preview_row.addWidget(self.sample_print_btn)
        data_col.addLayout(preview_row)
        self.preview_canvas = LabelPreviewCanvas(self)
        self.preview_canvas.element_selected.connect(self._on_canvas_element_selected)
        data_col.addWidget(self.preview_canvas)
        self.size_combo.currentTextChanged.connect(self.update_preview_canvas_size)
        self.active_element_group = self._build_active_element_panel()
        data_col.addWidget(self.active_element_group, 0, Qt.AlignmentFlag.AlignTop)
        data_col.addStretch(1)
        self.size_combo.currentIndexChanged.connect(self.update_preview_canvas_size)
        columns.addLayout(data_col, 1)
        self.update_preview_canvas_size(self.size_combo.currentText())
        columns.setStretch(0, 1)
        columns.setStretch(1, 2)
        layout.addLayout(columns, 1)
        layout.addSpacing(8)
        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 0, 0, 6)
        save_row.setSpacing(10)
        save_row.addStretch(1)
        self.cancel_config_btn = QPushButton('Cancel Configuration')
        self.cancel_config_btn.setStyleSheet(self._cancel_button_style())
        self.cancel_config_btn.setMinimumHeight(32)
        self.cancel_config_btn.setMinimumWidth(160)
        self.cancel_config_btn.clicked.connect(self.cancel_label_settings)
        save_row.addWidget(self.cancel_config_btn)
        self.save_config_btn = QPushButton('Save Configuration Settings')
        self.save_config_btn.setStyleSheet(self._save_settings_button_style())
        self.save_config_btn.setMinimumHeight(32)
        self.save_config_btn.setMinimumWidth(220)
        self.save_config_btn.clicked.connect(self.save_label_settings)
        save_row.addWidget(self.save_config_btn)
        save_row.addStretch(1)
        layout.addLayout(save_row)
        return tab

    def _wire_settings_preview_signals(self):
        """Connect settings-tab widgets to the debounced live preview canvas."""
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(200)
        self._preview_timer.timeout.connect(self.update_live_preview)
        self.company_input.textChanged.connect(self._schedule_live_preview)
        self.size_combo.currentTextChanged.connect(self.update_preview_canvas_size)
        self.size_combo.currentIndexChanged.connect(self._schedule_live_preview)
        self.gap_combo.currentTextChanged.connect(self.update_preview_canvas_size)
        self.gap_combo.currentIndexChanged.connect(self._schedule_live_preview)
        self.price_key_matrix.itemChanged.connect(self._schedule_live_preview)

    def update_preview_canvas_size(self, _size_text=None):
        """
        Resize preview to full roll width (2-Up when dual) plus gap strip at 100 px/inch.
        """
        if not hasattr(self, 'preview_canvas'):
            return
        try:
            text = _size_text
            if text is None and hasattr(self, 'size_combo'):
                text = self.size_combo.currentText()
            gap_text = ''
            if hasattr(self, 'gap_combo'):
                gap_text = self.gap_combo.currentText()
            layout = preview_roll_layout(text or '', gap_text)
            width_px = int(round(layout['roll_width_px'])) + 12
            height_px = int(round(layout['roll_height_px'])) + 12
            width_px = max(width_px, 100)
            height_px = max(height_px, 52)
            self.preview_canvas.setFixedSize(width_px, height_px)
            self.preview_canvas.update()
            QCoreApplication.processEvents()
        except Exception:
            pass

    def is_dual_roll_layout(self) -> bool:
        """True when the sticker size combo selects a dual 2-Up roll."""
        if hasattr(self, 'size_combo'):
            return parse_sticker_size_text(self.size_combo.currentText()).get('columns', 1) > 1
        try:
            from bizora_core.barcode_db import fetch_barcode_preferences
            if self.db:
                prefs = fetch_barcode_preferences(self.db)
                from bizora_core.barcode_db import _size_index_from_stored
                return _size_index_from_stored(prefs.get('default_size', 0)) == 1
        except Exception:
            pass
        return False

    def _render_calibration_profile(self) -> dict:
        """Merge sticker_config.json with the active sticker size selection."""
        if hasattr(self, 'size_combo'):
            cfg = calibration_profile_from_size_text(self.size_combo.currentText(), load_calibration_config())
            cfg['element_offsets'] = self.get_element_offsets()
            return cfg
        from bizora_core.barcode_db import build_calibration_profile_from_prefs, fetch_barcode_preferences
        if self.db:
            try:
                prefs = fetch_barcode_preferences(self.db)
                return build_calibration_profile_from_prefs(prefs, load_calibration_config())
            except Exception:
                pass
        return dict(load_calibration_config())

    def _build_quick_select_panel(self) -> QGroupBox:
        """Left-side shortcut buttons for selecting editable preview elements."""
        group = QGroupBox('Quick Select Element')
        group.setStyleSheet(self._strip_style() + self._group_box_style())
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setSpacing(6)
        self._quick_select_buttons = {}
        for element_key, (label_text, _supports_typography) in EDITABLE_LABEL_ELEMENTS.items():
            button = QPushButton(QUICK_SELECT_LABEL_OVERRIDES.get(element_key, label_text))
            button.setStyleSheet(self._compact_button_style())
            button.setFixedHeight(28)
            button.clicked.connect(lambda _checked=False, key=element_key: self.select_element(key))
            self._quick_select_buttons[element_key] = button
            layout.addWidget(button)
        return group

    def _update_quick_select_button_styles(self):
        """Highlight the quick-select button matching the active preview element."""
        if not hasattr(self, '_quick_select_buttons'):
            return
        for element_key, button in self._quick_select_buttons.items():
            if element_key == self.current_active_element:
                button.setStyleSheet(self._quick_select_active_style())
            else:
                button.setStyleSheet(self._compact_button_style())

    def select_element(self, element_id: str):
        """Select an editable label element from quick buttons or canvas clicks."""
        self._on_canvas_element_selected(element_id)

    def _build_active_element_panel(self) -> QGroupBox:
        """Single contextual editor for the canvas element last clicked."""
        self.active_element_group = QGroupBox('Active Element Settings: [Click an item above]')
        self.active_element_group.setObjectName('activeElementPanel')
        self.active_element_group.setStyleSheet(self._strip_style() + self._group_box_style() + self._active_element_group_style() + self._checkbox_style())
        panel_layout = QVBoxLayout(self.active_element_group)
        panel_layout.setContentsMargins(10, 10, 10, 24)
        panel_layout.setSpacing(4)
        panel_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        lbl_style = theme.barcode_manager_muted_hint_style()
        self.active_position_label = QLabel('Position: X: 0 | Y: 0')
        self.active_position_label.setFixedHeight(14)
        self.active_position_label.setStyleSheet(theme.barcode_manager_label_style())
        panel_layout.addWidget(self.active_position_label)
        controls_row = QHBoxLayout()
        controls_row.setSpacing(20)
        controls_row.setAlignment(Qt.AlignmentFlag.AlignTop)
        dpad_col = QVBoxLayout()
        dpad_col.setContentsMargins(0, 0, 0, 4)
        dpad_col.setSpacing(2)
        dpad_heading = QLabel('Direction')
        dpad_heading.setFixedHeight(12)
        dpad_heading.setStyleSheet(lbl_style)
        dpad_col.addWidget(dpad_heading)
        dpad_widget = QWidget()
        dpad_widget.setFixedSize(124, 130)
        dpad_layout = QGridLayout(dpad_widget)
        dpad_layout.setContentsMargins(0, 0, 0, 4)
        dpad_layout.setSpacing(5)
        dpad_btn_style = self._dpad_push_style()
        self._offset_dpad_buttons = []
        btn_up = QPushButton('Up')
        btn_down = QPushButton('Dn')
        btn_left = QPushButton('Lt')
        btn_right = QPushButton('Rt')
        for btn in (btn_up, btn_down, btn_left, btn_right):
            btn.setStyleSheet(dpad_btn_style)
            btn.setFixedSize(36, 36)
            btn.setEnabled(False)
            self._offset_dpad_buttons.append(btn)
        btn_up.clicked.connect(self._nudge_active_up)
        btn_down.clicked.connect(self._nudge_active_down)
        btn_left.clicked.connect(lambda: self._adjust_active_offset(-1, 0))
        btn_right.clicked.connect(lambda: self._adjust_active_offset(1, 0))
        dpad_layout.addWidget(btn_up, 0, 1)
        dpad_layout.addWidget(btn_left, 1, 0)
        dpad_layout.addWidget(btn_right, 1, 2)
        dpad_layout.addWidget(btn_down, 2, 1)
        dpad_col.addWidget(dpad_widget, 0, Qt.AlignmentFlag.AlignLeft)
        controls_row.addLayout(dpad_col, 0)
        typo_col = QVBoxLayout()
        typo_col.setSpacing(5)
        typo_heading = QLabel('Typography')
        typo_heading.setStyleSheet(lbl_style)
        typo_col.addWidget(typo_heading)
        typo_col.addWidget(self._build_font_size_stepper())
        self.element_thickness_combo = QComboBox()
        self.element_thickness_combo.setStyleSheet(self._input_style())
        self.element_thickness_combo.addItems(FONT_THICKNESS_OPTIONS)
        self.element_thickness_combo.setEnabled(False)
        self.element_thickness_combo.currentIndexChanged.connect(self._on_active_element_control_changed)
        typo_col.addWidget(self.element_thickness_combo)
        self.bold_checkbox = create_checkbox('Bold Text')
        self.bold_checkbox.setEnabled(False)
        self.bold_checkbox.stateChanged.connect(self._on_active_element_control_changed)
        typo_col.addWidget(self.bold_checkbox)
        controls_row.addLayout(typo_col, 0)
        controls_row.addStretch(1)
        panel_layout.addLayout(controls_row)
        self.active_element_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.active_element_group.setMinimumHeight(236)
        return self.active_element_group

    def _build_font_size_stepper(self) -> QWidget:
        """Font size with explicit minus/plus buttons (native spin arrows fail on dark theme)."""
        frame = QFrame()
        frame.setStyleSheet(theme.barcode_manager_strip_style())
        row = QHBoxLayout(frame)
        row.setContentsMargins(6, 6, 6, 6)
        row.setSpacing(6)
        step_style = self._stepper_button_style()
        self.size_stepper_label = QLabel('Size')
        self.size_stepper_label.setStyleSheet(theme.barcode_manager_muted_hint_style())
        row.addWidget(self.size_stepper_label)
        self.font_down_btn = QPushButton('−')
        self.font_down_btn.setFixedSize(36, 36)
        self.font_down_btn.setStyleSheet(step_style)
        self.font_down_btn.setToolTip('Decrease size')
        self.font_down_btn.setEnabled(False)
        self.font_down_btn.clicked.connect(self._decrease_font_size)
        self.font_size_input = QSpinBox()
        self.font_size_input.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self.font_size_input.setKeyboardTracking(True)
        self.font_size_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.font_size_input.setStyleSheet(self._spin_style())
        self.font_size_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.font_size_input.setFixedSize(52, 36)
        self.font_size_input.setEnabled(False)
        self.font_size_input.valueChanged.connect(self._on_active_element_control_changed)
        self.font_up_btn = QPushButton('+')
        self.font_up_btn.setFixedSize(36, 36)
        self.font_up_btn.setStyleSheet(step_style)
        self.font_up_btn.setToolTip('Increase size')
        self.font_up_btn.setEnabled(False)
        self.font_up_btn.clicked.connect(self._increase_font_size)
        row.addWidget(self.font_down_btn)
        row.addWidget(self.font_size_input)
        row.addWidget(self.font_up_btn)
        frame.setMinimumWidth(200)
        return frame

    def _decrease_font_size(self):
        """Step the active size value down using the visible decrement control."""
        if getattr(self, '_active_element_key', None) == 'barcode':
            self._adjust_active_barcode_size(-BARCODE_SIZE_STEP)
            return
        self.font_size_input.setValue(max(self.font_size_input.minimum(), self.font_size_input.value() - 1))

    def _increase_font_size(self):
        """Step the active size value up using the visible increment control."""
        if getattr(self, '_active_element_key', None) == 'barcode':
            self._adjust_active_barcode_size(BARCODE_SIZE_STEP)
            return
        self.font_size_input.setValue(min(self.font_size_input.maximum(), self.font_size_input.value() + 1))

    def _adjust_active_barcode_size(self, delta: int):
        """Resize the active barcode graphic without changing its position."""
        if getattr(self, '_active_element_key', None) != 'barcode':
            return
        current_w = int(self._live_offsets.get('barcode_graphic_w', 0) or 0)
        current_h = int(self._live_offsets.get('barcode_graphic_h', 0) or 0)
        next_w = max(BARCODE_WIDTH_MIN, min(BARCODE_WIDTH_MAX, current_w + delta))
        next_h = max(BARCODE_HEIGHT_MIN, min(BARCODE_HEIGHT_MAX, current_h + delta))
        self._live_offsets['barcode_graphic_w'] = next_w
        self._live_offsets['barcode_graphic_h'] = next_h
        self.font_size_input.blockSignals(True)
        self.font_size_input.setValue(next_w)
        self.font_size_input.blockSignals(False)
        self.trigger_preview_update()

    def _on_canvas_element_selected(self, element_id: str):
        """Load the contextual panel for the element clicked on the preview."""
        element_id = canonical_element_id(element_id)
        if element_id not in EDITABLE_LABEL_ELEMENTS:
            return
        self._active_element_key = element_id
        self.current_active_element = element_id
        display_name, _supports_typo = EDITABLE_LABEL_ELEMENTS[element_id]
        self.active_element_group.setTitle(f'Active Element: {display_name}')
        self._load_active_element_controls()
        self._set_offset_dpad_enabled(True)
        typo_enabled = EDITABLE_LABEL_ELEMENTS[element_id][1]
        size_enabled = typo_enabled or element_id == 'barcode'
        self.font_size_input.setEnabled(size_enabled)
        self.font_up_btn.setEnabled(size_enabled)
        self.font_down_btn.setEnabled(size_enabled)
        self.element_thickness_combo.setEnabled(typo_enabled)
        self.bold_checkbox.setEnabled(typo_enabled)
        self._update_quick_select_button_styles()
        if hasattr(self, 'preview_canvas'):
            self.preview_canvas.update()

    def _set_offset_dpad_enabled(self, enabled: bool):
        """Enable or disable the unified position D-Pad controls."""
        if hasattr(self, '_offset_dpad_buttons'):
            for button in self._offset_dpad_buttons:
                button.setEnabled(enabled)

    def _update_position_label(self):
        """Refresh the coordinate readout above the offset D-Pad."""
        key = self._active_element_key
        if not key:
            self.active_position_label.setText('Position: X: 0 | Y: 0')
            return
        offset_keys = element_offset_keys(key)
        if not offset_keys:
            self.active_position_label.setText('Position: X: 0 | Y: 0')
            return
        x_key, y_key = offset_keys
        x_val = int(self._live_offsets.get(x_key, 0))
        y_val = int(self._live_offsets.get(y_key, 0))
        self.active_position_label.setText(f'Position: X: {x_val} | Y: {y_val}')

    def _adjust_active_offset(self, delta_x: int, delta_y: int):
        """Move only the active element's canonical coordinate keys."""
        key = canonical_element_id(self._active_element_key)
        if not key:
            return
        offset_keys = element_offset_keys(key)
        if not offset_keys:
            return
        x_key, y_key = offset_keys
        if delta_x:
            new_x = max(-500, min(500, int(self._live_offsets.get(x_key, 0)) + delta_x))
            self._live_offsets[x_key] = new_x
        if delta_y:
            new_y = max(-500, min(500, int(self._live_offsets.get(y_key, 0)) + delta_y))
            self._live_offsets[y_key] = new_y
        self._update_position_label()
        self.trigger_preview_update()

    def _nudge_active_up(self):
        """Increase Y offset so the preview element moves upward on the label."""
        self._adjust_active_offset(0, 1)

    def _nudge_active_down(self):
        """Decrease Y offset so the preview element moves downward on the label."""
        self._adjust_active_offset(0, -1)

    def _install_arrow_key_filter(self):
        """Install an application-wide filter so arrows never steal spinbox focus."""
        if getattr(self, '_arrow_key_filter_installed', False):
            return
        try:
            app = QApplication.instance()
            if app:
                app.installEventFilter(self)
                self._arrow_key_filter_installed = True
        except Exception:
            pass

    def _teardown_app_event_filter(self):
        """Remove the application-wide arrow-key filter safely."""
        if not getattr(self, '_arrow_key_filter_installed', False):
            return
        try:
            app = QApplication.instance()
            if app:
                app.removeEventFilter(self)
        except Exception:
            pass
        self._arrow_key_filter_installed = False

    def _settings_dialog_has_focus(self) -> bool:
        """True when keyboard focus is inside this dialog's window."""
        if not self.isVisible():
            return False
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        try:
            return focus.window() is self.window()
        except RuntimeError:
            return False

    def _handle_arrow_key_press(self, key_code: int) -> bool:
        """Consume arrow keys for offset nudging when an element is selected."""
        if not self._active_element_key or not self.isVisible():
            return False
        if key_code == Qt.Key.Key_Up:
            self._nudge_active_up()
            return True
        if key_code == Qt.Key.Key_Down:
            self._nudge_active_down()
            return True
        if key_code == Qt.Key.Key_Left:
            self._adjust_active_offset(-1, 0)
            return True
        if key_code == Qt.Key.Key_Right:
            self._adjust_active_offset(1, 0)
            return True
        return False

    def _is_widget_in_price_key_tree(self, widget) -> bool:
        """True when widget is the price-key table or its in-cell editor."""
        if widget is None or not hasattr(self, 'price_key_matrix'):
            return False
        if not isinstance(widget, QWidget):
            return False
        matrix = self.price_key_matrix
        node = widget
        while node is not None:
            if node is matrix:
                return True
            parent = node.parentWidget()
            if parent is None:
                break
            node = parent
        return False

    def _clear_price_key_selection(self):
        """Remove the persistent blue highlight from the cipher matrix."""
        if not hasattr(self, 'price_key_matrix'):
            return
        try:
            table = self.price_key_matrix
            table.clearSelection()
            table.setCurrentItem(None)
            table.clearFocus()
            table.viewport().update()
        except Exception:
            pass

    def _on_price_key_edit_finished(self, _editor, _hint):
        """Drop selection highlight after the user leaves a cipher cell."""
        QTimer.singleShot(0, self._clear_price_key_selection)

    def eventFilter(self, watched, event):
        """Company field select-all; queue Enter flow; arrow keys; price-key cleanup."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if (
                    isinstance(watched, QLineEdit)
                    and hasattr(self, 'table')
                    and watched is not getattr(self, 'search_product_input', None)
                    and self.table.isAncestorOf(watched)
                ):
                    delegate = getattr(self, '_queue_delegate', None) or self.table.itemDelegate()
                    row = self.table.currentRow()
                    col = self.table.currentColumn()
                    if (
                        col in BarcodePrintQueueDelegate.EDITABLE_COLUMNS
                        and hasattr(delegate, 'handle_enter_navigation')
                    ):
                        delegate.handle_enter_navigation(watched, row, col)
                        return True
        if hasattr(self, 'search_product_input') and watched is self.search_product_input and (event.type() == QEvent.Type.KeyPress):
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._handle_search_enter()
                return True
            if key == Qt.Key.Key_Down:
                self._open_product_selection_dialog(self.search_product_input.text().strip())
                return True
            if key == Qt.Key.Key_Escape:
                self._hide_product_popup()
                if self.table.rowCount() > 0:
                    QTimer.singleShot(0, lambda: self.focus_queue_cell(self.table.rowCount() - 1, COL_PRINT_QTY))
                return True
        if hasattr(self, 'company_input') and watched is self.company_input:
            if event.type() == QEvent.Type.FocusIn:
                QTimer.singleShot(0, self.company_input.selectAll)
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    QTimer.singleShot(0, self.company_input.selectAll)
                    return True
        if event.type() == QEvent.Type.MouseButtonPress:
            if self.isVisible() and event.button() == Qt.MouseButton.LeftButton and hasattr(self, 'price_key_matrix'):
                try:
                    if not self._is_widget_in_price_key_tree(watched):
                        QTimer.singleShot(0, self._clear_price_key_selection)
                except Exception:
                    pass
        if event.type() == QEvent.Type.KeyPress:
            if self._settings_dialog_has_focus():
                if self._handle_arrow_key_press(event.key()):
                    return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        """Clear lookup state and remove the global arrow-key filter on close."""
        self.reset_product_lookup_state()
        self._teardown_app_event_filter()
        super().closeEvent(event)

    def _load_active_element_controls(self):
        """Push saved offset/typography values into the active element controls."""
        key = canonical_element_id(self._active_element_key)
        if not key:
            return
        self._active_element_key = key
        typo_key = typography_key_prefix(key)
        typo = self._live_typography
        defaults = default_typography_settings()
        self._update_position_label()
        for control in (self.font_size_input, self.bold_checkbox, self.element_thickness_combo):
            control.blockSignals(True)
        self._configure_active_size_control(key)
        if key == 'barcode':
            self.font_size_input.setValue(int(self._live_offsets.get('barcode_graphic_w', 0)))
        else:
            self.font_size_input.setValue(int(typo.get(f'{typo_key}_size', defaults.get(f'{typo_key}_size', 6))))
        bold_default = bool(typo.get(f'{typo_key}_bold', defaults.get(f'{typo_key}_bold', False)))
        thickness = normalize_font_thickness(typo.get(f'{typo_key}_thickness', defaults.get(f'{typo_key}_thickness')), 'Extra Bold' if bold_default else 'Normal')
        self.bold_checkbox.setChecked(thickness in ('Bold', 'Extra Bold'))
        thickness_idx = self.element_thickness_combo.findText(thickness)
        self.element_thickness_combo.setCurrentIndex(max(0, thickness_idx))
        for control in (self.font_size_input, self.bold_checkbox, self.element_thickness_combo):
            control.blockSignals(False)

    def _configure_active_size_control(self, key: str):
        """Switch the size stepper between text font size and barcode width."""
        if key == 'barcode':
            self.font_size_input.setRange(BARCODE_WIDTH_MIN, BARCODE_WIDTH_MAX)
            self.font_size_input.setToolTip('Barcode width adjustment in 0.5 mm steps')
            self.font_down_btn.setToolTip('Decrease barcode size')
            self.font_up_btn.setToolTip('Increase barcode size')
            if hasattr(self, 'size_stepper_label'):
                self.size_stepper_label.setText('Width')
            return
        self.font_size_input.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self.font_size_input.setToolTip('Font size in points')
        self.font_down_btn.setToolTip('Decrease font size')
        self.font_up_btn.setToolTip('Increase font size')
        if hasattr(self, 'size_stepper_label'):
            self.size_stepper_label.setText('Size')

    def _on_active_element_control_changed(self, _value=None):
        """Persist active size/typography edits and repaint the canvas."""
        key = canonical_element_id(self._active_element_key)
        if not key:
            return
        self._active_element_key = key
        if key == 'barcode':
            current_w = int(self._live_offsets.get('barcode_graphic_w', 0) or 0)
            current_h = int(self._live_offsets.get('barcode_graphic_h', 0) or 0)
            next_w = max(BARCODE_WIDTH_MIN, min(BARCODE_WIDTH_MAX, self.font_size_input.value()))
            height_delta = next_w - current_w
            next_h = max(BARCODE_HEIGHT_MIN, min(BARCODE_HEIGHT_MAX, current_h + height_delta))
            self._live_offsets['barcode_graphic_w'] = next_w
            self._live_offsets['barcode_graphic_h'] = next_h
            if next_w != self.font_size_input.value():
                self.font_size_input.blockSignals(True)
                self.font_size_input.setValue(next_w)
                self.font_size_input.blockSignals(False)
            self.trigger_preview_update()
            return
        if EDITABLE_LABEL_ELEMENTS[key][1]:
            typo_key = typography_key_prefix(key)
            sender = self.sender() if hasattr(self, 'sender') else None
            if sender is self.bold_checkbox:
                next_thickness = 'Bold' if self.bold_checkbox.isChecked() else 'Normal'
                combo_idx = self.element_thickness_combo.findText(next_thickness)
                self.element_thickness_combo.blockSignals(True)
                self.element_thickness_combo.setCurrentIndex(max(0, combo_idx))
                self.element_thickness_combo.blockSignals(False)
            self._live_typography[f'{typo_key}_size'] = self.font_size_input.value()
            thickness = normalize_font_thickness(self.element_thickness_combo.currentText(), 'Normal')
            self._live_typography[f'{typo_key}_thickness'] = thickness
            self._live_typography[f'{typo_key}_bold'] = thickness in ('Bold', 'Extra Bold')
            self.bold_checkbox.blockSignals(True)
            self.bold_checkbox.setChecked(thickness in ('Bold', 'Extra Bold'))
            self.bold_checkbox.blockSignals(False)
        self.trigger_preview_update()

    def get_typography_settings(self) -> dict:
        """Font size and bold flags for PDF/preview rendering."""
        merged = default_typography_settings()
        if getattr(self, '_use_live_layout_edits', False):
            merged.update(getattr(self, '_live_typography', {}))
            return merged
        if self.db:
            try:
                from bizora_core.barcode_db import fetch_barcode_preferences
                merged.update(fetch_barcode_preferences(self.db).get('typography_settings') or {})
                return merged
            except Exception:
                pass
        merged.update(getattr(self, '_live_typography', {}))
        return merged

    def get_element_offsets(self) -> dict:
        """Alignment offsets for PDF/preview rendering."""
        merged = normalize_element_offsets()
        if getattr(self, '_use_live_layout_edits', False):
            live_offsets = getattr(self, '_live_offsets', {})
            return normalize_element_offsets({**merged, **live_offsets})
        if self.db:
            try:
                from bizora_core.barcode_db import fetch_barcode_preferences
                saved_offsets = fetch_barcode_preferences(self.db).get('element_offsets') or {}
                return normalize_element_offsets({**merged, **saved_offsets})
            except Exception:
                pass
        live_offsets = getattr(self, '_live_offsets', {})
        return normalize_element_offsets({**merged, **live_offsets})

    def _apply_saved_label_settings(self):
        """Restore combo boxes, offsets, and printer from barcode_settings.json."""
        try:
            if hasattr(self, 'size_combo'):
                idx = int(self.barcode_settings.sticker_size_index or 0)
                if 0 <= idx < self.size_combo.count():
                    self.size_combo.setCurrentIndex(idx)
            if hasattr(self, 'gap_combo'):
                gidx = int(self.barcode_settings.media_gap_index or 0)
                if 0 <= gidx < self.gap_combo.count():
                    self.gap_combo.setCurrentIndex(gidx)
            self._live_offsets = normalize_element_offsets(self.barcode_settings.element_offsets or {})
            self._live_typography = dict(self.barcode_settings.typography_settings or default_typography_settings())
            if self._active_element_key:
                self._load_active_element_controls()
            if hasattr(self, 'preview_canvas'):
                self.preview_canvas.update()
            if self.barcode_settings.printer_name and hasattr(self, 'printer_combo'):
                pidx = self.printer_combo.findText(self.barcode_settings.printer_name)
                if pidx >= 0:
                    self.printer_combo.setCurrentIndex(pidx)
            if hasattr(self, 'padding_combo'):
                padding = getattr(self.barcode_settings, 'barcode_padding', BARCODE_PADDING_OPTIONS[0])
                pad_idx = self.padding_combo.findText(padding)
                if pad_idx < 0:
                    pad_idx = 0
                self.padding_combo.setCurrentIndex(pad_idx)
        except Exception:
            pass

    def cancel_label_settings(self):
        """Discard unsaved label settings and restore the last saved configuration."""
        try:
            if self.db is not None and getattr(self, '_close_on_settings_save', False):
                from bizora_core.barcode_db import fetch_barcode_preferences, preferences_to_barcode_settings
                prefs = fetch_barcode_preferences(self.db)
                self.barcode_settings = preferences_to_barcode_settings(prefs)
            else:
                self.barcode_settings = BarcodeSettings().load()
            self.engine.settings = self.barcode_settings
            self.calibration = load_calibration_config()
            if hasattr(self, 'company_input'):
                self.company_input.setText(self.barcode_settings.company_name or '')
            self._reload_price_key_matrix()
            self._active_element_key = None
            self.current_active_element = None
            if hasattr(self, 'active_element_group'):
                self.active_element_group.setTitle('Active Element Settings: [Click an item above]')
            self._set_offset_dpad_enabled(False)
            if hasattr(self, 'font_size_input'):
                self.font_size_input.setEnabled(False)
                self.font_up_btn.setEnabled(False)
                self.font_down_btn.setEnabled(False)
            if hasattr(self, 'bold_checkbox'):
                self.bold_checkbox.setEnabled(False)
            if hasattr(self, 'element_thickness_combo'):
                self.element_thickness_combo.setEnabled(False)
            self._apply_saved_label_settings()
            self._update_quick_select_button_styles()
            self._clear_price_key_selection()
            if hasattr(self, 'preview_canvas'):
                self.preview_canvas.update()
            if getattr(self, '_close_on_settings_save', False):
                self.reject()
        except Exception as exc:
            QMessageBox.warning(self, 'Cancel Failed', str(exc))

    def _reload_price_key_matrix(self):
        """Refresh cipher letters from the persisted price-key map."""
        if not hasattr(self, 'price_key_matrix'):
            return
        self.price_key_matrix.blockSignals(True)
        try:
            for col, number in enumerate(DEFAULT_PRICE_DIGITS):
                letter = self.barcode_settings.price_key_map.get(number, DEFAULT_PRICE_LETTERS[col])
                let_item = self.price_key_matrix.item(1, col)
                if let_item is not None:
                    let_item.setText(str(letter).upper()[:1])
                    let_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        except Exception:
            pass
        finally:
            self.price_key_matrix.blockSignals(False)

    def save_label_settings(self):
        """Persist company, cipher matrix, offsets, paper size, and printer."""
        try:
            self.barcode_settings.company_name = self.company_input.text().strip()
            self.engine.settings.company_name = self.barcode_settings.company_name
            self.barcode_settings.price_key_map = self._current_price_map()
            self.barcode_settings.sticker_size_index = self.size_combo.currentIndex()
            self.barcode_settings.media_gap_index = self.gap_combo.currentIndex()
            self.barcode_settings.element_offsets = self.get_element_offsets()
            self.barcode_settings.typography_settings = self.get_typography_settings()
            self.barcode_settings.printer_name = self.printer_combo.currentText().strip()
            self.barcode_settings.barcode_padding = self.padding_combo.currentText() if hasattr(self, 'padding_combo') else BARCODE_PADDING_OPTIONS[0]
            self.barcode_settings.font_thickness = normalize_font_thickness(getattr(self.barcode_settings, 'font_thickness', DEFAULT_FONT_THICKNESS), DEFAULT_FONT_THICKNESS)
            if self.db is not None:
                from bizora_core.barcode_db import save_barcode_preferences
                size_text = self.size_combo.currentText() if hasattr(self, 'size_combo') else self.barcode_settings.sticker_size_index
                gap_text = self.gap_combo.currentText() if hasattr(self, 'gap_combo') else self.barcode_settings.media_gap_index
                payload = {'company_name': self.barcode_settings.company_name, 'cipher_string': ''.join((str(self.barcode_settings.price_key_map.get(d, ''))[:1].upper() for d in DEFAULT_PRICE_DIGITS)), 'price_key_map': self.barcode_settings.price_key_map, 'default_size': size_text, 'default_gap': gap_text, 'default_printer': self.barcode_settings.printer_name, 'barcode_padding': self.barcode_settings.barcode_padding, 'font_thickness': self.barcode_settings.font_thickness, 'element_offsets': self.barcode_settings.element_offsets, 'typography_settings': self.barcode_settings.typography_settings}
                if not save_barcode_preferences(self.db, payload):
                    QMessageBox.warning(self, 'Save Failed', 'Could not update barcode_settings table.')
                    return
            if not self.barcode_settings.save():
                QMessageBox.warning(self, 'Save Failed', 'Could not write barcode_settings.json. Check file permissions.')
                return
            cfg = load_calibration_config()
            cfg['element_offsets'] = self.barcode_settings.element_offsets
            save_calibration_config(cfg)
            self.calibration = cfg
            QMessageBox.information(self, 'Settings Saved', 'Settings Saved Successfully.')
            if getattr(self, '_close_on_settings_save', False):
                self.accept()
        except Exception as exc:
            QMessageBox.warning(self, 'Save Failed', str(exc))

    def load_system_printers(self):
        """Probe live system printers and restore the last saved selection."""
        self.printer_combo.clear()
        printers = list_system_printers()
        if printers:
            self.printer_combo.addItems(printers)
        else:
            self.printer_combo.addItem('(Default Printer)')
        preferred = ''
        if hasattr(self, 'barcode_settings') and self.barcode_settings.printer_name:
            preferred = self.barcode_settings.printer_name
        elif self.printer_combo.count():
            try:
                from PySide6.QtPrintSupport import QPrinterInfo
                preferred = QPrinterInfo.defaultPrinter().printerName()
            except Exception:
                preferred = ''
        if preferred:
            idx = self.printer_combo.findText(preferred)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)

    @staticmethod
    def _price_key_edit_triggers():
        """Edit triggers compatible with PySide6 builds lacking SingleClicked."""
        triggers = QAbstractItemView.EditTrigger.SelectedClicked | QAbstractItemView.EditTrigger.AnyKeyPressed
        try:
            triggers |= QAbstractItemView.EditTrigger.SingleClicked
        except AttributeError:
            triggers |= QAbstractItemView.EditTrigger.CurrentChanged
        return triggers

    @staticmethod
    def _price_key_pixel_width(table: QTableWidget) -> int:
        """Total widget width so all columns fit inside the table viewport."""
        try:
            col_total = sum((table.columnWidth(col) for col in range(table.columnCount())))
        except Exception:
            col_total = PRICE_KEY_COL_WIDTH * PRICE_KEY_COL_COUNT
        frame = table.frameWidth() * 2
        grid_lines = max(0, table.columnCount() - 1)
        return col_total + frame + grid_lines + 4

    def _sync_price_key_table_geometry(self):
        """After layout, widen the matrix so digit 0 and its cipher letter stay visible."""
        if not hasattr(self, 'price_key_matrix'):
            return
        table = self.price_key_matrix
        try:
            total_w = self._price_key_pixel_width(table)
            table.setFixedWidth(total_w)
            table.setFixedHeight(74)
            if hasattr(self, 'price_key_host'):
                host_w = self._price_key_pixel_width(table)
                self.price_key_host.setFixedSize(host_w, 74)
            table.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            table.viewport().update()
        except Exception:
            pass

    def _build_price_key_matrix(self):
        """Build the 2-row x 10-col editable cipher matrix table."""
        col_width = PRICE_KEY_COL_WIDTH
        matrix = QTableWidget(2, PRICE_KEY_COL_COUNT)
        self.price_key_matrix = matrix
        self.price_key_matrix.setStyleSheet(theme.barcode_manager_matrix_style())
        try:
            self.price_key_matrix.setShowGrid(True)
            self.price_key_matrix.setGridStyle(Qt.PenStyle.SolidLine)
        except Exception:
            pass
        self.price_key_matrix.horizontalHeader().setVisible(False)
        self.price_key_matrix.verticalHeader().setVisible(False)
        self.price_key_matrix.verticalHeader().setFixedWidth(0)
        self.price_key_matrix.verticalHeader().setMaximumWidth(0)
        self.price_key_matrix.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.price_key_matrix.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.price_key_matrix.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._price_key_delegate = PriceKeyCipherDelegate(self.price_key_matrix)
        self.price_key_matrix.setItemDelegate(self._price_key_delegate)
        self._price_key_delegate.closeEditor.connect(self._on_price_key_edit_finished)
        self.price_key_matrix.setEditTriggers(self._price_key_edit_triggers())
        self.price_key_matrix.blockSignals(True)
        for col, number in enumerate(DEFAULT_PRICE_DIGITS):
            top = QTableWidgetItem(number)
            top.setTextAlignment(Qt.AlignCenter)
            top.setFlags(top.flags() & ~Qt.ItemIsEditable)
            self.price_key_matrix.setItem(0, col, top)
            letter = self.barcode_settings.price_key_map.get(number, DEFAULT_PRICE_LETTERS[col])
            bottom = QTableWidgetItem(str(letter).upper()[:1])
            bottom.setTextAlignment(Qt.AlignCenter)
            self.price_key_matrix.setItem(1, col, bottom)
        self.price_key_matrix.blockSignals(False)
        header = self.price_key_matrix.horizontalHeader()
        header.setStretchLastSection(False)
        try:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            header.setDefaultSectionSize(col_width)
        except AttributeError:
            header.setSectionResizeMode(QHeaderView.Fixed)
            header.setDefaultSectionSize(col_width)
        for col in range(PRICE_KEY_COL_COUNT):
            self.price_key_matrix.setColumnWidth(col, col_width)
        self.price_key_matrix.setRowHeight(0, 30)
        self.price_key_matrix.setRowHeight(1, 34)
        self.price_key_matrix.setFixedWidth(self._price_key_pixel_width(matrix))
        self.price_key_matrix.setFixedHeight(74)
        self.price_key_matrix.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.price_key_matrix.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.price_key_matrix.itemChanged.connect(self._on_price_key_item_changed)
        return self.price_key_matrix

    def _build_grid(self):
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(['SL', 'Barcode', 'Product Name', 'Supplier Code', 'Cipher Price', 'MRP', 'Item Index', 'Print Qty'])
        self.table.setStyleSheet(self._table_style())
        self._queue_delegate = BarcodePrintQueueDelegate(self.table, self)
        self.table.setItemDelegate(self._queue_delegate)
        self.table.installEventFilter(self)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.verticalHeader().setMinimumSectionSize(30)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        try:
            header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        except AttributeError:
            header.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        self.table.setColumnWidth(COL_SL, 42)
        self.table.setColumnWidth(COL_BARCODE, 72)
        self.table.setColumnWidth(COL_SUPPLIER, 96)
        self.table.setColumnWidth(COL_PURCHASE, 88)
        self.table.setColumnWidth(COL_MRP, 72)
        self.table.setColumnWidth(COL_INDEX, 72)
        self.table.setColumnWidth(COL_PRINT_QTY, 72)
        self.table.cellClicked.connect(self._on_queue_cell_clicked)
        return self.table

    def _on_queue_cell_clicked(self, row: int, col: int) -> None:
        """Single-click opens Supplier Code or Print Qty for fast keyboard entry."""
        if col not in BarcodePrintQueueDelegate.EDITABLE_COLUMNS:
            return
        QTimer.singleShot(0, lambda target_row=row, target_col=col: self.focus_queue_cell(target_row, target_col))

    def _build_action_panel(self):
        frame = QFrame()
        frame.setStyleSheet(self._strip_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        layout.addStretch(1)
        self.remove_selected_btn = QPushButton('Remove Selected Item')
        self.remove_selected_btn.setStyleSheet(self._button_style("warning"))
        self.remove_selected_btn.setFixedHeight(34)
        self._make_button_non_default(self.remove_selected_btn)
        self.remove_selected_btn.clicked.connect(self.remove_selected_items)
        layout.addWidget(self.remove_selected_btn)
        self.clear_btn = QPushButton('Clear List')
        self.clear_btn.setStyleSheet(self._button_style("danger"))
        self.clear_btn.setFixedHeight(34)
        self.clear_btn.clicked.connect(self.clear_list)
        layout.addWidget(self.clear_btn)
        self.preview_btn = QPushButton('Preview Layout')
        self.preview_btn.setStyleSheet(self._button_style("primary"))
        self.preview_btn.setFixedHeight(34)
        self.preview_btn.clicked.connect(self.preview_layout)
        layout.addWidget(self.preview_btn)
        self.print_btn = QPushButton('Dispatch Print')
        self.print_btn.setStyleSheet(self._button_style("success"))
        self.print_btn.setFixedHeight(34)
        self.print_btn.clicked.connect(self.dispatch_print)
        layout.addWidget(self.print_btn)
        return frame

    def load_rows(self, rows):
        """Populate the grid from a list of pre-built label row dictionaries."""
        for row in rows or []:
            self._append_row(row)
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
            self._schedule_live_preview()
            QTimer.singleShot(0, self._focus_supplier_on_last_row)
        apply_adjustable_table_columns(self.table, sl_no_column=COL_SL)

    def _append_row(self, data):
        """Insert one label row dict into the grid."""
        try:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setRowHeight(r, 30)
            sl_item = self._readonly_item(str(r + 1))
            sl_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, COL_SL, sl_item)
            self.table.setItem(r, COL_BARCODE, self._readonly_item(str(data.get('barcode', '') or '')))
            self.table.setItem(r, COL_NAME, self._readonly_item(str(data.get('product_name', '') or '')))
            supplier_item = self._editable_item(normalized_supplier_code(data))
            if not supplier_item.text().strip():
                supplier_item.setToolTip('Supplier Code is blank; this sticker will print without a supplier code.')
            self.table.setItem(r, COL_SUPPLIER, supplier_item)
            raw_purchase_price = data.get('purchase_price', 0)
            cipher_text = encode_price_cipher(raw_purchase_price, self.barcode_settings.price_key_map or default_price_map())
            cipher_item = self._readonly_item(cipher_text)
            cipher_item.setData(PURCHASE_PRICE_ROLE, raw_purchase_price)
            cipher_item.setToolTip(f'Raw purchase price: {self._money(raw_purchase_price)}')
            self.table.setItem(r, COL_PURCHASE, cipher_item)
            self.table.setItem(r, COL_MRP, self._readonly_item(self._money(data.get('mrp'))))
            index_val = data.get('item_index')
            if index_val in (None, ''):
                index_val = r + 1
            self.table.setItem(r, COL_INDEX, self._readonly_item(str(index_val)))
            qty_value = data.get('print_qty', '')
            qty_text = ''
            if qty_value not in (None, ''):
                try:
                    qty_text = str(int(float(str(qty_value).strip())))
                except (TypeError, ValueError):
                    qty_text = str(qty_value)
            qty_item = self._editable_item(qty_text)
            self.table.setItem(r, COL_PRINT_QTY, qty_item)
            self._schedule_live_preview()
        except Exception:
            pass

    def add_product(self, product, supplier_code='', print_qty=1, item_index=None):
        """Build a row dict from a product record and append it to the grid."""
        if not product:
            return
        self._append_row({'barcode': product.get('barcode', ''), 'product_name': product.get('name', ''), 'supplier_code': normalized_supplier_code(supplier_code, product), 'purchase_price': product.get('purchase_rate', 0) or 0, 'mrp': product.get('mrp', 0) or product.get('sale_price', 0) or 0, 'item_index': item_index, 'print_qty': print_qty})
        apply_adjustable_table_columns(self.table, sl_no_column=COL_SL)

    def clear_list(self):
        self.table.setRowCount(0)
        self._reset_live_preview_placeholder()

    def _selected_queue_rows(self):
        """Return queue row numbers that are part of the actual table selection."""
        try:
            selection_model = self.table.selectionModel()
            if selection_model is None:
                return []
            selected_rows = {index.row() for index in selection_model.selectedRows()}
            return sorted((row for row in selected_rows if 0 <= row < self.table.rowCount()))
        except Exception:
            return []

    def remove_selected_items(self):
        """Remove selected queue rows and renumber the visible serial column."""
        try:
            if self.table.rowCount() == 0:
                QMessageBox.warning(self, 'Remove Item', 'Please select an item to remove.')
                return
            selected_rows = self._selected_queue_rows()
            if not selected_rows:
                QMessageBox.warning(self, 'Remove Item', 'Please select an item to remove.')
                return
            confirmation = QMessageBox.question(self, 'Remove Item', 'Are you sure you want to remove the selected item(s)?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if confirmation != QMessageBox.StandardButton.Yes:
                return
            next_row = min(selected_rows)
            for row in sorted(selected_rows, reverse=True):
                self.table.removeRow(row)
            self._renumber_queue_rows()
            if self.table.rowCount() > 0:
                next_row = min(next_row, self.table.rowCount() - 1)
                self.table.selectRow(next_row)
            else:
                self._reset_live_preview_placeholder()
            self._schedule_live_preview()
        except Exception as exc:
            QMessageBox.warning(self, 'Remove Item', f'Could not remove item: {exc}')

    def _renumber_queue_rows(self):
        """Refresh the SL column after row removals."""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_SL)
            if item is None:
                item = self._readonly_item('')
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, COL_SL, item)
            item.setText(str(row + 1))

    def _wire_live_preview_signals(self):
        """Connect UI changes to a debounced live sticker preview refresh."""
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(200)
        self._preview_timer.timeout.connect(self.update_live_preview)
        self.table.itemSelectionChanged.connect(self._schedule_live_preview)
        self.company_input.textChanged.connect(self._schedule_live_preview)

    def _schedule_live_preview(self):
        """Debounce rapid edits so preview regeneration does not stack up."""
        if hasattr(self, '_preview_timer'):
            self._preview_timer.start()

    def trigger_preview_update(self):
        """Immediately repaint the live preview after manual layout changes."""
        try:
            if hasattr(self, '_preview_timer'):
                self._preview_timer.stop()
            self.update_live_preview()
            QCoreApplication.processEvents()
        except Exception:
            if hasattr(self, 'preview_canvas'):
                self.preview_canvas.update()

    def _reset_live_preview_placeholder(self):
        """Refresh the dummy-data canvas when table selection is cleared."""
        if hasattr(self, 'preview_canvas'):
            self.preview_canvas.update()

    def _selected_row_dict(self):
        """Build a single label payload dict from the currently selected table row."""
        row = self.table.currentRow()
        if row < 0:
            selected = self.table.selectedItems()
            if selected:
                row = selected[0].row()
        if row < 0:
            return None
        barcode = self._cell_text(row, COL_BARCODE)
        name = self._cell_text(row, COL_NAME)
        if not barcode and (not name):
            return None
        qty = self._cell_int(row, COL_PRINT_QTY, 0)
        item_index = self._cell_text(row, COL_INDEX) or str(row + 1)
        return {'sl_no': self._cell_text(row, COL_SL) or str(row + 1), 'barcode': barcode, 'product_name': name, 'supplier_code': normalized_supplier_code(self._cell_text(row, COL_SUPPLIER)), 'purchase_price': self._cell_raw_purchase(row), 'mrp': self._cell_float(row, COL_MRP), 'item_index': item_index, 'print_qty': qty, 'batch_tag': f'{item_index}-{qty}'}

    def _preview_canvas_size_tuple(self):
        """Return live preview widget size for PDF coordinate scaling."""
        if hasattr(self, 'preview_canvas'):
            return (self.preview_canvas.width(), self.preview_canvas.height())
        return None

    def generate_single_preview_pdf(self):
        """Render one selected-row label to a temp PDF using DB barcode_settings."""
        row_data = self._selected_row_dict()
        if not row_data:
            return None
        try:
            out_path = os.path.join(tempfile.gettempdir(), 'temp_single_preview.pdf')
            preview_size = self._preview_canvas_size_tuple()
            if self.db:
                ok, _msg = compile_pdf_document_stream(self.db, [row_data], out_path, preview_canvas_size=preview_size, element_offsets=self.get_element_offsets(), typography_settings=self.get_typography_settings())
            else:
                ok, _msg = self.engine.render([row_data], out_path, calibration=self._render_calibration_profile(), element_offsets=self.get_element_offsets(), typography_settings=self.get_typography_settings(), preview_canvas_size=preview_size)
            if not ok or not os.path.exists(out_path):
                return None
            return out_path
        except Exception:
            return None

    def _current_target_printer(self) -> str:
        """Return the selected printer, falling back to persisted/default printer."""
        try:
            if hasattr(self, 'printer_combo'):
                selected = self.printer_combo.currentText().strip()
                if selected and selected != '(Default Printer)':
                    return selected
        except Exception:
            pass
        prefs = {}
        if self.db:
            try:
                from bizora_core.barcode_db import fetch_barcode_preferences
                prefs = fetch_barcode_preferences(self.db)
            except Exception:
                prefs = {}
        return _default_printer_name(prefs)

    def _sample_label_row(self) -> dict:
        """Build one dummy label row matching the live preview content."""
        return {'sl_no': '1', 'barcode': SAMPLE_LABEL_BARCODE, 'product_name': SAMPLE_LABEL_PRODUCT, 'supplier_code': SAMPLE_LABEL_SUPPLIER, 'supplier_short_code': SAMPLE_LABEL_ASSOCIATED_CODE, 'purchase_price': SAMPLE_LABEL_PURCHASE_PRICE, 'mrp': SAMPLE_LABEL_MRP, 'batch_index': SAMPLE_LABEL_BATCH_INDEX, 'item_index': SAMPLE_LABEL_ASSOCIATED_CODE, 'print_qty': 1, 'batch_tag': SAMPLE_LABEL_ASSOCIATED_CODE, '__sample_label': True}

    def _render_sample_to_temp(self):
        """Render one dummy live-preview label to a temp PDF."""
        try:
            sample_settings = BarcodeSettings()
            sample_settings.company_name = SAMPLE_LABEL_COMPANY
            sample_settings.price_key_map = self._current_price_map() if hasattr(self, 'price_key_matrix') else self.barcode_settings.price_key_map
            sample_engine = LabelRenderEngine(sample_settings)
            out_path = os.path.join(tempfile.gettempdir(), 'barcode_sample_label.pdf')
            ok, msg = sample_engine.render([self._sample_label_row()], out_path, calibration=self._render_calibration_profile(), element_offsets=self.get_element_offsets(), typography_settings=self.get_typography_settings(), preview_canvas_size=self._preview_canvas_size_tuple())
            if not ok:
                return (None, msg)
            return (out_path, msg)
        except Exception as exc:
            return (None, f'Sample render error: {exc}')

    def _paint_pdf_to_printer(self, temp_pdf_path: str, target_printer: str, calibration: dict):
        """Paint an already-rendered label PDF directly to the selected printer."""
        if fitz is None:
            return (False, 'PyMuPDF (fitz) is not installed. Run: pip install PyMuPDF')
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setPrinterName(target_printer)
            printer.setFullPage(True)
            cfg = calibration or self._render_calibration_profile()
            width_mm = float(cfg.get('roll_width', 76.2))
            height_mm = float(cfg.get('roll_height', 25.4))
            custom_page_size = QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter)
            printer.setPageSize(custom_page_size)
            margins = QMarginsF(0, 0, 0, 0)
            layout = QPageLayout(custom_page_size, QPageLayout.Orientation.Portrait, margins, QPageLayout.Unit.Millimeter)
            printer.setPageLayout(layout)
            pdf_doc = fitz.open(temp_pdf_path)
            painter = QPainter()
            painter.begin(printer)
            try:
                for i in range(len(pdf_doc)):
                    if i > 0:
                        printer.newPage()
                    page = pdf_doc.load_page(i)
                    pix = page.get_pixmap(dpi=300)
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                    try:
                        rect = printer.paperRect(QPrinter.Unit.DevicePixel)
                    except Exception:
                        rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                    if not rect.isValid() or rect.width() <= 0 or rect.height() <= 0:
                        rect = painter.viewport()
                    painter.drawImage(rect, img)
            finally:
                painter.end()
                pdf_doc.close()
            return (True, f'Labels injected directly to {target_printer} hardware successfully.')
        except Exception as exc:
            return (False, f'Failed to paint directly to printer driver:\n{exc}')

    def print_sample_label(self):
        """Render and print one dummy label using the current preview settings."""
        temp_pdf_path, msg = self._render_sample_to_temp()
        if not temp_pdf_path:
            QMessageBox.warning(self, 'Sample Print', msg)
            return
        target_printer = self._current_target_printer()
        if not target_printer:
            try:
                os.startfile(temp_pdf_path)
            except Exception:
                pass
            QMessageBox.warning(self, 'Sample Print', 'No printer is configured. Sample PDF was generated for preview.')
            return
        ok, print_msg = self._paint_pdf_to_printer(temp_pdf_path, target_printer, self._render_calibration_profile())
        if ok:
            QMessageBox.information(self, 'Sample Print', print_msg)
        elif fitz is None:
            try:
                os.startfile(temp_pdf_path)
            except Exception:
                pass
            QMessageBox.warning(self, 'Sample Print', f'{print_msg}\n\nSample PDF was generated for preview.')
        else:
            QMessageBox.critical(self, 'Sample Print', print_msg)

    def update_live_preview(self):
        """Repaint the high-DPI dummy-data preview canvas."""
        if hasattr(self, 'preview_canvas'):
            self.preview_canvas.update()

    def collect_rows(self):
        """Read the grid back into a list of label row dictionaries."""
        rows = []
        for r in range(self.table.rowCount()):
            try:
                rows.append({'sl_no': self._cell_text(r, COL_SL) or str(r + 1), 'barcode': self._cell_text(r, COL_BARCODE), 'product_name': self._cell_text(r, COL_NAME), 'supplier_code': normalized_supplier_code(self._cell_text(r, COL_SUPPLIER)), 'purchase_price': self._cell_raw_purchase(r), 'mrp': self._cell_float(r, COL_MRP), 'item_index': self._cell_text(r, COL_INDEX), 'print_qty': self._cell_text(r, COL_PRINT_QTY)})
            except Exception:
                continue
        return rows

    def _missing_supplier_row_numbers(self):
        """Return visible row numbers whose Supplier Code cell is still blank."""
        missing = []
        for r in range(self.table.rowCount()):
            try:
                barcode = self._cell_text(r, COL_BARCODE)
                name = self._cell_text(r, COL_NAME)
                supplier_code = normalized_supplier_code(self._cell_text(r, COL_SUPPLIER))
                if (barcode or name) and (not supplier_code):
                    missing.append(str(r + 1))
            except Exception:
                continue
        return missing

    def _render_to_temp(self):
        """Render current rows to a temp PDF. Returns (path|None, message)."""
        rows = self.collect_rows()
        if not rows:
            return (None, 'Add at least one product before printing.')
        try:
            out_path = os.path.join(tempfile.gettempdir(), 'barcode_labels.pdf')
            preview_size = self._preview_canvas_size_tuple()
            if self.db:
                ok, msg = compile_pdf_document_stream(self.db, rows, out_path, preview_canvas_size=preview_size, element_offsets=self.get_element_offsets(), typography_settings=self.get_typography_settings())
            else:
                self.calibration = self._render_calibration_profile()
                ok, msg = self.engine.render(rows, out_path, calibration=self.calibration, element_offsets=self.get_element_offsets(), typography_settings=self.get_typography_settings(), preview_canvas_size=preview_size)
            if not ok:
                return (None, msg)
            return (out_path, msg)
        except Exception as exc:
            return (None, f'Rendering error: {exc}')

    def preview_layout(self):
        path, msg = self._render_to_temp()
        if not path:
            QMessageBox.warning(self, 'Preview', msg)
            return
        try:
            os.startfile(path)
        except Exception:
            QMessageBox.information(self, 'Preview', f'Labels rendered to:\n{path}')

    def dispatch_print(self):
        """Inject the rendered labels straight into the printer driver.

        PyMuPDF rasterises each PDF page to a 300 DPI image which QPainter paints
        directly onto the QPrinter device - a complete shell/GUI bypass so no PDF
        viewer or Edge window can hijack the print.
        """
        target_printer = self._current_target_printer()
        if not target_printer:
            QMessageBox.warning(self, 'Print', 'Configure a printer in Barcode Settings (Settings menu or gear button).')
            return
        missing_supplier_rows = self._missing_supplier_row_numbers()
        if missing_supplier_rows:
            row_text = ', '.join(missing_supplier_rows[:12])
            if len(missing_supplier_rows) > 12:
                row_text += '...'
            reply = QMessageBox.question(self, 'Missing Supplier Code', f'Supplier Code is blank for row(s): {row_text}.\n\nThose stickers will print without a supplier code. Fill the Supplier Code column before printing, or continue if this is expected.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        temp_pdf_path, msg = self._render_to_temp()
        if not temp_pdf_path:
            QMessageBox.warning(self, 'Print', msg)
            return
        ok, print_msg = self._paint_pdf_to_printer(temp_pdf_path, target_printer, self._render_calibration_profile())
        if ok:
            QMessageBox.information(self, 'Spooler Active', print_msg)
        else:
            QMessageBox.critical(self, 'Hardware Error', print_msg)

    def open_windows_printer_settings(self):
        """Open the native Windows 'Devices and Printers' control panel."""
        try:
            os.system('control printers')
        except Exception as exc:
            QMessageBox.warning(self, 'Add Printer', f'Could not open printer settings: {exc}')

    def load_calibration_config(self):
        """Read sticker_config.json; return defaults if the file is missing."""
        return load_calibration_config()

    def open_sticker_calibration(self):
        """Launch the graphical sticker calibration dialog."""
        dialog = StickerCalibrationDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.calibration = load_calibration_config()

    def _on_company_changed(self):
        self.barcode_settings.company_name = self.company_input.text().strip()
        self.barcode_settings.save()

    def _on_price_key_item_changed(self, item):
        """Enforce single uppercase letters in the cipher row and persist the map."""
        if item is None or item.row() != 1:
            return
        self.price_key_matrix.blockSignals(True)
        cleaned = (item.text() or '').strip().upper()[:1]
        item.setText(cleaned)
        item.setTextAlignment(Qt.AlignCenter)
        self.price_key_matrix.blockSignals(False)
        self.barcode_settings.price_key_map = self._current_price_map()
        self.barcode_settings.save()
        self._schedule_live_preview()

    def _current_price_map(self) -> dict:
        """Read the cipher matrix back into a digit-character -> letter dict."""
        mapping = {}
        self.price_key_matrix.blockSignals(True)
        try:
            for col in range(self.price_key_matrix.columnCount()):
                num_item = self.price_key_matrix.item(0, col)
                let_item = self.price_key_matrix.item(1, col)
                if num_item is None:
                    continue
                number = num_item.text().strip()
                letter = let_item.text().strip().upper()[:1] if let_item else ''
                mapping[number] = letter or DEFAULT_PRICE_LETTERS[col % 10]
        finally:
            self.price_key_matrix.blockSignals(False)
        return mapping

    def _current_label_dims(self):
        """Return (width_pt, height_pt) for the selected sticker size (72 pt/inch)."""
        text = self.size_combo.currentText() if hasattr(self, 'size_combo') else ''
        profile = parse_sticker_size_text(text)
        return (profile['width_in'] * 72, profile['height_in'] * 72)

    def _current_gap_pt(self):
        """Return the media gap in points for the selected tracker mode."""
        text = self.gap_combo.currentText() if hasattr(self, 'gap_combo') else ''
        if text.startswith('Continuous'):
            return 0.0
        return 3.0 * 72.0 / 25.4

    def _on_search_enter(self):
        """Commit the highlighted popup product from the search field."""
        self._handle_search_enter()

    def _handle_search_enter(self):
        """Add an exact barcode match, otherwise show the Sales-style selector."""
        term = self.search_product_input.text().strip()
        if term:
            product = self._lookup_exact_barcode(term)
            if product:
                self.add_product(product, supplier_code=normalized_supplier_code(product), print_qty=1)
                self._clear_search_after_product_add()
                return
        self._open_product_selection_dialog(term)

    def _lookup_exact_barcode(self, barcode):
        """Return the active-company product whose barcode exactly matches."""
        if self.db is None:
            return None
        company_id = self._active_company_id()
        if not company_id:
            return None
        try:
            if hasattr(self.db, 'get_product_by_barcode'):
                return self.db.get_product_by_barcode(company_id, barcode)
            rows = self.db.execute_query('\n                SELECT id, name, barcode, hsn, color, size, unit, category,\n                       purchase_rate, sale_price, wholesale_rate, mrp,\n                       cgst, sgst, igst, cess, reorder_level,\n                       description, quantity, auto_barcode\n                FROM products\n                WHERE company_id = ? AND barcode = ?\n                ', (company_id, barcode))
            return rows[0] if rows else None
        except Exception:
            return None

    def _on_search_text_changed(self, text):
        """Refresh the floating product popup while the operator types."""
        if self._suppress_product_popup:
            return
        term = str(text or '').strip()
        if not term:
            self._hide_product_popup()
            return
        self._show_product_popup(term)

    def _active_company_id(self):
        """Return the active company id for product lookups, or None."""
        try:
            company = active_company_manager.get_active_company() if active_company_manager else None
            if hasattr(active_company_manager, 'get_active_company_id'):
                company_id = active_company_manager.get_active_company_id()
                if company_id:
                    return company_id
            if isinstance(company, dict):
                return company.get('id')
        except Exception:
            return None
        return None

    def _open_product_selection_dialog(self, initial_term=''):
        """Open the same compact product selector pattern used by Sales Entry."""
        company_id = self._active_company_id()
        if not company_id:
            QMessageBox.warning(self, 'Error', 'No active company selected.')
            return
        popup = QDialog(self)
        self._product_selection_dialog = popup
        popup.setWindowTitle('Select Product')
        popup.resize(620, 440)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)
        top = QHBoxLayout()
        search_lbl = QLabel('Search (name / barcode):')
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type to search...')
        top.addWidget(search_lbl)
        top.addWidget(search_input)
        layout.addLayout(top)
        hint = QLabel('Type to search. Max 100 results shown.')
        hint.setStyleSheet(theme.barcode_manager_muted_hint_style())
        layout.addWidget(hint)
        table = QTableWidget()
        self._product_selection_table = table
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(['Name', 'Barcode', 'Code', 'Rate', 'Stock'])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setColumnWidth(0, 220)
        table.setColumnWidth(1, 110)
        table.setColumnWidth(2, 80)
        table.setColumnWidth(3, 80)
        layout.addWidget(table)
        search_timer = QTimer(popup)
        search_timer.setSingleShot(True)
        search_timer.setInterval(200)

        def do_search():
            term = search_input.text().strip()
            table.setRowCount(0)
            if len(term) < 1:
                return
            try:
                results = self.db.search_products_limited(company_id, term, limit=100)
            except Exception:
                results = []
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            for product in results or []:
                row = table.rowCount()
                table.insertRow(row)
                name_item = QTableWidgetItem(str(product.get('name', '') or ''))
                name_item.setData(Qt.ItemDataRole.UserRole, product.get('id'))
                table.setItem(row, 0, name_item)
                table.setItem(row, 1, QTableWidgetItem(str(product.get('barcode', '') or '')))
                table.setItem(row, 2, QTableWidgetItem(str(product.get('code', '') or '')))
                rate = float(product.get('sale_price') or product.get('mrp') or product.get('wholesale_rate') or product.get('purchase_rate') or 0)
                table.setItem(row, 3, QTableWidgetItem(f'{rate:.2f}'))
                try:
                    stock = float(product.get('quantity') or 0.0)
                except (TypeError, ValueError):
                    stock = 0.0
                table.setItem(row, 4, QTableWidgetItem(f'{stock:.3f}'))
            table.blockSignals(False)
            table.setUpdatesEnabled(True)
            if table.rowCount() > 0:
                table.selectRow(0)
            apply_adjustable_table_columns(table)

        def select_product():
            row = table.currentRow()
            if row < 0:
                return
            product_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            product_name = table.item(row, 0).text()
            code_val = table.item(row, 2).text() if table.item(row, 2) else ''
            try:
                full_product = self.db.get_product_by_id(company_id, product_id)
            except Exception:
                full_product = None
            if full_product:
                product = full_product
                product['code'] = product.get('code') or product.get('item_code') or code_val
            else:
                product = {'id': product_id, 'name': product_name, 'barcode': table.item(row, 1).text() if table.item(row, 1) else '', 'code': code_val}
            popup.accept()
            self.add_product(product, supplier_code=normalized_supplier_code(product), print_qty=1)
            self._clear_search_after_product_add()

        def focus_popup_table():
            if table.rowCount() > 0:
                if table.currentRow() < 0:
                    table.selectRow(0)
                table.setFocus()

        def search_key_press(event):
            if event.key() == Qt.Key.Key_Down:
                focus_popup_table()
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                select_product()
                return
            if event.key() == Qt.Key.Key_Escape:
                popup.reject()
                return
            QLineEdit.keyPressEvent(search_input, event)

        def table_key_press(event):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                select_product()
                return
            if event.key() == Qt.Key.Key_Escape:
                popup.reject()
                return
            QTableWidget.keyPressEvent(table, event)
        search_timer.timeout.connect(do_search)
        search_input.textChanged.connect(lambda: search_timer.start())
        search_input.keyPressEvent = search_key_press
        table.keyPressEvent = table_key_press
        table.doubleClicked.connect(select_product)
        btns = QHBoxLayout()
        btns.addStretch(1)
        select_btn = QPushButton('Select')
        cancel_btn = QPushButton('Cancel')
        select_btn.clicked.connect(select_product)
        cancel_btn.clicked.connect(popup.reject)
        btns.addWidget(select_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)
        search_input.setText(initial_term)
        search_input.setFocus()
        if initial_term:
            search_input.selectAll()
            QTimer.singleShot(0, do_search)
        try:
            popup.exec()
        finally:
            self._product_selection_dialog = None
            self._product_selection_table = None

    def _clear_search_after_product_add(self):
        """Clear lookup text and continue on the new row Supplier Code."""
        self._after_product_added()

    def _search_products_for_popup(self, term):
        """Fetch product rows for the barcode queue popup without blocking the UI."""
        if self.db is None:
            return []
        company_id = self._active_company_id()
        if not company_id:
            return []
        try:
            rows = self.db.search_products_limited(company_id, term, limit=100)
            return rows or []
        except Exception:
            return []

    def _ensure_product_popup(self):
        """Create the reusable floating product selector dialog."""
        if self._product_popup is not None and self._product_popup_table is not None:
            return
        popup = QDialog(self)
        popup.setWindowTitle('Select Product')
        popup.setWindowFlags(Qt.WindowType.Popup)
        popup.setModal(False)
        popup.setStyleSheet(theme.entry_picker_dialog_style())
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(6, 6, 6, 6)
        table = QTableWidget(0, 5, popup)
        table.setHorizontalHeaderLabels(['Name', 'Barcode', 'Supplier Code', 'Purchase Price', 'MRP'])
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.itemDoubleClicked.connect(lambda _item: self._select_current_popup_product())

        def table_key_press(event):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._select_current_popup_product()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._hide_product_popup()
                self.search_product_input.setFocus()
                return
            QTableWidget.keyPressEvent(table, event)
        table.keyPressEvent = table_key_press
        layout.addWidget(table)
        self._product_popup = popup
        self._product_popup_table = table

    def _show_product_popup(self, term):
        """Display product matches directly below the queue search field."""
        self._ensure_product_popup()
        table = self._product_popup_table
        popup = self._product_popup
        if table is None or popup is None:
            return
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        table.setRowCount(0)
        for product in self._search_products_for_popup(term):
            row = table.rowCount()
            table.insertRow(row)
            supplier_code = normalized_supplier_code(product)
            values = [str(product.get('name', '') or ''), str(product.get('barcode', '') or ''), supplier_code, self._money(product.get('purchase_rate', 0)), self._money(product.get('mrp', 0) or product.get('sale_price', 0))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, product)
                table.setItem(row, col, item)
        table.blockSignals(False)
        table.setUpdatesEnabled(True)
        apply_adjustable_table_columns(table)
        if table.rowCount() < 1:
            self._hide_product_popup()
            return
        table.selectRow(0)
        popup.resize(max(self.search_product_input.width(), 620), 260)
        popup.move(self.search_product_input.mapToGlobal(QPoint(0, self.search_product_input.height())))
        popup.show()

    def _hide_product_popup(self):
        """Close the floating product selector if it is visible."""
        try:
            if self._product_popup is not None:
                self._product_popup.hide()
        except Exception:
            pass

    def reset_product_lookup_state(self):
        """Clear product lookup text and destroy any transient lookup popup."""
        self._suppress_product_popup = True
        try:
            if hasattr(self, 'search_product_input'):
                self.search_product_input.clear()
                self.search_product_input.clearFocus()
        except Exception:
            pass
        finally:
            self._suppress_product_popup = False
        try:
            if self._product_popup_table is not None:
                self._product_popup_table.clearSelection()
                self._product_popup_table.setRowCount(0)
        except Exception:
            pass
        try:
            if self._product_selection_table is not None:
                self._product_selection_table.clearSelection()
                self._product_selection_table.setRowCount(0)
        except Exception:
            pass
        try:
            if self._product_selection_dialog is not None:
                self._product_selection_dialog.reject()
                self._product_selection_dialog.close()
                self._product_selection_dialog.deleteLater()
        except Exception:
            pass
        self._product_selection_dialog = None
        self._product_selection_table = None
        try:
            if self._product_popup is not None:
                self._product_popup.hide()
                self._product_popup.close()
                self._product_popup.deleteLater()
        except Exception:
            pass
        self._product_popup = None
        self._product_popup_table = None

    def _select_current_popup_product(self):
        """Append the selected product to the queue and preserve raw price data."""
        table = self._product_popup_table
        if table is None or table.rowCount() < 1:
            self._show_product_popup(self.search_product_input.text().strip())
            return
        row = table.currentRow()
        if row < 0:
            row = 0
            table.selectRow(row)
        item = table.item(row, 0)
        product = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not product:
            return
        self.add_product(product, supplier_code=normalized_supplier_code(product), print_qty=1)
        self._hide_product_popup()
        self._after_product_added()

    @staticmethod
    def _money(value):
        try:
            return f'{float(value or 0):.2f}'
        except (TypeError, ValueError):
            return '0.00'

    def _cell_text(self, row, col):
        item = self.table.item(row, col)
        return item.text().strip() if item else ''

    def _cell_float(self, row, col, default=0.0):
        text = self._cell_text(row, col).replace(',', '').strip()
        try:
            return float(text) if text else default
        except ValueError:
            return default

    def _cell_int(self, row, col, default=0):
        """Read an integer table cell without forcing blank cells to one."""
        text = self._cell_text(row, col).replace(',', '').strip()
        try:
            return int(float(text)) if text else default
        except ValueError:
            return default

    def _cell_raw_purchase(self, row):
        """Return raw purchase price stored behind the visible cipher cell."""
        item = self.table.item(row, COL_PURCHASE)
        if item is not None:
            try:
                raw_value = item.data(PURCHASE_PRICE_ROLE)
                if raw_value not in (None, ''):
                    return float(raw_value)
            except (TypeError, ValueError):
                pass
        return self._cell_float(row, COL_PURCHASE)

    @staticmethod
    def _readonly_item(text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    @staticmethod
    def _editable_item(text):
        """Input-style cell for inline editable queue columns."""
        item = QTableWidgetItem(str(text or ''))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )
        try:
            colors = theme._theme_colors()
            fg = QColor(colors['input_text'])
            bg = QColor(colors['input_bg'])
            item.setBackground(bg)
            item.setForeground(fg)
            item.setData(Qt.ItemDataRole.BackgroundRole, QBrush(bg))
            item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(fg))
        except Exception:
            pass
        return item

    @staticmethod
    def _label(text):
        label = QLabel(text)
        label.setStyleSheet(theme.barcode_manager_label_style())
        return label

    @staticmethod
    def _form_row_label(text):
        """Left-column form label with enough width to avoid truncation."""
        label = QLabel(text)
        label.setStyleSheet(theme.barcode_manager_label_style())
        label.setMinimumWidth(108)
        return label

    @staticmethod
    def _compact_field_label(text):
        """Tight label sitting directly above a compact input field."""
        from ui import theme

        label = QLabel(text)
        label.setStyleSheet(theme.barcode_manager_label_style())
        label.setContentsMargins(0, 0, 0, 0)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return label

    @staticmethod
    def _active_element_group_style():
        """Extra bottom room so the direction D-Pad Down control is not clipped."""
        return '\n        QGroupBox#activeElementPanel {\n            padding-top: 8px;\n            padding-bottom: 14px;\n            margin-bottom: 4px;\n        }\n        '

    @staticmethod
    def _window_style():
        from ui import theme
        return theme.barcode_manager_shell_style()

    @staticmethod
    def _strip_style():
        from ui import theme
        return theme.barcode_manager_strip_style()

    @staticmethod
    def _group_box_style():
        from ui import theme
        return theme.barcode_manager_group_box_style()

    @staticmethod
    def _spin_style():
        from ui import theme
        return theme.barcode_manager_spin_style()

    @staticmethod
    def _active_element_spin_style():
        """Spinbox style with separated text field and clickable arrow subcontrols."""
        from ui import theme
        colors = theme._theme_colors()
        alt = colors.get("surface_alt", colors["panel_bg"])
        return f"""
        QSpinBox {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            font-weight: bold;
            border: 1px solid {colors['border']};
            border-radius: 3px;
            padding-right: 25px;
            min-width: 80px;
            min-height: 28px;
            max-height: 28px;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 24px;
            background-color: {alt};
            border-left: 1px solid {colors['border']};
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {colors['focus_border']};
        }}
        """

    @staticmethod
    def _font_size_spin_style():
        """Font-size spinbox with visible native up/down stepper buttons on Windows."""
        from ui import theme
        colors = theme._theme_colors()
        alt = colors.get("surface_alt", colors["panel_bg"])
        return f"""
        QSpinBox {{
            background-color: {colors['input_bg']};
            color: {colors['input_text']};
            font-weight: bold;
            font-size: 12px;
            border: 1px solid {colors['border']};
            border-radius: 3px;
            padding-right: 32px;
            padding-left: 6px;
            min-height: 30px;
            max-height: 30px;
        }}
        QSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 28px;
            height: 14px;
            background-color: {alt};
            border-left: 1px solid {colors['border']};
            border-bottom: 1px solid {colors['border']};
        }}
        QSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 28px;
            height: 14px;
            background-color: {alt};
            border-left: 1px solid {colors['border']};
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {colors['focus_border']};
        }}
        """

    @staticmethod
    def _checkbox_style():
        from ui import theme
        return theme.barcode_manager_checkbox_style()

    @staticmethod
    def _input_style():
        from ui import theme
        return theme.barcode_manager_input_style()

    @staticmethod
    def _compact_input_style():
        """Compact single-line field used beside the Price Key matrix."""
        from ui import theme
        return theme.barcode_manager_compact_input_style()

    @staticmethod
    def _matrix_style():
        from ui import theme
        return theme.barcode_manager_matrix_style()

    @staticmethod
    def _table_style():
        from ui import theme
        return theme.barcode_manager_queue_table_style()

    @staticmethod
    def _compact_button_style():
        from ui import theme
        return theme.barcode_manager_compact_button_style()

    @staticmethod
    def _dpad_push_style():
        from ui import theme
        return theme.barcode_manager_stepper_button_style()

    @staticmethod
    def _stepper_button_style():
        from ui import theme
        return theme.barcode_manager_stepper_button_style()

    @staticmethod
    def _quick_select_active_style():
        from ui import theme
        return theme.barcode_manager_active_button_style()

    @staticmethod
    def _tab_style():
        from ui import theme
        return theme.barcode_manager_tab_style()

    @staticmethod
    def _cancel_button_style():
        """Red cancel control for settings and calibration dialogs."""
        return BarcodeManagerWindow._button_style("danger")

    @staticmethod
    def _save_settings_button_style():
        return BarcodeManagerWindow._button_style("success")

    @staticmethod
    def _button_style(variant="primary"):
        from ui import theme
        return theme.barcode_tool_button_style(variant)

class StickerCalibrationDialog(UiMemoryMixin, QDialog):
    """Live graphical tool to calibrate sticker roll dimensions in millimetres."""
    PREVIEW_SCALE = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Sticker Roll Calibration')
        self.setMinimumSize(820, 420)
        self.setStyleSheet(theme.barcode_manager_shell_style())
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(8)
        title = QLabel('Millimetre Measurements')
        title.setStyleSheet(theme.barcode_manager_label_style())
        left.addWidget(title)
        cfg = load_calibration_config()
        self.roll_width_spin = self._make_mm_spin(cfg.get('roll_width', 76.2), 10, 300)
        self.roll_height_spin = self._make_mm_spin(cfg.get('roll_height', 25.4), 5, 100)
        self.label_width_spin = self._make_mm_spin(cfg.get('label_width', 38.0), 5, 200)
        self.label_height_spin = self._make_mm_spin(cfg.get('label_height', 25.0), 5, 100)
        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 6)
        self.columns_spin.setValue(int(cfg.get('columns', 2)))
        self.gap_spin = self._make_mm_spin(cfg.get('center_gap', 0.2), 0, 50)
        left.addLayout(self._field_row('Total Roll Width', self._build_stepper_wrapper(self.roll_width_spin)))
        left.addLayout(self._field_row('Total Roll Height', self._build_stepper_wrapper(self.roll_height_spin)))
        left.addLayout(self._field_row('Label Width', self._build_stepper_wrapper(self.label_width_spin)))
        left.addLayout(self._field_row('Label Height', self._build_stepper_wrapper(self.label_height_spin)))
        left.addLayout(self._field_row('Columns', self._build_stepper_wrapper(self.columns_spin)))
        left.addLayout(self._field_row('Center Gap / Horizontal Margin', self._build_stepper_wrapper(self.gap_spin)))
        for spin in (self.roll_width_spin, self.roll_height_spin, self.label_width_spin, self.label_height_spin, self.gap_spin):
            spin.valueChanged.connect(self.update_preview)
        self.columns_spin.valueChanged.connect(self.update_preview)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet(BarcodeManagerWindow._cancel_button_style())
        cancel_btn.setMinimumHeight(32)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton('Save Calibration')
        save_btn.setStyleSheet(BarcodeManagerWindow._button_style("success"))
        save_btn.setMinimumHeight(32)
        save_btn.clicked.connect(self.save_calibration)
        action_row.addWidget(cancel_btn)
        action_row.addWidget(save_btn)
        left.addStretch()
        left.addLayout(action_row)
        root.addLayout(left, 0)
        right = QVBoxLayout()
        preview_title = QLabel('Live Preview')
        preview_title.setStyleSheet(theme.barcode_manager_label_style())
        right.addWidget(preview_title)
        self.preview_scene = QGraphicsScene(self)
        self.preview_view = QGraphicsView(self.preview_scene)
        self.preview_view.setStyleSheet(theme.barcode_manager_strip_style())
        self.preview_view.setMinimumSize(420, 320)
        self.preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.preview_view.setInteractive(True)
        right.addWidget(self.preview_view, 1)
        root.addLayout(right, 1)
        self.update_preview()
        self._init_ui_memory()

    def resizeEvent(self, event):
        """Refit the calibration preview whenever the dialog is resized."""
        super().resizeEvent(event)
        self._schedule_fit_preview_to_view()

    def _fit_preview_to_view(self):
        """Scale the calibration scene into the available preview viewport."""
        if not hasattr(self, 'preview_scene') or not hasattr(self, 'preview_view'):
            return
        scene_rect = self.preview_scene.sceneRect()
        if scene_rect.isNull():
            return
        self.preview_view.resetTransform()
        self.preview_view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.preview_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.preview_view.setInteractive(True)

    def _schedule_fit_preview_to_view(self):
        """Refit the preview after Qt applies pending scene and viewport updates."""
        QTimer.singleShot(0, self._fit_preview_to_view)

    def _spin_style(self):
        """Spinbox body only; +/- stepper buttons sit outside the field."""
        return '\n            QDoubleSpinBox, QSpinBox {\n                background-color: #1e293b;\n                color: #f1f5f9;\n                font-weight: bold;\n                border: 1px solid #475569;\n                border-radius: 3px;\n                padding: 2px 4px;\n                min-height: 24px;\n            }\n        '

    @staticmethod
    def _stepper_button_style():
        """Visible minus/plus controls (replaces native up/down spinbox arrows)."""
        return BarcodeManagerWindow._stepper_button_style()

    def _build_stepper_wrapper(self, spin: QAbstractSpinBox) -> QWidget:
        """Wrap a spinbox with explicit minus and plus buttons."""
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setStyleSheet(self._spin_style())
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        btn_style = self._stepper_button_style()
        minus_btn = QPushButton('−')
        minus_btn.setFixedSize(28, 28)
        minus_btn.setStyleSheet(btn_style)
        minus_btn.setToolTip('Decrease')
        plus_btn = QPushButton('+')
        plus_btn.setFixedSize(28, 28)
        plus_btn.setStyleSheet(btn_style)
        plus_btn.setToolTip('Increase')

        def _decrease():
            try:
                spin.setValue(max(spin.minimum(), spin.value() - spin.singleStep()))
            except Exception:
                pass

        def _increase():
            try:
                spin.setValue(min(spin.maximum(), spin.value() + spin.singleStep()))
            except Exception:
                pass
        minus_btn.clicked.connect(_decrease)
        plus_btn.clicked.connect(_increase)
        row.addWidget(minus_btn)
        row.addWidget(spin, 1)
        row.addWidget(plus_btn)
        return box

    def _make_mm_spin(self, value, minimum, maximum):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(2)
        spin.setSingleStep(0.5)
        spin.setSuffix(' mm')
        spin.setValue(float(value))
        return spin

    def _field_row(self, label_text, widget):
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setStyleSheet(theme.barcode_manager_muted_hint_style())
        label.setMinimumWidth(200)
        row.addWidget(label)
        row.addWidget(widget, 1)
        return row

    def _current_values(self) -> dict:
        return {'roll_width': self.roll_width_spin.value(), 'roll_height': self.roll_height_spin.value(), 'label_width': self.label_width_spin.value(), 'label_height': self.label_height_spin.value(), 'columns': self.columns_spin.value(), 'center_gap': self.gap_spin.value()}

    def update_preview(self):
        """Redraw the paper roll and label positions from current spinbox values."""
        self.preview_scene.clear()
        scale = self.PREVIEW_SCALE
        cfg = self._current_values()
        roll_w = cfg['roll_width'] * scale
        roll_h = cfg['roll_height'] * scale
        label_w = cfg['label_width'] * scale
        label_h = cfg['label_height'] * scale
        columns = int(cfg['columns'])
        gap = cfg['center_gap']
        paper = QGraphicsRectItem(0, 0, roll_w, roll_h)
        paper.setBrush(QBrush(QColor('#FFFFFF')))
        paper.setPen(QPen(QColor('#64748b'), 1))
        self.preview_scene.addItem(paper)
        total_w = columns * cfg['label_width'] + max(0, columns - 1) * gap
        start_x = (cfg['roll_width'] - total_w) / 2.0
        label_y = (cfg['roll_height'] - cfg['label_height']) / 2.0
        for col in range(columns):
            x_mm = start_x + col * (cfg['label_width'] + gap)
            label_rect = QGraphicsRectItem(x_mm * scale, label_y * scale, label_w, label_h)
            label_rect.setBrush(QBrush(QColor(96, 165, 250, 140)))
            label_rect.setPen(QPen(QColor('#2563eb'), 1))
            self.preview_scene.addItem(label_rect)
        self.preview_scene.setSceneRect(0, 0, roll_w + 20, roll_h + 20)
        self._schedule_fit_preview_to_view()

    def save_calibration(self):
        """Write spinbox values to sticker_config.json and close."""
        config = self._current_values()
        if save_calibration_config(config):
            QMessageBox.information(self, 'Calibration Saved', 'Sticker dimensions saved to sticker_config.json.')
            self.accept()
        else:
            QMessageBox.warning(self, 'Save Failed', 'Could not write sticker_config.json.')