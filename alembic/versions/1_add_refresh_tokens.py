"""add refresh tokens table

Revision ID: 1_add_refresh_tokens
Revises: 9e413e918fa4
Create Date: 2025-06-20 22:30:00
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1'
down_revision = '9e413e918fa4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'refresh_tokens',
        sa.Column('token', sa.String(), primary_key=True),
        sa.Column('user_email', sa.String(), index=True),
        sa.Column('expires_at', sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table('refresh_tokens')
