"""
Sales Book page.
"""

from typing import Optional

from db import DB_PATH, Database
from bizora_core.sales_book_logic import SalesBookLogic
from ui.net_sales_book import create_view_net_sales_button, open_net_sales_book_window
from .book_report_common import BOOK_REPORT_ACTION_BUTTON_HEIGHT, BookReportPageWidget


class SalesBookPageWidget(BookReportPageWidget):
    """UI page for Sales Book."""

    def __init__(self, db: Optional[Database] = None, parent=None):
        self._net_sales_window = None
        self.logic_instance = SalesBookLogic(db)
        super().__init__(
            db or self.logic_instance.db,
            self.logic_instance,
            "Sales Book",
            [
                "Bill Wise Sales",
                "Item Wise Sales",
                "Tax Wise Sales",
                "Sales Tax Summary",
                "Credit Sales",
                "Party Wise Sales",
                "Category Wise Sales",
            ],
            parent,
        )

    def _build_ui(self) -> None:
        """Build the shared Sales Book layout and add the Net Sales Book shortcut."""
        super()._build_ui()
        self._add_net_sales_book_button()

    def _add_net_sales_book_button(self) -> None:
        """Add Net Sales Book shortcut on the shared action button row."""
        self.net_sales_btn = create_view_net_sales_button(
            action_height=BOOK_REPORT_ACTION_BUTTON_HEIGHT,
        )
        self.net_sales_btn.clicked.connect(self.open_net_sales_book)
        stretch_index = max(self.filter_action_layout.count() - 1, 0)
        self.filter_action_layout.insertWidget(stretch_index, self.net_sales_btn)

    def open_net_sales_book(self) -> None:
        """Open Net Sales Book in a standalone popup window."""
        db_path = getattr(self.db, "db_path", None) or DB_PATH
        self._net_sales_window = open_net_sales_book_window(
            self,
            db_path=db_path,
            existing_window=self._net_sales_window,
        )