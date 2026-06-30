"""
Product and Creditor popup logic for Purchase Entry widget.
Contains ProductPopupDelegate, CreditorPopupDelegate, and popup display formatting.
"""

from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QCompleter, QListView, QStyle
from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex, QSize, QTimer
from PySide6.QtGui import QPainter, QColor, QStandardItemModel, QStandardItem


from config import active_company_manager
from ui.party_display import party_display_name
from ui import theme


class NonInsertingCompleter(QCompleter):
    """A completer that shows a popup but does NOT auto-insert/set the editor text
    when the user selects an item. This prevents returnPressed from firing with the
    completed text and causing double-add.
    """

    def pathFromIndex(self, index):
        """Return empty string so completer never writes to the editor on selection."""
        return ""

    def splitPath(self, path):
        """Return the typed path so filtering still works normally."""
        return [path]

# Constants for high-volume product search optimization
POPUP_PRELOAD_THRESHOLD = 5000
MAX_POPUP_RESULTS = 100
MIN_POPUP_CHARS = 2


class ProductPopupDelegate(QStyledItemDelegate):
    """Custom delegate for product popup to display formatted text with barcode and stock."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        """Override paint to display formatted text with barcode and purchase rate."""
        # Get product data from UserRole
        product = index.data(Qt.UserRole)
        if not product:
            super().paint(painter, option, index)
            return

        # Format display text: [Barcode] Product Name - Rate: X
        barcode = product.get('barcode', '')
        name = product['name']
        # Use purchase_rate first, fallback to sale_price → sales_rate → 0
        rate = product.get('purchase_rate', 0)
        if not rate:
            rate = product.get('sale_price', 0)
        if not rate:
            rate = product.get('sales_rate', 0)
        display_text = f"[{barcode}] {name} - Rate: {rate}"

        # Draw background
        colors = theme.popup_list_delegate_colors()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(colors["selected_bg"]))
        else:
            painter.fillRect(option.rect, QColor(colors["normal_bg"]))

        painter.setPen(QColor(colors["text"]))
        painter.drawText(option.rect.adjusted(5, 0, -5, 0), Qt.AlignLeft | Qt.AlignVCenter, display_text)

    def sizeHint(self, option, index):
        """Override sizeHint to provide proper height for popup items."""
        return QSize(200, 30)


class CreditorPopupDelegate(QStyledItemDelegate):
    """Custom delegate for creditor popup to display formatted text with mobile and balance."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        """Override paint to display formatted text with mobile and balance."""
        # Get creditor data from UserRole
        creditor = index.data(Qt.UserRole)
        if not creditor:
            super().paint(painter, option, index)
            return

        # Handle both dict and string cases
        if isinstance(creditor, dict):
            name = party_display_name(creditor)
            mobile = creditor.get('mobile_number', '')
            balance = creditor.get('opening_balance', 0)
            display_text = f"{name}"
            if mobile:
                display_text += f" - {mobile}"
            if balance:
                display_text += f" - Bal: {balance}"
        else:
            # creditor is a string (name only)
            display_text = str(creditor)

        # Draw background
        colors = theme.popup_list_delegate_colors()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(colors["selected_bg"]))
        else:
            painter.fillRect(option.rect, QColor(colors["normal_bg"]))

        painter.setPen(QColor(colors["text"]))
        painter.drawText(option.rect.adjusted(5, 0, -5, 0), Qt.AlignLeft | Qt.AlignVCenter, display_text)

    def sizeHint(self, option, index):
        """Override sizeHint to provide proper height for popup items."""
        return QSize(200, 30)


def setup_product_completer(editor, parent_widget, index, on_product_selected_callback):
    """Set up completer for product search using DB-backed search_products_limited.

    Always uses a debounced (200 ms) DB search regardless of catalog size.
    This avoids freezing the UI for both small and large product catalogs.
    """
    # Remove old completer to avoid duplicate signal connections
    if editor.completer():
        old = editor.completer()
        editor.setCompleter(None)
        old.deleteLater()

    completer = NonInsertingCompleter(parent_widget)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)

    model = QStandardItemModel()
    completer.setModel(model)

    # Debounce timer — fires DB search 200 ms after last keystroke
    _timer = QTimer(parent_widget)
    _timer.setSingleShot(True)
    _timer.setInterval(200)

    def _do_db_search():
        text = editor.text().strip()
        if len(text) < MIN_POPUP_CHARS:
            model.clear()
            return

        active_company = None
        try:
            active_company = active_company_manager.get_active_company()
        except Exception:
            pass

        matches = []
        if active_company:
            # DB search — returns quantity already computed via SQL subquery
            matches = parent_widget.db.search_products_limited(
                active_company['id'], text, MAX_POPUP_RESULTS
            )

        model.clear()
        for product in matches:
            name = product.get('name', '')
            barcode = product.get('barcode', '') or ''
            rate = float(product.get('purchase_rate') or product.get('sale_price') or
                         product.get('wholesale_rate') or 0)
            stock = float(product.get('quantity') or 0.0)
            item = QStandardItem(name)
            item.setData(product, Qt.UserRole)
            item.setToolTip(f"Barcode: {barcode}\nRate: {rate:.2f}\nStock: {stock:.3f}")
            model.appendRow(item)

        if matches:
            completer.complete()

    _timer.timeout.connect(_do_db_search)
    editor.textChanged.connect(lambda _: _timer.start())

    editor.setCompleter(completer)

    # Install custom delegate on popup to display formatted text
    popup = completer.popup()
    popup.setItemDelegate(ProductPopupDelegate(parent_widget))
    theme.apply_completer_popup_theme(completer)

    # Handle activated signal for final selection using QModelIndex
    completer.activated[QModelIndex].connect(
        lambda model_idx, idx=index, ed=editor: on_product_selected_callback(idx, model_idx, ed)
    )


def _build_product_model(products_data):
    """Build product model for completer (used for small datasets)."""
    model = QStandardItemModel()
    for product in products_data:
        name = product['name']
        barcode = product.get('barcode', '')
        # Use purchase_rate first, fallback to sale_price → sales_rate → 0
        rate = product.get('purchase_rate', 0)
        if not rate:
            rate = product.get('sale_price', 0)
        if not rate:
            rate = product.get('sales_rate', 0)
        item = QStandardItem(name)
        item.setData(product, Qt.UserRole)
        item.setToolTip(f"Barcode: {barcode}\nRate: {rate}")
        model.appendRow(item)
    return model


def setup_creditor_completer(editor, parent_widget, on_creditor_selected_callback):
    """Set up completer for creditor search with custom popup delegate."""
    # Always create a new completer to ensure fresh data
    if editor.completer():
        old_completer = editor.completer()
        editor.setCompleter(None)
        old_completer.deleteLater()

    completer = QCompleter(parent_widget)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)

    # Create model with creditor names for completion
    model = QStandardItemModel()
    for creditor in parent_widget.creditors_data:
        # Handle both dict and string cases
        if isinstance(creditor, dict):
            name = creditor.get('name', '')
            display_name = party_display_name(creditor)
            mobile = creditor.get('mobile_number', '')
            balance = creditor.get('opening_balance', 0)
            item = QStandardItem(display_name)
            item.setData(creditor, Qt.UserRole)  # Store full creditor data
            item.setToolTip(f"Mobile: {mobile}\nBalance: {balance}")
        else:
            # creditor is a string (name only)
            name = str(creditor)
            item = QStandardItem(name)
            item.setData({'name': name}, Qt.UserRole)
            item.setToolTip(name)
        model.appendRow(item)

    completer.setModel(model)
    editor.setCompleter(completer)

    # Install custom delegate on popup to display formatted text
    popup = completer.popup()
    popup.setItemDelegate(CreditorPopupDelegate(parent_widget))
    theme.apply_completer_popup_theme(completer)

    # Handle activated signal for final selection using QModelIndex
    completer.activated[QModelIndex].connect(
        lambda model_idx: on_creditor_selected_callback(model_idx, editor)
    )