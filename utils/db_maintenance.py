"""
SQLite database maintenance utilities.

Provides compact-and-repair operations using integrity checks, index rebuilds,
and VACUUM for company database files.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Tuple


class DatabaseMaintenance:
    """Maintenance helpers for SQLite company database files."""

    @staticmethod
    def _file_size_mb(db_path: str) -> float:
        """Return the file size of ``db_path`` in megabytes (2 decimal places)."""
        size_bytes = os.path.getsize(db_path)
        return round(size_bytes / (1024 * 1024), 2)

    @classmethod
    def compact_and_repair(cls, db_path: str) -> Tuple[bool, str]:
        """
        Check integrity, rebuild indexes, and compact a SQLite database.

        Uses autocommit mode because VACUUM cannot run inside a transaction.

        Args:
            db_path: Absolute or relative path to the SQLite database file.

        Returns:
            A tuple of (success flag, message). On success the message includes
            before/after sizes and space saved; on failure it describes the error.
        """
        raw_path = str(db_path or "").strip()
        if not raw_path:
            return False, "Database path is required."

        normalized_path = os.path.abspath(raw_path)
        if not os.path.isfile(normalized_path):
            return False, f"Database file not found: {normalized_path}"

        connection = None
        try:
            size_before_mb = cls._file_size_mb(normalized_path)

            connection = sqlite3.connect(normalized_path, isolation_level=None)
            cursor = connection.cursor()

            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchall()
            if integrity_result != [("ok",)]:
                detail = ", ".join(
                    str(row[0]) if row else "" for row in integrity_result
                ) or "unknown integrity failure"
                return False, f"Database integrity check failed: {detail}"

            cursor.execute("REINDEX")
            cursor.execute("VACUUM")

            size_after_mb = cls._file_size_mb(normalized_path)
            space_saved_mb = round(size_before_mb - size_after_mb, 2)

            message = (
                "Database compact and repair completed successfully. "
                f"Size before: {size_before_mb:.2f} MB, "
                f"size after: {size_after_mb:.2f} MB, "
                f"space saved: {space_saved_mb:.2f} MB."
            )
            return True, message
        except sqlite3.Error as exc:
            return False, f"SQLite maintenance error: {exc}"
        except OSError as exc:
            return False, f"File access error: {exc}"
        except Exception as exc:
            return False, f"Unexpected maintenance error: {exc}"
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
