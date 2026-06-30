from db import Database
from bizora_core.ledger_logic import LedgerLogic

def clean_database():
    db = Database()
    ledger = LedgerLogic(db)
    
    # Using company ID 25 based on previous terminal logs
    COMPANY_ID = 25 
    
    print("🧹 Wiping corrupted ledger entries and rebuilding...")
    result = ledger.rebuild_ledger_for_company(COMPANY_ID)
    
    if result.get('success'):
        print("\n✅ SUCCESS!")
        print(f"Sales Posted: {result.get('sales_posted')}")
        print(f"Purchases Posted: {result.get('purchases_posted')}")
        print(f"Sales Returns Posted: {result.get('sales_returns_posted')}")
        print(f"Purchase Returns Posted: {result.get('purchase_returns_posted')}")
        print(f"Ledger entries before: {result.get('ledger_entries_before')}")
        print(f"Ledger entries after: {result.get('ledger_entries_after')}")
    else:
        print(f"\n❌ FAILED: {result.get('message')}")

if __name__ == "__main__":
    clean_database()
