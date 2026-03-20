"""Added columns for state, budget, move_in_date, lifestyle, activities, prefs to models.py & updated /updateUser in users.py.

Revision ID: a7b5b97fcdbc
Revises: 5b107a6ffbf2
Create Date: 2025-11-21 11:26:31.173356

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b5b97fcdbc'
down_revision: Union[str, None] = '5b107a6ffbf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('state', sa.String(), nullable=True))
    op.add_column('users', sa.Column('budget', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('move_in_date', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('lifestyle', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('activities', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('prefs', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'prefs')
    op.drop_column('users', 'activities')
    op.drop_column('users', 'lifestyle')
    op.drop_column('users', 'move_in_date')
    op.drop_column('users', 'budget')
    op.drop_column('users', 'state')
