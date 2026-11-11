import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/courses", tags=["Presensi - Mata Kuliah"])


@router.post("/", response_model=schemas.CourseOut, status_code=201)
def create_course(
    payload: schemas.CourseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    existing = db.query(models.Course).filter(models.Course.kode == payload.kode).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Kode mata kuliah '{payload.kode}' sudah dipakai")

    course = models.Course(id=str(uuid.uuid4()), kode=payload.kode, nama=payload.nama, sks=payload.sks)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@router.get("/", response_model=list[schemas.CourseOut])
def list_courses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    return db.query(models.Course).order_by(models.Course.nama.asc()).all()


@router.patch("/{course_id}", response_model=schemas.CourseOut)
def update_course(
    course_id: str,
    payload: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Mata kuliah tidak ditemukan")

    if payload.nama is not None:
        course.nama = payload.nama
    if payload.sks is not None:
        course.sks = payload.sks

    db.commit()
    db.refresh(course)
    return course


@router.delete("/{course_id}", status_code=204)
def delete_course(
    course_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Mata kuliah tidak ditemukan")

    in_use = (
        db.query(models.CourseAssignment)
        .filter(models.CourseAssignment.course_id == course_id)
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="Mata kuliah ini masih dipakai di data Pengampu Mata Kuliah, tidak bisa dihapus",
        )

    db.delete(course)
    db.commit()
    return None
