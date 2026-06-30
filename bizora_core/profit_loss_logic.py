"""
Deprecated Profit & Loss compatibility module.

FinancialReportingEngine is the active reporting engine. This module remains
only to keep legacy imports working while avoiding duplicate P&L calculations.
"""

from typing import Any, Dict, Optional

from bizora_core.financial_reporting_engine import FinancialReportingEngine


class ProfitLossLogic:
    """Compatibility wrapper around the active financial reporting engine."""

    def __init__(self, db):
        """Initialize the wrapper with the shared database connection."""
        self.db = db
        self.engine = FinancialReportingEngine(db)

    def calculate_profit_loss(
        self,
        company_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return P&L data from FinancialReportingEngine."""
        try:
            return self.engine.generate_profit_and_loss(
                company_id,
                from_date,
                to_date,
            )
        except Exception as exc:
            print(f"ProfitLossLogic compatibility wrapper error: {exc}")
            return self._empty_profit_loss_result()

    def generate_profit_and_loss(
        self,
        company_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias legacy callers to the active P&L report method."""
        return self.calculate_profit_loss(company_id, from_date, to_date)

    @staticmethod
    def _empty_profit_loss_result() -> Dict[str, Any]:
        """Return an empty result compatible with FinancialReportingEngine."""
        return {
            "direct_incomes": [],
            "direct_expenses": [],
            "indirect_incomes": [],
            "indirect_expenses": [],
            "total_direct_incomes": 0.0,
            "total_direct_expenses": 0.0,
            "gross_profit": 0.0,
            "total_indirect_incomes": 0.0,
            "total_indirect_expenses": 0.0,
            "net_profit": 0.0,
        }
