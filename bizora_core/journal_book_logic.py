"""
Journal Book logic.
Read-only accounting book report queries for Journal vouchers.
"""

from typing import Any, Dict, List, Optional

from db import Database


def safe_float(value: Any) -> float:
    """Convert common database values to float safely."""
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class JournalBookLogic:
    """Logic for Journal Book - read-only view of Journal vouchers."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def _ph(self) -> str:
        """Get database placeholder."""
        return self.db._get_placeholder()

    def get_journal_book_data(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get Journal Book data for Journal vouchers only.

        Args:
            company_id: Company ID
            from_date: From date (YYYY-MM-DD)
            to_date: To date (YYYY-MM-DD)
            filters: Optional dict with filters (account_id, account_type, voucher_no, narration_search)

        Returns:
            List of journal voucher records with debit/credit accounts grouped
        """
        ph = self._ph()
        conditions = [f"jv.company_id = {ph}"]
        params = [company_id]

        # Date filter
        conditions.append(f"jv.voucher_date >= {ph}")
        params.append(from_date)
        conditions.append(f"jv.voucher_date <= {ph}")
        params.append(to_date)

        if filters:
            if filters.get('account_id'):
                conditions.append(f"EXISTS (SELECT 1 FROM journal_voucher_lines jvl WHERE jvl.journal_id = jv.id AND jvl.account_id = {ph})")
                params.append(filters['account_id'])
            if filters.get('account_type'):
                account_type = filters['account_type']
                if account_type == "sundry_debtors":
                    conditions.append(f"EXISTS (SELECT 1 FROM journal_voucher_lines jvl LEFT JOIN ledger_accounts la ON jvl.account_id = la.id LEFT JOIN parties p ON la.id = p.ledger_account_id WHERE jvl.journal_id = jv.id AND la.account_type = 'party' AND LOWER(p.party_type) = {ph})")
                    params.append('debtor')
                elif account_type == "sundry_creditors":
                    conditions.append(f"EXISTS (SELECT 1 FROM journal_voucher_lines jvl LEFT JOIN ledger_accounts la ON jvl.account_id = la.id LEFT JOIN parties p ON la.id = p.ledger_account_id WHERE jvl.journal_id = jv.id AND la.account_type = 'party' AND LOWER(p.party_type) = {ph})")
                    params.append('creditor')
                elif account_type == "general":
                    conditions.append(f"EXISTS (SELECT 1 FROM journal_voucher_lines jvl LEFT JOIN ledger_accounts la ON jvl.account_id = la.id WHERE jvl.journal_id = jv.id AND la.account_type <> 'party')")
            if filters.get('voucher_no'):
                conditions.append(f"jv.id = {ph}")
                params.append(filters['voucher_no'])
            if filters.get('narration_search'):
                conditions.append(f"(jv.narration LIKE {ph} OR jv.remark LIKE {ph})")
                search_term = f"%{filters['narration_search']}%"
                params.append(search_term)
                params.append(search_term)

        where_clause = " AND ".join(conditions)

        # Main query to get journal vouchers with grouped debit/credit accounts
        query = f"""
            SELECT
                jv.id AS voucher_no,
                jv.voucher_date AS date,
                jv.voucher_no,
                jv.narration,
                COALESCE(jv.remark, '') AS remark,
                (
                    SELECT GROUP_CONCAT(la.account_name)
                    FROM journal_voucher_lines jvl
                    LEFT JOIN ledger_accounts la ON jvl.account_id = la.id
                    WHERE jvl.journal_id = jv.id AND jvl.debit > 0
                    ORDER BY jvl.sl_no
                ) AS debit_accounts,
                (
                    SELECT GROUP_CONCAT(la.account_name)
                    FROM journal_voucher_lines jvl
                    LEFT JOIN ledger_accounts la ON jvl.account_id = la.id
                    WHERE jvl.journal_id = jv.id AND jvl.credit > 0
                    ORDER BY jvl.sl_no
                ) AS credit_accounts,
                (
                    SELECT COALESCE(SUM(debit), 0)
                    FROM journal_voucher_lines jvl
                    WHERE jvl.journal_id = jv.id
                ) AS amount
            FROM journal_vouchers jv
            WHERE {where_clause}
            ORDER BY jv.voucher_date ASC, jv.id ASC
        """

        results = self.db.execute_query(query, tuple(params))

        # DEBUG PRINTS
        print(f"JOURNAL ENTRY COUNT = {len(results)}")
        print(f"FILTER ACCOUNT TYPE = {filters.get('account_type', 'All') if filters else 'All'}")
        print(f"FILTER ACCOUNT = {filters.get('account_id', 'All') if filters else 'All'}")
        print(f"FILTER VOUCHER = {filters.get('voucher_no', 'All') if filters else 'All'}")

        return results

    def get_account_choices(self, company_id: int) -> List[Dict[str, Any]]:
        """Get active non-system ledger accounts for account filter dropdown."""
        ph = self._ph()
        query = f"""
            SELECT
                la.id,
                la.account_name,
                la.account_type,
                la.group_name,
                p.id AS party_id,
                p.party_type
            FROM ledger_accounts la
            LEFT JOIN parties p ON la.id = p.ledger_account_id
            WHERE la.company_id = {ph}
              AND la.is_active = 1
              AND COALESCE(la.is_system, 0) = 0
            ORDER BY la.account_name
        """
        return self.db.execute_query(query, (company_id,))
