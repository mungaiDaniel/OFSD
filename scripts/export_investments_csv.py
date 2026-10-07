"""
Script to extract all investments data from the database into a CSV file.

Usage:
    python scripts/export_investments_csv.py [output_path]

Example:
    python scripts/export_investments_csv.py
    python scripts/export_investments_csv.py investments_export.csv
"""

import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import create_app, Config
from app.database.database import db
from app.Reports.route import generate_investments_csv


def export_csv(output_file="investments_data.csv"):
    app = create_app(Config)
    with app.app_context():
        print("Fetching investment records from database...")
        csv_buffer = generate_investments_csv(db.session)
        
        output_path = Path(output_file)
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_buffer.getvalue())
        
        print(f"Successfully exported data to: {output_path.resolve()}")


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "investments_data.csv"
    export_csv(out_file)
