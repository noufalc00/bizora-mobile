"""
Global menu search field with autocomplete for the shortcut toolbar row.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QStringListModel, Signal, QSize, QTimer
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from bizora_core.global_search import collect_search_labels
from ui.theme import apply_completer_popup_theme

_APP_ROOT = Path(__file__).resolve().parent.parent
_SEARCH_ICON = _APP_ROOT / "assets" / "icons" / "search.svg"


class GlobalSearchLineEdit(QLineEdit):
    """Search field that selects all text on a single mouse click."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Select the entire query on click for immediate overwrite."""
        super().mousePressEvent(event)
        self.selectAll()


class GlobalSearchBar(QWidget):
    """Expanding search row with suggestion popup and 3D search button."""

    search_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("globalSearchBar")
        self._search_labels = collect_search_labels()
        self._search_dispatch_pending = False
        self._setup_ui()
        self.refresh_theme()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.search_input = GlobalSearchLineEdit()
        self.search_input.setObjectName("shortcutSearchInput")
        self.search_input.setPlaceholderText("Search menus...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(34)
        self.search_input.setMinimumWidth(280)
        self.search_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.search_input.returnPressed.connect(self._emit_search_requested)
        layout.addWidget(self.search_input, 1)

        self.search_model = QStringListModel(self._search_labels, self.search_input)
        self.search_completer = QCompleter(self.search_model, self.search_input)
        self.search_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.search_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.search_completer.setMaxVisibleItems(12)
        self.search_completer.activated.connect(self._on_completer_activated)
        self.search_input.setCompleter(self.search_completer)
        apply_completer_popup_theme(self.search_completer)
        self.search_input.textEdited.connect(self._show_completer_popup)

        self.search_btn = QPushButton()
        self.search_btn.setObjectName("shortcutSearchButton")
        if _SEARCH_ICON.is_file():
            self.search_btn.setIcon(QIcon(str(_SEARCH_ICON)))
            self.search_btn.setIconSize(QSize(22, 22))
        else:
            self.search_btn.setText("Go")
        self.search_btn.setToolTip("Search menus (Enter)")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setFixedSize(42, 34)
        self.search_btn.clicked.connect(self._emit_search_requested)
        layout.addWidget(self.search_btn)

    def _show_completer_popup(self, text: str) -> None:
        """Open the suggestion popup while the user types."""
        if text.strip():
            self.search_completer.complete()

    def _on_completer_activated(self, text: str) -> None:
        """Run search immediately when the user picks a suggestion."""
        popup = self.search_completer.popup()
        if popup is not None:
            popup.hide()
        self.search_input.setText(text)
        self._emit_search_requested()

    def _emit_search_requested(self) -> None:
        """Emit one debounced search request per user action."""
        if self._search_dispatch_pending:
            return

        query = self.search_input.text().strip()
        if not query:
            return

        popup = self.search_completer.popup()
        if popup is not None:
            popup.hide()

        self._search_dispatch_pending = True
        QTimer.singleShot(0, lambda: self._dispatch_search_request(query))

    def _dispatch_search_request(self, query: str) -> None:
        """Dispatch the search signal after duplicate events in the same tick."""
        try:
            if query:
                self.search_requested.emit(query)
        finally:
            self._search_dispatch_pending = False

    def focus_search_field(self) -> None:
        """Focus the search field and select all text."""
        self.search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_input.selectAll()

    def _apply_search_input_style(self) -> None:
        from ui.theme_manager import get_theme_manager

        colors = get_theme_manager().get_colors()
        self.search_input.setStyleSheet(f"""
            QLineEdit#shortcutSearchInput {{
                background-color: {colors['input_bg']};
                border: 1px solid {colors['border']};
                border-radius: 6px;
                color: {colors['input_text']};
                font-size: 13px;
                padding: 4px 10px;
            }}
            QLineEdit#shortcutSearchInput:focus {{
                border: 1px solid {colors['focus_border']};
            }}
        """)

    def _apply_search_button_style(self) -> None:
        from ui.theme import shortcut_toolbar_3d_icon_button_style

        self.search_btn.setStyleSheet(
            shortcut_toolbar_3d_icon_button_style().replace(
                "QPushButton#shortcutIconButton",
                "QPushButton#shortcutSearchButton",
            )
        )

    def refresh_theme(self) -> None:
        """Re-apply theme-aware styles after a global theme change."""
        self._apply_search_input_style()
        self._apply_search_button_style()
        apply_completer_popup_theme(self.search_completer)

    def reload_search_catalog(self) -> None:
        """Refresh searchable labels after navigation catalog changes."""
        self._search_labels = collect_search_labels()
        self.search_model.setStringList(self._search_labels)
