"""remove legacy academic and attendance tables

Revision ID: b7e26c4d91a0
Revises: 6f02a8b7c911
Create Date: 2026-10-24 02:45:00.000000

This drops only tables/column used by the retired academic attendance feature.
Users, devices, permissions, NFC cards, guest access, and access logs are kept.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7e26c4d91a0"
down_revision: Union[str, None] = "6f02a8b7c911"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # Drop children before parents to respect foreign-key dependencies.
    for table in (
        "attendances",
        "schedules",
        "course_assignments",
        "rombel_members",
        "rombels",
        "courses",
        "academic_periods",
    ):
        if table in tables:
            op.drop_table(table)

    inspector = sa.inspect(bind)
    if "users" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "academic_role" in cols:
            op.drop_column("users", "academic_role")

    # PostgreSQL enum types are independent schema objects; drop after dependent
    # tables/columns are gone. checkfirst makes this safe across existing DB states.
    if bind.dialect.name == "postgresql":
        for enum_name in ("attendancestatus", "dayofweek", "semestertype", "academicrole"):
            op.execute(f"DROP TYPE IF EXISTS {enum_name}")


def downgrade() -> None:
    # Recreate the old schema empty (data removed by upgrade cannot be restored).
    bind = op.get_bind()
    academic_role = sa.Enum("mahasiswa", "dosen", name="academicrole")
    semester_type = sa.Enum("ganjil", "genap", name="semestertype")
    day_of_week = sa.Enum("senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu", name="dayofweek")
    attendance_status = sa.Enum("hadir", "tidak_hadir", name="attendancestatus")
    for typ in (academic_role, semester_type, day_of_week, attendance_status):
        typ.create(bind, checkfirst=True)

    inspector = sa.inspect(bind)
    if "academic_role" not in {c["name"] for c in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("academic_role", academic_role, nullable=True))

    op.create_table(
        "academic_periods",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tahun_ajaran", sa.String(length=9), nullable=False),
        sa.Column("semester", semester_type, nullable=False),
        sa.Column("tanggal_mulai", sa.Date(), nullable=False),
        sa.Column("tanggal_selesai", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tahun_ajaran", "semester", name="uq_period_tahun_semester"),
    )
    op.create_table(
        "courses",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kode", sa.String(length=20), nullable=False, unique=True),
        sa.Column("nama", sa.String(length=150), nullable=False),
        sa.Column("sks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "rombels",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("dosen_wali_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "rombel_members",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("rombel_id", sa.String(), sa.ForeignKey("rombels.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rombel_id", "user_id", name="uq_rombel_member"),
    )
    op.create_table(
        "course_assignments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("academic_period_id", sa.String(), sa.ForeignKey("academic_periods.id"), nullable=False),
        sa.Column("rombel_id", sa.String(), sa.ForeignKey("rombels.id"), nullable=False),
        sa.Column("course_id", sa.String(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("dosen_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("semester_ke", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("academic_period_id", "rombel_id", "course_id", name="uq_assignment_period_rombel_course"),
    )
    op.create_table(
        "schedules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("course_assignment_id", sa.String(), sa.ForeignKey("course_assignments.id"), nullable=False),
        sa.Column("device_id", sa.String(), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("hari", day_of_week, nullable=False),
        sa.Column("jam_mulai", sa.Time(), nullable=False),
        sa.Column("jam_selesai", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "attendances",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("schedule_id", sa.String(), sa.ForeignKey("schedules.id"), nullable=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tanggal", sa.Date(), nullable=False),
        sa.Column("status", attendance_status, nullable=False, server_default="hadir"),
        sa.Column("waktu_masuk", sa.DateTime(), nullable=True),
        sa.Column("access_log_id", sa.String(), sa.ForeignKey("access_logs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("schedule_id", "user_id", "tanggal", name="uq_attendance_schedule_user_date"),
    )
