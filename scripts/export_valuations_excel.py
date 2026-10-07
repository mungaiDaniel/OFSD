"""
Script to extract valuation statement data and calculations from the database into an Excel (.xlsx) file.

Usage:
    python scripts/export_valuations_excel.py [output_path] [valuation_run_id]

Example:
    python scripts/export_valuations_excel.py
    python scripts/export_valuations_excel.py valuations_statement.xlsx
    python scripts/export_valuations_excel.py valuation_run_1.xlsx 1
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import create_app, Config
from app.database.database import db
from app.Reports.route import generate_valuations_excel


def export_valuations(output_file="valuations_statement.xlsx", valuation_run_id=None):
    app = create_app(Config)
    with app.app_context():
        print("Extracting valuation statements and methodology from database...")
        excel_buffer = generate_valuations_excel(db.session, valuation_run_id=valuation_run_id)

        output_path = Path(output_file)
        with open(output_path, "wb") as f:
            f.write(excel_buffer.getvalue())

        print(f"Successfully generated valuation statement Excel: {output_path.resolve()}")


if __name__ == "__main__":
    out_file = "valuations_statement.xlsx"
    run_id = None

    if len(sys.argv) > 1:
        # Check if first arg is an integer (run_id) or a filename
        if sys.argv[1].isdigit():
            run_id = int(sys.argv[1])
            out_file = f"valuation_run_{run_id}_statement.xlsx"
        else:
            out_file = sys.argv[1]
            if len(sys.argv) > 2 and sys.argv[2].isdigit():
                run_id = int(sys.argv[2])

    export_valuations(out_file, valuation_run_id=run_id)
