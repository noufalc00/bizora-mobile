"""
Sales Return Book page.
"""

from typing import Optional

from db import Database
from bizora_core.sales_return_book_logic import SalesReturnBookLogic
from .book_report_common import BookReportPageWidget


class SalesReturnBookPageWidget(BookReportPageWidget):
    """UI page for Sales Return Book."""

    def __init__(self, db: Optional[Database] = None, parent=None):
        self.logic_instance = SalesReturnBookLogic(db)
        super().__init__(db or self.logic_instance.db, self.logic_instance, "Sales Return Book", ['Bill Wise Sales Return', 'Item Wise Sales Return', 'Tax Wise Sales Return', 'Sales Return Tax Summary', 'Credit Sales Return', 'Party Wise Sales Return'], parent)