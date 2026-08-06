import json
import os
import shutil

SUMMARY_FILE = "output/semua_tempat_summary.json"
OUTPUT_DIR   = "output"

# Batas wilayah Kabupaten Gresik + Pulau Bawean
LAT_MIN, LAT_MAX = -7.20, -5.85
LNG_MIN, LNG_MAX = 112.38, 112.75

def dalam_gresik(lat, lng):
    try:
        return LAT_MIN <= float(lat) <= LAT_MAX and LNG_MIN <= float(lng) <= LNG_MAX
    except (TypeError, ValueError):
        return False

# Baca summary
with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

tetap    = []
dihapus  = []
no_koord = []

for t in data:
    lat = t.get("latitude")
    lng = t.get("longitude")
    key = t.get("key", "")

    if lat is None or lng is None:
        no_koord.append(t.get("tempat", key))
        tetap.append(t)  # tidak ada koordinat, biarkan
        continue

    if dalam_gresik(lat, lng):
        tetap.append(t)
    else:
        dihapus.append((key, t.get("tempat", key)))

# Hapus folder
print(f"\n🗑️  Menghapus {len(dihapus)} tempat di luar Gresik...\n")
for key, nama in dihapus:
    folder = os.path.join(OUTPUT_DIR, key)
    if os.path.exists(folder):
        shutil.rmtree(folder)
        print(f"  ❌ Dihapus: {nama} ({key})")
    else:
        print(f"  ⚠️  Folder tidak ada: {key}")

# Update summary
with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
    json.dump(tetap, f, ensure_ascii=False, indent=2)

print(f"\n✅ Selesai!")
print(f"   Tersisa  : {len(tetap)} tempat")
print(f"   Dihapus  : {len(dihapus)} tempat")
print(f"   Tanpa koordinat (dibiarkan): {len(no_koord)} tempat")