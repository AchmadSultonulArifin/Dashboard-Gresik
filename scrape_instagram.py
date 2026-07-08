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

        self.page.mouse.wheel(0,5000)

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

            df = df.sort_values(
                    "tanggal",
                    ascending=False)
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

        except Exception:

            return None

        caption = ""

        tanggal = ""

        likes = 0

        komentar = self.ambil_semua_komentar()

        comments = len(komentar)

        try:

            waktu = self.page.locator("time")

            tanggal = waktu.first.get_attribute("datetime")

        except:

            pass

        selectors = [

                        "article h1",

                        "article div[dir='auto'] span",

                        "article span[dir='auto']",

                        "div[role='dialog'] h1",

                        "div[role='dialog'] span",

                        "meta[property='og:description']"

                    ]

        for s in selectors:

            try:

                teks = self.page.locator(s).first.inner_text().strip()

                if len(teks) > 20:

                    caption = teks

                    break

            except:

                pass

        try:

            body = self.page.locator("body").inner_text()

            m = re.search(r'([\d.,]+)\s+likes', body)

            if m:

                likes = int(

                    m.group(1)

                    .replace(".","")

                    .replace(",","")

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
    
    def ambil_semua_komentar(self):

        komentar = []

        sudah = set()

        # klik tombol komentar berkali-kali
        for _ in range(MAX_COMMENT_CLICK):

            try:

                tombol = self.page.locator(
                    "text=View all comments"
                )

                if tombol.count() > 0:

                    tombol.first.click()

                    self.page.wait_for_timeout(WAIT_COMMENT)

            except:
                pass

            try:

                tombol = self.page.locator(
                    "text=Load more comments"
                )

                if tombol.count() > 0:

                    tombol.last.click()

                    self.page.wait_for_timeout(WAIT_COMMENT)

            except:
                pass

            try:

                self.page.mouse.wheel(0,2500)

                self.page.wait_for_timeout(800)

            except:
                pass

        # ambil semua komentar

        kandidat = self.page.locator("ul ul span")

        total = kandidat.count()

        print("Komentar ditemukan :", total)

        for i in range(total):

            try:

                teks = kandidat.nth(i).inner_text().strip()

                if len(teks) < 2:
                    continue

                if teks in sudah:
                    continue

                sudah.add(teks)

                komentar.append(teks)

            except:

                pass

        return komentar

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

        if label in ["positive","positif"]:
            return "positif"

        if label in ["negative","negatif"]:
            return "negatif"

        return "netral"

    except:

        return "netral"
    
TOPIK = {

    "infrastruktur":[
        "jalan",
        "jembatan",
        "lampu",
        "trotoar"
    ],

    "pendidikan":[
        "sekolah",
        "guru",
        "siswa"
    ],

    "kesehatan":[
        "rumah sakit",
        "puskesmas",
        "dokter"
    ],

    "ekonomi":[
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