"""Diagnostic: print the column layout of the sales_items table.

Read-only schema inspection. The database location is imported from db.py
(get_default_database_path) so this tool always opens the application's own
accounting.db regardless of the working directory it is launched from.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_default_database_path


def main():
    """Connect to the shared database and list sales_items table columns."""
    db_path = get_default_database_path()
    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found at: {db_path}")
        return

    connection = None
    try:
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        # Match the application's journal handling so no -wal/-shm sidecar
        # files are ever created against the live database.
        cursor.execute("PRAGMA journal_mode = DELETE;")
        cursor.execute("PRAGMA table_info(sales_items)")
        columns = cursor.fetchall()
        print(f"Database: {db_path}")
        print("SALES_ITEMS TABLE COLUMNS:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        print(f"\nTotal columns: {len(columns)}")
    except sqlite3.Error as exc:
        print(f"Database error while reading sales_items schema: {exc}")
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
