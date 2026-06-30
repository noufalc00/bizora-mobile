"""
Van Sales / Van Load / Van Return logic.

This module intentionally keeps van operations operational and stock-safe:
- Van load records goods issued to a van but does not post ledger entries.
- Van return/settlement records returned/sold quantities.
- Only sold quantities are posted to stock_movements as stock-out so company stock stays correct.
- No ledger_entries are created here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from config import active_company_manager
from bizora_core.common_finance import to_decimal, money_round, format_money


class VanLogic:
    """Business logic for Van Entry and Van Return Entry."""

    def __init__(self, db):
        self.db = db
        self.ensure_schema()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    def _ph(self) -> str:
        return self.db._get_placeholder() if hasattr(self.db, "_get_placeholder") else "?"

    def _timestamp_default(self) -> str:
        return self.db._get_timestamp_default() if hasattr(self.db, "_get_timestamp_default") else "CURRENT_TIMESTAMP"

    def _pk(self) -> str:
        return self.db._get_primary_key_autoincrement() if hasattr(self.db, "_get_primary_key_autoincrement") else "INTEGER PRIMARY KEY AUTOINCREMENT"

    def _text_type(self, length: Optional[int] = None) -> str:
        if hasattr(self.db, "_get_text_type"):
            return self.db._get_text_type(length)
        return "TEXT"

    def _decimal_type(self) -> str:
        if hasattr(self.db, "_get_decimal_type"):
            return self.db._get_decimal_type(18, 2)
        return "REAL"

    def _db_money(self, value: Any) -> str:
        """Return DB-safe string for Decimal money values."""
        return str(money_round(value))

    def _db_qty(self, value: Any) -> str:
        """Return DB-safe string for quantities/rates stored in REAL fields."""
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
        # Database uses a persistent connection. Commit any previous implicit transaction first.
        try:
            conn.commit()
        except Exception:
            pass
        if getattr(self.db, "db_type", "sqlite") == "mysql" and hasattr(conn, "start_transaction"):
            conn.start_transaction()
        else:
            conn.execute("BEGIN")

    def _column_exists(self, cursor, table: str, column: str) -> bool:
        if getattr(self.db, "db_type", "sqlite") == "sqlite":
            cursor.execute(f"PRAGMA table_info({table})")
            return column in [row[1] for row in cursor.fetchall()]
        cursor.execute(f"SHOW COLUMNS FROM {table} LIKE {self._ph()}", (column,))
        return cursor.fetchone() is not None

    def _table_exists(self, cursor, table: str) -> bool:
        if hasattr(self.db, "_check_table_exists"):
            return self.db._check_table_exists(cursor, table)
        ph = self._ph()
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name={ph}", (table,))
        return cursor.fetchone() is not None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def ensure_schema(self) -> Dict[str, Any]:
        """Create/migrate all van tables safely."""
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        pk = self._pk()
        ts = self._timestamp_default()
        txt_50 = self._text_type(50)
        txt_100 = self._text_type(100)
        txt_255 = self._text_type(255)
        dec = self._decimal_type()

        try:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS locations (
                    id {pk},
                    company_id INTEGER NOT NULL,
                    location_name {txt_255} NOT NULL,
                    location_type {txt_50} NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT {ts},
                    updated_at TIMESTAMP DEFAULT {ts},
                    UNIQUE(company_id, location_name)
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS van_loads (
                    id {pk},
                    company_id INTEGER NOT NULL,
                    van_id INTEGER NOT NULL,
                    load_no {txt_100} NOT NULL,
                    load_date DATE NOT NULL,
                    status {txt_50} DEFAULT 'Loaded',
                    narration TEXT,
                    created_at TIMESTAMP DEFAULT {ts},
                    updated_at TIMESTAMP DEFAULT {ts},
                    UNIQUE(company_id, load_no)
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS van_load_items (
                    id {pk},
                    van_load_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    sl_no INTEGER,
                    product_name {txt_255},
                    main_stock_before {dec} DEFAULT 0.0,
                    load_qty {dec} DEFAULT 0.0,
                    rate {dec} DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT {ts}
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS van_returns (
                    id {pk},
                    company_id INTEGER NOT NULL,
                    van_id INTEGER NOT NULL,
                    van_load_id INTEGER,
                    return_no {txt_100} NOT NULL,
                    return_date DATE NOT NULL,
                    total_goods_value {dec} DEFAULT 0.0,
                    total_return_value {dec} DEFAULT 0.0,
                    total_sold_value {dec} DEFAULT 0.0,
                    cash_received {dec} DEFAULT 0.0,
                    credit_amount {dec} DEFAULT 0.0,
                    shortage_excess {dec} DEFAULT 0.0,
                    status {txt_50} DEFAULT 'Returned',
                    narration TEXT,
                    created_at TIMESTAMP DEFAULT {ts},
                    updated_at TIMESTAMP DEFAULT {ts},
                    UNIQUE(company_id, return_no)
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS van_return_items (
                    id {pk},
                    van_return_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    sl_no INTEGER,
                    product_name {txt_255},
                    issued_qty {dec} DEFAULT 0.0,
                    returned_qty {dec} DEFAULT 0.0,
                    sold_qty {dec} DEFAULT 0.0,
                    rate {dec} DEFAULT 0.0,
                    sold_value {dec} DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT {ts}
                )
            """)

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS van_credit_bills (
                    id {pk},
                    van_return_id INTEGER NOT NULL,
                    party_id INTEGER,
                    party_name {txt_255},
                    bill_no {txt_100},
                    amount {dec} DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT {ts}
                )
            """)

            if self._table_exists(cursor, "stock_movements"):
                for col in ("source_location_id", "destination_location_id"):
                    if not self._column_exists(cursor, "stock_movements", col):
                        cursor.execute(f"ALTER TABLE stock_movements ADD COLUMN {col} INTEGER")

            # Conversion tracking columns (safe migration)
            for tbl_col in [
                ("van_loads", "converted_to_sales", "INTEGER DEFAULT 0"),
                ("van_loads", "converted_sales_id", "TEXT"),
                ("van_returns", "converted_to_sales", "INTEGER DEFAULT 0"),
                ("van_returns", "converted_sales_id", "TEXT"),
            ]:
                tbl, col, col_def = tbl_col
                if self._table_exists(cursor, tbl) and not self._column_exists(cursor, tbl, col):
                    cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_def}")

            indexes = [
                ("idx_locations_company_type", "locations", "company_id, location_type"),
                ("idx_van_loads_company_van_date", "van_loads", "company_id, van_id, load_date"),
                ("idx_van_load_items_load_product", "van_load_items", "van_load_id, product_id"),
                ("idx_van_returns_company_van_date", "van_returns", "company_id, van_id, return_date"),
                ("idx_van_return_items_return_product", "van_return_items", "van_return_id, product_id"),
                ("idx_van_credit_bills_return", "van_credit_bills", "van_return_id"),
            ]
            for name, table, columns in indexes:
                try:
                    if hasattr(self.db, "_create_index_if_missing"):
                        self.db._create_index_if_missing(cursor, table, name, columns)
                    else:
                        cursor.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")
                except Exception:
                    pass

            conn.commit()
            company_id = active_company_manager.get_active_company_id()
            if company_id:
                self.ensure_main_godown(company_id)
            return {"success": True, "message": "Van schema ready"}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Van schema error: {e}"}

    def ensure_main_godown(self, company_id: int) -> Dict[str, Any]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            cursor.execute(
                f"SELECT id FROM locations WHERE company_id={ph} AND location_name={ph}",
                (company_id, "Main Godown"),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"INSERT INTO locations (company_id, location_name, location_type, is_active) VALUES ({ph}, {ph}, {ph}, 1)",
                    (company_id, "Main Godown", "Warehouse"),
                )
                conn.commit()
            return {"success": True}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}

    # ------------------------------------------------------------------
    # Conversion tracking helpers
    # ------------------------------------------------------------------
    def mark_van_load_converted(self, company_id: int, load_id: int, sales_ref: str = "") -> Dict[str, Any]:
        """Mark a van load as converted to a Sales Bill."""
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            cursor.execute(
                f"UPDATE van_loads SET converted_to_sales=1, converted_sales_id={ph}, updated_at=CURRENT_TIMESTAMP WHERE id={ph} AND company_id={ph}",
                (sales_ref, load_id, company_id),
            )
            conn.commit()
            return {"success": True}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}

    def mark_van_return_converted(self, company_id: int, return_id: int, sales_ref: str = "") -> Dict[str, Any]:
        """Mark a van return as converted to a Sales Bill."""
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            cursor.execute(
                f"UPDATE van_returns SET converted_to_sales=1, converted_sales_id={ph}, updated_at=CURRENT_TIMESTAMP WHERE id={ph} AND company_id={ph}",
                (sales_ref, return_id, company_id),
            )
            conn.commit()
            return {"success": True}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}

    def reverse_van_return_stock(self, company_id: int, return_id: int) -> Dict[str, Any]:
        """Reverse stock movements posted by a van return so Sales Entry can re-post cleanly.

        Called BEFORE opening Sales Entry from a saved Van Return to prevent
        double stock-out posting.  The van_return record itself is preserved.
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            cursor.execute(
                f"DELETE FROM stock_movements WHERE company_id={ph} AND reference_type={ph} AND reference_id={ph}",
                (company_id, "van_return", return_id),
            )
            conn.commit()
            return {"success": True, "deleted": cursor.rowcount}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": str(e)}

    def get_van_load_conversion_status(self, company_id: int, load_id: int) -> Dict[str, Any]:
        """Return conversion flag and linked sales ref for a van load."""
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(
            f"SELECT converted_to_sales, converted_sales_id FROM van_loads WHERE id={ph} AND company_id={ph}",
            (load_id, company_id),
        )
        row = self._fetchone(cursor)
        if row is None:
            return {"found": False, "converted": False, "sales_ref": ""}
        return {
            "found": True,
            "converted": bool(row.get("converted_to_sales", 0)),
            "sales_ref": row.get("converted_sales_id") or "",
        }

    def get_van_return_conversion_status(self, company_id: int, return_id: int) -> Dict[str, Any]:
        """Return conversion flag and linked sales ref for a van return."""
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(
            f"SELECT converted_to_sales, converted_sales_id FROM van_returns WHERE id={ph} AND company_id={ph}",
            (return_id, company_id),
        )
        row = self._fetchone(cursor)
        if row is None:
            return {"found": False, "converted": False, "sales_ref": ""}
        return {
            "found": True,
            "converted": bool(row.get("converted_to_sales", 0)),
            "sales_ref": row.get("converted_sales_id") or "",
        }

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------
    def get_locations(self, company_id: int, location_type: Optional[str] = None) -> List[Dict[str, Any]]:
        self.ensure_main_godown(company_id)
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        if location_type:
            cursor.execute(
                f"SELECT * FROM locations WHERE company_id={ph} AND location_type={ph} AND COALESCE(is_active,1)=1 ORDER BY location_name",
                (company_id, location_type),
            )
        else:
            cursor.execute(
                f"SELECT * FROM locations WHERE company_id={ph} AND COALESCE(is_active,1)=1 ORDER BY location_type, location_name",
                (company_id,),
            )
        return self._fetchall(cursor)

    def get_vans(self, company_id: int) -> List[Dict[str, Any]]:
        return self.get_locations(company_id, "Van")

    def get_main_godown(self, company_id: int) -> Optional[Dict[str, Any]]:
        self.ensure_main_godown(company_id)
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(
            f"SELECT * FROM locations WHERE company_id={ph} AND location_name={ph}",
            (company_id, "Main Godown"),
        )
        return self._fetchone(cursor)

    def create_van(self, company_id: int, van_name: str) -> Dict[str, Any]:
        van_name = (van_name or "").strip()
        if not van_name:
            return {"success": False, "message": "Van name is required."}
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            self._begin(conn)
            cursor.execute(
                f"SELECT id FROM locations WHERE company_id={ph} AND LOWER(location_name)=LOWER({ph})",
                (company_id, van_name),
            )
            if cursor.fetchone() is not None:
                conn.rollback()
                return {"success": False, "message": f"Van/location '{van_name}' already exists."}
            cursor.execute(
                f"INSERT INTO locations (company_id, location_name, location_type, is_active) VALUES ({ph}, {ph}, {ph}, 1)",
                (company_id, van_name, "Van"),
            )
            conn.commit()
            return {"success": True, "message": f"Van '{van_name}' created."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Error adding van: {e}"}

    def update_van(self, company_id: int, van_id: int, new_name: str) -> Dict[str, Any]:
        new_name = (new_name or "").strip()
        if not new_name:
            return {"success": False, "message": "Van name is required."}
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            self._begin(conn)
            cursor.execute(
                f"SELECT id FROM locations WHERE company_id={ph} AND LOWER(location_name)=LOWER({ph}) AND id!={ph}",
                (company_id, new_name, van_id)
            )
            if cursor.fetchone() is not None:
                conn.rollback()
                return {"success": False, "message": f"Van '{new_name}' already exists."}
            cursor.execute(
                f"UPDATE locations SET location_name={ph}, updated_at=CURRENT_TIMESTAMP WHERE id={ph} AND company_id={ph} AND location_type='Van'",
                (new_name, van_id, company_id)
            )
            conn.commit()
            return {"success": True, "message": f"Van updated to '{new_name}'."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Error updating van: {e}"}

    def delete_van(self, company_id: int, van_id: int) -> Dict[str, Any]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            self._begin(conn)
            cursor.execute(f"DELETE FROM locations WHERE id={ph} AND company_id={ph} AND location_type='Van'", (van_id, company_id))
            conn.commit()
            return {"success": True, "message": "Van deleted."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Error deleting van: {e}"}

    def get_products_for_van_load(self, company_id: int) -> List[Dict[str, Any]]:
        try:
            products = self.db.get_products_by_company(company_id)
        except Exception:
            products = []
        cleaned = []
        for product in products:
            cleaned.append({
                "product_id": product.get("id"),
                "product_name": product.get("name", ""),
                "barcode": product.get("barcode", ""),
                "hsn": product.get("hsn", ""),
                "unit": product.get("unit", "pcs"),
                "current_main_stock": product.get("quantity", 0),
                "rate": product.get("sale_price") or product.get("mrp") or product.get("purchase_rate") or 0,
            })
        return cleaned

    def get_next_van_load_no(self, company_id: int) -> str:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(
            f"SELECT load_no FROM van_loads WHERE company_id={ph} ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        row = cursor.fetchone()
        if not row:
            return "VL-0001"
        value = row[0] if not isinstance(row, dict) else row.get("load_no", "")
        return self._next_code(value, "VL")

    def get_next_van_return_no(self, company_id: int) -> str:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(
            f"SELECT return_no FROM van_returns WHERE company_id={ph} ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        row = cursor.fetchone()
        if not row:
            return "VR-0001"
        value = row[0] if not isinstance(row, dict) else row.get("return_no", "")
        return self._next_code(value, "VR")

    def _next_code(self, previous: str, prefix: str) -> str:
        try:
            num = int(str(previous).split("-")[-1]) + 1
        except Exception:
            num = 1
        return f"{prefix}-{num:04d}"


    # ------------------------------------------------------------------
    # Van load/return navigation helpers
    # ------------------------------------------------------------------
    def get_van_load_ids(self, company_id: int) -> List[int]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(f"SELECT id FROM van_loads WHERE company_id={ph} ORDER BY id ASC", (company_id,))
        rows = self._fetchall(cursor)
        return [int(r.get("id")) for r in rows if r.get("id") is not None]

    def get_van_return_ids(self, company_id: int) -> List[int]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(f"SELECT id FROM van_returns WHERE company_id={ph} ORDER BY id ASC", (company_id,))
        rows = self._fetchall(cursor)
        return [int(r.get("id")) for r in rows if r.get("id") is not None]

    def get_previous_van_load(self, company_id: int, current_id: int) -> Optional[Dict[str, Any]]:
        """Return the van load with the highest id strictly less than current_id."""
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(
            f"SELECT id FROM van_loads WHERE company_id={ph} AND id<{ph} ORDER BY id DESC LIMIT 1",
            (company_id, current_id),
        )
        row = self._fetchone(cursor)
        return row  # dict with 'id' or None

    def get_next_van_load(self, company_id: int, current_id: int) -> Optional[Dict[str, Any]]:
        """Return the van load with the lowest id strictly greater than current_id."""
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(
            f"SELECT id FROM van_loads WHERE company_id={ph} AND id>{ph} ORDER BY id ASC LIMIT 1",
            (company_id, current_id),
        )
        row = self._fetchone(cursor)
        return row  # dict with 'id' or None

    def get_van_load_by_id(self, company_id: int, load_id: int) -> Dict[str, Any]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(f"SELECT * FROM van_loads WHERE company_id={ph} AND id={ph}", (company_id, load_id))
        header = self._fetchone(cursor)
        if not header:
            return {"success": False, "message": "Van Load not found.", "header": None, "items": []}
        cursor.execute(f"SELECT * FROM van_load_items WHERE van_load_id={ph} ORDER BY sl_no, id", (load_id,))
        return {"success": True, "header": header, "items": self._fetchall(cursor)}

    def get_van_return_by_id(self, company_id: int, return_id: int) -> Dict[str, Any]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        cursor.execute(f"SELECT * FROM van_returns WHERE company_id={ph} AND id={ph}", (company_id, return_id))
        header = self._fetchone(cursor)
        if not header:
            return {"success": False, "message": "Van Return not found.", "header": None, "items": [], "credit_bills": []}
        cursor.execute(f"SELECT * FROM van_return_items WHERE van_return_id={ph} ORDER BY sl_no, id", (return_id,))
        items = self._fetchall(cursor)
        cursor.execute(f"SELECT * FROM van_credit_bills WHERE van_return_id={ph} ORDER BY id", (return_id,))
        credit_bills = self._fetchall(cursor)
        return {"success": True, "header": header, "items": items, "credit_bills": credit_bills}

    # ------------------------------------------------------------------
    # Van Load
    # ------------------------------------------------------------------
    def save_van_entry(self, company_id: int, van_id: int, load_date: str, items: List[Dict[str, Any]], narration: str = "") -> Dict[str, Any]:
        valid_items = []
        for item in items:
            load_qty = to_decimal(item.get("load_qty"))
            if load_qty > 0:
                current_stock = to_decimal(item.get("current_main_stock"))
                if load_qty > current_stock:
                    return {"success": False, "message": f"Load qty exceeds stock for {item.get('product_name', '')}."}
                valid_items.append(item)
        if not valid_items:
            return {"success": False, "message": "Enter at least one Load Qty."}

        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            self._begin(conn)
            load_no = self.get_next_van_load_no(company_id)
            cursor.execute(
                f"INSERT INTO van_loads (company_id, van_id, load_no, load_date, status, narration) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                (company_id, van_id, load_no, load_date, "Loaded", narration),
            )
            load_id = cursor.lastrowid

            for sl_no, item in enumerate(valid_items, 1):
                cursor.execute(
                    f"""
                    INSERT INTO van_load_items
                    (van_load_id, product_id, sl_no, product_name, main_stock_before, load_qty, rate)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (
                        load_id,
                        item.get("product_id"),
                        sl_no,
                        item.get("product_name", ""),
                        self._db_qty(item.get("current_main_stock")),
                        self._db_qty(item.get("load_qty")),
                        self._db_money(item.get("rate")),
                    ),
                )

            conn.commit()
            return {"success": True, "message": f"Van Load {load_no} saved.", "load_id": load_id, "load_no": load_no}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Failed to save Van Load: {e}"}

    def get_open_van_loads(self, company_id: int, van_id: Optional[int] = None) -> List[Dict[str, Any]]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        if van_id:
            cursor.execute(
                f"""
                SELECT vl.*, l.location_name AS van_name
                FROM van_loads vl
                LEFT JOIN locations l ON l.id = vl.van_id
                WHERE vl.company_id={ph} AND vl.van_id={ph} AND vl.status='Loaded'
                ORDER BY vl.id DESC
                """,
                (company_id, van_id),
            )
        else:
            cursor.execute(
                f"""
                SELECT vl.*, l.location_name AS van_name
                FROM van_loads vl
                LEFT JOIN locations l ON l.id = vl.van_id
                WHERE vl.company_id={ph} AND vl.status='Loaded'
                ORDER BY vl.id DESC
                """,
                (company_id,),
            )
        return self._fetchall(cursor)

    def get_van_load_for_return(self, company_id: int, van_id: int, van_load_id: Optional[int] = None) -> Dict[str, Any]:
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        if not van_load_id:
            loads = self.get_open_van_loads(company_id, van_id)
            if not loads:
                return {"success": False, "message": "No open Van Load found for this van.", "header": None, "items": []}
            van_load_id = loads[0]["id"]
        cursor.execute(
            f"SELECT * FROM van_loads WHERE company_id={ph} AND van_id={ph} AND id={ph}",
            (company_id, van_id, van_load_id),
        )
        header = self._fetchone(cursor)
        if not header:
            return {"success": False, "message": "Van Load not found.", "header": None, "items": []}
        cursor.execute(
            f"SELECT * FROM van_load_items WHERE van_load_id={ph} ORDER BY sl_no, id",
            (van_load_id,),
        )
        return {"success": True, "header": header, "items": self._fetchall(cursor)}

    # ------------------------------------------------------------------
    # Van Return
    # ------------------------------------------------------------------
    def save_van_return(
        self,
        company_id: int,
        van_id: int,
        return_date: str,
        van_load_id: int,
        return_items: List[Dict[str, Any]],
        credit_bills: List[Dict[str, Any]],
        cash_received: Any,
        narration: str = "",
    ) -> Dict[str, Any]:
        if not return_items:
            return {"success": False, "message": "No van return items found."}

        total_goods = Decimal("0.00")
        total_return = Decimal("0.00")
        total_sold = Decimal("0.00")
        normalized_items = []
        for item in return_items:
            issued = to_decimal(item.get("issued_qty"))
            returned = to_decimal(item.get("returned_qty"))
            if returned > issued:
                return {"success": False, "message": f"Returned qty exceeds issued qty for {item.get('product_name', '')}."}
            sold = issued - returned
            rate = to_decimal(item.get("rate"))
            sold_value = money_round(sold * rate)
            total_goods += money_round(issued * rate)
            total_return += money_round(returned * rate)
            total_sold += sold_value
            normalized_items.append((item, issued, returned, sold, rate, sold_value))

        credit_total = Decimal("0.00")
        normalized_credit = []
        for bill in credit_bills:
            amount = to_decimal(bill.get("amount"))
            if amount > 0:
                credit_total += amount
                normalized_credit.append((bill, amount))

        cash = to_decimal(cash_received)
        expected_cash = money_round(total_sold - credit_total)
        shortage_excess = money_round(cash - expected_cash)
        if shortage_excess != Decimal("0.00"):
            return {"success": False, "message": f"Shortage/Excess must be 0.00 before saving. Current: {format_money(shortage_excess)}"}

        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            self._begin(conn)
            return_no = self.get_next_van_return_no(company_id)
            cursor.execute(
                f"""
                INSERT INTO van_returns
                (company_id, van_id, van_load_id, return_no, return_date, total_goods_value,
                 total_return_value, total_sold_value, cash_received, credit_amount, shortage_excess, status, narration)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """,
                (
                    company_id,
                    van_id,
                    van_load_id,
                    return_no,
                    return_date,
                    self._db_money(total_goods),
                    self._db_money(total_return),
                    self._db_money(total_sold),
                    self._db_money(cash),
                    self._db_money(credit_total),
                    self._db_money(shortage_excess),
                    "Returned",
                    narration,
                ),
            )
            return_id = cursor.lastrowid

            for sl_no, (item, issued, returned, sold, rate, sold_value) in enumerate(normalized_items, 1):
                cursor.execute(
                    f"""
                    INSERT INTO van_return_items
                    (van_return_id, product_id, sl_no, product_name, issued_qty, returned_qty, sold_qty, rate, sold_value)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (
                        return_id,
                        item.get("product_id"),
                        sl_no,
                        item.get("product_name", ""),
                        self._db_qty(issued),
                        self._db_qty(returned),
                        self._db_qty(sold),
                        self._db_money(rate),
                        self._db_money(sold_value),
                    ),
                )

                # Post only actually sold quantity to stock movements, so company stock reduces once.
                if sold > 0:
                    cursor.execute(
                        f"""
                        INSERT INTO stock_movements
                        (company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, movement_date, voucher_type, voucher_no, qty_out, rate, value_out)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                        """,
                        (
                            company_id,
                            item.get("product_id"),
                            "sale",
                            -self._db_qty(sold),
                            "van_return",
                            return_id,
                            f"Van sale settled by {return_no}",
                            return_date,
                            "Van Sale",
                            return_no,
                            self._db_qty(sold),
                            self._db_money(rate),
                            self._db_money(sold_value),
                        ),
                    )

            for bill, amount in normalized_credit:
                cursor.execute(
                    f"""
                    INSERT INTO van_credit_bills
                    (van_return_id, party_id, party_name, bill_no, amount)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (
                        return_id,
                        bill.get("party_id"),
                        bill.get("party_name", ""),
                        bill.get("bill_no", ""),
                        self._db_money(amount),
                    ),
                )

            cursor.execute(f"UPDATE van_loads SET status='Returned', updated_at=CURRENT_TIMESTAMP WHERE id={ph}", (van_load_id,))
            conn.commit()
            return {"success": True, "message": f"Van Return {return_no} saved.", "return_id": return_id, "return_no": return_no}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Failed to save Van Return: {e}"}

    # ------------------------------------------------------------------
    # Safe delete helpers
    # ------------------------------------------------------------------
    def delete_van_load(self, company_id: int, load_id: int) -> Dict[str, Any]:
        """Safely delete a Van Load entry and all its dependents.

        Order of operations (all in one transaction):
        1. Reverse any stock_movements posted for this van load.
        2. Delete all van_load_items rows.
        3. Delete the van_loads header row.

        NOTE: Van loads do NOT post ledger_entries, so no ledger reversal is needed.
        If any linked van_return exists it is left intact (orphaned returns are
        not deleted automatically — the user should handle them separately).
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            # Verify the load belongs to this company
            cursor.execute(
                f"SELECT id, load_no FROM van_loads WHERE id={ph} AND company_id={ph}",
                (load_id, company_id),
            )
            row = self._fetchone(cursor)
            if not row:
                return {"success": False, "message": "Van Load not found or access denied."}
            load_no = row.get("load_no", str(load_id))

            self._begin(conn)

            # 1. Remove stock_movements linked to this van load (safety — usually none for loads)
            cursor.execute(
                f"DELETE FROM stock_movements WHERE company_id={ph} AND reference_type={ph} AND reference_id={ph}",
                (company_id, "van_load", load_id),
            )

            # 2. Remove line items
            cursor.execute(
                f"DELETE FROM van_load_items WHERE van_load_id={ph}",
                (load_id,),
            )

            # 3. Remove header
            cursor.execute(
                f"DELETE FROM van_loads WHERE id={ph} AND company_id={ph}",
                (load_id, company_id),
            )

            conn.commit()
            return {"success": True, "message": f"Van Load {load_no} deleted successfully."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Failed to delete Van Load: {e}"}

    def delete_van_return(self, company_id: int, return_id: int) -> Dict[str, Any]:
        """Safely delete a Van Return entry and all its dependents.

        Order of operations (all in one transaction):
        1. Reverse stock_movements posted by this van return (sold qty stock-outs).
        2. Optionally re-open the linked van load status back to 'Loaded'.
        3. Delete all van_return_items rows.
        4. Delete all van_credit_bills rows.
        5. Delete the van_returns header row.

        NOTE: Van returns do NOT post ledger_entries directly, so no ledger
        reversal is needed. Cash/credit tracking is done inside the van module only.
        """
        conn = self.db.connect()
        cursor = conn.cursor()
        ph = self._ph()
        try:
            # Verify the return belongs to this company
            cursor.execute(
                f"SELECT id, return_no, van_load_id FROM van_returns WHERE id={ph} AND company_id={ph}",
                (return_id, company_id),
            )
            row = self._fetchone(cursor)
            if not row:
                return {"success": False, "message": "Van Return not found or access denied."}
            return_no = row.get("return_no", str(return_id))
            van_load_id = row.get("van_load_id")

            self._begin(conn)

            # 1. Reverse stock_movements posted by this van return
            cursor.execute(
                f"DELETE FROM stock_movements WHERE company_id={ph} AND reference_type={ph} AND reference_id={ph}",
                (company_id, "van_return", return_id),
            )

            # 2. Re-open linked van load (if still present) so it can be settled again
            if van_load_id:
                cursor.execute(
                    f"UPDATE van_loads SET status='Loaded', updated_at=CURRENT_TIMESTAMP "
                    f"WHERE id={ph} AND company_id={ph} AND status='Returned'",
                    (van_load_id, company_id),
                )

            # 3. Remove credit bills
            cursor.execute(
                f"DELETE FROM van_credit_bills WHERE van_return_id={ph}",
                (return_id,),
            )

            # 4. Remove line items
            cursor.execute(
                f"DELETE FROM van_return_items WHERE van_return_id={ph}",
                (return_id,),
            )

            # 5. Remove header
            cursor.execute(
                f"DELETE FROM van_returns WHERE id={ph} AND company_id={ph}",
                (return_id, company_id),
            )

            conn.commit()
            return {"success": True, "message": f"Van Return {return_no} deleted successfully."}
        except Exception as e:
            conn.rollback()
            return {"success": False, "message": f"Failed to delete Van Return: {e}"}

