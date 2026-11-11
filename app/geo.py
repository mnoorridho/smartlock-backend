import math

# Kalau akurasi GPS yang dikirim client lebih buruk (angka meter lebih besar)
# dari ini, unlock ditolak dulu -- daripada geofence lolos/gagal cuma gara-gara
# GPS lagi meleset jauh (mis. di dalam gedung, cuaca buruk, dsb). Sesuai catatan
# di dokumen project: "simpan nilai akurasi; tolak atau minta ulang jika terlalu buruk."
DEFAULT_MAX_GPS_ACCURACY_M = 50.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Hitung jarak antara dua titik koordinat (meter) pakai formula haversine.
    Cukup akurat buat radius geofence rumahan/kampus (galat < 0.5% pada jarak
    beberapa km), gak perlu library eksternal.
    """
    R = 6_371_000  # radius Bumi rata-rata, meter
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
