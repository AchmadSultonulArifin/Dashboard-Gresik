import os
import json
import re
import time
from datetime import datetime, timedelta
from transformers import pipeline
from transformers import AutoTokenizer
from transformers import AutoModelForSequenceClassification

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError

load_dotenv()

# ======================================================
# KONFIGURASI
# ======================================================

OUTPUT_FOLDER = "output"

OUTPUT_JSON = os.path.join(
    OUTPUT_FOLDER,
    "gresik_instagram.json"
)

OUTPUT_CSV = os.path.join(
    OUTPUT_FOLDER,
    "gresik_instagram.csv"
)

STATE_FILE = "browser/state.json"

HEADLESS = False

WAIT_PROFILE = 4000

WAIT_POST = 3000

WAIT_COMMENT = 1500

MAX_POST_PER_ACCOUNT = 20

MAX_COMMENT_CLICK = 50

JUMLAH_HARI = int(
    os.getenv(
        "JUMLAH_HARI",
        7
    )
)

TARGETS = [

    "infogresik",

    "petrokimia.gresik",

]

classifier = pipeline(
    "text-classification",
    model="w11wo/indonesian-roberta-base-sentiment-classifier",
    truncation=True
)

# ======================================================
# FILTER TEKS YANG BUKAN KOMENTAR
# ======================================================

TEKS_DIABAIKAN = {
    "view all comments",
    "load more comments",
    "reply",
    "replies",
    "balas",
    "lihat semua komentar",
    "like",
    "likes",
    "likes.",
    "follow",
    "following",
    "followers",
    "share",
    "save",
    "more",
    "hide",
    "report",
    "translate",
    "see translation",
    "terjemahan",
    "send",
    "kirim",
    "add a comment",
    "tambahkan komentar",
}

def is_valid_comment(teks: str) -> bool:
    """
    Mengembalikan True jika teks kemungkinan adalah komentar asli.
    """
    t = teks.strip()

    # Terlalu pendek
    if len(t) < 3:
        return False

    # Hanya angka (jumlah like, dll)
    if re.fullmatch(r"[\d.,\s]+", t):
        return False

    # Hanya emoji
    if re.fullmatch(r"[\U00010000-\U0010ffff\s]+", t):
        return False

    # Masuk daftar teks UI yang diabaikan
    if t.lower() in TEKS_DIABAIKAN:
        return False

    # Pola waktu seperti "2 jam", "3 hari", "1 minggu", "Just now", "2h", "5d"
    if re.fullmatch(
        r"(\d+\s*(jam|hari|minggu|bulan|detik|w|h|d|m)\s*(ago)?|\d+[whdm]|just now|baru saja)",
        t,
        re.IGNORECASE
    ):
        return False

    return True


# ======================================================
# CLASS
# ======================================================


class InstagramScraper:

    def __init__(self):

        self.data = []

        self.username = ""

        self.page = None

        self.context = None

        self.browser = None

        self.playwright = None

        self.batas_tanggal = (
            datetime.now()
            - timedelta(days=JUMLAH_HARI)
        )

    # --------------------------------------------------

    def start_browser(self):

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(

            headless=HEADLESS,

            slow_mo=300

        )

        self.context = self.browser.new_context(

            storage_state=STATE_FILE,

            viewport={

                "width": 1400,

                "height": 900

            }

        )

        self.page = self.context.new_page()

        self.page.set_default_timeout(30000)

        self.page.set_default_navigation_timeout(30000)

    # --------------------------------------------------

    def close_browser(self):

        try:

            if self.context:

                self.context.close()

        except:

            pass

        try:

            if self.browser:

                self.browser.close()

        except:

            pass

        try:

            if self.playwright:

                self.playwright.stop()

        except:

            pass

    # --------------------------------------------------

    def buka_profil(self, username):

        self.username = username

        print("="*60)
        print(f"Membuka akun : {username}")
        print("="*60)

        try:

            self.page.goto(

                f"https://www.instagram.com/{username}/",

                wait_until="domcontentloaded"

            )

            self.page.wait_for_timeout(WAIT_PROFILE)

            return True

        except Exception as e:

            print(e)

            return False

    # --------------------------------------------------

    def ambil_link_postingan(self):

        posting = []

        sudah = set()

        self.page.mouse.wheel(0, 5000)

        self.page.wait_for_timeout(1500)

        cards = self.page.locator("a[href*='/p/']")

        total = cards.count()

        print()

        print(f"Posting ditemukan : {total}")

        print()

        for i in range(total):

            try:

                href = cards.nth(i).get_attribute("href")

                if href is None:

                    continue

                if "/p/" not in href:

                    continue

                shortcode = href.split("/p/")[1].split("/")[0]

                if shortcode in sudah:

                    continue

                sudah.add(shortcode)

                posting.append({

                    "id": shortcode,

                    "url": f"https://www.instagram.com/p/{shortcode}/"

                })

                if len(posting) >= MAX_POST_PER_ACCOUNT:

                    break

            except:

                pass

        return posting

    # --------------------------------------------------

    def scrape_profile(self, username):

        if not self.buka_profil(username):
            return

        daftar = self.ambil_link_postingan()

        print()

        print(f"Total posting diproses : {len(daftar)}")

        print()

        for i, post in enumerate(daftar):

            print(f"[{i+1}/{len(daftar)}]")

            hasil = self.ambil_detail_postingan(post)

            if hasil is not None:

                self.data.append(hasil)
                print(
                    f"✔ {hasil['username']} | "
                    f"{hasil['likes']} like | "
                    f"{hasil['comments']} komentar"
                )

                time.sleep(2)

    # --------------------------------------------------

    def save(self):

        os.makedirs("output", exist_ok=True)

        with open(
            OUTPUT_JSON,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.data,
                f,
                ensure_ascii=False,
                indent=4
            )

        df = pd.DataFrame(self.data)

        if not df.empty:

            df = df.drop_duplicates(subset=["id"])
            df = df.sort_values(
                "tanggal",
                ascending=False
            )

            if "komentar" not in df.columns:
                df["komentar"] = ""

            if "caption" not in df.columns:
                df["caption"] = ""

            if "likes" not in df.columns:
                df["likes"] = 0

            if "comments" not in df.columns:
                df["comments"] = 0

            df.to_csv(

                OUTPUT_CSV,

                index=False,

                encoding="utf-8-sig"

            )

            print()

            print(df[[
                "author",
                "sentimen",
                "topik",
                "likes"
            ]].head())

    # ======================================================

    def ambil_detail_postingan(self, post):

        try:

            self.page.goto(

                post["url"],

                wait_until="domcontentloaded"

            )

            self.page.wait_for_timeout(WAIT_POST)

            html = self.page.content()

            with open("debug_instagram.html", "w", encoding="utf-8") as f:

                f.write(html)

        except Exception:

            return None

        caption = ""

        tanggal = ""

        likes = 0

        # ---- Ambil komentar (DIPERBAIKI) ----
        komentar = self.ambil_semua_komentar()

        comments = len(komentar)

        try:

            waktu = self.page.locator("time")

            tanggal = waktu.first.get_attribute("datetime")

        except:

            pass

        selectors = [

            "article h1",

            "article span",

            "article div span",

            "div[role='dialog'] span",

            "div[dir='auto'] span",

            "span"

        ]

        for s in selectors:

            try:

                teks = self.page.locator(s).first.inner_text().strip()

                if len(teks) > 20:

                    caption = teks

                    break

            except:

                pass

        print("=" * 50)
        print("Caption ditemukan:")
        print(caption)
        print("=" * 50)

        try:

            body = self.page.locator("body").inner_text()

            m = re.search(r'([\d.,]+)\s+likes', body)

            if m:

                likes = int(

                    m.group(1)

                    .replace(".", "")

                    .replace(",", "")

                )

        except:

            pass

        teks = clean_text(
            caption + " " + " ".join(komentar)
        )

        sentimen = analisis_sentimen(teks)

        topik = klasifikasi_topik(teks)

        return {

            "source": "instagram",

            "id": post["id"],

            "username": self.username,

            "author": self.username,

            "caption": caption,

            "komentar": " || ".join(komentar),

            "teks_asli": caption + " " + " ".join(komentar),

            "teks_bersih": teks,

            "likes": likes,

            "comments": comments,

            "tanggal": tanggal,

            "sentimen": sentimen,

            "topik": topik,

            "url": post["url"]

        }

    # --------------------------------------------------
    # FUNGSI AMBIL KOMENTAR — DIPERBAIKI TOTAL
    # --------------------------------------------------

    def ambil_semua_komentar(self) -> list[str]:
        """
        Mengambil semua komentar dari halaman postingan Instagram.

        Perbaikan utama vs kode lama:
        1. Loop load-more dan pengumpulan komentar dipisah.
        2. Selector lebih spesifik (ul[class*='comment'] dan
           div[role='dialog'] ul).
        3. Filter is_valid_comment() menyaring elemen UI.
        4. Scroll di dalam section komentar, bukan di seluruh halaman.
        """

        komentar_set: set[str] = set()
        komentar_list: list[str] = []

        # ── TAHAP 1 : Muat semua komentar ─────────────────────────
        for klik in range(MAX_COMMENT_CLICK):

            halaman_berubah = False

            # Tombol "View all comments"
            try:
                tombol_view = self.page.locator(
                    "button:has-text('View all comments'), "
                    "span:has-text('View all comments')"
                )
                if tombol_view.count() > 0:
                    tombol_view.first.click()
                    self.page.wait_for_timeout(WAIT_COMMENT)
                    halaman_berubah = True
            except Exception:
                pass

            # Tombol "Load more comments"
            try:
                tombol_more = self.page.locator(
                    "button:has-text('Load more comments'), "
                    "span:has-text('Load more comments')"
                )
                if tombol_more.count() > 0:
                    tombol_more.last.click()
                    self.page.wait_for_timeout(WAIT_COMMENT)
                    halaman_berubah = True
            except Exception:
                pass

            # Scroll di area komentar — lebih akurat daripada scroll halaman
            try:
                # Coba scroll di dalam container komentar dulu
                container = self.page.locator(
                    "div[role='dialog'], "
                    "article"
                )
                if container.count() > 0:
                    box = container.first.bounding_box()
                    if box:
                        cx = box["x"] + box["width"] / 2
                        cy = box["y"] + box["height"] / 2
                        self.page.mouse.move(cx, cy)
                        self.page.mouse.wheel(0, 3000)
                        self.page.wait_for_timeout(800)
                        halaman_berubah = True
            except Exception:
                pass

            # Jika tidak ada perubahan pada iterasi ini, hentikan lebih awal
            if not halaman_berubah and klik > 2:
                break

        # ── TAHAP 2 : Kumpulkan teks komentar ─────────────────────
        #
        # Urutan selector dari yang paling spesifik ke yang paling umum.
        # Kita ambil yang pertama kali menghasilkan elemen > 0.
        SELECTORS_KOMENTAR = [
            # Komentar di dalam dialog (postingan yang dibuka via feed)
            "div[role='dialog'] ul li span[dir='auto']",
            # Komentar di halaman postingan langsung
            "article ul li span[dir='auto']",
            # Fallback: semua span dir=auto di halaman
            "span[dir='auto']",
        ]

        kandidat = None
        for s in SELECTORS_KOMENTAR:
            try:
                lok = self.page.locator(s)
                if lok.count() > 0:
                    kandidat = lok
                    print(f"Selector komentar dipakai: {s} ({lok.count()} elemen)")
                    break
            except Exception:
                pass

        if kandidat is None:
            print("⚠ Tidak ada elemen komentar ditemukan.")
            return []

        total = kandidat.count()
        print(f"Total elemen komentar sebelum filter: {total}")

        for i in range(total):
            try:
                teks = kandidat.nth(i).inner_text().strip()

                if not is_valid_comment(teks):
                    continue

                if teks in komentar_set:
                    continue

                komentar_set.add(teks)
                komentar_list.append(teks)

            except Exception:
                pass

        print(f"✔ Komentar valid terkumpul: {len(komentar_list)}")
        return komentar_list


# ======================================================
# UTILITAS
# ======================================================

def clean_text(text):

    if text is None:
        return ""

    text = str(text)

    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"www\S+", "", text)

    text = re.sub(r"@\w+", "", text)

    text = re.sub(r"#(\w+)", r"\1", text)

    text = re.sub(r"\n", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def analisis_sentimen(teks):

    if teks is None:
        return "netral"

    teks = str(teks).strip()

    if teks == "":
        return "netral"

    try:

        hasil = classifier(teks)[0]

        label = hasil["label"].lower()

        if label in ["positive", "positif"]:
            return "positif"

        if label in ["negative", "negatif"]:
            return "negatif"

        return "netral"

    except:

        return "netral"


TOPIK = {

    "infrastruktur": [
        "jalan",
        "jembatan",
        "lampu",
        "trotoar"
    ],

    "pendidikan": [
        "sekolah",
        "guru",
        "siswa"
    ],

    "kesehatan": [
        "rumah sakit",
        "puskesmas",
        "dokter"
    ],

    "ekonomi": [
        "umkm",
        "pasar",
        "usaha"
    ]

}


def klasifikasi_topik(teks):

    teks = teks.lower()

    for topik, kata in TOPIK.items():

        for k in kata:

            if k in teks:

                return topik

    return "lainnya"


# ======================================================

def main():
    scraper = InstagramScraper()

    try:
        scraper.start_browser()

        for akun in TARGETS:
            scraper.scrape_profile(akun)

        scraper.save()

    finally:
        scraper.close_browser()


# ======================================================

if __name__ == "__main__":

    main()