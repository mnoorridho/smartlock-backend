"""add nfc value to accessmethod enum

Revision ID: a720664181da
Revises: 65955ba89307
Create Date: 2026-09-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a720664181da'
down_revision: Union[str, None] = '65955ba89307'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum AccessMethod di Python (app/models.py) selama ini cuma punya
    # password/face/qr/manual -- akibatnya SEMUA unlock (termasuk yang lewat
    # verifikasi NFC di aplikasi) tercatat sebagai "manual" di access_logs,
    # karena tipe enum di database ("accessmethod") juga cuma punya 4 value
    # itu dan bakal ERROR kalau dipaksa insert value lain.
    #
    # ALTER TYPE ... ADD VALUE tidak bisa langsung dipakai di transaksi yang
    # sama dengan migration ini (batasan PostgreSQL) -- tapi aman dipakai
    # setelah migration ini selesai commit (yaitu pas aplikasi jalan normal),
    # jadi tidak perlu langkah tambahan.
    op.execute("ALTER TYPE accessmethod ADD VALUE IF NOT EXISTS 'nfc'")


def downgrade() -> None:
    # PostgreSQL TIDAK mendukung menghapus satu value dari enum type secara
    # langsung (butuh rebuild total tipe + semua kolom yang memakainya).
    # Downgrade untuk migration jenis "tambah value enum" sengaja dikosongkan
    # -- ini pola umum, bukan kelalaian.
    pass
