# -*- coding: utf-8 -*-
"""
Sidebar component with accordion-style navigation menu for the Accounting Desktop Application.
Provides main menu navigation with icons and modern styling.
"""

from pathlib import Path

from ui.brand_logo import (
    create_brand_logo_box,
    refresh_brand_logo_box,
    sidebar_logo_content_size,
)

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QScrollArea, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEvent
from PySide6.QtGui import QMouseEvent, QEnterEvent

from components.menu_icons import pixmap_for_menu_icon
from ui.theme_manager import get_theme_manager
from ui.theme import sidebar_icon_box_style, sidebar_route_button_style, sidebar_section_header_style
from ui.keyboard_shortcuts import format_route_button_text
from ui.scrollbar_style import scrollbar_stylesheet
from ui.qt_pump import pump_ui_events
from bizora_core.navigation_catalog import NAVIGATION_MENU

_APP_ROOT = Path(__file__).resolve().parent.parent
_ICON_BOX_SIZE = 44
_ICON_BOX_INSET = 3

SIDEBAR_SECTION_ICONS: dict[str, str] = {
    "File": "assets/icons/file.svg",
    "Masters": "assets/icons/masters.svg",
    "Entry": "assets/icons/entry.svg",
    "Books": "assets/icons/books.svg",
    "Reports": "assets/icons/reports.svg",
    "Utilities": "assets/icons/utilities.svg",
    "Settings": "assets/icons/settings.svg",
    "About Me": "assets/icons/about.svg",
}


class SidebarSectionHeader(QWidget):
    """Sidebar accordion header with a filled icon box and section title."""

    clicked = Signal()

    def __init__(self, section_name: str, icon_path: str = "", parent=None):
        super().__init__(parent)
        self.section_name = section_name
        self.icon_path = icon_path
        self._is_active = False
        self._is_hovered = False
        self.setObjectName("sidebarSectionHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("hovered", "false")
        self.setProperty("active", "false")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 18, 6)
        layout.setSpacing(10)

        self.icon_box = QFrame(self)
        self.icon_box.setObjectName("sidebarIconBox")
        self.icon_box.setFixedSize(_ICON_BOX_SIZE, _ICON_BOX_SIZE)
        self.icon_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.icon_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        box_layout = QVBoxLayout(self.icon_box)
        box_layout.setContentsMargins(
            _ICON_BOX_INSET,
            _ICON_BOX_INSET,
            _ICON_BOX_INSET,
            _ICON_BOX_INSET,
        )
        box_layout.setSpacing(0)

        inner_size = _ICON_BOX_SIZE - (_ICON_BOX_INSET * 2)
        self.icon_label = QLabel(self.icon_box)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setScaledContents(True)
        self.icon_label.setFixedSize(inner_size, inner_size)
        self.icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        box_layout.addWidget(self.icon_label)

        self.title_label = QLabel(section_name, self)
        self.title_label.setObjectName("sidebarSectionTitle")
        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        layout.addWidget(self.icon_box)
        layout.addWidget(self.title_label, 1)

        self.apply_header_style(is_active=False)

    def _repolish(self) -> None:
        """Re-evaluate dynamic QSS properties after hover or active state changes."""
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()

    def _sync_header_properties(self) -> None:
        """Push hovered/active state into QSS dynamic properties."""
        self.setProperty("hovered", "true" if self._is_hovered and not self._is_active else "false")
        self.setProperty("active", "true" if self._is_active else "false")

    def apply_header_style(self, is_active: bool = False) -> None:
        """Apply filled 3D icon box and row colours for normal/active states."""
        self._is_active = is_active
        if is_active:
            self._is_hovered = False
        self._sync_header_properties()
        self.setStyleSheet(sidebar_section_header_style())
        self.icon_box.setStyleSheet(sidebar_icon_box_style())
        self._repolish()

    def _set_hovered(self, hovered: bool) -> None:
        """Toggle the hover band on the section header row."""
        if self._is_active or self._is_hovered == hovered:
            return
        self._is_hovered = hovered
        self._sync_header_properties()
        self._repolish()

    def enterEvent(self, event: QEnterEvent) -> None:
        """Highlight the row while the pointer is over the header."""
        self._set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        """Remove hover highlight when the pointer leaves the header."""
        self._set_hovered(False)
        super().leaveEvent(event)

    def event(self, event: QEvent) -> bool:
        """Fallback hover tracking for platforms where enter/leave events are skipped."""
        if event.type() == QEvent.Type.HoverEnter:
            self._set_hovered(True)
        elif event.type() == QEvent.Type.HoverLeave:
            self._set_hovered(False)
        return super().event(event)

    def apply_icon(self) -> None:
        """Load the section icon using the same hi-DPI 3D SVG tiles as the shortcut bar."""
        pixmap = pixmap_for_menu_icon(
            self.icon_path,
            self.icon_label.size(),
            device_pixel_ratio=self.devicePixelRatioF(),
            bust_cache=True,
        )
        if pixmap is None:
            self.icon_label.clear()
            return

        self.icon_label.setPixmap(pixmap)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Emit ``clicked`` when the header row is pressed."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class Sidebar(QWidget):
    """Sidebar with accordion-style navigation menu."""
    
    page_changed = Signal(str)
    company_closed = Signal()
    
    def __init__(self):
        super().__init__()
        self.current_open_section = None
        self.setup_ui()
        QTimer.singleShot(0, self._apply_section_icons)

    def _nav_colors(self) -> dict[str, str]:
        return get_theme_manager().get_colors()

    def _divider_style(self) -> str:
        c = self._nav_colors()
        return f"""
            QLabel {{
                background-color: {c['nav_divider_bg']};
                color: {c['nav_divider_text']};
                border: none;
                border-left: 3px solid {c['nav_accent']};
                padding: 8px 18px 4px 18px;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }}
        """

    def _header_button_style(self, is_active: bool = False) -> str:
        c = self._nav_colors()
        bg = c["nav_header_active"] if is_active else c["nav_header_bg"]
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {c['nav_header_text']};
                border: none;
                border-left: 3px solid {c['nav_accent']};
                padding: 8px 18px 8px 10px;
                text-align: left;
                border-radius: 0px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {c['nav_header_hover']};
                color: {c['nav_header_text']};
                border-left: 3px solid {c['nav_accent']};
            }}
            QPushButton:pressed {{
                background-color: {c['nav_header_active']};
                color: {'#FFFFFF' if get_theme_manager().get_current_theme() == 'light' else c['nav_header_text']};
                border-left: 3px solid {c['nav_accent']};
            }}
        """

    def _route_button_style(self) -> str:
        """Return sidebar submenu button QSS (also defined in the global app theme)."""
        return sidebar_route_button_style()
    
    def setup_ui(self):
        """Setup the sidebar UI."""
        colors = self._nav_colors()
        self.setObjectName("applicationSidebar")
        self.setFixedWidth(280)
        self.setStyleSheet(f"""
            QWidget#applicationSidebar {{
                background-color: {colors['panel_bg']};
                border-right: 1px solid {colors['border']};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # App title
        title_widget = self.create_app_title()
        layout.addWidget(title_widget)
        
        # Menu scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            {scrollbar_stylesheet()}
        """)
        
        menu_widget = QWidget()
        menu_widget.setObjectName("sidebarMenuHost")
        menu_widget.setStyleSheet(f"""
            QWidget#sidebarMenuHost {{
                background-color: {colors['panel_bg']};
            }}
        """)
        menu_layout = QVBoxLayout(menu_widget)
        menu_layout.setContentsMargins(10, 10, 10, 10)
        menu_layout.setSpacing(2)
        
        # Create menu sections and keep route references for permission filtering.
        self.menu_sections = {}
        self.navigation_buttons = {}
        self.navigation_section_items = {}
        menu_items = NAVIGATION_MENU
        
        # Section icons — same 3D SVG pack as the main-page shortcut toolbar.
        menu_icons = SIDEBAR_SECTION_ICONS
        
        for section_name, subsections in menu_items.items():
            icon = menu_icons.get(section_name, "")
            section_widget = self.create_menu_section(section_name, subsections, icon)
            self.menu_sections[section_name] = section_widget
            self.navigation_section_items[section_name] = getattr(
                section_widget, "navigation_items", []
            )
            menu_layout.addWidget(section_widget)
            pump_ui_events()
        
        menu_layout.addStretch()
        scroll_area.setWidget(menu_widget)
        layout.addWidget(scroll_area)
    
    def create_app_title(self) -> QWidget:
        """Create application title widget."""
        colors = self._nav_colors()
        title_widget = QWidget()
        title_widget.setObjectName("sidebarTitleBar")
        title_widget.setFixedHeight(206)
        title_widget.setStyleSheet(f"""
            QWidget#sidebarTitleBar {{
                background-color: {colors['panel_bg']};
                border-bottom: 1px solid {colors['border']};
            }}
        """)
        
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(8, 8, 8, 8)
        title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_width, logo_height = sidebar_logo_content_size()
        self.logo_box, self.brand_logo_label = create_brand_logo_box(
            logo_width,
            logo_height,
            label_object_name="sidebarBrandLogo",
        )
        title_layout.addWidget(self.logo_box, alignment=Qt.AlignmentFlag.AlignCenter)
        
        return title_widget
    
    def is_category_divider(self, subsection: str) -> bool:
        """Return True when a sidebar subsection should render as a divider."""
        return subsection.startswith("--") and subsection.endswith("--")

    def create_category_divider(self, title: str) -> QLabel:
        """Create a non-clickable category divider for grouped menu items."""
        clean_title = title.strip("- ").upper()
        label = QLabel(clean_title)
        label.setObjectName(f"category_{clean_title.replace(' ', '_')}")
        label.setEnabled(False)
        label.setStyleSheet(self._divider_style())
        return label

    def create_menu_section(self, section_name: str, subsections: list, icon: str = "") -> QWidget:
        """Create a menu section with accordion behavior."""
        section_widget = QFrame()
        section_widget.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-radius: 6px;
                margin: 2px 0;
            }}
        """)
        
        section_layout = QVBoxLayout(section_widget)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)
        
        # Section header with filled icon box (dashboard card style)
        header_btn = SidebarSectionHeader(section_name, icon)
        header_btn.setProperty("sectionKey", section_name)
        header_btn.clicked.connect(
            lambda name=section_name: self.toggle_section(name)
        )
        section_layout.addWidget(header_btn)
        
        # Subsections container
        subsections_widget = QWidget()
        subsections_widget.setObjectName(f"subsections_{section_name}")
        subsections_widget.setVisible(False)  # Initially collapsed
        
        subsections_layout = QVBoxLayout(subsections_widget)
        subsections_layout.setContentsMargins(20, 0, 0, 0)
        subsections_layout.setSpacing(1)
        
        # Create subsection buttons
        navigation_items = []
        for subsection in subsections:
            if self.is_category_divider(subsection):
                divider = self.create_category_divider(subsection)
                navigation_items.append(divider)
                subsections_layout.addWidget(divider)
                continue

            route_name = "Debitor/Creditor" if subsection == "Debtor/Creditor" else subsection
            sub_btn = self._create_sidebar_route_button(subsection, route_name)
            sub_btn.route_name = route_name
            sub_btn.setVisible(True)
            sub_btn.setEnabled(True)
            if subsection == "Close Company":
                sub_btn.clicked.connect(self.close_company)
            else:
                sub_btn.clicked.connect(lambda checked, name=route_name: self.page_changed.emit(name))
            self.navigation_buttons.setdefault(route_name, []).append(sub_btn)
            navigation_items.append(sub_btn)
            subsections_layout.addWidget(sub_btn)
        
        section_layout.addWidget(subsections_widget)
        
        # Store references
        section_widget.header_btn = header_btn
        section_widget.subsections_widget = subsections_widget
        section_widget.navigation_items = navigation_items
        
        return section_widget

    def _apply_section_icons(self) -> None:
        """Attach cached menu icons after the sidebar layout is built."""
        for section_widget in self.menu_sections.values():
            header_btn = getattr(section_widget, "header_btn", None)
            if header_btn is None:
                continue
            if hasattr(header_btn, "apply_icon"):
                header_btn.apply_icon()

    def _create_sidebar_route_button(self, subsection: str, route_name: str) -> QPushButton:
        """Create a plain sidebar route button (no nested labels)."""
        button = QPushButton(format_route_button_text(subsection, route_name))
        button.setObjectName(f"sub_{subsection.replace(' ', '_')}")
        button.setStyleSheet(self._route_button_style())
        return button
    
    def close_company(self):
        """Handle Close Company action with confirmation dialog."""
        from config import active_company_manager
        
        # Check if there's an active company to close
        if not active_company_manager.has_active_company():
            return
        
        from ui.message_boxes import question as themed_question

        reply = themed_question(
            self,
            "Close Company",
            "Are you sure you want to close the active company?",
        )
        
        if reply == QMessageBox.Yes:
            # User confirmed, close the company
            active_company_manager.clear_active_company()
            self.company_closed.emit()  # Emit signal for main window to handle
            self.page_changed.emit("Dashboard")  # Show dashboard after closing company
        # If No, do nothing and keep company open
    
    def toggle_section(self, section_name: str):
        """Toggle accordion section open/closed."""
        if self.current_open_section == section_name:
            # Close current section
            self.menu_sections[section_name].subsections_widget.setVisible(False)
            self.current_open_section = None
            self.update_button_style(self.menu_sections[section_name].header_btn, False)
        else:
            # Close previous section if open
            if self.current_open_section:
                self.menu_sections[self.current_open_section].subsections_widget.setVisible(False)
                self.update_button_style(self.menu_sections[self.current_open_section].header_btn, False)
            
            # Open new section
            self.menu_sections[section_name].subsections_widget.setVisible(True)
            self.current_open_section = section_name
            self.update_button_style(self.menu_sections[section_name].header_btn, True)
    
    def update_button_style(self, button, is_active):
        """Update button style based on active state."""
        if hasattr(button, "apply_header_style"):
            button.apply_header_style(is_active=is_active)
            return
        button.setStyleSheet(self._header_button_style(is_active=is_active))
    
    def open_section(self, section_name: str):
        """Open specific section."""
        if section_name in self.menu_sections:
            self.toggle_section(section_name)

    def show_all_routes(self):
        """Show and enable every sidebar route and section."""
        for widgets in self.navigation_buttons.values():
            if not isinstance(widgets, (list, tuple, set)):
                widgets = [widgets]
            for widget in widgets:
                if widget is None:
                    continue
                widget.setVisible(True)
                widget.setEnabled(True)

        for section_widget in self.menu_sections.values():
            section_widget.setVisible(True)
            section_widget.header_btn.setVisible(True)
            section_widget.header_btn.setEnabled(True)
            navigation_items = getattr(section_widget, "navigation_items", [])
            for item in navigation_items:
                item.setVisible(True)
                item.setEnabled(False if isinstance(item, QLabel) else True)

    def refresh_theme(self):
        """Refresh sidebar styling based on current theme."""
        theme_manager = get_theme_manager()
        colors = theme_manager.get_colors()

        self.setStyleSheet(f"""
            QWidget#applicationSidebar {{
                background-color: {colors['panel_bg']};
                border-right: 1px solid {colors['border']};
            }}
        """)

        menu_host = self.findChild(QWidget, "sidebarMenuHost")
        if menu_host is not None:
            menu_host.setStyleSheet(f"""
                QWidget#sidebarMenuHost {{
                    background-color: {colors['panel_bg']};
                }}
            """)

        for section_widget in self.menu_sections.values():
            header_btn = getattr(section_widget, "header_btn", None)
            if header_btn is not None:
                is_active = self.current_open_section == getattr(
                    header_btn, "section_name", None
                )
                self.update_button_style(header_btn, is_active)
                if hasattr(header_btn, "apply_icon"):
                    header_btn.apply_icon()
            for item in getattr(section_widget, "navigation_items", []):
                if isinstance(item, QLabel):
                    item.setStyleSheet(self._divider_style())
                elif isinstance(item, QPushButton):
                    item.setStyleSheet(self._route_button_style())

        scroll_area = self.findChild(QScrollArea)
        if scroll_area:
            scroll_area.setStyleSheet(f"""
                QScrollArea {{
                    border: none;
                    background-color: transparent;
                }}
                {scrollbar_stylesheet()}
            """)

        title_bar = self.findChild(QWidget, "sidebarTitleBar")
        if title_bar is not None:
            title_bar.setStyleSheet(f"""
                QWidget#sidebarTitleBar {{
                    background-color: {colors['panel_bg']};
                    border-bottom: 1px solid {colors['border']};
                }}
            """)
        if hasattr(self, "logo_box"):
            logo_width, logo_height = sidebar_logo_content_size()
            refresh_brand_logo_box(
                self.logo_box,
                self.brand_logo_label,
                logo_width,
                logo_height,
            )
