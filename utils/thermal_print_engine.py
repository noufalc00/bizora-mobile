"""
WebEngine-backed 80mm thermal receipt print engine for Faizan Pro Accounting.

The module renders escaped compact receipt HTML and sends it through PySide6's
Chromium/QPrinter pipeline, mirroring the A4 print engine's physical route.
"""

from __future__ import annotations

import html
import json
import os
import tempfile
from typing import Any, Mapping, Optional, Sequence

from PySide6.QtCore import (
    QCoreApplication,
    QEventLoop,
    QMarginsF,
    QSizeF,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QDesktopServices, QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from utils.print_time_format import PRINT_TIME_KEY, append_print_time_to_date

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional runtime dependency
    fitz = None


THERMAL_ROLL_WIDTH_MM = 80.0
THERMAL_ROLL_HEIGHT_MM = 1000.0
THERMAL_MARGIN_MM = 0.0
THERMAL_VIEW_WIDTH_PX = 302
THERMAL_VIEW_HEIGHT_PX = 1200
WEBENGINE_LOAD_TIMEOUT_MS = 15000
WEBENGINE_PRINT_TIMEOUT_MS = 30000
_thermal_print_view = None
SHOW_ITEM_BARCODE_BELOW_NAME_KEY = "show_item_barcode_below_name"
SHOW_ITEM_BARCODE_BELOW_NAME_ALIASES = (
    SHOW_ITEM_BARCODE_BELOW_NAME_KEY,
    "show_barcode_below_name",
    "item_barcode_below_name",
    "show_item_barcode",
)


def _text(value: Any) -> str:
    """Return a safe string for nullable display values."""
    return "" if value is None else str(value)


def _escape(value: Any) -> str:
    """Escape dynamic text before placing it inside thermal receipt HTML."""
    return html.escape(_text(value), quote=True)


def _escape_multiline(value: Any) -> str:
    """Escape multiline receipt text while preserving line breaks."""
    escaped_text = _escape(value)
    return escaped_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def _to_float(value: Any) -> float:
    """Convert numeric inputs to float while tolerating blank UI values."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _money(value: Any) -> str:
    """Format a numeric amount with two decimals for receipt display."""
    return f"{_to_float(value):.2f}"


def _first_value(data: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    """Return the first non-empty value from a mapping using alias keys."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _section(data: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    """Return a nested dictionary section if present, otherwise an empty mapping."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _saved_bool(value: Any) -> bool:
    """Return a boolean from saved print-setting values and JSON metadata."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "checked"}


def _layout_metadata(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return saved print designer metadata from layout coordinates."""
    raw_coordinates = settings.get("layout_coordinates", "") or ""
    if not raw_coordinates:
        return {}
    try:
        coordinates = json.loads(_text(raw_coordinates))
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(coordinates, Mapping):
        return {}
    metadata = coordinates.get("__settings__", {})
    return metadata if isinstance(metadata, Mapping) else {}


def _setting_bool_from_mapping(settings: Mapping[str, Any]) -> Optional[bool]:
    """Resolve barcode-below-name from direct settings or layout metadata aliases."""
    metadata = _layout_metadata(settings)
    for source in (metadata, settings):
        for key in SHOW_ITEM_BARCODE_BELOW_NAME_ALIASES:
            if key in source:
                return _saved_bool(source.get(key))
    return None


def _resolve_show_item_barcode_below_name(
    transaction_data: Mapping[str, Any],
    show_item_barcode_below_name: Optional[bool],
) -> bool:
    """Resolve the item barcode placement setting for thermal receipts."""
    if show_item_barcode_below_name is not None:
        return _saved_bool(show_item_barcode_below_name)

    for section_key in ("print_settings", "settings", "receipt_settings"):
        settings = transaction_data.get(section_key)
        if isinstance(settings, Mapping):
            resolved = _setting_bool_from_mapping(settings)
            if resolved is not None:
                return resolved

    resolved = _setting_bool_from_mapping(transaction_data)
    if resolved is not None:
        return resolved

    # Preserve the historical thermal renderer behavior when callers do not
    # provide print settings.
    return True


def _sequence(data: Mapping[str, Any], *keys: str) -> Sequence[Mapping[str, Any]]:
    """Return a sequence of item mappings from common transaction aliases."""
    for key in keys:
        value = data.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def _render_optional_line(label: str, value: Any, multiline: bool = False) -> str:
    """Render a compact labeled line only when the value is available."""
    if value in (None, ""):
        return ""
    safe_value = _escape_multiline(value) if multiline else _escape(value)
    return (
        '<div class="line">'
        f'<span class="label">{_escape(label)}:</span> {safe_value}'
        "</div>"
    )


def _render_item_rows(
    items: Sequence[Mapping[str, Any]],
    show_barcode_below_name: bool = True,
) -> str:
    """Render escaped receipt item rows optimized for narrow 80mm paper."""
    if not items:
        return (
            '<tr><td colspan="5" style="text-align: center; vertical-align: top;">'
            "No items found"
            "</td></tr>"
        )

    rows = []
    for row_index, item in enumerate(items, start=1):
        serial_no = _first_value(item, "sl_no", "sl", "serial_no", default=row_index)
        item_name = _first_value(
            item,
            "item_name",
            "product_name",
            "name",
            "description",
            default="Item",
        )
        quantity = _first_value(item, "quantity", "qty", default=0)
        rate = _first_value(item, "rate", "price", "unit_price", default=0)
        barcode = _first_value(
            item,
            "barcode",
            "bar_code",
            "item_code",
            "product_code",
            "code",
            default="",
        )
        amount = _first_value(
            item,
            "grand_total",
            "line_total",
            "total",
            "amount",
            default=_to_float(quantity) * _to_float(rate),
        )
        safe_item_name = _escape(item_name)
        barcode_text = _text(barcode).strip()
        safe_barcode = _escape(barcode_text)
        if show_barcode_below_name:
            barcode_line = (
                f'<br/><span style="font-size: 10px; color: #555;">BC: {safe_barcode}</span>'
                if barcode_text
                else ""
            )
            item_display = f'<span style="font-weight: bold;">{safe_item_name}</span>{barcode_line}'
        else:
            item_label = (
                f"{safe_barcode} - {safe_item_name}"
                if barcode_text
                else safe_item_name
            )
            item_display = f'<span style="font-weight: bold;">{item_label}</span>'
        rows.append(
            "<tr>"
            f'<td style="width: 10%; text-align: left; vertical-align: top;">{_escape(serial_no)}</td>'
            '<td style="width: 40%; text-align: left; vertical-align: top; word-wrap: break-word;">'
            f"{item_display}"
            "</td>"
            f'<td style="width: 14%; text-align: right; vertical-align: top;">{_escape(_money(quantity))}</td>'
            f'<td style="width: 17%; text-align: right; vertical-align: top;">{_escape(_money(rate))}</td>'
            f'<td style="width: 19%; text-align: right; vertical-align: top;">{_escape(_money(amount))}</td>'
            "</tr>"
        )
    return "".join(rows)


def _render_total_rows(
    transaction_data: Mapping[str, Any],
    totals_data: Mapping[str, Any],
) -> str:
    """Render compact total and tax rows from flat or nested transaction data."""
    source_data = dict(transaction_data)
    source_data.update(dict(totals_data))
    row_specs = (
        ("Sub Total", ("subtotal", "sub_total", "taxable_total")),
        ("Discount", ("discount", "discount_total")),
        ("CGST", ("cgst", "cgst_total")),
        ("SGST", ("sgst", "sgst_total")),
        ("CESS", ("cess", "cess_total", "total_cess")),
        ("Round Off", ("round_off",)),
    )
    rows = []
    for label, keys in row_specs:
        value = _first_value(source_data, *keys, default="")
        if value not in (None, "") and abs(_to_float(value)) > 0:
            rows.append(
                "<tr>"
                f"<td>{_escape(label)}</td>"
                f'<td class="right">{_escape(_money(value))}</td>'
                "</tr>"
            )

    grand_total = _first_value(
        source_data,
        "grand_total",
        "total",
        "total_amount",
        "net_amount",
        default=0,
    )
    rows.append(
        '<tr class="grand-total">'
        "<td>Grand Total</td>"
        f'<td class="right">{_escape(_money(grand_total))}</td>'
        "</tr>"
    )
    return "".join(rows)


def generate_thermal_html(
    transaction_data: Mapping[str, Any],
    type: str = "sales",
    show_item_barcode_below_name: Optional[bool] = None,
    document_title: str = "Tax Invoice",
    theme_name: Optional[str] = None,
) -> str:
    """
    Return complete escaped HTML for an 80mm thermal receipt.

    Args:
        transaction_data: Flat or nested sales transaction data containing company,
            item, total, payment, and optional footer details.
        type: Receipt type label. ``sales`` is supported by default and other
            values are rendered as a readable receipt title.
        show_item_barcode_below_name: Optional setting override for whether the
            barcode prints on a second line under the item name.
        document_title: Header title to render for the printed document. Existing
            data-level ``document_title`` values are still honored.
        theme_name: Optional explicit thermal theme override. When omitted, the
            renderer resolves embedded ``thermal_theme``/``theme`` settings.
    """
    safe_data = transaction_data or {}
    company_data = _section(safe_data, "company", "company_data", "business")
    totals_data = _section(safe_data, "totals", "totals_data", "summary")
    payment_data = _section(safe_data, "payment", "payment_data")
    items = _sequence(safe_data, "items", "cart_data", "cart", "products", "lines")
    show_barcode_below_name = _resolve_show_item_barcode_below_name(
        safe_data,
        show_item_barcode_below_name,
    )

    # Resolve thermal theme variables from the explicit argument, embedded
    # transaction settings, layout metadata, and legacy flat transaction keys.
    settings_sources: list[Mapping[str, Any]] = []
    for section_key in ("print_settings", "settings", "receipt_settings"):
        section_value = safe_data.get(section_key)
        if isinstance(section_value, Mapping):
            metadata = _layout_metadata(section_value)
            if isinstance(metadata, Mapping):
                settings_sources.append(metadata)
            settings_sources.append(section_value)
    metadata = _layout_metadata(safe_data)
    if isinstance(metadata, Mapping):
        settings_sources.append(metadata)
    settings_sources.append(safe_data)

    requested_theme = _text(theme_name).strip()
    if not requested_theme:
        for settings_source in settings_sources:
            requested_theme = _text(
                _first_value(
                    settings_source,
                    "thermal_theme",
                    "theme",
                    "default_theme",
                    default="",
                )
            ).strip()
            if requested_theme:
                break

    resolved_theme_name = requested_theme or "Classic POS"
    theme_aliases = {
        "Classic": "Classic POS",
        "Classic Thermal": "Classic POS",
        "Retail Compact": "Compact Retail",
    }
    resolved_theme_name = theme_aliases.get(resolved_theme_name, resolved_theme_name)
    thermal_theme_names = {
        "Classic POS",
        "Compact Retail",
        "Elegant Bill",
        "Modern Invoice",
        "Bold Total",
    }
    if resolved_theme_name not in thermal_theme_names:
        resolved_theme_name = "Classic POS"

    bg_color = "#FFFFFF"
    text_color = "#000000"
    muted_color = "#444444"
    border_color = "#000000"
    header_bg = "#FFFFFF"
    font_family = "Arial, sans-serif"
    font_size = "12px"
    border_style = "1px dashed #000000"
    header_align = "center"
    header_font_size = "11px"
    header_text_transform = "none"
    title_border_style = border_style
    title_letter_spacing = "0"
    company_name_weight = "bold"
    total_border_style = border_style
    footer_align = "center"
    if resolved_theme_name == "Compact Retail":
        font_family = '"Arial Narrow", Arial, sans-serif'
        font_size = "11px"
        header_font_size = "10px"
        border_style = "1px dotted #000000"
        title_border_style = border_style
        total_border_style = "1px solid #000000"
    elif resolved_theme_name == "Elegant Bill":
        font_family = '"Times New Roman", Times, serif'
        font_size = "12px"
        border_style = "1px solid #000000"
        header_text_transform = "uppercase"
        title_letter_spacing = "0.6px"
        title_border_style = "2px solid #000000"
        total_border_style = "2px double #000000"
    elif resolved_theme_name == "Modern Invoice":
        font_family = '"Segoe UI", Arial, sans-serif'
        font_size = "12px"
        muted_color = "#333333"
        border_style = "1px solid #000000"
        header_align = "left"
        header_font_size = "11px"
        title_border_style = "1px solid #000000"
        total_border_style = "2px solid #000000"
        footer_align = "left"
    elif resolved_theme_name == "Bold Total":
        font_family = "Arial, sans-serif"
        font_size = "12px"
        border_style = "1px dashed #000000"
        header_text_transform = "uppercase"
        title_border_style = "2px solid #000000"
        total_border_style = "3px double #000000"
        company_name_weight = "800"

    company_name = _first_value(
        company_data,
        "company_name",
        "business_name",
        "name",
        default=_first_value(safe_data, "company_name", "business_name", default="Company Name"),
    )
    company_address = _first_value(
        company_data,
        "company_address",
        "address",
        default=_first_value(safe_data, "company_address", "address"),
    )
    company_phone = _first_value(
        company_data,
        "phone",
        "phone_number",
        "mobile",
        default=_first_value(safe_data, "phone", "phone_number", "mobile"),
    )
    company_gstin = _first_value(
        company_data,
        "company_gstin",
        "gstin",
        default=_first_value(safe_data, "company_gstin", "gstin"),
    )
    receipt_title = _first_value(
        safe_data,
        "document_title",
        "title",
        default=document_title,
    )
    bill_no = _first_value(
        safe_data,
        "bill_no",
        "invoice_number",
        "voucher_no",
        default=_first_value(totals_data, "bill_no", "invoice_number", "voucher_no"),
    )
    bill_date = _first_value(
        safe_data,
        "date",
        "bill_date",
        "invoice_date",
        default=_first_value(totals_data, "date", "bill_date", "invoice_date"),
    )
    print_time_enabled = False
    for settings_source in settings_sources:
        if PRINT_TIME_KEY in settings_source:
            print_time_enabled = _saved_bool(settings_source.get(PRINT_TIME_KEY))
            break
    bill_date = append_print_time_to_date(bill_date, include_time=print_time_enabled)
    customer_name = _first_value(
        safe_data,
        "customer_name",
        "party_name",
        default=_first_value(totals_data, "customer_name", "party_name", default="Cash Customer"),
    )
    payment_mode = _first_value(
        payment_data,
        "mode",
        "payment_mode",
        default=_first_value(safe_data, "payment_mode", "mode"),
    )
    amount_paid = _first_value(
        payment_data,
        "paid",
        "amount_paid",
        "paid_amount",
        "amount_received",
        "tendered_amount",
        "cash_received",
        "received",
        default=_first_value(
            safe_data,
            "amount_paid",
            "paid_amount",
            "amount_received",
            "tendered_amount",
            "cash_received",
            "paid",
            "received",
        ),
    )
    balance = _first_value(
        payment_data,
        "balance",
        "printed_balance",
        "balance_amount",
        default=_first_value(safe_data, "balance", "printed_balance", "balance_amount"),
    )
    if balance in (None, "") and amount_paid not in (None, ""):
        balance = (
            _to_float(amount_paid) - _to_float(_first_value(totals_data, "grand_total", "total", "total_amount", default=0))
            if _text(payment_mode).strip().lower() == "cash"
            else 0.0
        )
    footer = _first_value(
        safe_data,
        "footer",
        "footer_text",
        "thermal_footer",
        "terms_conditions",
        default="",
    )

    company_lines = "".join(
        (
            f'<div class="company-name">{_escape(company_name)}</div>',
            f'<div>{_escape_multiline(company_address)}</div>' if company_address else "",
            _render_optional_line("GSTIN", company_gstin),
            _render_optional_line("Phone", company_phone),
        )
    )
    payment_lines = "".join(
        (
            _render_optional_line("Payment Mode", payment_mode),
            _render_optional_line("Paid", _money(amount_paid) if amount_paid not in (None, "") else ""),
            _render_optional_line("Balance", _money(balance) if balance not in (None, "") else ""),
        )
    )

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        :root {{
            --bg-color: {bg_color};
            --text-color: {text_color};
            --muted-color: {muted_color};
            --border-color: {border_color};
            --header-bg: {header_bg};
            --font-family: {font_family};
            --theme-border-style: {border_style};
            --title-border-style: {title_border_style};
            --total-border-style: {total_border_style};
        }}
        @page {{ margin: 0; }}
        body {{
            background-color: {bg_color};
            color: {text_color};
            width: 260px;
            margin: 0;
            padding-right: 5px;
            font-family: {font_family};
            font-size: {font_size};
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
        }}
        th, td {{
            padding: 2px 2px;
            line-height: 1.2;
            overflow-wrap: break-word;
            vertical-align: top;
        }}
        th {{
            background-color: {header_bg};
            border-bottom: {border_style};
            font-weight: bold;
            text-align: center;
        }}
        hr {{
            border-top: {border_style};
        }}
        .header-text {{
            background-color: {header_bg};
            text-align: {header_align};
            font-size: {header_font_size};
            text-transform: {header_text_transform};
        }}
        .receipt {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            width: 100%;
        }}
        .center {{
            text-align: center;
        }}
        .right {{
            text-align: right;
        }}
        .muted {{
            color: {muted_color};
        }}
        .company-name {{
            font-weight: {company_name_weight};
            text-transform: uppercase;
        }}
        .title {{
            border-bottom: {title_border_style};
            border-top: {title_border_style};
            font-weight: bold;
            letter-spacing: {title_letter_spacing};
            margin: 3px 0;
            padding: 2px 0;
            text-align: center;
            text-transform: uppercase;
        }}
        .line {{
            line-height: 1.25;
        }}
        .label {{
            font-weight: bold;
        }}
        .meta {{
            border-bottom: {border_style};
            margin-bottom: 2px;
            padding-bottom: 2px;
        }}
        .totals {{
            border-top: {total_border_style};
            margin-top: 2px;
            padding-top: 2px;
        }}
        .totals td:first-child {{
            width: 58%;
        }}
        .grand-total td {{
            border-top: {total_border_style};
            font-weight: bold;
            padding-top: 2px;
        }}
        .footer {{
            border-top: {border_style};
            margin-top: 3px;
            padding-top: 2px;
            text-align: {footer_align};
        }}
    </style>
</head>
<body>
    <div class="receipt">
        <div class="header-text">{company_lines}</div>
        <div class="title">{_escape(receipt_title)}</div>
        <div class="meta">
            {_render_optional_line("Bill No", bill_no)}
            {_render_optional_line("Date", bill_date)}
            {_render_optional_line("Customer", customer_name)}
        </div>
        <table style="width: 100%; table-layout: fixed; border-collapse: collapse;">
            <thead>
                <tr>
                    <th style="width: 10%; text-align: left;">SN</th>
                    <th style="width: 40%; text-align: left;">Item</th>
                    <th style="width: 14%; text-align: right;">Qty</th>
                    <th style="width: 17%; text-align: right;">Rate</th>
                    <th style="width: 19%; text-align: right;">Total</th>
                </tr>
            </thead>
            <tbody>{_render_item_rows(items, show_barcode_below_name)}</tbody>
        </table>
        <table class="totals">{_render_total_rows(safe_data, totals_data)}</table>
        <div class="payment">{payment_lines}</div>
        <div class="footer">{_escape_multiline(footer) if footer else "Thank you!"}</div>
    </div>
</body>
</html>
"""


def _webengine_print_method(page: QWebEnginePage) -> Any:
    """Return the installed WebEngine physical print method, if Qt exposes one."""
    return getattr(page, "print", None) or getattr(page, "print_", None)


def _create_temp_pdf_path() -> str:
    """Reserve a Windows-safe temporary path for thermal fallback PDF generation."""
    handle, file_path = tempfile.mkstemp(prefix="faizan_thermal_receipt_", suffix=".pdf")
    os.close(handle)
    return file_path


def _set_native_output_format(printer: QPrinter) -> None:
    """Force QPrinter to use the Windows native spooler for physical printing."""
    output_format_type = getattr(QPrinter, "OutputFormat", None)
    native_format = (
        getattr(output_format_type, "NativeFormat", None)
        if output_format_type is not None
        else getattr(QPrinter, "NativeFormat", None)
    )
    if native_format is not None:
        printer.setOutputFormat(native_format)


def configure_thermal_printer_page(printer: QPrinter) -> None:
    """Apply an 80mm custom receipt roll page size when the driver permits it."""
    try:
        printer.setFullPage(True)
    except Exception:
        pass

    try:
        page_size = QPageSize(
            QSizeF(THERMAL_ROLL_WIDTH_MM, THERMAL_ROLL_HEIGHT_MM),
            QPageSize.Unit.Millimeter,
            "80mm Thermal Receipt",
        )
        printer.setPageSize(page_size)
    except Exception:
        # Some Windows thermal drivers only accept paper configured in the
        # printer preferences, so retain the driver/default paper in that case.
        pass

    try:
        printer.setPageMargins(
            QMarginsF(
                THERMAL_MARGIN_MM,
                THERMAL_MARGIN_MM,
                THERMAL_MARGIN_MM,
                THERMAL_MARGIN_MM,
            ),
            QPageLayout.Unit.Millimeter,
        )
    except Exception:
        pass


def _thermal_page_layout() -> QPageLayout:
    """Return a custom 80mm roll layout for WebEngine PDF fallback output."""
    page_size = QPageSize(
        QSizeF(THERMAL_ROLL_WIDTH_MM, THERMAL_ROLL_HEIGHT_MM),
        QPageSize.Unit.Millimeter,
        "80mm Thermal Receipt",
    )
    return QPageLayout(
        page_size,
        QPageLayout.Orientation.Portrait,
        QMarginsF(THERMAL_MARGIN_MM, THERMAL_MARGIN_MM, THERMAL_MARGIN_MM, THERMAL_MARGIN_MM),
        QPageLayout.Unit.Millimeter,
    )


def render_thermal_html_to_printer(html_string: str, printer: QPrinter) -> None:
    """Render thermal HTML through Chromium's WebEngine physical print pipeline."""
    global _thermal_print_view

    if QApplication.instance() is None:
        raise RuntimeError("A QApplication must exist before thermal WebEngine printing starts.")

    _thermal_print_view = QWebEngineView()
    _thermal_print_view.resize(THERMAL_VIEW_WIDTH_PX, THERMAL_VIEW_HEIGHT_PX)
    _thermal_print_view.move(-32000, -32000)
    _thermal_print_view.show()
    print(
        "[THERMAL_PRINT] using WebEngineView print "
        f"printer='{printer.printerName() or 'default'}' "
        f"html_len={len(_text(html_string))}"
    )
    load_success = {"value": None, "timed_out": False}
    load_loop = QEventLoop()
    load_timer = QTimer()
    load_timer.setSingleShot(True)

    def on_load_finished(success: bool) -> None:
        """Stop the local event loop once Chromium finishes loading HTML."""
        load_success["value"] = bool(success)
        if load_timer.isActive():
            load_timer.stop()
        print(
            "[THERMAL_PRINT] WebEngine loadFinished "
            f"success={bool(success)} "
            f"printer='{printer.printerName() or 'default'}'"
        )
        load_loop.quit()

    def on_load_timeout() -> None:
        """Stop waiting when Chromium does not report HTML load completion."""
        load_success["timed_out"] = True
        print(
            "[THERMAL_PRINT] WebEngine load timeout "
            f"timeout_ms={WEBENGINE_LOAD_TIMEOUT_MS} "
            f"printer='{printer.printerName() or 'default'}'"
        )
        load_loop.quit()

    _thermal_print_view.loadFinished.connect(on_load_finished)
    load_timer.timeout.connect(on_load_timeout)
    load_timer.start(WEBENGINE_LOAD_TIMEOUT_MS)
    _thermal_print_view.setHtml(_text(html_string))
    if load_success["value"] is None and not load_success["timed_out"]:
        load_loop.exec()

    if load_success["timed_out"]:
        raise RuntimeError(
            "QWebEngineView did not finish loading thermal receipt HTML before timeout."
        )
    if load_success["value"] is not True:
        raise RuntimeError("QWebEngineView failed to load thermal receipt HTML.")

    print_success = {"value": None, "timed_out": False}
    print_loop = QEventLoop()
    print_timer = QTimer()
    print_timer.setSingleShot(True)

    def on_print_finished(*args: Any) -> None:
        """Accept PySide6/PyQt6 print callback variants and unblock printing."""
        print_success["value"] = bool(args[0]) if args else True
        if print_timer.isActive():
            print_timer.stop()
        print(
            "[THERMAL_PRINT] WebEngine print callback "
            f"success={print_success['value']} "
            f"printer='{printer.printerName() or 'default'}' "
            f"args={args}"
        )
        print_loop.quit()

    def on_print_timeout() -> None:
        """Stop waiting when Chromium does not report print completion."""
        print_success["timed_out"] = True
        print(
            "[THERMAL_PRINT] WebEngine print timeout "
            f"timeout_ms={WEBENGINE_PRINT_TIMEOUT_MS} "
            f"printer='{printer.printerName() or 'default'}'"
        )
        print_loop.quit()

    print_method = _webengine_print_method(_thermal_print_view.page())
    if print_method is None:
        raise RuntimeError("QWebEngineView page print method is unavailable.")
    print_timer.timeout.connect(on_print_timeout)
    print_timer.start(WEBENGINE_PRINT_TIMEOUT_MS)
    print_method(printer, on_print_finished)
    if print_success["value"] is None and not print_success["timed_out"]:
        print_loop.exec()

    if print_success["timed_out"]:
        raise RuntimeError(
            "Chromium did not report thermal print completion before timeout. "
            f"Printer: '{printer.printerName() or 'default'}'."
        )
    if print_success["value"] is not True:
        raise RuntimeError(
            "Chromium print engine failed to send the thermal receipt to the printer spooler. "
            f"Printer: '{printer.printerName() or 'default'}'."
        )


def export_thermal_pdf(html_string: str, file_path: str) -> None:
    """
    Export thermal receipt HTML to PDF through QWebEnginePage's native PDF path.

    Raises:
        RuntimeError: If WebEngine cannot load the HTML or complete PDF export.
    """
    try:
        page = QWebEnginePage()
        print(
            "[THERMAL_PRINT] using WebEngine printToPdf "
            f"file='{file_path}' "
            f"html_len={len(_text(html_string))}"
        )
        load_success = {"value": False}
        load_loop = QEventLoop()

        def on_load_finished(success: bool) -> None:
            """Stop waiting once Chromium has fully loaded the receipt HTML."""
            load_success["value"] = bool(success)
            load_loop.quit()

        page.loadFinished.connect(on_load_finished)
        page.setHtml(_text(html_string))
        load_loop.exec()

        if not load_success["value"]:
            raise RuntimeError("QWebEnginePage failed to load thermal receipt HTML.")

        pdf_success = {"value": None}
        pdf_loop = QEventLoop()

        def on_pdf_printing_finished(path: str, success: bool) -> None:
            """Capture Qt's PDF completion signal before returning to callers."""
            del path
            pdf_success["value"] = bool(success)
            pdf_loop.quit()

        pdf_finished_signal = getattr(page, "pdfPrintingFinished", None)
        if pdf_finished_signal is None:
            raise RuntimeError("QWebEnginePage PDF completion signal is unavailable.")

        pdf_finished_signal.connect(on_pdf_printing_finished)
        page.printToPdf(file_path, _thermal_page_layout())
        pdf_loop.exec()

        if pdf_success["value"] is False:
            raise RuntimeError("QWebEnginePage thermal PDF export failed.")
        if pdf_success["value"] is None:
            raise RuntimeError("QWebEnginePage thermal PDF export did not report completion.")
    except Exception as exc:
        raise RuntimeError(f"Could not export thermal PDF: {exc}") from exc


def _open_pdf_for_manual_print(pdf_path: str) -> None:
    """Open a fallback PDF so the user can print manually from the PDF viewer."""
    opened = False
    try:
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(pdf_path)))
    except Exception:
        opened = False
    if not opened:
        try:
            os.startfile(pdf_path)  # type: ignore[attr-defined]
            opened = True
        except Exception as exc:
            raise RuntimeError(
                "PDF fallback was generated, but Windows could not open it for "
                f"manual printing. File: '{pdf_path}'. Error: {exc}"
            ) from exc
    print(f"[THERMAL_PRINT] PDF fallback opened for manual print file='{pdf_path}'")


def _try_windows_pdf_shell_print(pdf_path: str) -> str:
    """Ask Windows' registered PDF application to print the PDF fallback."""
    if os.name != "nt":
        raise RuntimeError("Windows shell PDF printing is unavailable on this OS.")
    try:
        os.startfile(pdf_path, "print")  # type: ignore[attr-defined]
    except Exception as exc:
        raise RuntimeError(f"Windows PDF print command failed: {exc}") from exc
    return (
        "WebEngine direct thermal print is unsupported in this Qt install. "
        "A PDF fallback was generated and sent to the Windows default PDF print command."
    )


def _paint_pdf_to_printer(pdf_path: str, printer: QPrinter) -> str:
    """Rasterize a generated thermal PDF and paint it to the selected printer."""
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF (fitz) is not installed, so direct PDF-to-printer fallback "
            "is unavailable."
        )

    pdf_doc = None
    painter = QPainter()
    try:
        pdf_doc = fitz.open(pdf_path)
        if not pdf_doc:
            raise RuntimeError("Generated PDF contains no pages.")
        if not painter.begin(printer):
            raise RuntimeError("Qt could not begin painting to the selected printer driver.")
        try:
            for page_index in range(len(pdf_doc)):
                if page_index > 0 and not printer.newPage():
                    raise RuntimeError(f"Printer driver refused page {page_index + 1}.")
                page = pdf_doc.load_page(page_index)
                pixmap = page.get_pixmap(dpi=203, alpha=False)
                image = QImage(
                    pixmap.samples,
                    pixmap.width,
                    pixmap.height,
                    pixmap.stride,
                    QImage.Format.Format_RGB888,
                )
                try:
                    target_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                except Exception:
                    target_rect = printer.paperRect(QPrinter.Unit.DevicePixel)
                if (
                    not target_rect.isValid()
                    or target_rect.width() <= 0
                    or target_rect.height() <= 0
                ):
                    target_rect = painter.viewport()
                painter.drawImage(target_rect, image)
                QCoreApplication.processEvents()
        finally:
            painter.end()
    except Exception as exc:
        raise RuntimeError(f"PDF fallback direct printer paint failed: {exc}") from exc
    finally:
        if pdf_doc is not None:
            pdf_doc.close()

    return (
        "WebEngine direct thermal print is unsupported in this Qt install. "
        f"PDF fallback was generated and painted to printer '{printer.printerName() or 'default'}'."
    )


def _print_generated_pdf_fallback(pdf_path: str, printer: QPrinter) -> str:
    """Print or open a generated PDF fallback using the safest available route."""
    try:
        message = _paint_pdf_to_printer(pdf_path, printer)
        print(
            "[THERMAL_PRINT] PDF fallback direct paint success "
            f"file='{pdf_path}' printer='{printer.printerName() or 'default'}'"
        )
        return message
    except Exception as paint_exc:
        print(
            "[THERMAL_PRINT] PDF fallback direct paint unavailable "
            f"file='{pdf_path}' printer='{printer.printerName() or 'default'}' "
            f"error='{paint_exc}'"
        )

    try:
        message = _try_windows_pdf_shell_print(pdf_path)
        print(f"[THERMAL_PRINT] PDF fallback Windows shell print file='{pdf_path}'")
        return message
    except Exception as shell_exc:
        print(
            "[THERMAL_PRINT] PDF fallback shell print unavailable "
            f"file='{pdf_path}' error='{shell_exc}'"
        )

    _open_pdf_for_manual_print(pdf_path)
    return (
        "WebEngine direct thermal print is unsupported in this Qt install. "
        "A PDF fallback was generated and opened in the PDF viewer. "
        f"Please print it from the viewer. File: '{pdf_path}'."
    )


def print_thermal_receipt(html_string: str, printer: QPrinter) -> str:
    """
    Print an 80mm thermal receipt through QWebEngineView or PDF fallback.

    Args:
        html_string: Complete HTML content returned by ``generate_thermal_html``.
        printer: Preconfigured ``QPrinter`` for the selected thermal printer.

    Raises:
        RuntimeError: If the printer or WebEngine print operation fails.
    """
    try:
        if printer is None or not isinstance(printer, QPrinter):
            raise RuntimeError("A valid QPrinter must be supplied for thermal printing.")
        _set_native_output_format(printer)
        configure_thermal_printer_page(printer)
        if not printer.isValid():
            raise RuntimeError(
                "No valid Windows printer is available for thermal printing. "
                f"Resolved printer: '{printer.printerName() or 'default'}'."
            )
        print(
            "[THERMAL_PRINT] physical route "
            f"selected_printer='{printer.printerName() or 'default'}' "
            f"printer_valid={printer.isValid()} "
            f"html_len={len(_text(html_string))}"
        )
        probe_page = QWebEnginePage()
        direct_print_available = _webengine_print_method(probe_page) is not None
        print_to_pdf_available = hasattr(probe_page, "printToPdf")
        pdf_finished_available = hasattr(probe_page, "pdfPrintingFinished")
        probe_page.deleteLater()
        print(
            "[THERMAL_PRINT] WebEngine method availability "
            f"print={direct_print_available} "
            f"printToPdf={print_to_pdf_available} "
            f"pdfPrintingFinished={pdf_finished_available}"
        )
        if direct_print_available:
            render_thermal_html_to_printer(html_string, printer)
            return "Thermal receipt sent to printer through WebEngine direct physical print."

        temp_pdf_path = _create_temp_pdf_path()
        print(
            "[THERMAL_PRINT] direct WebEngine print unsupported; generating PDF fallback "
            f"file='{temp_pdf_path}' "
            f"printer='{printer.printerName() or 'default'}'"
        )
        export_thermal_pdf(html_string, temp_pdf_path)
        return _print_generated_pdf_fallback(temp_pdf_path, printer)
    except Exception as exc:
        raise RuntimeError(f"Could not print thermal receipt: {exc}") from exc
