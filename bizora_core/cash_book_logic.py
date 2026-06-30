"""
Cash Book Logic Module

Computes Cash Book entirely from ledger_entries and ledger_accounts.
Does NOT query sales/purchase/voucher tables directly.

Cash Book shows all inflow/outflow transactions of the Cash Account.
"""

from typing import Dict, List, Any, Optional
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from bizora_core.common_finance import to_decimal, money_round, is_balanced, safe_add, safe_subtract


class CashBookLogic:
    """Cash Book logic for cash account transaction reporting."""

    def __init__(self, db):
        """
        Initialize cash book logic with database connection.

        Args:
            db: Database instance (db.Database)
        """
        self.db = db
        self._ledger_logic = None

    def _get_ledger_logic(self):
        """Lazy load ledger_logic."""
        if self._ledger_logic is None:
            from .ledger_logic import LedgerLogic
            self._ledger_logic = LedgerLogic(self.db)
        return self._ledger_logic

    def get_cash_book(self, company_id: int, from_date: date, to_date: date) -> Dict[str, Any]:
        """
        Return cash book data for the given date range.

        Args:
            company_id: Company ID
            from_date: Start date
            to_date: End date

        Returns:
            {
                "success": True/False,
                "message": str,
                "opening_balance": Decimal,
                "entries": [
                    {
                        "date": str,
                        "voucher_no": str,
                        "voucher_type": str,
                        "particulars": str,
                        "narration": str,
                        "debit": Decimal,
                        "credit": Decimal,
                        "running_balance": Decimal
                    },
                    ...
                ],
                "total_receipts": Decimal,
                "total_payments": Decimal,
                "closing_balance": Decimal
            }
        """
        try:
            # Step 1: Find Cash Account
            cash_account = self._find_cash_account(company_id)
            if not cash_account:
                return {
                    "success": False,
                    "message": "Cash Account not found",
                    "opening_balance": Decimal("0.00"),
                    "entries": [],
                    "total_receipts": Decimal("0.00"),
                    "total_payments": Decimal("0.00"),
                    "closing_balance": Decimal("0.00")
                }

            cash_account_id = cash_account['id']

            # Step 2: Get Opening Balance
            ledger_logic = self._get_ledger_logic()
            opening_balance_data = ledger_logic._get_account_balance_before_date_old(
                company_id, cash_account_id, from_date
            )
            opening_balance = to_decimal(opening_balance_data.get('net', 0))

            # Step 3: Fetch Ledger Entries
            entries = self._fetch_cash_entries(company_id, cash_account_id, from_date, to_date)

            # Step 4: Calculate Running Balance
            running_balance = opening_balance
            for entry in entries:
                debit = to_decimal(entry.get('debit', 0))
                credit = to_decimal(entry.get('credit', 0))
                running_balance = running_balance + debit - credit
                entry['running_balance'] = running_balance

            # Step 5: Calculate Totals
            total_receipts = sum(to_decimal(e.get('debit', 0)) for e in entries)
            total_payments = sum(to_decimal(e.get('credit', 0)) for e in entries)
            closing_balance = running_balance

            return {
                "success": True,
                "message": "Cash Book retrieved successfully",
                "opening_balance": opening_balance,
                "entries": entries,
                "total_receipts": total_receipts,
                "total_payments": total_payments,
                "closing_balance": closing_balance
            }

        except Exception as e:
            print(f"Error in get_cash_book: {e}")
            return {
                "success": False,
                "message": f"Error retrieving cash book: {str(e)}",
                "opening_balance": Decimal("0.00"),
                "entries": [],
                "total_receipts": Decimal("0.00"),
                "total_payments": Decimal("0.00"),
                "closing_balance": Decimal("0.00")
            }

    def _find_cash_account(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Find the Cash Account for the company.

        Args:
            company_id: Company ID

        Returns:
            Cash account dict or None
        """
        try:
            ph = self.db._get_placeholder()

            # Preferred: 'Cash Account'
            result = self.db.execute_query(
                f"SELECT id, account_name FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph} AND is_active = 1",
                (company_id, 'Cash Account')
            )
            if result:
                return result[0]

            # Fallback: 'Cash'
            result = self.db.execute_query(
                f"SELECT id, account_name FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph} AND is_active = 1",
                (company_id, 'Cash')
            )
            if result:
                return result[0]

            return None

        except Exception as e:
            print(f"Error finding cash account: {e}")
            return None

    def _fetch_cash_entries(self, company_id: int, cash_account_id: int,
                           from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """
        Fetch ledger entries for cash account within date range.

        Args:
            company_id: Company ID
            cash_account_id: Cash Account ID
            from_date: Start date
            to_date: End date

        Returns:
            List of entry dicts with contra account resolved
        """
        try:
            ph = self.db._get_placeholder()

            # Fetch entries for cash account
            query = f"""
                SELECT DISTINCT le.id,
                       le.voucher_date,
                       le.voucher_no,
                       le.voucher_type,
                       le.narration,
                       le.debit,
                       le.credit
                FROM ledger_entries le
                WHERE le.company_id = {ph}
                  AND le.account_id = {ph}
                  AND DATE(le.voucher_date) >= DATE({ph})
                  AND DATE(le.voucher_date) <= DATE({ph})
                  AND le.voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                ORDER BY le.voucher_date, le.id
            """
            entries = self.db.execute_query(
                query,
                (company_id, cash_account_id, str(from_date), str(to_date))
            )

            if not entries:
                return []

            # Resolve contra accounts for each entry
            result = []
            for entry in entries:
                entry_dict = dict(entry)
                # Find contra account (the other side of the double entry)
                contra_account = self._find_contra_account(
                    company_id, cash_account_id, entry['id'], entry['voucher_date'], entry['voucher_no']
                )
                entry_dict['particulars'] = contra_account if contra_account else 'Unknown'
                result.append(entry_dict)

            return result

        except Exception as e:
            print(f"Error fetching cash entries: {e}")
            return []

    def _find_contra_account(self, company_id: int, cash_account_id: int,
                           entry_id: int, voucher_date, voucher_no: str) -> Optional[str]:
        """
        Find the contra account name for a ledger entry.

        Args:
            company_id: Company ID
            cash_account_id: Cash Account ID
            entry_id: Entry ID
            voucher_date: Voucher date
            voucher_no: Voucher number

        Returns:
            Contra account name or None
        """
        try:
            ph = self.db._get_placeholder()

            # Find other entries in the same voucher (same voucher_no, same voucher_type)
            # that are NOT the cash account
            query = f"""
                SELECT DISTINCT le.account_id, la.account_name
                FROM ledger_entries le
                JOIN ledger_accounts la ON le.account_id = la.id
                WHERE le.company_id = {ph}
                  AND le.voucher_no = {ph}
                  AND le.id != {ph}
                  AND le.account_id != {ph}
                  AND le.voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                LIMIT 1
            """
            result = self.db.execute_query(
                query,
                (company_id, voucher_no, entry_id, cash_account_id)
            )

            if result:
                return result[0]['account_name']

            return None

        except Exception as e:
            print(f"Error finding contra account: {e}")
            return None
