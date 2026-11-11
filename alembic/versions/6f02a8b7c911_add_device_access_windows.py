"""Add configurable access windows and per-user after-hours override.

Revision ID: 6f02a8b7c911
Revises: d38ca9580d02
Create Date: 2026-10-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "6f02a8b7c911"
down_revision: Union[str, None] = "d38ca9580d02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("devices", sa.Column("access_window_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("devices", sa.Column("access_start_time", sa.Time(), nullable=False, server_default=sa.text("'07:00:00'")))
    op.add_column("devices", sa.Column("access_end_time", sa.Time(), nullable=False, server_default=sa.text("'17:00:00'")))
    op.add_column("permissions", sa.Column("allow_outside_schedule", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade() -> None:
    op.drop_column("permissions", "allow_outside_schedule")
    op.drop_column("devices", "access_end_time")
    op.drop_column("devices", "access_start_time")
    op.drop_column("devices", "access_window_enabled")
