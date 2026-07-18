from apify_client import ApifyClient
from dotenv import load_dotenv
import json
import csv
import os

load_dotenv()
API_TOKEN = os.getenv("APIFY_API_TOKEN")

# ── Buat folder output ──
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 4 Tempat Target di Gresik ──
run_input = {
    "searchStringsArray": [
        "Kantor Bupati Gresik",
        "RSUD Ibnu Sina Gresik",
        "Mall Pelayanan Publik Gresik",
        "DISPENDUKCAPIL Gresik"
    ],
    "locationQuery": "Gresik, Jawa Timur, Indonesia",
    "maxCrawledPlacesPerSearch": 1,
    "includeReviews": True,
    "maxReviews": 50,
    "includeOpeningHours": False,
    "language": "id",
}

print("⏳ Menjalankan scraper... harap tunggu")

# ── Jalankan Actor ──
run = client.actor("compass/crawler-google-places").call(run_input=run_input)

# ── Ambil Hasil ──
results = list(client.dataset(run.default_dataset_id).iterate_items())

print(f"✅ Berhasil mengambil {len(results)} tempat\n")

# ── Tampilkan Ringkasan di Terminal ──
for place in results:
    print(f"📍 {place.get('title')} — {place.get('totalScore')}⭐ ({place.get('reviewsCount')} ulasan)")

# ── Simpan ke JSON ──
json_path = os.path.join(OUTPUT_DIR, "gresik_ulasan.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n💾 JSON  → {json_path}")

# ── Simpan Ulasan ke CSV ──
csv_path = os.path.join(OUTPUT_DIR, "gresik_ulasan.csv")
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Tempat", "Rating Tempat", "Total Ulasan",
                     "Nama Reviewer", "Bintang", "Tanggal", "Ulasan"])

    for place in results:
        nama_tempat   = place.get("title", "")
        rating_tempat = place.get("totalScore", "")
        total_ulasan  = place.get("reviewsCount", "")
        reviews       = place.get("reviews", [])

        if reviews:
            for r in reviews:
                writer.writerow([
                    nama_tempat,
                    rating_tempat,
                    total_ulasan,
                    r.get("name") or "",
                    r.get("stars" )or "",
                    r.get("publishedAtDate") or "",
                    (r.get("text") or "").replace("\n", " ")
                ])
        else:
            writer.writerow([nama_tempat, rating_tempat, total_ulasan, "", "", "", ""])

print(f"💾 CSV   → {csv_path}")
print(f"\n🔗 Dataset online: https://console.apify.com/storage/datasets/{run.default_dataset_id}")