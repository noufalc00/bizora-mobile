"""
Shared application brand logo loader and QLabel helpers.
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

_APP_ROOT = Path(__file__).resolve().parent.parent
_EXTERNAL_ICON_ROOT = Path(r"D:\App making\extract\icons")
_MAX_TRIM_DIMENSION = 1024
_PIXMAP_CACHE: dict[tuple[str, int, int, int], QPixmap] = {}

# Chrome consumed by sidebar_logo_box_style border + create_brand_logo_box padding.
LOGO_BOX_BORDER_PX = 3
LOGO_BOX_PADDING_PX = 10

# Sidebar title row inner slot (sidebar width 280 minus 8px layout margins each side).
SIDEBAR_LOGO_SLOT_WIDTH = 264
SIDEBAR_LOGO_SLOT_HEIGHT = 190

APP_LOGO_CANDIDATES = (
    _EXTERNAL_ICON_ROOT / "app logo.png",
    _EXTERNAL_ICON_ROOT / "app_logo.png",
    _APP_ROOT / "assets" / "icons" / "app_logo.png",
    _APP_ROOT / "assets" / "icons" / "app logo.png",
)

SIDEBAR_LOGO_CANDIDATES = (
    _APP_ROOT / "assets" / "icons" / "sidebar_logo.png",
    _EXTERNAL_ICON_ROOT / "app logo 4.png",
    _EXTERNAL_ICON_ROOT / "app_logo_4.png",
)


def _is_valid_png_file(path: Path) -> bool:
    """Return True when a file is structurally a valid PNG stream."""
    try:
        data = path.read_bytes()
    except OSError:
        return False

    signature = b"\x89PNG\r\n\x1a\n"
    if len(data) < 12 or not data.startswith(signature):
        return False

    offset = len(signature)
    data_len = len(data)
    saw_iend = False
    while offset + 12 <= data_len:
        chunk_len = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        offset += 8

        if not chunk_type.isalpha():
            return False
        if offset + chunk_len + 4 > data_len:
            return False

        offset += chunk_len + 4
        if chunk_type == b"IEND":
            saw_iend = True
            break

    return saw_iend


def _downscale_large_pixmap(pixmap: QPixmap) -> QPixmap:
    """Shrink oversized source art before expensive alpha scans."""
    if pixmap.isNull():
        return pixmap

    max_dim = max(pixmap.width(), pixmap.height())
    if max_dim <= _MAX_TRIM_DIMENSION:
        return pixmap

    if pixmap.width() >= pixmap.height():
        return pixmap.scaledToWidth(
            _MAX_TRIM_DIMENSION,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap.scaledToHeight(
        _MAX_TRIM_DIMENSION,
        Qt.TransformationMode.SmoothTransformation,
    )


def _alpha_bounds(image: QImage) -> tuple[int, int, int, int] | None:
    """Return non-transparent bounds as (left, top, right, bottom)."""
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width = image.width()
    height = image.height()
    left, right = width, -1
    top, bottom = height, -1

    for y in range(height):
        line = image.constScanLine(y)
        for x in range(width):
            alpha = line[x * 4 + 3]
            if alpha > 0:
                if x < left:
                    left = x
                if x > right:
                    right = x
                if y < top:
                    top = y
                if y > bottom:
                    bottom = y

    if right < left or bottom < top:
        return None
    return (left, top, right, bottom)


def _trim_transparent_padding(pixmap: QPixmap) -> QPixmap:
    """Crop transparent margins while preserving full-resolution detail."""
    if pixmap.isNull():
        return pixmap

    preview = _downscale_large_pixmap(pixmap)
    bounds = _alpha_bounds(preview.toImage())
    if bounds is None:
        return pixmap

    if preview.width() == pixmap.width() and preview.height() == pixmap.height():
        left, top, right, bottom = bounds
        return pixmap.copy(left, top, right - left + 1, bottom - top + 1)

    sx = pixmap.width() / max(preview.width(), 1)
    sy = pixmap.height() / max(preview.height(), 1)
    left, top, right, bottom = bounds
    full_left = max(0, int(left * sx))
    full_top = max(0, int(top * sy))
    full_right = min(pixmap.width() - 1, int((right + 1) * sx) - 1)
    full_bottom = min(pixmap.height() - 1, int((bottom + 1) * sy) - 1)
    return pixmap.copy(
        full_left,
        full_top,
        full_right - full_left + 1,
        full_bottom - full_top + 1,
    )


def resolve_app_logo_path() -> Path | None:
    """Return the first available application logo file path."""
    for candidate in APP_LOGO_CANDIDATES:
        if candidate.is_file() and _is_valid_png_file(candidate):
            return candidate
    return None


def resolve_sidebar_logo_path() -> Path | None:
    """Return the sidebar-only logo file path (app logo 4 variant)."""
    for candidate in SIDEBAR_LOGO_CANDIDATES:
        if candidate.is_file() and _is_valid_png_file(candidate):
            return candidate
    return None


def _load_logo_pixmap_from_path(
    logo_path: Path,
    max_width: int,
    max_height: int,
) -> QPixmap:
    """Load, trim, and scale a logo file to the requested bounds."""
    if max_width <= 0 or max_height <= 0:
        return QPixmap()

    try:
        cache_key = (str(logo_path), int(logo_path.stat().st_mtime_ns), max_width, max_height)
        cached = _PIXMAP_CACHE.get(cache_key)
        if cached is not None and not cached.isNull():
            return cached
    except OSError:
        cache_key = None

    pixmap = QPixmap(str(logo_path))
    if pixmap.isNull():
        return QPixmap()

    pixmap = _trim_transparent_padding(pixmap)
    scaled = pixmap.scaled(
        max_width,
        max_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    if cache_key is not None:
        _PIXMAP_CACHE[cache_key] = scaled
    return scaled


def load_app_logo_pixmap(max_width: int, max_height: int) -> QPixmap:
    """Load the brand logo scaled to fit within the supplied bounds."""
    logo_path = resolve_app_logo_path()
    if logo_path is None:
        return QPixmap()
    return _load_logo_pixmap_from_path(logo_path, max_width, max_height)


def load_sidebar_logo_pixmap(max_width: int, max_height: int) -> QPixmap:
    """Load the sidebar-specific logo (app logo 4) scaled to fit."""
    logo_path = resolve_sidebar_logo_path()
    if logo_path is None:
        return load_app_logo_pixmap(max_width, max_height)
    return _load_logo_pixmap_from_path(logo_path, max_width, max_height)


def load_app_logo_icon() -> QIcon:
    """Return the application logo as a window icon."""
    pixmap = load_app_logo_pixmap(64, 64)
    if pixmap.isNull():
        return QIcon()
    return QIcon(pixmap)


def apply_sidebar_logo_to_label(label: QLabel, max_width: int, max_height: int) -> bool:
    """Apply the sidebar-specific logo pixmap to a label."""
    pixmap = load_sidebar_logo_pixmap(max_width, max_height)
    if pixmap.isNull():
        label.clear()
        return False
    label.setPixmap(pixmap)
    return True


def create_sidebar_brand_logo_label(
    max_width: int,
    max_height: int,
    *,
    object_name: str = "sidebarBrandLogo",
) -> QLabel:
    """Create a centered QLabel for the sidebar top logo (app logo 4)."""
    label = QLabel()
    label.setObjectName(object_name)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    label.setFixedHeight(max_height)
    label.setStyleSheet("background: transparent; border: none;")
    apply_sidebar_logo_to_label(label, max_width, max_height)
    return label


def apply_brand_logo_to_label(label: QLabel, max_width: int, max_height: int) -> bool:
    """Apply a scaled brand logo pixmap to an existing label."""
    pixmap = load_app_logo_pixmap(max_width, max_height)
    if pixmap.isNull():
        label.clear()
        return False
    label.setPixmap(pixmap)
    return True


def create_brand_logo_label(
    max_width: int,
    max_height: int,
    *,
    object_name: str = "brandLogoLabel",
) -> QLabel:
    """Create a centered QLabel that displays the application logo."""
    label = QLabel()
    label.setObjectName(object_name)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    label.setFixedHeight(max_height)
    label.setStyleSheet("background: transparent; border: none;")
    apply_brand_logo_to_label(label, max_width, max_height)
    return label


def logo_frame_chrome_size() -> tuple[int, int]:
    """Return total width and height added by the logo frame border and padding."""
    per_side = LOGO_BOX_BORDER_PX + LOGO_BOX_PADDING_PX
    return per_side * 2, per_side * 2


def fit_brand_logo_content_size(slot_width: int, slot_height: int) -> tuple[int, int]:
    """Shrink pixmap bounds so the framed logo fits inside a layout slot."""
    chrome_w, chrome_h = logo_frame_chrome_size()
    return max(1, slot_width - chrome_w), max(1, slot_height - chrome_h)


def sidebar_logo_content_size() -> tuple[int, int]:
    """Return pixmap bounds that keep the sidebar logo fully inside the title bar."""
    return fit_brand_logo_content_size(
        SIDEBAR_LOGO_SLOT_WIDTH,
        SIDEBAR_LOGO_SLOT_HEIGHT,
    )


def refresh_brand_logo_box(
    logo_box: QFrame | None,
    label: QLabel | None,
    max_width: int,
    max_height: int,
    *,
    sidebar_variant: bool = False,
) -> None:
    """Reapply theme-aware logo frame styles and pixmap after a theme switch."""
    if logo_box is not None:
        from ui.theme import sidebar_logo_box_style

        logo_box.setStyleSheet(sidebar_logo_box_style())
    if label is None:
        return
    if sidebar_variant:
        apply_sidebar_logo_to_label(label, max_width, max_height)
    else:
        apply_brand_logo_to_label(label, max_width, max_height)
    label.setStyleSheet("background: transparent; border: none;")


def create_brand_logo_box(
    max_width: int,
    max_height: int,
    *,
    label_object_name: str = "brandLogoLabel",
    sidebar_variant: bool = False,
) -> tuple[QFrame, QLabel]:
    """Create the theme-aware logo frame used on the sidebar and login screens."""
    from ui.theme import sidebar_logo_box_style

    logo_box = QFrame()
    logo_box.setObjectName("sidebarLogoBox")
    logo_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    logo_box.setStyleSheet(sidebar_logo_box_style())

    box_layout = QHBoxLayout(logo_box)
    box_layout.setContentsMargins(
        LOGO_BOX_PADDING_PX,
        LOGO_BOX_PADDING_PX,
        LOGO_BOX_PADDING_PX,
        LOGO_BOX_PADDING_PX,
    )
    box_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    chrome_w, chrome_h = logo_frame_chrome_size()
    logo_box.setMaximumSize(max_width + chrome_w, max_height + chrome_h)

    if sidebar_variant:
        label = create_sidebar_brand_logo_label(
            max_width,
            max_height,
            object_name=label_object_name,
        )
    else:
        label = create_brand_logo_label(
            max_width,
            max_height,
            object_name=label_object_name,
        )
    box_layout.addWidget(label)
    return logo_box, label
