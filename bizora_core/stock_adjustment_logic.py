"""
Stock Adjustment Logic Module

Handles business logic for stock adjustment vouchers.
Integrates with centralized stock movement and ledger posting systems.
Uses Decimal for all calculations (not float) for accounting precision.
"""

from decimal import Decimal
from typing import Dict, Any, List, Optional
from db import Database
from bizora_core.stock_logic import StockLogic
from bizora_core.ledger_logic import LedgerLogic


class StockAdjustmentLogic:
    """Business logic for stock adjustment vouchers."""
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize with database connection."""
        self.db = db or Database()
        self.stock_logic = StockLogic(self.db)
        self.ledger_logic = LedgerLogic(self.db)
    
    def save_adjustment(self, header_data: Dict[str, Any], items_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Save a new stock adjustment with atomic transaction safety.
        
        Transaction flow:
        BEGIN → save header → save items → insert stock movements → post ledger → COMMIT
        If ANY step fails: FULL ROLLBACK
        
        Uses Decimal for all calculations.
        """
        from config import active_company_manager
        
        company_id = header_data['company_id']
        qty_only_no_value_effect = bool(header_data.get('qty_only_no_value_effect'))
        
        # Calculate totals using Decimal
        total_increase = Decimal('0')
        total_decrease = Decimal('0')
        
        for item in items_data:
            difference_qty = Decimal(str(item.get('difference_qty', 0)))
            rate = Decimal('0') if qty_only_no_value_effect else Decimal(str(item.get('rate', 0)))
            value = difference_qty * rate
            
            if qty_only_no_value_effect:
                item['rate'] = 0.0
            item['value'] = float(value)  # Store as float in DB, but calculated with Decimal
            
            if difference_qty > 0:
                total_increase += value
            elif difference_qty < 0:
                total_decrease += abs(value)
        
        net_adjustment = total_increase - total_decrease
        
        # Update header with calculated totals
        header_data['total_increase_value'] = float(total_increase)
        header_data['total_decrease_value'] = float(total_decrease)
        header_data['net_adjustment'] = float(net_adjustment)
        
        # BEGIN TRANSACTION
        conn = self.db.connect()
        cursor = conn.cursor()
        
        try:
            # Save header and items
            adjustment_id = self.db.save_stock_adjustment(header_data, items_data)
            
            # Insert stock movements for each item
            for item in items_data:
                product_id = item['product_id']
                difference_qty = Decimal(str(item.get('difference_qty', 0)))
                
                # Movement type: "stock_adjustment" (standardized)
                # Positive difference = stock increase
                # Negative difference = stock decrease
                self.stock_logic.apply_stock_adjustment_movement(
                    company_id=company_id,
                    product_id=product_id,
                    difference_qty=float(difference_qty),
                    adjustment_id=adjustment_id
                )
            
            # Sync product quantity cache
            for item in items_data:
                product_id = item['product_id']
                self.stock_logic.sync_product_quantity_from_movements(product_id)
            
            # Qty-only adjustments deliberately do not post gain/loss valuation entries.
            if not qty_only_no_value_effect:
                self.ledger_logic.post_stock_adjustment_voucher(
                    adjustment_data=header_data,
                    items_data=items_data
                )
            
            conn.commit()
            
            return {
                'success': True,
                'adjustment_id': adjustment_id,
                'message': 'Stock adjustment saved successfully'
            }
            
        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'adjustment_id': None,
                'message': f'Error saving stock adjustment: {str(e)}'
            }
        finally:
            conn.close()
    
    def update_adjustment(self, adjustment_id: int, header_data: Dict[str, Any], items_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Update an existing stock adjustment with safe repost flow.
        
        Safe repost flow:
        1. Reverse old stock movements
        2. Reverse old ledger entries
        3. Delete old items
        4. Insert new items
        5. Repost movements
        6. Repost ledger
        
        Uses Decimal for all calculations.
        """
        from config import active_company_manager
        
        company_id = header_data['company_id']
        qty_only_no_value_effect = bool(header_data.get('qty_only_no_value_effect'))
        
        # Get old items for reversal
        old_items = self.db.get_stock_adjustment_items(adjustment_id)
        
        # Calculate totals using Decimal
        total_increase = Decimal('0')
        total_decrease = Decimal('0')
        
        for item in items_data:
            difference_qty = Decimal(str(item.get('difference_qty', 0)))
            rate = Decimal('0') if qty_only_no_value_effect else Decimal(str(item.get('rate', 0)))
            value = difference_qty * rate
            
            if qty_only_no_value_effect:
                item['rate'] = 0.0
            item['value'] = float(value)
            
            if difference_qty > 0:
                total_increase += value
            elif difference_qty < 0:
                total_decrease += abs(value)
        
        net_adjustment = total_increase - total_decrease
        
        header_data['total_increase_value'] = float(total_increase)
        header_data['total_decrease_value'] = float(total_decrease)
        header_data['net_adjustment'] = float(net_adjustment)
        
        # BEGIN TRANSACTION
        conn = self.db.connect()
        cursor = conn.cursor()
        
        try:
            # Step 1: Reverse old stock movements
            for old_item in old_items:
                product_id = old_item['product_id']
                old_difference_qty = Decimal(str(old_item.get('difference_qty', 0)))
                
                # Reverse the movement (opposite sign)
                self.stock_logic.apply_stock_adjustment_movement(
                    company_id=company_id,
                    product_id=product_id,
                    difference_qty=float(-old_difference_qty),
                    adjustment_id=adjustment_id
                )
            
            # Step 2: Reverse old ledger entries
            self.ledger_logic.delete_stock_adjustment_voucher_entries(adjustment_id)
            
            # Step 3 & 4: Delete old items and insert new items (handled by update_stock_adjustment)
            self.db.update_stock_adjustment(adjustment_id, header_data, items_data)
            
            # Step 5: Repost stock movements
            for item in items_data:
                product_id = item['product_id']
                difference_qty = Decimal(str(item.get('difference_qty', 0)))
                
                self.stock_logic.apply_stock_adjustment_movement(
                    company_id=company_id,
                    product_id=product_id,
                    difference_qty=float(difference_qty),
                    adjustment_id=adjustment_id
                )
            
            # Sync product quantity cache for all affected products
            all_product_ids = set()
            for old_item in old_items:
                all_product_ids.add(old_item['product_id'])
            for item in items_data:
                all_product_ids.add(item['product_id'])
            
            for product_id in all_product_ids:
                self.stock_logic.sync_product_quantity_from_movements(product_id)
            
            # Step 6: Repost ledger entries unless this is qty-only.
            if not qty_only_no_value_effect:
                self.ledger_logic.post_stock_adjustment_voucher(
                    adjustment_data=header_data,
                    items_data=items_data
                )
            
            conn.commit()
            
            return {
                'success': True,
                'message': 'Stock adjustment updated successfully'
            }
            
        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'message': f'Error updating stock adjustment: {str(e)}'
            }
        finally:
            conn.close()
    
    def delete_adjustment(self, adjustment_id: int) -> Dict[str, Any]:
        """Delete a stock adjustment with atomic rollback safety.
        
        Flow:
        1. Reverse stock movements
        2. Delete ledger entries
        3. Delete items (cascade)
        4. Delete header
        5. Sync product cache
        
        Uses Decimal for calculations.
        """
        # Get adjustment details
        adjustment = self.db.get_stock_adjustment_by_id(adjustment_id)
        if not adjustment:
            return {
                'success': False,
                'message': 'Stock adjustment not found'
            }
        
        company_id = adjustment['company_id']
        items = self.db.get_stock_adjustment_items(adjustment_id)
        
        # BEGIN TRANSACTION
        conn = self.db.connect()
        cursor = conn.cursor()
        
        try:
            # Step 1: Reverse stock movements
            for item in items:
                product_id = item['product_id']
                difference_qty = Decimal(str(item.get('difference_qty', 0)))
                
                # Reverse the movement (opposite sign)
                self.stock_logic.apply_stock_adjustment_movement(
                    company_id=company_id,
                    product_id=product_id,
                    difference_qty=float(-difference_qty),
                    adjustment_id=adjustment_id
                )
            
            # Step 2: Delete ledger entries
            self.ledger_logic.delete_stock_adjustment_voucher_entries(adjustment_id)
            
            # Step 3 & 4: Delete items and header (cascade handled by DB)
            self.db.delete_stock_adjustment(adjustment_id)
            
            # Step 5: Sync product quantity cache
            for item in items:
                product_id = item['product_id']
                self.stock_logic.sync_product_quantity_from_movements(product_id)
            
            conn.commit()
            
            return {
                'success': True,
                'message': 'Stock adjustment deleted successfully'
            }
            
        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'message': f'Error deleting stock adjustment: {str(e)}'
            }
        finally:
            conn.close()
    
    def get_adjustment_by_id(self, adjustment_id: int) -> Optional[Dict[str, Any]]:
        """Get a stock adjustment by ID."""
        return self.db.get_stock_adjustment_by_id(adjustment_id)
    
    def get_adjustment_items(self, adjustment_id: int) -> List[Dict[str, Any]]:
        """Get all items for a stock adjustment."""
        return self.db.get_stock_adjustment_items(adjustment_id)
