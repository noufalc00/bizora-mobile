"""
Active Logic Files MySQL Placeholder Scanner

This scanner inspects active logic files for hardcoded SQLite `?` placeholders
that need to be replaced with backend-agnostic placeholder usage.
"""

import re
from pathlib import Path
from datetime import datetime


class ActiveLogicPlaceholderScanner:
    """Scanner for active logic files MySQL placeholder issues."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.logic_dir = self.project_root / "logic"
        self.issues = []
        
        # Directories to skip
        self.skip_dirs = {
            "archive_unused_files",
            "archive_unused_files_pending_delete",
            "__pycache__",
            ".git",
            "venv",
            "env",
            "build",
            "dist",
        }
        
        # Active logic files to scan
        self.active_files = [
            "sales_logic.py",
            "sales_return_logic.py",
            "purchase_logic.py",
            "purchase_return_logic.py",
            "stock_logic.py",
            "party_logic.py",
            "ledger_logic.py",
            "trial_balance_logic.py",
            "billing_engine.py",
            "party_balance_engine.py",
        ]
    
    def scan(self):
        """Scan active logic files for hardcoded SQLite placeholders."""
        if not self.logic_dir.exists():
            print(f"ERROR: logic directory not found at {self.logic_dir}")
            return
        
        print(f"Scanning active logic files at: {self.logic_dir}")
        print("=" * 80)
        
        # Scan each active logic file
        for filename in self.active_files:
            file_path = self.logic_dir / filename
            if file_path.exists():
                self._scan_file(file_path)
            else:
                print(f"Skipping (not found): {filename}")
        
        self._generate_report()
    
    def _scan_file(self, file_path: Path):
        """Scan a single file for placeholder issues."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            self._check_line(line_num, line, lines, file_path)
    
    def _check_line(self, line_num: int, line: str, all_lines: list, file_path: Path):
        """Check a single line for placeholder issues."""
        # Skip comments
        if line.strip().startswith('#'):
            return
        
        # Skip docstrings (triple quotes)
        if '"""' in line or "'''" in line:
            # Simple check - if line is part of a docstring, skip
            # This is a basic check; for more robust handling, we'd need proper parsing
            context_start = max(0, line_num - 5)
            context = '\n'.join(all_lines[context_start:line_num])
            if ('"""' in context or "'''" in context) and '"""' not in line and "'''" not in line:
                return
        
        # Check for SQL with hardcoded ?
        patterns = [
            (r'cursor\.execute\([^)]*\?', "cursor.execute with hardcoded ?", "CRITICAL"),
            (r'self\.db\.execute_query\([^)]*\?', "self.db.execute_query with hardcoded ?", "CRITICAL"),
            (r'self\.db\.execute_update\([^)]*\?', "self.db.execute_update with hardcoded ?", "CRITICAL"),
            (r'query\s*=\s*["\'][^"\']*\?', "query variable assignment with hardcoded ?", "CRITICAL"),
            (r'sql\s*=\s*["\'][^"\']*\?', "sql variable assignment with hardcoded ?", "CRITICAL"),
            (r'INSERT INTO.*VALUES.*\?', "INSERT with hardcoded ?", "CRITICAL"),
            (r'SELECT.*WHERE.*\?', "SELECT WHERE with hardcoded ?", "CRITICAL"),
            (r'UPDATE.*SET.*WHERE.*\?', "UPDATE with hardcoded ?", "CRITICAL"),
            (r'DELETE.*WHERE.*\?', "DELETE WHERE with hardcoded ?", "CRITICAL"),
            (r'reference_type\s*=\s*\?', "reference_type = ? pattern", "CRITICAL"),
            (r'reference_id\s*=\s*\?', "reference_id = ? pattern", "CRITICAL"),
            (r"VALUES\s*\(\?,", "VALUES (, ... pattern", "CRITICAL"),
            (r"WHERE.*=\s*\?", "WHERE field = ? pattern", "CRITICAL"),
            (r'\.join\([\'"]\?[\'"]', "','.join('?') pattern", "CRITICAL"),
            (r'import sqlite3', "direct sqlite3 import", "WARNING"),
            (r'from sqlite3 import', "direct sqlite3 import", "WARNING"),
            (r'PRAGMA', "PRAGMA statement (SQLite-only)", "WARNING"),
            (r'INSERT OR REPLACE', "INSERT OR REPLACE (SQLite-only)", "WARNING"),
            (r'sqlite_master', "sqlite_master (SQLite-only)", "WARNING"),
        ]
        
        for pattern, description, severity in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Get context
                context_start = max(0, line_num - 2)
                context_end = min(len(all_lines), line_num + 2)
                context = '\n'.join(all_lines[context_start:context_end])
                
                self.issues.append({
                    'file': file_path.name,
                    'line': line_num,
                    'description': description,
                    'severity': severity,
                    'code': line.strip(),
                    'context': context
                })
                break  # Only report first match per line
    
    def _generate_report(self):
        """Generate the markdown report."""
        report_dir = self.project_root / "reports"
        report_dir.mkdir(exist_ok=True)
        
        report_path = report_dir / "active_logic_mysql_placeholder_report.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# Active Logic Files MySQL Placeholder Scanner Report\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Logic Directory:** {self.logic_dir}\n")
            f.write(f"**Total Issues Found:** {len(self.issues)}\n\n")
            
            # Count by severity
            critical_issues = [i for i in self.issues if i['severity'] == 'CRITICAL']
            warning_issues = [i for i in self.issues if i['severity'] == 'WARNING']
            
            f.write(f"**Critical Issues:** {len(critical_issues)}\n")
            f.write(f"**Warning Issues:** {len(warning_issues)}\n\n")
            
            if not self.issues:
                f.write("## ✅ NO ISSUES FOUND\n\n")
                f.write("Active logic files have no hardcoded SQLite `?` placeholders that need fixing.\n")
            else:
                f.write("## ISSUES FOUND\n\n")
                
                # Group by file
                files_with_issues = {}
                for issue in self.issues:
                    if issue['file'] not in files_with_issues:
                        files_with_issues[issue['file']] = []
                    files_with_issues[issue['file']].append(issue)
                
                for filename, issues in files_with_issues.items():
                    f.write(f"### {filename}\n\n")
                    f.write(f"Issues: {len(issues)}\n\n")
                    
                    for i, issue in enumerate(issues, 1):
                        f.write(f"#### Issue {i}\n\n")
                        f.write(f"**Line:** {issue['line']}\n")
                        f.write(f"**Severity:** {issue['severity']}\n")
                        f.write(f"**Description:** {issue['description']}\n")
                        f.write(f"**Code:**\n```\n{issue['code']}\n```\n")
                        f.write(f"**Context:**\n```\n{issue['context']}\n```\n\n")
        
        print(f"\nReport written to: {report_path}")
        print(f"Total issues: {len(self.issues)} (Critical: {len(critical_issues)}, Warnings: {len(warning_issues)})")


def main():
    """Main entry point."""
    import sys
    
    # Get project root from script location
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    scanner = ActiveLogicPlaceholderScanner(str(project_root))
    scanner.scan()


if __name__ == "__main__":
    main()
