"""
Dashboard widget for the Accounting Desktop Application.
Main dashboard page for the QStackedWidget workspace.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSizePolicy,
)

from config import CURRENCY_SYMBOL
from db import Database
from bizora_core.dashboard_logic import DashboardLogic
from ui.dashboard_refresh import dashboard_refresh_bus
from ui.qt_pump import pump_ui_events
from ui.simple_bar_chart import SimpleMonthlyBarChart
from ui.theme_manager import get_theme_manager
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class DashboardWidget(UiMemoryMixin, QWidget):
    """Main dashboard widget showing financial overview."""

    _SUMMARY_SPECS = (
        ("net_realized_sale", "Net Realized Sale", "button_primary"),
        ("total_creditors", "Total to Give to Creditors", "button_danger"),
        ("total_debtors", "Total to Get from Debtors", "button_success"),
        ("day_credit_sale", "Day Credit Sale", "accent"),
    )
    _ROW_SPACING = 15

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.dashboard_logic = DashboardLogic(self.db)
        self._cards = []
        self._summary_card_labels: dict[str, QLabel] = {}
        self._text_labels = []
        self._activity_items: list[str] = []
        self._activity_title_label: QLabel | None = None
        self._activity_body_label: QLabel | None = None
        self._sales_chart: SimpleMonthlyBarChart | None = None
        self._purchase_chart: SimpleMonthlyBarChart | None = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15_000)
        self._refresh_timer.timeout.connect(self.refresh_data)
        dashboard_refresh_bus.refresh_requested.connect(self.refresh_data)
        self.setup_ui()
        self.refresh_theme()
        self.refresh_data()
        self._refresh_timer.start()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)

    def set_database(self, db) -> None:
        """Point the dashboard at the active company database connection."""
        if db is None:
            return
        self.db = db
        self.dashboard_logic = DashboardLogic(db)

    def showEvent(self, event: QShowEvent) -> None:
        """Refresh live metrics whenever the dashboard becomes visible."""
        super().showEvent(event)
        self.refresh_data()

    def _format_currency(self, amount: float) -> str:
        """Format dashboard currency values with the app rupee symbol."""
        return f"{CURRENCY_SYMBOL}{amount:,.2f}"

    def _metric_accent(self, color_token: str, colors: dict[str, str] | None = None) -> str:
        """Resolve the accent color used for a dashboard metric card."""
        palette = colors or self._colors()
        return palette.get(color_token, palette["button_primary"])

    def _accent_frame_style(self, colors: dict[str, str], accent: str) -> str:
        """Return QSS for a dashboard panel with a matching heading accent border."""
        return f"""
            QFrame {{
                background-color: {colors['card_bg']};
                border: 1px solid {accent};
                border-left: 4px solid {accent};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border: 1px solid {accent};
                border-left: 4px solid {accent};
            }}
        """

    def _metric_card_html(self, title: str, amount_text: str, accent: str) -> str:
        """Build summary card HTML with matching heading and value colors."""
        return (
            f'<span style="color:{accent}; font-size:12px; font-weight:600;">{title}</span>'
            f'<br><span style="color:{accent}; font-size:22px; font-weight:700;">'
            f"{amount_text}</span>"
        )

    def refresh_data(self) -> None:
        """Reload live summary metrics, charts, and recent activity."""
        try:
            metrics = self.dashboard_logic.get_summary_metrics()
            colors = self._colors()
            for metric_key, title, color_token in self._SUMMARY_SPECS:
                label = self._summary_card_labels.get(metric_key)
                if label is None:
                    continue
                value = float(metrics.get(metric_key, 0.0) or 0.0)
                accent = self._metric_accent(color_token, colors)
                label.setText(
                    self._metric_card_html(title, self._format_currency(value), accent)
                )

            sales_series = self.dashboard_logic.get_monthly_sales_chart_data()
            purchase_series = self.dashboard_logic.get_monthly_purchase_chart_data()
            if self._sales_chart is not None:
                self._sales_chart.set_data(
                    [row["label"] for row in sales_series],
                    [float(row["total"]) for row in sales_series],
                )
            if self._purchase_chart is not None:
                self._purchase_chart.set_data(
                    [row["label"] for row in purchase_series],
                    [float(row["total"]) for row in purchase_series],
                )

            self._activity_items = self.dashboard_logic.get_recent_activities(limit=5)
            if not self._activity_items:
                self._activity_items = ["No recent activity recorded yet."]
            if self._activity_body_label is not None:
                sections = self._section_palette(colors)
                self._activity_body_label.setText(
                    self._format_activity_body(colors, sections["activity"]["body"])
                )

            pump_ui_events()
        except Exception as exc:
            print(f"[DASHBOARD] refresh_data failed: {exc}")

    def _colors(self) -> dict[str, str]:
        return get_theme_manager().get_colors()

    def setup_ui(self):
        """Setup dashboard sections to fit the workspace without scrolling."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.summary_widget = self.create_summary_section()
        layout.addWidget(self.summary_widget, 0)

        self.charts_widget = self.create_charts_section()
        layout.addWidget(self.charts_widget, 3)

        self.activity_widget = self.create_recent_activity_section()
        layout.addWidget(self.activity_widget, 2)

    def _section_palette(self, colors: dict[str, str]) -> dict[str, dict[str, str]]:
        """Return distinct accent colors for dashboard chart and activity panels."""
        sales_accent = colors.get("button_success", "#4CAF50")
        purchase_accent = colors.get("button_primary", "#2196F3")
        return {
            "sales": {
                "title": sales_accent,
                "bar": sales_accent,
                "border": sales_accent,
            },
            "purchase": {
                "title": purchase_accent,
                "bar": purchase_accent,
                "border": purchase_accent,
            },
            "activity": {
                "title": colors.get("accent_label", "#fbbf24"),
                "border": colors.get("accent_label", "#fbbf24"),
                "body": colors.get("label_text", colors["input_text"]),
            },
        }

    def refresh_theme(self) -> None:
        """Reapply theme colors after a global theme switch."""
        colors = self._colors()
        sections = self._section_palette(colors)
        self.setStyleSheet(f"background-color: {colors['app_bg']}; color: {colors['input_text']};")

        for label in self._text_labels:
            role = label.property("dashboard_role")
            if role == "activity_title":
                if self._activity_title_label is not None:
                    activity_title_color = sections["activity"]["title"]
                    self._activity_title_label.setText(
                        f'<span style="color:{activity_title_color}; font-size:16px; '
                        f'font-weight:700;">Recent Activity</span>'
                    )
            elif role == "activity_body":
                if self._activity_body_label is not None:
                    self._activity_body_label.setText(
                        self._format_activity_body(colors, sections["activity"]["body"])
                    )

        for card, color_token in self._cards:
            accent = self._metric_accent(color_token, colors)
            card.setStyleSheet(self._accent_frame_style(colors, accent))

        if self._sales_chart is not None:
            sales_palette = sections["sales"]
            self._sales_chart.set_theme_colors(
                text_color=colors["input_text"],
                muted_color=colors["muted_text"],
                grid_color=colors["border"],
                card_bg=colors["card_bg"],
                bar_color=sales_palette["bar"],
                title_color=sales_palette["title"],
                accent_border=sales_palette["border"],
            )
        if self._purchase_chart is not None:
            purchase_palette = sections["purchase"]
            self._purchase_chart.set_theme_colors(
                text_color=colors["input_text"],
                muted_color=colors["muted_text"],
                grid_color=colors["border"],
                card_bg=colors["card_bg"],
                bar_color=purchase_palette["bar"],
                title_color=purchase_palette["title"],
                accent_border=purchase_palette["border"],
            )

        self.refresh_data()

        if hasattr(self, "activity_widget"):
            activity_palette = sections["activity"]
            activity_accent = activity_palette["border"]
            self.activity_widget.setStyleSheet(f"""
                QFrame#dashboardActivityFrame {{
                    background-color: {colors['card_bg']};
                    border: 1px solid {activity_accent};
                    border-left: 4px solid {activity_accent};
                    border-radius: 8px;
                }}
            """)

    def create_summary_section(self) -> QWidget:
        """Create financial summary cards aligned with the chart row width."""
        summary_widget = QWidget()
        summary_layout = QHBoxLayout(summary_widget)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(self._ROW_SPACING)

        colors = self._colors()
        for metric_key, title, color_token in self._SUMMARY_SPECS:
            accent = self._metric_accent(color_token, colors)
            card, card_label = self.create_summary_card(metric_key, title, color_token, accent)
            self._summary_card_labels[metric_key] = card_label
            summary_layout.addWidget(card, 1)

        return summary_widget

    def create_summary_card(
        self,
        metric_key: str,
        title: str,
        color_token: str,
        accent: str,
    ) -> tuple[QFrame, QLabel]:
        """Create a summary card widget and return the card plus value label."""
        colors = self._colors()
        card = QFrame()
        card.setMinimumHeight(104)
        card.setMaximumHeight(112)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setProperty("dashboard_metric", metric_key)
        self._cards.append((card, color_token))
        card.setStyleSheet(self._accent_frame_style(colors, accent))

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        card_text = QLabel()
        card_text.setWordWrap(True)
        card_text.setTextFormat(Qt.TextFormat.RichText)
        card_text.setStyleSheet(
            "background: transparent; border: none; font-size: 13px; font-weight: 500;"
        )
        card_text.setText(self._metric_card_html(title, self._format_currency(0.0), accent))
        layout.addWidget(card_text)

        return card, card_text

    def create_charts_section(self) -> QWidget:
        """Create monthly sales and purchase bar charts."""
        charts_widget = QWidget()
        charts_layout = QHBoxLayout(charts_widget)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(self._ROW_SPACING)

        colors = self._colors()
        self._sales_chart = SimpleMonthlyBarChart(
            "Monthly Sales",
            bar_color=colors["button_success"],
        )
        self._purchase_chart = SimpleMonthlyBarChart(
            "Monthly Purchase",
            bar_color=colors["button_primary"],
        )
        charts_layout.addWidget(self._sales_chart, 1)
        charts_layout.addWidget(self._purchase_chart, 1)
        return charts_widget

    def create_recent_activity_section(self) -> QFrame:
        """Create recent activity section showing the latest five vouchers."""
        colors = self._colors()
        activity_widget = QFrame()
        activity_widget.setObjectName("dashboardActivityFrame")
        activity_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.activity_widget = activity_widget

        activity_layout = QVBoxLayout(activity_widget)
        activity_layout.setContentsMargins(16, 12, 16, 12)
        activity_layout.setSpacing(8)

        self._activity_items = []

        activity_title = QLabel(
            f'<span style="color:{colors.get("accent_label", "#fbbf24")}; '
            f'font-size:16px; font-weight:700;">Recent Activity</span>'
        )
        activity_title.setTextFormat(Qt.TextFormat.RichText)
        activity_title.setProperty("dashboard_role", "activity_title")
        self._activity_title_label = activity_title
        self._text_labels.append(activity_title)
        activity_layout.addWidget(activity_title)

        activity_body = QLabel(
            self._format_activity_body(
                colors,
                colors.get("label_text", colors["input_text"]),
            )
        )
        activity_body.setWordWrap(True)
        activity_body.setTextFormat(Qt.TextFormat.RichText)
        activity_body.setProperty("dashboard_role", "activity_body")
        activity_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._activity_body_label = activity_body
        self._text_labels.append(activity_body)
        activity_layout.addWidget(activity_body, 1)

        return activity_widget

    def _format_activity_body(
        self,
        colors: dict[str, str],
        body_color: str | None = None,
    ) -> str:
        """Build theme-aware HTML for the recent-activity bullet list."""
        text_color = body_color or colors.get("label_text", colors["input_text"])
        if not self._activity_items:
            return (
                f'<span style="color:{text_color}; font-size:12px;">'
                "&#8226; No recent activity recorded yet.</span>"
            )
        return "<br>".join(
            f'<span style="color:{text_color}; font-size:12px;">'
            f"&#8226; {item}</span>"
            for item in self._activity_items[:5]
        )