"""
Pipeline Lengkap — Analisis Sentimen Google Maps Kabupaten Gresik
=================================================================
Tahap 1 : cari_tempat()       → Scraping daftar tempat ke master_tempat.csv
Tahap 2 : scrape_google_maps() → Scraping ulasan per tempat (rotasi token)
Tahap 3 : analisis_sentimen()  → Proses sentimen dari ulasan_mentah.json
Tahap 4 : scan_output()        → Rebuild semua_tempat_summary.json dari folder

Jalankan semua tahap sekaligus:
    python googlemaps_baru.py

Atau jalankan tahap tertentu:
    python googlemaps_baru.py --tahap cari
    python googlemaps_baru.py --tahap scrape
    python googlemaps_baru.py --tahap sentimen
    python googlemaps_baru.py --tahap scan

══════════════════════════════════════════════════════════════════
STRUKTUR SUB-KATEGORI 
══════════════════════════════════════════════════════════════════

Kategori Utama       Sub-Kategori
────────────────────────────────────────────────────────────────
Pemerintahan     →  Dinas/OPD
                     Kecamatan
                     Kelurahan/Desa
                     Instansi Vertikal   (Polres, Koramil, dst.)
                     Pemerintah Kabupaten (Bupati, Sekretariat, DPRD)

Kesehatan        →  Rumah Sakit
                     Puskesmas
                     Klinik & Praktek Dokter
                     Apotek & Farmasi
                     BPJS Kesehatan
                     Posyandu & Poskesdes

Pendidikan       →  SD / MI
                     SMP / MTs
                     SMA / SMK / MA
                     Perguruan Tinggi

Tempat Ibadah    →  Masjid & Musholla
                     Gereja
                     Pura & Vihara

Keamanan & TNI   →  Polsek & Polres
                     TNI (Koramil, Kodim, Korem)
                     Pos Pemadam Kebakaran

Transportasi &   →  SPBU & Pertamini
Energi               Terminal & Halte
                     Pelabuhan & Dermaga

Ritel & Kuliner  →  Minimarket (Indomaret, Alfamart)
                     Rumah Makan & Warung
                     Pasar Tradisional
                     Mall & Pusat Perbelanjaan

Pelayanan Publik →  (tetap)
Perbankan        →  (tetap)
Wisata           →  (tetap)
Olahraga         →  (tetap)
Industri         →  (tetap)
Lainnya          →  (fallback)

══════════════════════════════════════════════════════════════════
MODE SWEEP AREA (cari_semua_gresik)
══════════════════════════════════════════════════════════════════
Selain pencarian berbasis keyword, tersedia mode sweep yang men-crawl
seluruh wilayah Kabupaten Gresik (termasuk Pulau Bawean) dengan membagi
wilayah menjadi grid sel koordinat. Setiap sel di-query tanpa keyword
(pencarian kosong / "place" saja) sehingga Google Maps mengembalikan
semua tempat yang ada di area tersebut tanpa terpaku pada kategori.

Jalankan:
    python googlemaps_baru.py --tahap sweep
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


# Batas wilayah Kabupaten Gresik: daratan + Pulau Bawean di utara.
GRESIK_LAT_MIN, GRESIK_LAT_MAX = -7.65, -5.55
GRESIK_LNG_MIN, GRESIK_LNG_MAX = 112.20, 112.95

def dalam_area_gresik(lat, lng) -> bool:
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return False
    return GRESIK_LAT_MIN <= lat <= GRESIK_LAT_MAX and GRESIK_LNG_MIN <= lng <= GRESIK_LNG_MAX


def kota_valid(data: dict) -> bool:
    """
    Whitelist approach: hanya terima tempat yang EKSPLISIT menyebut
    'gresik' atau 'bawean' di field city/address/state.
    """
    city    = str(data.get("city")    or "").lower().strip()
    address = str(data.get("address") or "").lower().strip()
    state   = str(data.get("state")   or "").lower().strip()
    gabungan = f"{city} {address} {state}".strip()

    if not gabungan:
        return True

    return any(kata in gabungan for kata in ["gresik", "bawean"])


def get_lokasi(folder_name: str, place: dict = None):
    data = place if (place and isinstance(place, dict)) else None

    if data is None:
        mentah_path = os.path.join(OUTPUT_DIR, folder_name, "ulasan_mentah.json")
        if os.path.exists(mentah_path):
            try:
                with open(mentah_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = None

    if data is None:
        return None, None

    loc = data.get("location") or {}
    lat = loc.get("lat")
    lng = loc.get("lng")

    if lat is None or lng is None:
        return None, None

    if not dalam_area_gresik(lat, lng):
        return None, None

    if not kota_valid(data):
        return None, None

    return lat, lng


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
# Setiap sub-kategori memiliki keyword pencarian sendiri sehingga
# data yang dikumpulkan sudah terpartisi secara natural dari sumber.
# Field "kategori" di master_tempat.csv diisi dengan SUB-KATEGORI
# (bukan kategori utama) agar downstream dapat langsung memakai label
# yang detail tanpa perlu inferensi ulang.
# ════════════════════════════════════════════════════════════════

KATEGORI_CARI = {

    # ── PEMERINTAHAN ──────────────────────────────────────────
    "Pemerintah Kabupaten": [
        "kantor bupati gresik",
        "sekretariat daerah gresik",
        "sekretariat dprd gresik",
        "dprd kabupaten gresik",
        "setda kabupaten gresik",
    ],
    "Dinas/OPD": [
        "dinas pendidikan gresik",
        "dinas kesehatan gresik",
        "dinas pekerjaan umum gresik",
        "dinas perhubungan gresik",
        "dinas sosial gresik",
        "dinas lingkungan hidup gresik",
        "dinas kependudukan gresik",
        "dinas penanaman modal gresik",
        "dinas koperasi gresik",
        "dinas komunikasi gresik",
        "badan kepegawaian gresik",
        "badan perencanaan gresik",
        "inspektorat gresik",
        "satpol pp gresik",
        "dinas pertanian gresik",
        "dinas ketenagakerjaan gresik",
        "dinas pariwisata gresik",
    ],
    "Kecamatan": [
        "kantor kecamatan gresik",
        "kantor camat gresik",
        "kecamatan kebomas gresik",
        "kecamatan gresik kota",
        "kecamatan manyar gresik",
        "kecamatan bungah gresik",
        "kecamatan sidayu gresik",
        "kecamatan dukun gresik",
        "kecamatan panceng gresik",
        "kecamatan ujungpangkah gresik",
        "kecamatan sangkapura bawean",
        "kecamatan tambak bawean",
        "kecamatan cerme gresik",
        "kecamatan benjeng gresik",
        "kecamatan balongpanggang gresik",
        "kecamatan menganti gresik",
        "kecamatan kedamean gresik",
        "kecamatan wringinanom gresik",
        "kecamatan driyorejo gresik",
    ],
    "Kelurahan/Desa": [
        "kantor kelurahan gresik",
        "kantor desa gresik",
        "balai desa gresik",
        "kantor kepala desa gresik",
        "kantor desa kebomas",
        "kantor desa manyar gresik",
        "kantor desa bungah gresik",
        "kantor desa menganti gresik",
        "kantor desa driyorejo",
        "kantor desa cerme gresik",
    ],
    "Instansi Vertikal": [
        "polres gresik",
        "polsek gresik",
        "kodim gresik",
        "koramil gresik",
        "kejaksaan negeri gresik",
        "pengadilan negeri gresik",
        "pengadilan agama gresik",
        "kantor imigrasi gresik",
        "kanwil kementerian agama gresik",
        "kantor kemenag gresik",
        "bnn gresik",
        "lapas gresik",
    ],

    # ── KESEHATAN ──────────────────────────────────────────────
    "Rumah Sakit": [
        "rsud ibnu sina gresik",
        "rumah sakit gresik",
        "rs petrokimia gresik",
        "rsia gresik",
        "rs swasta gresik",
        "rs islam gresik",
        "rs umum gresik",
    ],
    "Puskesmas": [
        "puskesmas gresik",
        "puskesmas pembantu gresik",
        "pustu gresik",
        "puskesmas kebomas",
        "puskesmas manyar",
        "puskesmas bungah",
        "puskesmas menganti",
        "puskesmas driyorejo",
        "puskesmas cerme",
        "puskesmas sangkapura bawean",
        "puskesmas tambak bawean",
    ],
    "Klinik & Praktek Dokter": [
        "klinik gresik",
        "klinik pratama gresik",
        "klinik utama gresik",
        "praktek dokter gresik",
        "klinik kesehatan gresik",
        "klinik bidan gresik",
        "klinik spesialis gresik",
        "klinik aesthetic gresik",
    ],
    "Apotek & Farmasi": [
        "apotek gresik",
        "apotik gresik",
        "farmasi gresik",
        "apotek kimia farma gresik",
        "apotek k24 gresik",
    ],
    "BPJS Kesehatan": [
        "bpjs kesehatan gresik",
        "kantor bpjs gresik",
        "bpjs ketenagakerjaan gresik",
    ],
    "Posyandu & Poskesdes": [
        "posyandu gresik",
        "poskesdes gresik",
        "polindes gresik",
        "pos kesehatan desa gresik",
    ],

    # ── PENDIDIKAN ─────────────────────────────────────────────
    "SD/MI": [
        "sd negeri gresik",
        "sd swasta gresik",
        "mi negeri gresik",
        "madrasah ibtidaiyah gresik",
    ],
    "SMP/MTs": [
        "smp negeri gresik",
        "smp swasta gresik",
        "mts gresik",
        "madrasah tsanawiyah gresik",
    ],
    "SMA/SMK/MA": [
        "sma negeri gresik",
        "sma swasta gresik",
        "smk negeri gresik",
        "smk swasta gresik",
        "madrasah aliyah gresik",
        "man gresik",
    ],
    "Perguruan Tinggi": [
        "universitas gresik",
        "kampus gresik",
        "akademi gresik",
        "politeknik gresik",
        "sekolah tinggi gresik",
        "stikes gresik",
        "unigres",
    ],

    # ── PELAYANAN PUBLIK ───────────────────────────────────────
    "Pelayanan Publik": [
        "mall pelayanan publik gresik",
        "kantor pos gresik",
        "samsat gresik",
        "disdukcapil gresik",
        "kua gresik",
        "bpn gresik",
        "kantor pajak gresik",
        "kantor imigrasi gresik",
    ],

    # ── PERBANKAN ──────────────────────────────────────────────
    "Perbankan": [
        "bank bca gresik",
        "bank bri gresik",
        "bank mandiri gresik",
        "bank bni gresik",
        "bank btn gresik",
        "bank jatim gresik",
        "bpr gresik",
        "koperasi gresik",
        "pegadaian gresik",
    ],

    # ── WISATA ─────────────────────────────────────────────────
    "Wisata": [
        "wisata gresik",
        "pantai gresik",
        "museum gresik",
        "makam sunan giri",
        "makam maulana malik ibrahim",
        "taman gresik",
        "wisata bawean",
        "pulau bawean",
    ],

    # ── OLAHRAGA ───────────────────────────────────────────────
    "Olahraga": [
        "stadion gresik",
        "gor gresik",
        "gedung olahraga gresik",
        "lapangan futsal gresik",
        "kolam renang gresik",
        "gym gresik",
        "fitness center gresik",
    ],

    # ── INDUSTRI ───────────────────────────────────────────────
    "Industri": [
        "petrokimia gresik",
        "semen gresik",
        "pelabuhan gresik",
        "terminal gresik",
        "kawasan industri gresik",
        "pabrik gresik",
        "gudang gresik",
    ],

    # ── TEMPAT IBADAH ──────────────────────────────────────────
    "Masjid & Musholla": [
        "masjid gresik",
        "masjid agung gresik",
        "masjid jami gresik",
        "masjid raya gresik",
        "musholla gresik",
        "mushola gresik",
        "langgar gresik",
        "masjid bawean",
        "masjid kebomas",
        "masjid manyar gresik",
        "masjid menganti gresik",
        "masjid driyorejo",
    ],
    "Gereja": [
        "gereja gresik",
        "gereja katolik gresik",
        "gereja kristen gresik",
        "gkjw gresik",
        "gpdi gresik",
    ],
    "Pura & Vihara": [
        "pura gresik",
        "vihara gresik",
        "klenteng gresik",
        "wihara gresik",
    ],

    # ── KEAMANAN & TNI ─────────────────────────────────────────
    "Polsek & Polres": [
        "polsek gresik",
        "polsek kebomas",
        "polsek manyar",
        "polsek bungah",
        "polsek sidayu",
        "polsek dukun",
        "polsek panceng",
        "polsek cerme gresik",
        "polsek benjeng",
        "polsek menganti",
        "polsek driyorejo",
        "polsek wringinanom",
        "polsek kedamean",
        "polsek sangkapura bawean",
        "polres gresik",
    ],
    "TNI": [
        "koramil gresik",
        "kodim gresik",
        "korem gresik",
        "markas tni gresik",
        "pos tni gresik",
    ],
    "Pemadam Kebakaran": [
        "pemadam kebakaran gresik",
        "damkar gresik",
        "pos damkar gresik",
        "dinas pemadam gresik",
    ],

    # ── TRANSPORTASI & ENERGI ──────────────────────────────────
    "SPBU & BBM": [
        "spbu gresik",
        "pertamina gresik",
        "pom bensin gresik",
        "pertamini gresik",
        "spbu kebomas",
        "spbu manyar gresik",
        "spbu menganti gresik",
        "spbu driyorejo",
        "spbu cerme gresik",
    ],
    "Terminal & Transportasi": [
        "terminal gresik",
        "halte bus gresik",
        "terminal bus gresik",
        "stasiun gresik",
        "angkutan umum gresik",
        "ojek online gresik",
    ],
    "Pelabuhan & Dermaga": [
        "pelabuhan gresik",
        "pelabuhan sangkapura bawean",
        "dermaga bawean",
        "ferry bawean",
        "kapal bawean",
    ],

    # ── RITEL & KULINER ────────────────────────────────────────
    "Minimarket": [
        "indomaret gresik",
        "alfamart gresik",
        "alfamidi gresik",
        "indomaret kebomas",
        "alfamart manyar gresik",
        "indomaret menganti",
        "indomaret driyorejo",
    ],
    "Rumah Makan & Kuliner": [
        "rumah makan gresik",
        "warung makan gresik",
        "restoran gresik",
        "kuliner gresik",
        "depot gresik",
        "cafe gresik",
        "warung seafood gresik",
        "nasi bebek gresik",
    ],
    "Pasar Tradisional": [
        "pasar gresik",
        "pasar tradisional gresik",
        "pasar kebomas",
        "pasar bungah",
        "pasar sidayu",
        "pasar manyar gresik",
        "pasar menganti",
        "pasar cerme gresik",
        "pasar bawean",
    ],
    "Mall & Pusat Perbelanjaan": [
        "mall gresik",
        "plaza gresik",
        "pusat perbelanjaan gresik",
        "swalayan gresik",
        "supermarket gresik",
        "giant gresik",
        "hypermart gresik",
    ],
}


def cari_tempat():
    """
    Tahap 1: Scraping daftar tempat per sub-kategori → master_tempat.csv
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

    for sub_kategori, keyword_list in KATEGORI_CARI.items():
        print(f"\n========== {sub_kategori} ==========")
        for keyword in keyword_list:
            print("Cari :", keyword)
            run_input = {
                "searchStringsArray"       : [keyword],
                "locationQuery"            : "Gresik, Jawa Timur, Indonesia",
                "maxCrawledPlacesPerSearch": 30,
                "includeReviews"           : False,
                "language"                 : "id",
            }
            try:
                run     = client.actor("compass/crawler-google-places").call(run_input=run_input)
                dataset = client.dataset(run.default_dataset_id)
                for item in dataset.iterate_items():
                    semua_tempat.append({
                        "sub_kategori" : sub_kategori,
                        "kategori"     : _kategori_utama(sub_kategori),
                        "nama"         : item.get("title", ""),
                        "alamat"       : item.get("address", ""),
                        "rating"       : item.get("totalScore", ""),
                        "jumlah_ulasan": item.get("reviewsCount", ""),
                    })
            except Exception as e:
                print(f"   ⚠️  Error keyword '{keyword}': {e}")
                continue

    df = pd.DataFrame(semua_tempat)
    df.drop_duplicates(subset=["nama"], inplace=True)
    df.sort_values(["kategori", "sub_kategori", "nama"], inplace=True)
    df.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")

    print(f"\n✅ Master tempat disimpan: {len(df)} tempat → {MASTER_FILE}")
    print(df.groupby("sub_kategori").size().to_string())


def _kategori_utama(sub_kategori: str) -> str:
    """Petakan sub-kategori ke kategori utama."""
    mapping = {
        # Pemerintahan
        "Pemerintah Kabupaten"   : "Pemerintahan",
        "Dinas/OPD"              : "Pemerintahan",
        "Kecamatan"              : "Pemerintahan",
        "Kelurahan/Desa"         : "Pemerintahan",
        "Instansi Vertikal"      : "Pemerintahan",
        # Kesehatan
        "Rumah Sakit"            : "Kesehatan",
        "Puskesmas"              : "Kesehatan",
        "Klinik & Praktek Dokter": "Kesehatan",
        "Apotek & Farmasi"       : "Kesehatan",
        "BPJS Kesehatan"         : "Kesehatan",
        "Posyandu & Poskesdes"   : "Kesehatan",
        # Pendidikan
        "SD/MI"                  : "Pendidikan",
        "SMP/MTs"                : "Pendidikan",
        "SMA/SMK/MA"             : "Pendidikan",
        "Perguruan Tinggi"       : "Pendidikan",
        # Tempat Ibadah
        "Masjid & Musholla"      : "Tempat Ibadah",
        "Gereja"                 : "Tempat Ibadah",
        "Pura & Vihara"          : "Tempat Ibadah",
        # Keamanan & TNI
        "Polsek & Polres"        : "Keamanan & TNI",
        "TNI"                    : "Keamanan & TNI",
        "Pemadam Kebakaran"      : "Keamanan & TNI",
        # Transportasi & Energi
        "SPBU & BBM"             : "Transportasi & Energi",
        "Terminal & Transportasi": "Transportasi & Energi",
        "Pelabuhan & Dermaga"    : "Transportasi & Energi",
        # Ritel & Kuliner
        "Minimarket"             : "Ritel & Kuliner",
        "Rumah Makan & Kuliner"  : "Ritel & Kuliner",
        "Pasar Tradisional"      : "Ritel & Kuliner",
        "Mall & Pusat Perbelanjaan": "Ritel & Kuliner",
        # Lainnya
        "Pelayanan Publik"       : "Pelayanan Publik",
        "Perbankan"              : "Perbankan",
        "Wisata"                 : "Wisata",
        "Olahraga"               : "Olahraga",
        "Industri"               : "Industri",
    }
    return mapping.get(sub_kategori, "Lainnya")


# ════════════════════════════════════════════════════════════════
# TAHAP 2 — SCRAPE ULASAN GOOGLE MAPS (ROTASI TOKEN)
# ════════════════════════════════════════════════════════════════

EXCLUDE_KEYWORDS = [
    "atm", "bank", "bca", "bni", "bri", "mandiri", "brilink",
    "indomaret", "alfamart", "minimarket", "spbu", "agen",
    "toko", "warung", "resto", "kafe", "salon", "barbershop",
    "laundry", "bengkel", "dealer", "hotel", "kost",
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
    Membaca kolom 'sub_kategori' jika tersedia, fallback ke 'kategori'.
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
                    # Simpan sub_kategori & kategori utama
                    place["sub_kategori"] = str(master.iloc[i].get("sub_kategori", ""))
                    place["kategori"]     = str(master.iloc[i].get("kategori", ""))
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
            data[0]["sub_kategori"] = str(row.get("sub_kategori", ""))
            data[0]["kategori"]     = str(row.get("kategori", ""))
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
        sub = place.get("sub_kategori", "-")
        print(f"   📍 {place.get('title')} | {sub} | {place.get('reviewsCount')} ulasan")

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


# ════════════════════════════════════════════════════════════════
# DETEKSI SUB-KATEGORI & KATEGORI UTAMA
# ════════════════════════════════════════════════════════════════
#
# Hierarki prioritas get_sub_kategori():
#   1. Kolom 'sub_kategori' di master_tempat.csv   (paling akurat)
#   2. Field 'sub_kategori' di ulasan_mentah.json  (hasil scrape)
#   3. Inferensi dari nama folder menggunakan keyword matching
#   4. Fallback "Lainnya"
#
# Setelah sub-kategori diketahui, kategori utama didapat via
# _kategori_utama() yang sudah didefinisikan di atas.
# ════════════════════════════════════════════════════════════════

# ── Tabel keyword → sub-kategori (untuk inferensi dari folder name) ──────────

_SUB_KEYWORD_MAP: list[tuple[list[str], str]] = [

    # Pemerintahan — urutan dari paling spesifik ke paling umum
    (["bupati", "sekretariat_daerah", "setda", "dprd"], "Pemerintah Kabupaten"),
    (["dinas_", "badan_", "inspektorat", "satpol", "bagian_"], "Dinas/OPD"),
    (["kecamatan_", "kec_", "camat"], "Kecamatan"),
    (["kelurahan_", "desa_", "kel_", "balai_desa", "kepala_desa"], "Kelurahan/Desa"),
    (["polres", "polsek", "kodim", "koramil", "kejaksaan",
       "pengadilan", "imigrasi", "kemenag", "bnn", "lapas"], "Instansi Vertikal"),

    # Kesehatan
    (["rsud", "rsu_", "rsia", "rs_", "rumah_sakit"], "Rumah Sakit"),
    (["puskesmas", "pkm_", "pustu"], "Puskesmas"),
    (["klinik", "praktek_dokter", "dokter_", "bidan_",
       "skincare", "aesthetic", "clinic"], "Klinik & Praktek Dokter"),
    (["apotek", "apotik", "farmasi"], "Apotek & Farmasi"),
    (["bpjs"], "BPJS Kesehatan"),
    (["posyandu", "poskesdes", "polindes"], "Posyandu & Poskesdes"),

    # Pendidikan
    (["sdn_", "sd_", "mi_", "upt_sd", "madrasah_ibtidaiyah"], "SD/MI"),
    (["smpn_", "smp_", "mts_", "upt_smp", "madrasah_tsanawiyah"], "SMP/MTs"),
    (["sman_", "sma_", "smkn_", "smk_", "man_", "ma_",
       "upt_sma", "upt_smk", "madrasah_aliyah"], "SMA/SMK/MA"),
    (["universitas", "kampus", "akademi", "politeknik",
       "sekolah_tinggi", "stikes", "unigres"], "Perguruan Tinggi"),

    # Pelayanan Publik
    (["disdukcapil", "samsat", "mall_pelayanan", "kua",
       "bpn", "pajak", "kantor_pos"], "Pelayanan Publik"),

    # Perbankan
    (["bank_", "bri_", "bni_", "bca_", "mandiri_", "btn_",
       "bpr_", "pegadaian", "koperasi_", "atm_", "brilink"], "Perbankan"),

    # Wisata
    (["wisata", "pantai", "museum", "makam", "taman_",
       "sunan_giri", "bawean"], "Wisata"),

    # Olahraga
    (["stadion", "gor_", "gedung_olahraga", "lapangan_",
       "kolam_renang", "futsal", "gym", "fitness"], "Olahraga"),

    # Industri
    (["petrokimia", "semen_", "pabrik_", "pelabuhan", "terminal_",
       "kawasan_industri", "gudang_"], "Industri"),

    # Tempat Ibadah
    (["masjid_", "musholla", "mushola", "langgar", "masjid_agung",
       "masjid_jami", "masjid_raya"], "Masjid & Musholla"),
    (["gereja_", "gkjw", "gpdi", "gereja_katolik",
       "gereja_kristen"], "Gereja"),
    (["pura_", "vihara", "wihara", "klenteng"], "Pura & Vihara"),

    # Keamanan & TNI
    (["polsek_", "polres_"], "Polsek & Polres"),
    (["koramil_", "kodim_", "korem_", "markas_tni",
       "pos_tni"], "TNI"),
    (["damkar", "pemadam_kebakaran", "pos_damkar"], "Pemadam Kebakaran"),

    # Transportasi & Energi
    (["spbu_", "pertamina_", "pom_bensin",
       "pertamini"], "SPBU & BBM"),
    (["terminal_bus", "halte_", "stasiun_",
       "angkutan"], "Terminal & Transportasi"),
    (["pelabuhan_", "dermaga_", "ferry_", "kapal_"], "Pelabuhan & Dermaga"),

    # Ritel & Kuliner
    (["indomaret", "alfamart", "alfamidi"], "Minimarket"),
    (["rumah_makan", "warung_makan", "restoran", "depot_",
       "cafe_", "nasi_", "seafood"], "Rumah Makan & Kuliner"),
    (["pasar_", "pasar_tradisional"], "Pasar Tradisional"),
    (["mall_", "plaza_", "swalayan", "supermarket",
       "hypermart"], "Mall & Pusat Perbelanjaan"),
]


def get_sub_kategori(folder_name: str) -> str:
    """
    Kembalikan sub-kategori detail untuk sebuah folder/tempat.
    Lihat hierarki prioritas di docstring modul di atas.
    """
    # Prioritas 1: dari master CSV (kolom sub_kategori)
    if os.path.exists(MASTER_FILE):
        try:
            df_master = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
            if "sub_kategori" in df_master.columns:
                for _, row in df_master.iterrows():
                    if get_folder(str(row["nama"])) == folder_name:
                        val = str(row["sub_kategori"]).strip()
                        if val and val.lower() not in ("nan", "none", ""):
                            return val
        except Exception:
            pass

    # Prioritas 2: dari ulasan_mentah.json
    mentah_path = os.path.join(OUTPUT_DIR, folder_name, "ulasan_mentah.json")
    if os.path.exists(mentah_path):
        try:
            with open(mentah_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            val = str(data.get("sub_kategori", "")).strip()
            if val and val.lower() not in ("nan", "none", ""):
                return val
            # coba field lama "kategori" jika memang sudah detail
            val2 = str(data.get("kategori", "")).strip()
            if val2 in {sk for _, sk in _SUB_KEYWORD_MAP}:
                return val2
        except Exception:
            pass

    # Prioritas 3: inferensi dari nama folder (keyword matching)
    fn = folder_name.lower()
    for keywords, sub_kat in _SUB_KEYWORD_MAP:
        if any(kw in fn for kw in keywords):
            return sub_kat

    return "Lainnya"


def get_kategori(folder_name: str) -> str:
    """
    Kembalikan kategori UTAMA untuk sebuah folder.
    Memanggil get_sub_kategori() lalu memetakan via _kategori_utama().
    """
    return _kategori_utama(get_sub_kategori(folder_name))


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

def koreksi_dengan_bintang(label_model: str, bintang) -> str:
    try:
        bintang = int(bintang)
    except (ValueError, TypeError):
        return label_model

    if bintang >= 4:
        if label_model == "Negatif":
            return "Positif"
        return label_model
    elif 1 <= bintang <= 2:
        if label_model == "Positif":
            return "Negatif"
        return label_model
    else:
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
# HELPER — Buat dict summary item (menghindari duplikasi kode)
# ════════════════════════════════════════════════════════════════

def _build_summary_item(
    folder_name: str,
    nama: str,
    place_raw: dict,
    df: pd.DataFrame | None,
    lat, lng,
) -> dict:
    """
    Bangun dict summary standar.
    df boleh None jika tidak ada ulasan (akan diisi 0 semua).
    """
    sub_kat = get_sub_kategori(folder_name)
    kat     = _kategori_utama(sub_kat)
    rating  = place_raw.get("totalScore", 0)

    if df is not None and len(df) > 0:
        total_u = len(df)
        positif = int((df["sentimen"] == "Positif").sum())
        netral  = int((df["sentimen"] == "Netral").sum())
        negatif = int((df["sentimen"] == "Negatif").sum())
    else:
        total_u = positif = netral = negatif = 0

    return {
        "key"           : folder_name,
        "kategori"      : kat,
        "sub_kategori"  : sub_kat,
        "tempat"        : nama,
        "rating"        : rating,
        "total_ulasan"  : total_u,
        "positif"       : positif,
        "netral"        : netral,
        "negatif"       : negatif,
        "persen_positif": round(positif / total_u * 100, 1) if total_u else 0,
        "persen_netral" : round(netral  / total_u * 100, 1) if total_u else 0,
        "persen_negatif": round(negatif / total_u * 100, 1) if total_u else 0,
        "latitude"      : lat,
        "longitude"     : lng,
    }


# ════════════════════════════════════════════════════════════════
# TAHAP 3 — ANALISIS SENTIMEN (dari ulasan_mentah.json)
# ════════════════════════════════════════════════════════════════

def analisis_sentimen(pipe=None):
    """
    Tahap 3: Proses sentimen untuk semua folder yang punya ulasan_mentah.json
    tapi belum punya ulasan_sentimen.json.
    Output JSON sekarang menyertakan field 'sub_kategori'.
    """
    print("\n" + "=" * 60)
    print("TAHAP 3 — ANALISIS SENTIMEN INDOBERT")
    print("=" * 60)

    if pipe is None:
        pipe = load_indobert()

    all_summary = []
    folders     = sorted(os.listdir(OUTPUT_DIR))
    total_dir   = len([f for f in folders if os.path.isdir(os.path.join(OUTPUT_DIR, f))])
    diproses    = 0

    for i, folder_name in enumerate(folders):
        folder_path   = os.path.join(OUTPUT_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        json_sentimen = os.path.join(folder_path, "ulasan_sentimen.json")
        json_mentah   = os.path.join(folder_path, "ulasan_mentah.json")

        sub_kat = get_sub_kategori(folder_name)
        kat     = _kategori_utama(sub_kat)

        # ── Sudah ada sentimen → load ─────────────────────────
        if os.path.exists(json_sentimen):
            with open(json_sentimen, "r", encoding="utf-8") as f:
                data = json.load(f)
            lat = data.get("latitude")
            lng = data.get("longitude")
            if lat is None or lng is None:
                lat, lng = get_lokasi(folder_name)

            # Patch sub_kategori jika belum ada di file lama
            if "sub_kategori" not in data:
                data["sub_kategori"] = sub_kat
                with open(json_sentimen, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

            all_summary.append({
                "key"           : folder_name,
                "kategori"      : kat,
                "sub_kategori"  : sub_kat,
                "tempat"        : data.get("tempat", folder_name),
                "rating"        : data.get("rating", 0),
                "total_ulasan"  : data.get("total_ulasan", 0),
                "positif"       : data.get("positif", 0),
                "netral"        : data.get("netral", 0),
                "negatif"       : data.get("negatif", 0),
                "persen_positif": data.get("persen_positif", 0),
                "persen_netral" : data.get("persen_netral", 0),
                "persen_negatif": data.get("persen_negatif", 0),
                "latitude"      : lat,
                "longitude"     : lng,
            })
            print(f"[{i + 1}/{total_dir}] 📂 Load: {data.get('tempat', folder_name)} [{sub_kat}]")
            continue

        # ── Belum ada sentimen → proses dari mentah ───────────
        if not os.path.exists(json_mentah):
            continue

        with open(json_mentah, "r", encoding="utf-8") as f:
            place = json.load(f)

        nama    = place.get("title", folder_name)
        reviews = place.get("reviews", [])
        lat, lng = get_lokasi(folder_name, place)

        print(f"[{i + 1}/{total_dir}] 🔍 Proses: {nama} [{sub_kat}] ({len(reviews)} ulasan)")

        if not reviews:
            item = _build_summary_item(folder_name, nama, place, None, lat, lng)
            all_summary.append(item)
            continue

        rows = []
        for r in reviews:
            rows.append({
                "Kategori"      : kat,
                "Sub Kategori"  : sub_kat,
                "Tempat"        : nama,
                "Rating Tempat" : place.get("totalScore", ""),
                "Total Ulasan"  : place.get("reviewsCount", ""),
                "Nama Reviewer" : r.get("name") or "",
                "Bintang"       : r.get("stars") or "",
                "Tanggal"       : r.get("publishedAtDate") or "",
                "Ulasan"        : (r.get("text") or "").replace("\n", " "),
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
        df["sentimen"]       = [
            koreksi_dengan_bintang(label, bintang)
            for label, bintang in zip(df["sentimen"], df["Bintang"])
        ]

        item = _build_summary_item(folder_name, nama, place, df, lat, lng)
        item["ulasan"] = df[[
            "Kategori", "Sub Kategori", "Nama Reviewer", "Bintang", "Tanggal",
            "Ulasan", "teks_final", "topik", "sentimen", "sentimen_score"
        ]].to_dict(orient="records")

        with open(json_sentimen, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)

        df.to_csv(os.path.join(folder_path, "ulasan_sentimen.csv"), index=False, encoding="utf-8-sig")

        all_summary.append({k: v for k, v in item.items() if k != "ulasan"})
        diproses += 1
        print(f"   ✅ {item['positif']}P / {item['netral']}N / {item['negatif']}Neg")

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(all_summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"✅ Selesai! {diproses} diproses, {len(all_summary)} total tempat")
    print(f"💾 {SUMMARY_FILE}")

    update_status("gmaps", True, f"Berhasil {len(all_summary)} tempat tersedia")

    return pipe


# ════════════════════════════════════════════════════════════════
# TAHAP 3b — PROCESS PER TEMPAT (dari hasil scrape langsung)
# ════════════════════════════════════════════════════════════════

def process_per_tempat(results: list, pipe):
    """
    Alternatif Tahap 3: proses sentimen langsung dari list results
    (output scrape_google_maps), bukan dari folder.
    Output JSON menyertakan field 'sub_kategori'.
    """
    print(f"\n{'=' * 60}")
    print("📊 PREPROCESSING + SENTIMENT PER TEMPAT")
    print(f"{'=' * 60}")

    all_summary = []

    for place in results:
        nama        = place.get("title", "unknown")
        folder_name = get_folder(nama)
        folder      = os.path.join(OUTPUT_DIR, folder_name)
        os.makedirs(folder, exist_ok=True)
        reviews     = place.get("reviews", [])
        lat, lng    = get_lokasi(folder_name, place)

        sub_kat = place.get("sub_kategori") or get_sub_kategori(folder_name)
        kat     = _kategori_utama(sub_kat)

        print(f"\n📍 {nama} [{sub_kat}]")
        if not reviews:
            print(f"   ⚠️  Tidak ada ulasan, dilewati.")
            continue

        rows = []
        for r in reviews:
            rows.append({
                "Kategori"      : kat,
                "Sub Kategori"  : sub_kat,
                "Tempat"        : nama,
                "Rating Tempat" : place.get("totalScore", ""),
                "Total Ulasan"  : place.get("reviewsCount", ""),
                "Nama Reviewer" : r.get("name") or "",
                "Bintang"       : r.get("stars") or "",
                "Tanggal"       : r.get("publishedAtDate") or "",
                "Ulasan"        : (r.get("text") or "").replace("\n", " "),
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
        df["sentimen"]       = [
            koreksi_dengan_bintang(label, bintang)
            for label, bintang in zip(df["sentimen"], df["Bintang"])
        ]

        if len(df) == 0:
            print("   ⚠️  Semua ulasan kosong setelah preprocessing, skip.")
            continue

        item = _build_summary_item(folder_name, nama, place, df, lat, lng)

        total_u = item["total_ulasan"]
        print(f"   ⭐ Rating  : {item['rating']}")
        print(f"   ✅ Positif : {item['positif']} ({item['persen_positif']}%)")
        print(f"   ➖ Netral  : {item['netral']}  ({item['persen_netral']}%)")
        print(f"   ❌ Negatif : {item['negatif']} ({item['persen_negatif']}%)")

        item["ulasan"] = df[[
            "Kategori", "Sub Kategori", "Nama Reviewer", "Bintang", "Tanggal",
            "Ulasan", "teks_final", "topik", "sentimen", "sentimen_score"
        ]].to_dict(orient="records")

        csv_out = os.path.join(folder, "ulasan_sentimen.csv")
        df.to_csv(csv_out, index=False, encoding="utf-8-sig")
        print(f"   💾 {csv_out}")

        json_out = os.path.join(folder, "ulasan_sentimen.json")
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
        print(f"   💾 {json_out}")

        all_summary.append({k: v for k, v in item.items() if k != "ulasan"})

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
    Sekarang menyertakan field 'sub_kategori' di setiap item.
    """
    print("\n" + "=" * 60)
    print("TAHAP 4 — SCAN OUTPUT & REBUILD SUMMARY")
    print("=" * 60)

    # Load master CSV untuk mapping nama → sub_kategori & kategori
    master_map = {}
    if os.path.exists(MASTER_FILE):
        df_master = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
        for _, row in df_master.iterrows():
            key = get_folder(str(row["nama"]))
            master_map[key] = {
                "sub_kategori": str(row.get("sub_kategori", "")).strip(),
                "kategori"    : str(row.get("kategori", "")).strip(),
                "nama"        : str(row["nama"]),
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
        sub_kat = (
            master_info.get("sub_kategori")
            or get_sub_kategori(folder_name)
        )
        if not sub_kat or sub_kat.lower() in ("nan", "none", ""):
            sub_kat = get_sub_kategori(folder_name)
        kat         = _kategori_utama(sub_kat)
        nama_master = master_info.get("nama", "")

        if os.path.exists(json_sentimen):
            with open(json_sentimen, "r", encoding="utf-8") as f:
                data = json.load(f)
            nama = data.get("tempat") or nama_master or folder_name
            lat  = data.get("latitude")
            lng  = data.get("longitude")
            if lat is None or lng is None:
                lat, lng = get_lokasi(folder_name)
            summary.append({
                "key"           : folder_name,
                "kategori"      : kat,
                "sub_kategori"  : sub_kat,
                "tempat"        : nama,
                "rating"        : float(data.get("rating") or 0),
                "total_ulasan"  : int(data.get("total_ulasan") or 0),
                "positif"       : int(data.get("positif") or 0),
                "netral"        : int(data.get("netral") or 0),
                "negatif"       : int(data.get("negatif") or 0),
                "persen_positif": float(data.get("persen_positif") or 0),
                "persen_netral" : float(data.get("persen_netral") or 0),
                "persen_negatif": float(data.get("persen_negatif") or 0),
                "latitude"      : lat,
                "longitude"     : lng,
            })
            print(f"✅ {nama} [{sub_kat}]")

        elif os.path.exists(json_mentah):
            with open(json_mentah, "r", encoding="utf-8") as f:
                data = json.load(f)
            nama = data.get("title") or nama_master or folder_name
            lat, lng = get_lokasi(folder_name, data)
            summary.append({
                "key"           : folder_name,
                "kategori"      : kat,
                "sub_kategori"  : sub_kat,
                "tempat"        : nama,
                "rating"        : float(data.get("totalScore") or 0),
                "total_ulasan"  : int(data.get("reviewsCount") or 0),
                "positif"       : 0,
                "netral"        : 0,
                "negatif"       : 0,
                "persen_positif": 0.0,
                "persen_netral" : 0.0,
                "persen_negatif": 0.0,
                "latitude"      : lat,
                "longitude"     : lng,
            })
            print(f"⚠️  {nama} [{sub_kat}] (belum diproses sentimen)")

        else:
            skipped.append(folder_name)

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Summary dibuat: {len(summary)} tempat")
    print(f"⛔ Skip: {len(skipped)} folder")
    print(f"💾 {SUMMARY_FILE}")

    # Statistik per sub-kategori
    from collections import Counter
    counter = Counter(item["sub_kategori"] for item in summary)
    print("\n📊 Distribusi sub-kategori:")
    for sub, count in sorted(counter.items()):
        print(f"   {sub}: {count}")


# ════════════════════════════════════════════════════════════════
# TAHAP 5 — BERSIHKAN KOORDINAT (untuk summary yang sudah ada)
# ════════════════════════════════════════════════════════════════

def bersihkan_koordinat():
    """
    Tahap 5: Validasi ulang latitude/longitude pada
    semua_tempat_summary.json yang SUDAH ADA.
    """
    print("\n" + "=" * 60)
    print("TAHAP 5 — BERSIHKAN KOORDINAT")
    print("=" * 60)

    if not os.path.exists(SUMMARY_FILE):
        print(f"⚠️  {SUMMARY_FILE} belum ada, jalankan tahap 'scan' dulu.")
        return

    backup_path = SUMMARY_FILE + ".bak"
    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 Backup dibuat: {backup_path}")

    total       = len(data)
    dibersihkan = []

    for tempat in data:
        key      = tempat.get("key", "")
        nama     = tempat.get("tempat", key)
        lat_lama = tempat.get("latitude")
        lng_lama = tempat.get("longitude")

        if lat_lama is None or lng_lama is None:
            continue

        lat_baru, lng_baru = get_lokasi(key)

        if lat_baru is None or lng_baru is None:
            dibersihkan.append(f"  - {nama}  (lat={lat_lama}, lng={lng_lama})")
            tempat["latitude"]  = None
            tempat["longitude"] = None

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Total tempat        : {total}")
    print(f"✅ Koordinat dibersihkan: {len(dibersihkan)}")
    if dibersihkan:
        print("\nTempat yang koordinatnya dikosongkan:")
        print("\n".join(dibersihkan))
    print(f"\n💾 {SUMMARY_FILE}")


# ════════════════════════════════════════════════════════════════
# TAHAP 6 — SWEEP SELURUH WILAYAH GRESIK (GRID + KEYWORD UMUM)
# ════════════════════════════════════════════════════════════════
#
# Strategi:
#   1. Bagi wilayah Kabupaten Gresik (daratan) dan Pulau Bawean
#      menjadi sel-sel koordinat (grid).
#   2. Untuk setiap sel, jalankan query dengan daftar keyword generik
#      (masjid, musholla, spbu, warung, dll) agar semua jenis tempat
#      terjaring meski tidak ada dalam KATEGORI_CARI.
#   3. Setiap tempat yang ditemukan divalidasi lewat dalam_area_gresik()
#      dan kota_valid() sebelum dimasukkan ke master_tempat.csv.
#   4. Checkpoint per-sel disimpan ke sweep_checkpoint.json sehingga
#      bisa dilanjutkan jika proses terputus.
#   5. Hasil di-merge ke master_tempat.csv (deduplikasi berdasarkan nama).
#
# Parameter kunci:
#   SWEEP_STEP_LAT  — tinggi satu sel (derajat lintang)
#   SWEEP_STEP_LNG  — lebar satu sel (derajat bujur)
#   SWEEP_MAX_PLACES — batas hasil per query per sel
#
# Perkiraan sel:
#   Daratan Gresik  ≈ 12 × 10 = 120 sel  (step 0.05°)
#   Pulau Bawean    ≈  4 ×  4 =  16 sel
#   Total keyword   = 20 keyword umum
#   → ~136 sel × 20 keyword ≈ 2.720 query
#   Gunakan rotasi token; setiap token Apify gratis ~$5/bulan.
# ════════════════════════════════════════════════════════════════

# Batas kotak wilayah (daratan Gresik, bukan Bawean)
_DARATAN_LAT_MIN, _DARATAN_LAT_MAX = -7.55, -7.00
_DARATAN_LNG_MIN, _DARATAN_LNG_MAX = 112.30, 112.80

# Pulau Bawean (terpisah jauh di utara)
_BAWEAN_LAT_MIN, _BAWEAN_LAT_MAX = -5.85, -5.65
_BAWEAN_LNG_MIN, _BAWEAN_LNG_MAX = 112.55, 112.75

# Resolusi grid
SWEEP_STEP_LAT   = 0.05   # ~5.5 km per sel
SWEEP_STEP_LNG   = 0.05   # ~4.9 km per sel
SWEEP_MAX_PLACES = 20     # hasil per query (hemat kuota)

SWEEP_CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "sweep_checkpoint.json")

# Keyword umum yang dipakai di setiap sel grid.
# Dipilih agar mencakup tempat yang tidak ada di KATEGORI_CARI keyword.
SWEEP_KEYWORDS_UMUM = [
    "masjid",
    "musholla",
    "mushola",
    "gereja",
    "pura",
    "vihara",
    "spbu",
    "pom bensin",
    "polsek",
    "koramil",
    "pemadam kebakaran",
    "pasar",
    "minimarket",
    "indomaret",
    "alfamart",
    "warung makan",
    "rumah makan",
    "apotek",
    "kantor desa",
    "posyandu",
    "sekolah",
    "puskesmas",
    "klinik",
    "taman",
    "lapangan",
    "terminal",
    "dermaga",
    "pelabuhan",
    "hotel",
    "penginapan",
]


def _buat_grid_sel() -> list[dict]:
    """
    Hasilkan daftar sel grid untuk daratan Gresik dan Pulau Bawean.
    Setiap sel berupa dict dengan center_lat, center_lng, label.
    """
    import math

    sel_list = []

    def tambah_grid(lat_min, lat_max, lng_min, lng_max, label_prefix):
        lat = lat_min
        while lat < lat_max:
            lng = lng_min
            while lng < lng_max:
                center_lat = round(lat + SWEEP_STEP_LAT / 2, 6)
                center_lng = round(lng + SWEEP_STEP_LNG / 2, 6)
                sel_list.append({
                    "label"     : f"{label_prefix}_{round(lat,3)}_{round(lng,3)}",
                    "center_lat": center_lat,
                    "center_lng": center_lng,
                })
                lng = round(lng + SWEEP_STEP_LNG, 6)
            lat = round(lat + SWEEP_STEP_LAT, 6)

    tambah_grid(_DARATAN_LAT_MIN, _DARATAN_LAT_MAX,
                _DARATAN_LNG_MIN, _DARATAN_LNG_MAX, "daratan")
    tambah_grid(_BAWEAN_LAT_MIN,  _BAWEAN_LAT_MAX,
                _BAWEAN_LNG_MIN,  _BAWEAN_LNG_MAX,  "bawean")

    return sel_list


def _load_sweep_checkpoint() -> set:
    """Muat set label sel yang sudah selesai."""
    if os.path.exists(SWEEP_CHECKPOINT_FILE):
        try:
            with open(SWEEP_CHECKPOINT_FILE, "r") as f:
                data = json.load(f)
            return set(data.get("selesai", []))
        except Exception:
            pass
    return set()


def _save_sweep_checkpoint(selesai: set):
    with open(SWEEP_CHECKPOINT_FILE, "w") as f:
        json.dump({"selesai": list(selesai)}, f)


def _clear_sweep_checkpoint():
    if os.path.exists(SWEEP_CHECKPOINT_FILE):
        os.remove(SWEEP_CHECKPOINT_FILE)


def cari_semua_gresik(keywords: list[str] | None = None, reset: bool = False):
    """
    Tahap 6 / mode 'sweep': Crawl SELURUH wilayah Kabupaten Gresik
    (daratan + Pulau Bawean) menggunakan grid koordinat dan daftar
    keyword umum.

    Parameter
    ---------
    keywords : list[str] | None
        Daftar keyword yang akan digunakan di setiap sel.
        Default: SWEEP_KEYWORDS_UMUM (30 keyword generik).
    reset : bool
        Jika True, abaikan checkpoint dan mulai dari awal.

    Output
    ------
    Hasil di-merge ke master_tempat.csv. Tempat yang sudah ada
    (nama duplikat) tidak ditambahkan ulang.
    """
    print("\n" + "=" * 60)
    print("TAHAP 6 — SWEEP SELURUH WILAYAH GRESIK (GRID + KEYWORD UMUM)")
    print("=" * 60)

    token = SINGLE_TOKEN or (TOKENS[0] if TOKENS else None)
    if not token:
        print("❌ Tidak ada token Apify. Set APIFY_API_TOKEN di .env")
        return

    kw_list = keywords or SWEEP_KEYWORDS_UMUM
    sel_list = _buat_grid_sel()

    print(f"🗺️  Total sel grid : {len(sel_list)}")
    print(f"🔑 Keyword per sel : {len(kw_list)}")
    print(f"📊 Total query     : {len(sel_list) * len(kw_list)}")

    if reset:
        _clear_sweep_checkpoint()
        print("🔄 Checkpoint direset, mulai dari awal.")

    selesai_set = _load_sweep_checkpoint()
    if selesai_set:
        print(f"⏩ Melanjutkan sweep ({len(selesai_set)} sel sudah selesai)")

    # Muat nama-nama yang sudah ada di master (untuk deduplikasi)
    existing_names: set[str] = set()
    existing_rows:  list[dict] = []
    if os.path.exists(MASTER_FILE):
        try:
            df_existing = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
            existing_names = set(df_existing["nama"].dropna().str.strip().str.lower())
            existing_rows  = df_existing.to_dict(orient="records")
        except Exception:
            pass

    client       = ApifyClient(token)
    temuan_baru  = []
    total_query  = 0
    total_temuan = 0

    for idx_sel, sel in enumerate(sel_list):
        label = sel["label"]

        if label in selesai_set:
            continue

        print(f"\n[{idx_sel + 1}/{len(sel_list)}] 📍 Sel {label}")

        for keyword in kw_list:
            total_query += 1
            try:
                run_input = {
                    "searchStringsArray"       : [keyword],
                    "lat"                      : sel["center_lat"],
                    "lng"                      : sel["center_lng"],
                    "zoom"                     : 14,          # ~3 km radius
                    "maxCrawledPlacesPerSearch": SWEEP_MAX_PLACES,
                    "includeReviews"           : False,
                    "language"                 : "id",
                }
                run     = client.actor("compass/crawler-google-places").call(run_input=run_input)
                dataset = client.dataset(run.default_dataset_id)

                for item in dataset.iterate_items():
                    nama  = str(item.get("title", "")).strip()
                    if not nama:
                        continue

                    # Validasi koordinat wilayah Gresik
                    loc = item.get("location") or {}
                    lat = loc.get("lat")
                    lng = loc.get("lng")
                    if not dalam_area_gresik(lat, lng):
                        continue

                    # Validasi kota
                    if not kota_valid(item):
                        continue

                    # Deduplikasi berdasarkan nama (case-insensitive)
                    if nama.lower() in existing_names:
                        continue

                    # Tebak sub-kategori dari nama tempat
                    fn      = get_folder(nama)
                    sub_kat = get_sub_kategori(fn)
                    kat     = _kategori_utama(sub_kat)

                    row = {
                        "sub_kategori" : sub_kat,
                        "kategori"     : kat,
                        "nama"         : nama,
                        "alamat"       : item.get("address", ""),
                        "rating"       : item.get("totalScore", ""),
                        "jumlah_ulasan": item.get("reviewsCount", ""),
                    }
                    temuan_baru.append(row)
                    existing_names.add(nama.lower())
                    total_temuan += 1

            except Exception as e:
                err = str(e).lower()
                if any(k in err for k in ["402", "limit", "quota", "payment", "credit"]):
                    print(f"   ⚠️  Kuota habis pada keyword '{keyword}': {str(e)[:60]}")
                    print("   ⏸️  Sweep dihentikan sementara. Checkpoint disimpan.")
                    _save_sweep_checkpoint(selesai_set)
                    _flush_sweep_ke_master(existing_rows, temuan_baru)
                    return
                else:
                    print(f"   ⚠️  Error '{keyword}': {str(e)[:60]}")
                    continue

        selesai_set.add(label)
        _save_sweep_checkpoint(selesai_set)
        print(f"   ✅ Selesai sel {label} | Temuan baru s/d sekarang: {total_temuan}")

    # Semua sel selesai
    _flush_sweep_ke_master(existing_rows, temuan_baru)
    _clear_sweep_checkpoint()

    print(f"\n{'=' * 60}")
    print(f"✅ Sweep selesai!")
    print(f"   Total query    : {total_query}")
    print(f"   Tempat baru    : {total_temuan}")
    print(f"   Total master   : {len(existing_rows) + total_temuan}")
    print(f"💾 {MASTER_FILE}")


def _flush_sweep_ke_master(existing_rows: list[dict], temuan_baru: list[dict]):
    """Gabungkan existing_rows + temuan_baru dan simpan ke master_tempat.csv."""
    semua = existing_rows + temuan_baru
    df = pd.DataFrame(semua)
    # Pastikan kolom sub_kategori & kategori ada
    for col in ["sub_kategori", "kategori", "nama", "alamat", "rating", "jumlah_ulasan"]:
        if col not in df.columns:
            df[col] = ""
    df.drop_duplicates(subset=["nama"], inplace=True)
    df.sort_values(["kategori", "sub_kategori", "nama"], inplace=True)
    df.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"\n💾 Master diperbarui: {len(df)} tempat → {MASTER_FILE}")
    # Cetak distribusi sub_kategori
    dist = df.groupby("sub_kategori").size().sort_values(ascending=False)
    print("\n📊 Distribusi sub-kategori setelah sweep:")
    print(dist.to_string())


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

TAHAP_MAP = {
    "cari"      : "Tahap 1 — Cari Tempat (keyword per sub-kategori)",
    "scrape"    : "Tahap 2 — Scrape Ulasan Google Maps",
    "sentimen"  : "Tahap 3 — Analisis Sentimen IndoBERT",
    "scan"      : "Tahap 4 — Scan & Rebuild Summary",
    "bersihkan" : "Tahap 5 — Bersihkan Koordinat",
    "sweep"     : "Tahap 6 — Sweep Seluruh Wilayah Gresik (Grid Area)",
}

if __name__ == "__main__":
    args  = sys.argv[1:]
    tahap = None

    # Parse --tahap
    if "--tahap" in args:
        idx   = args.index("--tahap")
        tahap = args[idx + 1] if idx + 1 < len(args) else None

    # Parse --reset (untuk sweep)
    reset_sweep = "--reset" in args

    if tahap and tahap not in TAHAP_MAP:
        print(f"❌ Tahap tidak dikenal: '{tahap}'")
        print(f"   Pilihan: {', '.join(TAHAP_MAP.keys())}")
        sys.exit(1)

    # ── Tahap tunggal ────────────────────────────────────────
    if tahap == "cari":
        cari_tempat()

    elif tahap == "scrape":
        scrape_google_maps()

    elif tahap == "sentimen":
        analisis_sentimen()

    elif tahap == "scan":
        scan_output()

    elif tahap == "bersihkan":
        bersihkan_koordinat()

    elif tahap == "sweep":
        # Jalankan sweep area. Gunakan --reset untuk mulai dari awal.
        # Contoh:
        #   python googlemaps_baru.py --tahap sweep
        #   python googlemaps_baru.py --tahap sweep --reset
        cari_semua_gresik(reset=reset_sweep)

    # ── Semua tahap (pipeline penuh) ─────────────────────────
    else:
        print("🚀 Menjalankan pipeline lengkap...\n")
        print("   Urutan: cari → sweep → scrape → sentimen → scan → bersihkan")
        print("   Tip: jalankan tahap individu dengan --tahap <nama>\n")

        # Tahap 1: keyword per sub-kategori
        cari_tempat()

        # Tahap 6: sweep seluruh area (merge ke master yang sudah ada)
        # Jalankan setelah cari_tempat() agar temuan sweep langsung
        # ditambahkan ke master_tempat.csv yang baru dibuat.
        cari_semua_gresik()

        # Tahap 2: scrape ulasan per tempat di master
        results = scrape_google_maps()

        # Tahap 3: analisis sentimen
        if results:
            pipe = load_indobert()
            process_per_tempat(results, pipe)
        else:
            analisis_sentimen()

        # Tahap 4 & 5: rebuild summary + bersihkan koordinat
        scan_output()
        bersihkan_koordinat()

        print("\n🎉 Semua tahap selesai!")