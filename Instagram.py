"""
Scraper komentar Instagram berdasarkan KEYWORD menggunakan Selenium.
Alur: Cari keyword → kumpulkan URL postingan → ambil komentar tiap postingan → analisis sentimen.

Install:
    pip install selenium pandas transformers torch webdriver-manager

Cara pakai:
    1. Isi IG_COOKIES (dari F12 → Application → Cookies → instagram.com)
    2. Isi KEYWORDS dengan kata kunci yang ingin dicari
    3. python Instagram_keyword.py
"""

import time
import json
import re
import os
import random
import pandas as pd
from transformers import pipeline

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    InvalidSessionIdException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# ══════════════════════════════════════════════════════════════
#  KONFIGURASI
# ══════════════════════════════════════════════════════════════

IG_USERNAME = "sanikhsan336"   # username akun kamu

# Ambil cookie dari browser Chrome yang sudah login Instagram:
# F12 → Application → Cookies → https://www.instagram.com → copy nilai tiap cookie
IG_COOKIES = {
    "sessionid"  : "12624996697%3AteWM3Pc9bRYEtu%3A5%3AAYgLkRCiPdCuiQTWmplyQG-RVkbXfOhxmqE1k9Lqiw",
    "csrftoken"  : "Hdv1nIq1UCSW72qYTe8zqaNkFNAXzhoe",
    "ds_user_id" : "12624996697",
    "mid"        : "akiS_wALAAFCy3HhTuj6TLtNlN4G",
    "ig_did"     : "27B7384E-D2AB-458B-B44B-8AEC11485196",
    "rur"        : "EAG%2C17841412620928124%2C1784864829%3A01ff430327ecb157770a8b91824d7afff36fc8c7ea5b536a100519283e54049c8455a86a",
}
# ── Keyword yang ingin dicari ──────────────────────────────────
KEYWORDS = [
    "Gresik",
    "Kabupaten Gresik",
    "Pemkab Gresik"
]

MAKS_POST_PER_KEYWORD   = 30    # berapa postingan yang diambil per keyword
MAKS_KOMENTAR_PER_POST  = 50    # berapa komentar per postingan
TAMPILKAN_BROWSER       = True  # True = lihat browser, False = headless

os.makedirs("output", exist_ok=True)

# ══════════════════════════════════════════════════════════════
#  MODEL SENTIMEN IndoBERT
# ══════════════════════════════════════════════════════════════
print("Memuat model IndoBERT...")
sentimen_model = pipeline(
    "text-classification",
    model="mdhugol/indonesia-bert-sentiment-classification"
)
LABEL_MAP = {"LABEL_0": "positif", "LABEL_1": "netral", "LABEL_2": "negatif"}


# ══════════════════════════════════════════════════════════════
#  FUNGSI PEMBANTU
# ══════════════════════════════════════════════════════════════

def jeda(min_s=1.5, max_s=3.5):
    time.sleep(random.uniform(min_s, max_s))

def bersihkan_teks(teks):
    teks = re.sub(r"http\S+", "", teks)
    teks = re.sub(r"@\w+", "", teks)
    teks = re.sub(r"#(\w+)", r"\1", teks)
    teks = re.sub(r"[^\w\s]", "", teks)
    return re.sub(r"\s+", " ", teks).strip().lower()

def cek_sentimen(teks):
    if not teks or len(teks) < 5:
        return "netral", 0.0
    h = sentimen_model(teks[:512])[0]
    return LABEL_MAP.get(h["label"], "netral"), round(h["score"], 3)

def deteksi_topik(teks):
    t = teks.lower()
    if any(k in t for k in ["banjir", "longsor", "gempa", "bencana"]):
        return "bencana"
    if any(k in t for k in ["pabrik", "industri", "petrokimia", "semen", "pupuk"]):
        return "industri"
    if any(k in t for k in ["kuliner", "makanan", "soto", "bandeng", "otak-otak"]):
        return "kuliner"
    if any(k in t for k in ["wisata", "pantai", "religi", "sunan giri"]):
        return "wisata"
    if any(k in t for k in ["pemda", "bupati", "pemerintah", "apbd"]):
        return "pemerintahan"
    if any(k in t for k in ["persegres", "sepak bola", "liga"]):
        return "olahraga"
    if any(k in t for k in ["macet", "jalan", "tol", "infrastruktur"]):
        return "infrastruktur"
    return "umum"

def cek_sesi_aktif(driver):
    try:
        _ = driver.current_url
        return True
    except (InvalidSessionIdException, WebDriverException):
        return False


# ══════════════════════════════════════════════════════════════
#  BUAT DRIVER
# ══════════════════════════════════════════════════════════════

def buat_driver():
    opts = Options()
    if not TAMPILKAN_BROWSER:
        opts.add_argument("--headless=new")

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1366,768")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ══════════════════════════════════════════════════════════════
#  LOGIN INSTAGRAM
# ══════════════════════════════════════════════════════════════

def login_instagram(driver) -> bool:
    print("Membuka Instagram...")
    driver.get("https://www.instagram.com/")
    jeda(3, 5)

    if not cek_sesi_aktif(driver):
        print("  Browser crash saat membuka Instagram.")
        return False

    driver.delete_all_cookies()

    for nama, nilai in IG_COOKIES.items():
        if not nilai:
            continue
        driver.add_cookie({
            "name"  : nama,
            "value" : nilai,
            "domain": ".instagram.com",
            "path"  : "/",
            "secure": True,
        })

    driver.refresh()
    jeda(4, 6)

    if not cek_sesi_aktif(driver):
        print("  Browser crash setelah inject cookie.")
        return False

    if "accounts/login" in driver.current_url or "auth_platform" in driver.current_url:
        driver.save_screenshot("output/debug_login.png")
        print("  Cookie tidak valid atau expired.")
        print("  Ambil ulang cookie dari browser lalu update IG_COOKIES.")
        return False

    print(f"  Login berhasil sebagai @{IG_USERNAME}\n")
    return True


# ══════════════════════════════════════════════════════════════
#  TUTUP POPUP
# ══════════════════════════════════════════════════════════════

def tutup_popup(driver):
    xpaths = [
        "//button[contains(text(),'Tidak Sekarang')]",
        "//button[contains(text(),'Not Now')]",
        "//button[contains(text(),'Tutup')]",
        "//button[contains(text(),'Close')]",
        "//div[@role='dialog']//button[contains(@aria-label,'Close')]",
    ]
    for xpath in xpaths:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            btn.click()
            jeda(1, 2)
            return
        except Exception:
            continue


# ══════════════════════════════════════════════════════════════
#  CARI POSTINGAN BERDASARKAN KEYWORD
# ══════════════════════════════════════════════════════════════

def cari_postingan(driver, keyword: str, maks_post: int) -> list[str]:
    """
    Buka halaman pencarian Instagram, ketik keyword,
    lalu kumpulkan URL postingan dari hasil pencarian.
    Mengembalikan list shortcode.
    """
    print(f"  Mencari postingan dengan keyword: '{keyword}'")
    url_hasil = []

    # ── Coba via URL explore/search ───────────────────────────
    # Encode keyword untuk URL
    keyword_encoded = keyword.replace(" ", "%20")
    search_url = f"https://www.instagram.com/explore/search/keyword/?q={keyword_encoded}"

    try:
        driver.get(search_url)
        jeda(5, 8)
        tutup_popup(driver)
    except Exception as e:
        print(f"  Gagal buka halaman search: {e}")
        return []

    if not cek_sesi_aktif(driver):
        return []

    # Scroll beberapa kali untuk load lebih banyak postingan
    for scroll in range(5):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            jeda(2, 3)
        except Exception:
            break

        # Ambil semua link postingan yang sudah muncul
        try:
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
            for link in links:
                href = link.get_attribute("href")
                if href and "/p/" in href:
                    # Ekstrak shortcode dari URL
                    match = re.search(r"/p/([^/?]+)", href)
                    if match:
                        sc = match.group(1)
                        if sc not in url_hasil:
                            url_hasil.append(sc)
        except Exception:
            break

        if len(url_hasil) >= maks_post:
            break

        print(f"  Scroll {scroll+1}: {len(url_hasil)} postingan ditemukan", end="\r")

    print(f"\n  Ditemukan {len(url_hasil)} postingan untuk keyword '{keyword}'")

    # ── Fallback: via kolom pencarian di navbar ────────────────
    if not url_hasil:
        print("  Mencoba via kolom pencarian navbar...")
        try:
            driver.get("https://www.instagram.com/")
            jeda(3, 5)
            tutup_popup(driver)

            # Klik ikon Search di sidebar
            search_icon_xpaths = [
                "//a[@href='/explore/']",
                "//span[contains(text(),'Search')]",
                "//a[contains(@href,'explore')]",
                "//div[@role='button'][contains(.,'Search')]",
            ]
            klik_berhasil = False
            for xpath in search_icon_xpaths:
                try:
                    btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, xpath))
                    )
                    btn.click()
                    klik_berhasil = True
                    jeda(2, 3)
                    break
                except Exception:
                    continue

            if not klik_berhasil:
                print("  Tidak bisa klik ikon Search.")
                return []

            # Ketik keyword di input pencarian
            input_el = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='Search'], input[aria-label*='Search'], input[aria-label*='Cari']"))
            )
            input_el.clear()
            for ch in keyword:
                input_el.send_keys(ch)
                time.sleep(random.uniform(0.05, 0.15))
            jeda(2, 3)

            # Tekan Enter atau pilih tab "Posts"
            input_el.send_keys(Keys.RETURN)
            jeda(3, 5)
            tutup_popup(driver)

            # Scroll dan kumpulkan postingan
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                jeda(2, 3)
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/p/']")
                for link in links:
                    href = link.get_attribute("href")
                    if href:
                        match = re.search(r"/p/([^/?]+)", href)
                        if match:
                            sc = match.group(1)
                            if sc not in url_hasil:
                                url_hasil.append(sc)
                if len(url_hasil) >= maks_post:
                    break

            print(f"  Fallback: {len(url_hasil)} postingan ditemukan")

        except Exception as e:
            print(f"  Fallback pencarian gagal: {e}")

    return url_hasil[:maks_post]


# ══════════════════════════════════════════════════════════════
#  AMBIL KOMENTAR DARI SATU POSTINGAN
# ══════════════════════════════════════════════════════════════

def ambil_komentar_post(driver, shortcode: str, maks: int) -> list[dict]:
    """Buka postingan dan ambil komentar beserta username & caption."""
    url = f"https://www.instagram.com/p/{shortcode}/"
    print(f"    Membuka: {url}")

    try:
        driver.get(url)
    except Exception as e:
        print(f"    Gagal buka URL: {e}")
        return []

    jeda(6, 9)
    if not cek_sesi_aktif(driver):
        return []

    tutup_popup(driver)

    # Ambil caption
    caption = ""
    try:
        cap_el = driver.find_element(
            By.CSS_SELECTOR,
            "div._a9zs span, h1, div[data-testid='post-comment-root'] span"
        )
        caption = cap_el.text[:100].replace("\n", " ")
    except Exception:
        caption = shortcode

    # Klik "Lihat semua komentar"
    try:
        btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH,
                "//span[contains(text(),'Lihat semua') or contains(text(),'View all') "
                "or contains(text(),'komentar') or contains(text(),'comments')]"
            ))
        )
        btn.click()
        jeda(2, 3)
    except TimeoutException:
        pass
    except Exception:
        pass

    komentar  = []
    sudah     = set()
    tidak_bertambah = 0

    def kumpulkan():
        if not cek_sesi_aktif(driver):
            return
        selectors = [
            "div._a9zs span",
            "ul._a9ym li div._a9zs",
            "span._aade",
            "ul[class*='comment'] span[dir='auto']",
            "div[role='dialog'] ul li span[dir='auto']",
            "article ul li span[dir='auto']",
            "ul li span[dir='auto']",
        ]
        for sel in selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                continue
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

    kumpulkan()

    while len(komentar) < maks:
        if not cek_sesi_aktif(driver):
            break

        sebelum = len(komentar)

        try:
            btn_muat = driver.find_element(
                By.XPATH,
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

    print(f"    ✓ {len(komentar)} komentar dari postingan ini")
    return komentar[:maks]


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    # Validasi cookie
    kosong = [k for k, v in IG_COOKIES.items() if not v]
    if kosong:
        print("Cookie belum diisi:")
        for k in kosong:
            print(f"  - {k}")
        print("\nF12 → Application → Cookies → https://www.instagram.com")
        return

    driver     = buat_driver()
    semua_data = []

    try:
        if not login_instagram(driver):
            return

        for keyword in KEYWORDS:
            print(f"\n{'─'*50}")
            print(f"KEYWORD: '{keyword}'")
            print(f"{'─'*50}")

            shortcodes = cari_postingan(driver, keyword, MAKS_POST_PER_KEYWORD)

            if not shortcodes:
                print(f"  Tidak ada postingan ditemukan untuk '{keyword}'")
                continue

            for i, sc in enumerate(shortcodes, 1):
                print(f"\n  [{i}/{len(shortcodes)}] Postingan: {sc}")

                if not cek_sesi_aktif(driver):
                    print("  Browser tidak aktif, melewati.")
                    continue

                komentar_list = ambil_komentar_post(driver, sc, MAKS_KOMENTAR_PER_POST)

                for k in komentar_list:
                    teks_asli   = k["text"]
                    teks_bersih = bersihkan_teks(teks_asli)
                    label, skor = cek_sentimen(teks_bersih)
                    topik       = deteksi_topik(teks_asli)

                    semua_data.append({
                        "keyword"    : keyword,
                        "shortcode"  : sc,
                        "link_postingan": k.get("link_postingan", ""),
                        "caption"    : k.get("caption", ""),
                        "teks_asli"  : teks_asli,
                        "teks_bersih": teks_bersih,
                        "sentimen"   : label,
                        "skor"       : skor,
                        "topik"      : topik,
                    })

                jeda(3, 6)

    except Exception as e:
        print(f"\nError tidak terduga: {e}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    if not semua_data:
        print("\nTidak ada data terkumpul.")
        print("Kemungkinan penyebab:")
        print("  1. Cookie expired — ambil ulang dari browser.")
        print("  2. Keyword tidak menghasilkan postingan publik.")
        print("  3. Instagram memblokir sementara — tunggu 10 menit.")
        return

    # ── Simpan ────────────────────────────────────────────────
    df = pd.DataFrame(semua_data)

    df = df[
        [
            "shortcode",
            "link_postingan",
            "teks_asli",
            "teks_bersih",
            "sentimen",
            "skor",
            "topik"
        ]
    ]

    df.to_csv(
        "output/gresik_ig_sentimen.csv",
        index=False,
        encoding="utf-8-sig"
    )


    hasil_json = []

    for row in semua_data:
        hasil_json.append({
            "shortcode": row["shortcode"],
            "link_postingan": row["link_postingan"],
            "teks_asli": row["teks_asli"],
            "teks_bersih": row["teks_bersih"],
            "sentimen": row["sentimen"],
            "skor": row["skor"],
            "topik": row["topik"]
        })

    with open("output/keyword_ig_komentar.json", "w", encoding="utf-8") as f:
        json.dump(semua_data, f, ensure_ascii=False, indent=2)

    # ── Ringkasan ─────────────────────────────────────────────
    total = len(df)
    print(f"\n{'='*47}")
    print(f"  HASIL ANALISIS SENTIMEN — KEYWORD SEARCH")
    print(f"{'='*47}")
    print(f"  Total komentar : {total}")

    print(f"\n  Sentimen:")
    for lbl, jml in df["sentimen"].value_counts().items():
        bar = "█" * int(jml / total * 30)
        print(f"  {lbl:10s} {jml:4d} ({jml/total*100:5.1f}%)  {bar}")

    print(f"\n  Topik terpopuler:")
    for topik, jml in df["topik"].value_counts().head(5).items():
        print(f"  {topik:15s} {jml:4d} komentar")

    print(f"\n  Hasil per keyword:")
    for kw, grp in df.groupby("keyword"):
        print(f"  '{kw}' → {len(grp)} komentar dari {grp['shortcode'].nunique()} postingan")

    print(f"\n  File disimpan:")
    print(f"  output/keyword_ig_sentimen.csv")
    print(f"  output/keyword_ig_komentar.json")


if __name__ == "__main__":
    main()