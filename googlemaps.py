"""
Google Maps Scraper + Preprocessing + IndoBERT Sentiment Analysis
Instansi Pemerintahan Kabupaten Gresik
Output: 1 file CSV & JSON per tempat (untuk dashboard)
=================================================================
"""

import re
import csv
import json
import os
import warnings
warnings.filterwarnings("ignore")

from apify_client import ApifyClient
from dotenv import load_dotenv
import pandas as pd

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
except ImportError:
    os.system("pip install transformers torch")
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch


# ════════════════════════════════════════════════════
# KONFIGURASI — ROTASI 3 TOKEN APIFY
# ════════════════════════════════════════════════════
load_dotenv()

TOKENS = [
    os.getenv("APIFY_API_TOKEN_1"),
    os.getenv("APIFY_API_TOKEN_2"),
    os.getenv("APIFY_API_TOKEN_3"),
]
TOKENS = [t for t in TOKENS if t]  # hapus yang kosong
print(f"✅ {len(TOKENS)} token Apify terbaca")

token_index = 0  # index token yang sedang dipakai

def get_client():
    """Ambil client dengan token aktif."""
    return ApifyClient(TOKENS[token_index])

def rotate_token():
    """Pindah ke token berikutnya."""
    global token_index
    token_index = (token_index + 1) % len(TOKENS)
    print(f"🔄 Rotasi ke token {token_index + 1}")

def run_actor(run_input: dict, max_retry: int = None) -> list:
    if max_retry is None:
        max_retry = len(TOKENS)
    
    for attempt in range(max_retry):
        try:
            client = get_client()
            run    = client.actor("compass/crawler-google-places").call(run_input=run_input)
            return list(client.dataset(run.default_dataset_id).iterate_items())
        except Exception as e:
            err = str(e).lower()
            # ✅ tambah "exceed" dan "usage" sebagai trigger rotasi
            if any(k in err for k in ["402", "limit", "quota", "payment", "credit", "exceed", "usage", "subscription"]):
                print(f"⚠️  Token {token_index + 1} kena limit: {str(e)[:80]}")
                rotate_token()
            elif any(k in err for k in ["dns", "connect", "network", "timeout", "host"]):
                print(f"⚠️  Koneksi terputus (attempt {attempt+1}), tunggu 10 detik...")
                time.sleep(10)
            else:
                print(f"❌ Error: {e}")
                raise
    
    print("❌ Semua token habis limit, skip tempat ini.")
    return []



MASTER_FILE = "output/master_tempat.csv"
CHECKPOINT_FILE = "output/checkpoint.txt"  # ← sudah ada
OUTPUT_DIR      = "output" 

# ════════════════════════════════════════════════
# CHECKPOINT FUNCTIONS — tambahkan di sini
# ════════════════════════════════════════════════
def get_checkpoint() -> int:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            return int(open(CHECKPOINT_FILE).read().strip())
        except:
            return 0
    return 0

def save_checkpoint(index: int):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(index))

def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)

token_index = 0  # ← sudah ada


def get_folder(nama_tempat):
    return re.sub(r'[^a-z0-9]+', '_', nama_tempat.lower()).strip('_')


def buat_master_tempat():
    SEARCHES = {
        "Pemerintahan": [
            "kantor pemerintah gresik",
            "kantor desa gresik",
            "kantor kecamatan gresik",
            "kantor kelurahan gresik"
        ],
        "Kesehatan": [
            "rumah sakit gresik",
            "puskesmas gresik",
            "klinik gresik"
        ],
        "Pendidikan": [
            "sekolah gresik",
            "universitas gresik",
            "kampus gresik"
        ],
        "Pelayanan Publik": [
            "disdukcapil gresik",
            "samsat gresik",
            "mall pelayanan publik gresik"
        ],
        "Wisata": ["wisata gresik"],
        "Industri": ["pabrik gresik"]
    }

    semua = []
    for kategori, pencarian in SEARCHES.items():
        print(f"\n===== {kategori} =====")
        for keyword in pencarian:
            print("Cari :", keyword)
            # ✅ pakai run_actor(), bukan client.actor()
            items = run_actor({
                "searchStringsArray": [keyword],
                "locationQuery": "Gresik, Jawa Timur",
                "maxCrawledPlacesPerSearch": 20,
                "includeReviews": False
            })
            for item in items:
                semua.append({
                    "kategori": kategori,
                    "nama": item["title"]
                })

    df = pd.DataFrame(semua).drop_duplicates("nama")
    os.makedirs("output", exist_ok=True)
    df.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"\nMaster tempat berhasil dibuat ({len(df)})")



def scrape_google_maps():
    if not os.path.exists(MASTER_FILE):
        print("Master tempat belum ada, membuat...")
        buat_master_tempat()

    master  = pd.read_csv(MASTER_FILE)
    results = []

    # Tentukan titik mulai dari checkpoint
    start_index = get_checkpoint()
    if start_index > 0:
        nama_lanjut = master.iloc[start_index]["nama"] if start_index < len(master) else "selesai"
        print(f"⏩ Melanjutkan dari tempat ke-{start_index + 1}: {nama_lanjut}\n")

        # Load hasil yang sudah tersimpan sebelumnya
        for i in range(start_index):
            nama_lama = master.iloc[i]["nama"]
            json_path = os.path.join(OUTPUT_DIR, get_folder(nama_lama), "ulasan_mentah.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    place = json.load(f)
                    place["kategori"] = master.iloc[i]["kategori"]
                    results.append(place)
        print(f"   📂 Load cache: {nama_lama}")
    else:
        print("⏳ Memulai scraping dari awal...\n")

    for i, (_, row) in enumerate(master.iterrows()):
        if i < start_index:
            continue  # skip yang sudah selesai

        print(f"[{i+1}/{len(master)}] 📍 {row['nama']}")
        data = run_actor({
            "searchStringsArray"       : [row["nama"]],
            "maxCrawledPlacesPerSearch": 1,
            "includeReviews"           : True,
            "maxReviews"               : 30,
            "language"                 : "id"
        })

        if data:
            data[0]["kategori"] = row["kategori"]
            results.extend(data)

            # Simpan JSON mentah langsung
            nama   = data[0].get("title", row["nama"])
            folder = os.path.join(OUTPUT_DIR, get_folder(nama))
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "ulasan_mentah.json"), "w", encoding="utf-8") as f:
                json.dump(data[0], f, ensure_ascii=False, indent=2)
        else:
            print(f"   ⚠️  Tidak ada data, skip.")

        # Simpan checkpoint setelah tiap tempat
        save_checkpoint(i + 1)
        print(f"   ✅ Checkpoint: {i+1}/{len(master)}")

    # Selesai penuh — hapus checkpoint
    clear_checkpoint()
    print(f"\n✅ Scraping selesai! Total {len(results)} tempat\n")
    for place in results:
        print(f"   📍 {place.get('title')} | {place.get('kategori')} | {place.get('reviewsCount')} ulasan")

    return results


# ════════════════════════════════════════════════════
# BAGIAN 2 — PREPROCESSING TEKS
# ════════════════════════════════════════════════════

SLANG_DICT = {
    "yg": "yang", "dgn": "dengan", "utk": "untuk", "krn": "karena",
    "sdh": "sudah", "blm": "belum", "tdk": "tidak", "ga": "tidak",
    "gak": "tidak", "nggak": "tidak", "ngga": "tidak", "gk": "tidak",
    "bgt": "banget", "bngt": "banget", "sgt": "sangat", "skrg": "sekarang",
    "klo": "kalau", "klu": "kalau", "kl": "kalau", "tp": "tapi",
    "tpi": "tapi", "ttg": "tentang", "dr": "dari", "dlm": "dalam",
    "dg": "dengan", "sm": "sama", "jg": "juga", "hrs": "harus",
    "msh": "masih", "lbh": "lebih", "krng": "kurang", "byk": "banyak",
    "plg": "paling", "pd": "pada", "spy": "supaya", "sy": "saya",
    "gue": "saya", "gw": "saya", "loe": "kamu", "lu": "kamu",
    "lo": "kamu", "ok": "oke", "oks": "oke", "mantap": "bagus",
    "mantul": "bagus", "keren": "bagus", "jos": "bagus",
    "wkwk": "", "haha": "", "hehe": "", "wkwkwk": "",
    "antri": "antrian", "ngantri": "antrian",
    "rmh sakit": "rumah sakit", "rs": "rumah sakit",
    "kmr": "kamar",
}

STOPWORDS_ID = {
    "yang", "dan", "di", "ke", "dari", "ini", "itu", "ada", "dengan",
    "untuk", "pada", "adalah", "dalam", "tidak", "juga", "sudah",
    "saya", "kami", "kita", "mereka", "dia", "ia", "anda", "kamu",
    "akan", "bisa", "dapat", "oleh", "atau", "tapi", "namun", "tetapi",
    "jika", "kalau", "karena", "saat", "ketika", "setelah", "sebelum",
    "lebih", "sangat", "sekali", "masih", "belum", "baru", "lagi",
    "pun", "nya", "lah", "kah", "pula", "sih", "deh", "dong",
}

def clean_text(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'http\S+|www\S+', '', text)
    text = re.sub(r'@\w+|#\w+', '', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\b\d+\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def normalize_slang(text: str) -> str:
    return ' '.join(SLANG_DICT.get(w, w) for w in text.split()).strip()

def remove_stopwords(text: str) -> str:
    return ' '.join(w for w in text.split() if w not in STOPWORDS_ID and len(w) > 1)

def preprocess(text: str) -> dict:
    step1 = clean_text(text)
    step2 = normalize_slang(step1)
    step3 = remove_stopwords(step2)
    return {"cleaned": step1, "normalized": step2, "final": step3}

# ==========================================================
# DETEKSI TOPIK
# ==========================================================

TOPIC_RULES = {
    "Pelayanan": [
        "pelayanan", "layanan", "petugas", "pegawai",
        "ramah", "cepat", "lambat", "antri", "antrian",
        "administrasi", "birokrasi", "loket"
    ],

    "Fasilitas": [
        "fasilitas", "gedung", "ruangan", "toilet",
        "parkir", "kursi", "wifi", "ac",
        "bersih", "kotor", "nyaman"
    ],

    "Kesehatan": [
        "dokter", "perawat", "rumah sakit",
        "puskesmas", "obat", "pasien",
        "bpjs", "igd", "rawat"
    ],

    "Administrasi": [
        "ktp", "kk", "akta", "nik",
        "dokumen", "berkas", "izin",
        "surat", "disdukcapil"
    ],

    "Infrastruktur": [
        "jalan", "bangunan", "renovasi",
        "akses", "lift", "tangga",
        "trotoar", "parkiran"
    ],

    "Keamanan": [
        "satpam", "aman", "keamanan",
        "polisi", "security"
    ]
}


def detect_topic(text):
    text = text.lower()

    for topic, keywords in TOPIC_RULES.items():
        for keyword in keywords:
            if keyword in text:
                return topic

    return "Lainnya"
# ════════════════════════════════════════════════════
# BAGIAN 3 — INDOBERT SENTIMENT ANALYSIS
# ════════════════════════════════════════════════════

LABEL_MAP = {
    "LABEL_0": "Negatif",
    "LABEL_1": "Netral",
    "LABEL_2": "Positif",
}

def load_indobert():
    print("\n🤖 Memuat model IndoBERT...")
    MODEL_NAME = "mdhugol/indonesia-bert-sentiment-classification"
    tokenizer  = AutoTokenizer.from_pretrained(MODEL_NAME)
    model      = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    pipe = pipeline(
        "sentiment-analysis",
        model=model,
        tokenizer=tokenizer,
        device=0 if torch.cuda.is_available() else -1,
        truncation=True,
        max_length=512,
    )
    print("✅ Model IndoBERT berhasil dimuat!")
    return pipe

def predict_sentiment(pipe, text: str) -> dict:
    if not text or len(text.strip()) < 3:
        return {"label": "Netral", "score": 0.0}
    try:
        result = pipe(text[:512])[0]
        return {
            "label": LABEL_MAP.get(result["label"], result["label"]),
            "score": round(result["score"], 4),
        }
    except Exception:
        return {"label": "Error", "score": 0.0}


# ════════════════════════════════════════════════════
# BAGIAN 4 — PROSES PER TEMPAT
# ════════════════════════════════════════════════════

def process_per_tempat(results: list, pipe):
    print(f"\n{'='*60}")
    print("📊 PREPROCESSING + SENTIMENT PER TEMPAT")
    print(f"{'='*60}")

    all_summary = []

    for place in results:
        nama   = place.get("title", "unknown")
        folder = os.path.join(OUTPUT_DIR, get_folder(nama))
        os.makedirs(folder, exist_ok=True)
        reviews = place.get("reviews", [])

        print(f"\n📍 {nama}")

        if not reviews:
            print(f"   ⚠️  Tidak ada ulasan, dilewati.")
            continue

        # Buat DataFrame
        rows = []
        for r in reviews:
            rows.append({
                "Kategori": place.get("kategori"),
                "Tempat"       : nama,
                "Rating Tempat": place.get("totalScore", ""),
                "Total Ulasan" : place.get("reviewsCount", ""),
                "Nama Reviewer": r.get("name") or "",
                "Bintang"      : r.get("stars") or "",
                "Tanggal"      : r.get("publishedAtDate") or "",
                "Ulasan"       : (r.get("text") or "").replace("\n", " "),
            })

        df = pd.DataFrame(rows)
        df = df[df["Ulasan"].str.strip() != ""]

        # Preprocessing
        preproc = df["Ulasan"].apply(preprocess)
        df["teks_cleaned"]    = preproc.apply(lambda x: x["cleaned"])
        df["teks_normalized"] = preproc.apply(lambda x: x["normalized"])
        df["teks_final"]      = preproc.apply(lambda x: x["final"])
        df["topik"] = df["teks_final"].apply(detect_topic)
        df = df[df["teks_final"].str.strip() != ""]

        # Prediksi sentimen
        print(f"   🔍 Menganalisis {len(df)} ulasan...")
        sentiments           = [predict_sentiment(pipe, t) for t in df["teks_final"]]
        df["sentimen"]       = [s["label"] for s in sentiments]
        df["sentimen_score"] = [s["score"] for s in sentiments]

        # Statistik
        total   = len(df)
        positif = int((df["sentimen"] == "Positif").sum())
        netral  = int((df["sentimen"] == "Netral").sum())
        negatif = int((df["sentimen"] == "Negatif").sum())
        rating  = place.get("totalScore", "")

        print(f"   ⭐ Rating  : {rating}")
        print(f"   ✅ Positif : {positif} ({positif/total*100:.1f}%)")
        print(f"   ➖ Netral  : {netral}  ({netral/total*100:.1f}%)")
        print(f"   ❌ Negatif : {negatif} ({negatif/total*100:.1f}%)")

        # Simpan CSV per tempat
        csv_out = os.path.join(folder, "ulasan_sentimen.csv")
        df.to_csv(csv_out, index=False, encoding="utf-8-sig")
        print(f"   💾 {csv_out}")

        # Simpan JSON per tempat (lengkap dengan semua ulasan)
        summary = {
            "kategori"       : place.get("kategori"),
            "tempat"         : nama,
            "rating"         : rating,
            "total_ulasan"   : total,
            "positif"        : positif,
            "netral"         : netral,
            "negatif"        : negatif,
            "persen_positif" : round(positif / total * 100, 1),
            "persen_netral"  : round(netral  / total * 100, 1),
            "persen_negatif" : round(negatif / total * 100, 1),
            "ulasan"         : df[[
                "Kategori","Nama Reviewer", "Bintang", "Tanggal",
                "Ulasan", "teks_final","topik", "sentimen", "sentimen_score"
            ]].to_dict(orient="records"),
        }

        json_out = os.path.join(folder, "ulasan_sentimen.json")
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"   💾 {json_out}")

        # Kumpulkan untuk summary global (tanpa detail ulasan)
        all_summary.append({k: v for k, v in summary.items() if k != "ulasan"})

    # Simpan 1 JSON gabungan semua tempat (untuk halaman overview dashboard)
    summary_path = os.path.join(OUTPUT_DIR, "semua_tempat_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_summary, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Summary semua tempat → {summary_path}")


# ════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    # 1. Scraping
    results = scrape_google_maps()

    # 2. Load IndoBERT sekali untuk semua tempat
    pipe = load_indobert()

    # 3. Preprocessing + Sentiment per tempat
    process_per_tempat(results, pipe)