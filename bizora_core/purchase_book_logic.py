"""
Purchase Book logic.
Read-only accounting book report queries.
"""

from typing import Optional

from db import Database
from .book_report_common import VoucherBookLogic


CONFIG = {
    "voucher_type": "purchase",
    "title": "Purchase Book",
    "header_table": "purchases",
    "item_table": "purchase_items",
    "item_fk": "purchase_id",
    "number_col": "purchase_number",
    "date_col": "purchase_date",
    "party_col": "party_id",
    "type_col": "purchase_type",
    "settled_col": "amount_paid",
    "party_types": [
        "Creditor",
        "Both"
    ]
}


class PurchaseBookLogic(VoucherBookLogic):
    """Logic wrapper for Purchase Book."""

    def __init__(self, db: Optional[Database] = None):
        super().__init__(db, CONFIG)

    def get_bill_wise_purchase(self, company_id, from_date, to_date, filters=None):
        return self.get_bill_wise(company_id, from_date, to_date, filters)

    def get_item_wise_purchase(self, company_id, from_date, to_date, filters=None):
        return self.get_item_wise(company_id, from_date, to_date, filters)

    def get_tax_wise_purchase(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_wise(company_id, from_date, to_date, filters)

    def get_tax_summary_purchase(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_summary(company_id, from_date, to_date, filters)

    def get_party_wise_purchase(self, company_id, from_date, to_date, filters=None):
        return self.get_party_wise(company_id, from_date, to_date, filters)

    def get_category_wise_purchase(self, company_id, from_date, to_date, filters=None):
        return self.get_category_wise(company_id, from_date, to_date, filters)

    def get_purchase_detail(self, company_id, voucher_id):
        return self.get_bill_detail(company_id, voucher_id)
