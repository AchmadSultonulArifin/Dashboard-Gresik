"""
╔══════════════════════════════════════════════════════════════╗
║   SCRAPER TOKO GRESIK DI SHOPEE  — Versi Dinamis            ║
║   Fitur:                                                     ║
║     • Keyword produk bisa diinput / diatur di config         ║
║     • Kategori Shopee seragam (elektronik, fashion, dll)     ║
║     • Filter lokasi Kab. Gresik otomatis                     ║
║     • Output: toko_gresik_shopee.csv + _per_toko.csv         ║
╚══════════════════════════════════════════════════════════════╝

CARA PAKAI:
  1. pip install selenium pandas
  2. Taruh chromedriver.exe di folder yang sama (sesuai versi Chrome)
  3. Jalankan:
       python shopee_gresik.py
     ATAU dengan keyword langsung:
       python shopee_gresik.py --keyword "baju batik" --kategori "Fashion Wanita"
     ATAU multikeyword:
       python shopee_gresik.py --keyword "sepatu,sandal,tas" --kategori "Fashion"
  4. Saat browser terbuka, LOGIN ke Shopee lalu tekan Enter
"""

import time, random, re, os, argparse, sys
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, NoSuchElementException
)

# ══════════════════════════════════════════════════════════════
# PENGATURAN DEFAULT  (bisa di-override via argumen CLI)
# ══════════════════════════════════════════════════════════════
DEFAULT_KEYWORDS  = ["produk gresik"]   # Kata kunci pencarian default
DEFAULT_KATEGORI  = "Semua Kategori"    # Kategori default jika tidak diisi
MAX_HALAMAN       = 12                  # Shopee max 12 halaman per keyword
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "toko_gresik_shopee.csv")
CHROMEDRIVER      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver.exe")

# ── Kata penanda lokasi Gresik ─────────────────────────────────────────────
KATA_GRESIK = [
    "kab. gresik", "kab.gresik", "gresik",
    "kebomas", "driyorejo", "manyar", "duduksampeyan",
    "bungah", "sidayu", "cerme", "benjeng",
    "balongpanggang", "panceng", "ujungpangkah",
    "sangkapura", "tambak",
]

# ── Kategori Shopee resmi (sesuai sidebar Shopee.co.id) ───────────────────
KATEGORI_SHOPEE = {
    "Semua Kategori"         : "",
    "Pakaian Wanita"         : "Fashion%20Wanita",
    "Pakaian Pria"           : "Fashion%20Pria",
    "Fashion Muslim"         : "Fashion%20Muslim",
    "Aksesoris Fashion"      : "Aksesoris%20Fashion",
    "Tas Wanita"             : "Tas%20Wanita",
    "Sepatu Wanita"          : "Sepatu%20Wanita",
    "Sepatu Pria"            : "Sepatu%20Pria",
    "Jam Tangan"             : "Jam%20Tangan",
    "Elektronik"             : "Elektronik",
    "Handphone & Tablet"     : "Handphone%20%26%20Tablet",
    "Komputer & Laptop"      : "Komputer%20%26%20Laptop",
    "Kamera"                 : "Kamera",
    "Peralatan Rumah"        : "Peralatan%20Rumah",
    "Dapur"                  : "Dapur",
    "Makanan & Minuman"      : "Makanan%20%26%20Minuman",
    "Kesehatan"              : "Kesehatan",
    "Kecantikan"             : "Kecantikan",
    "Ibu & Bayi"             : "Ibu%20%26%20Bayi",
    "Mainan & Hobi"          : "Mainan%20%26%20Hobi",
    "Olahraga & Outdoor"     : "Olahraga%20%26%20Outdoor",
    "Otomotif"               : "Otomotif",
    "Pertanian"              : "Pertanian",
    "Industri"               : "Industri",
    "Furnitur"               : "Furnitur",
    "Buku & Alat Tulis"      : "Buku%20%26%20Alat%20Tulis",
    "Musik & Media"          : "Musik%20%26%20Media",
    "Hewan Peliharaan"       : "Hewan%20Peliharaan",
    "Voucher"                : "Voucher",
}

# ══════════════════════════════════════════════════════════════
# ARGUMEN CLI
# ══════════════════════════════════════════════════════════════
def parse_args():
    parser = argparse.ArgumentParser(
        description="Scraper toko Gresik di Shopee — keyword & kategori dinamis"
    )
    parser.add_argument(
        "--keyword", "-k",
        type=str,
        default=None,
        help='Keyword pencarian, pisahkan koma untuk multi. '
             'Contoh: "baju batik,sarung,kopiah"'
    )
    parser.add_argument(
        "--kategori", "-c",
        type=str,
        default=None,
        help=f'Kategori Shopee. Pilihan: {", ".join(list(KATEGORI_SHOPEE.keys())[:8])} ...'
    )
    parser.add_argument(
        "--halaman", "-p",
        type=int,
        default=MAX_HALAMAN,
        help=f"Jumlah halaman per keyword (default: {MAX_HALAMAN}, max: 12)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=OUTPUT_FILE,
        help="Nama file output CSV"
    )
    parser.add_argument(
        "--list-kategori",
        action="store_true",
        help="Tampilkan daftar kategori Shopee yang tersedia"
    )
    return parser.parse_args()


def tampilkan_kategori():
    print("\n📋 DAFTAR KATEGORI SHOPEE:\n")
    for i, kat in enumerate(KATEGORI_SHOPEE.keys(), 1):
        print(f"  {i:2}. {kat}")
    print()


def minta_input_interaktif():
    """Minta input keyword & kategori secara interaktif jika tidak ada argumen CLI."""
    print("\n" + "═"*60)
    print("  KONFIGURASI PENCARIAN")
    print("═"*60)

    # Keyword
    raw = input(
        "  Keyword produk yang dicari\n"
        "  (pisahkan koma untuk multi-keyword,\n"
        "   kosongkan = pakai default 'produk gresik'): "
    ).strip()
    keywords = [k.strip() for k in raw.split(",") if k.strip()] if raw else DEFAULT_KEYWORDS

    # Kategori
    print("\n  Kategori Shopee (opsional):")
    for i, kat in enumerate(KATEGORI_SHOPEE.keys(), 1):
        print(f"  {i:2}. {kat}")
    raw_kat = input(
        "\n  Masukkan nomor atau nama kategori\n"
        "  (kosongkan = Semua Kategori): "
    ).strip()
    kategori = DEFAULT_KATEGORI
    if raw_kat:
        if raw_kat.isdigit():
            idx = int(raw_kat) - 1
            keys = list(KATEGORI_SHOPEE.keys())
            if 0 <= idx < len(keys):
                kategori = keys[idx]
        else:
            for k in KATEGORI_SHOPEE:
                if raw_kat.lower() in k.lower():
                    kategori = k
                    break

    print(f"\n  ✅ Keyword   : {', '.join(keywords)}")
    print(f"  ✅ Kategori  : {kategori}")
    print("═"*60)
    return keywords, kategori


# ══════════════════════════════════════════════════════════════
# SETUP BROWSER
# ══════════════════════════════════════════════════════════════
def buat_browser():
    if not os.path.exists(CHROMEDRIVER):
        print(f"❌ chromedriver.exe tidak ditemukan di:\n   {CHROMEDRIVER}")
        print("   Download: https://chromedriver.chromium.org/downloads")
        sys.exit(1)

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
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(4)
    return driver


# ══════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════
def jeda(a=2.0, b=3.5):
    time.sleep(random.uniform(a, b))


def buka(driver, url):
    try:
        driver.get(url)
        return True
    except (TimeoutException, WebDriverException):
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        return False


def ada_gresik(teks):
    t = (teks or "").lower()
    return any(k in t for k in KATA_GRESIK)


def scroll_pelan(driver, n=10):
    for _ in range(n):
        driver.execute_script("window.scrollBy(0, 500)")
        time.sleep(random.uniform(0.4, 0.8))
    time.sleep(1.5)


def bangun_url(keyword, kategori_key, page_idx=0):
    """
    Bangun URL pencarian Shopee dengan keyword, kategori, filter Jawa Timur,
    dan halaman tertentu.
    """
    kw_enc   = keyword.replace(" ", "%20")
    kat_slug = KATEGORI_SHOPEE.get(kategori_key, "")

    base = f"https://shopee.co.id/search?keyword={kw_enc}"
    if kat_slug:
        base += f"&category={kat_slug}"
    # Filter lokasi Jawa Timur (Shopee location code = 217 = Jawa Timur)
    base += f"&locations=217&sortBy=sales&page={page_idx}"
    return base


# ══════════════════════════════════════════════════════════════
# LANGKAH 1: Login manual
# ══════════════════════════════════════════════════════════════
def login_manual(driver):
    print("\n📍 Membuka Shopee...")
    buka(driver, "https://shopee.co.id")
    time.sleep(4)

    print("\n" + "="*60)
    print("  SHOPEE BUTUH LOGIN AGAR FILTER LOKASI BERFUNGSI")
    print("="*60)
    print("  1. Silakan LOGIN di browser yang sudah terbuka")
    print("  2. Setelah login berhasil, kembali ke terminal ini")
    print("  3. Tekan Enter untuk mulai scraping")
    print("="*60)
    input("\n  ▶ Tekan Enter setelah login... ")
    print("  ✅ Login dikonfirmasi, mulai scraping!\n")


# ══════════════════════════════════════════════════════════════
# LANGKAH 2: Scrape 1 keyword
# ══════════════════════════════════════════════════════════════
def scrape_satu_keyword(driver, keyword, kategori_key, max_halaman, seen):
    """
    Scrape produk untuk satu keyword tertentu.
    Mengembalikan list dict produk.
    """
    hasil      = []
    kosong_cnt = 0

    for hal in range(1, max_halaman + 1):
        hal_idx = hal - 1
        url     = bangun_url(keyword, kategori_key, hal_idx)

        print(f"  [{keyword}] Hal {hal:2}/{max_halaman} → ", end="", flush=True)
        buka(driver, url)
        time.sleep(5)
        scroll_pelan(driver, 10)
        time.sleep(2)

        produk_hal = []

        # ── Ambil card produk ──────────────────────────────────
        card_sels = [
            "div[data-sqe='item']",
            "li.shopee-search-item-result__item",
            "div.shopee-search-item-result__item",
            "div[class*='col-xs-2-4']",
            "div[class*='shopee-search-item']",
        ]
        cards = []
        for sel in card_sels:
            c = driver.find_elements(By.CSS_SELECTOR, sel)
            if len(c) > 3:
                cards = c
                break

        if not cards:
            try:
                cards = driver.execute_script("""
                    return Array.from(document.querySelectorAll(
                        '[data-sqe="item"], .shopee-search-item-result__item, [class*="col-xs-2-4"]'
                    ));
                """)
            except Exception:
                pass

        for card in cards:
            try:
                ct = card.text.strip()
                if not ct or not ada_gresik(ct):
                    continue

                lines = [l.strip() for l in ct.split("\n") if l.strip()]

                nama_produk = ""
                harga       = ""
                harga_coret = ""
                diskon      = ""
                rating      = ""
                terjual     = ""
                lokasi      = ""
                nama_toko   = ""

                for l in lines:
                    lo = l.lower()

                    if ada_gresik(l) and len(l) < 40 and not lokasi:
                        lokasi = re.sub(r'^[^\w]*', '', l).strip()

                    elif re.match(r'^Rp[\d.,]+$', l):
                        if not harga:
                            harga = l
                        else:
                            harga_coret = l

                    elif re.match(r'^\d+%$', l) and not diskon:
                        diskon = l

                    elif re.match(r'^\d+\.\d+$', l) and not rating:
                        rating = l

                    elif ("terjual" in lo or
                          re.match(r'^\d+[Kk]+\+?\s*terjual', l)):
                        terjual = l

                    elif (len(l) > 8 and not nama_produk and
                          not any(x in lo for x in [
                              "rp", "terjual", "star+", "pilih lokal", "grosir",
                              "gratis ongkir", "kab.", "gresik", "besok",
                              "2-4 hari", "flash", "promo", "⭐", "★",
                              "cicilan", "cashback", "voucher",
                          ])):
                        nama_produk = l[:200]

                # Ambil nama toko dari href card
                try:
                    links = card.find_elements(By.CSS_SELECTOR, "a")
                    for a in links:
                        h = a.get_attribute("href") or ""
                        m = re.search(r'shopee\.co\.id/([^/?#]+)', h)
                        if m and m.group(1) not in ("search", "product", ""):
                            slug = m.group(1)
                            # Abaikan slug yang berisi angka panjang (ID produk)
                            if not re.match(r'^\d+$', slug):
                                nama_toko = slug.replace("-", " ").title()
                                break
                except Exception:
                    pass

                key = (nama_produk[:60] if nama_produk else "") + "|" + lokasi
                if lokasi and nama_produk and key not in seen:
                    seen.add(key)
                    produk_hal.append({
                        "keyword_cari"  : keyword,
                        "kategori"      : kategori_key,
                        "nama_produk"   : nama_produk,
                        "harga"         : harga or "-",
                        "harga_coret"   : harga_coret or "-",
                        "diskon"        : diskon or "-",
                        "rating"        : rating or "-",
                        "terjual"       : terjual or "-",
                        "lokasi_seller" : lokasi,
                        "nama_toko"     : nama_toko or "-",
                        "platform"      : "Shopee",
                        "waktu_scrape"  : datetime.now().strftime("%Y-%m-%d %H:%M"),
                    })

            except Exception:
                pass

        # Fallback: scan body text
        if not produk_hal:
            try:
                body_lines = driver.find_element(By.TAG_NAME, "body").text.split("\n")
                i = 0
                while i < len(body_lines):
                    baris = body_lines[i].strip()
                    if ada_gresik(baris) and len(baris) < 40:
                        lokasi = re.sub(r'^[^\w]*', '', baris).strip()
                        nama = harga = terjual = ""
                        for back in range(1, 10):
                            if i - back < 0:
                                break
                            prev = body_lines[i - back].strip()
                            lo   = prev.lower()
                            if re.match(r'^Rp[\d.,]+', prev) and not harga:
                                harga = prev
                            elif "terjual" in lo and not terjual:
                                terjual = prev
                            elif (len(prev) > 8 and not nama and
                                  not any(x in lo for x in
                                  ["rp", "terjual", "gresik", "kab.",
                                   "star+", "grosir", "besok", "flash"])):
                                nama = prev[:200]

                        key = (nama[:60] if nama else "") + "|" + lokasi
                        if nama and key not in seen:
                            seen.add(key)
                            produk_hal.append({
                                "keyword_cari"  : keyword,
                                "kategori"      : kategori_key,
                                "nama_produk"   : nama,
                                "harga"         : harga or "-",
                                "harga_coret"   : "-",
                                "diskon"        : "-",
                                "rating"        : "-",
                                "terjual"       : terjual or "-",
                                "lokasi_seller" : lokasi,
                                "nama_toko"     : "-",
                                "platform"      : "Shopee",
                                "waktu_scrape"  : datetime.now().strftime("%Y-%m-%d %H:%M"),
                            })
                    i += 1
            except Exception:
                pass

        hasil.extend(produk_hal)
        n_toko = len(set(p["nama_toko"] for p in hasil if p["nama_toko"] != "-"))
        print(f"{len(produk_hal)} produk | Total: {len(hasil)} | {n_toko} toko unik")

        if len(produk_hal) == 0:
            kosong_cnt += 1
            if kosong_cnt >= 2:
                print(f"  [{keyword}] 2x halaman kosong → lanjut keyword berikutnya")
                break
        else:
            kosong_cnt = 0

        jeda()

    return hasil


# ══════════════════════════════════════════════════════════════
# LANGKAH 3: Loop semua keyword
# ══════════════════════════════════════════════════════════════
def scrape_semua_keyword(driver, keywords, kategori_key, max_halaman):
    semua_hasil = []
    seen        = set()   # Deduplikasi global lintas keyword

    print(f"\n🔍 Scraping {len(keywords)} keyword | Kategori: {kategori_key}\n")
    for i, kw in enumerate(keywords, 1):
        print(f"\n  ── Keyword {i}/{len(keywords)}: '{kw}' ────────────────────")
        hasil_kw = scrape_satu_keyword(driver, kw, kategori_key, max_halaman, seen)
        semua_hasil.extend(hasil_kw)
        print(f"  ✅ '{kw}': {len(hasil_kw)} produk baru ditemukan")
        if i < len(keywords):
            jeda(3, 5)   # Jeda lebih panjang antar keyword

    return semua_hasil


# ══════════════════════════════════════════════════════════════
# SIMPAN CSV
# ══════════════════════════════════════════════════════════════
def simpan_csv(hasil, output_file):
    if not hasil:
        print("\n⚠ Tidak ada data yang ditemukan.")
        return None, None

    kolom_urut = [
        "keyword_cari", "kategori", "nama_produk",
        "harga", "harga_coret", "diskon", "rating", "terjual",
        "lokasi_seller", "nama_toko", "platform", "waktu_scrape",
    ]

    df = pd.DataFrame(hasil).drop_duplicates(subset=["nama_produk", "lokasi_seller"])
    df[[c for c in kolom_urut if c in df.columns]].to_csv(
        output_file, index=False, encoding="utf-8-sig"
    )

    # Ringkasan per toko
    file_toko = output_file.replace(".csv", "_per_toko.csv")
    ringkasan = (
        df.groupby(["nama_toko", "lokasi_seller", "kategori"])
        .agg(
            jumlah_produk   = ("nama_produk", "count"),
            keyword_list    = ("keyword_cari", lambda x: " | ".join(sorted(set(x)))),
            daftar_produk   = ("nama_produk",  lambda x: " | ".join(list(x.unique())[:6])),
        )
        .reset_index()
        .sort_values("jumlah_produk", ascending=False)
    )
    ringkasan.to_csv(file_toko, index=False, encoding="utf-8-sig")

    # Print ringkasan di terminal
    n_toko = df["nama_toko"].nunique()
    print(f"\n{'═'*65}")
    print(f"  HASIL SCRAPING TOKO GRESIK DI SHOPEE")
    print(f"{'═'*65}")
    print(f"  🏪 Total toko unik     : {n_toko}")
    print(f"  📦 Total produk        : {len(df)}")
    print(f"  🔑 Keyword digunakan   : {df['keyword_cari'].nunique()}")
    print(f"  📍 Wilayah Gresik      : {df['lokasi_seller'].nunique()} area")
    print(f"  💾 Semua produk        → {output_file}")
    print(f"  💾 Ringkasan per toko  → {file_toko}")
    print(f"{'═'*65}")

    print(f"\n  TOP TOKO DI GRESIK:\n")
    print(f"  {'No':<4} {'Nama Toko':<28} {'Lokasi':<20} {'Kat':<18} {'Produk':<8} Keyword")
    print(f"  {'-'*95}")
    for i, (_, r) in enumerate(ringkasan.head(20).iterrows(), 1):
        print(
            f"  {i:<4} {str(r.get('nama_toko','-'))[:27]:<28} "
            f"{str(r.get('lokasi_seller','-'))[:19]:<20} "
            f"{str(r.get('kategori','-'))[:17]:<18} "
            f"{r.get('jumlah_produk',0):<8} "
            f"{str(r.get('keyword_list','-'))[:25]}"
        )

    return output_file, file_toko


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    args = parse_args()
    os.makedirs("output", exist_ok=True) 

    # ── Tampilkan daftar kategori jika diminta ─────────────────
    if args.list_kategori:
        tampilkan_kategori()
        sys.exit(0)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SCRAPER TOKO GRESIK DI SHOPEE  — Versi Dinamis            ║")
    print(f"║   Mulai: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print("  Ctrl+C untuk berhenti kapan saja\n")

    # ── Tentukan keyword & kategori ───────────────────────────
    if args.keyword:
        keywords = [k.strip() for k in args.keyword.split(",") if k.strip()]
    else:
        keywords = None  # akan ditanya interaktif

    if args.kategori:
        # Cocokkan ke nama kategori resmi
        kategori_key = DEFAULT_KATEGORI
        for k in KATEGORI_SHOPEE:
            if args.kategori.lower() in k.lower():
                kategori_key = k
                break
    else:
        kategori_key = None  # akan ditanya interaktif

    # Jika salah satu belum ada → minta interaktif
    if keywords is None or kategori_key is None:
        kw_inter, kat_inter = minta_input_interaktif()
        if keywords is None:
            keywords = kw_inter
        if kategori_key is None:
            kategori_key = kat_inter

    max_halaman = min(args.halaman, 12)
    output_file = args.output

    # ── Jalankan scraper ──────────────────────────────────────
    driver = buat_browser()
    hasil  = []

    try:
        login_manual(driver)
        hasil = scrape_semua_keyword(driver, keywords, kategori_key, max_halaman)

        if not hasil:
            print("\n❌ Tidak ada produk Gresik ditemukan.")
            return

        # Auto-save progress
        pd.DataFrame(hasil).to_csv(
            output_file.replace(".csv", "_progress.csv"),
            index=False, encoding="utf-8-sig"
        )

    except KeyboardInterrupt:
        print("\n\n⏹ Dihentikan oleh user.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    simpan_csv(hasil, output_file)
    print(f"\n✅ Selesai! Buka file: {output_file}")
    print(f"   Dashboard: buka dashboard.html di browser\n")


if __name__ == "__main__":
    main()
"""
╔══════════════════════════════════════════════════════════════╗
║   SCRAPER TOKO GRESIK DI SHOPEE  — Versi Dinamis            ║
║   Fitur:                                                     ║
║     • Keyword produk bisa diinput / diatur di config         ║
║     • Kategori Shopee seragam (elektronik, fashion, dll)     ║
║     • Filter lokasi Kab. Gresik otomatis                     ║
║     • Output: toko_gresik_shopee.csv + _per_toko.csv         ║
╚══════════════════════════════════════════════════════════════╝

CARA PAKAI:
  1. pip install selenium pandas
  2. Taruh chromedriver.exe di folder yang sama (sesuai versi Chrome)
  3. Jalankan:
       python shopee_gresik.py
     ATAU dengan keyword langsung:
       python shopee_gresik.py --keyword "baju batik" --kategori "Fashion Wanita"
     ATAU multikeyword:
       python shopee_gresik.py --keyword "sepatu,sandal,tas" --kategori "Fashion"
  4. Saat browser terbuka, LOGIN ke Shopee lalu tekan Enter
"""

import time, random, re, os, argparse, sys
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException, WebDriverException, NoSuchElementException
)

# ══════════════════════════════════════════════════════════════
# PENGATURAN DEFAULT  (bisa di-override via argumen CLI)
# ══════════════════════════════════════════════════════════════
DEFAULT_KEYWORDS  = ["produk gresik"]   # Kata kunci pencarian default
DEFAULT_KATEGORI  = "Semua Kategori"    # Kategori default jika tidak diisi
MAX_HALAMAN       = 12                  # Shopee max 12 halaman per keyword
OUTPUT_FILE       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "toko_gresik_shopee.csv")
CHROMEDRIVER      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromedriver.exe")

# ── Kata penanda lokasi Gresik ─────────────────────────────────────────────
KATA_GRESIK = [
    "kab. gresik", "kab.gresik", "gresik",
    "kebomas", "driyorejo", "manyar", "duduksampeyan",
    "bungah", "sidayu", "cerme", "benjeng",
    "balongpanggang", "panceng", "ujungpangkah",
    "sangkapura", "tambak",
]

# ── Kategori Shopee resmi (sesuai sidebar Shopee.co.id) ───────────────────
KATEGORI_SHOPEE = {
    "Semua Kategori"         : "",
    "Pakaian Wanita"         : "Fashion%20Wanita",
    "Pakaian Pria"           : "Fashion%20Pria",
    "Fashion Muslim"         : "Fashion%20Muslim",
    "Aksesoris Fashion"      : "Aksesoris%20Fashion",
    "Tas Wanita"             : "Tas%20Wanita",
    "Sepatu Wanita"          : "Sepatu%20Wanita",
    "Sepatu Pria"            : "Sepatu%20Pria",
    "Jam Tangan"             : "Jam%20Tangan",
    "Elektronik"             : "Elektronik",
    "Handphone & Tablet"     : "Handphone%20%26%20Tablet",
    "Komputer & Laptop"      : "Komputer%20%26%20Laptop",
    "Kamera"                 : "Kamera",
    "Peralatan Rumah"        : "Peralatan%20Rumah",
    "Dapur"                  : "Dapur",
    "Makanan & Minuman"      : "Makanan%20%26%20Minuman",
    "Kesehatan"              : "Kesehatan",
    "Kecantikan"             : "Kecantikan",
    "Ibu & Bayi"             : "Ibu%20%26%20Bayi",
    "Mainan & Hobi"          : "Mainan%20%26%20Hobi",
    "Olahraga & Outdoor"     : "Olahraga%20%26%20Outdoor",
    "Otomotif"               : "Otomotif",
    "Pertanian"              : "Pertanian",
    "Industri"               : "Industri",
    "Furnitur"               : "Furnitur",
    "Buku & Alat Tulis"      : "Buku%20%26%20Alat%20Tulis",
    "Musik & Media"          : "Musik%20%26%20Media",
    "Hewan Peliharaan"       : "Hewan%20Peliharaan",
    "Voucher"                : "Voucher",
}

# ══════════════════════════════════════════════════════════════
# ARGUMEN CLI
# ══════════════════════════════════════════════════════════════
def parse_args():
    parser = argparse.ArgumentParser(
        description="Scraper toko Gresik di Shopee — keyword & kategori dinamis"
    )
    parser.add_argument(
        "--keyword", "-k",
        type=str,
        default=None,
        help='Keyword pencarian, pisahkan koma untuk multi. '
             'Contoh: "baju batik,sarung,kopiah"'
    )
    parser.add_argument(
        "--kategori", "-c",
        type=str,
        default=None,
        help=f'Kategori Shopee. Pilihan: {", ".join(list(KATEGORI_SHOPEE.keys())[:8])} ...'
    )
    parser.add_argument(
        "--halaman", "-p",
        type=int,
        default=MAX_HALAMAN,
        help=f"Jumlah halaman per keyword (default: {MAX_HALAMAN}, max: 12)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=OUTPUT_FILE,
        help="Nama file output CSV"
    )
    parser.add_argument(
        "--list-kategori",
        action="store_true",
        help="Tampilkan daftar kategori Shopee yang tersedia"
    )
    return parser.parse_args()


def tampilkan_kategori():
    print("\n📋 DAFTAR KATEGORI SHOPEE:\n")
    for i, kat in enumerate(KATEGORI_SHOPEE.keys(), 1):
        print(f"  {i:2}. {kat}")
    print()


def minta_input_interaktif():
    """Minta input keyword & kategori secara interaktif jika tidak ada argumen CLI."""
    print("\n" + "═"*60)
    print("  KONFIGURASI PENCARIAN")
    print("═"*60)

    # Keyword
    raw = input(
        "  Keyword produk yang dicari\n"
        "  (pisahkan koma untuk multi-keyword,\n"
        "   kosongkan = pakai default 'produk gresik'): "
    ).strip()
    keywords = [k.strip() for k in raw.split(",") if k.strip()] if raw else DEFAULT_KEYWORDS

    # Kategori
    print("\n  Kategori Shopee (opsional):")
    for i, kat in enumerate(KATEGORI_SHOPEE.keys(), 1):
        print(f"  {i:2}. {kat}")
    raw_kat = input(
        "\n  Masukkan nomor atau nama kategori\n"
        "  (kosongkan = Semua Kategori): "
    ).strip()
    kategori = DEFAULT_KATEGORI
    if raw_kat:
        if raw_kat.isdigit():
            idx = int(raw_kat) - 1
            keys = list(KATEGORI_SHOPEE.keys())
            if 0 <= idx < len(keys):
                kategori = keys[idx]
        else:
            for k in KATEGORI_SHOPEE:
                if raw_kat.lower() in k.lower():
                    kategori = k
                    break

    print(f"\n  ✅ Keyword   : {', '.join(keywords)}")
    print(f"  ✅ Kategori  : {kategori}")
    print("═"*60)
    return keywords, kategori


# ══════════════════════════════════════════════════════════════
# SETUP BROWSER
# ══════════════════════════════════════════════════════════════
def buat_browser():
    if not os.path.exists(CHROMEDRIVER):
        print(f"❌ chromedriver.exe tidak ditemukan di:\n   {CHROMEDRIVER}")
        print("   Download: https://chromedriver.chromium.org/downloads")
        sys.exit(1)

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
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(4)
    return driver


# ══════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════
def jeda(a=2.0, b=3.5):
    time.sleep(random.uniform(a, b))


def buka(driver, url):
    try:
        driver.get(url)
        return True
    except (TimeoutException, WebDriverException):
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
        return False


def ada_gresik(teks):
    t = (teks or "").lower()
    return any(k in t for k in KATA_GRESIK)


def scroll_pelan(driver, n=10):
    for _ in range(n):
        driver.execute_script("window.scrollBy(0, 500)")
        time.sleep(random.uniform(0.4, 0.8))
    time.sleep(1.5)


def bangun_url(keyword, kategori_key, page_idx=0):
    """
    Bangun URL pencarian Shopee dengan keyword, kategori, filter Jawa Timur,
    dan halaman tertentu.
    """
    kw_enc   = keyword.replace(" ", "%20")
    kat_slug = KATEGORI_SHOPEE.get(kategori_key, "")

    base = f"https://shopee.co.id/search?keyword={kw_enc}"
    if kat_slug:
        base += f"&category={kat_slug}"
    # Filter lokasi Jawa Timur (Shopee location code = 217 = Jawa Timur)
    base += f"&locations=217&sortBy=sales&page={page_idx}"
    return base


# ══════════════════════════════════════════════════════════════
# LANGKAH 1: Login manual
# ══════════════════════════════════════════════════════════════
def login_manual(driver):
    print("\n📍 Membuka Shopee...")
    buka(driver, "https://shopee.co.id")
    time.sleep(4)

    print("\n" + "="*60)
    print("  SHOPEE BUTUH LOGIN AGAR FILTER LOKASI BERFUNGSI")
    print("="*60)
    print("  1. Silakan LOGIN di browser yang sudah terbuka")
    print("  2. Setelah login berhasil, kembali ke terminal ini")
    print("  3. Tekan Enter untuk mulai scraping")
    print("="*60)
    input("\n  ▶ Tekan Enter setelah login... ")
    print("  ✅ Login dikonfirmasi, mulai scraping!\n")


# ══════════════════════════════════════════════════════════════
# LANGKAH 2: Scrape 1 keyword
# ══════════════════════════════════════════════════════════════
def scrape_satu_keyword(driver, keyword, kategori_key, max_halaman, seen):
    """
    Scrape produk untuk satu keyword tertentu.
    Mengembalikan list dict produk.
    """
    hasil      = []
    kosong_cnt = 0

    for hal in range(1, max_halaman + 1):
        hal_idx = hal - 1
        url     = bangun_url(keyword, kategori_key, hal_idx)

        print(f"  [{keyword}] Hal {hal:2}/{max_halaman} → ", end="", flush=True)
        buka(driver, url)
        time.sleep(5)
        scroll_pelan(driver, 10)
        time.sleep(2)

        produk_hal = []

        # ── Ambil card produk ──────────────────────────────────
        card_sels = [
            "div[data-sqe='item']",
            "li.shopee-search-item-result__item",
            "div.shopee-search-item-result__item",
            "div[class*='col-xs-2-4']",
            "div[class*='shopee-search-item']",
        ]
        cards = []
        for sel in card_sels:
            c = driver.find_elements(By.CSS_SELECTOR, sel)
            if len(c) > 3:
                cards = c
                break

        if not cards:
            try:
                cards = driver.execute_script("""
                    return Array.from(document.querySelectorAll(
                        '[data-sqe="item"], .shopee-search-item-result__item, [class*="col-xs-2-4"]'
                    ));
                """)
            except Exception:
                pass

        for card in cards:
            try:
                ct = card.text.strip()
                if not ct or not ada_gresik(ct):
                    continue

                lines = [l.strip() for l in ct.split("\n") if l.strip()]

                nama_produk = ""
                harga       = ""
                harga_coret = ""
                diskon      = ""
                rating      = ""
                terjual     = ""
                lokasi      = ""
                nama_toko   = ""

                for l in lines:
                    lo = l.lower()

                    if ada_gresik(l) and len(l) < 40 and not lokasi:
                        lokasi = re.sub(r'^[^\w]*', '', l).strip()

                    elif re.match(r'^Rp[\d.,]+$', l):
                        if not harga:
                            harga = l
                        else:
                            harga_coret = l

                    elif re.match(r'^\d+%$', l) and not diskon:
                        diskon = l

                    elif re.match(r'^\d+\.\d+$', l) and not rating:
                        rating = l

                    elif ("terjual" in lo or
                          re.match(r'^\d+[Kk]+\+?\s*terjual', l)):
                        terjual = l

                    elif (len(l) > 8 and not nama_produk and
                          not any(x in lo for x in [
                              "rp", "terjual", "star+", "pilih lokal", "grosir",
                              "gratis ongkir", "kab.", "gresik", "besok",
                              "2-4 hari", "flash", "promo", "⭐", "★",
                              "cicilan", "cashback", "voucher",
                          ])):
                        nama_produk = l[:200]

                # Ambil nama toko dari href card
                try:
                    links = card.find_elements(By.CSS_SELECTOR, "a")
                    for a in links:
                        h = a.get_attribute("href") or ""
                        m = re.search(r'shopee\.co\.id/([^/?#]+)', h)
                        if m and m.group(1) not in ("search", "product", ""):
                            slug = m.group(1)
                            # Abaikan slug yang berisi angka panjang (ID produk)
                            if not re.match(r'^\d+$', slug):
                                nama_toko = slug.replace("-", " ").title()
                                break
                except Exception:
                    pass

                key = (nama_produk[:60] if nama_produk else "") + "|" + lokasi
                if lokasi and nama_produk and key not in seen:
                    seen.add(key)
                    produk_hal.append({
                        "keyword_cari"  : keyword,
                        "kategori"      : kategori_key,
                        "nama_produk"   : nama_produk,
                        "harga"         : harga or "-",
                        "harga_coret"   : harga_coret or "-",
                        "diskon"        : diskon or "-",
                        "rating"        : rating or "-",
                        "terjual"       : terjual or "-",
                        "lokasi_seller" : lokasi,
                        "nama_toko"     : nama_toko or "-",
                        "platform"      : "Shopee",
                        "waktu_scrape"  : datetime.now().strftime("%Y-%m-%d %H:%M"),
                    })

            except Exception:
                pass

        # Fallback: scan body text
        if not produk_hal:
            try:
                body_lines = driver.find_element(By.TAG_NAME, "body").text.split("\n")
                i = 0
                while i < len(body_lines):
                    baris = body_lines[i].strip()
                    if ada_gresik(baris) and len(baris) < 40:
                        lokasi = re.sub(r'^[^\w]*', '', baris).strip()
                        nama = harga = terjual = ""
                        for back in range(1, 10):
                            if i - back < 0:
                                break
                            prev = body_lines[i - back].strip()
                            lo   = prev.lower()
                            if re.match(r'^Rp[\d.,]+', prev) and not harga:
                                harga = prev
                            elif "terjual" in lo and not terjual:
                                terjual = prev
                            elif (len(prev) > 8 and not nama and
                                  not any(x in lo for x in
                                  ["rp", "terjual", "gresik", "kab.",
                                   "star+", "grosir", "besok", "flash"])):
                                nama = prev[:200]

                        key = (nama[:60] if nama else "") + "|" + lokasi
                        if nama and key not in seen:
                            seen.add(key)
                            produk_hal.append({
                                "keyword_cari"  : keyword,
                                "kategori"      : kategori_key,
                                "nama_produk"   : nama,
                                "harga"         : harga or "-",
                                "harga_coret"   : "-",
                                "diskon"        : "-",
                                "rating"        : "-",
                                "terjual"       : terjual or "-",
                                "lokasi_seller" : lokasi,
                                "nama_toko"     : "-",
                                "platform"      : "Shopee",
                                "waktu_scrape"  : datetime.now().strftime("%Y-%m-%d %H:%M"),
                            })
                    i += 1
            except Exception:
                pass

        hasil.extend(produk_hal)
        n_toko = len(set(p["nama_toko"] for p in hasil if p["nama_toko"] != "-"))
        print(f"{len(produk_hal)} produk | Total: {len(hasil)} | {n_toko} toko unik")

        if len(produk_hal) == 0:
            kosong_cnt += 1
            if kosong_cnt >= 2:
                print(f"  [{keyword}] 2x halaman kosong → lanjut keyword berikutnya")
                break
        else:
            kosong_cnt = 0

        jeda()

    return hasil


# ══════════════════════════════════════════════════════════════
# LANGKAH 3: Loop semua keyword
# ══════════════════════════════════════════════════════════════
def scrape_semua_keyword(driver, keywords, kategori_key, max_halaman):
    semua_hasil = []
    seen        = set()   # Deduplikasi global lintas keyword

    print(f"\n🔍 Scraping {len(keywords)} keyword | Kategori: {kategori_key}\n")
    for i, kw in enumerate(keywords, 1):
        print(f"\n  ── Keyword {i}/{len(keywords)}: '{kw}' ────────────────────")
        hasil_kw = scrape_satu_keyword(driver, kw, kategori_key, max_halaman, seen)
        semua_hasil.extend(hasil_kw)
        print(f"  ✅ '{kw}': {len(hasil_kw)} produk baru ditemukan")
        if i < len(keywords):
            jeda(3, 5)   # Jeda lebih panjang antar keyword

    return semua_hasil


# ══════════════════════════════════════════════════════════════
# SIMPAN CSV
# ══════════════════════════════════════════════════════════════
def simpan_csv(hasil, output_file):
    if not hasil:
        print("\n⚠ Tidak ada data yang ditemukan.")
        return None, None

    kolom_urut = [
        "keyword_cari", "kategori", "nama_produk",
        "harga", "harga_coret", "diskon", "rating", "terjual",
        "lokasi_seller", "nama_toko", "platform", "waktu_scrape",
    ]

    df = pd.DataFrame(hasil).drop_duplicates(subset=["nama_produk", "lokasi_seller"])
    df[[c for c in kolom_urut if c in df.columns]].to_csv(
        output_file, index=False, encoding="utf-8-sig"
    )

    # Ringkasan per toko
    file_toko = output_file.replace(".csv", "_per_toko.csv")
    ringkasan = (
        df.groupby(["nama_toko", "lokasi_seller", "kategori"])
        .agg(
            jumlah_produk   = ("nama_produk", "count"),
            keyword_list    = ("keyword_cari", lambda x: " | ".join(sorted(set(x)))),
            daftar_produk   = ("nama_produk",  lambda x: " | ".join(list(x.unique())[:6])),
        )
        .reset_index()
        .sort_values("jumlah_produk", ascending=False)
    )
    ringkasan.to_csv(file_toko, index=False, encoding="utf-8-sig")

    # Print ringkasan di terminal
    n_toko = df["nama_toko"].nunique()
    print(f"\n{'═'*65}")
    print(f"  HASIL SCRAPING TOKO GRESIK DI SHOPEE")
    print(f"{'═'*65}")
    print(f"  🏪 Total toko unik     : {n_toko}")
    print(f"  📦 Total produk        : {len(df)}")
    print(f"  🔑 Keyword digunakan   : {df['keyword_cari'].nunique()}")
    print(f"  📍 Wilayah Gresik      : {df['lokasi_seller'].nunique()} area")
    print(f"  💾 Semua produk        → {output_file}")
    print(f"  💾 Ringkasan per toko  → {file_toko}")
    print(f"{'═'*65}")

    print(f"\n  TOP TOKO DI GRESIK:\n")
    print(f"  {'No':<4} {'Nama Toko':<28} {'Lokasi':<20} {'Kat':<18} {'Produk':<8} Keyword")
    print(f"  {'-'*95}")
    for i, (_, r) in enumerate(ringkasan.head(20).iterrows(), 1):
        print(
            f"  {i:<4} {str(r.get('nama_toko','-'))[:27]:<28} "
            f"{str(r.get('lokasi_seller','-'))[:19]:<20} "
            f"{str(r.get('kategori','-'))[:17]:<18} "
            f"{r.get('jumlah_produk',0):<8} "
            f"{str(r.get('keyword_list','-'))[:25]}"
        )

    return output_file, file_toko


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    args = parse_args()
    os.makedirs("output", exist_ok=True)

    # ── Tampilkan daftar kategori jika diminta ─────────────────
    if args.list_kategori:
        tampilkan_kategori()
        sys.exit(0)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   SCRAPER TOKO GRESIK DI SHOPEE  — Versi Dinamis            ║")
    print(f"║   Mulai: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print("  Ctrl+C untuk berhenti kapan saja\n")

    # ── Tentukan keyword & kategori ───────────────────────────
    if args.keyword:
        keywords = [k.strip() for k in args.keyword.split(",") if k.strip()]
    else:
        keywords = None  # akan ditanya interaktif

    if args.kategori:
        # Cocokkan ke nama kategori resmi
        kategori_key = DEFAULT_KATEGORI
        for k in KATEGORI_SHOPEE:
            if args.kategori.lower() in k.lower():
                kategori_key = k
                break
    else:
        kategori_key = None  # akan ditanya interaktif

    # Jika salah satu belum ada → minta interaktif
    if keywords is None or kategori_key is None:
        kw_inter, kat_inter = minta_input_interaktif()
        if keywords is None:
            keywords = kw_inter
        if kategori_key is None:
            kategori_key = kat_inter

    max_halaman = min(args.halaman, 12)
    output_file = args.output

    # ── Jalankan scraper ──────────────────────────────────────
    driver = buat_browser()
    hasil  = []

    try:
        login_manual(driver)
        hasil = scrape_semua_keyword(driver, keywords, kategori_key, max_halaman)

        if not hasil:
            print("\n❌ Tidak ada produk Gresik ditemukan.")
            return

        # Auto-save progress
        pd.DataFrame(hasil).to_csv(
            output_file.replace(".csv", "_progress.csv"),
            index=False, encoding="utf-8-sig"
        )

    except KeyboardInterrupt:
        print("\n\n⏹ Dihentikan oleh user.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    simpan_csv(hasil, output_file)
    print(f"\n✅ Selesai! Buka file: {output_file}")
    print(f"   Dashboard: buka dashboard.html di browser\n")


if __name__ == "__main__":
    main()