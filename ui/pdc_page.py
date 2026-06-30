"""
PDC (Post Dated Cheque) Page widget.
"""
from PySide6.QtWidgets import *
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor
from config import active_company_manager
from db import Database
from bizora_core.pdc_logic import PDCLogic
from ui import theme
from ui.book_report_common import (
    compact_combo_style,
    compact_date_style,
    compact_input_style,
    compact_label_style,
    compact_primary_button_style,
    compact_topbar_frame_style,
    report_accent_label_chip_style,
    report_compound_entry_page_style,
)
from ui.voucher_common import AccountComboBox
from ui.table_header_utils import apply_adjustable_table_columns, apply_read_only_report_table_selection
from ui.date_formats import configure_qdate_edit, format_display_date, prepare_report_date_edit, qdate_to_db, qdate_to_display
from ui.ui_memory import UiMemoryMixin

class PDCPage(UiMemoryMixin, QWidget):

    def __init__(self, db=None):
        super().__init__()
        self.db = db or Database()
        self.pdc_logic = PDCLogic(self.db)
        self.company_id = None
        self.current_pdc_id = None
        self.current_tab = 'receipt'
        self.parties_data = []
        self.bank_accounts_data = []
        self.general_accounts_data = []
        self.receipt_party_id = None
        self.receipt_bank_account_id = None
        self.issue_party_id = None
        self.issue_bank_account_id = None
        self.current_pdc_type = None
        self.setup_ui()
        self.load_company()
        self.load_parties()
        self.load_bank_accounts()
        self.load_general_accounts()
        self.clear_form()
        self.check_due_pdc_alerts()
        self._init_ui_memory()

    def load_company(self):
        active = active_company_manager.get_active_company()
        if active:
            self.company_id = active.get('id')

    def load_parties(self):
        """Load party accounts used by the PDC account dropdowns."""
        if not self.company_id:
            return
        debtors = self.pdc_logic.get_parties_by_type(self.company_id, 'Debitor')
        creditors = self.pdc_logic.get_parties_by_type(self.company_id, 'Creditor')
        combined = []
        seen = set()
        for party in debtors + creditors:
            pid = party.get('id')
            if pid not in seen:
                combined.append(party)
                seen.add(pid)
        if not combined and hasattr(self.pdc_logic, 'get_all_parties'):
            combined = self.pdc_logic.get_all_parties(self.company_id)
        self.parties_data = combined
        self._refresh_account_combos()

    def load_bank_accounts(self):
        """Load bank master accounts and refresh searchable bank dropdowns."""
        if not self.company_id:
            return
        self.bank_accounts_data = self.pdc_logic.get_bank_accounts(self.company_id)
        self._refresh_bank_combos()
        self._refresh_account_combos()

    def load_general_accounts(self):
        """Load general ledger accounts used by the PDC account dropdowns."""
        if not self.company_id:
            return
        self.general_accounts_data = self.pdc_logic.get_general_accounts(self.company_id)
        self._refresh_account_combos()

    def setup_ui(self):
        self.setStyleSheet(report_compound_entry_page_style())
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)
        header_frame = QFrame()
        header_frame.setStyleSheet(self._sales_header_strip_style())
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.setSpacing(0)
        title_label = QLabel('POST DATED CHEQUE')
        title_label.setStyleSheet(self._sales_page_title_style())
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addWidget(header_frame)
        self.alert_label = QLabel()
        self.alert_label.setStyleSheet(f'color: {theme.semantic_warning_hex()}; font-size: 11px; padding: 4px;')
        self.alert_label.setVisible(False)
        layout.addWidget(self.alert_label)
        self.tab_widget = QTabWidget()
        self.receipt_tab = self.create_receipt_tab()
        self.issue_tab = self.create_issue_tab()
        self.register_tab = self.create_register_tab()
        self.tab_widget.addTab(self.receipt_tab, 'PDC Receipt')
        self.tab_widget.addTab(self.issue_tab, 'PDC Issue')
        self.tab_widget.addTab(self.register_tab, 'PDC Register')
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tab_widget)

    def _pdc_label(self, text, width=90):
        label = QLabel(text)
        label.setFixedWidth(width)
        label.setMinimumHeight(34)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setStyleSheet(report_accent_label_chip_style('padding-left: 6px;'))
        return label

    def _footer_button(self, text, width=120, color=None):
        button = QPushButton(text)
        button.setFixedWidth(width)
        button.setMinimumHeight(38)
        colors = theme._theme_colors()
        bg = color or colors['button_primary']
        button.setStyleSheet(f"\n            QPushButton {{\n                background-color: {bg};\n                color: white;\n                border: none;\n                border-radius: 5px;\n                font-size: 12px;\n                font-weight: bold;\n                padding: 8px 12px;\n            }}\n            QPushButton:hover {{ background-color: {colors['focus_border']}; }}\n        ")
        return button

    def _sales_header_strip_style(self):
        """Return the Sales Entry page-header strip stylesheet."""
        return theme.entry_section_frame_style()

    def _sales_page_title_style(self):
        """Return the Sales Entry page-title stylesheet."""
        return theme.entry_page_title_label_style()

    def _sales_command_strip_style(self):
        """Return the Sales Entry command-strip stylesheet."""
        return theme.entry_command_strip_style()

    def _sales_micro_label_style(self):
        """Return the Sales Entry compact top-bar label stylesheet."""
        return theme.sales_micro_label_style()

    def _sales_compact_input_style(self):
        """Return the Sales Entry compact top-bar input stylesheet."""
        return theme.sales_compact_input_style()

    def _sales_nav_button_style(self):
        """Return the Sales Entry compact navigation button stylesheet."""
        return theme.sales_nav_button_style()

    def _create_nav_button_stack(self, next_callback, previous_callback):
        """Create Sales Entry-style vertical Next/Previous navigation buttons."""
        nav_container = QWidget()
        nav_container.setFixedWidth(18)
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setSpacing(1)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        next_btn = QPushButton('▲')
        next_btn.setStyleSheet(self._sales_nav_button_style())
        next_btn.setFixedSize(18, 11)
        next_btn.clicked.connect(next_callback)
        nav_layout.addWidget(next_btn)
        previous_btn = QPushButton('▼')
        previous_btn.setStyleSheet(self._sales_nav_button_style())
        previous_btn.setFixedSize(18, 11)
        previous_btn.clicked.connect(previous_callback)
        nav_layout.addWidget(previous_btn)
        return nav_container

    def _create_header_reset_button(self, tab_type: str) -> QPushButton:
        """Create the compact Reset button shown beside voucher/PDC number fields."""
        reset_btn = QPushButton('Reset')
        reset_btn.setStyleSheet(theme.sales_compact_button_style())
        reset_btn.setFixedWidth(50)
        reset_btn.clicked.connect(lambda: self.clear_form(tab_type))
        return reset_btn

    def _update_action_buttons(self):
        """Refresh Save/Update button text for the currently loaded PDC state."""
        receipt_text = 'Update' if self.current_pdc_id and self.current_pdc_type == 'RECEIPT' else 'Save'
        issue_text = 'Update' if self.current_pdc_id and self.current_pdc_type == 'ISSUE' else 'Save'
        if hasattr(self, 'receipt_save_btn'):
            self.receipt_save_btn.setText(receipt_text)
        if hasattr(self, 'issue_save_btn'):
            self.issue_save_btn.setText(issue_text)

    def _save_or_update_pdc(self, transaction_type):
        """Route the primary action button to save or update based on loaded state."""
        if self.current_pdc_id and self.current_pdc_type == transaction_type:
            self.update_pdc(transaction_type)
        else:
            self.save_pdc(transaction_type)

    def _quick_create_button(self):
        """Create the raised 3D bank quick-create button."""
        button = QPushButton('+')
        button.setObjectName('salesIconButton')
        button.setFlat(False)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(28, 28)
        button.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        button.setToolTip('Create New Bank Account')
        button.setStyleSheet(theme.sales_modern_3d_icon_button_style())
        return button

    def _combo_items_with_blank(self, accounts):
        """Return account rows with a blank first option for optional selection."""
        return [{'id': None, 'account_name': ''}] + accounts

    def _normalise_party_accounts(self, parties):
        """Convert party rows to AccountComboBox-compatible account rows."""
        return [{'id': party.get('id'), 'account_name': party.get('name', '')} for party in parties]

    def _account_items_for_type(self, acc_type):
        """Return account rows for the selected PDC account type."""
        if acc_type == 'Sundry Debtors':
            parties = [party for party in self.parties_data if str(party.get('party_type', '')).lower() in ('debitor', 'debtor', 'sundry debtors', 'both')]
            return self._normalise_party_accounts(parties)
        if acc_type == 'Sundry Creditors':
            parties = [party for party in self.parties_data if str(party.get('party_type', '')).lower() in ('creditor', 'sundry creditors', 'both')]
            return self._normalise_party_accounts(parties)
        if acc_type == 'Bank':
            return self.bank_accounts_data
        return self.general_accounts_data

    def _load_account_combo(self, combo, accounts, selected_id=None):
        """Load a searchable account combo and optionally select an account ID."""
        if not combo:
            return
        combo.blockSignals(True)
        combo.load_accounts(self._combo_items_with_blank(accounts))
        if selected_id is not None:
            self._set_combo_account_id(combo, selected_id)
        combo.blockSignals(False)

    def _set_combo_account_id(self, combo, account_id):
        """Select a combo row by stored account ID."""
        combo.set_account_id(account_id)

    def _selected_combo_id(self, combo):
        """Return the selected account ID, guarding against free text."""
        if not combo:
            return None
        return combo.get_account_id()

    def _refresh_account_combos(self):
        """Refresh Receipt/Issue account dropdowns when source data changes."""
        if hasattr(self, 'receipt_party_input'):
            self._load_account_combo(self.receipt_party_input, self._account_items_for_type(self.receipt_acc_type.currentText()), self.receipt_party_id)
        if hasattr(self, 'issue_party_input'):
            self._load_account_combo(self.issue_party_input, self._account_items_for_type(self.issue_acc_type.currentText()), self.issue_party_id)

    def _refresh_bank_combos(self):
        """Refresh Receipt/Issue bank dropdowns when bank masters change."""
        if hasattr(self, 'receipt_bank_input'):
            self._load_account_combo(self.receipt_bank_input, self.bank_accounts_data, self.receipt_bank_account_id)
        if hasattr(self, 'issue_bank_input'):
            self._load_account_combo(self.issue_bank_input, self.bank_accounts_data, self.issue_bank_account_id)

    def _sync_selected_account_ids(self):
        """Synchronize stored IDs from searchable combo selections."""
        self.receipt_party_id = self._selected_combo_id(self.receipt_party_input)
        self.receipt_bank_account_id = self._selected_combo_id(self.receipt_bank_input)
        self.issue_party_id = self._selected_combo_id(self.issue_party_input)
        self.issue_bank_account_id = self._selected_combo_id(self.issue_bank_input)

    def _create_receipt_footer(self):
        frame = QFrame()
        frame.setStyleSheet(theme.section_panel_frame_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        layout.addStretch()
        self.receipt_save_btn = self._footer_button('Save', 110, theme.semantic_positive_hex())
        self.receipt_save_btn.clicked.connect(lambda: self._save_or_update_pdc('RECEIPT'))
        layout.addWidget(self.receipt_save_btn)
        reset_btn = self._footer_button('Reset', 110, theme.semantic_neutral_hex())
        reset_btn.clicked.connect(lambda: self.clear_form('receipt'))
        layout.addWidget(reset_btn)
        clear_btn = self._footer_button('Mark Cleared', 135, theme._theme_colors()['button_primary'])
        clear_btn.clicked.connect(lambda: self.mark_cleared('RECEIPT'))
        layout.addWidget(clear_btn)
        bounce_btn = self._footer_button('Mark Bounced', 140, theme._theme_colors()['border'])
        bounce_btn.clicked.connect(lambda: self.mark_bounced('RECEIPT'))
        layout.addWidget(bounce_btn)
        cancel_btn = self._footer_button('Cancel', 110, theme.semantic_negative_hex())
        cancel_btn.clicked.connect(lambda: self.mark_cancelled('RECEIPT'))
        layout.addWidget(cancel_btn)
        exit_btn = self._footer_button('Exit', 90, theme._theme_colors()['border'])
        exit_btn.clicked.connect(self.close)
        layout.addWidget(exit_btn)
        return frame

    def _create_issue_footer(self):
        frame = QFrame()
        frame.setStyleSheet(theme.section_panel_frame_style())
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        layout.addStretch()
        self.issue_save_btn = self._footer_button('Save', 110, theme.semantic_positive_hex())
        self.issue_save_btn.clicked.connect(lambda: self._save_or_update_pdc('ISSUE'))
        layout.addWidget(self.issue_save_btn)
        reset_btn = self._footer_button('Reset', 110, theme.semantic_neutral_hex())
        reset_btn.clicked.connect(lambda: self.clear_form('issue'))
        layout.addWidget(reset_btn)
        clear_btn = self._footer_button('Mark Cleared', 135, theme._theme_colors()['button_primary'])
        clear_btn.clicked.connect(lambda: self.mark_cleared('ISSUE'))
        layout.addWidget(clear_btn)
        bounce_btn = self._footer_button('Mark Bounced', 140, theme._theme_colors()['border'])
        bounce_btn.clicked.connect(lambda: self.mark_bounced('ISSUE'))
        layout.addWidget(bounce_btn)
        cancel_btn = self._footer_button('Cancel', 110, theme.semantic_negative_hex())
        cancel_btn.clicked.connect(lambda: self.mark_cancelled('ISSUE'))
        layout.addWidget(cancel_btn)
        exit_btn = self._footer_button('Exit', 90, theme._theme_colors()['border'])
        exit_btn.clicked.connect(self.close)
        layout.addWidget(exit_btn)
        return frame

    def create_receipt_tab(self):
        """Create a clean PDC Receipt form with compact rows and footer actions."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        form_frame = QFrame()
        form_frame.setStyleSheet(theme.section_panel_frame_style())
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(12, 12, 12, 12)
        command_frame = QFrame()
        command_frame.setStyleSheet(self._sales_command_strip_style())
        row1 = QHBoxLayout(command_frame)
        row1.setSpacing(8)
        row1.setContentsMargins(6, 4, 6, 4)
        row1.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        pdc_label = QLabel('PDC No')
        pdc_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(pdc_label)
        self.receipt_pdc_no = QLineEdit()
        self.receipt_pdc_no.setPlaceholderText('Auto')
        self.receipt_pdc_no.setReadOnly(True)
        self.receipt_pdc_no.setStyleSheet(self._sales_compact_input_style())
        self.receipt_pdc_no.setFixedWidth(70)
        row1.addWidget(self.receipt_pdc_no)
        row1.addWidget(self._create_nav_button_stack(self.navigate_next_receipt, self.navigate_previous_receipt))
        row1.addWidget(self._create_header_reset_button('receipt'))
        received_date_label = QLabel('Received Date')
        received_date_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(received_date_label)
        self.receipt_recv_date = QDateEdit()
        configure_qdate_edit(self.receipt_recv_date)
        self.receipt_recv_date.setCalendarPopup(True)
        self.receipt_recv_date.setDate(QDate.currentDate())
        self.receipt_recv_date.setStyleSheet(self._sales_compact_input_style())
        self.receipt_recv_date.setFixedWidth(110)
        row1.addWidget(self.receipt_recv_date)
        cheque_date_label = QLabel('Cheque Date')
        cheque_date_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(cheque_date_label)
        self.receipt_cheque_date = QDateEdit()
        configure_qdate_edit(self.receipt_cheque_date)
        self.receipt_cheque_date.setCalendarPopup(True)
        self.receipt_cheque_date.setDate(QDate.currentDate())
        self.receipt_cheque_date.setStyleSheet(self._sales_compact_input_style())
        self.receipt_cheque_date.setFixedWidth(110)
        row1.addWidget(self.receipt_cheque_date)
        status_label = QLabel('Status')
        status_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(status_label)
        self.receipt_status = QLabel('PENDING')
        self.receipt_status.setStyleSheet(f'color: {theme.semantic_positive_hex()}; font-weight: bold; font-size: 11px; background: transparent; border: none;')
        self.receipt_status.setFixedWidth(90)
        row1.addWidget(self.receipt_status)
        row1.addStretch()
        form_layout.addWidget(command_frame)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._pdc_label('Account Type', 105))
        self.receipt_acc_type = QComboBox()
        self.receipt_acc_type.addItems(['General', 'Sundry Debtors', 'Sundry Creditors', 'Bank'])
        self.receipt_acc_type.setFixedWidth(150)
        self.receipt_acc_type.currentTextChanged.connect(self.on_receipt_acc_type_changed)
        row2.addWidget(self.receipt_acc_type)
        self.receipt_party_label = self._pdc_label('Account', 70)
        row2.addWidget(self.receipt_party_label)
        self.receipt_party_input = AccountComboBox()
        self.receipt_party_input.setPlaceholderText('Select account...')
        self.receipt_party_input.setMinimumWidth(260)
        self.receipt_party_input.currentIndexChanged.connect(lambda _index: setattr(self, 'receipt_party_id', self._selected_combo_id(self.receipt_party_input)))
        row2.addWidget(self.receipt_party_input, 1)
        row2.addWidget(self._pdc_label('Deposit Bank', 105))
        self.receipt_bank_input = AccountComboBox()
        self.receipt_bank_input.setPlaceholderText('Select deposit bank...')
        self.receipt_bank_input.setMinimumWidth(260)
        self.receipt_bank_input.currentIndexChanged.connect(lambda _index: setattr(self, 'receipt_bank_account_id', self._selected_combo_id(self.receipt_bank_input)))
        row2.addWidget(self.receipt_bank_input, 1)
        bank_btn = self._quick_create_button()
        bank_btn.clicked.connect(lambda: self.open_bank_account_quick_create('receipt'))
        row2.addWidget(bank_btn)
        form_layout.addLayout(row2)
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(self._pdc_label('Cheque No', 90))
        self.receipt_cheque_no = QLineEdit()
        self.receipt_cheque_no.setPlaceholderText('Enter cheque number')
        self.receipt_cheque_no.setFixedWidth(250)
        row3.addWidget(self.receipt_cheque_no)
        row3.addWidget(self._pdc_label('Cheque Bank', 105))
        self.receipt_cheque_bank = QLineEdit()
        self.receipt_cheque_bank.setPlaceholderText('Bank name')
        self.receipt_cheque_bank.setFixedWidth(260)
        row3.addWidget(self.receipt_cheque_bank)
        row3.addWidget(self._pdc_label('Branch', 70))
        self.receipt_branch = QLineEdit()
        self.receipt_branch.setPlaceholderText('Branch name')
        self.receipt_branch.setMinimumWidth(220)
        row3.addWidget(self.receipt_branch, 1)
        form_layout.addLayout(row3)
        row4 = QHBoxLayout()
        row4.setSpacing(8)
        row4.addWidget(self._pdc_label('Amount', 90))
        self.receipt_amount = QLineEdit()
        self.receipt_amount.setPlaceholderText('0.00')
        self.receipt_amount.setFixedWidth(250)
        row4.addWidget(self.receipt_amount)
        row4.addWidget(self._pdc_label('Narration', 90))
        self.receipt_narration = QLineEdit()
        self.receipt_narration.setPlaceholderText('Optional')
        self.receipt_narration.setMinimumWidth(420)
        row4.addWidget(self.receipt_narration, 1)
        form_layout.addLayout(row4)
        layout.addWidget(form_frame)
        layout.addStretch()
        footer = self._create_receipt_footer()
        layout.addWidget(footer)
        return tab

    def create_issue_tab(self):
        """Create a clean PDC Issue form with compact rows and footer actions."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        form_frame = QFrame()
        form_frame.setStyleSheet(theme.section_panel_frame_style())
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(10)
        form_layout.setContentsMargins(12, 12, 12, 12)
        command_frame = QFrame()
        command_frame.setStyleSheet(self._sales_command_strip_style())
        row1 = QHBoxLayout(command_frame)
        row1.setSpacing(8)
        row1.setContentsMargins(6, 4, 6, 4)
        row1.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        pdc_label = QLabel('PDC No')
        pdc_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(pdc_label)
        self.issue_pdc_no = QLineEdit()
        self.issue_pdc_no.setPlaceholderText('Auto')
        self.issue_pdc_no.setReadOnly(True)
        self.issue_pdc_no.setStyleSheet(self._sales_compact_input_style())
        self.issue_pdc_no.setFixedWidth(70)
        row1.addWidget(self.issue_pdc_no)
        row1.addWidget(self._create_nav_button_stack(self.navigate_next_issue, self.navigate_previous_issue))
        row1.addWidget(self._create_header_reset_button('issue'))
        issued_date_label = QLabel('Issued Date')
        issued_date_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(issued_date_label)
        self.issue_issued_date = QDateEdit()
        configure_qdate_edit(self.issue_issued_date)
        self.issue_issued_date.setCalendarPopup(True)
        self.issue_issued_date.setDate(QDate.currentDate())
        self.issue_issued_date.setStyleSheet(self._sales_compact_input_style())
        self.issue_issued_date.setFixedWidth(110)
        row1.addWidget(self.issue_issued_date)
        cheque_date_label = QLabel('Cheque Date')
        cheque_date_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(cheque_date_label)
        self.issue_cheque_date = QDateEdit()
        configure_qdate_edit(self.issue_cheque_date)
        self.issue_cheque_date.setCalendarPopup(True)
        self.issue_cheque_date.setDate(QDate.currentDate())
        self.issue_cheque_date.setStyleSheet(self._sales_compact_input_style())
        self.issue_cheque_date.setFixedWidth(110)
        row1.addWidget(self.issue_cheque_date)
        status_label = QLabel('Status')
        status_label.setStyleSheet(self._sales_micro_label_style())
        row1.addWidget(status_label)
        self.issue_status = QLabel('PENDING')
        self.issue_status.setStyleSheet(f'color: {theme.semantic_positive_hex()}; font-weight: bold; font-size: 11px; background: transparent; border: none;')
        self.issue_status.setFixedWidth(90)
        row1.addWidget(self.issue_status)
        row1.addStretch()
        form_layout.addWidget(command_frame)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._pdc_label('Account Type', 105))
        self.issue_acc_type = QComboBox()
        self.issue_acc_type.addItems(['General', 'Sundry Debtors', 'Sundry Creditors', 'Bank'])
        self.issue_acc_type.setFixedWidth(150)
        self.issue_acc_type.currentTextChanged.connect(self.on_issue_acc_type_changed)
        row2.addWidget(self.issue_acc_type)
        self.issue_party_label = self._pdc_label('Account', 70)
        row2.addWidget(self.issue_party_label)
        self.issue_party_input = AccountComboBox()
        self.issue_party_input.setPlaceholderText('Select account...')
        self.issue_party_input.setMinimumWidth(260)
        self.issue_party_input.currentIndexChanged.connect(lambda _index: setattr(self, 'issue_party_id', self._selected_combo_id(self.issue_party_input)))
        row2.addWidget(self.issue_party_input, 1)
        row2.addWidget(self._pdc_label('Paid From Bank', 115))
        self.issue_bank_input = AccountComboBox()
        self.issue_bank_input.setPlaceholderText('Select paid from bank...')
        self.issue_bank_input.setMinimumWidth(260)
        self.issue_bank_input.currentIndexChanged.connect(lambda _index: setattr(self, 'issue_bank_account_id', self._selected_combo_id(self.issue_bank_input)))
        row2.addWidget(self.issue_bank_input, 1)
        bank_btn = self._quick_create_button()
        bank_btn.clicked.connect(lambda: self.open_bank_account_quick_create('issue'))
        row2.addWidget(bank_btn)
        form_layout.addLayout(row2)
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(self._pdc_label('Cheque No', 90))
        self.issue_cheque_no = QLineEdit()
        self.issue_cheque_no.setPlaceholderText('Enter cheque number')
        self.issue_cheque_no.setFixedWidth(250)
        row3.addWidget(self.issue_cheque_no)
        row3.addWidget(self._pdc_label('Cheque Bank', 105))
        self.issue_cheque_bank = QLineEdit()
        self.issue_cheque_bank.setPlaceholderText('Bank name')
        self.issue_cheque_bank.setFixedWidth(260)
        row3.addWidget(self.issue_cheque_bank)
        row3.addWidget(self._pdc_label('Branch', 70))
        self.issue_branch = QLineEdit()
        self.issue_branch.setPlaceholderText('Branch name')
        self.issue_branch.setMinimumWidth(220)
        row3.addWidget(self.issue_branch, 1)
        form_layout.addLayout(row3)
        row4 = QHBoxLayout()
        row4.setSpacing(8)
        row4.addWidget(self._pdc_label('Amount', 90))
        self.issue_amount = QLineEdit()
        self.issue_amount.setPlaceholderText('0.00')
        self.issue_amount.setFixedWidth(250)
        row4.addWidget(self.issue_amount)
        row4.addWidget(self._pdc_label('Narration', 90))
        self.issue_narration = QLineEdit()
        self.issue_narration.setPlaceholderText('Optional')
        self.issue_narration.setMinimumWidth(420)
        row4.addWidget(self.issue_narration, 1)
        form_layout.addLayout(row4)
        layout.addWidget(form_frame)
        layout.addStretch()
        footer = self._create_issue_footer()
        layout.addWidget(footer)
        return tab

    def _register_filter_column(self, label_text: str, widget: QWidget) -> QVBoxLayout:
        """Stack a compact label above a register filter control."""
        column = QVBoxLayout()
        column.setSpacing(4)
        column.setContentsMargins(0, 0, 0, 0)
        label = QLabel(label_text)
        label.setStyleSheet(compact_label_style())
        column.addWidget(label)
        column.addWidget(widget)
        return column

    def create_register_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)
        filter_frame = QFrame()
        filter_frame.setStyleSheet(compact_topbar_frame_style())
        filter_layout = QVBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(8)
        self.reg_from_date = QDateEdit()
        self.reg_from_date.setDate(QDate.currentDate().addMonths(-1))
        prepare_report_date_edit(self.reg_from_date, style_sheet=compact_date_style())
        self.reg_to_date = QDateEdit()
        self.reg_to_date.setDate(QDate.currentDate())
        prepare_report_date_edit(self.reg_to_date, style_sheet=compact_date_style())
        self.reg_type = QComboBox()
        self.reg_type.addItems(['All', 'RECEIPT', 'ISSUE'])
        self.reg_type.setStyleSheet(compact_combo_style())
        self.reg_type.setFixedWidth(105)
        self.reg_status = QComboBox()
        self.reg_status.addItems(['All', 'PENDING', 'CLEARED', 'BOUNCED', 'CANCELLED'])
        self.reg_status.setStyleSheet(compact_combo_style())
        self.reg_status.setFixedWidth(115)
        self.reg_search = QLineEdit()
        self.reg_search.setPlaceholderText('Cheque no, party, bank...')
        self.reg_search.setStyleSheet(compact_input_style())
        self.reg_search.setMinimumWidth(220)
        refresh_btn = QPushButton('Refresh')
        refresh_btn.setStyleSheet(compact_primary_button_style())
        refresh_btn.setFixedHeight(28)
        refresh_btn.setMinimumWidth(72)
        refresh_btn.clicked.connect(self.refresh_register)
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.setContentsMargins(0, 0, 0, 0)
        for label_text, widget in (
            ('Maturity From', self.reg_from_date),
            ('Maturity To', self.reg_to_date),
            ('Type', self.reg_type),
            ('Status', self.reg_status),
        ):
            top_row.addLayout(self._register_filter_column(label_text, widget))
        top_row.addStretch()
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)
        bottom_row.setContentsMargins(0, 0, 0, 0)
        search_column = self._register_filter_column('Search', self.reg_search)
        bottom_row.addLayout(search_column, 1)
        bottom_row.addWidget(refresh_btn, 0, Qt.AlignBottom)
        filter_layout.addLayout(top_row)
        filter_layout.addLayout(bottom_row)
        layout.addWidget(filter_frame)
        self.reg_table = QTableWidget()
        self.reg_table.setColumnCount(14)
        self.reg_table.setHorizontalHeaderLabels(['PDC No', 'Type', 'Account Type', 'Party/Account', 'Bank', 'Date', 'Cheque Date', 'Cheque No', 'Cheque Bank', 'Amount', 'Status', 'Linked Voucher', 'Narration', ''])
        self.reg_table.itemDoubleClicked.connect(self.on_register_double_click)
        layout.addWidget(self.reg_table)
        return tab

    def on_tab_changed(self, index):
        if index == 2:
            self.refresh_register()

    def check_due_pdc_alerts(self):
        if not self.company_id:
            return
        current_date = QDate.currentDate().toString('yyyy-MM-dd')
        due_pdcs = self.pdc_logic.get_due_pdc_alerts(self.company_id, current_date)
        if due_pdcs:
            self.alert_label.setText(f'You have {len(due_pdcs)} PDC(s) ready for clearance.')
            self.alert_label.setVisible(True)

    def on_receipt_acc_type_changed(self, text):
        if text == 'Sundry Debtors':
            self.receipt_party_label.setText('Received From')
        elif text == 'Sundry Creditors':
            self.receipt_party_label.setText('Received From')
        elif text == 'Bank':
            self.receipt_party_label.setText('Bank Account')
        else:
            self.receipt_party_label.setText('Account')
        self.receipt_party_id = None
        self._load_account_combo(self.receipt_party_input, self._account_items_for_type(text))

    def on_issue_acc_type_changed(self, text):
        if text == 'Sundry Debtors':
            self.issue_party_label.setText('Issued To')
        elif text == 'Sundry Creditors':
            self.issue_party_label.setText('Issued To')
        elif text == 'Bank':
            self.issue_party_label.setText('Bank Account')
        else:
            self.issue_party_label.setText('Account')
        self.issue_party_id = None
        self._load_account_combo(self.issue_party_input, self._account_items_for_type(text))

    def open_bank_account_quick_create(self, target):
        """Open the existing Bank Account entry UI and select the new bank account."""
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        try:
            from ui.bank_accounts import BankAccountWidget
            existing_ids = {account.get('id') for account in self.bank_accounts_data}
            dialog = QDialog(self)
            dialog.setWindowTitle('Create New Bank Account')
            dialog.setModal(True)
            dialog.resize(760, 520)
            layout = QVBoxLayout(dialog)
            bank_widget = BankAccountWidget(self.db)
            bank_widget.show_entry_page(clear_form=True)
            layout.addWidget(bank_widget)
            close_btn = QPushButton('Close')
            close_btn.setStyleSheet(theme.sales_compact_button_style())
            close_btn.clicked.connect(dialog.reject)
            layout.addWidget(close_btn, alignment=Qt.AlignRight)
            created_bank_id = {'value': None}
            original_save = bank_widget.save

            def save_and_select_new_bank():
                original_save()
                refreshed_accounts = self.pdc_logic.get_bank_accounts(self.company_id)
                new_accounts = [account for account in refreshed_accounts if account.get('id') not in existing_ids]
                if new_accounts:
                    newest_account = max(new_accounts, key=lambda account: account.get('id') or 0)
                    created_bank_id['value'] = newest_account.get('id')
                    dialog.accept()
            try:
                bank_widget.save_btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            bank_widget.save_btn.clicked.connect(save_and_select_new_bank)
            if dialog.exec() == QDialog.Accepted and created_bank_id['value'] is not None:
                self.load_bank_accounts()
                if target == 'receipt':
                    self.receipt_bank_account_id = created_bank_id['value']
                    self._set_combo_account_id(self.receipt_bank_input, created_bank_id['value'])
                else:
                    self.issue_bank_account_id = created_bank_id['value']
                    self._set_combo_account_id(self.issue_bank_input, created_bank_id['value'])
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to open bank account creation: {str(e)}')

    def show_receipt_party_popup(self):
        acc_type = self.receipt_acc_type.currentText()
        items = []
        columns = []
        headers = []
        if acc_type == 'Sundry Debtors':
            items = [p for p in self.parties_data if str(p.get('party_type', '')).lower() in ('debitor', 'debtor', 'sundry debtors', 'both')]
            columns = ['name', 'gstin']
            headers = ['Name', 'GSTIN']
        elif acc_type == 'Sundry Creditors':
            items = [p for p in self.parties_data if str(p.get('party_type', '')).lower() in ('creditor', 'sundry creditors', 'both')]
            columns = ['name', 'gstin']
            headers = ['Name', 'GSTIN']
        elif acc_type == 'General':
            items = self.general_accounts_data
            columns = ['account_name', 'account_type']
            headers = ['Account Name', 'Type']
        elif acc_type == 'Bank':
            items = self.bank_accounts_data
            columns = ['account_name', 'bank_name']
            headers = ['Account Name', 'Bank Name']
        if not items:
            QMessageBox.information(self, 'No Data', f'No {acc_type} accounts found for active company. Please confirm the correct company is open and party master has Debtor/Creditor records.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Select {acc_type}')
        dialog.setFixedSize(500, 350)
        layout = QVBoxLayout(dialog)
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type to filter...')
        layout.addWidget(search_input)
        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(items))
        apply_read_only_report_table_selection(table)
        for i, item in enumerate(items):
            for j, col in enumerate(columns):
                table.setItem(i, j, QTableWidgetItem(str(item.get(col, ''))))
        layout.addWidget(table)

        def filter_table(text):
            for i in range(table.rowCount()):
                match = any((text.lower() in table.item(i, j).text().lower() for j in range(table.columnCount())))
                table.setRowHidden(i, not match)
        search_input.textChanged.connect(filter_table)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton('Select')
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        if dialog.exec() == QDialog.Accepted:
            row = table.currentRow()
            if row >= 0:
                self.receipt_party_input.setCurrentText(table.item(row, 0).text())
                self.receipt_party_id = items[row].get('id')

    def show_receipt_bank_popup(self):
        if not self.bank_accounts_data:
            QMessageBox.information(self, 'No Data', 'No bank accounts found.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Select Bank Account')
        dialog.setFixedSize(500, 350)
        layout = QVBoxLayout(dialog)
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type to filter...')
        layout.addWidget(search_input)
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['Account Name', 'Bank Name', 'Account Number'])
        table.setRowCount(len(self.bank_accounts_data))
        apply_read_only_report_table_selection(table)
        for i, item in enumerate(self.bank_accounts_data):
            table.setItem(i, 0, QTableWidgetItem(item.get('account_name', '')))
            table.setItem(i, 1, QTableWidgetItem(item.get('bank_name', '')))
            table.setItem(i, 2, QTableWidgetItem(item.get('account_number', '')))
        layout.addWidget(table)

        def filter_table(text):
            for i in range(table.rowCount()):
                match = any((text.lower() in table.item(i, j).text().lower() for j in range(table.columnCount())))
                table.setRowHidden(i, not match)
        search_input.textChanged.connect(filter_table)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton('Select')
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        if dialog.exec() == QDialog.Accepted:
            row = table.currentRow()
            if row >= 0:
                self.receipt_bank_input.setCurrentText(table.item(row, 0).text())
                self.receipt_bank_account_id = self.bank_accounts_data[row].get('id')

    def show_issue_party_popup(self):
        acc_type = self.issue_acc_type.currentText()
        items = []
        columns = []
        headers = []
        if acc_type == 'Sundry Debtors':
            items = [p for p in self.parties_data if str(p.get('party_type', '')).lower() in ('debitor', 'debtor', 'sundry debtors', 'both')]
            columns = ['name', 'gstin']
            headers = ['Name', 'GSTIN']
        elif acc_type == 'Sundry Creditors':
            items = [p for p in self.parties_data if str(p.get('party_type', '')).lower() in ('creditor', 'sundry creditors', 'both')]
            columns = ['name', 'gstin']
            headers = ['Name', 'GSTIN']
        elif acc_type == 'General':
            items = self.general_accounts_data
            columns = ['account_name', 'account_type']
            headers = ['Account Name', 'Type']
        elif acc_type == 'Bank':
            items = self.bank_accounts_data
            columns = ['account_name', 'bank_name']
            headers = ['Account Name', 'Bank Name']
        if not items:
            QMessageBox.information(self, 'No Data', f'No {acc_type} accounts found for active company. Please confirm the correct company is open and party master has Debtor/Creditor records.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Select {acc_type}')
        dialog.setFixedSize(500, 350)
        layout = QVBoxLayout(dialog)
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type to filter...')
        layout.addWidget(search_input)
        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(items))
        apply_read_only_report_table_selection(table)
        for i, item in enumerate(items):
            for j, col in enumerate(columns):
                table.setItem(i, j, QTableWidgetItem(str(item.get(col, ''))))
        layout.addWidget(table)

        def filter_table(text):
            for i in range(table.rowCount()):
                match = any((text.lower() in table.item(i, j).text().lower() for j in range(table.columnCount())))
                table.setRowHidden(i, not match)
        search_input.textChanged.connect(filter_table)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton('Select')
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        if dialog.exec() == QDialog.Accepted:
            row = table.currentRow()
            if row >= 0:
                self.issue_party_input.setCurrentText(table.item(row, 0).text())
                self.issue_party_id = items[row].get('id')

    def show_issue_bank_popup(self):
        if not self.bank_accounts_data:
            QMessageBox.information(self, 'No Data', 'No bank accounts found.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Select Bank Account')
        dialog.setFixedSize(500, 350)
        layout = QVBoxLayout(dialog)
        search_input = QLineEdit()
        search_input.setPlaceholderText('Type to filter...')
        layout.addWidget(search_input)
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(['Account Name', 'Bank Name', 'Account Number'])
        table.setRowCount(len(self.bank_accounts_data))
        apply_read_only_report_table_selection(table)
        for i, item in enumerate(self.bank_accounts_data):
            table.setItem(i, 0, QTableWidgetItem(item.get('account_name', '')))
            table.setItem(i, 1, QTableWidgetItem(item.get('bank_name', '')))
            table.setItem(i, 2, QTableWidgetItem(item.get('account_number', '')))
        layout.addWidget(table)

        def filter_table(text):
            for i in range(table.rowCount()):
                match = any((text.lower() in table.item(i, j).text().lower() for j in range(table.columnCount())))
                table.setRowHidden(i, not match)
        search_input.textChanged.connect(filter_table)
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton('Select')
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        if dialog.exec() == QDialog.Accepted:
            row = table.currentRow()
            if row >= 0:
                self.issue_bank_input.setCurrentText(table.item(row, 0).text())
                self.issue_bank_account_id = self.bank_accounts_data[row].get('id')

    def save_pdc(self, transaction_type):
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        try:
            self._sync_selected_account_ids()
            if transaction_type == 'RECEIPT':
                data = {'company_id': self.company_id, 'transaction_type': 'RECEIPT', 'account_type': self.receipt_acc_type.currentText(), 'received_issued_date': qdate_to_db(self.receipt_recv_date.date()), 'cheque_date': qdate_to_db(self.receipt_cheque_date.date()), 'cheque_number': self.receipt_cheque_no.text(), 'cheque_bank_name': self.receipt_cheque_bank.text(), 'branch_name': self.receipt_branch.text(), 'amount': self.receipt_amount.text(), 'narration': self.receipt_narration.text(), 'status': 'PENDING'}
                if self.receipt_party_id:
                    data['party_id'] = self.receipt_party_id
                    data['account_name'] = self.receipt_party_input.currentText()
                if self.receipt_bank_account_id:
                    data['bank_account_id'] = self.receipt_bank_account_id
                    data['bank_name'] = self.receipt_bank_input.currentText()
            else:
                data = {'company_id': self.company_id, 'transaction_type': 'ISSUE', 'account_type': self.issue_acc_type.currentText(), 'received_issued_date': qdate_to_db(self.issue_issued_date.date()), 'cheque_date': qdate_to_db(self.issue_cheque_date.date()), 'cheque_number': self.issue_cheque_no.text(), 'cheque_bank_name': self.issue_cheque_bank.text(), 'branch_name': self.issue_branch.text(), 'amount': self.issue_amount.text(), 'narration': self.issue_narration.text(), 'status': 'PENDING'}
                if self.issue_party_id:
                    data['party_id'] = self.issue_party_id
                    data['account_name'] = self.issue_party_input.currentText()
                if self.issue_bank_account_id:
                    data['bank_account_id'] = self.issue_bank_account_id
                    data['bank_name'] = self.issue_bank_input.currentText()
            pdc_id = self.pdc_logic.create_pdc(data)
            QMessageBox.information(self, 'Success', f'PDC saved with ID: {pdc_id}')
            self.clear_form(transaction_type.lower())
            self.check_due_pdc_alerts()
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    def update_pdc(self, transaction_type):
        if not self.current_pdc_id:
            QMessageBox.warning(self, 'Error', 'No PDC selected for update.')
            return
        try:
            self._sync_selected_account_ids()
            if transaction_type == 'RECEIPT':
                data = {'company_id': self.company_id, 'transaction_type': 'RECEIPT', 'account_type': self.receipt_acc_type.currentText(), 'received_issued_date': qdate_to_db(self.receipt_recv_date.date()), 'cheque_date': qdate_to_db(self.receipt_cheque_date.date()), 'cheque_number': self.receipt_cheque_no.text(), 'cheque_bank_name': self.receipt_cheque_bank.text(), 'branch_name': self.receipt_branch.text(), 'amount': self.receipt_amount.text(), 'narration': self.receipt_narration.text()}
                if self.receipt_party_id:
                    data['party_id'] = self.receipt_party_id
                    data['account_name'] = self.receipt_party_input.currentText()
                if self.receipt_bank_account_id:
                    data['bank_account_id'] = self.receipt_bank_account_id
                    data['bank_name'] = self.receipt_bank_input.currentText()
            else:
                data = {'company_id': self.company_id, 'transaction_type': 'ISSUE', 'account_type': self.issue_acc_type.currentText(), 'received_issued_date': qdate_to_db(self.issue_issued_date.date()), 'cheque_date': qdate_to_db(self.issue_cheque_date.date()), 'cheque_number': self.issue_cheque_no.text(), 'cheque_bank_name': self.issue_cheque_bank.text(), 'branch_name': self.issue_branch.text(), 'amount': self.issue_amount.text(), 'narration': self.issue_narration.text()}
                if self.issue_party_id:
                    data['party_id'] = self.issue_party_id
                    data['account_name'] = self.issue_party_input.currentText()
                if self.issue_bank_account_id:
                    data['bank_account_id'] = self.issue_bank_account_id
                    data['bank_name'] = self.issue_bank_input.currentText()
            self.pdc_logic.update_pdc(self.current_pdc_id, data)
            QMessageBox.information(self, 'Success', 'PDC updated successfully.')
            self.clear_form(transaction_type.lower())
        except Exception as e:
            QMessageBox.critical(self, 'Error', str(e))

    def mark_cleared(self, transaction_type):
        if not self.current_pdc_id:
            QMessageBox.warning(self, 'Error', 'No PDC selected.')
            return
        self._sync_selected_account_ids()
        bank_account_id = self.receipt_bank_account_id if transaction_type == 'RECEIPT' else self.issue_bank_account_id
        if not bank_account_id:
            QMessageBox.warning(self, 'Error', 'Select a bank account before clearing this PDC.')
            return
        reply = QMessageBox.question(self, 'Confirm', 'Mark this PDC as CLEARED and post ledger entries?', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                cleared_date = QDate.currentDate().toString('yyyy-MM-dd')
                self.pdc_logic.mark_cleared(self.current_pdc_id, bank_account_id, cleared_date)
                QMessageBox.information(self, 'Success', 'PDC marked as CLEARED and posted to ledger.')
                self.clear_form(transaction_type.lower())
                self.refresh_register()
            except Exception as e:
                QMessageBox.critical(self, 'Error', str(e))

    def mark_bounced(self, transaction_type):
        if not self.current_pdc_id:
            QMessageBox.warning(self, 'Error', 'No PDC selected.')
            return
        reason, ok = QInputDialog.getText(self, 'Reason', 'Enter bounce reason (optional):')
        if ok:
            try:
                bounced_date = QDate.currentDate().toString('yyyy-MM-dd')
                self.pdc_logic.mark_bounced(self.current_pdc_id, bounced_date, reason)
                QMessageBox.information(self, 'Success', 'PDC marked as BOUNCED.')
                self.clear_form(transaction_type.lower())
                self.refresh_register()
            except Exception as e:
                QMessageBox.critical(self, 'Error', str(e))

    def mark_cancelled(self, transaction_type):
        if not self.current_pdc_id:
            QMessageBox.warning(self, 'Error', 'No PDC selected.')
            return
        reply = QMessageBox.question(self, 'Confirm', 'Mark this PDC as CANCELLED?', QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            reason, ok = QInputDialog.getText(self, 'Reason', 'Enter cancellation reason (optional):')
            if ok:
                try:
                    cancelled_date = QDate.currentDate().toString('yyyy-MM-dd')
                    self.pdc_logic.mark_cancelled(self.current_pdc_id, cancelled_date, reason)
                    QMessageBox.information(self, 'Success', 'PDC marked as CANCELLED.')
                    self.clear_form(transaction_type.lower())
                    self.refresh_register()
                except Exception as e:
                    QMessageBox.critical(self, 'Error', str(e))

    def clear_form(self, tab='receipt'):
        self.current_pdc_id = None
        self.current_pdc_type = None
        if tab == 'receipt':
            self.receipt_pdc_no.setText('')
            self.receipt_pdc_no.setPlaceholderText('Auto')
            self.receipt_recv_date.setDate(QDate.currentDate())
            self.receipt_cheque_date.setDate(QDate.currentDate())
            self.receipt_acc_type.setCurrentIndex(0)
            self.receipt_party_id = None
            self._load_account_combo(self.receipt_party_input, self._account_items_for_type(self.receipt_acc_type.currentText()))
            self.receipt_bank_account_id = None
            self._load_account_combo(self.receipt_bank_input, self.bank_accounts_data)
            self.receipt_cheque_no.setText('')
            self.receipt_cheque_bank.setText('')
            self.receipt_branch.setText('')
            self.receipt_amount.setText('')
            self.receipt_narration.setText('')
            self.receipt_status.setText('PENDING')
        elif tab == 'issue':
            self.issue_pdc_no.setText('')
            self.issue_pdc_no.setPlaceholderText('Auto')
            self.issue_issued_date.setDate(QDate.currentDate())
            self.issue_cheque_date.setDate(QDate.currentDate())
            self.issue_acc_type.setCurrentIndex(0)
            self.issue_party_id = None
            self._load_account_combo(self.issue_party_input, self._account_items_for_type(self.issue_acc_type.currentText()))
            self.issue_bank_account_id = None
            self._load_account_combo(self.issue_bank_input, self.bank_accounts_data)
            self.issue_cheque_no.setText('')
            self.issue_cheque_bank.setText('')
            self.issue_branch.setText('')
            self.issue_amount.setText('')
            self.issue_narration.setText('')
            self.issue_status.setText('PENDING')
        self._update_action_buttons()

    def refresh_register(self):
        if not self.company_id:
            return
        filters = {'from_date': qdate_to_db(self.reg_from_date.date()), 'to_date': qdate_to_db(self.reg_to_date.date()), 'transaction_type': self.reg_type.currentText(), 'status': self.reg_status.currentText(), 'search': self.reg_search.text()}
        pdcs = self.pdc_logic.list_pdc(self.company_id, filters)
        self.reg_table.setRowCount(len(pdcs))
        for i, pdc in enumerate(pdcs):
            self.reg_table.setItem(i, 0, QTableWidgetItem(str(pdc.get('id', ''))))
            self.reg_table.setItem(i, 1, QTableWidgetItem(pdc.get('transaction_type', '')))
            self.reg_table.setItem(i, 2, QTableWidgetItem(pdc.get('account_type', '')))
            self.reg_table.setItem(i, 3, QTableWidgetItem(pdc.get('account_name', pdc.get('party_name', ''))))
            self.reg_table.setItem(i, 4, QTableWidgetItem(pdc.get('bank_name', pdc.get('bank_account_name', ''))))
            self.reg_table.setItem(i, 5, QTableWidgetItem(format_display_date(pdc.get('received_issued_date', ''))))
            self.reg_table.setItem(i, 6, QTableWidgetItem(format_display_date(pdc.get('cheque_date', ''))))
            self.reg_table.setItem(i, 7, QTableWidgetItem(pdc.get('cheque_number', '')))
            self.reg_table.setItem(i, 8, QTableWidgetItem(pdc.get('cheque_bank_name', '')))
            self.reg_table.setItem(i, 9, QTableWidgetItem(str(pdc.get('amount', ''))))
            status_item = QTableWidgetItem(pdc.get('status', ''))
            if pdc.get('status') == 'CLEARED':
                status_item.setForeground(QColor(theme.semantic_positive_hex()))
            elif pdc.get('status') == 'BOUNCED':
                status_item.setForeground(QColor(theme.semantic_negative_hex()))
            elif pdc.get('status') == 'CANCELLED':
                status_item.setForeground(QColor(theme.semantic_neutral_hex()))
            self.reg_table.setItem(i, 10, status_item)
            self.reg_table.setItem(i, 11, QTableWidgetItem(str(pdc.get('linked_voucher_id', ''))))
            self.reg_table.setItem(i, 12, QTableWidgetItem(pdc.get('narration', '')[:30] if pdc.get('narration') else ''))
        apply_adjustable_table_columns(self.reg_table)

    def on_register_double_click(self, item):
        row = item.row()
        pdc_id = int(self.reg_table.item(row, 0).text())
        self.load_pdc_to_form(pdc_id)

    def load_pdc_to_form(self, pdc_id):
        pdc = self.pdc_logic.get_pdc_by_id(pdc_id)
        if not pdc:
            return
        self.current_pdc_id = pdc_id
        transaction_type = pdc.get('transaction_type')
        self.current_pdc_type = transaction_type
        if transaction_type == 'RECEIPT':
            self.tab_widget.setCurrentIndex(0)
            self.receipt_pdc_no.setText(str(pdc_id))
            self.receipt_recv_date.setDate(QDate.fromString(pdc.get('received_issued_date'), 'yyyy-MM-dd'))
            self.receipt_cheque_date.setDate(QDate.fromString(pdc.get('cheque_date'), 'yyyy-MM-dd'))
            self.receipt_acc_type.setCurrentText(pdc.get('account_type', 'General'))
            self.receipt_party_id = pdc.get('party_id')
            self._load_account_combo(self.receipt_party_input, self._account_items_for_type(self.receipt_acc_type.currentText()), self.receipt_party_id)
            self.receipt_bank_account_id = pdc.get('bank_account_id')
            self._load_account_combo(self.receipt_bank_input, self.bank_accounts_data, self.receipt_bank_account_id)
            self.receipt_cheque_no.setText(pdc.get('cheque_number', ''))
            self.receipt_cheque_bank.setText(pdc.get('cheque_bank_name', ''))
            self.receipt_branch.setText(pdc.get('branch_name', ''))
            self.receipt_amount.setText(str(pdc.get('amount', '')))
            self.receipt_narration.setText(pdc.get('narration', ''))
            self.receipt_status.setText(pdc.get('status', 'PENDING'))
        else:
            self.tab_widget.setCurrentIndex(1)
            self.issue_pdc_no.setText(str(pdc_id))
            self.issue_issued_date.setDate(QDate.fromString(pdc.get('received_issued_date'), 'yyyy-MM-dd'))
            self.issue_cheque_date.setDate(QDate.fromString(pdc.get('cheque_date'), 'yyyy-MM-dd'))
            self.issue_acc_type.setCurrentText(pdc.get('account_type', 'General'))
            self.issue_party_id = pdc.get('party_id')
            self._load_account_combo(self.issue_party_input, self._account_items_for_type(self.issue_acc_type.currentText()), self.issue_party_id)
            self.issue_bank_account_id = pdc.get('bank_account_id')
            self._load_account_combo(self.issue_bank_input, self.bank_accounts_data, self.issue_bank_account_id)
            self.issue_cheque_no.setText(pdc.get('cheque_number', ''))
            self.issue_cheque_bank.setText(pdc.get('cheque_bank_name', ''))
            self.issue_branch.setText(pdc.get('branch_name', ''))
            self.issue_amount.setText(str(pdc.get('amount', '')))
            self.issue_narration.setText(pdc.get('narration', ''))
            self.issue_status.setText(pdc.get('status', 'PENDING'))
        self._update_action_buttons()

    def load_pdc_for_edit(self, pdc_id: int, tab_index: int=None):
        """Load PDC entry for editing from PDC Book double-click."""
        print(f'[DEBUG] Loading PDC for edit: ID={pdc_id}, Tab={tab_index}')
        if tab_index is not None:
            self.tab_widget.setCurrentIndex(tab_index)
        self.load_pdc_to_form(pdc_id)

    def navigate_previous_receipt(self):
        """Navigate to previous PDC Receipt record."""
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        current_id = self.current_pdc_id
        if current_id is None:
            ph = self.db._get_placeholder()
            query = f'\n                SELECT id FROM pdc_register\n                WHERE company_id = {ph} AND transaction_type = {ph}\n                ORDER BY id DESC LIMIT 1\n            '
            result = self.db.execute_query(query, (self.company_id, 'RECEIPT'))
            if result:
                self.load_pdc_to_form(result[0]['id'])
            else:
                QMessageBox.information(self, 'Info', 'No PDC Receipt records found.')
            return
        previous = self.pdc_logic.get_previous_pdc(self.company_id, current_id, 'RECEIPT')
        if previous:
            self.load_pdc_to_form(previous['id'])
        else:
            QMessageBox.information(self, 'Info', 'No previous PDC Receipt record.')

    def navigate_next_receipt(self):
        """Navigate to next PDC Receipt record."""
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        current_id = self.current_pdc_id
        if current_id is None:
            ph = self.db._get_placeholder()
            query = f'\n                SELECT id FROM pdc_register\n                WHERE company_id = {ph} AND transaction_type = {ph}\n                ORDER BY id ASC LIMIT 1\n            '
            result = self.db.execute_query(query, (self.company_id, 'RECEIPT'))
            if result:
                self.load_pdc_to_form(result[0]['id'])
            else:
                QMessageBox.information(self, 'Info', 'No PDC Receipt records found.')
            return
        next_pdc = self.pdc_logic.get_next_pdc(self.company_id, current_id, 'RECEIPT')
        if next_pdc:
            self.load_pdc_to_form(next_pdc['id'])
        else:
            QMessageBox.information(self, 'Info', 'No next PDC Receipt record.')

    def navigate_previous_issue(self):
        """Navigate to previous PDC Issue record."""
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        current_id = self.current_pdc_id
        if current_id is None:
            ph = self.db._get_placeholder()
            query = f'\n                SELECT id FROM pdc_register\n                WHERE company_id = {ph} AND transaction_type = {ph}\n                ORDER BY id DESC LIMIT 1\n            '
            result = self.db.execute_query(query, (self.company_id, 'ISSUE'))
            if result:
                self.load_pdc_to_form(result[0]['id'])
            else:
                QMessageBox.information(self, 'Info', 'No PDC Issue records found.')
            return
        previous = self.pdc_logic.get_previous_pdc(self.company_id, current_id, 'ISSUE')
        if previous:
            self.load_pdc_to_form(previous['id'])
        else:
            QMessageBox.information(self, 'Info', 'No previous PDC Issue record.')

    def navigate_next_issue(self):
        """Navigate to next PDC Issue record."""
        if not self.company_id:
            QMessageBox.warning(self, 'Error', 'No company selected.')
            return
        current_id = self.current_pdc_id
        if current_id is None:
            ph = self.db._get_placeholder()
            query = f'\n                SELECT id FROM pdc_register\n                WHERE company_id = {ph} AND transaction_type = {ph}\n                ORDER BY id ASC LIMIT 1\n            '
            result = self.db.execute_query(query, (self.company_id, 'ISSUE'))
            if result:
                self.load_pdc_to_form(result[0]['id'])
            else:
                QMessageBox.information(self, 'Info', 'No PDC Issue records found.')
            return
        next_pdc = self.pdc_logic.get_next_pdc(self.company_id, current_id, 'ISSUE')
        if next_pdc:
            self.load_pdc_to_form(next_pdc['id'])
        else:
            QMessageBox.information(self, 'Info', 'No next PDC Issue record.')

    def close(self):
        self.window().close()