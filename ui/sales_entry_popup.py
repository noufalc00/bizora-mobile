"""
Product and Party popup logic for Sales Entry widget.
Contains ProductPopupDelegate, PartyPopupDelegate, and popup display formatting.
"""

from PySide6.QtWidgets import QStyledItemDelegate, QLineEdit, QCompleter, QListView, QStyle
from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex, QSize, QTimer
from PySide6.QtGui import QPainter, QColor, QStandardItemModel, QStandardItem
from ui.party_display import party_display_name
from ui import theme

try:
    from config import active_company_manager
except ImportError:
    # Fallback for when config is not in path
    active_company_manager = None


class ProductPopupDelegate(QStyledItemDelegate):
    """Custom delegate for product popup to display formatted text with barcode and stock."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        """Override paint to display formatted text with barcode and stock."""
        # Get product data from UserRole
        product = index.data(Qt.UserRole)
        if not product:
            super().paint(painter, option, index)
            return

        # Format display text: [Barcode] Product Name - Stock: X
        barcode = product.get('barcode', '')
        name = product['name']
        stock = product.get('quantity', 0)
        display_text = f"[{barcode}] {name} - Stock: {stock}"

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


class PartyPopupDelegate(QStyledItemDelegate):
    """Custom delegate for party popup to display formatted text with mobile and balance."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        """Override paint to display formatted text with mobile and balance."""
        # Get party data from UserRole
        party = index.data(Qt.UserRole)
        if not party:
            super().paint(painter, option, index)
            return

        # Format display text: Party Name (CODE) - Mobile - Balance
        name = party_display_name(party)
        mobile = party.get('mobile_number', '') or party.get('mobile', '')
        balance = party.get('opening_balance', 0)
        display_text = f"{name}"
        if mobile:
            display_text += f" - {mobile}"
        if balance:
            display_text += f" - Bal: {balance}"

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


MAX_POPUP_RESULTS = 100
MIN_POPUP_CHARS = 2


def setup_product_completer(editor, parent_widget, index, on_product_selected_callback, min_chars=MIN_POPUP_CHARS):
    """Set up completer for product search using DB-backed search_products_limited.

    Always uses a debounced (200 ms) DB search regardless of catalog size.
    This avoids freezing the UI for both small and large product catalogs.
    """
    # Remove old completer to avoid duplicate signal connections
    if editor.completer():
        old = editor.completer()
        editor.setCompleter(None)
        old.deleteLater()

    completer = QCompleter(parent_widget)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchStartsWith)
    completer.setCompletionMode(QCompleter.PopupCompletion)

    model = QStandardItemModel()
    completer.setModel(model)

    # Debounce timer — fires DB search 200 ms after last keystroke
    _timer = QTimer(parent_widget)
    _timer.setSingleShot(True)
    _timer.setInterval(200)

    def _do_db_search():
        text = editor.text().strip()
        if len(text) < min_chars:
            model.clear()
            return

        active_company = None
        if active_company_manager is not None:
            try:
                active_company = active_company_manager.get_active_company()
            except Exception:
                pass

        matches = []
        if active_company:
            # DB search — quantity already computed via SQL subquery
            matches = parent_widget.db.search_products_limited(
                active_company['id'], text, MAX_POPUP_RESULTS
            )
            text_lower = text.lower()
            matches = [
                product for product in matches
                if str(product.get('name') or '').lower().startswith(text_lower)
                or str(product.get('barcode') or '').lower().startswith(text_lower)
            ]

        model.clear()
        for product in matches:
            name = product.get('name', '')
            barcode = product.get('barcode', '') or ''
            stock = float(product.get('quantity') or 0.0)
            rate = float(product.get('sale_price') or product.get('mrp') or
                         product.get('wholesale_rate') or product.get('purchase_rate') or 0)
            item = QStandardItem(name)
            item.setData(product, Qt.UserRole)
            item.setToolTip(f"Barcode: {barcode}\nRate: {rate:.2f}\nStock: {stock:.3f}")
            model.appendRow(item)

        if matches:
            completer.complete()

    _timer.timeout.connect(_do_db_search)
    editor.textChanged.connect(lambda _: _timer.start())
    editor.returnPressed.connect(lambda: (_timer.stop(), _do_db_search(), completer.complete()))

    editor.setCompleter(completer)

    # Install custom delegate on popup to display formatted text
    popup = completer.popup()
    popup.setItemDelegate(ProductPopupDelegate(parent_widget))
    theme.apply_completer_popup_theme(completer)

    # Handle activated signal for final selection using QModelIndex
    completer.activated[QModelIndex].connect(
        lambda model_idx, idx=index, ed=editor: on_product_selected_callback(idx, model_idx, ed)
    )


def setup_party_completer(editor, parent_widget, on_party_selected_callback):
    """Set up completer for party search with custom popup delegate."""
    completer = QCompleter(parent_widget)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    completer.setCompletionMode(QCompleter.PopupCompletion)

    # Create model with party names for completion
    model = QStandardItemModel()
    for party in parent_widget.parties_data:
        name = party.get('name', '')
        display_name = party_display_name(party)
        mobile = party.get('mobile_number', '') or party.get('mobile', '')
        balance = party.get('opening_balance', 0)
        item = QStandardItem(display_name)
        item.setData(party, Qt.UserRole)  # Store full party data
        # Set tooltip to show mobile and balance
        item.setToolTip(f"Mobile: {mobile}\nBalance: {balance}")
        model.appendRow(item)

    completer.setModel(model)
    editor.setCompleter(completer)

    # Install custom delegate on popup to display formatted text
    popup = completer.popup()
    popup.setItemDelegate(PartyPopupDelegate(parent_widget))
    theme.apply_completer_popup_theme(completer)

    # Handle activated signal for final selection using QModelIndex
    completer.activated[QModelIndex].connect(
        lambda model_idx: on_party_selected_callback(model_idx, editor)
    )