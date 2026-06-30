import sys
sys.path.insert(0, r'h:\Shared drives\My Drive\App making\apps with windsurf\accounting_app')

from db import Database
from bizora_core.sales_logic import SalesLogic
from bizora_core.stock_logic import StockLogic
from bizora_core.party_logic import PartyLogic

print("Logic imports OK")
db = Database(db_type="sqlite")
print("DB object OK:", db.db_type)

# Try additional imports if they exist
try:
    from bizora_core.purchase_logic import PurchaseLogic
    print("PurchaseLogic import OK")
except ImportError as e:
    print(f"PurchaseLogic import failed (may not exist): {e}")

try:
    from bizora_core.sales_return_logic import SalesReturnLogic
    print("SalesReturnLogic import OK")
except ImportError as e:
    print(f"SalesReturnLogic import failed (may not exist): {e}")

try:
    from bizora_core.purchase_return_logic import PurchaseReturnLogic
    print("PurchaseReturnLogic import OK")
except ImportError as e:
    print(f"PurchaseReturnLogic import failed (may not exist): {e}")

try:
    from bizora_core.ledger_logic import LedgerLogic
    print("LedgerLogic import OK")
except ImportError as e:
    print(f"LedgerLogic import failed (may not exist): {e}")

try:
    from bizora_core.trial_balance_logic import TrialBalanceLogic
    print("TrialBalanceLogic import OK")
except ImportError as e:
    print(f"TrialBalanceLogic import failed (may not exist): {e}")

try:
    from bizora_core.party_balance_engine import PartyBalanceEngine
    print("PartyBalanceEngine import OK")
except ImportError as e:
    print(f"PartyBalanceEngine import failed (may not exist): {e}")
