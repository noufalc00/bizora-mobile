from pathlib import Path
import datetime

p = Path("db.py")
stat = p.stat()
print("DB_PATH:", p.resolve())
print("DB_SIZE_BYTES:", stat.st_size)
print("DB_MODIFIED:", datetime.datetime.fromtimestamp(stat.st_mtime))
