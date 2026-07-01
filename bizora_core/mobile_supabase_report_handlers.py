"""
Cloud (Supabase) report handlers that return desktop-shaped row data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Callable

from bizora_core.mobile_report_columns import build_slug_table_payload
from bizora_core.mobile_supabase_ledger import build_account_summary, filter_accounts_for_view

_QUOTE_TYPES = frozenset(
    {"quotation", "estimate", "quote", "Quotation", "Estimate", "Quote"}
)


def _parse_date(value: Any) -> str:
    return str(value or "")[:10]


def _in_range(value: Any, from_date: str, to_date: str) -> bool:
    text = _parse_date(value)
    if not text:
        return False
    if from_date and text < from_date:
        return False
    if to_date and text > to_date:
        return False
    return True


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _finish(slug: str, rows: list[dict[str, Any]], filters: dict[str, Any], handler: str) -> dict[str, Any]:
    """Attach desktop column metadata to one cloud report result."""
    table_payload = build_slug_table_payload(
        slug,
        rows,
        handler=handler,
        report_mode=filters.get("report_mode"),
        filters=filters,
    )
    return {
        "success": True,
        "message": "" if rows else "No records found for the selected filters.",
        "data_source": "supabase",
        **table_payload,
    }


def run_cloud_day_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build Day Book rows using desktop Cash/Bank Day Book logic."""
    from bizora_core.mobile_supabase_day_book import run_day_book_from_supabase

    return run_day_book_from_supabase(fetch_table, company_id, filters)


def run_cloud_cash_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build Cash Book rows matching desktop columns."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))

    accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select="id,account_name,account_type",
        limit=2000,
    )
    cash_accounts = [
        row for row in accounts
        if str(row.get("account_type") or "").lower() == "cash_bank"
    ]
    if not cash_accounts:
        cash_accounts = [
            row for row in accounts
            if "cash" in str(row.get("account_name") or "").lower()
        ]

    cash_ids = {int(row["id"]) for row in cash_accounts if row.get("id") is not None}
    account_names = {
        int(row["id"]): str(row.get("account_name") or "")
        for row in accounts
        if row.get("id") is not None
    }

    entries = fetch_table(
        "ledger_entries",
        company_id,
        select="voucher_date,voucher_no,voucher_type,account_id,debit,credit,narration",
        limit=15000,
        order_col="voucher_date",
    )

    cash_entries = [
        row for row in entries
        if row.get("account_id") is not None
        and int(row["account_id"]) in cash_ids
        and _in_range(row.get("voucher_date"), from_date, to_date)
        and str(row.get("voucher_type") or "") not in _QUOTE_TYPES
    ]

    by_voucher: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in entries:
        if str(row.get("voucher_type") or "") in _QUOTE_TYPES:
            continue
        key = (str(row.get("voucher_no") or ""), str(row.get("voucher_type") or ""))
        by_voucher[key].append(row)

    running = 0.0
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(
        sorted(cash_entries, key=lambda item: (_parse_date(item.get("voucher_date")), str(item.get("voucher_no") or ""))),
        start=1,
    ):
        voucher_key = (str(entry.get("voucher_no") or ""), str(entry.get("voucher_type") or ""))
        contra_name = ""
        for sibling in by_voucher.get(voucher_key, []):
            sibling_id = sibling.get("account_id")
            if sibling_id is not None and int(sibling_id) not in cash_ids:
                contra_name = account_names.get(int(sibling_id), "")
                if contra_name:
                    break

        debit = _safe_float(entry.get("debit"))
        credit = _safe_float(entry.get("credit"))
        running = round(running + debit - credit, 2)
        rows.append(
            {
                "sl_no": index,
                "voucher_date": _parse_date(entry.get("voucher_date")),
                "voucher_no": entry.get("voucher_no", ""),
                "voucher_type": str(entry.get("voucher_type") or "").replace("_", " ").title(),
                "particulars": contra_name or "Unknown",
                "narration": entry.get("narration", ""),
                "debit": round(debit, 2),
                "credit": round(credit, 2),
                "running_balance": running,
            }
        )

    return _finish("cash-book", rows, filters, "cash_book")


def run_cloud_journal_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Return journal voucher lines with desktop columns."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))

    accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select="id,account_name",
        limit=2000,
    )
    account_names = {
        int(row["id"]): str(row.get("account_name") or "")
        for row in accounts
        if row.get("id") is not None
    }

    entries = fetch_table(
        "ledger_entries",
        company_id,
        select="voucher_date,voucher_no,voucher_type,account_id,debit,credit,narration",
        limit=15000,
        order_col="voucher_date",
    )

    rows = []
    for entry in entries:
        if not _in_range(entry.get("voucher_date"), from_date, to_date):
            continue
        if "journal" not in str(entry.get("voucher_type") or "").lower():
            continue
        account_id = entry.get("account_id")
        rows.append(
            {
                "voucher_date": _parse_date(entry.get("voucher_date")),
                "voucher_no": entry.get("voucher_no", ""),
                "account_name": account_names.get(int(account_id), "") if account_id is not None else "",
                "debit": round(_safe_float(entry.get("debit")), 2),
                "credit": round(_safe_float(entry.get("credit")), 2),
                "narration": entry.get("narration", ""),
            }
        )

    return _finish("journal-book", rows, filters, "journal_book")


def run_cloud_ledger_summary(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Run ledger summary views with the same LedgerLogic layer as desktop."""
    from bizora_core.mobile_supabase_financial_cloud import run_cloud_ledger_desktop_parity

    return run_cloud_ledger_desktop_parity(fetch_table, company_id, filters)


def _split_opening_closing(row: dict[str, Any]) -> dict[str, Any]:
    """Convert opening/closing balance + Dr/Cr into trial balance debit/credit columns."""
    opening = _safe_float(row.get("opening_balance"))
    opening_type = str(row.get("opening_balance_type") or "Dr")
    closing = _safe_float(row.get("closing_balance"))
    closing_type = str(row.get("closing_balance_type") or "Dr")
    return {
        "sl_no": row.get("sl_no"),
        "account_name": row.get("account_name", ""),
        "account_type": row.get("account_type", ""),
        "opening_debit": opening if opening_type == "Dr" and opening else 0.0,
        "opening_credit": opening if opening_type == "Cr" and opening else 0.0,
        "period_debit": _safe_float(row.get("period_debit")),
        "period_credit": _safe_float(row.get("period_credit")),
        "closing_debit": closing if closing_type == "Dr" and closing else 0.0,
        "closing_credit": closing if closing_type == "Cr" and closing else 0.0,
    }


def run_cloud_trial_balance(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build trial balance rows from synced ledger accounts and entries."""
    summary = run_cloud_ledger_summary(fetch_table, company_id, {**filters, "ledger_view": "General"})
    rows = []
    for index, row in enumerate(summary.get("rows") or [], start=1):
        shaped = _split_opening_closing({**row, "sl_no": index})
        account_type = str(filters.get("account_type") or "All")
        if account_type != "All" and account_type.lower() not in str(shaped.get("account_type") or "").lower():
            continue
        rows.append(shaped)
    return _finish("trial-balance", rows, filters, "trial_balance")


def run_cloud_products_report(
    slug: str,
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
    handler: str,
) -> dict[str, Any]:
    """Build stock/price list style rows from synced products."""
    products = fetch_table(
        "products",
        company_id,
        select="id,barcode,name,category,unit,quantity,sale_price,purchase_rate,wholesale_rate,mrp",
        limit=5000,
        order_col="name",
    )
    search = str(filters.get("search") or "").strip().lower()
    category = str(filters.get("category") or "").strip().lower()
    rows: list[dict[str, Any]] = []
    for index, product in enumerate(products, start=1):
        if search and search not in str(product).lower():
            continue
        if category and category not in str(product.get("category") or "").lower():
            continue
        qty = _safe_float(product.get("quantity"))
        rate = _safe_float(product.get("sale_price") or product.get("purchase_rate"))
        row = {
            "sl_no": index,
            "barcode": product.get("barcode", ""),
            "product_name": product.get("name", ""),
            "category": product.get("category", ""),
            "unit": product.get("unit", ""),
            "current_qty": round(qty, 3),
            "rate": round(rate, 2),
            "stock_value": round(qty * rate, 2),
            "item_code": product.get("barcode", ""),
            "current_stock": round(qty, 3),
            "purchase_rate": round(_safe_float(product.get("purchase_rate")), 2),
            "sales_rate": round(_safe_float(product.get("sale_price")), 2),
            "wholesale_rate": round(_safe_float(product.get("wholesale_rate")), 2),
            "mrp": round(_safe_float(product.get("mrp")), 2),
        }
        rows.append(row)
    return _finish(slug, rows, filters, handler)


def run_cloud_bill_history(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Merge sales/purchase/return headers into one bill history list."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    voucher_type = str(filters.get("voucher_type") or "All")
    parties = fetch_table("parties", company_id, select="id,name", limit=2000)
    party_names = {int(row["id"]): str(row.get("name") or "") for row in parties if row.get("id") is not None}

    rows: list[dict[str, Any]] = []

    def append_rows(source: str, table: str, number_col: str, date_col: str, type_label: str) -> None:
        if voucher_type not in ("All", type_label):
            return
        for header in fetch_table(table, company_id, limit=3000, order_col=date_col):
            if not _in_range(header.get(date_col), from_date, to_date):
                continue
            party_id = header.get("party_id")
            rows.append(
                {
                    "voucher_date": _parse_date(header.get(date_col)),
                    "bill_no": header.get(number_col, ""),
                    "voucher_type": type_label,
                    "party_name": party_names.get(int(party_id), "") if party_id is not None else "",
                    "grand_total": round(_safe_float(header.get("grand_total")), 2),
                    "status": header.get("status", "Active"),
                }
            )

    append_rows("sales", "sales", "invoice_number", "invoice_date", "Sales")
    append_rows("purchases", "purchases", "purchase_number", "purchase_date", "Purchase")
    append_rows("sales_returns", "sales_returns", "return_no", "return_date", "Sales Return")
    append_rows("purchase_returns", "purchase_returns", "return_no", "return_date", "Purchase Return")
    rows.sort(key=lambda item: (item.get("voucher_date") or "", item.get("bill_no") or ""))
    return _finish("bill-history", rows, filters, "bill_history")


def run_cloud_pdc_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Return PDC register rows from Supabase."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    parties = fetch_table("parties", company_id, select="id,name", limit=2000)
    party_names = {int(row["id"]): str(row.get("name") or "") for row in parties if row.get("id") is not None}
    rows = []
    for row in fetch_table("pdc_register", company_id, limit=3000, order_col="cheque_date"):
        if not _in_range(row.get("cheque_date"), from_date, to_date):
            continue
        tx_type = str(filters.get("transaction_type") or "All")
        if tx_type != "All" and tx_type != str(row.get("transaction_type") or ""):
            continue
        status = str(filters.get("status") or "All")
        if status != "All" and status != str(row.get("status") or ""):
            continue
        party_id = row.get("party_id")
        party_name = party_names.get(int(party_id), "") if party_id is not None else str(row.get("account_name") or "")
        rows.append(
            {
                "id": row.get("id"),
                "transaction_type": row.get("transaction_type", ""),
                "party_name": party_name,
                "cheque_date": _parse_date(row.get("cheque_date")),
                "cheque_number": row.get("cheque_number", ""),
                "amount": round(_safe_float(row.get("amount")), 2),
                "status": row.get("status", ""),
            }
        )
    return _finish("pdc-book", rows, filters, "pdc_book")


def run_cloud_purchase_order_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Return purchase order headers from Supabase."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    status_filter = str(filters.get("status") or "All")
    rows = []
    for row in fetch_table("purchase_orders", company_id, limit=3000, order_col="date"):
        if not _in_range(row.get("date"), from_date, to_date):
            continue
        if status_filter != "All" and status_filter != str(row.get("status") or ""):
            continue
        rows.append(
            {
                "date": _parse_date(row.get("date")),
                "po_number": row.get("po_number", ""),
                "creditor_name": row.get("creditor_name", ""),
                "status": row.get("status", ""),
                "grand_total": round(_safe_float(row.get("grand_total")), 2),
            }
        )
    return _finish("purchase-order-book", rows, filters, "purchase_order_book")


def run_cloud_daily_stock_register(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Return stock movement rows from Supabase."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    products = fetch_table("products", company_id, select="id,name", limit=5000)
    product_names = {int(row["id"]): str(row.get("name") or "") for row in products if row.get("id") is not None}
    movement_type = str(filters.get("voucher_type") or "All")
    rows = []
    running: dict[int, float] = defaultdict(float)
    for row in fetch_table(
        "stock_movements",
        company_id,
        select="product_id,movement_type,quantity,created_at",
        limit=5000,
        order_col="created_at",
    ):
        move_date = _parse_date(row.get("created_at"))
        if not _in_range(move_date, from_date, to_date):
            continue
        if movement_type != "All" and movement_type != str(row.get("movement_type") or ""):
            continue
        product_id = row.get("product_id")
        qty = _safe_float(row.get("quantity"))
        if product_id is not None:
            running[int(product_id)] = round(running[int(product_id)] + qty, 3)
        rows.append(
            {
                "movement_date": move_date,
                "product_name": product_names.get(int(product_id), "") if product_id is not None else "",
                "movement_type": row.get("movement_type", ""),
                "qty_in": round(qty, 3) if qty > 0 else 0.0,
                "qty_out": round(abs(qty), 3) if qty < 0 else 0.0,
                "balance_qty": running.get(int(product_id), 0.0) if product_id is not None else 0.0,
            }
        )
    return _finish("daily-stock-register", rows, filters, "daily_stock_register")


def run_cloud_gst_report(
    slug: str,
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
    handler: str,
) -> dict[str, Any]:
    """Return simplified GST sales/purchase rows from synced headers."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    if slug == "gst-purchase-report":
        table, number_col, date_col = "purchases", "purchase_number", "purchase_date"
    else:
        table, number_col, date_col = "sales", "invoice_number", "invoice_date"
    parties = fetch_table("parties", company_id, select="id,name", limit=2000)
    party_names = {int(row["id"]): str(row.get("name") or "") for row in parties if row.get("id") is not None}
    rows = []
    for header in fetch_table(table, company_id, limit=3000, order_col=date_col):
        if not _in_range(header.get(date_col), from_date, to_date):
            continue
        party_id = header.get("party_id")
        rows.append(
            {
                "voucher_date": _parse_date(header.get(date_col)),
                "voucher_no": header.get(number_col, ""),
                "party_name": party_names.get(int(party_id), "") if party_id is not None else "",
                "taxable_amount": round(_safe_float(header.get("sub_total")), 2),
                "tax_total": round(_safe_float(header.get("tax_total")), 2),
                "grand_total": round(_safe_float(header.get("grand_total")), 2),
            }
        )
    return _finish(slug, rows, filters, handler)


def run_cloud_profit_and_loss_handler(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Desktop-parity Profit and Loss for cloud mode."""
    from bizora_core.mobile_supabase_financial_cloud import run_cloud_profit_and_loss

    return run_cloud_profit_and_loss(fetch_table, company_id, filters)


def run_cloud_balance_sheet_handler(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Desktop-parity Balance Sheet for cloud mode."""
    from bizora_core.mobile_supabase_financial_cloud import run_cloud_balance_sheet

    return run_cloud_balance_sheet(fetch_table, company_id, filters)


def run_cloud_handler_report(
    handler: str,
    slug: str,
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    """Dispatch one cloud report handler; None when not implemented."""
    handlers = {
        "day_book": lambda: run_cloud_day_book(fetch_table, company_id, filters),
        "cash_book": lambda: run_cloud_cash_book(fetch_table, company_id, filters),
        "journal_book": lambda: run_cloud_journal_book(fetch_table, company_id, filters),
        "ledger": lambda: run_cloud_ledger_summary(fetch_table, company_id, filters),
        "trial_balance": lambda: run_cloud_trial_balance(fetch_table, company_id, filters),
        "bill_history": lambda: run_cloud_bill_history(fetch_table, company_id, filters),
        "pdc_book": lambda: run_cloud_pdc_book(fetch_table, company_id, filters),
        "purchase_order_book": lambda: run_cloud_purchase_order_book(fetch_table, company_id, filters),
        "daily_stock_register": lambda: run_cloud_daily_stock_register(fetch_table, company_id, filters),
        "stock_report": lambda: run_cloud_products_report(slug, fetch_table, company_id, filters, handler),
        "stock_value": lambda: run_cloud_products_report(slug, fetch_table, company_id, filters, handler),
        "price_list": lambda: run_cloud_products_report(slug, fetch_table, company_id, filters, handler),
        "gst_sales_report": lambda: run_cloud_gst_report(slug, fetch_table, company_id, filters, handler),
        "gst_purchase_report": lambda: run_cloud_gst_report(slug, fetch_table, company_id, filters, handler),
        "profit_and_loss": lambda: run_cloud_profit_and_loss_handler(fetch_table, company_id, filters),
        "balance_sheet": lambda: run_cloud_balance_sheet_handler(fetch_table, company_id, filters),
    }
    runner = handlers.get(handler)
    if runner is None:
        return None
    return runner()
