"""
╔══════════════════════════════════════════════════════════════╗
║   SCRAPER TOKO GRESIK DI TOKOPEDIA — v2 (setara Lazada v3)  ║
║   Filter : Tab Toko → Kab. Gresik                           ║
║   Kategori : Diambil LANGSUNG dari halaman Tokopedia         ║
║   Mode   : Listing → PDP (paralel, headless)                ║
║   Output : toko_gresik_tokopedia.csv                        ║
║            dashboard_data_tokopedia.json                    ║
║   CRUD   : Manajemen kategori + riwayat perubahan           ║
╚══════════════════════════════════════════════════════════════╝

CARA PAKAI:
  # Scraping biasa
  python tokopedia_gresik_v2.py
  python tokopedia_gresik_v2.py --headful --debug --workers 3

  # CRUD Kategori
  python tokopedia_gresik_v2.py --tambah-kat "Pertanian" --kw "pupuk,bibit,cangkul"
  python tokopedia_gresik_v2.py --tambah-kw "Makanan & Minuman" --kw "jamu,wedang"
  python tokopedia_gresik_v2.py --hapus-kw "Elektronik" --kw "elektronik"
  python tokopedia_gresik_v2.py --edit-kat "Lainnya|Produk Umum"
  python tokopedia_gresik_v2.py --hapus-kat "Hobi & Koleksi"
  python tokopedia_gresik_v2.py --lihat-kat
  python tokopedia_gresik_v2.py --lihat-kat "Elektronik"
  python tokopedia_gresik_v2.py --riwayat

CATATAN KATEGORI:
  - Kategori diambil LANGSUNG dari breadcrumb / label kategori Tokopedia
    di setiap halaman PDP produk, bukan dari mapping keyword manual.
  - Jika Tokopedia tidak menampilkan kategori, fallback ke mapping keyword
    yang bisa dikelola via CRUD di atas.
  - Semua kategori yang pernah ditemukan disimpan di keywords_config.json
    dan bisa diedit kapan saja.
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

OUTPUT_FILE     = os.path.join(OUTPUT_DIR, "toko_gresik_tokopedia.csv")
DASHBOARD_FILE  = os.path.join(OUTPUT_DIR, "dashboard_data_tokopedia.json")
CONFIG_FILE_DEF = os.path.join(BASE_DIR, "keywords_config_tokopedia.json")
RIWAYAT_FILE    = os.path.join(BASE_DIR, "riwayat_kategori_tokopedia.json")
DEFAULT_WORKERS = 4
FAST_WAIT       = 0.5

DEFAULT_KATA_GRESIK = [
    "kab. gresik", "gresik", "kabupaten gresik",
    "kebomas", "driyorejo", "manyar", "duduksampeyan",
    "bungah", "sidayu", "cerme", "benjeng",
    "balongpanggang", "panceng", "ujungpangkah",
    "sangkapura", "tambak",
]

# Fallback mapping — hanya dipakai jika Tokopedia tidak menampilkan kategori
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

# Badge / label resmi Tokopedia
TOKOPEDIA_BADGE = ["official store", "power merchant", "star seller",
                   "mall", "topads", "tokopedia mall"]

SKIP_PATTERNS = ["rp", "rating", "terjual", "bintang", "gratis", "%",
                 "ongkir", "lihat", "tambah", "keranjang", "diskon",
                 "flash sale", "voucher", "koin", "cashback"]

# Blacklist teks yang bukan nama toko
TOKO_BLACKLIST = [
    "chat sekarang", "chat", "diskusi", "ikuti", "follow",
    "lihat toko", "kunjungi toko", "beli sekarang",
    "tokopedia", "official store", "power merchant", "star seller",
    "tambah ke keranjang", "add to cart", "masukkan keranjang",
    "gratis ongkir", "cashback", "flash sale", "voucher",
    "login", "daftar", "pilih varian", "ulasan",
]

# ── SELECTOR KARTU PRODUK ────────────────────────────────────────────────────
CARD_SELECTORS = [
    "[data-testid='divProductCard']",
    "[data-testid='product-card']",
    "div[class*='css-'][data-testid*='product']",
    "div[class*='ProductCard']",
    "div[class*='product-card']",
    "div[class*='prd_link']",
    ".css-jza1fo",          # class umum grid produk Tokopedia
    "li[class*='product']",
]

NAMA_PRODUK_SEL = [
    "[data-testid='linkProductName']",
    "[class*='prd_link-product-name']",
    "[class*='product-name']",
    "span[class*='OHyMw']",   # hash class Tokopedia
    "a[class*='pcv3__info-content']",
    "h2", "h3",
    "span[class*='name']",
]

HARGA_SEL = [
    "[data-testid='linkProductPrice']",
    "[class*='prd_link-product-price']",
    "span[class*='HiChL']",
    "span[class*='price']",
    "div[class*='price']",
]

LOKASI_SEL = [
    "[data-testid='txtProductLocation']",
    "[class*='prd_link-product-sold-location']",
    "span[class*='yktvO']",
    "span[class*='location']",
    "[class*='sold-location']",
]

TERJUAL_SEL = [
    "[data-testid='txtProductSold']",
    "span[class*='_4yw5I']",
    "span[class*='sold']",
    "span[class*='terjual']",
]

RATING_SEL = [
    "[data-testid='txtProductRating']",
    "span[class*='F5vXh']",
    "span[class*='rating']",
    "span[class*='stars']",
]

# ── SELECTOR PDP Tokopedia ────────────────────────────────────────────────────
# Nama toko
PDP_TOKO_SEL = [
    "[data-testid='llbShopName'] a",
    "[data-testid='llbShopName']",
    "a[data-testid='llbShopNameLink']",
    "[class*='shopName'] a",
    "[class*='shop-name'] a",
    "a[href*='/shop']",             # link ke halaman toko
    "[class*='ShopInfo'] a",
    "[class*='shopInfo'] a",
    "h2[class*='shop']",
]

# Kategori produk — diambil dari breadcrumb Tokopedia
PDP_KATEGORI_SEL = [
    # Breadcrumb Tokopedia (urutan: Beranda > Kategori > Sub-kategori > Produk)
    "[data-testid='divProductBreadcrumb'] a",
    "[class*='Breadcrumb'] a",
    "[class*='breadcrumb'] a",
    "nav[aria-label='breadcrumb'] a",
    "ol[class*='breadcrumb'] li a",
    "[class*='pdp-link_type_category'] a",
    "a[data-testid*='category']",
    # Label kategori langsung
    "[data-testid='lblCategoryProduct']",
    "[class*='css-category']",
    "[class*='product-category']",
    # Chip/tag kategori di bawah judul produk
    "[class*='ProductCategory']",
    "[class*='productCategory']",
]

PDP_RATING_TOKO_SEL = [
    "[data-testid='shopRating']",
    "[class*='shopRating']",
    "[class*='shop-rating'] span",
    "[class*='ratingShop'] span",
]

PDP_RATING_PRODUK_SEL = [
    "[data-testid='lblPDPDetailProductRatingNumber']",
    "[class*='productRating'] span",
    "span[class*='rating-number']",
    "span[class*='score']",
]

PDP_TERJUAL_SEL = [
    "[data-testid='lblPDPDetailProductSoldCounter']",
    "span[class*='soldCount']",
    "[class*='productSold'] span",
    "span[class*='sold']",
]

PDP_BADGE_SEL = [
    "[data-testid='shopBadge']",
    "[class*='shopBadge']",
    "[class*='ShopBadge']",
    "img[alt*='Power Merchant']",
    "img[alt*='Official Store']",
    "img[alt*='Star Seller']",
]


# ══════════════════════════════════════════════════════
# CRUD KATEGORI + RIWAYAT PERUBAHAN
# ══════════════════════════════════════════════════════
class KategoriManager:
    """Mengelola CRUD kategori beserta riwayat setiap perubahan."""

    def __init__(self, kategori_mapping: dict, riwayat_path: str = RIWAYAT_FILE):
        self.kategori      = dict(kategori_mapping)
        self._riwayat_path = riwayat_path
        self._riwayat: list = self._muat_riwayat()

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
        entri = {
            "waktu" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "aksi"  : aksi,
            "nama"  : nama,
            "detail": detail or {},
        }
        self._riwayat.append(entri)
        self._simpan_riwayat()
        print(f"   📝 Riwayat: [{aksi}] {nama}")

    # CREATE
    def tambah_kategori(self, nama: str, keywords: list) -> bool:
        if nama in self.kategori:
            print(f"   ⚠  Kategori '{nama}' sudah ada.")
            return False
        kw = [k.lower().strip() for k in keywords if k.strip()]
        self.kategori[nama] = kw
        self._catat("TAMBAH", nama, {"keywords": kw})
        print(f"   ✅ Kategori '{nama}' ditambahkan dengan {len(kw)} keyword.")
        return True

    # READ
    def lihat_kategori(self, nama: str = None) -> None:
        if nama:
            if nama not in self.kategori:
                print(f"   ❌ Kategori '{nama}' tidak ditemukan.")
                return
            kw = self.kategori[nama]
            print(f"\n  📂 {nama} ({len(kw)} keyword fallback):")
            for k in kw:
                print(f"       • {k}")
        else:
            print(f"\n  📂 Daftar Kategori ({len(self.kategori)} total):")
            print(f"  {'No':<4} {'Nama Kategori':<35} {'Jml KW Fallback'}")
            print(f"  {'-'*58}")
            for i, (nm, kw) in enumerate(self.kategori.items(), 1):
                print(f"  {i:<4} {nm:<35} {len(kw)}")

    # UPDATE — ganti nama
    def edit_nama_kategori(self, nama_lama: str, nama_baru: str) -> bool:
        if nama_lama not in self.kategori:
            print(f"   ❌ Kategori '{nama_lama}' tidak ditemukan.")
            return False
        if nama_baru in self.kategori:
            print(f"   ⚠  Nama '{nama_baru}' sudah dipakai.")
            return False
        self.kategori[nama_baru] = self.kategori.pop(nama_lama)
        self._catat("EDIT", nama_lama, {"nama_baru": nama_baru})
        print(f"   ✅ '{nama_lama}' → '{nama_baru}'.")
        return True

    # UPDATE — tambah keyword fallback
    def tambah_keyword(self, nama: str, keywords: list) -> bool:
        if nama not in self.kategori:
            print(f"   ❌ Kategori '{nama}' tidak ditemukan.")
            return False
        kw_baru = [
            k.lower().strip() for k in keywords
            if k.strip() and k.lower().strip() not in self.kategori[nama]
        ]
        self.kategori[nama].extend(kw_baru)
        self._catat("TAMBAH_KW", nama, {"keywords_baru": kw_baru})
        print(f"   ✅ {len(kw_baru)} keyword ditambahkan ke '{nama}'.")
        return True

    # UPDATE — hapus keyword fallback
    def hapus_keyword(self, nama: str, keywords: list) -> bool:
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

    # DELETE
    def hapus_kategori(self, nama: str) -> bool:
        if nama not in self.kategori:
            print(f"   ❌ Kategori '{nama}' tidak ditemukan.")
            return False
        kw_backup = self.kategori.pop(nama)
        self._catat("HAPUS", nama, {"keywords_backup": kw_backup})
        print(f"   ✅ Kategori '{nama}' dihapus (backup di riwayat).")
        return True

    # Tampilkan riwayat
    def tampilkan_riwayat(self, n: int = 30) -> None:
        if not self._riwayat:
            print("   ℹ️  Belum ada riwayat perubahan.")
            return
        tampil = self._riwayat[-n:]
        print(f"\n  📋 Riwayat ({len(tampil)} dari {len(self._riwayat)} total):")
        print(f"  {'No':<5} {'Waktu':<21} {'Aksi':<12} {'Nama':<32} Detail")
        print(f"  {'-'*100}")
        for i, e in enumerate(tampil, start=max(1, len(self._riwayat) - n + 1)):
            detail_str = json.dumps(e.get("detail", {}), ensure_ascii=False)
            if len(detail_str) > 45:
                detail_str = detail_str[:42] + "..."
            print(f"  {i:<5} {e['waktu']:<21} {e['aksi']:<12} {e['nama']:<32} {detail_str}")
        print(f"\n  💾 Riwayat: {self._riwayat_path}")

    def ke_dict(self) -> dict:
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
    cfg = {"kata_gresik": DEFAULT_KATA_GRESIK,
           "kategori_mapping": DEFAULT_KATEGORI_MAPPING}
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
    opt.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
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
            Object.defineProperty(navigator, 'languages',
                {get: () => ['id-ID','id','en-US','en']});
        """
    })
    driver.set_page_load_timeout(45)
    driver.implicitly_wait(FAST_WAIT)

CHROMEDRIVER = os.path.join(BASE_DIR, "chromedriver.exe")

def buat_browser(headless=True):
    opt = _buat_options(headless)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=opt)
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
        "button[aria-label='close']", "button[class*='close']",
        "[data-testid='btnCloseModal']", "button[data-testid*='close']",
        "[class*='modal'] button", "div[class*='dismiss']",
        "button[aria-label='Close']",
    ]:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    el.click()
                    time.sleep(0.3)
        except: pass
    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.4)
    except: pass

def scroll_halaman(driver, jumlah=10, jeda_antar=0.25):
    for i in range(jumlah):
        driver.execute_script(f"window.scrollBy(0, {550 + i * 40});")
        time.sleep(jeda_antar)
    driver.execute_script("window.scrollBy(0, -300);")
    time.sleep(0.4)

def ada_gresik(teks, kata_gresik):
    t = (teks or "").lower()
    return any(k in t for k in kata_gresik)

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

def standarisasi_kategori_fallback(teks, kategori_mapping):
    """Dipakai hanya jika kategori tidak berhasil diambil dari website."""
    t = (teks or "").lower()
    for kat, kw_list in kategori_mapping.items():
        if any(kw in t for kw in kw_list): return kat
    return "Lainnya"

def deteksi_badge_teks(teks):
    t = (teks or "").lower()
    for b in TOKOPEDIA_BADGE:
        if b in t: return b.title()
    return "-"

def debug_simpan(driver, nama):
    try:
        png  = os.path.join(OUTPUT_DIR, f"debug_{nama}.png")
        html = os.path.join(OUTPUT_DIR, f"debug_{nama}.html")
        driver.save_screenshot(png)
        with open(html, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"   🔍 Debug: output/debug_{nama}.png + .html disimpan")
    except: pass


# ══════════════════════════════════════════════════════
# AMBIL NAMA PRODUK DARI ELEMEN LINK / CARD
# ══════════════════════════════════════════════════════
def ambil_nama_dari_link(driver, a_el):
    # 1. title attribute
    try:
        t = (a_el.get_attribute("title") or "").strip()
        if t and len(t) > 5:
            return t
    except: pass

    # 2. teks langsung
    try:
        t = a_el.text.strip()
        if t and len(t) > 5:
            return t[:200]
    except: pass

    # 3. cari di parent card via JS
    try:
        parent = driver.execute_script(
            "return arguments[0].closest("
            "'[data-testid*=\"product\"],[class*=\"ProductCard\"],"
            "[class*=\"product-card\"],[class*=\"prd_link\"]')",
            a_el
        )
        if parent:
            for sel in NAMA_PRODUK_SEL:
                try:
                    el = parent.find_element(By.CSS_SELECTOR, sel)
                    t = el.text.strip()
                    if t and len(t) > 5: return t[:200]
                except: pass
            try:
                inner = parent.text or ""
                kandidat = [b.strip() for b in inner.split("\n")
                            if b.strip() and len(b.strip()) > 8
                            and not baris_skip(b.strip())]
                if kandidat:
                    return max(kandidat, key=len)[:200]
            except: pass
    except: pass

    return ""


# ══════════════════════════════════════════════════════
# AMBIL KATEGORI LANGSUNG DARI TOKOPEDIA (BREADCRUMB PDP)
# ══════════════════════════════════════════════════════
# Teks yang harus diabaikan dari breadcrumb
BREADCRUMB_SKIP = {
    "beranda", "home", "semua kategori", "all categories", "tokopedia", ""
}

def _ambil_kategori_dari_breadcrumb(driver):
    """
    Mengambil kategori produk dari breadcrumb halaman PDP Tokopedia.
    Breadcrumb format: Beranda > Kategori Utama > Sub-kategori > [Nama Produk]
    Kita ambil level 2 (Kategori Utama) atau level 3 (Sub-kategori).

    Mengembalikan tuple: (kategori_utama, sub_kategori)
    """
    kategori_utama = ""
    sub_kategori   = ""

    for sel in PDP_KATEGORI_SEL:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if not els:
                continue

            teks_list = []
            for el in els:
                t = el.text.strip()
                if t and t.lower() not in BREADCRUMB_SKIP:
                    teks_list.append(t)

            # Breadcrumb: [Kat Utama, Sub-kat, ...] — buang item terakhir
            # kalau itu mirip nama produk (panjang > 40 karakter)
            if teks_list and len(teks_list[-1]) > 40:
                teks_list = teks_list[:-1]

            if len(teks_list) >= 2:
                kategori_utama = teks_list[0]
                sub_kategori   = teks_list[1]
                return kategori_utama, sub_kategori
            elif len(teks_list) == 1:
                kategori_utama = teks_list[0]
                return kategori_utama, ""
        except: pass

    # Fallback: cari teks breadcrumb via JSON-LD (structured data Tokopedia)
    try:
        scripts = driver.find_elements(By.CSS_SELECTOR, "script[type='application/ld+json']")
        for sc in scripts:
            try:
                data = json.loads(sc.get_attribute("innerHTML") or "")
                # BreadcrumbList
                if data.get("@type") == "BreadcrumbList":
                    items = data.get("itemListElement", [])
                    # items: [{position, name, item}]
                    breadcrumbs = [
                        it["name"] for it in items
                        if it.get("name", "").lower() not in BREADCRUMB_SKIP
                    ]
                    # Buang item terakhir kalau panjang (kemungkinan nama produk)
                    if breadcrumbs and len(breadcrumbs[-1]) > 40:
                        breadcrumbs = breadcrumbs[:-1]
                    if len(breadcrumbs) >= 2:
                        return breadcrumbs[0], breadcrumbs[1]
                    elif len(breadcrumbs) == 1:
                        return breadcrumbs[0], ""
                # Product dengan breadcrumb embedded
                if data.get("@type") == "Product":
                    kat = data.get("category", "")
                    if kat:
                        parts = [p.strip() for p in kat.split(">") if p.strip()]
                        if len(parts) >= 2:
                            return parts[0], parts[1]
                        elif parts:
                            return parts[0], ""
            except: pass
    except: pass

    return kategori_utama, sub_kategori


# ══════════════════════════════════════════════════════
# AMBIL NAMA TOKO DARI PDP
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
    # Prioritas 1: link ke /shop/
    for sel in ["a[href*='/shop/']", "a[data-testid='llbShopNameLink']"]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                t    = el.text.strip()
                href = el.get_attribute("href") or ""
                if _teks_valid_nama_toko(t) and "tokopedia.com" in href:
                    return t, href
        except: pass

    # Prioritas 2: selector class
    for sel in PDP_TOKO_SEL:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                t = el.text.strip()
                if not _teks_valid_nama_toko(t):
                    continue
                href = ""
                try:
                    href = el.get_attribute("href") or ""
                    if href and "tokopedia.com" not in href:
                        href = ""
                except: pass
                if not href:
                    try:
                        a = el.find_element(By.TAG_NAME, "a")
                        href = a.get_attribute("href") or ""
                    except: pass
                return t, href
        except: pass

    # Prioritas 3: scan semua <a> ke /shop/
    try:
        for el in driver.find_elements(By.TAG_NAME, "a"):
            href = el.get_attribute("href") or ""
            if "/shop/" not in href or "tokopedia.com" not in href:
                continue
            t = el.text.strip()
            if _teks_valid_nama_toko(t):
                return t, href
    except: pass

    return "-", "-"


# ══════════════════════════════════════════════════════
# LANGKAH 1: Buka Tokopedia, cari URL listing toko Gresik
# ══════════════════════════════════════════════════════
CANDIDATE_URLS = [
    "https://www.tokopedia.com/search?q=gresik&st=shop&location=Kab.+Gresik",
    "https://www.tokopedia.com/search?q=gresik&navsource=&st=shop&ob=23&location=Kab.+Gresik",
    "https://www.tokopedia.com/search?q=gresik&st=shop&shop_location=Kab.+Gresik",
    "https://www.tokopedia.com/search?q=&st=shop&location=Kab.+Gresik",
    "https://www.tokopedia.com/search?q=toko&st=shop&location=Gresik",
    "https://www.tokopedia.com/search?q=gresik&st=shop",
]

def _url_punya_toko(driver, url, kata_gresik):
    buka(driver, url)
    time.sleep(4)
    tutup_popup(driver)
    scroll_halaman(driver, jumlah=5, jeda_antar=0.2)

    body = driver.find_element(By.TAG_NAME, "body").text
    # Cek ada konten toko dan ada kata Gresik
    ada_toko = (
        "toko" in body.lower()
        or len(driver.find_elements(By.CSS_SELECTOR,
               "[data-testid='divShopCard'],[data-testid='shop-card'],"
               "div[class*='ShopCard'],div[class*='shop-card']")) >= 2
    )
    return ada_gresik(body, kata_gresik) and ada_toko

def aktifkan_filter(driver, kata_gresik):
    print("\n📍 Mencari URL listing toko Gresik di Tokopedia...")

    for url in CANDIDATE_URLS:
        print(f"   Coba: {url[:75]}...", end=" ", flush=True)
        try:
            ada = _url_punya_toko(driver, url, kata_gresik)
        except Exception as e:
            print(f"❌ error ({e})")
            continue
        if ada:
            print(f"✅")
            return driver.current_url  # URL aktual setelah redirect
        else:
            print("⬜")

    # Coba klik filter manual
    print("\n   Coba klik filter sidebar Gresik...")
    return _coba_filter_sidebar(driver, kata_gresik)

def _coba_filter_sidebar(driver, kata_gresik):
    buka(driver, "https://www.tokopedia.com/search?q=gresik&st=shop")
    time.sleep(5)
    tutup_popup(driver)
    scroll_halaman(driver, jumlah=8, jeda_antar=0.15)

    target = ["kab. gresik", "kab.gresik", "kabupaten gresik", "gresik"]

    # Klik "lihat selengkapnya" di filter lokasi kalau ada
    for xpath in [
        "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
        "'abcdefghijklmnopqrstuvwxyz'),'lihat selengkapnya')]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    driver.execute_script("arguments[0].click()", el)
                    time.sleep(1)
        except: pass

    for xpath in [
        "//*[contains(translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//*[translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='gresik']",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                t = el.text.strip().lower()
                if el.is_displayed() and any(k in t for k in target):
                    print(f"   ✅ Filter: '{el.text.strip()}'")
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'})", el)
                    try: el.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click()", el)
                    time.sleep(4)
                    return driver.current_url
        except: pass

    print("   ⚠  Filter tidak ditemukan, lanjut tanpa filter.")
    return "https://www.tokopedia.com/search?q=gresik&st=shop"


# ══════════════════════════════════════════════════════
# LANGKAH 2: Kumpulkan URL produk dari listing toko
# ══════════════════════════════════════════════════════
MAX_RETRY = 3

def _scrape_satu_halaman(driver, url, kata_gresik, semua, halaman_ke, debug=False):
    buka(driver, url)
    time.sleep(3)
    tutup_popup(driver)
    scroll_halaman(driver, jumlah=12, jeda_antar=0.2)
    baru = 0

    # ── Strategi 1: Cari kartu produk via selector ────────────────────────────
    for sel in CARD_SELECTORS:
        cards = driver.find_elements(By.CSS_SELECTOR, sel)
        if len(cards) < 2:
            continue
        print(f"      → Selector '{sel}': {len(cards)} kartu")

        for card in cards:
            try:
                teks = card.text.strip()
                if not teks: continue

                url_prod = ""
                nama     = ""

                for a in card.find_elements(By.TAG_NAME, "a"):
                    try:
                        h = a.get_attribute("href") or ""
                        # URL produk Tokopedia: domain.com/shopname/produk
                        if ("tokopedia.com/" in h
                                and "/shop/" not in h
                                and "/search" not in h
                                and len(h) > 30):
                            url_prod_cand = h.split("?")[0].rstrip("/")
                            if url_prod_cand in semua:
                                continue
                            nama_cand = ambil_nama_dari_link(driver, a)
                            if nama_cand:
                                url_prod = url_prod_cand
                                nama     = nama_cand
                                break
                            elif not url_prod:
                                url_prod = url_prod_cand
                    except: pass

                if not url_prod or url_prod in semua:
                    continue

                if not nama:
                    nama = ambil_teks_el(card, *NAMA_PRODUK_SEL)
                if not nama:
                    for l in teks.split("\n"):
                        l = l.strip()
                        if l and not baris_skip(l) and len(l) > 8:
                            nama = l[:200]
                            break
                if not nama:
                    nama = f"(produk-{url_prod.split('/')[-1][:30]})"

                harga   = ambil_teks_el(card, *HARGA_SEL)
                lokasi  = ambil_teks_el(card, *LOKASI_SEL)
                terjual = ambil_teks_el(card, *TERJUAL_SEL)
                rating  = ambil_teks_el(card, *RATING_SEL)

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
                    "badge"         : deteksi_badge_teks(teks),
                    # Diisi saat PDP
                    "nama_toko"     : "-",
                    "url_toko"      : "-",
                    "rating_toko"   : "-",
                    "kategori_web"  : "",   # dari breadcrumb Tokopedia
                    "sub_kategori"  : "",
                }
                baru += 1
            except StaleElementReferenceException: pass
            except WebDriverException: raise
            except: pass

        if baru > 0:
            break

    # ── Strategi 2: Fallback scan semua <a> ──────────────────────────────────
    if baru == 0:
        seen_s2 = set()
        try:
            semua_a = driver.find_elements(By.TAG_NAME, "a")
        except: semua_a = []

        print(f"      → Fallback: {len(semua_a)} elemen <a>")

        for a_el in semua_a:
            try:
                h = a_el.get_attribute("href") or ""
                if ("tokopedia.com/" not in h
                        or "/shop/" in h
                        or "/search" in h
                        or len(h) < 30):
                    continue
                url_prod = h.split("?")[0].rstrip("/")
                if url_prod in semua or url_prod in seen_s2:
                    continue
                seen_s2.add(url_prod)

                nama = ambil_nama_dari_link(driver, a_el)
                if not nama or len(nama) < 5:
                    # Ambil dari slug terakhir URL
                    slug = url_prod.rstrip("/").split("/")[-1]
                    slug_clean = slug.replace("-", " ").strip()
                    if len(slug_clean) < 5:
                        continue
                    nama = slug_clean[:200]

                semua[url_prod] = {
                    "url_produk"   : url_prod,
                    "nama_produk"  : nama,
                    "harga"        : "-",
                    "lokasi_seller": "Kab. Gresik",
                    "rating_produk": "-",
                    "terjual"      : "-",
                    "badge"        : "-",
                    "nama_toko"    : "-",
                    "url_toko"     : "-",
                    "rating_toko"  : "-",
                    "kategori_web" : "",
                    "sub_kategori" : "",
                }
                baru += 1
            except WebDriverException: raise
            except: pass

    if baru == 0 and debug:
        debug_simpan(driver, f"hal{halaman_ke}")
        try:
            hrefs = [a.get_attribute("href") or ""
                     for a in driver.find_elements(By.TAG_NAME, "a")[:50]]
            toped = [h for h in hrefs if "tokopedia" in h][:5]
            print(f"      🔍 Sampel href: {toped}")
        except: pass

    return baru

def kumpulkan_url_produk(driver, url_filter, kata_gresik,
                         headless=True, debug=False):
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

        for percobaan in range(1, MAX_RETRY + 1):
            try:
                baru = _scrape_satu_halaman(
                    driver, url, kata_gresik, semua,
                    halaman_ke=hal, debug=debug
                )
                break
            except Exception as e:
                print(f"   ⚠  Browser error (percobaan {percobaan}/{MAX_RETRY}): "
                      f"{type(e).__name__} — restart...")
                try: driver.quit()
                except: pass
                time.sleep(2)
                driver = buat_browser(headless=headless)
                if percobaan == MAX_RETRY:
                    print(f"   ❌ Hal {hal} dilewati.")
                    baru = 0

        print(f"   Hasil: +{baru} produk baru | Total: {len(semua)}")
        kosong_str = 0 if baru > 0 else kosong_str + 1
        if kosong_str >= 3:
            print("   3x halaman kosong → selesai.")
            break
        jeda()

    return list(semua.values()), driver


# ══════════════════════════════════════════════════════
# LANGKAH 3: Buka PDP paralel — ambil nama toko + KATEGORI DARI WEB
# ══════════════════════════════════════════════════════
def _ambil_satu_pdp(url, headless):
    driver = None
    hasil = {
        "nama_toko"    : "-",
        "url_toko"     : "-",
        "rating_toko"  : "-",
        "rating_produk": "-",
        "terjual"      : "-",
        "kategori_web" : "",   # kategori utama dari breadcrumb Tokopedia
        "sub_kategori" : "",   # sub-kategori dari breadcrumb Tokopedia
        "badge"        : "-",
    }
    try:
        driver = buat_browser(headless=headless)
        buka(driver, url)
        time.sleep(2)
        tutup_popup(driver)
        driver.execute_script("window.scrollBy(0, 500)")
        time.sleep(0.6)

        # ── Nama & URL toko ──────────────────────────────────────────────────
        nama_toko, url_toko = _ambil_nama_toko_dari_pdp(driver)
        hasil["nama_toko"] = nama_toko
        hasil["url_toko"]  = url_toko

        # ── Kategori LANGSUNG dari breadcrumb Tokopedia ──────────────────────
        kat_utama, sub_kat = _ambil_kategori_dari_breadcrumb(driver)
        hasil["kategori_web"] = kat_utama
        hasil["sub_kategori"] = sub_kat

        # ── Rating toko ──────────────────────────────────────────────────────
        hasil["rating_toko"] = bersihkan_rating(
            ambil_teks_driver(driver, *PDP_RATING_TOKO_SEL)
        )

        # ── Rating produk ─────────────────────────────────────────────────────
        hasil["rating_produk"] = bersihkan_rating(
            ambil_teks_driver(driver, *PDP_RATING_PRODUK_SEL)
        )

        # ── Terjual ───────────────────────────────────────────────────────────
        hasil["terjual"] = bersihkan_terjual(
            ambil_teks_driver(driver, *PDP_TERJUAL_SEL)
        )

        # ── Badge ─────────────────────────────────────────────────────────────
        badge_teks = ambil_teks_driver(driver, *PDP_BADGE_SEL)
        if not badge_teks:
            badge_teks = driver.find_element(By.TAG_NAME, "body").text
        hasil["badge"] = deteksi_badge_teks(badge_teks)

        return url, hasil
    except Exception:
        return url, hasil
    finally:
        if driver:
            try: driver.quit()
            except: pass

def ambil_info_pdp_paralel(produk_list, workers, headless):
    total = len(produk_list)
    url_ke_item = {p["url_produk"]: p for p in produk_list
                   if p.get("url_produk", "-") != "-"}
    urls = list(url_ke_item.keys())

    print(f"\n🏪 Ambil info PDP (toko + kategori web) — "
          f"{total} produk, {workers} browser paralel...")

    selesai = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_ambil_satu_pdp, u, headless): u for u in urls
        }
        for future in as_completed(future_map):
            url, hasil = future.result()
            item = url_ke_item[url]
            item["nama_toko"]    = hasil["nama_toko"]
            item["url_toko"]     = hasil["url_toko"]
            item["rating_toko"]  = hasil["rating_toko"]
            item["kategori_web"] = hasil["kategori_web"]
            item["sub_kategori"] = hasil["sub_kategori"]
            if item.get("badge", "-") == "-":
                item["badge"] = hasil["badge"]
            if item.get("rating_produk", "-") == "-":
                item["rating_produk"] = hasil["rating_produk"]
            if item.get("terjual", "-") == "-":
                item["terjual"] = hasil["terjual"]

            selesai += 1
            if selesai % 10 == 0 or selesai == total:
                dapat_toko = sum(1 for p in produk_list if p["nama_toko"] != "-")
                dapat_kat  = sum(1 for p in produk_list if p.get("kategori_web"))
                print(f"   [{selesai:>4}/{total}] selesai "
                      f"| toko: {dapat_toko} | kategori web: {dapat_kat}")

    dapat_toko = sum(1 for p in produk_list if p["nama_toko"] != "-")
    dapat_kat  = sum(1 for p in produk_list if p.get("kategori_web"))
    print(f"\n   ✅ Nama toko: {dapat_toko}/{total} "
          f"| Kategori dari web: {dapat_kat}/{total}")
    return produk_list


# ══════════════════════════════════════════════════════
# SIMPAN CSV
# ══════════════════════════════════════════════════════
def simpan_csv(data_list, kategori_mapping):
    if not data_list:
        print("\n⚠  Tidak ada data.")
        return None

    df = pd.DataFrame(data_list)

    # Kolom kategori: utamakan dari web, fallback ke keyword mapping
    def tentukan_kategori(row):
        if row.get("kategori_web"):
            return row["kategori_web"]
        return standarisasi_kategori_fallback(
            row.get("nama_produk", ""), kategori_mapping)

    def tentukan_sub(row):
        return row.get("sub_kategori", "") or ""

    df["kategori"]    = df.apply(tentukan_kategori, axis=1)
    df["sub_kategori"] = df.apply(tentukan_sub, axis=1)
    df["platform"]    = "Tokopedia"
    df["waktu_scrape"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    df = df.drop_duplicates(subset=["url_produk"])

    kolom = [
        "nama_toko", "url_toko", "rating_toko",
        "nama_produk", "harga", "rating_produk", "terjual",
        "lokasi_seller", "kategori", "sub_kategori", "badge",
        "url_produk", "platform", "waktu_scrape",
    ]
    df_out = df[[c for c in kolom if c in df.columns]]
    df_out.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    # Ringkasan per toko
    file_toko = os.path.join(OUTPUT_DIR, "toko_gresik_tokopedia_per_toko.csv")
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

    # Ringkasan per lokasi
    file_lokasi = os.path.join(OUTPUT_DIR, "toko_gresik_tokopedia_per_lokasi.csv")
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

    # Ringkasan per kategori
    file_kat = os.path.join(OUTPUT_DIR, "toko_gresik_tokopedia_per_kategori.csv")
    grp_kat = (
        df.groupby(["kategori", "sub_kategori"])
        .agg(
            jumlah_produk =("nama_produk", "count"),
            jumlah_toko   =("nama_toko",   lambda x: x[x != "-"].nunique()),
        )
        .reset_index()
        .sort_values("jumlah_produk", ascending=False)
    )
    grp_kat.to_csv(file_kat, index=False, encoding="utf-8-sig")

    # Statistik coverage kategori dari web
    dari_web    = int((df["kategori_web"] != "").sum()) if "kategori_web" in df.columns else 0
    dari_fallbk = len(df) - dari_web

    print(f"\n{'='*64}")
    print(f"  HASIL SCRAPING TOKO GRESIK DI TOKOPEDIA v2")
    print(f"{'='*64}")
    print(f"  📦 Total produk unik      : {len(df)}")
    print(f"  🏪 Total toko unik        : {df[df['nama_toko'] != '-']['nama_toko'].nunique()}")
    print(f"  📍 Wilayah Gresik         : {df['lokasi_seller'].nunique()}")
    print(f"  🏷️  Kategori terdeteksi   : {df['kategori'].nunique()}")
    print(f"  🌐 Kategori dari web      : {dari_web} produk")
    print(f"  🔄 Kategori fallback KW   : {dari_fallbk} produk")
    if "badge" in df.columns:
        bc = df[df["badge"] != "-"]["badge"].value_counts()
        if not bc.empty: print(f"  🏅 Badge Tokopedia        : {bc.to_dict()}")
    print(f"  💾 Detail produk          → output/toko_gresik_tokopedia.csv")
    print(f"  💾 Per toko               → output/toko_gresik_tokopedia_per_toko.csv")
    print(f"  💾 Per lokasi             → output/toko_gresik_tokopedia_per_lokasi.csv")
    print(f"  💾 Per kategori           → output/toko_gresik_tokopedia_per_kategori.csv")
    print(f"{'='*64}")

    print(f"\n  SAMPEL (20 produk pertama):\n")
    for _, r in df.head(20).iterrows():
        badge = f"[{r.get('badge','-')}] " if r.get("badge", "-") != "-" else ""
        sub   = f" / {r['sub_kategori']}" if r.get("sub_kategori") else ""
        print(f"  🏪 {str(r.get('nama_toko','-'))[:20]:<20} | "
              f"{badge}{r['nama_produk'][:35]:<35} | "
              f"{r['harga']} | {r['kategori']}{sub}")

    return df


# ══════════════════════════════════════════════════════
# EKSPOR DASHBOARD JSON
# ══════════════════════════════════════════════════════
def ekspor_dashboard(df, kata_gresik, kategori_mapping):
    if df is None or df.empty:
        data = {
            "platform"         : "Tokopedia",
            "keywords"         : kata_gresik,
            "kategori_tersedia": list(kategori_mapping.keys()),
            "badge_tokopedia"  : TOKOPEDIA_BADGE,
            "ringkasan"        : {},
            "data_toko"        : [],
            "produk"           : [],
        }
    else:
        data_toko = []
        toko_cols = ["nama_toko", "lokasi_seller", "url_toko", "rating_toko"]
        for keys, grp in df.groupby(toko_cols):
            nama_toko, lokasi, url_toko, rating_toko = keys
            if nama_toko == "-": continue
            produk_toko = grp[[
                "nama_produk", "harga", "kategori", "sub_kategori",
                "badge", "rating_produk", "terjual", "url_produk"
            ]].to_dict(orient="records")
            data_toko.append({
                "nama_toko"       : nama_toko,
                "lokasi"          : lokasi,
                "url_toko"        : url_toko,
                "rating_toko"     : rating_toko,
                "jumlah_produk"   : len(grp),
                "kategori_dijual" : sorted(grp["kategori"].unique().tolist()),
                "badge"           : grp["badge"].mode()[0]
                                    if not grp["badge"].empty else "-",
                "produk"          : produk_toko,
            })
        data_toko.sort(key=lambda x: x["jumlah_produk"], reverse=True)

        # Kategori yang ditemukan dari web (bukan fallback)
        dari_web = {}
        if "kategori_web" in df.columns:
            dari_web = (
                df[df["kategori_web"] != ""]
                .groupby(["kategori_web", "sub_kategori"])
                .size()
                .reset_index(name="count")
                .to_dict(orient="records")
            )

        ringkasan = {
            "total_produk"          : len(df),
            "total_toko"            : len(data_toko),
            "per_kategori"          : df["kategori"].value_counts().to_dict(),
            "per_sub_kategori"      : df["sub_kategori"].value_counts().to_dict()
                                      if "sub_kategori" in df.columns else {},
            "per_lokasi"            : df["lokasi_seller"].value_counts().to_dict(),
            "per_badge"             : (df[df["badge"] != "-"]["badge"]
                                       .value_counts().to_dict()
                                       if "badge" in df.columns else {}),
            "kategori_dari_web"     : dari_web,
            "coverage_kategori_web" : int((df.get("kategori_web", "") != "").sum()),
            "waktu_ekspor"          : datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        data = {
            "platform"          : "Tokopedia",
            "keywords"          : kata_gresik,
            "kategori_tersedia" : list(kategori_mapping.keys()),
            "badge_tokopedia"   : TOKOPEDIA_BADGE,
            "ringkasan"         : ringkasan,
            "data_toko"         : data_toko,
            "produk"            : df.to_dict(orient="records"),
        }

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  📊 Dashboard JSON         → output/dashboard_data_tokopedia.json")


# ══════════════════════════════════════════════════════
# ARGUMEN CLI
# ══════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(
        description="Scraper toko Gresik di Tokopedia v2",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
CONTOH PENGGUNAAN:
  # Scraping biasa
  python tokopedia_gresik_v2.py
  python tokopedia_gresik_v2.py --url "https://www.tokopedia.com/search?q=gresik&st=shop"
  python tokopedia_gresik_v2.py --headful --debug --workers 3
  python tokopedia_gresik_v2.py --no-pdp   # skip PDP, hanya listing

  # CRUD Kategori (keyword fallback)
  python tokopedia_gresik_v2.py --tambah-kat "Pertanian" --kw "pupuk,bibit,cangkul"
  python tokopedia_gresik_v2.py --tambah-kw "Makanan & Minuman" --kw "jamu,wedang"
  python tokopedia_gresik_v2.py --hapus-kw "Elektronik" --kw "elektronik"
  python tokopedia_gresik_v2.py --edit-kat "Lainnya|Produk Umum"
  python tokopedia_gresik_v2.py --hapus-kat "Hobi & Koleksi"
  python tokopedia_gresik_v2.py --lihat-kat
  python tokopedia_gresik_v2.py --lihat-kat "Elektronik"
  python tokopedia_gresik_v2.py --riwayat
"""
    )

    # Scraping
    p.add_argument("--keywords", type=str, default="",
                   help="Keyword lokasi tambahan, pisah koma")
    p.add_argument("--config",   type=str, default=CONFIG_FILE_DEF,
                   help="Path file konfigurasi JSON")
    p.add_argument("--url",      type=str, default="",
                   help="URL filter Tokopedia langsung (skip langkah aktifkan_filter)")
    p.add_argument("--workers",  type=int, default=DEFAULT_WORKERS,
                   help=f"Browser paralel untuk PDP (default {DEFAULT_WORKERS})")
    p.add_argument("--headful",  action="store_true",
                   help="Tampilkan browser (nonaktifkan headless)")
    p.add_argument("--debug",    action="store_true",
                   help="Screenshot + page source saat 0 produk ditemukan")
    p.add_argument("--no-pdp",   action="store_true",
                   help="Skip tahap PDP (hanya data listing, tanpa nama toko & kategori web)")

    # CRUD Kategori
    grp = p.add_argument_group("CRUD Kategori Fallback")
    grp.add_argument("--tambah-kat", type=str, default="", metavar="NAMA")
    grp.add_argument("--hapus-kat",  type=str, default="", metavar="NAMA")
    grp.add_argument("--edit-kat",   type=str, default="", metavar="LAMA|BARU")
    grp.add_argument("--tambah-kw",  type=str, default="", metavar="NAMA")
    grp.add_argument("--hapus-kw",   type=str, default="", metavar="NAMA")
    grp.add_argument("--kw",         type=str, default="", metavar="KW1,KW2,...")
    grp.add_argument("--lihat-kat",  type=str, default=None,
                     nargs="?", const="__semua__", metavar="NAMA")
    grp.add_argument("--riwayat",    action="store_true")
    grp.add_argument("--riwayat-n",  type=int, default=30, metavar="N")

    return p.parse_args()


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
def main():
    args     = parse_args()
    headless = not args.headful

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SCRAPER TOKO GRESIK DI TOKOPEDIA — v2                     ║")
    print(f"║   Mulai : {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                              ║")
    print(f"║   Mode  : {'HEADLESS' if headless else 'HEADFUL':<10} | Workers PDP: {args.workers:<3}              ║")
    print("║   Kategori : LANGSUNG dari breadcrumb Tokopedia              ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")

    if args.debug:
        print("   🔍 MODE DEBUG AKTIF\n")

    cfg         = muat_konfigurasi(args.config)
    cfg         = gabungkan_keyword_cli(cfg, args.keywords)
    kata_gresik = [k.lower() for k in cfg["kata_gresik"]]
    kat_mgr     = KategoriManager(
        cfg.get("kategori_mapping", DEFAULT_KATEGORI_MAPPING),
        riwayat_path=RIWAYAT_FILE,
    )

    # ── CRUD ────────────────────────────────────────────────────────────────
    crud_dilakukan = False

    if args.riwayat:
        kat_mgr.tampilkan_riwayat(n=args.riwayat_n)
        return

    if args.lihat_kat is not None:
        kat_mgr.lihat_kategori(None if args.lihat_kat == "__semua__" else args.lihat_kat)
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
            print("   ❌ Format: 'Nama Lama|Nama Baru'")
        crud_dilakukan = True

    if args.tambah_kw:
        kat_mgr.tambah_keyword(args.tambah_kw,
                               [k.strip() for k in args.kw.split(",") if k.strip()])
        crud_dilakukan = True

    if args.hapus_kw:
        kat_mgr.hapus_keyword(args.hapus_kw,
                              [k.strip() for k in args.kw.split(",") if k.strip()])
        crud_dilakukan = True

    if crud_dilakukan:
        cfg["kategori_mapping"] = kat_mgr.ke_dict()
        simpan_konfigurasi(args.config, cfg)
        print(f"\n  💾 Config disimpan  : {args.config}")
        print(f"  📋 Riwayat          : {RIWAYAT_FILE}")
        if not args.url and not args.keywords:
            return

    kategori_mapping = kat_mgr.ke_dict()

    print(f"  🔑 Keyword aktif  ({len(kata_gresik)}): {', '.join(kata_gresik)}")
    print(f"  🏷️  Kategori fallback ({len(kategori_mapping)}): "
          f"{', '.join(list(kategori_mapping.keys())[:5])}...")
    print(f"  🌐 Kategori utama  : diambil LANGSUNG dari breadcrumb Tokopedia\n")

    cfg["kata_gresik"]      = kata_gresik
    cfg["kategori_mapping"] = kategori_mapping
    simpan_konfigurasi(args.config, cfg)

    # ── Scraping ─────────────────────────────────────────────────────────────
    driver = buat_browser(headless=headless)
    produk = []

    try:
        url_filter = args.url or aktifkan_filter(driver, kata_gresik)
        if not url_filter:
            print("\n❌ Gagal mendapatkan URL filter.")
            print("   Coba: python tokopedia_gresik_v2.py --headful")
            print("   Atau: python tokopedia_gresik_v2.py --url \"<URL>\"")
            return

        print(f"\n   ✅ URL filter: {url_filter[:100]}...")

        produk, driver = kumpulkan_url_produk(
            driver, url_filter, kata_gresik,
            headless=headless, debug=args.debug
        )

        if not produk:
            print("\n❌ Tidak ada produk ditemukan.")
            print("\n💡 SOLUSI:")
            print("   1. python tokopedia_gresik_v2.py --headful --debug")
            print("   2. python tokopedia_gresik_v2.py --url \"<URL filter Gresik>\"")
            ekspor_dashboard(None, kata_gresik, kategori_mapping)
            return

        # Backup listing
        backup = os.path.join(OUTPUT_DIR,
                              "toko_gresik_tokopedia_listing_backup.csv")
        pd.DataFrame(produk).to_csv(backup, index=False, encoding="utf-8-sig")
        print(f"\n   💾 Backup listing → output/toko_gresik_tokopedia_listing_backup.csv")

    except KeyboardInterrupt:
        print("\n\n⏹ Dihentikan saat listing.")
    finally:
        try: driver.quit()
        except: pass

    if produk and not args.no_pdp:
        try:
            produk = ambil_info_pdp_paralel(
                produk, workers=args.workers, headless=headless
            )
        except KeyboardInterrupt:
            print("\n\n⏹ Dihentikan saat PDP.")
    elif args.no_pdp:
        print("\n   ⏩ Skip PDP (--no-pdp aktif)")

    df = simpan_csv(produk, kategori_mapping)
    ekspor_dashboard(df, kata_gresik, kategori_mapping)
    print(f"\n✅ Selesai! Semua file → folder output/")


if __name__ == "__main__":
    main()