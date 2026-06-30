"""
Compatibility entry point for company setup UI.

The application currently uses NewCompanyPageWidget for create/edit company
setup. This module preserves the requested import path for future callers.
"""

from ui.new_company_page import NewCompanyPageWidget


class CompanySetupView(NewCompanyPageWidget):
    """Company setup view with GST registration type support."""

    pass