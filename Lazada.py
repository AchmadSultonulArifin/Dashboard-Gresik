"""
╔══════════════════════════════════════════════════════╗
║   SCRAPER TOKO GRESIK DI LAZADA                     ║
║   Filter: Shipped From → Kab. Gresik                ║
║   Output: toko_gresik_lazada.csv                    ║
║   + Keyword dinamis (config JSON, sama dgn Tokopedia)║
║   + Kategori produk standar (ala Shopee)            ║
╚══════════════════════════════════════════════════════╝

CARA PAKAI:
  1. pip install selenium pandas
  2. Taruh chromedriver.exe di folder yang sama
  3. python lazada_gresik.py
       --keywords "gresik,kebomas,manyar"   (opsional, override keyword)
       --config keywords_config.json         (opsional, path config custom)

CATATAN DASHBOARD:
  - keywords_config.json  → dipakai bersama dengan scraper Tokopedia,
    berisi daftar keyword lokasi & mapping kategori. Dashboard bisa
    membaca/mengedit file ini langsung.
  - dashboard_data_lazada.json → hasil scraping yang sudah diringkas +
    daftar keyword & kategori yang tersedia, siap dikonsumsi dashboard.
"""

import time, random, re, os, json, argparse
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException, ElementClickInterceptedException

# ══════════════════════════════════════════════════════
# PENGATURAN DASAR
# ══════════════════════════════════════════════════════
MAX_HALAMAN     = 15
# Tentukan folder output
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)  # buat folder kalau belum ada

OUTPUT_FILE     = os.path.join(OUTPUT_DIR, "toko_gresik_lazada.csv")
DASHBOARD_FILE  = os.path.join(OUTPUT_DIR, "dashboard_data_lazada.json")
CONFIG_FILE_DEF = os.path.join(BASE_DIR, "keywords_config.json")
CHROMEDRIVER    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver.exe")

# Keyword lokasi & mapping kategori "bawaan" (dipakai kalau config belum ada).
# Sama persis dengan scraper Tokopedia supaya dashboard bisa menyatukan
# data dari kedua platform dengan taksonomi kategori yang seragam.
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
    "Hobi & Koleksi":        ["action figure", "mainan koleksi", "kartu", "hobi",
                               "diecast"],
    "Buku & Alat Tulis":     ["buku", "alat tulis", "pulpen", "pensil", "note book"],
    "Perawatan Hewan":       ["pakan kucing", "pakan anjing", "kandang hewan", "pet shop"],
    "Souvenir & Perayaan":   ["souvenir", "kado", "hampers", "balon", "dekorasi ulang tahun"],
}


# ══════════════════════════════════════════════════════
# KONFIGURASI DINAMIS (keyword & kategori)
# ══════════════════════════════════════════════════════
def muat_konfigurasi(path_config):
    """
    Memuat keyword lokasi & mapping kategori dari file JSON.
    File ini dipakai bersama scraper Tokopedia — kalau sudah ada
    (dibuat oleh scraper lain), keyword/kategori yang tersimpan
    di situ langsung dipakai di sini juga.
    """
    if os.path.exists(path_config):
        try:
            with open(path_config, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("kata_gresik", DEFAULT_KATA_GRESIK)
            cfg.setdefault("kategori_mapping", DEFAULT_KATEGORI_MAPPING)
            print(f"⚙️  Konfigurasi dimuat dari: {path_config}")
            return cfg
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠ Gagal membaca {path_config} ({e}), pakai default.")

    cfg = {
        "kata_gresik": DEFAULT_KATA_GRESIK,
        "kategori_mapping": DEFAULT_KATEGORI_MAPPING,
    }
    simpan_konfigurasi(path_config, cfg)
    print(f"⚙️  Konfigurasi default dibuat: {path_config}")
    return cfg


def simpan_konfigurasi(path_config, cfg):
    with open(path_config, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def gabungkan_keyword_cli(cfg, keyword_cli):
    """
    Kalau user memberi --keywords lewat command line, keyword itu
    ditambahkan ke config yang sudah ada (tanpa duplikat), lalu
    disimpan ulang supaya dashboard & scraper lain ikut ter-update.
    """
    if not keyword_cli:
        return cfg
    tambahan = [k.strip().lower() for k in keyword_cli.split(",") if k.strip()]
    gabungan = list(dict.fromkeys(cfg["kata_gresik"] + tambahan))
    cfg["kata_gresik"] = gabungan
    return cfg


# ══════════════════════════════════════════════════════
# SETUP BROWSER
# ══════════════════════════════════════════════════════
def buat_browser():
    if not os.path.exists(CHROMEDRIVER):
        print(f"❌ chromedriver.exe tidak ditemukan di: {CHROMEDRIVER}")
        exit(1)
    opt = Options()
    opt.add_argument("--no-sandbox")
    opt.add_argument("--disable-dev-shm-usage")
    opt.add_argument("--window-size=1400,900")
    opt.add_argument("--disable-blink-features=AutomationControlled")
    opt.add_argument("--lang=id-ID")
    opt.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
    opt.add_experimental_option("excludeSwitches", ["enable-automation"])
    opt.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER), options=opt)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"})
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(5)
    return driver

# ══════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════
def jeda(a=2.5, b=4.0):
    time.sleep(random.uniform(a, b))

def buka(driver, url):
    try:
        driver.get(url)
        return True
    except (TimeoutException, WebDriverException):
        try: driver.execute_script("window.stop();")
        except: pass
        return False

def tutup_popup(driver):
    for sel in ["button[class*='close']", ".pdp-mod-common-image.close-icon", "[data-testid='close-button']"]:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed(): el.click(); time.sleep(0.3)
        except: pass

def ada_gresik(teks, kata_gresik):
    t = (teks or "").lower()
    return any(k in t for k in kata_gresik)

def standarisasi_kategori(teks_produk, kategori_mapping):
    """
    Mencocokkan teks produk ke kategori standar (ala Shopee).
    Mengembalikan nama kategori baku, atau 'Lainnya' kalau tidak cocok.
    """
    t = (teks_produk or "").lower()
    for kategori, kw_list in kategori_mapping.items():
        if any(kw in t for kw in kw_list):
            return kategori
    return "Lainnya"

def ambil_teks(driver, *sels):
    for s in sels:
        try:
            t = driver.find_element(By.CSS_SELECTOR, s).text.strip()
            if t and len(t) > 1: return t
        except: pass
    return ""

def ambil_href(driver, *sels):
    for s in sels:
        try:
            h = driver.find_element(By.CSS_SELECTOR, s).get_attribute("href") or ""
            if "lazada.co.id" in h: return h
        except: pass
    return ""

# ══════════════════════════════════════════════════════
# LANGKAH 1: Klik filter "Kab. Gresik" di sidebar
# ══════════════════════════════════════════════════════
def aktifkan_filter(driver, kata_gresik):
    print("\n📍 Membuka Lazada...")
    buka(driver, "https://www.lazada.co.id/catalog/?q=gresik&sort=0")
    time.sleep(6)
    tutup_popup(driver)

    print("   Scroll sidebar untuk load semua filter...")
    for _ in range(10):
        driver.execute_script("window.scrollBy(0, 300)")
        time.sleep(0.5)
    time.sleep(2)

    print("   Mencari tombol 'Lihat Lebih Banyak'...")
    for xpath in [
        "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat lebih banyak')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat lebih banyak')]",
        "//div[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat lebih banyak')]",
        "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'see more')]",
        "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'more')]",
    ]:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                if el.is_displayed():
                    print(f"   ✓ Tombol ditemukan: '{el.text}' → diklik")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click()", el)
                    time.sleep(2)
        except: pass

    for _ in range(5):
        driver.execute_script("window.scrollBy(0, 300)")
        time.sleep(0.4)
    time.sleep(2)

    print("   Mencari filter 'Kab. Gresik'...")

    # Ambil kata kunci Gresik "inti" (yang benar-benar merujuk nama wilayah,
    # bukan kecamatan) dari config untuk pencarian filter checkbox
    target_texts = [k for k in kata_gresik if "gresik" in k] or ["gresik"]

    for xpath in [
        "//label[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//span[translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='kab. gresik']",
        "//span[translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='gresik']",
        "//div[translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='kab. gresik']",
        "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//input[@type='checkbox'][following-sibling::*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'gresik')]]",
    ]:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                t = el.text.strip().lower()
                if el.is_displayed() and any(k in t for k in target_texts):
                    print(f"   ✅ Filter ditemukan: '{el.text}'")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                    time.sleep(0.8)
                    try:
                        el.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click()", el)
                    time.sleep(5)
                    url = driver.current_url
                    print(f"   ✅ Filter aktif! URL: {url}")
                    return url
        except: pass

    print("   XPath tidak menemukan, coba scan semua label...")
    try:
        all_labels = driver.find_elements(By.TAG_NAME, "label")
        for el in all_labels:
            try:
                t = el.text.strip()
                if t and any(k in t.lower() for k in target_texts):
                    print(f"   ✅ Label ditemukan: '{t}'")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click()", el)
                    time.sleep(5)
                    return driver.current_url
            except: pass
    except: pass

    print("   ❌ Filter 'Kab. Gresik' tidak ditemukan.")
    print("   💡 Coba: scroll manual ke bagian 'Shipped From' → klik 'Lihat Lebih Banyak'")
    print("      lalu cek apakah 'Kab. Gresik' muncul di daftar.")
    return None

# ══════════════════════════════════════════════════════
# LANGKAH 2: Kumpulkan URL produk semua halaman
# ══════════════════════════════════════════════════════
def kumpulkan_url(driver, url_filter):
    print(f"\n📋 Mengumpulkan URL produk (maks {MAX_HALAMAN} halaman)...")
    semua = []
    kosong = 0

    for hal in range(1, MAX_HALAMAN + 1):
        if "page=" in url_filter:
            url = re.sub(r"page=\d+", f"page={hal}", url_filter)
        else:
            url = url_filter + f"&page={hal}"

        print(f"   Hal {hal:2}/{MAX_HALAMAN} → ", end="", flush=True)
        buka(driver, url)
        time.sleep(4)
        tutup_popup(driver)

        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 700)")
            time.sleep(0.7)
        time.sleep(2)

        sebelum = len(semua)
        for a in driver.find_elements(By.CSS_SELECTOR, "a"):
            try:
                href = (a.get_attribute("href") or "").split("?")[0]
                if "lazada.co.id/products/" in href and href not in semua:
                    semua.append(href)
            except: pass

        baru = len(semua) - sebelum
        print(f"+{baru} produk | Total: {len(semua)}")

        if baru == 0:
            kosong += 1
            if kosong >= 2:
                print(f"   Halaman kosong 2x berturut → selesai.")
                break
        else:
            kosong = 0
        jeda(2, 3)

    print(f"\n✅ Total URL: {len(semua)}")
    return semua

# ══════════════════════════════════════════════════════
# LANGKAH 3: Ambil info dari halaman listing (bukan detail)
# ══════════════════════════════════════════════════════
def ambil_dari_listing(driver, url_filter, kata_gresik, kategori_mapping):
    """
    Ambil nama toko + produk langsung dari halaman listing.
    Lebih cepat karena tidak perlu buka satu-satu halaman produk.
    Lokasi "Kab. Gresik" sudah terlihat di card produk.
    """
    print(f"\n🚀 Mengambil data langsung dari halaman listing...")
    print(f"   (Lebih cepat — lokasi sudah tampil di card produk)\n")

    hasil = []
    kosong = 0

    for hal in range(1, MAX_HALAMAN + 1):
        if "page=" in url_filter:
            url = re.sub(r"page=\d+", f"page={hal}", url_filter)
        else:
            url = url_filter + f"&page={hal}"

        print(f"   Hal {hal:2}/{MAX_HALAMAN}...", end="", flush=True)
        buka(driver, url)
        time.sleep(4)
        tutup_popup(driver)

        for _ in range(6):
            driver.execute_script("window.scrollBy(0, 600)")
            time.sleep(0.6)
        time.sleep(2)

        body_lines = driver.find_element(By.TAG_NAME, "body").text.split("\n")

        produk_halaman = []
        i = 0
        while i < len(body_lines):
            line = body_lines[i].strip()
            if ada_gresik(line, kata_gresik) and len(line) < 50:
                nama_produk = ""
                harga = ""
                lokasi = line

                for back in range(1, 6):
                    if i - back >= 0:
                        prev = body_lines[i - back].strip()
                        if "Rp" in prev and not harga:
                            harga = prev
                        elif prev and len(prev) > 10 and not any(
                            x in prev.lower() for x in
                            ["rp", "rating", "terjual", "bintang", "gratis", "%"]
                        ) and not nama_produk:
                            nama_produk = prev

                if nama_produk:
                    produk_halaman.append({
                        "nama_produk"  : nama_produk[:200],
                        "harga"        : harga or "-",
                        "lokasi_seller": lokasi,
                    })
            i += 1

        try:
            cards = driver.find_elements(By.CSS_SELECTOR,
                "div[data-item-id], div[class*='product-card'], div[class*='ProductCard']"
            )
            for card in cards:
                try:
                    ct = card.text.strip()
                    if ada_gresik(ct, kata_gresik):
                        lines_card = ct.split("\n")
                        nama = harga = lokasi = ""
                        for l in lines_card:
                            l = l.strip()
                            if not l: continue
                            if ada_gresik(l, kata_gresik) and len(l) < 50:
                                lokasi = l
                            elif "Rp" in l and not harga:
                                harga = l.split("\n")[0]
                            elif len(l) > 10 and not nama and not any(
                                x in l.lower() for x in
                                ["rp","rating","terjual","gratis","ongkir","%","bintang"]
                            ):
                                nama = l[:200]
                        if lokasi and nama:
                            produk_halaman.append({
                                "nama_produk"  : nama,
                                "harga"        : harga or "-",
                                "lokasi_seller": lokasi,
                            })
                except: pass
        except: pass

        seen_produk = set()
        for p in produk_halaman:
            key = p["nama_produk"][:50]
            if key not in seen_produk:
                seen_produk.add(key)
                p["nama_toko"]   = "-"
                p["url_produk"]  = "-"
                p["kategori"]    = standarisasi_kategori(p["nama_produk"], kategori_mapping)
                p["platform"]    = "Lazada"
                p["waktu_scrape"]= datetime.now().strftime("%Y-%m-%d %H:%M")
                hasil.append(p)

        print(f" {len(seen_produk)} produk Gresik ditemukan | Total: {len(hasil)}")

        if len(seen_produk) == 0:
            kosong += 1
            if kosong >= 2:
                print("   Halaman kosong 2x → selesai.")
                break
        else:
            kosong = 0

        jeda(2, 3)

    return hasil

# ══════════════════════════════════════════════════════
# LANGKAH 4: (OPSIONAL) Ambil nama toko dari halaman produk
# ══════════════════════════════════════════════════════
def ambil_nama_toko(driver, url_produk):
    try:
        buka(driver, url_produk)
        time.sleep(3)
        tutup_popup(driver)
        nama = ambil_teks(driver,
            "a[href*='/shop/']",
            "[class*='seller-name'] a",
            "[class*='sellerName']",
            "[data-spm='dshopname']",
        )
        url_toko = ambil_href(driver, "a[href*='/shop/']", "a[href*='/seller/']")
        return nama or "-", url_toko or "-"
    except:
        return "-", "-"

# ══════════════════════════════════════════════════════
# SIMPAN CSV
# ══════════════════════════════════════════════════════
def simpan_csv(data_list):
    if not data_list:
        print("\n⚠ Tidak ada data."); return None

    df = pd.DataFrame(data_list)
    df = df.drop_duplicates(subset=["nama_produk"])

    kolom = ["nama_produk", "harga", "lokasi_seller", "kategori", "nama_toko",
             "platform", "waktu_scrape"]
    df_out = df[[c for c in kolom if c in df.columns]]
    df_out.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    # Ringkasan per lokasi
    file_ringkasan = OUTPUT_FILE.replace(".csv", "_ringkasan.csv")
    ringkasan = (
        df.groupby("lokasi_seller")
        .agg(
            jumlah_produk=("nama_produk", "count"),
            contoh_produk=("nama_produk", lambda x: " | ".join(x.unique()[:5])),
        )
        .reset_index()
        .sort_values("jumlah_produk", ascending=False)
    )
    ringkasan.to_csv(file_ringkasan, index=False, encoding="utf-8-sig")

    # Ringkasan per kategori
    file_kategori = OUTPUT_FILE.replace(".csv", "_per_kategori.csv")
    if "kategori" in df.columns:
        ringkasan_kat = (
            df.groupby("kategori")
            .agg(jumlah_produk=("nama_produk", "count"))
            .reset_index()
            .sort_values("jumlah_produk", ascending=False)
        )
        ringkasan_kat.to_csv(file_kategori, index=False, encoding="utf-8-sig")

    print(f"\n{'='*55}")
    print(f"  HASIL SCRAPING TOKO GRESIK DI LAZADA")
    print(f"{'='*55}")
    print(f"  📦 Total produk unik   : {len(df)}")
    print(f"  📍 Lokasi Gresik       : {df['lokasi_seller'].nunique()} wilayah")
    if "kategori" in df.columns:
        print(f"  🏷️  Kategori terdeteksi : {df['kategori'].nunique()} kategori")
    print(f"  💾 Detail produk       → {OUTPUT_FILE}")
    print(f"  💾 Ringkasan lokasi    → {file_ringkasan}")
    print(f"{'='*55}")
    print(f"\n  PRODUK YANG DIJUAL DI GRESIK (sampel):\n")
    for _, r in df.head(20).iterrows():
        kategori = r.get("kategori", "-")
        print(f"  • {r['nama_produk'][:55]} | {kategori} | {r['harga']} | {r['lokasi_seller']}")

    return df


def ekspor_dashboard(df, kata_gresik, kategori_mapping):
    """
    Menulis dashboard_data_lazada.json: ringkasan hasil + daftar keyword
    & kategori yang tersedia, supaya dashboard bisa menyatukan tampilan
    filter dengan scraper Tokopedia (format sama).
    """
    if df is None or df.empty:
        data = {"platform": "Lazada", "keywords": kata_gresik,
                "kategori_tersedia": list(kategori_mapping.keys()),
                "produk": [], "ringkasan": {}}
    else:
        kategori_count = df["kategori"].value_counts().to_dict() if "kategori" in df.columns else {}
        lokasi_count   = df["lokasi_seller"].value_counts().to_dict()
        data = {
            "platform": "Lazada",
            "keywords": kata_gresik,
            "kategori_tersedia": list(kategori_mapping.keys()),
            "produk": df.to_dict(orient="records"),
            "ringkasan": {
                "total_produk": len(df),
                "per_kategori": kategori_count,
                "per_lokasi": lokasi_count,
                "waktu_ekspor": datetime.now().strftime("%Y-%m-%d %H:%M"),
            },
        }

    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  📊 Data dashboard      → {DASHBOARD_FILE}")

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(description="Scraper toko Gresik di Lazada")
    p.add_argument("--keywords", type=str, default="",
                    help="Tambahan keyword lokasi, pisahkan koma. Contoh: 'gresik,kebomas'")
    p.add_argument("--config", type=str, default=CONFIG_FILE_DEF,
                    help="Path file konfigurasi keyword & kategori (JSON)")
    return p.parse_args()

def main():
    args = parse_args()

    print("╔══════════════════════════════════════════════════════╗")
    print("║   SCRAPER TOKO GRESIK DI LAZADA                     ║")
    print(f"║   Mulai: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                          ║")
    print("╚══════════════════════════════════════════════════════╝")
    print("\n  Ctrl+C untuk berhenti kapan saja\n")

    # Muat konfigurasi keyword & kategori (dinamis, sama dgn scraper Tokopedia)
    cfg = muat_konfigurasi(args.config)
    cfg = gabungkan_keyword_cli(cfg, args.keywords)
    simpan_konfigurasi(args.config, cfg)

    kata_gresik      = [k.lower() for k in cfg["kata_gresik"]]
    kategori_mapping = cfg["kategori_mapping"]

    print(f"  🔑 Keyword aktif ({len(kata_gresik)}): {', '.join(kata_gresik)}")
    print(f"  🏷️  Kategori tersedia ({len(kategori_mapping)}): {', '.join(kategori_mapping.keys())}")

    driver = buat_browser()
    hasil  = []

    try:
        url_filter = aktifkan_filter(driver, kata_gresik)
        if not url_filter:
            print("\n❌ Tidak bisa aktifkan filter. Keluar.")
            return

        hasil = ambil_dari_listing(driver, url_filter, kata_gresik, kategori_mapping)

        if not hasil:
            print("❌ Tidak ada produk ditemukan.")
            return

        pd.DataFrame(hasil).to_csv(
            OUTPUT_FILE.replace(".csv","_progress.csv"),
            index=False, encoding="utf-8-sig"
        )

    except KeyboardInterrupt:
        print("\n\n⏹ Dihentikan.")
    finally:
        try: driver.quit()
        except: pass

    df = simpan_csv(hasil)
    ekspor_dashboard(df, kata_gresik, kategori_mapping)
    print(f"\n✅ Selesai! Buka file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()