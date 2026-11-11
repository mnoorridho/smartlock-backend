"""Logika auto-presensi dari unlock/NFC/Face yang berhasil."""
import uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import models
from app.config import settings

_DAY_MAP = {
    0: models.DayOfWeek.senin,
    1: models.DayOfWeek.selasa,
    2: models.DayOfWeek.rabu,
    3: models.DayOfWeek.kamis,
    4: models.DayOfWeek.jumat,
    5: models.DayOfWeek.sabtu,
    6: models.DayOfWeek.minggu,
}


def get_local_now() -> datetime:
    """Ambil waktu sekarang sesuai timezone aplikasi.

    Windows Python sering tidak membawa IANA timezone database secara
    bawaan. Kalau ``ZoneInfo("Asia/Jakarta")`` tidak tersedia, gunakan
    fallback WIB (UTC+07:00) supaya auto-presensi tetap berjalan dan endpoint
    hardware tidak berubah menjadi HTTP 500 hanya karena timezone database.
    Paket ``tzdata`` juga dicantumkan di requirements sebagai sumber IANA
    timezone untuk instalasi baru.
    """
    try:
        tz = ZoneInfo(settings.app_timezone)
    except ZoneInfoNotFoundError:
        # Smartlock target deployment: WIB. Fallback ini terutama untuk
        # Windows development environment yang belum memasang tzdata.
        tz = timezone(timedelta(hours=7), name="WIB")
    return datetime.now(tz)


def _utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _schedule_info(db: Session, schedule: models.Schedule) -> dict:
    assignment = db.get(models.CourseAssignment, schedule.course_assignment_id)
    period = db.get(models.AcademicPeriod, assignment.academic_period_id) if assignment else None
    course = db.get(models.Course, assignment.course_id) if assignment else None
    rombel = db.get(models.Rombel, assignment.rombel_id) if assignment else None
    dosen = db.get(models.User, assignment.dosen_id) if assignment else None
    return {
        "schedule_id": schedule.id,
        "hari": schedule.hari.value if schedule.hari else None,
        "jam": f"{schedule.jam_mulai:%H:%M}-{schedule.jam_selesai:%H:%M}",
        "mata_kuliah": course.kode if course else "-",
        "rombel": rombel.nama if rombel else "-",
        "dosen": dosen.email if dosen else "-",
        "periode": f"{period.tahun_ajaran} {period.semester.value}" if period else "-",
        "periode_aktif": bool(period and period.is_active),
        "periode_mulai": str(period.tanggal_mulai) if period else None,
        "periode_selesai": str(period.tanggal_selesai) if period else None,
    }


def record_attendance_if_scheduled(
    db: Session,
    device_id: str,
    user_id: str,
    access_log_id: str = None,
) -> dict:
    """Buat presensi otomatis kalau ada jadwal yang benar-benar aktif.

    Jadwal aktif = device sama + hari sama + jam sedang berlangsung + periode
    is_active=True + tanggal sekarang berada di rentang periode.

    Return selalu aman dipakai oleh endpoint hardware; error presensi tidak
    boleh mengubah akses NFC/face yang sudah sukses menjadi HTTP 500.
    """
    result = {
        "recorded": 0,
        "matched_schedules": 0,
        "already_recorded": 0,
        "not_participant": 0,
        "error": None,
        "diagnostic": None,
    }

    if not user_id:
        result["diagnostic"] = "Kartu/hasil verifikasi tidak tertaut ke user; presensi otomatis tidak dapat dibuat."
        return result

    user = db.get(models.User, user_id)
    if not user or not user.is_active:
        result["diagnostic"] = "User tidak ditemukan atau tidak aktif."
        return result

    # Kebijakan Smartlock yang disepakati untuk demo: akses dosen/owner tetap
    # diperbolehkan, tetapi presensi akademik pada menu mahasiswa hanya dibuat
    # untuk akun dengan academic_role=mahasiswa.
    if user.academic_role != models.AcademicRole.mahasiswa:
        result["diagnostic"] = (
            "Akses pintu tetap dapat diberikan, tetapi presensi otomatis hanya "
            "dibuat untuk mahasiswa yang menjadi anggota rombel pada jadwal aktif."
        )
        return result

    try:
        # Hitung waktu lokal DI DALAM try. Ini penting di Windows: bila
        # timezone database belum tersedia, helper sekarang memakai fallback WIB
        # dan exception lain tetap diterjemahkan menjadi diagnostic, bukan HTTP 500.
        local_now = get_local_now()
        today = local_now.date()
        hari_ini = _DAY_MAP[local_now.weekday()]
        jam_sekarang = local_now.time().replace(tzinfo=None)

        # Ambil kandidat yang cocok secara fisik (device + hari + jam) DULU,
        # tanpa menyaring periode, supaya kalau gagal kita bisa menjelaskan
        # apakah jadwalnya ternyata berada di periode yang salah/nonaktif.
        candidates = (
            db.query(models.Schedule)
            .filter(
                models.Schedule.device_id == device_id,
                models.Schedule.hari == hari_ini,
                models.Schedule.jam_mulai <= jam_sekarang,
                models.Schedule.jam_selesai > jam_sekarang,
            )
            .all()
        )

        if not candidates:
            result["diagnostic"] = (
                f"Tidak ada jadwal pada device ini untuk {hari_ini.value} pukul "
                f"{jam_sekarang:%H:%M} WIB yang sedang berlangsung."
            )
            return result

        valid_schedules = []
        excluded = []
        for schedule in candidates:
            info = _schedule_info(db, schedule)
            assignment = db.get(models.CourseAssignment, schedule.course_assignment_id)
            period = db.get(models.AcademicPeriod, assignment.academic_period_id) if assignment else None
            if not assignment or not period:
                excluded.append(info | {"alasan": "pengampu/periode tidak ditemukan"})
                continue
            if not period.is_active:
                excluded.append(info | {"alasan": "periode tidak aktif"})
                continue
            if period.tanggal_mulai > today or period.tanggal_selesai < today:
                excluded.append(info | {"alasan": "tanggal sekarang di luar rentang periode"})
                continue
            valid_schedules.append(schedule)

        if not valid_schedules:
            parts = []
            for item in excluded[:5]:
                parts.append(
                    f"{item['mata_kuliah']}/{item['rombel']} {item['jam']} "
                    f"[{item['periode']}: {item['alasan']}]"
                )
            result["diagnostic"] = (
                "Ada jadwal yang cocok hari+jam, tetapi tidak dianggap aktif. "
                + ("; ".join(parts) if parts else "Periksa periode akademik.")
            )
            return result

        for schedule in valid_schedules:
            result["matched_schedules"] += 1
            assignment = db.get(models.CourseAssignment, schedule.course_assignment_id)
            if not assignment:
                continue

            is_participant = assignment.dosen_id == user_id
            if not is_participant:
                is_member = (
                    db.query(models.RombelMember)
                    .filter(
                        models.RombelMember.rombel_id == assignment.rombel_id,
                        models.RombelMember.user_id == user_id,
                    )
                    .first()
                )
                is_participant = is_member is not None

            if not is_participant:
                result["not_participant"] += 1
                continue

            existing = (
                db.query(models.Attendance)
                .filter(
                    models.Attendance.schedule_id == schedule.id,
                    models.Attendance.user_id == user_id,
                    models.Attendance.tanggal == today,
                )
                .first()
            )
            if existing:
                result["already_recorded"] += 1
                continue

            attendance = models.Attendance(
                id=str(uuid.uuid4()),
                schedule_id=schedule.id,
                user_id=user_id,
                tanggal=today,
                status=models.AttendanceStatus.hadir,
                waktu_masuk=_utc_naive(local_now),
                access_log_id=access_log_id,
            )

            try:
                with db.begin_nested():
                    db.add(attendance)
                    db.flush()
                result["recorded"] += 1
            except IntegrityError:
                existing = (
                    db.query(models.Attendance)
                    .filter(
                        models.Attendance.schedule_id == schedule.id,
                        models.Attendance.user_id == user_id,
                        models.Attendance.tanggal == today,
                    )
                    .first()
                )
                if existing:
                    result["already_recorded"] += 1
                else:
                    result["error"] = "gagal menyimpan presensi karena konflik database"

        if result["recorded"]:
            db.commit()

        if result["not_participant"] and not result["recorded"]:
            result["diagnostic"] = "Jadwal aktif ditemukan, tetapi user bukan dosen pengampu atau anggota rombel jadwal tersebut."
        elif result["recorded"]:
            result["diagnostic"] = f"Presensi dibuat otomatis pada {local_now:%Y-%m-%d %H:%M:%S} WIB."
        elif result["already_recorded"]:
            result["diagnostic"] = "Presensi sesi ini sudah tercatat sebelumnya."

    except SQLAlchemyError:
        db.rollback()
        result["error"] = "database presensi bermasalah (cek migration/schema dan log server)"
    except Exception:
        db.rollback()
        result["error"] = "terjadi kesalahan saat memproses presensi (cek log server)"

    return result
