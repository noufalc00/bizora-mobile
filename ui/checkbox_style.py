"""3D checkbox widget and label-only stylesheet helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QRadioButton


def _is_light_theme() -> bool:
    try:
        from ui.theme_manager import get_theme_manager

        return get_theme_manager().get_current_theme() == "light"
    except Exception:
        return False


def _theme_colors() -> dict[str, str]:
    try:
        from ui.theme_manager import get_theme_manager

        return get_theme_manager().get_colors()
    except Exception:
        return {}


def _default_label_color() -> str:
    colors = _theme_colors()
    if _is_light_theme():
        return colors.get("label_text", "#263238")
    return colors.get("muted_text", "#94a3b8")


def _status_label_color() -> str:
    colors = _theme_colors()
    if _is_light_theme():
        return colors.get("accent_label", "#1565C0")
    return "#fbbf24"


def _compact_label_color() -> str:
    return _status_label_color()


_VARIANTS = {
    "status": {"color_key": "status", "font_size": 11, "indicator": 16, "spacing": 6},
    "default": {"color_key": "default", "font_size": 11, "indicator": 16, "spacing": 6},
    "compact": {"color_key": "compact", "font_size": 8, "indicator": 14, "spacing": 4},
}


def _variant_label_color(variant: str) -> str:
    cfg = _VARIANTS.get(variant, _VARIANTS["default"])
    if cfg["color_key"] == "status":
        return _status_label_color()
    if cfg["color_key"] == "compact":
        return _compact_label_color()
    return _default_label_color()


class CheckBox3D(QCheckBox):
    """Checkbox with a painted 3D box and gradient tick (no QSS indicator images)."""

    def __init__(
        self,
        text: str = "",
        parent=None,
        *,
        variant: str = "default",
        label_color: str | None = None,
        font_size: int | None = None,
        indicator_size: int | None = None,
        spacing: int | None = None,
    ):
        super().__init__(text, parent)
        cfg = _VARIANTS.get(variant, _VARIANTS["default"])
        self._label_color = label_color or _variant_label_color(variant)
        self._font_size = font_size if font_size is not None else cfg["font_size"]
        self._indicator_size = indicator_size if indicator_size is not None else cfg["indicator"]
        self._spacing = spacing if spacing is not None else cfg["spacing"]

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        font = QFont(self.font())
        font.setPixelSize(self._font_size)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(
            "QCheckBox { background: transparent; spacing: 0px; }"
            "QCheckBox::indicator { width: 0px; height: 0px; border: none; }"
        )
        self.setMinimumHeight(max(self._indicator_size + 2, self._font_size + 6))

    def set_label_color(self, color: str) -> None:
        self._label_color = color
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ind = self._indicator_size
        box_y = max(0, (self.height() - ind) // 2)
        box = QRectF(0, box_y, ind, ind)

        self._paint_box(painter, box)
        if self.isChecked():
            self._paint_tick(painter, box)

        label = self.text()
        if label:
            text_x = ind + self._spacing
            text_rect = QRect(text_x, 0, max(0, self.width() - text_x), self.height())
            color = QColor(self._label_color)
            if not self.isEnabled():
                color.setAlpha(140)
            painter.setPen(color)
            painter.setFont(self.font())
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                label,
            )

    def _paint_box(self, painter: QPainter, box: QRectF) -> None:
        checked = self.isChecked()
        path = QPainterPath()
        path.addRoundedRect(box, 3, 3)

        grad = QLinearGradient(box.topLeft(), box.bottomLeft())
        if _is_light_theme():
            if checked:
                grad.setColorAt(0.0, QColor("#D2F2F2"))
                grad.setColorAt(0.5, QColor("#0E7490"))
                grad.setColorAt(1.0, QColor("#0B5F6B"))
                border = QColor("#0B5F6B")
            else:
                grad.setColorAt(0.0, QColor("#FFFFFF"))
                grad.setColorAt(0.45, QColor("#E8FAFA"))
                grad.setColorAt(1.0, QColor("#C0E8E8"))
                border = QColor("#7FB8B8")
        elif checked:
            grad.setColorAt(0.0, QColor("#243041"))
            grad.setColorAt(0.5, QColor("#1e293b"))
            grad.setColorAt(1.0, QColor("#334155"))
            border = QColor("#64748b")
        else:
            grad.setColorAt(0.0, QColor("#5b6b82"))
            grad.setColorAt(0.45, QColor("#3d4d63"))
            grad.setColorAt(1.0, QColor("#1e293b"))
            border = QColor("#94a3b8")

        if not self.isEnabled():
            painter.setOpacity(0.55)

        painter.fillPath(path, grad)
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)

        if not checked:
            highlight = QColor("#FFFFFF") if _is_light_theme() else QColor("#cbd5e1")
            painter.setPen(QPen(highlight, 1))
            painter.drawLine(
                int(box.left() + 1.5),
                int(box.top() + 1.5),
                int(box.right() - 2),
                int(box.top() + 1.5),
            )
            painter.drawLine(
                int(box.left() + 1.5),
                int(box.top() + 1.5),
                int(box.left() + 1.5),
                int(box.bottom() - 2),
            )
        else:
            shadow = QColor(21, 101, 192, 120) if _is_light_theme() else QColor(15, 23, 42, 170)
            painter.setPen(QPen(shadow, 1))
            painter.drawLine(
                int(box.left() + 1.5),
                int(box.top() + 1.5),
                int(box.right() - 2),
                int(box.top() + 1.5),
            )
            painter.drawLine(
                int(box.left() + 1.5),
                int(box.top() + 1.5),
                int(box.left() + 1.5),
                int(box.bottom() - 2),
            )

        painter.setOpacity(1.0)

    def _paint_tick(self, painter: QPainter, box: QRectF) -> None:
        x, y, w, h = box.x(), box.y(), box.width(), box.height()
        tick = QPainterPath()
        tick.moveTo(x + w * 0.22, y + h * 0.56)
        tick.lineTo(x + w * 0.43, y + h * 0.76)
        tick.lineTo(x + w * 0.80, y + h * 0.30)

        shadow = QPainterPath(tick)
        shadow.translate(0.6, 0.6)
        shadow_color = QColor(38, 50, 56, 90) if _is_light_theme() else QColor(15, 23, 42, 120)
        painter.setPen(
            QPen(
                shadow_color,
                2.8,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawPath(shadow)

        tick_color = "#0E7490" if _is_light_theme() else "#60a5fa"
        painter.setPen(
            QPen(
                QColor(tick_color),
                2.5,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawPath(tick)

        painter.setPen(
            QPen(
                QColor(255, 255, 255, 150),
                1.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawPath(tick)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        spacing = self._spacing if text_w else 0
        width = self._indicator_size + spacing + text_w + 4
        height = max(self._indicator_size, fm.height()) + 4
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        if self.text():
            return self.sizeHint()
        return QSize(self._indicator_size, self._indicator_size)


class RadioButton3D(QRadioButton):
    """Radio button with painted 3D circle indicator matching CheckBox3D styling."""

    def __init__(
        self,
        text: str = "",
        parent=None,
        *,
        variant: str = "default",
        label_color: str | None = None,
        font_size: int | None = None,
        indicator_size: int | None = None,
        spacing: int | None = None,
        highlight_checked_label: bool = True,
    ):
        super().__init__(text, parent)
        cfg = _VARIANTS.get(variant, _VARIANTS["default"])
        self._label_color = label_color or _variant_label_color(variant)
        self._font_size = font_size if font_size is not None else cfg["font_size"]
        self._indicator_size = indicator_size if indicator_size is not None else cfg["indicator"]
        self._spacing = spacing if spacing is not None else cfg["spacing"]
        self._highlight_checked_label = highlight_checked_label

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        font = QFont(self.font())
        font.setPixelSize(self._font_size)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet(
            "QRadioButton { background: transparent; spacing: 0px; }"
            "QRadioButton::indicator { width: 0px; height: 0px; border: none; }"
        )
        self.setMinimumHeight(max(self._indicator_size + 2, self._font_size + 6))

    def set_label_color(self, color: str) -> None:
        """Update the unchecked label color and repaint."""
        self._label_color = color
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        ind = self._indicator_size
        box_y = max(0, (self.height() - ind) // 2)
        box = QRectF(0, box_y, ind, ind)

        self._paint_circle(painter, box)
        if self.isChecked():
            self._paint_dot(painter, box)

        label = self.text()
        if label:
            text_x = ind + self._spacing
            text_rect = QRect(text_x, 0, max(0, self.width() - text_x), self.height())
            if self._highlight_checked_label and self.isChecked():
                color = QColor(_status_label_color() if _is_light_theme() else "#facc15")
            else:
                color = QColor(self._label_color)
            if not self.isEnabled():
                color.setAlpha(140)
            painter.setPen(color)
            painter.setFont(self.font())
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                label,
            )

    def _paint_circle(self, painter: QPainter, box: QRectF) -> None:
        checked = self.isChecked()
        path = QPainterPath()
        path.addEllipse(box)

        grad = QLinearGradient(box.topLeft(), box.bottomLeft())
        if _is_light_theme():
            if checked:
                grad.setColorAt(0.0, QColor("#D2F2F2"))
                grad.setColorAt(0.5, QColor("#0E7490"))
                grad.setColorAt(1.0, QColor("#0B5F6B"))
                border = QColor("#0B5F6B")
            else:
                grad.setColorAt(0.0, QColor("#FFFFFF"))
                grad.setColorAt(0.45, QColor("#E8FAFA"))
                grad.setColorAt(1.0, QColor("#C0E8E8"))
                border = QColor("#7FB8B8")
        elif checked:
            grad.setColorAt(0.0, QColor("#243041"))
            grad.setColorAt(0.5, QColor("#1e293b"))
            grad.setColorAt(1.0, QColor("#334155"))
            border = QColor("#64748b")
        else:
            grad.setColorAt(0.0, QColor("#5b6b82"))
            grad.setColorAt(0.45, QColor("#3d4d63"))
            grad.setColorAt(1.0, QColor("#1e293b"))
            border = QColor("#94a3b8")

        if not self.isEnabled():
            painter.setOpacity(0.55)

        painter.fillPath(path, grad)
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)
        painter.setOpacity(1.0)

    def _paint_dot(self, painter: QPainter, box: QRectF) -> None:
        inset = box.width() * 0.28
        dot = QRectF(
            box.x() + inset,
            box.y() + inset,
            box.width() - (2 * inset),
            box.height() - (2 * inset),
        )
        dot_path = QPainterPath()
        dot_path.addEllipse(dot)

        grad = QLinearGradient(dot.topLeft(), dot.bottomLeft())
        if _is_light_theme():
            grad.setColorAt(0.0, QColor("#64B5F6"))
            grad.setColorAt(0.5, QColor("#1E88E5"))
            grad.setColorAt(1.0, QColor("#1565C0"))
            border = QColor("#0D47A1")
        else:
            grad.setColorAt(0.0, QColor("#93c5fd"))
            grad.setColorAt(0.5, QColor("#60a5fa"))
            grad.setColorAt(1.0, QColor("#2563eb"))
            border = QColor("#1d4ed8")
        painter.fillPath(dot_path, grad)
        painter.setPen(QPen(border, 1))
        painter.drawPath(dot_path)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        spacing = self._spacing if text_w else 0
        width = self._indicator_size + spacing + text_w + 4
        height = max(self._indicator_size, fm.height()) + 4
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        if self.text():
            return self.sizeHint()
        return QSize(self._indicator_size, self._indicator_size)


def create_checkbox(
    text: str = "",
    parent=None,
    *,
    variant: str = "default",
    **kwargs,
) -> CheckBox3D:
    """Create a painted 3D checkbox (standard app tick style — same as Sales Entry)."""
    return CheckBox3D(text, parent, variant=variant, **kwargs)


create_app_checkbox = create_checkbox


def create_radio_button(
    text: str = "",
    parent=None,
    *,
    variant: str = "default",
    **kwargs,
) -> RadioButton3D:
    """Create a painted 3D radio button (same visual language as Sales Entry checkboxes)."""
    return RadioButton3D(text, parent, variant=variant, **kwargs)


create_app_radio_button = create_radio_button


def _dark_checkbox_indicator_style(width: int = 16, height: int = 16) -> str:
    size = max(width, height)
    return f"""
    QCheckBox::indicator {{
        width: {size}px;
        height: {size}px;
        border-radius: 3px;
    }}
    QCheckBox::indicator:unchecked {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #5b6b82, stop:0.45 #3d4d63, stop:1 #1e293b
        );
        border-top: 1px solid #94a3b8;
        border-left: 1px solid #94a3b8;
        border-right: 1px solid #0f172a;
        border-bottom: 1px solid #0f172a;
    }}
    QCheckBox::indicator:checked {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #243041, stop:0.5 #1e293b, stop:1 #334155
        );
        border-top: 1px solid #0f172a;
        border-left: 1px solid #0f172a;
        border-right: 1px solid #64748b;
        border-bottom: 1px solid #94a3b8;
    }}
    """


def _light_checkbox_indicator_style(width: int = 16, height: int = 16) -> str:
    size = max(width, height)
    return f"""
    QCheckBox::indicator {{
        width: {size}px;
        height: {size}px;
        border-radius: 3px;
    }}
    QCheckBox::indicator:unchecked {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #FFFFFF, stop:0.45 #E8FAFA, stop:1 #C0E8E8
        );
        border-top: 1px solid #FFFFFF;
        border-left: 1px solid #FFFFFF;
        border-right: 1px solid #7FB8B8;
        border-bottom: 1px solid #7FB8B8;
    }}
    QCheckBox::indicator:checked {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 #D2F2F2, stop:0.5 #0E7490, stop:1 #0B5F6B
        );
        border-top: 1px solid #FFFFFF;
        border-left: 1px solid #FFFFFF;
        border-right: 1px solid #0B5F6B;
        border-bottom: 1px solid #085F66;
    }}
    """


def checkbox_indicator_style(width: int = 16, height: int = 16) -> str:
    """Label-adjacent fallback for plain QCheckBox (border-only, no images)."""
    if _is_light_theme():
        return _light_checkbox_indicator_style(width, height)
    return _dark_checkbox_indicator_style(width, height)


def labeled_checkbox_style(
    label_color: str | None = None,
    *,
    font_size: int = 11,
    spacing: int = 6,
    indicator_width: int = 16,
    indicator_height: int = 16,
) -> str:
    color = label_color or _default_label_color()
    return f"""
    QCheckBox {{
        color: {color};
        font-size: {font_size}px;
        font-weight: bold;
        background: transparent;
        spacing: {spacing}px;
    }}
    {checkbox_indicator_style(indicator_width, indicator_height)}
    """


def sales_status_checkbox_style() -> str:
    return labeled_checkbox_style(_status_label_color(), font_size=11, spacing=6)


def sales_checkbox_style() -> str:
    return labeled_checkbox_style(_default_label_color(), font_size=11, spacing=6)


def sales_compact_checkbox_style() -> str:
    return labeled_checkbox_style(
        _compact_label_color(),
        font_size=8,
        spacing=4,
        indicator_width=14,
        indicator_height=14,
    )


def app_checkbox_style() -> str:
    return sales_checkbox_style()