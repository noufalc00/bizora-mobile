# -*- coding: utf-8 -*-
"""
Day Book Logic Module

Builds a traditional retail Cash/Bank Day Book from ledger_entries only.
Debit means cash/bank money received. Credit means cash/bank money paid.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bizora_core.common_finance import money_round, to_decimal

try:
    from PySide6.QtCore import QCoreApplication
except Exception:  # pragma: no cover - PySide6 may be unavailable in logic tests.
    QCoreApplication = None


QUOTE_VOUCHER_TYPES = ("quotation", "estimate", "quote", "Quotation", "Estimate", "Quote")
MIN_MONEY = Decimal("0.004")
SUMMARY_ZERO_TOLERANCE = Decimal("0.005")


class DayBookLogic:
    """Business logic for the Cash/Bank Day Book report."""

    def __init__(self, db):
        """Initialize Day Book logic with a database adapter."""
        self.db = db

    def _ph(self) -> str:
        """Return the database placeholder token."""
        return self.db._get_placeholder()

    def _safe_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Run a parameterized query and return an empty list on failure."""
        try:
            return self.db.execute_query(query, params) or []
        except Exception as exc:
            print(f"[Day Book ERROR] Query failed: {exc}")
            print(f"[Day Book ERROR] SQL: {query}")
            print(f"[Day Book ERROR] Params: {params}")
            return []

    def _process_events(self) -> None:
        """Let the Qt event loop breathe during long report loops."""
        try:
            if QCoreApplication is not None:
                QCoreApplication.processEvents()
        except Exception:
            pass

    def _table_exists(self, table_name: str) -> bool:
        """Check table existence without raising UI-breaking errors."""
        try:
            ph = self._ph()
            if hasattr(self.db, "_is_sqlite") and self.db._is_sqlite():
                rows = self._safe_query(
                    f"SELECT name FROM sqlite_master WHERE type = {ph} AND name = {ph}",
                    ("table", table_name),
                )
                return bool(rows)

            rows = self._safe_query(
                f"""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_name = {ph}
                """,
                (table_name,),
            )
            return bool(rows)
        except Exception as exc:
            print(f"[Day Book] table check failed for {table_name}: {exc}")
            return False

    def _date_list(self, from_date: str, to_date: str) -> List[str]:
        """Return an inclusive ISO date list for the selected period."""
        try:
            start = datetime.strptime(str(from_date)[:10], "%Y-%m-%d").date()
            end = datetime.strptime(str(to_date)[:10], "%Y-%m-%d").date()
        except Exception:
            return [str(from_date)[:10]]

        if end < start:
            start, end = end, start

        days = []
        current = start
        while current <= end:
            days.append(current.isoformat())
            current += timedelta(days=1)
        return days

    def _quote_placeholders(self) -> str:
        """Return placeholders for quote/estimate voucher exclusion."""
        return ",".join([self._ph()] * len(QUOTE_VOUCHER_TYPES))

    def _account_placeholders(self, account_ids: Sequence[Any]) -> str:
        """Return placeholders for a cash/bank account id list."""
        return ",".join([self._ph()] * len(account_ids))

    def _is_summary_amount_zero(self, value: Any) -> bool:
        """Return whether a summary value is visually zero at two decimals."""
        return abs(to_decimal(value)) < SUMMARY_ZERO_TOLERANCE

    def _has_party_summary_activity(self, row: Dict[str, Any]) -> bool:
        """Keep only party summaries with balance or period movement."""
        return not all(
            self._is_summary_amount_zero(row.get(key))
            for key in ("opening_balance", "debit", "credit", "closing_balance")
        )

    def _day_book_sort_priority(self, row: Dict[str, Any]) -> int:
        """Return the custom display priority for final Day Book rows."""
        particulars = str(row.get("particulars") or "").strip().lower()
        row_type = str(row.get("row_type") or "").strip().lower()
        if row_type == "opening" or particulars == "daily opening balance":
            return 0
        if particulars in ("sales account", "sales"):
            return 1
        if row_type == "total" or particulars == "total":
            return 3
        if row_type == "closing_balance" or particulars in ("c/d", "closing_balance"):
            return 4
        return 2

    def _sort_day_book_entries(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort final Day Book rows by date group, business priority, and voucher."""
        def sort_key(indexed_row: Tuple[int, Dict[str, Any]]) -> Tuple[str, int, str, str, int]:
            original_index, row = indexed_row
            entry_date = str(row.get("date") or row.get("metadata", {}).get("date") or "")
            voucher_no = str(row.get("voucher_no") or "")
            particulars = str(row.get("particulars") or "")
            return (
                entry_date,
                self._day_book_sort_priority(row),
                voucher_no,
                particulars.lower(),
                original_index,
            )

        return [row for _, row in sorted(enumerate(rows), key=sort_key)]

    def _dedupe_rows_by_id(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove accidental duplicate ledger rows by physical ledger id."""
        unique_rows: List[Dict[str, Any]] = []
        seen_ids = set()
        for row in rows:
            row_id = row.get("id")
            if row_id is None or row_id not in seen_ids:
                unique_rows.append(row)
            if row_id is not None:
                seen_ids.add(row_id)
        return unique_rows

    def _get_cash_bank_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """Return active Cash and Bank ledger accounts for the company."""
        if not self._table_exists("ledger_accounts"):
            return []

        ph = self._ph()
        rows = self._safe_query(
            f"""
            SELECT id,
                   account_name,
                   account_type,
                   group_name,
                   opening_balance,
                   opening_balance_type
            FROM ledger_accounts
            WHERE company_id = {ph}
              AND COALESCE(is_active, 1) = 1
              AND (
                    LOWER(COALESCE(account_type, '')) = LOWER({ph})
                 OR LOWER(COALESCE(group_name, '')) = LOWER({ph})
                 OR LOWER(COALESCE(account_name, '')) LIKE LOWER({ph})
                 OR LOWER(COALESCE(account_name, '')) LIKE LOWER({ph})
              )
            ORDER BY account_name
            """,
            (company_id, "cash_bank", "Cash & Bank", "%cash%", "%bank%"),
        )
        return [row for row in rows if row.get("id") is not None]

    def _cash_bank_opening_before_date(self, company_id: int, from_date: str) -> float:
        """Calculate combined Cash/Bank balance before the selected date."""
        accounts = self._get_cash_bank_accounts(company_id)
        if not accounts:
            return 0.0

        opening = Decimal("0.00")
        for account in accounts:
            amount = to_decimal(account.get("opening_balance"))
            side = str(account.get("opening_balance_type") or "Dr").lower()
            opening += amount if side.startswith("dr") else -amount

        if not self._table_exists("ledger_entries"):
            return float(money_round(opening))

        account_ids = [account.get("id") for account in accounts]
        ph = self._ph()
        account_ph = self._account_placeholders(account_ids)
        quote_ph = self._quote_placeholders()
        params: Tuple[Any, ...] = tuple([company_id, *account_ids, from_date, *QUOTE_VOUCHER_TYPES])
        rows = self._safe_query(
            f"""
            SELECT COALESCE(SUM(debit), 0) AS debit_total,
                   COALESCE(SUM(credit), 0) AS credit_total
            FROM ledger_entries
            WHERE company_id = {ph}
              AND account_id IN ({account_ph})
              AND DATE(voucher_date) < DATE({ph})
              AND voucher_type NOT IN ({quote_ph})
            """,
            params,
        )
        if rows:
            opening += to_decimal(rows[0].get("debit_total"))
            opening -= to_decimal(rows[0].get("credit_total"))
        return float(money_round(opening))

    def _fetch_cash_bank_voucher_lines(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        cash_bank_account_ids: Sequence[Any],
    ) -> List[Dict[str, Any]]:
        """Fetch ledger lines only for vouchers that include Cash/Bank movement."""
        if not cash_bank_account_ids or not self._table_exists("ledger_entries"):
            return []

        ph = self._ph()
        account_ph = self._account_placeholders(cash_bank_account_ids)
        quote_ph = self._quote_placeholders()
        params: Tuple[Any, ...] = tuple(
            [
                *cash_bank_account_ids,
                from_date,
                to_date,
                *QUOTE_VOUCHER_TYPES,
                company_id,
                from_date,
                to_date,
                *QUOTE_VOUCHER_TYPES,
            ]
        )
        rows = self._safe_query(
            f"""
            SELECT le.id,
                   le.voucher_date,
                   le.voucher_no,
                   le.voucher_type,
                   le.voucher_id,
                   le.account_id,
                   le.contra_account_id,
                   COALESCE(le.narration, '') AS narration,
                   COALESCE(le.debit, 0) AS debit,
                   COALESCE(le.credit, 0) AS credit,
                   COALESCE(la.account_name, '') AS account_name,
                   COALESCE(la.account_type, '') AS account_type,
                   COALESCE(la.group_name, '') AS group_name
            FROM ledger_entries le
            LEFT JOIN ledger_accounts la ON la.id = le.account_id
                AND la.company_id = le.company_id
            WHERE EXISTS (
                SELECT 1
                FROM ledger_entries cb
                WHERE cb.company_id = le.company_id
                  AND cb.account_id IN ({account_ph})
                  AND DATE(cb.voucher_date) = DATE(le.voucher_date)
                  AND cb.voucher_type = le.voucher_type
                  AND cb.voucher_id = le.voucher_id
                  AND COALESCE(cb.voucher_no, '') = COALESCE(le.voucher_no, '')
                  AND DATE(cb.voucher_date) >= DATE({ph})
                  AND DATE(cb.voucher_date) <= DATE({ph})
                  AND cb.voucher_type NOT IN ({quote_ph})
            )
              AND le.company_id = {ph}
              AND DATE(le.voucher_date) >= DATE({ph})
              AND DATE(le.voucher_date) <= DATE({ph})
              AND le.voucher_type NOT IN ({quote_ph})
            ORDER BY DATE(le.voucher_date), le.voucher_type, le.voucher_no, le.voucher_id, le.id
            """,
            params,
        )
        return self._dedupe_rows_by_id(rows)

    def _fetch_all_voucher_lines(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
    ) -> List[Dict[str, Any]]:
        """Fetch every posted ledger leg for the selected Day Book period."""
        if not self._table_exists("ledger_entries"):
            return []

        ph = self._ph()
        quote_ph = self._quote_placeholders()
        rows = self._safe_query(
            f"""
            SELECT DISTINCT le.id,
                   le.voucher_date,
                   le.voucher_no,
                   le.voucher_type,
                   le.voucher_id,
                   le.account_id,
                   le.contra_account_id,
                   COALESCE(le.narration, '') AS narration,
                   COALESCE(le.debit, 0) AS debit,
                   COALESCE(le.credit, 0) AS credit,
                   COALESCE(la.account_name, '') AS account_name,
                   COALESCE(la.account_type, '') AS account_type,
                   COALESCE(la.group_name, '') AS group_name
            FROM ledger_entries le
            LEFT JOIN ledger_accounts la ON la.id = le.account_id
            WHERE le.company_id = {ph}
              AND DATE(le.voucher_date) >= DATE({ph})
              AND DATE(le.voucher_date) <= DATE({ph})
              AND le.voucher_type NOT IN ({quote_ph})
            ORDER BY DATE(le.voucher_date), le.voucher_type, le.voucher_no, le.voucher_id, le.id
            """,
            (company_id, from_date, to_date, *QUOTE_VOUCHER_TYPES),
        )
        return self._dedupe_rows_by_id(rows)

    def _voucher_key(self, row: Dict[str, Any]) -> Tuple[str, str, Any, str]:
        """Build the grouping identity for a posted voucher."""
        return (
            str(row.get("voucher_date") or "")[:10],
            str(row.get("voucher_type") or ""),
            row.get("voucher_id"),
            str(row.get("voucher_no") or ""),
        )

    def _unique_names(self, rows: Iterable[Dict[str, Any]]) -> List[str]:
        """Return account names once, preserving ledger order."""
        names: List[str] = []
        seen = set()
        for row in rows:
            name = str(row.get("account_name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key not in seen:
                names.append(name)
                seen.add(key)
        return names

    def _is_tax_or_rounding_name(self, name: str) -> bool:
        """Identify tax and rounding rows that should not dominate particulars."""
        lowered = name.lower()
        noisy_tokens = ("gst", "cgst", "sgst", "igst", "cess", "tax", "round", "discount")
        return any(token in lowered for token in noisy_tokens)

    def _select_particulars(self, lines: List[Dict[str, Any]], cash_bank_ids: set) -> str:
        """Choose the opposite account description for the Day Book row."""
        opposite_rows = [row for row in lines if row.get("account_id") not in cash_bank_ids]
        if not opposite_rows:
            narration = next((str(row.get("narration") or "").strip() for row in lines if row.get("narration")), "")
            return narration or "Cash/Bank Contra"

        party_rows = [
            row for row in opposite_rows
            if str(row.get("account_type") or "").lower() == "party"
            or "sundry" in str(row.get("group_name") or "").lower()
        ]
        if party_rows:
            return ", ".join(self._unique_names(party_rows)) or "Party Account"

        business_rows = [
            row for row in opposite_rows
            if any(
                token in str(row.get("account_name") or "").lower()
                for token in ("sales", "purchase", "expense", "income")
            )
        ]
        if business_rows:
            return ", ".join(self._unique_names(business_rows)) or "Ledger Account"

        clean_rows = [
            row for row in opposite_rows
            if not self._is_tax_or_rounding_name(str(row.get("account_name") or ""))
        ]
        names = self._unique_names(clean_rows or opposite_rows)
        if len(names) > 3:
            return ", ".join(names[:3]) + " ..."
        return ", ".join(names) or "Ledger Account"

    def _make_row(
        self,
        date: str,
        particulars: str,
        debit: Any = 0.0,
        credit: Any = 0.0,
        voucher_no: str = "",
        row_type: str = "transaction",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create one normalized Day Book row."""
        debit_amount = money_round(to_decimal(debit))
        credit_amount = money_round(to_decimal(credit))
        row_metadata = metadata or {}
        return {
            "date": date,
            "voucher_no": voucher_no or "",
            "particulars": particulars or "",
            "debit": float(debit_amount),
            "credit": float(credit_amount),
            "amount": float(money_round(max(abs(debit_amount), abs(credit_amount)))),
            "row_type": row_type,
            "metadata": row_metadata,
            "entry_type": row_type,
            "party_name": particulars or "",
            "narration": "",
            "source": "",
            "drilldown_mode": row_metadata.get("drilldown_mode", ""),
            "voucher_type": row_metadata.get("voucher_type", ""),
            "voucher_id": row_metadata.get("voucher_id"),
        }

    def _display_voucher_type(self, voucher_type: Any) -> str:
        """Return a compact voucher type label for UI and export output."""
        raw_value = str(voucher_type or "").strip()
        if not raw_value:
            return ""
        return raw_value.replace("_", " ").replace("-", " ").title()

    def _is_debtor_row(self, row: Dict[str, Any]) -> bool:
        """Identify Sundry Debtors/customer rows for optional summarisation."""
        group_name = str(row.get("group_name") or "").lower()
        account_type = str(row.get("account_type") or "").lower()
        account_name = str(row.get("particulars") or row.get("account_name") or "").lower()
        return (
            "sundry debtor" in group_name
            or "sundry debtor" in account_type
            or account_type == "customer"
            or "customer" in group_name
            or account_name == "sundry debtors"
        )

    def _is_creditor_row(self, row: Dict[str, Any]) -> bool:
        """Identify Sundry Creditors/supplier rows for optional summarisation."""
        group_name = str(row.get("group_name") or "").lower()
        account_type = str(row.get("account_type") or "").lower()
        account_name = str(row.get("particulars") or row.get("account_name") or "").lower()
        return (
            "sundry creditor" in group_name
            or "sundry creditor" in account_type
            or account_type == "supplier"
            or "supplier" in group_name
            or account_name == "sundry creditors"
        )

    def _merged_voucher_type(self, rows: Sequence[Dict[str, Any]]) -> str:
        """Return the concrete voucher type carried by a summary bucket."""
        for row in rows:
            voucher_type = str(row.get("voucher_type") or "").strip()
            if voucher_type:
                return voucher_type
        return ""

    def _summary_group_key(self, row: Dict[str, Any], particulars: str = "") -> Tuple[str, str, str]:
        """Build the date, account, and voucher type key used by summaries."""
        account_name = str(particulars or row.get("account_name") or row.get("particulars") or "").strip()
        voucher_type = str(row.get("voucher_type") or "").strip()
        return (str(row.get("date") or ""), account_name, voucher_type)

    def _summary_voucher_key(self, row: Dict[str, Any]) -> Tuple[str, str, Any, str]:
        """Build the voucher identity used for summary-only cleanup."""
        return (
            str(row.get("date") or ""),
            str(row.get("voucher_type") or ""),
            row.get("voucher_id"),
            str(row.get("voucher_no") or ""),
        )

    def _summary_account_key(self, row: Dict[str, Any]) -> Tuple[Any, str, str]:
        """Build a stable account identity for same-voucher netting."""
        account_name = str(row.get("account_name") or row.get("particulars") or "").strip()
        return (row.get("account_id"), account_name.lower(), str(row.get("voucher_type") or ""))

    def _is_tax_row(self, row: Dict[str, Any]) -> bool:
        """Identify GST/CESS tax rows that can be absorbed during summaries."""
        group_name = str(row.get("group_name") or "").lower()
        account_type = str(row.get("account_type") or "").lower()
        account_name = str(row.get("account_name") or row.get("particulars") or "").lower()
        tax_tokens = ("cgst", "sgst", "igst", "cess")
        return (
            "duties" in group_name
            or "tax" in group_name
            or "tax" in account_type
            or any(token in account_name for token in tax_tokens)
        )

    def _is_cash_bank_row(self, row: Dict[str, Any], cash_bank_ids: set) -> bool:
        """Return whether a ledger line belongs to the Day Book cash/bank base."""
        account_id = row.get("account_id")
        if account_id in cash_bank_ids:
            return True

        account_name = str(row.get("account_name") or row.get("particulars") or "").strip().lower()
        account_type = str(row.get("account_type") or "").strip().lower()
        group_name = str(row.get("group_name") or "").strip().lower()
        return (
            account_name in {"cash account", "bank account"}
            or account_type == "cash_bank"
            or group_name == "cash & bank"
        )

    def _cash_drawer_display_lines(
        self,
        voucher_lines: Sequence[Dict[str, Any]],
        cash_bank_ids: set,
    ) -> List[Dict[str, Any]]:
        """Hide cash/bank legs and show opposing accounts from a cash drawer view."""
        cash_lines = [
            row for row in voucher_lines
            if self._is_cash_bank_row(row, cash_bank_ids)
        ]
        if not cash_lines:
            return [dict(row) for row in voucher_lines]

        cash_debit = sum(to_decimal(row.get("debit")) for row in cash_lines)
        cash_credit = sum(to_decimal(row.get("credit")) for row in cash_lines)
        cash_movement = money_round(cash_debit - cash_credit)
        if abs(cash_movement) <= MIN_MONEY:
            return []

        opposing_lines = [
            row for row in voucher_lines
            if not self._is_cash_bank_row(row, cash_bank_ids)
        ]
        if not opposing_lines:
            return []

        display_rows: List[Tuple[Dict[str, Any], Decimal]] = []
        for row in opposing_lines:
            debit = to_decimal(row.get("debit"))
            credit = to_decimal(row.get("credit"))
            contribution = credit - debit if cash_movement > 0 else debit - credit
            if contribution > MIN_MONEY:
                display_rows.append((row, money_round(contribution)))

        if not display_rows:
            display_rows = [
                (row, money_round(abs(to_decimal(row.get("debit")) - to_decimal(row.get("credit")))))
                for row in opposing_lines
            ]
            display_rows = [(row, amount) for row, amount in display_rows if amount > MIN_MONEY]

        if not display_rows:
            return []

        target_total = money_round(abs(cash_movement))
        source_total = money_round(sum(amount for _, amount in display_rows))
        scale = target_total / source_total if source_total > MIN_MONEY else Decimal("1")
        prepared_rows: List[Dict[str, Any]] = []
        running_total = Decimal("0.00")

        for index, (row, source_amount) in enumerate(display_rows):
            row_copy = dict(row)
            if index == len(display_rows) - 1:
                display_amount = money_round(target_total - running_total)
            else:
                display_amount = money_round(source_amount * scale)
                running_total += display_amount

            if display_amount <= MIN_MONEY:
                continue

            if cash_movement > 0:
                row_copy["debit"] = float(display_amount)
                row_copy["credit"] = 0.0
            else:
                row_copy["debit"] = 0.0
                row_copy["credit"] = float(display_amount)
            row_copy["amount"] = float(display_amount)
            prepared_rows.append(row_copy)

        return prepared_rows

    def _voucher_trade_kind(self, voucher_type: Any) -> str:
        """Classify a voucher type for summary tax absorption."""
        normalized_type = str(voucher_type or "").lower().replace("_", " ").replace("-", " ")
        if "sales return" in normalized_type or "sale return" in normalized_type:
            return "sales_return"
        if "purchase return" in normalized_type:
            return "purchase_return"
        if "sales" in normalized_type or normalized_type.startswith("sale"):
            return "sales"
        if "purchase" in normalized_type:
            return "purchase"
        return ""

    def _is_matching_trading_row(self, row: Dict[str, Any], trade_kind: str) -> bool:
        """Return whether a row is the main sales/purchase account for a voucher."""
        if not trade_kind or self._is_tax_row(row):
            return False

        group_name = str(row.get("group_name") or "").lower()
        account_type = str(row.get("account_type") or "").lower()
        account_name = str(row.get("account_name") or row.get("particulars") or "").lower()
        haystack = f"{group_name} {account_type} {account_name}"

        if trade_kind == "sales_return":
            return "sales return" in haystack or "sale return" in haystack
        if trade_kind == "purchase_return":
            return "purchase return" in haystack
        if trade_kind == "sales":
            return "sales" in haystack and "return" not in haystack
        if trade_kind == "purchase":
            return "purchase" in haystack and "return" not in haystack
        return False

    def _find_tax_absorption_target(self, voucher_rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find the same-voucher trading row that should receive tax amounts."""
        if not voucher_rows:
            return None

        trade_kind = self._voucher_trade_kind(voucher_rows[0].get("voucher_type"))
        candidates = [row for row in voucher_rows if self._is_matching_trading_row(row, trade_kind)]
        if not candidates:
            return None

        def candidate_score(row: Dict[str, Any]) -> Tuple[int, int]:
            account_name = str(row.get("account_name") or row.get("particulars") or "").lower()
            group_name = str(row.get("group_name") or "").lower()
            exact_label = {
                "sales": "sales account",
                "sales_return": "sales return account",
                "purchase": "purchase account",
                "purchase_return": "purchase return account",
            }.get(trade_kind, "")
            exact_score = 1 if exact_label and exact_label in account_name else 0
            group_score = 1 if "account" in group_name or "return" in group_name else 0
            return (exact_score, group_score)

        return sorted(candidates, key=candidate_score, reverse=True)[0]

    def _absorb_tax_rows_for_summary(self, voucher_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Hide same-voucher tax rows after adding them to a trading account."""
        tax_rows = [row for row in voucher_rows if self._is_tax_row(row)]
        if not tax_rows:
            return [dict(row) for row in voucher_rows]

        target_row = self._find_tax_absorption_target(voucher_rows)
        if target_row is None:
            return [dict(row) for row in voucher_rows]

        target_copy = dict(target_row)
        debit_total = money_round(
            to_decimal(target_copy.get("debit")) + sum(to_decimal(row.get("debit")) for row in tax_rows)
        )
        credit_total = money_round(
            to_decimal(target_copy.get("credit")) + sum(to_decimal(row.get("credit")) for row in tax_rows)
        )
        target_copy["debit"] = float(debit_total)
        target_copy["credit"] = float(credit_total)
        target_copy["amount"] = float(money_round(max(abs(debit_total), abs(credit_total))))
        target_copy["metadata"] = {
            **dict(target_copy.get("metadata") or {}),
            "tax_absorbed": True,
            "tax_row_count": len(tax_rows),
        }

        cleaned_rows: List[Dict[str, Any]] = []
        target_inserted = False
        for row in voucher_rows:
            if self._is_tax_row(row):
                continue
            if row is target_row and not target_inserted:
                cleaned_rows.append(target_copy)
                target_inserted = True
            else:
                cleaned_rows.append(dict(row))
        return cleaned_rows

    def _net_same_voucher_account_rows(self, voucher_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Net same-account debit and credit movement inside one voucher."""
        netted_rows: List[Dict[str, Any]] = []
        row_index: Dict[Tuple[Any, str, str], Dict[str, Any]] = {}

        for row in voucher_rows:
            key = self._summary_account_key(row)
            existing_row = row_index.get(key)
            if existing_row is None:
                row_copy = dict(row)
                row_index[key] = row_copy
                netted_rows.append(row_copy)
                continue

            existing_row["debit"] = float(
                money_round(to_decimal(existing_row.get("debit")) + to_decimal(row.get("debit")))
            )
            existing_row["credit"] = float(
                money_round(to_decimal(existing_row.get("credit")) + to_decimal(row.get("credit")))
            )
            existing_row["amount"] = float(
                money_round(
                    max(
                        abs(to_decimal(existing_row.get("debit"))),
                        abs(to_decimal(existing_row.get("credit"))),
                    )
                )
            )

        cleaned_rows: List[Dict[str, Any]] = []
        for row in netted_rows:
            net_amount = money_round(to_decimal(row.get("debit")) - to_decimal(row.get("credit")))
            if abs(net_amount) <= MIN_MONEY:
                continue

            row["debit"] = float(net_amount if net_amount > 0 else Decimal("0.00"))
            row["credit"] = float(abs(net_amount) if net_amount < 0 else Decimal("0.00"))
            row["amount"] = float(money_round(abs(net_amount)))
            cleaned_rows.append(row)
        return cleaned_rows

    def _prepare_summary_entry_rows(self, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply voucher-scoped tax absorption and netting before summaries."""
        voucher_buckets: Dict[Tuple[str, str, Any, str], List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            voucher_buckets[self._summary_voucher_key(row)].append(row)

        prepared_rows: List[Dict[str, Any]] = []
        for voucher_rows in voucher_buckets.values():
            absorbed_rows = self._absorb_tax_rows_for_summary(voucher_rows)
            prepared_rows.extend(self._net_same_voucher_account_rows(absorbed_rows))
        return prepared_rows

    def _merge_transaction_rows(
        self,
        rows: Sequence[Dict[str, Any]],
        particulars: str,
        force_summary: bool = False,
    ) -> Dict[str, Any]:
        """Merge transaction rows while preserving cash-neutral display totals."""
        first_row = rows[0]
        debit_total = money_round(sum(to_decimal(row.get("debit")) for row in rows))
        credit_total = money_round(sum(to_decimal(row.get("credit")) for row in rows))
        merged_row = dict(first_row)
        merged_row.update(
            {
                "voucher_no": "" if force_summary or len(rows) > 1 else first_row.get("voucher_no", ""),
                "particulars": particulars,
                "party_name": particulars,
                "debit": float(debit_total),
                "credit": float(credit_total),
                "amount": float(money_round(max(abs(debit_total), abs(credit_total)))),
                "voucher_type": self._merged_voucher_type(rows),
                "voucher_id": None if len(rows) > 1 else first_row.get("voucher_id"),
                "drilldown_mode": "open_book" if force_summary or len(rows) > 1 else first_row.get("drilldown_mode", ""),
                "metadata": {
                    "summarized": force_summary or len(rows) > 1,
                    "source_count": len(rows),
                },
            }
        )
        return merged_row

    def _summarize_transaction_rows(
        self,
        rows: List[Dict[str, Any]],
        summarize_entries: bool,
        summarize_debtors: bool,
        summarize_creditors: bool = False,
    ) -> List[Dict[str, Any]]:
        """Apply optional Day Book summaries to transaction rows only."""
        if not summarize_entries and not summarize_debtors and not summarize_creditors:
            return rows

        debtor_buckets: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        creditor_buckets: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        remaining_rows: List[Dict[str, Any]] = []
        for row in rows:
            if summarize_debtors and self._is_debtor_row(row):
                debtor_buckets[self._summary_group_key(row, "Sundry Debtors")].append(row)
            elif summarize_creditors and self._is_creditor_row(row):
                creditor_buckets[self._summary_group_key(row, "Sundry Creditors")].append(row)
            else:
                remaining_rows.append(row)

        summarized_rows: List[Dict[str, Any]] = []
        for debtor_rows in debtor_buckets.values():
            summarized_rows.append(self._merge_transaction_rows(debtor_rows, "Sundry Debtors", force_summary=True))
        for creditor_rows in creditor_buckets.values():
            summarized_rows.append(self._merge_transaction_rows(creditor_rows, "Sundry Creditors", force_summary=True))

        if summarize_entries:
            entry_buckets: Dict[Tuple[str, str, str, Any, str], List[Dict[str, Any]]] = defaultdict(list)
            for row in self._prepare_summary_entry_rows(remaining_rows):
                account_name = str(row.get("account_name") or row.get("particulars") or "").strip()
                key = (
                    str(row.get("date") or ""),
                    account_name,
                    str(row.get("voucher_type") or ""),
                    row.get("voucher_id"),
                    str(row.get("voucher_no") or ""),
                )
                entry_buckets[key].append(row)

            for (_, particulars, _, _, _), grouped_rows in entry_buckets.items():
                if len(grouped_rows) > 1:
                    summarized_rows.append(self._merge_transaction_rows(grouped_rows, particulars, force_summary=True))
                else:
                    summarized_rows.extend(grouped_rows)
        else:
            summarized_rows.extend(remaining_rows)

        return sorted(
            summarized_rows,
            key=lambda row: (
                str(row.get("date") or ""),
                str(row.get("voucher_type") or ""),
                str(row.get("voucher_no") or ""),
                str(row.get("particulars") or ""),
            ),
        )

    def _build_all_transaction_rows(
        self,
        ledger_lines: Sequence[Dict[str, Any]],
        cash_bank_ids: set,
        summarize_entries: bool,
        summarize_debtors: bool,
        summarize_creditors: bool = False,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build display rows from every ledger leg in the selected period."""
        date_buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        voucher_buckets: Dict[Tuple[str, str, Any, str], List[Dict[str, Any]]] = defaultdict(list)
        for line in ledger_lines:
            voucher_buckets[self._voucher_key(line)].append(line)

        for index, voucher_lines in enumerate(voucher_buckets.values()):
            if index % 50 == 0:
                self._process_events()

            display_lines = self._cash_drawer_display_lines(voucher_lines, cash_bank_ids)
            for line in display_lines:
                entry_date = str(line.get("voucher_date") or "")[:10]
                particulars = str(line.get("account_name") or "").strip()
                if not particulars:
                    particulars = str(line.get("narration") or "").strip() or "Ledger Account"

                row = self._make_row(
                    entry_date,
                    particulars,
                    debit=line.get("debit", 0.0),
                    credit=line.get("credit", 0.0),
                    voucher_no=str(line.get("voucher_no") or ""),
                    row_type="transaction",
                    metadata={
                        "drilldown_mode": "open_voucher",
                        "voucher_type": self._display_voucher_type(line.get("voucher_type")),
                        "raw_voucher_type": line.get("voucher_type"),
                        "voucher_id": line.get("voucher_id"),
                        "date": entry_date,
                    },
                )
                row["account_id"] = line.get("account_id")
                row["account_name"] = particulars
                row["account_type"] = line.get("account_type", "")
                row["group_name"] = line.get("group_name", "")
                row["source_debit"] = float(money_round(to_decimal(line.get("debit"))))
                row["source_credit"] = float(money_round(to_decimal(line.get("credit"))))
                date_buckets[entry_date].append(row)

        for entry_date, rows in list(date_buckets.items()):
            date_buckets[entry_date] = self._summarize_transaction_rows(
                rows,
                summarize_entries,
                summarize_debtors,
                summarize_creditors,
            )
        return date_buckets

    def _aggregate_transaction_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge duplicate transaction rows by date, voucher number, and particulars."""
        aggregated_rows: List[Dict[str, Any]] = []
        row_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        for index, row in enumerate(rows):
            if index % 100 == 0:
                self._process_events()

            if row.get("row_type") != "transaction":
                aggregated_rows.append(row)
                continue

            key = (
                str(row.get("date") or ""),
                str(row.get("voucher_no") or ""),
                str(row.get("particulars") or ""),
            )
            existing_row = row_index.get(key)
            if existing_row is None:
                row_copy = dict(row)
                row_copy["debit"] = float(money_round(to_decimal(row_copy.get("debit"))))
                row_copy["credit"] = float(money_round(to_decimal(row_copy.get("credit"))))
                row_copy["amount"] = float(
                    money_round(
                        max(
                            abs(to_decimal(row_copy.get("debit"))),
                            abs(to_decimal(row_copy.get("credit"))),
                        )
                    )
                )
                row_index[key] = row_copy
                aggregated_rows.append(row_copy)
                continue

            debit_total = money_round(to_decimal(existing_row.get("debit")) + to_decimal(row.get("debit")))
            credit_total = money_round(to_decimal(existing_row.get("credit")) + to_decimal(row.get("credit")))
            existing_row["debit"] = float(debit_total)
            existing_row["credit"] = float(credit_total)
            existing_row["amount"] = float(money_round(max(abs(debit_total), abs(credit_total))))

        return aggregated_rows

    def _build_transaction_rows(
        self,
        grouped_lines: Dict[Tuple[str, str, Any, str], List[Dict[str, Any]]],
        cash_bank_ids: set,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Build one consolidated transaction row per cash/bank voucher."""
        date_buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for index, (key, lines) in enumerate(grouped_lines.items()):
            if index % 50 == 0:
                self._process_events()

            entry_date, voucher_type, voucher_id, voucher_no = key
            cash_lines = [row for row in lines if row.get("account_id") in cash_bank_ids]
            cash_debit = sum(to_decimal(row.get("debit")) for row in cash_lines)
            cash_credit = sum(to_decimal(row.get("credit")) for row in cash_lines)
            net_amount = money_round(cash_debit - cash_credit)
            if abs(net_amount) <= MIN_MONEY:
                continue

            debit = net_amount if net_amount > 0 else Decimal("0.00")
            credit = abs(net_amount) if net_amount < 0 else Decimal("0.00")
            particulars = self._select_particulars(lines, cash_bank_ids)
            date_buckets[entry_date].append(
                self._make_row(
                    entry_date,
                    particulars,
                    debit=debit,
                    credit=credit,
                    voucher_no=voucher_no,
                    row_type="transaction",
                    metadata={
                        "drilldown_mode": "open_voucher",
                        "voucher_type": voucher_type,
                        "voucher_id": voucher_id,
                        "date": entry_date,
                    },
                )
            )
        for entry_date, rows in list(date_buckets.items()):
            date_buckets[entry_date] = self._aggregate_transaction_rows(rows)
        return date_buckets

    def get_day_book_daily_sections(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build daily Cash/Bank Day Book sections with opening, totals, and c/d."""
        try:
            options = options or {}
            summarize_entries = bool(options.get("summarize_entries", True))
            summarize_debtors = bool(options.get("summarize_debtors", False))
            summarize_creditors = bool(options.get("summarize_creditors", False))
            accounts = self._get_cash_bank_accounts(company_id)
            cash_bank_ids = {account.get("id") for account in accounts if account.get("id") is not None}
            all_ledger_lines = self._fetch_all_voucher_lines(company_id, from_date, to_date)
            cash_ledger_lines = [
                row for row in all_ledger_lines
                if row.get("account_id") in cash_bank_ids
            ]
            grouped_cash_lines: Dict[Tuple[str, str, Any, str], List[Dict[str, Any]]] = defaultdict(list)
            for row in cash_ledger_lines:
                grouped_cash_lines[self._voucher_key(row)].append(row)

            cash_transaction_buckets = self._build_transaction_rows(grouped_cash_lines, cash_bank_ids)
            transaction_buckets = self._build_all_transaction_rows(
                all_ledger_lines,
                cash_bank_ids,
                summarize_entries,
                summarize_debtors,
                summarize_creditors,
            )
            sections = []
            current_opening = to_decimal(self._cash_bank_opening_before_date(company_id, from_date))

            for day_index, entry_date in enumerate(self._date_list(from_date, to_date)):
                if day_index % 10 == 0:
                    self._process_events()

                rows: List[Dict[str, Any]] = [
                    self._make_row(
                        entry_date,
                        "Daily Opening Balance",
                        debit=current_opening if current_opening >= 0 else Decimal("0.00"),
                        credit=abs(current_opening) if current_opening < 0 else Decimal("0.00"),
                        row_type="opening",
                        metadata={"date": entry_date},
                    )
                ]
                rows.extend(transaction_buckets.get(entry_date, []))

                debit_total = money_round(sum(to_decimal(row.get("debit")) for row in rows))
                credit_total = money_round(sum(to_decimal(row.get("credit")) for row in rows))
                cash_rows = cash_transaction_buckets.get(entry_date, [])
                cash_debit = sum(to_decimal(row.get("debit")) for row in cash_rows)
                cash_credit = sum(to_decimal(row.get("credit")) for row in cash_rows)
                closing = money_round(current_opening + cash_debit - cash_credit)

                rows.append(self._make_row(entry_date, "TOTAL", debit=debit_total, credit=credit_total, row_type="total"))
                rows.append(
                    self._make_row(
                        entry_date,
                        "c/d",
                        debit=closing if closing >= 0 else Decimal("0.00"),
                        credit=abs(closing) if closing < 0 else Decimal("0.00"),
                        row_type="closing_balance",
                        metadata={"closing_balance": float(closing), "date": entry_date},
                    )
                )

                sections.append(
                    {
                        "date": entry_date,
                        "opening_balance": float(money_round(current_opening)),
                        "rows": rows,
                        "day_debit_total": float(debit_total),
                        "day_credit_total": float(credit_total),
                        "transaction_debit_total": float(money_round(cash_debit)),
                        "transaction_credit_total": float(money_round(cash_credit)),
                        "closing_balance": float(closing),
                    }
                )
                current_opening = closing

            return {"success": True, "sections": sections, "message": f"Built {len(sections)} day sections"}
        except Exception as exc:
            print(f"[Day Book ERROR] Cash/Bank Day Book build failed: {exc}")
            return {"success": False, "sections": [], "message": str(exc)}

    def _flatten_sections(self, sections: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flatten daily sections into UI/export rows."""
        rows: List[Dict[str, Any]] = []
        for section in sections:
            rows.extend(section.get("rows", []))
        return rows

    def get_day_book_entries(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        summarize_entries: bool = True,
        summarize_debtors: bool = False,
        summarize_creditors: bool = False,
    ) -> Dict[str, Any]:
        """Return flattened Cash/Bank Day Book rows for the UI."""
        result = self.get_day_book_daily_sections(
            company_id,
            from_date,
            to_date,
            {
                "summarize_entries": summarize_entries,
                "summarize_debtors": summarize_debtors,
                "summarize_creditors": summarize_creditors,
            },
        )
        if not result.get("success"):
            return {"success": False, "data": [], "message": result.get("message", "Failed to load Day Book")}
        rows = self._sort_day_book_entries(self._flatten_sections(result.get("sections", [])))
        return {"success": True, "data": rows, "message": f"Retrieved {len(rows)} Day Book rows"}

    def get_day_book_summary(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        summarize_entries: bool = True,
        summarize_debtors: bool = False,
        summarize_creditors: bool = False,
    ) -> Dict[str, Any]:
        """Return summary totals for the Cash/Bank Day Book strip."""
        sections_result = self.get_day_book_daily_sections(
            company_id,
            from_date,
            to_date,
            {
                "summarize_entries": summarize_entries,
                "summarize_debtors": summarize_debtors,
                "summarize_creditors": summarize_creditors,
            },
        )
        sections = sections_result.get("sections", []) if sections_result.get("success") else []
        transaction_debit = sum(to_decimal(section.get("transaction_debit_total")) for section in sections)
        transaction_credit = sum(to_decimal(section.get("transaction_credit_total")) for section in sections)
        opening_balance = sections[0].get("opening_balance", 0.0) if sections else 0.0
        closing_balance = sections[-1].get("closing_balance", 0.0) if sections else 0.0
        summary = {
            "opening_balance": float(money_round(opening_balance)),
            "day_debit_total": float(money_round(transaction_debit)),
            "day_credit_total": float(money_round(transaction_credit)),
            "cash_bank_debit_total": float(money_round(transaction_debit)),
            "cash_bank_credit_total": float(money_round(transaction_credit)),
            "closing_balance": float(money_round(closing_balance)),
            "income_credit_total": 0.0,
            "expense_debit_total": 0.0,
            "cash_sales_total": float(money_round(transaction_debit)),
            "credit_sales_total": 0.0,
            "cash_purchase_total": float(money_round(transaction_credit)),
            "credit_purchase_total": 0.0,
            "sales_return_total": 0.0,
            "purchase_return_total": 0.0,
        }
        return {"success": True, "data": summary, "message": "Summary loaded"}

    def get_voucher_ledger_lines(
        self,
        company_id: int,
        voucher_type: str,
        voucher_id: Any = None,
        voucher_no: str = "",
    ) -> Dict[str, Any]:
        """Return ledger lines for the selected non-quote voucher."""
        if not self._table_exists("ledger_entries"):
            return {"success": True, "data": [], "message": "No ledger_entries table"}

        ph = self._ph()
        quote_ph = self._quote_placeholders()
        params: List[Any] = [company_id, voucher_type, *QUOTE_VOUCHER_TYPES]
        where = f"le.company_id = {ph} AND LOWER(le.voucher_type) = LOWER({ph}) AND le.voucher_type NOT IN ({quote_ph})"
        if voucher_id is not None:
            where += f" AND le.voucher_id = {ph}"
            params.append(voucher_id)
        elif voucher_no:
            where += f" AND le.voucher_no = {ph}"
            params.append(voucher_no)

        rows = self._safe_query(
            f"""
            SELECT DISTINCT le.id,
                   le.voucher_date,
                   le.voucher_type,
                   le.voucher_no,
                   COALESCE(la.account_name, '') AS account_name,
                   COALESCE(le.narration, '') AS narration,
                   COALESCE(le.debit, 0) AS debit,
                   COALESCE(le.credit, 0) AS credit
            FROM ledger_entries le
            LEFT JOIN ledger_accounts la ON la.id = le.account_id
            WHERE {where}
            ORDER BY le.id
            """,
            tuple(params),
        )
        return {"success": True, "data": rows, "message": f"Loaded {len(rows)} ledger lines"}

    def get_debitor_summary(self, company_id: int, from_date: str, to_date: str) -> Dict[str, Any]:
        """Return debtor summaries for the existing drilldown dialog."""
        return self._party_summary(company_id, from_date, to_date, "Sundry Debtors")

    def get_creditor_summary(self, company_id: int, from_date: str, to_date: str) -> Dict[str, Any]:
        """Return creditor summaries for the existing drilldown dialog."""
        return self._party_summary(company_id, from_date, to_date, "Sundry Creditors")

    def _party_summary(self, company_id: int, from_date: str, to_date: str, group_name: str) -> Dict[str, Any]:
        """Build a date-aware account movement summary for a party group."""
        if not self._table_exists("ledger_accounts"):
            return {"success": True, "data": [], "message": "No ledger_accounts table"}

        ph = self._ph()
        quote_ph = self._quote_placeholders()
        rows = self._safe_query(
            f"""
            SELECT la.account_name AS party_name,
                   COALESCE(la.opening_balance, 0) AS opening_balance,
                   COALESCE(la.opening_balance_type, 'Dr') AS opening_balance_type,
                   COALESCE(SUM(CASE WHEN DATE(le.voucher_date) < DATE({ph}) THEN le.debit ELSE 0 END), 0) AS prior_debit,
                   COALESCE(SUM(CASE WHEN DATE(le.voucher_date) < DATE({ph}) THEN le.credit ELSE 0 END), 0) AS prior_credit,
                   COALESCE(SUM(CASE WHEN DATE(le.voucher_date) >= DATE({ph}) AND DATE(le.voucher_date) <= DATE({ph}) THEN le.debit ELSE 0 END), 0) AS debit,
                   COALESCE(SUM(CASE WHEN DATE(le.voucher_date) >= DATE({ph}) AND DATE(le.voucher_date) <= DATE({ph}) THEN le.credit ELSE 0 END), 0) AS credit
            FROM ledger_accounts la
            LEFT JOIN ledger_entries le ON le.account_id = la.id
                AND le.company_id = la.company_id
                AND le.voucher_type NOT IN ({quote_ph})
            WHERE la.company_id = {ph}
              AND LOWER(COALESCE(la.group_name, '')) = LOWER({ph})
            GROUP BY la.id, la.account_name, la.opening_balance, la.opening_balance_type
            ORDER BY la.account_name
            """,
            (
                from_date,
                from_date,
                from_date,
                to_date,
                from_date,
                to_date,
                *QUOTE_VOUCHER_TYPES,
                company_id,
                group_name,
            ),
        )
        filtered_rows = []
        for row in rows:
            account_opening = to_decimal(row.get("opening_balance"))
            opening_type = str(row.get("opening_balance_type") or "Dr").strip().lower()
            opening = -account_opening if opening_type.startswith("cr") else account_opening
            opening += to_decimal(row.get("prior_debit"))
            opening -= to_decimal(row.get("prior_credit"))
            debit = to_decimal(row.get("debit"))
            credit = to_decimal(row.get("credit"))
            row["closing_balance"] = float(money_round(opening + debit - credit))
            row["opening_balance"] = float(money_round(opening))
            row["debit"] = float(money_round(debit))
            row["credit"] = float(money_round(credit))
            if self._has_party_summary_activity(row):
                filtered_rows.append(row)
        return {"success": True, "data": filtered_rows, "message": f"Loaded {len(filtered_rows)} accounts"}

    def diagnose_sources(self, company_id: int, from_date: str, to_date: str) -> None:
        """Print a concise diagnostic summary for Day Book loading."""
        result = self.get_day_book_daily_sections(company_id, from_date, to_date)
        sections = result.get("sections", []) if result.get("success") else []
        print("[Day Book Diagnose] ========== START DIAGNOSIS ==========")
        print(f"[Day Book Diagnose] company_id={company_id}, from_date={from_date}, to_date={to_date}")
        print(f"[Day Book Diagnose] sections={len(sections)}")
        for section in sections:
            print(
                f"[Day Book Diagnose] {section.get('date')}: "
                f"opening={section.get('opening_balance')}, "
                f"receipts={section.get('transaction_debit_total')}, "
                f"payments={section.get('transaction_credit_total')}, "
                f"closing={section.get('closing_balance')}, "
                f"rows={len(section.get('rows', []))}"
            )
        print("[Day Book Diagnose] ========== END DIAGNOSIS ==========")
