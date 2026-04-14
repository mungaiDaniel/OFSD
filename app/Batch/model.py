from app.database.database import db
from base_model import Base
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric


from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, UniqueConstraint

class Batch(Base, db.Model):
    __tablename__ = 'batches'
    __table_args__ = (
        UniqueConstraint('batch_name', name='uq_batches_batch_name'),
    )
    
    id = Column(Integer, primary_key=True)
    batch_name = Column(String(100), nullable=False)
    certificate_number = Column(String(100), unique=True, nullable=True)
    total_principal = Column(Numeric(20, 2), default=0.00)
    date_deployed = Column(DateTime, nullable=True)
    duration_days = Column(Integer, default=30)
    date_closed = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=False)  # Changed from True to False for new batches
    is_transferred = Column(Boolean, default=False)
    deployment_confirmed = Column(Boolean, default=False)  # Tracks Stage 3 confirmation
    stage = Column(Integer, default=1)  # Current stage: 1=Deposited, 2=Transferred, 3=Deployed, 4=Active

    # Relationships
    performance = db.relationship('Performance', foreign_keys='Performance.batch_id', uselist=False, back_populates='batch', overlaps="performance_records")
    investments = db.relationship('Investment', foreign_keys='Investment.batch_id', back_populates='batch')

    @property
    def expected_close_date(self):
        """Calculate expected close date based on deployment date + duration. Returns None if date_deployed is None."""
        if self.date_deployed is None:
            return None
        deployed = self.date_deployed
        # Ensure timezone-aware for comparison with other timezone-aware datetimes
        if deployed.tzinfo is None:
            deployed = deployed.replace(tzinfo=timezone.utc)
        return deployed + timedelta(days=self.duration_days)

    def __repr__(self):
        return f'<Batch {self.batch_name} - {self.certificate_number}>'