"""
====================================================================
PIPELINE LENGKAP — DASHBOARD GRESIK
====================================================================
Urutan proses:
  1. Cari tempat Google Maps → output/master_tempat.csv
  2. Analisis sentimen ulasan Google Maps → output/semua_tempat_summary.json
  3. Scraping & sentimen komentar Instagram → output/gresik_ig_*.csv

INSTALL:
    pip install selenium pandas transformers torch webdriver-manager
    pip install apify-client python-dotenv

CARA PAKAI:
    python pipeline.py                  # jalankan semua
    python pipeline.py --step gmaps     # hanya Google Maps (cari + sentimen)
    python pipeline.py --step instagram # hanya Instagram
    python pipeline.py --step sentimen  # hanya analisis sentimen GM (skip cari tempat)
====================================================================
"""

import argparse
import json
import os
import random
import re
import time
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
#  KONFIGURASI
# ══════════════════════════════════════════════════════════════════

# ── Google Maps / Apify ───────────────────────────────────────────
APIFY_TOKEN  = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_TOKEN_1", "")
OUTPUT_DIR   = "output"
MASTER_FILE  = os.path.join(OUTPUT_DIR, "master_tempat.csv")
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "semua_tempat_summary.json")
MASTER_KATEGORI_FILE = "master_tempat.csv"

KATEGORI_GMAPS = {
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
        "sd gresik", "smp gresik", "sma gresik",
        "smk gresik", "universitas gresik",
    ],
    "Pelayanan Publik": [
        "mall pelayanan publik gresik",
        "kantor pos gresik",
        "samsat gresik",
    ],
    "Perbankan": [
        "bank bca gresik", "bank bri gresik",
        "bank mandiri gresik", "bank bni gresik",
    ],
    "Wisata": [
        "wisata gresik", "pantai gresik", "museum gresik",
    ],
    "Olahraga": [
        "stadion gresik", "gor gresik",
    ],
    "Industri": [
        "pabrik gresik", "petrokimia gresik", "semen gresik",
    ],
}

# ── Instagram ─────────────────────────────────────────────────────
IG_COOKIES = {
    "sessionid"  : os.getenv("IG_SESSIONID", ""),
    "csrftoken"  : os.getenv("IG_CSRFTOKEN", ""),
    "ds_user_id" : os.getenv("IG_DS_USER_ID", ""),
    "mid"        : os.getenv("IG_MID", ""),
    "ig_did"     : os.getenv("IG_DID", ""),
    "rur"        : os.getenv("IG_RUR", ""),
}
IG_KEYWORDS              = ["Gresik"]
MAKS_POST_PER_KEYWORD    = 30
MAKS_KOMENTAR_PER_POST   = 50

# ── Model Sentimen ────────────────────────────────────────────────
MODEL_NAME = "mdhugol/indonesia-bert-sentiment-classification"
LABEL_MAP_GM = {"LABEL_0": "Negatif", "LABEL_1": "Netral",  "LABEL_2": "Positif"}
LABEL_MAP_IG = {"LABEL_0": "positif", "LABEL_1": "netral",  "LABEL_2": "negatif"}

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════
#  MASTER KATEGORI
# ══════════════════════════════════════════════════════════════════

PRIORITAS_KEYWORD = [
    ("gor",          "Olahraga"),   ("stadion",      "Olahraga"),
    ("gelora",       "Olahraga"),   ("lapangan",     "Olahraga"),
    ("futsal",       "Olahraga"),   ("sport",        "Olahraga"),
    ("renang",       "Olahraga"),   ("gym",          "Olahraga"),
    ("fitness",      "Olahraga"),   ("badminton",    "Olahraga"),
    ("tenis",        "Olahraga"),   ("basket",       "Olahraga"),
    ("voli",         "Olahraga"),
    ("rsud",         "Kesehatan"),  ("rsu",          "Kesehatan"),
    ("puskesmas",    "Kesehatan"),  ("klinik",       "Kesehatan"),
    ("apotek",       "Kesehatan"),  ("posyandu",     "Kesehatan"),
    ("sekolah",      "Pendidikan"), ("universitas",  "Pendidikan"),
    ("pesantren",    "Pendidikan"), ("madrasah",     "Pendidikan"),
    ("smk",          "Pendidikan"), ("sma",          "Pendidikan"),
    ("smp",          "Pendidikan"), ("sdn",          "Pendidikan"),
    ("kantor",       "Pemerintahan"), ("dinas",      "Pemerintahan"),
    ("kecamatan",    "Pemerintahan"), ("kelurahan",  "Pemerintahan"),
    ("polsek",       "Pemerintahan"), ("polres",     "Pemerintahan"),
    ("koramil",      "Pemerintahan"), ("kodim",      "Pemerintahan"),
    ("disdukcapil",  "Pelayanan Publik"), ("samsat", "Pelayanan Publik"),
    ("imigrasi",     "Pelayanan Publik"), ("bpjs",   "Pelayanan Publik"),
    ("petrokimia",   "Industri"),   ("semen",        "Industri"),
    ("pabrik",       "Industri"),   ("pelabuhan",    "Industri"),
    ("wisata",       "Wisata"),     ("pantai",       "Wisata"),
    ("museum",       "Wisata"),     ("makam",        "Wisata"),
    ("taman",        "Wisata"),     ("danau",        "Wisata"),
    ("bank",         "Perbankan"),  ("atm",          "Perbankan"),
    ("bri",          "Perbankan"),  ("bni",          "Perbankan"),
    ("bca",          "Perbankan"),  ("mandiri",      "Perbankan"),
    ("restoran",     "Kuliner"),    ("warung",       "Kuliner"),
    ("cafe",         "Kuliner"),    ("depot",        "Kuliner"),
]


def load_master_kategori() -> dict:
    path = MASTER_KATEGORI_FILE
    if not os.path.exists(path):
        path = MASTER_FILE  # fallback ke output/master_tempat.csv
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path)
        return {
            str(row["nama"]).strip().lower(): str(row["kategori"]).strip()
            for _, row in df.iterrows()
        }
    except Exception as e:
        print(f"⚠️  Gagal load master: {e}")
        return {}


def get_kategori(folder_name: str, nama_tempat: str = "", master: dict = {}) -> str:
    # Prioritas 1 — master CSV
    if nama_tempat and master:
        nama_lower = nama_tempat.strip().lower()
        if nama_lower in master:
            return master[nama_lower]
        for k, v in master.items():
            if k in nama_lower or nama_lower in k:
                return v
    # Prioritas 2 — keyword
    cek = (folder_name + " " + nama_tempat).lower()
    for keyword, kategori in PRIORITAS_KEYWORD:
        if keyword in cek:
            return kategori
    return "Lainnya"


# ══════════════════════════════════════════════════════════════════
#  STEP 1 — CARI TEMPAT GOOGLE MAPS (Apify)
# ══════════════════════════════════════════════════════════════════

def step_cari_tempat():
    print("\n" + "="*60)
    print("  STEP 1 — CARI TEMPAT GOOGLE MAPS")
    print("="*60)

    if not APIFY_TOKEN:
        print("⚠️  APIFY_API_TOKEN tidak ditemukan di .env, step ini dilewati.")
        return

    from apify_client import ApifyClient
    client = ApifyClient(APIFY_TOKEN)

    semua_tempat = []
    for kategori, keyword_list in KATEGORI_GMAPS.items():
        print(f"\n── {kategori} ──")
        for keyword in keyword_list:
            print(f"  Cari: {keyword}")
            try:
                run = client.actor("compass/crawler-google-places").call(
                    run_input={
                        "searchStringsArray"          : [keyword],
                        "locationQuery"               : "Gresik, Jawa Timur, Indonesia",
                        "maxCrawledPlacesPerSearch"   : 30,
                        "includeReviews"              : False,
                        "language"                    : "id",
                    }
                )
                for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                    semua_tempat.append({
                        "kategori"      : kategori,
                        "nama"          : item.get("title", ""),
                        "alamat"        : item.get("address", ""),
                        "rating"        : item.get("totalScore", ""),
                        "jumlah_ulasan" : item.get("reviewsCount", ""),
                    })
            except Exception as e:
                print(f"  ❌ Gagal: {e}")

    df = pd.DataFrame(semua_tempat)
    df.drop_duplicates(subset=["nama"], inplace=True)
    df.sort_values(["kategori", "nama"], inplace=True)
    df.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")

    print(f"\n✅ Total tempat ditemukan : {len(df)}")
    print(f"   Disimpan ke            : {MASTER_FILE}")


# ══════════════════════════════════════════════════════════════════
#  STEP 2 — ANALISIS SENTIMEN GOOGLE MAPS
# ══════════════════════════════════════════════════════════════════

SLANG_DICT = {
    "yg":"yang","dgn":"dengan","utk":"untuk","krn":"karena",
    "sdh":"sudah","blm":"belum","tdk":"tidak","ga":"tidak",
    "gak":"tidak","nggak":"tidak","ngga":"tidak","gk":"tidak",
    "bgt":"banget","bngt":"banget","sgt":"sangat","skrg":"sekarang",
    "klo":"kalau","klu":"kalau","kl":"kalau","tp":"tapi",
    "tpi":"tapi","ttg":"tentang","dr":"dari","dlm":"dalam",
    "dg":"dengan","sm":"sama","jg":"juga","hrs":"harus",
    "msh":"masih","lbh":"lebih","krng":"kurang","byk":"banyak",
    "plg":"paling","pd":"pada","spy":"supaya","sy":"saya",
    "gue":"saya","gw":"saya","loe":"kamu","lu":"kamu",
    "lo":"kamu","ok":"oke","oks":"oke","mantap":"bagus",
    "mantul":"bagus","keren":"bagus","jos":"bagus",
    "wkwk":"","haha":"","hehe":"","wkwkwk":"",
    "antri":"antrian","ngantri":"antrian",
    "rmh sakit":"rumah sakit","rs":"rumah sakit","kmr":"kamar",
}

STOPWORDS_ID = {
    "yang","dan","di","ke","dari","ini","itu","ada","dengan",
    "untuk","pada","adalah","dalam","tidak","juga","sudah",
    "saya","kami","kita","mereka","dia","ia","anda","kamu",
    "akan","bisa","dapat","oleh","atau","tapi","namun","tetapi",
    "jika","kalau","karena","saat","ketika","setelah","sebelum",
    "lebih","sangat","sekali","masih","belum","baru","lagi",
    "pun","nya","lah","kah","pula","sih","deh","dong",
}

TOPIC_RULES = {
    "Pelayanan"    : ["pelayanan","layanan","petugas","pegawai","ramah","cepat","lambat","antri","antrian","administrasi","birokrasi","loket"],
    "Fasilitas"    : ["fasilitas","gedung","ruangan","toilet","parkir","kursi","wifi","ac","bersih","kotor","nyaman"],
    "Kesehatan"    : ["dokter","perawat","rumah sakit","puskesmas","obat","pasien","bpjs","igd","rawat"],
    "Administrasi" : ["ktp","kk","akta","nik","dokumen","berkas","izin","surat","disdukcapil"],
    "Infrastruktur": ["jalan","bangunan","renovasi","akses","lift","tangga","trotoar","parkiran"],
    "Keamanan"     : ["satpam","aman","keamanan","polisi","security"],
}


def clean_text(text):
    if not text or not isinstance(text, str): return ""
    text = text.lower()
    text = re.sub(r'http\S+|www\S+', '', text)
    text = re.sub(r'@\w+|#\w+', '', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\b\d+\b', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def normalize_slang(text):
    return ' '.join(SLANG_DICT.get(w, w) for w in text.split()).strip()

def remove_stopwords(text):
    return ' '.join(w for w in text.split() if w not in STOPWORDS_ID and len(w) > 1)

def preprocess_gm(text):
    s1 = clean_text(text)
    s2 = normalize_slang(s1)
    s3 = remove_stopwords(s2)
    return {"cleaned": s1, "normalized": s2, "final": s3}

def detect_topic(text):
    text = text.lower()
    for topic, keywords in TOPIC_RULES.items():
        for kw in keywords:
            if kw in text:
                return topic
    return "Lainnya"


def koreksi_kategori_semua(master: dict):
    print("\n🔧 Mengoreksi kategori file lama...")
    diperbaiki = 0
    for folder_name in sorted(os.listdir(OUTPUT_DIR)):
        folder_path   = os.path.join(OUTPUT_DIR, folder_name)
        json_sentimen = os.path.join(folder_path, "ulasan_sentimen.json")
        if not os.path.isdir(folder_path) or not os.path.exists(json_sentimen):
            continue
        with open(json_sentimen, "r", encoding="utf-8") as f:
            data = json.load(f)
        nama_tempat   = data.get("tempat", folder_name)
        kategori_lama = data.get("kategori", "")
        kategori_baru = get_kategori(folder_name, nama_tempat, master)
        if kategori_lama != kategori_baru:
            print(f"   📝 {nama_tempat}: '{kategori_lama}' → '{kategori_baru}'")
            data["kategori"] = kategori_baru
            with open(json_sentimen, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            diperbaiki += 1
    print(f"   ✅ {diperbaiki} kategori dikoreksi." if diperbaiki else "   ✅ Semua kategori sudah benar.")


def step_sentimen_gmaps():
    print("\n" + "="*60)
    print("  STEP 2 — ANALISIS SENTIMEN GOOGLE MAPS")
    print("="*60)

    import torch
    from transformers import pipeline as hf_pipeline, AutoTokenizer, AutoModelForSequenceClassification

    print("🤖 Memuat model IndoBERT...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model_hf  = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
    pipe = hf_pipeline(
        "sentiment-analysis", model=model_hf, tokenizer=tokenizer,
        device=0 if torch.cuda.is_available() else -1,
        truncation=True, max_length=512,
    )
    print("✅ Model siap!\n")

    master = load_master_kategori()
    koreksi_kategori_semua(master)

    def predict_gm(text):
        if not text or len(text.strip()) < 3:
            return {"label": "Netral", "score": 0.0}
        try:
            r = pipe(text[:512])[0]
            return {"label": LABEL_MAP_GM.get(r["label"], r["label"]), "score": round(r["score"], 4)}
        except:
            return {"label": "Error", "score": 0.0}

    all_summary = []
    folders     = sorted(os.listdir(OUTPUT_DIR))
    total_folder= len([f for f in folders if os.path.isdir(os.path.join(OUTPUT_DIR, f))])
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
            nama_tempat = data.get("tempat", folder_name)
            kategori    = get_kategori(folder_name, nama_tempat, master)
            all_summary.append({
                "key"           : folder_name,
                "kategori"      : kategori,
                "tempat"        : nama_tempat,
                "rating"        : data.get("rating", 0),
                "total_ulasan"  : data.get("total_ulasan", 0),
                "positif"       : data.get("positif", 0),
                "netral"        : data.get("netral", 0),
                "negatif"       : data.get("negatif", 0),
                "persen_positif": data.get("persen_positif", 0),
                "persen_netral" : data.get("persen_netral", 0),
                "persen_negatif": data.get("persen_negatif", 0),
            })
            print(f"[{i+1}/{total_folder}] 📂 Load: {nama_tempat} ({kategori})")
            continue

        # Belum ada — proses dari mentah
        if not os.path.exists(json_mentah):
            diskip += 1
            continue

        with open(json_mentah, "r", encoding="utf-8") as f:
            place = json.load(f)

        nama    = place.get("title", folder_name)
        reviews = place.get("reviews", [])
        kat     = get_kategori(folder_name, nama, master)

        print(f"[{i+1}/{total_folder}] 🔍 Proses: {nama} | {kat} | {len(reviews)} ulasan")

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

        preproc               = df["Ulasan"].apply(preprocess_gm)
        df["teks_cleaned"]    = preproc.apply(lambda x: x["cleaned"])
        df["teks_normalized"] = preproc.apply(lambda x: x["normalized"])
        df["teks_final"]      = preproc.apply(lambda x: x["final"])
        df["topik"]           = df["teks_final"].apply(detect_topic)
        df = df[df["teks_final"].str.strip() != ""]

        sentiments           = [predict_gm(t) for t in df["teks_final"]]
        df["sentimen"]       = [s["label"] for s in sentiments]
        df["sentimen_score"] = [s["score"] for s in sentiments]

        total_u = len(df)
        positif = int((df["sentimen"] == "Positif").sum())
        netral  = int((df["sentimen"] == "Netral").sum())
        negatif = int((df["sentimen"] == "Negatif").sum())

        summary = {
            "kategori"      : kat,
            "tempat"        : nama,
            "rating"        : place.get("totalScore", 0),
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
            json.dump(summary, f, ensure_ascii=False, indent=2)
        df.to_csv(
            os.path.join(folder_path, "ulasan_sentimen.csv"),
            index=False, encoding="utf-8-sig"
        )

        all_summary.append(
            {k: v for k, v in summary.items() if k != "ulasan"} | {"key": folder_name}
        )
        diproses += 1
        print(f"   ✅ {positif}P / {netral}N / {negatif}Neg")

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_summary, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Selesai Google Maps!")
    print(f"   Diproses baru : {diproses}")
    print(f"   Total         : {len(all_summary)}")
    print(f"   Diskip        : {diskip}")
    print(f"   Output        : {SUMMARY_FILE}")


# ══════════════════════════════════════════════════════════════════
#  STEP 3 — SCRAPING & SENTIMEN INSTAGRAM
# ══════════════════════════════════════════════════════════════════

def update_status(platform, success, message=""):
    path = "output/scrape_status.json"
    status = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            status = json.load(f)
    import datetime
    status[platform] = {
        "success" : success,
        "message" : message,
        "last_run": datetime.datetime.now().strftime("%d %B %Y %H:%M"),
    }
    with open(path, "w") as f:
        json.dump(status, f, indent=2)


def jeda(min_s=1.5, max_s=3.5):
    time.sleep(random.uniform(min_s, max_s))


def bersihkan_teks_ig(teks):
    teks = re.sub(r"http\S+", "", teks)
    teks = re.sub(r"@\w+", "", teks)
    teks = re.sub(r"#(\w+)", r"\1", teks)
    teks = re.sub(r"[^\w\s]", "", teks)
    return re.sub(r"\s+", " ", teks).strip().lower()


def deteksi_topik_ig(teks):
    t = teks.lower()
    if any(k in t for k in ["banjir","longsor","gempa","bencana"]):        return "bencana"
    if any(k in t for k in ["pabrik","industri","petrokimia","semen","pupuk"]): return "industri"
    if any(k in t for k in ["kuliner","makanan","soto","bandeng","otak-otak"]): return "kuliner"
    if any(k in t for k in ["wisata","pantai","religi","sunan giri"]):      return "wisata"
    if any(k in t for k in ["pemda","bupati","pemerintah","apbd"]):         return "pemerintahan"
    if any(k in t for k in ["persegres","sepak bola","liga"]):              return "olahraga"
    if any(k in t for k in ["macet","jalan","tol","infrastruktur"]):        return "infrastruktur"
    return "umum"


def cek_sesi_aktif(driver):
    from selenium.common.exceptions import InvalidSessionIdException, WebDriverException
    try:
        _ = driver.current_url
        return True
    except (InvalidSessionIdException, WebDriverException):
        return False


def buat_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,768")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def tutup_popup(driver):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    for xpath in [
        "//button[contains(text(),'Tidak Sekarang')]",
        "//button[contains(text(),'Not Now')]",
        "//button[contains(text(),'Tutup')]",
        "//button[contains(text(),'Close')]",
        "//div[@role='dialog']//button[contains(@aria-label,'Close')]",
    ]:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            btn.click()
            jeda(1, 2)
            return
        except Exception:
            continue


def login_instagram(driver) -> bool:
    print("  Membuka Instagram...")
    driver.get("https://www.instagram.com/")
    jeda(3, 5)
    if not cek_sesi_aktif(driver):
        return False
    driver.delete_all_cookies()
    for nama, nilai in IG_COOKIES.items():
        if not nilai:
            continue
        driver.add_cookie({"name": nama, "value": nilai, "domain": ".instagram.com", "path": "/", "secure": True})
    driver.refresh()
    jeda(4, 6)
    if not cek_sesi_aktif(driver):
        return False
    if "accounts/login" in driver.current_url or "auth_platform" in driver.current_url:
        print("  ❌ Cookie tidak valid atau expired.")
        update_status("instagram", False, "Cookie tidak valid atau expired")
        return False
    print("  ✅ Login Instagram berhasil!\n")
    return True


def cari_postingan(driver, keyword: str, maks_post: int) -> list:
    from selenium.webdriver.common.by import By

    print(f"  Mencari postingan: '{keyword}'")
    url_hasil = []
    keyword_encoded = keyword.replace(" ", "%20")
    try:
        driver.get(f"https://www.instagram.com/explore/search/keyword/?q={keyword_encoded}")
        jeda(5, 8)
        tutup_popup(driver)
    except Exception as e:
        print(f"  Gagal buka halaman search: {e}")
        return []

    for scroll in range(5):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            jeda(2, 3)
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
            for link in links:
                href = link.get_attribute("href")
                if href and "/p/" in href:
                    match = re.search(r"/p/([^/?]+)", href)
                    if match:
                        sc = match.group(1)
                        if sc not in url_hasil:
                            url_hasil.append(sc)
        except Exception:
            break
        if len(url_hasil) >= maks_post:
            break

    print(f"  Ditemukan {len(url_hasil)} postingan")
    return url_hasil[:maks_post]


def ambil_komentar_post(driver, shortcode: str, maks: int) -> dict:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException

    url = f"https://www.instagram.com/p/{shortcode}/"
    print(f"    Membuka: {url}")
    try:
        driver.get(url)
    except Exception as e:
        print(f"    Gagal: {e}")
        return {"username": "-", "caption": shortcode, "likes": 0, "comments": 0, "tanggal": "-", "link": url, "komentar": []}

    jeda(6, 9)
    tutup_popup(driver)

    caption = shortcode
    try:
        cap_el  = driver.find_element(By.CSS_SELECTOR, "div._a9zs span, h1")
        caption = cap_el.text[:100].replace("\n", " ")
    except Exception:
        pass

    username = "-"
    try:
        username = driver.find_element(By.XPATH, "//header//a[contains(@href,'/')]").text.strip()
    except Exception:
        pass

    likes = 0
    try:
        for s in driver.find_elements(By.XPATH, "//section//span"):
            txt = s.text.strip()
            angka = re.sub(r"[^\d]", "", txt)
            if angka:
                likes = int(angka)
                break
    except Exception:
        pass

    tanggal = "-"
    try:
        tanggal = driver.find_element(By.TAG_NAME, "time").get_attribute("datetime")
    except Exception:
        pass

    try:
        btn = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH,
            "//span[contains(text(),'Lihat semua') or contains(text(),'View all') "
            "or contains(text(),'komentar') or contains(text(),'comments')]"
        )))
        btn.click()
        jeda(2, 3)
    except Exception:
        pass

    komentar = []
    sudah    = set()
    tidak_bertambah = 0

    def kumpulkan():
        if not cek_sesi_aktif(driver):
            return
        for sel in ["div._a9zs span","ul._a9ym li div._a9zs","span._aade","ul li span[dir='auto']"]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    for el in els:
                        try:
                            t = el.text.strip()
                        except Exception:
                            continue
                        if t and t not in sudah and len(t) > 2 and not t.startswith("@"):
                            sudah.add(t)
                            komentar.append({"text": t, "caption": caption, "shortcode": shortcode, "link_postingan": url})
                    if komentar:
                        break
            except Exception:
                continue

    kumpulkan()
    while len(komentar) < maks:
        if not cek_sesi_aktif(driver):
            break
        sebelum = len(komentar)
        try:
            btn_muat = driver.find_element(By.XPATH,
                "//button[contains(.,'Muat lebih') or contains(.,'Load more') or contains(.,'View more')]"
            )
            driver.execute_script("arguments[0].click();", btn_muat)
            jeda(2, 4)
        except NoSuchElementException:
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                break
            jeda(2, 3)
        except Exception:
            break
        kumpulkan()
        if len(komentar) == sebelum:
            tidak_bertambah += 1
            if tidak_bertambah >= 4:
                break
        else:
            tidak_bertambah = 0

    return {
        "username": username, "caption": caption, "likes": likes,
        "comments": len(komentar), "tanggal": tanggal, "link": url,
        "komentar": komentar[:maks],
    }


def step_instagram():
    print("\n" + "="*60)
    print("  STEP 3 — SCRAPING & SENTIMEN INSTAGRAM")
    print("="*60)

    from transformers import pipeline as hf_pipeline

    kosong = [k for k, v in IG_COOKIES.items() if not v]
    if kosong:
        print("⚠️  Cookie Instagram belum diisi di .env:")
        for k in kosong:
            print(f"   - {k}")
        print("   Ambil dari F12 → Application → Cookies → instagram.com")
        return

    print("🤖 Memuat model IndoBERT untuk Instagram...")
    sentimen_model = hf_pipeline(
        "text-classification",
        model=MODEL_NAME
    )
    print("✅ Model siap!\n")

    driver       = buat_driver()
    semua_data   = []
    semua_post   = []

    try:
        if not login_instagram(driver):
            return

        for keyword in IG_KEYWORDS:
            print(f"\n{'─'*50}")
            print(f"KEYWORD: '{keyword}'")
            print(f"{'─'*50}")

            shortcodes = cari_postingan(driver, keyword, MAKS_POST_PER_KEYWORD)
            if not shortcodes:
                print(f"  Tidak ada postingan untuk '{keyword}'")
                continue

            for idx, sc in enumerate(shortcodes, 1):
                print(f"\n  [{idx}/{len(shortcodes)}] {sc}")
                if not cek_sesi_aktif(driver):
                    print("  Browser tidak aktif, melewati.")
                    continue

                post = ambil_komentar_post(driver, sc, MAKS_KOMENTAR_PER_POST)
                semua_post.append({
                    "keyword"        : keyword,
                    "shortcode"      : sc,
                    "link_postingan" : post["link"],
                    "username"       : post["username"],
                    "caption"        : post["caption"],
                    "tanggal"        : post["tanggal"],
                    "likes"          : post["likes"],
                    "comments"       : post["comments"],
                })

                for k in post["komentar"]:
                    teks_asli   = k["text"]
                    teks_bersih = bersihkan_teks_ig(teks_asli)
                    hasil       = sentimen_model(teks_bersih[:512])[0]
                    label       = LABEL_MAP_IG.get(hasil["label"], "netral")
                    skor        = round(hasil["score"], 3)
                    topik       = deteksi_topik_ig(teks_asli)

                    semua_data.append({
                        "keyword"        : keyword,
                        "shortcode"      : sc,
                        "link_postingan" : k.get("link_postingan", ""),
                        "caption"        : k.get("caption", ""),
                        "teks_asli"      : teks_asli,
                        "teks_bersih"    : teks_bersih,
                        "sentimen"       : label,
                        "skor"           : skor,
                        "topik"          : topik,
                    })
                jeda(3, 6)

    except Exception as e:
        print(f"\nError: {e}")
        update_status("instagram", False, f"Error: {str(e)[:100]}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    if not semua_data:
        print("\n⚠️  Tidak ada data terkumpul.")
        update_status("instagram", False, "Tidak ada data — cookie expired atau diblokir")
        return

    df      = pd.DataFrame(semua_data)
    df_post = pd.DataFrame(semua_post)

    df_post.to_csv("output/gresik_ig_postingan.csv", index=False, encoding="utf-8-sig")
    df[["keyword","shortcode","link_postingan","teks_asli","teks_bersih","sentimen","skor","topik"]].to_csv(
        "output/gresik_ig_sentimen.csv", index=False, encoding="utf-8-sig"
    )
    with open("output/gresik_ig_komentar.json", "w", encoding="utf-8") as f:
        json.dump(semua_data, f, ensure_ascii=False, indent=2)

    total = len(df)
    print(f"\n✅ Selesai Instagram!")
    print(f"   Total komentar : {total}")
    print(f"   Sentimen:")
    for lbl, jml in df["sentimen"].value_counts().items():
        print(f"   {lbl:10s} {jml:4d} ({jml/total*100:5.1f}%)")
    update_status("instagram", True, f"Berhasil {total} komentar dari {df['shortcode'].nunique()} postingan")


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Pipeline Dashboard Gresik")
    parser.add_argument(
        "--step",
        choices=["all", "gmaps", "sentimen", "instagram"],
        default="all",
        help="Pilih step yang dijalankan (default: all)"
    )
    args = parser.parse_args()

    print("\n" + "="*60)
    print("   🏙️  PIPELINE DASHBOARD GRESIK")
    print("="*60)
    print(f"   Mode: {args.step.upper()}")

    if args.step in ("all", "gmaps"):
        step_cari_tempat()       # Step 1: cari tempat via Apify

    if args.step in ("all", "gmaps", "sentimen"):
        step_sentimen_gmaps()    # Step 2: analisis sentimen GM

    if args.step in ("all", "instagram"):
        step_instagram()         # Step 3: scraping Instagram

    print("\n" + "="*60)
    print("   ✅ SEMUA STEP SELESAI")
    print("="*60)


if __name__ == "__main__":
    main()