#!/usr/bin/env python3
"""Security regression tests for isolated quotation save SQL."""

import inspect
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from ui import quotation_entry  # noqa: E402


class _TextInput:
    """Small line-edit stand-in for quotation save tests."""

    def __init__(self, text=""):
        self._text = text

    def text(self):
        """Return configured widget text."""
        return self._text

    def setText(self, value):
        """Capture text assigned by save logic."""
        self._text = str(value)


class _Combo:
    """Small combo-box stand-in for quotation save tests."""

    def __init__(self, value):
        self._value = value

    def currentText(self):
        """Return configured combo text."""
        return self._value


class _DateInput:
    """Small date-edit stand-in for quotation save tests."""

    def __init__(self, value):
        self._value = value

    def date(self):
        """Return self so toString mirrors QDate usage."""
        return self

    def toString(self, _format):
        """Return configured ISO date text."""
        return self._value


class _TableItem:
    """Small table-item stand-in for quotation save tests."""

    def __init__(self, value):
        self._value = value

    def text(self):
        """Return configured cell text."""
        return self._value


class _ItemsTable:
    """Small table stand-in exposing only save-path methods."""

    def __init__(self):
        self._rows = [
            {
                1: "Widget A",
                2: "9988",
                3: "9",
                4: "9",
                5: "0",
                6: "0",
                7: "100",
                8: "2",
                9: "200",
                10: "0",
                11: "200",
                12: "18",
                13: "218",
            }
        ]

    def rowCount(self):
        """Return the number of fake item rows."""
        return len(self._rows)

    def item(self, row, column):
        """Return fake item data for a row and column."""
        value = self._rows[row].get(column)
        return _TableItem(value) if value is not None else None


class _Cursor:
    """Cursor that records every executed SQL statement."""

    lastrowid = 101

    def __init__(self, executed_sql):
        self._executed_sql = executed_sql

    def execute(self, sql, params=None):
        """Record SQL and parameters for assertions."""
        self._executed_sql.append((sql, params))


class _Connection:
    """Connection that returns a recording cursor."""

    def __init__(self, executed_sql):
        self._executed_sql = executed_sql
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        """Return a SQL-recording cursor."""
        return _Cursor(self._executed_sql)

    def commit(self):
        """Record successful transaction completion."""
        self.committed = True

    def rollback(self):
        """Record transaction rollback."""
        self.rolled_back = True


class _Database:
    """Database stand-in that exposes only quotation save APIs."""

    def __init__(self):
        self.executed_sql = []
        self.connection = _Connection(self.executed_sql)
        self.disconnected = False

    def _get_placeholder(self):
        """Return SQLite-style placeholders for parameterized SQL."""
        return "?"

    def _get_last_insert_id(self, _cursor):
        """Return a deterministic quotation id."""
        return 101

    def connect(self):
        """Return the fake connection."""
        return self.connection

    def disconnect(self):
        """Record disconnection."""
        self.disconnected = True


class _MessageBox:
    """No-op QMessageBox replacement for save tests."""

    @staticmethod
    def warning(*_args, **_kwargs):
        """Ignore warnings during tests."""

    @staticmethod
    def information(*_args, **_kwargs):
        """Ignore informational messages during tests."""

    @staticmethod
    def critical(*_args, **_kwargs):
        """Ignore critical messages during tests."""


def _build_widget(fake_db):
    """Build a QuotationEntryWidget instance without running QWidget init."""
    widget = quotation_entry.QuotationEntryWidget.__new__(quotation_entry.QuotationEntryWidget)
    widget.company_id = 1
    widget.db = fake_db
    widget.current_quotation_id = None
    widget.quotation_no_input = _TextInput("Q-0001")
    widget.customer_name_input = _TextInput("Acme Traders")
    widget.mobile_input = _TextInput("9999999999")
    widget.gstin_input = _TextInput("27ABCDE1234F1Z5")
    widget.address_input = _TextInput("Main Road")
    widget.narration_input = _TextInput("Test quotation")
    widget.state_combo = _Combo("Maharashtra")
    widget.nature_combo = _Combo("Local")
    widget.quotation_type_combo = _Combo("Standard")
    widget.status_combo = _Combo("Draft")
    widget.date_input = _DateInput("2026-06-06")
    widget.valid_until_input = _DateInput("2026-06-30")
    widget.parties_data = [{"id": 7, "name": "Acme Traders"}]
    widget.sale_items = [{"product_id": 11}]
    widget.products_dict = {11: {"barcode": "ABC123", "unit": "PCS"}}
    widget.items_table = _ItemsTable()
    widget.clear_form = lambda: None
    widget.calculate_totals = lambda: {
        "sub_total": 200.0,
        "discount_total": 0.0,
        "tax_total": 18.0,
        "cgst_total": 9.0,
        "sgst_total": 9.0,
        "igst_total": 0.0,
        "cess_total": 0.0,
        "freight": 0.0,
        "round_off": 0.0,
        "grand_total": 218.0,
    }
    return widget


def test_quotation_save_executes_only_allowed_inserts():
    """Assert quotation save writes only quotations and quotation_items rows."""
    fake_db = _Database()
    widget = _build_widget(fake_db)

    with patch.object(quotation_entry, "QMessageBox", _MessageBox):
        widget.save_quotation()

    normalized_sql = [" ".join(sql.lower().split()) for sql, _params in fake_db.executed_sql]
    assert len(normalized_sql) == 2
    assert normalized_sql[0].startswith("insert into quotations (")
    assert normalized_sql[1].startswith("insert into quotation_items (")
    assert fake_db.connection.committed is True
    assert fake_db.disconnected is True

    allowed_insert = re.compile(r"^insert\s+into\s+(quotations|quotation_items)\s*\(", re.IGNORECASE)
    for sql in normalized_sql:
        assert allowed_insert.match(sql)
        assert not re.search(r"\b(select|update|delete)\b", sql, re.IGNORECASE)


def test_quotation_update_executes_only_allowed_quotation_sql():
    """Assert quotation update overwrites only quotation header and items."""
    fake_db = _Database()
    widget = _build_widget(fake_db)
    widget.current_quotation_id = 202

    with patch.object(quotation_entry, "QMessageBox", _MessageBox):
        widget.save_quotation()

    normalized_sql = [" ".join(sql.lower().split()) for sql, _params in fake_db.executed_sql]
    assert len(normalized_sql) == 3
    assert normalized_sql[0].startswith("update quotations set")
    assert "where id=? and company_id=?" in normalized_sql[0]
    assert normalized_sql[1] == "delete from quotation_items where quotation_id=?"
    assert normalized_sql[2].startswith("insert into quotation_items (")
    assert fake_db.connection.committed is True
    assert fake_db.disconnected is True

    allowed_sql = (
        re.compile(r"^update\s+quotations\s+set\s+", re.IGNORECASE),
        re.compile(r"^delete\s+from\s+quotation_items\s+where\s+quotation_id\s*=", re.IGNORECASE),
        re.compile(r"^insert\s+into\s+quotation_items\s*\(", re.IGNORECASE),
    )
    for sql in normalized_sql:
        assert any(pattern.match(sql) for pattern in allowed_sql)
        assert not re.search(
            r"\b(products|ledger|cashbook|day_book|trial_balance)\b",
            sql,
            re.IGNORECASE,
        )


def test_quotation_save_source_has_no_forbidden_posting_references():
    """Statically guard against financial or inventory posting in save code."""
    save_source = inspect.getsource(quotation_entry.QuotationEntryWidget.save_quotation)
    update_source = inspect.getsource(quotation_entry.QuotationEntryWidget.update_quotation)
    item_source = inspect.getsource(quotation_entry.QuotationEntryWidget._insert_current_items)
    combined_source = f"{save_source}\n{update_source}\n{item_source}".lower()

    forbidden_terms = (
        "get_next_quotation_no",
        "select *",
        "update products",
        "insert into products",
        "debtors_ledger",
        "cashbook",
        "day_book",
        "trial_balance",
    )
    for term in forbidden_terms:
        assert term not in combined_source


if __name__ == "__main__":
    test_quotation_save_executes_only_allowed_inserts()
    test_quotation_update_executes_only_allowed_quotation_sql()
    test_quotation_save_source_has_no_forbidden_posting_references()
    print("Quotation save isolation tests passed.")
