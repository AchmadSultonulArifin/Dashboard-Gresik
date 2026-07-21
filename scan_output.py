import json
import os
import re

OUTPUT_DIR   = "output"
SUMMARY_FILE = "output/semua_tempat_summary.json"

KATEGORI_MAP = {
    # Pemerintahan
    "kantor"        : "Pemerintahan",
    "dinas"         : "Pemerintahan",
    "kecamatan"     : "Pemerintahan",
    "kelurahan"     : "Pemerintahan",
    "bupati"        : "Pemerintahan",
    "sekretariat"   : "Pemerintahan",
    "dprd"          : "Pemerintahan",
    "polisi"        : "Pemerintahan",
    "polsek"        : "Pemerintahan",
    "polres"        : "Pemerintahan",
    "koramil"       : "Pemerintahan",
    "kodim"         : "Pemerintahan",
    "kejaksaan"     : "Pemerintahan",
    "pengadilan"    : "Pemerintahan",
    # Kesehatan
    "rumah_sakit"   : "Kesehatan",
    "rsud"          : "Kesehatan",
    "rsu"           : "Kesehatan",
    "puskesmas"     : "Kesehatan",
    "klinik"        : "Kesehatan",
    "apotek"        : "Kesehatan",
    "laboratorium"  : "Kesehatan",
    # Pendidikan
    "sma"           : "Pendidikan",
    "smk"           : "Pendidikan",
    "smp"           : "Pendidikan",
    "sd_negeri"     : "Pendidikan",
    "universitas"   : "Pendidikan",
    "kampus"        : "Pendidikan",
    "sekolah"       : "Pendidikan",
    "madrasah"      : "Pendidikan",
    "pesantren"     : "Pendidikan",
    # Pelayanan Publik
    "disdukcapil"   : "Pelayanan Publik",
    "dispendukcapil": "Pelayanan Publik",
    "samsat"        : "Pelayanan Publik",
    "mall_pelayanan": "Pelayanan Publik",
    "imigrasi"      : "Pelayanan Publik",
    "bpjs"          : "Pelayanan Publik",
    "pos"           : "Pelayanan Publik",
    "kua"           : "Pelayanan Publik",
    "bpn"           : "Pelayanan Publik",
    "pajak"         : "Pelayanan Publik",
    "bea_cukai"     : "Pelayanan Publik",
    # Perbankan
    "bank"          : "Perbankan",
    "bri"           : "Perbankan",
    "bni"           : "Perbankan",
    "bca"           : "Perbankan",
    "mandiri"       : "Perbankan",
    "btn"           : "Perbankan",
    "bjb"           : "Perbankan",
    "bpd"           : "Perbankan",
    "bpr"           : "Perbankan",
    "cimb"          : "Perbankan",
    "danamon"       : "Perbankan",
    "pegadaian"     : "Perbankan",
    "koperasi"      : "Perbankan",
    "atm"           : "Perbankan",
    "brilink"       : "Perbankan",
    # Wisata
    "wisata"        : "Wisata",
    "pantai"        : "Wisata",
    "taman"         : "Wisata",
    "museum"        : "Wisata",
    "makam"         : "Wisata",
    "masjid"        : "Wisata",
    # Industri
    "petrokimia"    : "Industri",
    "semen"         : "Industri",
    "pabrik"        : "Industri",
    "pelabuhan"     : "Industri",
    "terminal"      : "Industri",
}

def get_kategori(folder_name: str) -> str:
    for key, kat in KATEGORI_MAP.items():
        if key in folder_name:
            return kat
    return "Lainnya"

summary = []
skipped = []

for folder_name in sorted(os.listdir(OUTPUT_DIR)):
    folder_path = os.path.join(OUTPUT_DIR, folder_name)
    
    # Skip jika bukan folder
    if not os.path.isdir(folder_path):
        continue
    
    # Coba baca ulasan_sentimen.json dulu
    json_sentimen = os.path.join(folder_path, "ulasan_sentimen.json")
    json_mentah   = os.path.join(folder_path, "ulasan_mentah.json")
    
    if os.path.exists(json_sentimen):
        with open(json_sentimen, "r", encoding="utf-8") as f:
            data = json.load(f)
        summary.append({
            "key"           : folder_name,
            "kategori"      : data.get("kategori") or get_kategori(folder_name),
            "tempat"        : data.get("tempat", folder_name),
            "rating"        : data.get("rating", 0),
            "total_ulasan"  : data.get("total_ulasan", 0),
            "positif"       : data.get("positif", 0),
            "netral"        : data.get("netral", 0),
            "negatif"       : data.get("negatif", 0),
            "persen_positif": data.get("persen_positif", 0),
            "persen_netral" : data.get("persen_netral", 0),
            "persen_negatif": data.get("persen_negatif", 0),
        })
        print(f"✅ {data.get('tempat', folder_name)}")

    elif os.path.exists(json_mentah):
        # Ada mentah tapi belum diproses sentimen
        with open(json_mentah, "r", encoding="utf-8") as f:
            data = json.load(f)
        summary.append({
            "key"           : folder_name,
            "kategori"      : get_kategori(folder_name),
            "tempat"        : data.get("title", folder_name),
            "rating"        : data.get("totalScore", 0),
            "total_ulasan"  : data.get("reviewsCount", 0),
            "positif"       : 0,
            "netral"        : 0,
            "negatif"       : 0,
            "persen_positif": 0,
            "persen_netral" : 0,
            "persen_negatif": 0,
        })
        print(f"⚠️  {data.get('title', folder_name)} (belum diproses sentimen)")
    else:
        skipped.append(folder_name)

# Simpan summary
with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"\n✅ Summary dibuat: {len(summary)} tempat")
print(f"⛔ Skip (tidak ada JSON): {len(skipped)} folder")
print(f"💾 Tersimpan di {SUMMARY_FILE}")