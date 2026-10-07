"""Create portfolio_display_cache table

Revision ID: 004_create_portfolio_display_cache
Revises: 003_dedup_investor_batch_records
Create Date: 2026-04-16

This migration creates the portfolio_display_cache table for storing pre-computed
aggregations and display data for investor portfolio pages.

Run with: flask db upgrade
Rollback with: flask db downgrade
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_create_portfolio_display_cache'
down_revision = '003_dedup_investor_batch_records'
branch_labels = None
depends_on = None


def upgrade():
    # Create portfolio_display_cache table
    op.create_table(
        'portfolio_display_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_code', sa.String(50), nullable=False, unique=True),
        sa.Column('investor_name', sa.String(100), nullable=True),
        
        # KPI Totals
        sa.Column('total_principal', sa.Numeric(20, 2), nullable=False, server_default='0.00'),
        sa.Column('total_current_balance', sa.Numeric(20, 2), nullable=False, server_default='0.00'),
        sa.Column('total_profit', sa.Numeric(20, 2), nullable=False, server_default='0.00'),
        sa.Column('profit_percentage', sa.Numeric(10, 4), nullable=False, server_default='0.0000'),
        sa.Column('profit_trend', sa.String(10), nullable=False, server_default='neutral'),  # up, down, neutral
        sa.Column('unique_batches', sa.Integer(), nullable=False, server_default='0'),
        
        # Aggregated Data (JSON)
        sa.Column('batch_breakdown', sa.JSON(), nullable=True),  # Array of batch summaries
        sa.Column('funds_grouped', sa.JSON(), nullable=True),  # Object with fund aggregations
        sa.Column('holdings_display', sa.JSON(), nullable=True),  # Array for holdings table
        sa.Column('fund_allocation', sa.JSON(), nullable=True),  # Array for allocation chart
        
        # Metadata
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for performance
    op.create_index(op.f('ix_portfolio_display_cache_client_code'), 'portfolio_display_cache', ['client_code'], unique=True)
    op.create_index(op.f('ix_portfolio_display_cache_updated_at'), 'portfolio_display_cache', ['updated_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_portfolio_display_cache_updated_at'), table_name='portfolio_display_cache')
    op.drop_index(op.f('ix_portfolio_display_cache_client_code'), table_name='portfolio_display_cache')
    op.drop_table('portfolio_display_cache')
