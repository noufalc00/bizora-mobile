"""
HTML print preview dialog for Faizan Pro Accounting.

This module provides a reusable PySide6 dialog that displays rendered HTML from
``PrintEngine`` and sends the rendered document to a user-selected printer.
"""
from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin, apply_standard_window_chrome

class PrintPreviewDialog(UiMemoryMixin, QDialog):
    """Preview rendered invoice HTML and print it through Qt print support."""

    def __init__(self, html_content: Optional[str]=None, parent: Optional[QWidget]=None) -> None:
        """
        Initialize the print preview dialog.

        Args:
            html_content: Optional rendered HTML to load immediately.
            parent: Optional parent widget for modal ownership.
        """
        super().__init__(parent)
        self.setWindowTitle('Print Preview')
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        self.text_browser = QTextBrowser(self)
        self.text_browser.setReadOnly(True)
        self.print_button = QPushButton('Print', self)
        self.save_pdf_button = QPushButton('Save as PDF', self)
        self.close_button = QPushButton('Close', self)
        self._setup_ui()
        self._connect_signals()
        if html_content is not None:
            self.load_html(html_content)
        self._init_ui_memory()

    def _setup_ui(self) -> None:
        """Build the preview area and bottom action bar."""
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.text_browser)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.print_button)
        button_layout.addWidget(self.save_pdf_button)
        button_layout.addWidget(self.close_button)
        main_layout.addLayout(button_layout)

    def _connect_signals(self) -> None:
        """Connect button signals to their dialog actions."""
        self.print_button.clicked.connect(self._print_document)
        self.save_pdf_button.clicked.connect(self._save_as_pdf)
        self.close_button.clicked.connect(self.close)

    def load_html(self, html_content: str) -> None:
        """
        Load rendered HTML into the preview browser.

        Args:
            html_content: Complete or partial HTML content from ``PrintEngine``.
        """
        try:
            self.text_browser.setHtml(html_content or '')
        except Exception as exc:
            QMessageBox.warning(self, 'Preview Error', f'Could not load print preview:\n{exc}')

    def _print_document(self) -> None:
        """Open the system print dialog and send the preview document to print."""
        try:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            print_dialog = QPrintDialog(printer, self)
            print_dialog.setWindowTitle('Print Document')
            if print_dialog.exec() != QPrintDialog.DialogCode.Accepted:
                return
            document = self.text_browser.document()
            print_method = getattr(document, 'print_', None) or getattr(document, 'print', None)
            if not callable(print_method):
                raise RuntimeError('Qt document printing API is unavailable.')
            print_method(printer)
        except Exception as exc:
            QMessageBox.warning(self, 'Print Error', f'Could not print the document:\n{exc}')

    def _save_as_pdf(self) -> None:
        """Export the preview document to a user-selected PDF file."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, 'Save Invoice as PDF', 'invoice.pdf', 'PDF Files (*.pdf)')
            if not file_path:
                return
            if not file_path.lower().endswith('.pdf'):
                file_path = f'{file_path}.pdf'
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(file_path)
            document = self.text_browser.document()
            print_method = getattr(document, 'print_', None) or getattr(document, 'print', None)
            if not callable(print_method):
                raise RuntimeError('Qt document PDF export API is unavailable.')
            print_method(printer)
            QMessageBox.information(self, 'PDF Saved', f'Invoice PDF saved successfully:\n{file_path}')
        except Exception as exc:
            QMessageBox.warning(self, 'PDF Export Error', f'Could not save the PDF:\n{exc}')