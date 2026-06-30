"""
Ledger Logic Module — Commercial Double-Entry Accounting Engine.

Supports:
- System account creation per company (all required types)
- Party account auto-creation and linking
- Voucher posting: Sales, Purchase, Sales Return, Purchase Return
- Proper GST/CESS split entries (CGST/SGST for local, IGST for inter-state)
- Delete-and-repost on edit, delete on void
- Running balance rebuild after any change
- SQLite/MySQL compatible via db.py helpers
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal

from bizora_core.common_finance import to_decimal, money_round, is_balanced, safe_add, safe_subtract


class LedgerLogic:
    """Core ledger logic for double-entry accounting operations."""

    QUOTATION_EXCLUSION_SQL = (
        "voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')"
    )
    LEDGER_MATH_ERROR = "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance."

    def __init__(self, db):
        """
        Initialize ledger logic with database connection.

        Args:
            db: Database instance (db.Database)
        """
        self.db = db
        # Cache system accounts per company_id to avoid repeated DB queries
        self._system_accounts_cache: Dict[int, Dict[str, Any]] = {}

    # ============================================================
    # ACCOUNT METHODS
    # ============================================================

    def _load_system_accounts_cache(self, company_id: int) -> None:
        """Load all system accounts for company into cache in one query."""
        try:
            placeholder = self.db._get_placeholder()
            result = self.db.execute_query(
                f"SELECT id, account_name, account_code, account_type, group_name FROM ledger_accounts WHERE company_id = {placeholder} AND is_system = 1",
                (company_id,)
            )
            self._system_accounts_cache[company_id] = {
                row['account_name']: dict(row) for row in result
            }
        except Exception as e:
            print(f"Error loading system accounts cache: {e}")
            self._system_accounts_cache[company_id] = {}

    def get_account_by_name_cached(self, company_id: int, account_name: str) -> Optional[Dict[str, Any]]:
        """Get system account from cache (no DB query if already loaded)."""
        if company_id not in self._system_accounts_cache:
            self._load_system_accounts_cache(company_id)
        return self._system_accounts_cache.get(company_id, {}).get(account_name)

    def invalidate_accounts_cache(self, company_id: int) -> None:
        """Invalidate cache when accounts are created/modified."""
        self._system_accounts_cache.pop(company_id, None)

    # Required system accounts: (name, code, type, group, ob_type)
    _SYSTEM_ACCOUNTS = [
        ('Cash Account',            'CASH',       'cash_bank',    'Cash & Bank',       'Dr'),
        ('Bank Account',            'BANK',       'cash_bank',    'Cash & Bank',       'Dr'),
        ('Sundry Debtors',          'DEBTORS',    'party',        'Current Assets',    'Dr'),
        ('Sundry Creditors',        'CREDITORS',  'party',        'Current Liabilities','Cr'),
        ('Stock Account',           'STOCK',      'stock',        'Current Assets',    'Dr'),
        ('Sales Account',           'SALES',      'income',       'Income',            'Cr'),
        ('Purchase Account',        'PURCHASE',   'expense',      'Purchase',          'Dr'),
        ('Sales Return Account',    'SALES_RET',  'expense',      'Returns',           'Dr'),
        ('Purchase Return Account', 'PUR_RET',    'income',       'Returns',           'Cr'),
        ('Output CGST',             'CGST_OUT',   'tax_liability','Tax',               'Cr'),
        ('Output SGST',             'SGST_OUT',   'tax_liability','Tax',               'Cr'),
        ('Output IGST',             'IGST_OUT',   'tax_liability','Tax',               'Cr'),
        ('Output CESS',             'CESS_OUT',   'tax_liability','Tax',               'Cr'),
        ('Input CGST',              'CGST_IN',    'tax_liability','Tax',               'Dr'),
        ('Input SGST',              'SGST_IN',    'tax_liability','Tax',               'Dr'),
        ('Input IGST',              'IGST_IN',    'tax_liability','Tax',               'Dr'),
        ('Input CESS',              'CESS_IN',    'tax_liability','Tax',               'Dr'),
        ('GST Payable',             'GST_PAY',    'tax_liability','Tax',               'Cr'),
        ('GST Receivable',          'GST_REC',    'tax_liability','Tax',               'Dr'),
        ('GST Paid',                'GST_PD',     'tax_liability','Tax',               'Dr'),
        ('GST Collected',           'GST_CL',     'tax_liability','Tax',               'Cr'),
        ('CESS Paid',               'CESS_PD',    'tax_liability','Tax',               'Dr'),
        ('CESS Collected',          'CESS_CL',    'tax_liability','Tax',               'Cr'),
        ('Discount Allowed',        'DISC_ALW',   'expense',      'Discount',          'Dr'),
        ('Discount Given',          'DISC_GIV',   'expense',      'Discount',          'Dr'),
        ('Discount Received',       'DISC_REC',   'income',       'Discount',          'Cr'),
        ('Salary Paid',             'SAL_PD',     'expense',      'Expense',           'Dr'),
        ('Salary Expense',          'SAL_EXP',    'expense',      'Expense',           'Dr'),
        ('Rent Paid',               'RENT_PD',    'expense',      'Expense',           'Dr'),
        ('Rent Expense',            'RENT_EXP',   'expense',      'Expense',           'Dr'),
        ('Miscellaneous Expense',   'MISC_EXP',   'expense',      'Expense',           'Dr'),
        ('Miscellaneous Income',    'MISC_INC',   'income',       'Income',            'Cr'),
        ('Round Off',               'ROUND_OFF',  'expense',      'Indirect Expenses', 'Dr'),
        ('Profit and Loss Account', 'P&L',        'income',       'P&L',               'Cr'),
        ('Opening Stock',           'OPEN_STK',   'stock',        'Stock',             'Dr'),
        ('Closing Stock',           'CLOSE_STK',  'stock',        'Stock',             'Dr'),
        ('Capital Account',         'CAPITAL',    'capital',      'Capital',           'Cr'),
        ('Drawings',               'DRAWINGS',   'capital',      'Capital',           'Dr'),
        ('Suspense Account',        'SUSPENSE',   'expense',      'Suspense',          'Dr'),
        ('Stock Adjustment Loss',   'STK_LOSS',   'expense',      'Expense',           'Dr'),
        ('Stock Adjustment Gain',   'STK_GAIN',   'income',       'Income',            'Cr'),
    ]

    def ensure_system_accounts(self, company_id: int) -> bool:
        """Ensure all required system accounts exist for a company."""
        if company_id in self._system_accounts_cache and self._system_accounts_cache[company_id]:
            return True
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            placeholder = self.db._get_placeholder()
            ts = self.db._get_timestamp_default()
            for name, code, actype, group, ob_type in self._SYSTEM_ACCOUNTS:
                cursor.execute(
                    f"SELECT id FROM ledger_accounts WHERE company_id={placeholder} AND account_name={placeholder}",
                    (company_id, name)
                )
                existing_account = cursor.fetchone()
                if existing_account:
                    cursor.execute(
                        f"""
                        UPDATE ledger_accounts
                        SET is_system = 1
                        WHERE company_id = {placeholder}
                          AND account_name = {placeholder}
                          AND COALESCE(is_system, 0) <> 1
                        """,
                        (company_id, name)
                    )
                else:
                    cursor.execute(
                        f"""INSERT INTO ledger_accounts (company_id, account_name, account_code,
                            account_type, group_name, opening_balance, opening_balance_type,
                            is_system, is_active, created_at, updated_at)
                           VALUES ({placeholder},{placeholder},{placeholder},{placeholder},{placeholder},
                                   0.0,{placeholder},1,1,{ts},{ts})""",
                        (company_id, name, code, actype, group, ob_type)
                    )
            conn.commit()
            self.db.disconnect()
            self.invalidate_accounts_cache(company_id)
            self._load_system_accounts_cache(company_id)
            return True
        except Exception as e:
            print(f"Error ensuring system accounts: {e}")
            if 'conn' in locals():
                conn.rollback()
            self.db.disconnect()
            return False

    # ============================================================
    # PARTY ACCOUNT METHODS
    # ============================================================

    def get_or_create_party_account(self, company_id: int, party_id: int,
                                    party_name: str, party_type: str,
                                    opening_balance: float = 0.0,
                                    opening_balance_type: str = 'Dr') -> Optional[Dict[str, Any]]:
        """Get or create a ledger account for a party and link it.

        party_type: 'Debitor', 'Creditor', or 'Both'
        opening_balance_type: 'Dr' for debitors, 'Cr' for creditors
        Returns the ledger account dict or None on failure.
        """
        try:
            print(f"[DEBUG get_or_create_party_account] START: company_id={company_id}, party_id={party_id}, party_name='{party_name}', party_type='{party_type}'")
            placeholder = self.db._get_placeholder()
            # Check if party already has a linked ledger_account_id
            result = self.db.execute_query(
                f"SELECT ledger_account_id FROM parties WHERE id={placeholder} AND company_id={placeholder}",
                (party_id, company_id)
            )
            if result and result[0]['ledger_account_id']:
                print(f"[DEBUG get_or_create_party_account] Party already has ledger_account_id={result[0]['ledger_account_id']}")
                acct = self.get_account(company_id, result[0]['ledger_account_id'])
                if acct:
                    print(f"[DEBUG get_or_create_party_account] Returning existing linked account")
                    return acct

            # Look up by name
            print(f"[DEBUG get_or_create_party_account] Looking up ledger account by name: '{party_name}'")
            existing = self.get_account_by_name(company_id, party_name)
            if existing:
                print(f"[DEBUG get_or_create_party_account] Found existing ledger account by name: id={existing['id']}")
            else:
                print(f"[DEBUG get_or_create_party_account] No existing ledger account found, will create new")
                
            if not existing:
                # Determine ob_type from party_type
                if party_type in ('Creditor',):
                    ob_type = 'Cr'
                else:
                    ob_type = 'Dr'
                if opening_balance_type:
                    ob_type = opening_balance_type
                print(f"[DEBUG get_or_create_party_account] Creating new ledger account with ob_type='{ob_type}'")
                acct_id = self.create_account(company_id, {
                    'account_name': party_name,
                    'account_code': None,
                    'account_type': 'party',
                    'group_name': 'Sundry Debtors' if ob_type == 'Dr' else 'Sundry Creditors',
                    'opening_balance': opening_balance,
                    'opening_balance_type': ob_type,
                })
                if not acct_id:
                    print(f"[DEBUG get_or_create_party_account] FAILED to create ledger account")
                    return None
                existing = self.get_account(company_id, acct_id)
                print(f"[DEBUG get_or_create_party_account] Created new ledger account id={acct_id}")

            # Link the account to the party
            try:
                print(f"[DEBUG get_or_create_party_account] Linking ledger_account_id={existing['id']} to party_id={party_id}")
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute(
                    f"UPDATE parties SET ledger_account_id={placeholder} WHERE id={placeholder} AND company_id={placeholder}",
                    (existing['id'], party_id, company_id)
                )
                conn.commit()
                self.db.disconnect()
                print(f"[DEBUG get_or_create_party_account] Link successful")
            except Exception as e:
                print(f"Warning: could not link party ledger: {e}")
            return existing
        except Exception as e:
            print(f"Error get_or_create_party_account: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_account_by_party_id(self, company_id: int, party_id: int) -> Optional[Dict[str, Any]]:
        """Get the linked ledger account for a party by party_id."""
        try:
            placeholder = self.db._get_placeholder()
            result = self.db.execute_query(
                f"SELECT ledger_account_id FROM parties WHERE id={placeholder} AND company_id={placeholder}",
                (party_id, company_id)
            )
            if result and result[0]['ledger_account_id']:
                return self.get_account(company_id, result[0]['ledger_account_id'])
            # Fallback: look up by party name
            party_result = self.db.execute_query(
                f"SELECT name, party_type, opening_balance FROM parties WHERE id={placeholder} AND company_id={placeholder}",
                (party_id, company_id)
            )
            if party_result:
                p = party_result[0]
                ptype = p.get('party_type', 'Debitor')
                ob = float(money_round(to_decimal(p.get('opening_balance', 0.0) or 0.0)))
                ob_type = 'Cr' if ptype == 'Creditor' else 'Dr'
                return self.get_or_create_party_account(
                    company_id, party_id, p['name'], ptype, ob, ob_type
                )
            return None
        except Exception as e:
            print(f"Error get_account_by_party_id: {e}")
            return None

    def _bank_master_has_ledger_column(self) -> bool:
        """Return whether bank_accounts.ledger_account_id exists in the active schema."""
        try:
            if self.db._is_sqlite():
                conn = self.db.connect()
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(bank_accounts)")
                cols = [row[1] for row in cursor.fetchall()]
                self.db.disconnect()
                return 'ledger_account_id' in cols
            rows = self.db.execute_query(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'bank_accounts' AND column_name = 'ledger_account_id'
                LIMIT 1
                """
            )
            return bool(rows)
        except Exception:
            return False

    def get_ledger_account_id_for_bank_master(self, company_id: int, bank_master_id: int) -> Optional[int]:
        """Resolve a bank master row to its linked ledger account id."""
        if not bank_master_id:
            return None
        try:
            account = self.get_or_create_bank_master_ledger(company_id, int(bank_master_id))
            return int(account['id']) if account and account.get('id') else None
        except Exception as e:
            print(f"Error resolving bank master ledger: {e}")
            return None

    def get_or_create_bank_master_ledger(self, company_id: int, bank_master_id: int) -> Optional[Dict[str, Any]]:
        """Get or create the ledger account linked to a bank master row."""
        try:
            self.ensure_system_accounts(company_id)
            placeholder = self.db._get_placeholder()
            has_ledger_col = self._bank_master_has_ledger_column()
            ledger_col = ", ledger_account_id" if has_ledger_col else ""
            rows = self.db.execute_query(
                f"""
                SELECT id, account_name, opening_balance{ledger_col}
                FROM bank_accounts
                WHERE company_id = {placeholder} AND id = {placeholder}
                """,
                (company_id, bank_master_id),
            )
            if not rows:
                return None
            bank_row = rows[0]
            account_name = str(bank_row.get('account_name') or '').strip() or 'Bank Account'
            opening_balance = float(money_round(to_decimal(bank_row.get('opening_balance') or 0.0)))

            linked_id = bank_row.get('ledger_account_id') if has_ledger_col else None
            if linked_id:
                existing = self.get_account(company_id, int(linked_id))
                if existing:
                    self._sync_bank_master_ledger(company_id, int(linked_id), account_name, opening_balance)
                    return existing

            existing = self.get_account_by_name(company_id, account_name)
            if not existing and account_name.lower() == 'bank account':
                existing = self.get_account_by_name(company_id, 'Bank Account')

            if not existing:
                code = f"BANK{bank_master_id}"
                ledger_id = self.create_account(company_id, {
                    'account_name': account_name,
                    'account_code': code,
                    'account_type': 'cash_bank',
                    'group_name': 'Cash & Bank',
                    'opening_balance': opening_balance,
                    'opening_balance_type': 'Dr',
                })
                if not ledger_id:
                    return None
                existing = self.get_account(company_id, ledger_id)
            else:
                self._sync_bank_master_ledger(
                    company_id, int(existing['id']), account_name, opening_balance
                )

            if has_ledger_col and existing:
                self.db.update_bank_account_ledger_link(company_id, bank_master_id, int(existing['id']))
            return existing
        except Exception as e:
            print(f"Error get_or_create_bank_master_ledger: {e}")
            return None

    def _sync_bank_master_ledger(self, company_id: int, ledger_account_id: int,
                                  account_name: str, opening_balance: float) -> None:
        """Keep linked bank ledger account name and opening balance aligned with the master."""
        try:
            self.update_account(company_id, ledger_account_id, {
                'account_name': account_name,
                'opening_balance': opening_balance,
                'opening_balance_type': 'Dr',
            })
        except Exception as e:
            print(f"Warning: could not sync bank master ledger: {e}")

    def ensure_bank_master_ledgers(self, company_id: int) -> None:
        """Ensure every bank master row has a linked ledger account and migrate old postings."""
        try:
            if not self._bank_master_has_ledger_column():
                return
            placeholder = self.db._get_placeholder()
            rows = self.db.execute_query(
                f"SELECT id FROM bank_accounts WHERE company_id = {placeholder} ORDER BY account_name",
                (company_id,),
            )
            for row in rows or []:
                bank_id = row.get('id')
                if bank_id:
                    self.get_or_create_bank_master_ledger(company_id, int(bank_id))
            self.migrate_bank_ledger_postings(company_id)
        except Exception as e:
            print(f"Error ensuring bank master ledgers: {e}")

    def migrate_bank_ledger_postings(self, company_id: int) -> None:
        """Move legacy combined Bank Account postings onto per-bank ledger accounts."""
        try:
            if not self._bank_master_has_ledger_column():
                return
            system_bank = self.get_account_by_name(company_id, 'Bank Account')
            if not system_bank:
                return
            system_bank_id = int(system_bank['id'])
            placeholder = self.db._get_placeholder()
            conn = self.db.connect()
            cursor = conn.cursor()

            voucher_maps = (
                ('bank_receipt', 'bank_receipts'),
                ('bank_payment', 'bank_payments'),
            )
            for voucher_type, header_table in voucher_maps:
                cursor.execute(
                    f"""
                    UPDATE ledger_entries
                    SET account_id = (
                        SELECT ba.ledger_account_id
                        FROM {header_table} hdr
                        INNER JOIN bank_accounts ba ON ba.id = hdr.bank_account_id
                        WHERE hdr.id = ledger_entries.voucher_id
                          AND hdr.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                    )
                    WHERE company_id = {placeholder}
                      AND account_id = {placeholder}
                      AND voucher_type = {placeholder}
                      AND EXISTS (
                        SELECT 1
                        FROM {header_table} hdr
                        INNER JOIN bank_accounts ba ON ba.id = hdr.bank_account_id
                        WHERE hdr.id = ledger_entries.voucher_id
                          AND hdr.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                          AND ba.ledger_account_id <> {placeholder}
                      )
                    """,
                    (company_id, system_bank_id, voucher_type, system_bank_id),
                )
                cursor.execute(
                    f"""
                    UPDATE ledger_entries
                    SET contra_account_id = (
                        SELECT ba.ledger_account_id
                        FROM {header_table} hdr
                        INNER JOIN bank_accounts ba ON ba.id = hdr.bank_account_id
                        WHERE hdr.id = ledger_entries.voucher_id
                          AND hdr.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                    )
                    WHERE company_id = {placeholder}
                      AND contra_account_id = {placeholder}
                      AND voucher_type = {placeholder}
                      AND EXISTS (
                        SELECT 1
                        FROM {header_table} hdr
                        INNER JOIN bank_accounts ba ON ba.id = hdr.bank_account_id
                        WHERE hdr.id = ledger_entries.voucher_id
                          AND hdr.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                          AND ba.ledger_account_id <> {placeholder}
                      )
                    """,
                    (company_id, system_bank_id, voucher_type, system_bank_id),
                )

            for voucher_type in ('pdc_receipt', 'pdc_payment'):
                cursor.execute(
                    f"""
                    UPDATE ledger_entries
                    SET account_id = (
                        SELECT ba.ledger_account_id
                        FROM pdc_register pdc
                        INNER JOIN bank_accounts ba ON ba.id = pdc.bank_account_id
                        WHERE pdc.id = ledger_entries.voucher_id
                          AND pdc.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                    )
                    WHERE company_id = {placeholder}
                      AND account_id = {placeholder}
                      AND voucher_type = {placeholder}
                      AND EXISTS (
                        SELECT 1
                        FROM pdc_register pdc
                        INNER JOIN bank_accounts ba ON ba.id = pdc.bank_account_id
                        WHERE pdc.id = ledger_entries.voucher_id
                          AND pdc.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                          AND ba.ledger_account_id <> {placeholder}
                      )
                    """,
                    (company_id, system_bank_id, voucher_type, system_bank_id),
                )
                cursor.execute(
                    f"""
                    UPDATE ledger_entries
                    SET contra_account_id = (
                        SELECT ba.ledger_account_id
                        FROM pdc_register pdc
                        INNER JOIN bank_accounts ba ON ba.id = pdc.bank_account_id
                        WHERE pdc.id = ledger_entries.voucher_id
                          AND pdc.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                    )
                    WHERE company_id = {placeholder}
                      AND contra_account_id = {placeholder}
                      AND voucher_type = {placeholder}
                      AND EXISTS (
                        SELECT 1
                        FROM pdc_register pdc
                        INNER JOIN bank_accounts ba ON ba.id = pdc.bank_account_id
                        WHERE pdc.id = ledger_entries.voucher_id
                          AND pdc.company_id = ledger_entries.company_id
                          AND ba.ledger_account_id IS NOT NULL
                          AND ba.ledger_account_id <> {placeholder}
                      )
                    """,
                    (company_id, system_bank_id, voucher_type, system_bank_id),
                )

            conn.commit()
            self.db.disconnect()
        except Exception as e:
            print(f"Error migrating bank ledger postings: {e}")
            if 'conn' in locals():
                try:
                    conn.rollback()
                except Exception:
                    pass
            self.db.disconnect()

    def create_account(self, company_id: int, account_data: Dict[str, Any]) -> Optional[int]:
        """
        Create a new ledger account.

        Args:
            company_id: Company ID
            account_data: Dictionary with account details
                - account_name
                - account_code (optional)
                - account_type (party, cash_bank, income, expense, tax_liability, capital, stock)
                - group_name (optional)
                - opening_balance (optional, default 0)
                - opening_balance_type (optional, default 'Dr')

        Returns:
            Account ID if successful, None otherwise
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            timestamp_default = self.db._get_timestamp_default()
            placeholder = self.db._get_placeholder()
            query = f"""
                INSERT INTO ledger_accounts (
                    company_id, account_name, account_code, account_type, group_name,
                    opening_balance, opening_balance_type, is_system, is_active,
                    created_at, updated_at
                ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                    {placeholder}, {placeholder}, 0, 1, {timestamp_default}, {timestamp_default})
            """
            params = (
                company_id,
                account_data.get('account_name'),
                account_data.get('account_code'),
                account_data.get('account_type'),
                account_data.get('group_name'),
                account_data.get('opening_balance', 0.0),
                account_data.get('opening_balance_type', 'Dr')
            )
            cursor.execute(query, params)

            account_id = self.db._get_last_insert_id(cursor)
            conn.commit()
            self.db.disconnect()
            return account_id
        except Exception as e:
            print(f"Error creating account: {e}")
            if 'conn' in locals():
                conn.rollback()
            self.db.disconnect()
            return None

    def update_account(self, company_id: int, account_id: int, account_data: Dict[str, Any]) -> bool:
        """
        Update an existing ledger account.

        Args:
            company_id: Company ID
            account_id: Account ID
            account_data: Dictionary with fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # Build dynamic update query
            update_fields = []
            params = []
            timestamp_default = self.db._get_timestamp_default()
            placeholder = self.db._get_placeholder()

            if 'account_name' in account_data:
                update_fields.append(f"account_name = {placeholder}")
                params.append(account_data['account_name'])
            if 'account_code' in account_data:
                update_fields.append(f"account_code = {placeholder}")
                params.append(account_data['account_code'])
            if 'account_type' in account_data:
                update_fields.append(f"account_type = {placeholder}")
                params.append(account_data['account_type'])
            if 'group_name' in account_data:
                update_fields.append(f"group_name = {placeholder}")
                params.append(account_data['group_name'])
            if 'opening_balance' in account_data:
                update_fields.append(f"opening_balance = {placeholder}")
                params.append(account_data['opening_balance'])
            if 'opening_balance_type' in account_data:
                update_fields.append(f"opening_balance_type = {placeholder}")
                params.append(account_data['opening_balance_type'])
            if 'is_active' in account_data:
                update_fields.append(f"is_active = {placeholder}")
                params.append(account_data['is_active'])

            if not update_fields:
                self.db.disconnect()
                return True

            update_fields.append(f"updated_at = {timestamp_default}")
            params.extend([company_id, account_id])

            query = f"""
                UPDATE ledger_accounts
                SET {', '.join(update_fields)}
                WHERE company_id = {placeholder} AND id = {placeholder}
            """
            cursor.execute(query, params)

            conn.commit()
            self.db.disconnect()
            return True
        except Exception as e:
            print(f"Error updating account: {e}")
            if 'conn' in locals():
                conn.rollback()
            self.db.disconnect()
            return False

    def get_account(self, company_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        """
        Get account details by ID.

        Args:
            company_id: Company ID
            account_id: Account ID

        Returns:
            Account dictionary if found, None otherwise
        """
        try:
            placeholder = self.db._get_placeholder()
            query = f"""
                SELECT id, company_id, account_name, account_code, account_type,
                       group_name, opening_balance, opening_balance_type, is_system, is_active
                FROM ledger_accounts
                WHERE company_id = {placeholder} AND id = {placeholder}
            """
            result = self.db.execute_query(query, (company_id, account_id))
            return result[0] if result else None
        except Exception as e:
            print(f"Error getting account: {e}")
            return None

    def get_account_by_name(self, company_id: int, account_name: str) -> Optional[Dict[str, Any]]:
        """
        Get account details by name.

        Args:
            company_id: Company ID
            account_name: Account name

        Returns:
            Account dictionary if found, None otherwise
        """
        try:
            placeholder = self.db._get_placeholder()
            query = f"""
                SELECT id, company_id, account_name, account_code, account_type,
                       group_name, opening_balance, opening_balance_type, is_system, is_active
                FROM ledger_accounts
                WHERE company_id = {placeholder} AND account_name = {placeholder}
            """
            result = self.db.execute_query(query, (company_id, account_name))
            return result[0] if result else None
        except Exception as e:
            print(f"Error getting account by name: {e}")
            return None

    def search_accounts(self, company_id: int, search_term: str = None,
                      account_type: str = None, is_active: bool = True) -> List[Dict[str, Any]]:
        """
        Search accounts with optional filters.

        Args:
            company_id: Company ID
            search_term: Optional search term for account name/code
            account_type: Optional account type filter
            is_active: Filter by active status (default True)

        Returns:
            List of account dictionaries
        """
        try:
            placeholder = self.db._get_placeholder()
            query = f"""
                SELECT id, company_id, account_name, account_code, account_type,
                       group_name, opening_balance, opening_balance_type, is_system, is_active
                FROM ledger_accounts
                WHERE company_id = {placeholder}
            """
            params = [company_id]

            if search_term:
                query += f" AND (account_name LIKE {placeholder} OR account_code LIKE {placeholder})"
                params.extend([f"%{search_term}%", f"%{search_term}%"])

            if account_type:
                query += f" AND account_type = {placeholder}"
                params.append(account_type)

            if is_active is not None:
                query += f" AND is_active = {placeholder}"
                params.append(1 if is_active else 0)

            query += " ORDER BY account_name"

            return self.db.execute_query(query, params)
        except Exception as e:
            print(f"Error searching accounts: {e}")
            return []

    # ============================================================
    # LEDGER METHODS
    # ============================================================

    def post_entry(self, company_id: int, entry_data: Dict[str, Any]) -> Optional[int]:
        """
        Post a single ledger entry.

        Args:
            company_id: Company ID
            entry_data: Dictionary with entry details
                - voucher_type (sales, purchase, receipt, payment, journal)
                - voucher_id (ID of the voucher record)
                - voucher_no (voucher number)
                - voucher_date
                - account_id
                - contra_account_id (optional)
                - narration (optional)
                - debit
                - credit
                - reference_type (optional)
                - reference_id (optional)

        Returns:
            Entry ID if successful, None otherwise
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            timestamp_default = self.db._get_timestamp_default()
            placeholder = self.db._get_placeholder()
            query = f"""
                INSERT INTO ledger_entries (
                    company_id, voucher_type, voucher_id, voucher_no, voucher_date,
                    account_id, contra_account_id, narration, debit, credit, running_balance,
                    reference_type, reference_id, created_at, updated_at
                ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                    {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 0.0,
                    {placeholder}, {placeholder}, {timestamp_default}, {timestamp_default})
            """
            params = (
                company_id,
                entry_data.get('voucher_type'),
                entry_data.get('voucher_id'),
                entry_data.get('voucher_no'),
                entry_data.get('voucher_date'),
                entry_data.get('account_id'),
                entry_data.get('contra_account_id'),
                entry_data.get('narration'),
                entry_data.get('debit', 0.0),
                entry_data.get('credit', 0.0),
                entry_data.get('reference_type'),
                entry_data.get('reference_id')
            )
            cursor.execute(query, params)

            entry_id = self.db._get_last_insert_id(cursor)

            # Update running balance
            self._update_running_balance(cursor, company_id, entry_data.get('account_id'),
                                        entry_data.get('voucher_date'))

            conn.commit()
            self.db.disconnect()
            return entry_id
        except Exception as e:
            print(f"Error posting entry: {e}")
            if 'conn' in locals():
                conn.rollback()
            self.db.disconnect()
            return None

    def post_double_entry(self, company_id: int, voucher_type: str, voucher_id: int,
                        voucher_no: str, voucher_date: date, entries: List[Dict[str, Any]],
                        narration: str = None, reference_type: str = None,
                        reference_id: int = None, conn=None, cursor=None,
                        commit: bool = True) -> bool:
        """
        Post a double-entry voucher (multiple entries that balance).

        ATOMIC DELETION PROTOCOL (Executed within same transaction):
        - Before inserting new entries, deletes old ledger_entries by voucher_no AND voucher_type
        - This prevents duplicate entries during voucher updates
        - Deletion happens within the same transaction as the INSERTs

        Args:
            company_id: Company ID
            voucher_type: Voucher type (sales, purchase, receipt, payment, journal)
            voucher_id: ID of the voucher record
            voucher_no: Voucher number
            voucher_date: Voucher date
            entries: List of entry dictionaries, each with:
                - account_id
                - debit
                - credit
            narration: Optional narration
            reference_type: Optional reference type
            reference_id: Optional reference ID
            conn: Optional caller-owned database connection for atomic voucher saves
            cursor: Optional caller-owned cursor for the active transaction
            commit: Commit internally when True; caller commits or rolls back when False

        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"[DEBUG] post_double_entry: company_id={company_id}, voucher_type={voucher_type}, voucher_id={voucher_id}, voucher_no={voucher_no}")
            
            owns_connection = conn is None
            conn = conn or self.db.connect()
            cursor = cursor or conn.cursor()

            placeholder = self.db._get_placeholder()

            # Mathematical firewall must run before any DELETE/INSERT mutation.
            total_debit = money_round(sum((to_decimal(e.get('debit', 0.0)) for e in entries), Decimal("0.00")))
            total_credit = money_round(sum((to_decimal(e.get('credit', 0.0)) for e in entries), Decimal("0.00")))
            print(f"[DEBUG] Mathematical Firewall: total_debit={total_debit}, total_credit={total_credit}")
            if total_debit != total_credit:
                raise ValueError(
                    f"{self.LEDGER_MATH_ERROR} debit={total_debit}, credit={total_credit}"
                )

            # ATOMIC DELETION PROTOCOL: Delete old entries within the same transaction
            # This runs BEFORE any INSERT operations, ensuring no duplicates
            print(f"[DEBUG] Executing DELETE FROM ledger_entries WHERE company_id={company_id} AND voucher_type={voucher_type} AND voucher_no={voucher_no}")
            cursor.execute(
                f"DELETE FROM ledger_entries WHERE company_id = {placeholder} AND voucher_type = {placeholder} AND voucher_no = {placeholder}",
                (company_id, voucher_type, voucher_no)
            )
            deleted_count = cursor.rowcount
            print(f"[DEBUG] Deleted {deleted_count} old ledger entries in post_double_entry")

            timestamp_default = self.db._get_timestamp_default()

            insert_query = f"""
                INSERT INTO ledger_entries (
                    company_id, voucher_type, voucher_id, voucher_no, voucher_date,
                    account_id, contra_account_id, narration, debit, credit, running_balance,
                    reference_type, reference_id, created_at, updated_at
                ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                    {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 0.0,
                    {placeholder}, {placeholder}, {timestamp_default}, {timestamp_default})
            """
            insert_data = [
                (
                    company_id, voucher_type, voucher_id, voucher_no, voucher_date,
                    entry.get('account_id'), entry.get('contra_account_id'), narration,
                    entry.get('debit', 0.0), entry.get('credit', 0.0),
                    reference_type, reference_id
                )
                for entry in entries
            ]
            cursor.executemany(insert_query, insert_data)
            print(f"[DEBUG] Inserted {len(insert_data)} new ledger entries")

            # Rebuild running balances for all affected accounts
            affected_accounts = list({e.get('account_id') for e in entries if e.get('account_id')})
            for acct_id in affected_accounts:
                self._rebuild_account_running_balance(cursor, company_id, acct_id)

            if commit:
                conn.commit()
                print(f"[DEBUG] Transaction committed successfully")
            if owns_connection:
                self.db.disconnect()
            return True
        except Exception as e:
            print(f"[DEBUG] Error in post_double_entry: {e}")
            if 'conn' in locals() and conn is not None and commit:
                conn.rollback()
            if locals().get('owns_connection'):
                self.db.disconnect()
            return False

    def update_voucher_entries(self, company_id: int, voucher_type: str, voucher_id: int,
                             new_entries: List[Dict[str, Any]]) -> bool:
        """
        Update voucher entries (delete old, post new).

        Args:
            company_id: Company ID
            voucher_type: Voucher type
            voucher_id: Voucher ID
            new_entries: New entries to post

        Returns:
            True if successful, False otherwise
        """
        try:
            # First, delete old entries for this voucher
            if not self.delete_voucher_entries(company_id, voucher_type, voucher_id):
                return False

            # Get voucher details for reposting
            voucher_details = self._get_voucher_details(company_id, voucher_type, voucher_id)
            if not voucher_details:
                return False

            # Post new entries
            return self.post_double_entry(
                company_id,
                voucher_type,
                voucher_id,
                voucher_details.get('voucher_no', ''),
                voucher_details.get('voucher_date'),
                new_entries,
                voucher_details.get('narration'),
                voucher_details.get('reference_type'),
                voucher_details.get('reference_id')
            )
        except Exception as e:
            print(f"Error updating voucher entries: {e}")
            return False

    def delete_voucher_entries(self, company_id: int, voucher_type: str, voucher_id: int,
                               voucher_no: Optional[str] = None, conn=None,
                               cursor=None, commit: bool = True) -> bool:
        """
        Delete all ledger entries for a voucher.
        
        STRICT DELETION PROTOCOL:
        - If voucher_no is provided, deletes by voucher_no AND voucher_type (more strict)
        - If voucher_no is not provided, deletes by voucher_id AND voucher_type
        - This prevents duplicate entries during voucher updates
        
        Args:
            company_id: Company ID
            voucher_type: Voucher type
            voucher_id: Voucher ID
            voucher_no: Voucher number (optional, for stricter deletion)

        Returns:
            True if successful, False otherwise
        """
        try:
            owns_connection = conn is None
            conn = conn or self.db.connect()
            cursor = cursor or conn.cursor()
            placeholder = self.db._get_placeholder()

            # Build WHERE clause based on what's provided
            if voucher_no:
                # STRICT: Delete by voucher_no AND voucher_type
                where_clause = f"company_id = {placeholder} AND voucher_type = {placeholder} AND voucher_no = {placeholder}"
                where_params = (company_id, voucher_type, voucher_no)
            else:
                # Fallback: Delete by voucher_id AND voucher_type
                where_clause = f"company_id = {placeholder} AND voucher_type = {placeholder} AND voucher_id = {placeholder}"
                where_params = (company_id, voucher_type, voucher_id)

            # Get affected accounts to rebuild running balances
            cursor.execute(
                f"SELECT DISTINCT account_id FROM ledger_entries WHERE {where_clause}",
                where_params
            )
            affected_accounts = [row[0] for row in cursor.fetchall()]

            # Get the voucher date for balance rebuilding
            cursor.execute(
                f"SELECT voucher_date FROM ledger_entries WHERE {where_clause} LIMIT 1",
                where_params
            )
            result = cursor.fetchone()
            voucher_date = result[0] if result else None

            # Delete entries
            print(f"[DEBUG] Executing DELETE FROM ledger_entries WHERE {where_clause} with params {where_params}")
            cursor.execute(
                f"DELETE FROM ledger_entries WHERE {where_clause}",
                where_params
            )
            deleted_rows = cursor.rowcount
            print(f"[DEBUG] Rows affected by delete: {deleted_rows}")

            # Rebuild running balances for affected accounts
            if voucher_date:
                for account_id in affected_accounts:
                    self._update_running_balance(cursor, company_id, account_id, voucher_date)

            if commit:
                conn.commit()
            if owns_connection:
                self.db.disconnect()
            return True
        except Exception as e:
            print(f"Error deleting voucher entries: {e}")
            if 'conn' in locals() and conn is not None and commit:
                conn.rollback()
            if locals().get('owns_connection'):
                self.db.disconnect()
            return False

    def calculate_ledger_balance(self, account_id: int, to_date: Optional[str] = None) -> float:
        """
        Centralized ledger balance calculation.
        
        Calculates the balance for a ledger account using a simple MySQL-safe query.
        Uses only the ledger_entries table with no complex multi-table JOINs.
        
        Args:
            account_id: Account ID
            to_date: Optional end date (YYYY-MM-DD). If None, calculates current balance.
            
        Returns:
            Account balance as float (positive for debit balance, negative for credit balance)
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            placeholder = self.db._get_placeholder()
            
            if to_date:
                # Calculate balance up to and including to_date
                query = f"""
                    SELECT 
                        SUM(COALESCE(debit, 0)) - SUM(COALESCE(credit, 0)) AS balance
                    FROM ledger_entries
                    WHERE account_id = {placeholder} 
                    AND voucher_date <= {placeholder}
                    AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                """
                params = (account_id, to_date)
            else:
                # Calculate current balance
                query = f"""
                    SELECT 
                        SUM(COALESCE(debit, 0)) - SUM(COALESCE(credit, 0)) AS balance
                    FROM ledger_entries
                    WHERE account_id = {placeholder}
                    AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                """
                params = (account_id,)
            
            cursor.execute(query, params)
            result = cursor.fetchone()
            self.db.disconnect()
            
            balance = result[0] if result and result[0] is not None else 0.0
            return round(float(balance), 2)
        except Exception as e:
            print(f"Error calculating ledger balance: {e}")
            if 'conn' in locals():
                self.db.disconnect()
            return 0.0

    # ============================================================
    # CENTRALIZED LEDGER BALANCE ENGINE (SSOT)
    # ============================================================

    def calculate_ledger_balance(self, company_id: int, account_id: int, to_date: Optional[str] = None) -> float:
        """
        Unified method to calculate ledger balance directly from ledger_entries.
        
        This is the SINGLE SOURCE OF TRUTH for ledger balance calculations.
        All other balance calculation methods must use this method.
        
        Args:
            company_id: Company ID
            account_id: Account ID
            to_date: Optional date string (YYYY-MM-DD) to calculate balance as of this date
                      If not provided, calculates balance up to current date
        
        Returns:
            Float balance: Positive = Dr balance, Negative = Cr balance
        """
        try:
            placeholder = self.db._get_placeholder()

            account_query = f"""
                SELECT opening_balance, opening_balance_type
                FROM ledger_accounts
                WHERE company_id = {placeholder} AND id = {placeholder}
            """
            account_result = self.db.execute_query(account_query, (company_id, account_id))
            if not account_result:
                return 0.0

            opening_balance = money_round(to_decimal(account_result[0].get('opening_balance') or 0.0))
            opening_type = str(account_result[0].get('opening_balance_type') or 'Dr').strip().lower()
            signed_opening = opening_balance if opening_type == 'dr' else -opening_balance

            # Build query with optional date filter
            if to_date:
                query = f"""
                    SELECT COALESCE(SUM(debit), 0) AS total_debit,
                           COALESCE(SUM(credit), 0) AS total_credit
                    FROM ledger_entries
                    WHERE company_id = {placeholder} AND account_id = {placeholder} AND DATE(voucher_date) <= DATE({placeholder})
                      AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                """
                result = self.db.execute_query(query, (company_id, account_id, to_date))
            else:
                query = f"""
                    SELECT COALESCE(SUM(debit), 0) AS total_debit,
                           COALESCE(SUM(credit), 0) AS total_credit
                    FROM ledger_entries
                    WHERE company_id = {placeholder} AND account_id = {placeholder}
                      AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                """
                result = self.db.execute_query(query, (company_id, account_id))

            movement_balance = Decimal("0.00")
            if result:
                total_debit = to_decimal(result[0].get('total_debit') or 0.0)
                total_credit = to_decimal(result[0].get('total_credit') or 0.0)
                movement_balance = total_debit - total_credit
            balance = money_round(signed_opening + movement_balance)
            return round(float(balance), 2)
        except Exception as e:
            print(f"Error calculating ledger balance: {e}")
            return 0.0

    # ============================================================
    # LEGACY BALANCE METHODS (DEPRECATED)
    # ============================================================

    def _get_account_balance_old(self, company_id: int, account_id: int, as_of_date: date = None) -> Dict[str, float]:
        """
        Get account balance as of a specific date.

        Args:
            company_id: Company ID
            account_id: Account ID
            as_of_date: Optional date (defaults to current date)

        Returns:
            Dictionary with debit, credit, and net balance
        """
        try:
            if as_of_date is None:
                as_of_date = date.today()

            # Get account details to determine Dr/Cr nature
            account = self.get_account(company_id, account_id)
            if not account:
                return {'debit': 0.0, 'credit': 0.0, 'net': 0.0}

            # Sum debits and credits
            placeholder = self.db._get_placeholder()
            query = f"""
                SELECT COALESCE(SUM(debit), 0.0) as total_debit,
                       COALESCE(SUM(credit), 0.0) as total_credit
                FROM ledger_entries
                WHERE company_id = {placeholder} AND account_id = {placeholder} AND voucher_date <= {placeholder}
                  AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
            """
            result = self.db.execute_query(query, (company_id, account_id, as_of_date))

            if result:
                total_debit = result[0]['total_debit']
                total_credit = result[0]['total_credit']

                # Add opening balance
                opening_balance = account.get('opening_balance', 0.0)
                opening_type = account.get('opening_balance_type', 'Dr')

                if opening_type == 'Dr':
                    total_debit += opening_balance
                else:
                    total_credit += opening_balance

                net_balance = total_debit - total_credit
                return {
                    'debit': total_debit,
                    'credit': total_credit,
                    'net': net_balance
                }

            return {'debit': 0.0, 'credit': 0.0, 'net': 0.0}
        except Exception as e:
            print(f"Error getting account balance: {e}")
            return {'debit': 0.0, 'credit': 0.0, 'net': 0.0}

    def _get_account_balance_formatted_old(self, company_id: int, account_id: int, to_date: date = None) -> Dict[str, Any]:
        """
        Get account balance with formatted display string for UI.

        Args:
            company_id: Company ID
            account_id: Account ID
            to_date: Optional date (defaults to current date)

        Returns:
            Dictionary with:
            - balance: absolute balance amount
            - side: "Dr" or "Cr"
            - display: formatted string like "100.00 Dr"
        """
        try:
            if to_date is None:
                to_date = date.today()

            # Use centralized calculate_ledger_balance method
            balance = self.calculate_ledger_balance(company_id, account_id, to_date.strftime('%Y-%m-%d') if to_date else None)

            if balance >= 0:
                side = "Dr"
            else:
                side = "Cr"
                balance = abs(balance)

            return {
                "balance": round(balance, 2),
                "side": side,
                "display": f"{balance:,.2f} {side}"
            }
        except Exception as e:
            print(f"Error getting formatted account balance: {e}")
            return {"balance": 0.0, "side": "Dr", "display": "0.00 Dr"}

    def _get_account_balance_before_date_old(self, company_id: int, account_id: int, before_date: date) -> Dict[str, float]:
        """
        Get account balance before a specific date.

        Args:
            company_id: Company ID
            account_id: Account ID
            before_date: Date (exclusive)

        Returns:
            Dictionary with debit, credit, and net balance
        """
        try:
            # Get account details
            account = self.get_account(company_id, account_id)
            if not account:
                return {'debit': 0.0, 'credit': 0.0, 'net': 0.0}

            # Sum debits and credits before date
            placeholder = self.db._get_placeholder()
            query = f"""
                SELECT COALESCE(SUM(debit), 0.0) as total_debit,
                       COALESCE(SUM(credit), 0.0) as total_credit
                FROM ledger_entries
                WHERE company_id = {placeholder} AND account_id = {placeholder} AND voucher_date < {placeholder}
                  AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
            """
            result = self.db.execute_query(query, (company_id, account_id, before_date))

            if result:
                total_debit = result[0]['total_debit']
                total_credit = result[0]['total_credit']

                # Add opening balance
                opening_balance = account.get('opening_balance', 0.0)
                opening_type = account.get('opening_balance_type', 'Dr')

                if opening_type == 'Dr':
                    total_debit += opening_balance
                else:
                    total_credit += opening_balance

                net_balance = total_debit - total_credit
                return {
                    'debit': total_debit,
                    'credit': total_credit,
                    'net': net_balance
                }

            return {'debit': 0.0, 'credit': 0.0, 'net': 0.0}
        except Exception as e:
            print(f"Error getting account balance before date: {e}")
            return {'debit': 0.0, 'credit': 0.0, 'net': 0.0}

    def get_running_ledger(self, company_id: int, account_id: int,
                         from_date: date = None, to_date: date = None,
                         limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get running ledger for an account with pagination.

        Args:
            company_id: Company ID
            account_id: Account ID
            from_date: Optional start date
            to_date: Optional end date
            limit: Number of records to return
            offset: Number of records to skip

        Returns:
            List of ledger entries with running balance
        """
        try:
            placeholder = self.db._get_placeholder()
            query = f"""
                SELECT DISTINCT le.id,
                       le.voucher_type,
                       le.voucher_id,
                       le.voucher_no,
                       le.voucher_date,
                       le.account_id,
                       le.contra_account_id,
                       le.narration,
                       le.debit,
                       le.credit,
                       le.running_balance,
                       le.created_at
                FROM ledger_entries le
                WHERE le.company_id = {placeholder} AND le.account_id = {placeholder}
                  AND le.voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
            """
            params = [company_id, account_id]

            if from_date:
                query += f" AND le.voucher_date >= {placeholder}"
                params.append(from_date)
            if to_date:
                query += f" AND le.voucher_date <= {placeholder}"
                params.append(to_date)

            query += f" ORDER BY le.voucher_date, le.id LIMIT {placeholder} OFFSET {placeholder}"
            params.extend([limit, offset])

            return self.db.execute_query(query, params)
        except Exception as e:
            print(f"Error getting running ledger: {e}")
            return []

    def get_trial_balance(self, company_id: int, as_of_date: date = None) -> List[Dict[str, Any]]:
        """
        Get trial balance for all accounts as of a date.

        Args:
            company_id: Company ID
            as_of_date: Optional date (defaults to current date)

        Returns:
            List of account balances
        """
        try:
            if as_of_date is None:
                as_of_date = date.today()

            accounts = self.search_accounts(company_id, is_active=True)
            trial_balance = []

            for account in accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], as_of_date)
                trial_balance.append({
                    'account_id': account['id'],
                    'account_name': account['account_name'],
                    'account_type': account['account_type'],
                    'debit': balance['debit'],
                    'credit': balance['credit'],
                    'net': balance['net']
                })

            return trial_balance
        except Exception as e:
            print(f"Error getting trial balance: {e}")
            return []

    def get_profit_loss_data(self, company_id: int, from_date: date = None,
                            to_date: date = None) -> Dict[str, Any]:
        """
        Get profit and loss data for a period.

        Args:
            company_id: Company ID
            from_date: Optional start date
            to_date: Optional end date

        Returns:
            Dictionary with income, expenses, and net profit/loss
        """
        try:
            if to_date is None:
                to_date = date.today()
            if from_date is None:
                from_date = to_date.replace(day=1)  # First day of current month

            # Get income accounts
            income_accounts = self.search_accounts(company_id, account_type='income')
            total_income = 0.0

            for account in income_accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], to_date)
                # Income accounts normally have credit balance
                total_income += balance['credit'] - balance['debit']

            # Get expense accounts
            expense_accounts = self.search_accounts(company_id, account_type='expense')
            total_expense = 0.0

            for account in expense_accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], to_date)
                # Expense accounts normally have debit balance
                total_expense += balance['debit'] - balance['credit']

            net_profit_loss = total_income - total_expense

            return {
                'total_income': total_income,
                'total_expense': total_expense,
                'net_profit_loss': net_profit_loss,
                'from_date': from_date,
                'to_date': to_date
            }
        except Exception as e:
            print(f"Error getting profit loss data: {e}")
            return {
                'total_income': 0.0,
                'total_expense': 0.0,
                'net_profit_loss': 0.0,
                'from_date': from_date,
                'to_date': to_date
            }

    def get_balance_sheet_data(self, company_id: int, as_of_date: date = None) -> Dict[str, Any]:
        """
        Get balance sheet data as of a date.

        Args:
            company_id: Company ID
            as_of_date: Optional date (defaults to current date)

        Returns:
            Dictionary with assets, liabilities, and equity
        """
        try:
            if as_of_date is None:
                as_of_date = date.today()

            # Get assets (cash_bank, capital with debit balance)
            assets = 0.0
            cash_bank_accounts = self.search_accounts(company_id, account_type='cash_bank')
            for account in cash_bank_accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], as_of_date)
                assets += balance['debit'] - balance['credit']

            # Get debtors (party accounts with debit balance)
            party_accounts = self.search_accounts(company_id, account_type='party')
            for account in party_accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], as_of_date)
                if balance['debit'] > balance['credit']:
                    assets += balance['debit'] - balance['credit']

            # Get liabilities (party accounts with credit balance)
            liabilities = 0.0
            for account in party_accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], as_of_date)
                if balance['credit'] > balance['debit']:
                    liabilities += balance['credit'] - balance['debit']

            # Get tax liabilities
            tax_accounts = self.search_accounts(company_id, account_type='tax_liability')
            for account in tax_accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], as_of_date)
                if balance['credit'] > balance['debit']:
                    liabilities += balance['credit'] - balance['debit']

            # Get equity (capital)
            equity = 0.0
            capital_accounts = self.search_accounts(company_id, account_type='capital')
            for account in capital_accounts:
                balance = self.calculate_ledger_balance(company_id, account['id'], as_of_date)
                equity += balance['credit'] - balance['debit']

            # Add profit/loss to equity
            pl_data = self.get_profit_loss_data(company_id, to_date=as_of_date)
            equity += pl_data['net_profit_loss']

            return {
                'assets': assets,
                'liabilities': liabilities,
                'equity': equity,
                'as_of_date': as_of_date
            }
        except Exception as e:
            print(f"Error getting balance sheet data: {e}")
            return {
                'assets': 0.0,
                'liabilities': 0.0,
                'equity': 0.0,
                'as_of_date': as_of_date
            }

    def get_outstanding_parties(self, company_id: int, party_type: str = None) -> List[Dict[str, Any]]:
        """
        Get outstanding balances for parties.

        Args:
            company_id: Company ID
            party_type: Optional filter (debitor, creditor)

        Returns:
            List of party outstanding balances
        """
        try:
            # This would need integration with parties table
            # For now, return empty list
            return []
        except Exception as e:
            print(f"Error getting outstanding parties: {e}")
            return []

    def rebuild_running_balances(self, company_id: int) -> bool:
        """
        Rebuild running balances for all accounts.

        Args:
            company_id: Company ID

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # Get all accounts
            placeholder = self.db._get_placeholder()
            cursor.execute(f"SELECT id FROM ledger_accounts WHERE company_id = {placeholder}", (company_id,))
            account_ids = [row[0] for row in cursor.fetchall()]

            # Rebuild running balance for each account using full rebuild
            for account_id in account_ids:
                self._rebuild_account_running_balance(cursor, company_id, account_id)

            conn.commit()
            self.db.disconnect()
            return True
        except Exception as e:
            print(f"Error rebuilding running balances: {e}")
            if 'conn' in locals():
                conn.rollback()
            self.db.disconnect()
            return False

    # ============================================================
    # VOUCHER HELPERS
    # ============================================================

    def _safe_amount(self, value) -> float:
        """Convert None, blank, Decimal, float, and invalid values safely to float money amount.

        Ledger posting entries are stored as REAL and many existing callers pass floats.
        Returning float here avoids Decimal + float TypeError regressions while still
        using the project's Decimal parser for safe input cleanup.
        """
        try:
            return float(to_decimal(value))
        except Exception:
            return 0.0

    def _sum_item_tax_split(self, items: List[Dict[str, Any]]) -> Dict[str, float]:
        """Return split GST totals from item rows as float amounts for ledger posting."""
        result = {
            "cgst_total": 0.0,
            "sgst_total": 0.0,
            "igst_total": 0.0,
            "cess_total": 0.0,
            "tax_total": 0.0,
        }
        for item in items:
            result["cgst_total"] += self._safe_amount(item.get("cgst_amount"))
            result["sgst_total"] += self._safe_amount(item.get("sgst_amount"))
            result["igst_total"] += self._safe_amount(item.get("igst_amount"))
            result["cess_total"] += self._safe_amount(item.get("cess_amount"))
            result["tax_total"] += self._safe_amount(item.get("tax_amount"))
        return result

    def post_sales_voucher(self, company_id: int, sale_id: int, sale_data: Dict[str, Any],
                          sale_items: List[Dict[str, Any]]) -> bool:
        """Post sales voucher with proper double-entry.

        Credit Sale:  Dr Debitor  |  Cr Sales + Cr Output GST/CESS
        Cash Sale:    Dr Cash     |  Cr Sales + Cr Output GST/CESS
        """
        try:
            self.ensure_system_accounts(company_id)

            sales_acct = self.get_account_by_name_cached(company_id, 'Sales Account')
            if not sales_acct:
                return False

            grand_total = self._safe_amount(sale_data.get('grand_total'))
            cgst_total  = self._safe_amount(sale_data.get('cgst_total'))
            sgst_total  = self._safe_amount(sale_data.get('sgst_total'))
            igst_total  = self._safe_amount(sale_data.get('igst_total'))
            cess_total  = self._safe_amount(sale_data.get('cess_total'))
            tax_total   = self._safe_amount(sale_data.get('tax_total'))

            # If header split totals are missing or zero, calculate from item rows
            if cgst_total == 0 and sgst_total == 0 and igst_total == 0 and cess_total == 0 and sale_items:
                item_tax_split = self._sum_item_tax_split(sale_items)
                cgst_total = item_tax_split['cgst_total']
                sgst_total = item_tax_split['sgst_total']
                igst_total = item_tax_split['igst_total']
                cess_total = item_tax_split['cess_total']
                if tax_total == 0:
                    tax_total = item_tax_split['tax_total']

            net_sales   = round(grand_total - tax_total, 2)

            entries = []

            # Cr Sales (net of tax)
            entries.append({'account_id': sales_acct['id'], 'debit': 0.0, 'credit': net_sales})

            # Cr Output GST/CESS (split by nature)
            nature = str(sale_data.get('nature', 'Local')).lower()
            if 'inter' in nature:
                if igst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Output IGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': igst_total})
            else:
                if cgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Output CGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': cgst_total})
                if sgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Output SGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': sgst_total})
            if cess_total > 0:
                a = self.get_account_by_name_cached(company_id, 'Output CESS')
                if a:
                    entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': cess_total})

            # Dr side: Handle amount_received for credit sales
            # For cash sales: Dr Cash with grand_total
            # For credit sales with partial payment: Dr Cash (amt_received) + Dr Debitor (balance)
            # For credit sales with no payment: Dr Debitor with grand_total
            sale_type = str(sale_data.get('sales_type', 'Credit')).lower()
            amount_received = self._safe_amount(sale_data.get('amount_received', 0.0))
            
            if 'cash' in sale_type:
                # Cash sale: full amount to Cash
                cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                if cash_acct:
                    entries.append({'account_id': cash_acct['id'], 'debit': grand_total, 'credit': 0.0})
                else:
                    susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                    if susp:
                        entries.append({'account_id': susp['id'], 'debit': grand_total, 'credit': 0.0})
            else:
                # Credit sale: split between Cash (if amount_received > 0) and Debitor
                party_id = sale_data.get('party_id')
                party_name = sale_data.get('customer_name') or sale_data.get('party_name', '')
                debitor_acct = None
                if party_id:
                    debitor_acct = self.get_account_by_party_id(company_id, party_id)
                if not debitor_acct:
                    debitor_acct = self.get_account_by_name_cached(company_id, 'Sundry Debtors')

                # Post cash received portion
                if amount_received > 0:
                    cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                    if cash_acct:
                        entries.append({'account_id': cash_acct['id'], 'debit': amount_received, 'credit': 0.0})
                
                # Post balance to debitor
                balance_due = grand_total - amount_received
                if balance_due > 0:
                    if debitor_acct:
                        entries.append({'account_id': debitor_acct['id'], 'debit': balance_due, 'credit': 0.0})
                    else:
                        susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                        if susp:
                            entries.append({'account_id': susp['id'], 'debit': balance_due, 'credit': 0.0})

            # Validate balance
            total_dr = sum(e['debit'] for e in entries)
            total_cr = sum(e['credit'] for e in entries)
            if total_dr != total_cr:
                raise ValueError(f"Sales voucher imbalance: Dr={total_dr} Cr={total_cr}")

            return self.post_double_entry(
                company_id, 'sales', sale_id,
                sale_data.get('invoice_number', sale_data.get('invoice_no', '')),
                sale_data.get('invoice_date'),
                entries,
                sale_data.get('narration'), 'sale', sale_id
            )
        except Exception as e:
            print(f"Error posting sales voucher: {e}")
            return False

    def post_purchase_voucher(self, company_id: int, purchase_id: int, purchase_data: Dict[str, Any],
                             purchase_items: List[Dict[str, Any]]) -> bool:
        """Post purchase voucher with proper double-entry.

        Credit Purchase:  Dr Purchase + Dr Input GST/CESS  |  Cr Creditor
        Cash Purchase:    Dr Purchase + Dr Input GST/CESS  |  Cr Cash
        """
        try:
            print(f"[DEBUG post_purchase_voucher] START: company_id={company_id}, purchase_id={purchase_id}")
            self.ensure_system_accounts(company_id)

            purch_acct = self.get_account_by_name_cached(company_id, 'Purchase Account')
            if not purch_acct:
                print(f"[DEBUG post_purchase_voucher] FAILED: Purchase Account not found")
                return False

            grand_total = self._safe_amount(purchase_data.get('grand_total'))
            cgst_total  = self._safe_amount(purchase_data.get('cgst_total'))
            sgst_total  = self._safe_amount(purchase_data.get('sgst_total'))
            igst_total  = self._safe_amount(purchase_data.get('igst_total'))
            cess_total  = self._safe_amount(purchase_data.get('cess_total'))
            tax_total   = self._safe_amount(purchase_data.get('tax_total'))

            print(f"[DEBUG post_purchase_voucher] grand_total={grand_total}, tax_total={tax_total}")

            # If header split totals are missing or zero, calculate from item rows
            if cgst_total == 0 and sgst_total == 0 and igst_total == 0 and cess_total == 0 and purchase_items:
                item_tax_split = self._sum_item_tax_split(purchase_items)
                cgst_total = item_tax_split['cgst_total']
                sgst_total = item_tax_split['sgst_total']
                igst_total = item_tax_split['igst_total']
                cess_total = item_tax_split['cess_total']
                if tax_total == 0:
                    tax_total = item_tax_split['tax_total']

            net_purch   = round(grand_total - tax_total, 2)

            entries = []

            # Dr Purchase (net of tax)
            entries.append({'account_id': purch_acct['id'], 'debit': net_purch, 'credit': 0.0})

            # Dr Input GST/CESS (split by nature)
            nature = str(purchase_data.get('nature', 'Local')).lower()
            if 'inter' in nature:
                if igst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Input IGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': igst_total, 'credit': 0.0})
            else:
                if cgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Input CGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': cgst_total, 'credit': 0.0})
                if sgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Input SGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': sgst_total, 'credit': 0.0})
            if cess_total > 0:
                a = self.get_account_by_name_cached(company_id, 'Input CESS')
                if a:
                    entries.append({'account_id': a['id'], 'debit': cess_total, 'credit': 0.0})

            # Cr side: Handle amount_paid for credit purchases
            # For cash purchases: Cr Cash with grand_total
            # For credit purchases with partial payment: Cr Cash (amt_paid) + Cr Creditor (balance)
            # For credit purchases with no payment: Cr Creditor with grand_total
            purch_type = str(purchase_data.get('purchase_type', 'Credit')).lower()
            amount_paid = self._safe_amount(purchase_data.get('amount_paid', 0.0))
            
            print(f"[DEBUG post_purchase_voucher] purch_type='{purch_type}', amount_paid={amount_paid}")
            
            if 'cash' in purch_type:
                # Cash purchase: full amount from Cash
                print(f"[DEBUG post_purchase_voucher] CASH PURCHASE detected")
                cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                if cash_acct:
                    entries.append({'account_id': cash_acct['id'], 'debit': 0.0, 'credit': grand_total})
                    print(f"[DEBUG post_purchase_voucher] Added Cash Account entry: credit={grand_total}")
                else:
                    susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                    if susp:
                        entries.append({'account_id': susp['id'], 'debit': 0.0, 'credit': grand_total})
                        print(f"[DEBUG post_purchase_voucher] Added Suspense Account entry (Cash not found)")
            else:
                # Credit purchase: split between Cash (if amount_paid > 0) and Creditor
                print(f"[DEBUG post_purchase_voucher] CREDIT PURCHASE detected")
                party_id = purchase_data.get('party_id')
                creditor_acct = None
                if party_id:
                    creditor_acct = self.get_account_by_party_id(company_id, party_id)
                if not creditor_acct:
                    creditor_acct = self.get_account_by_name_cached(company_id, 'Sundry Creditors')

                # Post cash paid portion
                if amount_paid > 0:
                    cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                    if cash_acct:
                        entries.append({'account_id': cash_acct['id'], 'debit': 0.0, 'credit': amount_paid})
                
                # Post balance to creditor
                balance_due = grand_total - amount_paid
                if balance_due > 0:
                    if creditor_acct:
                        entries.append({'account_id': creditor_acct['id'], 'debit': 0.0, 'credit': balance_due})
                    else:
                        susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                        if susp:
                            entries.append({'account_id': susp['id'], 'debit': 0.0, 'credit': balance_due})

            total_dr = sum(e['debit'] for e in entries)
            total_cr = sum(e['credit'] for e in entries)
            print(f"[DEBUG post_purchase_voucher] Entries: {entries}")
            print(f"[DEBUG post_purchase_voucher] Total Dr={total_dr}, Total Cr={total_cr}")
            if total_dr != total_cr:
                raise ValueError(f"Purchase voucher imbalance: Dr={total_dr} Cr={total_cr}")

            print(f"[DEBUG post_purchase_voucher] Calling post_double_entry...")
            result = self.post_double_entry(
                company_id, 'purchase', purchase_id,
                purchase_data.get('purchase_number', ''),
                purchase_data.get('purchase_date'),
                entries,
                purchase_data.get('narration'), 'purchase', purchase_id
            )
            print(f"[DEBUG post_purchase_voucher] post_double_entry returned: {result}")
            return result
        except Exception as e:
            print(f"[DEBUG post_purchase_voucher] EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
            return False

    def post_sales_return_voucher(self, company_id: int, sr_id: int,
                                  sr_data: Dict[str, Any], sr_items: List[Dict[str, Any]]) -> bool:
        """Post sales return voucher with proper double-entry.

        Cash Return:   Dr Sales Return + Dr Output GST reversal  |  Cr Cash
        Credit Return: Dr Sales Return + Dr Output GST reversal  |  Cr Debitor
        """
        try:
            self.ensure_system_accounts(company_id)

            sr_acct = self.get_account_by_name_cached(company_id, 'Sales Return Account')
            if not sr_acct:
                return False

            grand_total = self._safe_amount(sr_data.get('grand_total'))
            cgst_total  = self._safe_amount(sr_data.get('cgst_total'))
            sgst_total  = self._safe_amount(sr_data.get('sgst_total'))
            igst_total  = self._safe_amount(sr_data.get('igst_total'))
            cess_total  = self._safe_amount(sr_data.get('cess_total'))
            tax_total   = self._safe_amount(sr_data.get('tax_total'))

            # If header split totals are missing or zero, calculate from item rows
            if cgst_total == 0 and sgst_total == 0 and igst_total == 0 and cess_total == 0 and sr_items:
                item_tax_split = self._sum_item_tax_split(sr_items)
                cgst_total = item_tax_split['cgst_total']
                sgst_total = item_tax_split['sgst_total']
                igst_total = item_tax_split['igst_total']
                cess_total = item_tax_split['cess_total']
                if tax_total == 0:
                    tax_total = item_tax_split['tax_total']

            net_return  = round(grand_total - tax_total, 2)

            entries = []

            # Dr Sales Return (net)
            entries.append({'account_id': sr_acct['id'], 'debit': net_return, 'credit': 0.0})

            # Dr Output GST reversal
            nature = str(sr_data.get('nature', 'Local')).lower()
            if 'inter' in nature:
                if igst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Output IGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': igst_total, 'credit': 0.0})
            else:
                if cgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Output CGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': cgst_total, 'credit': 0.0})
                if sgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Output SGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': sgst_total, 'credit': 0.0})
            if cess_total > 0:
                a = self.get_account_by_name_cached(company_id, 'Output CESS')
                if a:
                    entries.append({'account_id': a['id'], 'debit': cess_total, 'credit': 0.0})

            # Cr side: Handle amount_received for credit returns
            # For cash returns: Cr Cash with grand_total
            # For credit returns with partial refund: Cr Cash (amt_received) + Cr Debitor (balance)
            # For credit returns with no refund: Cr Debitor with grand_total
            return_type = str(sr_data.get('return_type', 'Credit')).lower()
            amount_received = self._safe_amount(sr_data.get('amount_received', 0.0))
            
            if 'cash' in return_type:
                # Cash return: full amount to Cash
                cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                if cash_acct:
                    entries.append({'account_id': cash_acct['id'], 'debit': 0.0, 'credit': grand_total})
                else:
                    susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                    if susp:
                        entries.append({'account_id': susp['id'], 'debit': 0.0, 'credit': grand_total})
            else:
                # Credit return: split between Cash (if amount_received > 0) and Debitor
                party_id = sr_data.get('party_id')
                debitor_acct = None
                if party_id:
                    debitor_acct = self.get_account_by_party_id(company_id, party_id)
                if not debitor_acct:
                    debitor_acct = self.get_account_by_name_cached(company_id, 'Sundry Debtors')

                # Post cash refund portion
                if amount_received > 0:
                    cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                    if cash_acct:
                        entries.append({'account_id': cash_acct['id'], 'debit': 0.0, 'credit': amount_received})
                
                # Post balance to debitor
                balance_due = grand_total - amount_received
                if balance_due > 0:
                    if debitor_acct:
                        entries.append({'account_id': debitor_acct['id'], 'debit': 0.0, 'credit': balance_due})
                    else:
                        susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                        if susp:
                            entries.append({'account_id': susp['id'], 'debit': 0.0, 'credit': balance_due})

            total_dr = sum(e['debit'] for e in entries)
            total_cr = sum(e['credit'] for e in entries)
            if total_dr != total_cr:
                raise ValueError(f"Sales return voucher imbalance: Dr={total_dr} Cr={total_cr}")

            return self.post_double_entry(
                company_id, 'sales_return', sr_id,
                sr_data.get('return_no', ''),
                sr_data.get('return_date'),
                entries,
                sr_data.get('narration'), 'sales_return', sr_id
            )
        except Exception as e:
            print(f"Error posting sales return voucher: {e}")
            return False

    def post_purchase_return_voucher(self, company_id: int, pr_id: int,
                                     pr_data: Dict[str, Any], pr_items: List[Dict[str, Any]]) -> bool:
        """Post purchase return voucher with proper double-entry.

        Cash Return:   Dr Cash              |  Cr Purchase Return + Cr Input GST reversal
        Credit Return: Dr Creditor          |  Cr Purchase Return + Cr Input GST reversal
        """
        try:
            self.ensure_system_accounts(company_id)

            pr_acct = self.get_account_by_name_cached(company_id, 'Purchase Return Account')
            if not pr_acct:
                return False

            grand_total = self._safe_amount(pr_data.get('grand_total'))
            cgst_total  = self._safe_amount(pr_data.get('cgst_total'))
            sgst_total  = self._safe_amount(pr_data.get('sgst_total'))
            igst_total  = self._safe_amount(pr_data.get('igst_total'))
            cess_total  = self._safe_amount(pr_data.get('cess_total'))
            tax_total   = self._safe_amount(pr_data.get('tax_total'))

            # If header split totals are missing or zero, calculate from item rows
            if cgst_total == 0 and sgst_total == 0 and igst_total == 0 and cess_total == 0 and pr_items:
                item_tax_split = self._sum_item_tax_split(pr_items)
                cgst_total = item_tax_split['cgst_total']
                sgst_total = item_tax_split['sgst_total']
                igst_total = item_tax_split['igst_total']
                cess_total = item_tax_split['cess_total']
                if tax_total == 0:
                    tax_total = item_tax_split['tax_total']

            net_return  = round(grand_total - tax_total, 2)

            entries = []

            # Cr Purchase Return (net)
            entries.append({'account_id': pr_acct['id'], 'debit': 0.0, 'credit': net_return})

            # Cr Input GST reversal
            nature = str(pr_data.get('nature', 'Local')).lower()
            if 'inter' in nature:
                if igst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Input IGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': igst_total})
            else:
                if cgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Input CGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': cgst_total})
                if sgst_total > 0:
                    a = self.get_account_by_name_cached(company_id, 'Input SGST')
                    if a:
                        entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': sgst_total})
            if cess_total > 0:
                a = self.get_account_by_name_cached(company_id, 'Input CESS')
                if a:
                    entries.append({'account_id': a['id'], 'debit': 0.0, 'credit': cess_total})

            # Dr side: Handle amount_paid for credit returns
            # For cash returns: Dr Cash with grand_total
            # For credit returns with partial refund: Dr Cash (amt_paid) + Dr Creditor (balance)
            # For credit returns with no refund: Dr Creditor with grand_total
            return_type = str(pr_data.get('return_type', 'Credit')).lower()
            amount_paid = self._safe_amount(pr_data.get('amount_paid', 0.0))
            
            if 'cash' in return_type:
                # Cash return: full amount from Cash
                cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                if cash_acct:
                    entries.append({'account_id': cash_acct['id'], 'debit': grand_total, 'credit': 0.0})
                else:
                    susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                    if susp:
                        entries.append({'account_id': susp['id'], 'debit': grand_total, 'credit': 0.0})
            else:
                # Credit return: split between Cash (if amount_paid > 0) and Creditor
                party_id = pr_data.get('party_id')
                creditor_acct = None
                if party_id:
                    creditor_acct = self.get_account_by_party_id(company_id, party_id)
                if not creditor_acct:
                    creditor_acct = self.get_account_by_name_cached(company_id, 'Sundry Creditors')

                # Post cash refund portion
                if amount_paid > 0:
                    cash_acct = self.get_account_by_name_cached(company_id, 'Cash Account')
                    if cash_acct:
                        entries.append({'account_id': cash_acct['id'], 'debit': amount_paid, 'credit': 0.0})
                
                # Post balance to creditor
                balance_due = grand_total - amount_paid
                if balance_due > 0:
                    if creditor_acct:
                        entries.append({'account_id': creditor_acct['id'], 'debit': balance_due, 'credit': 0.0})
                    else:
                        susp = self.get_account_by_name_cached(company_id, 'Suspense Account')
                        if susp:
                            entries.append({'account_id': susp['id'], 'debit': balance_due, 'credit': 0.0})

            total_dr = sum(e['debit'] for e in entries)
            total_cr = sum(e['credit'] for e in entries)
            if total_dr != total_cr:
                raise ValueError(f"Purchase return voucher imbalance: Dr={total_dr} Cr={total_cr}")

            return self.post_double_entry(
                company_id, 'purchase_return', pr_id,
                pr_data.get('return_no', ''),
                pr_data.get('return_date'),
                entries,
                pr_data.get('narration'), 'purchase_return', pr_id
            )
        except Exception as e:
            print(f"Error posting purchase return voucher: {e}")
            return False

    # legacy alias kept for backward compat
    def create_purchase_return_ledger_entry(self, company_id, purchase_return_id, purchase_return_data):
        return self.post_purchase_return_voucher(company_id, purchase_return_id, purchase_return_data, [])

    def post_stock_adjustment_voucher(self, adjustment_data: Dict[str, Any], items_data: List[Dict[str, Any]]) -> bool:
        """Post consolidated ledger entries for stock adjustment.
        
        CONSOLIDATED entries (NOT per-item):
        - Stock Shortage (negative adjustment): Dr Stock Adjustment Loss | Cr Stock
        - Stock Excess (positive adjustment): Dr Stock | Cr Stock Adjustment Gain
        
        Uses Decimal for calculations.
        Validates Dr = Cr (±0.02 tolerance).
        """
        from decimal import Decimal
        
        company_id = adjustment_data['company_id']
        adjustment_id = adjustment_data.get('id')
        voucher_no = adjustment_data.get('voucher_no', '')
        voucher_date = adjustment_data.get('voucher_date')
        narration = adjustment_data.get('narration', '')
        
        try:
            self.ensure_system_accounts(company_id)
            
            stock_acct = self.get_account_by_name_cached(company_id, 'Stock Account')
            loss_acct = self.get_account_by_name_cached(company_id, 'Stock Adjustment Loss')
            gain_acct = self.get_account_by_name_cached(company_id, 'Stock Adjustment Gain')
            
            if not stock_acct:
                print("Error: Stock Account not found")
                return False
            
            # Calculate totals using Decimal
            total_increase = Decimal('0')
            total_decrease = Decimal('0')
            
            for item in items_data:
                difference_qty = Decimal(str(item.get('difference_qty', 0)))
                rate = Decimal(str(item.get('rate', 0)))
                value = difference_qty * rate
                
                if difference_qty > 0:
                    total_increase += value
                elif difference_qty < 0:
                    total_decrease += abs(value)
            
            entries = []
            
            # Stock Excess (positive adjustment): Dr Stock | Cr Stock Adjustment Gain
            if total_increase > 0:
                entries.append({
                    'account_id': stock_acct['id'],
                    'debit': float(total_increase),
                    'credit': 0.0
                })
                if gain_acct:
                    entries.append({
                        'account_id': gain_acct['id'],
                        'debit': 0.0,
                        'credit': float(total_increase)
                    })
            
            # Stock Shortage (negative adjustment): Dr Stock Adjustment Loss | Cr Stock
            if total_decrease > 0:
                if loss_acct:
                    entries.append({
                        'account_id': loss_acct['id'],
                        'debit': float(total_decrease),
                        'credit': 0.0
                    })
                entries.append({
                    'account_id': stock_acct['id'],
                    'debit': 0.0,
                    'credit': float(total_decrease)
                })
            
            # Validate Dr = Cr
            total_dr = sum(e['debit'] for e in entries)
            total_cr = sum(e['credit'] for e in entries)
            if abs(total_dr - total_cr) > 0.02:
                raise ValueError(f"Stock adjustment voucher imbalance: Dr={total_dr} Cr={total_cr}")
            
            # Post consolidated entries
            return self.post_double_entry(
                company_id,
                'stock_adjustment',
                adjustment_id,
                voucher_no,
                voucher_date,
                entries,
                narration,
                'stock_adjustment',
                adjustment_id
            )
        except Exception as e:
            print(f"Error posting stock adjustment voucher: {e}")
            return False

    def delete_stock_adjustment_voucher_entries(self, company_id: int, adjustment_id: int) -> bool:
        """Delete ledger entries for a stock adjustment.
        Uses centralized voucher deletion architecture with strict deletion protocol.
        """
        try:
            return self.delete_voucher_entries(company_id, 'stock_adjustment', adjustment_id)
        except Exception as e:
            print(f"Error deleting stock adjustment voucher entries: {e}")
            return False

    def post_receipt_voucher(self, company_id: int, receipt_id: int, receipt_data: Dict[str, Any]) -> bool:
        """
        Post receipt voucher (money received from debtor).

        Args:
            company_id: Company ID
            receipt_id: Receipt ID
            receipt_data: Receipt data

        Returns:
            True if successful, False otherwise
        """
        # Placeholder for future implementation
        return True

    def post_payment_voucher(self, company_id: int, payment_id: int, payment_data: Dict[str, Any]) -> bool:
        """
        Post payment voucher (money paid to creditor).

        Args:
            company_id: Company ID
            payment_id: Payment ID
            payment_data: Payment data

        Returns:
            True if successful, False otherwise
        """
        # Placeholder for future implementation
        return True

    def post_journal_voucher(self, company_id: int, journal_id: int, journal_data: Dict[str, Any],
                            entries: List[Dict[str, Any]]) -> bool:
        """
        Post journal voucher (general journal entry).

        Args:
            company_id: Company ID
            journal_id: Journal ID
            journal_data: Journal header data
            entries: Journal entries

        Returns:
            True if successful, False otherwise
        """
        # Placeholder for future implementation
        return True

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _rebuild_account_running_balance(self, cursor, company_id: int, account_id: int):
        """Rebuild running_balance for every entry of account_id in date+id order.

        Starts from opening_balance (Dr positive / Cr negative), then applies
        each debit (+) and credit (-) in chronological order.
        """
        try:
            placeholder = self.db._get_placeholder()
            cursor.execute(
                f"SELECT opening_balance, opening_balance_type FROM ledger_accounts WHERE id = {placeholder}",
                (account_id,)
            )
            row = cursor.fetchone()
            if not row:
                return
            ob = float(money_round(to_decimal(row[0] or 0.0)))
            ob_type = row[1] or 'Dr'
            running = ob if ob_type == 'Dr' else -ob

            cursor.execute(
                f"""SELECT id, debit, credit FROM ledger_entries
                   WHERE company_id = {placeholder} AND account_id = {placeholder}
                     AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                   ORDER BY voucher_date, id""",
                (company_id, account_id)
            )
            rows = cursor.fetchall()
            updates = []
            for r in rows:
                running += float(money_round(to_decimal(r[1] or 0.0))) - float(money_round(to_decimal(r[2] or 0.0)))
                updates.append((float(money_round(running)), r[0]))
            if updates:
                cursor.executemany(
                    f"UPDATE ledger_entries SET running_balance = {placeholder} WHERE id = {placeholder}",
                    updates
                )
        except Exception as e:
            print(f"Error rebuilding running balance for account {account_id}: {e}")

    def _update_running_balance(self, cursor, company_id: int, account_id: int, as_of_date):
        """Legacy shim — delegates to full rebuild."""
        self._rebuild_account_running_balance(cursor, company_id, account_id)

    def _get_voucher_details(self, company_id: int, voucher_type: str, voucher_id: int) -> Optional[Dict[str, Any]]:
        """
        Get voucher details for reposting.

        Args:
            company_id: Company ID
            voucher_type: Voucher type
            voucher_id: Voucher ID

        Returns:
            Voucher details dictionary
        """
        try:
            if voucher_type == 'sales':
                from .sales_logic import SalesLogic
                sales_logic = SalesLogic(self.db)
                result = sales_logic.get_sale_by_id(company_id, voucher_id)
                sale = result.get('data') if result and result.get('success') else None
                if sale:
                    return {
                        'voucher_no': sale.get('invoice_number', ''),
                        'voucher_date': sale.get('invoice_date'),
                        'narration': sale.get('narration'),
                        'reference_type': 'sale',
                        'reference_id': voucher_id
                    }
            elif voucher_type == 'purchase':
                from .purchase_logic import PurchaseLogic
                purchase_logic = PurchaseLogic(self.db)
                result = purchase_logic.get_purchase_by_id(company_id, voucher_id)
                purchase = result.get('data') if result and result.get('success') else None
                if purchase:
                    return {
                        'voucher_no': purchase.get('purchase_number', ''),
                        'voucher_date': purchase.get('purchase_date'),
                        'narration': purchase.get('narration'),
                        'reference_type': 'purchase',
                        'reference_id': voucher_id
                    }

            return None
        except Exception as e:
            print(f"Error getting voucher details: {e}")
            return None

    # ============================================================
    # SALES RETURN LEDGER HOOKS
    # ============================================================

    def create_sales_return_ledger_entry(self, company_id: int, sales_return_id: int,
                                          sales_return_data: Dict[str, Any]) -> bool:
        """Create ledger entries for a sales return."""
        return self.post_sales_return_voucher(company_id, sales_return_id, sales_return_data, [])

    def update_sales_return_ledger_entry(self, company_id: int, sales_return_id: int,
                                          sales_return_data: Dict[str, Any]) -> bool:
        """Update ledger entries for a sales return (delete old, repost fresh)."""
        self.delete_voucher_entries(company_id, 'sales_return', sales_return_id)
        return self.post_sales_return_voucher(company_id, sales_return_id, sales_return_data, [])

    def delete_sales_return_ledger_entry(self, company_id: int, sales_return_id: int) -> bool:
        """Delete ledger entries for a sales return.
        Uses centralized voucher deletion architecture with strict deletion protocol.
        """
        return self.delete_voucher_entries(company_id, 'sales_return', sales_return_id)

    # ============================================================
    # LEDGER PAGE SUPPORT METHODS
    # ============================================================

    def ensure_party_ledger_accounts(self, company_id: int) -> bool:
        """
        Ensure all parties have corresponding ledger accounts.
        Creates missing ledger accounts for parties without ledger_account_id.
        Preserves opening_balance from party master.
        Uses backend-safe placeholders for MySQL compatibility.

        Args:
            company_id: Company ID

        Returns:
            True if successful, False otherwise
        """
        try:
            placeholder = self.db._get_placeholder()
            # Get all parties for this company
            parties = self.db.execute_query(
                f"""SELECT id, name, party_type, opening_balance
                    FROM parties
                    WHERE company_id = {placeholder}
                    ORDER BY name""",
                (company_id,)
            )

            if not parties:
                return True  # No parties to process

            created_count = 0
            for party in parties:
                party_id = party['id']
                party_name = party['name']
                party_type = party.get('party_type', 'Debitor')
                opening_balance = float(money_round(to_decimal(party.get('opening_balance', 0.0) or 0.0)))

                # Check if party already has a linked ledger account
                result = self.db.execute_query(
                    f"SELECT ledger_account_id FROM parties WHERE id = {placeholder} AND company_id = {placeholder}",
                    (party_id, company_id)
                )

                if result and result[0].get('ledger_account_id'):
                    # Already has a ledger account - verify it exists
                    acct_id = result[0]['ledger_account_id']
                    acct_check = self.db.execute_query(
                        f"SELECT id FROM ledger_accounts WHERE id = {placeholder} AND company_id = {placeholder}",
                        (acct_id, company_id)
                    )
                    if acct_check:
                        continue  # Account exists, skip

                # Determine opening balance type based on party_type
                if party_type == 'Creditor':
                    ob_type = 'Cr'
                elif party_type == 'Debitor':
                    ob_type = 'Dr'
                else:  # 'Both'
                    ob_type = 'Dr'  # Default to Dr for 'Both' type

                # Check if an account with this name already exists
                existing = self.get_account_by_name(company_id, party_name)
                if existing:
                    # Link existing account to party
                    try:
                        conn = self.db.connect()
                        cursor = conn.cursor()
                        cursor.execute(
                            f"UPDATE parties SET ledger_account_id = {placeholder} WHERE id = {placeholder} AND company_id = {placeholder}",
                            (existing['id'], party_id, company_id)
                        )
                        conn.commit()
                        self.db.disconnect()
                    except Exception as e:
                        print(f"Warning: could not link party {party_name}: {e}")
                else:
                    # Create new ledger account for party
                    group_name = 'Sundry Debtors' if ob_type == 'Dr' else 'Sundry Creditors'
                    acct_id = self.create_account(company_id, {
                        'account_name': party_name,
                        'account_code': None,
                        'account_type': 'party',
                        'group_name': group_name,
                        'opening_balance': opening_balance,
                        'opening_balance_type': ob_type,
                    })

                    if acct_id:
                        # Link the new account to the party
                        try:
                            conn = self.db.connect()
                            cursor = conn.cursor()
                            cursor.execute(
                                f"UPDATE parties SET ledger_account_id = {placeholder} WHERE id = {placeholder} AND company_id = {placeholder}",
                                (acct_id, party_id, company_id)
                            )
                            conn.commit()
                            self.db.disconnect()
                            created_count += 1
                        except Exception as e:
                            print(f"Warning: could not link new party account {party_name}: {e}")

            if created_count > 0:
                print(f"Created {created_count} party ledger accounts")
                self.invalidate_accounts_cache(company_id)

            return True

        except Exception as e:
            print(f"Error ensuring party ledger accounts: {e}")
            return False

    def get_debtor_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Get all debtor party accounts with their ledger account info.
        Includes parties where party_type IN ('Debitor', 'Both').

        Args:
            company_id: Company ID

        Returns:
            List of debtor account dictionaries
        """
        try:
            placeholder = self.db._get_placeholder()
            # First ensure all parties have ledger accounts
            self.ensure_party_ledger_accounts(company_id)

            # Get all party ledger accounts that are debtors
            result = self.db.execute_query(
                f"""SELECT
                        la.id,
                        la.account_name,
                        la.account_type,
                        la.group_name,
                        la.opening_balance,
                        la.opening_balance_type,
                        p.id as party_id,
                        p.party_type
                    FROM ledger_accounts la
                    INNER JOIN parties p ON p.ledger_account_id = la.id
                    WHERE la.company_id = {placeholder}
                      AND la.account_type = 'party'
                      AND p.party_type IN ('Debitor', 'Both')
                      AND la.is_active = 1
                    ORDER BY la.account_name""",
                (company_id,)
            )

            return [dict(row) for row in result] if result else []

        except Exception as e:
            print(f"Error getting debtor accounts: {e}")
            return []

    def get_creditor_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Get all creditor party accounts with their ledger account info.
        Includes parties where party_type IN ('Creditor', 'Both').

        Args:
            company_id: Company ID

        Returns:
            List of creditor account dictionaries
        """
        try:
            placeholder = self.db._get_placeholder()
            # First ensure all parties have ledger accounts
            self.ensure_party_ledger_accounts(company_id)

            # Get all party ledger accounts that are creditors
            result = self.db.execute_query(
                f"""SELECT
                        la.id,
                        la.account_name,
                        la.account_type,
                        la.group_name,
                        la.opening_balance,
                        la.opening_balance_type,
                        p.id as party_id,
                        p.party_type
                    FROM ledger_accounts la
                    INNER JOIN parties p ON p.ledger_account_id = la.id
                    WHERE la.company_id = {placeholder}
                      AND la.account_type = 'party'
                      AND p.party_type IN ('Creditor', 'Both')
                      AND la.is_active = 1
                    ORDER BY la.account_name""",
                (company_id,)
            )

            return [dict(row) for row in result] if result else []

        except Exception as e:
            print(f"Error getting creditor accounts: {e}")
            return []

    def get_group_account_summary(self, company_id: int, group: str,
                                   from_date: date, to_date: date) -> Dict[str, Any]:
        """
        Get account summary for a specific ledger group.

        Args:
            company_id: Company ID
            group: Group identifier ('debtors', 'creditors', 'cash_bank', 'sales',
                                      'purchase', 'sales_return', 'purchase_return',
                                      'tax', 'stock', 'expense', 'income', 'all')
            from_date: Start date for period calculation
            to_date: End date for period calculation

        Returns:
            Dict with 'accounts' list and 'totals' dict
        """
        try:
            accounts = []

            if group == 'debtors':
                accounts = self.get_debtor_accounts(company_id)
            elif group == 'creditors':
                accounts = self.get_creditor_accounts(company_id)
            elif group == 'cash_bank':
                accounts = self.search_accounts(company_id, account_type='cash_bank', is_active=True)
            elif group == 'sales':
                all_income = self.search_accounts(company_id, account_type='income', is_active=True)
                accounts = [a for a in all_income if 'sales' in a.get('account_name', '').lower()]
            elif group == 'purchase':
                all_expense = self.search_accounts(company_id, account_type='expense', is_active=True)
                accounts = [a for a in all_expense if 'purchase' in a.get('account_name', '').lower()]
            elif group == 'sales_return':
                accounts = self.search_accounts(company_id, account_type='expense', is_active=True)
                accounts = [a for a in accounts if 'sales return' in a.get('account_name', '').lower()]
            elif group == 'purchase_return':
                accounts = self.search_accounts(company_id, account_type='income', is_active=True)
                accounts = [a for a in accounts if 'purchase return' in a.get('account_name', '').lower()]
            elif group == 'tax':
                accounts = self.search_accounts(company_id, account_type='tax_liability', is_active=True)
            elif group == 'stock':
                accounts = self.search_accounts(company_id, account_type='stock', is_active=True)
            elif group == 'expense':
                accounts = self.search_accounts(company_id, account_type='expense', is_active=True)
            elif group == 'income':
                accounts = self.search_accounts(company_id, account_type='income', is_active=True)
            elif group == 'all':
                accounts = self.search_accounts(company_id, is_active=True)

            # Calculate balances for each account
            account_data = []
            total_dr = 0.0
            total_cr = 0.0

            for acct in accounts:
                account_id = acct['id']

                # Get opening balance before from_date
                opening_data = self._get_account_balance_before_date_old(company_id, account_id, from_date)
                opening_net = opening_data['net']

                # Get closing balance as of to_date
                closing_data = self._get_account_balance_old(company_id, account_id, to_date)
                closing_net = closing_data['net']

                # Calculate period movement
                period_dr = closing_data['debit'] - opening_data['debit']
                period_cr = closing_data['credit'] - opening_data['credit']

                # Format opening and closing with Dr/Cr
                opening_fmt = self._fmt_balance(opening_net)
                closing_fmt = self._fmt_balance(closing_net)

                account_data.append({
                    'account_id': account_id,
                    'account_name': acct.get('account_name', ''),
                    'account_type': acct.get('account_type', ''),
                    'group_name': acct.get('group_name', ''),
                    'opening_balance': opening_net,
                    'opening_formatted': opening_fmt,
                    'period_debit': period_dr,
                    'period_credit': period_cr,
                    'closing_balance': closing_net,
                    'closing_formatted': closing_fmt,
                })

                total_dr += period_dr
                total_cr += period_cr

            return {
                'accounts': account_data,
                'totals': {
                    'debit': total_dr,
                    'credit': total_cr,
                    'count': len(account_data)
                }
            }

        except Exception as e:
            print(f"Error getting group account summary: {e}")
            return {'accounts': [], 'totals': {'debit': 0.0, 'credit': 0.0, 'count': 0}}

    def get_account_ledger(self, company_id: int, account_id: int,
                           from_date: date, to_date: date) -> Dict[str, Any]:
        """
        Get detailed ledger for a specific account.

        Args:
            company_id: Company ID
            account_id: Account ID
            from_date: Start date
            to_date: End date

        Returns:
            Dict with 'opening_balance', 'entries', 'totals', 'closing_balance'
        """
        try:
            # Get opening balance before from_date
            opening_data = self._get_account_balance_before_date_old(company_id, account_id, from_date)
            opening_net = opening_data['net']

            # Get ledger entries in date range with running balance
            entries = self.get_running_ledger(company_id, account_id, from_date, to_date, limit=5000)

            # Calculate totals for the period
            total_dr = sum(float(money_round(to_decimal(e.get('debit', 0.0) or 0.0))) for e in entries)
            total_cr = sum(float(money_round(to_decimal(e.get('credit', 0.0) or 0.0))) for e in entries)

            # Calculate closing balance
            closing_net = opening_net + total_dr - total_cr

            return {
                'opening_balance': opening_net,
                'opening_formatted': self._fmt_balance(opening_net),
                'entries': entries,
                'period_debit': total_dr,
                'period_credit': total_cr,
                'closing_balance': closing_net,
                'closing_formatted': self._fmt_balance(closing_net),
            }

        except Exception as e:
            print(f"Error getting account ledger: {e}")
            return {
                'opening_balance': 0.0,
                'opening_formatted': '0.00',
                'entries': [],
                'period_debit': 0.0,
                'period_credit': 0.0,
                'closing_balance': 0.0,
                'closing_formatted': '0.00',
            }

    @staticmethod
    def _fmt_balance(net: float) -> str:
        """Format a net balance with Dr/Cr suffix."""
        if net > 0.001:
            return f"{net:,.2f} Dr"
        elif net < -0.001:
            return f"{abs(net):,.2f} Cr"
        else:
            return "0.00"

    def rebuild_ledger_for_company(self, company_id: int) -> Dict[str, Any]:
        """
        Safely rebuild ledger entries for a company by reposting all saved vouchers.

        Args:
            company_id: Company ID

        Returns:
            Dict with success status, counts, and before/after ledger entry counts
        """
        result = {
            'success': False,
            'sales_posted': 0,
            'purchases_posted': 0,
            'sales_returns_posted': 0,
            'purchase_returns_posted': 0,
            'failed': [],
            'ledger_entries_before': 0,
            'ledger_entries_after': 0,
            'message': ''
        }

        try:
            print(f"[LEDGER REBUILD] Starting rebuild for company_id={company_id}")

            # Count ledger entries before rebuild
            ph = self.db._get_placeholder()
            before_count = self.db.execute_query(
                f"SELECT COUNT(*) as count FROM ledger_entries WHERE company_id = {ph}",
                (company_id,)
            )
            result['ledger_entries_before'] = before_count[0]['count'] if before_count else 0
            print(f"[LEDGER REBUILD] Ledger entries before: {result['ledger_entries_before']}")

            # Step 1: Ensure system accounts
            self.ensure_system_accounts(company_id)
            print(f"[LEDGER REBUILD] System accounts ensured")

            # Step 2: Ensure party ledger accounts
            self.ensure_party_ledger_accounts(company_id)
            print(f"[LEDGER REBUILD] Party ledger accounts ensured")

            # Step 3: Delete existing ledger_entries for this company only
            ph = self.db._get_placeholder()
            self.db.execute_update(
                f"DELETE FROM ledger_entries WHERE company_id = {ph}",
                (company_id,)
            )
            print(f"[LEDGER REBUILD] Deleted existing ledger_entries for company")

            # Step 4: Repost sales
            from .sales_logic import SalesLogic
            sales_logic = SalesLogic(self.db)
            sales = self.db.execute_query(
                f"SELECT id, invoice_number, invoice_date, party_id, sales_type, nature, "
                f"gstin, state, sales_rate, narration, sub_total, discount_total, tax_total, "
                f"round_off, grand_total, amount_received FROM sales WHERE company_id = {ph}",
                (company_id,)
            )
            for sale in sales or []:
                sale_id = sale['id']
                sale_items = self.db.execute_query(
                    f"SELECT * FROM sales_items WHERE sale_id = {ph}",
                    (sale_id,)
                )
                sale_data = dict(sale)
                if self.post_sales_voucher(company_id, sale_id, sale_data, sale_items or []):
                    result['sales_posted'] += 1
                else:
                    result['failed'].append(f"Sales #{sale.get('invoice_number', sale_id)}")
            print(f"[LEDGER REBUILD] Reposted {result['sales_posted']} sales")

            # Step 5: Repost purchases
            from .purchase_logic import PurchaseLogic
            purchase_logic = PurchaseLogic(self.db)
            purchases = self.db.execute_query(
                f"SELECT id, purchase_number, purchase_date, party_id, purchase_type, nature, "
                f"gstin, state, narration, sub_total, discount_total, tax_total, "
                f"round_off, grand_total, amount_paid FROM purchases WHERE company_id = {ph}",
                (company_id,)
            )
            for purchase in purchases or []:
                purchase_id = purchase['id']
                purchase_items = self.db.execute_query(
                    f"SELECT * FROM purchase_items WHERE purchase_id = {ph}",
                    (purchase_id,)
                )
                purchase_data = dict(purchase)
                if self.post_purchase_voucher(company_id, purchase_id, purchase_data, purchase_items or []):
                    result['purchases_posted'] += 1
                else:
                    result['failed'].append(f"Purchase #{purchase.get('purchase_number', purchase_id)}")
            print(f"[LEDGER REBUILD] Reposted {result['purchases_posted']} purchases")

            # Step 6: Repost sales returns (if table exists)
            try:
                sales_returns = self.db.execute_query(
                    f"SELECT * FROM sales_returns WHERE company_id = {ph}",
                    (company_id,)
                )
                for sr in sales_returns or []:
                    sr_id = sr['id']
                    sr_items = self.db.execute_query(
                        f"SELECT * FROM sales_return_items WHERE sales_return_id = {ph}",
                        (sr_id,)
                    )
                    sr_data = dict(sr)
                    if self.post_sales_return_voucher(company_id, sr_id, sr_data, sr_items or []):
                        result['sales_returns_posted'] += 1
                    else:
                        result['failed'].append(f"Sales Return #{sr.get('return_no', sr_id)}")
                print(f"[LEDGER REBUILD] Reposted {result['sales_returns_posted']} sales returns")
            except Exception as e:
                print(f"[LEDGER REBUILD] Sales returns table may not exist or error: {e}")

            # Step 7: Repost purchase returns (if table exists)
            try:
                purchase_returns = self.db.execute_query(
                    f"SELECT * FROM purchase_returns WHERE company_id = {ph}",
                    (company_id,)
                )
                for pr in purchase_returns or []:
                    pr_id = pr['id']
                    pr_items = self.db.execute_query(
                        f"SELECT * FROM purchase_return_items WHERE purchase_return_id = {ph}",
                        (pr_id,)
                    )
                    pr_data = dict(pr)
                    if self.post_purchase_return_voucher(company_id, pr_id, pr_data, pr_items or []):
                        result['purchase_returns_posted'] += 1
                    else:
                        result['failed'].append(f"Purchase Return #{pr.get('return_no', pr_id)}")
                print(f"[LEDGER REBUILD] Reposted {result['purchase_returns_posted']} purchase returns")
            except Exception as e:
                print(f"[LEDGER REBUILD] Purchase returns table may not exist or error: {e}")

            # Step 8: Rebuild running balances for all accounts
            self.rebuild_running_balances(company_id)
            print(f"[LEDGER REBUILD] Rebuilt running balances")

            # Count ledger entries after rebuild
            after_count = self.db.execute_query(
                f"SELECT COUNT(*) as count FROM ledger_entries WHERE company_id = {ph}",
                (company_id,)
            )
            result['ledger_entries_after'] = after_count[0]['count'] if after_count else 0
            print(f"[LEDGER REBUILD] Ledger entries after: {result['ledger_entries_after']}")

            result['success'] = True
            result['message'] = f"Rebuild complete: {result['sales_posted']} sales, {result['purchases_posted']} purchases"
            if result['sales_returns_posted'] > 0:
                result['message'] += f", {result['sales_returns_posted']} sales returns"
            if result['purchase_returns_posted'] > 0:
                result['message'] += f", {result['purchase_returns_posted']} purchase returns"
            if result['failed']:
                result['message'] += f". Failed: {len(result['failed'])}"

            print(f"[LEDGER REBUILD] {result['message']}")

            return result

        except Exception as e:
            print(f"[LEDGER REBUILD] Error during rebuild: {e}")
            result['success'] = False
            result['message'] = f"Rebuild failed: {str(e)}"
            return result

    # ============================================================
    # ============================================================
    # SIMPLIFIED LEDGER UI METHODS
    # ============================================================

    _EXTRA_GENERAL_ACCOUNTS = [
        ('Profit and Loss Account', 'PL', 'capital', 'Capital', 'Cr'),
        ('GST Paid', 'GST_PAID', 'tax_liability', 'Tax', 'Dr'),
        ('GST Collected', 'GST_COLL', 'tax_liability', 'Tax', 'Cr'),
        ('CESS Paid', 'CESS_PAID', 'tax_liability', 'Tax', 'Dr'),
        ('CESS Collected', 'CESS_COLL', 'tax_liability', 'Tax', 'Cr'),
        ('Opening Stock', 'OPEN_STOCK', 'stock', 'Stock', 'Dr'),
        ('Closing Stock', 'CLOSE_STOCK', 'stock', 'Stock', 'Dr'),
        ('Discount Allowed', 'DISC_ALLOW', 'expense', 'Discount', 'Dr'),
        ('Discount Given', 'DISC_GIVEN', 'expense', 'Discount', 'Dr'),
        ('Discount Received', 'DISC_REC', 'income', 'Discount', 'Cr'),
        ('Salary Paid', 'SALARY', 'expense', 'Expenses', 'Dr'),
    ]

    def _ensure_extra_general_accounts(self, company_id: int) -> bool:
        """Create the user-requested general accounts if they are missing."""
        try:
            ph = self.db._get_placeholder()
            ts = self.db._get_timestamp_default()
            conn = self.db.connect()
            cursor = conn.cursor()
            for name, code, account_type, group_name, ob_type in self._EXTRA_GENERAL_ACCOUNTS:
                cursor.execute(
                    f"SELECT id FROM ledger_accounts WHERE company_id = {ph} AND LOWER(account_name) = LOWER({ph}) LIMIT 1",
                    (company_id, name),
                )
                if cursor.fetchone():
                    continue
                cursor.execute(
                    f"""
                    INSERT INTO ledger_accounts (
                        company_id, account_name, account_code, account_type, group_name,
                        opening_balance, opening_balance_type, is_system, is_active,
                        created_at, updated_at
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, 0.0, {ph}, 1, 1, {ts}, {ts})
                    """,
                    (company_id, name, code, account_type, group_name, ob_type),
                )
            conn.commit()
            self.db.disconnect()
            self.invalidate_accounts_cache(company_id)
            return True
        except Exception as e:
            print(f"Error ensuring extra general accounts: {e}")
            if 'conn' in locals():
                conn.rollback()
            self.db.disconnect()
            return False

    def get_general_ledger_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """Return all non-party ledger accounts for the General ledger type."""
        try:
            self.ensure_system_accounts(company_id)
            self._ensure_extra_general_accounts(company_id)
            ph = self.db._get_placeholder()
            rows = self.db.execute_query(
                f"""
                SELECT id, account_name, account_code, account_type, group_name,
                       opening_balance, opening_balance_type, is_system, is_active
                FROM ledger_accounts
                WHERE company_id = {ph}
                  AND is_active = 1
                  AND account_type <> 'party'
                  AND account_type <> 'cash_bank'
                ORDER BY account_name
                """,
                (company_id,),
            )
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            print(f"Error getting general ledger accounts: {e}")
            return []

    def get_debtor_ledger_options(self, company_id: int) -> List[Dict[str, Any]]:
        """Return debtor and both-party ledger accounts."""
        return self.get_debtor_accounts(company_id)

    def get_creditor_ledger_options(self, company_id: int) -> List[Dict[str, Any]]:
        """Return creditor and both-party ledger accounts."""
        return self.get_creditor_accounts(company_id)

    def get_cash_bank_ledger_options(self, company_id: int) -> List[Dict[str, Any]]:
        """Return Cash Account plus each bank master row's linked ledger account."""
        try:
            self.ensure_system_accounts(company_id)
            self.ensure_bank_master_ledgers(company_id)
            options: List[Dict[str, Any]] = []
            cash_account = self.get_account_by_name(company_id, 'Cash Account')
            if cash_account:
                options.append(dict(cash_account))

            bank_master_rows: List[Dict[str, Any]] = []
            if self._bank_master_has_ledger_column():
                ph = self.db._get_placeholder()
                bank_master_rows = self.db.execute_query(
                    f"""
                    SELECT la.id, la.account_name, la.account_code, la.account_type, la.group_name,
                           la.opening_balance, la.opening_balance_type, la.is_system, la.is_active,
                           ba.id AS bank_master_id
                    FROM bank_accounts ba
                    INNER JOIN ledger_accounts la ON la.id = ba.ledger_account_id
                    WHERE ba.company_id = {ph}
                      AND la.is_active = 1
                    ORDER BY ba.account_name
                    """,
                    (company_id,),
                ) or []

            if bank_master_rows:
                options.extend(dict(row) for row in bank_master_rows)
            else:
                bank_account = self.get_account_by_name(company_id, 'Bank Account')
                if bank_account:
                    options.append(dict(bank_account))

            return options
        except Exception as e:
            print(f"Error getting cash/bank ledger options: {e}")
            return []

    @staticmethod
    def _split_balance(debit_total: float, credit_total: float) -> Tuple[float, str]:
        """Split totals into absolute balance and Dr or Cr type."""
        debit_total = float(money_round(to_decimal(debit_total or 0.0)))
        credit_total = float(money_round(to_decimal(credit_total or 0.0)))
        if debit_total > credit_total:
            return debit_total - credit_total, 'Dr'
        if credit_total > debit_total:
            return credit_total - debit_total, 'Cr'
        return 0.0, 'Dr'

    def _period_totals(self, company_id: int, account_id: int, from_date: date, to_date: date) -> Dict[str, float]:
        """Return debit and credit totals inside the selected period."""
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(
            f"""
            SELECT COALESCE(SUM(debit), 0.0) AS debit_total,
                   COALESCE(SUM(credit), 0.0) AS credit_total
            FROM ledger_entries
            WHERE company_id = {ph}
              AND account_id = {ph}
              AND DATE(voucher_date) >= DATE({ph})
              AND DATE(voucher_date) <= DATE({ph})
              AND voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
            """,
            (company_id, account_id, str(from_date), str(to_date)),
        )
        if not rows:
            return {'debit': 0.0, 'credit': 0.0}
        return {
            'debit': float(money_round(to_decimal(rows[0].get('debit_total') or 0.0))),
            'credit': float(money_round(to_decimal(rows[0].get('credit_total') or 0.0))),
        }

    def _summary_for_accounts(self, company_id: int, accounts: List[Dict[str, Any]],
                              from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """Build summary rows for the provided accounts using the actual ledger_entries schema."""
        summary = []
        for account in accounts:
            account_id = account.get('id')
            if not account_id:
                continue
            opening_data = self._get_account_balance_before_date_old(company_id, account_id, from_date)
            period = self._period_totals(company_id, account_id, from_date, to_date)
            opening_balance, opening_type = self._split_balance(opening_data.get('debit', 0.0), opening_data.get('credit', 0.0))
            closing_debit = float(money_round(to_decimal(opening_data.get('debit', 0.0) or 0.0))) + period['debit']
            closing_credit = float(money_round(to_decimal(opening_data.get('credit', 0.0) or 0.0))) + period['credit']
            closing_balance, closing_type = self._split_balance(closing_debit, closing_credit)
            summary.append({
                'id': account_id,
                'party_id': account.get('party_id'),
                'account_name': account.get('account_name', ''),
                'account_type': account.get('account_type', ''),
                'group_name': account.get('group_name', ''),
                'party_type': account.get('party_type', ''),
                'opening_balance': opening_balance,
                'opening_balance_type': opening_type,
                'period_debit': period['debit'],
                'period_credit': period['credit'],
                'closing_balance': closing_balance,
                'closing_balance_type': closing_type,
            })
        return summary

    def get_general_account_summary(self, company_id: int, from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """Return summary for all General ledger accounts."""
        return self._summary_for_accounts(company_id, self.get_general_ledger_accounts(company_id), from_date, to_date)

    def get_debtor_summary(self, company_id: int, from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """Return debtor-wise balance summary."""
        return self._summary_for_accounts(company_id, self.get_debtor_ledger_options(company_id), from_date, to_date)

    def get_creditor_summary(self, company_id: int, from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """Return creditor-wise balance summary."""
        return self._summary_for_accounts(company_id, self.get_creditor_ledger_options(company_id), from_date, to_date)

    def get_cash_bank_summary(self, company_id: int, from_date: date, to_date: date) -> List[Dict[str, Any]]:
        """Return summary for all Cash and Bank ledger accounts."""
        return self._summary_for_accounts(company_id, self.get_cash_bank_ledger_options(company_id), from_date, to_date)

    def get_account_ledger(self, company_id: int, account_id: int, from_date: date, to_date: date) -> Dict[str, Any]:
        """Return detailed ledger entries for an account using voucher_date, debit, and credit columns."""
        try:
            account = self.get_account(company_id, account_id)
            if not account:
                return {'account': None, 'opening_balance': 0.0, 'opening_formatted': '0.00', 'entries': []}
            opening_data = self._get_account_balance_before_date_old(company_id, account_id, from_date)
            opening_net = float(money_round(to_decimal(opening_data.get('net', 0.0) or 0.0)))
            ph = self.db._get_placeholder()
            entries = self.db.execute_query(
                f"""
                SELECT DISTINCT le.id,
                       le.voucher_date,
                       le.voucher_type,
                       le.voucher_id,
                       le.voucher_no,
                       le.narration,
                       le.debit,
                       le.credit,
                       le.running_balance,
                       le.reference_type,
                       le.reference_id
                FROM ledger_entries le
                WHERE le.company_id = {ph}
                  AND le.account_id = {ph}
                  AND DATE(le.voucher_date) >= DATE({ph})
                  AND DATE(le.voucher_date) <= DATE({ph})
                  AND le.voucher_type NOT IN ('quotation', 'estimate', 'quote', 'Quotation', 'Estimate', 'Quote')
                ORDER BY DATE(le.voucher_date), le.id
                """,
                (company_id, account_id, str(from_date), str(to_date)),
            )
            rows = [dict(row) for row in entries] if entries else []
            running = opening_net
            for row in rows:
                debit = float(money_round(to_decimal(row.get('debit') or 0.0)))
                credit = float(money_round(to_decimal(row.get('credit') or 0.0)))
                running += debit - credit
                row['running_balance'] = running
            return {
                'account': dict(account),
                'opening_balance': opening_net,
                'opening_formatted': self._fmt_balance(opening_net),
                'entries': rows,
                'period_debit': sum(float(money_round(to_decimal(r.get('debit') or 0.0))) for r in rows),
                'period_credit': sum(float(money_round(to_decimal(r.get('credit') or 0.0))) for r in rows),
                'closing_balance': running,
                'closing_formatted': self._fmt_balance(running),
            }
        except Exception as e:
            print(f"Error getting account ledger: {e}")
            return {'account': None, 'opening_balance': 0.0, 'opening_formatted': '0.00', 'entries': []}

    def get_cash_account(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Get the Cash account for a company."""
        try:
            placeholder = self.db._get_placeholder()
            result = self.db.execute_query(
                f"SELECT * FROM ledger_accounts WHERE company_id = {placeholder} AND account_name = 'Cash' AND is_system = 1",
                (company_id,)
            )
            return result[0] if result else None
        except Exception as e:
            print(f"Error getting cash account: {e}")
            return None

    def ensure_cash_account(self, company_id: int) -> Optional[int]:
        """Ensure Cash account exists for company, return account_id."""
        cash_account = self.get_cash_account(company_id)
        if cash_account:
            return cash_account['id']
        
        # Create Cash account if it doesn't exist
        try:
            placeholder = self.db._get_placeholder()
            ts = self.db._get_timestamp_default()
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                f"""INSERT INTO ledger_accounts (company_id, account_name, account_code, account_type, 
                    group_name, opening_balance, opening_balance_type, is_system, is_active, created_at, updated_at)
                    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, 
                    {placeholder}, {placeholder}, {placeholder}, {placeholder}, {ts}, {ts})""",
                (company_id, 'Cash', 'CASH-001', 'asset', 'Cash & Bank', 0.0, 'Dr', 1, 1)
            )
            account_id = self.db._get_last_insert_id(cursor)
            conn.commit()
            self.db.disconnect()
            return account_id
        except Exception as e:
            print(f"Error creating cash account: {e}")
            if 'conn' in locals():
                conn.rollback()
                self.db.disconnect()
            return None

    def get_account_options_by_type(self, company_id: int, account_type: str) -> List[Dict[str, Any]]:
        """Get account options filtered by type (general, debtor, creditor)."""
        try:
            placeholder = self.db._get_placeholder()
            if account_type == 'general':
                # General accounts: income, expense, salary, rent, discount, GST, CESS, etc.
                # Exclude debtor/creditor party accounts
                query = f"""
                    SELECT id, account_name, account_type, group_name
                    FROM ledger_accounts
                    WHERE company_id = {placeholder} AND is_active = 1
                    AND group_name NOT IN ('Sundry Debtors', 'Sundry Creditors')
                    ORDER BY account_name
                """
            elif account_type == 'debtor':
                # Debtor parties only
                query = f"""
                    SELECT la.id, la.account_name, la.account_type, la.group_name, p.party_type
                    FROM ledger_accounts la
                    LEFT JOIN parties p ON la.id = p.ledger_account_id
                    WHERE la.company_id = {placeholder} AND la.is_active = 1
                    AND la.group_name = 'Sundry Debtors'
                    ORDER BY la.account_name
                """
            elif account_type == 'creditor':
                # Creditor parties only
                query = f"""
                    SELECT la.id, la.account_name, la.account_type, la.group_name, p.party_type
                    FROM ledger_accounts la
                    LEFT JOIN parties p ON la.id = p.ledger_account_id
                    WHERE la.company_id = {placeholder} AND la.is_active = 1
                    AND la.group_name = 'Sundry Creditors'
                    ORDER BY la.account_name
                """
            else:
                return []
            
            result = self.db.execute_query(query, (company_id,))
            return result if result else []
        except Exception as e:
            print(f"Error getting account options by type: {e}")
            return []

    def format_balance(self, amount: float) -> str:
        """Format balance amount with Dr/Cr suffix."""
        if amount >= 0:
            return f"{abs(amount):.2f} Dr"
        else:
            return f"{abs(amount):.2f} Cr"
