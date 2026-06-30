"""
Sales Book logic.
Read-only accounting book report queries.
"""

from typing import Optional

from db import Database
from .book_report_common import VoucherBookLogic


CONFIG = {
    "voucher_type": "sales",
    "title": "Sales Book",
    "header_table": "sales",
    "item_table": "sales_items",
    "item_fk": "sale_id",
    "number_col": "invoice_number",
    "date_col": "invoice_date",
    "party_col": "party_id",
    "type_col": "sales_type",
    "settled_col": "amount_received",
    "party_types": [
        "Debitor",
        "Both"
    ]
}


class SalesBookLogic(VoucherBookLogic):
    """Logic wrapper for Sales Book."""

    def __init__(self, db: Optional[Database] = None):
        super().__init__(db, CONFIG)

    def get_bill_wise_sales(self, company_id, from_date, to_date, filters=None):
        return self.get_bill_wise(company_id, from_date, to_date, filters)

    def get_item_wise_sales(self, company_id, from_date, to_date, filters=None):
        return self.get_item_wise(company_id, from_date, to_date, filters)

    def get_tax_wise_sales(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_wise(company_id, from_date, to_date, filters)

    def get_tax_summary_sales(self, company_id, from_date, to_date, filters=None):
        return self.get_tax_summary(company_id, from_date, to_date, filters)

    def get_party_wise_sales(self, company_id, from_date, to_date, filters=None):
        return self.get_party_wise(company_id, from_date, to_date, filters)

    def get_category_wise_sales(self, company_id, from_date, to_date, filters=None):
        return self.get_category_wise(company_id, from_date, to_date, filters)

    def get_sales_detail(self, company_id, voucher_id):
        return self.get_bill_detail(company_id, voucher_id)
