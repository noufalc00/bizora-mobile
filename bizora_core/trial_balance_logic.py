"""
Trial Balance Logic Module

Computes Trial Balance entirely from ledger_accounts + ledger_entries.
Does NOT read sales/purchase/return/stock tables directly.

Balance convention (same as ledger_logic):
  running_balance = opening_debit_adj + sum(debit) - sum(credit)
  Positive net  → Debit balance
  Negative net  → Credit balance (show absolute value in Cr column)

Opening balance for an account:
  opening_balance field (Dr positive / Cr negative based on opening_balance_type)
  PLUS any ledger_entries with voucher_date < from_date

Period movement:
  ledger_entries with voucher_date between from_date and to_date (inclusive)

Closing balance:
  opening + period_debit - period_credit
"""

from typing import Dict, List, Any, Optional
from datetime import date
from bizora_core.common_finance import to_decimal, money_round, is_balanced


# Account type → display category mapping
_TYPE_CATEGORY = {
    'cash_bank': 'Cash/Bank',
    'party':     'Party',
    'income':    'Income',
    'expense':   'Expense',
    'tax_liability': 'Tax',
    'capital':   'Capital',
    'stock':     'Stock',
}

# Filter label → account_type values
FILTER_MAP = {
    'All':       None,
    'Cash/Bank': ['cash_bank'],
    'Party':     ['party'],
    'Income':    ['income'],
    'Expense':   ['expense'],
    'Tax':       ['tax_liability'],
    'Capital':   ['capital'],
    'Stock':     ['stock'],
    'Asset':     ['cash_bank', 'party', 'stock'],
    'Liability': ['party', 'tax_liability'],
}


class TrialBalanceLogic:
    """Compute Trial Balance from ledger data only."""

    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # MAIN ENTRY POINT
    # ------------------------------------------------------------------

    def get_trial_balance(
        self,
        company_id: int,
        from_date: date,
        to_date: date,
        account_type_filter: Optional[str] = None,
        search_term: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return trial balance rows + totals for the given date range.

        Uses two aggregation queries (one for opening, one for period) then
        merges results in Python — avoids loading every individual entry row.

        Returns:
            {
                'rows': [ {sl, account_id, account_name, account_type,
                            category, ob_dr, ob_cr,
                            period_dr, period_cr,
                            closing_dr, closing_cr} ],
                'totals': {ob_dr, ob_cr, period_dr, period_cr,
                           closing_dr, closing_cr, difference, balanced},
            }
        """
        try:
            ph = self.db._get_placeholder()

            # 1. Fetch all active accounts (filtered if requested)
            accounts = self._fetch_accounts(company_id, account_type_filter, search_term)
            print(f"[TB DEBUG] Accounts fetched: {len(accounts)}")
            if not accounts:
                print(f"[TB DEBUG] No accounts found, returning empty result")
                return self._empty_result()

            account_ids = [a['id'] for a in accounts]

            # 2. Opening aggregation: entries BEFORE from_date
            opening_map = self._aggregate_entries(
                company_id, account_ids, None, from_date, inclusive_end=False
            )

            # 3. Period aggregation: entries from_date..to_date inclusive
            period_map = self._aggregate_entries(
                company_id, account_ids, from_date, to_date, inclusive_end=True
            )

            # 4. Build rows
            rows = []
            sl = 1
            tot = {
                'ob_dr': 0.0, 'ob_cr': 0.0,
                'period_dr': 0.0, 'period_cr': 0.0,
                'closing_dr': 0.0, 'closing_cr': 0.0,
            }

            for acct in accounts:
                aid = acct['id']
                acct_ob = to_decimal(acct.get('opening_balance', 0.0) or 0.0)
                ob_type = str(acct.get('opening_balance_type', 'Dr'))
                # Opening balance as signed net (Dr +, Cr -)
                ob_net = to_decimal(acct_ob if ob_type == 'Dr' else -acct_ob)

                # Entry sums before from_date
                pre = opening_map.get(aid, {'dr': to_decimal(0), 'cr': to_decimal(0)})
                ob_net += pre['dr'] - pre['cr']

                # Period sums
                per = period_map.get(aid, {'dr': to_decimal(0), 'cr': to_decimal(0)})
                period_net = per['dr'] - per['cr']

                closing_net = ob_net + period_net

                # Split net into Dr/Cr columns (never negative, never -0.0)
                ob_dr    = ob_net  if ob_net  > to_decimal(0) else to_decimal(0)
                ob_cr    = -ob_net if ob_net  < to_decimal(0) else to_decimal(0)
                pdr      = per['dr']
                pcr      = per['cr']
                cl_dr    = closing_net  if closing_net  > to_decimal(0) else to_decimal(0)
                cl_cr    = -closing_net if closing_net  < to_decimal(0) else to_decimal(0)

                # Do not skip all-zero accounts - show all active ledger accounts
                category = _TYPE_CATEGORY.get(acct.get('account_type', ''), acct.get('account_type', ''))

                rows.append({
                    'sl':           sl,
                    'account_id':   aid,
                    'account_name': acct['account_name'],
                    'account_type': acct.get('account_type', ''),
                    'category':     category,
                    'ob_dr':        float(money_round(ob_dr)),
                    'ob_cr':        float(money_round(ob_cr)),
                    'period_dr':    float(money_round(pdr)),
                    'period_cr':    float(money_round(pcr)),
                    'closing_dr':   float(money_round(cl_dr)),
                    'closing_cr':   float(money_round(cl_cr)),
                })
                sl += 1

                tot['ob_dr']      += float(ob_dr)
                tot['ob_cr']      += float(ob_cr)
                tot['period_dr']  += float(pdr)
                tot['period_cr']  += float(pcr)
                tot['closing_dr'] += float(cl_dr)
                tot['closing_cr'] += float(cl_cr)

            # Round totals
            for k in tot:
                tot[k] = float(money_round(tot[k]))

            diff = abs(tot['closing_dr'] - tot['closing_cr'])
            tot['difference'] = diff
            tot['balanced'] = is_balanced(tot['closing_dr'], tot['closing_cr'])

            return {'rows': rows, 'totals': tot}

        except Exception as e:
            print(f"TrialBalanceLogic.get_trial_balance error: {e}")
            return self._empty_result()

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------

    def _fetch_accounts(
        self,
        company_id: int,
        account_type_filter: Optional[str],
        search_term: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Fetch ledger accounts (with optional type/name filter)."""
        ph = self.db._get_placeholder()
        query = (
            f"SELECT id, account_name, account_type, opening_balance, opening_balance_type "
            f"FROM ledger_accounts "
            f"WHERE company_id={ph} AND is_active=1"
        )
        params: list = [company_id]

        types = FILTER_MAP.get(account_type_filter) if account_type_filter else None
        if types:
            placeholders = ','.join([ph] * len(types))
            query += f" AND account_type IN ({placeholders})"
            params.extend(types)

        if search_term and search_term.strip():
            query += f" AND account_name LIKE {ph}"
            params.append(f"%{search_term.strip()}%")

        query += " ORDER BY account_type, account_name"
        return self.db.execute_query(query, params) or []

    def _aggregate_entries(
        self,
        company_id: int,
        account_ids: List[int],
        from_date: Optional[date],
        to_date: Optional[date],
        inclusive_end: bool,
    ) -> Dict[int, Dict[str, float]]:
        """Return {account_id: {dr, cr}} aggregated from ledger_entries.

        from_date=None means no lower bound.
        inclusive_end=True  → voucher_date <= to_date
        inclusive_end=False → voucher_date < to_date  (opening: before from_date)
        """
        if not account_ids:
            return {}

        ph = self.db._get_placeholder()
        id_phs = ','.join([ph] * len(account_ids))

        query = (
            f"SELECT account_id, "
            f"COALESCE(SUM(debit),0.0) as dr, "
            f"COALESCE(SUM(credit),0.0) as cr "
            f"FROM ledger_entries "
            f"WHERE company_id={ph} AND account_id IN ({id_phs})"
        )
        params: list = [company_id] + list(account_ids)

        if from_date is not None:
            query += f" AND voucher_date>={ph}"
            params.append(str(from_date))

        if to_date is not None:
            op = "<=" if inclusive_end else "<"
            query += f" AND voucher_date{op}{ph}"
            params.append(str(to_date))

        query += " GROUP BY account_id"

        rows = self.db.execute_query(query, params) or []
        return {
            int(r['account_id']): {
                'dr': to_decimal(r['dr'] or 0.0),
                'cr': to_decimal(r['cr'] or 0.0),
            }
            for r in rows
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            'rows': [],
            'totals': {
                'ob_dr': 0.0, 'ob_cr': 0.0,
                'period_dr': 0.0, 'period_cr': 0.0,
                'closing_dr': 0.0, 'closing_cr': 0.0,
                'difference': 0.0, 'balanced': True,
            },
        }
