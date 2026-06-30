"""Theme-aware 3D orbital loading animation for startup and gateway handoff."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


def _loading_palette() -> dict[str, QColor]:
    """Resolve accent colors from the active application theme."""
    try:
        from ui import theme

        colors = theme._theme_colors()
        return {
            "primary": QColor(colors["button_primary"]),
            "accent": QColor(colors.get("accent_label", colors["button_primary"])),
            "highlight": QColor(colors["focus_border"]),
            "shadow": QColor(colors.get("muted_text", colors["border"])),
            "glow": QColor(colors.get("card_bg", colors["panel_bg"])),
        }
    except Exception:
        return {
            "primary": QColor("#0E7490"),
            "accent": QColor("#D97706"),
            "highlight": QColor("#0E7490"),
            "shadow": QColor("#4F6666"),
            "glow": QColor("#E5F8F8"),
        }


class LoadingRunnerWidget(QWidget):
    """Modern 3D orbital loader with a transparent background."""

    def __init__(self, parent=None, *, width: int = 132, height: int = 132):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._phase = 0.0
        self.start()

    def hideEvent(self, event) -> None:
        self.stop()
        super().hideEvent(event)

    def stop(self) -> None:
        self._timer.stop()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self) -> None:
        self._phase = (self._phase + 2.4) % 360.0
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        center_x = width / 2.0
        center_y = height / 2.0
        palette = _loading_palette()

        shadow_grad = QRadialGradient(center_x, center_y + 34, 42)
        shadow_grad.setColorAt(0.0, QColor(palette["shadow"].red(), palette["shadow"].green(), palette["shadow"].blue(), 70))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(shadow_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(center_x - 42), int(center_y + 18), 84, 22)

        self._draw_orbital_ring(
            painter,
            center_x,
            center_y,
            radius_x=38,
            radius_y=16,
            tilt=0.55,
            sphere_count=6,
            palette=palette,
            phase_offset=0.0,
        )
        self._draw_orbital_ring(
            painter,
            center_x,
            center_y,
            radius_x=28,
            radius_y=28,
            tilt=0.2,
            sphere_count=4,
            palette=palette,
            phase_offset=90.0,
            ring_scale=0.72,
        )
        self._draw_core_sphere(painter, center_x, center_y - 4, palette)

    def _draw_core_sphere(
        self,
        painter: QPainter,
        center_x: float,
        center_y: float,
        palette: dict[str, QColor],
    ) -> None:
        """Draw the central glossy 3D sphere."""
        radius = 20.0
        spin = math.radians(self._phase * 1.6)

        glow = QRadialGradient(center_x, center_y, radius + 10)
        glow.setColorAt(0.0, QColor(palette["highlight"].red(), palette["highlight"].green(), palette["highlight"].blue(), 55))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            int(center_x - radius - 10),
            int(center_y - radius - 10),
            int((radius + 10) * 2),
            int((radius + 10) * 2),
        )

        sphere = QRadialGradient(
            center_x - radius * 0.35 * math.cos(spin),
            center_y - radius * 0.45,
            radius * 1.35,
        )
        sphere.setColorAt(0.0, palette["glow"])
        sphere.setColorAt(0.35, palette["highlight"])
        sphere.setColorAt(0.72, palette["primary"])
        sphere.setColorAt(1.0, palette["primary"].darker(165))
        painter.setBrush(sphere)
        painter.setPen(QPen(palette["primary"].darker(140), 1.2))
        painter.drawEllipse(
            int(center_x - radius),
            int(center_y - radius),
            int(radius * 2),
            int(radius * 2),
        )

        specular = QRadialGradient(center_x - 7, center_y - 9, 10)
        specular.setColorAt(0.0, QColor(255, 255, 255, 210))
        specular.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(specular)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(center_x - 14), int(center_y - 16), 18, 14)

    def _draw_orbital_ring(
        self,
        painter: QPainter,
        center_x: float,
        center_y: float,
        *,
        radius_x: float,
        radius_y: float,
        tilt: float,
        sphere_count: int,
        palette: dict[str, QColor],
        phase_offset: float,
        ring_scale: float = 1.0,
    ) -> None:
        """Draw orbiting glossy spheres with simulated depth."""
        orbit_phase = math.radians(self._phase + phase_offset)
        spheres: list[tuple[float, float, float, float]] = []

        for index in range(sphere_count):
            angle = orbit_phase + index * (2.0 * math.pi / sphere_count)
            depth = math.sin(angle)
            x = center_x + math.cos(angle) * radius_x
            y = center_y + math.sin(angle) * radius_y * tilt
            scale = (0.45 + (depth + 1.0) * 0.28) * ring_scale
            spheres.append((depth, x, y, scale))

        spheres.sort(key=lambda item: item[0])

        for depth, x, y, scale in spheres:
            radius = 7.5 * scale
            alpha = int(110 + (depth + 1.0) * 70)
            base_color = palette["accent"] if depth > 0 else palette["primary"]

            halo = QRadialGradient(x, y, radius + 5)
            halo.setColorAt(
                0.0,
                QColor(base_color.red(), base_color.green(), base_color.blue(), alpha // 3),
            )
            halo.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(halo)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(x - radius - 5), int(y - radius - 5), int((radius + 5) * 2), int((radius + 5) * 2))

            body = QRadialGradient(x - radius * 0.25, y - radius * 0.35, radius * 1.2)
            body.setColorAt(0.0, QColor(255, 255, 255, min(220, alpha + 40)))
            body.setColorAt(0.45, base_color.lighter(115))
            body.setColorAt(1.0, base_color.darker(150))
            painter.setBrush(body)
            painter.setPen(QPen(base_color.darker(170), 0.8))
            painter.drawEllipse(int(x - radius), int(y - radius), int(radius * 2), int(radius * 2))

        ring_grad = QConicalGradient(center_x, center_y, self._phase + phase_offset)
        ring_grad.setColorAt(0.0, QColor(palette["highlight"].red(), palette["highlight"].green(), palette["highlight"].blue(), 0))
        ring_grad.setColorAt(0.2, QColor(palette["highlight"].red(), palette["highlight"].green(), palette["highlight"].blue(), 90))
        ring_grad.setColorAt(0.5, QColor(palette["primary"].red(), palette["primary"].green(), palette["primary"].blue(), 40))
        ring_grad.setColorAt(1.0, QColor(palette["highlight"].red(), palette["highlight"].green(), palette["highlight"].blue(), 0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(ring_grad, 2.0))
        painter.drawEllipse(
            int(center_x - radius_x - 4),
            int(center_y - radius_y * tilt - 4),
            int((radius_x + 4) * 2),
            int((radius_y * tilt + 4) * 2),
        )