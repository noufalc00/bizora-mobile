"""
Small A4 HTML helpers for non-sales transaction vouchers.

The invoice engine owns physical printing; this module only prepares escaped
HTML and shared print settings for purchase/return/payment style documents.
"""

from __future__ import annotations

import html
import json
from typing import Any, Mapping, Sequence


def text_value(value: Any) -> str:
    """Return a safe display string for nullable values."""
    return "" if value is None else str(value)


def escape_html(value: Any) -> str:
    """Escape dynamic voucher text before rendering it into HTML."""
    return html.escape(text_value(value), quote=True)


def money_text(value: Any) -> str:
    """Format a numeric voucher amount with two decimals."""
    try:
        return f"{float(value or 0.0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def company_print_data(active_company: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize company fields used by A4 invoice and voucher HTML."""
    company = dict(active_company or {})
    return {
        "company_name": company.get("business_name") or company.get("company_name") or company.get("name") or "Company",
        "business_name": company.get("business_name") or company.get("company_name") or company.get("name") or "Company",
        "company_gstin": company.get("gstin") or "",
        "gstin": company.get("gstin") or "",
        "company_address": company.get("address") or "",
        "address": company.get("address") or "",
        "phone": company.get("phone_number") or company.get("mobile") or "",
        "email": company.get("email") or "",
        "state": company.get("state") or "",
        "pincode": company.get("pincode") or "",
        "logo_path": company.get("logo_path") or "",
        "signature_path": company.get("signature_path") or "",
    }


def settings_metadata(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return metadata embedded in saved print layout coordinates."""
    raw_coordinates = text_value((settings or {}).get("layout_coordinates")).strip()
    if not raw_coordinates:
        return {}
    try:
        coordinates = json.loads(raw_coordinates)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(coordinates, dict):
        return {}
    metadata = coordinates.get("__settings__", {})
    return metadata if isinstance(metadata, dict) else {}


def saved_a4_printer_name(settings: Mapping[str, Any] | None) -> str:
    """Return the saved normal/A4 printer name when one exists."""
    safe_settings = settings or {}
    metadata = settings_metadata(safe_settings)
    for key in ("normal_printer_name", "a4_printer_name", "printer_name"):
        value = metadata.get(key) or safe_settings.get(key)
        if text_value(value).strip():
            return text_value(value).strip()
    return ""


def paper_size_from_settings(settings: Mapping[str, Any] | None) -> str:
    """Return the selected A4 engine paper size."""
    safe_settings = settings or {}
    metadata = settings_metadata(safe_settings)
    for key in ("a4_paper_size", "paper_size", "default_format"):
        value = text_value(metadata.get(key) or safe_settings.get(key)).strip().upper()
        if value in {"A4", "A5"}:
            return value
    return "A4"


def generate_transaction_voucher_html(
    company_data: Mapping[str, Any],
    voucher_data: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    settings: Mapping[str, Any] | None = None,
) -> str:
    """Generate compact A4 HTML for purchase/sales return style vouchers."""
    theme_color = text_value((settings or {}).get("a4_theme_color") or "#1D4ED8")
    if not (len(theme_color) == 7 and theme_color.startswith("#")):
        theme_color = "#1D4ED8"
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td class='text-left'>{escape_html(item.get('product_name') or item.get('name'))}</td>"
            f"<td>{escape_html(item.get('hsn'))}</td>"
            f"<td>{money_text(item.get('quantity'))}</td>"
            f"<td>{money_text(item.get('rate'))}</td>"
            f"<td>{money_text(item.get('net_value'))}</td>"
            f"<td>{money_text(item.get('tax_amount'))}</td>"
            f"<td>{money_text(item.get('grand_total'))}</td>"
            "</tr>"
        )
    return _base_voucher_html(
        company_data=company_data,
        title=voucher_data.get("voucher_title") or "Voucher",
        theme_color=theme_color,
        party_label=voucher_data.get("party_label") or "Party",
        party_name=voucher_data.get("party_name") or "",
        meta_rows=[
            ("Voucher No", voucher_data.get("voucher_no") or ""),
            ("Date", voucher_data.get("voucher_date") or ""),
            ("Type", voucher_data.get("voucher_type") or ""),
            ("Reference", voucher_data.get("reference") or ""),
        ],
        table_html=(
            "<table class='items'>"
            "<thead><tr><th>Sl</th><th class='text-left'>Item</th><th>HSN</th>"
            "<th>Qty</th><th>Rate</th><th>Net</th><th>Tax</th><th>Total</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        ),
        totals=[
            ("Sub Total", voucher_data.get("sub_total")),
            ("Discount", voucher_data.get("discount_total")),
            ("Tax", voucher_data.get("tax_total")),
            ("Round Off", voucher_data.get("round_off")),
            ("Grand Total", voucher_data.get("grand_total")),
        ],
        narration=voucher_data.get("narration") or "",
    )


def generate_payment_receipt_html(
    company_data: Mapping[str, Any],
    voucher_data: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    settings: Mapping[str, Any] | None = None,
) -> str:
    """Generate compact A4 HTML for cash/bank receipt and payment vouchers."""
    theme_color = text_value((settings or {}).get("a4_theme_color") or "#047857")
    if not (len(theme_color) == 7 and theme_color.startswith("#")):
        theme_color = "#047857"
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td class='text-left'>{escape_html(item.get('account_name'))}</td>"
            f"<td>{escape_html(item.get('towards_voucher_no'))}</td>"
            f"<td>{money_text(item.get('amount'))}</td>"
            f"<td>{money_text(item.get('discount'))}</td>"
            "</tr>"
        )
    return _base_voucher_html(
        company_data=company_data,
        title=voucher_data.get("voucher_title") or "Payment / Receipt",
        theme_color=theme_color,
        party_label=voucher_data.get("party_label") or "Account",
        party_name=voucher_data.get("party_name") or "",
        meta_rows=[
            ("Voucher No", voucher_data.get("voucher_no") or ""),
            ("Date", voucher_data.get("voucher_date") or ""),
            ("Mode", voucher_data.get("payment_mode") or ""),
            ("Reference", voucher_data.get("reference") or ""),
        ],
        table_html=(
            "<table class='items'>"
            "<thead><tr><th>Sl</th><th class='text-left'>Account</th><th>Ref / Bill</th>"
            "<th>Amount</th><th>Discount</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        ),
        totals=[
            ("Amount", voucher_data.get("total_amount")),
            ("Discount", voucher_data.get("total_discount")),
            ("Net Amount", voucher_data.get("net_amount")),
        ],
        narration=voucher_data.get("narration") or "",
    )


def _base_voucher_html(
    company_data: Mapping[str, Any],
    title: Any,
    theme_color: str,
    party_label: Any,
    party_name: Any,
    meta_rows: Sequence[tuple[Any, Any]],
    table_html: str,
    totals: Sequence[tuple[Any, Any]],
    narration: Any,
) -> str:
    """Compose the common A4 voucher shell."""
    company_name = company_data.get("company_name") or company_data.get("business_name") or "Company"
    address_parts = [
        company_data.get("company_address") or company_data.get("address") or "",
        company_data.get("state") or "",
        company_data.get("pincode") or "",
    ]
    address_text = ", ".join(part for part in address_parts if text_value(part).strip())
    contact_parts = [
        f"GSTIN: {company_data.get('company_gstin') or company_data.get('gstin')}"
        if company_data.get("company_gstin") or company_data.get("gstin")
        else "",
        f"Phone: {company_data.get('phone')}" if company_data.get("phone") else "",
        f"Email: {company_data.get('email')}" if company_data.get("email") else "",
    ]
    meta_html = "".join(
        f"<div><span>{escape_html(label)}</span><strong>{escape_html(value)}</strong></div>"
        for label, value in meta_rows
        if text_value(value).strip()
    )
    totals_html = "".join(
        f"<tr><td>{escape_html(label)}</td><td>{money_text(value)}</td></tr>"
        for label, value in totals
        if text_value(value).strip() and abs(float(money_text(value))) > 0.0001
    )
    narration_html = (
        f"<div class='narration'><strong>Narration:</strong> {escape_html(narration)}</div>"
        if text_value(narration).strip()
        else ""
    )
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{ size: A4; margin: 12mm; }}
    body {{ color: #111827; font-family: Arial, sans-serif; font-size: 10pt; margin: 0; }}
    .sheet {{ border: 1px solid #d1d5db; min-height: 268mm; padding: 14px; }}
    .header {{ border-bottom: 3px solid {theme_color}; padding-bottom: 10px; text-align: center; }}
    .company {{ font-size: 19pt; font-weight: 700; letter-spacing: .3px; }}
    .muted {{ color: #4b5563; font-size: 9pt; margin-top: 3px; }}
    .title {{ background: {theme_color}; color: #fff; font-size: 13pt; font-weight: 700; margin-top: 12px; padding: 7px; text-align: center; }}
    .meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px 20px; margin: 12px 0; }}
    .meta div {{ border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; padding: 4px 0; }}
    .meta span {{ color: #4b5563; }}
    .party {{ border: 1px solid #e5e7eb; margin: 10px 0 12px; padding: 8px; }}
    .items {{ border-collapse: collapse; width: 100%; }}
    .items th {{ background: #f3f4f6; border: 1px solid #d1d5db; padding: 6px; }}
    .items td {{ border: 1px solid #e5e7eb; padding: 6px; text-align: right; }}
    .items .text-left {{ text-align: left; }}
    .summary {{ display: flex; justify-content: flex-end; margin-top: 12px; }}
    .summary table {{ border-collapse: collapse; min-width: 220px; }}
    .summary td {{ border: 1px solid #d1d5db; padding: 6px 8px; }}
    .summary td:last-child {{ font-weight: 700; text-align: right; }}
    .narration {{ border: 1px solid #e5e7eb; margin-top: 12px; padding: 8px; }}
    .footer {{ display: flex; justify-content: space-between; margin-top: 42px; }}
    .sign {{ border-top: 1px solid #111827; padding-top: 6px; text-align: center; width: 170px; }}
</style>
</head>
<body>
<div class="sheet">
    <div class="header">
        <div class="company">{escape_html(company_name)}</div>
        <div class="muted">{escape_html(address_text)}</div>
        <div class="muted">{escape_html(" | ".join(part for part in contact_parts if part))}</div>
    </div>
    <div class="title">{escape_html(title)}</div>
    <div class="meta">{meta_html}</div>
    <div class="party"><strong>{escape_html(party_label)}:</strong> {escape_html(party_name)}</div>
    {table_html}
    <div class="summary"><table>{totals_html}</table></div>
    {narration_html}
    <div class="footer">
        <div>Prepared By</div>
        <div class="sign">Authorised Signature</div>
    </div>
</div>
</body>
</html>"""
