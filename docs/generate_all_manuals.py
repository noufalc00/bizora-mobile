"""
Generate all BIZORA documentation PDFs in one step.

Run from project root:
    python docs/generate_all_manuals.py

Outputs in docs/:
    - BIZORA_User_Manual_v1.0.0.pdf          (complete manual with screenshots)
    - BIZORA_Operator_Manual_v1.0.0.pdf      (daily operations)
    - BIZORA_Admin_Manual_v1.0.0.pdf         (setup & maintenance)
    - BIZORA_Quick_Reference_Card_v1.0.0.pdf (printable desk card)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DOCS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DOCS_DIR))


def main() -> None:
    print("=" * 60)
    print("BIZORA Documentation Generator")
    print("=" * 60)

    print("\n[1/5] Capturing UI screenshots...")
    from capture_manual_screenshots import capture_all
    shot_count = capture_all()

    print("\n[2/5] Generating complete user manual...")
    import generate_user_manual_pdf
    full_path = generate_user_manual_pdf.build_manual()
    print(f"  -> {full_path} ({os.path.getsize(full_path):,} bytes)")

    print("\n[3/5] Generating operator manual...")
    import generate_operator_manual
    op_path = generate_operator_manual.build_manual()
    print(f"  -> {op_path} ({os.path.getsize(op_path):,} bytes)")

    print("\n[4/5] Generating administrator manual...")
    import generate_admin_manual
    admin_path = generate_admin_manual.build_manual()
    print(f"  -> {admin_path} ({os.path.getsize(admin_path):,} bytes)")

    print("\n[5/5] Generating quick reference card...")
    import generate_quick_reference_card
    card_path = generate_quick_reference_card.build_manual()
    print(f"  -> {card_path} ({os.path.getsize(card_path):,} bytes)")

    print("\n" + "=" * 60)
    print(f"Done. Screenshots: {shot_count}  |  PDFs: 4")
    print(f"Output folder: {DOCS_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
