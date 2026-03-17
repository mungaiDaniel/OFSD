from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey, Boolean
from app.database.database import db
from base_model import Base
from datetime import datetime
from decimal import Decimal


class Fund(Base, db.Model):
    __tablename__ = 'funds'

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    fund_name = Column(String(100), nullable=False)  # e.g., 'Axiom', 'Atium'
    certificate_number = Column(String(100), nullable=False)  # Parent batch certificate
    total_capital = Column(Numeric(20, 2), default=0.00)  # Sum of all investments in this fund
    
    # Fund-specific dates and tracking
    date_deployed = Column(DateTime, nullable=False)  # Inherited from batch
    duration_days = Column(Integer, default=30)  # Inherited from batch
    date_closed = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Relationships
    batch = db.relationship('Batch', backref='funds')
    performance_records = db.relationship('FundPerformance', backref='fund', cascade="all, delete-orphan")

    @property
    def expected_close_date(self):
        """Calculate expected close date based on deployment date + duration"""
        from datetime import timedelta
        return self.date_deployed + timedelta(days=self.duration_days)

    @property
    def total_performance_value(self):
        """Calculate cumulative performance as percentage"""
        if not self.performance_records or len(self.performance_records) == 0:
            return Decimal('0.00')
        latest = self.performance_records[-1]  # Most recent performance
        return (latest.cumulative_profit / self.total_capital * 100) if self.total_capital > 0 else Decimal('0.00')

    def __repr__(self):
        return f'<Fund {self.fund_name} (Batch: {self.batch_id}) - Capital: {self.total_capital}>'


class FundPerformance(Base, db.Model):
    """Monthly (or periodic) performance records for each fund"""
    __tablename__ = 'fund_performances'

    id = Column(Integer, primary_key=True)
    fund_id = Column(Integer, ForeignKey('funds.id'), nullable=False)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    
    # Performance metrics
    gross_profit = Column(Numeric(20, 2), nullable=False, default=0.00)
    transaction_costs = Column(Numeric(20, 2), default=0.00)
    cumulative_profit = Column(Numeric(20, 2), default=0.00)  # Running total
    
    # Reporting period
    report_date = Column(DateTime, nullable=False)  # When this performance is recorded
    reporting_period = Column(String(20), default='MONTHLY')  # WEEKLY, MONTHLY, QUARTERLY
    
    # Relationships
    batch = db.relationship('Batch', backref='fund_performances')

    @property
    def net_profit(self):
        """Calculate net profit (gross - costs)"""
        return self.gross_profit - self.transaction_costs

    def __repr__(self):
        return f'<FundPerformance {self.fund_id} - {self.report_date.date()} - Net Profit: {self.net_profit}>'
