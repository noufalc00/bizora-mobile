"""
Standalone A4 HTML print engine for Faizan Pro Accounting.

The module accepts already prepared invoice dictionaries, renders escaped A4
HTML, and sends that HTML to PySide6's Chromium/QPrinter pipeline.
"""

from __future__ import annotations

import html
import json
import os
import tempfile
from typing import Any, Mapping, Optional, Sequence

from PySide6.QtCore import QCoreApplication, QEventLoop, QMarginsF, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

from utils.print_time_format import A4_PRINT_TIME_KEY, PRINT_TIME_KEY, append_print_time_to_date

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional runtime dependency
    fitz = None


TAX_INVOICE = "TAX_INVOICE"
BILL_OF_SUPPLY = "BOS"
A4_THEME_NAMES = (
    "GST Standard",
    "Modern Clean",
    "Elegant Serif",
    "Compact Wholesale",
    "Bold Corporate",
    "Bill of Supply",
    "Color Block Header",
    "Vibrant Accent",
    "Modern Gradient",
)
A4_THEME_NAME_SET = set(A4_THEME_NAMES)
A4_PAGE_WIDTH_PT = 595
A4_PAGE_HEIGHT_PT = 842
A4_CONTENT_WIDTH_PT = 527
A5_PAGE_WIDTH_PT = 420
A5_PAGE_HEIGHT_PT = 595
A5_CONTENT_WIDTH_PT = 353
PAGE_MARGIN_MM = 12.0
PAGE_MARGIN_PT = 34
WEBENGINE_LOAD_TIMEOUT_MS = 15000
WEBENGINE_PRINT_TIMEOUT_MS = 30000
_print_view = None


def _text(value: Any) -> str:
    """Return a safe string for nullable display values."""
    return "" if value is None else str(value)


def _escape(value: Any) -> str:
    """Escape dynamic text before placing it inside invoice HTML."""
    return html.escape(_text(value), quote=True)


def _escape_multiline(value: Any) -> str:
    """Escape text area content and preserve user-entered line breaks."""
    escaped_text = _escape(value)
    return escaped_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def _to_float(value: Any) -> float:
    """Convert numeric inputs to float while tolerating blank UI values."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _money(value: Any) -> str:
    """Format a numeric amount with two decimals for invoice display."""
    return f"{_to_float(value):.2f}"


def _first_value(data: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    """Return the first non-empty value from a dictionary using alias keys."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return default


def _setting_value(settings: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    """Return a saved print setting using current and legacy key aliases."""
    for key in keys:
        value = settings.get(key)
        if value not in (None, ""):
            return value
    return default


def _setting_bool(settings: Mapping[str, Any], keys: Sequence[str], default: bool) -> bool:
    """Read checkbox-like settings saved as booleans, numbers, or strings."""
    value = _setting_value(settings, *keys, default=None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0

    normalized_value = _text(value).strip().lower()
    if normalized_value in {"1", "true", "yes", "on", "checked", "show"}:
        return True
    if normalized_value in {"0", "false", "no", "off", "unchecked", "hide", "hidden"}:
        return False
    return default


def _layout_metadata(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Return print-layout metadata saved inside the settings JSON."""
    raw_coordinates = _text(settings.get("layout_coordinates")).strip()
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


def _effective_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Merge direct print settings over metadata saved inside layout JSON."""
    metadata = _layout_metadata(settings)
    merged_settings = dict(metadata)
    merged_settings.update(dict(settings))
    return merged_settings


def _normalize_theme_color(value: Any) -> str:
    """Return a safe hex color for CSS theme accents."""
    color_text = _text(value).strip()
    if (
        len(color_text) == 7
        and color_text.startswith("#")
        and all(character in "0123456789abcdefABCDEF" for character in color_text[1:])
    ):
        return color_text.upper()
    return "#E63946"


def _normalize_bill_type(bill_type: Any) -> str:
    """Normalize caller bill type values to supported print variants."""
    clean_value = _text(bill_type).strip().upper().replace(" ", "_")
    if clean_value in {BILL_OF_SUPPLY, "BILL_OF_SUPPLY"}:
        return BILL_OF_SUPPLY
    return TAX_INVOICE


def _resolve_a4_theme_name(
    settings: Mapping[str, Any],
    theme_name: Optional[str] = None,
) -> str:
    """Resolve the selected A4 theme without letting thermal themes override it."""
    explicit_theme = _text(theme_name).strip()
    if explicit_theme in A4_THEME_NAME_SET:
        return explicit_theme

    for key in ("a4_theme", "default_theme", "theme"):
        candidate = _text(settings.get(key)).strip()
        if candidate in A4_THEME_NAME_SET:
            return candidate
    return "GST Standard"


def _paper_size_name(
    settings: Mapping[str, Any],
    paper_size: Optional[str] = None,
) -> str:
    """Normalize saved and explicit paper-size values to the A4 engine choices."""
    paper_size = _text(
        paper_size
        or _setting_value(
            settings,
            "a4_paper_size",
            "paper_size",
            "default_format",
            default="A4",
        )
    ).strip().upper()
    return "A5" if paper_size == "A5" else "A4"


def _paper_layout(
    settings: Mapping[str, Any],
    paper_size: Optional[str] = None,
) -> dict[str, Any]:
    """Return selected page dimensions and Qt page-size metadata in points."""
    normalized_paper_size = _paper_size_name(settings, paper_size)
    if normalized_paper_size == "A5":
        return {
            "name": "A5",
            "page_size_id": QPageSize.PageSizeId.A5,
            "page_width_pt": A5_PAGE_WIDTH_PT,
            "page_height_pt": A5_PAGE_HEIGHT_PT,
            "content_width_pt": A5_CONTENT_WIDTH_PT,
        }
    return {
        "name": "A4",
        "page_size_id": QPageSize.PageSizeId.A4,
        "page_width_pt": A4_PAGE_WIDTH_PT,
        "page_height_pt": A4_PAGE_HEIGHT_PT,
        "content_width_pt": A4_CONTENT_WIDTH_PT,
    }


def _html_has_preview_wrapper(html_string: str) -> bool:
    """Return whether the transient settings-preview wrapper leaked into print HTML."""
    return 'width: 794px' in html_string or 'class="preview-body"' in html_string


def _content_width_points(settings: Mapping[str, Any]) -> int:
    """Return the fixed invoice content width used by Qt HTML rendering."""
    return int(_paper_layout(settings)["content_width_pt"])


def configure_a4_printer_page(
    printer: QPrinter,
    settings: Optional[Mapping[str, Any]] = None,
    paper_size: Optional[str] = None,
) -> str:
    """Apply the selected A4/A5 page size and margins to a Qt printer."""
    safe_settings = _effective_settings(settings or {})
    paper_layout = _paper_layout(safe_settings, paper_size)
    printer.setPageSize(QPageSize(paper_layout["page_size_id"]))
    try:
        printer.setPageMargins(
            QMarginsF(PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM),
            QPageLayout.Unit.Millimeter,
        )
    except Exception:
        # Some printer drivers reject software margins; fit-to-print still
        # scales against their reported paintable rectangle.
        pass
    return str(paper_layout["name"])


def _light_theme_color(theme_color: str) -> str:
    """Return a pale solid color instead of unsupported alpha hex CSS."""
    try:
        red = int(theme_color[1:3], 16)
        green = int(theme_color[3:5], 16)
        blue = int(theme_color[5:7], 16)
    except (TypeError, ValueError, IndexError):
        return "#F3F4F6"
    red = int(red + (255 - red) * 0.86)
    green = int(green + (255 - green) * 0.86)
    blue = int(blue + (255 - blue) * 0.86)
    return f"#{red:02X}{green:02X}{blue:02X}"


def _available_printer_names() -> set[str]:
    """Return printer names currently reported by the local Qt print system."""
    try:
        return {
            printer.printerName()
            for printer in QPrinterInfo.availablePrinters()
            if printer.printerName()
        }
    except Exception:
        return set()


def _printer_names_for_message() -> str:
    """Return installed printer names formatted for user-facing errors."""
    printer_names = sorted(_available_printer_names())
    return ", ".join(printer_names) if printer_names else "none reported by Windows"


def _apply_printer_name(printer: QPrinter, printer_name: Optional[str]) -> None:
    """Apply a saved physical printer name and fail clearly if it is missing."""
    clean_name = _text(printer_name).strip()
    if not clean_name:
        return

    available_printers = _available_printer_names()
    if clean_name not in available_printers:
        raise RuntimeError(
            "Saved A4 printer is not installed or is offline: "
            f"'{clean_name}'. Available printers: {_printer_names_for_message()}."
        )
    printer.setPrinterName(clean_name)


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


def _validate_physical_printer(printer: QPrinter, requested_name: Optional[str]) -> None:
    """Validate the resolved Windows printer before Chromium starts printing."""
    selected_name = _text(printer.printerName()).strip()
    requested_label = _text(requested_name).strip() or "default"
    if not printer.isValid():
        raise RuntimeError(
            "No valid Windows printer is available for A4 printing. "
            f"Requested printer: '{requested_label}'. "
            f"Available printers: {_printer_names_for_message()}."
        )
    if not selected_name:
        raise RuntimeError(
            "Qt could not resolve a physical printer name for A4 printing. "
            f"Requested printer: '{requested_label}'. "
            f"Available printers: {_printer_names_for_message()}."
        )


def _webengine_print_method(page: QWebEnginePage) -> Any:
    """Return the installed WebEngine physical print method, if Qt exposes one."""
    return getattr(page, "print", None) or getattr(page, "print_", None)


def _create_temp_pdf_path() -> str:
    """Reserve a Windows-safe temporary path for A4 fallback PDF generation."""
    handle, file_path = tempfile.mkstemp(prefix="faizan_a4_receipt_", suffix=".pdf")
    os.close(handle)
    return file_path


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
    print(f"[A4_PRINT] PDF fallback opened for manual print file='{pdf_path}'")


def _try_windows_pdf_shell_print(pdf_path: str, printer_name: Optional[str]) -> str:
    """Ask Windows' registered PDF application to print the PDF fallback."""
    if os.name != "nt":
        raise RuntimeError("Windows shell PDF printing is unavailable on this OS.")
    if _text(printer_name).strip():
        raise RuntimeError(
            "Windows shell PDF print was skipped because it cannot safely honor "
            f"the selected printer '{_text(printer_name).strip()}'."
        )
    try:
        os.startfile(pdf_path, "print")  # type: ignore[attr-defined]
    except Exception as exc:
        raise RuntimeError(f"Windows PDF print command failed: {exc}") from exc
    return (
        "WebEngine direct print is unsupported in this Qt install. "
        "A PDF fallback was generated and sent to the Windows default PDF print command."
    )


def _paint_pdf_to_printer(pdf_path: str, printer: QPrinter) -> str:
    """Rasterize a generated A4 PDF and paint it directly to the selected printer."""
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
            raise RuntimeError(
                "Qt could not begin painting to the selected printer driver."
            )
        try:
            for page_index in range(len(pdf_doc)):
                if page_index > 0 and not printer.newPage():
                    raise RuntimeError(
                        f"Printer driver refused page {page_index + 1}."
                    )
                page = pdf_doc.load_page(page_index)
                pixmap = page.get_pixmap(dpi=300, alpha=False)
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
        "WebEngine direct print is unsupported in this Qt install. "
        f"PDF fallback was generated and painted to printer '{printer.printerName() or 'default'}'."
    )


def _print_generated_pdf_fallback(
    pdf_path: str,
    printer: QPrinter,
    printer_name: Optional[str],
) -> str:
    """Print or open a generated PDF fallback using the safest available route."""
    try:
        message = _paint_pdf_to_printer(pdf_path, printer)
        print(
            "[A4_PRINT] PDF fallback direct paint success "
            f"file='{pdf_path}' printer='{printer.printerName() or 'default'}'"
        )
        return message
    except Exception as paint_exc:
        print(
            "[A4_PRINT] PDF fallback direct paint unavailable "
            f"file='{pdf_path}' printer='{printer.printerName() or 'default'}' "
            f"error='{paint_exc}'"
        )

    try:
        message = _try_windows_pdf_shell_print(pdf_path, printer_name)
        print(f"[A4_PRINT] PDF fallback Windows shell print file='{pdf_path}'")
        return message
    except Exception as shell_exc:
        print(
            "[A4_PRINT] PDF fallback shell print unavailable "
            f"file='{pdf_path}' error='{shell_exc}'"
        )

    _open_pdf_for_manual_print(pdf_path)
    return (
        "WebEngine direct print is unsupported in this Qt install. "
        "A PDF fallback was generated and opened in the PDF viewer. "
        f"Please print it from the viewer. File: '{pdf_path}'."
    )


def _amount_to_words(value: Any) -> str:
    """Convert a numeric amount into simple Indian currency words."""
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


def _rate_text(value: Any) -> str:
    """Format tax rates without forcing blank values into visible zeros."""
    raw_value = _text(value).strip()
    if not raw_value:
        return ""
    if raw_value.endswith("%"):
        return raw_value
    rate_value = _to_float(value)
    if rate_value.is_integer():
        return f"{int(rate_value)}%"
    return f"{rate_value:.2f}".rstrip("0").rstrip(".") + "%"


def _row_tax_values(item: Mapping[str, Any]) -> dict[str, float]:
    """Calculate row GST and CESS display amounts from explicit tax rates."""
    taxable = _to_float(
        _first_value(item, "taxable", "taxable_value", "net_value", "amount", default=0)
    )
    gst_rate = _to_float(_first_value(item, "gst_rate", "tax_percent", default=0))
    cess_rate = _to_float(_first_value(item, "cess_rate", "cess_percent", default=0))
    cgst_amount = taxable * (gst_rate / 2) / 100
    sgst_amount = taxable * (gst_rate / 2) / 100
    cess_amount = taxable * cess_rate / 100
    return {
        "taxable": taxable,
        "gst_rate": gst_rate,
        "cess_rate": cess_rate,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "cess_amount": cess_amount,
    }


def _column_specs(
    settings: Mapping[str, Any],
    include_tax: bool,
) -> list[dict[str, Any]]:
    """Build item table columns from saved A4 print settings."""
    show_hsn = _setting_bool(settings, ("show_hsn", "a4_show_hsn_sac"), True)
    show_mrp = _setting_bool(settings, ("show_mrp", "a4_show_mrp"), False)
    show_discount = _setting_bool(settings, ("show_discount", "a4_show_discount"), False)
    show_tax_rate = _setting_bool(settings, ("show_tax_rate", "a4_show_tax_rate"), False)

    columns: list[dict[str, Any]] = [
        {"label": "SL", "class": "center", "keys": ("sl_no", "serial", "s_no"), "default": None},
        {"label": "Item", "class": "", "keys": ("item_name", "product_name", "name", "description"), "default": None},
    ]
    if show_hsn:
        columns.append({"label": "HSN", "class": "center", "keys": ("hsn", "hsn_code"), "default": ""})
    columns.append({"label": "Qty", "class": "right", "keys": ("quantity", "qty"), "default": 0, "money": True})
    if show_mrp:
        columns.append({"label": "MRP", "class": "right", "keys": ("mrp", "m_r_p", "list_price"), "default": 0, "money": True})
    columns.append({"label": "Rate", "class": "right", "keys": ("rate", "price", "unit_price"), "default": 0, "money": True})
    if show_discount:
        columns.append({"label": "Disc.", "class": "right", "keys": ("discount", "discount_amount", "disc"), "default": 0, "money": True})

    if include_tax:
        if show_tax_rate:
            columns.append(
                {
                    "label": "GST%",
                    "class": "right",
                    "keys": ("gst_rate", "tax_percent"),
                    "default": "",
                    "rate": True,
                }
            )
        columns.extend(
            (
                {
                    "label": "Taxable",
                    "class": "right",
                    "keys": ("taxable", "taxable_value", "net_value", "amount"),
                    "default": 0,
                    "money": True,
                },
                {"label": "CGST", "class": "right", "keys": ("cgst_amount", "cgst"), "default": 0, "money": True},
                {"label": "SGST", "class": "right", "keys": ("sgst_amount", "sgst"), "default": 0, "money": True},
                {"label": "CESS", "class": "right", "keys": ("cess_amount",), "default": 0, "money": True},
                {"label": "Total", "class": "right", "keys": ("grand_total", "total", "line_total", "amount"), "default": 0, "money": True},
            )
        )
    else:
        columns.append(
            {
                "label": "Amount",
                "class": "right",
                "keys": ("grand_total", "total", "line_total", "amount"),
                "default": 0,
                "money": True,
            }
        )
    return columns


def _column_width_points(
    columns: Sequence[Mapping[str, Any]],
    content_width_pt: int,
) -> list[int]:
    """Return fixed column widths so invoice tables remain print friendly."""
    fixed_widths = {
        "SL": 24,
        "HSN": 46,
        "Qty": 42,
        "MRP": 48,
        "Rate": 48,
        "Disc.": 44,
        "GST%": 38,
        "Taxable": 56,
        "CGST": 46,
        "SGST": 46,
        "CESS": 46,
        "Total": 56,
        "Amount": 66,
    }
    item_index = next(
        (index for index, column in enumerate(columns) if column["label"] == "Item"),
        1,
    )
    widths = [fixed_widths.get(_text(column["label"]), 0) for column in columns]
    fixed_total = sum(width for index, width in enumerate(widths) if index != item_index)
    item_width = max(110, content_width_pt - fixed_total)
    widths[item_index] = item_width
    total_width = sum(widths)
    if total_width <= content_width_pt:
        return widths

    scale = content_width_pt / total_width
    return [max(20, int(width * scale)) for width in widths]


def _cell_width_attributes(width_pt: int) -> str:
    """Return HTML attributes understood by Qt's rich text table layout."""
    return f' width="{width_pt}" style="width: {width_pt}pt;"'


def _render_item_header(
    columns: Sequence[Mapping[str, Any]],
    widths: Sequence[int],
) -> str:
    """Render escaped item table headers for the selected columns."""
    return "".join(
        f"<th{_cell_width_attributes(widths[index])}>{_escape(column['label'])}</th>"
        for index, column in enumerate(columns)
    )


def _render_item_rows(
    cart_data: Sequence[Mapping[str, Any]],
    columns: Sequence[Mapping[str, Any]],
    widths: Sequence[int],
) -> str:
    """Render escaped item rows for the A4 invoice table body."""
    if not cart_data:
        return f'<tr><td colspan="{len(columns)}" class="center muted">No items found</td></tr>'

    rows = []
    for row_index, item in enumerate(cart_data, start=1):
        cells = []
        tax_values = _row_tax_values(item)
        for column_index, column in enumerate(columns):
            default_value = row_index if column["label"] == "SL" else column.get("default", "")
            if column["label"] == "Item":
                default_value = f"Item {row_index}"
            label = column["label"]
            if label == "GST%":
                display_value = _rate_text(tax_values["gst_rate"])
            elif label == "Taxable":
                display_value = _money(tax_values["taxable"])
            elif label == "CGST":
                display_value = _money(tax_values["cgst_amount"])
            elif label == "SGST":
                display_value = _money(tax_values["sgst_amount"])
            elif label == "CESS":
                display_value = _money(tax_values["cess_amount"])
            else:
                value = _first_value(item, *column["keys"], default=default_value)
                if column.get("rate"):
                    display_value = _rate_text(value)
                elif column.get("money"):
                    display_value = _money(value)
                else:
                    display_value = value
            css_class = _escape(column.get("class", ""))
            cells.append(
                f'<td class="{css_class}"{_cell_width_attributes(widths[column_index])}>'
                f'{_escape(display_value)}</td>'
            )
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return "".join(rows)


def _render_total_rows(totals_data: Mapping[str, Any], include_tax: bool) -> str:
    """Render the footer totals table rows for the selected bill type."""
    subtotal = _first_value(totals_data, "subtotal", "sub_total", "taxable_total", default=0)
    discount = _first_value(totals_data, "discount", "discount_total", default=0)
    round_off = _first_value(totals_data, "round_off", default=0)
    grand_total = _first_value(totals_data, "grand_total", "total", "total_amount", default=0)
    payment_mode = _first_value(totals_data, "payment_mode", "mode", default="")
    amount_paid = _first_value(
        totals_data,
        "amount_received",
        "tendered_amount",
        "paid_amount",
        "amount_paid",
        "cash_received",
        "paid",
        "received",
        default="",
    )
    balance = _first_value(
        totals_data,
        "balance",
        "printed_balance",
        "balance_amount",
        default="",
    )
    if balance in (None, "") and amount_paid not in (None, ""):
        balance = (
            _to_float(amount_paid) - _to_float(grand_total)
            if _text(payment_mode).strip().lower() == "cash"
            else 0.0
        )

    tax_rows = ""
    if include_tax:
        tax_rows = """
            <tr><td>CGST</td><td class="right">{cgst}</td></tr>
            <tr><td>SGST</td><td class="right">{sgst}</td></tr>
            <tr><td>Total CESS</td><td class="right">{cess}</td></tr>
        """.format(
            cgst=_escape(_money(_first_value(totals_data, "cgst", "cgst_total", default=0))),
            sgst=_escape(_money(_first_value(totals_data, "sgst", "sgst_total", default=0))),
            cess=_escape(_money(_first_value(totals_data, "cess", "cess_total", "total_cess", default=0))),
        )

    return """
        <tr><td>Sub Total</td><td class="right">{subtotal}</td></tr>
        <tr><td>Discount</td><td class="right">{discount}</td></tr>
        {tax_rows}
        <tr><td>Round Off</td><td class="right">{round_off}</td></tr>
        <tr class="grand-total"><td>Grand Total</td><td class="right">{grand_total}</td></tr>
        {payment_rows}
    """.format(
        subtotal=_escape(_money(subtotal)),
        discount=_escape(_money(discount)),
        tax_rows=tax_rows,
        round_off=_escape(_money(round_off)),
        grand_total=_escape(_money(grand_total)),
        payment_rows="".join(
            (
                (
                    f'<tr><td>Payment Mode</td><td class="right">{_escape(payment_mode)}</td></tr>'
                    if payment_mode not in (None, "")
                    else ""
                ),
                (
                    f'<tr><td>Paid</td><td class="right">{_escape(_money(amount_paid))}</td></tr>'
                    if amount_paid not in (None, "")
                    else ""
                ),
                (
                    f'<tr><td>Balance</td><td class="right">{_escape(_money(balance))}</td></tr>'
                    if balance not in (None, "")
                    else ""
                ),
            )
        ),
    )


def _render_line(label: str, value: Any, multiline: bool = False) -> str:
    """Render a labeled detail line only when the value is present."""
    if value in (None, ""):
        return ""
    safe_value = _escape_multiline(value) if multiline else _escape(value)
    return f'<div><span class="label">{_escape(label)}:</span> {safe_value}</div>'


def _render_text_section(title: str, value: Any) -> str:
    """Render a multiline footer section such as bank details or terms."""
    if value in (None, ""):
        return ""
    return (
        '<div class="footer-section">'
        f'<div class="footer-heading">{_escape(title)}</div>'
        f'<div>{_escape_multiline(value)}</div>'
        '</div>'
    )


def _image_data_uri(base64_value: Any) -> str:
    """Return an inline image data URI for persisted base64 image content."""
    clean_value = _text(base64_value).strip()
    if not clean_value:
        return ""
    return f"data:image/png;base64,{clean_value}"


def _render_authorized_signatory(enabled: bool, signature_base64: Any = "") -> str:
    """Render the optional authorized signatory box."""
    if not enabled:
        return ""
    signature_uri = _image_data_uri(signature_base64)
    signature_image = (
        f'<img src="{_escape(signature_uri)}" style="max-height: 60px; max-width: 150px;">'
        if signature_uri
        else '<div class="signatory-space"></div>'
    )
    return """
        <td class="signatory-box">
            {signature_image}
            <div>Authorized Signatory</div>
        </td>
    """.format(signature_image=signature_image)


def generate_a4_html(
    company_data: Mapping[str, Any],
    cart_data: Sequence[Mapping[str, Any]],
    bill_type: str = TAX_INVOICE,
    totals_data: Optional[Mapping[str, Any]] = None,
    settings: Optional[Mapping[str, Any]] = None,
    document_title: str = "Tax Invoice",
    theme_name: Optional[str] = None,
) -> str:
    """
    Return complete A4 invoice HTML with escaped dynamic values.

    Args:
        company_data: Company details, and optionally customer or invoice header
            aliases when the caller does not provide them in ``totals_data``.
        cart_data: Item rows to render inside the invoice body table.
        bill_type: ``TAX_INVOICE`` includes CGST/SGST columns; ``BOS`` omits tax
            columns and renders a Bill of Supply title.
        totals_data: Optional totals/header values. ``None`` is treated as an
            empty dictionary to avoid mutable default arguments.
        settings: Optional Normal Printer settings. Missing settings preserve the
            original A4 invoice defaults for existing callers.
        document_title: Header title to render when the bill type does not force
            a Bill of Supply title.
        theme_name: Optional explicit A4 theme override. When omitted, the
            renderer resolves the saved ``a4_theme``/``theme`` settings.
    """
    safe_company = company_data or {}
    safe_totals = totals_data or {}
    safe_settings = _effective_settings(settings or {})
    requested_theme = _text(theme_name).strip()
    theme_color = _normalize_theme_color(
        safe_settings.get(
            "a4_theme_color",
            safe_settings.get("theme_color", "#E63946"),
        )
    )
    resolved_theme_name = _resolve_a4_theme_name(safe_settings, requested_theme)
    normalized_bill_type = _normalize_bill_type(bill_type)
    paper_layout = _paper_layout(safe_settings)
    paper_size_name = str(paper_layout["name"])
    page_width_pt = int(paper_layout["page_width_pt"])
    page_height_pt = int(paper_layout["page_height_pt"])
    content_width_pt = int(paper_layout["content_width_pt"])
    half_width_pt = int(content_width_pt / 2)
    amount_words_width_pt = int(content_width_pt * 0.62)
    totals_width_pt = content_width_pt - amount_words_width_pt
    signatory_width_pt = int(content_width_pt * 0.32)
    preview_mode = _setting_bool(safe_settings, ("a4_preview_mode", "preview_mode"), False)
    preview_body_class = ' class="preview-body"' if preview_mode else ""
    page_open = '<div class="page">'
    page_close = "</div>"
    preview_css = (
        f"""
            body.preview-body {{
                background-color: #f3f4f6;
                padding: 22px;
            }}
            .preview-sheet {{
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                box-shadow: 0 10px 28px rgba(15, 23, 42, 0.18);
                box-sizing: border-box;
                margin: 0 auto;
                min-height: {page_height_pt}pt;
                padding: {PAGE_MARGIN_PT}pt;
                width: {page_width_pt}pt;
            }}
        """
        if preview_mode
        else ""
    )
    accent_light_color = _light_theme_color(theme_color)

    def _complete_theme_palette(palette: Mapping[str, Any]) -> dict[str, str]:
        """Return a palette with both modern and legacy CSS color keys."""
        completed = dict(palette)
        completed.setdefault("bg", _text(completed.get("bg_color", "#ffffff")))
        completed.setdefault("text", _text(completed.get("text_color", "#000000")))
        completed.setdefault("border", _text(completed.get("border_color", "#cccccc")))
        completed.setdefault("header_bg", _text(completed.get("header_bg", "#f2f2f2")))
        completed.setdefault(
            "header_text",
            _text(completed.get("header_text_color", "#000000")),
        )
        completed.setdefault("bg_color", completed["bg"])
        completed.setdefault("text_color", completed["text"])
        completed.setdefault("border_color", completed["border"])
        completed.setdefault("header_text_color", completed["header_text"])
        completed.setdefault("muted_color", "#6B7280")
        completed.setdefault("strong_border_color", completed["border"])
        completed.setdefault("title_bg", completed["header_bg"])
        completed.setdefault("title_text_color", completed["header_text"])
        completed.setdefault("title_border_color", completed["border"])
        completed.setdefault("font_family", "Arial, sans-serif")
        completed.setdefault("font_size", "10pt")
        completed.setdefault("company_name_color", completed["text"])
        completed.setdefault("accent_color", completed["header_bg"])
        completed.setdefault("accent_light_color", completed["header_bg"])
        completed.setdefault("grand_total_color", completed["text"])
        completed.setdefault("table_row_border_color", completed["border"])
        return {str(key): _text(value) for key, value in completed.items()}

    # Keep palette keys aligned with the A4 theme dropdown in Print Settings.
    theme_palettes = {
        "Light": {
            "bg": "#ffffff",
            "text": "#000000",
            "border": "#cccccc",
            "header_bg": "#f2f2f2",
            "header_text": "#000000",
        },
        "Dark": {
            "bg": "#1e1e2e",
            "text": "#f8f8f2",
            "border": "#45475a",
            "header_bg": "#313244",
            "header_text": "#a6e3a1",
        },
        "Blue": {
            "bg": "#f0f8ff",
            "text": "#000033",
            "border": "#b0c4de",
            "header_bg": "#4682b4",
            "header_text": "#ffffff",
        },
        "Green": {
            "bg": "#f5fffa",
            "text": "#002b00",
            "border": "#98fb98",
            "header_bg": "#2e8b57",
            "header_text": "#ffffff",
        },
        "Classic": {
            "bg": "#ffffff",
            "text": "#333333",
            "border": "#000000",
            "header_bg": "#dddddd",
            "header_text": "#000000",
        },
        "GST Standard": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#D1D5DB",
            "strong_border_color": "#111827",
            "header_bg": "#E5E7EB",
            "header_text_color": "#111827",
            "title_bg": "#FFFFFF",
            "title_text_color": "#111827",
            "title_border_color": "#111827",
            "font_family": "Arial, sans-serif",
            "font_size": "10pt",
            "company_name_color": "#111827",
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": "#111827",
            "table_row_border_color": "#D1D5DB",
        },
        "Modern Clean": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#D1D5DB",
            "strong_border_color": "#111827",
            "header_bg": "#F2F2F2",
            "header_text_color": "#111827",
            "title_bg": "#FFFFFF",
            "title_text_color": "#111827",
            "title_border_color": "#111827",
            "font_family": "Arial, Helvetica, sans-serif",
            "font_size": "10pt",
            "company_name_color": "#111827",
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": "#111827",
            "table_row_border_color": "#E5E7EB",
        },
        "Elegant Serif": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#111827",
            "strong_border_color": "#111827",
            "header_bg": "#F8FAFC",
            "header_text_color": "#111827",
            "title_bg": "#FFFFFF",
            "title_text_color": "#111827",
            "title_border_color": "#111827",
            "font_family": '"Times New Roman", Times, serif',
            "font_size": "10.5pt",
            "company_name_color": "#111827",
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": "#111827",
            "table_row_border_color": "#D1D5DB",
        },
        "Compact Wholesale": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#111827",
            "strong_border_color": "#111827",
            "header_bg": "#FFFFFF",
            "header_text_color": "#111827",
            "title_bg": "#FFFFFF",
            "title_text_color": "#111827",
            "title_border_color": "#111827",
            "font_family": "Arial, sans-serif",
            "font_size": "10px",
            "company_name_color": "#111827",
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": "#111827",
            "table_row_border_color": "#111827",
        },
        "Bold Corporate": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#333333",
            "strong_border_color": "#333333",
            "header_bg": "#333333",
            "header_text_color": "#FFFFFF",
            "title_bg": "#333333",
            "title_text_color": "#FFFFFF",
            "title_border_color": "#333333",
            "font_family": "Arial, Helvetica, sans-serif",
            "font_size": "10pt",
            "company_name_color": "#111827",
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": "#111827",
            "table_row_border_color": "#9CA3AF",
        },
        "Bill of Supply": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#D1D5DB",
            "strong_border_color": "#111827",
            "header_bg": "#F9FAFB",
            "header_text_color": "#111827",
            "title_bg": "#FFFFFF",
            "title_text_color": "#111827",
            "title_border_color": "#111827",
            "font_family": "Arial, sans-serif",
            "font_size": "10pt",
            "company_name_color": "#111827",
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": "#111827",
            "table_row_border_color": "#E5E7EB",
        },
        "Color Block Header": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#DDDDDD",
            "strong_border_color": theme_color,
            "header_bg": theme_color,
            "header_text_color": "#FFFFFF",
            "title_bg": theme_color,
            "title_text_color": "#FFFFFF",
            "title_border_color": theme_color,
            "font_family": "Arial, Helvetica, sans-serif",
            "font_size": "10pt",
            "company_name_color": "#111827",
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": theme_color,
            "table_row_border_color": "#DDDDDD",
        },
        "Vibrant Accent": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#DDDDDD",
            "strong_border_color": theme_color,
            "header_bg": accent_light_color,
            "header_text_color": theme_color,
            "title_bg": "#FFFFFF",
            "title_text_color": theme_color,
            "title_border_color": "#DDDDDD",
            "font_family": "Arial, Helvetica, sans-serif",
            "font_size": "10pt",
            "company_name_color": theme_color,
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": theme_color,
            "table_row_border_color": "#DDDDDD",
        },
        "Modern Gradient": {
            "bg_color": "#FFFFFF",
            "text_color": "#111827",
            "muted_color": "#6B7280",
            "border_color": "#DDDDDD",
            "strong_border_color": theme_color,
            "header_bg": theme_color,
            "header_text_color": "#FFFFFF",
            "title_bg": theme_color,
            "title_text_color": "#FFFFFF",
            "title_border_color": theme_color,
            "font_family": "Arial, Helvetica, sans-serif",
            "font_size": "10pt",
            "company_name_color": theme_color,
            "accent_color": theme_color,
            "accent_light_color": accent_light_color,
            "grand_total_color": theme_color,
            "table_row_border_color": "#DDDDDD",
        },
    }
    theme_palettes = {
        palette_name: _complete_theme_palette(palette)
        for palette_name, palette in theme_palettes.items()
    }
    palette_theme_name = (
        resolved_theme_name if resolved_theme_name in theme_palettes else "Light"
    )
    colors = theme_palettes.get(palette_theme_name, theme_palettes["Light"])
    style_theme_name = resolved_theme_name
    include_tax = normalized_bill_type == TAX_INVOICE and style_theme_name != "Bill of Supply"
    invoice_title = _first_value(safe_totals, "document_title", "title", default="")
    if not invoice_title:
        invoice_title = "Bill of Supply" if not include_tax else document_title
    show_tax_references = include_tax

    bg_color = colors["bg_color"]
    text_color = colors["text_color"]
    muted_color = colors["muted_color"]
    border_color = colors["border_color"]
    strong_border_color = colors["strong_border_color"]
    header_bg = colors["header_bg"]
    header_text_color = colors["header_text_color"]
    title_bg = colors["title_bg"]
    title_text_color = colors["title_text_color"]
    title_border_color = colors["title_border_color"]
    font_family = colors["font_family"]
    font_size = colors["font_size"]
    company_name_color = colors["company_name_color"]
    accent_color = colors["accent_color"]
    accent_light_color = colors["accent_light_color"]
    grand_total_color = colors["grand_total_color"]
    table_row_border_color = colors["table_row_border_color"]

    company_name = _first_value(safe_company, "company_name", "business_name", "name", default="Company Name")
    company_gstin = _first_value(safe_company, "company_gstin", "gstin")
    company_address = _first_value(safe_company, "company_address", "address")
    company_phone = _first_value(safe_company, "phone", "phone_number", "mobile")
    company_email = _first_value(safe_company, "email", "company_email")
    logo_path = _first_value(safe_company, "logo_path", "company_logo", "logo")
    logo_base64 = _setting_value(safe_settings, "a4_logo_base64")
    signature_base64 = _setting_value(safe_settings, "a4_signature_base64")

    customer_name = _first_value(safe_totals, "customer_name", "party_name", default="")
    if not customer_name:
        customer_name = _first_value(safe_company, "customer_name", "party_name", default="Cash Customer")
    customer_gstin = _first_value(safe_totals, "customer_gstin", "party_gstin", "gstin", default="")
    customer_address = _first_value(safe_totals, "customer_address", "party_address", "address", default="")
    invoice_number = _first_value(safe_totals, "invoice_number", "bill_no", "voucher_no", default="")
    invoice_date = _first_value(safe_totals, "invoice_date", "bill_date", "date", default="")
    show_print_time = _setting_bool(
        safe_settings,
        (A4_PRINT_TIME_KEY, PRINT_TIME_KEY, "a4_print_time", "print_time"),
        False,
    )
    invoice_date = append_print_time_to_date(invoice_date, include_time=show_print_time)
    grand_total = _first_value(safe_totals, "grand_total", "total", "total_amount", default=0)
    amount_words = _first_value(safe_totals, "amount_in_words", default=_amount_to_words(grand_total))

    show_logo = _setting_bool(safe_settings, ("show_logo", "a4_show_logo"), False)
    show_company_name = _setting_bool(
        safe_settings,
        ("show_company_name", "a4_show_company_name"),
        True,
    )
    show_company_name_text = _setting_bool(
        safe_settings,
        ("a4_show_company_name_text",),
        True,
    )
    show_address = _setting_bool(
        safe_settings,
        ("show_address", "show_company_address", "a4_show_address"),
        True,
    )
    show_phone = _setting_bool(
        safe_settings,
        ("show_phone", "show_phone_number", "a4_show_phone"),
        True,
    )
    show_email = _setting_bool(safe_settings, ("show_email", "a4_show_email"), True)
    show_gstin = _setting_bool(
        safe_settings,
        ("show_gstin", "a4_show_gstin"),
        True,
    )
    show_signatory = _setting_bool(
        safe_settings,
        ("show_authorized_signatory", "a4_show_authorized_signatory"),
        True,
    )

    company_blocks = []
    logo_uri = _image_data_uri(logo_base64)
    if logo_uri:
        company_blocks.append(
            f'<img src="{_escape(logo_uri)}" style="max-height: 80px; max-width: 150px;">'
        )
    elif show_logo and logo_path:
        company_blocks.append(f'<img class="company-logo" src="{_escape(logo_path)}" alt="Logo">')
    if show_company_name and show_company_name_text:
        company_blocks.append(f'<h2 class="company-name">{_escape(company_name)}</h2>')
    if show_address and company_address:
        company_blocks.append(f'<div>{_escape_multiline(company_address)}</div>')
    if show_tax_references and show_gstin:
        company_blocks.append(_render_line("GSTIN", company_gstin))
    if show_phone:
        company_blocks.append(_render_line("Phone", company_phone))
    if show_email:
        company_blocks.append(_render_line("Email", company_email))
    company_html = "".join(company_blocks) or '<div class="muted">Company details hidden</div>'

    customer_blocks = [
        _render_line("Customer", customer_name),
        _render_line("Address", customer_address, multiline=True),
    ]
    if show_tax_references and show_gstin:
        customer_blocks.append(_render_line("GSTIN", customer_gstin))
    document_number_label = _first_value(
        safe_totals,
        "document_number_label",
        default="Invoice No",
    )
    document_date_label = _first_value(
        safe_totals,
        "document_date_label",
        default="Date",
    )
    customer_blocks.extend(
        (
            '<br>',
            _render_line(document_number_label, invoice_number),
            _render_line(document_date_label, invoice_date),
            _render_line("Valid Until", _first_value(safe_totals, "valid_until", default="")),
            _render_line("Status", _first_value(safe_totals, "quotation_status", "status", default="")),
        )
    )
    customer_html = "".join(customer_blocks)

    columns = _column_specs(safe_settings, include_tax)
    column_widths = _column_width_points(columns, content_width_pt)
    item_headers = _render_item_header(columns, column_widths)
    item_rows = _render_item_rows(cart_data or [], columns, column_widths)
    total_rows = _render_total_rows(safe_totals, include_tax)
    bank_details = _setting_value(safe_settings, "bank_details", "a4_bank_details")
    terms_conditions = _setting_value(
        safe_settings,
        "terms_conditions",
        "a4_terms_conditions",
        "terms_conditions_footer",
        "footer_terms",
    )
    footer_sections = "".join(
        (
            _render_text_section("Bank Details", bank_details),
            _render_text_section("Terms & Conditions", terms_conditions),
        )
    )
    signatory_cell = _render_authorized_signatory(show_signatory, signature_base64)
    notes_colspan = "" if signatory_cell else ' colspan="2"'

    base_css = """
            @page {
                size: __PAPER_SIZE__;
                margin: 12mm;
            }
            body {
                background-color: __BG_COLOR__;
                color: __TEXT_COLOR__;
                margin: 0;
            }
            th {
                background-color: __HEADER_BG__;
                border: 1px solid __BORDER_COLOR__;
                color: __HEADER_TEXT_COLOR__;
            }
            td {
                border: 1px solid __BORDER_COLOR__;
                color: __TEXT_COLOR__;
            }
            .page {
                width: __CONTENT_WIDTH_PT__pt;
            }
            .title {
                background-color: __TITLE_BG__;
                color: __TITLE_TEXT_COLOR__;
                font-size: 15pt;
                font-weight: bold;
                letter-spacing: 0.7px;
                margin-bottom: 8px;
                padding: 6px;
                text-align: center;
            }
            table {
                border-collapse: collapse;
                font-size: 11px;
                table-layout: auto;
                width: 100%;
            }
            th,
            td {
                border: 1px solid __BORDER_COLOR__;
                padding: 4px 6px;
                text-align: center;
                white-space: nowrap;
            }
            .header-table td {
                padding: 7px;
                vertical-align: top;
                width: __HALF_WIDTH_PT__pt;
            }
            .company-logo {
                max-height: 56px;
                max-width: 160px;
                margin-bottom: 5px;
            }
            .company-name {
                color: __COMPANY_NAME_COLOR__;
                font-size: 16pt;
                font-weight: bold;
                margin-top: 0;
                margin-bottom: 5px;
            }
            .label {
                color: __TEXT_COLOR__;
                font-weight: bold;
            }
            .items {
                margin-top: 10px;
                width: __CONTENT_WIDTH_PT__pt;
            }
            .items th {
                font-weight: bold;
                padding: 6px 4px;
            }
            .items td {
                padding: 5px 4px;
            }
            .footer {
                margin-top: 12px;
                width: __CONTENT_WIDTH_PT__pt;
            }
            .amount-words {
                padding: 8px;
                vertical-align: top;
                width: __AMOUNT_WORDS_WIDTH_PT__pt;
            }
            .totals {
                width: __TOTALS_WIDTH_PT__pt;
            }
            .totals td {
                padding: 5px 7px;
            }
            .footer-section {
                margin-top: 8px;
            }
            .footer-heading {
                color: __ACCENT_COLOR__;
                font-weight: bold;
                margin-bottom: 2px;
            }
            .signature-table {
                margin-top: 14px;
                width: __CONTENT_WIDTH_PT__pt;
            }
            .footer-notes {
                padding: 8px;
                vertical-align: top;
            }
            .signatory-box {
                padding: 8px;
                text-align: center;
                vertical-align: bottom;
                width: __SIGNATORY_WIDTH_PT__pt;
            }
            .signatory-space {
                height: 42px;
            }
            .signature-image {
                max-height: 42px;
                max-width: 130px;
                margin-bottom: 4px;
            }
            .grand-total td {
                color: __GRAND_TOTAL_COLOR__;
                font-size: 11pt;
                font-weight: bold;
            }
            .right {
                text-align: right;
            }
            .center {
                text-align: center;
            }
            .muted {
                color: __MUTED_COLOR__;
            }
            __PREVIEW_CSS__
    """
    base_css = (
        base_css.replace("__PAPER_SIZE__", paper_size_name)
        .replace("__CONTENT_WIDTH_PT__", str(content_width_pt))
        .replace("__HALF_WIDTH_PT__", str(half_width_pt))
        .replace("__AMOUNT_WORDS_WIDTH_PT__", str(amount_words_width_pt))
        .replace("__TOTALS_WIDTH_PT__", str(totals_width_pt))
        .replace("__SIGNATORY_WIDTH_PT__", str(signatory_width_pt))
        .replace("__PAGE_WIDTH_PT__", str(page_width_pt))
        .replace("__PAGE_HEIGHT_PT__", str(page_height_pt))
        .replace("__PAGE_MARGIN_PT__", str(PAGE_MARGIN_PT))
        .replace("__PREVIEW_CSS__", preview_css)
        .replace("__BG_COLOR__", bg_color)
        .replace("__TEXT_COLOR__", text_color)
        .replace("__MUTED_COLOR__", muted_color)
        .replace("__BORDER_COLOR__", border_color)
        .replace("__STRONG_BORDER_COLOR__", strong_border_color)
        .replace("__HEADER_BG__", header_bg)
        .replace("__HEADER_TEXT_COLOR__", header_text_color)
        .replace("__TITLE_BG__", title_bg)
        .replace("__TITLE_TEXT_COLOR__", title_text_color)
        .replace("__TITLE_BORDER_COLOR__", title_border_color)
        .replace("__COMPANY_NAME_COLOR__", company_name_color)
        .replace("__GRAND_TOTAL_COLOR__", grand_total_color)
        .replace("__TABLE_ROW_BORDER_COLOR__", table_row_border_color)
        .replace("__ACCENT_COLOR__", accent_color)
        .replace("__ACCENT_LIGHT_COLOR__", accent_light_color)
    )
    theme_styles = {
        "GST Standard": (
            "<style>" + base_css + """
            body {
                font-family: __FONT_FAMILY__;
                font-size: __FONT_SIZE__;
            }
            .title,
            .header-table td,
            .items th,
            .items td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {
                border: 1px solid __STRONG_BORDER_COLOR__;
            }
            .items th {
                background-color: __HEADER_BG__;
            }
            .totals td {
                border-bottom: 1px solid __TABLE_ROW_BORDER_COLOR__;
            }
            </style>"""
        ),
        "Modern Clean": (
            "<style>" + base_css + """
            body {
                font-family: __FONT_FAMILY__;
                font-size: __FONT_SIZE__;
            }
            .title {
                border-bottom: 2px solid __TITLE_BORDER_COLOR__;
            }
            .header-table td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {
                border: 1px solid __BORDER_COLOR__;
            }
            .items th {
                background-color: __HEADER_BG__;
                border-bottom: 1px solid __STRONG_BORDER_COLOR__;
            }
            .items td {
                border-bottom: 1px solid __TABLE_ROW_BORDER_COLOR__;
            }
            .totals td {
                border-bottom: 1px solid __TABLE_ROW_BORDER_COLOR__;
            }
            </style>"""
        ),
        "Elegant Serif": (
            "<style>" + base_css + """
            body {
                font-family: __FONT_FAMILY__;
                font-size: __FONT_SIZE__;
            }
            .title,
            .header-table td,
            .items th,
            .items td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {
                border: 1px solid __STRONG_BORDER_COLOR__;
            }
            .items th {
                background-color: __HEADER_BG__;
            }
            .totals td {
                border-bottom: 1px solid __TABLE_ROW_BORDER_COLOR__;
            }
            .grand-total td {
                border-bottom: 3px double __STRONG_BORDER_COLOR__;
                border-top: 3px double __STRONG_BORDER_COLOR__;
            }
            </style>"""
        ),
        "Compact Wholesale": (
            "<style>" + base_css + """
            body {
                font-family: __FONT_FAMILY__;
                font-size: __FONT_SIZE__;
            }
            .title {
                border: 1px solid __TITLE_BORDER_COLOR__;
                font-size: 12px;
                margin-bottom: 5px;
                padding: 3px;
            }
            .header-table td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {
                border: 1px solid __STRONG_BORDER_COLOR__;
                padding: 4px;
            }
            .items {
                margin-top: 6px;
            }
            .items th,
            .items td,
            .totals td {
                border: 1px solid __BORDER_COLOR__;
                padding: 2px 3px;
            }
            .footer {
                margin-top: 7px;
            }
            </style>"""
        ),
        "Bold Corporate": (
            "<style>" + base_css + """
            body {
                font-family: __FONT_FAMILY__;
                font-size: __FONT_SIZE__;
            }
            .title {
                background-color: __TITLE_BG__;
                border: 1px solid __TITLE_BORDER_COLOR__;
                color: __TITLE_TEXT_COLOR__;
            }
            .header-table td,
            .items th,
            .items td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {
                border: 1px solid __BORDER_COLOR__;
            }
            .items th {
                background-color: __HEADER_BG__;
                color: __HEADER_TEXT_COLOR__;
            }
            .totals td {
                border-bottom: 1px solid __TABLE_ROW_BORDER_COLOR__;
            }
            .grand-total td {
                font-size: 12pt;
                font-weight: 800;
            }
            </style>"""
        ),
        "Color Block Header": (
            "<style>" + base_css + f"""
            body {{
                font-family: Arial, Helvetica, sans-serif;
                font-size: 10pt;
            }}
            .title {{
                background-color: {title_bg};
                color: {title_text_color};
                margin-bottom: 0;
            }}
            .invoice-header {{
                background-color: {header_bg};
                color: {header_text_color};
                padding: 15px;
            }}
            .invoice-header td {{
                background-color: {header_bg};
                color: {header_text_color};
                padding: 15px;
            }}
            .invoice-header .label,
            .invoice-header .muted {{
                color: {header_text_color};
            }}
            th {{
                background-color: {header_bg};
                color: {header_text_color};
            }}
            .items th {{
                background-color: {header_bg};
                border: 1px solid {strong_border_color};
                color: {header_text_color};
            }}
            .items td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {{
                border: 1px solid {border_color};
            }}
            .totals td {{
                border-bottom: 1px solid {table_row_border_color};
            }}
            .grand-total td {{
                color: {grand_total_color};
            }}
            </style>"""
        ),
        "Vibrant Accent": (
            "<style>" + base_css + f"""
            body {{
                font-family: Arial, Helvetica, sans-serif;
                font-size: 10pt;
            }}
            .title {{
                color: {title_text_color};
                border-bottom: 1px solid {title_border_color};
            }}
            .invoice-header {{
                border-top: 6px solid {accent_color};
                padding: 15px;
            }}
            .invoice-header td {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                padding: 10px;
            }}
            th {{
                background-color: {accent_light_color};
                color: {header_text_color};
                border-top: 2px solid {accent_color};
                border-bottom: 2px solid {accent_color};
            }}
            .items th {{
                background-color: {accent_light_color};
                border-left: 1px solid {border_color};
                border-right: 1px solid {border_color};
                border-top: 2px solid {accent_color};
                border-bottom: 2px solid {accent_color};
                color: {header_text_color};
            }}
            .items td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {{
                border: 1px solid {border_color};
            }}
            .totals td {{
                border-bottom: 1px solid {table_row_border_color};
            }}
            .grand-total td {{
                color: {grand_total_color};
            }}
            </style>"""
        ),
        "Modern Gradient": (
            "<style>" + base_css + f"""
            body {{
                font-family: Arial, Helvetica, sans-serif;
                font-size: 10pt;
            }}
            .title {{
                background-color: {title_bg};
                color: {title_text_color};
            }}
            .invoice-header {{
                border: 1px solid {border_color};
                border-top: 5px solid {accent_color};
            }}
            .invoice-header td {{
                background-color: {bg_color};
                padding: 12px;
            }}
            .company-name,
            .footer-heading,
            .grand-total td {{
                color: {grand_total_color};
            }}
            .items th {{
                background-color: {header_bg};
                border: 1px solid {border_color};
                color: {header_text_color};
            }}
            .items td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {{
                border: 1px solid {border_color};
            }}
            .totals td {{
                border-bottom: 1px solid {table_row_border_color};
            }}
            </style>"""
        ),
        "Bill of Supply": (
            "<style>" + base_css + """
            body {
                font-family: __FONT_FAMILY__;
                font-size: __FONT_SIZE__;
            }
            .title {
                border-bottom: 1px solid __TITLE_BORDER_COLOR__;
            }
            .header-table td,
            .amount-words,
            .totals,
            .footer-notes,
            .signatory-box {
                border: 1px solid __BORDER_COLOR__;
            }
            .items th,
            .items td {
                border-bottom: 1px solid __BORDER_COLOR__;
            }
            .items th {
                background-color: __HEADER_BG__;
            }
            .totals td {
                border-bottom: 1px solid __TABLE_ROW_BORDER_COLOR__;
            }
            </style>"""
        ),
    }
    table_fit_css = """
            table {
                border-collapse: collapse;
                font-size: 11px;
                table-layout: auto;
                width: 100%;
            }
            th,
            td {
                border: 1px solid __BORDER_COLOR__;
                padding: 4px 6px;
                text-align: center;
                white-space: nowrap;
            }
            .items th,
            .items td {
                padding: 4px 6px;
                white-space: nowrap;
            }
    """.replace("__BORDER_COLOR__", border_color)
    visible_theme_css = {
        "GST Standard": """
            /* a4-theme-marker: gst-standard */
            .title {
                background-color: #FFFFFF;
                border: 2px solid #111827;
                color: #111827;
                letter-spacing: 0.7px;
            }
            .invoice-header td {
                background-color: #FFFFFF;
                border: 1px solid #111827;
            }
            .items th {
                background-color: #E5E7EB;
                border: 1px solid #111827;
                color: #111827;
            }
        """,
        "Modern Clean": """
            /* a4-theme-marker: modern-clean */
            .title {
                background-color: #F8FAFC;
                border: 0;
                border-bottom: 3px solid #2563EB;
                color: #1E3A8A;
                letter-spacing: 1.2px;
            }
            .invoice-header td {
                background-color: #FFFFFF;
                border: 1px solid #BFDBFE;
            }
            .items th {
                background-color: #DBEAFE;
                border: 1px solid #60A5FA;
                color: #1E3A8A;
            }
        """,
        "Elegant Serif": """
            /* a4-theme-marker: elegant-serif */
            body {
                font-family: "Times New Roman", Times, serif;
                font-size: 10.5pt;
            }
            .title {
                background-color: #FFF7ED;
                border-bottom: 4px double #92400E;
                border-top: 4px double #92400E;
                color: #78350F;
                font-style: italic;
                letter-spacing: 0.4px;
            }
            .items th {
                background-color: #FED7AA;
                border: 1px solid #92400E;
                color: #78350F;
            }
        """,
        "Compact Wholesale": """
            /* a4-theme-marker: compact-wholesale */
            body {
                font-family: Arial, sans-serif;
                font-size: 9px;
            }
            .title {
                background-color: #F9FAFB;
                border: 1px dashed #111827;
                color: #111827;
                font-size: 12px;
                letter-spacing: 0;
                padding: 3px;
            }
            .items {
                margin-top: 5px;
            }
            .items th,
            .items td {
                border: 1px solid #111827;
                padding: 2px 3px;
            }
        """,
        "Bold Corporate": """
            /* a4-theme-marker: bold-corporate */
            .title {
                background-color: #111827;
                border: 2px solid #111827;
                color: #FFFFFF;
                font-size: 16pt;
                letter-spacing: 1.4px;
            }
            .invoice-header td {
                border: 2px solid #111827;
            }
            .items th {
                background-color: #111827;
                border: 1px solid #111827;
                color: #FFFFFF;
            }
            .grand-total td {
                background-color: #F3F4F6;
                color: #111827;
                font-size: 12pt;
            }
        """,
        "Bill of Supply": """
            /* a4-theme-marker: bill-of-supply */
            .title {
                background-color: #F0FDF4;
                border: 2px solid #15803D;
                color: #166534;
                letter-spacing: 0.8px;
            }
            .invoice-header td {
                background-color: #F7FEE7;
                border: 1px solid #65A30D;
            }
            .items th {
                background-color: #DCFCE7;
                border: 1px solid #16A34A;
                color: #166534;
            }
        """,
        "Color Block Header": f"""
            /* a4-theme-marker: color-block-header */
            .title {{
                background-color: {theme_color};
                border: 2px solid {theme_color};
                color: #FFFFFF;
                letter-spacing: 1px;
                margin-bottom: 0;
            }}
            .invoice-header td {{
                background-color: {theme_color};
                border: 1px solid {theme_color};
                color: #FFFFFF;
            }}
            .invoice-header .label,
            .invoice-header .muted {{
                color: #FFFFFF;
            }}
            .items th {{
                background-color: {theme_color};
                border: 1px solid {theme_color};
                color: #FFFFFF;
            }}
        """,
        "Vibrant Accent": f"""
            /* a4-theme-marker: vibrant-accent */
            .title {{
                background-color: #FFFFFF;
                border-bottom: 5px solid {theme_color};
                color: {theme_color};
                letter-spacing: 1.5px;
            }}
            .invoice-header td {{
                background-color: {accent_light_color};
                border-top: 4px solid {theme_color};
            }}
            .items th {{
                background-color: {accent_light_color};
                border-bottom: 3px solid {theme_color};
                border-top: 3px solid {theme_color};
                color: {theme_color};
            }}
            .company-name,
            .grand-total td {{
                color: {theme_color};
            }}
        """,
        "Modern Gradient": f"""
            /* a4-theme-marker: modern-gradient */
            .title {{
                background: linear-gradient(90deg, {theme_color}, #111827);
                border: 0;
                color: #FFFFFF;
                letter-spacing: 1.1px;
            }}
            .invoice-header {{
                border-top: 6px solid {theme_color};
            }}
            .invoice-header td {{
                background-color: #F9FAFB;
                border: 1px solid #CBD5E1;
            }}
            .items th {{
                background: linear-gradient(90deg, {theme_color}, #111827);
                border: 1px solid #111827;
                color: #FFFFFF;
            }}
            .company-name,
            .grand-total td {{
                color: {theme_color};
            }}
        """,
    }
    style_block = theme_styles[style_theme_name].replace(
        "</style>",
        f"{table_fit_css}\n{visible_theme_css[style_theme_name]}\n            </style>",
    )
    style_block = (
        style_block.replace("__FONT_FAMILY__", font_family)
        .replace("__FONT_SIZE__", font_size)
        .replace("__BORDER_COLOR__", border_color)
        .replace("__STRONG_BORDER_COLOR__", strong_border_color)
        .replace("__HEADER_BG__", header_bg)
        .replace("__HEADER_TEXT_COLOR__", header_text_color)
        .replace("__TITLE_BG__", title_bg)
        .replace("__TITLE_TEXT_COLOR__", title_text_color)
        .replace("__TITLE_BORDER_COLOR__", title_border_color)
        .replace("__TABLE_ROW_BORDER_COLOR__", table_row_border_color)
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        {style_block}
    </head>
    <body{preview_body_class}>
        <div style="width: 100%; margin: 0 auto; background: {bg_color}; padding: 20px; box-sizing: border-box;">
            {page_open}
                <div class="title">{_escape(invoice_title)}</div>

                <table class="header-table invoice-header" width="{content_width_pt}" style="width: {content_width_pt}pt; border-collapse: collapse;">
                    <tr>
                        <td width="{half_width_pt}" style="width: {half_width_pt}pt;">{company_html}</td>
                        <td width="{half_width_pt}" style="width: {half_width_pt}pt;">{customer_html}</td>
                    </tr>
                </table>

                <table class="items" width="100%" style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr>
                            {item_headers}
                        </tr>
                    </thead>
                    <tbody>
                        {item_rows}
                    </tbody>
                </table>

                <table class="footer" width="{content_width_pt}" style="width: {content_width_pt}pt; border-collapse: collapse;">
                    <tr>
                        <td class="amount-words" width="{amount_words_width_pt}" style="width: {amount_words_width_pt}pt;">
                            <span class="label">Amount in Words:</span><br>
                            {_escape(amount_words)}
                        </td>
                        <td class="totals" width="{totals_width_pt}" style="width: {totals_width_pt}pt;">
                            <table width="{totals_width_pt}" style="width: {totals_width_pt}pt; border-collapse: collapse;">{total_rows}</table>
                        </td>
                    </tr>
                </table>
                <table class="signature-table" width="{content_width_pt}" style="width: {content_width_pt}pt; border-collapse: collapse;">
                    <tr>
                        <td class="footer-notes"{notes_colspan}>
                            {footer_sections}
                        </td>
                        {signatory_cell}
                    </tr>
                </table>
            {page_close}
        </div>
    </body>
    </html>
    """


def render_a4_html_to_printer(
    html_string: str,
    printer: QPrinter,
    scale_to_fit: bool = True,
) -> None:
    """Render A4 engine HTML through Chromium's WebEngine view print pipeline."""
    global _print_view

    del scale_to_fit

    if QApplication.instance() is None:
        raise RuntimeError("A QApplication must exist before A4 WebEngine printing starts.")

    _print_view = QWebEngineView()
    _print_view.resize(794, 1123)
    _print_view.move(-32000, -32000)
    _print_view.show()
    print(
        "[A4_PRINT] using WebEngineView print "
        f"printer='{printer.printerName() or 'default'}' "
        f"html_len={len(_text(html_string))} "
        f"preview_wrapper_present={_html_has_preview_wrapper(_text(html_string))}"
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
            "[A4_PRINT] WebEngine loadFinished "
            f"success={bool(success)} "
            f"printer='{printer.printerName() or 'default'}'"
        )
        load_loop.quit()

    def on_load_timeout() -> None:
        """Stop waiting when Chromium does not report HTML load completion."""
        load_success["timed_out"] = True
        print(
            "[A4_PRINT] WebEngine load timeout "
            f"timeout_ms={WEBENGINE_LOAD_TIMEOUT_MS} "
            f"printer='{printer.printerName() or 'default'}'"
        )
        load_loop.quit()

    _print_view.loadFinished.connect(on_load_finished)
    load_timer.timeout.connect(on_load_timeout)
    load_timer.start(WEBENGINE_LOAD_TIMEOUT_MS)
    _print_view.setHtml(_text(html_string))
    if load_success["value"] is None and not load_success["timed_out"]:
        load_loop.exec()

    if load_success["timed_out"]:
        raise RuntimeError(
            "QWebEngineView did not finish loading A4 receipt HTML before timeout."
        )
    if load_success["value"] is not True:
        raise RuntimeError("QWebEngineView failed to load A4 receipt HTML.")

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
            "[A4_PRINT] WebEngine print callback "
            f"success={print_success['value']} "
            f"printer='{printer.printerName() or 'default'}' "
            f"args={args}"
        )
        print_loop.quit()

    def on_print_timeout() -> None:
        """Stop waiting when Chromium does not report print completion."""
        print_success["timed_out"] = True
        print(
            "[A4_PRINT] WebEngine print timeout "
            f"timeout_ms={WEBENGINE_PRINT_TIMEOUT_MS} "
            f"printer='{printer.printerName() or 'default'}'"
        )
        print_loop.quit()

    print_method = _webengine_print_method(_print_view.page())
    if print_method is None:
        raise RuntimeError("QWebEngineView page print method is unavailable.")
    print_timer.timeout.connect(on_print_timeout)
    print_timer.start(WEBENGINE_PRINT_TIMEOUT_MS)
    print_method(printer, on_print_finished)
    if print_success["value"] is None and not print_success["timed_out"]:
        print_loop.exec()

    if print_success["timed_out"]:
        raise RuntimeError(
            "Chromium did not report A4 print completion before timeout. "
            f"Printer: '{printer.printerName() or 'default'}'."
        )
    if print_success["value"] is not True:
        raise RuntimeError(
            "Chromium print engine failed to send the document to the printer spooler. "
            f"Printer: '{printer.printerName() or 'default'}'."
        )


def print_a4_receipt(
    html_string: str,
    printer_name: Optional[Any] = None,
    settings: Optional[Mapping[str, Any]] = None,
    paper_size: Optional[str] = None,
    printer: Optional[QPrinter] = None,
) -> str:
    """
    Print an A4 HTML receipt through QWebEngineView, or a PDF fallback.

    Args:
        html_string: Complete HTML content returned by ``generate_a4_html`` or a
            compatible caller.
        printer_name: Optional saved local printer name. Missing printers use the
            system default printer; unavailable saved printers raise a clear error.
            For dialog-driven callers, a ``QPrinter`` may also be passed as this
            second positional argument to preserve the public API.
        settings: Optional Normal Printer settings containing ``a4_paper_size``.
        paper_size: Optional explicit paper-size override, either ``A4`` or ``A5``.
        printer: Optional preconfigured ``QPrinter`` from a ``QPrintDialog``.

    Raises:
        RuntimeError: If the printer or WebEngine print operation fails.
    """
    try:
        selected_printer = printer
        requested_printer_name = printer_name
        if isinstance(printer_name, QPrinter):
            selected_printer = printer_name
            requested_printer_name = None

        printer = selected_printer or QPrinter(QPrinter.PrinterMode.HighResolution)
        _set_native_output_format(printer)
        if selected_printer is None:
            printer.setResolution(96)
            _apply_printer_name(printer, requested_printer_name)
        selected_paper_size = configure_a4_printer_page(
            printer,
            settings=settings,
            paper_size=paper_size,
        )
        resolved_printer_name = _text(requested_printer_name).strip()
        _validate_physical_printer(printer, resolved_printer_name or printer.printerName())
        print(
            "[A4_PRINT] physical route "
            f"selected_printer='{printer.printerName() or 'default'}' "
            f"requested_printer='{resolved_printer_name or 'dialog/default'}' "
            f"paper_size='{selected_paper_size}' "
            f"printer_valid={printer.isValid()} "
            f"html_len={len(_text(html_string))}"
        )
        probe_page = QWebEnginePage()
        direct_print_available = _webengine_print_method(probe_page) is not None
        probe_page.deleteLater()
        print(
            "[A4_PRINT] WebEngine method availability "
            f"print={direct_print_available} "
            f"printToPdf={hasattr(probe_page, 'printToPdf')} "
            f"pdfPrintingFinished={hasattr(probe_page, 'pdfPrintingFinished')}"
        )
        if direct_print_available:
            render_a4_html_to_printer(html_string, printer)
            return (
                "A4 invoice sent to printer through WebEngine direct physical print."
            )

        temp_pdf_path = _create_temp_pdf_path()
        print(
            "[A4_PRINT] direct WebEngine print unsupported; generating PDF fallback "
            f"file='{temp_pdf_path}' "
            f"printer='{printer.printerName() or 'default'}'"
        )
        export_a4_pdf(
            html_string,
            temp_pdf_path,
            settings=settings,
            paper_size=paper_size,
        )
        return _print_generated_pdf_fallback(temp_pdf_path, printer, resolved_printer_name)
    except Exception as exc:
        raise RuntimeError(f"Could not print A4 receipt: {exc}") from exc


def export_a4_pdf(
    html_string: str,
    file_path: str,
    settings: Optional[Mapping[str, Any]] = None,
    paper_size: Optional[str] = None,
) -> None:
    """
    Export A4 HTML to PDF through QWebEnginePage's native PDF pipeline.

    Args:
        html_string: Complete HTML content returned by ``generate_a4_html`` or a
            compatible caller.
        file_path: Full destination path for the generated PDF file.
        settings: Optional Normal Printer settings containing ``a4_paper_size``.
        paper_size: Optional explicit paper-size override, either ``A4`` or ``A5``.

    Raises:
        RuntimeError: If WebEngine cannot load the HTML or complete PDF export.
    """
    try:
        safe_settings = _effective_settings(settings or {})
        paper_layout = _paper_layout(safe_settings, paper_size)
        page = QWebEnginePage()
        print(
            "[A4_PRINT] using WebEngine printToPdf "
            f"file='{file_path}' "
            f"paper_size='{paper_layout['name']}' "
            f"html_len={len(_text(html_string))} "
            f"preview_wrapper_present={_html_has_preview_wrapper(_text(html_string))}"
        )
        load_success = {"value": False}
        load_loop = QEventLoop()

        def on_load_finished(success: bool) -> None:
            """Stop waiting once Chromium has fully loaded the invoice HTML."""
            load_success["value"] = bool(success)
            load_loop.quit()

        page.loadFinished.connect(on_load_finished)
        page.setHtml(_text(html_string))
        load_loop.exec()

        if not load_success["value"]:
            raise RuntimeError("QWebEnginePage failed to load A4 receipt HTML.")

        layout = QPageLayout(
            QPageSize(paper_layout["page_size_id"]),
            QPageLayout.Orientation.Portrait,
            QMarginsF(0, 0, 0, 0),
            QPageLayout.Unit.Millimeter,
        )
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
        page.printToPdf(file_path, layout)
        pdf_loop.exec()

        if pdf_success["value"] is False:
            raise RuntimeError("QWebEnginePage PDF export failed.")
        if pdf_success["value"] is None:
            raise RuntimeError("QWebEnginePage PDF export did not report completion.")
    except Exception as exc:
        raise RuntimeError("Could not export A4 PDF.") from exc
