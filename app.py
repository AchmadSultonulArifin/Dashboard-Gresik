from flask import Flask, render_template, jsonify, request
from flask import request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask import redirect, url_for, flash
from dotenv import load_dotenv
import pandas as pd
import json
import os
import re
import sqlite3

load_dotenv()
app = Flask(__name__)

# ── Konfigurasi MySQL ──────────────────────────────
app.config["SECRET_KEY"]       = os.getenv("SECRET_KEY", "Sultonul12")
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}"
    f"@{os.getenv('MYSQL_HOST')}/{os.getenv('MYSQL_DB')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db            = SQLAlchemy(app)
bcrypt        = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view    = "login"
login_manager.login_message = "Silakan login terlebih dahulu."

# Path file
CSV_PATH           = "output/gresik_sentimen.csv"
STATUS_FILE_PATH   = "output/scrape_status.json"
INSTAGRAM_POST     = "output/gresik_ig_postingan.csv"
INSTAGRAM_SENTIMEN = "output/gresik_ig_sentimen.csv"
SUMMARY_FILE       = "output/semua_tempat_summary.json"
FACEBOOK_SENTIMEN  = "output/data_sentimen_gresik.csv"
BERITA_CSV         = "output/gresik_berita.csv"
TOPIK_CSV          = "output/gresik_berita_topik.csv"
SUMBER_CSV         = "output/gresik_berita_sumber.csv"

DB_PATH = "accounts.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()

def init_keyword_tables():
    conn, cur = get_db()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS keyword_groups (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL UNIQUE,
            platform  TEXT    NOT NULL DEFAULT 'gmaps',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS keywords (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id   INTEGER NOT NULL REFERENCES keyword_groups(id) ON DELETE CASCADE,
            name       TEXT    NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, name)
        );

        -- ✅ BARU: keyword untuk scraping berita
        CREATE TABLE IF NOT EXISTS berita_keywords (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword    TEXT    NOT NULL UNIQUE,
            aktif      INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ✅ BARU: aturan kategorisasi topik berita
        CREATE TABLE IF NOT EXISTS berita_topik_rules (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            topik      TEXT    NOT NULL,
            kata_kunci TEXT    NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(topik, kata_kunci)
        );

        PRAGMA foreign_keys = ON;
    """)

    # Seed keyword default jika kosong
    cur.execute("SELECT COUNT(*) FROM berita_keywords")
    if cur.fetchone()[0] == 0:
        defaults = [
            "gresik","kabupaten gresik","kota gresik","petrokimia gresik",
            "semen gresik","gkb","driyorejo","cerme gresik","bungah gresik",
            "sidayu gresik","panceng gresik","ujungpangkah","manyar gresik","wringinanom"
        ]
        cur.executemany("INSERT OR IGNORE INTO berita_keywords (keyword) VALUES (?)",
                        [(k,) for k in defaults])

    # Seed topik rules default jika kosong
    cur.execute("SELECT COUNT(*) FROM berita_topik_rules")
    if cur.fetchone()[0] == 0:
        defaults_topik = [
            ("Ekonomi & UMKM","umkm"),("Ekonomi & UMKM","ekonomi"),("Ekonomi & UMKM","bisnis"),
            ("Ekonomi & UMKM","investasi"),("Ekonomi & UMKM","industri"),("Ekonomi & UMKM","pasar"),
            ("Infrastruktur","jalan"),("Infrastruktur","jembatan"),("Infrastruktur","pembangunan"),
            ("Infrastruktur","proyek"),("Infrastruktur","pelabuhan"),("Infrastruktur","tol"),
            ("Pendidikan","sekolah"),("Pendidikan","pendidikan"),("Pendidikan","siswa"),
            ("Pendidikan","guru"),("Pendidikan","universitas"),("Pendidikan","mahasiswa"),
            ("Kesehatan","kesehatan"),("Kesehatan","rumah sakit"),("Kesehatan","puskesmas"),
            ("Kesehatan","dokter"),("Kesehatan","vaksin"),("Kesehatan","stunting"),
            ("Lingkungan","lingkungan"),("Lingkungan","sampah"),("Lingkungan","banjir"),
            ("Lingkungan","limbah"),("Lingkungan","polusi"),("Lingkungan","sungai"),
            ("Sosial & Budaya","budaya"),("Sosial & Budaya","festival"),("Sosial & Budaya","wisata"),
            ("Sosial & Budaya","kuliner"),("Sosial & Budaya","tradisi"),
            ("Politik & Pemda","bupati"),("Politik & Pemda","dprd"),("Politik & Pemda","pemerintah"),
            ("Politik & Pemda","pilkada"),("Politik & Pemda","apbd"),("Politik & Pemda","dinas"),
            ("Keamanan & Hukum","polisi"),("Keamanan & Hukum","hukum"),("Keamanan & Hukum","kriminal"),
            ("Keamanan & Hukum","korupsi"),("Keamanan & Hukum","narkoba"),("Keamanan & Hukum","tersangka"),
            ("Olahraga","olahraga"),("Olahraga","sepak bola"),("Olahraga","turnamen"),("Olahraga","juara"),
            ("Industri & Tambang","semen gresik"),("Industri & Tambang","petrokimia"),
            ("Industri & Tambang","pupuk"),("Industri & Tambang","kawasan industri"),
        ]
        cur.executemany("INSERT OR IGNORE INTO berita_topik_rules (topik, kata_kunci) VALUES (?,?)",
                        defaults_topik)

    conn.commit()
    conn.close()

init_keyword_tables()   # <-- panggil langsung di sini

# Upload Foto Profil
UPLOAD_FOLDER_FOTO = os.path.join("static", "foto_profil")
os.makedirs(UPLOAD_FOLDER_FOTO, exist_ok=True)
EKSTENSI_DIIZINKAN = {"png", "jpg", "jpeg", "webp"}

def ekstensi_valid(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in EKSTENSI_DIIZINKAN


# ══════════════════════════════════════════════════════════════
# NORMALISASI KATEGORI (sub-kategori detail)
# ══════════════════════════════════════════════════════════════
def normalisasi_kategori(nama: str, kategori_asli: str) -> str:
    """
    Petakan nama tempat ke sub-kategori yang lebih spesifik.
    Hanya override jika kategori_asli kosong atau 'Lainnya'.

    Urutan ATURAN penting: yang lebih spesifik harus di atas
    agar tidak tertangkap oleh aturan yang lebih umum.
    """
    # Jika kategori sudah spesifik, gunakan langsung
    if kategori_asli and kategori_asli.strip().lower() not in ("", "lainnya"):
        return kategori_asli

    n = nama.lower()

    ATURAN = [

        # ── KESEHATAN ──────────────────────────────────────────
        # Urutan: RS dulu (lebih spesifik), baru klinik, puskesmas, dst.
        (["rsud", "rumah sakit umum daerah", "rsu ", "rsia ", "rs dr",
          "rs paru", "rs jiwa", "rs mata", "rs orthopedi",
          "rumah sakit"],
         "Kesehatan — Rumah Sakit"),

        (["puskesmas", "pkm ", "pustu ", "puskesdes",
          "posyandu", "poskesdes"],
         "Kesehatan — Puskesmas"),

        (["klinik", "klinik pratama", "klinik utama",
          "balai pengobatan", "bp ", "aesthetic clinic",
          "skincare", "kecantikan", "clinic"],
         "Kesehatan — Klinik"),

        (["apotek", "apotik", "farmasi", "drug store"],
         "Kesehatan — Apotek"),

        (["bidan", "praktik bidan", "dokter", "dr. ", "drg.",
          "praktik dokter", "dr "],
         "Kesehatan — Dokter & Bidan Praktik"),

        (["laboratorium", "laborat", "lab "],
         "Kesehatan — Laboratorium"),

        # ── PEMERINTAHAN ──────────────────────────────────────
        (["kantor desa", "balai desa", "kantor kepala desa",
          "pemerintah desa", "pemdes"],
         "Pemerintahan — Kantor Desa"),

        (["kantor kelurahan", "kelurahan "],
         "Pemerintahan — Kelurahan"),

        (["kantor kecamatan", "kecamatan "],
         "Pemerintahan — Kecamatan"),

        (["kantor bupati", "kantor pemkab", "pemkab", "pemerintah kabupaten",
          "sekretariat daerah", "setda", "setdakab"],
         "Pemerintahan — Pemkab & Sekretariat"),

        (["dinas ", "badan ", "kantor dinas", "uptd ", "upt "],
         "Pemerintahan — Dinas & Instansi"),

        (["dprd", "dewan perwakilan"],
         "Pemerintahan — DPRD"),

        (["polsek", "polres", "polda", "kepolisian",
          "kantor polisi", "pos polisi"],
         "Pemerintahan — Kepolisian"),

        (["koramil", "kodim", "korem", "tentara", "tni",
          "markas", "batalyon"],
         "Pemerintahan — TNI & Militer"),

        (["pengadilan", "kejaksaan", "lapas", "rutan",
          "lembaga pemasyarakatan"],
         "Pemerintahan — Lembaga Hukum"),

        (["bpbd", "basarnas", "sar ", "damkar", "pemadam kebakaran"],
         "Pemerintahan — Kedaruratan & Bencana"),

        # ── PENDIDIKAN ────────────────────────────────────────
        (["universitas", "univ ", "institut ", "sekolah tinggi",
          "stikes", "stikim", "stia", "politeknik", "akademi ",
          "kampus"],
         "Pendidikan — Perguruan Tinggi"),

        (["pesantren", "pondok pesantren", "ponpes", "tpq ",
          "taman pendidikan quran", "madin ", "madrasah diniyah"],
         "Pendidikan — Pesantren & TPQ"),

        (["madrasah aliyah", " man ", "ma ", " sma ", "sman ",
          " smk ", "smkn ", "sekolah menengah atas",
          "sekolah menengah kejuruan"],
         "Pendidikan — SMA/SMK/MA"),

        (["madrasah tsanawiyah", " mts ", " smp ", "smpn ",
          "sekolah menengah pertama"],
         "Pendidikan — SMP/MTs"),

        (["madrasah ibtidaiyah", " mi ", " sd ", "sdn ", "sdit ",
          "sekolah dasar", "upt sd", "upt sdn"],
         "Pendidikan — SD/MI"),

        (["paud", "tk ", "taman kanak", "ra ", "raudhatul",
          "playgroup", "kb "],
         "Pendidikan — PAUD & TK"),

        # ── PELAYANAN PUBLIK ──────────────────────────────────
        (["disdukcapil", "dukcapil", "catatan sipil",
          "kependudukan", "capil"],
         "Pelayanan Publik — Adminduk"),

        (["samsat", "pajak kendaraan", "bapenda"],
         "Pelayanan Publik — Samsat & Pajak Kendaraan"),

        (["kantor pajak", "kpp pratama", "kpp ", "bea cukai",
          "dirjen pajak"],
         "Pelayanan Publik — Perpajakan"),

        (["bpjs ketenagakerjaan", "jamsostek", "bpjamsostek"],
         "Pelayanan Publik — BPJS Ketenagakerjaan"),

        (["bpjs kesehatan", "bpjs "],
         "Pelayanan Publik — BPJS Kesehatan"),

        (["kantor pos", "pos indonesia", "jne", "j&t", "sicepat",
          "anteraja", "ekspedisi"],
         "Pelayanan Publik — Pos & Ekspedisi"),

        (["imigrasi", "kantor imigrasi"],
         "Pelayanan Publik — Imigrasi"),

        (["kua ", "kantor urusan agama"],
         "Pelayanan Publik — KUA"),

        (["bpn ", "atrbpn", "pertanahan"],
         "Pelayanan Publik — Pertanahan"),

        (["mall pelayanan publik", "mpp "],
         "Pelayanan Publik — Mall Pelayanan Publik"),

        (["disnaker", "dinas tenaga kerja", "bp2mi"],
         "Pelayanan Publik — Ketenagakerjaan"),

        # ── PERBANKAN & KEUANGAN ──────────────────────────────
        (["bank bri", "bri "],
         "Perbankan — BRI"),

        (["bank bni", "bni "],
         "Perbankan — BNI"),

        (["bank bca", "bca "],
         "Perbankan — BCA"),

        (["bank mandiri", "mandiri "],
         "Perbankan — Mandiri"),

        (["bank btn", "btn "],
         "Perbankan — BTN"),

        (["bank jatim", "bankjatim"],
         "Perbankan — Bank Jatim"),

        (["bank syariah indonesia", "bsi ", "bank muamalat",
          "bank syariah", "bmt ", "baitul maal"],
         "Perbankan — Bank Syariah & BMT"),

        (["bpr ", "bank perkreditan", "lembaga keuangan mikro",
          "koperasi simpan pinjam", "ksp "],
         "Perbankan — BPR & Koperasi"),

        (["pegadaian"],
         "Perbankan — Pegadaian"),

        (["atm ", "mesin atm", "brilink", "agen bri",
          "agen bni", "agen mandiri", "agen bank", "laku pandai"],
         "Perbankan — ATM & Agen"),

        (["bank "],
         "Perbankan — Bank Umum"),

        # ── WISATA & ALAM ─────────────────────────────────────
        (["pantai", "pesisir"],
         "Wisata — Pantai"),

        (["taman", "alun-alun", "alun alun", "ruang terbuka"],
         "Wisata — Taman & Alun-alun"),

        (["telaga", "danau", "waduk", "embung"],
         "Wisata — Danau & Waduk"),

        (["museum", "monumen", "tugu", "situs", "cagar budaya"],
         "Wisata — Budaya & Sejarah"),

        (["wisata", "agrowisata", "ekowisata"],
         "Wisata — Wisata Umum"),

        # ── STADION & OLAHRAGA ────────────────────────────────
        (["stadion", "gelora"],
         "Olahraga — Stadion"),

        (["gor ", "gedung olahraga", "gedung olah raga"],
         "Olahraga — GOR"),

        (["lapangan", "soccerfield", "futsal"],
         "Olahraga — Lapangan"),

        (["kolam renang", "kolam_renang", "renang"],
         "Olahraga — Kolam Renang"),

        (["fitness", "gym ", "sport center"],
         "Olahraga — Fitness & Gym"),

        # ── TEMPAT IBADAH ─────────────────────────────────────
        (["masjid", "musholla", "mushola", "surau", "langgar"],
         "Tempat Ibadah — Masjid & Mushola"),

        (["gereja"],
         "Tempat Ibadah — Gereja"),

        (["pura", "vihara", "klenteng", "temple"],
         "Tempat Ibadah — Non-Muslim"),

        # ── INDUSTRI ──────────────────────────────────────────
        (["petrokimia", "semen gresik", "pabrik", "industri",
          "pt ", "cv ", "perusahaan", "gudang", "kawasan industri"],
         "Industri"),

        # ── PERDAGANGAN ───────────────────────────────────────
        (["pasar ", "pasar tradisional"],
         "Perdagangan — Pasar"),

        (["mall", "plaza", "supermarket", "swalayan",
          "indomaret", "alfamart", "minimarket"],
         "Perdagangan — Ritel Modern"),

        (["toko", "warung"],
         "Perdagangan — Toko & Warung"),

        # ── KULINER ───────────────────────────────────────────
        (["restoran", "restaurant", "rumah makan", "rm "],
         "Kuliner — Restoran"),

        (["cafe", "kafe", "coffee", "kopi"],
         "Kuliner — Kafe & Kopi"),

        (["warung makan", "bakso", "mie ", "nasi ", "soto",
          "ayam", "seafood", "pizza", "burger", "kedai"],
         "Kuliner — Warung & Kedai"),

        # ── HOTEL & PENGINAPAN ────────────────────────────────
        (["hotel", "resort", "villa", "penginapan",
          "homestay", "guest house"],
         "Hotel & Penginapan"),
    ]

    for keywords, kategori_baru in ATURAN:
        if any(kw in n for kw in keywords):
            return kategori_baru

    return "Lainnya"


# ── Context Processor ──────────────────────────────
@app.context_processor
def inject_update_terakhir():
    update_twitter = "-"
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH, usecols=["tanggal"])
            df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")
            update_twitter = df["tanggal"].max().strftime("%d %B %Y")
        except Exception:
            pass

    update_gmaps = "-"
    if os.path.exists(SUMMARY_FILE):
        try:
            mtime = os.path.getmtime(SUMMARY_FILE)
            update_gmaps = pd.Timestamp(mtime, unit="s").strftime("%d %B %Y")
        except Exception:
            pass

    update_instagram = "-"
    if os.path.exists(INSTAGRAM_POST):
        try:
            df_ig = pd.read_csv(INSTAGRAM_POST, usecols=["tanggal"])
            df_ig["tanggal"] = pd.to_datetime(df_ig["tanggal"], errors="coerce")
            update_instagram = df_ig["tanggal"].max().strftime("%d %B %Y")
        except Exception:
            pass

    return dict(
        update_twitter=update_twitter,
        update_gmaps=update_gmaps,
        update_instagram=update_instagram,
        scrape_status=load_scrape_status(),
    )

def catat_log(platform, aktivitas, status, keterangan=""):
    try:
        log = ActivityLog(platform=platform, aktivitas=aktivitas, status=status, keterangan=keterangan)
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Gagal mencatat log:", e)

_LAST_FILE_STATE = {}

def deteksi_perubahan_file(platform, path, aktivitas="scraping"):
    if not os.path.exists(path):
        return
    mtime = os.path.getmtime(path)
    kunci = f"{platform}_{aktivitas}"
    if _LAST_FILE_STATE.get(kunci) == mtime:
        return
    _LAST_FILE_STATE[kunci] = mtime
    total = 0
    try:
        if path.endswith(".csv"):
            total = len(pd.read_csv(path))
        elif path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            total = len(data) if isinstance(data, list) else 1
    except Exception as e:
        catat_log(platform, aktivitas, "gagal", f"Gagal membaca file: {e}")
        return
    catat_log(platform, aktivitas, "sukses", f"{total} data terdeteksi di {os.path.basename(path)}")

def cek_semua_platform():
    deteksi_perubahan_file("twitter",    CSV_PATH)
    deteksi_perubahan_file("instagram",  INSTAGRAM_POST)
    deteksi_perubahan_file("googlemaps", SUMMARY_FILE)
    deteksi_perubahan_file("facebook",   FACEBOOK_SENTIMEN)

def load_data():
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()
    try:
        df = pd.read_csv(CSV_PATH)
        if "teks_asli" in df.columns:
            df["teks_asli"] = df["teks_asli"].astype(str)
        if "username" in df.columns:
            df["username"] = df["username"].astype(str)
        if "tanggal" in df.columns:
            df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")
        df["likes"]    = pd.to_numeric(df.get("likes"),    errors="coerce").fillna(0) if "likes"    in df.columns else 0
        df["retweets"] = pd.to_numeric(df.get("retweets"), errors="coerce").fillna(0) if "retweets" in df.columns else 0
        df["replies"]  = pd.to_numeric(df.get("replies"),  errors="coerce").fillna(0) if "replies"  in df.columns else 0
        df["skor"]     = pd.to_numeric(df.get("skor"),     errors="coerce").fillna(0) if "skor"     in df.columns else 0.0
        return df
    except Exception as e:
        print("Error membaca CSV:", e)
        return pd.DataFrame()

def load_scrape_status():
    if not os.path.exists(STATUS_FILE_PATH):
        return {}
    try:
        with open(STATUS_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def parse_likes(nilai):
    if nilai is None:
        return 0
    s = str(nilai).strip().upper()
    if not s or s in ("NAN", "NONE", "", "-"):
        return 0
    try:
        if s.endswith("K"):
            return max(0, int(float(s[:-1]) * 1_000))
        if s.endswith("M"):
            return max(0, int(float(s[:-1]) * 1_000_000))
        s_clean = s.replace(",", "")
        if s_clean.count(".") == 1:
            bagian = s_clean.split(".")
            if len(bagian[1]) >= 3:
                s_clean = s_clean.replace(".", "")
        else:
            s_clean = s_clean.replace(".", "")
        return max(0, int(float(s_clean)))
    except (ValueError, OverflowError):
        return 0

def load_instagram():
    if not os.path.exists(INSTAGRAM_POST):
        return pd.DataFrame()
    try:
        df = pd.read_csv(INSTAGRAM_POST).fillna("")
        for kolom in ["keyword","shortcode","link_postingan","username","caption","tanggal","likes","comments"]:
            if kolom not in df.columns:
                df[kolom] = ""
        df["likes"]    = df["likes"].apply(parse_likes)
        df["comments"] = pd.to_numeric(df["comments"], errors="coerce").fillna(0).astype(int)
        df["tanggal"]  = pd.to_datetime(df["tanggal"], errors="coerce")
        return df
    except Exception as e:
        print("Error membaca data Instagram:", e)
        return pd.DataFrame()

def load_instagram_sentimen():
    if not os.path.exists(INSTAGRAM_SENTIMEN):
        return pd.DataFrame()
    return pd.read_csv(INSTAGRAM_SENTIMEN)

def ringkasan_twitter():
    df = load_data()
    if df.empty:
        return []
    hasil = []
    for tanggal, grup in df.groupby(df["tanggal"].dt.date):
        hasil.append({
            "tanggal" : tanggal.strftime("%d %B %Y"),
            "jumlah"  : len(grup),
            "positif" : (grup["sentimen"]=="positif").sum(),
            "netral"  : (grup["sentimen"]=="netral").sum(),
            "negatif" : (grup["sentimen"]=="negatif").sum(),
            "skor"    : round(grup["skor"].mean(), 3),
            "likes"   : int(grup["likes"].sum()),
            "replies" : int(grup["replies"].sum()),
            "retweets": int(grup["retweets"].sum()),
        })
    return hasil

def ringkasan_instagram():
    post     = load_instagram()
    sentimen = load_instagram_sentimen()
    if post.empty or sentimen.empty:
        return []
    hasil = []
    for tanggal, grup_post in post.groupby(post["tanggal"].dt.date):
        komentar = sentimen[sentimen["shortcode"].isin(grup_post["shortcode"])]
        hasil.append({
            "tanggal"  : tanggal.strftime("%d %B %Y"),
            "postingan": len(grup_post),
            "likes"    : int(grup_post["likes"].sum()),
            "komentar" : int(grup_post["comments"].sum()),
            "positif"  : (komentar["sentimen"]=="positif").sum(),
            "netral"   : (komentar["sentimen"]=="netral").sum(),
            "negatif"  : (komentar["sentimen"]=="negatif").sum(),
            "skor"     : round(komentar["skor"].mean(), 3),
        })
    return hasil

# ── Google Maps ────────────────────────────────────
def load_google_maps() -> list:
    if not os.path.exists(SUMMARY_FILE):
        return []
    try:
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            semua = json.load(f)
        hasil = []
        for t in semua:
            if "key" not in t:
                t["key"] = re.sub(r'[^a-z0-9]+', '_', str(t.get("tempat","")).lower()).strip('_')
            nama = str(t.get("tempat") or t.get("key") or "")

            # ✅ Filter: skip tempat tanpa koordinat valid Gresik
            lat = t.get("latitude")
            lng = t.get("longitude")
            if lat is None or lng is None:
                pass  # tetap masukkan, tapi tanpa koordinat
            else:
                # Tolak koordinat di luar Gresik + Bawean
                if not ((-7.65 <= float(lat) <= -5.55) and (112.20 <= float(lng) <= 112.95)):
                    continue  # skip tempat luar Gresik
            # ✅ Ambil sub_kategori dari summary
            sub_kat = str(t.get("sub_kategori") or "Lainnya")
            kat     = normalisasi_kategori(nama, str(t.get("kategori") or ""))    
            hasil.append({
                "id"            : str(t.get("key") or ""),
                "key"           : str(t.get("key") or ""),
                "nama"          : nama,
                "tempat"        : nama,
                "kategori"      : kat,
                "sub_kategori"  : sub_kat,   # ✅ tambah ini
                "rating"        : float(t.get("rating") or 0),
                "total_ulasan"  : int(t.get("total_ulasan") or 0),
                "positif"       : int(t.get("positif") or 0),
                "netral"        : int(t.get("netral") or 0),
                "negatif"       : int(t.get("negatif") or 0),
                "persen_positif": float(t.get("persen_positif") or 0),
                "persen_netral" : float(t.get("persen_netral") or 0),
                "persen_negatif": float(t.get("persen_negatif") or 0),
                "latitude"      : lat,
                "longitude"     : lng,
            })
        return hasil
    except Exception as e:
        print("Error load summary:", e)
        return []

def load_detail_tempat(key: str) -> dict:
    path = os.path.join("output", key, "ulasan_sentimen.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error load detail {key}:", e)
        return {}

def ringkasan_gmaps():
    semua = load_google_maps()
    if not semua:
        return {}
    for t in semua:
        skor_rating  = (float(t.get("rating", 0)) / 5) * 100
        skor_positif = float(t.get("persen_positif", 0))
        t["skor_gabungan"] = round((skor_rating * 0.6) + (skor_positif * 0.4), 1)

    dari_kategori = {}
    for t in semua:
        kat = t.get("kategori", "Lainnya")
        dari_kategori.setdefault(kat, []).append(t)

    return {
        kat: sorted(lst, key=lambda x: x["skor_gabungan"], reverse=True)[:5]
        for kat, lst in dari_kategori.items()
    }

def load_ringkasan():
    df = load_data()
    if df.empty:
        return pd.DataFrame()
    df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")
    ringkasan = (
        df.groupby(df["tanggal"].dt.date)
        .agg(jumlah_tweet=("id","count"), rata_skor=("skor","mean"),
             total_like=("likes","sum"), total_reply=("replies","sum"),
             total_retweet=("retweets","sum"))
        .reset_index()
    )
    sentimen = (
        df.groupby([df["tanggal"].dt.date, "sentimen"])
        .size().unstack(fill_value=0).reset_index()
    )
    ringkasan = ringkasan.merge(sentimen, on="tanggal", how="left")
    ringkasan["rata_skor"] = ringkasan["rata_skor"].round(3)
    return ringkasan


# ── Routes ─────────────────────────────────────────
@app.route("/")
@login_required
def index():
    df    = load_data()
    df_ig = load_instagram()
    if df.empty:
        return render_template("index.html")
    total           = len(df)
    total_instagram = len(df_ig)
    sentimen        = df["sentimen"].value_counts().to_dict()
    topik           = df["topik"].value_counts().head(6).to_dict()
    rata_skor       = round(df["skor"].mean(), 3)
    tweet_viral     = (
        df.nlargest(5, "likes")[["username","teks_asli","sentimen","skor","likes","tanggal"]]
        .to_dict("records")
    )
    if not df_ig.empty:
        total_like    = int(df_ig["likes"].sum())
        total_comment = int(df_ig["comments"].sum())
        rata_like     = round(df_ig["likes"].mean(), 1)
        post_terbaru  = df_ig.sort_values("tanggal", ascending=False).head(5).to_dict("records")
    else:
        total_like = total_comment = rata_like = 0
        post_terbaru = []
    update_terakhir = df["tanggal"].max().strftime("%d %B %Y")
    per_hari = df.groupby(["tanggal","sentimen"]).size().reset_index(name="jumlah")
    per_hari["tanggal"] = pd.to_datetime(per_hari["tanggal"]).dt.strftime("%Y-%m-%d")
    chart_data = per_hari.to_dict("records")
    return render_template(
        "index.html",
        total=total, sentimen=sentimen, topik=topik,
        tweet_viral=tweet_viral, chart_data=chart_data,
        update_terakhir=update_terakhir, kosong=False,
        total_instagram=total_instagram, total_like=total_like,
        total_comment=total_comment, rata_like=rata_like,
        rata_skor=rata_skor, post_terbaru=post_terbaru,
        ringkasan_tw=ringkasan_twitter(),
        ringkasan_ig=ringkasan_instagram(),
        ringkasan_gmaps=ringkasan_gmaps(),
    )

@app.route("/tweets")
@login_required
def twitter():
    df = load_data()
    if df.empty:
        return render_template("tweets.html", data=[], total=0,
                               sentimen={}, topik={}, tweet_viral=[],
                               chart_data=[], rata_skor=0, ringkasan=[])

    # Ringkasan per hari
    ringkasan = (
        df.groupby(df["tanggal"].dt.date)
        .agg(jumlah_tweet=("id","count"), rata_skor=("skor","mean"),
             total_like=("likes","sum"), total_reply=("replies","sum"),
             total_retweet=("retweets","sum"))
        .reset_index()
    )
    sentimen_pivot = (
        df.groupby([df["tanggal"].dt.date,"sentimen"])
        .size().unstack(fill_value=0).reset_index()
    )
    ringkasan = ringkasan.merge(sentimen_pivot, on="tanggal", how="left")
    ringkasan["rata_skor"] = ringkasan["rata_skor"].round(3)

    total     = len(df)
    df_valid  = df[df["sentimen"].isin(["positif","netral","negatif"])]
    sentimen  = df_valid["sentimen"].value_counts().to_dict()
    topik     = df["topik"].value_counts().head(10).to_dict()
    rata_skor = round(df["skor"].mean(), 3)
    tweet_viral = (
        df.nlargest(5, "likes")[["username","teks_asli","sentimen","likes","tanggal"]]
        .to_dict("records")
    )

    per_hari = df.groupby(["tanggal","sentimen"]).size().reset_index(name="jumlah")
    per_hari["tanggal"] = pd.to_datetime(per_hari["tanggal"]).dt.strftime("%Y-%m-%d")
    chart_data = per_hari.to_dict("records")

    # ✅ Konversi tanggal ke string agar JSON-safe (hindari NaT error)
    df_export = df.copy()
    df_export["tanggal"] = df_export["tanggal"].apply(
        lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(x) else ""
    )
    # Bersihkan kolom numerik dari NaN
    for col in ["likes", "retweets", "replies", "skor"]:
        if col in df_export.columns:
            df_export[col] = df_export[col].fillna(0)
    # Bersihkan kolom string dari NaN
    for col in ["teks_asli", "username", "sentimen", "topik"]:
        if col in df_export.columns:
            df_export[col] = df_export[col].fillna("").astype(str)

    data = df_export.sort_values("tanggal", ascending=False).to_dict("records")

    return render_template(
        "tweets.html",
        total=total, sentimen=sentimen, topik=topik,
        tweet_viral=tweet_viral, chart_data=chart_data,
        data=data, rata_skor=rata_skor,
        ringkasan=ringkasan.to_dict("records"),
    )

@app.route("/instagram")
@login_required
def instagram():
    df_post     = load_instagram()
    df_sentimen = load_instagram_sentimen()
    ringkasan   = load_ringkasan()
    skor_post = (
        df_sentimen.groupby("shortcode")
        .agg(skor=("skor","mean"),
             sentimen=("sentimen", lambda x: x.value_counts().idxmax()))
        .reset_index()
    )
    df_post = df_post.merge(skor_post, on="shortcode", how="left")
    df_post["skor"]     = df_post["skor"].fillna(0).round(3)
    df_post["sentimen"] = df_post["sentimen"].fillna("netral")
    if df_post.empty:
        return render_template("instagram.html", data=[], total=0,
                               total_like=0, total_comment=0, rata_like=0,
                               sentimen={}, topik={}, keyword={})
    total         = len(df_post)
    likes_bersih  = df_post["likes"].apply(parse_likes)
    total_like    = int(likes_bersih.sum())
    total_comment = int(df_post["comments"].sum())
    rata_like     = round(likes_bersih.mean(), 1) if total > 0 else 0
    last_update   = df_post["tanggal"].max().strftime("%d %B %Y")
    sentimen      = df_sentimen["sentimen"].value_counts().to_dict()
    rata_skor     = round(df_sentimen["skor"].mean(), 3)
    topik         = df_sentimen["topik"].value_counts().head(10).to_dict()
    keyword       = df_sentimen["keyword"].value_counts().to_dict()
    data          = df_post.sort_values("tanggal", ascending=False).to_dict("records")
    return render_template(
        "instagram.html",
        data=data, total=total, total_like=total_like,
        total_comment=total_comment, rata_like=rata_like,
        sentimen=sentimen, topik=topik, keyword=keyword,
        last_update=last_update, rata_skor=rata_skor,
        ringkasan=ringkasan.to_dict("records"),
    )


@app.route("/googlemaps")
@login_required
def googlemaps():
    semua = load_google_maps()

    # Kumpulkan kategori unik
    kategori_list = sorted(set(t["kategori"] for t in semua if t["kategori"]))

    # Buat mapping kategori → daftar sub-kategori unik
    sub_kategori_map = {}
    for t in semua:
        kat = t["kategori"]
        sub = t["sub_kategori"]
        if kat not in sub_kategori_map:
            sub_kategori_map[kat] = set()
        sub_kategori_map[kat].add(sub)
    sub_kategori_map = {k: sorted(v) for k, v in sub_kategori_map.items()}

    print(f"Total tempat: {len(semua)}")
    return render_template(
        "googlemaps.html",
        tempat=semua,
        kategori_list=kategori_list,
        sub_kategori_map=sub_kategori_map,
    )


@app.route("/api/googlemaps/sub-kategori")
@login_required
def api_sub_kategori():
    """API untuk ambil sub-kategori berdasarkan kategori yang dipilih."""
    kat    = request.args.get("kategori", "")
    semua  = load_google_maps()
    result = sorted(set(
        t["sub_kategori"] for t in semua
        if (not kat or t["kategori"] == kat) and t["sub_kategori"]
    ))
    return jsonify(result)


@app.route("/googlemaps/<key>")
def googlemaps_detail(key):
    data = load_detail_tempat(key)
    if not data:
        return "Tempat tidak ditemukan", 404
    return render_template("googlemaps_detail.html", data=data, key=key)


@app.route("/api/googlemaps/<key>")
def api_googlemaps_detail(key):
    data = load_detail_tempat(key)
    if not data:
        return jsonify({"error": "tidak ditemukan"}), 404
    return jsonify(data)



@app.route("/api/data")
def api_data():

    df = load_data()

    if df.empty:
        return jsonify([])
    return jsonify(df.tail(100).to_dict("records"))


@app.route("/api/instagram")
def api_instagram():

    df = load_instagram()

    if df.empty:
        return jsonify([])
    return jsonify(df.to_dict("records"))


@app.route("/api/scrape-status")
@login_required
def scrape_status():
    def cek_file(path):
        if not os.path.exists(path):
            return {"success": False, "message": "File tidak ditemukan", "last_run": "-", "total": 0}
        
        mtime    = os.path.getmtime(path)
        last_run = pd.Timestamp(mtime, unit="s").strftime("%d %b %Y %H:%M")
        total    = 0
        try:
            if path.endswith(".csv"):
                total = len(pd.read_csv(path))
            elif path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                total = len(data) if isinstance(data, list) else 1
        except Exception:
            pass
        return {"success": True, "last_run": last_run, "total": total}
    
    return jsonify({
        "twitter"  : cek_file("output/gresik_sentimen.csv"),
        "instagram": cek_file("output/gresik_ig_sentimen.csv"),
        "gmaps"    : cek_file("output/semua_tempat_summary.json"),
    })

# ── Models ─────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(50), unique=True, nullable=False)
    email      = db.Column(db.String(100), unique=True, nullable=False)
    password   = db.Column(db.String(255), nullable=False)
    role       = db.Column(db.String(20), default="user")
    foto       = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


@login_manager.user_loader
def load_user(user_id):
    if not user_id:
        return None
    try:
        return User.query.get(int(user_id))
    except (ValueError, TypeError):
        return None


class ActivityLog(db.Model):
    __tablename__ = "activity_log"
    id         = db.Column(db.Integer, primary_key=True)
    platform   = db.Column(db.String(30), nullable=False)
    aktivitas  = db.Column(db.String(50), nullable=False)
    status     = db.Column(db.String(20), nullable=False)
    keterangan = db.Column(db.String(255), nullable=True)
    waktu      = db.Column(db.DateTime, server_default=db.func.now())

# ── Auth ────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")
        user     = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(request.args.get("next") or url_for("index"))
        flash("Email atau password salah.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Berhasil logout.", "success")
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email    = request.form.get("email")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            flash("Email sudah terdaftar.", "danger")
            return redirect(url_for("register"))
        
        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        db.session.add(User(username=username, email=email, password=hashed_pw))
        db.session.commit()
        flash("Akun berhasil dibuat, silakan login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

from flask import session

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user  = User.query.filter_by(email=email).first()
        if user:
            session['reset_email'] = email
            flash("Email ditemukan. Silakan reset kata sandi.", "success")
            return redirect(url_for('reset_password'))
        flash("Email tidak terdaftar.", "danger")
    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if 'reset_email' not in session:
        flash("Sesi tidak valid. Ulangi proses lupa kata sandi.", "danger")
        return redirect(url_for('forgot_password'))
    if request.method == "POST":
        password_baru = request.form.get("password")
        konfirmasi    = request.form.get("konfirmasi")
        if password_baru != konfirmasi:
            flash("Kata sandi tidak cocok.", "danger")
            return redirect(url_for('reset_password'))
        user = User.query.filter_by(email=session.get('reset_email')).first()
        if user:
            user.password = bcrypt.generate_password_hash(password_baru).decode('utf-8')
            db.session.commit()
            session.pop('reset_email', None)
            flash("Kata sandi berhasil diubah. Silakan login.", "success")
            return redirect(url_for('login'))
        flash("Terjadi kesalahan.", "danger")
    return render_template("reset_password.html")


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        aksi = request.form.get("aksi")


        if aksi == "update_profile":
            username_baru = request.form.get("username", "").strip()
            email_baru    = request.form.get("email", "").strip()

            if not username_baru or not email_baru:
                flash("Nama pengguna dan email tidak boleh kosong.", "danger")
                return redirect(url_for("profile"))
            if User.query.filter(User.username == username_baru, User.id != current_user.id).first():
                flash("Nama pengguna sudah digunakan.", "danger")
                return redirect(url_for("profile"))
            if User.query.filter(User.email == email_baru, User.id != current_user.id).first():
                flash("Email sudah digunakan.", "danger")
                return redirect(url_for("profile"))
            
            current_user.username = username_baru
            current_user.email    = email_baru
            db.session.commit()
            flash("Profil berhasil diperbarui.", "success")
            return redirect(url_for("profile"))
        
        elif aksi == "upload_foto":
            file = request.files.get("foto")

            if not file or file.filename == "":
                flash("Tidak ada file yang dipilih.", "danger")
                return redirect(url_for("profile"))
            
            if not ekstensi_valid(file.filename):
                flash("Format file tidak didukung. Gunakan PNG, JPG, atau WEBP.", "danger")
                return redirect(url_for("profile"))
            
            from werkzeug.utils import secure_filename
            ext       = file.filename.rsplit(".", 1)[1].lower()
            nama_file = f"user_{current_user.id}.{ext}"

            if current_user.foto:

                path_lama = os.path.join(UPLOAD_FOLDER_FOTO, current_user.foto)
                if os.path.exists(path_lama) and current_user.foto != nama_file:
                    os.remove(path_lama)
            file.save(os.path.join(UPLOAD_FOLDER_FOTO, nama_file))
            current_user.foto = nama_file
            db.session.commit()
            flash("Foto profil berhasil diperbarui.", "success")
            return redirect(url_for("profile"))
        
        elif aksi == "hapus_foto":
            if current_user.foto:
                path_foto = os.path.join(UPLOAD_FOLDER_FOTO, current_user.foto)
                if os.path.exists(path_foto):
                    os.remove(path_foto)
                current_user.foto = None
                db.session.commit()
                flash("Foto profil berhasil dihapus.", "success")
            else:
                flash("Belum ada foto profil untuk dihapus.", "danger")
            return redirect(url_for("profile"))
        
        elif aksi == "ganti_password":
            password_lama   = request.form.get("password_lama", "")
            password_baru   = request.form.get("password_baru", "")
            konfirmasi_baru = request.form.get("konfirmasi_baru", "")

            if not bcrypt.check_password_hash(current_user.password, password_lama):
                flash("Kata sandi lama salah.", "danger")
                return redirect(url_for("profile"))
            
            if password_baru != konfirmasi_baru:
                flash("Konfirmasi kata sandi baru tidak cocok.", "danger")
                return redirect(url_for("profile"))
            
            if len(password_baru) < 8:
                flash("Kata sandi baru minimal 8 karakter.", "danger")
                return redirect(url_for("profile"))
            
            current_user.password = bcrypt.generate_password_hash(password_baru).decode("utf-8")
            db.session.commit()
            flash("Kata sandi berhasil diubah.", "success")
            return redirect(url_for("profile"))
        
    return render_template("profile.html")


@app.route("/settings/token/<platform>", methods=["POST"])
@login_required
def settings_token(platform):
    env_path = os.path.join(os.path.dirname(__file__), '.env')

    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

    def update_env(lines, key, value):

        for i, line in enumerate(lines):
            if line.startswith(key + '='):
                lines[i] = f"{key}={value}\n"
                return lines
        lines.append(f"{key}={value}\n")
        return lines
    MAPPING = {
        'twitter'  : {'AUTH_TOKEN':'auth_token','CT0':'ct0','AUTH_TOKEN_2':'auth_token_2','CT0_2':'ct0_2'},
        'instagram': {'IG_SESSIONID':'ig_sessionid','IG_CSRFTOKEN':'ig_csrftoken',
                      'IG_DS_USER_ID':'ig_ds_user_id','IG_MID':'ig_mid','IG_DID':'ig_did','IG_RUR':'ig_rur'},
        'gmaps'    : {'APIFY_API_TOKEN_1':'apify_token_1','APIFY_API_TOKEN_2':'apify_token_2',
                      'APIFY_API_TOKEN_3':'apify_token_3'},
    }
    for env_key, form_key in MAPPING.get(platform, {}).items():
        val = request.form.get(form_key, '')
        if val:
            lines = update_env(lines, env_key, val)
    with open(env_path, 'w') as f:
        f.writelines(lines)



    flash(f"Token {platform} berhasil disimpan.", "success")
    return redirect(request.referrer or url_for('index'))

# ── Facebook ────────────────────────────────────────
def load_facebook():

    if not os.path.exists(FACEBOOK_SENTIMEN):
        return pd.DataFrame()
    try:
        df = pd.read_csv(FACEBOOK_SENTIMEN, encoding="utf-8-sig").fillna("")
        for kolom in ["sumber","tanggal_ambil","tanggal_analisis","kategori",
                      "sentimen_final","sentimen_bert","skor_bert",
                      "sentimen_kw","skor_kw","konflik_label","urgensi","teks","url"]:
            if kolom not in df.columns:
                df[kolom] = ""
        df["skor_bert"]     = pd.to_numeric(df["skor_bert"], errors="coerce").fillna(0)
        df["skor_kw"]       = pd.to_numeric(df["skor_kw"],   errors="coerce").fillna(0)
        df["tanggal_ambil"] = pd.to_datetime(df["tanggal_ambil"], errors="coerce")

        return df
    except Exception as e:
        print("Error membaca data Facebook:", e)
        return pd.DataFrame()


@app.route("/facebook")
@login_required
def facebook():
    df = load_facebook()

    if df.empty:
        return render_template("facebook.html", data=[], total=0, sentimen={},
                               kategori={}, urgensi={}, sumber={}, rata_skor=0,
                               update_terakhir="-", urgensi_tinggi=[], chart_data=[])
    total    = len(df)
    rata_skor= round(df["skor_bert"].mean(), 3)
    sentimen = df["sentimen_final"].value_counts().to_dict()
    persen_negatif        = round(sentimen.get("negatif",0)/total*100, 1)
    persen_positif        = round(sentimen.get("positif",0)/total*100, 1)
    avg_confidence        = round(df["skor_bert"].mean()*100, 1)
    konflik_label         = df["konflik_label"].astype(str).str.lower().isin(["true","1","ya"]).sum()
    jumlah_urgensi_tinggi = df["urgensi"].str.lower().eq("tinggi").sum()
    kategori  = df["kategori"].value_counts().to_dict()
    urgensi   = df["urgensi"].value_counts().to_dict()
    sumber    = df["sumber"].value_counts().to_dict()
    update_terakhir = df["tanggal_ambil"].max().strftime("%d %B %Y") if df["tanggal_ambil"].notna().any() else "-"
    urgensi_tinggi  = df[df["urgensi"]=="tinggi"].sort_values("skor_bert",ascending=False).head(10).to_dict("records")
    chart_data      = df.groupby(["sumber","sentimen_final"]).size().reset_index(name="jumlah").to_dict("records")
    data            = df.sort_values("tanggal_ambil", ascending=False).to_dict("records")
    return render_template("facebook.html",
        data=data, total=total, sentimen=sentimen, kategori=kategori,
        urgensi=urgensi, sumber=sumber, rata_skor=rata_skor,
        update_terakhir=update_terakhir, urgensi_tinggi=urgensi_tinggi,
        chart_data=chart_data, persen_negatif=persen_negatif,
        persen_positif=persen_positif, avg_confidence=avg_confidence,
        konflik_label=konflik_label, jumlah_urgensi_tinggi=jumlah_urgensi_tinggi)

@app.route("/api/facebook")
@login_required
def api_facebook():
    df = load_facebook()
    if df.empty:
        return jsonify([])
    return jsonify(df.tail(100).to_dict("records"))

@app.route("/activity_log")
@login_required
def activity_log():
    cek_semua_platform()
    filter_platform = request.args.get("platform", "")
    filter_status   = request.args.get("status", "")
    filter_q        = request.args.get("q", "")
    page            = request.args.get("page", 1, type=int)
    per_page        = 20
    query = ActivityLog.query
    if filter_platform: query = query.filter_by(platform=filter_platform)
    if filter_status:   query = query.filter_by(status=filter_status)
    if filter_q:        query = query.filter(ActivityLog.keterangan.ilike(f"%{filter_q}%"))
    query      = query.order_by(ActivityLog.waktu.desc())
    total_log  = query.count()
    logs       = query.offset((page-1)*per_page).limit(per_page).all()
    total_sukses   = ActivityLog.query.filter_by(status="sukses").count()
    total_gagal    = ActivityLog.query.filter_by(status="gagal").count()
    total_berjalan = ActivityLog.query.filter_by(status="berjalan").count()
    total_pages    = (total_log + per_page - 1) // per_page
    log_terakhir   = logs[0].waktu.strftime("%d %B %Y %H:%M") if logs else "-"
    return render_template("activity_log.html",
        logs=logs, total_sukses=total_sukses, total_gagal=total_gagal,
        total_berjalan=total_berjalan, total_log=total_log,
        filter_platform=filter_platform, filter_status=filter_status,
        filter_q=filter_q, current_page=page, total_pages=total_pages,
        log_terakhir=log_terakhir)


# ══════════════════════════════════════════════════════════════
#  load berita
# ══════════════════════════════════════════════════════════════
def load_berita() -> pd.DataFrame:
    if not os.path.exists(BERITA_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(BERITA_CSV, encoding="utf-8-sig").fillna("")
        for kolom in ["judul","tanggal","topik","sumber","tipe","ringkasan","url","waktu_scrape"]:
            if kolom not in df.columns:
                df[kolom] = ""
        return df
    except Exception as e:
        print("Error membaca berita:", e)
        return pd.DataFrame()


def load_topik_berita() -> pd.DataFrame:
    if not os.path.exists(TOPIK_CSV):
        return pd.DataFrame()
    try:
        return pd.read_csv(TOPIK_CSV, encoding="utf-8-sig").fillna("")
    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# ROUTES — BERITA
# ══════════════════════════════════════════════════════════════
@app.route("/berita")
@login_required
def berita():
    df       = load_berita()
    df_topik = load_topik_berita()

    update_berita   = "-"
    total           = 0
    topik_dist      = {}
    sumber_dist     = {}
    tipe_dist       = {}
    chart_topik     = []
    chart_sumber    = []
    data_rows       = []
    topik_rows      = []

    if not df.empty:
        total         = len(df)
        update_berita = df["waktu_scrape"].iloc[-1] if "waktu_scrape" in df.columns else "-"
        topik_dist    = df["topik"].value_counts().head(10).to_dict()
        sumber_dist   = df["sumber"].value_counts().head(10).to_dict()
        tipe_dist     = df["tipe"].value_counts().to_dict()

        # Chart topik
        chart_topik = [
            {"topik": k, "jumlah": v}
            for k, v in df["topik"].value_counts().head(8).items()
        ]

        # Chart sumber (top 8)
        chart_sumber = [
            {"sumber": k, "jumlah": v}
            for k, v in df["sumber"].value_counts().head(8).items()
        ]

        # Tabel berita (maks 200)
        for _, row in df.head(200).iterrows():
            data_rows.append({
                "judul"    : row.get("judul",    "-"),
                "tanggal"  : row.get("tanggal",  "-"),
                "topik"    : row.get("topik",    "Umum"),
                "sumber"   : row.get("sumber",   "-"),
                "tipe"     : row.get("tipe",     "-"),
                "ringkasan": row.get("ringkasan","")[:150],
                "url"      : row.get("url",      "#"),
            })

    if not df_topik.empty:
        for _, row in df_topik.iterrows():
            topik_rows.append({
                "topik"        : row.get("topik",         "-"),
                "jumlah_berita": int(row.get("jumlah_berita", 0)),
                "sumber_berita": row.get("sumber_berita", "-"),
                "contoh_judul" : row.get("contoh_judul",  "-"),
            })

    return render_template(
        "berita.html",
        update_berita = update_berita,
        total         = total,
        topik_dist    = topik_dist,
        sumber_dist   = sumber_dist,
        tipe_dist     = tipe_dist,
        chart_topik   = chart_topik,
        chart_sumber  = chart_sumber,
        data          = data_rows,
        topik_rows    = topik_rows,
    )


@app.route("/api/berita")
@login_required
def api_berita():
    df = load_berita()
    if df.empty:
        return jsonify([])
    return jsonify(df.head(100).to_dict("records"))

# ══════════════════════════════════════════════════════════════
# PENGATURAN BERITA — CRUD Keyword & Topik
# ══════════════════════════════════════════════════════════════

@app.route("/berita/pengaturan")
@login_required
def berita_pengaturan():
    conn, cur = get_db()
    cur.execute("SELECT * FROM berita_keywords ORDER BY aktif DESC, keyword ASC")
    keywords = cur.fetchall()
    cur.execute("""
        SELECT topik, GROUP_CONCAT(kata_kunci, ', ') as kata_list,
               COUNT(*) as jumlah
        FROM berita_topik_rules
        GROUP BY topik ORDER BY topik
    """)
    topik_grouped = cur.fetchall()
    cur.execute("SELECT DISTINCT topik FROM berita_topik_rules ORDER BY topik")
    topik_list = [r["topik"] for r in cur.fetchall()]
    conn.close()
    return render_template("berita_pengaturan.html",
                           keywords=keywords,
                           topik_grouped=topik_grouped,
                           topik_list=topik_list)


# ── Keyword CRUD ───────────────────────────────────────────────

@app.route("/berita/keyword/tambah", methods=["POST"])
@login_required
def berita_keyword_tambah():
    keyword = request.form.get("keyword", "").strip().lower()
    if keyword:
        conn, cur = get_db()
        try:
            cur.execute("INSERT OR IGNORE INTO berita_keywords (keyword) VALUES (?)", (keyword,))
            conn.commit()
            flash(f"Keyword '{keyword}' berhasil ditambahkan.", "success")
        except Exception as e:
            flash(f"Gagal menambahkan: {e}", "danger")
        finally:
            conn.close()
    return redirect(url_for("berita_pengaturan"))


@app.route("/berita/keyword/hapus/<int:kid>", methods=["POST"])
@login_required
def berita_keyword_hapus(kid):
    conn, cur = get_db()
    cur.execute("SELECT keyword FROM berita_keywords WHERE id=?", (kid,))
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM berita_keywords WHERE id=?", (kid,))
        conn.commit()
        flash(f"Keyword '{row['keyword']}' dihapus.", "success")
    conn.close()
    return redirect(url_for("berita_pengaturan"))


@app.route("/berita/keyword/toggle/<int:kid>", methods=["POST"])
@login_required
def berita_keyword_toggle(kid):
    conn, cur = get_db()
    cur.execute("UPDATE berita_keywords SET aktif = CASE WHEN aktif=1 THEN 0 ELSE 1 END WHERE id=?", (kid,))
    conn.commit()
    conn.close()
    return redirect(url_for("berita_pengaturan"))


# ── Export keyword ke JSON (dibaca Berita.py) ──────────────────

@app.route("/api/berita/keywords")
def api_berita_keywords():
    """Endpoint publik — dibaca Berita.py saat scraping."""
    conn, cur = get_db()
    cur.execute("SELECT keyword FROM berita_keywords WHERE aktif=1 ORDER BY keyword")
    rows = cur.fetchall()
    conn.close()
    return jsonify([r["keyword"] for r in rows])


@app.route("/api/berita/topik-rules")
def api_berita_topik_rules():
    """Endpoint publik — dibaca Berita.py untuk kategorisasi."""
    conn, cur = get_db()
    cur.execute("SELECT topik, kata_kunci FROM berita_topik_rules ORDER BY topik")
    rows = cur.fetchall()
    conn.close()
    # Format: { "Ekonomi & UMKM": ["umkm","bisnis",...], ... }
    result = {}
    for r in rows:
        result.setdefault(r["topik"], []).append(r["kata_kunci"])
    return jsonify(result)


# ── Topik Rule CRUD ────────────────────────────────────────────

@app.route("/berita/topik/tambah", methods=["POST"])
@login_required
def berita_topik_tambah():
    topik     = request.form.get("topik", "").strip()
    topik_baru= request.form.get("topik_baru", "").strip()
    kata      = request.form.get("kata_kunci", "").strip().lower()
    nama_topik= topik_baru if topik_baru else topik
    if nama_topik and kata:
        conn, cur = get_db()
        try:
            cur.execute("INSERT OR IGNORE INTO berita_topik_rules (topik, kata_kunci) VALUES (?,?)",
                        (nama_topik, kata))
            conn.commit()
            flash(f"Kata kunci '{kata}' ditambahkan ke topik '{nama_topik}'.", "success")
        except Exception as e:
            flash(f"Gagal: {e}", "danger")
        finally:
            conn.close()
    return redirect(url_for("berita_pengaturan"))


@app.route("/berita/topik/hapus-kata", methods=["POST"])
@login_required
def berita_topik_hapus_kata():
    topik = request.form.get("topik", "")
    kata  = request.form.get("kata_kunci", "")
    conn, cur = get_db()
    cur.execute("DELETE FROM berita_topik_rules WHERE topik=? AND kata_kunci=?", (topik, kata))
    conn.commit()
    conn.close()
    flash(f"Kata kunci '{kata}' dihapus dari '{topik}'.", "success")
    return redirect(url_for("berita_pengaturan"))


@app.route("/berita/topik/hapus-semua", methods=["POST"])
@login_required
def berita_topik_hapus_semua():
    topik = request.form.get("topik", "")
    conn, cur = get_db()
    cur.execute("DELETE FROM berita_topik_rules WHERE topik=?", (topik,))
    conn.commit()
    conn.close()
    flash(f"Topik '{topik}' dan semua kata kuncinya dihapus.", "success")
    return redirect(url_for("berita_pengaturan"))

<<<<<<< HEAD
# ══════════════════════════════════════════════════════════════
# SHOPEE — Path file output scraper
# ══════════════════════════════════════════════════════════════
SHOPEE_CSV       = "output/toko_gresik_shopee.csv"
SHOPEE_TOKO_CSV  = "output/toko_gresik_shopee_per_toko.csv"


# ══════════════════════════════════════════════════════════════
# LOAD DATA SHOPEE
# ══════════════════════════════════════════════════════════════
def load_shopee() -> pd.DataFrame:
    """Muat data produk Shopee dari CSV hasil scraping."""
    if not os.path.exists(SHOPEE_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(SHOPEE_CSV, encoding="utf-8-sig").fillna("")
        for kolom in [
            "keyword_cari", "kategori", "nama_produk",
            "harga", "harga_coret", "diskon", "rating",
            "terjual", "lokasi_seller", "nama_toko",
            "platform", "waktu_scrape",
        ]:
            if kolom not in df.columns:
                df[kolom] = ""
        # Bersihkan harga jadi angka untuk sorting
        df["harga_num"] = (
            df["harga"]
            .str.replace(r"[Rp\.,\s]", "", regex=True)
            .pipe(pd.to_numeric, errors="coerce")
            .fillna(0)
        )
        df["rating_num"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0)
        df["waktu_scrape"] = pd.to_datetime(df["waktu_scrape"], errors="coerce")
        return df
    except Exception as e:
        print("Error membaca data Shopee:", e)
        return pd.DataFrame()


def load_shopee_toko() -> pd.DataFrame:
    """Muat ringkasan per toko dari CSV _per_toko."""
    if not os.path.exists(SHOPEE_TOKO_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(SHOPEE_TOKO_CSV, encoding="utf-8-sig").fillna("")
        for kolom in [
            "nama_toko", "lokasi_seller", "kategori",
            "jumlah_produk", "keyword_list", "daftar_produk",
        ]:
            if kolom not in df.columns:
                df[kolom] = ""
        df["jumlah_produk"] = pd.to_numeric(df["jumlah_produk"], errors="coerce").fillna(0).astype(int)
        return df
    except Exception as e:
        print("Error membaca data toko Shopee:", e)
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# ROUTE — /shopee
# ══════════════════════════════════════════════════════════════
@app.route("/shopee")
@login_required
def shopee():
    df      = load_shopee()
    df_toko = load_shopee_toko()

    # ── Default kosong ──────────────────────────────────────
    total          = 0
    total_toko     = 0
    total_area     = 0
    total_keyword  = 0
    update_terakhir = "-"
    kategori_dist  = {}
    lokasi_dist    = {}
    keyword_dist   = {}
    top_toko       = []
    produk_rows    = []
    toko_rows      = []
    chart_kategori = []
    chart_lokasi   = []

    if not df.empty:
        total           = len(df)
        total_toko      = df["nama_toko"].nunique()
        total_area      = df["lokasi_seller"].nunique()
        total_keyword   = df["keyword_cari"].nunique()
        update_terakhir = (
            df["waktu_scrape"].max().strftime("%d %B %Y %H:%M")
            if df["waktu_scrape"].notna().any() else "-"
        )

        kategori_dist = df["kategori"].value_counts().head(10).to_dict()
        lokasi_dist   = df["lokasi_seller"].value_counts().head(10).to_dict()
        keyword_dist  = df["keyword_cari"].value_counts().to_dict()

        # Chart
        chart_kategori = [
            {"label": k, "value": v}
            for k, v in df["kategori"].value_counts().head(8).items()
        ]
        chart_lokasi = [
            {"label": k, "value": v}
            for k, v in df["lokasi_seller"].value_counts().head(8).items()
        ]

        # Top toko berdasarkan jumlah produk di CSV produk
        top_toko_series = df["nama_toko"].value_counts().head(10)
        top_toko = [
            {"nama_toko": nm, "jumlah": cnt}
            for nm, cnt in top_toko_series.items()
        ]

        # Tabel produk (maks 300, terbaru dulu)
        df_sort = df.sort_values("waktu_scrape", ascending=False).head(300)
        for _, r in df_sort.iterrows():
            produk_rows.append({
                "nama_produk"   : r.get("nama_produk", "-"),
                "nama_toko"     : r.get("nama_toko", "-"),
                "harga"         : r.get("harga", "-"),
                "harga_coret"   : r.get("harga_coret", "-"),
                "diskon"        : r.get("diskon", "-"),
                "rating"        : r.get("rating", "-"),
                "terjual"       : r.get("terjual", "-"),
                "lokasi_seller" : r.get("lokasi_seller", "-"),
                "kategori"      : r.get("kategori", "-"),
                "keyword_cari"  : r.get("keyword_cari", "-"),
                "waktu_scrape"  : (
                    r["waktu_scrape"].strftime("%d/%m/%Y %H:%M")
                    if pd.notna(r.get("waktu_scrape")) else "-"
                ),
            })

    if not df_toko.empty:
        df_toko_sort = df_toko.sort_values("jumlah_produk", ascending=False).head(100)
        for _, r in df_toko_sort.iterrows():
            toko_rows.append({
                "nama_toko"     : r.get("nama_toko", "-"),
                "lokasi_seller" : r.get("lokasi_seller", "-"),
                "kategori"      : r.get("kategori", "-"),
                "jumlah_produk" : int(r.get("jumlah_produk", 0)),
                "keyword_list"  : r.get("keyword_list", "-"),
                "daftar_produk" : r.get("daftar_produk", "-"),
            })

    return render_template(
        "Shopee.html",
        total           = total,
        total_toko      = total_toko,
        total_area      = total_area,
        total_keyword   = total_keyword,
        update_terakhir = update_terakhir,
        kategori_dist   = kategori_dist,
        lokasi_dist     = lokasi_dist,
        keyword_dist    = keyword_dist,
        top_toko        = top_toko,
        chart_kategori  = chart_kategori,
        chart_lokasi    = chart_lokasi,
        data            = produk_rows,
        toko_rows       = toko_rows,
    )


# ══════════════════════════════════════════════════════════════
# API — /api/shopee  (JSON mentah)
# ══════════════════════════════════════════════════════════════
@app.route("/api/shopee")
@login_required
def api_shopee():
    df = load_shopee()
    if df.empty:
        return jsonify([])
    # Hapus kolom internal sebelum dikirim
    df_out = df.drop(columns=["harga_num", "rating_num"], errors="ignore")
    df_out["waktu_scrape"] = df_out["waktu_scrape"].apply(
        lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else ""
    )
    return jsonify(df_out.head(200).to_dict("records"))


# ══════════════════════════════════════════════════════════════
# API — /api/shopee/toko  (ringkasan per toko)
# ══════════════════════════════════════════════════════════════
@app.route("/api/shopee/toko")
@login_required
def api_shopee_toko():
    df = load_shopee_toko()
    if df.empty:
        return jsonify([])
    return jsonify(df.head(100).to_dict("records"))
    
# ══════════════════════════════════════════════════════════════
# PATH FILE OUTPUT LAZADA
# ══════════════════════════════════════════════════════════════
LAZADA_CSV      = "output/toko_gresik_lazada.csv"
LAZADA_TOKO_CSV = "output/toko_gresik_lazada_ringkasan.csv"


# ══════════════════════════════════════════════════════════════
# LOAD DATA LAZADA
# ══════════════════════════════════════════════════════════════
def load_lazada() -> pd.DataFrame:
    """Muat data produk Lazada dari CSV hasil scraping."""
    if not os.path.exists(LAZADA_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(LAZADA_CSV, encoding="utf-8-sig").fillna("")
        for kolom in [
            "nama_produk", "harga", "lokasi_seller",
            "kategori", "nama_toko", "platform", "waktu_scrape",
        ]:
            if kolom not in df.columns:
                df[kolom] = ""
        df["waktu_scrape"] = pd.to_datetime(df["waktu_scrape"], errors="coerce")
        return df
    except Exception as e:
        print("Error membaca data Lazada:", e)
        return pd.DataFrame()


def load_lazada_ringkasan() -> pd.DataFrame:
    """Muat ringkasan per lokasi dari CSV _ringkasan."""
    if not os.path.exists(LAZADA_TOKO_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(LAZADA_TOKO_CSV, encoding="utf-8-sig").fillna("")
        for kolom in ["lokasi_seller", "jumlah_produk", "contoh_produk"]:
            if kolom not in df.columns:
                df[kolom] = ""
        df["jumlah_produk"] = pd.to_numeric(df["jumlah_produk"], errors="coerce").fillna(0).astype(int)
        return df
    except Exception as e:
        print("Error membaca ringkasan Lazada:", e)
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# ROUTE — /lazada
# ══════════════════════════════════════════════════════════════
@app.route("/lazada")
@login_required
def lazada():
    df          = load_lazada()
    df_ringkasan= load_lazada_ringkasan()

    # ── Default kosong ──────────────────────────────────────
    total           = 0
    total_toko      = 0
    total_area      = 0
    total_kategori  = 0
    update_terakhir = "-"
    kategori_dist   = {}
    lokasi_dist     = {}
    top_toko        = []
    produk_rows     = []
    chart_kategori  = []
    chart_lokasi    = []

    if not df.empty:
        total           = len(df)
        total_toko      = df["nama_toko"].replace("-", pd.NA).dropna().nunique()
        total_area      = df["lokasi_seller"].nunique()
        total_kategori  = df["kategori"].nunique()
        update_terakhir = (
            df["waktu_scrape"].max().strftime("%d %B %Y %H:%M")
            if df["waktu_scrape"].notna().any() else "-"
        )

        kategori_dist = df["kategori"].value_counts().head(10).to_dict()
        lokasi_dist   = df["lokasi_seller"].value_counts().head(10).to_dict()

        # Chart Kategori (top 8)
        chart_kategori = [
            {"label": k, "value": int(v)}
            for k, v in df["kategori"].value_counts().head(8).items()
        ]

        # Chart Lokasi (top 8)
        chart_lokasi = [
            {"label": k, "value": int(v)}
            for k, v in df["lokasi_seller"].value_counts().head(8).items()
        ]

        # Top toko berdasarkan jumlah produk
        top_toko_series = (
            df[df["nama_toko"] != "-"]["nama_toko"]
            .value_counts().head(10)
        )
        top_toko = []
        for nm, cnt in top_toko_series.items():
            lokasi = df[df["nama_toko"] == nm]["lokasi_seller"].mode()
            top_toko.append({
                "nama_toko"    : nm,
                "jumlah"       : int(cnt),
                "lokasi_seller": lokasi.iloc[0] if not lokasi.empty else "-",
            })

        # Tabel produk (maks 300, terbaru dulu)
        df_sort = df.sort_values("waktu_scrape", ascending=False).head(300)
        for _, r in df_sort.iterrows():
            produk_rows.append({
                "nama_produk"   : r.get("nama_produk", "-"),
                "nama_toko"     : r.get("nama_toko", "-"),
                "harga"         : r.get("harga", "-"),
                "kategori"      : r.get("kategori", "-"),
                "lokasi_seller" : r.get("lokasi_seller", "-"),
                "waktu_scrape"  : (
                    r["waktu_scrape"].strftime("%d/%m/%Y %H:%M")
                    if pd.notna(r.get("waktu_scrape")) else "-"
                ),
            })

    return render_template(
        "Lazada.html",
        total           = total,
        total_toko      = total_toko,
        total_area      = total_area,
        total_kategori  = total_kategori,
        update_terakhir = update_terakhir,
        kategori_dist   = kategori_dist,
        lokasi_dist     = lokasi_dist,
        top_toko        = top_toko,
        chart_kategori  = chart_kategori,
        chart_lokasi    = chart_lokasi,
        data            = produk_rows,
    )


# ══════════════════════════════════════════════════════════════
# API — /api/lazada  (JSON mentah)
# ══════════════════════════════════════════════════════════════
@app.route("/api/lazada")
@login_required
def api_lazada():
    df = load_lazada()
    if df.empty:
        return jsonify([])
    df_out = df.copy()
    df_out["waktu_scrape"] = df_out["waktu_scrape"].apply(
        lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else ""
    )
    return jsonify(df_out.head(200).to_dict("records"))

# ══════════════════════════════════════════════════════════════
# PATH FILE OUTPUT TOKOPEDIA
# ══════════════════════════════════════════════════════════════
TOKPED_CSV = "output/toko_gresik_tokopedia.csv"


# ══════════════════════════════════════════════════════════════
# LOAD DATA TOKOPEDIA
# ══════════════════════════════════════════════════════════════
def load_tokopedia() -> pd.DataFrame:
    """Muat data toko Tokopedia dari CSV hasil scraping."""
    if not os.path.exists(TOKPED_CSV):
        return pd.DataFrame()
    try:
        df = pd.read_csv(TOKPED_CSV, encoding="utf-8-sig").fillna("")
        for kolom in [
            "nama_toko", "lokasi", "url_toko",
            "produk_dijual", "kategori", "harga_produk",
            "platform", "waktu_scrape",
        ]:
            if kolom not in df.columns:
                df[kolom] = ""
        df["waktu_scrape"] = pd.to_datetime(df["waktu_scrape"], errors="coerce")
        return df
    except Exception as e:
        print("Error membaca data Tokopedia:", e)
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════
# ROUTE — /tokopedia
# ══════════════════════════════════════════════════════════════
@app.route("/tokopedia")
@login_required
def tokopedia():
    df = load_tokopedia()

    # ── Default kosong ──────────────────────────────────────
    total           = 0
    total_area      = 0
    total_kategori  = 0
    total_produk    = 0
    update_terakhir = "-"
    kategori_dist   = {}
    lokasi_dist     = {}
    top_toko        = []
    produk_rows     = []
    chart_kategori  = []
    chart_lokasi    = []

    if not df.empty:
        total          = len(df)
        total_area     = df["lokasi"].nunique()
        total_kategori = df["kategori"].nunique()
        # Hitung estimasi total produk dari kolom produk_dijual (separator "|")
        total_produk   = df["produk_dijual"].apply(
            lambda x: len([p for p in str(x).split("|") if p.strip()])
        ).sum()
        update_terakhir = (
            df["waktu_scrape"].max().strftime("%d %B %Y %H:%M")
            if df["waktu_scrape"].notna().any() else "-"
        )

        kategori_dist = df["kategori"].value_counts().head(10).to_dict()
        lokasi_dist   = df["lokasi"].value_counts().head(10).to_dict()

        # Chart Kategori (top 8)
        chart_kategori = [
            {"label": k, "value": int(v)}
            for k, v in df["kategori"].value_counts().head(8).items()
        ]

        # Chart Lokasi (top 8)
        chart_lokasi = [
            {"label": k, "value": int(v)}
            for k, v in df["lokasi"].value_counts().head(8).items()
        ]

        # Top toko: 10 toko terbaru
        top_toko = (
            df.sort_values("waktu_scrape", ascending=False)
            .head(10)[["nama_toko", "lokasi", "kategori", "url_toko"]]
            .to_dict("records")
        )

        # Tabel toko (maks 300, terbaru dulu)
        df_sort = df.sort_values("waktu_scrape", ascending=False).head(300)
        for _, r in df_sort.iterrows():
            produk_rows.append({
                "nama_toko"    : r.get("nama_toko", "-"),
                "lokasi"       : r.get("lokasi", "-"),
                "url_toko"     : r.get("url_toko", "-"),
                "kategori"     : r.get("kategori", "-"),
                "produk_dijual": r.get("produk_dijual", "-"),
                "harga_produk" : r.get("harga_produk", "-"),
                "waktu_scrape" : (
                    r["waktu_scrape"].strftime("%d/%m/%Y %H:%M")
                    if pd.notna(r.get("waktu_scrape")) else "-"
                ),
            })

    return render_template(
        "Tokopedia.html",
        total           = total,
        total_area      = total_area,
        total_kategori  = total_kategori,
        total_produk    = int(total_produk),
        update_terakhir = update_terakhir,
        kategori_dist   = kategori_dist,
        lokasi_dist     = lokasi_dist,
        top_toko        = top_toko,
        chart_kategori  = chart_kategori,
        chart_lokasi    = chart_lokasi,
        data            = produk_rows,
    )


# ══════════════════════════════════════════════════════════════
# API — /api/tokopedia  (JSON mentah)
# ══════════════════════════════════════════════════════════════
@app.route("/api/tokopedia")
@login_required
def api_tokopedia():
    df = load_tokopedia()
    if df.empty:
        return jsonify([])
    df_out = df.copy()
    df_out["waktu_scrape"] = df_out["waktu_scrape"].apply(
        lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else ""
    )
    return jsonify(df_out.head(200).to_dict("records"))
=======
>>>>>>> f564e03 (Update semua)

if __name__ == "__main__":
    app.run(debug=True, port=5000)