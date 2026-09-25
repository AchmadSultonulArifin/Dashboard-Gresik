"""
╔══════════════════════════════════════════════════════════╗
║   SCRAPER TOKO GRESIK DI LAZADA — VERSI PERBAIKAN v3    ║
║   Filter : Shipped From → Kab. Gresik                   ║
║   Mode   : Listing → PDP (paralel, headless)            ║
║   Output : toko_gresik_lazada.csv                       ║
║            dashboard_data_lazada.json                   ║
║   CRUD   : Manajemen kategori + riwayat perubahan       ║
╚══════════════════════════════════════════════════════════╝

PERBAIKAN v3:
  1. [BUG FIX] Nama produk tidak lagi diambil dari slug URL ("pdp")
     → Kini diambil dari title attribute, teks <a>, atau elemen dalam card
  2. [BUG FIX] Nama toko tidak lagi menangkap teks tombol ("Click to feedback >")
     → Ditambah BLACKLIST teks tombol Lazada
  3. [BUG FIX] Selector kartu produk diperluas dengan pola Lazada 2024-2025
  4. [BUG FIX] Fallback nama produk via JS closest() untuk cari parent card
  5. [TAMBAH]  Fungsi _ambil_nama_toko_dari_pdp() yang lebih defensif
  6. [TAMBAH]  KategoriManager: CRUD kategori + penyimpanan riwayat JSON
  7. [TAMBAH]  Argumen CLI untuk operasi CRUD tanpa masuk ke mode scraping
"""

import time, random, re, os, json, argparse
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, WebDriverException,
    ElementClickInterceptedException, StaleElementReferenceException,
)

# ══════════════════════════════════════════════════════
# PENGATURAN DASAR
# ══════════════════════════════════════════════════════
MAX_HALAMAN     = 15
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR      = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE     = os.path.join(OUTPUT_DIR, "toko_gresik_lazada.csv")
DASHBOARD_FILE  = os.path.join(OUTPUT_DIR, "dashboard_data_lazada.json")
CONFIG_FILE_DEF = os.path.join(BASE_DIR, "keywords_config.json")
RIWAYAT_FILE    = os.path.join(BASE_DIR, "riwayat_kategori.json")
CHROMEDRIVER    = os.path.join(BASE_DIR, "chromedriver.exe")
DEFAULT_WORKERS = 5

DEFAULT_KATA_GRESIK = [
    "kab. gresik", "gresik", "kabupaten gresik",
    "kebomas", "driyorejo", "manyar", "duduksampeyan",
    "bungah", "sidayu", "cerme", "benjeng",
    "balongpanggang", "panceng", "ujungpangkah",
    "sangkapura", "tambak",
]

DEFAULT_KATEGORI_MAPPING = {
    "Handphone & Aksesoris": ["hp ", "handphone", "casing hp", "hardcase", "softcase",
                               "tempered glass", "powerbank", "charger hp", "kabel data"],
    "Komputer & Aksesoris":  ["laptop", "komputer", "keyboard", "mouse", "ssd", "hardisk",
                               "flashdisk", "printer", "monitor"],
    "Elektronik":            ["kulkas", "tv", "televisi", "kipas angin", "ac split",
                               "rice cooker", "blender", "setrika", "speaker", "elektronik"],
    "Fashion Wanita":        ["baju wanita", "dress", "gamis", "blouse", "rok", "kebaya",
                               "tunik", "daster", "kemeja wanita"],
    "Fashion Pria":          ["baju pria", "kemeja pria", "kaos pria", "celana pria",
                               "kaos polo", "jaket pria"],
    "Fashion Muslim":        ["hijab", "jilbab", "mukena", "sarung", "peci", "gamis syar'i"],
    "Fashion Anak":          ["baju anak", "baju bayi", "setelan anak", "sepatu anak"],
    "Sepatu & Sandal":       ["sepatu", "sandal", "sneakers", "selop"],
    "Tas & Koper":           ["tas wanita", "tas pria", "tas ransel", "koper", "dompet"],
    "Kecantikan":            ["skincare", "kosmetik", "lipstik", "serum", "sunscreen",
                               "parfum", "make up", "masker wajah"],
    "Kesehatan":             ["vitamin", "obat", "masker medis", "suplemen", "alat kesehatan",
                               "hand sanitizer"],
    "Makanan & Minuman":     ["snack", "kue", "keripik", "kopi", "teh", "makanan ringan",
                               "kerupuk", "sambal", "bumbu", "frozen food", "minuman"],
    "Ibu & Bayi":            ["popok", "diapers", "susu formula", "perlengkapan bayi",
                               "baby", "mainan bayi"],
    "Rumah Tangga":          ["peralatan dapur", "panci", "wajan", "rak", "sapu",
                               "perabotan", "gelas", "piring", "toples"],
    "Otomotif":              ["oli", "spare part", "aksesoris motor", "aksesoris mobil",
                               "helm", "ban motor"],
    "Olahraga & Outdoor":    ["alat olahraga", "sepeda", "matras yoga", "raket",
                               "tenda", "perlengkapan camping"],
    "Hobi & Koleksi":        ["action figure", "mainan koleksi", "kartu", "hobi", "diecast"],
    "Buku & Alat Tulis":     ["buku", "alat tulis", "pulpen", "pensil", "note book"],
    "Perawatan Hewan":       ["pakan kucing", "pakan anjing", "kandang hewan", "pet shop"],
    "Souvenir & Perayaan":   ["souvenir", "kado", "hampers", "balon", "dekorasi ulang tahun"],
}

LAZADA_BADGE  = ["lazmall", "official store", "preferred seller", "lazada mall"]
SKIP_PATTERNS = ["rp", "rating", "terjual", "bintang", "gratis", "%",
                 "ongkir", "lihat", "tambah", "keranjang", "diskon",
                 "flash sale", "voucher", "koin", "cashback"]

# ── BLACKLIST teks yang BUKAN nama toko (penyebab bug "Click to feedback >") ──
TOKO_BLACKLIST = [
    "click to feedback", "feedback", "chat", "follow", "ikuti",
    "lihat toko", "view shop", "ke toko", "kunjungi toko",
    "lazada", "official store", "lazmall", "preferred",
    "tambah ke keranjang", "beli sekarang", "add to cart",
    "masuk lebih murah", "voucher", "diskon", "flash sale",
    "gratis ongkir", "cashback", "koin", "login", "daftar",
    "botanical essentials",
]

# ── SELECTOR KARTU PRODUK ────────────────────────────────────────────────────
CARD_SELECTORS = [
    "[data-item-id]",
    "[data-tracking='product-card']",
    "div[class*='Bm3ON']",
    "div[class*='buTCk']",
    "div[class*='c-prd']",
    "div[class*='product-card']",
    "div[class*='ProductCard']",
    "div[class*='gridItem']",
    "div[class*='product-item']",
    ".c-2prjwa",
    "li[class*='product']",
]

NAMA_PRODUK_SEL = [
    "[class*='product-title']",
    "[class*='title--wFj13']",
    "[class*='RFzeYU']",
    "[class*='info-title']",
    "[class*='titulo']",
    "div[class*='title'] span",
    "div[class*='name'] a",
    "a[class*='title']",
    "span[class*='title']",
    "h2", "h3",
]

HARGA_SEL = [
    "[class*='price--NVB62']",
    "[class*='price-sale']",
    "[class*='priceWrapper']",
    "span[class*='price']",
    "div[class*='price']",
    "[data-spm='dprice']",
    "[class*='currency']",
]

LOKASI_SEL = [
    "[class*='location']",
    "[class*='shipping']",
    "[class*='seller-location']",
    "span[class*='loc']",
    "[class*='sold-location']",
]

RATING_SEL = [
    "[class*='rating']",
    "[class*='stars']",
    "span[class*='score']",
    "[class*='review-count']",
]

TERJUAL_SEL = [
    "[class*='sold']",
    "span[class*='sold']",
    "[class*='sales']",
]

# ── SELECTOR PDP ──────────────────────────────────────────────────────────────
PDP_TOKO_SEL = [
    "[data-spm='dshopname'] a",
    "[data-spm='dshopname']",
    "a[href*='/shop/']",
    "a[href*='/seller/']",
    "[class*='sellerName'] a",
    "[class*='seller-name'] a",
    "[class*='shop-name'] a",
    "[class*='shopName'] a",
    "[class*='pdp-product-brand'] a",
    "[class*='StoreInfo'] a",
    "[class*='seller-info'] a",
    "[class*='sellerName']",
    "[class*='seller-name']",
    "[class*='shop-name']",
    "[class*='seller-info'] span",
]

PDP_RATING_TOKO_SEL = [
    "[class*='seller-brief-rating']",
    "[class*='shop-rating']",
    "[class*='score-content'] span",
    "[class*='seller-brief__items'] span",
]

PDP_RATING_PRODUK_SEL = [
    "[class*='pdp-review-summary'] [class*='score']",
    "[class*='review-rating'] [class*='score']",
    "span[class*='score-average']",
    "[class*='rating-average']",
]

PDP_TERJUAL_SEL = [
    "[class*='sold-count']",
    "span[class*='sold']",
    "[class*='pdp-product-sold']",
    "[class*='review-count']",
]

FAST_WAIT             = 0.5
EXPLICIT_WAIT_TIMEOUT = 5


# ══════════════════════════════════════════════════════
# CRUD KATEGORI + RIWAYAT PERUBAHAN
# ══════════════════════════════════════════════════════
class KategoriManager:
    """Mengelola CRUD kategori beserta riwayat setiap perubahan."""

    def __init__(self, kategori_mapping: dict, riwayat_path: str = RIWAYAT_FILE):
        self.kategori      = dict(kategori_mapping)
        self._riwayat_path = riwayat_path
        self._riwayat: list = self._muat_riwayat()

    # ── Riwayat internal ──────────────────────────────
    def _muat_riwayat(self) -> list:
        if os.path.exists(self._riwayat_path):
            try:
                with open(self._riwayat_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _simpan_riwayat(self) -> None:
        with open(self._riwayat_path, "w", encoding="utf-8") as f:
            json.dump(self._riwayat, f, ensure_ascii=False, indent=2)

    def _catat(self, aksi: str, nama: str, detail: dict = None) -> None:
        """Catat satu entri perubahan ke riwayat."""
        entri = {
            "waktu"  : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "aksi"   : aksi,    # TAMBAH | HAPUS | EDIT | TAMBAH_KW | HAPUS_KW
            "nama"   : nama,
            "detail" : detail or {},
        }
        self._riwayat.append(entri)
        self._simpan_riwayat()
        print(f"   📝 Riwayat: [{aksi}] {nama}")

    # ── CREATE ────────────────────────────────────────
    def tambah_kategori(self, nama: str, keywords: list) -> bool:
        """Tambah kategori baru beserta keyword-nya."""
        if nama in self.kategori:
            print(f"   ⚠  Kategori '{nama}' sudah ada.")
            return False
        kw = [k.lower().strip() for k in keywords if k.strip()]
        self.kategori[nama] = kw
        self._catat("TAMBAH", nama, {"keywords": kw})
        print(f"   ✅ Kategori '{nama}' ditambahkan dengan {len(kw)} keyword.")
        return True

    # ── READ ──────────────────────────────────────────
    def lihat_kategori(self, nama: str = None) -> None:
        """Tampilkan satu kategori atau semua kategori."""
        if nama:
            if nama not in self.kategori:
                print(f"   ❌ Kategori '{nama}' tidak ditemukan.")
                return
            kw = self.kategori[nama]
            print(f"\n  📂 {nama} ({len(kw)} keyword):")
            for k in kw:
                print(f"       • {k}")
        else:
            print(f"\n  📂 Daftar Kategori ({len(self.kategori)} total):")
            print(f"  {'No':<4} {'Nama Kategori':<35} {'Jml KW'}")
            print(f"  {'-'*55}")
            for i, (nm, kw) in enumerate(self.kategori.items(), 1):
                print(f"  {i:<4} {nm:<35} {len(kw)}")

    # ── UPDATE — ganti nama ───────────────────────────
    def edit_nama_kategori(self, nama_lama: str, nama_baru: str) -> bool:
        """Ganti nama kategori tanpa mengubah keyword-nya."""
        if nama_lama not in self.kategori:
            print(f"   ❌ Kategori '{nama_lama}' tidak ditemukan.")
            return False
        if nama_baru in self.kategori:
            print(f"   ⚠  Nama '{nama_baru}' sudah dipakai kategori lain.")
            return False
        self.kategori[nama_baru] = self.kategori.pop(nama_lama)
        self._catat("EDIT", nama_lama, {"nama_baru": nama_baru})
        print(f"   ✅ Nama kategori '{nama_lama}' → '{nama_baru}'.")
        return True

    # ── UPDATE — tambah keyword ───────────────────────
    def tambah_keyword(self, nama: str, keywords: list) -> bool:
        """Tambah keyword ke kategori yang sudah ada."""
        if nama not in self.kategori:
            print(f"   ❌ Kategori '{nama}' tidak ditemukan.")
            return False
        kw_baru = [
            k.lower().strip() for k in keywords
            if k.strip() and k.lower().strip() not in self.kategori[nama]
        ]
        self.kategori[nama].extend(kw_baru)
        self._catat("TAMBAH_KW", nama, {"keywords_baru": kw_baru})
        print(f"   ✅ {len(kw_baru)} keyword baru ditambahkan ke '{nama}'.")
        return True

    # ── UPDATE — hapus keyword ────────────────────────
    def hapus_keyword(self, nama: str, keywords: list) -> bool:
        """Hapus keyword tertentu dari sebuah kategori."""
        if nama not in self.kategori:
            print(f"   ❌ Kategori '{nama}' tidak ditemukan.")
            return False
        kw_dihapus = [
            k.lower().strip() for k in keywords
            if k.lower().strip() in self.kategori[nama]
        ]
        for k in kw_dihapus:
            self.kategori[nama].remove(k)
        self._catat("HAPUS_KW", nama, {"keywords_dihapus": kw_dihapus})
        print(f"   ✅ {len(kw_dihapus)} keyword dihapus dari '{nama}'.")
        return True

    # ── DELETE ────────────────────────────────────────
    def hapus_kategori(self, nama: str) -> bool:
        """Hapus seluruh kategori. Keyword disimpan di riwayat sebagai backup."""
        if nama not in self.kategori:
            print(f"   ❌ Kategori '{nama}' tidak ditemukan.")
            return False
        kw_backup = self.kategori.pop(nama)
        self._catat("HAPUS", nama, {"keywords_backup": kw_backup})
        print(f"   ✅ Kategori '{nama}' dihapus ({len(kw_backup)} keyword di-backup ke riwayat).")
        return True

    # ── Riwayat — tampilkan ───────────────────────────
    def tampilkan_riwayat(self, n: int = 30) -> None:
        """Tampilkan n entri riwayat terbaru."""
        if not self._riwayat:
            print("   ℹ️  Belum ada riwayat perubahan kategori.")
            return
        tampil = self._riwayat[-n:]
        print(f"\n  📋 Riwayat Perubahan Kategori (menampilkan {len(tampil)} dari {len(self._riwayat)} total):")
        print(f"  {'No':<5} {'Waktu':<21} {'Aksi':<12} {'Nama Kategori':<32} Detail")
        print(f"  {'-'*100}")
        for i, e in enumerate(tampil, start=max(1, len(self._riwayat) - n + 1)):
            detail_str = json.dumps(e.get("detail", {}), ensure_ascii=False)
            if len(detail_str) > 45:
                detail_str = detail_str[:42] + "..."
            print(f"  {i:<5} {e['waktu']:<21} {e['aksi']:<12} {e['nama']:<32} {detail_str}")
        print(f"\n  💾 File riwayat lengkap: {self._riwayat_path}")

    # ── Export ke dict ────────────────────────────────
    def ke_dict(self) -> dict:
        """Kembalikan kategori sebagai dict untuk disimpan ke config."""
        return dict(self.kategori)


# ══════════════════════════════════════════════════════
# KONFIGURASI
# ══════════════════════════════════════════════════════
def muat_konfigurasi(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("kata_gresik", DEFAULT_KATA_GRESIK)
            cfg.setdefault("kategori_mapping", DEFAULT_KATEGORI_MAPPING)
            print(f"⚙️  Konfigurasi dimuat dari: {path}")
            return cfg
        except Exception as e:
            print(f"⚠  Gagal membaca config ({e}), pakai default.")
    cfg = {"kata_gresik": DEFAULT_KATA_GRESIK, "kategori_mapping": DEFAULT_KATEGORI_MAPPING}
    simpan_konfigurasi(path, cfg)
    print(f"⚙️  Konfigurasi default dibuat: {path}")
    return cfg

def simpan_konfigurasi(path, cfg):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def gabungkan_keyword_cli(cfg, keyword_cli):
    if not keyword_cli:
        return cfg
    tambahan = [k.strip().lower() for k in keyword_cli.split(",") if k.strip()]
    cfg["kata_gresik"] = list(dict.fromkeys(cfg["kata_gresik"] + tambahan))
    return cfg


# ══════════════════════════════════════════════════════
# BROWSER
# ══════════════════════════════════════════════════════
def _buat_options(headless=True):
    opt = Options()
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    opt.add_argument("--disable-gpu")
    opt.add_argument("--window-size=1400,900")
    opt.add_argument("--disable-blink-features=AutomationControlled")
    opt.add_argument("--lang=id-ID")
    opt.add_argument("--disable-extensions")
    opt.add_argument("--disable-popup-blocking")
    opt.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/120.0.0.0 Safari/537.36")
    opt.add_experimental_option("excludeSwitches", ["enable-automation"])
    opt.add_experimental_option("useAutomationExtension", False)
    if headless:
        opt.add_argument("--headless=new")
    return opt

def _pasang_anti_detection(driver):
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['id-ID','id','en-US','en']});
        """
    })
    driver.set_page_load_timeout(45)
    driver.implicitly_wait(FAST_WAIT)

def buat_browser(headless=True):
    opt = _buat_options(headless)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
        _pasang_anti_detection(driver)
        return driver
    except ImportError:
        print("   ℹ️  webdriver-manager tidak ada → pip install webdriver-manager")
    except Exception as e:
        print(f"   ⚠  webdriver-manager gagal: {e}")

    if os.path.exists(CHROMEDRIVER):
        try:
            driver = webdriver.Chrome(service=Service(CHROMEDRIVER), options=opt)
            _pasang_anti_detection(driver)
            return driver
        except Exception as e:
            print(f"   ❌ chromedriver.exe gagal: {e}")
            if "version" in str(e).lower() or "session" in str(e).lower():
                print("\n   SOLUSI: pip install webdriver-manager  lalu jalankan ulang.")
                exit(1)

    try:
        driver = webdriver.Chrome(options=opt)
        _pasang_anti_detection(driver)
        return driver
    except Exception as e:
        print(f"   ❌ Semua metode gagal: {e}")
        exit(1)


# ══════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════
def jeda(a=0.8, b=1.5):      time.sleep(random.uniform(a, b))
def jeda_pdp(a=0.3, b=0.6):  time.sleep(random.uniform(a, b))

def buka(driver, url):
    try:
        driver.get(url)
        return True
    except TimeoutException:
        try: driver.execute_script("window.stop();")
        except: pass
        return False

def tutup_popup(driver):
    for sel in [
        "button[class*='close']", ".pdp-mod-common-image.close-icon",
        "[data-testid='close-button']", "[class*='modal'] [class*='close']",
        ".ic-close-line", "[class*='Close']", "[class*='dismiss']",
        "button[aria-label='Close']",
    ]:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    el.click()
                    time.sleep(0.3)
        except: pass

def scroll_halaman(driver, jumlah=10, jeda_antar=0.2):
    for i in range(jumlah):
        driver.execute_script(f"window.scrollBy(0, {600 + i * 50});")
        time.sleep(jeda_antar)
    driver.execute_script("window.scrollBy(0, -300);")
    time.sleep(0.5)

def ada_gresik(teks, kata_gresik):
    t = (teks or "").lower()
    return any(k in t for k in kata_gresik)

def standarisasi_kategori(teks, kategori_mapping):
    t = (teks or "").lower()
    for kat, kw_list in kategori_mapping.items():
        if any(kw in t for kw in kw_list): return kat
    return "Lainnya"

def bersihkan_harga(raw):
    if not raw or raw == "-": return "-"
    matches = re.findall(r"Rp[\s]*([\d.,]+)", raw, re.IGNORECASE)
    if matches: return "Rp" + matches[0].replace(" ", "")
    return raw.split("\n")[0].strip()

def bersihkan_rating(raw):
    if not raw: return "-"
    m = re.search(r"(\d+[.,]\d+|\d+)", raw)
    return m.group(1) if m else raw.strip()

def bersihkan_terjual(raw):
    if not raw: return "-"
    m = re.search(r"([\d.,]+[kmb]?)", raw, re.IGNORECASE)
    return m.group(1) if m else raw.strip()[:20]

def deteksi_badge(teks):
    t = teks.lower()
    for b in LAZADA_BADGE:
        if b in t: return b.title()
    return "-"

def baris_skip(baris):
    b = baris.lower()
    return any(p in b for p in SKIP_PATTERNS) or len(baris) < 8

def ambil_teks_el(el, *sels):
    for s in sels:
        try:
            sub = el.find_element(By.CSS_SELECTOR, s)
            t = sub.text.strip()
            if t: return t
        except: pass
    return ""

def ambil_teks_driver(driver, *sels):
    for s in sels:
        try:
            el = driver.find_element(By.CSS_SELECTOR, s)
            t = el.text.strip()
            if t: return t
        except: pass
    return ""

def debug_simpan(driver, nama, headless=True):
    try:
        png  = os.path.join(OUTPUT_DIR, f"debug_{nama}.png")
        html = os.path.join(OUTPUT_DIR, f"debug_{nama}.html")
        driver.save_screenshot(png)
        with open(html, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"   🔍 Debug: output/debug_{nama}.png + output/debug_{nama}.html disimpan")
    except: pass


# ══════════════════════════════════════════════════════
# [FIX v3] AMBIL NAMA PRODUK DARI LINK/CARD
# ══════════════════════════════════════════════════════
def ambil_nama_dari_link(driver, a_el):
    # 1. Coba title attribute
    try:
        t = (a_el.get_attribute("title") or "").strip()
        if t and len(t) > 5 and t.lower() not in ("", "pdp", "-"):
            return t
    except: pass

    # 2. Coba teks langsung elemen
    try:
        t = a_el.text.strip()
        if t and len(t) > 5 and t.lower() not in ("pdp", "-"):
            return t[:200]
    except: pass

    # 3. Coba cari dalam card parent menggunakan JS closest()
    try:
        parent = driver.execute_script(
            "return arguments[0].closest('[data-item-id],[data-tracking],[class*=\"product-card\"],[class*=\"gridItem\"],[class*=\"c-prd\"]')",
            a_el
        )
        if parent:
            for sel in NAMA_PRODUK_SEL:
                try:
                    el = parent.find_element(By.CSS_SELECTOR, sel)
                    t = el.text.strip()
                    if t and len(t) > 5:
                        return t[:200]
                except: pass
            try:
                inner = parent.text or ""
                kandidat = []
                for baris in inner.split("\n"):
                    b = baris.strip()
                    if b and len(b) > 8 and not baris_skip(b):
                        kandidat.append(b)
                if kandidat:
                    return max(kandidat, key=len)[:200]
            except: pass
    except: pass

    return ""


# ══════════════════════════════════════════════════════
# [FIX v3] AMBIL NAMA TOKO DARI PDP
# ══════════════════════════════════════════════════════
def _teks_valid_nama_toko(teks):
    if not teks:
        return False
    t = teks.strip()
    t_lower = t.lower()
    if len(t) < 2 or len(t) > 80:
        return False
    if ">" in t or "<" in t:
        return False
    if any(bl in t_lower for bl in TOKO_BLACKLIST):
        return False
    if re.match(r'^[\d\s\-_.,]+$', t):
        return False
    return True


def _ambil_nama_toko_dari_pdp(driver):
    # Prioritas 1: selector berbasis href toko
    for sel in ["a[href*='/shop/']", "a[href*='/seller/']", "[data-spm='dshopname'] a"]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                t = el.text.strip()
                href = el.get_attribute("href") or ""
                if _teks_valid_nama_toko(t) and "lazada.co.id" in href:
                    return t, href
        except: pass

    # Prioritas 2: selector class berbasis nama toko
    for sel in [
        "[data-spm='dshopname']",
        "[class*='sellerName'] a", "[class*='sellerName']",
        "[class*='seller-name'] a", "[class*='seller-name']",
        "[class*='shop-name'] a", "[class*='shopName'] a",
        "[class*='pdp-product-brand'] a",
        "[class*='StoreInfo'] a", "[class*='StoreInfo']",
        "[class*='seller-info'] a",
    ]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                t = el.text.strip()
                if not _teks_valid_nama_toko(t):
                    continue
                href = ""
                try:
                    href = el.get_attribute("href") or ""
                    if href and "lazada.co.id" not in href:
                        href = ""
                except: pass
                if not href:
                    try:
                        a = el.find_element(By.TAG_NAME, "a")
                        href = a.get_attribute("href") or ""
                    except: pass
                return t, href
        except: pass

    # Prioritas 3: scan semua link di halaman yang mengarah ke toko
    try:
        semua_a = driver.find_elements(By.TAG_NAME, "a")
        for el in semua_a:
            href = el.get_attribute("href") or ""
            if "/shop/" not in href and "/seller/" not in href:
                continue
            if "lazada.co.id" not in href:
                continue
            t = el.text.strip()
            if _teks_valid_nama_toko(t):
                return t, href
    except: pass

    return "-", "-"


# ══════════════════════════════════════════════════════
# CANDIDATE URLS
# ══════════════════════════════════════════════════════
CANDIDATE_URLS = [
    "https://www.lazada.co.id/catalog/?q=&locations=ID110500000&sort=0",
    "https://www.lazada.co.id/catalog/?locations=ID110500000&sort=0&ajax=true",
    "https://www.lazada.co.id/catalog/?q=gresik&locations=ID110500000&sort=0",
    "https://www.lazada.co.id/catalog/?city=gresik&sort=0",
    "https://www.lazada.co.id/catalog/?q=toko+gresik&sort=0",
    "https://www.lazada.co.id/catalog/?q=gresik&sort=0",
]

def _url_punya_produk(driver, url, kata_gresik):
    buka(driver, url)
    time.sleep(3)
    tutup_popup(driver)
    scroll_halaman(driver, jumlah=6, jeda_antar=0.2)

    for sel in ["a[href*='/products/']", "a[href*='-i'][href*='-s']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        valid = [e for e in els if "lazada.co.id" in (e.get_attribute("href") or "")]
        if len(valid) >= 3:
            return True

    if len(driver.find_elements(By.CSS_SELECTOR, "[data-item-id]")) >= 3:
        return True

    return False


def aktifkan_filter(driver, kata_gresik):
    print("\n📍 Mencari URL listing Lazada dengan produk Gresik...")

    for url in CANDIDATE_URLS:
        print(f"   Coba: {url[:75]}...", end=" ", flush=True)
        try:
            ada = _url_punya_produk(driver, url, kata_gresik)
        except Exception as e:
            print(f"❌ error ({e})")
            continue
        if ada:
            print(f"✅ ada produk!")
            return url
        else:
            print("⬜ tidak ada produk")

    print("\n   Semua URL kandidat kosong. Mencoba klik filter sidebar...")
    return _coba_klik_filter_sidebar(driver, kata_gresik)


def _coba_klik_filter_sidebar(driver, kata_gresik):
    buka(driver, "https://www.lazada.co.id/catalog/?q=produk&sort=0")
    time.sleep(4)
    tutup_popup(driver)

    for _ in range(20):
        driver.execute_script("window.scrollBy(0, 200)")
        time.sleep(0.1)
    time.sleep(1)

    for xpath in [
        "//*[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat lebih banyak')]",
        "//*[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'see more')]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    driver.execute_script("arguments[0].click()", el)
                    time.sleep(0.5)
        except: pass

    target_kw = [k for k in kata_gresik if "gresik" in k] or ["gresik"]

    for xpath in [
        "//*[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//*[translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='gresik']",
        "//input[@type='checkbox'][following-sibling::*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'gresik')]]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                try:
                    t = el.text.strip().lower()
                    if el.is_displayed() and any(k in t for k in target_kw):
                        print(f"   ✅ Filter sidebar: '{el.text.strip()}'")
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                        try: el.click()
                        except ElementClickInterceptedException:
                            driver.execute_script("arguments[0].click()", el)
                        time.sleep(3)
                        url_hasil = driver.current_url
                        if _url_punya_produk(driver, url_hasil, kata_gresik):
                            return url_hasil
                except StaleElementReferenceException: pass
        except: pass

    print("   ❌ Tidak berhasil otomatis.")
    print("   💡 Jalankan dengan --url untuk set URL manual.")
    return None


# ══════════════════════════════════════════════════════
# LANGKAH 2 — Kumpulkan URL produk dari listing
# ══════════════════════════════════════════════════════
MAX_RETRY_PER_HALAMAN = 3

def _scrape_satu_halaman(driver, url, kata_gresik, semua, halaman_ke, debug=False):
    buka(driver, url)
    time.sleep(2.5)
    tutup_popup(driver)
    scroll_halaman(driver, jumlah=12, jeda_antar=0.25)

    baru = 0

    # ── STRATEGI 1: Cari kartu produk via selector ────────────────────────────
    for sel in CARD_SELECTORS:
        cards = driver.find_elements(By.CSS_SELECTOR, sel)
        if len(cards) < 3:
            continue

        print(f"      → Selector '{sel}': {len(cards)} kartu ditemukan")

        for card in cards:
            try:
                teks = card.text.strip()
                if not teks: continue

                url_prod = ""
                nama     = ""

                for a in card.find_elements(By.TAG_NAME, "a"):
                    try:
                        h = a.get_attribute("href") or ""
                        if "lazada.co.id/products/" in h or re.search(r"-i\d+", h):
                            url_prod_cand = h.split("?")[0]
                            if url_prod_cand in semua:
                                continue
                            nama_cand = ambil_nama_dari_link(driver, a)
                            if nama_cand and nama_cand.lower() not in ("pdp", ""):
                                url_prod = url_prod_cand
                                nama     = nama_cand
                                break
                            elif not url_prod:
                                url_prod = url_prod_cand
                    except: pass

                if not url_prod: continue
                if url_prod in semua: continue

                if not nama:
                    nama = ambil_teks_el(card, *NAMA_PRODUK_SEL)

                if not nama or nama.lower() == "pdp":
                    for l in teks.split("\n"):
                        l = l.strip()
                        if l and not baris_skip(l) and len(l) > 8:
                            nama = l[:200]
                            break

                if not nama or nama.lower() == "pdp":
                    continue

                harga   = ambil_teks_el(card, *HARGA_SEL)
                lokasi  = ambil_teks_el(card, *LOKASI_SEL)
                rating  = ambil_teks_el(card, *RATING_SEL)
                terjual = ambil_teks_el(card, *TERJUAL_SEL)

                if not lokasi:
                    for k in kata_gresik:
                        if k in teks.lower():
                            lokasi = k.title()
                            break
                lokasi = lokasi or "Kab. Gresik"

                semua[url_prod] = {
                    "url_produk"    : url_prod,
                    "nama_produk"   : nama[:200],
                    "harga"         : bersihkan_harga(harga),
                    "lokasi_seller" : lokasi,
                    "rating_produk" : bersihkan_rating(rating),
                    "terjual"       : bersihkan_terjual(terjual),
                    "badge"         : deteksi_badge(teks),
                    "nama_toko"     : "-",
                    "url_toko"      : "-",
                    "rating_toko"   : "-",
                }
                baru += 1
            except StaleElementReferenceException: pass
            except WebDriverException: raise
            except: pass

        if baru > 0:
            break

    # ── STRATEGI 2: Fallback — cari semua link produk ────────────────────────
    if baru == 0:
        semua_a = []
        try:
            semua_a = driver.find_elements(By.TAG_NAME, "a")
        except: pass

        print(f"      → Fallback: {len(semua_a)} elemen <a> ditemukan")

        seen_in_strat2 = set()
        for a_el in semua_a:
            try:
                h = a_el.get_attribute("href") or ""
                if not h or "lazada.co.id" not in h:
                    continue
                if "/products/" not in h and not (re.search(r"-i\d+", h) and re.search(r"-s\d+", h)):
                    continue

                url_prod = h.split("?")[0]
                if url_prod in semua or url_prod in seen_in_strat2:
                    continue
                seen_in_strat2.add(url_prod)

                nama = ambil_nama_dari_link(driver, a_el)

                if not nama or nama.lower() in ("pdp", ""):
                    slug = url_prod.rstrip("/").split("/")[-1]
                    slug = re.sub(r"-i\d+.*", "", slug)
                    slug_clean = slug.replace("-", " ").strip()
                    if slug_clean.lower() == "pdp" or len(slug_clean) < 5:
                        continue
                    nama = slug_clean[:200]

                semua[url_prod] = {
                    "url_produk"    : url_prod,
                    "nama_produk"   : nama,
                    "harga"         : "-",
                    "lokasi_seller" : "Kab. Gresik",
                    "rating_produk" : "-",
                    "terjual"       : "-",
                    "badge"         : "-",
                    "nama_toko"     : "-",
                    "url_toko"      : "-",
                    "rating_toko"   : "-",
                }
                baru += 1
            except WebDriverException: raise
            except: pass

    # ── DEBUG ─────────────────────────────────────────────────────────────────
    if baru == 0 and debug:
        debug_simpan(driver, f"hal{halaman_ke}")
        try:
            hrefs = [a.get_attribute("href") for a in driver.find_elements(By.TAG_NAME, "a")
                     if (a.get_attribute("href") or "")]
            lazada_hrefs = [h for h in hrefs if h and "lazada" in h][:8]
            print(f"      🔍 Sampel href Lazada di halaman:")
            for h in lazada_hrefs:
                print(f"         {h[:100]}")
        except: pass
    elif baru == 0:
        try:
            hrefs = [a.get_attribute("href") or ""
                     for a in driver.find_elements(By.TAG_NAME, "a")[:50]]
            lazada_hrefs = [h for h in hrefs if "lazada" in h][:3]
            if lazada_hrefs:
                print(f"      ℹ️  Sampel href: {lazada_hrefs[0][:90]}")
            else:
                print(f"      ℹ️  Tidak ada href Lazada — halaman mungkin kosong/CAPTCHA")
        except: pass

    return baru


def kumpulkan_url_produk(driver, url_filter, kata_gresik, headless=True, debug=False):
    print(f"\n📋 Kumpulkan URL produk dari listing (maks {MAX_HALAMAN} hal)...")
    semua      = {}
    kosong_str = 0

    for hal in range(1, MAX_HALAMAN + 1):
        if "page=" in url_filter:
            url = re.sub(r"page=\d+", f"page={hal}", url_filter)
        else:
            sep = "&" if "?" in url_filter else "?"
            url = f"{url_filter}{sep}page={hal}"

        print(f"\n   Hal {hal:2}/{MAX_HALAMAN} → {url[:80]}...")
        baru = 0

        for percobaan in range(1, MAX_RETRY_PER_HALAMAN + 1):
            try:
                baru = _scrape_satu_halaman(
                    driver, url, kata_gresik, semua,
                    halaman_ke=hal, debug=debug
                )
                break
            except Exception as e:
                print(f"   ⚠️  Browser error hal {hal} "
                      f"(percobaan {percobaan}/{MAX_RETRY_PER_HALAMAN}): "
                      f"{type(e).__name__} — restart browser...")
                try: driver.quit()
                except: pass
                time.sleep(2)
                driver = buat_browser(headless=headless)
                if percobaan == MAX_RETRY_PER_HALAMAN:
                    print(f"   ❌ Halaman {hal} dilewati.")
                    baru = 0

        print(f"   Hasil: +{baru} produk baru | Total terkumpul: {len(semua)}")
        kosong_str = 0 if baru > 0 else kosong_str + 1
        if kosong_str >= 3:
            print("   3x halaman kosong → selesai."); break
        jeda()

    return list(semua.values()), driver


# ══════════════════════════════════════════════════════
# LANGKAH 3 — Buka PDP secara PARALEL
# ══════════════════════════════════════════════════════
def _ambil_satu_pdp(url, headless):
    driver = None
    hasil = {
        "nama_toko"    : "-",
        "url_toko"     : "-",
        "rating_toko"  : "-",
        "rating_produk": "-",
        "terjual"      : "-",
    }
    try:
        driver = buat_browser(headless=headless)
        buka(driver, url)
        time.sleep(1.5)
        tutup_popup(driver)
        driver.execute_script("window.scrollBy(0, 400)")
        time.sleep(0.5)

        nama_toko, url_toko = _ambil_nama_toko_dari_pdp(driver)
        hasil["nama_toko"] = nama_toko
        hasil["url_toko"]  = url_toko

        hasil["rating_toko"] = bersihkan_rating(
            ambil_teks_driver(driver, *PDP_RATING_TOKO_SEL)
        )
        hasil["rating_produk"] = bersihkan_rating(
            ambil_teks_driver(driver, *PDP_RATING_PRODUK_SEL)
        )
        hasil["terjual"] = bersihkan_terjual(
            ambil_teks_driver(driver, *PDP_TERJUAL_SEL)
        )

        return url, hasil
    except Exception:
        return url, hasil
    finally:
        if driver:
            try: driver.quit()
            except: pass


def ambil_nama_toko_pdp_paralel(produk_list, workers, headless):
    total = len(produk_list)
    url_ke_item = {p["url_produk"]: p for p in produk_list if p.get("url_produk", "-") != "-"}
    urls = list(url_ke_item.keys())

    print(f"\n🏪 Ambil info toko via PDP — {total} produk, {workers} browser paralel...")

    selesai = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_ambil_satu_pdp, u, headless): u for u in urls}
        for future in as_completed(future_map):
            url, hasil = future.result()
            item = url_ke_item[url]
            item["nama_toko"]   = hasil["nama_toko"]
            item["url_toko"]    = hasil["url_toko"]
            item["rating_toko"] = hasil["rating_toko"]
            if item.get("rating_produk", "-") == "-":
                item["rating_produk"] = hasil["rating_produk"]
            if item.get("terjual", "-") == "-":
                item["terjual"] = hasil["terjual"]
            selesai += 1
            if selesai % 10 == 0 or selesai == total:
                dapat = sum(1 for p in produk_list if p["nama_toko"] != "-")
                print(f"   [{selesai:>4}/{total}] selesai | toko terdeteksi: {dapat}")

    dapat = sum(1 for p in produk_list if p["nama_toko"] != "-")
    print(f"\n   ✅ Nama toko berhasil: {dapat}/{total}")
    return produk_list


# ══════════════════════════════════════════════════════
# SIMPAN CSV
# ══════════════════════════════════════════════════════
def simpan_csv(data_list, kategori_mapping):
    if not data_list:
        print("\n⚠  Tidak ada data."); return None

    df = pd.DataFrame(data_list)
    df["kategori"]     = df["nama_produk"].apply(
        lambda x: standarisasi_kategori(x, kategori_mapping))
    df["platform"]     = "Lazada"
    df["waktu_scrape"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    df = df.drop_duplicates(subset=["url_produk"])

    kolom = [
        "nama_toko", "url_toko", "rating_toko",
        "nama_produk", "harga", "rating_produk", "terjual",
        "lokasi_seller", "kategori", "badge",
        "url_produk", "platform", "waktu_scrape",
    ]
    df_out = df[[c for c in kolom if c in df.columns]]
    df_out.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    file_toko = os.path.join(OUTPUT_DIR, "toko_gresik_lazada_per_toko.csv")
    grp_toko = (
        df[df["nama_toko"] != "-"]
        .groupby(["nama_toko", "lokasi_seller", "url_toko", "rating_toko"])
        .agg(
            jumlah_produk   =("nama_produk", "count"),
            kategori_dijual =("kategori",    lambda x: " | ".join(sorted(x.unique()))),
            contoh_produk   =("nama_produk", lambda x: " | ".join(list(x.unique())[:4])),
        )
        .reset_index()
        .sort_values("jumlah_produk", ascending=False)
    )
    grp_toko.to_csv(file_toko, index=False, encoding="utf-8-sig")

    file_lokasi = os.path.join(OUTPUT_DIR, "toko_gresik_lazada_per_lokasi.csv")
    grp_lokasi = (
        df.groupby("lokasi_seller")
        .agg(
            jumlah_toko   =("nama_toko",   lambda x: x[x != "-"].nunique()),
            jumlah_produk =("nama_produk", "count"),
            contoh_toko   =("nama_toko",   lambda x: " | ".join(x[x != "-"].unique()[:4])),
        )
        .reset_index()
        .sort_values("jumlah_produk", ascending=False)
    )
    grp_lokasi.to_csv(file_lokasi, index=False, encoding="utf-8-sig")

    file_kat = os.path.join(OUTPUT_DIR, "toko_gresik_lazada_per_kategori.csv")
    grp_kat = (
        df.groupby("kategori")
        .agg(
            jumlah_produk =("nama_produk", "count"),
            jumlah_toko   =("nama_toko",   lambda x: x[x != "-"].nunique()),
        )
        .reset_index()
        .sort_values("jumlah_produk", ascending=False)
    )
    grp_kat.to_csv(file_kat, index=False, encoding="utf-8-sig")

    print(f"\n{'='*62}")
    print(f"  HASIL SCRAPING TOKO GRESIK DI LAZADA")
    print(f"{'='*62}")
    print(f"  📦 Total produk unik    : {len(df)}")
    print(f"  🏪 Total toko unik      : {df[df['nama_toko'] != '-']['nama_toko'].nunique()}")
    print(f"  📍 Wilayah Gresik       : {df['lokasi_seller'].nunique()}")
    print(f"  🏷️  Kategori terdeteksi : {df['kategori'].nunique()}")
    if "badge" in df.columns:
        bc = df[df["badge"] != "-"]["badge"].value_counts()
        if not bc.empty: print(f"  🏅 Badge Lazada         : {bc.to_dict()}")
    print(f"  💾 Detail produk        → output/toko_gresik_lazada.csv")
    print(f"  💾 Ringkasan per toko   → output/toko_gresik_lazada_per_toko.csv")
    print(f"  💾 Ringkasan per lokasi → output/toko_gresik_lazada_per_lokasi.csv")
    print(f"  💾 Ringkasan kategori   → output/toko_gresik_lazada_per_kategori.csv")
    print(f"{'='*62}")
    print(f"\n  SAMPEL (20 produk pertama):\n")
    for _, r in df.head(20).iterrows():
        badge = f"[{r.get('badge', '-')}] " if r.get("badge", "-") != "-" else ""
        print(f"  🏪 {str(r.get('nama_toko', '-'))[:20]:<20} | "
              f"{badge}{r['nama_produk'][:35]:<35} | "
              f"{r['harga']} | ⭐{r.get('rating_produk', '-')}")

    return df


# ══════════════════════════════════════════════════════
# EKSPOR DASHBOARD JSON
# ══════════════════════════════════════════════════════
def ekspor_dashboard(df, kata_gresik, kategori_mapping):
    if df is None or df.empty:
        data = {
            "platform": "Lazada", "keywords": kata_gresik,
            "kategori_tersedia": list(kategori_mapping.keys()),
            "badge_lazada": LAZADA_BADGE,
            "ringkasan": {}, "data_toko": [], "produk": [],
        }
    else:
        data_toko = []
        toko_cols = ["nama_toko", "lokasi_seller", "url_toko", "rating_toko"]
        for keys, grp in df.groupby(toko_cols):
            nama_toko, lokasi, url_toko, rating_toko = keys
            if nama_toko == "-": continue
            produk_toko = grp[[
                "nama_produk", "harga", "kategori", "badge",
                "rating_produk", "terjual", "url_produk"
            ]].to_dict(orient="records")
            kategori_set = sorted(grp["kategori"].unique().tolist())
            data_toko.append({
                "nama_toko"       : nama_toko,
                "lokasi"          : lokasi,
                "url_toko"        : url_toko,
                "rating_toko"     : rating_toko,
                "jumlah_produk"   : len(grp),
                "kategori_dijual" : kategori_set,
                "badge"           : grp["badge"].mode()[0] if not grp["badge"].empty else "-",
                "produk"          : produk_toko,
            })
        data_toko.sort(key=lambda x: x["jumlah_produk"], reverse=True)

        ringkasan = {
            "total_produk"  : len(df),
            "total_toko"    : len(data_toko),
            "per_kategori"  : df["kategori"].value_counts().to_dict(),
            "per_lokasi"    : df["lokasi_seller"].value_counts().to_dict(),
            "per_badge"     : (df[df["badge"] != "-"]["badge"].value_counts().to_dict()
                               if "badge" in df.columns else {}),
            "waktu_ekspor"  : datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        data = {
            "platform"          : "Lazada",
            "keywords"          : kata_gresik,
            "kategori_tersedia" : list(kategori_mapping.keys()),
            "badge_lazada"      : LAZADA_BADGE,
            "ringkasan"         : ringkasan,
            "data_toko"         : data_toko,
            "produk"            : df.to_dict(orient="records"),
        }

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  📊 Dashboard JSON       → output/dashboard_data_lazada.json")


# ══════════════════════════════════════════════════════
# ARGUMEN CLI
# ══════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(
        description="Scraper toko Gresik di Lazada — versi perbaikan v3",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
CONTOH PENGGUNAAN:
  # Scraping biasa
  python Lazada_v3.py
  python Lazada_v3.py --url "https://www.lazada.co.id/catalog/?q=gresik"
  python Lazada_v3.py --headful --debug --workers 3

  # CRUD Kategori
  python Lazada_v3.py --tambah-kat "Pertanian" --kw "pupuk,bibit,cangkul,pestisida"
  python Lazada_v3.py --tambah-kw "Makanan & Minuman" --kw "jamu,wedang,es batu"
  python Lazada_v3.py --hapus-kw "Elektronik" --kw "elektronik"
  python Lazada_v3.py --edit-kat "Lainnya|Produk Umum"
  python Lazada_v3.py --hapus-kat "Hobi & Koleksi"
  python Lazada_v3.py --lihat-kat
  python Lazada_v3.py --lihat-kat "Elektronik"
  python Lazada_v3.py --riwayat
"""
    )

    # ── Scraping ──────────────────────────────────────
    p.add_argument("--keywords", type=str, default="",
                   help="Keyword lokasi tambahan, pisah koma")
    p.add_argument("--config",   type=str, default=CONFIG_FILE_DEF,
                   help="Path file konfigurasi JSON")
    p.add_argument("--url",      type=str, default="",
                   help="URL filter Lazada langsung (skip langkah aktifkan_filter)")
    p.add_argument("--workers",  type=int, default=DEFAULT_WORKERS,
                   help="Jumlah browser paralel untuk tahap PDP (default 5)")
    p.add_argument("--headful",  action="store_true",
                   help="Matikan headless (browser kelihatan)")
    p.add_argument("--debug",    action="store_true",
                   help="Simpan screenshot + page source kalau 0 produk ditemukan")
    p.add_argument("--no-pdp",   action="store_true",
                   help="Skip tahap PDP (hanya ambil data listing)")

    # ── CRUD Kategori ─────────────────────────────────
    grp = p.add_argument_group("CRUD Kategori")
    grp.add_argument("--tambah-kat", type=str, default="",
                     metavar="NAMA",
                     help="Tambah kategori baru dengan nama NAMA")
    grp.add_argument("--hapus-kat",  type=str, default="",
                     metavar="NAMA",
                     help="Hapus kategori NAMA (keyword di-backup ke riwayat)")
    grp.add_argument("--edit-kat",   type=str, default="",
                     metavar="LAMA|BARU",
                     help="Ganti nama kategori: 'Nama Lama|Nama Baru'")
    grp.add_argument("--tambah-kw",  type=str, default="",
                     metavar="NAMA",
                     help="Tambah keyword ke kategori NAMA (gunakan bersama --kw)")
    grp.add_argument("--hapus-kw",   type=str, default="",
                     metavar="NAMA",
                     help="Hapus keyword dari kategori NAMA (gunakan bersama --kw)")
    grp.add_argument("--kw",         type=str, default="",
                     metavar="KW1,KW2,...",
                     help="Daftar keyword untuk --tambah-kat / --tambah-kw / --hapus-kw")
    grp.add_argument("--lihat-kat",  type=str, default=None,
                     nargs="?", const="__semua__",
                     metavar="NAMA",
                     help="Lihat kategori (kosongkan = semua, isi = satu kategori)")
    grp.add_argument("--riwayat",    action="store_true",
                     help="Tampilkan riwayat perubahan kategori lalu keluar")
    grp.add_argument("--riwayat-n",  type=int, default=30,
                     metavar="N",
                     help="Jumlah baris riwayat yang ditampilkan (default 30)")

    return p.parse_args()


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
def main():
    args    = parse_args()
    headless = not args.headful

    print("╔══════════════════════════════════════════════════════════╗")
    print("║   SCRAPER TOKO GRESIK DI LAZADA — VERSI PERBAIKAN v3    ║")
    print(f"║   Mulai: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                            ║")
    print(f"║   Mode: {'HEADLESS' if headless else 'HEADFUL':<10} | Workers PDP: {args.workers:<3}            ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    if args.debug:
        print("   🔍 MODE DEBUG AKTIF\n")

    # ── Muat konfigurasi & inisialisasi KategoriManager ───────────────────────
    cfg = muat_konfigurasi(args.config)
    cfg = gabungkan_keyword_cli(cfg, args.keywords)

    kata_gresik = [k.lower() for k in cfg["kata_gresik"]]
    kat_mgr     = KategoriManager(
        cfg.get("kategori_mapping", DEFAULT_KATEGORI_MAPPING),
        riwayat_path=RIWAYAT_FILE,
    )

    # ── Eksekusi perintah CRUD (jika ada) ────────────────────────────────────
    crud_dilakukan = False

    if args.riwayat:
        kat_mgr.tampilkan_riwayat(n=args.riwayat_n)
        return

    if args.lihat_kat is not None:
        nama_filter = None if args.lihat_kat == "__semua__" else args.lihat_kat
        kat_mgr.lihat_kategori(nama_filter)
        crud_dilakukan = True

    if args.tambah_kat:
        kw_list = [k.strip() for k in args.kw.split(",") if k.strip()]
        kat_mgr.tambah_kategori(args.tambah_kat, kw_list)
        crud_dilakukan = True

    if args.hapus_kat:
        kat_mgr.hapus_kategori(args.hapus_kat)
        crud_dilakukan = True

    if args.edit_kat:
        parts = args.edit_kat.split("|", 1)
        if len(parts) == 2:
            kat_mgr.edit_nama_kategori(parts[0].strip(), parts[1].strip())
        else:
            print("   ❌ Format --edit-kat salah. Gunakan: 'Nama Lama|Nama Baru'")
        crud_dilakukan = True

    if args.tambah_kw:
        kw_list = [k.strip() for k in args.kw.split(",") if k.strip()]
        kat_mgr.tambah_keyword(args.tambah_kw, kw_list)
        crud_dilakukan = True

    if args.hapus_kw:
        kw_list = [k.strip() for k in args.kw.split(",") if k.strip()]
        kat_mgr.hapus_keyword(args.hapus_kw, kw_list)
        crud_dilakukan = True

    # Simpan perubahan CRUD ke config
    if crud_dilakukan:
        cfg["kategori_mapping"] = kat_mgr.ke_dict()
        simpan_konfigurasi(args.config, cfg)
        print(f"\n  💾 Perubahan kategori disimpan ke: {args.config}")
        print(f"  📋 Riwayat tersimpan di          : {RIWAYAT_FILE}")
        # Keluar kalau tidak ada perintah scraping
        if not args.url and not args.keywords:
            return

    # Gunakan kategori terbaru untuk scraping
    kategori_mapping = kat_mgr.ke_dict()

    print(f"  🔑 Keyword aktif  ({len(kata_gresik)}): {', '.join(kata_gresik)}")
    print(f"  🏷️  Kategori       ({len(kategori_mapping)}): {', '.join(kategori_mapping.keys())}\n")

    # ── Simpan config terbaru (keyword CLI dll) ───────────────────────────────
    cfg["kata_gresik"]      = kata_gresik
    cfg["kategori_mapping"] = kategori_mapping
    simpan_konfigurasi(args.config, cfg)

    # ── Scraping ──────────────────────────────────────────────────────────────
    driver = buat_browser(headless=headless)
    produk = []

    try:
        url_filter = args.url or aktifkan_filter(driver, kata_gresik)
        if not url_filter:
            print("\n❌ Filter gagal. Coba:")
            print("   1. Jalankan dengan --headful untuk lihat browser")
            print("   2. Copy URL filter manual lalu:")
            print("      python Lazada_v3.py --url \"<URL filter Gresik>\"")
            return

        print(f"\n   ✅ URL filter aktif: {url_filter[:100]}...")

        produk, driver = kumpulkan_url_produk(
            driver, url_filter, kata_gresik,
            headless=headless, debug=args.debug
        )

        if not produk:
            print("\n❌ Tidak ada produk ditemukan di listing.")
            print("\n💡 SOLUSI:")
            print("   1. Jalankan dengan --headful --debug")
            print("   2. Coba: python Lazada_v3.py --headful")
            print("   3. Copy URL filter manual: python Lazada_v3.py --url \"<URL>\"")
            ekspor_dashboard(None, kata_gresik, kategori_mapping)
            return

        backup_file = os.path.join(OUTPUT_DIR, "toko_gresik_lazada_listing_backup.csv")
        pd.DataFrame(produk).to_csv(backup_file, index=False, encoding="utf-8-sig")
        print(f"\n   💾 Backup listing → output/toko_gresik_lazada_listing_backup.csv")

    except KeyboardInterrupt:
        print("\n\n⏹ Dihentikan saat listing. Menyimpan data...")
    finally:
        try: driver.quit()
        except: pass

    if produk and not args.no_pdp:
        try:
            produk = ambil_nama_toko_pdp_paralel(
                produk, workers=args.workers, headless=headless
            )
        except KeyboardInterrupt:
            print("\n\n⏹ Dihentikan saat PDP. Menyimpan data...")
    elif args.no_pdp:
        print("\n   ⏩ Skip PDP (--no-pdp aktif)")

    df = simpan_csv(produk, kategori_mapping)
    ekspor_dashboard(df, kata_gresik, kategori_mapping)
    print(f"\n✅ Selesai! Semua file tersimpan di folder: output/")


if __name__ == "__main__":
    main()