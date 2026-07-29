import json
import os
import re
import pandas as pd

OUTPUT_DIR   = "output"
SUMMARY_FILE = "output/semua_tempat_summary.json"
MASTER_FILE  = "output/master_tempat.csv"

def get_folder(nama):
    return re.sub(r'[^a-z0-9]+', '_', nama.lower()).strip('_')

# ── Load master CSV untuk mapping nama → kategori ──
master_map = {}
if os.path.exists(MASTER_FILE):
    df_master = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
    for _, row in df_master.iterrows():
        key = get_folder(str(row["nama"]))
        master_map[key] = {
            "kategori": str(row.get("kategori", "Lainnya")),
            "nama"    : str(row["nama"]),
        }
print(f"✅ Master loaded: {len(master_map)} tempat")

summary  = []
skipped  = []
folders  = sorted(os.listdir(OUTPUT_DIR))

for folder_name in folders:
    folder_path = os.path.join(OUTPUT_DIR, folder_name)
    if not os.path.isdir(folder_path):
        continue

    json_sentimen = os.path.join(folder_path, "ulasan_sentimen.json")
    json_mentah   = os.path.join(folder_path, "ulasan_mentah.json")

    # Ambil kategori & nama dari master CSV
    master_info = master_map.get(folder_name, {})
    kategori    = master_info.get("kategori", "Lainnya")
    nama_master = master_info.get("nama", "")

    if os.path.exists(json_sentimen):
        with open(json_sentimen, "r", encoding="utf-8") as f:
            data = json.load(f)
        nama = data.get("tempat") or nama_master or folder_name
        summary.append({
            "key"           : folder_name,
            "kategori"      : kategori,
            "tempat"        : nama,
            "rating"        : float(data.get("rating") or 0),
            "total_ulasan"  : int(data.get("total_ulasan") or 0),
            "positif"       : int(data.get("positif") or 0),
            "netral"        : int(data.get("netral") or 0),
            "negatif"       : int(data.get("negatif") or 0),
            "persen_positif": float(data.get("persen_positif") or 0),
            "persen_netral" : float(data.get("persen_netral") or 0),
            "persen_negatif": float(data.get("persen_negatif") or 0),
        })
        print(f"✅ {nama} [{kategori}]")

    elif os.path.exists(json_mentah):
        with open(json_mentah, "r", encoding="utf-8") as f:
            data = json.load(f)
        nama = data.get("title") or nama_master or folder_name
        summary.append({
            "key"           : folder_name,
            "kategori"      : kategori,
            "tempat"        : nama,
            "rating"        : float(data.get("totalScore") or 0),
            "total_ulasan"  : int(data.get("reviewsCount") or 0),
            "positif"       : 0,
            "netral"        : 0,
            "negatif"       : 0,
            "persen_positif": 0.0,
            "persen_netral" : 0.0,
            "persen_negatif": 0.0,
        })
        print(f"⚠️  {nama} [{kategori}] (belum diproses sentimen)")
    else:
        skipped.append(folder_name)

with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(f"\n✅ Summary dibuat: {len(summary)} tempat")
print(f"⛔ Skip: {len(skipped)} folder")
print(f"💾 {SUMMARY_FILE}")