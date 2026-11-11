"""Add owner-enrolled face references; does not change existing account rows."""
from alembic import op
import sqlalchemy as sa

revision = "c4d91e830af2"
down_revision = "b7e26c4d91a0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "face_profiles",
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("descriptors", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("registered_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("face_profiles")
