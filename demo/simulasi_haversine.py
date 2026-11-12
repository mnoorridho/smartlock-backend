
from app.geo import haversine_distance_m

# Koordinat lokasi Smart Lock
device_lat = -6.200000
device_lon = 106.816666

# Radius Geofencing dalam meter
radius = 100

# Data koordinat pengguna untuk simulasi
scenarios = [
    ("Pengguna dekat", -6.1997302035, 106.816666),
    ("Pengguna jauh", -6.1977516959, 106.816666),
]

print("SIMULASI ALGORITMA HAVERSINE")
print("=" * 45)

for name, user_lat, user_lon in scenarios:

    # Menghitung jarak menggunakan fungsi asli backend
    distance = haversine_distance_m(
        user_lat,
        user_lon,
        device_lat,
        device_lon
    )

    print(f"\nSkenario: {name}")
    print(f"Jarak pengguna: {distance:.2f} meter")

    if distance <= radius:
        print("Status: DI DALAM RADIUS")
    else:
        print("Status: DI LUAR RADIUS")

print("\nSimulasi selesai.")

print("\nSIMULASI KEPUTUSAN GEOFENCING")
print("=" * 45)

# Radius default berdasarkan model Device
geofence_radius_m = 100.0

test_distances = [
    ("Pengguna di dalam radius", 30.0),
    ("Pengguna tepat pada batas radius", 100.0),
    ("Pengguna di luar radius", 250.0),
]

for scenario, distance in test_distances:
    print(f"\n{scenario}")
    print(f"Jarak: {distance:.2f} meter")
    print(f"Radius: {geofence_radius_m:.2f} meter")

    if distance > geofence_radius_m:
        print("Keputusan: AKSES DITOLAK")
    else:
        print("Keputusan: LOLOS GEOFENCING")
