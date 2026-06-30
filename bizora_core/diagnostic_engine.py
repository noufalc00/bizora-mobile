"""
Database diagnostic engine for historical accounting data fractures.

The engine performs read-only, tenant-scoped scans against ledger data and
returns structured health report rows suitable for UI display or logs.
"""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from bizora_core.common_finance import money_round, to_decimal


DiagnosticResult = Dict[str, Any]


class DiagnosticEngine:
    """Run read-only database health checks for a single company tenant."""

    HEALTHY_MESSAGE = "System Healthy"

    _HEADER_MAP: Mapping[str, Tuple[str, str, Optional[str], Optional[Sequence[str]]]] = MappingProxyType(
        {
            "sales": ("sales", "invoice_number", "status", ("Voided", "Cancelled", "Deleted")),
            "purchase": ("purchases", "purchase_number", "status", ("Voided", "Cancelled", "Deleted")),
            "sales_return": ("sales_returns", "return_no", "status", ("Voided", "Cancelled", "Deleted")),
            "purchase_return": ("purchase_returns", "return_no", "status", ("Voided", "Cancelled", "Deleted")),
            "cash_receipt": ("cash_receipts", "voucher_no", None, None),
            "cash_payment": ("cash_payments", "voucher_no", None, None),
            "bank_receipt": ("bank_receipts", "voucher_no", None, None),
            "bank_payment": ("bank_payments", "voucher_no", None, None),
            "journal": ("journal_vouchers", "voucher_no", None, None),
        }
    )
    _PDC_TYPES = ("pdc_receipt", "pdc_payment")

    def __init__(self, db: Any):
        """
        Initialize the diagnostic engine.

        Args:
            db: Application Database instance exposing execute_query and helpers.
        """
        self.db = db

    def run_full_diagnostics(self, company_id: int) -> List[DiagnosticResult]:
        """
        Run all database diagnostics for one company.

        Args:
            company_id: Active company identifier. Every query is scoped to it.

        Returns:
            List of structured result dictionaries. If no warning/error is found,
            returns a single healthy result with ``System Healthy`` message.
        """
        results: List[DiagnosticResult] = []
        try:
            tenant_id = int(company_id)
        except (TypeError, ValueError):
            return [
                self._result(
                    severity="ERROR",
                    check="Company Scope",
                    message="Diagnostic Engine Error: company_id must be a valid integer.",
                )
            ]

        self._run_check(results, "Trial Balance Check", self._check_trial_balance, tenant_id)
        self._run_check(results, "Negative Cash Check", self._check_negative_cash, tenant_id)
        self._run_check(results, "Orphaned Entries Check", self._check_orphaned_entries, tenant_id)

        if not results:
            return [
                self._result(
                    severity="HEALTHY",
                    check="Full Diagnostics",
                    message=self.HEALTHY_MESSAGE,
                )
            ]
        return results

    def _run_check(self, results: List[DiagnosticResult], check_name: str, check_func: Any, company_id: int) -> None:
        """Run one diagnostic check and convert unexpected failures into errors."""
        try:
            results.extend(check_func(company_id))
        except Exception as exc:
            results.append(
                self._result(
                    severity="ERROR",
                    check=check_name,
                    message=f"Diagnostic Engine Error: {check_name} failed: {exc}",
                )
            )

    def _check_trial_balance(self, company_id: int) -> List[DiagnosticResult]:
        """Compare company-wide ledger debit and credit totals after money rounding."""
        ph = self.db._get_placeholder()
        rows = self._execute_query(
            f"""
            SELECT COALESCE(SUM(debit), 0.0) AS total_debit,
                   COALESCE(SUM(credit), 0.0) AS total_credit
            FROM ledger_entries
            WHERE company_id = {ph}
            """,
            (company_id,),
        )
        row = rows[0] if rows else {}
        total_debit = money_round(to_decimal(row.get("total_debit") or 0))
        total_credit = money_round(to_decimal(row.get("total_credit") or 0))
        difference = money_round(total_debit - total_credit)
        if total_debit == total_credit:
            return []
        return [
            self._result(
                severity="ERROR",
                check="Trial Balance Check",
                message="Trial Balance mismatch: total ledger debits and credits do not match.",
                context={
                    "total_debit": str(total_debit),
                    "total_credit": str(total_credit),
                    "difference": str(difference),
                },
            )
        ]

    def _check_negative_cash(self, company_id: int) -> List[DiagnosticResult]:
        """Scan all cash/bank account running balances and report negative points."""
        ph = self.db._get_placeholder()
        account_rows = self._execute_query(
            f"""
            SELECT id,
                   account_name,
                   opening_balance,
                   opening_balance_type
            FROM ledger_accounts
            WHERE company_id = {ph}
              AND account_type = {ph}
              AND is_active = 1
            ORDER BY account_name, id
            """,
            (company_id, "cash_bank"),
        )
        warnings: List[DiagnosticResult] = []
        for account in account_rows or []:
            account_id = int(account.get("id") or 0)
            running_balance = self._signed_opening_balance(account)
            if running_balance < Decimal("0.00"):
                warnings.append(self._negative_cash_result(account, None, running_balance))

            entry_rows = self._execute_query(
                f"""
                SELECT id,
                       voucher_date,
                       voucher_type,
                       voucher_id,
                       voucher_no,
                       debit,
                       credit
                FROM ledger_entries
                WHERE company_id = {ph}
                  AND account_id = {ph}
                ORDER BY voucher_date, id
                """,
                (company_id, account_id),
            )
            for entry in entry_rows or []:
                running_balance = money_round(
                    running_balance
                    + to_decimal(entry.get("debit") or 0)
                    - to_decimal(entry.get("credit") or 0)
                )
                if running_balance < Decimal("0.00"):
                    warnings.append(self._negative_cash_result(account, entry, running_balance))
        return warnings

    def _check_orphaned_entries(self, company_id: int) -> List[DiagnosticResult]:
        """Find ledger entries whose voucher-specific active header is missing."""
        results: List[DiagnosticResult] = []
        for voucher_type, mapping in self._HEADER_MAP.items():
            table_name, number_column, status_column, inactive_statuses = mapping
            if not self._table_exists(table_name):
                continue
            if not self._column_exists(table_name, number_column):
                continue
            results.extend(
                self._find_missing_headers(
                    company_id,
                    voucher_type,
                    table_name,
                    number_column,
                    status_column,
                    inactive_statuses,
                )
            )

        if self._table_exists("pdc_register"):
            for voucher_type in self._PDC_TYPES:
                results.extend(self._find_missing_pdc_headers(company_id, voucher_type))
        return results

    def _find_missing_headers(
        self,
        company_id: int,
        voucher_type: str,
        table_name: str,
        number_column: str,
        status_column: Optional[str],
        inactive_statuses: Optional[Sequence[str]],
    ) -> List[DiagnosticResult]:
        """Run a voucher-type-specific orphan scan against one header table."""
        ph = self.db._get_placeholder()
        status_sql = ""
        params: List[Any] = [company_id, voucher_type, company_id]
        if status_column and inactive_statuses and self._column_exists(table_name, status_column):
            placeholders = ", ".join([ph for _ in inactive_statuses])
            status_sql = f"AND COALESCE(h.{status_column}, 'Active') NOT IN ({placeholders})"
            params.extend(inactive_statuses)

        rows = self._execute_query(
            f"""
            SELECT le.id,
                   le.voucher_type,
                   le.voucher_id,
                   le.voucher_no,
                   le.voucher_date,
                   le.account_id
            FROM ledger_entries le
            WHERE le.company_id = {ph}
              AND le.voucher_type = {ph}
              AND NOT EXISTS (
                  SELECT 1
                  FROM {table_name} h
                  WHERE h.company_id = {ph}
                    AND (
                        h.id = le.voucher_id
                        OR h.{number_column} = le.voucher_no
                    )
                    {status_sql}
              )
            ORDER BY le.voucher_date, le.id
            """,
            tuple(params),
        )
        return [self._orphan_result(row, table_name) for row in rows or []]

    def _find_missing_pdc_headers(self, company_id: int, voucher_type: str) -> List[DiagnosticResult]:
        """Find PDC ledger entries that no longer map to a cleared PDC register row."""
        ph = self.db._get_placeholder()
        rows = self._execute_query(
            f"""
            SELECT le.id,
                   le.voucher_type,
                   le.voucher_id,
                   le.voucher_no,
                   le.voucher_date,
                   le.account_id
            FROM ledger_entries le
            WHERE le.company_id = {ph}
              AND le.voucher_type = {ph}
              AND NOT EXISTS (
                  SELECT 1
                  FROM pdc_register pdc
                  WHERE pdc.company_id = {ph}
                    AND pdc.id = le.voucher_id
                    AND pdc.status = {ph}
                    AND COALESCE(pdc.linked_voucher_type, le.voucher_type) = le.voucher_type
              )
            ORDER BY le.voucher_date, le.id
            """,
            (company_id, voucher_type, company_id, "CLEARED"),
        )
        return [self._orphan_result(row, "pdc_register") for row in rows or []]

    def _signed_opening_balance(self, account: Dict[str, Any]) -> Decimal:
        """Return opening balance using Dr positive and Cr negative convention."""
        opening = money_round(to_decimal(account.get("opening_balance") or 0))
        opening_type = str(account.get("opening_balance_type") or "Dr").strip().lower()
        return opening if opening_type == "dr" else money_round(-opening)

    def _negative_cash_result(
        self,
        account: Dict[str, Any],
        entry: Optional[Dict[str, Any]],
        running_balance: Decimal,
    ) -> DiagnosticResult:
        """Build a warning result for a negative cash/bank running balance."""
        account_name = account.get("account_name") or f"Account {account.get('id')}"
        context = {
            "account_id": account.get("id"),
            "account_name": account_name,
            "running_balance": str(running_balance),
        }
        if entry:
            context.update(
                {
                    "voucher_date": entry.get("voucher_date"),
                    "voucher_type": entry.get("voucher_type"),
                    "voucher_id": entry.get("voucher_id"),
                    "voucher_no": entry.get("voucher_no"),
                    "ledger_entry_id": entry.get("id"),
                }
            )
            message = (
                f"Negative cash/bank balance detected for {account_name} "
                f"after voucher {entry.get('voucher_no') or entry.get('voucher_id')} "
                f"dated {entry.get('voucher_date')}."
            )
        else:
            message = f"Negative opening cash/bank balance detected for {account_name}."
        return self._result(
            severity="WARNING",
            check="Negative Cash Check",
            message=message,
            context=context,
        )

    def _orphan_result(self, row: Dict[str, Any], table_name: str) -> DiagnosticResult:
        """Build an error result for an orphaned ledger entry."""
        return self._result(
            severity="ERROR",
            check="Orphaned Entries Check",
            message=(
                f"Orphaned ledger entry {row.get('id')} references missing "
                f"or inactive {table_name} header."
            ),
            context={
                "ledger_entry_id": row.get("id"),
                "voucher_type": row.get("voucher_type"),
                "voucher_id": row.get("voucher_id"),
                "voucher_no": row.get("voucher_no"),
                "voucher_date": row.get("voucher_date"),
                "account_id": row.get("account_id"),
                "expected_header_table": table_name,
            },
        )

    def _table_exists(self, table_name: str) -> bool:
        """Check table availability through the configured database backend."""
        conn = self.db.connect()
        cursor = conn.cursor()
        return bool(self.db._check_table_exists(cursor, table_name))

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        """Check whether a table column exists for optional diagnostic paths."""
        if self.db._is_sqlite():
            rows = self._execute_query(f"PRAGMA table_info({table_name})")
            return any(str(row.get("name")) == column_name for row in rows or [])

        rows = self._execute_query(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            """,
            (table_name, column_name),
        )
        return bool(rows)

    def _execute_query(self, query: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Execute a required diagnostic SELECT and raise exact failures."""
        cursor = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            if self.db._is_sqlite():
                return [dict(row) for row in cursor.fetchall()]

            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as exc:
            raise RuntimeError(f"Diagnostic Engine Error: query execution failed: {exc}") from exc
        finally:
            if cursor is not None and hasattr(cursor, "close"):
                cursor.close()

    @staticmethod
    def _result(
        severity: str,
        check: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DiagnosticResult:
        """Create a normalized diagnostic result row."""
        return {
            "severity": severity,
            "check": check,
            "message": message,
            "context": context or {},
        }
