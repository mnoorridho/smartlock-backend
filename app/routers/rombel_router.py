import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth

router = APIRouter(prefix="/rombels", tags=["Presensi - Rombel"])


def _to_rombel_out(db: Session, rombel: models.Rombel) -> schemas.RombelOut:
    dosen_wali_nama = None
    if rombel.dosen_wali_id:
        dosen = db.get(models.User, rombel.dosen_wali_id)
        dosen_wali_nama = dosen.name if dosen else None

    jumlah = (
        db.query(models.RombelMember)
        .filter(models.RombelMember.rombel_id == rombel.id)
        .count()
    )

    return schemas.RombelOut(
        id=rombel.id,
        nama=rombel.nama,
        dosen_wali_id=rombel.dosen_wali_id,
        dosen_wali_nama=dosen_wali_nama,
        jumlah_anggota=jumlah,
        created_at=rombel.created_at,
    )


@router.post("/", response_model=schemas.RombelOut, status_code=201)
def create_rombel(
    payload: schemas.RombelCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    if payload.dosen_wali_id:
        dosen = db.get(models.User, payload.dosen_wali_id)
        if not dosen:
            raise HTTPException(status_code=404, detail="dosen_wali_id tidak ditemukan")

    rombel = models.Rombel(id=str(uuid.uuid4()), nama=payload.nama, dosen_wali_id=payload.dosen_wali_id)
    db.add(rombel)
    db.commit()
    db.refresh(rombel)
    return _to_rombel_out(db, rombel)


@router.get("/", response_model=list[schemas.RombelOut])
def list_rombels(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    rombels = db.query(models.Rombel).order_by(models.Rombel.nama.asc()).all()
    return [_to_rombel_out(db, r) for r in rombels]


@router.patch("/{rombel_id}", response_model=schemas.RombelOut)
def update_rombel(
    rombel_id: str,
    payload: schemas.RombelUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    rombel = db.get(models.Rombel, rombel_id)
    if not rombel:
        raise HTTPException(status_code=404, detail="Rombel tidak ditemukan")

    if payload.nama is not None:
        rombel.nama = payload.nama
    if payload.dosen_wali_id is not None:
        dosen = db.get(models.User, payload.dosen_wali_id)
        if not dosen:
            raise HTTPException(status_code=404, detail="dosen_wali_id tidak ditemukan")
        rombel.dosen_wali_id = payload.dosen_wali_id

    db.commit()
    db.refresh(rombel)
    return _to_rombel_out(db, rombel)


@router.delete("/{rombel_id}", status_code=204)
def delete_rombel(
    rombel_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    rombel = db.get(models.Rombel, rombel_id)
    if not rombel:
        raise HTTPException(status_code=404, detail="Rombel tidak ditemukan")

    in_use = (
        db.query(models.CourseAssignment)
        .filter(models.CourseAssignment.rombel_id == rombel_id)
        .first()
    )
    if in_use:
        raise HTTPException(
            status_code=409,
            detail="Rombel ini masih dipakai di data Pengampu Mata Kuliah, tidak bisa dihapus",
        )

    db.query(models.RombelMember).filter(models.RombelMember.rombel_id == rombel_id).delete()
    db.delete(rombel)
    db.commit()
    return None


# ---------- Anggota Rombel ----------
@router.post("/{rombel_id}/members", response_model=schemas.RombelMemberOut, status_code=201)
def add_member(
    rombel_id: str,
    payload: schemas.RombelMemberAdd,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    rombel = db.get(models.Rombel, rombel_id)
    if not rombel:
        raise HTTPException(status_code=404, detail="Rombel tidak ditemukan")

    user = db.query(models.User).filter(models.User.email == payload.user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User dengan email ini belum terdaftar di sistem")

    existing = (
        db.query(models.RombelMember)
        .filter(models.RombelMember.rombel_id == rombel_id, models.RombelMember.user_id == user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User ini sudah jadi anggota rombel ini")

    member = models.RombelMember(id=str(uuid.uuid4()), rombel_id=rombel_id, user_id=user.id)
    db.add(member)
    db.commit()

    return schemas.RombelMemberOut(id=member.id, user_id=user.id, user_name=user.name, user_email=user.email)


@router.get("/{rombel_id}/members", response_model=list[schemas.RombelMemberOut])
def list_members(
    rombel_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    rombel = db.get(models.Rombel, rombel_id)
    if not rombel:
        raise HTTPException(status_code=404, detail="Rombel tidak ditemukan")

    members = (
        db.query(models.RombelMember)
        .filter(models.RombelMember.rombel_id == rombel_id)
        .all()
    )
    result = []
    for m in members:
        user = db.get(models.User, m.user_id)
        if user:
            result.append(schemas.RombelMemberOut(id=m.id, user_id=user.id, user_name=user.name, user_email=user.email))
    return result


@router.delete("/{rombel_id}/members/{member_id}", status_code=204)
def remove_member(
    rombel_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.require_owner),
):
    member = (
        db.query(models.RombelMember)
        .filter(models.RombelMember.id == member_id, models.RombelMember.rombel_id == rombel_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan di rombel ini")

    db.delete(member)
    db.commit()
    return None
