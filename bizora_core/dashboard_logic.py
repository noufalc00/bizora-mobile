"""
Dashboard summary metrics backed by live company database values.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from config import active_company_manager
from db import Database
from bizora_core.common_finance import money_round, to_decimal
from bizora_core.ledger_logic import LedgerLogic
from utils.financial_year import (
    get_current_financial_year_label,
    get_financial_year_date_range,
    get_working_financial_year_label,
)

_QUOTE_VOUCHER_TYPES = (
    "quotation",
    "estimate",
    "quote",
    "Quotation",
    "Estimate",
    "Quote",
)

# Credit bills are stored as sales_type = 'Credit Sales' even when payment_mode is Cash.
_MONTH_LABELS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
_DASHBOARD_CHART_MONTH_COUNT = 6
_RECENT_ACTIVITY_LIMIT = 5

# Credit bills are stored as sales_type = 'Credit Sales' even when payment_mode is Cash.
_CREDIT_SALE_SQL = """
(
    LOWER(COALESCE(payment_mode, '')) LIKE '%credit%'
    OR LOWER(COALESCE(sales_type, '')) IN ('credit sales', 'credit')
)
"""


class DashboardLogic:
    """Load dashboard KPI values from the active company database."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def get_summary_metrics(self, company_id: Optional[int] = None) -> Dict[str, float]:
        """
        Return live dashboard totals for the active company.

        Keys:
            net_realized_sale, total_creditors, total_debtors, day_credit_sale
        """
        resolved_company_id = company_id or active_company_manager.get_active_company_id()
        if not resolved_company_id:
            return self._empty_metrics()

        try:
            today = date.today()
            today_text = today.isoformat()
            fy_label = get_working_financial_year_label() or get_current_financial_year_label()
            fy_start, fy_end = get_financial_year_date_range(fy_label)
            period_end = min(today, fy_end)

            company_key = int(resolved_company_id)
            return {
                "net_realized_sale": self._get_net_realized_sale(
                    company_key,
                    today_text,
                    today_text,
                ),
                "total_creditors": self._get_sundry_group_balance_total(
                    company_key,
                    fy_start,
                    period_end,
                    "Sundry Creditors",
                    "Cr",
                ),
                "total_debtors": self._get_sundry_group_balance_total(
                    company_key,
                    fy_start,
                    period_end,
                    "Sundry Debtors",
                    "Dr",
                ),
                "day_credit_sale": self._get_day_credit_sales(
                    company_key,
                    today_text,
                ),
            }
        except Exception as exc:
            print(f"[DASHBOARD] Failed to load summary metrics: {exc}")
            return self._empty_metrics()

    def get_monthly_sales_chart_data(
        self,
        company_id: Optional[int] = None,
        month_count: int = _DASHBOARD_CHART_MONTH_COUNT,
    ) -> List[Dict[str, Any]]:
        """Return monthly sales totals for the dashboard bar chart."""
        resolved_company_id = company_id or active_company_manager.get_active_company_id()
        if not resolved_company_id:
            return self._empty_monthly_series(month_count)
        return self._get_monthly_total_series(
            int(resolved_company_id),
            table_name="sales",
            date_column="invoice_date",
            month_count=month_count,
        )

    def get_monthly_purchase_chart_data(
        self,
        company_id: Optional[int] = None,
        month_count: int = _DASHBOARD_CHART_MONTH_COUNT,
    ) -> List[Dict[str, Any]]:
        """Return monthly purchase totals for the dashboard bar chart."""
        resolved_company_id = company_id or active_company_manager.get_active_company_id()
        if not resolved_company_id:
            return self._empty_monthly_series(month_count)
        return self._get_monthly_total_series(
            int(resolved_company_id),
            table_name="purchases",
            date_column="purchase_date",
            month_count=month_count,
        )

    def get_recent_activities(
        self,
        company_id: Optional[int] = None,
        limit: int = _RECENT_ACTIVITY_LIMIT,
    ) -> List[str]:
        """Return the latest voucher activity lines for the dashboard feed."""
        resolved_company_id = company_id or active_company_manager.get_active_company_id()
        if not resolved_company_id:
            return []

        try:
            rows: list[dict[str, Any]] = []
            rows.extend(
                self._fetch_recent_voucher_rows(
                    int(resolved_company_id),
                    source="sales",
                    date_column="invoice_date",
                    number_column="invoice_number",
                    amount_column="grand_total",
                    party_join="LEFT JOIN parties p ON p.id = s.party_id",
                    party_name_sql="COALESCE(p.name, 'Cash Customer')",
                    kind_label="Sale",
                    table_alias="s",
                )
            )
            rows.extend(
                self._fetch_recent_voucher_rows(
                    int(resolved_company_id),
                    source="purchases",
                    date_column="purchase_date",
                    number_column="purchase_number",
                    amount_column="grand_total",
                    party_join="LEFT JOIN parties p ON p.id = pu.party_id",
                    party_name_sql="COALESCE(p.name, 'Cash Supplier')",
                    kind_label="Purchase",
                    table_alias="pu",
                )
            )
            rows.extend(
                self._fetch_recent_voucher_rows(
                    int(resolved_company_id),
                    source="sales_returns",
                    date_column="return_date",
                    number_column="return_no",
                    amount_column="grand_total",
                    party_join="LEFT JOIN parties p ON p.id = sr.party_id",
                    party_name_sql="COALESCE(p.name, 'Customer')",
                    kind_label="Sales Return",
                    table_alias="sr",
                )
            )
            rows.extend(
                self._fetch_recent_voucher_rows(
                    int(resolved_company_id),
                    source="purchase_returns",
                    date_column="return_date",
                    number_column="return_no",
                    amount_column="grand_total",
                    party_join="LEFT JOIN parties p ON p.id = pr.party_id",
                    party_name_sql="COALESCE(p.name, 'Supplier')",
                    kind_label="Purchase Return",
                    table_alias="pr",
                )
            )
            rows.extend(
                self._fetch_recent_receipt_rows(int(resolved_company_id), "cash_receipts", "Cash Receipt")
            )
            rows.extend(
                self._fetch_recent_receipt_rows(int(resolved_company_id), "bank_receipts", "Bank Receipt")
            )

            rows.sort(
                key=lambda row: (
                    str(row.get("activity_date") or ""),
                    int(row.get("sort_id") or 0),
                ),
                reverse=True,
            )

            formatted: list[str] = []
            for row in rows[: max(int(limit), 0)]:
                text = self._format_activity_line(row)
                if text:
                    formatted.append(text)
            return formatted
        except Exception as exc:
            print(f"[DASHBOARD] Failed to load recent activity: {exc}")
            return []

    @staticmethod
    def _empty_monthly_series(month_count: int) -> List[Dict[str, Any]]:
        """Return zeroed monthly buckets when no company database is active."""
        labels, month_keys = DashboardLogic._build_month_window(month_count)
        return [
            {"label": label, "year": year, "month": month, "total": 0.0}
            for label, (year, month) in zip(labels, month_keys)
        ]

    @staticmethod
    def _build_month_window(month_count: int) -> Tuple[List[str], List[Tuple[int, int]]]:
        """Build display labels and (year, month) keys for the last N months."""
        today = date.today()
        labels: list[str] = []
        keys: list[tuple[int, int]] = []
        year = today.year
        month = today.month

        for offset in range(month_count - 1, -1, -1):
            target_month = month - offset
            target_year = year
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            labels.append(f"{_MONTH_LABELS[target_month - 1]} {str(target_year)[-2:]}")
            keys.append((target_year, target_month))

        return labels, keys

    @staticmethod
    def _month_start_date(year: int, month: int) -> date:
        """Return the first calendar day for a year/month pair."""
        return date(year, month, 1)

    def _get_monthly_total_series(
        self,
        company_id: int,
        *,
        table_name: str,
        date_column: str,
        month_count: int,
    ) -> List[Dict[str, Any]]:
        """Query monthly grand totals for one voucher table."""
        labels, month_keys = self._build_month_window(month_count)
        if not month_keys:
            return []

        start_year, start_month = month_keys[0]
        start_date = self._month_start_date(start_year, start_month).isoformat()
        ph = self.db._get_placeholder()
        year_expr = self.db.get_year_expression(date_column)
        month_expr = self.db.get_month_expression(date_column)

        query = f"""
            SELECT
                {year_expr} AS year_value,
                {month_expr} AS month_value,
                COALESCE(SUM(grand_total), 0) AS month_total
            FROM {table_name}
            WHERE company_id = {ph}
              AND COALESCE(status, 'Active') <> 'Voided'
              AND DATE({date_column}) >= DATE({ph})
            GROUP BY year_value, month_value
        """
        try:
            rows = self.db.execute_query(query, (company_id, start_date)) or []
        except Exception as exc:
            print(f"[DASHBOARD] Monthly chart query failed for {table_name}: {exc}")
            rows = []

        totals_by_key: dict[tuple[int, int], float] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            year_value = int(row.get("year_value") or 0)
            month_value = int(row.get("month_value") or 0)
            amount = float(money_round(to_decimal(row.get("month_total") or 0.0)))
            totals_by_key[(year_value, month_value)] = amount

        return [
            {
                "label": label,
                "year": year,
                "month": month,
                "total": totals_by_key.get((year, month), 0.0),
            }
            for label, (year, month) in zip(labels, month_keys)
        ]

    def _fetch_recent_voucher_rows(
        self,
        company_id: int,
        *,
        source: str,
        date_column: str,
        number_column: str,
        amount_column: str,
        party_join: str,
        party_name_sql: str,
        kind_label: str,
        table_alias: str,
    ) -> List[Dict[str, Any]]:
        """Load recent voucher rows from one posting table."""
        ph = self.db._get_placeholder()
        query = f"""
            SELECT
                {table_alias}.{date_column} AS activity_date,
                {table_alias}.{number_column} AS voucher_no,
                {party_name_sql} AS party_name,
                COALESCE({table_alias}.{amount_column}, 0) AS amount,
                {table_alias}.id AS sort_id
            FROM {source} {table_alias}
            {party_join}
            WHERE {table_alias}.company_id = {ph}
              AND COALESCE({table_alias}.status, 'Active') <> 'Voided'
            ORDER BY {table_alias}.{date_column} DESC, {table_alias}.id DESC
            LIMIT 8
        """
        try:
            rows = self.db.execute_query(query, (company_id,)) or []
        except Exception as exc:
            print(f"[DASHBOARD] Recent activity query failed for {source}: {exc}")
            return []

        formatted_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            formatted_rows.append(
                {
                    "activity_date": row.get("activity_date"),
                    "voucher_no": row.get("voucher_no") or "",
                    "party_name": row.get("party_name") or "",
                    "amount": float(money_round(to_decimal(row.get("amount") or 0.0))),
                    "kind_label": kind_label,
                    "sort_id": int(row.get("sort_id") or 0),
                }
            )
        return formatted_rows

    def _fetch_recent_receipt_rows(
        self,
        company_id: int,
        table_name: str,
        kind_label: str,
    ) -> List[Dict[str, Any]]:
        """Load recent cash or bank receipt rows for the activity feed."""
        ph = self.db._get_placeholder()
        query = f"""
            SELECT
                voucher_date AS activity_date,
                voucher_no AS voucher_no,
                COALESCE(narration, remark, 'Receipt') AS party_name,
                COALESCE(amount, 0) AS amount,
                id AS sort_id
            FROM {table_name}
            WHERE company_id = {ph}
            ORDER BY voucher_date DESC, id DESC
            LIMIT 8
        """
        try:
            rows = self.db.execute_query(query, (company_id,)) or []
        except Exception as exc:
            print(f"[DASHBOARD] Recent activity query failed for {table_name}: {exc}")
            return []

        formatted_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            formatted_rows.append(
                {
                    "activity_date": row.get("activity_date"),
                    "voucher_no": row.get("voucher_no") or "",
                    "party_name": row.get("party_name") or "",
                    "amount": float(money_round(to_decimal(row.get("amount") or 0.0))),
                    "kind_label": kind_label,
                    "sort_id": int(row.get("sort_id") or 0),
                }
            )
        return formatted_rows

    @staticmethod
    def _format_activity_line(row: Dict[str, Any]) -> str:
        """Format one recent activity row for dashboard display."""
        activity_date = str(row.get("activity_date") or "").strip()
        display_date = activity_date
        if activity_date:
            try:
                from ui.date_formats import format_display_date

                display_date = format_display_date(activity_date)
            except ValueError:
                display_date = activity_date

        kind_label = str(row.get("kind_label") or "Activity").strip()
        voucher_no = str(row.get("voucher_no") or "").strip()
        party_name = str(row.get("party_name") or "").strip()
        amount = float(row.get("amount") or 0.0)

        from config import CURRENCY_SYMBOL

        voucher_text = f" {voucher_no}" if voucher_no else ""
        party_text = f" — {party_name}" if party_name else ""
        return (
            f"{kind_label}{voucher_text}{party_text} — "
            f"{CURRENCY_SYMBOL}{amount:,.2f} ({display_date})"
        )

    @staticmethod
    def _empty_metrics() -> Dict[str, float]:
        """Return zeroed metrics when no company is open."""
        return {
            "net_realized_sale": 0.0,
            "total_creditors": 0.0,
            "total_debtors": 0.0,
            "day_credit_sale": 0.0,
        }

    def _fetch_scalar(self, query: str, params: tuple[Any, ...]) -> float:
        """Execute a scalar SUM query and return a rounded float."""
        try:
            rows = self.db.execute_query(query, params) or []
            if not rows:
                return 0.0
            row = rows[0]
            if isinstance(row, dict):
                value = next(iter(row.values()))
            elif isinstance(row, (list, tuple)):
                value = row[0]
            else:
                value = row
            return float(money_round(to_decimal(value or 0.0)))
        except Exception as exc:
            print(f"[DASHBOARD] Scalar query failed: {exc}")
            return 0.0

    def _quote_exclusion_sql(self) -> str:
        """Build a NOT IN clause for non-posting quote voucher types."""
        ph = self.db._get_placeholder()
        return ", ".join(ph for _ in _QUOTE_VOUCHER_TYPES)

    def _get_sundry_group_balance_total(
        self,
        company_id: int,
        from_date: date,
        to_date: date,
        group_name: str,
        balance_side: str,
    ) -> float:
        """
        Sum Dr or Cr closing balances for sundry debtor/creditor ledger accounts.

        Matches Day Book / Ledger group summaries: party sub-ledgers use
        group_name, and the system control account uses the same label as
        account_name (for example the parent "Sundry Debtors" account).
        """
        try:
            LedgerLogic(self.db).ensure_party_ledger_accounts(company_id)
        except Exception as exc:
            print(f"[DASHBOARD] ensure_party_ledger_accounts failed: {exc}")

        ph = self.db._get_placeholder()
        quote_sql = self._quote_exclusion_sql()
        side = balance_side.strip().lower()
        if side.startswith("cr"):
            balance_case = "WHEN closing_net < -0.004 THEN ABS(closing_net)"
        else:
            balance_case = "WHEN closing_net > 0.004 THEN closing_net"

        query = f"""
            SELECT COALESCE(SUM(
                CASE
                    {balance_case}
                    ELSE 0
                END
            ), 0) AS group_total
            FROM (
                SELECT
                    (
                        CASE
                            WHEN LOWER(COALESCE(la.opening_balance_type, 'Dr')) LIKE 'cr%'
                                THEN -COALESCE(la.opening_balance, 0)
                            ELSE COALESCE(la.opening_balance, 0)
                        END
                        + COALESCE(SUM(
                            CASE
                                WHEN DATE(le.voucher_date) < DATE({ph})
                                    THEN COALESCE(le.debit, 0) - COALESCE(le.credit, 0)
                                ELSE 0
                            END
                        ), 0)
                        + COALESCE(SUM(
                            CASE
                                WHEN DATE(le.voucher_date) >= DATE({ph})
                                 AND DATE(le.voucher_date) <= DATE({ph})
                                    THEN COALESCE(le.debit, 0) - COALESCE(le.credit, 0)
                                ELSE 0
                            END
                        ), 0)
                    ) AS closing_net
                FROM ledger_accounts la
                LEFT JOIN ledger_entries le
                    ON le.account_id = la.id
                   AND le.company_id = la.company_id
                   AND le.voucher_type NOT IN ({quote_sql})
                WHERE la.company_id = {ph}
                  AND COALESCE(la.is_active, 1) = 1
                  AND (
                        LOWER(COALESCE(la.group_name, '')) = LOWER({ph})
                        OR la.account_name = {ph}
                      )
                GROUP BY la.id, la.opening_balance, la.opening_balance_type
            ) sundry_balances
        """
        params: list[Any] = [
            from_date.isoformat(),
            from_date.isoformat(),
            to_date.isoformat(),
            *_QUOTE_VOUCHER_TYPES,
            company_id,
            group_name,
            group_name,
        ]
        return self._fetch_scalar(query, tuple(params))

    def _get_net_realized_sale(
        self,
        company_id: int,
        start_date: str,
        end_date: str,
    ) -> float:
        """
        Net realized sale for the selected date range.

        Formula matches Net Sales Book:
        total_sales - credit_sales - sales_returns + debtor_receipts - discount_allowed
        """
        ph = self.db._get_placeholder()

        total_sales = self._fetch_scalar(
            f"""
            SELECT COALESCE(SUM(grand_total), 0)
            FROM sales
            WHERE company_id = {ph}
              AND DATE(invoice_date) >= DATE({ph})
              AND DATE(invoice_date) <= DATE({ph})
              AND COALESCE(status, 'Active') <> 'Voided'
            """,
            (company_id, start_date, end_date),
        )
        credit_sales = self._fetch_scalar(
            f"""
            SELECT COALESCE(SUM(grand_total), 0)
            FROM sales
            WHERE company_id = {ph}
              AND {_CREDIT_SALE_SQL}
              AND DATE(invoice_date) >= DATE({ph})
              AND DATE(invoice_date) <= DATE({ph})
              AND COALESCE(status, 'Active') <> 'Voided'
            """,
            (company_id, start_date, end_date),
        )
        sales_returns = self._fetch_scalar(
            f"""
            SELECT COALESCE(SUM(grand_total), 0)
            FROM sales_returns
            WHERE company_id = {ph}
              AND DATE(return_date) >= DATE({ph})
              AND DATE(return_date) <= DATE({ph})
              AND COALESCE(status, 'Active') <> 'Voided'
            """,
            (company_id, start_date, end_date),
        )
        debtor_receipts = self._fetch_scalar(
            f"""
            SELECT COALESCE(SUM(receipt_total), 0)
            FROM (
                SELECT CASE
                    WHEN COALESCE(cr.total_amount, 0) > 0 THEN cr.total_amount
                    ELSE cr.amount
                END AS receipt_total
                FROM cash_receipts cr
                INNER JOIN ledger_accounts la
                    ON cr.received_from_account_id = la.id
                WHERE cr.company_id = {ph}
                  AND la.group_name = 'Sundry Debtors'
                  AND DATE(cr.voucher_date) >= DATE({ph})
                  AND DATE(cr.voucher_date) <= DATE({ph})
                UNION ALL
                SELECT CASE
                    WHEN COALESCE(br.total_amount, 0) > 0 THEN br.total_amount
                    ELSE br.amount
                END AS receipt_total
                FROM bank_receipts br
                INNER JOIN ledger_accounts la
                    ON br.received_from_account_id = la.id
                WHERE br.company_id = {ph}
                  AND la.group_name = 'Sundry Debtors'
                  AND DATE(br.voucher_date) >= DATE({ph})
                  AND DATE(br.voucher_date) <= DATE({ph})
            ) debtor_receipt_rows
            """,
            (
                company_id,
                start_date,
                end_date,
                company_id,
                start_date,
                end_date,
            ),
        )
        discount_allowed = self._fetch_scalar(
            f"""
            SELECT COALESCE(SUM(discount_amount), 0)
            FROM (
                SELECT COALESCE(cri.discount, 0) AS discount_amount
                FROM cash_receipt_items cri
                INNER JOIN cash_receipts cr ON cri.receipt_id = cr.id
                WHERE cr.company_id = {ph}
                  AND DATE(cr.voucher_date) >= DATE({ph})
                  AND DATE(cr.voucher_date) <= DATE({ph})
                UNION ALL
                SELECT COALESCE(bri.discount, 0) AS discount_amount
                FROM bank_receipt_items bri
                INNER JOIN bank_receipts br ON bri.receipt_id = br.id
                WHERE br.company_id = {ph}
                  AND DATE(br.voucher_date) >= DATE({ph})
                  AND DATE(br.voucher_date) <= DATE({ph})
            ) discount_rows
            """,
            (
                company_id,
                start_date,
                end_date,
                company_id,
                start_date,
                end_date,
            ),
        )

        return float(
            money_round(
                to_decimal(total_sales)
                - to_decimal(credit_sales)
                - to_decimal(sales_returns)
                + to_decimal(debtor_receipts)
                - to_decimal(discount_allowed)
            )
        )

    def _get_day_credit_sales(self, company_id: int, voucher_date: str) -> float:
        """Return today's credit sales total."""
        ph = self.db._get_placeholder()
        return self._fetch_scalar(
            f"""
            SELECT COALESCE(SUM(grand_total), 0)
            FROM sales
            WHERE company_id = {ph}
              AND {_CREDIT_SALE_SQL}
              AND DATE(invoice_date) = DATE({ph})
              AND COALESCE(status, 'Active') <> 'Voided'
            """,
            (company_id, voucher_date),
        )
