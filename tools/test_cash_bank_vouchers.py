"""Smoke test for Cash/Bank Receipt and Payment voucher modules.

This test copies accounting.db to a temporary database and does not change live data.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import Database
from bizora_core.cash_receipt_logic import CashReceiptLogic
from bizora_core.cash_payment_logic import CashPaymentLogic
from bizora_core.bank_receipt_logic import BankReceiptLogic
from bizora_core.bank_payment_logic import BankPaymentLogic

REPORT = ROOT / "reports" / "cash_bank_voucher_step4_report.md"
LIVE_DB = ROOT / "accounting.db"
TEMP_DB = ROOT / "cash_bank_voucher_test_temp.db"


def write_report(lines):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def pick_account(logic, company_id, main_type="General A/C"):
    options = logic.get_account_options(company_id, main_type)
    if not options:
        raise RuntimeError(f"No account options for {main_type}")
    return options[0]


def post_sample(logic, company_id, amount=123.0):
    primary = logic.get_primary_cash_bank_options(company_id)[0]
    account = pick_account(logic, company_id, "General A/C")
    voucher_no = logic.get_next_voucher_no(company_id)
    result = logic.save_voucher(
        {
            "company_id": company_id,
            "voucher_no": voucher_no,
            "voucher_date": "2026-05-04",
            "main_account_type": "General A/C",
            "cash_bank_account_id": primary["id"],
            "bank_account_id": primary.get("bank_account_id"),
            "remark": "Automated cash/bank voucher smoke test",
            "narration": "Automated cash/bank voucher smoke test",
            "items": [
                {
                    "account_id": account["id"],
                    "party_id": account.get("party_id"),
                    "account_kind": account.get("kind"),
                    "towards_voucher_no": "TEST",
                    "amount": amount,
                    "discount": 0.0,
                    "narration": "Automated smoke test",
                }
            ],
        }
    )
    if not result.get("success"):
        raise RuntimeError(result.get("message"))
    return result["voucher_id"], voucher_no


def check_ledger(db, company_id, voucher_type, voucher_id):
    ph = db._get_placeholder()
    rows = db.execute_query(
        f"""
        SELECT COALESCE(SUM(debit), 0) AS dr, COALESCE(SUM(credit), 0) AS cr, COUNT(*) AS cnt
        FROM ledger_entries
        WHERE company_id = {ph} AND voucher_type = {ph} AND voucher_id = {ph}
        """,
        (company_id, voucher_type, voucher_id),
    )
    if not rows:
        return False, 0.0, 0.0, 0
    dr = float(rows[0]["dr"] or 0.0)
    cr = float(rows[0]["cr"] or 0.0)
    cnt = int(rows[0]["cnt"] or 0)
    return abs(dr - cr) <= 0.01 and cnt >= 2, dr, cr, cnt


def main():
    lines = ["# Cash/Bank Voucher Step 4 Smoke Test", ""]
    if not LIVE_DB.exists():
        lines.append("ERROR: accounting.db not found.")
        write_report(lines)
        print("\n".join(lines))
        return 1
    if TEMP_DB.exists():
        TEMP_DB.unlink()
    shutil.copy2(LIVE_DB, TEMP_DB)

    db = Database(db_type="sqlite", db_path=str(TEMP_DB))
    db.initialize_database()

    company_rows = db.execute_query("SELECT id, business_name FROM companies WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
    if not company_rows:
        company_rows = db.execute_query("SELECT id, business_name FROM companies ORDER BY id DESC LIMIT 1")
    if not company_rows:
        lines.append("ERROR: No company found.")
        write_report(lines)
        print("\n".join(lines))
        return 1
    company_id = int(company_rows[0]["id"])
    lines.append(f"Company: {company_rows[0]['business_name']} ({company_id})")
    lines.append("")

    tests = [
        ("cash_receipt", CashReceiptLogic),
        ("cash_payment", CashPaymentLogic),
        ("bank_receipt", BankReceiptLogic),
        ("bank_payment", BankPaymentLogic),
    ]
    success = True
    for voucher_type, klass in tests:
        logic = klass(db)
        voucher_id, voucher_no = post_sample(logic, company_id)
        ok, dr, cr, cnt = check_ledger(db, company_id, voucher_type, voucher_id)
        lines.append(f"{voucher_type}: voucher={voucher_no}, id={voucher_id}, entries={cnt}, debit={dr:.2f}, credit={cr:.2f}, balanced={ok}")
        success = success and ok

    lines.append("")
    lines.append(f"success: {success}")
    write_report(lines)
    print("\n".join(lines))
    try:
        TEMP_DB.unlink()
    except Exception:
        pass
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
