"""
Dark theme module for the Accounting Desktop Application.
Provides the dark stylesheet as a Python function.
"""


def get_dark_stylesheet() -> str:
    """Load and return the dark theme stylesheet."""
    from utils.theme_manager import ThemeManager

    return ThemeManager.get_dark_theme_qss()


def apply_dark_theme(app):
    """Apply dark theme to the QApplication."""
    stylesheet = get_dark_stylesheet()
    app.setStyleSheet(stylesheet)
