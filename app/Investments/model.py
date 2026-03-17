from sqlalchemy import Column, Integer, String, DateTime, Numeric, ForeignKey
from app.database.database import db
from base_model import Base
from datetime import datetime


class Investment(Base, db.Model):
    __tablename__ = 'investments'

    id = Column(Integer, primary_key=True)
    investor_name = Column(String(100), nullable=False)
    investor_email = Column(String(100), nullable=False)
    investor_phone = Column(String(20))
    internal_client_code = Column(String(50), unique=True)  # Unique ID from Excel
    amount_deposited = Column(Numeric(20, 2), nullable=False)
    date_deposited = Column(DateTime, nullable=False, default=datetime.utcnow)
    date_transferred = Column(DateTime, nullable=True)  # When actually transferred/deployed
    fund_name = Column(String(100), nullable=False, default='Default')  # e.g., 'Axiom', 'Atium'
    batch_id = Column(Integer, ForeignKey('batches.id'), nullable=False)
    fund_id = Column(Integer, ForeignKey('funds.id'), nullable=True)

    # Relationships
    batch = db.relationship('Batch', back_populates='investments')
    fund = db.relationship('Fund', backref='fund_investments')

    def __repr__(self):
        return f'<Investment {self.investor_name} ({self.internal_client_code}) - Fund: {self.fund_name} - {self.amount_deposited}>'
