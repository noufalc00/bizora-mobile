"""
Shared lookup payloads for mobile report filter dropdowns.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

GST_FILTER_OPTIONS: list[dict[str, Any]] = [
    {"label": "All GST", "value": ""},
    {"label": "GST 0%", "value": "0"},
    {"label": "GST 1%", "value": "1"},
    {"label": "GST 3%", "value": "3"},
    {"label": "GST 5%", "value": "5"},
    {"label": "GST 12%", "value": "12"},
    {"label": "GST 18%", "value": "18"},
    {"label": "GST 28%", "value": "28"},
]

PDC_STATUS_OPTIONS = ["All", "PENDING", "CLEARED", "BOUNCED", "CANCELLED"]
PDC_TRANSACTION_OPTIONS = ["All", "RECEIPT", "ISSUE"]
PO_STATUS_OPTIONS = ["All", "Pending", "Completed", "Cancelled"]
MONTH_OPTIONS = [
    "April", "May", "June", "July", "August", "September",
    "October", "November", "December", "January", "February", "March",
]


def _financial_years(today: Optional[date] = None) -> list[str]:
    """Return recent Indian financial year labels."""
    today = today or date.today()
    start_year = today.year if today.month >= 4 else today.year - 1
    return [f"{year}-{str(year + 1)[-2:]}" for year in range(start_year, start_year - 4, -1)]


from bizora_core.mobile_supabase_party_links import party_by_ledger_account as _party_by_ledger_account


def _unique_sorted_names(rows: list[dict[str, Any]], key: str) -> list[str]:
    """Return sorted unique non-empty names from row dictionaries."""
    names = {
        str(row.get(key) or "").strip()
        for row in rows
        if str(row.get(key) or "").strip()
    }
    return sorted(names, key=lambda value: value.lower())


def build_local_report_lookups(db: Any, company_id: int, slug: str) -> dict[str, Any]:
    """Build dropdown lookup data from the local SQLite database."""
    lookups: dict[str, Any] = {
        "gst_options": GST_FILTER_OPTIONS,
        "financial_years": _financial_years(),
        "months": MONTH_OPTIONS,
        "pdc_statuses": PDC_STATUS_OPTIONS,
        "pdc_transaction_types": PDC_TRANSACTION_OPTIONS,
        "po_statuses": PO_STATUS_OPTIONS,
    }
    try:
        from bizora_core.book_report_common import VoucherBookLogic
        from bizora_core.ledger_logic import LedgerLogic
        from bizora_core.quotation_book_logic import QuotationBookLogic
        from bizora_core.sales_book_logic import SalesBookLogic

        voucher_logic_map = {
            "sales-book": SalesBookLogic,
            "sales-return-book": None,
            "purchase-book": None,
            "purchase-return-book": None,
            "quotation-book": QuotationBookLogic,
            "purchase-order-book": None,
        }
        logic_cls = voucher_logic_map.get(slug)
        if logic_cls is not None:
            logic = logic_cls(db)
            lookups["parties"] = logic.get_party_choices(company_id)
            lookups["products"] = logic.get_product_choices(company_id)
            lookups["categories"] = logic.get_category_choices(company_id)
        elif slug in {"sales-book", "purchase-book", "sales-return-book", "purchase-return-book"}:
            from bizora_core.purchase_book_logic import PurchaseBookLogic
            from bizora_core.purchase_return_book_logic import PurchaseReturnBookLogic
            from bizora_core.sales_return_book_logic import SalesReturnBookLogic

            fallback_map = {
                "purchase-book": PurchaseBookLogic,
                "purchase-return-book": PurchaseReturnBookLogic,
                "sales-return-book": SalesReturnBookLogic,
                "sales-book": SalesBookLogic,
            }
            logic = fallback_map[slug](db)
            lookups["parties"] = logic.get_party_choices(company_id)
            lookups["products"] = logic.get_product_choices(company_id)
            lookups["categories"] = logic.get_category_choices(company_id)

        ledger_logic = LedgerLogic(db)
        lookups["accounts"] = ledger_logic.get_general_ledger_accounts(company_id)
        lookups["ledger_debtors"] = [
            {"id": row.get("id"), "name": row.get("account_name", "")}
            for row in ledger_logic.get_debtor_ledger_options(company_id)
            if row.get("account_name")
        ]
        lookups["ledger_creditors"] = [
            {"id": row.get("id"), "name": row.get("account_name", "")}
            for row in ledger_logic.get_creditor_ledger_options(company_id)
            if row.get("account_name")
        ]
        lookups["ledger_cash_bank"] = [
            {"id": row.get("id"), "name": row.get("account_name", "")}
            for row in ledger_logic.get_cash_bank_ledger_options(company_id)
            if row.get("account_name")
        ]
        lookups["ledger_general"] = [
            {"id": row.get("id"), "name": row.get("account_name", "")}
            for row in ledger_logic.get_general_ledger_accounts(company_id)
            if row.get("account_name")
        ]

        ph = db._get_placeholder()
        salesman_rows = db.execute_query(
            f"""
            SELECT DISTINCT COALESCE(salesman, '') AS salesman
            FROM sales
            WHERE company_id = {ph}
              AND TRIM(COALESCE(salesman, '')) <> ''
            ORDER BY LOWER(salesman)
            """,
            (company_id,),
        ) or []
        lookups["salesmen"] = [
            str(row.get("salesman") or "").strip()
            for row in salesman_rows
            if str(row.get("salesman") or "").strip()
        ]

        creditor_rows = db.execute_query(
            f"""
            SELECT DISTINCT creditor_name
            FROM purchase_orders
            WHERE company_id = {ph}
              AND TRIM(COALESCE(creditor_name, '')) <> ''
            ORDER BY LOWER(creditor_name)
            """,
            (company_id,),
        ) or []
        lookups["creditors_po"] = _unique_sorted_names(creditor_rows, "creditor_name")
    except Exception as exc:
        print(f"[MOBILE-LOOKUPS] Local lookup build failed for {slug}: {exc}")
    return lookups


def build_supabase_report_lookups(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    slug: str,
) -> dict[str, Any]:
    """Build dropdown lookup data from synced Supabase tables."""
    lookups: dict[str, Any] = {
        "gst_options": GST_FILTER_OPTIONS,
        "financial_years": _financial_years(),
        "months": MONTH_OPTIONS,
        "pdc_statuses": PDC_STATUS_OPTIONS,
        "pdc_transaction_types": PDC_TRANSACTION_OPTIONS,
        "po_statuses": PO_STATUS_OPTIONS,
    }
    try:
        parties = fetch_table(
            "parties",
            company_id,
            select="id,name,party_type",
            limit=1000,
            order_col="name",
        )
        products = fetch_table(
            "products",
            company_id,
            select="id,name,barcode,category",
            limit=2000,
            order_col="name",
        )
        ledger_accounts = fetch_table(
            "ledger_accounts",
            company_id,
            select="id,account_name,account_type,group_name,is_active",
            limit=1000,
            order_col="account_name",
        )

        lookups["parties"] = [
            {
                "id": row.get("id"),
                "name": row.get("name", ""),
                "party_type": row.get("party_type", ""),
            }
            for row in parties
            if row.get("name")
        ]
        lookups["products"] = [
            {
                "id": row.get("id"),
                "name": row.get("name", ""),
                "barcode": row.get("barcode", ""),
                "category": row.get("category", ""),
            }
            for row in products
            if row.get("name")
        ]
        lookups["categories"] = sorted(
            {
                str(row.get("category") or "").strip()
                for row in products
                if str(row.get("category") or "").strip()
            },
            key=lambda value: value.lower(),
        )
        lookups["accounts"] = [
            {
                "id": row.get("id"),
                "account_name": row.get("account_name", ""),
            }
            for row in ledger_accounts
            if row.get("id") is not None and str(row.get("account_type") or "").lower() != "party"
        ]

        party_by_ledger = _party_by_ledger_account(parties, ledger_accounts)
        debtors: list[dict[str, Any]] = []
        creditors: list[dict[str, Any]] = []
        cash_bank: list[dict[str, Any]] = []
        general: list[dict[str, Any]] = []
        for account in ledger_accounts:
            if str(account.get("is_active", 1)) in {"0", "false", "False"}:
                continue
            account_id = account.get("id")
            account_name = str(account.get("account_name") or "").strip()
            if not account_name or account_id is None:
                continue
            account_type = str(account.get("account_type") or "").lower()
            option = {"id": account_id, "name": account_name}
            if account_type == "party":
                party = party_by_ledger.get(int(account_id))
                if not party:
                    continue
                party_type = str(party.get("party_type") or "")
                if party_type in {"Debitor", "Both"}:
                    debtors.append(option)
                if party_type in {"Creditor", "Both"}:
                    creditors.append(option)
            elif account_type == "cash_bank":
                cash_bank.append(option)
            else:
                general.append(option)

        lookups["ledger_debtors"] = debtors
        lookups["ledger_creditors"] = creditors
        lookups["ledger_cash_bank"] = cash_bank
        lookups["ledger_general"] = general

        sales_rows = fetch_table(
            "sales",
            company_id,
            select="salesman",
            limit=1000,
            order_col="invoice_date",
        )
        lookups["salesmen"] = sorted(
            {
                str(row.get("salesman") or "").strip()
                for row in sales_rows
                if str(row.get("salesman") or "").strip()
            },
            key=lambda value: value.lower(),
        )

        purchase_orders = fetch_table(
            "purchase_orders",
            company_id,
            select="creditor_name",
            limit=1000,
            order_col="date",
        )
        lookups["creditors_po"] = _unique_sorted_names(purchase_orders, "creditor_name")
    except Exception as exc:
        print(f"[MOBILE-LOOKUPS] Supabase lookup build failed for {slug}: {exc}")
    return lookups
