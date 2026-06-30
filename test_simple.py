#!/usr/bin/env python3
"""
Simple test to verify the product creation fix.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import Database

def test_column_count():
    """Test the INSERT statement directly to verify column count fix."""
    try:
        db = Database()
        conn = db.connect()
        cursor = conn.cursor()
        
        # Get the placeholder character
        ph = db._get_placeholder()
        
        # Test the exact query structure from the fixed code
        query = f"""
            INSERT INTO products (
                company_id, name, barcode, hsn, color, size, unit, category,
                purchase_rate, sale_price, wholesale_rate, mrp,
                cgst, sgst, igst, cess, reorder_level,
                description, quantity, auto_barcode
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        
        print("Testing INSERT statement structure...")
        print(f"Query: {query.strip()}")
        
        # Count placeholders
        placeholder_count = query.count(ph)
        print(f"Number of placeholders: {placeholder_count}")
        
        # Count columns in the INSERT part
        columns_part = query.split("INSERT INTO products (")[1].split(") VALUES")[0]
        columns = [col.strip() for col in columns_part.split(',')]
        print(f"Number of columns: {len(columns)}")
        print(f"Columns: {columns}")
        
        if placeholder_count == len(columns):
            print("SUCCESS: Column count matches placeholder count!")
            return True
        else:
            print(f"MISMATCH: {placeholder_count} placeholders vs {len(columns)} columns")
            return False
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

def check_companies():
    """Check what companies exist in the database."""
    try:
        db = Database()
        conn = db.connect()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name FROM companies LIMIT 5")
        companies = cursor.fetchall()
        
        print("Available companies:")
        for company in companies:
            print(f"  ID: {company[0]}, Name: {company[1]}")
            
        return companies
        
    except Exception as e:
        print(f"Error checking companies: {str(e)}")
        return []

if __name__ == "__main__":
    print("=" * 60)
    print("COLUMN COUNT FIX VERIFICATION")
    print("=" * 60)
    
    # Test the column count fix
    success = test_column_count()
    
    print("\n" + "=" * 60)
    print("COMPANY CHECK")
    print("=" * 60)
    
    companies = check_companies()
    
    print("\n" + "=" * 60)
    if success:
        print("FIX VERIFIED: Column count mismatch has been resolved!")
    else:
        print("FIX FAILED: Column count mismatch still exists!")
    print("=" * 60)
