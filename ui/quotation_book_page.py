"""
Quotation Book page.
"""

from typing import Optional

from db import Database
from bizora_core.quotation_book_logic import QuotationBookLogic
from .book_report_common import BookReportPageWidget


class QuotationBookPageWidget(BookReportPageWidget):
    """UI page for Quotation Book."""

    def __init__(self, db: Optional[Database] = None, parent=None):
        self.logic_instance = QuotationBookLogic(db)
        super().__init__(db or self.logic_instance.db, self.logic_instance, "Quotation Book", ['Bill Wise Quotations', 'Item Wise Quotations', 'Tax Wise Quotations', 'Quotation Tax Summary', 'Party Wise Quotations'], parent)