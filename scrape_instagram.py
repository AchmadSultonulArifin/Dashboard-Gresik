import os
import json
from datetime import datetime, timedelta

import pandas as pd
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
    "pemkabgresik",
    "petrokimia.gresik",
]

# ======================================================
# CLASS
# ======================================================


class InstagramScraper:

    def __init__(self):

        self.data = []

        self.batas_tanggal = datetime.now() - timedelta(days=JUMLAH_HARI)

    # --------------------------------------------------

    def start_browser(self):

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=False
        )

        self.context = self.browser.new_context(
            storage_state=STATE_FILE
        )

        self.page = self.context.new_page()

    # --------------------------------------------------

    def close_browser(self):

        self.browser.close()

        self.playwright.stop()

    # --------------------------------------------------

    def buka_profil(self, username):

        print("=" * 60)
        print(f"Membuka akun : {username}")
        print("=" * 60)

        url = f"https://www.instagram.com/{username}/"

        self.page.goto(url)

        self.page.wait_for_timeout(4000)

    # --------------------------------------------------

    def ambil_link_postingan(self):

        hasil = []

        posts = self.page.locator("a[href*='/p/']")

        total = posts.count()

        print(f"Posting ditemukan : {total}")

        for i in range(total):

            try:

                href = posts.nth(i).get_attribute("href")

                if href is None:
                    continue

                full_url = "https://www.instagram.com" + href

                shortcode = href.split("/")[2]

                hasil.append(
                    {
                        "shortcode": shortcode,
                        "url": full_url
                    }
                )

            except Exception:

                pass

        return hasil

    # --------------------------------------------------

    def scrape_profile(self, username):
        self.username = username
        self.buka_profil(username)

        daftar_post = self.ambil_link_postingan()

        print()

        print(f"Total posting ditemukan : {len(daftar_post)}")

        print()

        for i, post in enumerate(daftar_post):

            print(f"[{i+1}/{len(daftar_post)}] Membuka posting...")

            hasil = self.ambil_detail_postingan(post)

            if hasil:

                self.data.append(hasil)

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

        df.to_csv(
            OUTPUT_CSV,
            index=False,
            encoding="utf-8-sig"
        )

        print()

        print("=" * 60)

        print("SELESAI")

        print(f"Total Data : {len(self.data)}")

        print("=" * 60)


# ======================================================

def main():

    scraper = InstagramScraper()

    scraper.start_browser()

    for akun in TARGETS:

        scraper.scrape_profile(akun)

    scraper.save()

    scraper.close_browser()


def ambil_detail_postingan(self, post):

    try:

        self.page.goto(post["url"])

        self.page.wait_for_timeout(3000)

        caption = ""

        tanggal = ""

        try:
            caption = self.page.locator("article h1").inner_text(timeout=3000)
        except:
            pass

        try:
            tanggal = self.page.locator("time").get_attribute("datetime")
        except:
            pass

        return {
            "source": "instagram",
            "id": post["shortcode"],
            "author": self.username,
            "caption": caption,
            "tanggal": tanggal,
            "url": post["url"]
        }

    except Exception as e:

        print(e)

        return None
    


# ======================================================

if __name__ == "__main__":

    main()