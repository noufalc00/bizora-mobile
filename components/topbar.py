"""
Topbar component with company name and user controls.
Provides the header area of the main application window.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QFont, QIcon, QFontMetrics

from config import APP_NAME, BRAND_NAME, active_company_manager
from db import Database
from ui.theme_manager import get_theme_manager

_APP_ROOT = Path(__file__).resolve().parent.parent
_CALCULATOR_ICON = _APP_ROOT / "assets" / "icons" / "calculator.svg"
_COMPANY_FONT_MAX_PT = 26
_COMPANY_FONT_MIN_PT = 12


class TopbarWidget(QFrame):
    """Top header bar with company name (left) and user controls (right)."""

    logout_requested = Signal()

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self._company_display_text = BRAND_NAME
        self.setup_ui()
        self.setup_timer()
        self.update_title_display()

    def _theme_colors(self) -> dict[str, str]:
        return get_theme_manager().get_colors()

    def setup_ui(self):
        """Build the single-frame top bar with a 50/50 left-right layout."""
        colors = self._theme_colors()
        self.setObjectName("applicationTopbar")
        self.setFixedHeight(68)
        self.setStyleSheet(f"""
            QFrame#applicationTopbar {{
                background-color: {colors['panel_bg']};
                border-bottom: 1px solid {colors['border']};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(15)

        # Left half: prominent company name (stretch 1 = 50% of bar width).
        self.company_label = QLabel(BRAND_NAME)
        self.company_label.setObjectName("topbarCompanyLabel")
        company_font = QFont()
        company_font.setPointSize(26)
        company_font.setBold(True)
        self.company_label.setFont(company_font)
        self.company_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.company_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.company_label.setWordWrap(False)
        self._apply_company_label_style()
        layout.addWidget(self.company_label, 1)

        # Right half: user controls aligned to the right (stretch 1 reserves 50%).
        controls_host = QWidget()
        controls_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.user_layout = QHBoxLayout(controls_host)
        self.user_layout.setContentsMargins(0, 0, 0, 0)
        self.user_layout.setSpacing(12)
        self.user_layout.addStretch()

        datetime_widget = QWidget()
        datetime_layout = QHBoxLayout(datetime_widget)
        datetime_layout.setContentsMargins(0, 0, 0, 0)
        datetime_layout.setSpacing(8)

        self.date_label = QLabel()
        self.time_label = QLabel()
        self._apply_datetime_label_styles()
        datetime_layout.addWidget(self.date_label)
        datetime_layout.addWidget(self.time_label)
        self.user_layout.addWidget(datetime_widget)

        self.user_label = QLabel("Admin")
        self.user_label.setObjectName("topbarRoleLabel")
        self._apply_role_label_style()
        self.user_layout.addWidget(self.user_label)

        self.calculator_btn = QPushButton()
        if _CALCULATOR_ICON.is_file():
            self.calculator_btn.setIcon(QIcon(str(_CALCULATOR_ICON)))
            self.calculator_btn.setIconSize(QSize(24, 24))
        else:
            self.calculator_btn.setText("Calc")
        self.calculator_btn.setStyleSheet(self._calculator_button_style())
        self.calculator_btn.setToolTip("Calculator")
        self.calculator_btn.clicked.connect(self.open_calculator)
        self.user_layout.addWidget(self.calculator_btn)

        self.logout_btn = QPushButton("Log Out")
        self.logout_btn.setObjectName("logoutButton")
        self.logout_btn.setToolTip("Log out and switch to another user")
        self.logout_btn.setMinimumHeight(30)
        self.logout_btn.clicked.connect(self.logout_requested.emit)
        self.user_layout.addWidget(self.logout_btn)

        layout.addWidget(controls_host, 1)

    def _apply_company_label_style(self) -> None:
        """Apply theme colors to the company name label."""
        colors = self._theme_colors()
        title_color = (
            colors["focus_border"]
            if active_company_manager.has_active_company()
            else colors["input_text"]
        )
        self.company_label.setStyleSheet(f"""
            QLabel#topbarCompanyLabel {{
                color: {title_color};
                font-size: 26px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
        """)

    def _apply_datetime_label_styles(self) -> None:
        """Apply theme colors to the date and time labels."""
        colors = self._theme_colors()
        label_style = f"""
            QLabel {{
                color: {colors['accent_label']};
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                border: none;
            }}
        """
        self.date_label.setStyleSheet(label_style)
        self.time_label.setStyleSheet(label_style)

    def _apply_role_label_style(self) -> None:
        """Apply theme colors to the user role label."""
        colors = self._theme_colors()
        self.user_label.setStyleSheet(f"""
            QLabel#topbarRoleLabel {{
                color: {colors['input_text']};
                font-size: 13px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
        """)

    def _calculator_button_style(self) -> str:
        colors = self._theme_colors()
        hover = colors["focus_border"]
        pressed = "#1565C0" if get_theme_manager().get_current_theme() == "light" else "#1d4ed8"
        return f"""
            QPushButton {{
                background-color: {colors['button_primary']};
                color: white;
                border: 1px solid {colors['focus_border']};
                border-radius: 8px;
                padding: 5px;
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {pressed};
            }}
        """

    def setup_timer(self):
        """Setup timer for live date/time updates."""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_datetime_display)
        self.timer.start(1000)
        self.update_datetime_display()

    def update_title_display(self):
        """Update company name based on active company state."""
        if active_company_manager.has_active_company():
            self._company_display_text = active_company_manager.get_active_company_name()
        else:
            self._company_display_text = BRAND_NAME
        self._apply_company_label_style()
        self._refresh_company_label_text()

    def _refresh_company_label_text(self) -> None:
        """Scale the company label font so the full name fits its left-half space."""
        available_width = self.company_label.width()
        if available_width <= 0:
            self.company_label.setText(self._company_display_text)
            return

        base_font = self.company_label.font()
        chosen_font = QFont(base_font)
        metrics = QFontMetrics(chosen_font)

        for point_size in range(_COMPANY_FONT_MAX_PT, _COMPANY_FONT_MIN_PT - 1, -1):
            chosen_font.setPointSize(point_size)
            metrics = QFontMetrics(chosen_font)
            if metrics.horizontalAdvance(self._company_display_text) <= available_width:
                break

        if self.company_label.font().pointSize() != chosen_font.pointSize():
            self.company_label.setFont(chosen_font)

        self.company_label.setText(self._company_display_text)

    def resizeEvent(self, event):
        """Keep the company label scaled when the top bar is resized."""
        super().resizeEvent(event)
        self._refresh_company_label_text()

    def update_datetime_display(self):
        """Update date and time display."""
        from datetime import datetime

        from config import DATE_FORMAT

        now = datetime.now()
        self.date_label.setText(now.strftime(DATE_FORMAT))
        from ui.time_formats import format_display_time

        self.time_label.setText(format_display_time(now, include_seconds=True))

    def update_active_company(self):
        """Refresh the company name when the active company changes."""
        self.update_title_display()

    def set_current_user_display(self, username: str = None, role: str = None) -> None:
        """Update the displayed user role label."""
        role_text = (role or "").strip()
        if not role_text:
            role_text = "Admin" if not username else "User"

        if role_text.lower() == "admin":
            role_text = "Admin"
        elif role_text.lower() == "user":
            role_text = "User"

        self.user_label.setText(role_text)

    def set_logout_button_style(self, style_sheet: str) -> None:
        """Apply the logout button stylesheet from the main window theme."""
        if hasattr(self, "logout_btn"):
            self.logout_btn.setStyleSheet(style_sheet)

    def open_calculator(self):
        """Open calculator dialog."""
        from .calculator_dialog import CalculatorDialog

        calculator = CalculatorDialog(self)
        calculator.exec()

    def refresh_theme(self):
        """Refresh topbar styling based on current theme."""
        colors = self._theme_colors()

        self.setStyleSheet(f"""
            QFrame#applicationTopbar {{
                background-color: {colors['panel_bg']};
                border-bottom: 1px solid {colors['border']};
            }}
        """)

        self._apply_company_label_style()
        self._apply_datetime_label_styles()
        self._apply_role_label_style()

        if hasattr(self, "calculator_btn"):
            self.calculator_btn.setStyleSheet(self._calculator_button_style())

        self.update_active_company()
