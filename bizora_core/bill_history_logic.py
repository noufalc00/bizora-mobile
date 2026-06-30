"""
Bill history query and audit-safe voiding logic.

This module deliberately does not delete invoices, item rows, stock movements,
or ledger entries. Voiding marks the source voucher as Voided and posts formal
reversal rows for stock and ledger effects.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from db import Database


class BillHistoryLogic:
    """Business logic for the bill history dashboard."""

    VALID_TYPES = {"All", "Sales", "Purchases", "Sales Return", "Purchase Return"}

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.ensure_schema()

    def _ph(self) -> str:
        return self.db._get_placeholder()

    @staticmethod
    def _row_dict(row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        if isinstance(row, dict):
            return dict(row)
        try:
            return dict(row)
        except Exception:
            return {}

    @staticmethod
    def _cursor_row_dict(cursor, row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        if isinstance(row, dict):
            return dict(row)
        try:
            return dict(row)
        except Exception:
            columns = [column[0] for column in cursor.description or []]
            return dict(zip(columns, row))

    def _cursor_fetchall(self, cursor) -> List[Dict[str, Any]]:
        return [self._cursor_row_dict(cursor, row) for row in cursor.fetchall()]

    def _query(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        return [self._row_dict(row) for row in self.db.execute_query(sql, tuple(params)) or []]

    def _table_columns(self, table_name: str) -> set:
        columns = set()
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            if getattr(self.db, "db_type", "sqlite") == "sqlite":
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = {row[1] for row in cursor.fetchall()}
            else:
                ph = self._ph()
                cursor.execute(
                    f"""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = {ph}
                    """,
                    (table_name,),
                )
                columns = {row[0] for row in cursor.fetchall()}
        finally:
            try:
                if conn is not None:
                    self.db.disconnect()
            except Exception:
                pass
        return columns

    def _add_column_if_missing(self, table_name: str, column_name: str, column_sql: str) -> None:
        if column_name in self._table_columns(table_name):
            return
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
            conn.commit()
        finally:
            self.db.disconnect()

    def ensure_schema(self) -> None:
        """Ensure status fields and void audit table exist."""
        self._add_column_if_missing("sales", "status", "status VARCHAR(20) DEFAULT 'Active'")
        self._add_column_if_missing("purchases", "status", "status VARCHAR(20) DEFAULT 'Active'")
        self._add_column_if_missing("sales_returns", "status", "status VARCHAR(20) DEFAULT 'Active'")
        self._add_column_if_missing("purchase_returns", "status", "status VARCHAR(20) DEFAULT 'Active'")

        pk_autoinc = self.db._get_primary_key_autoincrement()
        timestamp_default = self.db._get_timestamp_default()
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS bill_void_audit (
                    id {pk_autoinc},
                    company_id INTEGER NOT NULL,
                    voucher_type VARCHAR(30) NOT NULL,
                    voucher_id INTEGER NOT NULL,
                    voucher_no VARCHAR(100) NOT NULL,
                    void_date DATE NOT NULL,
                    reason TEXT,
                    reversed_stock_rows INTEGER DEFAULT 0,
                    reversed_ledger_rows INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT {timestamp_default}
                )
                """
            )
            conn.commit()
        finally:
            self.db.disconnect()

    def get_filtered_bills(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        search_term: str = "",
        transaction_type: str = "All",
    ) -> List[Dict[str, Any]]:
        """Return sales, purchases, and returns matching the supplied filters."""
        transaction_type = transaction_type if transaction_type in self.VALID_TYPES else "All"
        ph = self._ph()
        search_term = (search_term or "").strip()
        search_pattern = f"%{search_term}%"

        queries: List[str] = []
        params: List[Any] = []

        if transaction_type in ("All", "Sales"):
            sales_where = [
                f"s.company_id = {ph}",
                f"s.invoice_date BETWEEN {ph} AND {ph}",
            ]
            sales_params: List[Any] = [company_id, from_date, to_date]
            if search_term:
                sales_where.append(f"(s.invoice_number LIKE {ph} OR p.name LIKE {ph})")
                sales_params.extend([search_pattern, search_pattern])
            queries.append(
                f"""
                SELECT
                    s.id AS voucher_id,
                    s.invoice_date AS bill_date,
                    s.invoice_number AS bill_no,
                    'Sales' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    s.grand_total AS total_amount,
                    COALESCE(s.status, 'Active') AS status
                FROM sales s
                LEFT JOIN parties p ON s.party_id = p.id
                WHERE {' AND '.join(sales_where)}
                """
            )
            params.extend(sales_params)

        if transaction_type in ("All", "Purchases"):
            purchase_where = [
                f"pu.company_id = {ph}",
                f"pu.purchase_date BETWEEN {ph} AND {ph}",
            ]
            purchase_params: List[Any] = [company_id, from_date, to_date]
            if search_term:
                purchase_where.append(f"(pu.purchase_number LIKE {ph} OR p.name LIKE {ph})")
                purchase_params.extend([search_pattern, search_pattern])
            queries.append(
                f"""
                SELECT
                    pu.id AS voucher_id,
                    pu.purchase_date AS bill_date,
                    pu.purchase_number AS bill_no,
                    'Purchases' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    pu.grand_total AS total_amount,
                    COALESCE(pu.status, 'Active') AS status
                FROM purchases pu
                LEFT JOIN parties p ON pu.party_id = p.id
                WHERE {' AND '.join(purchase_where)}
                """
            )
            params.extend(purchase_params)

        if transaction_type in ("All", "Sales Return"):
            sales_return_where = [
                f"sr.company_id = {ph}",
                f"sr.return_date BETWEEN {ph} AND {ph}",
            ]
            sales_return_params: List[Any] = [company_id, from_date, to_date]
            if search_term:
                sales_return_where.append(f"(sr.return_no LIKE {ph} OR p.name LIKE {ph})")
                sales_return_params.extend([search_pattern, search_pattern])
            queries.append(
                f"""
                SELECT
                    sr.id AS voucher_id,
                    sr.return_date AS bill_date,
                    sr.return_no AS bill_no,
                    'Sales Return' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    sr.grand_total AS total_amount,
                    COALESCE(sr.status, 'Active') AS status
                FROM sales_returns sr
                LEFT JOIN parties p ON sr.party_id = p.id
                WHERE {' AND '.join(sales_return_where)}
                """
            )
            params.extend(sales_return_params)

        if transaction_type in ("All", "Purchase Return"):
            purchase_return_where = [
                f"pr.company_id = {ph}",
                f"pr.return_date BETWEEN {ph} AND {ph}",
            ]
            purchase_return_params: List[Any] = [company_id, from_date, to_date]
            if search_term:
                purchase_return_where.append(f"(pr.return_no LIKE {ph} OR p.name LIKE {ph})")
                purchase_return_params.extend([search_pattern, search_pattern])
            queries.append(
                f"""
                SELECT
                    pr.id AS voucher_id,
                    pr.return_date AS bill_date,
                    pr.return_no AS bill_no,
                    'Purchase Return' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    pr.grand_total AS total_amount,
                    COALESCE(pr.status, 'Active') AS status
                FROM purchase_returns pr
                LEFT JOIN parties p ON pr.party_id = p.id
                WHERE {' AND '.join(purchase_return_where)}
                """
            )
            params.extend(purchase_return_params)

        if not queries:
            return []

        sql = " UNION ALL ".join(queries) + " ORDER BY bill_date DESC, voucher_id DESC"
        return self._query(sql, params)

    def get_invoice_details(self, company_id: int, voucher_type: str, voucher_id: int) -> Optional[Dict[str, Any]]:
        """Return one invoice header with read-only line item details."""
        ph = self._ph()
        if voucher_type == "Sales":
            header_sql = f"""
                SELECT
                    s.id AS voucher_id,
                    s.invoice_number AS bill_no,
                    s.invoice_date AS bill_date,
                    'Sales' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    s.sub_total,
                    s.discount_total,
                    s.tax_total,
                    s.round_off,
                    s.grand_total AS total_amount,
                    COALESCE(s.status, 'Active') AS status,
                    s.narration
                FROM sales s
                LEFT JOIN parties p ON s.party_id = p.id
                WHERE s.company_id = {ph} AND s.id = {ph}
            """
            items_sql = f"""
                SELECT
                    si.sl_no,
                    COALESCE(pr.name, '') AS product_name,
                    si.hsn,
                    si.rate,
                    si.quantity,
                    si.gross_value,
                    si.discount,
                    si.net_value,
                    si.tax_amount,
                    si.grand_total
                FROM sales_items si
                LEFT JOIN products pr ON si.product_id = pr.id
                WHERE si.sale_id = {ph}
                ORDER BY si.sl_no
            """
        elif voucher_type == "Purchases":
            header_sql = f"""
                SELECT
                    pu.id AS voucher_id,
                    pu.purchase_number AS bill_no,
                    pu.purchase_date AS bill_date,
                    'Purchases' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    pu.sub_total,
                    pu.discount_total,
                    pu.tax_total,
                    pu.round_off,
                    pu.grand_total AS total_amount,
                    COALESCE(pu.status, 'Active') AS status,
                    pu.narration
                FROM purchases pu
                LEFT JOIN parties p ON pu.party_id = p.id
                WHERE pu.company_id = {ph} AND pu.id = {ph}
            """
            items_sql = f"""
                SELECT
                    pi.sl_no,
                    COALESCE(pr.name, '') AS product_name,
                    pi.hsn,
                    pi.rate,
                    pi.quantity,
                    pi.gross_value,
                    pi.discount,
                    pi.net_value,
                    pi.tax_amount,
                    pi.grand_total
                FROM purchase_items pi
                LEFT JOIN products pr ON pi.product_id = pr.id
                WHERE pi.purchase_id = {ph}
                ORDER BY pi.sl_no
            """
        elif voucher_type == "Sales Return":
            header_sql = f"""
                SELECT
                    sr.id AS voucher_id,
                    sr.return_no AS bill_no,
                    sr.return_date AS bill_date,
                    'Sales Return' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    sr.sub_total,
                    sr.discount_total,
                    sr.tax_total,
                    sr.round_off,
                    sr.grand_total AS total_amount,
                    COALESCE(sr.status, 'Active') AS status,
                    sr.narration
                FROM sales_returns sr
                LEFT JOIN parties p ON sr.party_id = p.id
                WHERE sr.company_id = {ph} AND sr.id = {ph}
            """
            items_sql = f"""
                SELECT
                    sri.sl_no,
                    COALESCE(pr.name, '') AS product_name,
                    sri.hsn,
                    sri.rate,
                    sri.quantity,
                    sri.gross_value,
                    sri.discount,
                    sri.net_value,
                    sri.tax_amount,
                    sri.grand_total
                FROM sales_return_items sri
                LEFT JOIN products pr ON sri.product_id = pr.id
                WHERE sri.sales_return_id = {ph}
                ORDER BY sri.sl_no
            """
        elif voucher_type == "Purchase Return":
            header_sql = f"""
                SELECT
                    pr.id AS voucher_id,
                    pr.return_no AS bill_no,
                    pr.return_date AS bill_date,
                    'Purchase Return' AS transaction_type,
                    COALESCE(p.name, '') AS party_name,
                    pr.sub_total,
                    pr.discount_total,
                    pr.tax_total,
                    pr.round_off,
                    pr.grand_total AS total_amount,
                    COALESCE(pr.status, 'Active') AS status,
                    pr.narration
                FROM purchase_returns pr
                LEFT JOIN parties p ON pr.party_id = p.id
                WHERE pr.company_id = {ph} AND pr.id = {ph}
            """
            items_sql = f"""
                SELECT
                    pri.sl_no,
                    COALESCE(pr.name, '') AS product_name,
                    pri.hsn,
                    pri.rate,
                    pri.quantity,
                    pri.gross_value,
                    pri.discount,
                    pri.net_value,
                    pri.tax_amount,
                    pri.grand_total
                FROM purchase_return_items pri
                LEFT JOIN products pr ON pri.product_id = pr.id
                WHERE pri.purchase_return_id = {ph}
                ORDER BY pri.sl_no
            """
        else:
            return None

        header_rows = self._query(header_sql, (company_id, voucher_id))
        if not header_rows:
            return None

        details = header_rows[0]
        details["items"] = self._query(items_sql, (voucher_id,))
        return details

    def void_bill(
        self,
        company_id: int,
        voucher_type: str,
        voucher_id: int,
        reason: str = "",
    ) -> Tuple[bool, str]:
        """Void a bill by status update plus formal reversal rows."""
        voucher_config = {
            "Sales": {
                "table": "sales",
                "no_column": "invoice_number",
                "date_column": "invoice_date",
                "item_table": "sales_items",
                "item_fk": "sale_id",
                "source_ledger_type": "sales",
                "void_ledger_type": "sales_void",
                "stock_movement_type": "adjustment_in",
                "stock_sign": 1.0,
            },
            "Purchases": {
                "table": "purchases",
                "no_column": "purchase_number",
                "date_column": "purchase_date",
                "item_table": "purchase_items",
                "item_fk": "purchase_id",
                "source_ledger_type": "purchase",
                "void_ledger_type": "purchase_void",
                "stock_movement_type": "adjustment_out",
                "stock_sign": -1.0,
            },
            "Sales Return": {
                "table": "sales_returns",
                "no_column": "return_no",
                "date_column": "return_date",
                "item_table": "sales_return_items",
                "item_fk": "sales_return_id",
                "source_ledger_type": "sales_return",
                "void_ledger_type": "sales_return_void",
                "stock_movement_type": "adjustment",
                "stock_sign": -1.0,
            },
            "Purchase Return": {
                "table": "purchase_returns",
                "no_column": "return_no",
                "date_column": "return_date",
                "item_table": "purchase_return_items",
                "item_fk": "purchase_return_id",
                "source_ledger_type": "purchase_return",
                "void_ledger_type": "purchase_return_void",
                "stock_movement_type": "adjustment",
                "stock_sign": 1.0,
            },
        }
        if voucher_type not in voucher_config:
            return False, "Unsupported bill type."

        ph = self._ph()
        config = voucher_config[voucher_type]
        table_name = config["table"]
        id_column = "id"
        no_column = config["no_column"]
        date_column = config["date_column"]
        item_table = config["item_table"]
        item_fk = config["item_fk"]
        source_ledger_type = config["source_ledger_type"]
        void_ledger_type = config["void_ledger_type"]
        stock_movement_type = config["stock_movement_type"]
        stock_sign = float(config["stock_sign"])
        void_date = date.today().isoformat()

        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            conn.execute("BEGIN")

            cursor.execute(
                f"""
                SELECT {id_column} AS voucher_id, {no_column} AS voucher_no,
                       {date_column} AS voucher_date, COALESCE(status, 'Active') AS status
                FROM {table_name}
                WHERE company_id = {ph} AND {id_column} = {ph}
                """,
                (company_id, voucher_id),
            )
            header_row = cursor.fetchone()
            if not header_row:
                conn.rollback()
                return False, "Bill was not found."

            header = self._cursor_row_dict(cursor, header_row)
            if header.get("status") == "Voided":
                conn.rollback()
                return False, "Bill is already voided."

            voucher_no = str(header.get("voucher_no") or "")

            cursor.execute(
                f"UPDATE {table_name} SET status = {ph} WHERE company_id = {ph} AND {id_column} = {ph}",
                ("Voided", company_id, voucher_id),
            )

            cursor.execute(
                f"""
                SELECT product_id, quantity
                FROM {item_table}
                WHERE {item_fk} = {ph}
                ORDER BY sl_no
                """,
                (voucher_id,),
            )
            items = self._cursor_fetchall(cursor)

            reversed_stock_rows = 0
            touched_product_ids = set()
            for item in items:
                product_id = item.get("product_id")
                quantity = float(item.get("quantity") or 0.0)
                if not product_id or quantity <= 0:
                    continue
                cursor.execute(
                    f"""
                    INSERT INTO stock_movements
                        (company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, voucher_type)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (
                        company_id,
                        int(product_id),
                        stock_movement_type,
                        quantity * stock_sign,
                        void_ledger_type,
                        voucher_id,
                        f"Void reversal for {voucher_type} {voucher_no}",
                        void_ledger_type,
                    ),
                )
                reversed_stock_rows += 1
                touched_product_ids.add(int(product_id))

            cursor.execute(
                f"""
                SELECT account_id, contra_account_id, narration, debit, credit, reference_type, reference_id
                FROM ledger_entries
                WHERE company_id = {ph} AND voucher_type = {ph} AND voucher_id = {ph}
                ORDER BY id
                """,
                (company_id, source_ledger_type, voucher_id),
            )
            ledger_rows = self._cursor_fetchall(cursor)

            reversed_ledger_rows = 0
            for row in ledger_rows:
                cursor.execute(
                    f"""
                    INSERT INTO ledger_entries
                        (company_id, voucher_type, voucher_id, voucher_no, voucher_date,
                         account_id, contra_account_id, narration, debit, credit,
                         reference_type, reference_id)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (
                        company_id,
                        void_ledger_type,
                        voucher_id,
                        voucher_no,
                        void_date,
                        row.get("account_id"),
                        row.get("contra_account_id"),
                        f"Void reversal for {voucher_type} {voucher_no}",
                        float(row.get("credit") or 0.0),
                        float(row.get("debit") or 0.0),
                        void_ledger_type,
                        voucher_id,
                    ),
                )
                reversed_ledger_rows += 1

            cursor.execute(
                f"""
                INSERT INTO bill_void_audit
                    (company_id, voucher_type, voucher_id, voucher_no, void_date, reason,
                     reversed_stock_rows, reversed_ledger_rows)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """,
                (
                    company_id,
                    void_ledger_type,
                    voucher_id,
                    voucher_no,
                    void_date,
                    reason,
                    reversed_stock_rows,
                    reversed_ledger_rows,
                ),
            )

            conn.commit()

            if touched_product_ids and hasattr(self.db, "batch_sync_product_quantities"):
                self.db.batch_sync_product_quantities(company_id, list(touched_product_ids))

            return True, f"{voucher_type} bill {voucher_no} has been voided."
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            return False, str(exc)
        finally:
            try:
                self.db.disconnect()
            except Exception:
                pass
