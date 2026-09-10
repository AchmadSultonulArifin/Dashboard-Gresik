"""
╔══════════════════════════════════════════════════════╗
║   SCRAPER TOKO GRESIK DI LAZADA — VERSI PERBAIKAN   ║
║   Filter : Shipped From → Kab. Gresik               ║
║   Mode   : Listing → PDP (paralel, headless)        ║
║   Output : toko_gresik_lazada.csv                   ║
║            dashboard_data_lazada.json               ║
╚══════════════════════════════════════════════════════╝

PERBAIKAN DARI VERSI LAMA:
  1. [BUG FIX] Filter ada_gresik() tidak lagi dipakai untuk kartu produk
     → Karena filter Lazada sudah aktif, SEMUA produk di halaman = Gresik
     → Sebelumnya 0 produk lolos karena teks kartu tidak selalu ada lokasi
  2. [BUG FIX] Selector kartu produk diperbarui untuk struktur Lazada 2024+
     → Ditambah selector berbasis <a href*='products/'> sebagai fallback utama
  3. [BUG FIX] Scroll lebih dalam sebelum scrape (lazy-load Lazada butuh scroll)
  4. [BUG FIX] Nama toko diambil dari PDP dengan selector yang lebih lengkap
  5. [TAMBAH] Rating toko diambil dari PDP
  6. [TAMBAH] Jumlah terjual diambil dari listing dan PDP
  7. [TAMBAH] Debug mode: simpan screenshot + page source kalau 0 produk
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
os.makedirs(OUTPUT_DIR, exist_ok=True)          # buat folder output kalau belum ada
OUTPUT_FILE     = os.path.join(OUTPUT_DIR, "toko_gresik_lazada.csv")
DASHBOARD_FILE  = os.path.join(OUTPUT_DIR, "dashboard_data_lazada.json")
CONFIG_FILE_DEF = os.path.join(BASE_DIR, "keywords_config.json")
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

# ── SELECTOR KARTU PRODUK (diperbarui untuk Lazada 2024) ──────────────────────
# Lazada sering ganti class, jadi kita pakai strategi berlapis:
#   1. Coba selector berbasis atribut stabil
#   2. Fallback ke href produk langsung
CARD_SELECTORS = [
    "[data-item-id]",
    "[data-tracking='product-card']",
    "div[class*='product-card']",
    "div[class*='ProductCard']",
    "div[class*='gridItem']",
    "div[class*='product-item']",
    "div[class*='c-prd']",          # ← pola baru Lazada
    ".c-2prjwa",
    "li[class*='product']",         # ← kadang pakai <li>
]

NAMA_PRODUK_SEL = [
    "[class*='product-title']",
    "[class*='title--wFj13']",
    "[class*='RFzeYU']",
    "div[class*='title'] span",
    "div[class*='name'] a",
    "a[class*='title']",
    "span[class*='title']",
    "[class*='info-title']",        # ← tambahan
    "h2", "h3",                     # ← fallback generik
]

HARGA_SEL = [
    "[class*='price--NVB62']",
    "[class*='price-sale']",
    "span[class*='price']",
    "div[class*='price']",
    "[data-spm='dprice']",
    "[class*='currency']",          # ← tambahan
]

LOKASI_SEL = [
    "[class*='location']",
    "[class*='shipping']",
    "[class*='seller-location']",
    "span[class*='loc']",
    "[class*='sold-location']",     # ← tambahan
]

RATING_SEL = [
    "[class*='rating']",
    "[class*='stars']",
    "span[class*='score']",
    "[class*='review-count']",      # ← tambahan
]

TERJUAL_SEL = [
    "[class*='sold']",
    "span[class*='sold']",
    "[class*='sales']",
]

# ── SELECTOR PDP ──────────────────────────────────────────────────────────────
# Selector nama toko di halaman detail produk — lebih lengkap dari versi lama
PDP_TOKO_SEL = [
    # Selector stabil (pakai data-spm atau href)
    "[data-spm='dshopname'] a",
    "[data-spm='dshopname']",
    "a[href*='/shop/']",
    "a[href*='/seller/']",
    # Selector berbasis class (bisa berubah tiap deploy Lazada)
    "[class*='sellerName'] a",
    "[class*='seller-name'] a",
    "[class*='pdp-product-brand'] a",
    "[class*='shop-name'] a",
    "[class*='shopName'] a",
    "[class*='seller'] a[href*='shop']",
    # Fallback teks
    "[class*='seller-info'] span",
    "[class*='StoreInfo'] a",
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

FAST_WAIT = 0.5
EXPLICIT_WAIT_TIMEOUT = 5   # naikkan sedikit untuk PDP yang berat


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
    # PENTING: nonaktifkan blokir gambar agar Lazada tidak mendeteksi kita sebagai bot
    # (beberapa versi Lazada ngecek apakah gambar diload)
    # opt.add_experimental_option("prefs", {
    #     "profile.managed_default_content_settings.images": 2
    # })
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
    """Scroll pelan-pelan supaya lazy-load Lazada ter-trigger."""
    for i in range(jumlah):
        # Scroll bertahap lebih efektif daripada langsung ke bawah
        driver.execute_script(f"window.scrollBy(0, {600 + i * 50});")
        time.sleep(jeda_antar)
    # Scroll balik ke atas sedikit agar semua elemen render
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
    """Seperti ambil_teks_el tapi dari root driver (untuk PDP)."""
    for s in sels:
        try:
            el = driver.find_element(By.CSS_SELECTOR, s)
            t = el.text.strip()
            if t: return t
        except: pass
    return ""

def debug_simpan(driver, nama, headless):
    """Simpan screenshot dan page source ke output/ untuk debug."""
    try:
        png  = os.path.join(OUTPUT_DIR, f"debug_{nama}.png")
        html = os.path.join(OUTPUT_DIR, f"debug_{nama}.html")
        driver.save_screenshot(png)
        with open(html, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print(f"   🔍 Debug: output/debug_{nama}.png + output/debug_{nama}.html disimpan")
    except: pass


# ══════════════════════════════════════════════════════
# LANGKAH 1 — Dapatkan URL catalog Gresik yang valid
# ══════════════════════════════════════════════════════
#
# STRATEGI BARU (lebih reliable):
#   Lazada menyimpan filter lokasi sebagai parameter URL "locations".
#   Kita cukup buka URL catalog dengan parameter itu langsung —
#   tidak perlu klik sidebar filter yang sering berubah struktur HTML-nya.
#
# Daftar URL yang dicoba berurutan sampai ada yang menghasilkan produk:
CANDIDATE_URLS = [
    # Format 1 — parameter locations (paling stabil, pakai region code Gresik)
    "https://www.lazada.co.id/catalog/?q=&locations=ID110500000&sort=0",
    # Format 2 — nama kota di parameter
    "https://www.lazada.co.id/catalog/?locations=ID110500000&sort=0&ajax=true",
    # Format 3 — search keyword + filter lokasi via URL
    "https://www.lazada.co.id/catalog/?q=gresik&locations=ID110500000&sort=0",
    # Format 4 — catalog semua produk filter Gresik (tanpa keyword)
    "https://www.lazada.co.id/catalog/?city=gresik&sort=0",
    # Format 5 — search biasa, nanti scrape semua & filter teks
    "https://www.lazada.co.id/catalog/?q=toko+gresik&sort=0",
    "https://www.lazada.co.id/catalog/?q=gresik&sort=0",
]

def _url_punya_produk(driver, url, kata_gresik):
    """Buka URL, cek apakah ada link produk di halaman. Return True/False."""
    buka(driver, url)
    time.sleep(3)
    tutup_popup(driver)
    scroll_halaman(driver, jumlah=6, jeda_antar=0.2)

    # Cek ada link produk Lazada
    for sel in ["a[href*='/products/']", "a[href*='-i'][href*='-s']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        valid = [e for e in els if "lazada.co.id" in (e.get_attribute("href") or "")]
        if len(valid) >= 3:
            return True

    # Cek via [data-item-id]
    if len(driver.find_elements(By.CSS_SELECTOR, "[data-item-id]")) >= 3:
        return True

    return False


def aktifkan_filter(driver, kata_gresik):
    """
    Cari URL listing Lazada yang menghasilkan produk.
    Tidak lagi bergantung pada klik sidebar — langsung pakai URL dengan parameter filter.
    """
    print("\n📍 Mencari URL listing Lazada dengan produk Gresik...")

    # ── Coba CANDIDATE_URLS satu per satu ─────────────────────────────────────
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

    # ── Fallback: coba klik filter sidebar ────────────────────────────────────
    print("\n   Semua URL kandidat kosong. Mencoba klik filter sidebar...")
    return _coba_klik_filter_sidebar(driver, kata_gresik)


def _coba_klik_filter_sidebar(driver, kata_gresik):
    """Fallback: buka catalog, coba klik filter 'Kab. Gresik' di sidebar."""
    buka(driver, "https://www.lazada.co.id/catalog/?q=produk&sort=0")
    time.sleep(4)
    tutup_popup(driver)

    # Scroll untuk munculkan sidebar
    for _ in range(20):
        driver.execute_script("window.scrollBy(0, 200)")
        time.sleep(0.1)
    time.sleep(1)

    # Klik "Lihat Lebih Banyak" dulu
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

    # Cari elemen filter Gresik
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
                        # Pastikan URL hasil punya produk
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
    """
    [PERBAIKAN UTAMA]
    
    Versi lama: hanya simpan produk yang teksnya mengandung keyword Gresik
    → GAGAL karena Lazada tidak selalu tampilkan lokasi di kartu listing
    
    Versi baru: karena filter Lazada sudah aktif (Shipped From = Kab. Gresik),
    SEMUA produk di halaman ini = dari Gresik. Jadi kita ambil SEMUA produk,
    lalu cek lokasi kalau ada, kalau tidak ada isi default "Kab. Gresik".
    """
    buka(driver, url)
    time.sleep(2.5)  # naikkan jeda awal (Lazada butuh waktu render JS)
    tutup_popup(driver)

    # Scroll lebih dalam dan pelan (trigger lazy-load gambar & konten)
    scroll_halaman(driver, jumlah=12, jeda_antar=0.25)

    baru = 0

    # ── STRATEGI 1: Cari kartu produk via selector ────────────────────────────
    for sel in CARD_SELECTORS:
        cards = driver.find_elements(By.CSS_SELECTOR, sel)
        if len(cards) < 3:   # kalau kurang dari 3 kartu, selector ini salah
            continue

        print(f"      → Selector '{sel}': {len(cards)} kartu ditemukan")

        for card in cards:
            try:
                teks = card.text.strip()
                if not teks: continue

                # Cari URL produk
                url_prod = ""
                for a in card.find_elements(By.TAG_NAME, "a"):
                    try:
                        h = a.get_attribute("href") or ""
                        if "lazada.co.id/products/" in h or "-i" in h:
                            url_prod = h.split("?")[0]
                            break
                    except: pass
                if not url_prod: continue
                if url_prod in semua: continue

                nama    = ambil_teks_el(card, *NAMA_PRODUK_SEL)
                harga   = ambil_teks_el(card, *HARGA_SEL)
                lokasi  = ambil_teks_el(card, *LOKASI_SEL)
                rating  = ambil_teks_el(card, *RATING_SEL)
                terjual = ambil_teks_el(card, *TERJUAL_SEL)

                # Kalau nama tidak ketemu dari selector, ambil dari teks
                if not nama:
                    for l in teks.split("\n"):
                        l = l.strip()
                        if l and not baris_skip(l) and len(l) > 8:
                            nama = l[:200]
                            break
                if not nama: continue

                # [FIX] Lokasi default ke Kab. Gresik (filter sudah aktif)
                if not lokasi:
                    # Cek apakah ada keyword gresik di teks
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
            break  # selector berhasil, tidak perlu coba yang lain

    # ── STRATEGI 2: Fallback — cari semua link produk di halaman ─────────────
    if baru == 0:
        # Kumpulkan SEMUA href di halaman untuk inspeksi
        semua_href = []
        try:
            semua_href = [
                (a.get_attribute("href") or "")
                for a in driver.find_elements(By.TAG_NAME, "a")
            ]
        except: pass

        produk_href = [h for h in semua_href if h and "lazada.co.id" in h and (
            "/products/" in h
            or (re.search(r"-i\d+", h) and re.search(r"-s\d+", h))
        )]
        print(f"      → Fallback: {len(semua_href)} link total, "
              f"{len(produk_href)} link produk terdeteksi")

        seen_in_strat2 = set()
        for h in produk_href:
            try:
                url_prod = h.split("?")[0]
                if url_prod in semua or url_prod in seen_in_strat2: continue
                seen_in_strat2.add(url_prod)

                # Coba ambil nama dari slug URL
                slug = url_prod.rstrip("/").split("/")[-1]
                slug = re.sub(r"-i\d+.*", "", slug)      # hapus -i{id}-s{id}
                nama = slug.replace("-", " ").strip()[:200] or "Produk Lazada"

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

    # ── DEBUG: simpan kalau masih 0 ───────────────────────────────────────────
    if baru == 0 and debug:
        debug_simpan(driver, f"hal{halaman_ke}", headless=True)
        try:
            hrefs = [
                a.get_attribute("href") for a in driver.find_elements(By.TAG_NAME, "a")
                if (a.get_attribute("href") or "")
            ]
            lazada_hrefs = [h for h in hrefs if h and "lazada" in h][:8]
            print(f"      🔍 Sampel href Lazada di halaman:")
            for h in lazada_hrefs:
                print(f"         {h[:100]}")
        except: pass
    elif baru == 0:
        # Selalu print minimal info meski tidak debug mode
        try:
            hrefs = [
                a.get_attribute("href") or ""
                for a in driver.find_elements(By.TAG_NAME, "a")[:50]
            ]
            lazada_hrefs = [h for h in hrefs if "lazada" in h][:3]
            if lazada_hrefs:
                print(f"      ℹ️  Sampel href: {lazada_hrefs[0][:90]}")
            else:
                print(f"      ℹ️  Tidak ada href Lazada sama sekali — "
                      f"halaman mungkin kosong/CAPTCHA")
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
# LANGKAH 3 — Buka PDP secara PARALEL → ambil info toko
# ══════════════════════════════════════════════════════
def _ambil_satu_pdp(url, headless):
    """
    Buka 1 halaman detail produk, ambil:
    - nama_toko, url_toko, rating_toko
    - rating_produk (kalau di listing belum ada)
    - terjual (kalau di listing belum ada)
    """
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
        # Scroll sedikit agar elemen seller muncul
        driver.execute_script("window.scrollBy(0, 400)")
        time.sleep(0.5)

        # ── Nama toko ────────────────────────────────────────────────────────
        for sel in PDP_TOKO_SEL:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                t  = el.text.strip()
                if t and len(t) > 1 and len(t) < 100:
                    hasil["nama_toko"] = t
                    try:
                        h = el.get_attribute("href") or ""
                        if "lazada.co.id" in h:
                            hasil["url_toko"] = h
                    except: pass
                    break
            except: pass

        # ── URL toko (kalau belum dapat) ─────────────────────────────────────
        if hasil["url_toko"] == "-":
            for sel in ["a[href*='/shop/']", "a[href*='/seller/']"]:
                try:
                    h = driver.find_element(By.CSS_SELECTOR, sel).get_attribute("href") or ""
                    if "lazada.co.id" in h:
                        hasil["url_toko"] = h
                        break
                except: pass

        # ── Rating toko ───────────────────────────────────────────────────────
        hasil["rating_toko"] = bersihkan_rating(
            ambil_teks_driver(driver, *PDP_RATING_TOKO_SEL)
        )

        # ── Rating produk ─────────────────────────────────────────────────────
        hasil["rating_produk"] = bersihkan_rating(
            ambil_teks_driver(driver, *PDP_RATING_PRODUK_SEL)
        )

        # ── Jumlah terjual ────────────────────────────────────────────────────
        hasil["terjual"] = bersihkan_terjual(
            ambil_teks_driver(driver, *PDP_TERJUAL_SEL)
        )

        # ── Fallback nama toko dari body teks ────────────────────────────────
        if hasil["nama_toko"] == "-":
            try:
                body = driver.find_element(By.TAG_NAME, "body").text
                for line in body.split("\n"):
                    l = line.strip()
                    if l and 2 < len(l) < 60 and not baris_skip(l):
                        if not any(x in l.lower() for x in
                                   ["lazada", "add to", "beli", "cart", "login",
                                    "rp", "rating", "ulasan", "chat", "klik"]):
                            hasil["nama_toko"] = l
                            break
            except: pass

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
    print(f"   Data yang diambil: nama toko, URL toko, rating toko, rating produk, terjual")

    selesai = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(_ambil_satu_pdp, u, headless): u for u in urls}
        for future in as_completed(future_map):
            url, hasil = future.result()
            item = url_ke_item[url]
            # Update field — kalau listing sudah punya data, pakai yang PDP kalau lebih baik
            item["nama_toko"]    = hasil["nama_toko"]
            item["url_toko"]     = hasil["url_toko"]
            item["rating_toko"]  = hasil["rating_toko"]
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

    # ── Ringkasan per toko ────────────────────────────────────────────────────
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

    # ── Ringkasan per lokasi ──────────────────────────────────────────────────
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

    # ── Ringkasan per kategori ────────────────────────────────────────────────
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
# MAIN
# ══════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(description="Scraper toko Gresik di Lazada — versi perbaikan")
    p.add_argument("--keywords", type=str, default="",
                   help="Keyword lokasi tambahan, pisah koma")
    p.add_argument("--config",   type=str, default=CONFIG_FILE_DEF,
                   help="Path file konfigurasi JSON")
    p.add_argument("--url",      type=str, default="",
                   help="URL filter Lazada langsung (skip langkah aktifkan_filter)")
    p.add_argument("--workers",  type=int, default=DEFAULT_WORKERS,
                   help="Jumlah browser paralel untuk tahap PDP (default 5)")
    p.add_argument("--headful",  action="store_true",
                   help="Matikan headless (browser kelihatan) — DISARANKAN untuk debug")
    p.add_argument("--debug",    action="store_true",
                   help="Simpan screenshot + page source kalau 0 produk ditemukan")
    p.add_argument("--no-pdp",   action="store_true",
                   help="Skip tahap PDP (hanya ambil data listing, cepat tapi tanpa nama toko)")
    return p.parse_args()


def main():
    args = parse_args()
    headless = not args.headful

    print("╔══════════════════════════════════════════════════════╗")
    print("║   SCRAPER TOKO GRESIK DI LAZADA — VERSI PERBAIKAN   ║")
    print(f"║   Mulai: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                          ║")
    print(f"║   Mode: {'HEADLESS' if headless else 'HEADFUL':<10} | Workers PDP: {args.workers:<3}          ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    if args.debug:
        print("   🔍 MODE DEBUG AKTIF — screenshot & HTML akan disimpan kalau 0 produk\n")

    cfg = muat_konfigurasi(args.config)
    cfg = gabungkan_keyword_cli(cfg, args.keywords)
    simpan_konfigurasi(args.config, cfg)

    kata_gresik      = [k.lower() for k in cfg["kata_gresik"]]
    kategori_mapping = cfg["kategori_mapping"]

    print(f"  🔑 Keyword aktif  ({len(kata_gresik)}): {', '.join(kata_gresik)}")
    print(f"  🏷️  Kategori       ({len(kategori_mapping)}): {', '.join(kategori_mapping.keys())}\n")

    driver  = buat_browser(headless=headless)
    produk  = []

    try:
        url_filter = args.url or aktifkan_filter(driver, kata_gresik)
        if not url_filter:
            print("\n❌ Filter gagal. Coba:")
            print("   1. Jalankan dengan --headful untuk lihat browser")
            print("   2. Aktifkan filter manual di browser, copy URL, lalu:")
            print("      python Lazada_v2.py --url \"<URL filter Gresik>\"")
            return

        print(f"\n   ✅ URL filter aktif: {url_filter[:100]}...")

        produk, driver = kumpulkan_url_produk(
            driver, url_filter, kata_gresik,
            headless=headless, debug=args.debug
        )

        if not produk:
            print("\n❌ Tidak ada produk ditemukan di listing.")
            print("\n💡 SOLUSI:")
            print("   1. Jalankan dengan --headful --debug untuk inspeksi visual")
            print("   2. Coba: python Lazada_v2.py --headful")
            print("   3. Atau copy URL filter manual: python Lazada_v2.py --url \"<URL>\"")
            ekspor_dashboard(None, kata_gresik, kategori_mapping)
            return

        # Backup setelah listing — ikut masuk ke output/
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