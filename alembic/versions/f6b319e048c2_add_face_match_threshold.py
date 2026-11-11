"""Per-owner/device user face matching threshold."""
from alembic import op
import sqlalchemy as sa
revision = 'f6b319e048c2'
down_revision = 'e18b6a2d0419'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('permissions', sa.Column('face_match_threshold', sa.Float(), nullable=False, server_default='0.45'))

def downgrade():
    op.drop_column('permissions', 'face_match_threshold')
