"""
PDF Preview Dialog for in-app PDF viewing before saving.
"""
import os
import shutil
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QFileDialog, QWidget
from PySide6.QtCore import Qt, QUrl
from ui import theme
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class PdfPreviewDialog(UiMemoryMixin, QDialog):
    """Dialog to preview PDF before saving."""

    def __init__(self, pdf_filepath: str, parent=None):
        """
        Initialize the PDF preview dialog.
        
        Args:
            pdf_filepath: Path to the temporary PDF file to preview
            parent: Parent widget
        """
        super().__init__(parent)
        self.pdf_filepath = pdf_filepath
        self.setWindowTitle('PDF Preview')
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        self._setup_ui()
        self._load_pdf()
        self._init_ui_memory()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        save_btn = QPushButton('Save As PDF...')
        save_btn.setStyleSheet(theme.sales_primary_button_style())
        save_btn.clicked.connect(self._save_as)
        close_btn = QPushButton('Close')
        close_btn.setStyleSheet(theme.sales_compact_button_style())
        close_btn.clicked.connect(self.close)
        toolbar.addWidget(save_btn)
        toolbar.addStretch()
        toolbar.addWidget(close_btn)
        layout.addLayout(toolbar)
        self.pdf_viewer = self._create_pdf_viewer()
        layout.addWidget(self.pdf_viewer)

    def _create_pdf_viewer(self) -> QWidget:
        """
        Create PDF viewer widget.
        
        Tries QPdfView first, falls back to QWebEngineView.
        """
        try:
            from PySide6.QtPdfWidgets import QPdfView
            from PySide6.QtPdf import QPdfDocument
            viewer = QPdfView()
            self.pdf_document = QPdfDocument(self)
            self.pdf_document.load(self.pdf_filepath)
            viewer.setDocument(self.pdf_document)
            return viewer
        except ImportError:
            try:
                from PySide6.QtWebEngineWidgets import QWebEngineView
                viewer = QWebEngineView()
                viewer.setUrl(QUrl.fromLocalFile(self.pdf_filepath))
                return viewer
            except ImportError:
                from PySide6.QtWidgets import QLabel
                label = QLabel('PDF viewing not available.\nPlease save the file to view it externally.')
                label.setAlignment(Qt.AlignCenter)
                label.setStyleSheet(f"font-size: 14px; color: {theme._theme_colors()['muted_text']};")
                return label

    def _load_pdf(self):
        """Load the PDF into the viewer."""
        pass

    def _save_as(self):
        """Save the PDF to a user-selected location."""
        default_name = os.path.basename(self.pdf_filepath)
        if default_name.startswith('tmp'):
            default_name = 'export.pdf'
        file_path, _ = QFileDialog.getSaveFileName(self, 'Save PDF As', default_name, 'PDF Files (*.pdf)')
        if not file_path:
            return
        try:
            shutil.copy2(self.pdf_filepath, file_path)
            QMessageBox.information(self, 'Success', f'PDF saved successfully to:\n{file_path}')
        except Exception as e:
            QMessageBox.critical(self, 'Save Error', f'Failed to save PDF:\n{str(e)}')

    def closeEvent(self, event):
        """Handle dialog close event - cleanup temp file."""
        if hasattr(self, 'pdf_document'):
            self.pdf_document.close()
        import threading

        def cleanup_later():
            import time
            time.sleep(0.5)
            try:
                if os.path.exists(self.pdf_filepath):
                    os.remove(self.pdf_filepath)
            except Exception as e:
                print(f'[PdfPreviewDialog] Error removing temp file: {e}')
        cleanup_thread = threading.Thread(target=cleanup_later, daemon=True)
        cleanup_thread.start()
        super().closeEvent(event)