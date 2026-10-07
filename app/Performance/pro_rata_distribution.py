from sqlalchemy import Column, Integer, Numeric, ForeignKey, DateTime, String
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone


class ProRataDistribution(Base, db.Model):
    __tablename__ = 'pro_rata_distributions'

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    fund_id = Column(Integer, ForeignKey('core_funds.id'), nullable=True)
    fund_name = Column(String(100), nullable=False)
    investment_id = Column(Integer, ForeignKey('investments.id'), nullable=False)
    performance_id = Column(Integer, ForeignKey('performance.id'), nullable=False)
    
    # Calculation date (for weekly recalculations)
    calculation_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Days active (recalculated for live weekly updates)
    days_active = Column(Integer)
    
    # Weighted capital calculations
    weighted_capital = Column(Numeric(20, 2))
    profit_share_percentage = Column(Numeric(10, 4))
    
    # Final allocation
    profit_allocated = Column(Numeric(20, 2))
    
    # Investor details (denormalized for quick reporting)
    internal_client_code = Column(String(50))
    investor_name = Column(String(100))

    # Relationships
    batch = db.relationship('Batch', backref='distributions')
    fund = db.relationship('CoreFund', backref='pro_rata_distributions')
    investment = db.relationship('Investment', backref='pro_rata_distributions')
    performance = db.relationship('Performance', backref='distributions')

    def __repr__(self):
        return f'<ProRataDistribution Fund {self.fund_name} Investment {self.investment_id} - Profit: {self.profit_allocated}>'
