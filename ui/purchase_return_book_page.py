"""
Purchase Return Book page.
"""

from typing import Optional

from db import Database
from bizora_core.purchase_return_book_logic import PurchaseReturnBookLogic
from .book_report_common import BookReportPageWidget


class PurchaseReturnBookPageWidget(BookReportPageWidget):
    """UI page for Purchase Return Book."""

    def __init__(self, db: Optional[Database] = None, parent=None):
        self.logic_instance = PurchaseReturnBookLogic(db)
        super().__init__(db or self.logic_instance.db, self.logic_instance, "Purchase Return Book", ['Bill Wise Purchase Return', 'Item Wise Purchase Return', 'Tax Wise Purchase Return', 'Purchase Return Tax Summary', 'Refund / Credit Purchase Return', 'Party Wise Purchase Return'], parent)