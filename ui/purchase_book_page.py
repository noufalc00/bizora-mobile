"""
Purchase Book page.
"""

from typing import Optional

from db import Database
from bizora_core.purchase_book_logic import PurchaseBookLogic
from .book_report_common import BookReportPageWidget


class PurchaseBookPageWidget(BookReportPageWidget):
    """UI page for Purchase Book."""

    def __init__(self, db: Optional[Database] = None, parent=None):
        self.logic_instance = PurchaseBookLogic(db)
        super().__init__(db or self.logic_instance.db, self.logic_instance, "Purchase Book", ['Bill Wise Purchase', 'Item Wise Purchase', 'Tax Wise Purchase', 'Purchase Tax Summary', 'Party Wise Purchase', 'Category Wise Purchase'], parent)