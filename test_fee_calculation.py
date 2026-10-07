#!/usr/bin/env python3
"""
Fee Calculation and Valuation Verification Script
Validates: Transfer fees, Entry fees, Profit calculation, and SSOT consistency

Test Case:
- Investor A deposit: $30,000
- Investor B deposit: $10,000
- Transfer transaction cost: $60 (pro-rata)
- Entry fee: 1.5%
- Performance rate: 3% (Jan)
- Valuation period: Jan 1 - Jan 31
"""

from decimal import Decimal, ROUND_HALF_UP


def quantize_2dp(val):
    """Quantize to 2 decimal places"""
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class FeeCalculationValidator:
    """Validates fee calculations and valuations"""
    
    @staticmethod
    def calculate_pro_rata_fees(deposits: dict, total_transaction_fee: float) -> dict:
        """
        Calculate pro-rata transaction fees for each investor
        
        Args:
            deposits: {"investor_name": amount}
            total_transaction_fee: Total transaction fee to allocate
        
        Returns:
            {"investor_name": pro_rata_fee}
        """
        total_deposit = sum(Decimal(str(v)) for v in deposits.values())
        
        pro_rata = {}
        for investor, amount in deposits.items():
            amount_d = Decimal(str(amount))
            weight = amount_d / total_deposit
            fee = quantize_2dp(Decimal(str(total_transaction_fee)) * weight)
            pro_rata[investor] = {
                "weight": float(weight),
                "transaction_fee": float(fee),
            }
        
        return pro_rata
    
    @staticmethod
    def calculate_net_principal(deposit: float, transaction_fee: float, entry_fee_rate: float) -> dict:
        """
        Calculate net principal after transaction and entry fees
        
        Args:
            deposit: Original deposit amount
            transaction_fee: Pro-rata transaction fee
            entry_fee_rate: Entry fee as percentage (e.g., 0.015 for 1.5%)
        
        Returns:
            {
                "original_deposit": float,
                "after_transaction": float,
                "entry_fee": float,
                "net_principal": float
            }
        """
        deposit_d = quantize_2dp(Decimal(str(deposit)))
        txn_fee_d = quantize_2dp(Decimal(str(transaction_fee)))
        entry_rate_d = Decimal(str(entry_fee_rate))
        
        # After transaction cost
        after_txn = quantize_2dp(deposit_d - txn_fee_d)
        
        # Entry fee calculated on post-transaction amount
        entry_fee = quantize_2dp(after_txn * entry_rate_d)
        
        # Net principal
        net_principal = quantize_2dp(after_txn - entry_fee)
        
        return {
            "original_deposit": float(deposit_d),
            "after_transaction": float(after_txn),
            "entry_fee_rate": float(entry_rate_d),
            "entry_fee": float(entry_fee),
            "net_principal": float(net_principal),
        }
    
    @staticmethod
    def calculate_valuation(net_principal: float, performance_rate: float, days_in_period: int = 31) -> dict:
        """
        Calculate ending balance after valuation
        
        Args:
            net_principal: Starting balance (net after fees)
            performance_rate: Performance rate as percentage (e.g., 0.03 for 3%)
            days_in_period: Days in valuation period (for pro-rata if needed)
        
        Returns:
            {
                "opening_balance": float,
                "performance_rate": float,
                "profit": float,
                "closing_balance": float
            }
        """
        opening_d = quantize_2dp(Decimal(str(net_principal)))
        perf_rate_d = Decimal(str(performance_rate))
        
        # Profit calculation (assuming full month valuation)
        profit = quantize_2dp(opening_d * perf_rate_d)
        
        # Closing balance
        closing = quantize_2dp(opening_d + profit)
        
        return {
            "opening_balance": float(opening_d),
            "performance_rate": float(perf_rate_d),
            "profit": float(profit),
            "closing_balance": float(closing),
        }


def test_investor_a_b_scenario():
    """Test the Investor A & B scenario"""
    print("\n" + "=" * 70)
    print("FEE CALCULATION & VALUATION TEST")
    print("=" * 70)
    
    # ── Step 1: Pro-rata transaction fee allocation ──
    print("\n[STEP 1] Pro-rata Transaction Fee Allocation")
    print("-" * 70)
    
    deposits = {
        "Investor A": 30000,
        "Investor B": 10000,
    }
    
    total_deposit = sum(deposits.values())
    total_txn_fee = 60.00
    
    print(f"Total Deposits: ${total_deposit:,.2f}")
    print(f"Total Transaction Fee: ${total_txn_fee:,.2f}")
    print("\nCalculations:")
    
    pro_rata = FeeCalculationValidator.calculate_pro_rata_fees(deposits, total_txn_fee)
    
    txn_fees_by_investor = {}
    for investor, amount in deposits.items():
        info = pro_rata[investor]
        weight = info["weight"]
        fee = info["transaction_fee"]
        txn_fees_by_investor[investor] = fee
        
        print(f"\n  {investor}:")
        print(f"    Deposit: ${amount:,.2f}")
        print(f"    Weight: {weight:.1%}")
        print(f"    Transaction Fee: ${fee:.2f}")
    
    # Verify total fees sum correctly
    total_calculated_fees = sum(txn_fees_by_investor.values())
    print(f"\nTotal Transaction Fees (Check): ${total_calculated_fees:.2f}")
    assert abs(total_calculated_fees - total_txn_fee) < 0.01, "Transaction fees don't sum to total!"
    print("✓ Transaction fee allocation verified")
    
    # ── Step 2: Calculate net principal per investor ──
    print("\n\n[STEP 2] Net Principal Calculation (After Fees)")
    print("-" * 70)
    
    entry_fee_rate = 0.015  # 1.5%
    print(f"Entry Fee Rate: {entry_fee_rate:.1%}")
    print("\nCalculations:")
    
    net_principals = {}
    total_after_fees = Decimal("0")
    
    for investor, deposit in deposits.items():
        txn_fee = txn_fees_by_investor[investor]
        
        result = FeeCalculationValidator.calculate_net_principal(
            deposit, txn_fee, entry_fee_rate
        )
        
        net_principals[investor] = result["net_principal"]
        total_after_fees += Decimal(str(result["net_principal"]))
        
        print(f"\n  {investor}:")
        print(f"    Original Deposit: ${result['original_deposit']:,.2f}")
        print(f"    Less Transaction Fee: -${result['entry_fee_rate']:.2f}")
        print(f"    After Transaction: ${result['after_transaction']:,.2f}")
        print(f"    Less Entry Fee (1.5%): -${result['entry_fee']:.2f}")
        print(f"    Net Principal: ${result['net_principal']:,.2f}")
    
    total_entry_fees = sum(deposits.values()) - sum(net_principals.values()) - total_txn_fee
    print(f"\nSummary:")
    print(f"  Total Entry Fees: ${total_entry_fees:,.2f}")
    print(f"  Total Starting Capital (Net): ${float(total_after_fees):,.2f}")
    
    # Expected values from user input
    expected_a = 29505.67
    expected_b = 9835.22
    expected_total = 39340.89
    
    actual_a = net_principals["Investor A"]
    actual_b = net_principals["Investor B"]
    actual_total = float(total_after_fees)
    
    print(f"\n✓ Investor A: ${actual_a:,.2f} (expected: ${expected_a:,.2f})")
    assert abs(actual_a - expected_a) < 0.01, f"Investor A mismatch: {actual_a} vs {expected_a}"
    
    print(f"✓ Investor B: ${actual_b:,.2f} (expected: ${expected_b:,.2f})")
    assert abs(actual_b - expected_b) < 0.01, f"Investor B mismatch: {actual_b} vs {expected_b}"
    
    print(f"✓ Total: ${actual_total:,.2f} (expected: ${expected_total:,.2f})")
    assert abs(actual_total - expected_total) < 0.01, f"Total mismatch: {actual_total} vs {expected_total}"
    
    # ── Step 3: Calculate 3% performance valuation ──
    print("\n\n[STEP 3] January Valuation (3% Performance)")
    print("-" * 70)
    
    performance_rate = 0.03  # 3%
    print(f"Performance Rate: {performance_rate:.1%}")
    print("\nCalculations:")
    
    valuations = {}
    total_profit = Decimal("0")
    total_ending = Decimal("0")
    
    for investor, net_principal in net_principals.items():
        result = FeeCalculationValidator.calculate_valuation(
            net_principal, performance_rate
        )
        
        valuations[investor] = result
        total_profit += Decimal(str(result["profit"]))
        total_ending += Decimal(str(result["closing_balance"]))
        
        print(f"\n  {investor}:")
        print(f"    Opening Balance: ${result['opening_balance']:,.2f}")
        print(f"    Performance: {result['performance_rate']:.1%}")
        print(f"    Profit: ${result['profit']:,.2f}")
        print(f"    Closing Balance: ${result['closing_balance']:,.2f}")
    
    print(f"\nBatch Summary:")
    print(f"  Total Profit: ${float(total_profit):,.2f}")
    print(f"  Total Ending Balance (AUM): ${float(total_ending):,.2f}")
    
    # Expected values from user input
    expected_profit_a = 885.17
    expected_ending_a = 30390.84
    expected_profit_b = 295.06
    expected_ending_b = 10130.28
    expected_batch_ending = 40521.12
    
    actual_profit_a = valuations["Investor A"]["profit"]
    actual_ending_a = valuations["Investor A"]["closing_balance"]
    actual_profit_b = valuations["Investor B"]["profit"]
    actual_ending_b = valuations["Investor B"]["closing_balance"]
    actual_batch_ending = float(total_ending)
    
    print(f"\n✓ Investor A Profit: ${actual_profit_a:,.2f} (expected: ${expected_profit_a:,.2f})")
    assert abs(actual_profit_a - expected_profit_a) < 0.01
    
    print(f"✓ Investor A Ending: ${actual_ending_a:,.2f} (expected: ${expected_ending_a:,.2f})")
    assert abs(actual_ending_a - expected_ending_a) < 0.01
    
    print(f"✓ Investor B Profit: ${actual_profit_b:,.2f} (expected: ${expected_profit_b:,.2f})")
    assert abs(actual_profit_b - expected_profit_b) < 0.01
    
    print(f"✓ Investor B Ending: ${actual_ending_b:,.2f} (expected: ${expected_ending_b:,.2f})")
    assert abs(actual_ending_b - expected_ending_b) < 0.01
    
    print(f"✓ Batch Total: ${actual_batch_ending:,.2f} (expected: ${expected_batch_ending:,.2f})")
    assert abs(actual_batch_ending - expected_batch_ending) < 0.01
    
    # ── Step 4: Summary ──
    print("\n\n[SUMMARY]")
    print("=" * 70)
    print("\nFee Breakdown:")
    print(f"  Transaction Fees:  ${total_txn_fee:,.2f}")
    print(f"  Entry Fees:        ${total_entry_fees:,.2f}")
    print(f"  Total Fees:        ${total_txn_fee + total_entry_fees:,.2f}")
    
    print("\nStarting Capital:")
    print(f"  Gross Deposits:    ${total_deposit:,.2f}")
    print(f"  Net Principal:     ${float(total_after_fees):,.2f}")
    print(f"  Deducted:          ${total_txn_fee + total_entry_fees:,.2f}")
    
    print("\nEnding (After 3% Performance):")
    print(f"  Total Profit:      ${float(total_profit):,.2f}")
    print(f"  Total AUM:         ${actual_batch_ending:,.2f}")
    
    print("\nPer-Investor Results:")
    print(f"\n  Investor A:")
    print(f"    Net Principal:   ${actual_a:,.2f}")
    print(f"    Profit (3%):     ${actual_profit_a:,.2f}")
    print(f"    Ending Balance:  ${actual_ending_a:,.2f}")
    
    print(f"\n  Investor B:")
    print(f"    Net Principal:   ${actual_b:,.2f}")
    print(f"    Profit (3%):     ${actual_profit_b:,.2f}")
    print(f"    Ending Balance:  ${actual_ending_b:,.2f}")
    
    print("\n" + "=" * 70)
    print("✓ ALL TESTS PASSED!")
    print("=" * 70 + "\n")
    
    # Return data for use in API testing
    return {
        "batch_total_deposit": total_deposit,
        "batch_transaction_fee": total_txn_fee,
        "batch_entry_fee": total_entry_fees,
        "batch_net_principal": float(total_after_fees),
        "batch_profit": float(total_profit),
        "batch_ending": actual_batch_ending,
        "investors": {
            "Investor A": {
                "deposit": deposits["Investor A"],
                "net_principal": actual_a,
                "profit": actual_profit_a,
                "ending": actual_ending_a,
            },
            "Investor B": {
                "deposit": deposits["Investor B"],
                "net_principal": actual_b,
                "profit": actual_profit_b,
                "ending": actual_ending_b,
            }
        }
    }


if __name__ == "__main__":
    test_data = test_investor_a_b_scenario()
