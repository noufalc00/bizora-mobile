from db import Database
import os

path = "test_emergency_db_repair_temp.db"
if os.path.exists(path):
    os.remove(path)

db = Database(db_type="sqlite", db_path=path)
result = db.initialize_database()
print("INIT_RESULT:", result)

if os.path.exists(path):
    os.remove(path)
