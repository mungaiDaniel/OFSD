#!/usr/bin/env python3
"""
Quick Test Runner - Run individual tests or all tests for fee/valuation validation

Usage:
    # Run all tests
    python run_tests.py all
    
    # Run specific test
    python run_tests.py fee
    python run_tests.py ssot
    python run_tests.py scenario
    python run_tests.py display
"""

import sys
import subprocess
from pathlib import Path


TESTS = {
    "fee": {
        "name": "Fee Calculation Validation",
        "script": "test_fee_calculation.py",
        "description": "Tests pro-rata fee allocation, entry fees, and net principal calculation"
    },
    "ssot": {
        "name": "SSOT Consistency",
        "script": "test_ssot_consistency.py",
        "description": "Validates Statement values match SSOT calculations across all endpoints"
    },
    "scenario": {
        "name": "Scenario Validation",
        "script": "test_scenario_validation.py",
        "description": "Tests specific Investor A & B scenario with expected values"
    },
    "display": {
        "name": "Frontend Display Consistency",
        "script": "test_display_consistency.py",
        "description": "Verifies Overview, Batch, and Investor pages show same values"
    },
    "all": {
        "name": "All Tests",
        "script": "run_all_tests.py",
        "description": "Run complete validation suite"
    }
}


def run_test(test_key: str):
    """Run a specific test"""
    if test_key not in TESTS:
        print(f"✗ Unknown test: {test_key}")
        print(f"  Available: {', '.join(TESTS.keys())}")
        return 1
    
    test_info = TESTS[test_key]
    script = test_info["script"]
    
    backend_dir = Path(__file__).parent
    script_path = backend_dir / script
    
    if not script_path.exists():
        print(f"✗ Test script not found: {script_path}")
        return 1
    
    print(f"\n{'=' * 70}")
    print(f"Running: {test_info['name']}")
    print(f"{'=' * 70}")
    print(f"Description: {test_info['description']}\n")
    
    # Run the script
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(backend_dir)
        )
        return result.returncode
    except Exception as e:
        print(f"✗ Error running test: {str(e)}")
        return 1


def show_help():
    """Show help message"""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║           OFDS VALIDATION TEST SUITE - QUICK RUNNER                 ║
╚══════════════════════════════════════════════════════════════════════╝

Available Tests:
""")
    
    for test_key, test_info in TESTS.items():
        print(f"  {test_key:10} - {test_info['name']}")
        print(f"             {test_info['description']}\n")
    
    print("""Usage:
  python run_tests.py fee        # Run fee calculation tests
  python run_tests.py ssot       # Run SSOT consistency tests
  python run_tests.py scenario   # Run scenario validation
  python run_tests.py display    # Run frontend display tests
  python run_tests.py all        # Run all tests
  
Examples:
  # Validate fee calculation
  cd backend && python run_tests.py fee
  
  # Check SSOT compliance
  cd backend && python run_tests.py ssot
  
  # Full validation suite
  cd backend && python run_tests.py all

Test Environment:
  ✓ Requires Flask app context
  ✓ Database with test data (batches, investments)
  ✓ Optional: CommittedValuationRun for SSOT tests
""")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["help", "-h", "--help"]:
        show_help()
        return 0
    
    test_key = sys.argv[1].lower()
    
    if test_key == "all":
        return run_test("all")
    else:
        return run_test(test_key)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
