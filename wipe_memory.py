"""Temporary one-shot maintenance script: wipe Qt QSettings storage.

Clears every value Qt may have persisted for this application in the
Windows Registry (HKEY_CURRENT_USER\\Software\\Accounting Software\\
Accounting Desktop). The org/app names below are the exact names the
application registers in main.py via setOrganizationName("Accounting
Software") and setApplicationName(APP_NAME == "Accounting Desktop").

Run once on the affected machine, then delete this file:
    python wipe_memory.py
"""

from PySide6.QtCore import QSettings

# Exact scope used by main.py (setOrganizationName / setApplicationName).
ORGANIZATION_NAME = "Accounting Software"
APPLICATION_NAME = "Accounting Desktop"


def wipe_qsettings() -> None:
    """Clear and flush all persisted QSettings for this application."""
    try:
        settings = QSettings(ORGANIZATION_NAME, APPLICATION_NAME)
        print(f"QSettings target: {settings.fileName()}")
        keys = settings.allKeys()
        if keys:
            print(f"Found {len(keys)} stored key(s):")
            for key in keys:
                print(f"  - {key} = {settings.value(key)}")
        else:
            print("No stored keys found for this application scope.")
        settings.clear()
        settings.sync()
        print("Windows Registry QSettings completely wiped!")
    except Exception as exc:
        print(f"Error while wiping QSettings: {exc}")


if __name__ == "__main__":
    wipe_qsettings()
