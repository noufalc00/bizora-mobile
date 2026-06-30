"""
Reports widget for the Accounting Desktop Application.
Generates financial reports and analytics.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QComboBox, QDateEdit
from PySide6.QtCore import Qt, QDate

from config import COLORS
from ui.date_formats import configure_qdate_edit, prepare_report_date_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class ReportsWidget(UiMemoryMixin, QWidget):
    """Reports widget for financial analytics and reporting."""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)
    
    def setup_ui(self):
        """Setup reports UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Header
        title = QLabel("Financial Reports")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_primary']};
                font-size: 24px;
                font-weight: bold;
            }}
        """)
        layout.addWidget(title)
        
        # Report controls
        controls_frame = QFrame()
        controls_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface']};
                border-radius: 8px;
                padding: 16px;
            }}
        """)
        
        controls_layout = QHBoxLayout(controls_frame)
        
        # Report type selection
        controls_layout.addWidget(QLabel("Report Type:"))
        
        self.report_combo = QComboBox()
        self.report_combo.addItems([
            "Income & Expense Summary",
            "Account Balances",
            "Category Breakdown",
            "Monthly Trends",
            "Yearly Overview"
        ])
        self.report_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLORS['card']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                padding: 8px;
                border-radius: 4px;
                min-width: 200px;
            }}
        """)
        controls_layout.addWidget(self.report_combo)
        
        controls_layout.addSpacing(20)
        
        # Date range
        controls_layout.addWidget(QLabel("From:"))
        
        self.from_date = QDateEdit()
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        report_date_style = f"""
            QDateEdit {{
                background-color: {COLORS['card']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                padding: 8px;
                border-radius: 4px;
            }}
        """
        prepare_report_date_edit(self.from_date, style_sheet=report_date_style)
        controls_layout.addWidget(self.from_date)
        
        controls_layout.addWidget(QLabel("To:"))
        
        self.to_date = QDateEdit()
        self.to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.to_date, style_sheet=report_date_style)
        controls_layout.addWidget(self.to_date)
        
        controls_layout.addStretch()
        
        generate_btn = QPushButton("Generate Report")
        generate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary_dark']};
            }}
        """)
        controls_layout.addWidget(generate_btn)
        
        export_btn = QPushButton("Export")
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['success']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        controls_layout.addWidget(export_btn)
        
        layout.addWidget(controls_frame)
        
        # Report content area
        self.report_content = QFrame()
        self.report_content.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['surface']};
                border-radius: 8px;
                padding: 20px;
                min-height: 400px;
            }}
        """)
        
        report_layout = QVBoxLayout(self.report_content)
        
        # Placeholder content
        placeholder_title = QLabel("Income & Expense Summary")
        placeholder_title.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_primary']};
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 20px;
            }}
        """)
        report_layout.addWidget(placeholder_title)
        
        # Summary cards
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(15)
        
        summaries = [
            ("Total Income", "$3,750.00", COLORS['success']),
            ("Total Expenses", "$1,263.30", COLORS['error']),
            ("Net Income", "$2,486.70", COLORS['primary']),
            ("Savings Rate", "66.3%", COLORS['info'])
        ]
        
        for title_text, value, color in summaries:
            card = self.create_summary_card(title_text, value, color)
            summary_layout.addWidget(card)
        
        report_layout.addLayout(summary_layout)
        
        # Placeholder for charts
        chart_placeholder = QLabel("Chart visualization will be displayed here")
        chart_placeholder.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                padding: 60px;
                text-align: center;
                background-color: {COLORS['card']};
                border-radius: 8px;
                border: 2px dashed {COLORS['border']};
            }}
        """)
        chart_placeholder.setAlignment(Qt.AlignCenter)
        report_layout.addWidget(chart_placeholder)
        
        layout.addWidget(self.report_content)
    
    def create_summary_card(self, title: str, value: str, color: str) -> QFrame:
        """Create a summary card widget."""
        card = QFrame()
        card.setFixedHeight(100)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 12px;
            }}
            QFrame:hover {{
                border: 1px solid {color};
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setSpacing(5)
        
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                font-size: 12px;
            }}
        """)
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 16px;
                font-weight: bold;
            }}
        """)
        layout.addWidget(value_label)
        
        layout.addStretch()
        
        return card