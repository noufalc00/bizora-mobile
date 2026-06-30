import zipfile
from pathlib import Path
import os

project_root = Path(r"h:\Shared drives\My Drive\App making\apps with windsurf\accounting_app")
zip_path = project_root / "accounting_app_fresh.zip"

# Files to exclude
exclude_extensions = {'.db', '.db-wal', '.db-shm'}
exclude_dirs = {'__pycache__', '.git'}

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(project_root):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            file_path = Path(root) / file
            file_ext = file_path.suffix.lower()
            
            # Skip excluded files
            if file_ext in exclude_extensions:
                continue
            
            # Skip the zip file itself
            if file_path == zip_path:
                continue
            
            # Calculate relative path
            rel_path = file_path.relative_to(project_root)
            
            # Add to zip
            zipf.write(file_path, rel_path)

print(f"Fresh zip created: {zip_path}")
