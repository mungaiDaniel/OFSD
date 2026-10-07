"""
Report generation and distribution tracking models.

Tracks report runs (batches of statements generated) and their delivery status.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index, Boolean
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone


class ReportRun(Base, db.Model):
    """
    Represents a batch of reports generated and sent in a single operation.
    
    One ReportRun can contain multiple recipient reports (one per eligible investor).
    Tracks overall status and who initiated the run.
    """
    
    __tablename__ = "report_runs"
    
    id = Column(Integer, primary_key=True)
    period = Column(String(7), nullable=False)  # e.g. "2026-04"
    share_class_id = Column(Integer, ForeignKey("share_classes.id"), nullable=False)
    fund_id = Column(Integer, ForeignKey("core_funds.id"), nullable=False)
    
    # Metadata
    generated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    sent_by = Column(String(100), nullable=False)  # Email of user who initiated
    
    # Counts
    recipient_count = Column(Integer, nullable=False, default=0)  # Total recipients
    delivered_count = Column(Integer, nullable=False, default=0)  # Successfully delivered
    failed_count = Column(Integer, nullable=False, default=0)    # Failed to deliver
    pending_count = Column(Integer, nullable=False, default=0)   # Still pending
    
    # Overall status
    status = Column(String(20), nullable=False, default="pending")  # pending|sent|partial|failed
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("ix_report_runs_period", "period"),
        Index("ix_report_runs_fund_class", "fund_id", "share_class_id"),
    )
    
    # Relationships
    recipients = db.relationship("ReportRecipient", back_populates="report_run", cascade="all, delete-orphan")
    fund = db.relationship("CoreFund", backref="report_runs")
    share_class = db.relationship("ShareClass", backref="report_runs")
    
    def __repr__(self):
        return f"<ReportRun period={self.period} status={self.status} recipients={self.recipient_count}>"


class ReportRecipient(Base, db.Model):
    """
    Tracks a single recipient (investor) in a report run.
    
    Records email delivery status and whether the report was opened/viewed.
    """
    
    __tablename__ = "report_recipients"
    
    id = Column(Integer, primary_key=True)
    report_run_id = Column(Integer, ForeignKey("report_runs.id"), nullable=False)
    investor_id = Column(Integer, ForeignKey("investments.id"), nullable=False)
    
    # Email details
    investor_email = Column(String(100), nullable=False)
    
    # Delivery status
    delivery_status = Column(String(20), nullable=False, default="pending")  # pending|delivered|failed
    delivery_error = Column(String(500), nullable=True)  # Error message if failed
    
    # Tracking
    opened = Column(Boolean, nullable=False, default=False)  # Did investor open/view the PDF?
    opened_at = Column(DateTime(timezone=True), nullable=True)  # When did they open it?
    
    # PDF details
    pdf_url = Column(String(500), nullable=True)  # S3 or CDN URL for PDF download
    pdf_generated_at = Column(DateTime(timezone=True), nullable=True)  # When PDF was generated
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        UniqueConstraint("report_run_id", "investor_id", name="_report_recipient_run_investor_uc"),
        Index("ix_report_recipients_status", "delivery_status"),
    )
    
    # Relationships
    report_run = db.relationship("ReportRun", back_populates="recipients")
    investment = db.relationship("Investment", backref="report_recipients")
    
    def __repr__(self):
        return f"<ReportRecipient run={self.report_run_id} investor={self.investor_id} status={self.delivery_status}>"
