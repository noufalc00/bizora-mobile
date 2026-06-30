from db import Database
import os

path = "test_zip_verification_temp.db"
if os.path.exists(path):
    os.remove(path)

db = Database(db_type="sqlite", db_path=path)
result = db.initialize_database()
print("TEMP_SQLITE_INIT_RESULT:", result)

if os.path.exists(path):
    os.remove(path)
