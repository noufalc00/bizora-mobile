"""
Sales Wise Profit Book Logic Module
Handles profit calculations for Bill-wise, Party-wise, and Item-wise reports.
Uses historical cost snapshot captured at time of sale (NOT current stock cost).
"""

from typing import Optional, List, Dict, Any
from decimal import Decimal


class SalesProfitBookLogic:
    """Business logic for Sales Wise Profit Book reports."""

    def __init__(self, db):
        """Initialize profit book logic with database instance."""
        self.db = db

    def _parse_tax_filter(self, value: Any) -> Optional[float]:
        """Return a numeric GST filter from combo data or ignore blank values."""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip()
        if not text or text.lower() in ("all gst", "all tax", "all"):
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _sales_value_expr(self, alias: str = "si") -> str:
        """Return net item sales value after item discount, excluding tax."""
        return (
            f"COALESCE({alias}.net_value, "
            f"(COALESCE({alias}.rate, 0) * COALESCE({alias}.quantity, 0)) "
            f"- COALESCE({alias}.discount, 0))"
        )

    def _cost_value_expr(self, item_alias: str = "si", product_alias: str = "pr") -> str:
        """Return historical item cost with purchase-rate fallback for old rows."""
        return (
            "CASE "
            f"WHEN COALESCE({item_alias}.cost_value, 0) <> 0 "
            f"THEN COALESCE({item_alias}.cost_value, 0) "
            f"ELSE COALESCE({item_alias}.cost_price, {product_alias}.purchase_rate, 0) "
            f"* COALESCE({item_alias}.quantity, 0) "
            "END"
        )

    def _build_where(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        filters: Dict[str, Any],
    ) -> tuple[str, List[Any]]:
        """Build shared profit-report filters with parameterized inputs."""
        ph = self.db._get_placeholder()
        where_clauses = [f"s.company_id = {ph}"]
        params: List[Any] = [company_id]

        if from_date:
            where_clauses.append(f"s.invoice_date >= {ph}")
            params.append(from_date)
        if to_date:
            where_clauses.append(f"s.invoice_date <= {ph}")
            params.append(to_date)

        party_filter = str(filters.get("party") or "").strip()
        if party_filter and party_filter.lower() != "all parties":
            where_clauses.append(f"p.name LIKE {ph}")
            params.append(f"%{party_filter}%")

        product_filter = str(filters.get("product") or "").strip()
        barcode_filter = str(filters.get("barcode") or "").strip()
        if product_filter:
            where_clauses.append(f"pr.name LIKE {ph}")
            params.append(f"%{product_filter}%")
        if barcode_filter:
            where_clauses.append(f"pr.barcode LIKE {ph}")
            params.append(f"%{barcode_filter}%")

        tax_rate = self._parse_tax_filter(filters.get("tax_rate"))
        if tax_rate is not None:
            where_clauses.append(f"COALESCE(si.tax_percent, 0) = {ph}")
            params.append(tax_rate)

        search_filter = str(filters.get("search") or "").strip()
        if search_filter:
            where_clauses.append(
                f"(s.invoice_number LIKE {ph} OR p.name LIKE {ph} "
                f"OR pr.name LIKE {ph} OR pr.barcode LIKE {ph})"
            )
            like_value = f"%{search_filter}%"
            params.extend([like_value, like_value, like_value, like_value])

        return " AND ".join(where_clauses), params

    def _finalize_profit_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate net profit and margin percentage for fetched rows."""
        for row in rows:
            sales_value = Decimal(str(row.get("sales_value") or 0))
            cost_value = Decimal(str(row.get("cost_value") or 0))
            profit = sales_value - cost_value
            margin_percent = (profit / sales_value) * Decimal("100") if sales_value else Decimal("0")
            row["profit"] = float(profit)
            row["margin_percent"] = float(margin_percent)
        return rows

    def get_bill_wise(self, company_id: int, from_date: str, to_date: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get Bill-wise profit report (invoice-level profit).

        Args:
            company_id: Company ID
            from_date: Start date
            to_date: End date
            filters: Dictionary with filters (party, product, tax_rate, search)

        Returns:
            Dictionary with success flag and data list
        """
        filters = filters or {}
        where_clause, params = self._build_where(company_id, from_date, to_date, filters)
        sales_expr = self._sales_value_expr("si")
        cost_expr = self._cost_value_expr("si", "pr")
        query = f"""
            SELECT
                s.invoice_date,
                s.invoice_number,
                p.name as party_name,
                s.id as sale_id,
                SUM({sales_expr}) as sales_value,
                SUM({cost_expr}) as cost_value
            FROM sales s
            JOIN sales_items si ON s.id = si.sale_id
            JOIN parties p ON s.party_id = p.id
            LEFT JOIN products pr ON si.product_id = pr.id
            WHERE {where_clause}
            GROUP BY s.id, s.invoice_date, s.invoice_number, p.name
            ORDER BY s.invoice_date DESC, s.id DESC
        """
        results = self.db.execute_query(query, tuple(params))
        return {"success": True, "data": self._finalize_profit_rows(results)}

    def get_party_wise(self, company_id: int, from_date: str, to_date: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get Party-wise profit report (individual bills per party).

        Args:
            company_id: Company ID
            from_date: Start date
            to_date: End date
            filters: Dictionary with filters (party, product, tax_rate, search)

        Returns:
            Dictionary with success flag and data list
        """
        filters = filters or {}
        where_clause, params = self._build_where(company_id, from_date, to_date, filters)
        sales_expr = self._sales_value_expr("si")
        cost_expr = self._cost_value_expr("si", "pr")
        query = f"""
            SELECT
                s.invoice_date,
                s.invoice_number,
                p.name as party_name,
                s.id as sale_id,
                SUM({sales_expr}) as sales_value,
                SUM({cost_expr}) as cost_value
            FROM sales s
            JOIN sales_items si ON s.id = si.sale_id
            JOIN parties p ON s.party_id = p.id
            LEFT JOIN products pr ON si.product_id = pr.id
            WHERE {where_clause}
            GROUP BY s.id, s.invoice_date, s.invoice_number, p.name
            ORDER BY p.name, s.invoice_date DESC, s.id DESC
        """
        results = self.db.execute_query(query, tuple(params))
        return {"success": True, "data": self._finalize_profit_rows(results)}

    def get_item_wise(self, company_id: int, from_date: str, to_date: str, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get Item-wise profit report (individual bills per product).

        Args:
            company_id: Company ID
            from_date: Start date
            to_date: End date
            filters: Dictionary with filters (party, product, tax_rate, search)

        Returns:
            Dictionary with success flag and data list
        """
        filters = filters or {}
        where_clause, params = self._build_where(company_id, from_date, to_date, filters)
        sales_expr = self._sales_value_expr("si")
        cost_expr = self._cost_value_expr("si", "pr")
        query = f"""
            SELECT
                s.invoice_date,
                s.invoice_number,
                pr.name as product_name,
                s.id as sale_id,
                SUM(si.quantity) as qty_sold,
                SUM({sales_expr}) as sales_value,
                SUM({cost_expr}) as cost_value
            FROM sales_items si
            JOIN sales s ON si.sale_id = s.id
            JOIN products pr ON si.product_id = pr.id
            LEFT JOIN parties p ON s.party_id = p.id
            WHERE {where_clause}
            GROUP BY s.id, s.invoice_date, s.invoice_number, pr.id, pr.name
            ORDER BY pr.name, s.invoice_date DESC, s.id DESC
        """
        results = self.db.execute_query(query, tuple(params))
        return {"success": True, "data": self._finalize_profit_rows(results)}

    def get_party_choices(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Get party choices for filter dropdown.

        Args:
            company_id: Company ID

        Returns:
            List of party dictionaries
        """
        parties = self.db.get_parties_by_company(company_id)
        return parties

    def get_product_choices(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Get product choices for filter dropdown.

        Args:
            company_id: Company ID

        Returns:
            List of product dictionaries
        """
        products = self.db.get_products_by_company(company_id)
        return products
