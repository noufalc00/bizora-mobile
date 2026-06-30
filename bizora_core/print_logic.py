"""
Tenant-safe invoice print data and HTML generation helpers.

This module prepares structured invoice data, converts it into simple HTML
layouts, and sends the HTML to the operating-system print dialog. Rendering is
kept separate from Sales Entry so future page formats can evolve without
changing voucher save logic.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSizeF
from PySide6.QtGui import QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import QDialog

from db import Database


VALID_PRINT_FORMATS = {"Thermal_80mm", "A4", "A3", "Custom"}
DEFAULT_PRINT_FORMAT = "A4"


def _to_float(value: Any) -> float:
    """Return a float value for numeric print fields without raising errors."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _money(value: Any) -> str:
    """Format a numeric value as a two-decimal invoice amount."""
    return f"{_to_float(value):.2f}"


def _text(value: Any) -> str:
    """Return a plain string for display fields."""
    return "" if value is None else str(value)


def _html(value: Any) -> str:
    """Escape dynamic values before inserting them into invoice HTML."""
    return html.escape(_text(value), quote=True)


def _query_one(db: Database, sql: str, params: tuple) -> Optional[Dict[str, Any]]:
    """Execute a parameterized SELECT and return the first row as a dictionary."""
    rows = db.execute_query(sql, params) or []
    return dict(rows[0]) if rows else None


def _query_all(db: Database, sql: str, params: tuple) -> List[Dict[str, Any]]:
    """Execute a parameterized SELECT and return rows as dictionaries."""
    return [dict(row) for row in db.execute_query(sql, params) or []]


def _normalise_print_format(format_type: Any) -> str:
    """Return a supported print format, defaulting safely to A4-compatible HTML."""
    clean_format = _text(format_type).strip()
    return clean_format if clean_format in VALID_PRINT_FORMATS else DEFAULT_PRINT_FORMAT


def get_invoice_print_data(invoice_id, company_id) -> Dict[str, Any]:
    """
    Fetch one sales invoice with company firewalling for dynamic printing.

    Args:
        invoice_id: Sales invoice primary key from the sales table.
        company_id: Tenant company id. Every query is scoped to this company.

    Returns:
        Structured data with company, invoice, items, and footer sections. If
        the invoice is not found inside the requested company, success is False.
    """
    try:
        resolved_invoice_id = int(invoice_id)
        resolved_company_id = int(company_id)
    except (TypeError, ValueError) as exc:
        return {
            "success": False,
            "message": f"Invalid invoice or company id: {exc}",
            "company": {},
            "invoice": {},
            "items": [],
            "footer": {},
        }

    db = Database()
    ph = db._get_placeholder()

    try:
        company = _query_one(
            db,
            f"""
            SELECT
                id,
                business_name,
                address,
                gstin,
                phone_number
            FROM companies
            WHERE id = {ph}
            """,
            (resolved_company_id,),
        )
        if not company:
            return {
                "success": False,
                "message": "Company was not found for invoice printing.",
                "company": {},
                "invoice": {},
                "items": [],
                "footer": {},
            }

        header = _query_one(
            db,
            f"""
            SELECT
                s.id,
                s.invoice_number,
                s.invoice_date,
                s.party_id,
                COALESCE(p.name, '') AS customer_name,
                COALESCE(p.mobile_number, '') AS customer_phone,
                COALESCE(s.address, p.address, '') AS customer_address,
                COALESCE(s.gstin, p.gstin, '') AS customer_gstin,
                COALESCE(s.sales_type, '') AS sales_type,
                COALESCE(s.status, 'Active') AS status,
                COALESCE(s.sub_total, 0) AS sub_total,
                COALESCE(s.discount_total, 0) AS discount_total,
                COALESCE(s.tax_total, 0) AS tax_total,
                COALESCE(s.round_off, 0) AS round_off,
                COALESCE(s.grand_total, 0) AS grand_total
            FROM sales s
            LEFT JOIN parties p
                ON p.id = s.party_id
               AND p.company_id = s.company_id
            WHERE s.id = {ph}
              AND s.company_id = {ph}
            """,
            (resolved_invoice_id, resolved_company_id),
        )
        if not header:
            return {
                "success": False,
                "message": "Invoice was not found for the selected company.",
                "company": {},
                "invoice": {},
                "items": [],
                "footer": {},
            }

        item_rows = _query_all(
            db,
            f"""
            SELECT
                si.id,
                si.sl_no,
                COALESCE(pr.name, '') AS item_name,
                COALESCE(si.hsn, pr.hsn, '') AS hsn,
                COALESCE(si.unit, pr.unit, '') AS unit,
                COALESCE(si.quantity, 0) AS quantity,
                COALESCE(si.rate, 0) AS rate,
                COALESCE(si.gross_value, 0) AS gross_value,
                COALESCE(si.discount, 0) AS discount,
                COALESCE(si.net_value, 0) AS net_value,
                COALESCE(si.tax_percent, 0) AS tax_percent,
                COALESCE(si.tax_amount, 0) AS tax_amount,
                COALESCE(si.grand_total, 0) AS grand_total,
                COALESCE(si.cgst_amount, 0) AS cgst_amount,
                COALESCE(si.sgst_amount, 0) AS sgst_amount,
                COALESCE(si.igst_amount, 0) AS igst_amount,
                COALESCE(si.cess_amount, 0) AS cess_amount
            FROM sales_items si
            INNER JOIN sales s
                ON s.id = si.sale_id
               AND s.company_id = {ph}
            LEFT JOIN products pr
                ON pr.id = si.product_id
               AND pr.company_id = s.company_id
            WHERE si.sale_id = {ph}
            ORDER BY si.sl_no, si.id
            """,
            (resolved_company_id, resolved_invoice_id),
        )

        gst_rows = _query_all(
            db,
            f"""
            SELECT
                COALESCE(SUM(si.cgst_amount), 0) AS cgst,
                COALESCE(SUM(si.sgst_amount), 0) AS sgst,
                COALESCE(SUM(si.igst_amount), 0) AS igst,
                COALESCE(SUM(si.cess_amount), 0) AS cess,
                COALESCE(SUM(si.tax_amount), 0) AS total
            FROM sales_items si
            INNER JOIN sales s
                ON s.id = si.sale_id
               AND s.company_id = {ph}
            WHERE si.sale_id = {ph}
            """,
            (resolved_company_id, resolved_invoice_id),
        )
        gst_breakdown = gst_rows[0] if gst_rows else {}
        tax_total = _to_float(header.get("tax_total"))
        if tax_total == 0.0:
            tax_total = _to_float(gst_breakdown.get("total"))

        items = [
            {
                "sl_no": row.get("sl_no"),
                "item_name": row.get("item_name") or "Item",
                "hsn": row.get("hsn") or "",
                "unit": row.get("unit") or "",
                "qty": _to_float(row.get("quantity")),
                "rate": _to_float(row.get("rate")),
                "gross_value": _to_float(row.get("gross_value")),
                "discount": _to_float(row.get("discount")),
                "taxable_amount": _to_float(row.get("net_value")),
                "tax_percent": _to_float(row.get("tax_percent")),
                "tax": _to_float(row.get("tax_amount")),
                "total": _to_float(row.get("grand_total")),
                "cgst_amount": _to_float(row.get("cgst_amount")),
                "sgst_amount": _to_float(row.get("sgst_amount")),
                "igst_amount": _to_float(row.get("igst_amount")),
                "cess_amount": _to_float(row.get("cess_amount")),
            }
            for row in item_rows
        ]

        return {
            "success": True,
            "message": "",
            "company": {
                "id": company.get("id"),
                "name": company.get("business_name") or "",
                "address": company.get("address") or "",
                "gstin": company.get("gstin") or "",
                "phone": company.get("phone_number") or "",
            },
            "invoice": {
                "id": header.get("id"),
                "voucher_no": header.get("invoice_number") or "",
                "date": header.get("invoice_date") or "",
                "customer_name": header.get("customer_name") or "Cash Customer",
                "customer_phone": header.get("customer_phone") or "",
                "customer_address": header.get("customer_address") or "",
                "customer_gstin": header.get("customer_gstin") or "",
                "sales_type": header.get("sales_type") or "",
                "status": header.get("status") or "Active",
            },
            "items": items,
            "footer": {
                "subtotal": _to_float(header.get("sub_total")),
                "discount_total": _to_float(header.get("discount_total")),
                "tax_total": tax_total,
                "gst_breakdown": {
                    "cgst": _to_float(gst_breakdown.get("cgst")),
                    "sgst": _to_float(gst_breakdown.get("sgst")),
                    "igst": _to_float(gst_breakdown.get("igst")),
                    "cess": _to_float(gst_breakdown.get("cess")),
                    "total": _to_float(gst_breakdown.get("total")),
                },
                "round_off": _to_float(header.get("round_off")),
                "grand_total": _to_float(header.get("grand_total")),
            },
        }
    except Exception as exc:
        return {
            "success": False,
            "message": f"Invoice print data fetch failed: {exc}",
            "company": {},
            "invoice": {},
            "items": [],
            "footer": {},
        }


def generate_thermal_html(data: Dict[str, Any]) -> str:
    """
    Return lightweight 80mm POS invoice HTML.

    The layout uses monospace text and dashed separators so it stays readable on
    thermal printers without relying on heavy borders.
    """
    company = data.get("company", {}) or {}
    invoice = data.get("invoice", {}) or {}
    footer = data.get("footer", {}) or {}
    items = data.get("items", []) or []
    separator = "-" * 32

    item_html = []
    for item in items:
        item_html.append(
            f"""
            <div class="item">
                <div><b>{_html(item.get("item_name"))}</b></div>
                <div class="row">
                    <span>Qty {_html(_money(item.get("qty")))} x {_html(_money(item.get("rate")))}</span>
                    <span>{_html(_money(item.get("total")))}</span>
                </div>
                <div class="row muted">
                    <span>Tax {_html(_money(item.get("tax")))} @ {_html(_money(item.get("tax_percent")))}%</span>
                    <span>HSN {_html(item.get("hsn"))}</span>
                </div>
            </div>
            """
        )

    gst = footer.get("gst_breakdown", {}) or {}
    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                margin: 0;
                padding: 0;
                color: #111;
                background: #fff;
            }}
            .receipt {{
                width: 100%;
                max-width: 300px;
                font-family: monospace;
                font-size: 12px;
                text-align: center;
                margin: 0 auto;
            }}
            .separator {{
                border-top: 1px dashed #111;
                margin: 6px 0;
                height: 0;
            }}
            .row {{
                display: flex;
                justify-content: space-between;
                gap: 8px;
                text-align: left;
            }}
            .item {{
                padding: 4px 0;
                text-align: left;
            }}
            .muted {{
                color: #444;
                font-size: 11px;
            }}
            .totals {{
                text-align: left;
            }}
            .grand {{
                font-size: 14px;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="receipt">
            <h2>{_html(company.get("name"))}</h2>
            <div>{_html(company.get("address"))}</div>
            <div>{'Phone: ' + _html(company.get("phone")) if company.get("phone") else ''}</div>
            <div>{'GSTIN: ' + _html(company.get("gstin")) if company.get("gstin") else ''}</div>
            <div class="separator"></div>
            <div><b>TAX INVOICE</b></div>
            <div class="row"><span>No:</span><span>{_html(invoice.get("voucher_no"))}</span></div>
            <div class="row"><span>Date:</span><span>{_html(invoice.get("date"))}</span></div>
            <div class="row"><span>Customer:</span><span>{_html(invoice.get("customer_name"))}</span></div>
            <div class="separator"></div>
            <div>{_html(separator)}</div>
            {''.join(item_html)}
            <div>{_html(separator)}</div>
            <div class="totals">
                <div class="row"><span>Subtotal</span><span>{_html(_money(footer.get("subtotal")))}</span></div>
                <div class="row"><span>Discount</span><span>{_html(_money(footer.get("discount_total")))}</span></div>
                <div class="row"><span>CGST</span><span>{_html(_money(gst.get("cgst")))}</span></div>
                <div class="row"><span>SGST</span><span>{_html(_money(gst.get("sgst")))}</span></div>
                <div class="row"><span>IGST</span><span>{_html(_money(gst.get("igst")))}</span></div>
                <div class="row"><span>CESS</span><span>{_html(_money(gst.get("cess")))}</span></div>
                <div class="row"><span>Round Off</span><span>{_html(_money(footer.get("round_off")))}</span></div>
                <div class="separator"></div>
                <div class="row grand"><span>Grand Total</span><span>{_html(_money(footer.get("grand_total")))}</span></div>
            </div>
            <div class="separator"></div>
            <div>Thank you!</div>
        </div>
    </body>
    </html>
    """


def generate_standard_html(data: Dict[str, Any]) -> str:
    """
    Return professional A4/A3 invoice HTML with table borders and totals.

    This template is intentionally paper-size neutral so A3 and Custom can use
    it until dedicated layout controls are introduced.
    """
    company = data.get("company", {}) or {}
    invoice = data.get("invoice", {}) or {}
    footer = data.get("footer", {}) or {}
    items = data.get("items", []) or []
    gst = footer.get("gst_breakdown", {}) or {}

    item_rows = []
    for item in items:
        item_rows.append(
            f"""
            <tr>
                <td class="center">{_html(item.get("sl_no"))}</td>
                <td>{_html(item.get("item_name"))}</td>
                <td>{_html(item.get("hsn"))}</td>
                <td class="right">{_html(_money(item.get("qty")))}</td>
                <td class="right">{_html(_money(item.get("rate")))}</td>
                <td class="right">{_html(_money(item.get("taxable_amount")))}</td>
                <td class="right">{_html(_money(item.get("tax")))}</td>
                <td class="right">{_html(_money(item.get("total")))}</td>
            </tr>
            """
        )

    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                font-size: 10pt;
                color: #111827;
                margin: 0;
                padding: 18px;
            }}
            .invoice {{
                width: 100%;
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                border-bottom: 2px solid #111827;
                padding-bottom: 10px;
                margin-bottom: 14px;
            }}
            .company {{
                text-align: left;
                max-width: 58%;
            }}
            .company h1 {{
                margin: 0 0 6px;
                font-size: 22pt;
            }}
            .title {{
                text-align: right;
                font-size: 18pt;
                font-weight: bold;
            }}
            .meta {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 14px;
            }}
            .meta td {{
                border: 1px solid #9ca3af;
                padding: 7px;
                vertical-align: top;
            }}
            .items {{
                width: 100%;
                border-collapse: collapse;
            }}
            .items th {{
                background: #e5e7eb;
                border: 1px solid #6b7280;
                padding: 7px;
                font-weight: bold;
            }}
            .items td {{
                border: 1px solid #9ca3af;
                padding: 6px;
            }}
            .right {{
                text-align: right;
            }}
            .center {{
                text-align: center;
            }}
            .totals {{
                width: 38%;
                margin-left: auto;
                margin-top: 14px;
                border-collapse: collapse;
            }}
            .totals td {{
                border: 1px solid #9ca3af;
                padding: 6px;
            }}
            .grand td {{
                font-weight: bold;
                font-size: 12pt;
                background: #f3f4f6;
            }}
            .footer-note {{
                margin-top: 28px;
                border-top: 1px solid #d1d5db;
                padding-top: 8px;
                color: #374151;
            }}
        </style>
    </head>
    <body>
        <div class="invoice">
            <div class="header">
                <div class="company">
                    <h1>{_html(company.get("name"))}</h1>
                    <div>{_html(company.get("address"))}</div>
                    <div>{'Phone: ' + _html(company.get("phone")) if company.get("phone") else ''}</div>
                    <div>{'GSTIN: ' + _html(company.get("gstin")) if company.get("gstin") else ''}</div>
                </div>
                <div class="title">TAX INVOICE</div>
            </div>

            <table class="meta">
                <tr>
                    <td width="60%">
                        <b>Billed To</b><br>
                        {_html(invoice.get("customer_name"))}<br>
                        {_html(invoice.get("customer_address"))}<br>
                        {'GSTIN: ' + _html(invoice.get("customer_gstin")) if invoice.get("customer_gstin") else ''}
                    </td>
                    <td width="40%">
                        <b>Voucher No:</b> {_html(invoice.get("voucher_no"))}<br>
                        <b>Date:</b> {_html(invoice.get("date"))}<br>
                        <b>Status:</b> {_html(invoice.get("status"))}
                    </td>
                </tr>
            </table>

            <table class="items">
                <thead>
                    <tr>
                        <th>SL</th>
                        <th>Item Name</th>
                        <th>HSN</th>
                        <th>Qty</th>
                        <th>Rate</th>
                        <th>Taxable</th>
                        <th>Tax</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(item_rows)}
                </tbody>
            </table>

            <table class="totals">
                <tr><td>Subtotal</td><td class="right">{_html(_money(footer.get("subtotal")))}</td></tr>
                <tr><td>Discount</td><td class="right">{_html(_money(footer.get("discount_total")))}</td></tr>
                <tr><td>CGST</td><td class="right">{_html(_money(gst.get("cgst")))}</td></tr>
                <tr><td>SGST</td><td class="right">{_html(_money(gst.get("sgst")))}</td></tr>
                <tr><td>IGST</td><td class="right">{_html(_money(gst.get("igst")))}</td></tr>
                <tr><td>CESS</td><td class="right">{_html(_money(gst.get("cess")))}</td></tr>
                <tr><td>Round Off</td><td class="right">{_html(_money(footer.get("round_off")))}</td></tr>
                <tr class="grand"><td>Grand Total</td><td class="right">{_html(_money(footer.get("grand_total")))}</td></tr>
            </table>

            <div class="footer-note">Thank you for your business.</div>
        </div>
    </body>
    </html>
    """


def generate_invoice_html(data: Dict[str, Any], format_type: Any) -> str:
    """
    Route invoice data to the appropriate HTML template for the print format.

    Unknown formats fall back to the standard A4/A3-compatible template.
    """
    if _normalise_print_format(format_type) == "Thermal_80mm":
        return generate_thermal_html(data)
    return generate_standard_html(data)


def _configure_printer_page_size(printer: QPrinter, format_type: str) -> None:
    """Apply the requested page size to a QPrinter instance."""
    if format_type == "A3":
        printer.setPageSize(QPageSize(QPageSize.A3))
        return
    if format_type == "Thermal_80mm":
        try:
            page_size = QPageSize(
                QSizeF(80, 297),
                QPageSize.Unit.Millimeter,
                "Thermal 80mm",
            )
        except Exception:
            page_size = QPageSize(QSizeF(80, 297), QPageSize.Millimeter)
        printer.setPageSize(page_size)
        return
    printer.setPageSize(QPageSize(QPageSize.A4))


def execute_print(html_content: str, format_type: Any, parent_window=None) -> Dict[str, Any]:
    """
    Open the native print dialog and print HTML through QTextDocument.

    Args:
        html_content: Fully escaped invoice HTML string.
        format_type: Thermal_80mm, A4, A3, or Custom. Custom currently uses A4.
        parent_window: Optional Qt parent for the print dialog.

    Returns:
        A structured success flag and message so UI callers can show feedback
        without raising unhandled exceptions.
    """
    try:
        clean_format = _normalise_print_format(format_type)
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        except AttributeError:
            printer = QPrinter(QPrinter.HighResolution)
        _configure_printer_page_size(printer, clean_format)

        document = QTextDocument()
        document.setHtml(html_content or "")

        dialog = QPrintDialog(printer, parent_window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return {"success": False, "message": "Print was cancelled."}

        document.print_(printer)
        return {"success": True, "message": "Invoice sent to printer."}
    except Exception as exc:
        return {"success": False, "message": f"Print failed: {exc}"}
