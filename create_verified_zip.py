import zipfile
import os
from pathlib import Path

# Configuration
project_root = Path(".")
zip_name = "accounting_app_verified_2026_04_30.zip"

# Exclusions
exclude_dirs = {
    "__pycache__",
    ".git",
    "venv",
    "env",
    "build",
    "dist",
    "temp_extract",
}

exclude_files = {
    "accounting_app_fresh.zip",
    "accounting_app_verified_2026_04_30.zip",
    "accounting.db",
    "accounting.db-shm",
    "accounting.db-wal",
    "test_emergency_db_repair_temp.db",
    "test_zip_verification_temp.db",
    "test_*.db",
}

def should_exclude(path):
    """Check if path should be excluded from zip."""
    parts = Path(path).parts
    for part in parts:
        if part in exclude_dirs:
            return True
    if Path(path).name in exclude_files:
        return True
    if Path(path).name.startswith("test_") and Path(path).suffix == ".db":
        return True
    return False

# Create zip
with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(project_root):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            file_path = Path(root) / file
            relative_path = file_path.relative_to(project_root)
            
            if not should_exclude(relative_path):
                zf.write(file_path, relative_path)
                print(f"Added: {relative_path}")

print(f"\nZip created: {zip_name}")
print(f"Zip size: {Path(zip_name).stat().st_size} bytes")
