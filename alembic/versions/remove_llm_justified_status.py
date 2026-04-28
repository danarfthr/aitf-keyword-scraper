"""remove llm_justified status

Revision ID: remove_llm_justified_status
Revises: 3dac2b7d80bb_initial_schema
Create Date: 2026-04-28

"""
from alembic import op
import sqlalchemy as sa


revision = 'remove_llm_justified_status'
down_revision = '3dac2b7d80bb'
branch_labels = None
depends_on = None


def upgrade():
    # Update any existing LLM_JUSTIFIED keywords to EXPIRED before dropping the status
    op.execute("UPDATE keywords SET status = 'expired' WHERE status = 'llm_justified'")


def downgrade():
    # No going back — this is a one-way migration removing a deprecated status
    pass
