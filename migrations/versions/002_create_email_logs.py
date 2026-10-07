"""Create email_logs table

Revision ID: 002_create_email_logs
Revises: 001_create_audit_logs
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_create_email_logs'
down_revision = '001_create_audit_logs'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'email_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('investor_id', sa.Integer(), sa.ForeignKey('investments.id'), nullable=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('batches.id'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('email_type', sa.String(50), nullable=True),
        sa.Column('recipient_count', sa.Integer(), nullable=True, default=0),
        sa.Column('success_count', sa.Integer(), nullable=True, default=0),
        sa.Column('failure_count', sa.Integer(), nullable=True, default=0),
        sa.Column('error_message', sa.String(512), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index(op.f('ix_email_logs_investor_id'), 'email_logs', ['investor_id'], unique=False)
    op.create_index(op.f('ix_email_logs_batch_id'), 'email_logs', ['batch_id'], unique=False)
    op.create_index(op.f('ix_email_logs_status'), 'email_logs', ['status'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_email_logs_status'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_batch_id'), table_name='email_logs')
    op.drop_index(op.f('ix_email_logs_investor_id'), table_name='email_logs')
    op.drop_table('email_logs')