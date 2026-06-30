import sys
sys.path.insert(0, r'h:\Shared drives\My Drive\App making\apps with windsurf\accounting_app')

from db import Database

db = Database(db_type="sqlite")
print("DB object:", db.db_type)
print("Placeholder:", db._get_placeholder())
print("Varchar:", db._get_varchar_type(255))
print("Decimal:", db._get_decimal_type())
print("Boolean:", db._get_boolean_type())
print("Datetime:", db._get_datetime_type())
print("Primary Key Autoincrement:", db._get_primary_key_autoincrement())
print("Is SQLite:", db._is_sqlite())
print("Is MySQL:", db._is_mysql())
