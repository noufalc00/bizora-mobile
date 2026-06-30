"""Universal HTML preview dialog for printable reports and books."""
from __future__ import annotations
from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None

class UniversalPreviewDialog(UiMemoryMixin, QDialog):
    """Preview HTML report output with print and PDF export actions."""
    THERMAL_PREVIEW_WIDTH_PX = 280

    def __init__(self, html_string: str, mode: str='A4', parent=None, title: str | None=None):
        """Initialize the preview dialog with a complete HTML string."""
        if isinstance(mode, QWidget) and parent is None:
            parent = mode
            mode = 'A4'
        elif isinstance(mode, str) and mode.strip().lower() not in {'a4', 'thermal'}:
            title = title or mode
            mode = 'A4'
        super().__init__(parent)
        self.html_string = html_string or ''
        self.html = self.html_string
        self.mode = self._normalize_mode(mode)
        self.setWindowTitle(title or 'Report Preview')
        self._resize_for_mode()
        self._build_ui()
        self._init_ui_memory()

    def _normalize_mode(self, mode: object) -> str:
        """Return the supported preview mode name for caller-provided values."""
        mode_text = str(mode or 'A4').strip().lower()
        return 'Thermal' if mode_text == 'thermal' else 'A4'

    def _resize_for_mode(self) -> None:
        """Apply a page-like preview size for the selected print mode."""
        if self.mode == 'Thermal':
            self.resize(350, 700)
            return
        self.resize(1100, 720)

    def _build_ui(self) -> None:
        """Build the HTML preview browser and action button row."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self._uses_webengine = QWebEngineView is not None
        if self._uses_webengine:
            self.browser = QWebEngineView(self)
            self.browser.setHtml(self.html_string)
        else:
            self.browser = QTextBrowser(self)
            self.browser.setReadOnly(True)
            self.browser.setHtml(self.html_string)
        self._add_preview_browser(layout)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        print_button = QPushButton('Print')
        export_pdf_button = QPushButton('Export PDF')
        close_button = QPushButton('Close')
        print_button.clicked.connect(self._print_document)
        export_pdf_button.clicked.connect(self._export_pdf)
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(print_button)
        button_layout.addWidget(export_pdf_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def _add_preview_browser(self, layout: QVBoxLayout) -> None:
        """Add the browser with mode-specific sizing while preserving A4 expansion."""
        if self.mode != 'Thermal':
            layout.addWidget(self.browser, 1)
            return
        self.browser.setFixedWidth(self.THERMAL_PREVIEW_WIDTH_PX)
        self.browser.setStyleSheet(f'{self.browser.__class__.__name__} {{ background-color: #ffffff; }}')
        preview_container = QWidget(self)
        preview_container.setStyleSheet('QWidget { background-color: #d0d0d0; }')
        preview_layout = QHBoxLayout(preview_container)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.addWidget(self.browser, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(preview_container, 1)

    def _print_document(self) -> None:
        """Open the system print dialog and print the preview document."""
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            print_dialog = QPrintDialog(printer, self)
            print_dialog.setWindowTitle(f'Print {self.mode} Report')
            if print_dialog.exec() != QPrintDialog.DialogCode.Accepted:
                return
            if self.mode == 'Thermal':
                self._print_thermal(printer)
                return
            self._print_a4(printer)
        except Exception as exc:
            QMessageBox.critical(self, 'Print Failed', f'Could not print report:\n{exc}')

    def _print_a4(self, printer: QPrinter) -> None:
        """Route dialog-driven A4 printing through the A4 print engine."""
        try:
            from utils.a4_print_engine import print_a4_receipt
        except Exception as exc:
            raise RuntimeError('A4 print engine is unavailable.') from exc
        print_a4_receipt(self.html, printer)

    def _print_thermal(self, printer: QPrinter) -> None:
        """Route dialog-driven thermal printing through the thermal print engine."""
        try:
            from utils.thermal_print_engine import print_thermal_receipt
        except Exception as exc:
            raise RuntimeError('Thermal print engine is unavailable. Please try again after thermal_print_engine.py is installed.') from exc
        print_thermal_receipt(self.html, printer)

    def _export_a4_pdf(self, file_path: str) -> None:
        """Export A4 preview HTML through the A4 PDF engine."""
        try:
            from utils.a4_print_engine import export_a4_pdf
        except Exception as exc:
            raise RuntimeError('A4 PDF export engine is unavailable.') from exc
        export_a4_pdf(self.html, file_path)

    def _export_thermal_pdf(self, file_path: str) -> None:
        """Export thermal preview HTML using the thermal engine or a narrow PDF."""
        try:
            from utils.thermal_print_engine import export_thermal_pdf
        except ImportError:
            self._export_thermal_pdf_with_qt(file_path)
            return
        except Exception as exc:
            raise RuntimeError('Thermal PDF export engine is unavailable.') from exc
        export_thermal_pdf(self.html, file_path)

    def _export_thermal_pdf_with_qt(self, file_path: str) -> None:
        """Write a narrow receipt PDF when the thermal engine has no exporter yet."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(file_path)
        printer.setPageLayout(QPageLayout(QPageSize(QSizeF(80.0, 297.0), QPageSize.Unit.Millimeter, 'Thermal 80mm'), QPageLayout.Orientation.Portrait, QMarginsF(3.0, 3.0, 3.0, 3.0), QPageLayout.Unit.Millimeter))
        if self._uses_webengine:
            page = self.browser.page()
            pdf_finished_signal = getattr(page, 'pdfPrintingFinished', None)
            if pdf_finished_signal is not None:
                pdf_finished_signal.connect(self._on_webengine_pdf_finished)
            page.printToPdf(file_path, printer.pageLayout())
            return
        self.browser.document().print_(printer)
        QMessageBox.information(self, 'Export Complete', f'PDF exported to:\n{file_path}')

    def _export_pdf(self) -> None:
        """Export the current preview document to a user-selected PDF file."""
        file_path, _ = QFileDialog.getSaveFileName(self, 'Export PDF', 'thermal_receipt.pdf' if self.mode == 'Thermal' else 'report.pdf', 'PDF Files (*.pdf);;All Files (*)')
        if not file_path:
            return
        if not file_path.lower().endswith('.pdf'):
            file_path = f'{file_path}.pdf'
        try:
            if self.mode == 'Thermal':
                self._export_thermal_pdf(file_path)
                return
            self._export_a4_pdf(file_path)
            QMessageBox.information(self, 'Export Complete', f'PDF exported to:\n{file_path}')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', f'Could not export PDF:\n{exc}')

    def _on_webengine_pdf_finished(self, file_path: str, success: bool) -> None:
        """Show PDF export status once WebEngine finishes writing the file."""
        try:
            self.browser.page().pdfPrintingFinished.disconnect(self._on_webengine_pdf_finished)
        except Exception:
            pass
        if success:
            QMessageBox.information(self, 'Export Complete', f'PDF exported to:\n{file_path}')
            return
        QMessageBox.critical(self, 'Export Failed', f'Could not export PDF:\n{file_path}')