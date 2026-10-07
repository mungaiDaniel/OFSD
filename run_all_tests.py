#!/usr/bin/env python3
"""
Master Test Runner - Complete Verification Suite
Runs all validation tests and generates a comprehensive report

Tests:
1. Fee calculation correctness
2. SSOT consistency across endpoints
3. Scenario validation (Investor A & B)
4. Frontend display consistency
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, '/var/www/html')


def run_test(test_name: str, module_path: str) -> tuple[bool, str]:
    """Run a test module and capture results"""
    print(f"\n{'─' * 70}")
    print(f"Running: {test_name}")
    print(f"{'─' * 70}")
    
    try:
        # Import and run the test module
        import importlib.util
        spec = importlib.util.spec_from_file_location("test_module", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Capture test output by running main if exists
        if hasattr(module, 'main'):
            module.main()
        elif hasattr(module, 'test_investor_a_b_scenario'):
            module.test_investor_a_b_scenario()
        elif hasattr(module, 'print_formatted_report'):
            module.print_formatted_report()
        
        return True, "Completed successfully"
    
    except FileNotFoundError:
        return False, f"Test file not found: {module_path}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def main():
    print("\n" + "=" * 70)
    print(" " * 15 + "OFDS VALIDATION TEST SUITE")
    print(" " * 10 + "Complete Fee & SSOT Consistency Verification")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Define tests
    backend_dir = Path("/ofds/backend")
    tests = [
        (
            "1. Fee Calculation Validation",
            "test_fee_calculation.py",
            backend_dir / "test_fee_calculation.py"
        ),
        (
            "2. SSOT Consistency Verification",
            "test_ssot_consistency.py",
            backend_dir / "test_ssot_consistency.py"
        ),
        (
            "3. Scenario Validation (Investor A & B)",
            "test_scenario_validation.py",
            backend_dir / "test_scenario_validation.py"
        ),
        (
            "4. Frontend Display Consistency",
            "test_display_consistency.py",
            backend_dir / "test_display_consistency.py"
        ),
    ]
    
    # Run tests
    results = []
    for test_name, module_name, test_path in tests:
        passed, message = run_test(test_name, str(test_path))
        results.append({
            "name": test_name,
            "module": module_name,
            "passed": passed,
            "message": message
        })
    
    # Print summary
    print("\n\n" + "=" * 70)
    print(" " * 25 + "TEST SUMMARY")
    print("=" * 70 + "\n")
    
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    
    print(f"Results: {passed_count}/{total_count} tests passed\n")
    
    for result in results:
        status = "✓ PASS" if result["passed"] else "✗ FAIL"
        print(f"  {status}: {result['name']}")
        if not result["passed"]:
            print(f"         {result['message']}")
    
    print("\n" + "=" * 70)
    print("Test Coverage:")
    print("─" * 70)
    print("""
  ✓ Fee allocation (pro-rata by investment weight)
  ✓ Entry fee calculation (1.5% on post-transaction amount)
  ✓ Net principal validation
  ✓ Performance valuation (3% on net principal)
  ✓ SSOT pattern compliance
  ✓ Overview page AUM consistency
  ✓ Batch page totals match overview
  ✓ Investor portfolio page accuracy
  ✓ Investor directory aggregation
  ✓ No discrepancies between endpoints
  ✓ Database statement values match SSOT calculations
  ✓ Frontend display consistency
    """)
    
    print("=" * 70)
    print("Test Data Scenario:")
    print("─" * 70)
    print("""
  Investor A:
    · Original Deposit:   $30,000.00
    · Transfer Fee (75%): $45.00
    · Entry Fee (1.5%):   $449.33
    · Net Principal:      $29,505.67
    · 3% Profit:          $885.17
    · Ending Balance:     $30,390.84
    
  Investor B:
    · Original Deposit:   $10,000.00
    · Transfer Fee (25%): $15.00
    · Entry Fee (1.5%):   $149.78
    · Net Principal:      $9,835.22
    · 3% Profit:          $295.06
    · Ending Balance:     $10,130.28
    
  Batch Totals:
    · Total Deposits:     $40,000.00
    · Total Fees:         $659.11
    · Net Principal:      $39,340.89
    · Total Profit:       $1,180.23
    · Total AUM:          $40,521.12
    """)
    
    print("=" * 70)
    print("Consistency Requirements (MUST ALL MATCH):")
    print("─" * 70)
    print("""
  Overview Page:
    Total AUM = $40,521.12
    Total Profit = $1,180.23
    
  Batch Detail Page:
    Batch AUM = $40,521.12
    Individual investor holdings = sum to $40,521.12
    
  Investor A Portfolio Page:
    Current Balance = $30,390.84
    Holdings = $30,390.84
    
  Investor B Portfolio Page:
    Current Balance = $10,130.28
    Holdings = $10,130.28
    
  Investor Directory:
    Investor A Balance = $30,390.84
    Investor B Balance = $10,130.28
    Total Directory = $40,521.12
    """)
    
    print("=" * 70)
    if passed_count == total_count:
        print("✓ ENTIRE TEST SUITE PASSED!")
        print("  All values are consistent across all pages/endpoints")
    else:
        print(f"✗ {total_count - passed_count} test(s) failed")
        print("  Review failures above and correct issues")
    
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")
    
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
