"""
Portfolio Display Aggregation Service

Handles pre-computation and caching of investor portfolio display data.
Aggregates holdings, calculates KPIs, and formats data for frontend consumption.
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import func

from app.database.database import db
from app.Investments.model import Investment, EpochLedger, Withdrawal, PortfolioDisplayCache
from app.Valuation.model import Statement
from app.Batch.model import Batch

logger = logging.getLogger(__name__)

COLOR_PALETTE = ['#4682B4', '#87CEEB', '#50C878', '#9370DB', '#F4A460', '#FF6B6B', '#4ECDC4', '#45B7D1']


class PortfolioDisplayAggregationService:
    """Service for aggregating portfolio data and populating display cache."""
    
    @staticmethod
    def _safe_decimal(value, default=Decimal('0.00')):
        """Safely convert value to Decimal."""
        try:
            if value is None:
                return default
            return Decimal(str(value))
        except Exception:
            return default
    
    @staticmethod
    def _safe_float(value, default=0.0):
        """Safely convert value to float."""
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default
    
    @staticmethod
    def rebuild_cache(client_code, session):
        """
        Rebuild display cache for an investor.
        
        Args:
            client_code: Internal client code (investor ID)
            session: SQLAlchemy session
        
        Returns:
            PortfolioDisplayCache instance
        """
        try:
            # Fetch all investments for this investor
            investments = session.query(Investment).filter(
                func.lower(Investment.internal_client_code) == func.lower(client_code)
            ).order_by(Investment.batch_id, Investment.fund_name).all()
            
            if not investments:
                logger.warning(f"No investments found for {client_code}")
                return None
            
            investor_name = investments[0].investor_name
            
            # Group by (batch_id, fund_name)
            holdings_map = {}
            total_principal = Decimal('0.00')
            
            for inv in investments:
                batch_id = inv.batch_id
                fund_name = (inv.fund.fund_name if inv.fund else inv.fund_name) or "Unknown"
                key = (batch_id, fund_name)
                
                if key not in holdings_map:
                    batch = session.query(Batch).filter(Batch.id == batch_id).first() if batch_id else None
                    holdings_map[key] = {
                        'batch_id': batch_id,
                        'batch_name': batch.batch_name if batch else "Unknown",
                        'fund_name': fund_name,
                        'fund_id': inv.fund_id,
                        'investments': [],
                        'principal': Decimal('0.00'),
                        'withdrawals': Decimal('0.00'),
                        'profit': Decimal('0.00'),
                        'end_balance': Decimal('0.00'),
                    }
                
                holdings_map[key]['investments'].append(inv)
                holdings_map[key]['principal'] += PortfolioDisplayAggregationService._safe_decimal(inv.net_principal)
                total_principal += PortfolioDisplayAggregationService._safe_decimal(inv.net_principal)
            
            # Calculate current balances and build display data
            batch_breakdown = []
            holdings_display = []
            funds_grouped = {}
            batch_ids_set = set()
            
            logger.info(f"\n=== PROCESSING HOLDINGS FOR {client_code} ===")
            logger.info(f"Holdings count: {len(holdings_map)}")
            
            for (batch_id, fund_name), holding in sorted(holdings_map.items()):
                batch_ids_set.add(batch_id)
                batch = session.query(Batch).filter(Batch.id == batch_id).first() if batch_id else None
                
                # Calculate current balance for this holding
                current_balance = Decimal('0.00')
                profit = Decimal('0.00')
                withdrawals = Decimal('0.00')
                performance_rate = Decimal('0.00')
                epoch_end = None
                start_balance = holding['principal']
                
                try:
                    # SSOT alignment: compute per-batch values via BatchController
                    # Statement is keyed by (investor_id, batch_id, fund_id, valuation_run_id)
                    # This is the source of truth for per-batch holdings
                    
                    from app.Batch.controllers import BatchController

                    # SSOT: compute per-investment batch values (EpochLedger + withdrawals)
                    # and aggregate them into this holding row.
                    opening_balance = Decimal('0.00')
                    current_balance = Decimal('0.00')
                    withdrawals = Decimal('0.00')
                    profit = Decimal('0.00')
                    performance_rate = Decimal('0.00')
                    epoch_end = None

                    for inv in holding['investments']:
                        inv_vals = BatchController._calculate_batch_investment_values(inv, batch, session)
                        opening_balance += PortfolioDisplayAggregationService._safe_decimal(inv_vals.get('opening_balance'))
                        current_balance += PortfolioDisplayAggregationService._safe_decimal(inv_vals.get('current_balance'))
                        profit += PortfolioDisplayAggregationService._safe_decimal(inv_vals.get('profit'))
                        withdrawals += PortfolioDisplayAggregationService._safe_decimal(inv_vals.get('withdrawals'))

                        try:
                            _, inv_epoch_end = BatchController._epoch_ledger_attributed_balance_and_epoch_end(inv, session)
                            if inv_epoch_end and (epoch_end is None or inv_epoch_end > epoch_end):
                                epoch_end = inv_epoch_end
                        except Exception:
                            pass

                    # ✅ ATOMIC BATCHING: Each batch maintains its own valuation independently
                    # Do NOT share EpochLedger rows between batches
                    # B001 (Jan deployed) → Jan epoch with profit
                    # B002 (Feb deployed) → Only if it has its own Feb epoch; otherwise principal only
                    
                    if opening_balance > Decimal('0.00'):
                        # Use profit from BatchController which already handles batch-specific calculations
                        # This ensures B001 and B002 are NOT combined
                        performance_rate = (profit / opening_balance) * 100
                        
                        # ✅ KEY: Log for debugging - profit should be from this batch's portfolio, not shared
                        logger.info(f"Batch {batch_id}: Principal ${float(opening_balance):.2f}, Profit ${float(profit):.2f}, Performance {float(performance_rate):.2f}%")
                    else:
                        performance_rate = Decimal('0.00')

                    if epoch_end is not None and hasattr(epoch_end, "isoformat"):
                        epoch_end = epoch_end.isoformat()
                
                except Exception as e:
                    logger.error(f"Error calculating values for {client_code}/{batch_id}/{fund_name}: {e}", exc_info=True)
                    current_balance = holding['principal']
                    opening_balance = holding['principal']
                    profit = Decimal('0.00')
                    withdrawals = Decimal('0.00')
                    performance_rate = Decimal('0.00')
                
                # Build batch breakdown entry
                batch_color = COLOR_PALETTE[batch_id % len(COLOR_PALETTE)] if batch_id else COLOR_PALETTE[0]
                batch_entry = {
                    'batch_id': batch_id,
                    'batch_name': holding['batch_name'],
                    'principal': float(holding['principal']),
                    'current_balance': float(current_balance),
                    'profit': float(current_balance - holding['principal']),
                    'color': batch_color,
                }
                batch_breakdown.append(batch_entry)
                
                # Build holdings table entry
                holdings_entry = {
                    'batch_id': batch_id,
                    'batch_name': holding['batch_name'],
                    'fund_name': fund_name,
                    'fund_id': holding['fund_id'],
                    'opening_amount': float(start_balance),
                    'withdrawals': float(withdrawals),
                    'current_standing': float(current_balance),
                    'profit': float(profit),
                    'performance': float(performance_rate),
                    'epoch_end': epoch_end,
                    'investments_count': len(holding['investments']),
                }
                holdings_display.append(holdings_entry)
                
                # Aggregate by fund
                if fund_name not in funds_grouped:
                    funds_grouped[fund_name] = {
                        'name': fund_name,
                        'fund_id': holding['fund_id'],
                        'principal': 0.0,
                        'current': 0.0,
                        'profit': 0.0,
                        'deposits': 0.0,
                        'withdrawals': 0.0,
                        'performance': 0.0,
                    }
                
                funds_grouped[fund_name]['principal'] += float(holding['principal'])
                funds_grouped[fund_name]['current'] += float(current_balance)
                funds_grouped[fund_name]['profit'] += float(profit)
                funds_grouped[fund_name]['withdrawals'] += float(withdrawals)
            
            # Calculate KPIs
            total_current_balance = Decimal(str(sum(
                PortfolioDisplayAggregationService._safe_decimal(h['current_standing']) 
                for h in holdings_display
            )))
            total_profit = total_current_balance - total_principal
            
            profit_percentage = Decimal('0.0')
            if total_principal > 0:
                profit_percentage = (total_profit / total_principal) * 100
            
            profit_trend = 'up' if total_profit > 0 else ('down' if total_profit < 0 else 'neutral')
            
            # Build fund allocation data
            fund_allocation = []
            total_for_pct = sum(f['current'] for f in funds_grouped.values())
            for fund_name, fund_data in sorted(funds_grouped.items()):
                pct = (fund_data['current'] / total_for_pct * 100) if total_for_pct > 0 else 0
                fund_allocation.append({
                    'name': fund_name,
                    'fund_id': fund_data['fund_id'],
                    'value': fund_data['current'],
                    'percentage': f"{pct:.2f}%",
                })
            
            # Get or create cache entry
            cache = session.query(PortfolioDisplayCache).filter(
                func.lower(PortfolioDisplayCache.client_code) == func.lower(client_code)
            ).first()
            
            if not cache:
                cache = PortfolioDisplayCache()
                cache.client_code = client_code
                session.add(cache)
            
            # Update cache
            cache.investor_name = investor_name
            cache.total_principal = total_principal
            cache.total_current_balance = total_current_balance
            cache.total_profit = total_profit
            cache.profit_percentage = profit_percentage
            cache.profit_trend = profit_trend
            cache.unique_batches = len(batch_ids_set)
            
            cache.batch_breakdown = json.dumps(batch_breakdown)
            cache.funds_grouped = json.dumps(funds_grouped)
            cache.holdings_display = json.dumps(holdings_display)
            cache.fund_allocation = json.dumps(fund_allocation)
            
            cache.updated_at = datetime.now(timezone.utc)
            
            session.commit()
            
            logger.info(f"✓ Rebuilt display cache for {client_code}: balance={total_current_balance}, profit={total_profit}")
            return cache
        
        except Exception as e:
            logger.error(f"Error rebuilding cache for {client_code}: {e}", exc_info=True)
            session.rollback()
            return None
    
    @staticmethod
    def get_display_data(client_code, session):
        """
        Fetch pre-computed display data from cache.
        
        Args:
            client_code: Internal client code
            session: SQLAlchemy session
        
        Returns:
            Dictionary with formatted display data or None
        """
        cache = session.query(PortfolioDisplayCache).filter(
            func.lower(PortfolioDisplayCache.client_code) == func.lower(client_code)
        ).first()
        
        if not cache:
            return None
        
        try:
            return {
                'kpis': {
                    'total_principal': float(cache.total_principal),
                    'total_current_balance': float(cache.total_current_balance),
                    'total_profit': float(cache.total_profit),
                    'profit_percentage': float(cache.profit_percentage),
                    'profit_trend': cache.profit_trend,
                    'unique_batches': cache.unique_batches,
                },
                'batch_breakdown': json.loads(cache.batch_breakdown) if cache.batch_breakdown else [],
                'holdings_display': json.loads(cache.holdings_display) if cache.holdings_display else [],
                'funds_grouped': json.loads(cache.funds_grouped) if cache.funds_grouped else {},
                'fund_allocation': json.loads(cache.fund_allocation) if cache.fund_allocation else [],
            }
        except Exception as e:
            logger.error(f"Error parsing cache for {client_code}: {e}")
            return None
