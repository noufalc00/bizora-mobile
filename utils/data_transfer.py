"""
Inter-Company Data Transfer engine.

Uses SQLite ATTACH DATABASE to migrate master data (parties, products) and
transactional vouchers between company databases while resolving ID and barcode
collisions.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

TARGET_SCHEMA = "target_db"
SYNC_SUFFIX = "-SYNC"
TRANSFER_SUFFIX = "-TR"

RECORD_TYPE_LABELS: Dict[str, str] = {
    "sales": "Sales",
    "sales_returns": "Sales Return",
    "purchases": "Purchase",
    "purchase_returns": "Purchase Return",
    "quotations": "Quotation",
    "stock_adjustments": "Stock Adjustment",
}

TRANSACTION_SPECS: Dict[str, Dict[str, str]] = {
    "sales": {
        "header_table": "sales",
        "items_table": "sales_items",
        "item_fk": "sale_id",
        "date_column": "invoice_date",
        "number_column": "invoice_number",
        "party_column": "party_id",
    },
    "purchases": {
        "header_table": "purchases",
        "items_table": "purchase_items",
        "item_fk": "purchase_id",
        "date_column": "purchase_date",
        "number_column": "purchase_number",
        "party_column": "party_id",
    },
    "sales_returns": {
        "header_table": "sales_returns",
        "items_table": "sales_return_items",
        "item_fk": "sales_return_id",
        "date_column": "return_date",
        "number_column": "return_no",
        "party_column": "party_id",
    },
    "purchase_returns": {
        "header_table": "purchase_returns",
        "items_table": "purchase_return_items",
        "item_fk": "purchase_return_id",
        "date_column": "return_date",
        "number_column": "return_no",
        "party_column": "party_id",
    },
    "stock_adjustments": {
        "header_table": "stock_adjustments",
        "items_table": "stock_adjustment_items",
        "item_fk": "adjustment_id",
        "date_column": "voucher_date",
        "number_column": "voucher_no",
        "party_column": "",
    },
    "quotations": {
        "header_table": "quotations",
        "items_table": "quotation_items",
        "item_fk": "quotation_id",
        "date_column": "quotation_date",
        "number_column": "quotation_no",
        "party_column": "party_id",
    },
}


class DataTransferEngine:
    """Migrate master data and transactions between two company SQLite databases."""

    def transfer_data(
        self,
        source_db: str,
        target_db: str,
        selected_data: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Transfer selected records and their master-data dependencies into target_db.

        Execution order:
        1. Resolve party/product dependencies for the selected bill numbers.
        2. Sync those parties and products into the target (with barcode collision handling).
        3. Insert the selected transaction headers and line items.

        Args:
            source_db: Path to the source SQLite database (opened as ``main``).
            target_db: Path to the destination SQLite database (attached schema).
            selected_data: Selection payload such as
                ``{'master_data_only': True, 'sales': ['INV-01', 'INV-03']}``.

        Returns:
            ``(True, "Success")`` or ``(False, error_message)``.
        """
        source_path = os.path.abspath(source_db)
        target_path = os.path.abspath(target_db)

        if not os.path.isfile(source_path):
            return False, f"Source database not found: {source_path}"
        if not os.path.isfile(target_path):
            return False, f"Target database not found: {target_path}"
        if source_path == target_path:
            return False, "Source and target databases must be different files"

        master_data_only = bool(selected_data.get("master_data_only"))
        enabled_types, selected_numbers = _parse_selected_data(selected_data)
        if not master_data_only and not enabled_types:
            return False, "No records were selected for transfer"

        connection: Optional[sqlite3.Connection] = None
        attached = False
        try:
            connection = _connect(source_path)
            connection.execute(f"ATTACH DATABASE ? AS {TARGET_SCHEMA}", (target_path,))
            attached = True

            source_company_id = _get_active_company_id(connection, schema="main")
            target_company_id = _get_active_company_id(connection, schema=TARGET_SCHEMA)
            if not source_company_id:
                return False, "No company found in source database"
            if not target_company_id:
                return False, "No company found in target database"

            # Step 1: auto-dependency resolution for the specifically selected bills.
            party_ids: Set[int] = set()
            product_ids: Set[int] = set()
            if enabled_types:
                party_ids, product_ids = _resolve_dependencies_for_selected_records(
                    connection,
                    enabled_types,
                    selected_numbers,
                    source_company_id,
                )
            if master_data_only:
                party_ids |= _collect_all_party_ids(connection, source_company_id)
                product_ids |= _collect_all_product_ids(connection, source_company_id)

            connection.execute("BEGIN")

            # Step 2: sync master data required by the selected bills.
            party_map = self._sync_parties(
                connection,
                source_company_id,
                target_company_id,
                party_ids,
            )
            product_map = self._sync_products(
                connection,
                source_company_id,
                target_company_id,
                product_ids,
            )

            # Step 3: sync the selected transaction headers and line items.
            self._sync_transactions(
                connection,
                enabled_types,
                source_company_id,
                target_company_id,
                party_map,
                product_map,
                selected_numbers,
            )
            connection.execute("COMMIT")
            return True, "Success"
        except Exception as error:
            if connection is not None:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            return False, str(error)
        finally:
            if connection is not None:
                if attached:
                    try:
                        connection.execute(f"DETACH DATABASE {TARGET_SCHEMA}")
                    except sqlite3.Error:
                        pass
                connection.close()

    def _sync_parties(
        self,
        connection: sqlite3.Connection,
        source_company_id: int,
        target_company_id: int,
        party_ids: Set[int],
    ) -> Dict[int, int]:
        """Insert missing parties into the target and return source->target ID map."""
        if not party_ids:
            return {}

        placeholders = ",".join("?" * len(party_ids))
        party_columns = _get_insert_columns(connection, "parties", exclude=("id",))
        if not party_columns:
            return {}

        insert_columns = ", ".join(party_columns)

        # Bulk insert parties that do not already exist in the target (by name or phone).
        connection.execute(
            f"""
            INSERT INTO {TARGET_SCHEMA}.parties ({insert_columns})
            SELECT
                {", ".join(
                    str(target_company_id) if column == "company_id" else f"p.{column}"
                    for column in party_columns
                )}
            FROM main.parties p
            WHERE p.company_id = ?
              AND p.id IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM {TARGET_SCHEMA}.parties tp
                  WHERE tp.company_id = ?
                    AND (
                        tp.name = p.name
                        OR (
                            COALESCE(p.mobile_number, '') != ''
                            AND tp.mobile_number = p.mobile_number
                        )
                    )
              )
            """,
            (source_company_id, *party_ids, target_company_id),
        )

        return _build_party_map(
            connection,
            source_company_id,
            target_company_id,
            party_ids,
        )

    def _sync_products(
        self,
        connection: sqlite3.Connection,
        source_company_id: int,
        target_company_id: int,
        product_ids: Set[int],
    ) -> Dict[int, int]:
        """Resolve barcode conflicts and return source->target product ID map."""
        product_map: Dict[int, int] = {}
        if not product_ids:
            return product_map

        placeholders = ",".join("?" * len(product_ids))
        cursor = connection.execute(
            f"""
            SELECT *
            FROM main.products
            WHERE company_id = ?
              AND id IN ({placeholders})
            ORDER BY id
            """,
            (source_company_id, *product_ids),
        )
        source_products = [dict(row) for row in cursor.fetchall()]
        product_columns = _get_insert_columns(connection, "products", exclude=("id",))

        for product in source_products:
            source_id = int(product["id"])
            barcode = (product.get("barcode") or "").strip()
            name = (product.get("name") or "").strip()

            if barcode:
                target_match = connection.execute(
                    f"""
                    SELECT id, name
                    FROM {TARGET_SCHEMA}.products
                    WHERE company_id = ?
                      AND barcode = ?
                    LIMIT 1
                    """,
                    (target_company_id, barcode),
                ).fetchone()

                if target_match:
                    target_id = int(target_match["id"])
                    target_name = (target_match["name"] or "").strip()
                    if target_name == name:
                        product_map[source_id] = target_id
                        continue

                    insert_row = _product_row_for_insert(
                        product,
                        product_columns,
                        target_company_id,
                        barcode=_unique_sync_barcode(
                            connection,
                            target_company_id,
                            barcode,
                        ),
                    )
                    new_id = _insert_mapped_row(
                        connection,
                        f"{TARGET_SCHEMA}.products",
                        insert_row,
                    )
                    product_map[source_id] = new_id
                    continue

            insert_row = _product_row_for_insert(
                product,
                product_columns,
                target_company_id,
                barcode=barcode or product.get("barcode"),
            )
            new_id = _insert_mapped_row(connection, f"{TARGET_SCHEMA}.products", insert_row)
            product_map[source_id] = new_id

        return product_map

    def _sync_transactions(
        self,
        connection: sqlite3.Connection,
        enabled_types: Dict[str, Dict[str, str]],
        source_company_id: int,
        target_company_id: int,
        party_map: Dict[int, int],
        product_map: Dict[int, int],
        selected_numbers: Dict[str, List[str]],
    ) -> None:
        """Copy selected voucher headers and line items into the target database."""
        for type_key, spec in enabled_types.items():
            self._transfer_voucher_type(
                connection,
                type_key,
                spec,
                source_company_id,
                target_company_id,
                party_map,
                product_map,
                selected_numbers.get(type_key, []),
            )

    def _transfer_voucher_type(
        self,
        connection: sqlite3.Connection,
        type_key: str,
        spec: Dict[str, str],
        source_company_id: int,
        target_company_id: int,
        party_map: Dict[int, int],
        product_map: Dict[int, int],
        selected_values: List[str],
    ) -> None:
        header_table = spec["header_table"]
        items_table = spec["items_table"]
        item_fk = spec["item_fk"]
        number_column = spec["number_column"]
        party_column = spec.get("party_column") or ""

        if not _table_exists(connection, header_table):
            return
        if items_table and not _table_exists(connection, items_table):
            return

        header_columns = _get_insert_columns(connection, header_table, exclude=("id",))
        item_columns = (
            _get_insert_columns(connection, items_table, exclude=("id",))
            if items_table
            else []
        )

        if not selected_values:
            return

        headers = _fetch_headers_for_selection(
            connection,
            spec,
            source_company_id,
            selected_values,
        )

        allowed_numbers = {_selection_value_as_document_number(value) for value in selected_values}
        for header_row in headers:
            header = dict(header_row)
            source_header_id = int(header["id"])
            document_number = str(header.get(number_column) or "")

            if document_number not in allowed_numbers and str(source_header_id) not in {
                str(value) for value in selected_values
            }:
                continue

            if document_number and _document_number_exists(
                connection,
                header_table,
                number_column,
                target_company_id,
                document_number,
            ):
                header[number_column] = _resolve_document_number(
                    connection,
                    header_table,
                    number_column,
                    target_company_id,
                    document_number,
                )

            header["company_id"] = target_company_id
            if party_column:
                source_party_id = header.get(party_column)
                if source_party_id is not None:
                    mapped_party_id = party_map.get(int(source_party_id))
                    if mapped_party_id is None:
                        raise RuntimeError(
                            f"Missing party mapping for {type_key} document "
                            f"'{document_number or source_header_id}'."
                        )
                    header[party_column] = mapped_party_id

            target_header_id = _insert_mapped_row(
                connection,
                f"{TARGET_SCHEMA}.{header_table}",
                _row_for_insert(header, header_columns),
            )

            if not items_table:
                continue

            line_items = connection.execute(
                f"""
                SELECT *
                FROM main.{items_table}
                WHERE {item_fk} = ?
                ORDER BY sl_no, id
                """,
                (source_header_id,),
            ).fetchall()

            for item_row in line_items:
                item = dict(item_row)
                source_product_id = item.get("product_id")
                if source_product_id is not None:
                    mapped_product_id = product_map.get(int(source_product_id))
                    if mapped_product_id is None:
                        raise RuntimeError(
                            f"Missing product mapping for {type_key} document "
                            f"'{document_number or source_header_id}'."
                        )
                    item["product_id"] = mapped_product_id

                item[item_fk] = target_header_id
                _insert_mapped_row(
                    connection,
                    f"{TARGET_SCHEMA}.{items_table}",
                    _row_for_insert(item, item_columns),
                )


def fetch_available_records(
    source_db: str,
    start_date: str,
    end_date: str,
    type_keys: Iterable[str],
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Fetch bill summaries from the source database for UI selection.

    Returns:
        ``(True, "", records)`` or ``(False, error_message, [])``.
    """
    source_path = os.path.abspath(source_db)
    if not os.path.isfile(source_path):
        return False, f"Source database not found: {source_path}", []

    type_keys = [key for key in type_keys if key in TRANSACTION_SPECS]
    if not type_keys:
        return False, "No supported record types were requested.", []

    records: List[Dict[str, Any]] = []
    try:
        with closing(_connect(source_path)) as connection:
            company_id = _get_active_company_id(connection, schema="main")
            if not company_id:
                return False, "No company found in source database.", []

            for type_key in type_keys:
                spec = TRANSACTION_SPECS[type_key]
                header_table = spec["header_table"]
                date_column = spec["date_column"]
                number_column = spec["number_column"]
                party_column = spec.get("party_column") or ""

                if not _table_exists(connection, header_table):
                    continue

                party_select = "COALESCE(p.name, '')"
                party_join = ""
                if party_column:
                    party_join = f"LEFT JOIN main.parties p ON p.id = h.{party_column}"
                    if header_table == "quotations":
                        party_select = "COALESCE(p.name, h.customer_name, '')"

                rows = connection.execute(
                    f"""
                    SELECT
                        h.id AS record_id,
                        h.{number_column} AS document_number,
                        h.{date_column} AS document_date,
                        {party_select} AS party_name,
                        COALESCE(h.grand_total, 0.0) AS amount
                    FROM main.{header_table} h
                    {party_join}
                    WHERE h.company_id = ?
                      AND h.{date_column} BETWEEN ? AND ?
                    ORDER BY h.{date_column}, h.{number_column}
                    """,
                    (company_id, start_date, end_date),
                ).fetchall()

                type_label = RECORD_TYPE_LABELS.get(type_key, type_key.replace("_", " ").title())
                for row in rows:
                    record = dict(row)
                    records.append(
                        {
                            "type_key": type_key,
                            "type_label": type_label,
                            "record_id": int(record["record_id"]),
                            "document_number": str(record.get("document_number") or ""),
                            "document_date": str(record.get("document_date") or ""),
                            "party_name": str(record.get("party_name") or ""),
                            "amount": float(record.get("amount") or 0.0),
                        }
                    )
    except Exception as error:
        return False, str(error), []

    return True, "", records


def _parse_selected_data(
    selected_data: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, str]], Dict[str, List[str]]]:
    enabled_types: Dict[str, Dict[str, str]] = {}
    selected_numbers: Dict[str, List[str]] = {}

    for type_key, spec in TRANSACTION_SPECS.items():
        value = selected_data.get(type_key)
        if isinstance(value, list) and value:
            enabled_types[type_key] = spec
            selected_numbers[type_key] = [str(number) for number in value]

    return enabled_types, selected_numbers


def _split_selection_values(selected_values: List[str]) -> Tuple[List[str], List[int]]:
    document_numbers: List[str] = []
    record_ids: List[int] = []
    for value in selected_values:
        text = str(value).strip()
        if not text:
            continue
        if text.isdigit():
            record_ids.append(int(text))
        else:
            document_numbers.append(text)
    return document_numbers, record_ids


def _selection_value_as_document_number(value: str) -> str:
    return str(value).strip()


def _resolve_dependencies_for_selected_records(
    connection: sqlite3.Connection,
    enabled_types: Dict[str, Dict[str, str]],
    selected_numbers: Dict[str, List[str]],
    company_id: int,
) -> Tuple[Set[int], Set[int]]:
    """Collect party and product IDs referenced by the selected bill numbers."""
    party_ids: Set[int] = set()
    product_ids: Set[int] = set()

    for type_key, spec in enabled_types.items():
        selected_values = selected_numbers.get(type_key) or []
        if not selected_values:
            continue
        party_ids |= _collect_party_ids_for_documents(
            connection,
            spec,
            company_id,
            selected_values,
        )
        product_ids |= _collect_product_ids_for_documents(
            connection,
            spec,
            company_id,
            selected_values,
        )

    return party_ids, product_ids


def _selection_filter_clause(
    number_column: str,
    document_numbers: List[str],
    record_ids: List[int],
) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if document_numbers:
        placeholders = ",".join("?" * len(document_numbers))
        clauses.append(f"header.{number_column} IN ({placeholders})")
        params.extend(document_numbers)

    if record_ids:
        placeholders = ",".join("?" * len(record_ids))
        clauses.append(f"header.id IN ({placeholders})")
        params.extend(record_ids)

    if not clauses:
        return "1 = 0", []

    return f"({' OR '.join(clauses)})", params


def _fetch_headers_for_selection(
    connection: sqlite3.Connection,
    spec: Dict[str, str],
    company_id: int,
    selected_values: List[str],
) -> List[sqlite3.Row]:
    header_table = spec["header_table"]
    number_column = spec["number_column"]
    if not _table_exists(connection, header_table):
        return []

    document_numbers, record_ids = _split_selection_values(selected_values)
    where_clause, params = _selection_filter_clause(
        number_column,
        document_numbers,
        record_ids,
    )

    return connection.execute(
        f"""
        SELECT header.*
        FROM main.{header_table} header
        WHERE header.company_id = ?
          AND {where_clause}
        ORDER BY header.id
        """,
        (company_id, *params),
    ).fetchall()


def _collect_party_ids_for_documents(
    connection: sqlite3.Connection,
    spec: Dict[str, str],
    company_id: int,
    selected_values: List[str],
) -> Set[int]:
    header_table = spec["header_table"]
    number_column = spec["number_column"]
    party_column = spec.get("party_column") or ""
    if not _table_exists(connection, header_table):
        return set()

    document_numbers, record_ids = _split_selection_values(selected_values)
    where_clause, params = _selection_filter_clause(
        number_column,
        document_numbers,
        record_ids,
    )
    party_ids: Set[int] = set()

    if party_column:
        rows = connection.execute(
            f"""
            SELECT DISTINCT header.{party_column} AS party_id
            FROM main.{header_table} header
            WHERE header.company_id = ?
              AND {where_clause}
              AND header.{party_column} IS NOT NULL
            """,
            (company_id, *params),
        ).fetchall()
        party_ids.update(int(row["party_id"]) for row in rows if row["party_id"] is not None)

    if header_table == "quotations" and _table_exists(connection, "parties"):
        rows = connection.execute(
            f"""
            SELECT DISTINCT parties.id AS party_id
            FROM main.{header_table} header
            JOIN main.parties parties
              ON parties.company_id = header.company_id
             AND parties.name = header.customer_name
            WHERE header.company_id = ?
              AND {where_clause}
              AND COALESCE(header.customer_name, '') != ''
            """,
            (company_id, *params),
        ).fetchall()
        party_ids.update(int(row["party_id"]) for row in rows if row["party_id"] is not None)

    return party_ids


def _collect_product_ids_for_documents(
    connection: sqlite3.Connection,
    spec: Dict[str, str],
    company_id: int,
    selected_values: List[str],
) -> Set[int]:
    header_table = spec["header_table"]
    items_table = spec["items_table"]
    item_fk = spec["item_fk"]
    number_column = spec["number_column"]
    if not _table_exists(connection, header_table):
        return set()
    if not items_table or not _table_exists(connection, items_table):
        return set()

    document_numbers, record_ids = _split_selection_values(selected_values)
    where_clause, params = _selection_filter_clause(
        number_column,
        document_numbers,
        record_ids,
    )
    product_ids: Set[int] = set()

    rows = connection.execute(
        f"""
        SELECT DISTINCT items.product_id AS product_id
        FROM main.{items_table} items
        JOIN main.{header_table} header ON header.id = items.{item_fk}
        WHERE header.company_id = ?
          AND {where_clause}
          AND items.product_id IS NOT NULL
        """,
        (company_id, *params),
    ).fetchall()
    product_ids.update(int(row["product_id"]) for row in rows if row["product_id"] is not None)

    item_columns = _get_table_columns(connection, items_table)
    if "barcode" in item_columns and _table_exists(connection, "products"):
        barcode_rows = connection.execute(
            f"""
            SELECT DISTINCT products.id AS product_id
            FROM main.{items_table} items
            JOIN main.{header_table} header ON header.id = items.{item_fk}
            JOIN main.products products
              ON products.company_id = header.company_id
             AND products.barcode = items.barcode
            WHERE header.company_id = ?
              AND {where_clause}
              AND COALESCE(items.barcode, '') != ''
            """,
            (company_id, *params),
        ).fetchall()
        product_ids.update(
            int(row["product_id"]) for row in barcode_rows if row["product_id"] is not None
        )

    return product_ids


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a hardened SQLite connection."""
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000;")
    connection.execute("PRAGMA journal_mode = DELETE;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _get_table_columns(connection: sqlite3.Connection, table_name: str) -> List[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in rows]


def _get_insert_columns(
    connection: sqlite3.Connection,
    table_name: str,
    exclude: Iterable[str] = ("id",),
) -> List[str]:
    excluded = set(exclude)
    return [column for column in _get_table_columns(connection, table_name) if column not in excluded]


def _get_active_company_id(connection: sqlite3.Connection, schema: str) -> Optional[int]:
    table_ref = "companies" if schema == "main" else f"{schema}.companies"
    if not _table_exists(connection, "companies") and schema == "main":
        return None

    row = connection.execute(
        f"""
        SELECT id
        FROM {table_ref}
        WHERE is_active = 1
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])

    row = connection.execute(
        f"""
        SELECT id
        FROM {table_ref}
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    return int(row["id"]) if row else None


def _collect_all_party_ids(
    connection: sqlite3.Connection,
    company_id: int,
) -> Set[int]:
    if not _table_exists(connection, "parties"):
        return set()

    rows = connection.execute(
        """
        SELECT id
        FROM main.parties
        WHERE company_id = ?
        """,
        (company_id,),
    ).fetchall()
    return {int(row["id"]) for row in rows}


def _collect_all_product_ids(
    connection: sqlite3.Connection,
    company_id: int,
) -> Set[int]:
    if not _table_exists(connection, "products"):
        return set()

    rows = connection.execute(
        """
        SELECT id
        FROM main.products
        WHERE company_id = ?
        """,
        (company_id,),
    ).fetchall()
    return {int(row["id"]) for row in rows}


def _build_party_map(
    connection: sqlite3.Connection,
    source_company_id: int,
    target_company_id: int,
    party_ids: Set[int],
) -> Dict[int, int]:
    if not party_ids:
        return {}

    placeholders = ",".join("?" * len(party_ids))
    rows = connection.execute(
        f"""
        SELECT sp.id AS source_id, tp.id AS target_id
        FROM main.parties sp
        JOIN {TARGET_SCHEMA}.parties tp
          ON tp.company_id = ?
         AND (
                tp.name = sp.name
             OR (
                    COALESCE(sp.mobile_number, '') != ''
                AND tp.mobile_number = sp.mobile_number
             )
         )
        WHERE sp.company_id = ?
          AND sp.id IN ({placeholders})
        """,
        (target_company_id, source_company_id, *party_ids),
    ).fetchall()

    party_map: Dict[int, int] = {}
    for row in rows:
        party_map[int(row["source_id"])] = int(row["target_id"])
    return party_map


def _product_row_for_insert(
    product: Dict[str, Any],
    columns: List[str],
    target_company_id: int,
    barcode: Optional[str],
) -> Dict[str, Any]:
    row = _row_for_insert(product, columns)
    row["company_id"] = target_company_id
    if "barcode" in row:
        row["barcode"] = barcode
    return row


def _row_for_insert(source_row: Dict[str, Any], columns: List[str]) -> Dict[str, Any]:
    return {column: source_row.get(column) for column in columns}


def _insert_mapped_row(
    connection: sqlite3.Connection,
    qualified_table: str,
    row: Dict[str, Any],
) -> int:
    columns = list(row.keys())
    placeholders = ", ".join("?" * len(columns))
    values = [row[column] for column in columns]
    connection.execute(
        f"INSERT INTO {qualified_table} ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    inserted = connection.execute("SELECT last_insert_rowid()").fetchone()
    return int(inserted[0])


def _document_number_exists(
    connection: sqlite3.Connection,
    table_name: str,
    number_column: str,
    company_id: int,
    document_number: str,
) -> bool:
    row = connection.execute(
        f"""
        SELECT 1
        FROM {TARGET_SCHEMA}.{table_name}
        WHERE company_id = ?
          AND {number_column} = ?
        LIMIT 1
        """,
        (company_id, document_number),
    ).fetchone()
    return row is not None


def _resolve_document_number(
    connection: sqlite3.Connection,
    table_name: str,
    number_column: str,
    company_id: int,
    document_number: str,
) -> str:
    candidate = f"{document_number}{TRANSFER_SUFFIX}"
    counter = 1
    while _document_number_exists(connection, table_name, number_column, company_id, candidate):
        counter += 1
        candidate = f"{document_number}{TRANSFER_SUFFIX}{counter}"
    return candidate


def _unique_sync_barcode(
    connection: sqlite3.Connection,
    company_id: int,
    barcode: str,
) -> str:
    candidate = f"{barcode}{SYNC_SUFFIX}"
    counter = 1
    while connection.execute(
        f"""
        SELECT 1
        FROM {TARGET_SCHEMA}.products
        WHERE company_id = ?
          AND barcode = ?
        LIMIT 1
        """,
        (company_id, candidate),
    ).fetchone():
        counter += 1
        candidate = f"{barcode}{SYNC_SUFFIX}{counter}"
    return candidate
