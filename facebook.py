"""
====================================================================
LANGKAH 1: AMBIL DATA FACEBOOK GRESIK
====================================================================
INSTALL DULU:
    pip install playwright pandas
    playwright install chromium
CARA PAKAI:
    python langkah1_ambil_data.py
Hasil: output/data_facebook_gresik.csv
====================================================================
"""
import asyncio
import os
import pandas as pd
import random
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# ══════════════════════════════════════════════════════════════════
#  KONFIGURASI — EDIT BAGIAN INI
# ══════════════════════════════════════════════════════════════════
FB_EMAIL    = os.getenv("FB_EMAIL", "")
FB_PASSWORD = os.getenv("FB_PASSWORD", "")

TARGET_URLS = [
    "https://www.facebook.com/pemkabgresik",
    "https://www.facebook.com/groups/infogresik",
    "https://www.facebook.com/groups/wargagresik",
    "https://www.facebook.com/dishubgresik",
    "https://www.facebook.com/dinkesgresik"
]

JUMLAH_POST_PER_HALAMAN = 30

KEYWORDS = [
    "jalan", "jembatan", "banjir", "drainase", "macet", "trotoar",
    "puskesmas", "rumah sakit", "dokter", "bpjs", "posyandu",
    "sekolah", "guru", "beasiswa", "pendidikan",
    "sampah", "limbah", "polusi", "sungai", "jorok",
    "ktp", "kk", "akte", "pelayanan", "antri", "birokrasi",
    "pdam", "air bersih", "listrik", "pln", "mati lampu",
    "angkot", "bus", "terminal", "parkir",
    "bansos", "pkh", "blt", "sembako",
    "gresik",
]

# ── FOLDER OUTPUT ─────────────────────────────────────────────────
OUTPUT_DIR  = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "data_facebook_gresik.csv")

# ══════════════════════════════════════════════════════════════════

def mengandung_keyword(teks: str) -> bool:
    return any(kw in teks.lower() for kw in KEYWORDS)


async def klik_tombol_login(page):
    """Coba berbagai selector tombol login Facebook."""
    selectors = [
        '[data-testid="royal_login_button"]',
        'button[type="submit"]',
        'input[type="submit"]',
        '//button[contains(text(),"Log in")]',
        '//button[contains(text(),"Masuk")]',
        '//input[@value="Log In"]',
        '//input[@value="Masuk"]',
    ]
    for sel in selectors:
        try:
            if sel.startswith("//"):
                el = page.locator(f"xpath={sel}")
            else:
                el = page.locator(sel)
            if await el.is_visible(timeout=2000):
                await el.click()
                print(f"   ✅ Tombol login ditemukan: {sel}")
                return True
        except Exception:
            continue
    return False


async def tutup_popup(page):
    """Tutup popup cookie/consent jika muncul."""
    selectors = [
        '[data-testid="cookie-policy-manage-dialog-accept-button"]',
        'button:has-text("Allow all cookies")',
        'button:has-text("Accept all")',
        'button:has-text("Setuju")',
        'button:has-text("Terima")',
        'button:has-text("OK")',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel)
            if await el.is_visible(timeout=2000):
                await el.click()
                await page.wait_for_timeout(1000)
                print(f"   ℹ️  Popup ditutup")
                return
        except Exception:
            continue


async def ambil_data_facebook():
    from playwright.async_api import async_playwright

    semua_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            slow_mo=0,          # tidak perlu delay di headless
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="id-ID",
        )
        page = await context.new_page()

        # ── LOGIN ────────────────────────────────────────────────
        print("🔑 Membuka Facebook...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        await tutup_popup(page)
        await page.wait_for_timeout(1000)

        print("   Mengisi email...")
        try:
            await page.wait_for_selector('input[name="email"]', timeout=10000)
            await page.fill('input[name="email"]', FB_EMAIL)
        except Exception:
            print("   ⚠️  Input email tidak ditemukan, coba selector lain...")
            await page.fill('#email', FB_EMAIL)

        await page.wait_for_timeout(500)

        print("   Mengisi password...")
        try:
            await page.fill('input[name="pass"]', FB_PASSWORD)
        except Exception:
            await page.fill('#pass', FB_PASSWORD)

        await page.wait_for_timeout(800)

        print("   Klik tombol login...")
        
        berhasil_klik = await klik_tombol_login(page)
        if not berhasil_klik:
            print("   ⚠️  Tombol login tidak ditemukan, coba Enter...")
            await page.keyboard.press("Enter")

        print("   Menunggu proses login...")
        for i in range(60):
            await page.wait_for_timeout(1000)
            url_sekarang = page.url
            if (
                "facebook.com" in url_sekarang
                and "login" not in url_sekarang
                and "checkpoint" not in url_sekarang
            ):
                print("✅ Login berhasil!\n")
                break
            if i == 59:
                print("❌ Timeout login. Pastikan sudah login dan jalankan ulang.")
                await browser.close()
                return []

        await page.wait_for_timeout(2000)

        # ── SCRAPING PER HALAMAN ─────────────────────────────────
        for url in TARGET_URLS:
            nama_page = url.rstrip("/").split("/")[-1]
            print(f"📥 Membuka: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                await tutup_popup(page)

                post_count   = 0
                scroll_count = 0
                teks_sudah   = set()

                while post_count < JUMLAH_POST_PER_HALAMAN and scroll_count < 25:
                    posts = await page.query_selector_all(
                        '[data-pagelet*="FeedUnit"], [role="article"], [data-testid="post_message"]'
                    )
                    for post_el in posts:
                        try:
                            teks = (await post_el.inner_text()).strip()
                            if len(teks) < 20:
                                continue
                            if teks in teks_sudah:
                                continue
                            if not mengandung_keyword(teks):
                                continue

                            link_el  = await post_el.query_selector('a[href*="/posts/"]')
                            url_post = ""
                            if link_el:
                                url_post = await link_el.get_attribute("href") or ""

                            teks_sudah.add(teks)
                            semua_data.append({
                                "sumber"       : nama_page,
                                "teks"         : teks[:1000],
                                "url"          : url_post,
                                "tanggal_ambil": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            })
                            post_count += 1
                        except Exception:
                            continue

                    await page.evaluate("window.scrollBy(0, 1500)")
                    await page.wait_for_timeout(random.randint(1500, 2500))
                    scroll_count += 1

                print(f"   ✅ Terkumpul: {post_count} postingan relevan\n")

            except Exception as e:
                print(f"   ❌ Gagal ({nama_page}): {e}\n")
                continue

        await browser.close()

    return semua_data


def main():
    print("=" * 55)
    print("   🏙️  PENGAMBIL DATA FACEBOOK GRESIK")
    print("=" * 55)
    print(f"Target  : {len(TARGET_URLS)} halaman")
    print(f"Max post: {JUMLAH_POST_PER_HALAMAN} per halaman")
    print(f"Output  : {OUTPUT_FILE}")
    print()

    data = asyncio.run(ambil_data_facebook())

    if not data:
        print("\n⚠️  Tidak ada data terkumpul.")
        print("Tips:")
        print("  - Pastikan URL di TARGET_URLS benar dan halamannya publik")
        print("  - Pastikan email/password Facebook benar")
        print("  - Kalau Facebook minta verifikasi, selesaikan manual di browser")
        return

    # Buat folder output jika belum ada
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = pd.DataFrame(data)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    print(f"\n{'='*55}")
    print(f"✅ SELESAI! {len(data)} data tersimpan → {OUTPUT_FILE}")
    print(f"{'='*55}")
    print(f"\nPreview 3 data pertama:")
    print(df[["sumber", "teks"]].head(3).to_string(max_colwidth=70))
    print(f"\n➡️  Sekarang jalankan: python langkah2_analisis_sentimen.py")


if __name__ == "__main__":
    main()