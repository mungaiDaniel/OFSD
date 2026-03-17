"""
Multi-Fund Pro-Rata Profit Distribution Calculation Service

This module handles the core business logic for calculating profit distributions
across multiple funds within a single batch using the "Active Money Rule":

- Base Date: date_deployed (Day 0)
- Duration (Live): Duration = (Current_Date - date_deployed)
- Weekly Trigger: Calculates Current Value every 7 days, even if fund performance uploaded monthly
- Formula: Profit Share % = (Investor Amount × Days Active) / (Total Fund Weighted Capital) × 100
           Days Active = Max(Current_Date, Batch_End) - Max(Deposit_Date, date_deployed)
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from app.Batch.model import Batch
from app.Investments.model import Investment
from app.Performance.model import Performance
from app.Performance.pro_rata_distribution import ProRataDistribution
from app.database.database import db
import logging

logger = logging.getLogger(__name__)


class MultiFundProRataService:
    """Service for calculating pro-rata profit distributions across multiple funds"""

    # ==================== CORE CALCULATION METHODS ====================

    @staticmethod
    def calculate_days_active(deposit_date, batch, current_date=None):
        """
        Calculate days active for an investor with LIVE duration.
        
        Live Duration Rule: Duration = (Current_Date - date_deployed)
        Days Active = Max(Current_Date, Batch_End) - Max(Deposit_Date, date_deployed)
        
        Args:
            deposit_date: datetime when the client deposited
            batch: Batch object
            current_date: datetime to calculate against (defaults to now)
        
        Returns:
            Integer representing days active
        """
        if current_date is None:
            current_date = datetime.utcnow()
        
        # Deployment date is fixed starting point
        start_date = max(deposit_date, batch.date_deployed)
        
        # Calculate days active from start to current date
        days_active = (current_date - start_date).days
        
        # Ensure we don't get negative days
        return max(0, days_active)

    @staticmethod
    def calculate_weighted_capital(amount_deposited, days_active):
        """
        Calculate weighted capital = Amount × Days Active
        
        Args:
            amount_deposited: Decimal amount invested
            days_active: Integer days
        
        Returns:
            Decimal weighted capital
        """
        return Decimal(str(amount_deposited)) * Decimal(str(days_active))

    @staticmethod
    def calculate_profit_share(investor_weighted_capital, total_weighted_capital):
        """
        Calculate profit share percentage.
        
        Formula: Profit Share % = (Investor Weighted Capital / Total Weighted Capital) × 100
        
        Args:
            investor_weighted_capital: Decimal
            total_weighted_capital: Decimal
        
        Returns:
            Decimal percentage (0-100) with 4 decimal places
        """
        if total_weighted_capital == 0 or total_weighted_capital == Decimal('0'):
            return Decimal('0.0000')
        
        share = (Decimal(str(investor_weighted_capital)) / Decimal(str(total_weighted_capital))) * Decimal('100')
        return share.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

    @staticmethod
    def calculate_profit_allocated(profit_share_percentage, net_profit):
        """
        Calculate actual profit allocated to investor.
        
        Formula: Profit Allocated = (Profit Share % / 100) × Net Profit
        
        Args:
            profit_share_percentage: Decimal percentage
            net_profit: Decimal net profit amount
        
        Returns:
            Decimal profit allocated with 2 decimal places
        """
        allocated = (Decimal(str(profit_share_percentage)) / Decimal('100')) * Decimal(str(net_profit))
        return allocated.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # ==================== FUND-BASED CALCULATIONS ====================

    @classmethod
    def calculate_fund_distributions(cls, batch_id, fund_name, performance_id, current_date=None):
        """
        Calculate pro-rata distributions for a specific fund within a batch.
        
        Args:
            batch_id: ID of the batch
            fund_name: Name of the fund (e.g., 'Axiom', 'Atium')
            performance_id: ID of the performance record
            current_date: Optional current date for calculations (defaults to now)
        
        Returns:
            tuple: (success: bool, message: str, distributions: list[dict])
        """
        try:
            if current_date is None:
                current_date = datetime.utcnow()

            # Get batch and performance
            batch = Batch.query.get(batch_id)
            if not batch:
                return False, f"Batch {batch_id} not found", []

            performance = Performance.query.get(performance_id)
            if not performance:
                return False, f"Performance {performance_id} not found", []

            # Get all investments for this fund
            investments = Investment.query.filter_by(
                batch_id=batch_id,
                fund_name=fund_name
            ).all()
            
            if not investments:
                return False, f"No investments found for fund {fund_name} in batch {batch_id}", []

            # Get net profit
            net_profit = performance.net_profit

            # Step 1: Calculate weighted capitals
            weighted_capitals = {}
            total_weighted_capital = Decimal('0.00')

            for investment in investments:
                days_active = cls.calculate_days_active(
                    investment.date_deposited, batch, current_date
                )
                weighted_capital = cls.calculate_weighted_capital(
                    investment.amount_deposited, days_active
                )
                
                weighted_capitals[investment.id] = {
                    'investment': investment,
                    'days_active': days_active,
                    'weighted_capital': weighted_capital
                }
                total_weighted_capital += weighted_capital

            # Step 2: Calculate distributions
            distributions = []
            total_allocated = Decimal('0.00')

            for inv_id, data in weighted_capitals.items():
                investment = data['investment']
                days_active = data['days_active']
                weighted_capital = data['weighted_capital']

                # Calculate profit share percentage
                profit_share_pct = cls.calculate_profit_share(
                    weighted_capital, total_weighted_capital
                )

                # Calculate allocated profit
                profit_allocated = cls.calculate_profit_allocated(
                    profit_share_pct, net_profit
                )

                distributions.append({
                    'investment_id': investment.id,
                    'investor_name': investment.investor_name,
                    'investor_email': investment.investor_email,
                    'internal_client_code': investment.internal_client_code,
                    'fund_name': fund_name,
                    'amount_deposited': Decimal(str(investment.amount_deposited)),
                    'date_deposited': investment.date_deposited,
                    'days_active': days_active,
                    'weighted_capital': weighted_capital,
                    'profit_share_percentage': profit_share_pct,
                    'profit_allocated': profit_allocated
                })

                total_allocated += profit_allocated

            return True, f"Fund {fund_name} distributions calculated successfully", distributions

        except Exception as why:
            logger.error(f"Error calculating fund distributions: {str(why)}", exc_info=True)
            return False, f"Error: {str(why)}", []

    @classmethod
    def calculate_batch_all_funds(cls, batch_id, performance_data, current_date=None):
        """
        Calculate pro-rata distributions for ALL funds in a batch.
        
        This is the orchestration method that processes all funds and creates
        distribution records.
        
        Args:
            batch_id: ID of the batch
            performance_data: dict with fund_name -> performance_id mapping
            current_date: Optional current date for calculations
        
        Returns:
            tuple: (success: bool, message: str, summary: dict)
        """
        try:
            if current_date is None:
                current_date = datetime.utcnow()

            # Get batch
            batch = Batch.query.get(batch_id)
            if not batch:
                return False, f"Batch {batch_id} not found", {}

            # Get all unique funds in this batch
            unique_funds = db.session.query(Investment.fund_name).filter(
                Investment.batch_id == batch_id
            ).distinct().all()

            if not unique_funds:
                return False, "No funds found in this batch", {}

            all_distributions = []
            batch_summary = {
                'batch_id': batch_id,
                'calculation_date': current_date.isoformat(),
                'funds': {},
                'total_batch_value': Decimal('0.00'),
                'distribution_count': 0
            }

            for fund_row in unique_funds:
                fund_name = fund_row[0]
                
                # Get performance for this fund
                if fund_name not in performance_data:
                    logger.warning(f"No performance data for fund {fund_name}")
                    continue

                performance_id = performance_data[fund_name]
                
                # Calculate distributions for this fund
                success, message, distributions = cls.calculate_fund_distributions(
                    batch_id, fund_name, performance_id, current_date
                )

                if success:
                    all_distributions.extend(distributions)
                    
                    # Create distribution records in database
                    for dist in distributions:
                        dist_record = ProRataDistribution(
                            batch_id=batch_id,
                            fund_name=fund_name,
                            investment_id=dist['investment_id'],
                            performance_id=performance_id,
                            days_active=dist['days_active'],
                            weighted_capital=dist['weighted_capital'],
                            profit_share_percentage=dist['profit_share_percentage'],
                            profit_allocated=dist['profit_allocated'],
                            internal_client_code=dist['internal_client_code'],
                            investor_name=dist['investor_name'],
                            calculation_date=current_date
                        )
                        db.session.add(dist_record)
                    
                    total_fund_allocated = sum(d['profit_allocated'] for d in distributions)
                    batch_summary['funds'][fund_name] = {
                        'investor_count': len(distributions),
                        'total_allocated': float(total_fund_allocated),
                        'distributions': distributions
                    }
                    batch_summary['total_batch_value'] += total_fund_allocated
                    batch_summary['distribution_count'] += len(distributions)

            db.session.commit()

            return True, "All fund distributions calculated successfully", batch_summary

        except Exception as why:
            logger.error(f"Error in batch distribution calculation: {str(why)}", exc_info=True)
            db.session.rollback()
            return False, f"Error: {str(why)}", {}

    # ==================== WEEKLY RECALCULATION (LIVE TRACKING) ====================

    @classmethod
    def calculate_live_weekly_update(cls, batch_id, fund_name, current_date=None):
        """
        Calculate live weekly update for an investor showing CURRENT week's accrual.
        
        This is called weekly to show how much profit has been accrued since deployment
        without waiting for full monthly performance uploads.
        
        Args:
            batch_id: ID of the batch
            fund_name: Name of the fund
            current_date: Optional current date (defaults to today)
        
        Returns:
            tuple: (success: bool, message: str, weekly_data: dict)
        """
        try:
            if current_date is None:
                current_date = datetime.utcnow()

            batch = Batch.query.get(batch_id)
            if not batch:
                return False, f"Batch {batch_id} not found", {}

            # Get all investments for this fund
            investments = Investment.query.filter_by(
                batch_id=batch_id,
                fund_name=fund_name
            ).all()

            if not investments:
                return False, f"No investments for fund {fund_name}", {}

            weekly_data = {
                'batch_id': batch_id,
                'fund_name': fund_name,
                'as_of_date': current_date.isoformat(),
                'total_capital': Decimal('0.00'),
                'total_days_active': 0,
                'investors': []
            }

            for investment in investments:
                days_active = cls.calculate_days_active(
                    investment.date_deposited, batch, current_date
                )
                
                weekly_data['investors'].append({
                    'investor_name': investment.investor_name,
                    'investor_email': investment.investor_email,
                    'internal_client_code': investment.internal_client_code,
                    'amount_deposited': float(investment.amount_deposited),
                    'date_deposited': investment.date_deposited.isoformat(),
                    'days_active': days_active,
                    'expected_close_date': batch.expected_close_date.isoformat()
                })

                weekly_data['total_capital'] += Decimal(str(investment.amount_deposited))
                weekly_data['total_days_active'] += days_active

            return True, "Weekly update calculated", weekly_data

        except Exception as why:
            logger.error(f"Error in weekly update: {str(why)}", exc_info=True)
            return False, f"Error: {str(why)}", {}


# Maintain backward compatibility
ProRataCalculationService = MultiFundProRataService
