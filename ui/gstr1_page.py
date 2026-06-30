"""
GSTR-1 Report Page for the Accounting Desktop Application.
Provides GSTR-1 generation with JSON and Excel export for GST portal upload.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QDateEdit, QPushButton, QFrame, QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox, QFileDialog, QTabWidget
from PySide6.QtCore import Qt, QDate, QObject, QThread, Signal
from PySide6.QtGui import QColor
from config import active_company_manager
from db import Database
from bizora_core.gstr1_logic import GSTR1Logic
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui import theme
from ui.book_report_common import report_filter_frame_style, report_data_table_style, report_compound_entry_page_style, page_heading_style, report_status_label_style, footer_value_style
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class GSTR1ReportWorker(QObject):
    """Generate GSTR-1 data on a worker-owned database connection."""
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()

    def __init__(self, db_type, db_path, company_id, from_date, to_date):
        super().__init__()
        self.db_type = db_type
        self.db_path = db_path
        self.company_id = company_id
        self.from_date = from_date
        self.to_date = to_date

    def run(self):
        """Fetch, classify, and aggregate GSTR-1 data outside the UI thread."""
        worker_db = None
        try:
            worker_db = Database(db_type=self.db_type, db_path=self.db_path)
            logic = GSTR1Logic(worker_db)
            report = logic.generate_gstr1_report(self.company_id, self.from_date, self.to_date)
            self.data_ready.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if worker_db is not None:
                try:
                    worker_db.force_disconnect()
                except Exception:
                    pass
            self.finished.emit()

class GSTR1Page(UiMemoryMixin, QWidget):
    """GSTR-1 Report page with JSON/Excel export for GST portal upload."""

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.company_id = None
        self.company_state = ''
        self.current_report = None
        self.gstr1_logic = GSTR1Logic(self.db)
        self._loading = False
        self._report_thread = None
        self._report_worker = None
        self.setup_ui()
        self.load_company()
        self._init_ui_memory()

    def setup_ui(self):
        self.setStyleSheet(report_compound_entry_page_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.title_label = QLabel('GSTR-1 Report Generation')
        self.title_label.setStyleSheet(page_heading_style(18))
        layout.addWidget(self.title_label)
        self.filter_frame = QFrame()
        self.filter_frame.setStyleSheet(report_filter_frame_style())
        filter_layout = QHBoxLayout(self.filter_frame)
        filter_layout.setSpacing(10)
        self.from_date = QDateEdit()
        configure_qdate_edit(self.from_date)
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat('MMM yyyy')
        self.to_date = QDateEdit()
        configure_qdate_edit(self.to_date)
        self.to_date.setDate(QDate.currentDate())
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat('MMM yyyy')
        for label_text, widget in (('Period From:', self.from_date), ('To:', self.to_date)):
            filter_layout.addWidget(QLabel(label_text))
            filter_layout.addWidget(widget)
        generate_btn = QPushButton('Generate GSTR-1')
        generate_btn.clicked.connect(self.generate_gstr1)
        export_json_btn = QPushButton('Export JSON')
        export_json_btn.clicked.connect(self.export_json)
        export_json_btn.setEnabled(False)
        export_excel_btn = QPushButton('Export Excel')
        export_excel_btn.clicked.connect(self.export_excel)
        export_excel_btn.setEnabled(False)
        self.export_json_btn = export_json_btn
        self.export_excel_btn = export_excel_btn
        self.generate_btn = generate_btn
        filter_layout.addWidget(generate_btn)
        filter_layout.addWidget(export_json_btn)
        filter_layout.addWidget(export_excel_btn)
        filter_layout.addStretch()
        layout.addWidget(self.filter_frame)
        self.status_label = QLabel('Ready')
        self.status_label.setStyleSheet(report_status_label_style())
        layout.addWidget(self.status_label)
        self.summary_frame = QFrame()
        self.summary_frame.setStyleSheet(report_filter_frame_style())
        summary_layout = QGridLayout(self.summary_frame)
        summary_layout.setSpacing(10)
        self.summary_labels = {}
        for idx, (label, key) in enumerate([('Total Taxable Value:', 'total_taxable_value'), ('Total Tax Collected:', 'total_tax'), ('Total Invoices:', 'total_invoice_count'), ('B2B Invoices:', 'b2b_count'), ('B2CL Invoices:', 'b2cl_count'), ('B2CS Invoices:', 'b2cs_count')]):
            summary_layout.addWidget(QLabel(label), idx // 2, idx % 2 * 2)
            value_label = QLabel('0.00' if 'Value' in label or 'Tax' in label else '0')
            value_label.setStyleSheet(footer_value_style())
            summary_layout.addWidget(value_label, idx // 2, idx % 2 * 2 + 1)
            self.summary_labels[key] = value_label
        layout.addWidget(self.summary_frame)
        self.tab_widget = QTabWidget()
        self.b2b_table = self._create_table(['GSTIN/UIN', 'Invoice No', 'Invoice Date', 'Invoice Value', 'Place of Supply', 'Tax Rate', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'CESS'])
        self.tab_widget.addTab(self.b2b_table, 'B2B (Registered)')
        self.b2cl_table = self._create_table(['Invoice No', 'Invoice Date', 'Invoice Value', 'Place of Supply', 'Tax Rate', 'Taxable Value', 'IGST', 'CESS'])
        self.tab_widget.addTab(self.b2cl_table, 'B2CL (Interstate > 2.5L)')
        self.b2cs_table = self._create_table(['Type', 'Place of Supply', 'Tax Rate', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'CESS', 'Total Value', 'Invoice Count'])
        self.tab_widget.addTab(self.b2cs_table, 'B2CS (Consolidated)')
        self.hsn_table = self._create_table(['HSN Code', 'Description', 'UQC', 'Total Quantity', 'Total Taxable Value', 'IGST', 'CGST', 'SGST', 'CESS', 'Tax Rate'])
        self.tab_widget.addTab(self.hsn_table, 'HSN Summary')
        self.doc_table = self._create_table(['Document Type', 'From No', 'To No', 'Total Count', 'Cancelled Count', 'Net Count'])
        self.tab_widget.addTab(self.doc_table, 'Document Summary')
        layout.addWidget(self.tab_widget, 1)

    def _create_table(self, headers):
        """Create a styled table widget."""
        table = QTableWidget()
        table.setSortingEnabled(False)
        apply_read_only_report_table_selection(table)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        return table

    def load_company(self):
        active = active_company_manager.get_active_company()
        if active:
            self.company_id = active.get('id')
            self.company_state = (active.get('state') or '').strip()

    def generate_gstr1(self):
        """Generate GSTR-1 report for selected period."""
        if self._loading:
            return
        if not self.company_id:
            QMessageBox.warning(self, 'No Company', 'Please open a company first.')
            return
        from_date = qdate_to_db(self.from_date.date())
        to_date = qdate_to_db(self.to_date.date())
        db_type = getattr(self.db, 'db_type', None)
        db_path = getattr(self.db, 'db_path', None)
        thread = QThread(self)
        worker = GSTR1ReportWorker(db_type, db_path, self.company_id, from_date, to_date)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.data_ready.connect(self._on_report_ready)
        worker.error.connect(self._on_report_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_report_finished)
        self._report_thread = thread
        self._report_worker = worker
        self._set_loading_state(True)
        thread.start()

    def _set_loading_state(self, is_loading):
        """Toggle controls while the worker calculates the report."""
        self._loading = is_loading
        self.generate_btn.setEnabled(not is_loading)
        self.export_json_btn.setEnabled(not is_loading and bool(self.current_report))
        self.export_excel_btn.setEnabled(not is_loading and bool(self.current_report))
        if is_loading:
            self.status_label.setText('Calculating...')

    def _on_report_ready(self, report):
        """Populate all GSTR-1 tabs after worker calculation completes."""
        self.current_report = report
        summary = self.current_report.get('summary', {})
        self.summary_labels['total_taxable_value'].setText(f"{summary.get('total_taxable_value', 0):.2f}")
        self.summary_labels['total_tax'].setText(f"{summary.get('total_tax', 0):.2f}")
        self.summary_labels['total_invoice_count'].setText(str(summary.get('total_invoice_count', 0)))
        self.summary_labels['b2b_count'].setText(str(len(self.current_report.get('b2b', []))))
        self.summary_labels['b2cl_count'].setText(str(len(self.current_report.get('b2cl', []))))
        self.summary_labels['b2cs_count'].setText(str(len(self.current_report.get('b2cs', []))))
        self._populate_b2b_table()
        self._populate_b2cl_table()
        self._populate_b2cs_table()
        self._populate_hsn_table()
        self._populate_doc_table()
        self.status_label.setText('GSTR-1 report generated successfully.')

    def _on_report_error(self, message):
        """Display worker errors without touching worker-owned objects."""
        QMessageBox.critical(self, 'Error', f'Failed to generate GSTR-1 report: {message}')
        self.status_label.setText('GSTR-1 generation failed.')

    def _on_report_finished(self):
        """Reset worker references and controls after the thread exits."""
        self._report_thread = None
        self._report_worker = None
        self._set_loading_state(False)

    def _populate_b2b_table(self):
        """Populate B2B table."""
        self.b2b_table.setRowCount(0)
        b2b_data = self.current_report.get('b2b', [])
        for b2b in b2b_data:
            inv = b2b.get('inv', {})
            for item in inv.get('itms', []):
                det = item.get('itm_det', {})
                row = self.b2b_table.rowCount()
                self.b2b_table.insertRow(row)
                values = [b2b.get('ctin', ''), inv.get('inum', ''), inv.get('idt', ''), f"{inv.get('val', 0):.2f}", inv.get('pos', ''), f"{det.get('rt', 0):.2f}", f"{det.get('txval', 0):.2f}", f"{det.get('iamt', 0):.2f}", f"{det.get('camt', 0):.2f}", f"{det.get('samt', 0):.2f}", f"{det.get('csamt', 0):.2f}"]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.b2b_table.setItem(row, col, item)
        apply_adjustable_table_columns(self.b2b_table)

    def _populate_b2cl_table(self):
        """Populate B2CL table."""
        self.b2cl_table.setRowCount(0)
        b2cl_data = self.current_report.get('b2cl', [])
        for b2cl in b2cl_data:
            inv = b2cl.get('inv', {})
            for item in inv.get('itms', []):
                det = item.get('itm_det', {})
                row = self.b2cl_table.rowCount()
                self.b2cl_table.insertRow(row)
                values = [inv.get('inum', ''), inv.get('idt', ''), f"{inv.get('val', 0):.2f}", b2cl.get('pos', ''), f"{det.get('rt', 0):.2f}", f"{det.get('txval', 0):.2f}", f"{det.get('iamt', 0):.2f}", f"{det.get('csamt', 0):.2f}"]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.b2cl_table.setItem(row, col, item)
        apply_adjustable_table_columns(self.b2cl_table)

    def _populate_b2cs_table(self):
        """Populate B2CS table."""
        self.b2cs_table.setRowCount(0)
        b2cs_data = self.current_report.get('b2cs', [])
        for b2cs in b2cs_data:
            row = self.b2cs_table.rowCount()
            self.b2cs_table.insertRow(row)
            total_value = b2cs.get('txval', 0) + b2cs.get('iamt', 0) + b2cs.get('camt', 0) + b2cs.get('samt', 0) + b2cs.get('csamt', 0)
            values = [b2cs.get('typ', ''), b2cs.get('pos', ''), f"{b2cs.get('rt', 0):.2f}", f"{b2cs.get('txval', 0):.2f}", f"{b2cs.get('iamt', 0):.2f}", f"{b2cs.get('camt', 0):.2f}", f"{b2cs.get('samt', 0):.2f}", f"{b2cs.get('csamt', 0):.2f}", f'{total_value:.2f}', str(b2cs.get('inv_count', 0))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.b2cs_table.setItem(row, col, item)
        apply_adjustable_table_columns(self.b2cs_table)

    def _populate_hsn_table(self):
        """Populate HSN Summary table."""
        self.hsn_table.setRowCount(0)
        hsn_data = self.current_report.get('hsn', [])
        for hsn in hsn_data:
            row = self.hsn_table.rowCount()
            self.hsn_table.insertRow(row)
            values = [hsn.get('hsn', ''), hsn.get('desc', ''), hsn.get('uqc', ''), f"{hsn.get('qty', 0):.2f}", f"{hsn.get('val', 0):.2f}", f"{hsn.get('iamt', 0):.2f}", f"{hsn.get('camt', 0):.2f}", f"{hsn.get('samt', 0):.2f}", f"{hsn.get('csamt', 0):.2f}", f"{hsn.get('rt', 0):.2f}"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.hsn_table.setItem(row, col, item)
        apply_adjustable_table_columns(self.hsn_table)

    def _populate_doc_table(self):
        """Populate Document Summary table."""
        self.doc_table.setRowCount(0)
        doc_data = self.current_report.get('doc_issue', {})
        for doc in doc_data.get('doc_det', []):
            row = self.doc_table.rowCount()
            self.doc_table.insertRow(row)
            values = ['Invoice', doc.get('from_nm', ''), doc.get('to_nm', ''), str(doc.get('totnum', 0)), str(doc.get('cancel_num', 0)), str(doc.get('net_doc', 0))]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.doc_table.setItem(row, col, item)
        apply_adjustable_table_columns(self.doc_table)

    def export_json(self):
        """Export GSTR-1 report to JSON file."""
        if not self.current_report:
            QMessageBox.warning(self, 'No Report', 'Please generate GSTR-1 report first.')
            return
        filepath, _ = QFileDialog.getSaveFileName(self, 'Save GSTR-1 JSON', '', 'JSON Files (*.json)')
        if filepath:
            try:
                success = self.gstr1_logic.export_to_json(self.current_report, filepath)
                if success:
                    QMessageBox.information(self, 'Success', f'GSTR-1 JSON exported to {filepath}')
                else:
                    QMessageBox.critical(self, 'Error', 'Failed to export JSON file.')
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to export JSON: {e}')

    def export_excel(self):
        """Export GSTR-1 report to Excel file."""
        if not self.current_report:
            QMessageBox.warning(self, 'No Report', 'Please generate GSTR-1 report first.')
            return
        filepath, _ = QFileDialog.getSaveFileName(self, 'Save GSTR-1 Excel', '', 'Excel Files (*.xlsx)')
        if filepath:
            try:
                success = self.gstr1_logic.export_to_excel(self.current_report, filepath)
                if success:
                    QMessageBox.information(self, 'Success', f'GSTR-1 Excel exported to {filepath}')
                else:
                    QMessageBox.critical(self, 'Error', 'Failed to export Excel file. Make sure openpyxl is installed (pip install openpyxl).')
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Failed to export Excel: {e}')

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(report_compound_entry_page_style())
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(page_heading_style(18))
        if hasattr(self, 'filter_frame'):
            self.filter_frame.setStyleSheet(report_filter_frame_style())
        if hasattr(self, 'status_label'):
            self.status_label.setStyleSheet(report_status_label_style())
        if hasattr(self, 'summary_frame'):
            self.summary_frame.setStyleSheet(report_filter_frame_style())
        for value_label in getattr(self, 'summary_labels', {}).values():
            value_label.setStyleSheet(footer_value_style())
        for table_name in ('b2b_table', 'b2cl_table', 'b2cs_table', 'hsn_table'):
            table = getattr(self, table_name, None)
            if table is not None:
                table.setStyleSheet(report_data_table_style())