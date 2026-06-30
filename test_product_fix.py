#!/usr/bin/env python3
"""
Test script to verify the product creation fix.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import Database
from bizora_core.product_logic import ProductLogic

def test_product_creation():
    """Test creating a new product to verify the column count fix."""
    try:
        # Initialize database and product logic
        db = Database()
        product_logic = ProductLogic(db)
        
        # Test data for a new product
        test_product_data = {
            'name': 'Test Product Fix',
            'barcode': 'TEST123',
            'hsn': '1234',
            'color': 'Red',
            'size': 'M',
            'unit': 'pcs',
            'category': 'Test Category',
            'purchase_rate': 100.0,
            'sale_price': 150.0,
            'wholesale_rate': 120.0,
            'mrp': 200.0,
            'cgst': 9.0,
            'sgst': 9.0,
            'igst': 0.0,
            'cess': 0.0,
            'reorder_level': 10.0,
            'description': 'Test product for column count fix verification',
            'quantity': 50.0,
            'auto_barcode': False
        }
        
        # Use company_id 1 (assuming it exists)
        company_id = 1
        
        print("Testing product creation with fixed column count...")
        
        # Try to create the product
        result = product_logic.save_product(company_id, test_product_data)
        
        if result['success']:
            print(f"✅ SUCCESS: Product created successfully!")
            print(f"   Product ID: {result['data'].get('id')}")
            print(f"   Message: {result['message']}")
            
            # Clean up - delete the test product
            if result['data'].get('id'):
                delete_result = product_logic.delete_product(company_id, result['data']['id'])
                if delete_result['success']:
                    print("✅ Test product cleaned up successfully")
                else:
                    print(f"⚠️  Warning: Could not clean up test product: {delete_result['message']}")
            
            return True
        else:
            print(f"❌ FAILED: Product creation failed!")
            print(f"   Error: {result['message']}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("PRODUCT CREATION FIX VERIFICATION")
    print("=" * 60)
    
    success = test_product_creation()
    
    print("=" * 60)
    if success:
        print("✅ FIX VERIFIED: Product creation is working correctly!")
    else:
        print("❌ FIX FAILED: Product creation still has issues!")
    print("=" * 60)
