"""
Shared logic for Sales Book, Sales Return Book, Purchase Book, and Purchase Return Book.

This module contains read-only report queries only. It does not modify vouchers.
All SQL uses Database._get_placeholder for SQLite and future MySQL compatibility.
"""

import re
from typing import Any, Dict, List, Optional

from config import active_company_manager
from db import Database


def safe_float(value: Any) -> float:
    """Convert common database values to float safely."""
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def resolve_active_company_id(db: Database) -> Optional[int]:
    """Return only the company explicitly opened in this app session."""
    company_id = active_company_manager.get_active_company_id()
    return int(company_id) if company_id else None


class VoucherBookLogic:
    """Generic voucher book report logic configured by module-specific metadata."""

    def __init__(self, db: Optional[Database], config: Dict[str, Any]):
        self.db = db or Database()
        self.config = config

    def _ok(self, data: List[Dict[str, Any]], message: str = "") -> Dict[str, Any]:
        return {"success": True, "data": data, "message": message}

    def _fail(self, message: str) -> Dict[str, Any]:
        return {"success": False, "data": [], "message": message}

    def _ph(self) -> str:
        return self.db._get_placeholder()

    def _date_where(self, alias: str, from_date: str, to_date: str) -> str:
        date_col = self.config["date_col"]
        ph = self._ph()
        return f"DATE({alias}.{date_col}) >= DATE({ph}) AND DATE({alias}.{date_col}) <= DATE({ph})"

    def _table_columns(self, table_name: str) -> set:
        """Return column names for a table without raising on missing tables."""
        try:
            rows = self.db.execute_query(f"PRAGMA table_info({table_name})")
            return {row.get('name') for row in rows}
        except Exception:
            return set()

    def _item_tax_rate_col(self, tax_name: str) -> Optional[str]:
        """Return the tax rate column for GST filtering and display."""
        table_name = self.config["item_table"]
        cols = self._table_columns(table_name)
        percent_col = f"{tax_name}_percent"
        if percent_col in cols:
            return percent_col
        if tax_name in cols:
            return tax_name
        return None

    def _item_tax_rate_expr(self, alias: str, tax_name: str) -> str:
        """Return an SQL expression for a split GST rate, excluding cess."""
        col = self._item_tax_rate_col(tax_name)
        return f"COALESCE({alias}.{col}, 0)" if col else "0"

    def _item_taxable_expr(self, alias: str) -> str:
        """Return taxable value as rate times quantity minus item discount."""
        return (
            f"COALESCE({alias}.net_value, "
            f"(COALESCE({alias}.rate, 0) * COALESCE({alias}.quantity, 0)) "
            f"- COALESCE({alias}.discount, 0))"
        )

    def _item_tax_expr(self, alias: str, tax_name: str) -> str:
        """Return an SQL expression for split tax amount in currency."""
        table_name = self.config["item_table"]
        amount_col = f"{tax_name}_amount"
        cols = self._table_columns(table_name)
        if amount_col in cols:
            return f"COALESCE({alias}.{amount_col}, 0)"
        rate_col = self._item_tax_rate_col(tax_name)
        if rate_col:
            taxable_expr = self._item_taxable_expr(alias)
            return f"(({taxable_expr}) * COALESCE({alias}.{rate_col}, 0) / 100.0)"
        return "0"

    def _item_total_tax_expr(self, alias: str) -> str:
        """Return total item tax amount from split GST and cess amounts."""
        parts = [
            self._item_tax_expr(alias, "cgst"),
            self._item_tax_expr(alias, "sgst"),
            self._item_tax_expr(alias, "igst"),
            self._item_tax_expr(alias, "cess"),
        ]
        return "(" + " + ".join(parts) + ")"

    def _item_grand_total_expr(self, alias: str) -> str:
        """Return item gross total as taxable value plus tax amount."""
        return f"({self._item_taxable_expr(alias)} + {self._item_total_tax_expr(alias)})"

    def _item_totals_subquery(self, where_sql: str = "") -> str:
        """Return an item aggregation subquery used by bill and party reports."""
        c = self.config
        taxable_expr = self._item_taxable_expr("i")
        tax_expr = self._item_total_tax_expr("i")
        grand_expr = self._item_grand_total_expr("i")
        return f"""
            SELECT
                i.{c["item_fk"]} AS voucher_id,
                SUM({taxable_expr}) AS taxable_amount,
                SUM(COALESCE(i.discount, 0)) AS discount_total,
                SUM({self._item_tax_expr("i", "cgst")}) AS cgst_amount,
                SUM({self._item_tax_expr("i", "sgst")}) AS sgst_amount,
                SUM({self._item_tax_expr("i", "igst")}) AS igst_amount,
                SUM({self._item_tax_expr("i", "cess")}) AS cess_amount,
                SUM({tax_expr}) AS tax_total,
                SUM({grand_expr}) AS grand_total,
                COUNT(*) AS item_count
            FROM {c["item_table"]} i
            LEFT JOIN products pr ON pr.id = i.product_id
            WHERE 1 = 1
              {where_sql}
            GROUP BY i.{c["item_fk"]}
        """

    def _parse_tax_filter(self, value: Any) -> Optional[float]:
        """Extract a GST rate from combo data or descriptive combo text."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip()
        if not text or text.lower() in ("all", "all tax", "all gst"):
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else None

    def _gst_filter_condition(self, alias: str, tax_value: float) -> tuple[str, List[Any]]:
        """Build split-aware GST filtering for IGST full rate or CGST/SGST halves."""
        ph = self._ph()
        igst_expr = self._item_tax_rate_expr(alias, "igst")
        cgst_expr = self._item_tax_rate_expr(alias, "cgst")
        sgst_expr = self._item_tax_rate_expr(alias, "sgst")
        total_expr = f"COALESCE({alias}.tax_percent, 0)"
        if tax_value == 0:
            condition = (
                f"({total_expr} = {ph} "
                f"AND {igst_expr} = {ph} "
                f"AND {cgst_expr} = {ph} "
                f"AND {sgst_expr} = {ph})"
            )
            return condition, [0.0, 0.0, 0.0, 0.0]

        half_value = tax_value / 2.0
        condition = (
            f"(({igst_expr} = {ph}) "
            f"OR ({cgst_expr} = {ph} AND {sgst_expr} = {ph}) "
            f"OR ({total_expr} = {ph}))"
        )
        return condition, [tax_value, half_value, half_value, tax_value]

    def _base_header_select(self, totals_alias: Optional[str] = None) -> str:
        c = self.config
        settled_col = c.get("settled_col")
        settled_sql = f"COALESCE(v.{settled_col}, 0)" if settled_col else "0"
        if totals_alias:
            taxable_sql = f"COALESCE({totals_alias}.taxable_amount, 0)"
            discount_sql = f"COALESCE({totals_alias}.discount_total, 0)"
            tax_sql = f"COALESCE({totals_alias}.tax_total, 0)"
            grand_sql = f"COALESCE({totals_alias}.grand_total, 0)"
        else:
            taxable_sql = "COALESCE(v.sub_total, 0)"
            discount_sql = "COALESCE(v.discount_total, 0)"
            tax_sql = "COALESCE(v.tax_total, 0)"
            grand_sql = "COALESCE(v.grand_total, 0)"
        return f"""
            v.id AS voucher_id,
            '{c["voucher_type"]}' AS voucher_type,
            v.{c["number_col"]} AS voucher_no,
            v.{c["date_col"]} AS voucher_date,
            COALESCE(p.name, '') AS party_name,
            p.id AS party_id,
            COALESCE(v.{c.get("type_col", c["number_col"])}, '') AS voucher_subtype,
            COALESCE(v.nature, '') AS nature,
            {taxable_sql} AS taxable_amount,
            {discount_sql} AS discount_total,
            {tax_sql} AS tax_total,
            COALESCE(v.round_off, 0) AS round_off,
            {grand_sql} AS grand_total,
            {settled_sql} AS settled_amount,
            {grand_sql} - {settled_sql} AS balance_amount
        """

    def get_party_choices(self, company_id: int) -> List[Dict[str, Any]]:
        """Return party names for completers and filters."""
        ph = self._ph()
        party_types = self.config.get("party_types", [])
        params: List[Any] = [company_id]

        type_sql = ""
        if party_types:
            marks = ", ".join([ph] * len(party_types))
            type_sql = f" AND party_type IN ({marks})"
            params.extend(party_types)

        query = f"""
            SELECT id, name, party_type
            FROM parties
            WHERE company_id = {ph}
            {type_sql}
            ORDER BY LOWER(name)
        """
        return self.db.execute_query(query, tuple(params))

    def get_product_choices(self, company_id: int) -> List[Dict[str, Any]]:
        ph = self._ph()
        query = f"""
            SELECT id, name, barcode, category
            FROM products
            WHERE company_id = {ph}
            ORDER BY LOWER(name)
        """
        return self.db.execute_query(query, (company_id,))

    def get_category_choices(self, company_id: int) -> List[str]:
        """Return distinct product category names for report filter completers."""
        ph = self._ph()
        query = f"""
            SELECT DISTINCT COALESCE(category, '') AS category
            FROM products
            WHERE company_id = {ph}
              AND TRIM(COALESCE(category, '')) <> ''
            ORDER BY LOWER(category)
        """
        rows = self.db.execute_query(query, (company_id,))
        categories: List[str] = []
        for row in rows:
            name = str(row.get("category", "") or "").strip()
            if name:
                categories.append(name)
        return categories

    def _filter_sql(self, filters: Optional[Dict[str, Any]], include_product: bool = False) -> tuple[str, List[Any]]:
        filters = filters or {}
        ph = self._ph()
        clauses: List[str] = []
        params: List[Any] = []

        party_text = str(filters.get("party", "") or "").strip()
        if party_text and party_text.lower() not in ("all", "all parties"):
            clauses.append("LOWER(COALESCE(p.name, '')) LIKE LOWER(" + ph + ")")
            params.append(f"%{party_text}%")

        search_text = str(filters.get("search", "") or "").strip()
        if search_text:
            search_parts = [
                "LOWER(COALESCE(v." + self.config["number_col"] + ", '')) LIKE LOWER(" + ph + ")",
                "LOWER(COALESCE(p.name, '')) LIKE LOWER(" + ph + ")",
                "LOWER(COALESCE(v.narration, '')) LIKE LOWER(" + ph + ")",
            ]
            params.extend([f"%{search_text}%"] * 3)
            if include_product:
                search_parts.append("LOWER(COALESCE(pr.name, '')) LIKE LOWER(" + ph + ")")
                search_parts.append("LOWER(COALESCE(pr.barcode, '')) LIKE LOWER(" + ph + ")")
                params.extend([f"%{search_text}%"] * 2)
            clauses.append("(" + " OR ".join(search_parts) + ")")

        product_text = str(filters.get("product", "") or "").strip()
        if include_product and product_text:
            clauses.append("(LOWER(COALESCE(pr.name, '')) LIKE LOWER(" + ph + ") OR LOWER(COALESCE(pr.barcode, '')) LIKE LOWER(" + ph + "))")
            params.extend([f"%{product_text}%", f"%{product_text}%"])

        barcode_text = str(filters.get("barcode", "") or "").strip()
        if include_product and barcode_text:
            clauses.append("LOWER(COALESCE(pr.barcode, '')) LIKE LOWER(" + ph + ")")
            params.append(f"%{barcode_text}%")

        tax_value = self._parse_tax_filter(filters.get("tax_rate"))
        if include_product and tax_value is not None:
            condition, tax_params = self._gst_filter_condition("i", tax_value)
            clauses.append(condition)
            params.extend(tax_params)

        category_text = str(filters.get("category", "") or "").strip()
        if include_product and category_text and category_text.lower() not in (
            "all",
            "all categories",
        ):
            clauses.append("LOWER(COALESCE(pr.category, '')) LIKE LOWER(" + ph + ")")
            params.append(f"%{category_text}%")

        if not clauses:
            return "", params

        return " AND " + " AND ".join(clauses), params

    def _item_filter_sql(self, filters: Optional[Dict[str, Any]]) -> tuple[str, List[Any]]:
        """Return item-only filters safe for use inside aggregation subqueries."""
        filters = filters or {}
        item_filters = {
            "barcode": filters.get("barcode"),
            "product": filters.get("product"),
            "tax_rate": filters.get("tax_rate"),
            "category": filters.get("category"),
        }
        return self._filter_sql(item_filters, include_product=True)

    def get_bill_wise(self, company_id: int, from_date: str, to_date: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        c = self.config
        ph = self._ph()
        extra_sql, extra_params = self._filter_sql(filters, include_product=False)
        item_filter_sql, item_filter_params = self._item_filter_sql(filters)
        query = f"""
            SELECT
                {self._base_header_select("item_totals")},
                COALESCE(item_totals.cgst_amount, 0) AS cgst_amount,
                COALESCE(item_totals.sgst_amount, 0) AS sgst_amount,
                COALESCE(item_totals.igst_amount, 0) AS igst_amount,
                COALESCE(item_totals.cess_amount, 0) AS cess_amount,
                COALESCE(item_totals.item_count, 0) AS item_count
            FROM {c["header_table"]} v
            LEFT JOIN parties p ON p.id = v.{c["party_col"]}
            JOIN (
                {self._item_totals_subquery(item_filter_sql)}
            ) item_totals ON item_totals.voucher_id = v.id
            WHERE v.company_id = {ph}
              AND {self._date_where("v", from_date, to_date)}
              {extra_sql}
            ORDER BY DATE(v.{c["date_col"]}), v.id
        """
        params = item_filter_params + [company_id, from_date, to_date] + extra_params
        return self._ok(self.db.execute_query(query, tuple(params)))

    def get_item_wise(self, company_id: int, from_date: str, to_date: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        c = self.config
        ph = self._ph()
        extra_sql, extra_params = self._filter_sql(filters, include_product=True)
        query = f"""
            SELECT
                v.id AS voucher_id,
                '{c["voucher_type"]}' AS voucher_type,
                v.{c["number_col"]} AS voucher_no,
                v.{c["date_col"]} AS voucher_date,
                COALESCE(p.name, '') AS party_name,
                p.id AS party_id,
                i.product_id,
                COALESCE(pr.name, '') AS product_name,
                COALESCE(pr.barcode, '') AS barcode,
                COALESCE(i.hsn, pr.hsn, '') AS hsn,
                COALESCE(i.quantity, 0) AS quantity,
                COALESCE(i.rate, 0) AS rate,
                COALESCE(i.gross_value, 0) AS gross_value,
                COALESCE(i.discount, 0) AS discount,
                {self._item_taxable_expr("i")} AS taxable_amount,
                COALESCE(i.tax_percent, 0) AS tax_percent,
                COALESCE(i.cgst, 0) AS cgst,
                COALESCE(i.sgst, 0) AS sgst,
                COALESCE(i.igst, 0) AS igst,
                COALESCE(i.cess, 0) AS cess,
                {self._item_tax_expr("i", "cgst")} AS cgst_amount,
                {self._item_tax_expr("i", "sgst")} AS sgst_amount,
                {self._item_tax_expr("i", "igst")} AS igst_amount,
                {self._item_tax_expr("i", "cess")} AS cess_amount,
                {self._item_total_tax_expr("i")} AS tax_amount,
                {self._item_grand_total_expr("i")} AS grand_total
            FROM {c["header_table"]} v
            JOIN {c["item_table"]} i ON i.{c["item_fk"]} = v.id
            LEFT JOIN parties p ON p.id = v.{c["party_col"]}
            LEFT JOIN products pr ON pr.id = i.product_id
            WHERE v.company_id = {ph}
              AND {self._date_where("v", from_date, to_date)}
              {extra_sql}
            ORDER BY DATE(v.{c["date_col"]}), v.id, i.sl_no
        """
        params = [company_id, from_date, to_date] + extra_params
        return self._ok(self.db.execute_query(query, tuple(params)))

    def get_tax_wise(self, company_id: int, from_date: str, to_date: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.get_item_wise(company_id, from_date, to_date, filters)

    def get_tax_summary(self, company_id: int, from_date: str, to_date: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        c = self.config
        ph = self._ph()
        extra_sql, extra_params = self._filter_sql(filters, include_product=True)
        query = f"""
            SELECT
                '{c["voucher_type"]}' AS voucher_type,
                COALESCE(i.tax_percent, 0) AS tax_percent,
                COALESCE(i.cgst, 0) AS cgst,
                COALESCE(i.sgst, 0) AS sgst,
                COALESCE(i.igst, 0) AS igst,
                COALESCE(i.cess, 0) AS cess,
                COALESCE(v.nature, '') AS nature,
                COUNT(DISTINCT v.id) AS bill_count,
                SUM({self._item_taxable_expr("i")}) AS taxable_amount,
                SUM({self._item_tax_expr("i", "cgst")}) AS cgst_amount,
                SUM({self._item_tax_expr("i", "sgst")}) AS sgst_amount,
                SUM({self._item_tax_expr("i", "igst")}) AS igst_amount,
                SUM({self._item_tax_expr("i", "cess")}) AS cess_amount,
                SUM({self._item_total_tax_expr("i")}) AS tax_amount,
                SUM({self._item_grand_total_expr("i")}) AS grand_total
            FROM {c["header_table"]} v
            JOIN {c["item_table"]} i ON i.{c["item_fk"]} = v.id
            LEFT JOIN parties p ON p.id = v.{c["party_col"]}
            LEFT JOIN products pr ON pr.id = i.product_id
            WHERE v.company_id = {ph}
              AND {self._date_where("v", from_date, to_date)}
              {extra_sql}
            GROUP BY
                COALESCE(i.tax_percent, 0),
                COALESCE(i.cgst, 0),
                COALESCE(i.sgst, 0),
                COALESCE(i.igst, 0),
                COALESCE(i.cess, 0),
                COALESCE(v.nature, '')
            ORDER BY
                COALESCE(i.cgst, 0),
                COALESCE(i.sgst, 0),
                COALESCE(i.igst, 0),
                COALESCE(i.cess, 0),
                COALESCE(v.nature, '')
        """
        params = [company_id, from_date, to_date] + extra_params
        return self._ok(self.db.execute_query(query, tuple(params)))

    def get_credit_or_pending(self, company_id: int, from_date: str, to_date: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        c = self.config
        type_col = c.get("type_col")
        if not type_col:
            return self.get_bill_wise(company_id, from_date, to_date, filters)

        ph = self._ph()
        extra_sql, extra_params = self._filter_sql(filters, include_product=False)
        item_filter_sql, item_filter_params = self._item_filter_sql(filters)
        settled_col = c.get("settled_col")
        settled_sql = f"COALESCE(v.{settled_col}, 0)" if settled_col else "0"
        query = f"""
            SELECT
                {self._base_header_select("item_totals")},
                COALESCE(v.due_date, '') AS due_date,
                CASE
                    WHEN COALESCE(item_totals.grand_total, 0) - {settled_sql} > 0 THEN 'Pending'
                    ELSE 'Cleared'
                END AS status
            FROM {c["header_table"]} v
            LEFT JOIN parties p ON p.id = v.{c["party_col"]}
            JOIN (
                {self._item_totals_subquery(item_filter_sql)}
            ) item_totals ON item_totals.voucher_id = v.id
            WHERE v.company_id = {ph}
              AND {self._date_where("v", from_date, to_date)}
              AND (
                    LOWER(COALESCE(v.{type_col}, '')) LIKE LOWER({ph})
                    OR COALESCE(item_totals.grand_total, 0) - {settled_sql} > 0
                  )
              {extra_sql}
            ORDER BY DATE(v.{c["date_col"]}), v.id
        """
        params = item_filter_params + [company_id, from_date, to_date, "%credit%"] + extra_params
        return self._ok(self.db.execute_query(query, tuple(params)))

    def get_party_wise(self, company_id: int, from_date: str, to_date: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        c = self.config
        ph = self._ph()
        extra_sql, extra_params = self._filter_sql(filters, include_product=False)
        item_filter_sql, item_filter_params = self._item_filter_sql(filters)
        settled_col = c.get("settled_col")
        settled_sql = f"COALESCE(v.{settled_col}, 0)" if settled_col else "0"
        query = f"""
            SELECT
                p.id AS party_id,
                COALESCE(p.name, '') AS party_name,
                COALESCE(p.party_type, '') AS party_type,
                COUNT(v.id) AS bill_count,
                SUM(COALESCE(item_totals.taxable_amount, 0)) AS taxable_amount,
                SUM(COALESCE(item_totals.tax_total, 0)) AS tax_total,
                SUM(COALESCE(item_totals.discount_total, 0)) AS discount_total,
                SUM(COALESCE(item_totals.grand_total, 0)) AS grand_total,
                SUM({settled_sql}) AS settled_amount,
                SUM(COALESCE(item_totals.grand_total, 0) - {settled_sql}) AS balance_amount
            FROM {c["header_table"]} v
            LEFT JOIN parties p ON p.id = v.{c["party_col"]}
            JOIN (
                {self._item_totals_subquery(item_filter_sql)}
            ) item_totals ON item_totals.voucher_id = v.id
            WHERE v.company_id = {ph}
              AND {self._date_where("v", from_date, to_date)}
              {extra_sql}
            GROUP BY p.id, p.name, p.party_type
            ORDER BY LOWER(COALESCE(p.name, ''))
        """
        params = item_filter_params + [company_id, from_date, to_date] + extra_params
        return self._ok(self.db.execute_query(query, tuple(params)))

    def get_category_wise(self, company_id: int, from_date: str, to_date: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return totals grouped by product category (item category type)."""
        c = self.config
        ph = self._ph()
        extra_sql, extra_params = self._filter_sql(filters, include_product=True)
        query = f"""
            SELECT
                COALESCE(pr.category, '') AS category,
                COUNT(DISTINCT v.id) AS bill_count,
                SUM(COALESCE(i.quantity, 0)) AS quantity_total,
                SUM({self._item_taxable_expr("i")}) AS taxable_amount,
                SUM({self._item_total_tax_expr("i")}) AS tax_total,
                SUM(COALESCE(i.discount, 0)) AS discount_total,
                SUM({self._item_grand_total_expr("i")}) AS grand_total
            FROM {c["header_table"]} v
            JOIN {c["item_table"]} i ON i.{c["item_fk"]} = v.id
            LEFT JOIN parties p ON p.id = v.{c["party_col"]}
            LEFT JOIN products pr ON pr.id = i.product_id
            WHERE v.company_id = {ph}
              AND {self._date_where("v", from_date, to_date)}
              {extra_sql}
            GROUP BY COALESCE(pr.category, '')
            ORDER BY LOWER(COALESCE(pr.category, ''))
        """
        params = [company_id, from_date, to_date] + extra_params
        return self._ok(self.db.execute_query(query, tuple(params)))

    def get_bill_detail(self, company_id: int, voucher_id: int) -> Dict[str, Any]:
        c = self.config
        ph = self._ph()
        header_query = f"""
            SELECT
                {self._base_header_select("item_totals")},
                COALESCE(v.narration, '') AS narration,
                COALESCE(v.gstin, '') AS gstin,
                COALESCE(v.state, '') AS state
            FROM {c["header_table"]} v
            LEFT JOIN parties p ON p.id = v.{c["party_col"]}
            JOIN (
                {self._item_totals_subquery()}
            ) item_totals ON item_totals.voucher_id = v.id
            WHERE v.company_id = {ph}
              AND v.id = {ph}
        """
        headers = self.db.execute_query(header_query, (company_id, voucher_id))
        if not headers:
            return {"success": False, "header": {}, "items": [], "message": "Source voucher was not found."}

        item_query = f"""
            SELECT
                i.sl_no,
                COALESCE(pr.name, '') AS product_name,
                COALESCE(pr.barcode, '') AS barcode,
                COALESCE(i.hsn, pr.hsn, '') AS hsn,
                COALESCE(i.quantity, 0) AS quantity,
                COALESCE(i.rate, 0) AS rate,
                COALESCE(i.gross_value, 0) AS gross_value,
                COALESCE(i.discount, 0) AS discount,
                {self._item_taxable_expr("i")} AS taxable_amount,
                COALESCE(i.tax_percent, 0) AS tax_percent,
                {self._item_tax_expr("i", "cgst")} AS cgst_amount,
                {self._item_tax_expr("i", "sgst")} AS sgst_amount,
                {self._item_tax_expr("i", "igst")} AS igst_amount,
                {self._item_tax_expr("i", "cess")} AS cess_amount,
                {self._item_total_tax_expr("i")} AS tax_amount,
                {self._item_grand_total_expr("i")} AS grand_total
            FROM {c["item_table"]} i
            LEFT JOIN products pr ON pr.id = i.product_id
            WHERE i.{c["item_fk"]} = {ph}
            ORDER BY i.sl_no, i.id
        """
        items = self.db.execute_query(item_query, (voucher_id,))
        return {"success": True, "header": headers[0], "items": items, "message": ""}

    def get_summary_detail_rows(self, company_id: int, from_date: str, to_date: str, report_type: str, row_data: Dict[str, Any], filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return supporting rows for double-clicking summary reports."""
        local_filters = dict(filters or {})
        if row_data.get("party_name"):
            local_filters["party"] = row_data.get("party_name")
        if row_data.get("tax_percent") is not None:
            local_filters["tax_rate"] = str(row_data.get("tax_percent"))

        if "Party Wise" in report_type:
            return self.get_bill_wise(company_id, from_date, to_date, local_filters)
        if "Category Wise" in report_type:
            if row_data.get("category") is not None:
                local_filters["category"] = row_data.get("category")
            return self.get_item_wise(company_id, from_date, to_date, local_filters)
        if "Tax Summary" in report_type or report_type.endswith("Tax Summary"):
            return self.get_tax_wise(company_id, from_date, to_date, local_filters)
        return self.get_bill_wise(company_id, from_date, to_date, local_filters)
