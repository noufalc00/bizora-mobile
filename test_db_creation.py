from db import Database
db = Database(db_type="sqlite")
print("Database object created:", db.db_type)
