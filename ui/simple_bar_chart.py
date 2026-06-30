"""
Lightweight monthly bar chart widget for the dashboard.

Uses QPainter only (no QtCharts dependency) so charts stay simple and theme-aware.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QLabel


class SimpleMonthlyBarChart(QFrame):
    """Paint a compact monthly totals bar chart."""

    def __init__(self, title: str, bar_color: str = "#2196F3", parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardSimpleBarChart")
        self._title = title
        self._bar_color = bar_color
        self._labels: list[str] = []
        self._values: list[float] = []
        self._text_color = "#ffffff"
        self._muted_color = "#94a3b8"
        self._grid_color = "#404040"
        self._card_bg = "#1E1E1E"

        self.setMinimumHeight(180)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("dashboardChartTitle")
        layout.addWidget(self._title_label)
        layout.addStretch(1)

    def set_theme_colors(
        self,
        *,
        text_color: str,
        muted_color: str,
        grid_color: str,
        card_bg: str,
        bar_color: str | None = None,
        title_color: str | None = None,
        accent_border: str | None = None,
    ) -> None:
        """Apply palette tokens from the active application theme."""
        self._text_color = text_color
        self._muted_color = muted_color
        self._grid_color = grid_color
        self._card_bg = card_bg
        if bar_color:
            self._bar_color = bar_color
        heading_color = title_color or text_color
        border_accent = accent_border or grid_color
        self._title_label.setStyleSheet(
            f"color: {heading_color}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        self.setStyleSheet(
            f"QFrame#dashboardSimpleBarChart {{ "
            f"background-color: {card_bg}; "
            f"border: 1px solid {border_accent}; "
            f"border-left: 4px solid {border_accent}; "
            f"border-radius: 8px; }}"
        )
        self.update()

    def set_data(self, labels: list[str], values: list[float]) -> None:
        """Replace chart categories and bar heights."""
        self._labels = list(labels or [])
        self._values = [float(value or 0.0) for value in (values or [])]
        if len(self._values) < len(self._labels):
            self._values.extend(0.0 for _ in range(len(self._labels) - len(self._values)))
        elif len(self._values) > len(self._labels):
            self._values = self._values[: len(self._labels)]
        self.update()

    def paintEvent(self, event) -> None:
        """Draw grid lines, bars, and month labels below the title label."""
        chart_rect = QRectF(48, 52, max(self.width() - 64, 40), max(self.height() - 88, 60))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._labels:
            painter.setPen(QColor(self._muted_color))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(
                chart_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                "No data available",
            )
            painter.end()
            super().paintEvent(event)
            return

        max_value = max(self._values) if self._values else 0.0
        if max_value <= 0:
            max_value = 1.0

        grid_pen = QPen(QColor(self._grid_color))
        grid_pen.setWidthF(1.0)
        painter.setPen(grid_pen)
        for step in range(5):
            y = chart_rect.top() + (chart_rect.height() * step / 4.0)
            painter.drawLine(chart_rect.left(), y, chart_rect.right(), y)

        bar_count = len(self._labels)
        gap = 10.0
        bar_width = max((chart_rect.width() - gap * (bar_count + 1)) / bar_count, 8.0)
        bar_color = QColor(self._bar_color)

        painter.setFont(QFont("Segoe UI", 8))
        for index, (label, value) in enumerate(zip(self._labels, self._values)):
            x = chart_rect.left() + gap + index * (bar_width + gap)
            height_ratio = max(value, 0.0) / max_value
            bar_height = chart_rect.height() * height_ratio
            y = chart_rect.bottom() - bar_height
            painter.fillRect(QRectF(x, y, bar_width, bar_height), bar_color)

            painter.setPen(QColor(self._muted_color))
            painter.drawText(
                QRectF(x - 4, chart_rect.bottom() + 4, bar_width + 8, 24),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                label,
            )

            if value > 0:
                painter.setPen(QColor(self._text_color))
                value_text = self._compact_amount(value)
                painter.drawText(
                    QRectF(x - 8, y - 18, bar_width + 16, 16),
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom),
                    value_text,
                )

        painter.end()
        super().paintEvent(event)

    @staticmethod
    def _compact_amount(amount: float) -> str:
        """Format large totals in a compact label above each bar."""
        if amount >= 1_000_000:
            return f"{amount / 1_000_000:.1f}M"
        if amount >= 1_000:
            return f"{amount / 1_000:.1f}K"
        return f"{amount:.0f}"