"""
Correct a holding recorded with the wrong class share count after a class switch.

DRY RUN by default: prints before/after and saves nothing. Add --apply to save.
TAKE A DATABASE BACKUP FIRST (Backups page -> Run now).

Esther Makara (client 1966812), batch 44, per the Mauritius shareholder
transactions report (R20915 / SW20914):

    venv/bin/python scripts/fix_switch_to_class_i.py \\
        --batch-id 44 --shares 2187.58 --nav 1418.5235 --date 2026-08-10 \\
        --expected-value 3103131.99

    # happy with the output? run again with --apply
"""

import argparse
import json
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch-id", type=int, required=True)
    ap.add_argument("--investment-id", type=int)
    ap.add_argument("--shares", required=True)
    ap.add_argument("--nav", required=True)
    ap.add_argument("--date", required=True, help="switch date, YYYY-MM-DD")
    ap.add_argument("--expected-value", help="shares x NAV must be within 1.00 of this")
    ap.add_argument("--apply", action="store_true", help="save the changes (default is a dry run)")
    args = ap.parse_args()

    from main import app
    from app.database.database import db
    from app.utils.switch_correction import apply_switch_correction, SwitchCorrectionError

    with app.app_context():
        try:
            result = apply_switch_correction(
                db.session, args.batch_id, Decimal(args.shares), Decimal(args.nav),
                date.fromisoformat(args.date), investment_id=args.investment_id,
                expected_value=args.expected_value, apply=args.apply, actor="fix_switch_to_class_i.py",
            )
        except SwitchCorrectionError as e:
            db.session.rollback()
            print(f"REFUSED - nothing changed: {e}")
            sys.exit(1)
        print(json.dumps(result, indent=2))
        print("\nAPPLIED - changes saved." if result["applied"] else "\nDRY RUN - nothing was saved. Re-run with --apply to save.")


if __name__ == "__main__":
    main()
