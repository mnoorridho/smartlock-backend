import uuid
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/attendances", tags=["Presensi - Rekap"])


def _to_out(db: Session, a: models.Attendance) -> schemas.AttendanceOut:
    user = db.get(models.User, a.user_id)
    schedule = db.get(models.Schedule, a.schedule_id) if a.schedule_id else None
    assignment = db.get(models.CourseAssignment, schedule.course_assignment_id) if schedule else None
    course = db.get(models.Course, assignment.course_id) if assignment else None
    rombel = db.get(models.Rombel, assignment.rombel_id) if assignment else None
    access_log = db.get(models.AccessLog, a.access_log_id) if a.access_log_id else None
    source = access_log.method.value.upper() if access_log and access_log.method else "MANUAL"
    otomatis = bool(access_log and access_log.method in {models.AccessMethod.nfc, models.AccessMethod.face})

    return schemas.AttendanceOut(
        id=a.id,
        schedule_id=a.schedule_id,
        user_id=a.user_id,
        user_name=user.name if user else "-",
        tanggal=a.tanggal,
        status=a.status,
        waktu_masuk=a.waktu_masuk,
        course_kode=course.kode if course else "(jadwal dihapus)",
        course_nama=course.nama if course else "(jadwal dihapus)",
        rombel_nama=rombel.nama if rombel else "-",
        access_log_id=a.access_log_id,
        sumber=source,
        otomatis=otomatis,
    )


@router.get("/", response_model=list[schemas.AttendanceOut])
def list_attendances(
    schedule_id: str = None,
    user_id: str = None,
    rombel_id: str = None,
    tanggal: date_type = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Rekap presensi, bisa difilter kombinasi:
    ?schedule_id=... (1 sesi kelas spesifik)
    ?user_id=... (riwayat 1 orang -- dosen/mahasiswa lihat punya sendiri)
    ?rombel_id=... (semua presensi 1 rombel, lintas mata kuliah)
    ?tanggal=YYYY-MM-DD (1 hari spesifik)

    User biasa (bukan owner) HANYA bisa lihat presensi miliknya sendiri --
    kalau dia coba filter user_id milik orang lain, otomatis diabaikan
    dan tetap dikembalikan punya dia sendiri saja.
    """
    query = db.query(models.Attendance)

    if current_user.role != models.UserRole.owner:
        query = query.filter(models.Attendance.user_id == current_user.id)
    elif user_id:
        query = query.filter(models.Attendance.user_id == user_id)

    if schedule_id:
        query = query.filter(models.Attendance.schedule_id == schedule_id)
    if tanggal:
        query = query.filter(models.Attendance.tanggal == tanggal)

    if rombel_id:
        # rombel_id gak ada langsung di tabel attendances -- join lewat schedule -> course_assignment
        schedule_ids = [
            s.id for s in (
                db.query(models.Schedule)
                .join(models.CourseAssignment, models.Schedule.course_assignment_id == models.CourseAssignment.id)
                .filter(models.CourseAssignment.rombel_id == rombel_id)
                .all()
            )
        ]
        query = query.filter(models.Attendance.schedule_id.in_(schedule_ids))

    records = query.order_by(models.Attendance.tanggal.desc(), models.Attendance.waktu_masuk.desc()).all()
    return [_to_out(db, a) for a in records]


@router.post("/manual", response_model=schemas.AttendanceOut, status_code=201)
def create_manual_attendance(
    payload: schemas.AttendanceManualCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    """Tandai kehadiran manual -- buat kasus edge (mis. mahasiswa hadir
    tapi lupa/gak sempat unlock sendiri, atau ada masalah teknis di device
    pas jam kelas). Dipakai OWNER (atau nanti bisa dibuka juga ke dosen
    pengampu, kalau perlu -- untuk sekarang dibatasi owner dulu)."""
    schedule = db.get(models.Schedule, payload.schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")
    user = db.get(models.User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan")

    existing = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.schedule_id == payload.schedule_id,
            models.Attendance.user_id == payload.user_id,
            models.Attendance.tanggal == payload.tanggal,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Presensi untuk jadwal, user, dan tanggal ini sudah ada")

    # Presensi manual tetap menjadi fallback; tidak mengisi access_log_id sehingga
    # dashboard bisa membedakan manual vs presensi otomatis.
    attendance = models.Attendance(
        id=str(uuid.uuid4()),
        schedule_id=payload.schedule_id,
        user_id=payload.user_id,
        tanggal=payload.tanggal,
        status=payload.status,
        waktu_masuk=None,
        access_log_id=None,
    )
    db.add(attendance)
    db.commit()
    db.refresh(attendance)
    return _to_out(db, attendance)


@router.delete("/{attendance_id}", status_code=204)
def delete_attendance(
    attendance_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    attendance = db.get(models.Attendance, attendance_id)
    if not attendance:
        raise HTTPException(status_code=404, detail="Data presensi tidak ditemukan")
    db.delete(attendance)
    db.commit()
    return None
