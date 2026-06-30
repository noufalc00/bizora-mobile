from pathlib import Path
import zipfile

zip_path = Path("accounting_app_verified_2026_04_30.zip")
print("ZIP_PATH:", zip_path.resolve())

with zipfile.ZipFile(zip_path, "r") as z:
    names = z.namelist()
    
    # Check for tools/
    tools_files = [n for n in names if n.startswith("tools/")]
    print("TOOLS_FILES:", tools_files)
    
    # Check for reports/
    reports_files = [n for n in names if n.startswith("reports/")]
    print("REPORTS_FILES:", reports_files)
    
    # Check for specific reports
    required_reports = [
        "reports/db_py_emergency_repair_report_2026_04_30.md",
        "reports/db_py_placeholder_verification_report.md",
    ]
    
    for report in required_reports:
        found = report in names
        print(f"{report}: {'FOUND' if found else 'NOT FOUND'}")
