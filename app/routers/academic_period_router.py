import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/academic-periods", tags=["Presensi - Periode Akademik"])


@router.post("/", response_model=schemas.AcademicPeriodOut, status_code=201)
def create_period(
    payload: schemas.AcademicPeriodCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    if payload.tanggal_selesai <= payload.tanggal_mulai:
        raise HTTPException(status_code=422, detail="tanggal_selesai harus lebih besar dari tanggal_mulai")

    existing = (
        db.query(models.AcademicPeriod)
        .filter(
            models.AcademicPeriod.tahun_ajaran == payload.tahun_ajaran,
            models.AcademicPeriod.semester == payload.semester,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Periode akademik dengan tahun ajaran & semester ini sudah ada")

    if payload.is_active:
        # Cuma boleh 1 periode aktif dalam satu waktu -- nonaktifkan yang lain dulu.
        db.query(models.AcademicPeriod).update({models.AcademicPeriod.is_active: False})

    period = models.AcademicPeriod(
        id=str(uuid.uuid4()),
        tahun_ajaran=payload.tahun_ajaran,
        semester=payload.semester,
        tanggal_mulai=payload.tanggal_mulai,
        tanggal_selesai=payload.tanggal_selesai,
        is_active=payload.is_active,
    )
    db.add(period)
    db.commit()
    db.refresh(period)
    return period


@router.get("/", response_model=list[schemas.AcademicPeriodOut])
def list_periods(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return db.query(models.AcademicPeriod).order_by(models.AcademicPeriod.tanggal_mulai.desc()).all()


@router.patch("/{period_id}", response_model=schemas.AcademicPeriodOut)
def update_period(
    period_id: str,
    payload: schemas.AcademicPeriodUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    period = db.get(models.AcademicPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Periode akademik tidak ditemukan")

    if payload.is_active is True:
        db.query(models.AcademicPeriod).update({models.AcademicPeriod.is_active: False})
        period.is_active = True
    elif payload.is_active is False:
        period.is_active = False

    if payload.tanggal_mulai is not None:
        period.tanggal_mulai = payload.tanggal_mulai
    if payload.tanggal_selesai is not None:
        period.tanggal_selesai = payload.tanggal_selesai

    if period.tanggal_selesai <= period.tanggal_mulai:
        raise HTTPException(status_code=422, detail="tanggal_selesai harus lebih besar dari tanggal_mulai")

    db.commit()
    db.refresh(period)
    return period


@router.delete("/{period_id}", status_code=204)
def delete_period(
    period_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    period = db.get(models.AcademicPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="Periode akademik tidak ditemukan")

    in_use = (
        db.query(models.CourseAssignment)
        .filter(models.CourseAssignment.academic_period_id == period_id)
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="Periode ini masih dipakai di data Pengampu Mata Kuliah, tidak bisa dihapus",
        )

    db.delete(period)
    db.commit()
    return None
