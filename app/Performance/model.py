from sqlalchemy import Column, Integer, Numeric, ForeignKey, DateTime, String
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone
from decimal import Decimal


class Performance(Base, db.Model):
    __tablename__ = 'performance'

    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    fund_name = Column(String(100), nullable=True)  # Link to specific fund within batch
    gross_profit = Column(Numeric(20, 2), nullable=False)
    transaction_costs = Column(Numeric(20, 2), default=0.00)
    report_date = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    batch = db.relationship('Batch', back_populates='performance', overlaps="performance_records")

    @property
    def net_profit(self):
        """Calculate net profit (gross - costs)"""
        return self.gross_profit - self.transaction_costs

    def __repr__(self):
        return f'<Performance Batch {self.batch_id} Fund {self.fund_name} - Net Profit: {self.net_profit}>'
