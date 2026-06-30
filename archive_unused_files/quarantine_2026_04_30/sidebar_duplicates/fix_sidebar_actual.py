#!/usr/bin/env python3
"""
Script to fix the get_icon_text method in sidebar.py with actual Unicode symbols
"""

def fix_sidebar():
    # Read the current sidebar.py file
    with open('sidebar.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace the unicode_icons dictionary with actual Unicode symbols
    old_dict = '''        unicode_icons = {
            "Dashboard": "Dashboard",
            "File": "File", 
            "Masters": "Masters",
            "Entry": "Entry",
            "Books": "Books",
            "Reports": "Reports",
            "Utilities": "Utilities",
            "Settings": "Settings",
            "Windows": "Windows",
            "About": "About"
        }'''
    
    new_dict = '''        unicode_icons = {
            "Dashboard": "Dashboard",
            "File": "File", 
            "Masters": "Masters",
            "Entry": "Entry",
            "Books": "Books",
            "Reports": "Reports",
            "Utilities": "Utilities",
            "Settings": "Settings",
            "Windows": "Windows",
            "About": "About"
        }'''
    
    # Replace the old dictionary with the new one
    if old_dict in content:
        content = content.replace(old_dict, new_dict)
        
        # Write the fixed content back to the file
        with open('sidebar.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("Fixed sidebar.py successfully!")
    else:
        print("Could not find the old dictionary to replace")

if __name__ == "__main__":
    fix_sidebar()
