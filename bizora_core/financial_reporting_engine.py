from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from bizora_core.common_finance import to_decimal, money_round, is_balanced

if TYPE_CHECKING:
    from db import Database

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

class FinancialReportingEngine:
    def __init__(self, db: Any):
        self.db = db

    @staticmethod
    def _signed_opening_balance(account: Optional[Dict[str, Any]]) -> float:
        """Return opening balance as Dr positive and Cr negative."""
        if not account:
            return 0.0
        opening = float(account.get('opening_balance') or 0.0)
        opening_type = str(account.get('opening_balance_type') or 'Dr').strip().lower()
        return opening if opening_type.startswith('dr') else -opening

    def get_account_balance(self, company_id: int, account_id: int, to_date: Optional[str] = None) -> Dict[str, any]:
        """
        The Absolute Single Source of Truth for a single account's balance.
        Returns amount and balance type (Dr/Cr).
        """
        ph = self.db._get_placeholder()
        params = [company_id, account_id]
        date_query = ""
        if to_date:
            date_query = f" AND DATE(voucher_date) <= DATE({ph}) "
            params.append(to_date)

        query = f"""
            SELECT COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) AS raw_balance
            FROM ledger_entries
            WHERE company_id = {ph} AND account_id = {ph}
              AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
              {date_query}
        """
        result = self.db.execute_query(query, tuple(params))

        account_result = self.db.execute_query(
            f"""
            SELECT opening_balance, opening_balance_type
            FROM ledger_accounts
            WHERE company_id = {ph} AND id = {ph}
            """,
            (company_id, account_id)
        )
        opening_balance = self._signed_opening_balance(account_result[0] if account_result else None)
        
        if not result:
            raw_balance = opening_balance
        else:
            raw_balance = opening_balance + float(result[0]['raw_balance'] or 0.0)
        
        balance_type = ""
        if raw_balance > 0.001:
            balance_type = "Dr"
        elif raw_balance < -0.001:
            balance_type = "Cr"
            
        return {
            "raw_balance": raw_balance,
            "formatted_amount": abs(raw_balance),
            "type": balance_type,
            "display_string": f"₹ {abs(raw_balance):.2f} {balance_type}".strip()
        }

    def generate_trial_balance(
        self,
        company_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        account_type_filter: Optional[str] = None,
        search_term: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        The SSOT for Trial Balance. Groups all ledger entries by account.
        Supports opening balance, period movement, and closing balance calculations.
        
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
            if not accounts:
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
            print(f"FinancialReportingEngine.generate_trial_balance error: {e}")
            return self._empty_result()

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
            f"WHERE company_id={ph} AND account_id IN ({id_phs}) "
            f"AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')"
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

    @staticmethod
    def _normalized_group_name(group_name: Optional[str]) -> str:
        """Return a stable group key for exact financial classification."""
        return " ".join(str(group_name or "").strip().lower().split())

    def _classify_profit_loss_bucket(
        self,
        account_type: str,
        group_name: Optional[str],
    ) -> str:
        """Classify P&L accounts strictly from ledger account group names."""
        group_key = self._normalized_group_name(group_name)
        direct_income_groups = {
            "direct income",
            "direct incomes",
            "sales",
            "sales account",
            "income",
        }
        direct_expense_groups = {
            "direct expense",
            "direct expenses",
            "purchase",
            "purchases",
            "purchase account",
            "freight",
            "direct labour",
            "direct labor",
            "carriage",
        }
        indirect_income_groups = {
            "indirect income",
            "indirect incomes",
            "commission received",
            "discount received",
            "interest received",
            "discount",
        }
        indirect_expense_groups = {
            "indirect expense",
            "indirect expenses",
            "expenses",
            "expense",
            "administrative",
            "salary",
            "rent",
            "electricity",
            "office expense",
            "discount",
        }

        if group_key == "returns":
            return "direct_incomes" if account_type == "income" else "direct_expenses"
        if account_type == "income":
            if group_key in direct_income_groups:
                return "direct_incomes"
            if group_key in indirect_income_groups:
                return "indirect_incomes"
            return "indirect_incomes"
        if group_key in direct_expense_groups:
            return "direct_expenses"
        if group_key in indirect_expense_groups:
            return "indirect_expenses"
        return "indirect_expenses"

    def _classify_balance_sheet_bucket(
        self,
        account_type: str,
        group_name: Optional[str],
        debit: float,
        credit: float,
    ) -> Optional[str]:
        """Classify balance sheet accounts from group names and balance side."""
        group_key = self._normalized_group_name(group_name)
        current_asset_groups = {
            "current assets",
            "current asset",
            "sundry debtors",
            "cash",
            "bank",
            "cash & bank",
            "cash/bank",
            "stock",
        }
        fixed_asset_groups = {
            "fixed assets",
            "fixed asset",
        }
        current_liability_groups = {
            "current liabilities",
            "current liability",
            "sundry creditors",
            "duties & taxes",
            "tax liability",
        }
        capital_groups = {
            "capital",
            "capital account",
            "reserves and surplus",
        }

        if group_key in capital_groups or account_type == "capital":
            return "capital_accounts"
        if group_key in fixed_asset_groups:
            return "fixed_assets"
        if group_key in current_asset_groups:
            return "current_assets"
        if group_key in current_liability_groups:
            return "current_liabilities"
        if account_type in ("party", "tax_liability"):
            return "current_assets" if debit >= credit else "current_liabilities"
        if account_type in ("cash_bank", "stock"):
            return "current_assets"
        return None

    def generate_profit_and_loss(
        self,
        company_id: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate Profit & Loss Statement with Trading Account (Gross Profit) and P&L Account (Net Profit).
        
        Categorizes accounts into:
        - Direct Incomes (e.g., Sales Accounts)
        - Direct Expenses (e.g., Purchase Accounts, Direct Wages)
        - Indirect Incomes
        - Indirect Expenses
        
        Returns:
            {
                'direct_incomes': [{'account_name': str, 'balance': float, 'type': 'Dr/Cr'}],
                'direct_expenses': [{'account_name': str, 'balance': float, 'type': 'Dr/Cr'}],
                'indirect_incomes': [{'account_name': str, 'balance': float, 'type': 'Dr/Cr'}],
                'indirect_expenses': [{'account_name': str, 'balance': float, 'type': 'Dr/Cr'}],
                'total_direct_incomes': float,
                'total_direct_expenses': float,
                'gross_profit': float,
                'total_indirect_incomes': float,
                'total_indirect_expenses': float,
                'net_profit': float,
            }
        """
        try:
            ph = self.db._get_placeholder()
            
            # Build date filter
            date_filter = ""
            date_params = []
            if from_date:
                date_filter += f" AND DATE(le.voucher_date) >= DATE({ph})"
                date_params.append(from_date)
            if to_date:
                date_filter += f" AND DATE(le.voucher_date) <= DATE({ph})"
                date_params.append(to_date)
            params = date_params + [company_id]
            
            # Fetch all income and expense accounts with their net balances
            query = f"""
                SELECT 
                    la.id,
                    la.account_name,
                    la.account_type,
                    la.group_name,
                    COALESCE(SUM(le.debit), 0) as total_debit,
                    COALESCE(SUM(le.credit), 0) as total_credit
                FROM ledger_accounts la
                LEFT JOIN ledger_entries le ON la.id = le.account_id
                    AND le.company_id = la.company_id
                    AND le.voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                    {date_filter}
                WHERE la.company_id = {ph}
                  AND la.is_active = 1
                  AND la.account_type IN ('income', 'expense')
                GROUP BY la.id, la.account_name, la.account_type, la.group_name
                ORDER BY la.account_type, la.account_name
            """
            
            accounts = self.db.execute_query(query, tuple(params))
            
            # Categorize accounts
            direct_incomes = []
            direct_expenses = []
            indirect_incomes = []
            indirect_expenses = []
            
            for acc in accounts:
                account_type = acc['account_type']
                debit = float(acc['total_debit'] or 0)
                credit = float(acc['total_credit'] or 0)
                
                # Calculate net balance (Credit - Debit for Income, Debit - Credit for Expense)
                if account_type == 'income':
                    net_balance = credit - debit
                    balance_type = 'Cr' if net_balance > 0 else 'Dr'
                else:  # expense
                    net_balance = debit - credit
                    balance_type = 'Dr' if net_balance > 0 else 'Cr'
                
                account_data = {
                    'account_name': acc['account_name'],
                    'balance': abs(net_balance),
                    'type': balance_type
                }

                bucket = self._classify_profit_loss_bucket(
                    account_type,
                    acc.get('group_name'),
                )
                if bucket == 'direct_incomes':
                    direct_incomes.append(account_data)
                elif bucket == 'direct_expenses':
                    direct_expenses.append(account_data)
                elif bucket == 'indirect_incomes':
                    indirect_incomes.append(account_data)
                else:
                    indirect_expenses.append(account_data)
            
            # Calculate totals
            total_direct_incomes = sum(acc['balance'] for acc in direct_incomes)
            total_direct_expenses = sum(acc['balance'] for acc in direct_expenses)
            total_indirect_incomes = sum(acc['balance'] for acc in indirect_incomes)
            total_indirect_expenses = sum(acc['balance'] for acc in indirect_expenses)
            
            # Calculate profits
            gross_profit = total_direct_incomes - total_direct_expenses
            net_profit = gross_profit + total_indirect_incomes - total_indirect_expenses
            
            return {
                'direct_incomes': direct_incomes,
                'direct_expenses': direct_expenses,
                'indirect_incomes': indirect_incomes,
                'indirect_expenses': indirect_expenses,
                'total_direct_incomes': total_direct_incomes,
                'total_direct_expenses': total_direct_expenses,
                'gross_profit': gross_profit,
                'total_indirect_incomes': total_indirect_incomes,
                'total_indirect_expenses': total_indirect_expenses,
                'net_profit': net_profit,
            }
            
        except Exception as e:
            print(f"FinancialReportingEngine.generate_profit_and_loss error: {e}")
            return {
                'direct_incomes': [],
                'direct_expenses': [],
                'indirect_incomes': [],
                'indirect_expenses': [],
                'total_direct_incomes': 0.0,
                'total_direct_expenses': 0.0,
                'gross_profit': 0.0,
                'total_indirect_incomes': 0.0,
                'total_indirect_expenses': 0.0,
                'net_profit': 0.0,
            }

    def generate_balance_sheet(
        self,
        company_id: int,
        to_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate Balance Sheet with T-Format: Liabilities & Capital (Left), Assets (Right).
        
        Automatically pulls Net Profit/Loss from P&L and applies to Capital.
        
        Returns:
            {
                'capital_accounts': [{'account_name': str, 'balance': float}],
                'current_liabilities': [{'account_name': str, 'balance': float}],
                'fixed_assets': [{'account_name': str, 'balance': float}],
                'current_assets': [{'account_name': str, 'balance': float}],
                'net_profit': float,
                'total_capital': float,
                'total_liabilities': float,
                'total_assets': float,
                'grand_total': float,
            }
        """
        try:
            # Step 1: Get Net Profit/Loss from P&L
            pnl_data = self.generate_profit_and_loss(company_id, None, to_date)
            net_profit = pnl_data.get('net_profit', 0.0)
            
            ph = self.db._get_placeholder()
            
            # Build date filter
            date_filter = ""
            date_params = []
            if to_date:
                date_filter += f" AND DATE(le.voucher_date) <= DATE({ph})"
                date_params.append(to_date)
            params = date_params + [company_id]
            
            # Fetch all non-income/expense accounts (Assets, Liabilities, Capital)
            query = f"""
                SELECT 
                    la.id,
                    la.account_name,
                    la.account_type,
                    la.group_name,
                    COALESCE(SUM(le.debit), 0) as total_debit,
                    COALESCE(SUM(le.credit), 0) as total_credit
                FROM ledger_accounts la
                LEFT JOIN ledger_entries le ON la.id = le.account_id
                    AND le.company_id = la.company_id
                    AND le.voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                    {date_filter}
                WHERE la.company_id = {ph}
                  AND la.is_active = 1
                  AND la.account_type IN ('cash_bank', 'party', 'tax_liability', 'capital', 'stock')
                GROUP BY la.id, la.account_name, la.account_type, la.group_name
                ORDER BY la.account_type, la.account_name
            """
            
            accounts = self.db.execute_query(query, tuple(params))
            
            # Categorize accounts
            capital_accounts = []
            current_liabilities = []
            fixed_assets = []
            current_assets = []
            
            for acc in accounts:
                account_type = acc['account_type']
                debit = float(acc['total_debit'] or 0)
                credit = float(acc['total_credit'] or 0)
                
                # Calculate net balance
                # For Assets: Debit - Credit (normal Dr balance)
                # For Liabilities/Capital: Credit - Debit (normal Cr balance)
                if account_type in ('cash_bank', 'party', 'stock'):
                    # Assets: Dr balance is positive
                    net_balance = debit - credit
                else:  # tax_liability, capital
                    # Liabilities/Capital: Cr balance is positive
                    net_balance = credit - debit
                
                balance = abs(net_balance)
                if balance == 0:
                    continue  # Skip zero-balance accounts
                
                account_data = {
                    'account_name': acc['account_name'],
                    'balance': balance
                }

                bucket = self._classify_balance_sheet_bucket(
                    account_type,
                    acc.get('group_name'),
                    debit,
                    credit,
                )
                if bucket == 'capital_accounts':
                    capital_accounts.append(account_data)
                elif bucket == 'current_liabilities':
                    current_liabilities.append(account_data)
                elif bucket == 'fixed_assets':
                    fixed_assets.append(account_data)
                elif bucket == 'current_assets':
                    current_assets.append(account_data)
            
            # Calculate HONEST mathematical totals
            total_capital = sum(acc['balance'] for acc in capital_accounts)
            total_liabilities = sum(acc['balance'] for acc in current_liabilities)
            total_assets = sum(acc['balance'] for acc in fixed_assets) + sum(acc['balance'] for acc in current_assets)
            
            # Apply Net Profit/Loss to Capital for display purposes
            # Net Profit increases Capital, Net Loss decreases Capital
            adjusted_capital = total_capital + net_profit
            
            # HONEST totals - do NOT force them to match
            # total_liabilities_side = adjusted_capital + total_liabilities
            # total_assets_side = total_assets
            # These may not match if user hasn't entered Capital yet - that's mathematically correct
            
            return {
                'capital_accounts': capital_accounts,
                'current_liabilities': current_liabilities,
                'fixed_assets': fixed_assets,
                'current_assets': current_assets,
                'net_profit': net_profit,
                'total_capital': total_capital,
                'total_liabilities': total_liabilities,
                'total_assets': total_assets,
                'adjusted_capital': adjusted_capital,
            }
            
        except Exception as e:
            print(f"FinancialReportingEngine.generate_balance_sheet error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'capital_accounts': [],
                'current_liabilities': [],
                'fixed_assets': [],
                'current_assets': [],
                'net_profit': 0.0,
                'total_capital': 0.0,
                'total_liabilities': 0.0,
                'total_assets': 0.0,
                'adjusted_capital': 0.0,
            }

