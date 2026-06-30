"""
Invoice template rendering engine for Faizan Pro Accounting.

This module reads invoice HTML templates from the project root, fetches
tenant-scoped sales data, escapes all dynamic values, and returns final HTML
ready for print preview or printing.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from db import Database
from bizora_core.print_settings_logic import get_print_settings


LOGGER = logging.getLogger(__name__)


def _to_float(value: Any) -> float:
    """Convert numeric database values to float without raising UI errors."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _money(value: Any) -> str:
    """Format a numeric amount for invoice display."""
    return f"{_to_float(value):.2f}"


def _text(value: Any) -> str:
    """Return a safe plain string for nullable database values."""
    return "" if value is None else str(value)


def _receipt_balance(payment_mode: Any, amount_received: Any, grand_total: Any) -> float:
    """Return cash change for receipts, or zero for non-cash modes."""
    if _text(payment_mode).strip().lower() == "cash":
        return _to_float(amount_received) - _to_float(grand_total)
    return 0.0


def _amount_received_for_print(invoice: Dict[str, Any]) -> float:
    """Return saved tender amount with a fallback for legacy cash invoices."""
    amount_received = _to_float(invoice.get("amount_received"))
    grand_total = _to_float(invoice.get("grand_total"))
    payment_mode = _text(invoice.get("payment_mode")).strip().lower()
    sales_type = _text(invoice.get("sales_type")).strip().lower()
    if (
        amount_received == 0.0
        and grand_total > 0.0
        and payment_mode in ("", "cash")
        and sales_type not in ("credit sales", "credit")
    ):
        return grand_total
    return amount_received


def _escape(value: Any) -> str:
    """Escape dynamic text before inserting it into an HTML template."""
    return html.escape(_text(value), quote=True)


def _amount_to_words(value: Any) -> str:
    """Convert a numeric invoice amount into simple Indian currency words."""
    ones = (
        "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
        "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
        "Sixteen", "Seventeen", "Eighteen", "Nineteen",
    )
    tens = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")

    def below_hundred(number: int) -> str:
        if number < 20:
            return ones[number]
        return tens[number // 10] if number % 10 == 0 else f"{tens[number // 10]} {ones[number % 10]}"

    def below_thousand(number: int) -> str:
        if number < 100:
            return below_hundred(number)
        suffix = number % 100
        words = f"{ones[number // 100]} Hundred"
        return words if suffix == 0 else f"{words} {below_hundred(suffix)}"

    amount = round(_to_float(value), 2)
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


class PrintEngine:
    """
    Generate invoice HTML by combining tenant-safe database data with templates.

    The engine intentionally stays separate from ``logic.print_logic`` so the
    older print flow remains compatible while newer callers can use file-based
    invoice templates.
    """

    def __init__(
        self,
        db: Optional[Database] = None,
        templates_dir: Optional[Path] = None,
    ) -> None:
        """
        Initialize the print engine with an existing or new database instance.

        Args:
            db: Optional shared Database instance supplied by a UI or service.
            templates_dir: Optional override used by tests or custom installers.
        """
        self.db = db or Database()
        self.templates_dir = templates_dir or Path(__file__).resolve().parents[1] / "templates"

    def generate_invoice_html(
        self,
        company_id: int,
        voucher_id: int,
        format_type: str = "a4",
        theme: str = "classic",
    ) -> str:
        """
        Return rendered invoice HTML for a company-scoped sales voucher.

        Args:
            company_id: Tenant company id. Every query is scoped by this value.
            voucher_id: Primary key from the sales table.
            format_type: ``a4`` or ``thermal``/``thermal_80mm``.
            theme: A4 visual theme, either ``classic`` or ``modern``.

        Returns:
            A complete HTML string. An empty string is returned if data cannot
            be fetched or the template cannot be rendered.
        """
        try:
            resolved_company_id = int(company_id)
            resolved_voucher_id = int(voucher_id)
            clean_format = self._normalize_format(format_type)
            clean_theme = self._normalize_theme(theme)
            template = self._read_template(clean_format, clean_theme)
            company = self._fetch_company(resolved_company_id)
            invoice = self._fetch_sales_header(resolved_company_id, resolved_voucher_id)

            if not company:
                LOGGER.warning(
                    "Invoice HTML generation blocked: company not found. company_id=%s",
                    resolved_company_id,
                )
                return ""
            if not invoice:
                LOGGER.warning(
                    "Invoice HTML generation blocked: voucher not found in company scope. "
                    "company_id=%s voucher_id=%s",
                    resolved_company_id,
                    resolved_voucher_id,
                )
                return ""

            items = self._fetch_sales_items(resolved_company_id, resolved_voucher_id)
            print_settings = get_print_settings(self.db, resolved_company_id)
            context = self._build_context(company, invoice, items, clean_format, print_settings)
            return self._replace_placeholders(template, context)
        except (TypeError, ValueError) as exc:
            LOGGER.exception("Invalid invoice render identifiers: %s", exc)
        except OSError as exc:
            LOGGER.exception("Invoice template file operation failed: %s", exc)
        except Exception as exc:
            LOGGER.exception("Invoice HTML generation failed unexpectedly: %s", exc)
        return ""

    def fetch_invoice_data(
        self,
        company_id: int,
        voucher_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Return structured company-scoped invoice data for non-HTML print engines.

        Args:
            company_id: Tenant company id. Every query is scoped by this value.
            voucher_id: Primary key from the sales table.

        Returns:
            A mapping with company, invoice, items, and print_settings, or None
            when the requested voucher does not belong to the active company.
        """
        try:
            resolved_company_id = int(company_id)
            resolved_voucher_id = int(voucher_id)
            company = self._fetch_company(resolved_company_id)
            invoice = self._fetch_sales_header(resolved_company_id, resolved_voucher_id)
            if not company or not invoice:
                LOGGER.warning(
                    "Invoice data fetch blocked. company_id=%s voucher_id=%s",
                    resolved_company_id,
                    resolved_voucher_id,
                )
                return None
            amount_received = _amount_received_for_print(invoice)
            grand_total = _to_float(invoice.get("grand_total"))
            payment_mode = _text(invoice.get("payment_mode")).strip() or "Cash"
            printed_balance = _receipt_balance(payment_mode, amount_received, grand_total)
            invoice["payment_mode"] = payment_mode
            invoice["amount_received"] = amount_received
            invoice["tendered_amount"] = amount_received
            invoice["paid_amount"] = amount_received
            invoice["cash_received"] = amount_received
            invoice["balance"] = printed_balance
            invoice["printed_balance"] = printed_balance
            items = self._fetch_sales_items(resolved_company_id, resolved_voucher_id)
            return {
                "company": company,
                "invoice": invoice,
                "items": items,
                "print_settings": get_print_settings(self.db, resolved_company_id),
            }
        except (TypeError, ValueError) as exc:
            LOGGER.exception("Invalid invoice data identifiers: %s", exc)
        except Exception as exc:
            LOGGER.exception("Invoice data fetch failed unexpectedly: %s", exc)
        return None

    def _normalize_format(self, format_type: Any) -> str:
        """
        Normalize caller print format names to a supported template key.

        Returns:
            ``a4`` for the A4 template or ``thermal`` for the 80mm template.
        """
        clean_format = _text(format_type).strip().lower()
        if clean_format in {"thermal", "thermal_80mm", "thermal-80mm", "80mm"}:
            return "thermal"
        return "a4"

    def _normalize_theme(self, theme: Any) -> str:
        """
        Normalize caller theme names to a supported A4 template key.

        Unknown values intentionally fall back to ``classic`` so existing print
        flows continue without user-visible failures.
        """
        clean_theme = _text(theme).strip().lower()
        if clean_theme in {"modern", "modern pink", "pink modern"}:
            return "modern"
        return "classic"

    def _read_template(self, format_type: str, theme: str) -> str:
        """
        Read the requested invoice template from the root templates directory.

        Args:
            format_type: Normalized template key from ``_normalize_format``.
            theme: Normalized A4 theme key from ``_normalize_theme``.
        """
        if format_type == "thermal":
            file_name = "invoice_thermal.html"
        elif theme == "modern":
            file_name = "invoice_a4_modern.html"
        else:
            file_name = "invoice_a4_classic.html"
        template_path = self.templates_dir / file_name
        with open(template_path, "r", encoding="utf-8") as template_file:
            return template_file.read()

    def _fetch_company(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch company details for the selected tenant.

        Args:
            company_id: Tenant company id used as the company firewall.
        """
        ph = self.db._get_placeholder()
        try:
            rows = self.db.execute_query(
                f"""
                SELECT
                    id,
                    business_name,
                    address,
                    phone_number,
                    gstin,
                    gst_type,
                    signature_path,
                    print_signature
                FROM companies
                WHERE id = {ph}
                """,
                (company_id,),
            )
            return rows[0] if rows else None
        except Exception as exc:
            LOGGER.exception("Company query failed for invoice rendering: %s", exc)
            return None

    def _fetch_sales_header(
        self,
        company_id: int,
        voucher_id: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch one sales voucher header within the requested company scope.

        Args:
            company_id: Tenant company id used as the company firewall.
            voucher_id: Sales table primary key.
        """
        ph = self.db._get_placeholder()
        try:
            rows = self.db.execute_query(
                f"""
                SELECT
                    s.id,
                    s.company_id,
                    s.invoice_number,
                    s.invoice_date,
                    s.party_id,
                    s.sales_type,
                    s.nature,
                    s.address,
                    s.gstin,
                    s.sub_total,
                    s.discount_total,
                    s.tax_total,
                    s.round_off,
                    s.grand_total,
                    s.amount_received,
                    s.payment_mode,
                    COALESCE(p.name, '') AS customer_name,
                    COALESCE(p.mobile_number, '') AS customer_phone,
                    COALESCE(p.address, '') AS party_address,
                    COALESCE(p.gstin, '') AS party_gstin
                FROM sales s
                LEFT JOIN parties p
                    ON p.id = s.party_id
                   AND p.company_id = s.company_id
                WHERE s.company_id = {ph}
                  AND s.id = {ph}
                """,
                (company_id, voucher_id),
            )
            return rows[0] if rows else None
        except Exception as exc:
            LOGGER.exception("Sales header query failed for invoice rendering: %s", exc)
            return None

    def _fetch_sales_items(
        self,
        company_id: int,
        voucher_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch sales items through a company-scoped sales header join.

        The ``sales_items`` table does not own ``company_id``, so the tenant
        firewall is enforced by joining to ``sales`` with both voucher id and
        company id before reading child rows.
        """
        ph = self.db._get_placeholder()
        try:
            return self.db.execute_query(
                f"""
                SELECT
                    si.id,
                    si.sale_id,
                    si.product_id,
                    si.sl_no,
                    si.hsn,
                    si.tax_percent,
                    si.cgst,
                    si.sgst,
                    si.igst,
                    si.cess,
                    si.unit,
                    si.rate,
                    si.quantity,
                    si.gross_value,
                    si.discount,
                    si.net_value,
                    si.tax_amount,
                    si.grand_total,
                    si.cgst_amount,
                    si.sgst_amount,
                    si.igst_amount,
                    si.cess_amount,
                    COALESCE(pr.name, '') AS item_name,
                    COALESCE(pr.barcode, '') AS barcode
                FROM sales_items si
                INNER JOIN sales s
                    ON s.id = si.sale_id
                   AND s.company_id = {ph}
                   AND s.id = {ph}
                LEFT JOIN products pr
                    ON pr.id = si.product_id
                   AND pr.company_id = s.company_id
                ORDER BY si.sl_no, si.id
                """,
                (company_id, voucher_id),
            )
        except Exception as exc:
            LOGGER.exception("Sales item query failed for invoice rendering: %s", exc)
            return []

    def _build_context(
        self,
        company: Dict[str, Any],
        invoice: Dict[str, Any],
        items: List[Dict[str, Any]],
        format_type: str,
        print_settings: Dict[str, str],
    ) -> Dict[str, str]:
        """
        Build escaped placeholder values used by invoice templates.

        Args:
            company: Company row from the tenant-scoped company query.
            invoice: Sales header row from the tenant-scoped sales query.
            items: Sales item rows from the tenant-scoped item query.
            format_type: Normalized print format for row rendering.
        """
        is_composition = _text(company.get("gst_type")).strip().lower() == "composition"
        is_bill_of_supply = _text(invoice.get("sales_type")).strip().lower() == "bill of supply"
        render_bill_of_supply = is_composition or is_bill_of_supply
        cgst_total = 0.0 if render_bill_of_supply else sum(_to_float(item.get("cgst_amount")) for item in items)
        sgst_total = 0.0 if render_bill_of_supply else sum(_to_float(item.get("sgst_amount")) for item in items)
        igst_total = 0.0 if render_bill_of_supply else sum(_to_float(item.get("igst_amount")) for item in items)
        cess_total = 0.0 if render_bill_of_supply else sum(_to_float(item.get("cess_amount")) for item in items)
        tax_total = 0.0 if render_bill_of_supply else _to_float(invoice.get("tax_total"))
        amount_received = _amount_received_for_print(invoice)
        grand_total = _to_float(invoice.get("grand_total"))
        payment_mode = _text(invoice.get("payment_mode")).strip() or "Cash"
        balance = _receipt_balance(payment_mode, amount_received, grand_total)
        customer_address = invoice.get("address") or invoice.get("party_address") or ""
        customer_gstin = invoice.get("gstin") or invoice.get("party_gstin") or ""
        header_quote = _text(print_settings.get("header_quote")).strip()
        footer_terms = _text(print_settings.get("footer_terms")).strip()

        return {
            "company_name": _escape(company.get("business_name")),
            "company_address": _escape(company.get("address")),
            "company_phone": _escape(company.get("phone_number")),
            "company_gstin": _escape(company.get("gstin")),
            "gst_type": _escape(company.get("gst_type") or "Regular"),
            "invoice_title": "BILL OF SUPPLY" if render_bill_of_supply else "TAX INVOICE",
            "composition_note": (
                "(Composition Taxable Person, Not Eligible To Collect Taxes)"
                if is_composition
                else ("Tax not collected on Bill of Supply" if is_bill_of_supply else "")
            ),
            "header_quote": _escape(header_quote),
            "header_quote_block": f'<div class="header-quote">{_escape(header_quote)}</div>' if header_quote else "",
            "footer_terms": _escape(footer_terms),
            "footer_terms_block": f'<div class="terms">{_escape(footer_terms)}</div>' if footer_terms else "",
            "is_composition": "1" if render_bill_of_supply else "0",
            "voucher_no": _escape(invoice.get("invoice_number")),
            "invoice_date": _escape(invoice.get("invoice_date")),
            "customer_name": _escape(invoice.get("customer_name") or "Cash Customer"),
            "customer_address": _escape(customer_address),
            "customer_phone": _escape(invoice.get("customer_phone")),
            "customer_gstin": _escape(customer_gstin),
            "sales_type": _escape(invoice.get("sales_type")),
            "subtotal": _escape(_money(invoice.get("sub_total"))),
            "discount_total": _escape(_money(invoice.get("discount_total"))),
            "tax_total": _escape(_money(tax_total)),
            "cgst_total": _escape(_money(cgst_total)),
            "sgst_total": _escape(_money(sgst_total)),
            "igst_total": _escape(_money(igst_total)),
            "cess_total": _escape(_money(cess_total)),
            "round_off": _escape(_money(invoice.get("round_off"))),
            "grand_total": _escape(_money(grand_total)),
            "amount_received": _escape(_money(amount_received)),
            "tendered_amount": _escape(_money(amount_received)),
            "paid_amount": _escape(_money(amount_received)),
            "balance": _escape(_money(balance)),
            "amount_in_words": _escape(_amount_to_words(grand_total)),
            "payment_mode": _escape(payment_mode),
            "item_rows": self._render_item_rows(items, format_type, render_bill_of_supply),
            "generated_at": _escape(datetime.now().strftime("%Y-%m-%d %H:%M")),
        }

    def _render_item_rows(
        self,
        items: List[Dict[str, Any]],
        format_type: str,
        is_composition: bool,
    ) -> str:
        """
        Render escaped item row HTML for either A4 or thermal templates.

        Args:
            items: Sales item rows returned from ``_fetch_sales_items``.
            format_type: Normalized print format from ``_normalize_format``.
        """
        if format_type == "thermal":
            return self._render_thermal_item_rows(items, is_composition)
        return self._render_a4_item_rows(items, is_composition)

    def _render_a4_item_rows(self, items: List[Dict[str, Any]], is_composition: bool) -> str:
        """
        Render table rows for the professional A4 invoice template.

        Args:
            items: Sales item rows returned from the database.
        """
        if not items:
            return '<tr><td colspan="9" class="center">No items found</td></tr>'

        rows = []
        for index, item in enumerate(items, start=1):
            sl_no = item.get("sl_no") or index
            item_name = item.get("item_name") or f"Item {index}"
            rows.append(
                """
                <tr>
                    <td class="center">{sl_no}</td>
                    <td>{item_name}</td>
                    <td>{hsn}</td>
                    <td class="right">{quantity}</td>
                    <td>{unit}</td>
                    <td class="right">{rate}</td>
                    <td class="right">{taxable}</td>
                    <td class="right">{tax}</td>
                    <td class="right">{total}</td>
                </tr>
                """.format(
                    sl_no=_escape(sl_no),
                    item_name=_escape(item_name),
                    hsn=_escape(item.get("hsn")),
                    quantity=_escape(_money(item.get("quantity"))),
                    unit=_escape(item.get("unit")),
                    rate=_escape(_money(item.get("rate"))),
                    taxable=_escape(_money(item.get("net_value"))),
                    tax=_escape(_money(0.0 if is_composition else item.get("tax_amount"))),
                    total=_escape(_money(item.get("grand_total"))),
                )
            )
        return "".join(rows)

    def _render_thermal_item_rows(self, items: List[Dict[str, Any]], is_composition: bool) -> str:
        """
        Render compact item rows optimized for an 80mm thermal receipt.

        Args:
            items: Sales item rows returned from the database.
        """
        if not items:
            return '<tr><td colspan="5" class="center">No items found</td></tr>'

        rows = []
        for index, item in enumerate(items, start=1):
            item_name = item.get("item_name") or f"Item {index}"
            rows.append(
                """
                <tr>
                    <td class="center">{sl_no}</td>
                    <td>{item_name}</td>
                    <td class="right">{quantity}</td>
                    <td class="right">{rate}</td>
                    <td class="right">{total}</td>
                </tr>
                """.format(
                    sl_no=_escape(item.get("sl_no") or index),
                    item_name=_escape(item_name),
                    quantity=_escape(_money(item.get("quantity"))),
                    rate=_escape(_money(item.get("rate"))),
                    total=_escape(_money(item.get("grand_total"))),
                )
            )
        return "".join(rows)

    def _replace_placeholders(self, template: str, context: Dict[str, str]) -> str:
        """
        Replace known Jinja2-style placeholders with escaped invoice values.

        Args:
            template: Raw HTML template string from the templates directory.
            context: Whitelisted placeholder values built by ``_build_context``.
        """
        rendered_html = template
        for key, value in context.items():
            rendered_html = rendered_html.replace(f"{{{{ {key} }}}}", value)
        return rendered_html
