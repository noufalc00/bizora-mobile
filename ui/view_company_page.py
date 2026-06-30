"""

View Company page for the Accounting Desktop Application.

Shows the active company's filled profile data with section headings.

"""



from PySide6.QtCore import Qt

from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget



from config import active_company_manager

from db import Database

from ui import theme

from ui.company_profile_content import CompanyProfileContentWidget
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin


class ViewCompanyPageWidget(UiMemoryMixin, QWidget):

    """Read-only page that displays the active company profile."""



    def __init__(self, db=None, parent=None):

        super().__init__(parent)

        self.db = db or Database()

        self.setup_ui()

        self.load_company_data()
        self._init_ui_memory(restore_geometry=False, save_geometry=False)



    def setup_ui(self) -> None:

        self.setObjectName("ViewCompanyPageWidget")

        self.setStyleSheet(theme.master_scroll_page_style("ViewCompanyPageWidget"))



        layout = QVBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)

        layout.setSpacing(0)



        scroll_area = QScrollArea()

        scroll_area.setWidgetResizable(True)

        scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_area.setStyleSheet(theme.master_scroll_page_style())



        content_widget = QWidget()

        content_widget.setStyleSheet(theme.master_page_background_style())

        content_layout = QVBoxLayout(content_widget)

        content_layout.setContentsMargins(28, 22, 28, 22)

        content_layout.setSpacing(20)



        title = QLabel("View Company")

        title.setStyleSheet(theme.master_page_title_style(28))

        content_layout.addWidget(title, alignment=Qt.AlignLeft)



        self.subtitle_label = QLabel("Active company profile")

        self.subtitle_label.setStyleSheet(theme.master_page_subtitle_style())

        content_layout.addWidget(self.subtitle_label, alignment=Qt.AlignLeft)



        self.empty_state_label = QLabel(

            "No active company is open. Open a company first to view its details."

        )

        self.empty_state_label.setWordWrap(True)

        self.empty_state_label.setAlignment(Qt.AlignCenter)

        self.empty_state_label.setStyleSheet(theme.master_empty_state_style())

        self.empty_state_label.hide()

        content_layout.addWidget(self.empty_state_label)



        self.profile_content = CompanyProfileContentWidget(show_actions=True)

        content_layout.addWidget(self.profile_content)

        content_layout.addStretch()



        scroll_area.setWidget(content_widget)

        layout.addWidget(scroll_area)



    def load_company_data(self) -> None:

        """Load the active company and refresh the read-only profile."""

        company_data = None



        try:

            company_data = self.db.get_active_company() if self.db else None

        except Exception as error:

            print(f"[VIEW COMPANY] Could not load active company: {error}")



        if not company_data:

            company_data = active_company_manager.get_active_company()



        if company_data:

            business_name = company_data.get("business_name") or "Active company"

            self.subtitle_label.setText(f"Showing filled details for {business_name}")

            self.empty_state_label.hide()

            self.profile_content.show()

            self.profile_content.set_company_data(company_data)

            return



        self.subtitle_label.setText("No active company selected")

        self.profile_content.hide()

        self.empty_state_label.show()



    def refresh_theme(self) -> None:

        """Re-apply theme styles after a global theme change."""

        self.setStyleSheet(theme.master_scroll_page_style("ViewCompanyPageWidget"))

        self.subtitle_label.setStyleSheet(theme.master_page_subtitle_style())

        self.empty_state_label.setStyleSheet(theme.master_empty_state_style())

        if hasattr(self.profile_content, "refresh_theme"):

            self.profile_content.refresh_theme()

