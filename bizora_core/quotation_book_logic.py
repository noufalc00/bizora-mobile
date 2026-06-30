"""
Quotation Book logic.
Read-only quotation book report queries.
"""

from typing import Optional

from db import Database
from .book_report_common import VoucherBookLogic


CONFIG = {
    "voucher_type": "quotation",
    "title": "Quotation Book",
    "header_table": "quotations",
    "item_table": "quotation_items",
    "item_fk": "quotation_id",
    "number_col": "quotation_no",
    "date_col": "quotation_date",
    "party_col": "party_id",
    "type_col": "quotation_type",
    "settled_col": None,  # Quotations don't have settlement
    "party_types": [
        "Debitor",
        "Both"
    ]
}


class QuotationBookLogic(VoucherBookLogic):
    """Logic wrapper for Quotation Book."""

    def __init__(self, db: Optional[Database] = None):
        super().__init__(db, CONFIG)

    def get_bill_wise_quotations(self, company_id, from_date, to_date, filters=None):
        return self.get_bill_wise(company_id, from_date, to_date, filters)

    def get_item_wise_quotations(self, company_id, from_date, to_date, filters=None):
        return self.get_item_wise(company_id, from_date, to_date, filters)

    def get_tax_wise_quotations(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_wise(company_id, from_date, to_date, filters)

    def get_tax_summary_quotations(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_summary(company_id, from_date, to_date, filters)

    def get_party_wise_quotations(self, company_id, from_date, to_date, filters=None):
        return self.get_party_wise(company_id, from_date, to_date, filters)

    def get_quotation_detail(self, company_id, voucher_id):
        return self.get_bill_detail(company_id, voucher_id)
