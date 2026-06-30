"""
Configuration settings for the Accounting Desktop Application.
Contains app metadata, colors, window sizes, and other constants.
"""

import os

# Application metadata
APP_NAME = "BIZORA"
BRAND_NAME = "BIZORA"
COMPANY_DISPLAY_NAME = "BIZORA Software Solutions"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "A modern desktop accounting application"

# Window dimensions
WINDOW_SIZE = (1200, 800)
MIN_WINDOW_SIZE = (800, 600)
MAX_WINDOW_SIZE = (1920, 1080)

# Dark theme color palette (static defaults; use get_colors() for theme-aware access).
_DARK_COLORS = {
    # Primary colors
    "primary": "#2196F3",
    "primary_dark": "#1976D2",
    "primary_light": "#BBDEFB",
    
    # Background colors
    "background": "#121212",
    "surface": "#1E1E1E",
    "card": "#2D2D2D",
    "sidebar": "#1A1A1A",
    
    # Text colors
    "text_primary": "#FFFFFF",
    "text_secondary": "#B3B3B3",
    "text_disabled": "#666666",
    
    # Status colors
    "success": "#4CAF50",
    "warning": "#FF9800",
    "error": "#F44336",
    "info": "#2196F3",
    
    # Border colors
    "border": "#404040",
    "border_light": "#555555",
    "border_focus": "#2196F3",

    # Scrollbar colors
    "scrollbar_track": "#141c2b",
    "scrollbar_handle": "#4a6fa5",
    "scrollbar_handle_hover": "#60a5fa",
    "scrollbar_handle_pressed": "#3b82f6",
    
    # Button colors
    "button_default": "#2D2D2D",
    "button_hover": "#3D3D3D",
    "button_pressed": "#4D4D4D",
}


class _ThemeAwareColors(dict):
    """Dict that resolves legacy COLORS keys from the active application theme."""

    _KEYS = frozenset(_DARK_COLORS.keys())

    def __getitem__(self, key: str):
        if key in self._KEYS:
            try:
                from ui import theme
                return theme.legacy_colors()[key]
            except Exception:
                return _DARK_COLORS[key]
        try:
            from ui import theme
            token = theme._theme_colors().get(key)
            if token is not None:
                return token
        except Exception:
            pass
        raise KeyError(key)

    def get(self, key: str, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        if key in self._KEYS or key in _DARK_COLORS:
            return True
        try:
            from ui import theme
            return key in theme._theme_colors()
        except Exception:
            return False

    def keys(self):
        return _DARK_COLORS.keys()

    def values(self):
        return [self[k] for k in _DARK_COLORS]

    def items(self):
        return [(k, self[k]) for k in _DARK_COLORS]

    def copy(self):
        return {k: self[k] for k in _DARK_COLORS}


COLORS = _ThemeAwareColors()

# Database settings
DATABASE_TYPE = "sqlite"  # Options: "sqlite" or "mysql"
DATABASE_NAME = "accounting.db"
DATABASE_BACKUP_DIR = "backups"

# MySQL configuration (only used if DATABASE_TYPE is "mysql")
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = ""
MYSQL_DATABASE = "accounting_db"

# UI settings
FONT_FAMILY = "Segoe UI"
FONT_SIZE = 10
HEADER_FONT_SIZE = 14
TITLE_FONT_SIZE = 16

# Animation settings
ANIMATION_DURATION = 200  # milliseconds
FADE_DURATION = 150

# Grid settings
GRID_SPACING = 10
MARGIN = 16
PADDING = 8

# File paths
ASSETS_DIR = "assets"
ICONS_DIR = os.path.join(ASSETS_DIR, "icons")
STYLES_DIR = os.path.join(ASSETS_DIR, "styles")

# Currency settings
DEFAULT_CURRENCY = "INR"
CURRENCY_SYMBOL = "₹"
DECIMAL_PLACES = 2

# Date format
UI_DISPLAY_DATE_FORMAT = "dd-MM-yyyy"
DB_DATE_FORMAT = "yyyy-MM-dd"
PYTHON_DISPLAY_DATE_FORMAT = "%d-%m-%Y"
PYTHON_DB_DATE_FORMAT = "%Y-%m-%d"
DATE_FORMAT = PYTHON_DISPLAY_DATE_FORMAT
DATE_TIME_FORMAT = "%d-%m-%Y %H:%M:%S"

# Application settings
AUTO_SAVE_INTERVAL = 300  # seconds
MAX_RECENT_FILES = 10

# Company registry pools
COMPANY_VISIBILITY_NORMAL = "normal"
COMPANY_VISIBILITY_SECRET = "secret"
MAX_NORMAL_COMPANIES = 3
MAX_SECRET_COMPANIES = 2

# Active Company State Management
class ActiveCompanyManager:
    """Central manager for active company state across the application."""
    
    def __init__(self):
        self.active_company = None
        self.active_company_id = None
    
    def set_active_company(self, company_data):
        """Set the active company."""
        self.active_company = company_data
        self.active_company_id = company_data.get('id') if company_data else None
    
    def get_active_company(self):
        """Get the current active company."""
        return self.active_company
    
    def get_active_company_id(self):
        """Get the current active company ID."""
        return self.active_company_id
    
    def get_active_company_name(self):
        """Get the current active company name."""
        if self.active_company:
            return self.active_company.get('business_name', '')
        return ''

    def get_working_financial_year(self):
        """Get the working financial year for the active company."""
        if self.active_company:
            financial_year = (self.active_company.get('financial_year') or '').strip()
            if financial_year:
                return financial_year
        return None
    
    def clear_active_company(self):
        """Clear the active company state."""
        self.active_company = None
        self.active_company_id = None
    
    def has_active_company(self):
        """Check if there is an active company."""
        return self.active_company is not None

def resolve_active_company_id(db):
    """Return the company explicitly opened in the current app session.

    Important: do not silently load companies.is_active from the database on
    startup. The user must open a company from File > Open Company before
    accounting modules are allowed to open/save.
    """
    company_id = active_company_manager.get_active_company_id()
    return int(company_id) if company_id else None

# Global instance for app-wide access
active_company_manager = ActiveCompanyManager()
