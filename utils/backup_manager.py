"""
Backup and restore utilities for company database files.

Backups are stored in the application-level backups directory using a
company/date/sequence naming pattern such as abc01-14-06-2026-001.db.
"""

import glob
import json
import os
import shutil
import datetime
import sqlite3
import re
from contextlib import closing


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PENDING_RESTORE_MARKER = os.path.join(APP_ROOT, ".pending_restore.json")
PENDING_RESTORE_SOURCE = os.path.join(APP_ROOT, ".pending_restore_source.db")


def execute_backup(db_path, target_dir, company_name):
    """
    Copy the database into target_dir using company-date-sequence naming.

    Returns:
        tuple: (True, final_filename) on success, or (False, error_message).
    """
    try:
        if not os.path.isdir(target_dir):
            return False, f"Backup target directory does not exist: {target_dir}"

        date_str = datetime.datetime.now().strftime("%d-%m-%Y")
        base_name = f"{company_name}-{date_str}-"
        search_pattern = os.path.join(target_dir, f"{base_name}*.db")
        highest_sequence = 0

        for backup_path in glob.glob(search_pattern):
            file_name = os.path.basename(backup_path)
            sequence_text = file_name[len(base_name):-3]
            if len(sequence_text) == 3 and sequence_text.isdigit():
                highest_sequence = max(highest_sequence, int(sequence_text))

        sequence = highest_sequence + 1
        final_filename = f"{base_name}{sequence:03d}.db"
        final_path = os.path.join(target_dir, final_filename)
        shutil.copy2(db_path, final_path)
        return True, final_filename
    except Exception as error:
        return False, str(error)


def execute_restore(backup_file_path, current_db_path):
    """
    Restore a backup database file over the current database path.

    Returns:
        bool: True when the restore succeeds, otherwise False.
    """
    try:
        shutil.copy2(backup_file_path, current_db_path)
        return True
    except Exception:
        return False


def schedule_restore_on_restart(
    backup_file_path,
    current_db_path,
    replace_company_id=None,
):
    """
    Stage a restore so it is applied before any database opens on restart.

    Returns:
        tuple: (True, message) on success, or (False, error_message).
    """
    try:
        shutil.copy2(backup_file_path, PENDING_RESTORE_SOURCE)
        marker_payload = {
            "source_path": PENDING_RESTORE_SOURCE,
            "target_path": os.path.abspath(current_db_path),
            "company_name": _company_name_from_backup_file(backup_file_path),
            "replace_company_id": replace_company_id,
        }
        with open(PENDING_RESTORE_MARKER, "w", encoding="utf-8") as marker_file:
            json.dump(marker_payload, marker_file)
        return True, "Restore scheduled successfully."
    except Exception as error:
        return False, str(error)


def apply_pending_restore_if_any():
    """
    Apply a previously scheduled restore before the app opens the database.

    Returns:
        tuple: (True, restored_path) if restored, (False, error), or (None, "").
    """
    if not os.path.exists(PENDING_RESTORE_MARKER):
        return None, ""

    try:
        with open(PENDING_RESTORE_MARKER, "r", encoding="utf-8") as marker_file:
            marker_payload = json.load(marker_file)

        source_path = marker_payload.get("source_path") or PENDING_RESTORE_SOURCE
        target_path = marker_payload.get("target_path")
        company_name = marker_payload.get("company_name", "")
        replace_company_id = marker_payload.get("replace_company_id")
        if not target_path:
            raise RuntimeError("Pending restore target path is missing.")

        target_dir = os.path.dirname(target_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        shutil.copy2(source_path, target_path)
        _register_restored_company(target_path, company_name, replace_company_id)
        return True, target_path
    except Exception as error:
        return False, str(error)
    finally:
        for cleanup_path in (PENDING_RESTORE_MARKER, PENDING_RESTORE_SOURCE):
            try:
                if os.path.exists(cleanup_path):
                    os.remove(cleanup_path)
            except OSError:
                pass


def _company_name_from_backup_file(backup_file_path):
    """Extract the company name prefix from a sequenced backup filename."""
    file_stem = os.path.splitext(os.path.basename(backup_file_path))[0]
    match = re.match(r"^(?P<company>.+)-\d{2}-\d{2}-\d{4}-\d{3}$", file_stem)
    if match:
        return match.group("company").strip()
    return ""


def _register_restored_company(db_path, restored_company_name, replace_company_id=None):
    """Mark the restored company active in the restored database."""
    with closing(sqlite3.connect(db_path, timeout=30.0)) as connection:
        connection.execute("PRAGMA busy_timeout = 5000;")
        connection.execute("PRAGMA journal_mode = DELETE;")
        connection.execute("PRAGMA synchronous = NORMAL;")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            )
            """
        )
        company_record = _select_restored_company(connection, restored_company_name)
        if not company_record:
            connection.commit()
            return

        company_id, company_name = company_record
        if replace_company_id is not None:
            company_id, company_name = _replace_company_identity(
                connection,
                source_company_id=company_id,
                target_company_id=int(replace_company_id),
                restored_company_name=restored_company_name or company_name,
            )
        connection.execute("UPDATE companies SET is_active = 0")
        connection.execute(
            """
            UPDATE companies
            SET is_active = 1
            WHERE id = ?
            """,
            (company_id,),
        )
        _upsert_setting(connection, "last_active_company_id", str(company_id))
        _upsert_setting(
            connection,
            "last_active_company_name",
            company_name or restored_company_name,
        )
        _upsert_setting(
            connection,
            "last_active_company_path",
            os.path.abspath(db_path),
        )
        connection.commit()


def _replace_company_identity(
    connection,
    source_company_id,
    target_company_id,
    restored_company_name,
):
    """Replace the old company ID/name with the restored company's identity."""
    if source_company_id == target_company_id:
        if restored_company_name:
            connection.execute(
                """
                UPDATE companies
                SET business_name = ?
                WHERE id = ?
                """,
                (restored_company_name, target_company_id),
            )
        return target_company_id, restored_company_name

    connection.execute(
        """
        DELETE FROM companies
        WHERE id = ?
        """,
        (target_company_id,),
    )
    connection.execute(
        """
        UPDATE companies
        SET id = ?,
            business_name = COALESCE(NULLIF(?, ''), business_name)
        WHERE id = ?
        """,
        (target_company_id, restored_company_name, source_company_id),
    )
    _repoint_company_scoped_rows(connection, source_company_id, target_company_id)
    return target_company_id, restored_company_name


def _repoint_company_scoped_rows(connection, source_company_id, target_company_id):
    """Move restored company-scoped rows to the replaced company ID."""
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    )
    for (table_name,) in cursor.fetchall():
        if table_name == "companies":
            continue
        table_info = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        column_names = {row[1] for row in table_info}
        if "company_id" not in column_names:
            continue
        connection.execute(
            f"""
            UPDATE {table_name}
            SET company_id = ?
            WHERE company_id = ?
            """,
            (target_company_id, source_company_id),
        )


def _select_restored_company(connection, restored_company_name):
    """Return the company row that should be active after restore."""
    cursor = connection.cursor()
    preferred_name = (restored_company_name or "").strip()
    if preferred_name:
        cursor.execute(
            """
            SELECT id, business_name
            FROM companies
            WHERE LOWER(TRIM(business_name)) = LOWER(TRIM(?))
            ORDER BY id
            LIMIT 1
            """,
            (preferred_name,),
        )
        row = cursor.fetchone()
        if row:
            return row

    cursor.execute(
        """
        SELECT id, business_name
        FROM companies
        ORDER BY is_active DESC, id
        LIMIT 1
        """
    )
    return cursor.fetchone()


def _upsert_setting(connection, setting_key, setting_value):
    """Update or insert one app setting."""
    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE app_settings
        SET setting_value = ?
        WHERE setting_key = ?
        """,
        (setting_value, setting_key),
    )
    if cursor.rowcount == 0:
        cursor.execute(
            """
            INSERT INTO app_settings (setting_key, setting_value)
            VALUES (?, ?)
            """,
            (setting_key, setting_value),
        )


def create_backup(db_path, company_name):
    """Create a sequenced backup copy of the selected company database."""
    app_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    backup_dir = os.path.join(app_root, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    success, result = execute_backup(db_path, backup_dir, company_name)
    if not success:
        raise RuntimeError(result)
    return os.path.join(backup_dir, result)


def restore_backup(backup_path, target_db_path):
    """Restore a backup database file over the target database path."""
    if not execute_restore(backup_path, target_db_path):
        raise RuntimeError("Could not restore backup database.")
