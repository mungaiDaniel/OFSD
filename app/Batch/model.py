from app.database.database import db
from base_model import Base
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric


class Batch(Base, db.Model):
    __tablename__ = 'batches'
    
    id = Column(Integer, primary_key=True)
    batch_name = Column(String(100), nullable=False)
    certificate_number = Column(String(100), unique=True, nullable=True)
    total_principal = Column(Numeric(20, 2), default=0.00)
    date_deployed = Column(DateTime, nullable=True)
    duration_days = Column(Integer, default=30)
    date_closed = Column(DateTime)
    is_active = Column(Boolean, default=True)
    is_transferred = Column(Boolean, default=False)

    # Relationships
    performance = db.relationship('Performance', foreign_keys='Performance.batch_id', uselist=False, back_populates='batch', overlaps="performance_records")
    investments = db.relationship('Investment', foreign_keys='Investment.batch_id', back_populates='batch')

    @property
    def expected_close_date(self):
        """Calculate expected close date based on deployment date + duration"""
        return self.date_deployed + timedelta(days=self.duration_days)

    def __repr__(self):
        return f'<Batch {self.batch_name} - {self.certificate_number}>'