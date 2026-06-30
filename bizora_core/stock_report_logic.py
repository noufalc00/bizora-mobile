"""
Stock Report Logic Module
Handles stock report business logic and calculations.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class StockReportLogic:
    """Business logic for stock report operations."""

    def __init__(self, db):
        """Initialize stock report logic with database instance."""
        self.db = db

    def search_products(self, company_id: int, search_text: str, limit: int = 100) -> Dict[str, Any]:
        """
        Search products by name or barcode with result limit.
        Safe for very large product catalogs.

        Returns:
            Dict with success status, message, and data
        """
        try:
            if not search_text or len(search_text.strip()) < 1:
                return {
                    "success": True,
                    "message": "Search term too short",
                    "data": []
                }

            products = self.db.search_products_limited(company_id, search_text, limit)
            return {
                "success": True,
                "message": "Products searched successfully",
                "data": products
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to search products: {str(e)}",
                "data": []
            }

    def get_stock_summary(self, company_id: int, filters: Dict[str, Any] = None,
                         limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Get product-wise stock summary with pagination.
        Returns opening, inward, outward, closing stock per product.

        Returns:
            Dict with success status, message, data, and total_count
        """
        try:
            filters = filters or {}
            date_from = filters.get('date_from')
            date_to = filters.get('date_to')
            category = filters.get('category')
            search_text = filters.get('search_text')
            stock_status = filters.get('stock_status')

            # Get total count for pagination
            total_count = self.db.get_stock_summary_count(company_id, filters)

            # Get paginated results
            summary_data = self.db.get_stock_summary(
                company_id, filters, limit, offset
            )

            # Filter by stock status if specified
            if stock_status and stock_status != 'All':
                summary_data = self._filter_by_stock_status(summary_data, stock_status)

            return {
                "success": True,
                "message": "Stock summary retrieved successfully",
                "data": summary_data,
                "total_count": total_count
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve stock summary: {str(e)}",
                "data": [],
                "total_count": 0
            }

    def _filter_by_stock_status(self, data: List[Dict], status: str) -> List[Dict]:
        """Filter stock data by status."""
        filtered = []
        for item in data:
            closing_qty = item.get('closing_qty', 0)
            reorder_level = item.get('reorder_level', 0)

            if status == 'In Stock' and closing_qty > 0:
                filtered.append(item)
            elif status == 'Low Stock' and closing_qty > 0 and closing_qty <= reorder_level:
                filtered.append(item)
            elif status == 'Negative Stock' and closing_qty < 0:
                filtered.append(item)
            elif status == 'Zero Stock' and closing_qty == 0:
                filtered.append(item)

        return filtered

    def get_stock_ledger(self, company_id: int, product_id: int,
                        date_from: str = None, date_to: str = None,
                        limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        Get movement-wise stock ledger for a specific product.
        Returns detailed stock movements with running balance calculation.

        Returns:
            Dict with success status, message, data, and total_count
        """
        try:
            # Get total count for pagination
            total_count = self.db.get_stock_ledger_count(
                company_id, product_id, date_from, date_to
            )

            # Get paginated results
            ledger_data = self.db.get_stock_ledger(
                company_id, product_id, date_from, date_to, limit, offset
            )

            # Calculate running balance
            ledger_data = self._calculate_running_balance(ledger_data, company_id, product_id, date_from)

            return {
                "success": True,
                "message": "Stock ledger retrieved successfully",
                "data": ledger_data,
                "total_count": total_count
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve stock ledger: {str(e)}",
                "data": [],
                "total_count": 0
            }

    def _calculate_running_balance(self, ledger_data: List[Dict], company_id: int,
                                   product_id: int, date_from: str = None) -> List[Dict]:
        """
        Calculate running balance for stock ledger.
        Opening balance is calculated from movements before date_from.
        """
        try:
            # Get opening balance before date_from using signed movement quantity.
            opening_balance = self._get_opening_balance(company_id, product_id, date_from)
            
            balance_qty = opening_balance
            balance_value = 0.0  # Will be calculated from rates

            for item in ledger_data:
                qty_in = item.get('qty_in', 0)
                qty_out = item.get('qty_out', 0)
                rate = item.get('rate', 0)

                # Update balance quantity
                balance_qty += qty_in - qty_out

                # Update balance value (simple rate-based calculation)
                if qty_in > 0:
                    balance_value += qty_in * rate
                if qty_out > 0:
                    balance_value -= qty_out * rate

                item['balance_qty'] = balance_qty
                item['balance_value'] = balance_value

            return ledger_data
        except Exception as e:
            print(f"Error calculating running balance: {e}")
            return ledger_data

    def _get_opening_balance(self, company_id: int, product_id: int, date_from: str = None) -> float:
        """Return signed opening stock before date_from, excluding draft documents."""
        try:
            if not date_from:
                return 0.0
            ph = self.db._get_placeholder()
            query = f"""
                SELECT COALESCE(SUM(quantity), 0) AS balance
                FROM stock_movements
                WHERE company_id = {ph}
                  AND product_id = {ph}
                  AND DATE(COALESCE(movement_date, created_at)) < DATE({ph})
                  AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
            """
            result = self.db.execute_query(query, (company_id, product_id, date_from))
            return float(result[0]['balance']) if result and result[0]['balance'] else 0.0
        except Exception as e:
            print(f"Error calculating opening balance: {e}")
            return 0.0

    def get_negative_stock(self, company_id: int, filters: Dict[str, Any] = None,
                         limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        List products with stock below 0.

        Returns:
            Dict with success status, message, data, and total_count
        """
        try:
            filters = filters or {}
            total_count = self.db.get_negative_stock_count(company_id, filters)
            data = self.db.get_negative_stock(company_id, filters, limit, offset)

            return {
                "success": True,
                "message": "Negative stock retrieved successfully",
                "data": data,
                "total_count": total_count
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve negative stock: {str(e)}",
                "data": [],
                "total_count": 0
            }

    def get_low_stock(self, company_id: int, filters: Dict[str, Any] = None,
                     limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        List products below reorder/minimum level.

        Returns:
            Dict with success status, message, data, and total_count
        """
        try:
            filters = filters or {}
            total_count = self.db.get_low_stock_count(company_id, filters)
            data = self.db.get_low_stock(company_id, filters, limit, offset)

            return {
                "success": True,
                "message": "Low stock retrieved successfully",
                "data": data,
                "total_count": total_count
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve low stock: {str(e)}",
                "data": [],
                "total_count": 0
            }

    def get_zero_stock(self, company_id: int, filters: Dict[str, Any] = None,
                      limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """
        List products with zero closing stock.

        Returns:
            Dict with success status, message, data, and total_count
        """
        try:
            filters = filters or {}
            total_count = self.db.get_zero_stock_count(company_id, filters)
            data = self.db.get_zero_stock(company_id, filters, limit, offset)

            return {
                "success": True,
                "message": "Zero stock retrieved successfully",
                "data": data,
                "total_count": total_count
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve zero stock: {str(e)}",
                "data": [],
                "total_count": 0
            }

    def get_fast_moving_products(self, company_id: int, date_from: str, date_to: str,
                                limit: int = 50) -> Dict[str, Any]:
        """
        List fast-moving products based on sales volume.
        Future-ready method.

        Returns:
            Dict with success status, message, and data
        """
        try:
            data = self.db.get_fast_moving_products(company_id, date_from, date_to, limit)
            return {
                "success": True,
                "message": "Fast moving products retrieved successfully",
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve fast moving products: {str(e)}",
                "data": []
            }

    def get_slow_moving_products(self, company_id: int, date_from: str, date_to: str,
                                limit: int = 50) -> Dict[str, Any]:
        """
        List slow-moving products based on sales volume.
        Future-ready method.

        Returns:
            Dict with success status, message, and data
        """
        try:
            data = self.db.get_slow_moving_products(company_id, date_from, date_to, limit)
            return {
                "success": True,
                "message": "Slow moving products retrieved successfully",
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve slow moving products: {str(e)}",
                "data": []
            }

    def get_stock_value(self, company_id: int, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get total stock valuation.

        Returns:
            Dict with success status, message, and stock value
        """
        try:
            filters = filters or {}
            stock_value = self.db.get_stock_value(company_id, filters)
            return {
                "success": True,
                "message": "Stock value retrieved successfully",
                "data": stock_value
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve stock value: {str(e)}",
                "data": 0.0
            }

    def get_stock_summary_stats(self, company_id: int, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get summary statistics for stock report dashboard.
        Returns total products, total qty, total value, negative count, zero count.

        Returns:
            Dict with success status, message, and stats
        """
        try:
            filters = filters or {}
            stats = self.db.get_stock_summary_stats(company_id, filters)
            return {
                "success": True,
                "message": "Stock summary stats retrieved successfully",
                "data": stats
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve stock summary stats: {str(e)}",
                "data": {}
            }

    def rebuild_stock_balances(self, company_id: int) -> Dict[str, Any]:
        """
        Audit/support method to rebuild stock balances from movements.
        This recalculates balance_qty and balance_value for all movements.

        Returns:
            Dict with success status and message
        """
        try:
            self.db.rebuild_stock_balances(company_id)
            return {
                "success": True,
                "message": "Stock balances rebuilt successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to rebuild stock balances: {str(e)}"
            }

    def export_stock_report_excel(self, company_id: int, report_type: str,
                                   filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Export stock report to Excel format.
        
        Returns:
            Dict with success status, message, and file path
        """
        try:
            # Placeholder for Excel export implementation
            # Will use openpyxl if available
            return {
                "success": False,
                "message": "Excel export not yet implemented. Requires openpyxl library.",
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to export to Excel: {str(e)}",
                "data": None
            }

    def export_stock_report_pdf(self, company_id: int, report_type: str,
                                filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Export stock report to PDF format.
        
        Returns:
            Dict with success status, message, and file path
        """
        try:
            # Placeholder for PDF export implementation
            # Will use reportlab if available
            return {
                "success": False,
                "message": "PDF export not yet implemented. Requires reportlab library.",
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to export to PDF: {str(e)}",
                "data": None
            }
