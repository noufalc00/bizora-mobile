"""
Capture UI screenshots for BIZORA user manuals (isolated subprocess per screen).

Uses the native Windows Qt platform so Segoe UI text renders correctly.
Offscreen mode is avoided because it produces block/tofu glyphs in grabs.

Run from project root:
    python docs/capture_manual_screenshots.py
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = Path(__file__).resolve().parent / "screenshots"

SCREENSHOT_TARGETS = [
    ("01_company_gateway.png", "Company Gateway", "ui.company_gateway", "CompanyGateway", "w = cls()"),
    ("02_dashboard.png", "Dashboard", "ui.dashboard", "DashboardWidget", "w = cls(db)"),
    ("03_sales_entry.png", "Sales Entry", "ui.sales_entry", "SalesEntryWidget", "w = cls(db)"),
    ("04_purchase_entry.png", "Purchase Entry", "ui.purchase_entry", "PurchaseEntryWidget", "w = cls(parent=host, db=db)"),
    ("05_products_master.png", "Products Master", "ui.products", "ProductsWidget", "w = cls(db)"),
    ("06_party_master.png", "Party Master", "ui.debitor_creditor", "DebitorCreditorWidget", "w = cls(db)"),
    ("07_ledger.png", "Ledger", "ui.ledger_page", "LedgerPageWidget", "w = cls(db)"),
    ("08_day_book.png", "Day Book", "ui.day_book_page", "DayBookPageWidget", "w = cls(db)"),
    ("09_trial_balance.png", "Trial Balance", "ui.trial_balance_page", "TrialBalancePageWidget", "w = cls(db)"),
    ("10_cash_receipt.png", "Cash Receipt", "ui.cash_receipt_page", "CashReceiptPageWidget", "w = cls(db)"),
    ("11_new_company.png", "New Company", "ui.new_company_page", "NewCompanyPageWidget", "w = cls(db)"),
    ("12_invoice_settings.png", "Invoice Settings", "ui.settings", "SettingsWidget", "w = cls(db)"),
    ("13_general_settings.png", "General Settings", "ui.settings_dialog", "GlobalSettingsDialog", "w = cls(parent=host)"),
    ("14_backup_restore.png", "Backup Restore", "ui.backup_dialog", "BackupRestoreDialog", "w = cls(db.db_path, 'Demo Company Ltd', host)"),
    ("16_account_master.png", "Account Master", "ui.account_creation_page", "AccountCreationPageWidget", "w = cls(db)"),
    ("17_sales_book.png", "Sales Book", "ui.sales_book_page", "SalesBookPageWidget", "w = cls(db)"),
    ("18_gst_sales_report.png", "GST Sales Report", "ui.gst_sales_report_page", "GSTSalesReportPage", "w = cls(db)"),
    ("15_user_management.png", "User Management", "ui.user_management", "UserManagementDialog", "w = cls(parent=host, db_path=db.db_path); w.setWindowTitle('Manage Users')"),
]

CAPTURE_SNIPPET = '''
import os, sys, tempfile, traceback, time, platform
ROOT = {root!r}
OUT = {out!r}
sys.path.insert(0, ROOT)

# Offscreen Qt cannot render Windows system fonts — text appears as blocks.
if platform.system() != "Windows":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from config import FONT_FAMILY, FONT_SIZE
from db import Database
from utils.theme_manager import ThemeManager
import importlib


def _resolve_font_family() -> str:
    """Pick a font family that exists on this machine."""
    families = set(QFontDatabase.families())
    for candidate in (FONT_FAMILY, "Segoe UI", "Arial", "Helvetica", "Tahoma"):
        if candidate in families:
            return candidate
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


def _apply_app_font(app) -> None:
    """Ensure every widget inherits a real system font before grab()."""
    font = QFont(_resolve_font_family(), FONT_SIZE)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)


def _pump_events(cycles: int = 8, delay: float = 0.08) -> None:
    """Give Qt time to lay out widgets and load font glyphs."""
    for _ in range(cycles):
        QCoreApplication.processEvents()
        time.sleep(delay)


def _prepare_widget(widget: QWidget) -> None:
    """Show widget off-screen with theme applied and fonts settled."""
    if not isinstance(widget, QDialog):
        widget.setWindowFlags(Qt.WindowType.Widget)
    widget.resize(1280, 800)
    widget.move(-4000, -4000)
    widget.show()
    _pump_events(3, 0.05)
    if hasattr(widget, "refresh_theme"):
        widget.refresh_theme()
    widget.repaint()
    _pump_events(6, 0.1)


app = QApplication.instance() or QApplication([])
ThemeManager.apply_application_theme(app)
_apply_app_font(app)

host = QWidget()
host.hide()
try:
    from db import get_default_database_path
    db = Database(db_path=get_default_database_path())
except Exception:
    db = Database(db_path=os.path.join(tempfile.mkdtemp(prefix="bizora_shot_"), "shot.db"))

try:
    mod = importlib.import_module({mod!r})
    cls = getattr(mod, {cls!r})
    {build}
    _prepare_widget(w)
    pix = w.grab()
    if pix.isNull():
        print("FAIL: empty pixmap")
    elif pix.save(OUT, "PNG"):
        print("OK")
    else:
        print("FAIL: save error")
except Exception as exc:
    print("FAIL:", exc)
    traceback.print_exc()
finally:
    try:
        w.hide()
    except Exception:
        pass
    QCoreApplication.processEvents()
'''


def capture_one(filename: str, module_path: str, class_name: str, build_line: str) -> bool:
    """Capture one screenshot in an isolated subprocess."""
    out_path = SCREENSHOTS_DIR / filename
    code = CAPTURE_SNIPPET.format(
        root=str(PROJECT_ROOT),
        out=str(out_path),
        mod=module_path,
        cls=class_name,
        build=build_line,
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print(f"  FAIL {filename} (timeout)")
        return False
    output = (result.stdout or "") + (result.stderr or "")
    ok = "OK" in (result.stdout or "") and result.returncode == 0
    status = "OK  " if ok else "FAIL"
    print(f"  {status} {filename}")
    if not ok and output.strip():
        for line in output.strip().splitlines()[-6:]:
            print(f"       {line}")
    return ok


def capture_all() -> int:
    """Capture all screenshots. Returns success count."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving screenshots to: {SCREENSHOTS_DIR}")
    if platform.system() == "Windows":
        print("Using native Windows Qt rendering (Segoe UI fonts).")
    else:
        print("Non-Windows host: using offscreen fallback (fonts may differ).")
    success = 0
    for filename, label, module_path, class_name, build_line in SCREENSHOT_TARGETS:
        print(f"Capturing {label}...")
        if capture_one(filename, module_path, class_name, build_line):
            success += 1
    print(f"\nCaptured {success}/{len(SCREENSHOT_TARGETS)} screenshots.")
    return success


def main() -> None:
    capture_all()


if __name__ == "__main__":
    main()
