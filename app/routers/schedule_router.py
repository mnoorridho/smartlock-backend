import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/schedules", tags=["Presensi - Jadwal"])


def _to_out(db: Session, s: models.Schedule) -> schemas.ScheduleOut:
    assignment = db.get(models.CourseAssignment, s.course_assignment_id)
    course = db.get(models.Course, assignment.course_id) if assignment else None
    rombel = db.get(models.Rombel, assignment.rombel_id) if assignment else None
    dosen = db.get(models.User, assignment.dosen_id) if assignment else None
    device = db.get(models.Device, s.device_id)
    period = db.get(models.AcademicPeriod, assignment.academic_period_id) if assignment else None

    return schemas.ScheduleOut(
        id=s.id,
        course_assignment_id=s.course_assignment_id,
        course_kode=course.kode if course else "-",
        course_nama=course.nama if course else "-",
        rombel_nama=rombel.nama if rombel else "-",
        dosen_nama=dosen.name if dosen else "-",
        device_id=s.device_id,
        device_name=device.name if device else "-",
        tahun_ajaran=period.tahun_ajaran if period else "-",
        semester=period.semester if period else None,
        is_period_active=bool(period and period.is_active),
        periode_tanggal_mulai=period.tanggal_mulai if period else None,
        periode_tanggal_selesai=period.tanggal_selesai if period else None,
        hari=s.hari,
        jam_mulai=s.jam_mulai,
        jam_selesai=s.jam_selesai,
        created_at=s.created_at,
    )


def _periods_overlap(a: models.AcademicPeriod, b: models.AcademicPeriod) -> bool:
    if not a or not b:
        # Data lama yang rusak tidak boleh membuat validasi jatuh/crash.
        return True
    return a.tanggal_mulai <= b.tanggal_selesai and b.tanggal_mulai <= a.tanggal_selesai


def _check_conflict(
    db: Session,
    hari,
    jam_mulai,
    jam_selesai,
    device_id: str,
    dosen_id: str,
    rombel_id: str,
    academic_period_id: str,
):
    """Cek bentrok ruangan, dosen, dan rombel hanya untuk periode akademik
    yang tanggalnya saling overlap. Jadwal semester ganjil dan genap yang
    berbeda periode tidak seharusnya saling memblokir meskipun hari/jam dan
    ruangnya sama."""
    new_period = db.get(models.AcademicPeriod, academic_period_id)

    same_day = db.query(models.Schedule).filter(models.Schedule.hari == hari).all()
    for s in same_day:
        overlap = jam_mulai < s.jam_selesai and s.jam_mulai < jam_selesai
        if not overlap:
            continue

        assignment = db.get(models.CourseAssignment, s.course_assignment_id)
        if not assignment:
            continue
        existing_period = db.get(models.AcademicPeriod, assignment.academic_period_id)
        if not _periods_overlap(new_period, existing_period):
            continue

        if s.device_id == device_id:
            raise HTTPException(
                status_code=409,
                detail=f"Bentrok RUANGAN: ruangan ini sudah dipakai jadwal lain di jam {s.jam_mulai}-{s.jam_selesai} hari {hari.value} pada periode yang tanggalnya bertabrakan.",
            )

        if assignment.dosen_id == dosen_id:
            raise HTTPException(
                status_code=409,
                detail=f"Bentrok DOSEN: dosen ini sudah punya jadwal lain di jam {s.jam_mulai}-{s.jam_selesai} hari {hari.value} pada periode yang tanggalnya bertabrakan.",
            )
        if assignment.rombel_id == rombel_id:
            raise HTTPException(
                status_code=409,
                detail=f"Bentrok ROMBEL: rombel ini sudah punya jadwal lain di jam {s.jam_mulai}-{s.jam_selesai} hari {hari.value} pada periode yang tanggalnya bertabrakan.",
            )


@router.post("/", response_model=schemas.ScheduleOut, status_code=201)
def create_schedule(
    payload: schemas.ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    assignment = db.get(models.CourseAssignment, payload.course_assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="course_assignment_id (pengampu) tidak ditemukan")
    device = db.get(models.Device, payload.device_id)
    if not device:
        raise HTTPException(status_code=404, detail="device_id (ruangan) tidak ditemukan")

    _check_conflict(
        db, payload.hari, payload.jam_mulai, payload.jam_selesai,
        payload.device_id, assignment.dosen_id, assignment.rombel_id, assignment.academic_period_id,
    )

    schedule = models.Schedule(
        id=str(uuid.uuid4()),
        course_assignment_id=payload.course_assignment_id,
        device_id=payload.device_id,
        hari=payload.hari,
        jam_mulai=payload.jam_mulai,
        jam_selesai=payload.jam_selesai,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _to_out(db, schedule)


@router.get("/", response_model=list[schemas.ScheduleOut])
def list_schedules(
    device_id: str = None,
    course_assignment_id: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Bisa difilter ?device_id=... (jadwal 1 ruangan) atau ?course_assignment_id=..."""
    query = db.query(models.Schedule)
    if device_id:
        query = query.filter(models.Schedule.device_id == device_id)
    if course_assignment_id:
        query = query.filter(models.Schedule.course_assignment_id == course_assignment_id)

    schedules = query.all()
    # urut manual by (hari, jam_mulai) -- SQLAlchemy Enum ordering di Postgres
    # ikut urutan definisi enum-nya sendiri, yang kebetulan sudah senin->minggu
    hari_order = {d: i for i, d in enumerate(models.DayOfWeek)}
    schedules.sort(key=lambda s: (hari_order[s.hari], s.jam_mulai))
    return [_to_out(db, s) for s in schedules]


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    schedule = db.get(models.Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Jadwal tidak ditemukan")

    # Presensi yang udah kejadian tetap disimpan sebagai riwayat (sama
    # prinsipnya kayak access_logs) -- cuma LINK ke jadwal ini yang diputus,
    # biar gak kena error foreign key.
    db.query(models.Attendance).filter(models.Attendance.schedule_id == schedule_id).update(
        {models.Attendance.schedule_id: None}
    )
    db.delete(schedule)
    db.commit()
    return None
