from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from app.database.database import db
from base_model import Base
from datetime import datetime, timezone
import json


class UploadColumnMapping(Base, db.Model):
    """
    Remembers a user's last column mapping for a given "shape" of upload file
    (identified by template_key, a hash of the sorted/normalized source
    header names — see _template_key() in route.py) so a repeat upload of a
    similarly-shaped file skips the manual mapping step.
    """

    __tablename__ = "upload_column_mappings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    template_key = Column(String(64), nullable=False)
    source_headers = Column(Text, nullable=False)
    mapping_json = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("user_id", "template_key", name="_upload_mapping_user_template_uc"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "template_key": self.template_key,
            "source_headers": json.loads(self.source_headers) if self.source_headers else [],
            "mapping": json.loads(self.mapping_json) if self.mapping_json else {},
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BulkUploadJob(Base, db.Model):
    """
    Tracks a bulk-upload commit that runs as a background job instead of
    inline in the request — a 100,000-row commit takes too long (and does
    too much per-row work: batch assignment, a PendingEmail row, an audit log
    entry) to hold one HTTP request open for. See app/BulkUpload/route.py's
    commit_rows()/_run_bulk_upload_commit_job() for how this gets driven.

    status: 'queued' -> 'running' -> 'completed' | 'failed'
    rows_payload holds the exact request body (validated rows the admin
    confirmed) so the background worker has everything it needs without the
    request that created the job still being open.
    """

    __tablename__ = "bulk_upload_jobs"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="queued")

    total_rows = Column(Integer, nullable=False, default=0)
    processed_rows = Column(Integer, nullable=False, default=0)
    succeeded_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)

    rows_payload = Column(Text, nullable=False)
    results_payload = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_by_user_id = Column(Integer, nullable=True)
    created_by_email = Column(String(120), nullable=True)
    created_by_name = Column(String(120), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<BulkUploadJob {self.id} {self.status} {self.processed_rows}/{self.total_rows}>"
