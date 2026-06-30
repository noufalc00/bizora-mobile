"""
Purchase Return Book logic.
Read-only accounting book report queries.
"""

from typing import Optional

from db import Database
from .book_report_common import VoucherBookLogic


CONFIG = {
    "voucher_type": "purchase_return",
    "title": "Purchase Return Book",
    "header_table": "purchase_returns",
    "item_table": "purchase_return_items",
    "item_fk": "purchase_return_id",
    "number_col": "return_no",
    "date_col": "return_date",
    "party_col": "party_id",
    "type_col": "return_type",
    "settled_col": "amount_received_or_adjusted",
    "party_types": [
        "Creditor",
        "Both"
    ]
}


class PurchaseReturnBookLogic(VoucherBookLogic):
    """Logic wrapper for Purchase Return Book."""

    def __init__(self, db: Optional[Database] = None):
        super().__init__(db, CONFIG)

    def get_bill_wise_purchase_return(self, company_id, from_date, to_date, filters=None):
        return self.get_bill_wise(company_id, from_date, to_date, filters)

    def get_item_wise_purchase_return(self, company_id, from_date, to_date, filters=None):
        return self.get_item_wise(company_id, from_date, to_date, filters)

    def get_tax_wise_purchase_return(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_wise(company_id, from_date, to_date, filters)

    def get_tax_summary_purchase_return(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_summary(company_id, from_date, to_date, filters)

    def get_party_wise_purchase_return(self, company_id, from_date, to_date, filters=None):
        return self.get_party_wise(company_id, from_date, to_date, filters)

    def get_purchase_return_detail(self, company_id, voucher_id):
        return self.get_bill_detail(company_id, voucher_id)
