"""
Mobile web authentication and company selection for local SQLite mode.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any, Optional

from bizora_core.company_logic import CompanyLogic
from config import COMPANY_VISIBILITY_NORMAL, active_company_manager
from db import Database, ensure_company_users_table, hash_password


class MobileAuthService:
    """Company listing and login validation for the mobile web client."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize auth helpers against the master registry database."""
        self.db = db or Database()
        self.company_logic = CompanyLogic(self.db)

    @staticmethod
    def _public_company_row(row: dict[str, Any]) -> dict[str, Any]:
        """Return a safe company payload for the mobile login UI."""
        return {
            "id": row.get("id"),
            "business_name": row.get("business_name") or "",
            "gstin": row.get("gstin") or "",
            "phone_number": row.get("phone_number") or "",
            "email": row.get("email") or "",
            "state": row.get("state") or "",
            "is_active": bool(row.get("is_active")),
            "visibility": (row.get("visibility") or "normal").strip().lower(),
        }

    def list_companies(self, visibility: Optional[str] = None) -> dict[str, Any]:
        """List companies for one visibility pool."""
        try:
            result = self.company_logic.get_all_companies(visibility=visibility)
            companies = [
                self._public_company_row(row)
                for row in (result.get("data") or [])
            ]
            return {"success": True, "companies": companies}
        except Exception as exc:
            return {"success": False, "message": str(exc), "companies": []}

    def get_bootstrap(self) -> dict[str, Any]:
        """Return the last active normal company shown on the desktop login screen."""
        try:
            company = self.db.get_active_company(visibility=COMPANY_VISIBILITY_NORMAL)
            payload = {
                "success": True,
                "company": self._public_company_row(company) if company else None,
            }
            if company and company.get("id"):
                payload["usernames"] = self.list_usernames(int(company["id"]))
            else:
                payload["usernames"] = []
            return payload
        except Exception as exc:
            return {"success": False, "message": str(exc), "company": None, "usernames": []}

    def list_usernames(self, company_id: int) -> list[str]:
        """Return usernames scoped to one company database."""
        company = self.db.get_company_by_id(company_id)
        if not company:
            return ["admin"]
        db_path = self._company_db_path(company)
        try:
            ensure_company_users_table(db_path, company_id)
            with closing(sqlite3.connect(db_path, timeout=30.0)) as connection:
                connection.execute("PRAGMA busy_timeout = 5000;")
                connection.execute("PRAGMA journal_mode = DELETE;")
                connection.execute("PRAGMA synchronous = NORMAL;")
                with closing(connection.cursor()) as cursor:
                    cursor.execute(
                        """
                        SELECT username
                        FROM users
                        WHERE company_id = ?
                        ORDER BY username
                        """,
                        (company_id,),
                    )
                    rows = cursor.fetchall()
            usernames = [str(row[0]) for row in rows if row and row[0]]
            return usernames or ["admin"]
        except (sqlite3.Error, OSError, ValueError) as exc:
            print(f"[MOBILE-AUTH] Username load failed: {exc}")
            return ["admin"]

    @staticmethod
    def _company_db_path(company: dict[str, Any]) -> str:
        """Resolve the SQLite path that stores users for one company."""
        for key in ("db_path", "database_path", "company_db_path", "file_path", "path"):
            value = company.get(key)
            if value:
                return str(value)
        return ""

    def login(
        self,
        company_id: int,
        username: str,
        password: str,
        *,
        is_secret: bool = False,
    ) -> dict[str, Any]:
        """Validate credentials and activate the selected company for mobile reads."""
        entered_username = str(username or "").strip()
        entered_password = str(password or "")
        if not entered_username or not entered_password:
            return {"success": False, "message": "Invalid credentials"}

        company = self.db.get_company_by_id(company_id)
        if not company:
            return {"success": False, "message": "Company not found."}

        try:
            user_record = self._fetch_user_record(company, entered_username)
        except sqlite3.Error as exc:
            return {"success": False, "message": f"Unable to validate credentials: {exc}"}

        stored_hash = user_record[0] if user_record else ""
        stored_plain_password = user_record[1] if user_record else ""
        password_matches = (
            bool(stored_hash) and hash_password(entered_password) == stored_hash
        ) or (bool(stored_plain_password) and entered_password == stored_plain_password)
        if not user_record or not password_matches:
            return {"success": False, "message": "Invalid credentials"}

        role = self._normalize_role(user_record[2])
        activated = self._activate_company(company, is_secret=is_secret)
        return {
            "success": True,
            "message": "",
            "session": {
                "company_id": int(activated.get("id") or company_id),
                "company_name": activated.get("business_name") or "",
                "username": entered_username,
                "role": role,
                "is_secret": bool(is_secret),
            },
            "company": self._public_company_row(activated),
        }

    def _fetch_user_record(self, company: dict[str, Any], username: str):
        """Return password hash, plain password, role, and permissions."""
        company_id = int(company.get("id") or 0)
        db_path = self._company_db_path(company) or self.db.db_path
        ensure_company_users_table(db_path, company_id)
        with closing(sqlite3.connect(db_path, timeout=30.0)) as connection:
            connection.execute("PRAGMA busy_timeout = 5000;")
            connection.execute("PRAGMA journal_mode = DELETE;")
            connection.execute("PRAGMA synchronous = NORMAL;")
            with closing(connection.cursor()) as cursor:
                cursor.execute(
                    """
                    SELECT password_hash, password, role, permissions
                    FROM users
                    WHERE company_id = ?
                      AND username = ?
                    """,
                    (company_id, username),
                )
                return cursor.fetchone()

    @staticmethod
    def _normalize_role(role: Any) -> str:
        """Return the canonical role string used by the desktop app."""
        role_text = str(role or "").strip()
        if role_text.lower() == "admin":
            return "Admin"
        if role_text.lower() == "user":
            return "User"
        return role_text or "User"

    def _activate_company(self, company: dict[str, Any], *, is_secret: bool) -> dict[str, Any]:
        """Persist or session-scope the opened company after successful login."""
        active_company = dict(company)
        try:
            if is_secret:
                active_company_manager.set_active_company(active_company)
                return active_company
            if company.get("id"):
                self.db.set_active_company(int(company["id"]))
                refreshed = self.db.get_active_company()
                if refreshed:
                    active_company = refreshed
            active_company_manager.set_active_company(active_company)
        except Exception as exc:
            print(f"[MOBILE-AUTH] Active company update failed: {exc}")
        return active_company
