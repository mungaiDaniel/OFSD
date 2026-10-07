#!/usr/bin/env python3
"""
Quick verification that all 4 blocking endpoints are defined and importable.
"""

from app.Reports.route import (
    get_eligible_investors,
    generate_reports,
    list_report_runs,
    get_report_run_detail,
)

print("✓ All 4 blocking endpoints imported successfully:")
print("  1. #7: get_eligible_investors")
print("  2. #8: generate_reports")
print("  3. #9: list_report_runs")
print("  4. #10: get_report_run_detail")
print("\n✓ Endpoint verification complete!")
