"""
Native PDF invoice generator for sales bills.

Uses PySide6's native document and WebEngine PDF APIs; no third-party PDF
dependencies are required.
"""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QPageSize, QPdfWriter, QTextDocument

from db import Database
from bizora_core.print_settings_logic import get_print_settings

try:
    from utils.a4_print_engine import (
        export_a4_pdf,
        generate_a4_html,
    )
except ImportError:
    export_a4_pdf = None
    generate_a4_html = None


def _money(value: Any) -> str:
    try:
        return f"{float(value or 0.0):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _enabled(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


def _image_src(path_value: Any) -> str:
    path_text = _text(path_value).strip()
    if not path_text or path_text.lower().endswith(".pdf"):
        return ""

    path = Path(path_text)
    if not path.exists():
        return ""
    return path.resolve().as_uri()


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned or "invoice"


def _print_settings_metadata(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Return metadata embedded in saved print layout coordinates."""
    raw_coordinates = (settings or {}).get("layout_coordinates", "") or ""
    if not raw_coordinates:
        return {}
    try:
        coordinates = json.loads(raw_coordinates)
    except (TypeError, json.JSONDecodeError) as exc:
        print(f"Invalid print settings metadata JSON: {exc}")
        return {}
    if not isinstance(coordinates, dict):
        return {}
    metadata = coordinates.get("__settings__", {})
    return metadata if isinstance(metadata, dict) else {}


def _a4_theme_name(settings: Dict[str, Any]) -> str:
    """Return the active A4 invoice theme from saved print settings."""
    a4_theme_names = {
        "GST Standard",
        "Modern Clean",
        "Elegant Serif",
        "Compact Wholesale",
        "Bold Corporate",
        "Bill of Supply",
        "Color Block Header",
        "Vibrant Accent",
        "Modern Gradient",
    }
    settings = settings or {}
    metadata = _print_settings_metadata(settings)
    for key in ("a4_theme", "default_theme", "theme"):
        theme_name = str(metadata.get(key) or settings.get(key) or "").strip()
        if theme_name in a4_theme_names:
            return theme_name
    return "GST Standard"


def _amount_to_words(value: Any) -> str:
    """Convert a numeric invoice amount into simple Indian currency words."""
    ones = (
        "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
        "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
        "Sixteen", "Seventeen", "Eighteen", "Nineteen",
    )
    tens = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")

    def below_hundred(number: int) -> str:
        """Render numbers from 0 to 99 in words."""
        if number < 20:
            return ones[number]
        suffix = number % 10
        return tens[number // 10] if suffix == 0 else f"{tens[number // 10]} {ones[suffix]}"

    def below_thousand(number: int) -> str:
        """Render numbers from 0 to 999 in words."""
        if number < 100:
            return below_hundred(number)
        suffix = number % 100
        words = f"{ones[number // 100]} Hundred"
        return words if suffix == 0 else f"{words} {below_hundred(suffix)}"

    amount = round(float(value or 0.0), 2)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    parts = []
    for divisor, label in ((10000000, "Crore"), (100000, "Lakh"), (1000, "Thousand")):
        chunk = rupees // divisor
        if chunk:
            parts.append(f"{below_thousand(chunk)} {label}")
            rupees %= divisor
    if rupees:
        parts.append(below_thousand(rupees))
    if not parts:
        parts.append("Zero")
    words = f"{' '.join(parts)} Rupees"
    if paise:
        words = f"{words} and {below_hundred(paise)} Paise"
    return f"{words} Only"


def _query_one(db: Database, sql: str, params=()) -> Optional[Dict[str, Any]]:
    rows = db.execute_query(sql, tuple(params)) or []
    return dict(rows[0]) if rows else None


def _query(db: Database, sql: str, params=()) -> List[Dict[str, Any]]:
    return [dict(row) for row in db.execute_query(sql, tuple(params)) or []]


def _build_invoice_html(company: Dict[str, Any], header: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    company_name = html.escape(_text(company.get("business_name") or ""))
    company_address = html.escape(_text(company.get("address") or "")) if _enabled(company.get("print_address")) else ""
    company_phone = html.escape(_text(company.get("phone_number") or "")) if _enabled(company.get("print_phone")) else ""
    company_gstin = html.escape(_text(company.get("gstin") or "")) if _enabled(company.get("print_gstin")) else ""
    company_email = html.escape(_text(company.get("email") or "")) if _enabled(company.get("print_email")) else ""
    logo_src = _image_src(company.get("logo_path")) if _enabled(company.get("print_logo")) else ""
    signature_src = _image_src(company.get("signature_path")) if _enabled(company.get("print_signature")) else ""
    logo_html = f"<img class='logo' src='{html.escape(logo_src)}'>" if logo_src else ""
    signature_html = f"<img class='signature-img' src='{html.escape(signature_src)}'><br>" if signature_src else ""

    bill_no = html.escape(_text(header.get("invoice_number") or ""))
    bill_date = html.escape(_text(header.get("invoice_date") or ""))
    party_name = html.escape(_text(header.get("party_name") or "Cash Customer"))
    party_address = html.escape(_text(header.get("party_address") or header.get("address") or ""))
    party_gstin = html.escape(_text(header.get("party_gstin") or header.get("gstin") or ""))
    status = html.escape(_text(header.get("status") or "Active"))

    item_rows = []
    for item in items:
        item_rows.append(
            "<tr>"
            f"<td class='center'>{html.escape(_text(item.get('sl_no') or ''))}</td>"
            f"<td>{html.escape(_text(item.get('product_name') or ''))}</td>"
            f"<td>{html.escape(_text(item.get('hsn') or ''))}</td>"
            f"<td class='right'>{_money(item.get('quantity'))}</td>"
            f"<td class='right'>{_money(item.get('rate'))}</td>"
            f"<td class='right'>{_money(item.get('discount'))}</td>"
            f"<td class='right'>{_money(item.get('tax_amount'))}</td>"
            f"<td class='right'>{_money(item.get('grand_total'))}</td>"
            "</tr>"
        )

    return f"""
    <html>
    <head>
    <style>
        body {{
            font-family: Arial, sans-serif;
            font-size: 10pt;
            color: #111827;
        }}
        .company {{
            text-align: center;
            border-bottom: 2px solid #111827;
            padding-bottom: 10px;
            margin-bottom: 12px;
        }}
        .company h1 {{
            margin: 0;
            font-size: 22pt;
            letter-spacing: 0.5px;
        }}
        .logo {{
            max-height: 60px;
            max-width: 150px;
            margin-bottom: 6px;
        }}
        .invoice-title {{
            text-align: center;
            font-size: 15pt;
            font-weight: bold;
            margin: 10px 0;
        }}
        .meta {{
            width: 100%;
            margin-bottom: 12px;
        }}
        .meta td {{
            vertical-align: top;
            padding: 4px;
        }}
        table.items {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
        }}
        .items th {{
            background: #e5e7eb;
            border: 1px solid #9ca3af;
            padding: 6px;
        }}
        .items td {{
            border: 1px solid #d1d5db;
            padding: 5px;
        }}
        .right {{ text-align: right; }}
        .center {{ text-align: center; }}
        .totals {{
            margin-top: 12px;
            width: 100%;
        }}
        .terms {{
            margin-top: 24px;
            font-size: 9pt;
            color: #374151;
            border-top: 1px solid #d1d5db;
            padding-top: 8px;
        }}
        .signature {{
            margin-top: 28px;
            text-align: right;
            font-size: 9pt;
        }}
        .signature-img {{
            max-height: 55px;
            max-width: 150px;
        }}
    </style>
    </head>
    <body>
        <div class="company">
            {logo_html}
            <h1>{company_name}</h1>
            <div>{company_address}</div>
            <div>{'Phone: ' + company_phone if company_phone else ''}</div>
            <div>{'GSTIN: ' + company_gstin if company_gstin else ''}</div>
            <div>{'Email: ' + company_email if company_email else ''}</div>
        </div>

        <div class="invoice-title">TAX INVOICE</div>

        <table class="meta">
            <tr>
                <td width="55%">
                    <b>Billed To:</b><br>
                    {party_name}<br>
                    {party_address}<br>
                    {'GSTIN: ' + party_gstin if party_gstin else ''}
                </td>
                <td width="45%">
                    <b>Bill No:</b> {bill_no}<br>
                    <b>Date:</b> {bill_date}<br>
                    <b>Status:</b> {status}
                </td>
            </tr>
        </table>

        <table class="items">
            <thead>
                <tr>
                    <th>SL</th>
                    <th>Product</th>
                    <th>HSN</th>
                    <th>Qty</th>
                    <th>Rate</th>
                    <th>Disc</th>
                    <th>Tax</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
                {''.join(item_rows)}
            </tbody>
        </table>

        <table class="totals">
            <tr>
                <td class="right">
                    Sub Total: <b>{_money(header.get('sub_total'))}</b><br>
                    Discount: <b>{_money(header.get('discount_total'))}</b><br>
                    Tax: <b>{_money(header.get('tax_total'))}</b><br>
                    Round Off: <b>{_money(header.get('round_off'))}</b><br>
                    Total Amount: <b>{_money(header.get('grand_total'))}</b>
                </td>
            </tr>
        </table>

        <div class="terms">
            <b>Terms:</b> Goods once sold are subject to the agreed business terms.
            This is a computer generated invoice.
        </div>
        <div class="signature">
            {signature_html}
            Authorised Signature
        </div>
    </body>
    </html>
    """


def generate_invoice_pdf(bill_no: str, db: Optional[Database] = None, open_pdf: bool = True) -> str:
    """Generate and optionally open a PDF invoice for the given sales bill number."""
    if not bill_no:
        raise ValueError("Bill number is required.")

    database = db or Database()
    ph = database._get_placeholder()

    company = _query_one(
        database,
        f"""
        SELECT id, business_name, address, phone_number, gstin, email,
               logo_path, signature_path,
               COALESCE(print_phone, 1) AS print_phone,
               COALESCE(print_gstin, 1) AS print_gstin,
               COALESCE(print_email, 1) AS print_email,
               COALESCE(print_address, 1) AS print_address,
               COALESCE(print_logo, 1) AS print_logo,
               COALESCE(print_signature, 1) AS print_signature
        FROM companies
        WHERE is_active = 1
        ORDER BY id DESC
        """,
    )
    if not company:
        raise ValueError("No active company found.")

    header = _query_one(
        database,
        f"""
        SELECT s.id, s.invoice_number, s.invoice_date, s.party_id, s.sales_type,
               COALESCE(p.name, '') AS party_name,
               p.address AS party_address,
               p.gstin AS party_gstin,
               s.address, s.gstin, s.sub_total, s.discount_total, s.tax_total,
               s.round_off, s.grand_total, COALESCE(s.status, 'Active') AS status
        FROM sales s
        LEFT JOIN parties p ON s.party_id = p.id
        WHERE s.company_id = {ph} AND s.invoice_number = {ph}
        """,
        (company["id"], bill_no),
    )
    if not header:
        raise ValueError(f"Sales bill '{bill_no}' was not found.")

    items = _query(
        database,
        f"""
        SELECT si.sl_no, COALESCE(pr.name, '') AS product_name, si.hsn,
               si.rate, si.quantity, si.gross_value, si.discount, si.net_value,
               si.tax_percent, si.cgst, si.sgst, si.igst, si.cess,
               si.tax_amount, si.grand_total, si.cgst_amount,
               si.sgst_amount, si.igst_amount, si.cess_amount
        FROM sales_items si
        LEFT JOIN products pr ON si.product_id = pr.id
        WHERE si.sale_id = {ph}
        ORDER BY si.sl_no
        """,
        (header["id"],),
    )

    invoices_dir = Path(__file__).resolve().parents[1] / "invoices"
    invoices_dir.mkdir(parents=True, exist_ok=True)
    output_path = invoices_dir / f"{_safe_filename(str(bill_no))}.pdf"

    if generate_a4_html is not None and export_a4_pdf is not None:
        company_data = dict(company)
        company_data.setdefault("company_name", company_data.get("business_name", ""))
        company_data.setdefault("name", company_data.get("business_name", ""))
        company_data.setdefault("company_address", company_data.get("address", ""))
        company_data.setdefault("phone", company_data.get("phone_number", ""))
        company_data.setdefault("company_gstin", company_data.get("gstin", ""))

        sales_type = _text(header.get("sales_type")).strip().lower()
        bill_type = "BOS" if "bill of supply" in sales_type else "TAX_INVOICE"
        is_bos = bill_type == "BOS"
        cart_data = []
        for index, item in enumerate(items, start=1):
            gst_rate = 0.0 if is_bos else (
                float(item.get("cgst") or 0.0)
                + float(item.get("sgst") or 0.0)
                + float(item.get("igst") or 0.0)
            )
            cgst_amount = 0.0 if is_bos else item.get("cgst_amount", 0.0)
            sgst_amount = 0.0 if is_bos else item.get("sgst_amount", 0.0)
            cart_data.append({
                "sl_no": item.get("sl_no") or index,
                "product_name": item.get("product_name", ""),
                "name": item.get("product_name", ""),
                "description": item.get("product_name", ""),
                "hsn": item.get("hsn", ""),
                "quantity": item.get("quantity", 0.0),
                "qty": item.get("quantity", 0.0),
                "rate": item.get("rate", 0.0),
                "gross": item.get("gross_value", 0.0),
                "discount": item.get("discount", 0.0),
                "net_value": item.get("net_value", 0.0),
                "taxable_value": item.get("net_value", 0.0),
                "tax_percent": gst_rate,
                "gst_rate": gst_rate,
                "cess_rate": 0.0 if is_bos else item.get("cess", 0.0),
                "cgst": cgst_amount,
                "sgst": sgst_amount,
                "cgst_amount": cgst_amount,
                "sgst_amount": sgst_amount,
                "igst_amount": 0.0 if is_bos else item.get("igst_amount", 0.0),
                "cess_amount": 0.0 if is_bos else item.get("cess_amount", 0.0),
                "tax_amount": 0.0 if is_bos else item.get("tax_amount", 0.0),
                "total": item.get("grand_total", 0.0),
                "grand_total": item.get("grand_total", 0.0),
            })

        grand_total = float(header.get("grand_total") or 0.0)
        totals_data = {
            "bill_type": bill_type,
            "invoice_number": header.get("invoice_number", ""),
            "bill_no": header.get("invoice_number", ""),
            "invoice_date": header.get("invoice_date", ""),
            "bill_date": header.get("invoice_date", ""),
            "customer_name": header.get("party_name") or "Cash Customer",
            "party_name": header.get("party_name") or "Cash Customer",
            "customer_address": header.get("party_address") or header.get("address", ""),
            "party_address": header.get("party_address") or header.get("address", ""),
            "customer_gstin": header.get("party_gstin") or header.get("gstin", ""),
            "party_gstin": header.get("party_gstin") or header.get("gstin", ""),
            "subtotal": header.get("sub_total", 0.0),
            "sub_total": header.get("sub_total", 0.0),
            "taxable_total": header.get("sub_total", 0.0),
            "discount": header.get("discount_total", 0.0),
            "discount_total": header.get("discount_total", 0.0),
            "cgst": sum(float(item.get("cgst_amount") or 0.0) for item in cart_data),
            "sgst": sum(float(item.get("sgst_amount") or 0.0) for item in cart_data),
            "cess": sum(float(item.get("cess_amount") or 0.0) for item in cart_data),
            "cgst_total": sum(float(item.get("cgst_amount") or 0.0) for item in cart_data),
            "sgst_total": sum(float(item.get("sgst_amount") or 0.0) for item in cart_data),
            "cess_total": sum(float(item.get("cess_amount") or 0.0) for item in cart_data),
            "tax_total": 0.0 if is_bos else header.get("tax_total", 0.0),
            "round_off": header.get("round_off", 0.0),
            "grand_total": grand_total,
            "total": grand_total,
            "total_amount": grand_total,
            "amount_in_words": _amount_to_words(grand_total),
        }
        print_settings = get_print_settings(database, company["id"])
        html_string = generate_a4_html(
            company_data,
            cart_data,
            bill_type=bill_type,
            totals_data=totals_data,
            settings=print_settings,
            theme_name=_a4_theme_name(print_settings),
        )
        preview_wrapper_present = (
            "width: 794px" in html_string
            or 'class="preview-body"' in html_string
        )
        print(
            "[A4_PRINT] invoice_printer PDF export route "
            f"paper_size='{print_settings.get('a4_paper_size') or print_settings.get('paper_size') or 'A4'}' "
            f"html_len={len(html_string)} "
            f"preview_wrapper_present={preview_wrapper_present}"
        )
        export_a4_pdf(html_string, str(output_path), settings=print_settings)
        if open_pdf:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(output_path)))
        return str(output_path)

    document = QTextDocument()
    document.setHtml(_build_invoice_html(company, header, items))

    writer = QPdfWriter(str(output_path))
    writer.setPageSize(QPageSize(QPageSize.A4))
    writer.setResolution(96)
    document.print_(writer)

    if open_pdf:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(output_path)))

    return str(output_path)
