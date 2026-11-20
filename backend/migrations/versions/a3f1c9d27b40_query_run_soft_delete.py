"""query_runs: soft delete (deleted_at, deleted_by)

Revision ID: a3f1c9d27b40
Revises: 5716f2628d5b
Create Date: 2026-11-11 12:40:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a3f1c9d27b40'
down_revision: str | None = '5716f2628d5b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('query_runs', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('query_runs', sa.Column('deleted_by', sa.Uuid(), nullable=True))
    op.create_foreign_key('query_runs_deleted_by_fkey', 'query_runs', 'users', ['deleted_by'], ['id'])


def downgrade() -> None:
    op.drop_constraint('query_runs_deleted_by_fkey', 'query_runs', type_='foreignkey')
    op.drop_column('query_runs', 'deleted_by')
    op.drop_column('query_runs', 'deleted_at')
