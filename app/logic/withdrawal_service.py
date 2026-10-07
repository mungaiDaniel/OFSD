from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import func
from app.Investments.model import Investment, Withdrawal

class WithdrawalService:
    """
    Service for handling investor withdrawals and applying exit fees.
    """

    EXIT_FEE_RATE = Decimal("0.02")  # 2%
    EXIT_FEE_DAYS_THRESHOLD = 180  # 6 months

    @staticmethod
    def calculate_exit_fee(investor_code: str, fund_id: int, withdrawal_amount: Decimal, withdrawal_date: datetime, session) -> dict:
        """
        Check if a withdrawal is subject to an exit fee (if within 180 days of deposit).
        The fee applies if the withdrawal happens within 180 days of ANY deposit for that fund.
        Actually, many systems apply "First-In-First-Out" or "Last-In-First-Out".
        The PDF says: "If an investor withdraws within 6 months of their deposit date".
        
        Logic: Find the latest deposit for this investor/fund. If it was less than 180 days ago, apply fee.
        Wait, if they have multiple deposits, we should probably check if the *specific* amount being withdrawn
        was deposited < 180 days ago. But the PDF is simple. Let's find the earliest deposit date that has
        un-withdrawn principal.
        
        Simplified Rule: If CURRENT_DATE - EARLIEST_DEPOSIT_DATE < 180 days, apply fee.
        Wait, that would favor them. If they deposit $1000 in Jan and $1000 in June, and withdraw in July.
        The Jan deposit is >180 days, the June one is <180 days.
        
        Standard Fund Logic: FIFO (First-In, First-Out).
        If withdrawal amount <= Principal deposited > 180 days ago, fee = 0.
        If withdrawal amount > Principal deposited > 180 days ago, fee applies to the excess.
        """
        
        # 1. Get all investments for this investor/fund sorted by date
        investments = session.query(Investment).filter(
            Investment.internal_client_code == investor_code,
            Investment.fund_id == fund_id
        ).order_by(Investment.date_deposited.asc()).all()
        
        if not investments:
            return {"gross": withdrawal_amount, "fee": Decimal("0.00"), "net": withdrawal_amount, "reason": "No investments found"}

        # 2. Track "Available Principal" that is > 180 days old
        total_matured_principal = Decimal("0.00")
        total_unmatured_principal = Decimal("0.00")
        
        threshold_date = withdrawal_date - timedelta(days=WithdrawalService.EXIT_FEE_DAYS_THRESHOLD)
        
        for inv in investments:
            deposit_date = inv.date_deposited
            if deposit_date.tzinfo is None:
                deposit_date = deposit_date.replace(tzinfo=timezone.utc)
                
            if deposit_date <= threshold_date:
                total_matured_principal += Decimal(str(inv.net_principal))
            else:
                total_unmatured_principal += Decimal(str(inv.net_principal))

        # 3. Handle existing withdrawals (we need to know how much matured principal is ALREADY used)
        past_withdrawals_sum = session.query(func.sum(Withdrawal.gross_amount)).filter(
            Withdrawal.internal_client_code == investor_code,
            Withdrawal.fund_id == fund_id,
            Withdrawal.status == "Executed"
        ).scalar() or Decimal("0.00")
        
        # Matured principal remaining = Total Matured - Past Withdrawals
        available_matured = max(Decimal("0.00"), total_matured_principal - past_withdrawals_sum)
        
        fee_applicable_amount = Decimal("0.00")
        if withdrawal_amount > available_matured:
            fee_applicable_amount = withdrawal_amount - available_matured
            
        exit_fee = (fee_applicable_amount * WithdrawalService.EXIT_FEE_RATE).quantize(Decimal("0.01"))
        
        return {
            "gross": withdrawal_amount,
            "fee": exit_fee,
            "net": withdrawal_amount - exit_fee,
            "matured_consumed": min(withdrawal_amount, available_matured),
            "fee_applicable_amount": fee_applicable_amount,
            "threshold_date": threshold_date.isoformat()
        }
