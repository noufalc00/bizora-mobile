from datetime import datetime
from typing import Any, Dict, List, Tuple

from bizora_core.common_finance import MONEY_ZERO, money_round, to_decimal

class MonthlyAnalysisLogic:
    """Logic for Monthly Analysis report (read-only business analysis)."""
    
    # Financial-year month ordering: April to March
    FINANCIAL_YEAR_MONTHS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
    
    # Month name mapping
    MONTH_MAP = {
        1: "January", 2: "February", 3: "March",
        4: "April", 5: "May", 6: "June",
        7: "July", 8: "August", 9: "September",
        10: "October", 11: "November", 12: "December"
    }

    TRADING_INCOME_TOKENS = ("sales", "purchase return")
    DIRECT_EXPENSE_TOKENS = (
        "purchase",
        "sales return",
        "freight",
        "direct labour",
        "direct labor",
        "carriage",
        "direct expense",
        "wages",
    )
    
    def __init__(self, db):
        """Initialize Monthly Analysis Logic.
        
        Args:
            db: Database instance
        """
        self.db = db
    
    def get_financial_year_range(self, financial_year_str: str, from_month: str = "April", to_month: str = "March") -> Tuple[str, str]:
        """Get date range for financial year with month filtering.
        
        Args:
            financial_year_str: Financial year string (e.g., "2025-26")
            from_month: From month name (e.g., "April")
            to_month: To month name (e.g., "March")
            
        Returns:
            Tuple of (start_date, end_date) in YYYY-MM-DD format
        """
        year = int(financial_year_str.split('-')[0])
        
        month_name_to_num = {v: k for k, v in self.MONTH_MAP.items()}
        from_month_num = month_name_to_num.get(from_month, 4)
        to_month_num = month_name_to_num.get(to_month, 3)
        
        # Financial year starts in April (month 4)
        # If from_month is April to December, use the start year
        # If from_month is January to March, use the next year
        if from_month_num >= 4:
            start_year = year
        else:
            start_year = year + 1
        
        # If to_month is April to December, use the start year (if after April) or next year
        # If to_month is January to March, use the next year
        if to_month_num >= 4 and from_month_num >= 4:
            end_year = year
        elif to_month_num >= 4 and from_month_num < 4:
            end_year = year + 1
        else:
            end_year = year + 1
        
        # Get last day of the month
        def get_last_day(y, m):
            if m == 12:
                return 31
            elif m in [1, 3, 5, 7, 8, 10, 12]:
                return 31
            elif m in [4, 6, 9, 11]:
                return 30
            else:  # February
                # Check for leap year
                if (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0):
                    return 29
                else:
                    return 28
        
        start_date = f"{start_year}-{from_month_num:02d}-01"
        end_date = f"{end_year}-{to_month_num:02d}-{get_last_day(end_year, to_month_num)}"
        
        print(f"[DEBUG] Financial year range: {start_date} to {end_date} (FY: {financial_year_str}, {from_month} to {to_month})")
        return start_date, end_date
    
    def get_month_range_indices(self, from_month: str, to_month: str) -> Tuple[int, int]:
        """Get month range indices in financial-year sequence.
        
        Args:
            from_month: Month name (e.g., "April")
            to_month: Month name (e.g., "March")
            
        Returns:
            Tuple of (start_index, end_index) in FINANCIAL_YEAR_MONTHS
        """
        month_name_to_num = {v: k for k, v in self.MONTH_MAP.items()}
        from_month_num = month_name_to_num.get(from_month, 4)  # Default April
        to_month_num = month_name_to_num.get(to_month, 3)  # Default March
        
        try:
            start_index = self.FINANCIAL_YEAR_MONTHS.index(from_month_num)
            end_index = self.FINANCIAL_YEAR_MONTHS.index(to_month_num)
        except ValueError:
            # Fallback to full financial year
            start_index = 0
            end_index = len(self.FINANCIAL_YEAR_MONTHS) - 1
        
        return start_index, end_index
    
    def get_monthly_analysis(self, company_id: int, start_date: str, end_date: str,
                             from_month: str = "April", to_month: str = "March") -> Dict[str, Any]:
        """Get monthly profit analysis from verified ledger entries only.
        
        Args:
            company_id: Company ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            from_month: From month name (default "April")
            to_month: To month name (default "March")
            
        Returns:
            Dictionary with success flag, data list, and summary totals
        """
        try:
            ph = self.db._get_placeholder()
            year_expr = self.db.get_year_expression("le.voucher_date")
            month_expr = self.db.get_month_expression("le.voucher_date")
            monthly_data = self._initialize_monthly_data(start_date, end_date)
            query = f"""
                SELECT
                    {year_expr} AS year,
                    {month_expr} AS month_int,
                    la.id AS account_id,
                    la.account_name AS account_name,
                    la.account_type AS account_type,
                    COALESCE(la.group_name, '') AS group_name,
                    COALESCE(SUM(le.debit), 0) AS total_debit,
                    COALESCE(SUM(le.credit), 0) AS total_credit
                FROM ledger_entries le
                INNER JOIN ledger_accounts la
                    ON la.id = le.account_id
                   AND la.company_id = le.company_id
                WHERE le.company_id = {ph}
                  AND le.voucher_date >= {ph}
                  AND le.voucher_date <= {ph}
                  AND la.is_active = 1
                  AND la.account_type IN ('income', 'expense')
                  AND COALESCE(le.voucher_type, '') NOT IN (
                      'quotation', 'estimate', 'quote',
                      'Quotation', 'Estimate', 'Quote'
                  )
                GROUP BY
                    {year_expr},
                    {month_expr},
                    la.id,
                    la.account_name,
                    la.account_type,
                    la.group_name
                ORDER BY
                    {year_expr},
                    {month_expr},
                    la.account_name
            """
            rows = self.db.execute_query(query, (company_id, start_date, end_date))

            for row in rows:
                year = int(row["year"])
                month_int = int(row["month_int"])
                key = (year, month_int)
                if key not in monthly_data:
                    continue
                bucket = self._classify_account(row)
                amount = self._ledger_impact(row)
                monthly_data[key][bucket] = money_round(monthly_data[key][bucket] + amount)

            data = []
            summary = self._empty_summary()
            for key in sorted(monthly_data.keys()):
                entry = monthly_data[key]
                entry["gross_profit"] = money_round(
                    entry["trading_income"] - entry["direct_expenses"]
                )
                entry["net_profit"] = money_round(
                    entry["gross_profit"]
                    + entry["indirect_income"]
                    - entry["indirect_expenses"]
                )
                self._add_compatibility_keys(entry)
                data.append(entry)
                for field in (
                    "trading_income",
                    "direct_expenses",
                    "indirect_income",
                    "indirect_expenses",
                    "gross_profit",
                    "net_profit",
                ):
                    summary[field] = money_round(summary[field] + entry[field])

            self._add_summary_compatibility_keys(summary)
            return {"success": True, "data": data, "summary": summary}
        except Exception as exc:
            print(f"Error loading monthly analysis from ledger: {exc}")
            return {
                "success": False,
                "message": f"Error loading monthly analysis: {exc}",
                "data": [],
                "summary": self._empty_summary(),
            }

    def _initialize_monthly_data(self, start_date: str, end_date: str) -> Dict[Tuple[int, int], Dict[str, Any]]:
        """Create zero-filled rows for every year/month in the requested range."""
        monthly_data = {}
        current_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        while current_dt <= end_dt:
            year = current_dt.year
            month = current_dt.month
            monthly_data[(year, month)] = {
                "year": year,
                "month": month,
                "month_name": self.MONTH_MAP.get(month, str(month)),
                "trading_income": MONEY_ZERO,
                "direct_expenses": MONEY_ZERO,
                "indirect_income": MONEY_ZERO,
                "indirect_expenses": MONEY_ZERO,
                "gross_profit": MONEY_ZERO,
                "net_profit": MONEY_ZERO,
            }
            if month == 12:
                current_dt = current_dt.replace(year=year + 1, month=1, day=1)
            else:
                current_dt = current_dt.replace(month=month + 1, day=1)
        return monthly_data

    def _classify_account(self, row: Dict[str, Any]) -> str:
        """Classify an income/expense account into the monthly analysis buckets."""
        account_type = (row.get("account_type") or "").strip().lower()
        account_name = (row.get("account_name") or "").strip().lower()
        group_name = (row.get("group_name") or "").strip().lower()
        classifier_text = f"{account_name} {group_name}"

        if account_type == "income":
            if any(token in classifier_text for token in self.TRADING_INCOME_TOKENS):
                return "trading_income"
            return "indirect_income"
        if any(token in classifier_text for token in self.DIRECT_EXPENSE_TOKENS):
            return "direct_expenses"
        return "indirect_expenses"

    def _ledger_impact(self, row: Dict[str, Any]):
        """Return signed account impact using income/expense normal balances."""
        debit = to_decimal(row.get("total_debit"))
        credit = to_decimal(row.get("total_credit"))
        if (row.get("account_type") or "").strip().lower() == "income":
            return money_round(credit - debit)
        return money_round(debit - credit)

    def _empty_summary(self) -> Dict[str, Any]:
        """Return a zero-filled summary shape for monthly analysis."""
        return {
            "trading_income": MONEY_ZERO,
            "direct_expenses": MONEY_ZERO,
            "indirect_income": MONEY_ZERO,
            "indirect_expenses": MONEY_ZERO,
            "gross_profit": MONEY_ZERO,
            "net_profit": MONEY_ZERO,
        }

    def _add_compatibility_keys(self, entry: Dict[str, Any]) -> None:
        """Preserve legacy table/chart keys while exposing ledger-based totals."""
        entry["sales"] = entry["trading_income"]
        entry["sales_discount"] = MONEY_ZERO
        entry["sales_return"] = MONEY_ZERO
        entry["sales_return_discount"] = MONEY_ZERO
        entry["purchase"] = entry["direct_expenses"]
        entry["purchase_discount"] = MONEY_ZERO
        entry["purchase_return"] = MONEY_ZERO
        entry["purchase_return_discount"] = MONEY_ZERO
        entry["net_sales"] = entry["trading_income"]
        entry["net_purchase"] = entry["direct_expenses"]

    def _add_summary_compatibility_keys(self, summary: Dict[str, Any]) -> None:
        """Preserve legacy summary keys for any callers not yet updated."""
        summary["total_sales"] = summary["trading_income"]
        summary["total_sales_return"] = MONEY_ZERO
        summary["net_sales"] = summary["trading_income"]
        summary["total_purchase"] = summary["direct_expenses"]
        summary["total_purchase_return"] = MONEY_ZERO
        summary["net_purchase"] = summary["direct_expenses"]
