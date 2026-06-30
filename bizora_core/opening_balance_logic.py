"""
Opening Balance logic module.

Handles saving and retrieving opening balance vouchers which initialize
ledger balances and stock quantities for a company.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from bizora_core.common_finance import to_decimal, money_round, format_money, is_balanced

class OpeningBalanceLogic:
    _schema_ready = False

    def __init__(self, db: Any):
        self.db = db
        self.ensure_schema()

    def _ph(self) -> str:
        return self.db._get_placeholder() if hasattr(self.db, "_get_placeholder") else "?"

    def _pk(self) -> str:
        return self.db._get_primary_key_autoincrement() if hasattr(self.db, "_get_primary_key_autoincrement") else "INTEGER PRIMARY KEY AUTOINCREMENT"

    def _text_type(self, length: Optional[int] = None) -> str:
        return self.db._get_text_type(length) if hasattr(self.db, "_get_text_type") else "TEXT"

    def _decimal_type(self) -> str:
        return self.db._get_decimal_type(18, 2) if hasattr(self.db, "_get_decimal_type") else "REAL"

    def _db_money(self, value: Any) -> str:
        return str(money_round(value))

    def _db_qty(self, value: Any) -> str:
        return str(to_decimal(value))

    def _fetchall(self, cursor) -> List[Dict[str, Any]]:
        rows = cursor.fetchall()
        result = []
        for row in rows:
            if isinstance(row, dict):
                result.append(row)
            else:
                try:
                    result.append(dict(row))
                except Exception:
                    columns = [d[0] for d in cursor.description]
                    result.append(dict(zip(columns, row)))
        return result

    def _fetchone(self, cursor) -> Optional[Dict[str, Any]]:
        row = cursor.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        try:
            return dict(row)
        except Exception:
            columns = [d[0] for d in cursor.description]
            return dict(zip(columns, row))

    def _begin(self, conn):
        try:
            conn.commit()
        except Exception:
            pass
        if getattr(self.db, "db_type", "sqlite") == "mysql" and hasattr(conn, "start_transaction"):
            conn.start_transaction()
        else:
            conn.execute("BEGIN")

    def ensure_schema(self) -> Dict[str, Any]:
        """Create/migrate opening balance tables safely."""
        if OpeningBalanceLogic._schema_ready:
            return {"success": True, "message": "Opening Balance schema ready"}

        conn = self.db.connect()
        cursor = conn.cursor()
        pk = self._pk()
        ts = "CURRENT_TIMESTAMP"
        if hasattr(self.db, "_get_timestamp_default"):
            ts = self.db._get_timestamp_default()
        txt_100 = self._text_type(100)
        txt_255 = self._text_type(255)
        dec = self._decimal_type()

        try:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS opening_balances (
                    id {pk},
                    company_id INTEGER NOT NULL,
                    financial_year_id INTEGER DEFAULT 1,
                    voucher_no {txt_100} NOT NULL,
                    voucher_date DATE NOT NULL,
                    narration TEXT,
                    total_debit {dec} DEFAULT 0.0,
                    total_credit {dec} DEFAULT 0.0,
                    status {txt_100} DEFAULT 'Balanced',
                    created_at TIMESTAMP DEFAULT {ts},
                    updated_at TIMESTAMP DEFAULT {ts},
                    UNIQUE(company_id, financial_year_id)
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS opening_ledger_items (
                    id {pk},
                    opening_id INTEGER NOT NULL,
                    sl_no INTEGER,
                    account_id INTEGER NOT NULL,
                    debit {dec} DEFAULT 0.0,
                    credit {dec} DEFAULT 0.0,
                    narration TEXT
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS opening_stock_items (
                    id {pk},
                    opening_id INTEGER NOT NULL,
                    sl_no INTEGER,
                    product_id INTEGER NOT NULL,
                    qty {dec} DEFAULT 0.0,
                    rate {dec} DEFAULT 0.0,
                    value {dec} DEFAULT 0.0
                )
            """)

            conn.commit()
            OpeningBalanceLogic._schema_ready = True
            return {"success": True, "message": "Opening Balance schema ready"}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Schema error: {e}"}

    def get_opening_balance(self, company_id: int, financial_year_id: int = 1) -> Dict[str, Any]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        
        cursor.execute(
            f"SELECT * FROM opening_balances WHERE company_id={ph} AND financial_year_id={ph}",
            (company_id, financial_year_id)
        )
        header = self._fetchone(cursor)
        if not header:
            return {"success": False, "header": None, "ledger_items": [], "stock_items": []}
            
        opening_id = header["id"]
        
        cursor.execute(
            f"SELECT * FROM opening_ledger_items WHERE opening_id={ph} ORDER BY sl_no",
            (opening_id,)
        )
        ledger_items = self._fetchall(cursor)
        
        cursor.execute(
            f"SELECT * FROM opening_stock_items WHERE opening_id={ph} ORDER BY sl_no",
            (opening_id,)
        )
        stock_items = self._fetchall(cursor)
        
        return {
            "success": True,
            "header": header,
            "ledger_items": ledger_items,
            "stock_items": stock_items
        }

    def save_opening_balance(
        self,
        company_id: int,
        voucher_date: str,
        ledger_items: List[Dict[str, Any]],
        stock_items: List[Dict[str, Any]],
        narration: str = "",
        financial_year_id: int = 1
    ) -> Dict[str, Any]:
        """Save opening balance with fully atomic transaction.

        Transaction sequence (single BEGIN/COMMIT):
        1. Reverse old postings (ledger + stock) if editing
        2. Delete old item rows
        3. Update/insert header
        4. Insert new item rows
        5. Repost ledger entries via centralized engine
        6. Repost stock movements via centralized engine
        7. COMMIT (or ROLLBACK on any failure)
        """
        from bizora_core.voucher_posting_engine import VoucherPostingEngine

        # ------------------------------------------------------------------
        # Phase 1: Decimal-safe validation (no DB operations)
        # ------------------------------------------------------------------
        total_debit = Decimal('0.0')
        total_credit = Decimal('0.0')
        total_stock_value = Decimal('0.0')

        clean_ledger = []
        for sl, item in enumerate(ledger_items, 1):
            if not item.get("account_id"):
                continue
            deb = to_decimal(item.get("debit", 0))
            cre = to_decimal(item.get("credit", 0))
            if is_balanced(deb, 0) and is_balanced(cre, 0):
                continue
            total_debit += deb
            total_credit += cre
            clean_ledger.append({
                "sl_no": sl,
                "account_id": item["account_id"],
                "debit": deb,
                "credit": cre,
                "narration": item.get("narration", "")
            })

        clean_stock = []
        for sl, item in enumerate(stock_items, 1):
            if not item.get("product_id"):
                continue
            qty = to_decimal(item.get("qty", 0))
            if is_balanced(qty, 0):
                continue
            rate = to_decimal(item.get("rate", 0))
            val = money_round(qty * rate)
            total_stock_value += val
            clean_stock.append({
                "sl_no": sl,
                "product_id": item["product_id"],
                "qty": qty,
                "rate": rate,
                "value": val
            })

        # Balance validation: (Debit + Opening Stock) must equal Credit
        if (total_debit + total_stock_value) != total_credit:
            return {
                "success": False,
                "message": (
                    f"Opening Balance is unbalanced!\n"
                    f"Debit ({format_money(total_debit)} + Stock {format_money(total_stock_value)}"
                    f" = {format_money(total_debit + total_stock_value)})"
                    f" | Credit: {format_money(total_credit)}"
                )
            }

        # ------------------------------------------------------------------
        # Phase 2: Resolve Opening Stock Account BEFORE transaction
        # ------------------------------------------------------------------
        # The stock value debit must be injected into ledger entries for posting
        # so that the posted ledger remains balanced.
        stock_account_id = None
        if total_stock_value > Decimal('0.0'):
            conn_check = self.db.connect()
            cursor_check = conn_check.cursor()
            ph = self._ph()
            cursor_check.execute(
                f"SELECT id FROM ledger_accounts WHERE company_id={ph} AND account_name={ph}",
                (company_id, "Opening Stock Account"),
            )
            stock_acc = self._fetchone(cursor_check)
            if not stock_acc:
                return {"success": False, "message": "Opening Stock Account not found in ledgers! Please create it first."}
            stock_account_id = stock_acc["id"]

        # Build the complete ledger entry list for engine posting
        # (user ledger items + Opening Stock Account debit)
        posting_entries = []
        for item in clean_ledger:
            posting_entries.append({
                "account_id": item["account_id"],
                "debit": float(money_round(item["debit"])),
                "credit": float(money_round(item["credit"])),
                "narration": item.get("narration", ""),
            })
        if stock_account_id and total_stock_value > Decimal('0.0'):
            posting_entries.append({
                "account_id": stock_account_id,
                "debit": float(money_round(total_stock_value)),
                "credit": 0.0,
                "narration": "Opening Stock Value",
            })

        # ------------------------------------------------------------------
        # Phase 3: Fully atomic DB transaction
        # ------------------------------------------------------------------
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()

        try:
            self._begin(conn)

            # Step 1: Check for existing opening balance (singleton)
            cursor.execute(
                f"SELECT id, voucher_no FROM opening_balances WHERE company_id={ph} AND financial_year_id={ph}",
                (company_id, financial_year_id),
            )
            existing = self._fetchone(cursor)

            if existing:
                opening_id = existing["id"]
                voucher_no = existing["voucher_no"]

                # Step 2a: Reverse old postings FIRST (before any data changes)
                # Delete old ledger entries via centralized method
                cursor.execute(
                    f"SELECT DISTINCT account_id FROM ledger_entries "
                    f"WHERE company_id={ph} AND voucher_type={ph} AND voucher_id={ph}",
                    (company_id, "opening", opening_id),
                )
                # Just delete — running balances will be rebuilt by post_double_entry
                cursor.execute(
                    f"DELETE FROM ledger_entries "
                    f"WHERE company_id={ph} AND voucher_type={ph} AND voucher_id={ph}",
                    (company_id, "opening", opening_id),
                )

                # Delete old stock movements
                cursor.execute(
                    f"DELETE FROM stock_movements "
                    f"WHERE reference_type={ph} AND reference_id={ph}",
                    ("opening", opening_id),
                )

                # Step 2b: Delete old item rows
                cursor.execute(f"DELETE FROM opening_ledger_items WHERE opening_id={ph}", (opening_id,))
                cursor.execute(f"DELETE FROM opening_stock_items WHERE opening_id={ph}", (opening_id,))

                # Step 2c: Update header
                cursor.execute(
                    f"UPDATE opening_balances SET voucher_date={ph}, narration={ph}, "
                    f"total_debit={ph}, total_credit={ph}, updated_at=CURRENT_TIMESTAMP "
                    f"WHERE id={ph}",
                    (voucher_date, narration, self._db_money(total_debit),
                     self._db_money(total_credit), opening_id),
                )
            else:
                voucher_no = "OP-001"
                cursor.execute(
                    f"INSERT INTO opening_balances "
                    f"(company_id, financial_year_id, voucher_no, voucher_date, narration, total_debit, total_credit) "
                    f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                    (company_id, financial_year_id, voucher_no, voucher_date, narration,
                     self._db_money(total_debit), self._db_money(total_credit)),
                )
                opening_id = cursor.lastrowid

            # Step 3: Insert new item rows
            for item in clean_ledger:
                cursor.execute(
                    f"INSERT INTO opening_ledger_items "
                    f"(opening_id, sl_no, account_id, debit, credit, narration) "
                    f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                    (opening_id, item["sl_no"], item["account_id"],
                     self._db_money(item["debit"]), self._db_money(item["credit"]),
                     item["narration"]),
                )

            for item in clean_stock:
                cursor.execute(
                    f"INSERT INTO opening_stock_items "
                    f"(opening_id, sl_no, product_id, qty, rate, value) "
                    f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                    (opening_id, item["sl_no"], item["product_id"],
                     self._db_qty(item["qty"]), self._db_money(item["rate"]),
                     self._db_money(item["value"])),
                )

            # Step 4: Repost ledger entries via centralized engine
            # Use post_double_entry — the same method used by Cash Receipt,
            # Cash Payment, Journal, etc. — NOT manual create_ledger_entry loops.
            engine = VoucherPostingEngine(self.db)
            ledger = engine._ledger()
            ok = ledger.post_double_entry(
                company_id=company_id,
                voucher_type="opening",
                voucher_id=opening_id,
                voucher_no=voucher_no,
                voucher_date=voucher_date,
                entries=posting_entries,
                narration=narration,
                reference_type="opening",
                reference_id=opening_id,
            )
            if not ok:
                conn.rollback()
                return {"success": False, "message": "Failed to post ledger entries via centralized engine."}

            # Step 5: Repost stock movements via centralized engine
            if clean_stock:
                engine.post_stock_movements(
                    company_id=company_id,
                    voucher_type="opening",
                    voucher_id=opening_id,
                    voucher_no=voucher_no,
                    voucher_date=voucher_date,
                    items=clean_stock,
                )

            # Step 6: COMMIT — everything succeeded
            conn.commit()
            return {"success": True, "message": "Opening Balance saved successfully."}

        except Exception as e:
            conn.rollback()
            import traceback
            traceback.print_exc()
            return {"success": False, "message": f"Database error: {e}"}

    def has_other_transactions(self, company_id: int) -> bool:
        """Check if any non-opening ledger entries exist for this company.

        Used by the UI to warn users that editing the opening balance
        will affect existing Trial Balance / Stock valuation.
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM ledger_entries "
                f"WHERE company_id={ph} AND voucher_type != {ph}",
                (company_id, "opening"),
            )
            row = self._fetchone(cursor)
            return int((row or {}).get("cnt", 0) or 0) > 0
        except Exception:
            return False

