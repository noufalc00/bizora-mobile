"""
View Company dialog for the Accounting Desktop Application.
Provides a professional interface to view complete company details with logo and signature previews.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QFrame, QScrollArea, QVBoxLayout
from ui import theme
from ui.company_profile_content import CompanyProfileContentWidget
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class ViewCompanyDialog(UiMemoryMixin, QDialog):
    """Dialog to view complete company details with professional layout."""

    def __init__(self, company_data, parent=None):
        super().__init__(parent)
        self.company_data = company_data
        self.setWindowTitle(f"View Company - {company_data['business_name']}")
        self.setMinimumSize(600, 500)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.setup_ui()
        self._init_ui_memory()

    def setup_ui(self):
        """Setup the dialog UI."""
        lc = theme.legacy_colors()
        self.setStyleSheet(f"\n            QDialog {{\n                background-color: {lc['background']};\n                color: {lc['text_primary']};\n            }}\n        ")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet(theme.master_scroll_page_style())
        self.profile_content = CompanyProfileContentWidget(self.company_data, show_actions=True)
        scroll_area.setWidget(self.profile_content)
        layout.addWidget(scroll_area)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton('Close')
        close_button.clicked.connect(self.accept)
        close_button.setStyleSheet(theme.master_primary_action_button_style('10px 20px', 14))
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)