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

OUTPUT_JSON = "output/gresik_instagram.json"
OUTPUT_CSV = "output/gresik_instagram.csv"

STATE_FILE = "browser/state.json"

JUMLAH_HARI = int(os.getenv("JUMLAH_HARI", 7))

TARGETS = [
    "infogresik",

    "petrokimia.gresik",
]

HEADLESS = False

WAIT_PROFILE = 3000
WAIT_POST = 2500

MAX_POST_PER_ACCOUNT = 20

print("="*60)
print("Memuat Model IndoBERT...")
print("="*60)

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

        self.batas_tanggal = datetime.now() - timedelta(days=7)

    # --------------------------------------------------

    def start_browser(self):

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=HEADLESS
        )

        self.context = self.browser.new_context(
            storage_state=STATE_FILE,
            viewport={
                "width":1400,
                "height":900
            }
        )

        self.page = self.context.new_page()

    # --------------------------------------------------

    def close_browser(self):

        self.browser.close()

        self.playwright.stop()

    # --------------------------------------------------

    def buka_profil(self, username):
        print("="*60)
        print(f"Membuka akun : {username}")
        print("="*60)

        self.username = username

        try:

            self.page.goto(
                f"https://www.instagram.com/{username}/",
                wait_until="networkidle",
                timeout=30000
            )

            self.page.wait_for_timeout(WAIT_PROFILE)

            return True

        except TimeoutError:

            print("Timeout membuka profil")

            return False
        

    # --------------------------------------------------

    def ambil_link_postingan(self):

        hasil = []

        posting = self.page.locator("a[href*='/p/']")

        total = posting.count()

        print(f"Posting ditemukan : {total}")

        sudah = set()

        for i in range(total):

            href = posting.nth(i).get_attribute("href")

            if not href:
                continue

            m = re.search(r"/p/([^/]+)/", href)

            if not m:
                continue

            shortcode = m.group(1)

            if shortcode in sudah:
                continue

            sudah.add(shortcode)

            hasil.append({

                "shortcode": shortcode,

                "url": f"https://www.instagram.com/p/{shortcode}/"

            })

            if len(hasil) >= MAX_POST_PER_ACCOUNT:
                break

        return hasil

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

                wait_until="networkidle",

                timeout=30000

            )

            self.page.wait_for_timeout(WAIT_POST)

            caption = ""
            caption_bersih = ""

            tanggal = ""

            likes = 0

            comments = 0
            

            try:

                caption = self.page.locator("article h1").inner_text()
                caption_bersih = clean_text(caption)

            except:

                pass

            try:

                tanggal = self.page.locator("time").get_attribute("datetime")

            except:

                pass

            try:

                text = self.page.locator("section").inner_text()

                m = re.search(r"([\d,.]+)\s+likes?", text)

                if m:

                    likes = int(

                        m.group(1)

                        .replace(".","")

                        .replace(",","")

                    )

            except:

                pass
                
            try:

                komentar = self.page.locator("ul")

                comments = komentar.count()

            except:

                pass

            return {

                "source": "instagram",

                "id": post["shortcode"],

                "username": self.username,

                "author": self.username,

                "caption": caption or "",

                "teks_asli": caption,

                "teks_bersih": caption_bersih,

                "likes": likes,

                "comments": comments,

                "tanggal": tanggal,

                "sentimen": analisis_sentimen(caption_bersih),

                "topik": klasifikasi_topik(caption_bersih),

                "url": post["url"]

            }


        except TimeoutError:

                print("Timeout")

                return None
        except Exception as e:

                print(e)
                return None

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