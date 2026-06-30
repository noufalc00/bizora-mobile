"""
Credit / Debit Note page.
Memo-only entry page with compact PDC-style layout.
"""
from __future__ import annotations
from typing import Any, Dict, Optional
from PySide6.QtCore import QDate, QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QDateEdit, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from config import active_company_manager
from db import Database
from bizora_core.credit_debit_note_logic import CreditDebitNoteLogic
from ui import theme
from ui.checkbox_style import create_radio_button
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin
from ui.entry_field_helpers import install_click_select_all

class CreditDebitNoteNavigationFilter(QObject):
    """Enter moves forward and Esc moves backward for normal form fields."""

    def __init__(self, fields):
        super().__init__()
        self.fields = fields

    def eventFilter(self, obj, event):
        if event.type() != QEvent.KeyPress:
            return False
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if obj in self.fields:
                index = self.fields.index(obj)
                if index < len(self.fields) - 1:
                    self.fields[index + 1].setFocus()
                return True
        if event.key() == Qt.Key_Escape:
            if obj in self.fields:
                index = self.fields.index(obj)
                if index > 0:
                    self.fields[index - 1].setFocus()
                return True
        return False

class CreditDebitNotePage(UiMemoryMixin, QWidget):
    REASON_OPTIONS = [
        'Deficit/Damage on goods purchased',
        'Deficit/Damage on goods sold',
        'Discount on purchases',
        'Discount on sales',
        'Purchase price variation',
        'Purchase return',
        'Sales price variation',
        'Sales return',
    ]

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.logic = CreditDebitNoteLogic(self.db)
        self.company_id: Optional[int] = None
        self.current_note_id: Optional[int] = None
        self.current_party_id: Optional[int] = None
        self._nav_filter = None
        self.load_company()
        self.setup_ui()
        self.setup_navigation()
        self.clear_form()
        self._init_ui_memory()

    def load_company(self):
        active = active_company_manager.get_active_company()
        if active:
            self.company_id = active.get('id')

    def setup_ui(self):
        self.setObjectName('CreditDebitNotePage')
        self.setStyleSheet(self.page_style())
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self.create_header())
        self.form_frame = QFrame()
        self.form_frame.setObjectName('mainFormFrame')
        form = QVBoxLayout(self.form_frame)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)
        form.addLayout(self.create_top_row())
        form.addLayout(self.create_account_row())
        form.addLayout(self.create_reason_row())
        form.addLayout(self.create_bill_row())
        form.addLayout(self.create_document_row())
        form.addLayout(self.create_amount_row())
        form.addLayout(self.create_remarks_row())
        form.addStretch()
        root.addWidget(self.form_frame, 1)
        root.addWidget(self.create_footer())

    def create_header(self):
        frame = QFrame()
        frame.setObjectName('titleFrame')
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 7, 12, 7)
        title = QLabel('CREDIT / DEBIT NOTE')
        title.setObjectName('titleLabel')
        layout.addWidget(title)
        layout.addStretch()
        return frame

    def create_top_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.label_box('Serial No', 92))
        serial_container = QWidget()
        serial_container.setFixedWidth(228)
        serial_layout = QHBoxLayout(serial_container)
        serial_layout.setContentsMargins(0, 0, 0, 0)
        serial_layout.setSpacing(2)
        self.serial_no = QLineEdit()
        self.serial_no.setPlaceholderText('Auto')
        self.serial_no.setReadOnly(True)
        self.serial_no.setFixedWidth(118)
        serial_layout.addWidget(self.serial_no)
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav = QVBoxLayout(nav_container)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(1)
        self.prev_btn = QPushButton('▲')
        self.prev_btn.setStyleSheet(theme.sales_nav_button_style())
        self.prev_btn.setFixedSize(18, 11)
        self.prev_btn.clicked.connect(self.navigate_next)
        nav.addWidget(self.prev_btn)
        self.next_btn = QPushButton('▼')
        self.next_btn.setStyleSheet(theme.sales_nav_button_style())
        self.next_btn.setFixedSize(18, 11)
        self.next_btn.clicked.connect(self.navigate_previous)
        nav.addWidget(self.next_btn)
        serial_layout.addWidget(nav_container)
        self.header_reset_btn = QPushButton('Reset')
        self.header_reset_btn.setStyleSheet(theme.sales_compact_button_style())
        self.header_reset_btn.setFixedWidth(50)
        self.header_reset_btn.clicked.connect(self.clear_form)
        serial_layout.addWidget(self.header_reset_btn)
        row.addWidget(serial_container)
        row.addWidget(self.label_box('Date', 62))
        self.note_date = self.date_edit(136)
        row.addWidget(self.note_date)
        row.addWidget(self.label_box('Note Type', 90))
        self.credit_note_radio = create_radio_button('Credit Note', label_color=theme._theme_colors()['input_text'], font_size=12)
        self.credit_note_radio.setChecked(True)
        self.credit_note_radio.toggled.connect(self.on_note_type_changed)
        self.debit_note_radio = create_radio_button('Debit Note', label_color=theme._theme_colors()['input_text'], font_size=12)
        self.debit_note_radio.toggled.connect(self.on_note_type_changed)
        row.addWidget(self.credit_note_radio)
        row.addWidget(self.debit_note_radio)
        row.addStretch()
        return row

    def create_account_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.label_box('To', 72))
        self.party_type_combo = QComboBox()
        self.party_type_combo.addItems(['Debtor', 'Creditor'])
        self.party_type_combo.setFixedWidth(130)
        self.party_type_combo.currentTextChanged.connect(self.on_party_type_changed)
        row.addWidget(self.party_type_combo)
        row.addWidget(self.label_box('Account', 85))
        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText('Select Account')
        self.account_input.returnPressed.connect(self.show_account_popup)
        install_click_select_all(self.account_input)
        account_box = self.field_with_button(self.account_input, self.show_account_popup, width=450)
        row.addWidget(account_box)
        row.addStretch()
        return row

    def create_reason_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.label_box('Reason', 72))
        self.reason_combo = QComboBox()
        self.reason_combo.addItem('Select Reason', None)
        for reason in self.REASON_OPTIONS:
            self.reason_combo.addItem(reason, reason)
        self.reason_combo.setCurrentIndex(0)
        self.reason_combo.setFixedWidth(330)
        row.addWidget(self.reason_combo)
        row.addWidget(self.label_box('Description', 100))
        self.goods_description = QLineEdit()
        self.goods_description.setPlaceholderText('Description of goods...')
        self.goods_description.setFixedWidth(430)
        row.addWidget(self.goods_description)
        row.addStretch()
        return row

    def create_bill_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.label_box('Quantity', 78))
        self.quantity = QLineEdit()
        self.quantity.setPlaceholderText('0.00')
        self.quantity.setFixedWidth(120)
        row.addWidget(self.quantity)
        row.addWidget(self.label_box('Bill No', 72))
        self.bill_no = QLineEdit()
        self.bill_no.setPlaceholderText('Bill no...')
        self.bill_no.setFixedWidth(190)
        row.addWidget(self.bill_no)
        row.addWidget(self.label_box('Bill Date', 82))
        self.bill_date = self.date_edit(136)
        row.addWidget(self.bill_date)
        row.addStretch()
        return row

    def create_document_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.label_box('Return Date', 100))
        self.return_date = self.date_edit(136)
        row.addWidget(self.return_date)
        row.addWidget(self.label_box('Document Details', 132))
        self.document_details = QLineEdit()
        self.document_details.setPlaceholderText('Document details...')
        self.document_details.setFixedWidth(510)
        row.addWidget(self.document_details)
        row.addStretch()
        return row

    def create_amount_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.label_box('Amount', 72))
        self.amount = QLineEdit()
        self.amount.setPlaceholderText('0.00')
        self.amount.setFixedWidth(140)
        self.amount.textChanged.connect(self.calculate_total)
        row.addWidget(self.amount)
        row.addWidget(self.label_box('Related Tax', 98))
        self.related_tax = QLineEdit()
        self.related_tax.setPlaceholderText('0.00')
        self.related_tax.setFixedWidth(140)
        self.related_tax.textChanged.connect(self.calculate_total)
        row.addWidget(self.related_tax)
        row.addWidget(self.label_box('Total', 68))
        self.total = QLineEdit()
        self.total.setText('0.00')
        self.total.setReadOnly(True)
        self.total.setObjectName('totalField')
        self.total.setFixedWidth(150)
        row.addWidget(self.total)
        row.addStretch()
        return row

    def create_remarks_row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.label_box('Remarks', 82))
        self.remarks = QLineEdit()
        self.remarks.setPlaceholderText('Optional remarks...')
        self.remarks.setFixedWidth(620)
        row.addWidget(self.remarks)
        row.addStretch()
        return row

    def create_footer(self):
        frame = QFrame()
        frame.setObjectName('footerFrame')
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)
        layout.addStretch()
        self.save_btn = self.footer_button('Save', 125, 'save')
        self.save_btn.clicked.connect(self.save_note)
        layout.addWidget(self.save_btn)
        self.remove_btn = self.footer_button('Remove Entry', 150, 'danger')
        self.remove_btn.clicked.connect(self.remove_note)
        layout.addWidget(self.remove_btn)
        self.reset_btn = self.footer_button('Reset All', 130, 'neutral')
        self.reset_btn.clicked.connect(self.clear_form)
        layout.addWidget(self.reset_btn)
        self.exit_btn = self.footer_button('Exit', 100, 'exit')
        self.exit_btn.clicked.connect(self.close_page)
        layout.addWidget(self.exit_btn)
        return frame

    def label_box(self, text: str, width: int) -> QLabel:
        label = QLabel(text)
        label.setFixedWidth(width)
        label.setMinimumHeight(34)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setStyleSheet(theme.accent_field_label_style())
        return label

    def date_edit(self, width: int) -> QDateEdit:
        edit = QDateEdit()
        edit.setCalendarPopup(True)
        edit.setDate(QDate.currentDate())
        edit
        edit.setFixedWidth(width)
        return edit

    def field_with_button(self, field: QLineEdit, callback, width: int) -> QWidget:
        container = QWidget()
        container.setFixedWidth(width)
        container.setStyleSheet('background: transparent; border: none;')
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        field.setFixedHeight(34)
        field.setStyleSheet(theme.entry_picker_field_style())
        layout.addWidget(field)
        button = QPushButton('...')
        button.setFixedSize(40, 34)
        button.setStyleSheet(theme.entry_picker_button_style())
        button.clicked.connect(callback)
        layout.addWidget(button)
        return container

    def footer_button(self, text: str, width: int, kind: str) -> QPushButton:
        from ui import theme
        button = QPushButton(text)
        button.setFixedWidth(width)
        button.setMinimumHeight(40)
        button.setStyleSheet(theme.credit_debit_footer_button_style(kind))
        return button

    def page_style(self) -> str:
        from ui import theme
        from ui.book_report_common import report_compound_entry_page_style
        c = theme._theme_colors()
        return report_compound_entry_page_style() + f"\n            QFrame#titleFrame, QFrame#mainFormFrame, QFrame#footerFrame {{\n                background-color: {c['panel_bg']};\n                border: 1px solid {c['border']};\n                border-radius: 6px;\n            }}\n            QLabel#titleLabel {{\n                color: {c['heading_text']};\n                font-size: 16px;\n                font-weight: bold;\n                background: transparent;\n                border: none;\n            }}\n            QLineEdit#totalField {{\n                background-color: {c['accent_label']};\n                color: {c['input_text']};\n                border: 1px solid {c['button_warning']};\n                font-weight: bold;\n            }}\n        "

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self.setStyleSheet(self.page_style())
        self.prev_btn.setStyleSheet(theme.sales_nav_button_style())
        self.next_btn.setStyleSheet(theme.sales_nav_button_style())
        self.header_reset_btn.setStyleSheet(theme.sales_compact_button_style())
        for button, kind in (
            (self.save_btn, 'save'),
            (self.remove_btn, 'danger'),
            (self.reset_btn, 'neutral'),
            (self.exit_btn, 'exit'),
        ):
            button.setStyleSheet(theme.credit_debit_footer_button_style(kind))

    def setup_navigation(self):
        fields = [self.serial_no, self.note_date, self.party_type_combo, self.account_input, self.reason_combo, self.goods_description, self.quantity, self.bill_no, self.bill_date, self.return_date, self.document_details, self.amount, self.related_tax, self.remarks]
        self._nav_filter = CreditDebitNoteNavigationFilter(fields)
        for field in fields:
            field.installEventFilter(self._nav_filter)
            install_click_select_all(field)

    def on_note_type_changed(self):
        pass

    def on_party_type_changed(self, _text):
        self.account_input.clear()
        self.current_party_id = None

    def show_account_popup(self):
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        party_type = self.party_type_combo.currentText()
        parties = self.logic.get_parties_by_type(self.company_id, party_type)
        if not parties:
            QMessageBox.information(self, 'No Data', f'No {party_type} accounts found.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Select {party_type}')
        dialog.setFixedSize(560, 380)
        dialog.setStyleSheet(self.page_style())
        layout = QVBoxLayout(dialog)
        search_input = QLineEdit()
        search_input.setPlaceholderText('Search account...')
        layout.addWidget(search_input)
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['Name', 'GSTIN', 'Type'])
        table.setRowCount(len(parties))
        apply_read_only_report_table_selection(table)
        for row, party in enumerate(parties):
            table.setItem(row, 0, QTableWidgetItem(str(party.get('name', ''))))
            table.setItem(row, 1, QTableWidgetItem(str(party.get('gstin', ''))))
            table.setItem(row, 2, QTableWidgetItem(str(party.get('party_type', ''))))
        apply_adjustable_table_columns(table)
        layout.addWidget(table)

        def filter_table(text):
            text = text.lower().strip()
            for row in range(table.rowCount()):
                visible = any((table.item(row, col) and text in table.item(row, col).text().lower() for col in range(table.columnCount())))
                table.setRowHidden(row, not visible)

        def accept_current():
            if table.currentRow() >= 0:
                dialog.accept()
        search_input.textChanged.connect(filter_table)
        table.itemDoubleClicked.connect(lambda *_: accept_current())
        button_row = QHBoxLayout()
        button_row.addStretch()
        select_btn = self.footer_button('Select', 100, 'primary')
        select_btn.clicked.connect(accept_current)
        cancel_btn = self.footer_button('Cancel', 100, 'neutral')
        cancel_btn.clicked.connect(dialog.reject)
        button_row.addWidget(select_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)
        if dialog.exec() == QDialog.Accepted:
            row = table.currentRow()
            if row >= 0:
                self.account_input.setText(table.item(row, 0).text())
                self.current_party_id = parties[row].get('id')

    def calculate_total(self):
        amount = self.to_float(self.amount.text())
        tax = self.to_float(self.related_tax.text())
        self.total.setText(f'{amount + tax:.2f}')

    def collect_data(self) -> Dict[str, Any]:
        return {'company_id': self.company_id, 'serial_no': self.serial_no.text().strip(), 'note_type': 'Credit Note' if self.credit_note_radio.isChecked() else 'Debit Note', 'note_date': qdate_to_db(self.note_date.date()), 'party_type': self.party_type_combo.currentText(), 'party_id': self.current_party_id, 'party_name': self.account_input.text().strip(), 'reason': '' if self.reason_combo.currentData() is None else self.reason_combo.currentText(), 'goods_description': self.goods_description.text().strip(), 'quantity': self.quantity.text().strip(), 'related_bill_no': self.bill_no.text().strip(), 'related_bill_date': qdate_to_db(self.bill_date.date()), 'return_date': qdate_to_db(self.return_date.date()), 'return_document_details': self.document_details.text().strip(), 'amount': self.amount.text().strip(), 'related_tax': self.related_tax.text().strip(), 'remarks': self.remarks.text().strip()}

    def save_note(self):
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        if self.current_note_id:
            self.update_note()
            return
        if not self.current_party_id:
            QMessageBox.warning(self, 'Error', 'Please select an account.')
            return
        try:
            serial = self.logic.create_note(self.collect_data())
            QMessageBox.information(self, 'Success', f'Note saved: {serial}')
            self.clear_form()
        except Exception as exc:
            QMessageBox.critical(self, 'Error', f'Failed to save note: {exc}')

    def update_note(self):
        if not self.current_note_id:
            QMessageBox.warning(self, 'Error', 'No note selected for update.')
            return
        if not self.current_party_id:
            QMessageBox.warning(self, 'Error', 'Please select an account.')
            return
        try:
            self.logic.update_note(self.current_note_id, self.collect_data())
            QMessageBox.information(self, 'Success', 'Note updated successfully.')
            self.clear_form()
        except Exception as exc:
            QMessageBox.critical(self, 'Error', f'Failed to update note: {exc}')

    def remove_note(self):
        if not self.current_note_id:
            QMessageBox.warning(self, 'Error', 'No note selected for removal.')
            return
        reply = QMessageBox.question(self, 'Confirm', 'Remove this note?', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                self.logic.delete_note(self.current_note_id)
                QMessageBox.information(self, 'Success', 'Note removed successfully.')
                self.clear_form()
            except Exception as exc:
                QMessageBox.critical(self, 'Error', f'Failed to remove note: {exc}')

    def navigate_previous(self):
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        note_type = 'Credit Note' if self.credit_note_radio.isChecked() else 'Debit Note'
        if self.current_note_id is None:
            ph = self.db._get_placeholder()
            rows = self.db.execute_query(f'\n                SELECT id FROM credit_debit_notes\n                WHERE company_id={ph} AND note_type={ph}\n                ORDER BY id DESC LIMIT 1\n                ', (self.company_id, note_type))
            if rows:
                self.load_note_to_form(rows[0]['id'])
            else:
                QMessageBox.information(self, 'Info', f'No {note_type} records found.')
            return
        note = self.logic.get_previous_note(self.company_id, self.current_note_id, note_type)
        if note:
            self.load_note_to_form(note['id'])
        else:
            QMessageBox.information(self, 'Info', f'No previous {note_type} record.')

    def navigate_next(self):
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        note_type = 'Credit Note' if self.credit_note_radio.isChecked() else 'Debit Note'
        if self.current_note_id is None:
            ph = self.db._get_placeholder()
            rows = self.db.execute_query(f'\n                SELECT id FROM credit_debit_notes\n                WHERE company_id={ph} AND note_type={ph}\n                ORDER BY id ASC LIMIT 1\n                ', (self.company_id, note_type))
            if rows:
                self.load_note_to_form(rows[0]['id'])
            else:
                QMessageBox.information(self, 'Info', f'No {note_type} records found.')
            return
        note = self.logic.get_next_note(self.company_id, self.current_note_id, note_type)
        if note:
            self.load_note_to_form(note['id'])
        else:
            QMessageBox.information(self, 'Info', f'No next {note_type} record.')

    def load_note_to_form(self, note_id: int):
        note = self.logic.get_note_by_id(note_id)
        if not note:
            return
        self.current_note_id = note_id
        self.save_btn.setText('Update')
        self.serial_no.setText(str(note.get('serial_no') or ''))
        self.note_date.setDate(self.qdate_from_string(note.get('note_date')))
        if note.get('note_type') == 'Debit Note':
            self.debit_note_radio.setChecked(True)
        else:
            self.credit_note_radio.setChecked(True)
        self.party_type_combo.setCurrentText(str(note.get('party_type') or 'Debtor'))
        self.account_input.setText(str(note.get('party_name') or ''))
        self.current_party_id = note.get('party_id')
        reason_text = str(note.get('reason') or '')
        reason_index = self.reason_combo.findText(reason_text)
        self.reason_combo.setCurrentIndex(reason_index if reason_index >= 0 else 0)
        self.goods_description.setText(str(note.get('goods_description') or ''))
        self.quantity.setText(self.clean_number(note.get('quantity')))
        self.bill_no.setText(str(note.get('related_bill_no') or ''))
        self.bill_date.setDate(self.qdate_from_string(note.get('related_bill_date')))
        self.return_date.setDate(self.qdate_from_string(note.get('return_date')))
        self.document_details.setText(str(note.get('return_document_details') or ''))
        self.amount.setText(self.clean_number(note.get('amount')))
        self.related_tax.setText(self.clean_number(note.get('related_tax')))
        self.total.setText(self.clean_number(note.get('total')))
        self.remarks.setText(str(note.get('remarks') or ''))

    def clear_form(self):
        self.current_note_id = None
        self.current_party_id = None
        self.save_btn.setText('Save')
        self.serial_no.clear()
        self.serial_no.setPlaceholderText('Auto')
        self.note_date.setDate(QDate.currentDate())
        self.credit_note_radio.setChecked(True)
        self.party_type_combo.setCurrentIndex(0)
        self.account_input.clear()
        self.reason_combo.setCurrentIndex(0)
        self.goods_description.clear()
        self.quantity.clear()
        self.bill_no.clear()
        self.bill_date.setDate(QDate.currentDate())
        self.return_date.setDate(QDate.currentDate())
        self.document_details.clear()
        self.amount.clear()
        self.related_tax.clear()
        self.total.setText('0.00')
        self.remarks.clear()

    def close_page(self):
        self.window().close()

    @staticmethod
    def to_float(value: Any) -> float:
        try:
            if value is None or value == '':
                return 0.0
            return float(str(value).replace(',', ''))
        except Exception:
            return 0.0

    @staticmethod
    def clean_number(value: Any) -> str:
        try:
            return f'{float(value or 0):.2f}'
        except Exception:
            return '0.00'

    @staticmethod
    def qdate_from_string(value: Any) -> QDate:
        if not value:
            return QDate.currentDate()
        date = QDate.fromString(str(value), 'yyyy-MM-dd')
        return date if date.isValid() else QDate.currentDate()