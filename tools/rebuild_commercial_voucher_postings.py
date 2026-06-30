#!/usr/bin/env python3
"""Rebuild ledger/stock postings through the commercial posting engine."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import Database
from bizora_core.voucher_posting_engine import VoucherPostingEngine


def active_company_id(db):
    rows = db.execute_query("SELECT id, business_name FROM companies WHERE is_active = 1 LIMIT 1")
    if rows:
        return int(rows[0]["id"]), rows[0]["business_name"]
    rows = db.execute_query("SELECT id, business_name FROM companies ORDER BY id LIMIT 1")
    if rows:
        return int(rows[0]["id"]), rows[0]["business_name"]
    return None, ""


def run():
    db = Database()
    init_result = db.initialize_database()
    company_id, company_name = active_company_id(db)
    lines = [
        "# Commercial Voucher Posting Rebuild Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"DB initialize result: {init_result}",
        f"Active company: {company_name} ({company_id})",
        "",
    ]
    if not company_id:
        lines.append("No company found. Rebuild skipped.")
        success = False
    else:
        engine = VoucherPostingEngine(db)
        result = engine.repost_all_company(company_id, dry_run=False)
        success = bool(result.get("success"))
        lines.append(f"success: {success}")
        lines.append(f"posted: {result.get('posted')}")
        lines.append(f"failed_count: {len(result.get('failed', []))}")
        for failed in result.get("failed", [])[:50]:
            lines.append(f"- FAILED {failed.get('voucher_type')} {failed.get('voucher_id')}: {failed.get('message')}")
    report_path = ROOT / "reports" / "commercial_voucher_posting_rebuild_report.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(run())
