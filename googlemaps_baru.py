"""
Pipeline Lengkap — Analisis Sentimen Google Maps Kabupaten Gresik
=================================================================
Tahap 1 : cari_tempat()      → Scraping daftar tempat ke master_tempat.csv
Tahap 2 : scrape_google_maps() → Scraping ulasan per tempat (rotasi token)
Tahap 3 : analisis_sentimen() → Proses sentimen dari ulasan_mentah.json
Tahap 4 : scan_output()       → Rebuild semua_tempat_summary.json dari folder

Jalankan semua tahap sekaligus:
    python googlemaps_baru.py

Atau jalankan tahap tertentu:
    python googlemaps_baru.py --tahap cari
    python googlemaps_baru.py --tahap scrape
    python googlemaps_baru.py --tahap sentimen
    python googlemaps_baru.py --tahap scan
"""

import re
import csv
import json
import os
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

import pandas as pd
from dotenv import load_dotenv

try:
    from apify_client import ApifyClient
except ImportError:
    os.system("pip install apify-client")
    from apify_client import ApifyClient

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
except ImportError:
    os.system("pip install transformers torch")
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch

# ════════════════════════════════════════════════════════════════
# KONFIGURASI UMUM
# ════════════════════════════════════════════════════════════════

load_dotenv()

OUTPUT_DIR      = "output"
MASTER_FILE     = os.path.join(OUTPUT_DIR, "master_tempat.csv")
SUMMARY_FILE    = os.path.join(OUTPUT_DIR, "semua_tempat_summary.json")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.txt")
STATUS_FILE     = os.path.join(OUTPUT_DIR, "scrape_status.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Rotasi 3 token Apify ─────────────────────────────────────
TOKENS = [
    os.getenv("APIFY_API_TOKEN_1"),
    os.getenv("APIFY_API_TOKEN_2"),
    os.getenv("APIFY_API_TOKEN_3"),
]
TOKENS = [t for t in TOKENS if t]

# Fallback: token tunggal (untuk cari_tempat)
SINGLE_TOKEN = os.getenv("APIFY_API_TOKEN")

print(f"✅ {len(TOKENS)} token Apify (rotasi) terbaca")

token_index = 0


# ════════════════════════════════════════════════════════════════
# HELPER UMUM
# ════════════════════════════════════════════════════════════════

def get_folder(nama: str) -> str:
    """Ubah nama tempat menjadi nama folder yang aman."""
    return re.sub(r'[^a-z0-9]+', '_', nama.lower()).strip('_')


def update_status(platform: str, success: bool, message: str = ""):
    status = {}
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, "r") as f:
            status = json.load(f)
    status[platform] = {
        "success" : success,
        "message" : message,
        "last_run": datetime.now().strftime("%d %B %Y %H:%M"),
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)


# ════════════════════════════════════════════════════════════════
# TAHAP 1 — CARI TEMPAT
# ════════════════════════════════════════════════════════════════

KATEGORI_CARI = {
    "Pemerintahan": [
        "kantor pemerintah gresik",
        "kantor dinas gresik",
        "kantor kecamatan gresik",
        "kantor kelurahan gresik",
    ],
    "Kesehatan": [
        "rumah sakit gresik",
        "puskesmas gresik",
        "klinik gresik",
    ],
    "Pendidikan": [
        "sd gresik",
        "smp gresik",
        "sma gresik",
        "smk gresik",
        "universitas gresik",
    ],
    "Pelayanan Publik": [
        "mall pelayanan publik gresik",
        "kantor pos gresik",
        "samsat gresik",
    ],
    "Perbankan": [
        "bank bca gresik",
        "bank bri gresik",
        "bank mandiri gresik",
        "bank bni gresik",
    ],
    "Wisata": [
        "wisata gresik",
        "pantai gresik",
        "museum gresik",
    ],
    "Olahraga": [
        "stadion gresik",
        "gor gresik",
    ],
}


def cari_tempat():
    """
    Tahap 1: Scraping daftar tempat per kategori → master_tempat.csv
    Menggunakan APIFY_API_TOKEN tunggal (bukan rotasi).
    """
    print("\n" + "=" * 60)
    print("TAHAP 1 — MENCARI DAFTAR TEMPAT")
    print("=" * 60)

    token = SINGLE_TOKEN or (TOKENS[0] if TOKENS else None)
    if not token:
        print("❌ Tidak ada token Apify. Set APIFY_API_TOKEN di .env")
        return

    client = ApifyClient(token)
    semua_tempat = []

    for kategori, keyword_list in KATEGORI_CARI.items():
        print(f"\n========== {kategori} ==========")
        for keyword in keyword_list:
            print("Cari :", keyword)
            run_input = {
                "searchStringsArray"       : [keyword],
                "locationQuery"            : "Gresik, Jawa Timur, Indonesia",
                "maxCrawledPlacesPerSearch": 30,
                "includeReviews"           : False,
                "language"                 : "id",
            }
            run     = client.actor("compass/crawler-google-places").call(run_input=run_input)
            dataset = client.dataset(run.default_dataset_id)
            for item in dataset.iterate_items():
                semua_tempat.append({
                    "kategori"     : kategori,
                    "nama"         : item.get("title", ""),
                    "alamat"       : item.get("address", ""),
                    "rating"       : item.get("totalScore", ""),
                    "jumlah_ulasan": item.get("reviewsCount", ""),
                })

    df = pd.DataFrame(semua_tempat)
    df.drop_duplicates(subset=["nama"], inplace=True)
    df.sort_values(["kategori", "nama"], inplace=True)
    df.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")

    print(f"\n✅ Master tempat disimpan: {len(df)} tempat → {MASTER_FILE}")
    print(df.head())


# ════════════════════════════════════════════════════════════════
# TAHAP 2 — SCRAPE ULASAN GOOGLE MAPS (ROTASI TOKEN)
# ════════════════════════════════════════════════════════════════

EXCLUDE_KEYWORDS = [
    "atm", "bank", "bca", "bni", "bri", "mandiri", "brilink",
    "indomaret", "alfamart", "minimarket", "spbu", "agen",
    "toko", "warung", "resto", "kafe", "salon", "barbershop",
    "apotek", "laundry", "bengkel", "dealer", "hotel", "kost",
]


def is_valid_tempat(nama: str) -> bool:
    nama_lower = nama.lower()
    return not any(ex in nama_lower for ex in EXCLUDE_KEYWORDS)


def get_client():
    return ApifyClient(TOKENS[token_index])


def rotate_token():
    global token_index
    token_index = (token_index + 1) % len(TOKENS)
    print(f"🔄 Rotasi ke token {token_index + 1}")


def run_actor(run_input: dict, max_retry: int = None) -> list:
    if max_retry is None:
        max_retry = max(len(TOKENS), 1)
    for attempt in range(max_retry):
        try:
            client = get_client()
            run    = client.actor("compass/crawler-google-places").call(run_input=run_input)
            return list(client.dataset(run.default_dataset_id).iterate_items())
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ["402", "limit", "quota", "payment", "credit", "exceed", "usage", "subscription"]):
                print(f"⚠️  Token {token_index + 1} kena limit: {str(e)[:80]}")
                rotate_token()
            elif any(k in err for k in ["dns", "connect", "network", "timeout", "host"]):
                print(f"⚠️  Koneksi terputus (attempt {attempt + 1}), tunggu 10 detik...")
                time.sleep(10)
            else:
                print(f"❌ Error: {e}")
                raise
    print("❌ Semua token habis limit, skip tempat ini.")
    return []


def get_checkpoint() -> int:
    if os.path.exists(CHECKPOINT_FILE):
        try:
            return int(open(CHECKPOINT_FILE).read().strip())
        except Exception:
            return 0
    return 0


def save_checkpoint(index: int):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(index))


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


def scrape_google_maps():
    """
    Tahap 2: Scraping ulasan per tempat dari master_tempat.csv.
    Mendukung checkpoint (resume jika terputus).
    """
    print("\n" + "=" * 60)
    print("TAHAP 2 — SCRAPING ULASAN GOOGLE MAPS")
    print("=" * 60)

    if not TOKENS:
        print("❌ Tidak ada token rotasi. Set APIFY_API_TOKEN_1/2/3 di .env")
        return []

    if not os.path.exists(MASTER_FILE):
        print("⚠️  master_tempat.csv belum ada, jalankan tahap 'cari' dulu.")
        return []

    master      = pd.read_csv(MASTER_FILE)
    results     = []
    start_index = get_checkpoint()

    if start_index > 0:
        nama_lanjut = master.iloc[start_index]["nama"] if start_index < len(master) else "selesai"
        print(f"⏩ Melanjutkan dari tempat ke-{start_index + 1}: {nama_lanjut}\n")
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
            continue

        print(f"[{i + 1}/{len(master)}] 📍 {row['nama']}")
        data = run_actor({
            "searchStringsArray"       : [row["nama"]],
            "maxCrawledPlacesPerSearch": 1,
            "includeReviews"           : True,
            "maxReviews"               : 30,
            "language"                 : "id",
        })

        if data:
            data[0]["kategori"] = row["kategori"]
            results.extend(data)
            nama   = data[0].get("title", row["nama"])
            folder = os.path.join(OUTPUT_DIR, get_folder(nama))
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "ulasan_mentah.json"), "w", encoding="utf-8") as f:
                json.dump(data[0], f, ensure_ascii=False, indent=2)
        else:
            print(f"   ⚠️  Tidak ada data, skip.")

        save_checkpoint(i + 1)
        print(f"   ✅ Checkpoint: {i + 1}/{len(master)}")

    clear_checkpoint()
    print(f"\n✅ Scraping selesai! Total {len(results)} tempat")

    if not results:
        update_status("gmaps", False, "Tidak ada data — semua token habis atau error")

    for place in results:
        print(f"   📍 {place.get('title')} | {place.get('kategori')} | {place.get('reviewsCount')} ulasan")

    return results


# ════════════════════════════════════════════════════════════════
# SHARED — PREPROCESSING TEKS & DETEKSI TOPIK
# ════════════════════════════════════════════════════════════════

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
    "rmh sakit": "rumah sakit", "rs": "rumah sakit", "kmr": "kamar",
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

TOPIC_RULES = {
    "Pelayanan"    : ["pelayanan", "layanan", "petugas", "pegawai", "ramah", "cepat", "lambat", "antri", "antrian", "administrasi", "birokrasi", "loket"],
    "Fasilitas"    : ["fasilitas", "gedung", "ruangan", "toilet", "parkir", "kursi", "wifi", "ac", "bersih", "kotor", "nyaman"],
    "Kesehatan"    : ["dokter", "perawat", "rumah sakit", "puskesmas", "obat", "pasien", "bpjs", "igd", "rawat"],
    "Administrasi" : ["ktp", "kk", "akta", "nik", "dokumen", "berkas", "izin", "surat", "disdukcapil"],
    "Infrastruktur": ["jalan", "bangunan", "renovasi", "akses", "lift", "tangga", "trotoar", "parkiran"],
    "Keamanan"     : ["satpam", "aman", "keamanan", "polisi", "security"],
}

LABEL_MAP = {"LABEL_0": "Negatif", "LABEL_1": "Netral", "LABEL_2": "Positif"}

KATEGORI_MAP = {
    "kantor": "Pemerintahan", "dinas": "Pemerintahan", "kecamatan": "Pemerintahan",
    "kelurahan": "Pemerintahan", "bupati": "Pemerintahan", "sekretariat": "Pemerintahan",
    "dprd": "Pemerintahan", "polsek": "Pemerintahan", "polres": "Pemerintahan",
    "koramil": "Pemerintahan", "kodim": "Pemerintahan", "kejaksaan": "Pemerintahan",
    "pengadilan": "Pemerintahan",
    "rsud": "Kesehatan", "rsu": "Kesehatan", "puskesmas": "Kesehatan",
    "klinik": "Kesehatan", "apotek": "Kesehatan", "rumah_sakit": "Kesehatan",
    "sma": "Pendidikan", "smk": "Pendidikan", "smp": "Pendidikan","upt": "Pendidikan",
    "Upt": "Pendidikan",
    "universitas": "Pendidikan", "kampus": "Pendidikan", "sekolah": "Pendidikan",
    "madrasah": "Pendidikan", "pesantren": "Pendidikan",
    "disdukcapil": "Pelayanan Publik", "samsat": "Pelayanan Publik",
    "mall_pelayanan": "Pelayanan Publik", "imigrasi": "Pelayanan Publik",
    "bpjs": "Pelayanan Publik", "pos": "Pelayanan Publik", "kua": "Pelayanan Publik",
    "bpn": "Pelayanan Publik", "pajak": "Pelayanan Publik",
    "brilink": "Perbankan", "atm": "Perbankan", "bank": "Perbankan",
    "bri": "Perbankan", "bni": "Perbankan", "bca": "Perbankan",
    "mandiri": "Perbankan", "btn": "Perbankan", "bpr": "Perbankan",
    "pegadaian": "Perbankan", "koperasi": "Perbankan",
    "wisata": "Wisata", "pantai": "Wisata", "taman": "Wisata",
    "museum": "Wisata", "makam": "Wisata", "masjid": "Wisata",
    "petrokimia": "Industri", "semen": "Industri", "pabrik": "Industri",
    "pelabuhan": "Industri", "terminal": "Industri",
}


def get_kategori(folder_name: str) -> str:
    # Prioritas 1: dari master CSV
    if os.path.exists(MASTER_FILE):
        try:
            df_master = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
            for _, row in df_master.iterrows():
                if get_folder(str(row["nama"])) == folder_name:
                    return str(row["kategori"])
        except Exception:
            pass

    # Prioritas 2: dari ulasan_mentah.json (ada field kategori)
    mentah_path = os.path.join(OUTPUT_DIR, folder_name, "ulasan_mentah.json")
    if os.path.exists(mentah_path):
        try:
            with open(mentah_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("kategori"):
                return data["kategori"]
        except Exception:
            pass

    # Prioritas 3: tebak dari nama folder (keyword matching)
    keywords_pendidikan = ["sdn", "sd_", "smpn", "smp_", "sman", "sma_", "smkn",
                           "smk_", "mts", "man_", "mi_", "upt_sd", "upt_smp",
                           "upt_sma", "upt_smk", "negeri", "sekolah", "madrasah",
                           "pesantren", "universitas", "kampus", "akademi"]
    keywords_kesehatan  = ["puskesmas", "pkm", "rsud", "rsu_", "rsia", "rs_",
                           "klinik", "apotek", "rumah_sakit"]
    keywords_pemda      = ["kantor", "dinas", "kecamatan", "kelurahan", "bupati",
                           "sekretariat", "dprd", "polsek", "polres", "koramil",
                           "kodim", "kejaksaan", "pengadilan", "kec_", "kel_"]
    keywords_publik     = ["disdukcapil", "samsat", "mall_pelayanan", "imigrasi",
                           "bpjs", "kantor_pos", "kua", "bpn", "pajak"]
    keywords_perbankan  = ["bank", "bri", "bni", "bca", "mandiri", "btn", "bpr",
                           "pegadaian", "koperasi", "atm", "brilink"]
    keywords_wisata     = ["wisata", "pantai", "taman", "museum", "makam",
                           "masjid", "waduk", "alam"]
    keywords_olahraga   = ["stadion", "gor_", "lapangan", "kolam_renang", "sport"]
    keywords_industri   = ["petrokimia", "semen", "pabrik", "pelabuhan", "terminal"]

    checks = [
        (keywords_pendidikan, "Pendidikan"),
        (keywords_kesehatan,  "Kesehatan"),
        (keywords_pemda,      "Pemerintahan"),
        (keywords_publik,     "Pelayanan Publik"),
        (keywords_perbankan,  "Perbankan"),
        (keywords_wisata,     "Wisata"),
        (keywords_olahraga,   "Olahraga"),
        (keywords_industri,   "Industri"),
    ]
    for keywords, kat in checks:
        if any(kw in folder_name for kw in keywords):
            return kat

    return "Lainnya" 


def clean_text(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'http\S+|www\S+', '', text)
    text = re.sub(r'@\w+|#\w+', '', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\b\d+\b', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def normalize_slang(text: str) -> str:
    return ' '.join(SLANG_DICT.get(w, w) for w in text.split()).strip()


def remove_stopwords(text: str) -> str:
    return ' '.join(w for w in text.split() if w not in STOPWORDS_ID and len(w) > 1)


def preprocess(text: str) -> dict:
    s1 = clean_text(text)
    s2 = normalize_slang(s1)
    s3 = remove_stopwords(s2)
    return {"cleaned": s1, "normalized": s2, "final": s3}


def detect_topic(text: str) -> str:
    text = text.lower()
    for topic, keywords in TOPIC_RULES.items():
        for kw in keywords:
            if kw in text:
                return topic
    return "Lainnya"


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


# ════════════════════════════════════════════════════════════════
# KOREKSI SENTIMEN BERDASARKAN BINTANG
# ════════════════════════════════════════════════════════════════
# Model IndoBERT terkadang salah membaca teks ulasan pendek/ambigu
# (misal: teks positif tapi diberi label "Negatif"). Fungsi ini
# mengoreksi hasil model menggunakan rating bintang sebagai sinyal
# tambahan yang lebih bisa dipercaya karena diisi langsung oleh user.
#
# Aturan:
#   - Bintang 4 atau 5  -> kuat condong Positif.
#                          Jika model bilang "Negatif", diubah jadi "Positif".
#   - Bintang 1 atau 2  -> kuat condong Negatif.
#                          Jika model bilang "Positif", diubah jadi "Negatif".
#   - Bintang 3, 0, atau kosong/tidak valid -> tidak ada sinyal kuat,
#                          hasil model dibiarkan apa adanya.
# ════════════════════════════════════════════════════════════════

def koreksi_dengan_bintang(label_model: str, bintang) -> str:
    try:
        bintang = int(bintang)
    except (ValueError, TypeError):
        return label_model

    if bintang >= 4:
        if label_model == "Negatif":
            return "Positif"
        return label_model
    elif bintang <= 2 and bintang >= 1:
        if label_model == "Positif":
            return "Negatif"
        return label_model
    else:
        # bintang == 3, atau bintang == 0 / tidak ada data
        return label_model


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
    print("✅ Model IndoBERT siap!")
    return pipe


# ════════════════════════════════════════════════════════════════
# TAHAP 3 — ANALISIS SENTIMEN (dari ulasan_mentah.json)
# ════════════════════════════════════════════════════════════════

def analisis_sentimen(pipe=None):
    """
    Tahap 3: Proses sentimen untuk semua folder yang punya ulasan_mentah.json
    tapi belum punya ulasan_sentimen.json.
    Jika pipe tidak diberikan, model akan dimuat otomatis.
    """
    print("\n" + "=" * 60)
    print("TAHAP 3 — ANALISIS SENTIMEN INDOBERT")
    print("=" * 60)

    if pipe is None:
        pipe = load_indobert()

    all_summary = []
    folders     = sorted(os.listdir(OUTPUT_DIR))
    total       = len([f for f in folders if os.path.isdir(os.path.join(OUTPUT_DIR, f))])
    diproses    = 0
    diskip      = 0

    for i, folder_name in enumerate(folders):
        folder_path   = os.path.join(OUTPUT_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        json_sentimen = os.path.join(folder_path, "ulasan_sentimen.json")
        json_mentah   = os.path.join(folder_path, "ulasan_mentah.json")

        # Sudah ada sentimen — langsung load
        if os.path.exists(json_sentimen):
            with open(json_sentimen, "r", encoding="utf-8") as f:
                data = json.load(f)
            all_summary.append({
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
            print(f"[{i + 1}/{total}] 📂 Load: {data.get('tempat', folder_name)}")
            continue

        # Belum ada sentimen — proses dari mentah
        if not os.path.exists(json_mentah):
            diskip += 1
            continue

        with open(json_mentah, "r", encoding="utf-8") as f:
            place = json.load(f)

        nama    = place.get("title", folder_name)
        reviews = place.get("reviews", [])
        kat     = get_kategori(folder_name)

        print(f"[{i + 1}/{total}] 🔍 Proses: {nama} ({len(reviews)} ulasan)")

        if not reviews:
            all_summary.append({
                "key": folder_name, "kategori": kat, "tempat": nama,
                "rating": place.get("totalScore", 0), "total_ulasan": 0,
                "positif": 0, "netral": 0, "negatif": 0,
                "persen_positif": 0, "persen_netral": 0, "persen_negatif": 0,
            })
            continue

        rows = []
        for r in reviews:
            rows.append({
                "Kategori"     : kat,
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

        preproc = df["Ulasan"].apply(preprocess)
        df["teks_cleaned"]    = preproc.apply(lambda x: x["cleaned"])
        df["teks_normalized"] = preproc.apply(lambda x: x["normalized"])
        df["teks_final"]      = preproc.apply(lambda x: x["final"])
        df["topik"]           = df["teks_final"].apply(detect_topic)
        df = df[df["teks_final"].str.strip() != ""]

        sentiments           = [predict_sentiment(pipe, t) for t in df["teks_final"]]
        df["sentimen"]       = [s["label"] for s in sentiments]
        df["sentimen_score"] = [s["score"] for s in sentiments]

        # ── Koreksi sentimen berdasarkan bintang ──────────────
        df["sentimen"] = [
            koreksi_dengan_bintang(label, bintang)
            for label, bintang in zip(df["sentimen"], df["Bintang"])
        ]

        total_u = len(df)
        positif = int((df["sentimen"] == "Positif").sum())
        netral  = int((df["sentimen"] == "Netral").sum())
        negatif = int((df["sentimen"] == "Negatif").sum())
        rating  = place.get("totalScore", 0)

        summary_item = {
            "kategori"      : kat,
            "tempat"        : nama,
            "rating"        : rating,
            "total_ulasan"  : total_u,
            "positif"       : positif,
            "netral"        : netral,
            "negatif"       : negatif,
            "persen_positif": round(positif / total_u * 100, 1) if total_u else 0,
            "persen_netral" : round(netral  / total_u * 100, 1) if total_u else 0,
            "persen_negatif": round(negatif / total_u * 100, 1) if total_u else 0,
            "ulasan"        : df[[
                "Kategori", "Nama Reviewer", "Bintang", "Tanggal",
                "Ulasan", "teks_final", "topik", "sentimen", "sentimen_score"
            ]].to_dict(orient="records"),
        }

        with open(json_sentimen, "w", encoding="utf-8") as f:
            json.dump(summary_item, f, ensure_ascii=False, indent=2)

        df.to_csv(os.path.join(folder_path, "ulasan_sentimen.csv"), index=False, encoding="utf-8-sig")

        all_summary.append({k: v for k, v in summary_item.items() if k != "ulasan"} | {"key": folder_name})
        diproses += 1
        print(f"   ✅ {positif}P / {netral}N / {negatif}Neg")

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"✅ Selesai! {diproses} diproses, {len(all_summary)} total tempat")
    print(f"💾 {SUMMARY_FILE}")

    return pipe  # kembalikan pipe supaya bisa dipakai process_per_tempat


# ════════════════════════════════════════════════════════════════
# TAHAP 3b — PROCESS PER TEMPAT (dari hasil scrape langsung)
# ════════════════════════════════════════════════════════════════

def process_per_tempat(results: list, pipe):
    """
    Alternatif Tahap 3: proses sentimen langsung dari list results
    (output scrape_google_maps), bukan dari folder.
    """
    print(f"\n{'=' * 60}")
    print("📊 PREPROCESSING + SENTIMENT PER TEMPAT")
    print(f"{'=' * 60}")

    all_summary = []

    for place in results:
        nama    = place.get("title", "unknown")
        folder  = os.path.join(OUTPUT_DIR, get_folder(nama))
        os.makedirs(folder, exist_ok=True)
        reviews = place.get("reviews", [])

        print(f"\n📍 {nama}")
        if not reviews:
            print(f"   ⚠️  Tidak ada ulasan, dilewati.")
            continue

        rows = []
        for r in reviews:
            rows.append({
                "Kategori"     : place.get("kategori"),
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

        preproc = df["Ulasan"].apply(preprocess)
        df["teks_cleaned"]    = preproc.apply(lambda x: x["cleaned"])
        df["teks_normalized"] = preproc.apply(lambda x: x["normalized"])
        df["teks_final"]      = preproc.apply(lambda x: x["final"])
        df["topik"]           = df["teks_final"].apply(detect_topic)
        df = df[df["teks_final"].str.strip() != ""]

        print(f"   🔍 Menganalisis {len(df)} ulasan...")
        sentiments           = [predict_sentiment(pipe, t) for t in df["teks_final"]]
        df["sentimen"]       = [s["label"] for s in sentiments]
        df["sentimen_score"] = [s["score"] for s in sentiments]

        # ── Koreksi sentimen berdasarkan bintang ──────────────
        df["sentimen"] = [
            koreksi_dengan_bintang(label, bintang)
            for label, bintang in zip(df["sentimen"], df["Bintang"])
        ]

        total   = len(df)
        positif = int((df["sentimen"] == "Positif").sum())
        netral  = int((df["sentimen"] == "Netral").sum())
        negatif = int((df["sentimen"] == "Negatif").sum())
        rating  = place.get("totalScore", "")

        print(f"   ⭐ Rating  : {rating}")

        # ✅ Tambah pengecekan total == 0
        if total == 0:
            print("   ⚠️  Semua ulasan kosong setelah preprocessing, skip.")
            continue

        print(f"   ✅ Positif : {positif} ({positif / total * 100:.1f}%)")
        print(f"   ➖ Netral  : {netral}  ({netral  / total * 100:.1f}%)")
        print(f"   ❌ Negatif : {negatif} ({negatif / total * 100:.1f}%)")

        csv_out = os.path.join(folder, "ulasan_sentimen.csv")
        df.to_csv(csv_out, index=False, encoding="utf-8-sig")
        print(f"   💾 {csv_out}")

        summary = {
            "kategori"      : place.get("kategori"),
            "tempat"        : nama,
            "rating"        : rating,
            "total_ulasan"  : total,
            "positif"       : positif,
            "netral"        : netral,
            "negatif"       : negatif,
            "persen_positif": round(positif / total * 100, 1),
            "persen_netral" : round(netral   / total * 100, 1),
            "persen_negatif": round(negatif  / total * 100, 1),
            "ulasan"        : df[[
                "Kategori", "Nama Reviewer", "Bintang", "Tanggal",
                "Ulasan", "teks_final", "topik", "sentimen", "sentimen_score"
            ]].to_dict(orient="records"),
        }

        json_out = os.path.join(folder, "ulasan_sentimen.json")
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"   💾 {json_out}")

        all_summary.append({
            **{k: v for k, v in summary.items() if k != "ulasan"},
            "key": get_folder(nama),
        })

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_summary, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Summary semua tempat → {SUMMARY_FILE}")
    update_status("gmaps", True, f"Berhasil {len(all_summary)} tempat diproses")


# ════════════════════════════════════════════════════════════════
# TAHAP 4 — SCAN OUTPUT (rebuild summary dari folder)
# ════════════════════════════════════════════════════════════════

def scan_output():
    """
    Tahap 4: Rebuild semua_tempat_summary.json dari semua folder output.
    Berguna untuk sinkronisasi ulang tanpa harus scrape/sentimen ulang.
    """
    print("\n" + "=" * 60)
    print("TAHAP 4 — SCAN OUTPUT & REBUILD SUMMARY")
    print("=" * 60)

    # Load master CSV untuk mapping nama → kategori
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

    summary = []
    skipped = []
    folders = sorted(os.listdir(OUTPUT_DIR))

    for folder_name in folders:
        folder_path = os.path.join(OUTPUT_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        json_sentimen = os.path.join(folder_path, "ulasan_sentimen.json")
        json_mentah   = os.path.join(folder_path, "ulasan_mentah.json")

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


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

TAHAP_MAP = {
    "cari"    : "Tahap 1 — Cari Tempat",
    "scrape"  : "Tahap 2 — Scrape Ulasan",
    "sentimen": "Tahap 3 — Analisis Sentimen",
    "scan"    : "Tahap 4 — Scan Output",
}

if __name__ == "__main__":
    args  = sys.argv[1:]
    tahap = None

    # Cek argumen --tahap
    if "--tahap" in args:
        idx   = args.index("--tahap")
        tahap = args[idx + 1] if idx + 1 < len(args) else None

    if tahap and tahap not in TAHAP_MAP:
        print(f"❌ Tahap tidak dikenal: '{tahap}'")
        print(f"   Pilihan: {', '.join(TAHAP_MAP.keys())}")
        sys.exit(1)

    if tahap == "cari":
        cari_tempat()

    elif tahap == "scrape":
        scrape_google_maps()

    elif tahap == "sentimen":
        analisis_sentimen()

    elif tahap == "scan":
        scan_output()

    else:
        # Jalankan semua tahap secara berurutan
        print("🚀 Menjalankan semua tahap pipeline...\n")

        # Tahap 1
        cari_tempat()

        # Tahap 2
        results = scrape_google_maps()

        # Tahap 3 — pakai process_per_tempat jika ada results dari scrape,
        # atau analisis_sentimen jika hanya perlu proses folder yang ada
        if results:
            pipe = load_indobert()
            process_per_tempat(results, pipe)
        else:
            analisis_sentimen()

        # Tahap 4
        scan_output()

        print("\n🎉 Semua tahap selesai!")