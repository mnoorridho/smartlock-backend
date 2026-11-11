"""add academic attendance management tables

Revision ID: d38ca9580d02
Revises: a720664181da
Create Date: 2026-09-08 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd38ca9580d02'
down_revision: Union[str, None] = 'a720664181da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Kolom baru di tabel users: academic_role (mahasiswa/dosen/null)
    # ------------------------------------------------------------------
    academic_role_enum = sa.Enum('mahasiswa', 'dosen', name='academicrole')
    academic_role_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'users',
        sa.Column('academic_role', academic_role_enum, nullable=True),
    )

    # ------------------------------------------------------------------
    # academic_periods
    # ------------------------------------------------------------------
    op.create_table(
        'academic_periods',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('tahun_ajaran', sa.String(length=9), nullable=False),
        sa.Column('semester', sa.Enum('ganjil', 'genap', name='semestertype'), nullable=False),
        sa.Column('tanggal_mulai', sa.Date(), nullable=False),
        sa.Column('tanggal_selesai', sa.Date(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tahun_ajaran', 'semester', name='uq_period_tahun_semester'),
    )

    # ------------------------------------------------------------------
    # courses
    # ------------------------------------------------------------------
    op.create_table(
        'courses',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('kode', sa.String(length=20), nullable=False, unique=True),
        sa.Column('nama', sa.String(length=150), nullable=False),
        sa.Column('sks', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # rombels
    # ------------------------------------------------------------------
    op.create_table(
        'rombels',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('nama', sa.String(length=100), nullable=False),
        sa.Column('dosen_wali_id', sa.String(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # rombel_members
    # ------------------------------------------------------------------
    op.create_table(
        'rombel_members',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('rombel_id', sa.String(), sa.ForeignKey('rombels.id'), nullable=False),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('rombel_id', 'user_id', name='uq_rombel_member'),
    )

    # ------------------------------------------------------------------
    # course_assignments (Pengampu Mata Kuliah)
    # ------------------------------------------------------------------
    op.create_table(
        'course_assignments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('academic_period_id', sa.String(), sa.ForeignKey('academic_periods.id'), nullable=False),
        sa.Column('rombel_id', sa.String(), sa.ForeignKey('rombels.id'), nullable=False),
        sa.Column('course_id', sa.String(), sa.ForeignKey('courses.id'), nullable=False),
        sa.Column('dosen_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('semester_ke', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            'academic_period_id', 'rombel_id', 'course_id',
            name='uq_assignment_period_rombel_course',
        ),
    )

    # ------------------------------------------------------------------
    # schedules (Jadwal)
    # ------------------------------------------------------------------
    op.create_table(
        'schedules',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('course_assignment_id', sa.String(), sa.ForeignKey('course_assignments.id'), nullable=False),
        sa.Column('device_id', sa.String(), sa.ForeignKey('devices.id'), nullable=False),
        sa.Column('hari', sa.Enum(
            'senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu', 'minggu',
            name='dayofweek',
        ), nullable=False),
        sa.Column('jam_mulai', sa.Time(), nullable=False),
        sa.Column('jam_selesai', sa.Time(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # attendances (Presensi)
    # ------------------------------------------------------------------
    op.create_table(
        'attendances',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('schedule_id', sa.String(), sa.ForeignKey('schedules.id'), nullable=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('tanggal', sa.Date(), nullable=False),
        sa.Column('status', sa.Enum('hadir', 'tidak_hadir', name='attendancestatus'), nullable=False, server_default='hadir'),
        sa.Column('waktu_masuk', sa.DateTime(), nullable=True),
        sa.Column('access_log_id', sa.String(), sa.ForeignKey('access_logs.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('schedule_id', 'user_id', 'tanggal', name='uq_attendance_schedule_user_date'),
    )


def downgrade() -> None:
    op.drop_table('attendances')
    op.drop_table('schedules')
    op.drop_table('course_assignments')
    op.drop_table('rombel_members')
    op.drop_table('rombels')
    op.drop_table('courses')
    op.drop_table('academic_periods')
    op.drop_column('users', 'academic_role')

    # Bersihin enum type-nya juga (Postgres nyimpen enum sebagai tipe
    # terpisah, gak otomatis kehapus pas kolom/tabel yang makainya dihapus)
    bind = op.get_bind()
    sa.Enum(name='attendancestatus').drop(bind, checkfirst=True)
    sa.Enum(name='dayofweek').drop(bind, checkfirst=True)
    sa.Enum(name='semestertype').drop(bind, checkfirst=True)
    sa.Enum(name='academicrole').drop(bind, checkfirst=True)
