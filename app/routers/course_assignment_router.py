import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/course-assignments", tags=["Presensi - Pengampu Mata Kuliah"])


def _to_out(db: Session, a: models.CourseAssignment) -> schemas.CourseAssignmentOut:
    period = db.get(models.AcademicPeriod, a.academic_period_id)
    rombel = db.get(models.Rombel, a.rombel_id)
    course = db.get(models.Course, a.course_id)
    dosen = db.get(models.User, a.dosen_id)
    return schemas.CourseAssignmentOut(
        id=a.id,
        academic_period_id=a.academic_period_id,
        tahun_ajaran=f"{period.tahun_ajaran} ({period.semester.value})" if period else "-",
        rombel_id=a.rombel_id,
        rombel_nama=rombel.nama if rombel else "-",
        course_id=a.course_id,
        course_kode=course.kode if course else "-",
        course_nama=course.nama if course else "-",
        dosen_id=a.dosen_id,
        dosen_nama=dosen.name if dosen else "-",
        semester_ke=a.semester_ke,
        created_at=a.created_at,
    )


@router.post("/", response_model=schemas.CourseAssignmentOut, status_code=201)
def create_assignment(
    payload: schemas.CourseAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    period = db.get(models.AcademicPeriod, payload.academic_period_id)
    if not period:
        raise HTTPException(status_code=404, detail="academic_period_id tidak ditemukan")

    expected_semester = (
        models.SemesterType.ganjil if payload.semester_ke % 2 == 1
        else models.SemesterType.genap
    )
    if period.semester != expected_semester:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Semester ke-{payload.semester_ke} tidak sesuai dengan periode "
                f"{period.tahun_ajaran} semester {period.semester.value}. "
                f"Semester ganjil hanya boleh nomor ganjil (1,3,5,...), "
                f"semester genap hanya boleh nomor genap (2,4,6,...)."
            ),
        )
    if not db.get(models.Rombel, payload.rombel_id):
        raise HTTPException(status_code=404, detail="rombel_id tidak ditemukan")
    if not db.get(models.Course, payload.course_id):
        raise HTTPException(status_code=404, detail="course_id tidak ditemukan")

    dosen = db.query(models.User).filter(models.User.email == payload.dosen_email).first()
    if not dosen:
        raise HTTPException(status_code=404, detail="Dosen dengan email ini belum terdaftar di sistem")

    existing = (
        db.query(models.CourseAssignment)
        .filter(
            models.CourseAssignment.academic_period_id == payload.academic_period_id,
            models.CourseAssignment.rombel_id == payload.rombel_id,
            models.CourseAssignment.course_id == payload.course_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Kombinasi periode + rombel + mata kuliah ini sudah ada pengampunya",
        )

    assignment = models.CourseAssignment(
        id=str(uuid.uuid4()),
        academic_period_id=payload.academic_period_id,
        rombel_id=payload.rombel_id,
        course_id=payload.course_id,
        dosen_id=dosen.id,
        semester_ke=payload.semester_ke,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return _to_out(db, assignment)


@router.get("/", response_model=list[schemas.CourseAssignmentOut])
def list_assignments(
    academic_period_id: str = None,
    rombel_id: str = None,
    dosen_id: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Bisa difilter ?academic_period_id=...&rombel_id=...&dosen_id=..."""
    query = db.query(models.CourseAssignment)
    if academic_period_id:
        query = query.filter(models.CourseAssignment.academic_period_id == academic_period_id)
    if rombel_id:
        query = query.filter(models.CourseAssignment.rombel_id == rombel_id)
    if dosen_id:
        query = query.filter(models.CourseAssignment.dosen_id == dosen_id)

    assignments = query.order_by(models.CourseAssignment.created_at.desc()).all()
    return [_to_out(db, a) for a in assignments]


@router.delete("/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    assignment = db.get(models.CourseAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Data pengampu tidak ditemukan")

    in_use = (
        db.query(models.Schedule)
        .filter(models.Schedule.course_assignment_id == assignment_id)
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="Data pengampu ini masih dipakai di Jadwal, hapus jadwalnya dulu",
        )

    db.delete(assignment)
    db.commit()
    return None
