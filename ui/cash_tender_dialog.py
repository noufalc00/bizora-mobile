"""
Cash tender dialog for collecting payment against a bill total.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from PySide6.QtCore import QEvent, QLocale, Qt
from PySide6.QtGui import QDoubleValidator, QKeyEvent
from PySide6.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout
from ui import theme
from ui.date_formats import configure_qdate_edit, format_display_date, qdate_to_db, qdate_to_display, db_to_qdate
from ui.ui_memory import UiMemoryMixin

class CashTenderDialog(UiMemoryMixin, QDialog):
    """Application-modal dialog for cash tender and balance calculation."""
    MAX_CASH_AMOUNT = 999999999999.99
    MONEY_QUANTIZE = Decimal('0.01')

    def __init__(self, bill_amount=0, parent=None):
        """
        Initialize the cash tender dialog.

        Args:
            bill_amount: Read-only bill amount due from the customer.
            parent: Optional parent widget for modal ownership.
        """
        super().__init__(parent)
        self.bill_amount = self._parse_amount(bill_amount)
        self.cash_received = Decimal('0.00')
        self.balance_returned = Decimal('0.00')
        self.payment_mode = 'Cash'
        self.setWindowTitle('Cash Tender')
        self.setWindowModality(Qt.ApplicationModal)
        self.setModal(True)
        self.setFixedSize(400, 300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMinimizeButtonHint)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)
        self._setup_ui()
        self._connect_signals()
        self.toggle_payment_fields(self.payment_mode_combo.currentText())
        self._apply_theme()
        self._init_ui_memory()

    def _apply_theme(self) -> None:
        """Apply the active application theme to dialog controls."""
        try:
            self.setStyleSheet(theme.cash_tender_dialog_style())
        except Exception as exc:
            print(f'Cash Tender theme apply error: {exc}')

    def refresh_theme(self, theme_name: str | None = None) -> None:
        """Refresh dialog styling when the global theme changes."""
        if theme_name is not None:
            try:
                from ui.theme_manager import sync_theme
                sync_theme(theme_name)
            except Exception as exc:
                print(f'Cash Tender theme sync error: {exc}')
        self._apply_theme()

    def _setup_ui(self):
        """Build the payment mode and cash tender form."""
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(15)
        heading = QLabel('Cash Tender')
        heading.setObjectName('headingLabel')
        heading.setAlignment(Qt.AlignCenter)
        root_layout.addWidget(heading)
        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setFormAlignment(Qt.AlignTop)
        root_layout.addLayout(form_layout)
        self.payment_mode_combo = QComboBox()
        self.payment_mode_combo.setObjectName('paymentModeCombo')
        self.payment_mode_combo.addItems(['Cash', 'Online', 'Card', 'UPI'])
        self.payment_mode_combo.installEventFilter(self)
        self.payment_mode_combo.setMinimumHeight(36)
        form_layout.addRow(self._create_form_label('Payment Mode'), self.payment_mode_combo)
        self.bill_amount_label = QLabel(self._format_money(self.bill_amount))
        self.bill_amount_label.setObjectName('amountValueLabel')
        self.bill_amount_label.setAlignment(Qt.AlignCenter)
        self.bill_amount_label.setMinimumHeight(38)
        form_layout.addRow(self._create_form_label('Bill Amount'), self.bill_amount_label)
        self.cash_received_input = QLineEdit()
        self.cash_received_input.setObjectName('cashReceivedInput')
        self.cash_received_input.setAlignment(Qt.AlignCenter)
        self.cash_received_input.setPlaceholderText('0.00')
        self.cash_received_input.setValidator(self._create_cash_validator())
        self.cash_received_input.installEventFilter(self)
        self.cash_received_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.cash_received_input.setMinimumHeight(40)
        self.cash_received_label = self._create_form_label('Cash Received')
        form_layout.addRow(self.cash_received_label, self.cash_received_input)
        self.balance_returned_label = QLabel('0.00')
        self.balance_returned_label.setObjectName('balanceReturnedLabel')
        self.balance_returned_label.setAlignment(Qt.AlignCenter)
        self.balance_returned_label.setMinimumHeight(38)
        self.balance_label = self._create_form_label('Balance to Return')
        self.balance_display = self.balance_returned_label
        form_layout.addRow(self.balance_label, self.balance_display)
        instruction = QLabel('Press Enter to accept. Press Escape to cancel.')
        instruction.setObjectName('instructionLabel')
        instruction.setAlignment(Qt.AlignCenter)
        root_layout.addWidget(instruction)
        self.payment_mode_combo.setFocus(Qt.FocusReason.OtherFocusReason)

    def _connect_signals(self):
        """Connect cash input edits to the live balance calculation."""
        self.cash_received_input.textChanged.connect(self._update_balance)
        self.payment_mode_combo.currentTextChanged.connect(self.toggle_payment_fields)

    def _create_cash_validator(self):
        """Create a strict decimal validator for cash received entry."""
        validator = QDoubleValidator(0.0, self.MAX_CASH_AMOUNT, 2, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        validator.setLocale(QLocale(QLocale.Language.English))
        return validator

    def _create_form_label(self, title):
        """
        Create a plain form label without any extra container frame.

        Args:
            title: Caption displayed beside a payment field.
        """
        title_label = QLabel(title)
        title_label.setObjectName('formTitleLabel')
        title_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return title_label

    def _update_balance(self):
        """Recalculate and display cash balance whenever cash received changes."""
        self.payment_mode = self.payment_mode_combo.currentText().strip() or 'Cash'
        if self.payment_mode != 'Cash':
            self.cash_received = self.bill_amount
            self.balance_returned = Decimal('0.00')
            self.balance_display.setText('0.00')
            return
        try:
            self.cash_received = self._parse_amount(self.cash_received_input.text())
            balance = self.cash_received - self.bill_amount
            if balance < Decimal('0.00'):
                balance = Decimal('0.00')
            self.balance_returned = self._round_money(balance)
            self.balance_returned_label.setText(self._format_money(self.balance_returned))
        except Exception:
            self.cash_received = Decimal('0.00')
            self.balance_returned = Decimal('0.00')
            self.balance_returned_label.setText('0.00')

    def toggle_payment_fields(self, mode):
        """
        Show cash fields only for cash payments and sync non-cash values.

        Args:
            mode: Selected payment mode from the payment mode combo box.
        """
        self.payment_mode = str(mode or 'Cash').strip() or 'Cash'
        is_cash = self.payment_mode == 'Cash'
        self.cash_received_label.setVisible(is_cash)
        self.cash_received_input.setVisible(is_cash)
        self.balance_label.setVisible(is_cash)
        self.balance_display.setVisible(is_cash)
        if is_cash:
            self._update_balance()
            return
        self.cash_received = self.bill_amount
        self.balance_returned = Decimal('0.00')
        self.balance_display.setText('0.00')

    def get_values(self):
        """
        Return accepted tender values as plain floats.

        Returns:
            Dictionary containing bill_amount, cash_received, and
            balance_returned values plus payment_mode.
        """
        self.toggle_payment_fields(self.payment_mode_combo.currentText())
        return {'bill_amount': float(self.bill_amount), 'cash_received': float(self.cash_received), 'tendered_amount': float(self.cash_received), 'balance_returned': float(self.balance_returned), 'balance': float(self.balance_returned), 'payment_mode': self.payment_mode}

    def get_data(self):
        """Return accepted tender values including selected payment mode."""
        return self.get_values()

    def accept(self):
        """Accept the dialog after synchronizing the latest entered cash value."""
        self.toggle_payment_fields(self.payment_mode_combo.currentText())
        super().accept()

    def reject(self):
        """Reject the dialog without modifying accepted return values."""
        super().reject()

    def keyPressEvent(self, event: QKeyEvent):
        """Handle Enter and Escape without relying on hidden default buttons."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.reject()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched, event):
        """Capture Enter/Escape from the cash input before it consumes them."""
        payment_mode_combo = getattr(self, 'payment_mode_combo', None)
        cash_received_input = getattr(self, 'cash_received_input', None)
        if watched is payment_mode_combo and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                current_mode = payment_mode_combo.currentText().strip() or 'Cash'
                if current_mode == 'Cash' and cash_received_input is not None and (not cash_received_input.isHidden()):
                    cash_received_input.setFocus(Qt.FocusReason.OtherFocusReason)
                    cash_received_input.selectAll()
                else:
                    self.accept()
                return True
            if event.key() == Qt.Key_Escape:
                self.reject()
                return True
        if watched is cash_received_input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.accept()
                return True
            if event.key() == Qt.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(watched, event)

    @classmethod
    def _parse_amount(cls, value):
        """
        Parse any supported numeric input into a two-decimal Decimal amount.

        Args:
            value: String, float, int, or Decimal amount to normalize.
        """
        try:
            if value is None:
                return Decimal('0.00')
            text_value = str(value).strip()
            if not text_value:
                return Decimal('0.00')
            parsed = Decimal(text_value)
            if parsed < Decimal('0.00'):
                return Decimal('0.00')
            return cls._round_money(parsed)
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0.00')

    @classmethod
    def _round_money(cls, value):
        """
        Round an amount using accounting-style two-decimal quantization.

        Args:
            value: Decimal amount to round to currency precision.
        """
        try:
            return Decimal(value).quantize(cls.MONEY_QUANTIZE, rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError):
            return Decimal('0.00')

    @classmethod
    def _format_money(cls, value):
        """
        Format a numeric value for display with exactly two decimal places.

        Args:
            value: Amount to display in the dialog.
        """
        return f'{cls._parse_amount(value):.2f}'