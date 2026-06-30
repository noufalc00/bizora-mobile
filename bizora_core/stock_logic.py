"""
Stock Logic module for the Accounting Desktop Application.
Handles stock movement validation, creation, and balance calculations.
This is a foundation module - stock movements are tracked but products.quantity
remains the primary display field for now.
"""

from typing import Optional, List, Dict, Any


class StockLogic:
    """Business logic for stock movements."""
    
    def __init__(self, db):
        """Initialize stock logic with database instance."""
        self.db = db
    
    def calculate_stock_balance(self, company_id: int, product_id: int, to_date: Optional[str] = None) -> float:
        """
        Centralized stock balance calculation (SSOT).
        
        Calculates inventory levels strictly from SUM(quantity) in the stock_movements table.
        The posting engine ALREADY inserts negative quantities for sales and positive for purchases.
        Do NOT perform Python-level sign inversions. Trust the database signs.
        
        Args:
            company_id: Company ID
            product_id: Product ID
            to_date: Optional end date (YYYY-MM-DD). If None, calculates current balance.
            
        Returns:
            Stock balance as float
        """
        try:
            placeholder = self.db._get_placeholder()
            
            exclusion_sql = "COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')"
            if to_date:
                # Calculate balance up to and including to_date
                query = f"""
                    SELECT 
                        COALESCE(SUM(quantity), 0) AS balance
                    FROM stock_movements
                    WHERE company_id = {placeholder}
                    AND product_id = {placeholder}
                    AND DATE(COALESCE(movement_date, created_at)) <= DATE({placeholder})
                    AND {exclusion_sql}
                """
                params = (company_id, product_id, to_date)
            else:
                # Calculate current balance
                query = f"""
                    SELECT 
                        COALESCE(SUM(quantity), 0) AS balance
                    FROM stock_movements
                    WHERE company_id = {placeholder}
                    AND product_id = {placeholder}
                    AND {exclusion_sql}
                """
                params = (company_id, product_id)
            
            result = self.db.execute_query(query, params)
            
            if result and result[0]['balance'] is not None:
                return round(float(result[0]['balance']), 2)
            return 0.0
        except Exception as e:
            print(f"Error calculating stock balance: {e}")
            return 0.0
    
    def delete_stock_movements(self, voucher_type: str, voucher_id: int, voucher_no: Optional[str] = None) -> int:
        """
        Strict deletion protocol for stock movements.
        
        Deletes stock movements by voucher_no AND voucher_type (if voucher_no provided),
        or by voucher_id AND voucher_type (if voucher_no not provided).
        This prevents duplicate stock movements during voucher updates.
        
        Args:
            voucher_type: Voucher type
            voucher_id: Voucher ID
            voucher_no: Voucher number (optional, for stricter deletion)
            
        Returns:
            Number of rows deleted
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            placeholder = self.db._get_placeholder()
            
            # Build WHERE clause based on what's provided
            if voucher_no:
                # STRICT: Delete by voucher_no AND voucher_type
                where_clause = f"voucher_type = {placeholder} AND voucher_no = {placeholder}"
                where_params = (voucher_type, voucher_no)
            else:
                # Fallback: Delete by voucher_id AND voucher_type
                where_clause = f"voucher_type = {placeholder} AND reference_id = {placeholder}"
                where_params = (voucher_type, voucher_id)
            
            # Delete movements
            cursor.execute(
                f"DELETE FROM stock_movements WHERE {where_clause}",
                where_params
            )
            
            deleted_count = cursor.rowcount
            conn.commit()
            self.db.disconnect()
            return deleted_count
        except Exception as e:
            print(f"Error deleting stock movements: {e}")
            if 'conn' in locals():
                conn.rollback()
                self.db.disconnect()
            return 0
    
    def validate_movement_data(self, movement_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate stock movement data before creation.
        
        Args:
            movement_data: Dictionary containing movement information
            
        Returns:
            Dictionary with validation result and normalized data
        """
        errors = []
        
        # Validate required fields
        if 'company_id' not in movement_data or not movement_data['company_id']:
            errors.append("Company ID is required")
        
        if 'product_id' not in movement_data or not movement_data['product_id']:
            errors.append("Product ID is required")
        
        if 'movement_type' not in movement_data or not movement_data['movement_type']:
            errors.append("Movement type is required")
        else:
            valid_types = [
                'opening', 'purchase', 'sale', 'return',
                'adjustment', 'transfer_in', 'transfer_out'
            ]
            if movement_data['movement_type'] not in valid_types:
                errors.append(f"Invalid movement type. Must be one of: {', '.join(valid_types)}")
        
        if 'quantity' not in movement_data:
            errors.append("Quantity is required")
        else:
            try:
                quantity = float(movement_data['quantity'])
                if quantity == 0:
                    errors.append("Quantity cannot be zero")
            except (ValueError, TypeError):
                errors.append("Quantity must be a valid number")
        
        if errors:
            return {
                'success': False,
                'errors': errors,
                'data': None
            }
        
        # Normalize data
        normalized_data = {
            'company_id': int(movement_data['company_id']),
            'product_id': int(movement_data['product_id']),
            'movement_type': movement_data['movement_type'].strip().lower(),
            'quantity': float(movement_data['quantity']),
            'reference_type': movement_data.get('reference_type'),
            'reference_id': movement_data.get('reference_id'),
            'notes': movement_data.get('notes')
        }
        
        return {
            'success': True,
            'errors': None,
            'data': normalized_data
        }
    
    def create_stock_movement(self, movement_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a stock movement record.

        Args:
            movement_data: Dictionary containing:
                - company_id: Company ID
                - product_id: Product ID
                - movement_type: Type of movement (purchase, sale, transfer_in, transfer_out, adjustment, opening, return)
                - quantity: Quantity (positive for additions, negative for deductions)
                - reference_type: Reference type (purchase, sale, transfer, adjustment, product, purchase_return, sales_return)
                - reference_id: Reference ID
                - notes: Optional notes
                - voucher_type: Optional voucher type for distinguishing return types

        Returns:
            Dict with success status and message
        """
        try:
            # Validate required fields
            required_fields = ['company_id', 'product_id', 'movement_type', 'quantity', 'reference_type', 'reference_id']
            for field in required_fields:
                if field not in movement_data:
                    return {'success': False, 'message': f'Missing required field: {field}'}

            # Get values
            company_id = movement_data['company_id']
            product_id = movement_data['product_id']
            movement_type = movement_data['movement_type']
            quantity = movement_data['quantity']
            reference_type = movement_data['reference_type']
            reference_id = movement_data['reference_id']
            notes = movement_data.get('notes', '')
            voucher_type = movement_data.get('voucher_type')

            # DEBUG PRINT
            print(f"INSERTING STOCK MOVEMENT = {movement_type}, {quantity}, {reference_type}, voucher_type={voucher_type}")

            # Create movement record
            movement_id = self.db.create_stock_movement(
                company_id=company_id,
                product_id=product_id,
                movement_type=movement_type,
                quantity=quantity,
                reference_type=reference_type,
                reference_id=reference_id,
                notes=notes,
                voucher_type=voucher_type,
            )

            if movement_id:
                return {
                    'success': True,
                    'message': 'Stock movement created successfully',
                    'movement_id': movement_id
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to create stock movement'
                }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error creating stock movement: {str(e)}'
            }
    
    def get_stock_movements_by_product(self, company_id: int, product_id: int) -> List[Dict[str, Any]]:
        """Get all stock movements for a specific product.
        
        Args:
            company_id: Company ID
            product_id: Product ID
            
        Returns:
            List of stock movement records
        """
        try:
            return self.db.get_stock_movements_by_product(company_id, product_id)
        except Exception as e:
            print(f"Error getting stock movements: {e}")
            return []
    
    def get_stock_movements_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all stock movements for a specific company.
        
        Args:
            company_id: Company ID
            
        Returns:
            List of stock movement records
        """
        try:
            return self.db.get_stock_movements_by_company(company_id)
        except Exception as e:
            print(f"Error getting stock movements: {e}")
            return []
    
    def get_stock_balance_from_movements(self, company_id: int, product_id: int) -> float:
        """Calculate current stock balance from movements for a product.
        
        Uses centralized calculate_stock_balance method (SSOT).
        
        Args:
            company_id: Company ID
            product_id: Product ID
            
        Returns:
            Current stock balance
        """
        try:
            return self.calculate_stock_balance(company_id, product_id)
        except Exception as e:
            print(f"Error calculating stock balance: {e}")
            return 0.0
    
    def create_opening_stock_movement(self, company_id: int, product_id: int, opening_quantity: float) -> bool:
        """Create an opening stock movement for a new product.
        
        This is a helper method to create an initial 'opening' movement
        when a product is created with opening quantity.
        
        Args:
            company_id: Company ID
            product_id: Product ID
            opening_quantity: Opening stock quantity
            
        Returns:
            True if successful, False otherwise
        """
        if opening_quantity <= 0:
            return True  # No opening stock, no movement needed
        
        movement_data = {
            'company_id': company_id,
            'product_id': product_id,
            'movement_type': 'opening',
            'quantity': opening_quantity,
            'reference_type': 'product_creation',
            'reference_id': product_id,
            'notes': 'Opening stock from product creation'
        }
        
        result = self.create_stock_movement(movement_data)
        return result['success']

    def validate_sale_stock(self, company_id: int, sale_items: List[Dict[str, Any]], 
                          current_sale_id: Optional[int] = None) -> Dict[str, Any]:
        """Validate that sale items won't cause negative stock.
        
        This method fetches the latest stock from DB (multi-window safe) and checks
        if the sale quantities would cause negative stock.
        
        Args:
            company_id: Company ID
            sale_items: List of sale items with product_id and quantity
            current_sale_id: Current sale ID (for edit mode, to exclude current bill from stock calculation)
            
        Returns:
            Dictionary with validation result
        """
        try:
            for item in sale_items:
                product_id = item.get('product_id')
                quantity = float(item.get('quantity', 0))
                
                if not product_id or quantity == 0:
                    continue
                
                # Get latest stock from DB (multi-window safe)
                current_stock = self.calculate_stock_balance(company_id, product_id)
                
                # If editing, add back current bill's stock to get pre-bill stock
                if current_sale_id:
                    old_items = self.db.get_sale_items(current_sale_id) or []
                    for old_item in old_items:
                        if old_item.get('product_id') == product_id:
                            old_qty = float(old_item.get('quantity', 0))
                            current_stock += old_qty
                            break
                
                # Check if this would cause negative stock
                if quantity > current_stock:
                    return {
                        'success': False,
                        'message': f"Insufficient stock for product. Available: {current_stock:.3f}, Required: {quantity:.3f}",
                        'product_id': product_id,
                        'available_stock': current_stock,
                        'required_quantity': quantity
                    }
            
            return {
                'success': True,
                'message': 'Stock validation passed'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Error validating stock: {str(e)}'
            }

    def get_current_stock(self, company_id: int, product_id: int) -> float:
        """Return current stock calculated from stock_movements table.

        Formula: opening + purchase - sale + adjustment_in - adjustment_out
        This is the authoritative stock source. Do NOT use products.quantity as truth.

        Args:
            company_id: Company ID
            product_id: Product ID

        Returns:
            Current stock balance as float
        """
        try:
            return self.calculate_stock_balance(company_id, product_id)
        except Exception as e:
            print(f"Error getting current stock: {e}")
            return 0.0

    def delete_movements_for_reference(self, reference_type: str, reference_id: int) -> bool:
        """Delete all stock movements for a given reference (bill/product).

        Used before replacing movements when a sale/purchase is edited or deleted.

        Args:
            reference_type: 'sale', 'purchase', or 'product'
            reference_id: ID of the referenced bill or product

        Returns:
            True if successful
        """
        try:
            return self.db.delete_stock_movements_by_reference(reference_type, reference_id)
        except Exception as e:
            print(f"Error deleting movements for reference: {e}")
            return False

    def replace_movements_for_reference(self, company_id: int, reference_type: str,
                                        reference_id: int,
                                        movements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Safely replace all stock movements for a reference.

        Steps:
        1. Delete old movements for the reference.
        2. Insert new movements.
        3. Sync products.quantity cache for all affected products.

        Args:
            company_id: Company ID
            reference_type: 'sale' or 'purchase'
            reference_id: Bill ID
            movements: List of dicts with keys: product_id, movement_type, quantity

        Returns:
            Dict with success/message
        """
        try:
            self.db.delete_stock_movements_by_reference(reference_type, reference_id)
            affected_product_ids = set()
            for m in movements:
                product_id = m.get('product_id')
                quantity = float(m.get('quantity', 0))
                movement_type = m.get('movement_type', reference_type)
                if not product_id or quantity <= 0:
                    continue
                self.db.create_stock_movement(
                    company_id, product_id, movement_type,
                    quantity, reference_type, reference_id
                )
                affected_product_ids.add(product_id)
            for pid in affected_product_ids:
                self.sync_product_quantity_from_movements(company_id, pid)
            return {'success': True, 'message': 'Stock movements replaced successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Error replacing movements: {str(e)}'}

    def sync_product_quantity_from_movements(self, company_id: int, product_id: int) -> bool:
        """Update products.quantity from movement balance (cache sync only).

        products.quantity is a display cache. The authoritative value is always
        computed via get_current_stock() from the movements table.

        Args:
            company_id: Company ID
            product_id: Product ID

        Returns:
            True if successful
        """
        try:
            balance = self.calculate_stock_balance(company_id, product_id)
            return self.db.set_product_quantity_cache(company_id, product_id, balance)
        except Exception as e:
            print(f"Error syncing product quantity: {e}")
            return False

    def apply_sale_stock_movements(self, company_id: int, sale_id: int,
                                   sale_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create 'sale' stock movements for a new sale and sync cache.

        Args:
            company_id: Company ID
            sale_id: Sale ID
            sale_items: List of sale items with product_id and quantity

        Returns:
            Dictionary with operation result
        """
        try:
            affected = set()
            for item in sale_items:
                product_id = item.get('product_id')
                quantity = float(item.get('quantity', 0))
                if not product_id or quantity <= 0:
                    continue
                self.db.create_stock_movement(
                    company_id, product_id, 'sale', -abs(quantity), 'sale', sale_id
                )
                affected.add(product_id)
            self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Stock movements applied successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Error applying stock movements: {str(e)}'}

    def reverse_sale_stock_movements(self, company_id: int, sale_id: int) -> Dict[str, Any]:
        """Delete stock movements for a sale when the sale is deleted.

        Clean approach: simply delete the movements for this reference.
        The balance formula (opening+purchase-sale) will automatically restore
        the correct stock without needing orphan 'return' movements.

        Args:
            company_id: Company ID
            sale_id: Sale ID

        Returns:
            Dictionary with operation result
        """
        try:
            items = self.db.get_sale_items(sale_id) or []
            affected = {item['product_id'] for item in items
                        if item.get('product_id') and float(item.get('quantity', 0)) > 0}
            self.db.delete_stock_movements_by_reference('sale', sale_id)
            self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Stock movements reversed successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Error reversing stock movements: {str(e)}'}

    def adjust_sale_stock_movements(self, company_id: int, sale_id: int,
                                    old_items: List[Dict[str, Any]],
                                    new_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Replace stock movements when editing a saved sale.

        Clean approach: delete old movements for this sale, insert new ones.
        No orphan 'return' movements are created.

        Args:
            company_id: Company ID
            sale_id: Sale ID
            old_items: Previous sale items (used to identify affected products)
            new_items: Updated sale items

        Returns:
            Dictionary with operation result
        """
        try:
            affected = set()
            for item in old_items:
                if item.get('product_id'):
                    affected.add(item['product_id'])
            self.db.delete_stock_movements_by_reference('sale', sale_id)
            for item in new_items:
                product_id = item.get('product_id')
                quantity = float(item.get('quantity', 0))
                if not product_id or quantity <= 0:
                    continue
                self.db.create_stock_movement(
                    company_id, product_id, 'sale', -abs(quantity), 'sale', sale_id
                )
                affected.add(product_id)
            self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Stock movements adjusted successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Error adjusting stock movements: {str(e)}'}

    def apply_purchase_stock_movements(self, company_id: int, purchase_id: int,
                                       purchase_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create 'purchase' stock movements for a new purchase and sync cache.

        Args:
            company_id: Company ID
            purchase_id: Purchase ID
            purchase_items: List of purchase items with product_id and quantity

        Returns:
            Dictionary with operation result
        """
        try:
            affected = set()
            for item in purchase_items:
                product_id = item.get('product_id')
                quantity = float(item.get('quantity', 0))
                if not product_id or quantity <= 0:
                    continue
                self.db.create_stock_movement(
                    company_id, product_id, 'purchase', quantity, 'purchase', purchase_id
                )
                affected.add(product_id)
            self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Purchase stock movements applied successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Error applying purchase stock movements: {str(e)}'}

    def adjust_purchase_stock_movements(self, company_id: int, purchase_id: int,
                                        old_items: List[Dict[str, Any]],
                                        new_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Replace stock movements when editing a saved purchase.

        Args:
            company_id: Company ID
            purchase_id: Purchase ID
            old_items: Previous purchase items
            new_items: Updated purchase items

        Returns:
            Dictionary with operation result
        """
        try:
            affected = set()
            for item in old_items:
                if item.get('product_id'):
                    affected.add(item['product_id'])
            self.db.delete_stock_movements_by_reference('purchase', purchase_id)
            for item in new_items:
                product_id = item.get('product_id')
                quantity = float(item.get('quantity', 0))
                if not product_id or quantity <= 0:
                    continue
                self.db.create_stock_movement(
                    company_id, product_id, 'purchase', quantity, 'purchase', purchase_id
                )
                affected.add(product_id)
            self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Purchase stock movements adjusted successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Error adjusting purchase stock movements: {str(e)}'}

    def reverse_purchase_stock_movements(self, company_id: int, purchase_id: int) -> Dict[str, Any]:
        """Delete stock movements for a purchase when the purchase is deleted.

        Args:
            company_id: Company ID
            purchase_id: Purchase ID

        Returns:
            Dictionary with operation result
        """
        try:
            items = self.db.get_purchase_items(purchase_id) or []
            affected = {item['product_id'] for item in items
                        if item.get('product_id') and float(item.get('quantity', 0)) > 0}
            self.db.delete_stock_movements_by_reference('purchase', purchase_id)
            self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Purchase stock movements reversed successfully'}
        except Exception as e:
            return {'success': False, 'message': f'Error reversing purchase stock movements: {str(e)}'}

    def apply_purchase_return_stock_movements(self, company_id: int, purchase_return_id: int,
                                              return_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create purchase return stock movements and sync product quantity cache.

        Purchase returns are outward stock movements and must be stored negative.
        """
        try:
            affected = set()
            for item in return_items:
                product_id = item.get('product_id')
                quantity = float(item.get('quantity', 0))
                if not product_id or quantity <= 0:
                    continue
                self.db.create_stock_movement(
                    company_id, product_id, 'return', -abs(quantity),
                    'purchase_return', purchase_return_id, voucher_type='purchase_return'
                )
                affected.add(product_id)
            if affected:
                self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Purchase return stock movements applied'}
        except Exception as e:
            return {'success': False, 'message': f'Error applying purchase return stock movements: {str(e)}'}

    def adjust_purchase_return_stock_movements(self, company_id: int, purchase_return_id: int,
                                               old_items: List[Dict[str, Any]],
                                               new_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Replace stock movements when editing a saved purchase return."""
        try:
            affected = set()
            for item in old_items:
                if item.get('product_id'):
                    affected.add(item['product_id'])
            self.db.delete_stock_movements_by_reference('purchase_return', purchase_return_id)
            for item in new_items:
                product_id = item.get('product_id')
                quantity = float(item.get('quantity', 0))
                if not product_id or quantity <= 0:
                    continue
                self.db.create_stock_movement(
                    company_id, product_id, 'return', -abs(quantity),
                    'purchase_return', purchase_return_id, voucher_type='purchase_return'
                )
                affected.add(product_id)
            if affected:
                self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Purchase return stock movements adjusted'}
        except Exception as e:
            return {'success': False, 'message': f'Error adjusting purchase return stock movements: {str(e)}'}

    def reverse_purchase_return_stock_movements(self, company_id: int, purchase_return_id: int) -> Dict[str, Any]:
        """Delete stock movements when a purchase return is deleted."""
        try:
            items = self.db.get_purchase_return_items(purchase_return_id) or []
            affected = {item['product_id'] for item in items if item.get('product_id')}
            self.db.delete_stock_movements_by_reference('purchase_return', purchase_return_id)
            if affected:
                self.db.batch_sync_product_quantities(company_id, list(affected))
            return {'success': True, 'message': 'Purchase return stock movements reversed'}
        except Exception as e:
            return {'success': False, 'message': f'Error reversing purchase return stock movements: {str(e)}'}

    def apply_stock_adjustment_movement(self, company_id: int, product_id: int, 
                                       difference_qty: float, adjustment_id: int) -> Dict[str, Any]:
        """Create 'stock_adjustment' stock movement.
        
        Movement type: 'stock_adjustment' (standardized).
        Positive difference_qty = stock increase
        Negative difference_qty = stock decrease
        
        Uses centralized stock movement system.
        Never directly updates products.qty.
        """
        try:
            if not product_id or difference_qty == 0:
                return {'success': True, 'message': 'No movement needed (zero quantity or no product)'}
            
            # Movement type: "stock_adjustment" (standardized, NOT "ADJUSTMENT")
            self.db.create_stock_movement(
                company_id=company_id,
                product_id=product_id,
                movement_type='stock_adjustment',
                quantity=difference_qty,
                reference_type='stock_adjustment',
                reference_id=adjustment_id
            )
            
            # Sync product quantity cache
            self.sync_product_quantity_from_movements(company_id, product_id)
            
            return {'success': True, 'message': 'Stock adjustment movement applied'}
        except Exception as e:
            return {'success': False, 'message': f'Error applying stock adjustment movement: {str(e)}'}

    def reverse_stock_adjustment_movement(self, adjustment_id: int) -> Dict[str, Any]:
        """Delete stock movements when a stock adjustment is reversed (edit/delete).

        Uses centralized stock movement system.
        Never directly updates products.qty.
        """
        try:
            # Get items to know which products are affected
            items = self.db.get_stock_adjustment_items(adjustment_id) or []
            affected = {item['product_id'] for item in items if item.get('product_id')}

            # Delete all stock movements for this adjustment
            self.db.delete_stock_movements_by_reference('stock_adjustment', adjustment_id)

            # Sync product quantity cache
            for product_id in affected:
                self.sync_product_quantity_from_movements(product_id)

            return {'success': True, 'message': 'Stock adjustment movements reversed'}
        except Exception as e:
            return {'success': False, 'message': f'Error reversing stock adjustment movements: {str(e)}'}

    def post_stock_reconciliation(self, company_id: int, date: str, adjustments: list) -> Dict[str, Any]:
        """
        Post physical stock reconciliation adjustments.

        Creates a stock adjustment voucher and posts stock movements for all items
        with non-zero variance. Wraps operation in database transaction.

        Args:
            company_id: Company ID
            date: Adjustment date (YYYY-MM-DD)
            adjustments: List of dicts with product_id, variance, item_name

        Returns:
            Dict with success status and message
        """
        try:
            conn = self.db.connect()
            cursor = conn.cursor()

            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")

            # Generate voucher number
            voucher_no = self._generate_stock_adjustment_voucher_no(company_id, cursor)

            # Create stock adjustment header
            header_query = """
                INSERT INTO stock_adjustments (company_id, voucher_date, voucher_no, narration)
                VALUES (?, ?, ?, ?)
            """
            cursor.execute(header_query, (company_id, date, voucher_no, "Auto-generated physical stock reconciliation"))

            adjustment_id = cursor.lastrowid

            # Create items and post stock movements
            sl_no = 1
            for adj in adjustments:
                product_id = adj.get('product_id')
                variance = adj.get('variance', 0.0)

                if variance == 0 or not product_id:
                    continue

                # Create stock adjustment item
                item_query = """
                    INSERT INTO stock_adjustment_items (adjustment_id, sl_no, product_id, difference_qty)
                    VALUES (?, ?, ?, ?)
                """
                cursor.execute(item_query, (adjustment_id, sl_no, product_id, variance))
                sl_no += 1

                # Post stock movement
                # Positive variance = stock increase, Negative variance = stock decrease
                # Use 'adjustment' type with signed quantity (compatible with existing CHECK constraint)
                self.db.create_stock_movement(
                    company_id=company_id,
                    product_id=product_id,
                    movement_type='adjustment',
                    quantity=variance,
                    reference_type='stock_adjustment',
                    reference_id=adjustment_id
                )

                # Sync product quantity cache
                self.sync_product_quantity_from_movements(company_id, product_id)

            # Commit transaction
            conn.commit()

            return {
                'success': True,
                'message': f'Stock reconciliation posted successfully. Voucher: {voucher_no}, Items adjusted: {len([a for a in adjustments if a.get("variance") != 0])}'
            }

        except Exception as e:
            # Rollback on error
            try:
                conn.rollback()
            except:
                pass
            return {
                'success': False,
                'message': f'Error posting stock reconciliation: {str(e)}'
            }

    def _generate_stock_adjustment_voucher_no(self, company_id: int, cursor) -> str:
        """Generate next stock adjustment voucher number."""
        try:
            query = """
                SELECT voucher_no FROM stock_adjustments
                WHERE company_id = ?
                ORDER BY id DESC LIMIT 1
            """
            cursor.execute(query, (company_id,))
            result = cursor.fetchone()

            if result and result[0]:
                # Extract number from voucher_no (e.g., SA-001 -> 001)
                last_no = result[0]
                if '-' in last_no:
                    num_part = last_no.split('-')[-1]
                    try:
                        next_num = int(num_part) + 1
                        return f"SA-{next_num:03d}"
                    except ValueError:
                        pass

            return "SA-001"
        except Exception:
            return "SA-001"
