"""
Inter-Company Data Transfer dialog.
"""
from __future__ import annotations
import os
from typing import Any
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QDateEdit, QDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from ui import theme
from ui.checkbox_style import CheckBox3D, create_checkbox
from ui.table_header_utils import apply_read_only_report_table_selection
from db import BASE_DIR, Database, get_default_database_path
from bizora_core.company_logic import CompanyLogic
from utils.data_transfer import DataTransferEngine, fetch_available_records
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin, configure_non_modal_window
TRANSFER_TYPE_OPTIONS: tuple[tuple[str, str, str], ...] = (('sales_entry_checkbox', 'sales', 'Sales Entry'), ('sales_return_entry_checkbox', 'sales_returns', 'Sales Return Entry'), ('purchase_entry_checkbox', 'purchases', 'Purchase Entry'), ('purchase_return_entry_checkbox', 'purchase_returns', 'Purchase Return Entry'), ('quotation_entry_checkbox', 'quotations', 'Quotation Entry'))
TRANSFER_OPTION_GRID_ROWS = (('sales_entry_checkbox', 'purchase_entry_checkbox'), ('sales_return_entry_checkbox', 'purchase_return_entry_checkbox'), ('quotation_entry_checkbox', None))

def _transfer_dialog_stylesheet() -> str:
    """Return theme-aware stylesheet for the inter-company transfer dialog."""
    colors = theme._theme_colors()
    return f"\n        {theme.complex_tool_dialog_style()}\n        QScrollArea {{\n            border: none;\n            background-color: transparent;\n        }}\n        QLineEdit#sourceCompanyInput {{\n            background-color: {colors.get('surface_alt', colors['input_bg'])};\n            color: {colors['input_text']};\n            border: 1px solid {colors['border']};\n            border-radius: 5px;\n            padding: 8px 10px;\n            font-size: 13px;\n        }}\n        QPushButton#loadRecordsButton {{\n            background-color: {colors.get('surface_alt', colors['panel_bg'])};\n            border: 1px solid {colors['border']};\n        }}\n        QPushButton#loadRecordsButton:hover {{\n            border-color: {colors['focus_border']};\n        }}\n        QPushButton#transferButton, QPushButton#confirmSelectionButton {{\n            background-color: {colors['button_primary']};\n            color: #FFFFFF;\n            border: none;\n        }}\n        QPushButton#transferButton:hover, QPushButton#confirmSelectionButton:hover {{\n            background-color: {colors['focus_border']};\n        }}\n        QPushButton#transferButton:disabled {{\n            background-color: {colors['border']};\n            color: {colors['muted_text']};\n        }}\n    "

def _create_row_select_checkbox(metadata: dict) -> tuple[QWidget, CheckBox3D]:
    container = QWidget()
    row_layout = QHBoxLayout(container)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    checkbox = create_checkbox('', label_color='#f3f4f6', font_size=11)
    checkbox.setChecked(False)
    checkbox.setProperty('transfer_metadata', metadata)
    row_layout.addWidget(checkbox)
    return (container, checkbox)

def _configure_records_table(table: QTableWidget) -> None:
    table.setHorizontalHeaderLabels(['Select', 'Type', 'Bill/Invoice No', 'Date', 'Party Name', 'Amount'])
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    apply_read_only_report_table_selection(table)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
    table.setColumnWidth(0, 70)

def _populate_records_table(table: QTableWidget, records: list[dict[str, Any]]) -> None:
    table.setRowCount(len(records))
    for row_index, record in enumerate(records):
        metadata = {'type_key': record['type_key'], 'record_id': record['record_id'], 'document_number': record['document_number']}
        select_widget, _checkbox = _create_row_select_checkbox(metadata)
        table.setCellWidget(row_index, 0, select_widget)
        table.setRowHeight(row_index, 34)
        values = [record['type_label'], record['document_number'], record['document_date'], record['party_name'], f"{record['amount']:.2f}"]
        for column_index, value in enumerate(values, start=1):
            item = QTableWidgetItem(str(value))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setData(Qt.ItemDataRole.UserRole, metadata)
            if column_index == 5:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_index, column_index, item)

def _row_select_checkbox(table: QTableWidget, row: int) -> CheckBox3D | None:
    container = table.cellWidget(row, 0)
    if container is None:
        return None
    checkbox = container.findChild(CheckBox3D)
    return checkbox if isinstance(checkbox, CheckBox3D) else None

def _collect_checked_records(table: QTableWidget) -> dict[str, list[str]]:
    selected_data: dict[str, list[str]] = {}
    for row_index in range(table.rowCount()):
        checkbox = _row_select_checkbox(table, row_index)
        if checkbox is None or not checkbox.isChecked():
            continue
        metadata = checkbox.property('transfer_metadata') or {}
        type_key = metadata.get('type_key')
        document_number = metadata.get('document_number')
        if not type_key or not document_number:
            continue
        numbers = selected_data.setdefault(str(type_key), [])
        if document_number not in numbers:
            numbers.append(str(document_number))
    return selected_data

class TransferRecordSelectionDialog(UiMemoryMixin, QDialog):
    """Separate window for reviewing and selecting bills to transfer."""

    def __init__(self, records: list[dict[str, Any]], start_date: str, end_date: str, parent=None):
        super().__init__(parent)
        self.records = records
        self.start_date = start_date
        self.end_date = end_date
        self.selected_data: dict[str, list[str]] = {}
        self._updating_select_all = False
        self.setWindowTitle('Select Records to Transfer')
        self.setMinimumSize(860, 520)
        self.resize(920, 600)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(_transfer_dialog_stylesheet())
        self._build_ui()
        self._load_records()
        self._init_ui_memory()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        title_label = QLabel('Available Records')
        title_label.setObjectName('titleLabel')
        layout.addWidget(title_label)
        hint_label = QLabel(f'Date range: {self.start_date} to {self.end_date}. Double-click a row to select it, or use Select All.')
        hint_label.setObjectName('recordsHintLabel')
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        toolbar = QHBoxLayout()
        self.select_all_checkbox = create_checkbox('Select All', label_color='#f3f4f6', font_size=12)
        self.select_all_checkbox.toggled.connect(self._on_select_all_toggled)
        toolbar.addWidget(self.select_all_checkbox)
        toolbar.addStretch()
        self.selection_count_label = QLabel('0 selected')
        self.selection_count_label.setObjectName('selectionSummaryLabel')
        toolbar.addWidget(self.selection_count_label)
        layout.addLayout(toolbar)
        self.records_table = QTableWidget(0, 6)
        _configure_records_table(self.records_table)
        self.records_table.doubleClicked.connect(self._on_record_table_double_clicked)
        layout.addWidget(self.records_table, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.reject)
        confirm_button = QPushButton('Confirm Selection')
        confirm_button.setObjectName('confirmSelectionButton')
        confirm_button.clicked.connect(self._confirm_selection)
        footer.addWidget(cancel_button)
        footer.addWidget(confirm_button)
        layout.addLayout(footer)

    def _load_records(self) -> None:
        _populate_records_table(self.records_table, self.records)
        for row_index in range(self.records_table.rowCount()):
            checkbox = _row_select_checkbox(self.records_table, row_index)
            if checkbox is not None:
                checkbox.toggled.connect(self._on_row_checkbox_toggled)
        self._update_selection_summary()

    def _set_all_rows_checked(self, checked: bool) -> None:
        self._updating_select_all = True
        for row_index in range(self.records_table.rowCount()):
            checkbox = _row_select_checkbox(self.records_table, row_index)
            if checkbox is not None:
                checkbox.setChecked(checked)
        self._updating_select_all = False
        self._update_selection_summary()

    def _on_select_all_toggled(self, checked: bool) -> None:
        if self._updating_select_all:
            return
        self._set_all_rows_checked(checked)

    def _on_row_checkbox_toggled(self, _checked: bool) -> None:
        if self._updating_select_all:
            return
        total_rows = self.records_table.rowCount()
        checked_rows = 0
        for row_index in range(total_rows):
            checkbox = _row_select_checkbox(self.records_table, row_index)
            if checkbox is not None and checkbox.isChecked():
                checked_rows += 1
        self._updating_select_all = True
        self.select_all_checkbox.setChecked(total_rows > 0 and checked_rows == total_rows)
        self._updating_select_all = False
        self._update_selection_summary()

    def _on_record_table_double_clicked(self, index) -> None:
        if not index.isValid():
            return
        checkbox = _row_select_checkbox(self.records_table, index.row())
        if checkbox is not None:
            checkbox.setChecked(not checkbox.isChecked())

    def _update_selection_summary(self) -> None:
        selected = _collect_checked_records(self.records_table)
        count = sum((len(numbers) for numbers in selected.values()))
        self.selection_count_label.setText(f'{count} selected')

    def _confirm_selection(self) -> None:
        self.selected_data = _collect_checked_records(self.records_table)
        if not self.selected_data:
            QMessageBox.warning(self, 'No Selection', 'Please select at least one record to transfer.')
            return
        self.accept()

    def get_selected_data(self) -> dict[str, list[str]]:
        return self.selected_data

class TransferDataDialog(UiMemoryMixin, QDialog):
    """Dialog for transferring master data and transactions between companies."""

    def __init__(self, master_db_path: str | None=None, active_company_id: int | None=None, parent=None):
        super().__init__(parent)
        self.master_db_path = self._resolve_master_db_path(master_db_path)
        self.active_company_id = active_company_id
        self.companies: list[dict] = []
        self.source_company: dict | None = None
        self.selected_transaction_data: dict[str, list[str]] = {}
        self.setWindowTitle('Inter-Company Data Transfer')
        self._ui_memory_geometry_key = 'inter_company_transfer'
        self.setMinimumSize(880, 520)
        self.resize(920, 580)
        self.setStyleSheet(_transfer_dialog_stylesheet())
        self._build_ui()
        self._load_companies()
        configure_non_modal_window(self, parent)
        self._init_ui_memory()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)
        title_label = QLabel('Inter-Company Data Transfer')
        title_label.setObjectName('titleLabel')
        layout.addWidget(title_label)
        company_row = QHBoxLayout()
        company_row.setSpacing(12)
        source_label = QLabel('Source Company:')
        source_label.setObjectName('fieldLabel')
        source_label.setMinimumWidth(118)
        self.source_company_input = QLineEdit()
        self.source_company_input.setObjectName('sourceCompanyInput')
        self.source_company_input.setReadOnly(True)
        self.source_company_input.setPlaceholderText('No company opened')
        target_label = QLabel('Target Company:')
        target_label.setObjectName('fieldLabel')
        target_label.setMinimumWidth(118)
        self.target_combo = QComboBox()
        company_row.addWidget(source_label)
        company_row.addWidget(self.source_company_input, 1)
        company_row.addSpacing(8)
        company_row.addWidget(target_label)
        company_row.addWidget(self.target_combo, 1)
        layout.addLayout(company_row)
        date_row = QHBoxLayout()
        date_row.setSpacing(12)
        start_label = QLabel('Start Date:')
        start_label.setObjectName('fieldLabel')
        start_label.setMinimumWidth(130)
        self.start_date_edit = QDateEdit()
        configure_qdate_edit(self.start_date_edit)
        self.start_date_edit.setCalendarPopup(True)
        today = QDate.currentDate()
        self.start_date_edit.setDate(QDate(today.year(), today.month(), 1))
        self.start_date_edit.dateChanged.connect(self._clear_selected_records)
        end_label = QLabel('End Date:')
        end_label.setObjectName('fieldLabel')
        self.end_date_edit = QDateEdit()
        configure_qdate_edit(self.end_date_edit)
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(today)
        self.end_date_edit.dateChanged.connect(self._clear_selected_records)
        date_row.addWidget(start_label)
        date_row.addWidget(self.start_date_edit, 1)
        date_row.addWidget(end_label)
        date_row.addWidget(self.end_date_edit, 1)
        layout.addLayout(date_row)
        transfer_group = QGroupBox('Data to Transfer')
        transfer_layout = QVBoxLayout(transfer_group)
        transfer_layout.setSpacing(10)
        self.master_data_checkbox = create_checkbox('Master Data Only (Products & Parties)', label_color='#f3f4f6', font_size=12)
        self.master_data_checkbox.setChecked(False)
        transfer_layout.addWidget(self.master_data_checkbox)
        options_grid = QGridLayout()
        options_grid.setHorizontalSpacing(28)
        options_grid.setVerticalSpacing(10)
        options_grid.setColumnStretch(0, 1)
        options_grid.setColumnStretch(1, 1)
        self.transfer_type_checkboxes: dict[str, CheckBox3D] = {}
        options_by_name = {attribute_name: (type_key, label) for attribute_name, type_key, label in TRANSFER_TYPE_OPTIONS}
        for row_index, (left_name, right_name) in enumerate(TRANSFER_OPTION_GRID_ROWS, start=0):
            if left_name:
                type_key, label = options_by_name[left_name]
                checkbox = create_checkbox(label, label_color='#f3f4f6', font_size=12)
                checkbox.setChecked(False)
                checkbox.toggled.connect(self._clear_selected_records)
                setattr(self, left_name, checkbox)
                self.transfer_type_checkboxes[type_key] = checkbox
                options_grid.addWidget(checkbox, row_index, 0, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if right_name:
                type_key, label = options_by_name[right_name]
                checkbox = create_checkbox(label, label_color='#f3f4f6', font_size=12)
                checkbox.setChecked(False)
                checkbox.toggled.connect(self._clear_selected_records)
                setattr(self, right_name, checkbox)
                self.transfer_type_checkboxes[type_key] = checkbox
                options_grid.addWidget(checkbox, row_index, 1, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        transfer_layout.addLayout(options_grid)
        layout.addWidget(transfer_group)
        self.load_records_button = QPushButton('Load Available Records')
        self.load_records_button.setObjectName('loadRecordsButton')
        self.load_records_button.clicked.connect(self.fetch_records_for_selection)
        layout.addWidget(self.load_records_button)
        self.records_hint_label = QLabel('Opens a separate window to review and select bills for transfer.')
        self.records_hint_label.setObjectName('recordsHintLabel')
        layout.addWidget(self.records_hint_label)
        self.selection_summary_label = QLabel('No bills selected yet.')
        self.selection_summary_label.setObjectName('selectionSummaryLabel')
        layout.addWidget(self.selection_summary_label)
        scroll_area.setWidget(content_widget)
        root_layout.addWidget(scroll_area, 1)
        warning_label = QLabel("Note: Barcode conflicts will be automatically resolved by appending '-SYNC' to the incoming item.")
        warning_label.setObjectName('warningLabel')
        warning_label.setWordWrap(True)
        root_layout.addWidget(warning_label)
        footer = QHBoxLayout()
        footer.addStretch()
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.reject)
        self.transfer_button = QPushButton('Start Transfer')
        self.transfer_button.setObjectName('transferButton')
        self.transfer_button.clicked.connect(self._start_transfer)
        footer.addWidget(cancel_button)
        footer.addWidget(self.transfer_button)
        root_layout.addLayout(footer)

    def _resolve_master_db_path(self, master_db_path: str | None) -> str:
        configured_path = master_db_path or get_default_database_path()
        configured_path = str(configured_path)
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.abspath(os.path.join(BASE_DIR, configured_path))

    def _resolve_company_db_path(self, company: dict) -> str:
        db_path = company.get('db_path') or company.get('database_path') or company.get('company_db_path') or self.master_db_path
        db_path = str(db_path)
        if not os.path.isabs(db_path):
            db_path = os.path.join(BASE_DIR, db_path)
        return os.path.abspath(db_path)

    def _load_companies(self) -> None:
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.companies = []
        self.source_company = None
        self.source_company_input.clear()
        if not os.path.isfile(self.master_db_path):
            QMessageBox.warning(self, 'Registry Not Found', f'Master registry database not found:\n{self.master_db_path}')
            self.transfer_button.setEnabled(False)
            self.target_combo.blockSignals(False)
            return
        result = CompanyLogic(Database(db_path=self.master_db_path)).get_all_companies(
            visibility='normal',
        )
        self.companies = result.get('data') or []
        if not self.companies:
            QMessageBox.information(self, 'No Companies', 'No companies were found in the master registry.')
            self.transfer_button.setEnabled(False)
            self.target_combo.blockSignals(False)
            return
        if self.active_company_id is not None:
            for company in self.companies:
                if company.get('id') == self.active_company_id:
                    self.source_company = company
                    break
        if self.source_company is None:
            QMessageBox.warning(self, 'No Open Company', 'Please open a company before using Inter-Company Transfer.')
            self.transfer_button.setEnabled(False)
            self.target_combo.blockSignals(False)
            return
        source_label = self.source_company.get('business_name') or f"Company {self.source_company.get('id')}"
        self.source_company_input.setText(source_label)
        self._refresh_target_combo()

    def _refresh_target_combo(self) -> None:
        source_id = self.source_company.get('id') if self.source_company else None
        previous_target = self.target_combo.currentData()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        for company in self.companies:
            if company.get('id') == source_id:
                continue
            label = company.get('business_name') or f"Company {company.get('id')}"
            self.target_combo.addItem(label, company)
        if self.target_combo.count() == 0:
            self.transfer_button.setEnabled(False)
            self.target_combo.blockSignals(False)
            return
        self.transfer_button.setEnabled(True)
        restored = False
        if previous_target:
            previous_id = previous_target.get('id')
            for index in range(self.target_combo.count()):
                company = self.target_combo.itemData(index)
                if company and company.get('id') == previous_id:
                    self.target_combo.setCurrentIndex(index)
                    restored = True
                    break
        if not restored:
            self.target_combo.setCurrentIndex(0)
        self.target_combo.blockSignals(False)

    def _clear_selected_records(self) -> None:
        self.selected_transaction_data = {}
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        count = sum((len(numbers) for numbers in self.selected_transaction_data.values()))
        if count == 0:
            self.selection_summary_label.setText('No bills selected yet.')
            return
        self.selection_summary_label.setText(f'{count} bill(s) selected for transfer.')

    def _transaction_type_keys_for_fetch(self) -> list[str]:
        type_keys: list[str] = []
        for type_key, checkbox in self.transfer_type_checkboxes.items():
            if checkbox.isChecked():
                type_keys.append(type_key)
        return type_keys

    def _has_transaction_selection_enabled(self) -> bool:
        return bool(self._transaction_type_keys_for_fetch())

    def fetch_records_for_selection(self) -> None:
        """Open a separate window to load and select bill records."""
        if not self.source_company:
            QMessageBox.warning(self, 'Validation Error', 'No opened company is available as the transfer source.')
            return
        type_keys = self._transaction_type_keys_for_fetch()
        if not type_keys:
            QMessageBox.warning(self, 'Validation Error', 'Select at least one entry type before loading records.')
            return
        start_date = qdate_to_db(self.start_date_edit.date())
        end_date = qdate_to_db(self.end_date_edit.date())
        if self.start_date_edit.date() > self.end_date_edit.date():
            QMessageBox.warning(self, 'Validation Error', 'Start date cannot be after end date.')
            return
        source_db = self._resolve_company_db_path(self.source_company)
        if not os.path.isfile(source_db):
            QMessageBox.warning(self, 'Validation Error', f'Source database not found:\n{source_db}')
            return
        success, message, records = fetch_available_records(source_db, start_date, end_date, type_keys)
        if not success:
            QMessageBox.critical(self, 'Load Failed', message or 'Could not load records.')
            return
        if not records:
            QMessageBox.information(self, 'No Records Found', 'No matching bills were found for the selected filters.')
            return
        picker = TransferRecordSelectionDialog(records, start_date, end_date, self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        self.selected_transaction_data = picker.get_selected_data()
        self._update_selection_summary()

    def _collect_selected_data(self) -> dict[str, object]:
        selected_data: dict[str, object] = {}
        if self.master_data_checkbox.isChecked():
            selected_data['master_data_only'] = True
        for type_key, document_numbers in self.selected_transaction_data.items():
            if document_numbers:
                selected_data[type_key] = list(document_numbers)
        return selected_data

    def _validate_inputs(self) -> tuple[bool, str, str, str]:
        if not self.source_company:
            return (False, 'No opened company is available as the transfer source.', '', '')
        target_company = self.target_combo.currentData()
        if not target_company:
            return (False, 'Please select a target company.', '', '')
        if self.source_company.get('id') == target_company.get('id'):
            return (False, 'Source and target companies must be different.', '', '')
        selected_data = self._collect_selected_data()
        has_master_data = bool(selected_data.get('master_data_only'))
        has_transactions = any((isinstance(value, list) and value for key, value in selected_data.items() if key != 'master_data_only'))
        if not has_master_data and (not has_transactions):
            if self._has_transaction_selection_enabled():
                return (False, 'Load available records and select at least one bill to transfer, or enable Master Data Only.', '', '')
            return (False, 'Select Master Data Only or choose bills to transfer.', '', '')
        if self.start_date_edit.date() > self.end_date_edit.date():
            return (False, 'Start date cannot be after end date.', '', '')
        source_db = self._resolve_company_db_path(self.source_company)
        target_db = self._resolve_company_db_path(target_company)
        if not os.path.isfile(source_db):
            return (False, f'Source database not found:\n{source_db}', '', '')
        if not os.path.isfile(target_db):
            return (False, f'Target database not found:\n{target_db}', '', '')
        if os.path.abspath(source_db) == os.path.abspath(target_db):
            return (False, 'Source and target companies use the same database file. Inter-company transfer requires separate company databases.', '', '')
        return (True, '', source_db, target_db)

    def _set_form_enabled(self, enabled: bool) -> None:
        self.target_combo.setEnabled(enabled)
        self.start_date_edit.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)
        self.master_data_checkbox.setEnabled(enabled)
        for checkbox in self.transfer_type_checkboxes.values():
            checkbox.setEnabled(enabled)
        self.load_records_button.setEnabled(enabled)
        self.transfer_button.setEnabled(enabled)

    def _start_transfer(self) -> None:
        is_valid, error_message, source_db, target_db = self._validate_inputs()
        if not is_valid:
            QMessageBox.warning(self, 'Validation Error', error_message)
            return
        source_name = self.source_company_input.text()
        target_name = self.target_combo.currentText()
        start_date = qdate_to_db(self.start_date_edit.date())
        end_date = qdate_to_db(self.end_date_edit.date())
        selected_data = self._collect_selected_data()
        selected_count = sum((len(value) for key, value in selected_data.items() if key != 'master_data_only' and isinstance(value, list)))
        summary_lines = []
        if selected_data.get('master_data_only'):
            summary_lines.append('- Master data (products and parties)')
        if selected_count:
            summary_lines.append(f'- {selected_count} selected bill(s)')
        selection_summary = '\n'.join(summary_lines) if summary_lines else '- Selected records'
        confirm = QMessageBox.question(self, 'Confirm Data Transfer', f'Transfer selected data from:\n  {source_name}\nto:\n  {target_name}\n\nDate range: {start_date} to {end_date}\n{selection_summary}\n\nDo you want to continue?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self._set_form_enabled(False)
        progress = QProgressDialog('Transferring data between companies. Please wait...', None, 0, 0, self)
        progress.setWindowTitle('Inter-Company Transfer')
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        try:
            engine = DataTransferEngine()
            success, message = engine.transfer_data(source_db, target_db, selected_data)
        finally:
            progress.close()
            self._set_form_enabled(True)
            if self.target_combo.count() == 0:
                self.transfer_button.setEnabled(False)
        if success:
            QMessageBox.information(self, 'Transfer Complete', 'Inter-company data transfer completed successfully.')
            return
        QMessageBox.critical(self, 'Transfer Failed', message or 'The transfer could not be completed.')