"""
╔══════════════════════════════════════════════════════╗
║   SCRAPER TOKO GRESIK DI TOKOPEDIA                  ║
║   Tab: Toko | Filter: Kab. Gresik                   ║
║   Output: toko_gresik_tokopedia.csv                 ║
║   + Keyword dinamis (config JSON)                   ║
║   + Kategori produk standar (ala Shopee)            ║
╚══════════════════════════════════════════════════════╝

CARA PAKAI:
  1. pip install selenium pandas
  2. Taruh chromedriver.exe di folder yang sama
  3. python tokopedia_gresik.py
       --keywords "gresik,kebomas,manyar"   (opsional, override keyword)
       --config keywords_config.json         (opsional, path config custom)

CATATAN DASHBOARD:
  - keywords_config.json  → berisi daftar keyword lokasi & mapping kategori.
    Dashboard bisa membaca/mengedit file ini langsung (format JSON biasa).
  - dashboard_data.json   → hasil scraping yang sudah diringkas + daftar
    keyword & kategori yang tersedia, siap dikonsumsi oleh dashboard
    (misalnya untuk dropdown filter keyword/kategori).
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
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_FILE     = os.path.join(OUTPUT_DIR, "toko_gresik_tokopedia.csv")
DASHBOARD_FILE  = os.path.join(OUTPUT_DIR, "dashboard_data_tokopedia.json")
CONFIG_FILE_DEF = os.path.join(BASE_DIR, "keywords_config.json")
CHROMEDRIVER    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver.exe")

# Keyword lokasi & mapping kategori "bawaan" (dipakai kalau config belum ada)
DEFAULT_KATA_GRESIK = [
    "gresik", "kab. gresik", "kabupaten gresik",
    "kebomas", "driyorejo", "manyar", "duduksampeyan",
    "bungah", "sidayu", "cerme", "benjeng",
    "balongpanggang", "panceng", "ujungpangkah",
    "sangkapura", "tambak",
]

# Kategori produk standar, meniru taksonomi umum Shopee.
# Setiap kategori berisi daftar kata kunci yang dicocokkan ke teks produk.
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
    Kalau file belum ada, dibuat dari nilai default lalu disimpan,
    supaya dashboard punya file untuk dibaca/diedit sejak awal.
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
    dipakai (menambah keyword yang sudah ada di config, tanpa duplikat)
    dan config disimpan ulang supaya dashboard ikut ter-update.
    """
    if not keyword_cli:
        return cfg
    tambahan = [k.strip().lower() for k in keyword_cli.split(",") if k.strip()]
    gabungan = list(dict.fromkeys(cfg["kata_gresik"] + tambahan))  # jaga urutan, hapus duplikat
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
    opt.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    opt.add_experimental_option("excludeSwitches", ["enable-automation"])
    opt.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER), options=opt)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"})
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(4)
    return driver

# ══════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════
def jeda(a=2.0, b=3.5):
    time.sleep(random.uniform(a, b))

def buka(driver, url):
    try:
        driver.get(url)
        return True
    except (TimeoutException, WebDriverException):
        try: driver.execute_script("window.stop();")
        except: pass
        return False

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

def scroll_pelan(driver, n=6):
    for _ in range(n):
        driver.execute_script("window.scrollBy(0, 600)")
        time.sleep(random.uniform(0.6, 1.0))

def tutup_popup(driver):
    for sel in [
        "button[aria-label='close']",
        "button[class*='close']",
        "div[class*='modal'] button",
        "[data-testid='btnCloseModal']",
        "button[data-testid*='close']",
    ]:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    el.click(); time.sleep(0.4)
        except: pass
    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.5)
    except: pass

# ══════════════════════════════════════════════════════
# LANGKAH 1: Buka Tokopedia, tab Toko, filter Kab. Gresik
# ══════════════════════════════════════════════════════
def buka_halaman_toko_gresik(driver, kata_gresik):
    print("\n📍 Membuka Tokopedia → Tab Toko → Filter Kab. Gresik...")

    url_kandidat = [
        "https://www.tokopedia.com/search?q=gresik&st=shop&location=Kab.+Gresik",
        "https://www.tokopedia.com/search?q=gresik&navsource=&st=shop&ob=23&location=Kab.+Gresik",
        "https://www.tokopedia.com/search?q=gresik&st=shop&shop_location=Kab.+Gresik",
        "https://www.tokopedia.com/search?q=&st=shop&location=Kab.+Gresik",
        "https://www.tokopedia.com/search?q=toko&st=shop&location=Gresik",
    ]

    for url in url_kandidat:
        print(f"   Coba: {url[:70]}...")
        buka(driver, url)
        time.sleep(5)
        tutup_popup(driver)
        scroll_pelan(driver, 3)
        time.sleep(2)

        body = driver.find_element(By.TAG_NAME, "body").text
        curr = driver.current_url

        if ada_gresik(body, kata_gresik) and ("kab. gresik" in body.lower() or "kab.gresik" in body.lower()):
            print(f"   ✅ Toko Gresik terdeteksi!")
            print(f"   URL aktif: {curr}")
            return curr

    print("\n   Coba filter manual...")

    buka(driver, "https://www.tokopedia.com/search?q=gresik&st=shop")
    time.sleep(5)
    tutup_popup(driver)
    scroll_pelan(driver, 3)
    time.sleep(2)

    for xpath in [
        "//p[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat selengkapnya')]",
        "//span[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat selengkapnya')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat selengkapnya')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'lihat selengkapnya')]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    print(f"   Klik: '{el.text}'")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click()", el)
                    time.sleep(2)
        except: pass

    target = ["kab. gresik", "kab.gresik", "kabupaten gresik", "gresik"]
    for xpath in [
        "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//span[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//p[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
        "//div[contains(translate(normalize-space(text()),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'kab. gresik')]",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                t = el.text.strip()
                if el.is_displayed() and any(k in t.lower() for k in target):
                    print(f"   ✅ Filter ditemukan: '{t}'")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click()", el)
                    time.sleep(5)
                    tutup_popup(driver)
                    print(f"   ✅ Filter aktif! URL: {driver.current_url}")
                    return driver.current_url
        except: pass

    for el in driver.find_elements(By.TAG_NAME, "label"):
        try:
            t = el.text.strip()
            if t and any(k in t.lower() for k in target) and len(t) < 30:
                print(f"   ✅ Label: '{t}'")
                driver.execute_script("arguments[0].click()", el)
                time.sleep(5)
                return driver.current_url
        except: pass

    print("   ⚠ Filter tidak ditemukan, lanjut tanpa filter...")
    return driver.current_url

# ══════════════════════════════════════════════════════
# LANGKAH 2: Scrape card toko dari halaman listing
# ══════════════════════════════════════════════════════
def scrape_toko(driver, url_filter, kata_gresik, kategori_mapping):
    print(f"\n🏪 Scraping data toko dari Tokopedia...\n")

    toko_list = []
    seen_toko = set()
    halaman   = 1
    kosong    = 0

    while True:
        if "page=" in url_filter:
            url = re.sub(r"page=\d+", f"page={halaman}", url_filter)
        elif "?" in url_filter:
            url = url_filter + f"&page={halaman}"
        else:
            url = url_filter + f"?page={halaman}"

        print(f"   Halaman {halaman} → ", end="", flush=True)
        buka(driver, url)
        time.sleep(5)
        tutup_popup(driver)
        scroll_pelan(driver, 8)
        time.sleep(3)

        toko_halaman = []

        card_sels = [
            "[data-testid='divShopCard']",
            "[data-testid='shop-card']",
            "div[class*='ShopCard']",
            "div[class*='shop-card']",
            "div[class*='css-'][class*='shop']",
        ]
        cards = []
        for sel in card_sels:
            c = driver.find_elements(By.CSS_SELECTOR, sel)
            if c and len(c) > 2:
                cards = c
                break

        for card in cards:
            try:
                ct = card.text.strip()
                if not ct or not ada_gresik(ct, kata_gresik):
                    continue

                lines = [l.strip() for l in ct.split("\n") if l.strip()]

                nama_toko  = ""
                lokasi     = ""
                produk_list= []
                harga_list = []
                url_toko   = ""

                for l in lines:
                    lo = l.lower()
                    if ada_gresik(l, kata_gresik) and len(l) < 40 and not lokasi:
                        lokasi = l
                    elif re.match(r"Rp[\d.,]+", l):
                        harga_list.append(l)
                    elif (l.isupper() or l.istitle()) and 3 < len(l) < 60 and not nama_toko:
                        if not any(x in lo for x in
                                   ["lihat","toko","produk","rp","kab","gresik"]):
                            nama_toko = l
                    elif (len(l) > 8 and not any(
                        x in lo for x in
                        ["lihat toko","rp","kab.","gresik","mall","power shop"]
                    ) and l not in (nama_toko, lokasi)):
                        produk_list.append(l[:100])

                try:
                    links = card.find_elements(By.CSS_SELECTOR, "a[href*='/']")
                    for a in links:
                        h = a.get_attribute("href") or ""
                        if "tokopedia.com/" in h and "/search" not in h:
                            url_toko = h
                            break
                except: pass

                if nama_toko and lokasi and nama_toko not in seen_toko:
                    seen_toko.add(nama_toko)
                    teks_produk_gabungan = " ".join(produk_list)
                    toko_halaman.append({
                        "nama_toko"    : nama_toko,
                        "lokasi"       : lokasi,
                        "url_toko"     : url_toko or "-",
                        "produk_dijual": " | ".join(produk_list[:5]) or "-",
                        "kategori"     : standarisasi_kategori(teks_produk_gabungan, kategori_mapping),
                        "harga_produk" : " | ".join(harga_list[:3]) or "-",
                        "platform"     : "Tokopedia",
                        "waktu_scrape" : datetime.now().strftime("%Y-%m-%d %H:%M"),
                    })
            except: pass

        if not toko_halaman:
            try:
                lokasi_els = driver.find_elements(By.XPATH,
                    "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                    "'abcdefghijklmnopqrstuvwxyz'),'kab. gresik') and string-length(text()) < 30]"
                )
                for lok_el in lokasi_els:
                    try:
                        parent = lok_el.find_element(By.XPATH, "./../..")
                        pt     = parent.text.strip()
                        lines  = [l.strip() for l in pt.split("\n") if l.strip()]

                        nama   = ""
                        lokasi = lok_el.text.strip()
                        produk = []
                        harga  = []

                        for l in lines:
                            lo = l.lower()
                            if re.match(r"Rp[\d.,]+", l):
                                harga.append(l)
                            elif ada_gresik(l, kata_gresik) or "lihat" in lo:
                                continue
                            elif l.isupper() and 3 < len(l) < 60 and not nama:
                                nama = l
                            elif len(l) > 8:
                                produk.append(l[:100])

                        if nama and nama not in seen_toko:
                            seen_toko.add(nama)
                            url_toko = "-"
                            try:
                                a = parent.find_element(By.CSS_SELECTOR, "a[href*='tokopedia']")
                                url_toko = a.get_attribute("href") or "-"
                            except: pass

                            teks_produk_gabungan = " ".join(produk)
                            toko_halaman.append({
                                "nama_toko"    : nama,
                                "lokasi"       : lokasi,
                                "url_toko"     : url_toko,
                                "produk_dijual": " | ".join(produk[:5]) or "-",
                                "kategori"     : standarisasi_kategori(teks_produk_gabungan, kategori_mapping),
                                "harga_produk" : " | ".join(harga[:3]) or "-",
                                "platform"     : "Tokopedia",
                                "waktu_scrape" : datetime.now().strftime("%Y-%m-%d %H:%M"),
                            })
                    except: pass
            except: pass

        if not toko_halaman:
            body_lines = driver.find_element(By.TAG_NAME, "body").text.split("\n")
            i = 0
            while i < len(body_lines):
                baris = body_lines[i].strip()
                if ada_gresik(baris, kata_gresik) and len(baris) < 40:
                    lokasi = baris
                    nama   = ""
                    produk = []
                    harga  = []
                    for back in range(1, 5):
                        if i - back < 0: break
                        prev = body_lines[i - back].strip()
                        lo   = prev.lower()
                        if re.match(r"Rp[\d.,]+", prev):
                            harga.append(prev)
                        elif (prev.isupper() or prev.istitle()) and 3 < len(prev) < 60:
                            if not any(x in lo for x in ["lihat","toko","filter","rp"]):
                                nama = prev
                                break
                    for fwd in range(1, 8):
                        if i + fwd >= len(body_lines): break
                        nxt = body_lines[i + fwd].strip()
                        lo  = nxt.lower()
                        if re.match(r"Rp[\d.,]+", nxt):
                            harga.append(nxt)
                        elif len(nxt) > 8 and not any(
                            x in lo for x in ["lihat toko","rp","kab.","gresik","mall"]
                        ):
                            produk.append(nxt[:100])

                    if nama and nama not in seen_toko:
                        seen_toko.add(nama)
                        teks_produk_gabungan = " ".join(produk)
                        toko_halaman.append({
                            "nama_toko"    : nama,
                            "lokasi"       : lokasi,
                            "url_toko"     : "-",
                            "produk_dijual": " | ".join(produk[:5]) or "-",
                            "kategori"     : standarisasi_kategori(teks_produk_gabungan, kategori_mapping),
                            "harga_produk" : " | ".join(harga[:3]) or "-",
                            "platform"     : "Tokopedia",
                            "waktu_scrape" : datetime.now().strftime("%Y-%m-%d %H:%M"),
                        })
                i += 1

        toko_list.extend(toko_halaman)
        print(f"{len(toko_halaman)} toko baru | Total: {len(toko_list)}")

        try:
            info = driver.find_element(By.XPATH,
                "//*[contains(text(),'dari total') or contains(text(),'of')]"
            ).text
            print(f"   Info halaman: {info}")
        except: pass

        if len(toko_halaman) == 0:
            kosong += 1
            if kosong >= 2:
                print("   2x kosong → selesai.")
                break
        else:
            kosong = 0

        halaman += 1
        jeda()

    return toko_list

# ══════════════════════════════════════════════════════
# SIMPAN CSV
# ══════════════════════════════════════════════════════
def simpan_csv(toko_list):
    if not toko_list:
        print("\n⚠ Tidak ada data."); return None

    df = pd.DataFrame(toko_list).drop_duplicates(subset=["nama_toko"])

    kolom = ["nama_toko","lokasi","url_toko","produk_dijual","kategori",
             "harga_produk","platform","waktu_scrape"]
    df[[c for c in kolom if c in df.columns]].to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print(f"\n{'='*60}")
    print(f"  HASIL SCRAPING TOKO GRESIK DI TOKOPEDIA")
    print(f"{'='*60}")
    print(f"  🏪 Total toko unik     : {len(df)}")
    print(f"  📍 Lokasi              : {df['lokasi'].nunique()} wilayah")
    if "kategori" in df.columns:
        print(f"  🏷️  Kategori terdeteksi : {df['kategori'].nunique()} kategori")
    print(f"  💾 File                → {OUTPUT_FILE}")
    print(f"{'='*60}")
    print(f"\n  DAFTAR TOKO DI GRESIK:\n")
    print(f"  {'No':<4} {'Nama Toko':<35} {'Lokasi':<20} {'Kategori':<22} {'Produk Dijual (sampel)'}")
    print(f"  {'-'*120}")
    for i, r in df.iterrows():
        produk = str(r.get("produk_dijual","-"))[:40]
        kategori = str(r.get("kategori","-"))
        print(f"  {i+1:<4} {str(r['nama_toko']):<35} {str(r['lokasi']):<20} {kategori:<22} {produk}")

    return df


def ekspor_dashboard(df, kata_gresik, kategori_mapping):
    """
    Menulis dashboard_data.json: ringkasan hasil + daftar keyword & kategori
    yang tersedia, supaya dashboard bisa langsung menampilkan filter
    (dropdown keyword lokasi, dropdown kategori) tanpa hardcode.
    """
    if df is None or df.empty:
        data = {"keywords": kata_gresik, "kategori_tersedia": list(kategori_mapping.keys()),
                "toko": [], "ringkasan": {}}
    else:
        kategori_count = df["kategori"].value_counts().to_dict() if "kategori" in df.columns else {}
        lokasi_count   = df["lokasi"].value_counts().to_dict()
        data = {
            "keywords": kata_gresik,
            "kategori_tersedia": list(kategori_mapping.keys()),
            "toko": df.to_dict(orient="records"),
            "ringkasan": {
                "total_toko": len(df),
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
    p = argparse.ArgumentParser(description="Scraper toko Gresik di Tokopedia")
    p.add_argument("--keywords", type=str, default="",
                    help="Tambahan keyword lokasi, pisahkan koma. Contoh: 'gresik,kebomas'")
    p.add_argument("--config", type=str, default=CONFIG_FILE_DEF,
                    help="Path file konfigurasi keyword & kategori (JSON)")
    return p.parse_args()

def main():
    args = parse_args()

    print("╔══════════════════════════════════════════════════════╗")
    print("║   SCRAPER TOKO GRESIK DI TOKOPEDIA                  ║")
    print(f"║   Mulai: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                          ║")
    print("╚══════════════════════════════════════════════════════╝")
    print("\n  Ctrl+C untuk berhenti kapan saja\n")

    # Muat konfigurasi keyword & kategori (dinamis, bisa diedit dashboard)
    cfg = muat_konfigurasi(args.config)
    cfg = gabungkan_keyword_cli(cfg, args.keywords)
    simpan_konfigurasi(args.config, cfg)  # simpan lagi biar sinkron dgn CLI

    kata_gresik      = [k.lower() for k in cfg["kata_gresik"]]
    kategori_mapping = cfg["kategori_mapping"]

    print(f"  🔑 Keyword aktif ({len(kata_gresik)}): {', '.join(kata_gresik)}")
    print(f"  🏷️  Kategori tersedia ({len(kategori_mapping)}): {', '.join(kategori_mapping.keys())}")

    driver    = buat_browser()
    toko_list = []

    try:
        url_filter = buka_halaman_toko_gresik(driver, kata_gresik)
        toko_list  = scrape_toko(driver, url_filter, kata_gresik, kategori_mapping)

        if not toko_list:
            print("❌ Tidak ada toko ditemukan.")
            return

        pd.DataFrame(toko_list).to_csv(
            OUTPUT_FILE.replace(".csv","_progress.csv"),
            index=False, encoding="utf-8-sig"
        )

    except KeyboardInterrupt:
        print("\n\n⏹ Dihentikan.")
    finally:
        try: driver.quit()
        except: pass

    df = simpan_csv(toko_list)
    ekspor_dashboard(df, kata_gresik, kategori_mapping)
    print(f"\n✅ Selesai! Buka file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()