"""Owner-controlled per-user access methods. Existing quick access stays denied."""
from alembic import op
import sqlalchemy as sa

revision = 'e18b6a2d0419'
down_revision = 'c4d91e830af2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('permissions', sa.Column('allow_face', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('permissions', sa.Column('allow_nfc', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('permissions', sa.Column('allow_quick', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('permissions', 'allow_quick')
    op.drop_column('permissions', 'allow_nfc')
    op.drop_column('permissions', 'allow_face')
