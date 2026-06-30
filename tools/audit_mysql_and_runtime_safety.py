"""
MySQL Readiness and Runtime Safety Scanner
Scans project for MySQL compatibility issues and duplicate files.
"""

import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Tuple, Set

class MySQLSafetyScanner:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.issues = {
            'CRITICAL': [],
            'WARNING': [],
            'INFO': []
        }
        self.active_runtime_files = self._get_active_runtime_files()
        self.python_files = self._find_python_files()
        
    def _get_active_runtime_files(self) -> Set[str]:
        """Define known active runtime files."""
        return {
            'main.py',
            'config.py',
            'helpers.py',
            'db.py',
            'ui/__init__.py',
            'ui/main_window.py',
            'ui/dashboard.py',
            'ui/accounts.py',
            'ui/transactions.py',
            'ui/reports.py',
            'ui/settings.py',
            'ui/party_page.py',
            'ui/product_page.py',
            'ui/sales_entry.py',
            'ui/purchase_entry.py',
            'ui/sales_return_entry.py',
            'ui/purchase_return_entry.py',
            'ui/ledger_page.py',
            'ui/bank_accounts_page.py',
            'ui/stock_report_page.py',
            'ui/trial_balance_page.py',
            'ui/purchase_entry_delegate.py',
            'components/__init__.py',
            'components/sidebar.py',
            'components/topbar.py',
            'logic/__init__.py',
            'logic/party_logic.py',
            'logic/product_logic.py',
            'logic/sales_logic.py',
            'logic/purchase_logic.py',
            'logic/sales_return_logic.py',
            'logic/purchase_return_logic.py',
            'logic/ledger_logic.py',
            'logic/trial_balance_logic.py',
            'logic/stock_logic.py',
        }
    
    def _find_python_files(self) -> List[Path]:
        """Find all Python files in project."""
        python_files = []
        for root, dirs, files in os.walk(self.project_root):
            # Skip archive, tools, __pycache__, .git, venv, env, .venv
            dirs[:] = [d for d in dirs if d not in [
                '__pycache__', '.git', 'venv', 'env', '.venv',
                'archive_unused_files', 'archive_unused_files_pending_delete',
                'tools', 'reports', 'build', 'dist', 'archive'
            ]]
            for file in files:
                if file.endswith('.py'):
                    python_files.append(Path(root) / file)
        return python_files
    
    def _is_active_runtime_file(self, file_path: Path) -> bool:
        """Check if file is in active runtime set."""
        rel_path = file_path.relative_to(self.project_root)
        return str(rel_path) in self.active_runtime_files or rel_path.name in self.active_runtime_files
    
    def _is_duplicate_backup(self, file_path: Path) -> Tuple[bool, str]:
        """Check if file appears to be duplicate/backup."""
        name_lower = file_path.name.lower()
        parent_lower = file_path.parent.name.lower()
        
        patterns = {
            'backup': r'backup',
            'old': r'\bold\b',
            'copy': r'\bcopy\b',
            'output': r'\boutput\b',
            'updated': r'\bupdated\b',
            'final': r'\bfinal\b',
            'fix': r'\bfix\b',
            'temp': r'\btemp\b',
            'test': r'\btest\b',
            'duplicate': r'\bduplicate\b',
        }
        
        for pattern_name, pattern in patterns.items():
            if re.search(pattern, name_lower) or re.search(pattern, parent_lower):
                return True, f"Contains '{pattern_name}' pattern"
        
        # Check for numbered duplicates (e.g., file1.py, file2.py)
        if re.search(r'\d+\.\w+$', file_path.name):
            return True, "Has numeric suffix suggesting duplicate"
        
        return False, ""
    
    def _check_sqlite_placeholders(self, file_path: Path, content: str, line_num: int, line: str):
        """Check for hardcoded SQLite placeholders."""
        # Skip comments
        if line.strip().startswith('#'):
            return
        
        # Skip helper methods that already handle backend differences
        if '_check_table_exists' in line or '_check_index_exists' in line or '_check_column_exists' in line:
            return
        
        # Skip lines that are inside _check_table_exists or _check_index_exists methods
        lines = content.split('\n')
        in_helper_method = False
        for i in range(line_num - 1, -1, -1):
            if 'def _check_table_exists' in lines[i] or 'def _check_index_exists' in lines[i] or 'def _check_column_exists' in lines[i]:
                in_helper_method = True
                break
            elif 'def ' in lines[i] and i > 0:
                break
        
        if in_helper_method:
            return
        
        # Look for hardcoded ? in SQL patterns
        patterns = [
            (r'\?\s*,', "Comma after placeholder"),
            (r',\s*\?', "Comma before placeholder"),
            (r'=\s*\?\s*$', "Placeholder at end of assignment"),
            (r'WHERE.*\?', "WHERE clause with placeholder"),
            (r'VALUES.*\?', "VALUES clause with placeholder"),
        ]
        
        for pattern, desc in patterns:
            if re.search(pattern, line) and 'cursor.execute' in line:
                # Check if using dynamic placeholder method
                if '_get_placeholder' not in line and 'self._get_placeholder' not in line:
                    self.issues['WARNING'].append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'line': line_num,
                        'type': 'Hardcoded SQLite placeholder',
                        'description': desc,
                        'code': line.strip()
                    })
    
    def _check_sqlite_only_code(self, file_path: Path, content: str, line_num: int, line: str):
        """Check for SQLite-only code."""
        if line.strip().startswith('#'):
            return
        
        # Skip backend helper methods that contain SQLite keywords in their names
        if '_get_primary_key_autoincrement' in line or '_get_text_type' in line:
            return
        
        # Skip _connect_sqlite() method - it's SQLite-only by design
        if 'def _connect_sqlite' in line:
            return
        
        lines = content.split('\n')
        
        # Find which method we're in
        current_method = None
        method_start_line = 0
        for i in range(line_num - 1, -1, -1):
            if 'def _connect_sqlite' in lines[i]:
                current_method = '_connect_sqlite'
                method_start_line = i
                break
            elif 'def _migrate_' in lines[i]:
                current_method = '_migrate_'
                method_start_line = i
                break
            elif 'def ' in lines[i]:
                # Found a different method, stop
                break
        
        # Skip _connect_sqlite method - it's SQLite-only by design
        if current_method == '_connect_sqlite':
            return
        
        # Migration methods are typically guarded at method level
        if current_method == '_migrate_':
            # Check if the method has _is_sqlite guard within first 5 lines
            method_context = '\n'.join(lines[method_start_line:min(method_start_line + 5, len(lines))])
            if '_is_sqlite()' in method_context or 'if self.db_type == "sqlite"' in method_context:
                return
        
        sqlite_patterns = [
            (r'PRAGMA\s+', "PRAGMA statement"),
            (r'sqlite_master', "sqlite_master query"),
            (r'CREATE INDEX IF NOT EXISTS', "CREATE INDEX IF NOT EXISTS"),
            (r'AUTOINCREMENT', "AUTOINCREMENT (use backend abstraction)"),
            (r'\bIFNULL\s*\(', "IFNULL (prefer COALESCE for MySQL)"),
        ]
        
        for pattern, desc in sqlite_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Check if guarded by _is_sqlite()
                context_start = max(0, line_num - 15)
                context_lines = content.split('\n')[context_start:line_num + 2]
                context = '\n'.join(context_lines)
                
                is_guarded = '_is_sqlite()' in context or 'if self.db_type == "sqlite"' in context or 'if self.db_type == "mysql"' in context
                
                if not is_guarded and self._is_active_runtime_file(file_path):
                    self.issues['CRITICAL'].append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'line': line_num,
                        'type': 'SQLite-only code unguarded',
                        'description': desc,
                        'code': line.strip()
                    })
                elif not is_guarded:
                    self.issues['WARNING'].append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'line': line_num,
                        'type': 'SQLite-only code unguarded',
                        'description': desc,
                        'code': line.strip()
                    })
    
    def _check_mysql_risk_code(self, file_path: Path, content: str, line_num: int, line: str):
        """Check for MySQL-risk code."""
        if line.strip().startswith('#'):
            return
        
        # Skip schema checks that just look at existing schema
        if 'TEXT UNIQUE' in line and 'in table_sql' in line:
            return
        
        # Check for raw cursor.lastrowid
        if re.search(r'cursor\.lastrowid', line):
            if '_get_last_insert_id' not in line and 'self._get_last_insert_id' not in line:
                # Only critical if outside db.py
                if file_path.name != 'db.py':
                    self.issues['CRITICAL'].append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'line': line_num,
                        'type': 'Raw cursor.lastrowid',
                        'description': 'Use _get_last_insert_id helper',
                        'code': line.strip()
                    })
        
        # Check for TEXT in UNIQUE or indexed fields
        if re.search(r'TEXT\s+UNIQUE', line, re.IGNORECASE) or \
           re.search(r'UNIQUE\s+.*TEXT', line, re.IGNORECASE):
            self.issues['WARNING'].append({
                'file': str(file_path.relative_to(self.project_root)),
                'line': line_num,
                'type': 'TEXT in UNIQUE constraint',
                'description': 'Consider VARCHAR for MySQL compatibility',
                'code': line.strip()
            })
        
        # Check for direct sqlite3 usage
        if re.search(r'import sqlite3', line) or re.search(r'from sqlite3', line):
            if file_path.name != 'db.py':
                self.issues['CRITICAL'].append({
                    'file': str(file_path.relative_to(self.project_root)),
                    'line': line_num,
                    'type': 'Direct sqlite3 import',
                    'description': 'Use db.py abstraction layer',
                    'code': line.strip()
                })
    
    def _check_file_content(self, file_path: Path):
        """Scan a single Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, start=1):
                    self._check_sqlite_placeholders(file_path, content, line_num, line)
                    self._check_sqlite_only_code(file_path, content, line_num, line)
                    self._check_mysql_risk_code(file_path, content, line_num, line)
        except Exception as e:
            self.issues['INFO'].append({
                'file': str(file_path.relative_to(self.project_root)),
                'line': 0,
                'type': 'Scan error',
                'description': str(e),
                'code': ''
            })
    
    def _check_duplicate_files(self):
        """Check for duplicate/backup files."""
        for file_path in self.python_files:
            is_duplicate, reason = self._is_duplicate_backup(file_path)
            
            if is_duplicate:
                rel_path = str(file_path.relative_to(self.project_root))
                
                # Check if it's an active runtime file
                if self._is_active_runtime_file(file_path):
                    self.issues['WARNING'].append({
                        'file': rel_path,
                        'line': 0,
                        'type': 'Potential duplicate file',
                        'description': f'{reason} but appears to be active',
                        'code': 'File in active runtime set'
                    })
                else:
                    # Check if imported
                    is_imported = self._check_if_imported(file_path)
                    
                    if is_imported:
                        self.issues['WARNING'].append({
                            'file': rel_path,
                            'line': 0,
                            'type': 'Potential duplicate file',
                            'description': f'{reason} but is imported',
                            'code': 'File is imported by active code'
                        })
                    else:
                        self.issues['INFO'].append({
                            'file': rel_path,
                            'line': 0,
                            'type': 'Unused duplicate file',
                            'description': reason,
                            'code': 'Candidate for quarantine'
                        })
    
    def _check_if_imported(self, file_path: Path) -> bool:
        """Check if a file is imported by active runtime files."""
        # Get module name from file path
        rel_path = file_path.relative_to(self.project_root)
        module_name = str(rel_path.with_suffix('')).replace(os.sep, '.')
        
        # Check if any active file imports this
        for active_file in self.active_runtime_files:
            active_path = self.project_root / active_file
            if not active_path.exists():
                continue
            
            try:
                with open(active_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Check for import statements
                if re.search(rf'import\s+{re.escape(module_name)}', content) or \
                   re.search(rf'from\s+{re.escape(module_name)}', content):
                    return True
            except:
                pass
        
        return False
    
    def scan(self):
        """Run full scan."""
        print("=" * 80)
        print("MYSQL READINESS AND RUNTIME SAFETY SCANNER")
        print("=" * 80)
        print()
        
        # Scan all Python files for code issues
        print("Scanning Python files for MySQL compatibility issues...")
        for file_path in self.python_files:
            self._check_file_content(file_path)
        
        # Check for duplicate files
        print("Checking for duplicate/backup files...")
        self._check_duplicate_files()
        
        # Write report to file
        self._write_report()
        
        # Print results
        self._print_results()
    
    def _write_report(self):
        """Write scan results to report file."""
        report_path = self.project_root / 'reports' / 'mysql_runtime_safety_report.md'
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# MySQL Runtime Safety Report\n\n")
            f.write(f"**Project Root:** {self.project_root}\n")
            f.write(f"**Scan Date:** {self._get_current_datetime()}\n\n")
            
            for severity in ['CRITICAL', 'WARNING', 'INFO']:
                f.write(f"## {severity} Issues ({len(self.issues[severity])})\n\n")
                
                if not self.issues[severity]:
                    f.write("None\n\n")
                    continue
                
                for issue in self.issues[severity]:
                    f.write(f"### {issue['type']}\n\n")
                    f.write(f"**File:** {issue['file']}\n")
                    if issue['line'] > 0:
                        f.write(f"**Line:** {issue['line']}\n")
                    f.write(f"**Description:** {issue['description']}\n")
                    if issue['code']:
                        f.write(f"**Code:** `{issue['code'][:200]}`\n")
                    f.write("\n---\n\n")
    
    def _get_current_datetime(self):
        """Get current datetime string."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _print_results(self):
        """Print scan results."""
        print()
        print("=" * 80)
        print("SCAN RESULTS")
        print("=" * 80)
        print()
        
        for severity in ['CRITICAL', 'WARNING', 'INFO']:
            if not self.issues[severity]:
                print(f"{severity}: None")
                print()
                continue
            
            print(f"{severity} ({len(self.issues[severity])} issues):")
            print("-" * 80)
            
            for issue in self.issues[severity]:
                print(f"  File: {issue['file']}")
                if issue['line'] > 0:
                    print(f"  Line: {issue['line']}")
                print(f"  Type: {issue['type']}")
                print(f"  Description: {issue['description']}")
                if issue['code']:
                    print(f"  Code: {issue['code'][:100]}")
                print()
        
        print("=" * 80)
        print("SCAN COMPLETE")
        print("=" * 80)
        print(f"Report written to: {self.project_root / 'reports' / 'mysql_runtime_safety_report.md'}")
        print("=" * 80)


if __name__ == '__main__':
    import sys
    
    # Get project root (assumes script is in tools/ subdirectory)
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    scanner = MySQLSafetyScanner(str(project_root))
    scanner.scan()
