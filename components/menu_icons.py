"""
Shared menu-icon loader used by the sidebar and shortcut toolbar.

Icons may live under ``assets/icons`` (SVG/JPG/PNG) or an external pack folder.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

_APP_ROOT = Path(__file__).resolve().parent.parent
_ICON_CACHE: dict[str, QIcon] = {}

# Optional external icon pack (user-provided 3D JPG icons).
_EXTERNAL_ICON_ROOT = Path(r"D:\App making\extract\icons")


def _resolve_icon_path(relative_path: str) -> Path | None:
    """Resolve a project-relative or absolute icon path."""
    if not relative_path:
        return None

    candidate = Path(relative_path)
    if candidate.is_file():
        return candidate

    app_path = _APP_ROOT / relative_path
    if app_path.is_file():
        return app_path

    # Allow loading directly from the external icon pack when bundled JPGs are absent.
    stem = Path(relative_path).stem.replace(" ", "_").lower()
    for suffix in (".jpg", ".jpeg", ".png", ".svg"):
        external = _EXTERNAL_ICON_ROOT / f"{stem}{suffix}"
        if external.is_file():
            return external

    return None


def load_menu_icon(relative_path: str, *, bust_cache: bool = False) -> QIcon | None:
    """Load and cache a menu icon from assets or the external icon pack."""
    if not relative_path:
        return None
    if bust_cache and relative_path in _ICON_CACHE:
        del _ICON_CACHE[relative_path]
    if relative_path in _ICON_CACHE:
        return _ICON_CACHE[relative_path]

    icon_path = _resolve_icon_path(relative_path)
    if icon_path is None or not icon_path.is_file():
        return None

    icon = QIcon(str(icon_path))
    if icon.isNull():
        return None

    _ICON_CACHE[relative_path] = icon
    return icon


def load_scaled_menu_icon(
    relative_path: str,
    size: QSize,
    *,
    bust_cache: bool = False,
) -> QIcon | None:
    """Return an icon rasterised to ``size`` so it fills icon boxes cleanly."""
    pixmap = pixmap_for_menu_icon(
        relative_path,
        size,
        bust_cache=bust_cache,
    )
    if pixmap is None:
        return None
    return QIcon(pixmap)


def pixmap_for_menu_icon(
    relative_path: str,
    logical_size: QSize,
    *,
    device_pixel_ratio: float = 1.0,
    bust_cache: bool = False,
) -> QPixmap | None:
    """Rasterise a menu SVG/icon at device-pixel ratio for crisp 3D tiles."""
    base_icon = load_menu_icon(relative_path, bust_cache=bust_cache)
    if base_icon is None or logical_size.isEmpty():
        return None

    ratio = max(device_pixel_ratio, 1.0)
    pixel_size = QSize(
        int(logical_size.width() * ratio),
        int(logical_size.height() * ratio),
    )
    pixmap = base_icon.pixmap(
        pixel_size,
        QIcon.Mode.Normal,
        QIcon.State.Off,
    )
    if pixmap.isNull():
        return None

    pixmap.setDevicePixelRatio(ratio)
    return pixmap
