"""Regression checks for independent barcode label layout controls."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ui.barcode_manager import (  # noqa: E402
    BarcodeManagerWindow,
    CANONICAL_LAYOUT_ELEMENTS,
    barcode_module_bar_rects,
    barcode_number_preview_top,
    default_element_offsets,
    draw_reportlab_barcode_modules,
    element_offset_keys,
    encode_code39_modules,
    normalize_element_offsets,
    supplier_preview_anchor,
)


EXPECTED_LAYOUT_KEYS = {
    "company": ("company_x", "company_y"),
    "product": ("product_x", "product_y"),
    "barcode": ("barcode_graphic_x", "barcode_graphic_y"),
    "barcode_num": ("barcode_number_x", "barcode_number_y"),
    "supplier_code": ("supplier_code_x", "supplier_code_y"),
    "price": ("price_x", "price_y"),
}


def _movement_window(element):
    """Build a minimal BarcodeManagerWindow instance for offset method checks."""
    window = BarcodeManagerWindow.__new__(BarcodeManagerWindow)
    window._active_element_key = element
    window._live_offsets = normalize_element_offsets(default_element_offsets())
    window._update_position_label = lambda: None
    return window


def _changed_keys(before, after):
    """Return offset keys whose values changed between two dictionaries."""
    all_keys = set(before) | set(after)
    return {key for key in all_keys if before.get(key) != after.get(key)}


class _FakeReportLabCanvas:
    """Capture ReportLab barcode rectangles without writing a PDF."""

    def __init__(self):
        self.rectangles = []

    def setFillColorRGB(self, *_args):
        """Accept the ReportLab fill-color call used by the renderer."""
        return None

    def rect(self, x_pos, y_pos, width, height, stroke=0, fill=1):
        """Store rectangle draws for bounds assertions."""
        self.rectangles.append((x_pos, y_pos, width, height, stroke, fill))


def test_canonical_layout_elements_have_distinct_xy_keys():
    """Verify the six user-facing components own explicit independent X/Y keys."""
    assert tuple(CANONICAL_LAYOUT_ELEMENTS) == (
        "company",
        "product",
        "barcode",
        "barcode_num",
        "supplier_code",
        "price",
    )
    used_keys = []
    for element, keys in EXPECTED_LAYOUT_KEYS.items():
        assert element_offset_keys(element) == keys
        used_keys.extend(keys)
    assert len(used_keys) == len(set(used_keys))


def test_each_canonical_element_move_changes_only_its_own_xy_keys():
    """Move every canonical element and assert no neighbor offsets are touched."""
    for element, keys in EXPECTED_LAYOUT_KEYS.items():
        window = _movement_window(element)
        before = dict(window._live_offsets)

        BarcodeManagerWindow._adjust_active_offset(window, 7, -3)

        assert _changed_keys(before, window._live_offsets) == set(keys)
        assert window._live_offsets[keys[0]] == before[keys[0]] + 7
        assert window._live_offsets[keys[1]] == before[keys[1]] - 3


def test_barcode_size_changes_do_not_move_any_text_positions():
    """Barcode graphic width/height changes must not move text anchors."""
    offsets = normalize_element_offsets(default_element_offsets())
    number_top = barcode_number_preview_top(96.0, offsets)
    supplier_anchor = supplier_preview_anchor(192.0, 96.0, offsets)

    offsets["barcode_graphic_w"] = 140
    offsets["barcode_graphic_h"] = 80

    assert barcode_number_preview_top(96.0, offsets) == number_top
    assert supplier_preview_anchor(192.0, 96.0, offsets) == supplier_anchor


def test_barcode_graphic_y_and_height_do_not_drive_text_positions():
    """Barcode graphic top/height changes must not derive text placement."""
    offsets = normalize_element_offsets(default_element_offsets())
    number_top = barcode_number_preview_top(96.0, offsets)
    supplier_anchor = supplier_preview_anchor(192.0, 96.0, offsets)

    offsets["barcode_graphic_y"] = 55
    offsets["barcode_graphic_h"] = 120

    assert barcode_number_preview_top(96.0, offsets) == number_top
    assert supplier_preview_anchor(192.0, 96.0, offsets) == supplier_anchor


def test_barcode_module_bars_stay_inside_configured_rect():
    """Shared barcode helper must clamp every bar to the configured graphic box."""
    pattern = encode_code39_modules("1234567890")
    for width in (12.5, 38.0, 101.75):
        for height in (8.0, 25.0):
            left = 3.25
            top = 4.5
            rectangles = barcode_module_bar_rects(pattern, left, top, width, height)

            assert rectangles
            assert all(rect[0] >= left for rect in rectangles)
            assert all(rect[1] == top for rect in rectangles)
            assert all(rect[2] > 0 for rect in rectangles)
            assert all(rect[3] == height for rect in rectangles)
            assert all(rect[0] + rect[2] <= left + width for rect in rectangles)


def test_reportlab_barcode_modules_do_not_overflow_width():
    """ReportLab barcode draw calls must never exceed the supplied barcode width."""
    pattern = encode_code39_modules("9876543210")
    canvas = _FakeReportLabCanvas()
    left = 11.3
    bottom = 7.0
    width = 38.0
    height = 25.0

    draw_reportlab_barcode_modules(canvas, pattern, left, bottom, height, width)

    assert canvas.rectangles
    for x_pos, y_pos, rect_width, rect_height, stroke, fill in canvas.rectangles:
        assert x_pos >= left
        assert y_pos == bottom
        assert rect_width > 0
        assert rect_height == height
        assert x_pos + rect_width <= left + width
        assert stroke == 0
        assert fill == 1
