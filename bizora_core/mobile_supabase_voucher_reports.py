"""
Voucher book reports for Supabase-backed mobile web (desktop column parity).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from bizora_core.report_column_catalog import build_voucher_table_payload

VOUCHER_SLUG_CONFIG: dict[str, dict[str, str]] = {
    "sales-book": {
        "header_table": "sales",
        "item_table": "sales_items",
        "item_fk": "sale_id",
        "number_col": "invoice_number",
        "date_col": "invoice_date",
        "party_col": "party_id",
        "type_col": "sales_type",
        "settled_col": "amount_received",
    },
    "sales-return-book": {
        "header_table": "sales_returns",
        "item_table": "sales_return_items",
        "item_fk": "sales_return_id",
        "number_col": "return_no",
        "date_col": "return_date",
        "party_col": "party_id",
        "type_col": "return_type",
        "settled_col": "",
    },
    "purchase-book": {
        "header_table": "purchases",
        "item_table": "purchase_items",
        "item_fk": "purchase_id",
        "number_col": "purchase_number",
        "date_col": "purchase_date",
        "party_col": "party_id",
        "type_col": "purchase_type",
        "settled_col": "amount_paid",
    },
    "purchase-return-book": {
        "header_table": "purchase_returns",
        "item_table": "purchase_return_items",
        "item_fk": "purchase_return_id",
        "number_col": "return_no",
        "date_col": "return_date",
        "party_col": "party_id",
        "type_col": "return_type",
        "settled_col": "",
    },
    "quotation-book": {
        "header_table": "quotations",
        "item_table": "quotation_items",
        "item_fk": "quotation_id",
        "number_col": "quotation_no",
        "date_col": "quotation_date",
        "party_col": "party_id",
        "type_col": "quotation_type",
        "settled_col": "",
    },
}

MODE_METHODS = {
    "Bill Wise": "bill_wise",
    "Item Wise": "item_wise",
    "Tax Wise": "tax_wise",
    "Tax Summary": "tax_summary",
    "Credit / Pending": "credit_pending",
    "Party Wise": "party_wise",
    "Category Wise": "category_wise",
}


def run_voucher_book_report(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    slug: str,
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Run one voucher book report using synced Supabase tables."""
    config = VOUCHER_SLUG_CONFIG.get(slug)
    if config is None:
        return {"success": False, "message": f"Voucher book not supported: {slug}", "rows": []}

    mode = str(filters.get("report_mode") or "Bill Wise")
    method_key = MODE_METHODS.get(mode, "bill_wise")
    builders = {
        "bill_wise": _build_bill_wise_rows,
        "item_wise": _build_item_wise_rows,
        "tax_wise": _build_item_wise_rows,
        "tax_summary": _build_tax_summary_rows,
        "credit_pending": _build_credit_pending_rows,
        "party_wise": _build_party_wise_rows,
        "category_wise": _build_category_wise_rows,
    }
    builder = builders.get(method_key, _build_bill_wise_rows)
    rows = builder(fetch_table, client, company_id, config, filters)

    if not rows:
        return {
            "success": True,
            "message": "No records found for the selected filters.",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "data_source": "supabase",
        }

    table_payload = build_voucher_table_payload(rows, mode)
    return {
        "success": True,
        "message": "",
        "data_source": "supabase",
        **table_payload,
    }


def _parse_date(value: Any) -> str:
    return str(value or "")[:10]


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _in_date_range(value: Any, from_date: str, to_date: str) -> bool:
    text = _parse_date(value)
    if not text:
        return False
    if from_date and text < from_date:
        return False
    if to_date and text > to_date:
        return False
    return True


def _item_taxable(item: dict[str, Any]) -> float:
    net_value = _safe_float(item.get("net_value"))
    if net_value:
        return net_value
    qty = _safe_float(item.get("quantity") or item.get("qty"))
    rate = _safe_float(item.get("rate"))
    discount = _safe_float(item.get("discount") or item.get("discount_amount"))
    return max((qty * rate) - discount, 0.0)


def _item_tax_amount(item: dict[str, Any]) -> float:
    direct = _safe_float(item.get("tax_amount") or item.get("tax_total"))
    if direct:
        return direct
    return (
        _safe_float(item.get("cgst_amount"))
        + _safe_float(item.get("sgst_amount"))
        + _safe_float(item.get("igst_amount"))
        + _safe_float(item.get("cess_amount"))
    )


def _item_grand_total(item: dict[str, Any]) -> float:
    direct = _safe_float(item.get("grand_total") or item.get("total"))
    if direct:
        return direct
    return _item_taxable(item) + _item_tax_amount(item)


def _fetch_parties_map(fetch_table: Callable[..., list[dict[str, Any]]], company_id: int) -> dict[int, dict[str, Any]]:
    parties = fetch_table("parties", company_id, select="id,name,party_type", limit=2000, order_col="name")
    return {
        int(row["id"]): row
        for row in parties
        if row.get("id") is not None
    }


def _fetch_products_map(fetch_table: Callable[..., list[dict[str, Any]]], company_id: int) -> dict[int, dict[str, Any]]:
    products = fetch_table("products", company_id, select="id,name,barcode,category,hsn", limit=5000, order_col="name")
    return {
        int(row["id"]): row
        for row in products
        if row.get("id") is not None
    }


def _fetch_items_for_headers(
    client: Any,
    item_table: str,
    item_fk: str,
    header_ids: list[int],
) -> list[dict[str, Any]]:
    """Fetch line items for a batch of voucher header ids."""
    if not header_ids:
        return []
    rows: list[dict[str, Any]] = []
    for start in range(0, len(header_ids), 80):
        batch = header_ids[start : start + 80]
        try:
            response = (
                client.table(item_table)
                .select("*")
                .in_(item_fk, batch)
                .limit(5000)
                .execute()
            )
            rows.extend(response.data or [])
        except Exception as exc:
            message = str(exc)
            if "Could not find the table" in message or "does not exist" in message:
                print(
                    f"[MOBILE-SUPABASE] Item table '{item_table}' missing in Supabase. "
                    "Run: python setup_supabase.py && python sync_bulk_to_supabase.py"
                )
                return []
            raise
    return rows


def _load_voucher_context(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    company_id: int,
    config: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    """Load headers, grouped items, parties, and products for voucher reports."""
    headers = fetch_table(
        config["header_table"],
        company_id,
        limit=2000,
        order_col=config["date_col"],
    )
    header_ids = [int(row["id"]) for row in headers if row.get("id") is not None]
    items = _fetch_items_for_headers(client, config["item_table"], config["item_fk"], header_ids)
    party_map = _fetch_parties_map(fetch_table, company_id)
    product_map = _fetch_products_map(fetch_table, company_id)

    items_by_header: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        fk_value = item.get(config["item_fk"])
        if fk_value is not None:
            items_by_header[int(fk_value)].append(item)
    return headers, items_by_header, party_map, product_map


def _apply_common_filters(
    row: dict[str, Any],
    filters: dict[str, Any],
) -> bool:
    """Return True when a row passes party/product/category/search filters."""
    search = str(filters.get("search") or "").strip().lower()
    if search:
        haystack = " ".join(str(value or "") for value in row.values()).lower()
        if search not in haystack:
            return False

    party_filter = str(filters.get("party") or "").strip().lower()
    if party_filter and party_filter not in {"all parties", "all"}:
        party_name = str(row.get("party_name") or "").lower()
        if party_filter not in party_name:
            return False

    product_filter = str(filters.get("product") or "").strip().lower()
    if product_filter and product_filter not in {"all products", "all"}:
        product_name = str(row.get("product_name") or "").lower()
        if product_filter not in product_name:
            return False

    category_filter = str(filters.get("category") or "").strip().lower()
    if category_filter and category_filter not in {"all categories", "all"}:
        category_name = str(row.get("category") or "").lower()
        if category_filter not in category_name:
            return False

    gst_filter = str(filters.get("gst") or "").strip()
    if gst_filter:
        gst_text = str(row.get("gst_percent", row.get("tax_percent", "")))
        if gst_filter not in gst_text:
            return False

    if str(row.get("status") or "Active").lower() == "voided":
        return False
    return True


def _build_bill_wise_rows(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    company_id: int,
    config: dict[str, str],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Aggregate voucher headers with item totals like desktop bill-wise mode."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    headers, items_by_header, party_map, _product_map = _load_voucher_context(
        fetch_table, client, company_id, config
    )

    rows: list[dict[str, Any]] = []
    for header in headers:
        header_id = header.get("id")
        if header_id is None:
            continue
        if not _in_date_range(header.get(config["date_col"]), from_date, to_date):
            continue

        line_items = items_by_header.get(int(header_id), [])
        taxable = sum(_item_taxable(item) for item in line_items)
        discount = sum(_safe_float(item.get("discount") or item.get("discount_amount")) for item in line_items)
        tax_total = sum(_item_tax_amount(item) for item in line_items)
        cgst = sum(_safe_float(item.get("cgst_amount")) for item in line_items)
        sgst = sum(_safe_float(item.get("sgst_amount")) for item in line_items)
        igst = sum(_safe_float(item.get("igst_amount")) for item in line_items)
        cess = sum(_safe_float(item.get("cess_amount")) for item in line_items)
        grand_total = _safe_float(header.get("grand_total"))
        if not grand_total and line_items:
            grand_total = sum(_item_grand_total(item) for item in line_items)
        settled_col = config.get("settled_col") or ""
        settled = _safe_float(header.get(settled_col)) if settled_col else 0.0
        party_id = header.get(config["party_col"])
        party_row = party_map.get(int(party_id), {}) if party_id is not None else {}
        party_name = str(party_row.get("name") or header.get("customer_name") or "")

        row = {
            "voucher_no": header.get(config["number_col"], ""),
            "voucher_date": _parse_date(header.get(config["date_col"])),
            "party_name": party_name,
            "voucher_subtype": str(header.get(config.get("type_col", "")) or ""),
            "nature": str(header.get("nature") or ""),
            "taxable_amount": round(taxable, 2),
            "cgst_amount": round(cgst, 2),
            "sgst_amount": round(sgst, 2),
            "igst_amount": round(igst, 2),
            "cess_amount": round(cess, 2),
            "tax_total": round(tax_total, 2),
            "discount_total": round(discount, 2),
            "round_off": round(_safe_float(header.get("round_off")), 2),
            "grand_total": round(grand_total, 2),
            "settled_amount": round(settled, 2),
            "balance_amount": round(max(grand_total - settled, 0.0), 2),
            "status": header.get("status", "Active"),
        }
        if _apply_common_filters(row, filters):
            rows.append(row)
    return rows


def _build_item_wise_rows(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    company_id: int,
    config: dict[str, str],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return item-level rows joined to voucher headers."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    headers, items_by_header, party_map, product_map = _load_voucher_context(
        fetch_table, client, company_id, config
    )
    header_by_id = {int(row["id"]): row for row in headers if row.get("id") is not None}

    rows: list[dict[str, Any]] = []
    for header_id, line_items in items_by_header.items():
        header = header_by_id.get(header_id)
        if not header:
            continue
        if not _in_date_range(header.get(config["date_col"]), from_date, to_date):
            continue

        party_id = header.get(config["party_col"])
        party_name = str(party_map.get(int(party_id), {}).get("name") or "") if party_id is not None else ""

        for item in line_items:
            product_id = item.get("product_id")
            product = product_map.get(int(product_id), {}) if product_id is not None else {}
            taxable = _item_taxable(item)
            tax_amount = _item_tax_amount(item)
            row = {
                "voucher_no": header.get(config["number_col"], ""),
                "voucher_date": _parse_date(header.get(config["date_col"])),
                "party_name": party_name,
                "product_name": product.get("name") or item.get("product_name") or "",
                "barcode": product.get("barcode") or item.get("barcode") or "",
                "hsn": item.get("hsn") or product.get("hsn") or "",
                "quantity": round(_safe_float(item.get("quantity") or item.get("qty")), 3),
                "rate": round(_safe_float(item.get("rate")), 2),
                "gross_value": round(_safe_float(item.get("gross_value") or (taxable + _safe_float(item.get("discount")))), 2),
                "discount": round(_safe_float(item.get("discount") or item.get("discount_amount")), 2),
                "taxable_amount": round(taxable, 2),
                "tax_percent": round(_safe_float(item.get("tax_percent")), 2),
                "cgst": round(_safe_float(item.get("cgst")), 2),
                "sgst": round(_safe_float(item.get("sgst")), 2),
                "igst": round(_safe_float(item.get("igst")), 2),
                "cess": round(_safe_float(item.get("cess")), 2),
                "cgst_amount": round(_safe_float(item.get("cgst_amount")), 2),
                "sgst_amount": round(_safe_float(item.get("sgst_amount")), 2),
                "igst_amount": round(_safe_float(item.get("igst_amount")), 2),
                "cess_amount": round(_safe_float(item.get("cess_amount")), 2),
                "tax_amount": round(tax_amount, 2),
                "grand_total": round(_item_grand_total(item), 2),
                "category": product.get("category") or item.get("category") or "",
                "nature": str(header.get("nature") or ""),
                "status": header.get("status", "Active"),
            }
            if _apply_common_filters(row, filters):
                rows.append(row)
    return rows


def _build_tax_summary_rows(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    company_id: int,
    config: dict[str, str],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Aggregate tax totals by rate like desktop tax summary mode."""
    item_rows = _build_item_wise_rows(fetch_table, client, company_id, config, filters)
    buckets: dict[tuple[Any, ...], dict[str, Any]] = {}

    for row in item_rows:
        key = (
            row.get("tax_percent"),
            row.get("cgst"),
            row.get("sgst"),
            row.get("igst"),
            row.get("cess"),
            row.get("nature", ""),
        )
        bucket = buckets.setdefault(
            key,
            {
                "tax_percent": row.get("tax_percent"),
                "cgst": row.get("cgst"),
                "sgst": row.get("sgst"),
                "igst": row.get("igst"),
                "cess": row.get("cess"),
                "nature": row.get("nature", ""),
                "bill_count": 0,
                "taxable_amount": 0.0,
                "cgst_amount": 0.0,
                "sgst_amount": 0.0,
                "igst_amount": 0.0,
                "cess_amount": 0.0,
                "tax_amount": 0.0,
                "grand_total": 0.0,
                "_vouchers": set(),
            },
        )
        bucket["taxable_amount"] += _safe_float(row.get("taxable_amount"))
        bucket["cgst_amount"] += _safe_float(row.get("cgst_amount"))
        bucket["sgst_amount"] += _safe_float(row.get("sgst_amount"))
        bucket["igst_amount"] += _safe_float(row.get("igst_amount"))
        bucket["cess_amount"] += _safe_float(row.get("cess_amount"))
        bucket["tax_amount"] += _safe_float(row.get("tax_amount"))
        bucket["grand_total"] += _safe_float(row.get("grand_total"))
        bucket["_vouchers"].add(row.get("voucher_no"))

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        rows.append(
            {
                "tax_percent": bucket["tax_percent"],
                "cgst": bucket["cgst"],
                "sgst": bucket["sgst"],
                "igst": bucket["igst"],
                "cess": bucket["cess"],
                "nature": bucket["nature"],
                "bill_count": len(bucket["_vouchers"]),
                "taxable_amount": round(bucket["taxable_amount"], 2),
                "cgst_amount": round(bucket["cgst_amount"], 2),
                "sgst_amount": round(bucket["sgst_amount"], 2),
                "igst_amount": round(bucket["igst_amount"], 2),
                "cess_amount": round(bucket["cess_amount"], 2),
                "tax_amount": round(bucket["tax_amount"], 2),
                "grand_total": round(bucket["grand_total"], 2),
            }
        )
    return rows


def _build_credit_pending_rows(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    company_id: int,
    config: dict[str, str],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return credit or pending bills like desktop credit mode."""
    rows = _build_bill_wise_rows(fetch_table, client, company_id, config, filters)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        subtype = str(row.get("voucher_subtype") or "").lower()
        balance = _safe_float(row.get("balance_amount"))
        if "credit" in subtype or balance > 0:
            status = "Pending" if balance > 0 else "Cleared"
            filtered.append({**row, "due_date": "", "status": status})
    return filtered


def _build_party_wise_rows(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    company_id: int,
    config: dict[str, str],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Aggregate bill totals by party."""
    bill_rows = _build_bill_wise_rows(fetch_table, client, company_id, config, filters)
    _, _, party_map, _ = _load_voucher_context(fetch_table, client, company_id, config)
    party_type_by_name = {
        str(row.get("name") or ""): str(row.get("party_type") or "")
        for row in party_map.values()
    }

    buckets: dict[str, dict[str, Any]] = {}
    for row in bill_rows:
        party_name = str(row.get("party_name") or "Unknown")
        bucket = buckets.setdefault(
            party_name,
            {
                "party_name": party_name,
                "party_type": party_type_by_name.get(party_name, ""),
                "bill_count": 0,
                "taxable_amount": 0.0,
                "tax_total": 0.0,
                "discount_total": 0.0,
                "grand_total": 0.0,
                "settled_amount": 0.0,
                "balance_amount": 0.0,
            },
        )
        bucket["bill_count"] += 1
        bucket["taxable_amount"] += _safe_float(row.get("taxable_amount"))
        bucket["tax_total"] += _safe_float(row.get("tax_total"))
        bucket["discount_total"] += _safe_float(row.get("discount_total"))
        bucket["grand_total"] += _safe_float(row.get("grand_total"))
        bucket["settled_amount"] += _safe_float(row.get("settled_amount"))
        bucket["balance_amount"] += _safe_float(row.get("balance_amount"))

    return [
        {
            "party_name": name,
            "party_type": values["party_type"],
            "bill_count": values["bill_count"],
            "taxable_amount": round(values["taxable_amount"], 2),
            "tax_total": round(values["tax_total"], 2),
            "discount_total": round(values["discount_total"], 2),
            "grand_total": round(values["grand_total"], 2),
            "settled_amount": round(values["settled_amount"], 2),
            "balance_amount": round(values["balance_amount"], 2),
        }
        for name, values in sorted(buckets.items(), key=lambda item: item[0].lower())
    ]


def _build_category_wise_rows(
    fetch_table: Callable[..., list[dict[str, Any]]],
    client: Any,
    company_id: int,
    config: dict[str, str],
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Aggregate item totals by product category."""
    item_rows = _build_item_wise_rows(fetch_table, client, company_id, config, filters)
    buckets: dict[str, dict[str, Any]] = {}

    for row in item_rows:
        category = str(row.get("category") or "").strip() or "Uncategorized"
        bucket = buckets.setdefault(
            category,
            {
                "category": category,
                "bill_count": 0,
                "quantity_total": 0.0,
                "taxable_amount": 0.0,
                "tax_total": 0.0,
                "discount_total": 0.0,
                "grand_total": 0.0,
                "_vouchers": set(),
            },
        )
        bucket["quantity_total"] += _safe_float(row.get("quantity"))
        bucket["taxable_amount"] += _safe_float(row.get("taxable_amount"))
        bucket["tax_total"] += _safe_float(row.get("tax_amount"))
        bucket["discount_total"] += _safe_float(row.get("discount"))
        bucket["grand_total"] += _safe_float(row.get("grand_total"))
        bucket["_vouchers"].add(row.get("voucher_no"))
        bucket["bill_count"] = len(bucket["_vouchers"])

    return [
        {
            "category": category,
            "bill_count": values["bill_count"],
            "quantity_total": round(values["quantity_total"], 3),
            "taxable_amount": round(values["taxable_amount"], 2),
            "tax_total": round(values["tax_total"], 2),
            "discount_total": round(values["discount_total"], 2),
            "grand_total": round(values["grand_total"], 2),
        }
        for category, values in sorted(buckets.items(), key=lambda item: item[0].lower())
    ]
