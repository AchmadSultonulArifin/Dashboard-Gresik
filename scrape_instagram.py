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

        try:
            self.page.goto(
                url,
                wait_until="commit",
                timeout=15000
            )

            self.page.wait_for_timeout(3000)

        except TimeoutError:
            print(f"Gagal membuka akun: {username}")
            return False

        return True

    # --------------------------------------------------

    def ambil_link_postingan(self):

        hasil = []

        posts = self.page.locator("a[href*='/p/']")

        total = posts.count()

        print(f"Posting ditemukan : {total}")

        for i in range(total):

            try:

                href = posts.nth(i).get_attribute("href")
                print(href)

                if href is None:
                    continue

                parts = href.strip("/").split("/")

                try:
                    idx = parts.index("p")
                    shortcode = parts[idx + 1]
                except ValueError:
                    continue

                full_url = f"https://www.instagram.com/p/{shortcode}/"
                print(full_url)

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
        if not self.buka_profil(username):
            return

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
    def ambil_detail_postingan(self, post):
        try:
            self.page.goto(
                post["url"],
                wait_until="commit",
                timeout=15000
            )
            self.page.wait_for_timeout(2000)

        except TimeoutError:
            print(f"Timeout: {post['url']}")
            return None

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