import asyncio
import pandas as pd
import json
import os
import re
import logging
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# ============================================================
# KONFIGURASI
# ============================================================
OUTPUT_DIR   = "data_gresik"
PROGRESS_FILE = "progress.json"   # tracking kategori yang sudah selesai
LOG_FILE      = "scraper.log"

MAX_RETRY     = 3       # retry per query jika gagal
DELAY_KARTU   = 1.5     # detik antar ambil detail
DELAY_QUERY   = 2.0     # detik antar query
DELAY_KATEGORI= 4.0     # detik antar kategori
MAX_SCROLL    = 15      # scroll ke bawah untuk load lebih banyak

os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ============================================================
# SEMUA KATEGORI + QUERY GRESIK
# ============================================================
KATEGORI = {
    "rumah_sakit": [
        "rumah sakit Gresik",
        "RSUD Ibnu Sina Gresik",
        "RS swasta Gresik",
        "klinik utama Gresik",
    ],
    "puskesmas": [
        "puskesmas Gresik",
        "puskesmas Kebomas",
        "puskesmas Driyorejo",
        "puskesmas Bungah Gresik",
        "puskesmas Cerme Gresik",
    ],
    "sekolah_dasar": [
        "SD negeri Gresik",
        "SD swasta Gresik",
        "MI negeri Gresik",
        "SD negeri Kebomas",
        "SD negeri Driyorejo",
    ],
    "sekolah_menengah": [
        "SMP negeri Gresik",
        "SMA negeri Gresik",
        "SMK negeri Gresik",
        "MTs negeri Gresik",
        "MA negeri Gresik",
    ],
    "kantor_kecamatan": [
        "kantor kecamatan Gresik",
        "kantor kecamatan Kebomas",
        "kantor kecamatan Cerme",
        "kantor kecamatan Bungah",
        "kantor kecamatan Driyorejo",
        "kantor kecamatan Duduksampeyan",
        "kantor kecamatan Manyar",
        "kantor kecamatan Panceng",
        "kantor kecamatan Ujungpangkah",
    ],
    "kantor_desa": [
        "kantor desa Gresik",
        "kantor kelurahan Gresik",
        "balai desa Gresik",
    ],
    "bank": [
        "bank BRI Gresik",
        "bank BNI Gresik",
        "bank Mandiri Gresik",
        "bank BCA Gresik",
        "bank Jatim Gresik",
        "bank BTN Gresik",
    ],
    "atm": [
        "ATM BRI Gresik",
        "ATM BNI Gresik",
        "ATM Mandiri Gresik",
    ],
    "spbu": [
        "SPBU Gresik",
        "pom bensin Gresik",
        "Pertamina Gresik",
    ],
    "apotek": [
        "apotek Gresik",
        "apotek K24 Gresik",
        "apotek Kimia Farma Gresik",
    ],
    "masjid": [
        "masjid Gresik",
        "masjid jami Gresik",
        "masjid agung Gresik",
        "musholla Gresik",
    ],
    "polisi": [
        "polsek Gresik",
        "polres Gresik",
        "pos polisi Gresik",
    ],
    "pemadam": [
        "pemadam kebakaran Gresik",
        "damkar Gresik",
    ],
    "kantor_pos": [
        "kantor pos Gresik",
        "pos Indonesia Gresik",
    ],
    "pasar": [
        "pasar tradisional Gresik",
        "pasar Gresik kota",
        "pasar Bungah",
        "pasar Driyorejo",
    ],
}


# ============================================================
# PROGRESS TRACKER (resume jika script dihentikan)
# ============================================================
class ProgressTracker:
    def __init__(self, path=PROGRESS_FILE):
        self.path = path
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                return json.load(f)
        return {"selesai": [], "gagal": [], "mulai": datetime.now().isoformat()}

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def sudah_selesai(self, kategori):
        return kategori in self.data["selesai"]

    def tandai_selesai(self, kategori):
        if kategori not in self.data["selesai"]:
            self.data["selesai"].append(kategori)
        self._save()
        log.info(f"Progress: {len(self.data['selesai'])}/{len(KATEGORI)} kategori selesai")

    def tandai_gagal(self, kategori, alasan=""):
        self.data["gagal"].append({"kategori": kategori, "alasan": alasan, "waktu": datetime.now().isoformat()})
        self._save()

    def reset(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        self.data = self._load()
        log.info("Progress di-reset.")


# ============================================================
# FUNGSI SCRAPING
# ============================================================
def buat_url(query):
    return "https://www.google.com/maps/search/" + query.replace(" ", "+")


async def scroll_panel(page, max_scroll=MAX_SCROLL):
    for i in range(max_scroll):
        try:
            panel = await page.query_selector('div[role="feed"]')
            if panel:
                await panel.evaluate("el => el.scrollTop += 800")
                await page.wait_for_timeout(1300)
            mentok = await page.query_selector('span.HlvSq')
            if mentok:
                log.info(f"    Scroll selesai ({i+1} iterasi)")
                break
        except Exception:
            break


async def parse_kartu(item):
    d = {}
    try:
        el = await item.query_selector("div.qBF1Pd")
        d["nama"] = (await el.inner_text()).strip() if el else ""

        el = await item.query_selector("span.MW4etd")
        d["rating"] = (await el.inner_text()).strip() if el else ""

        el = await item.query_selector("span.UY7F9")
        raw = (await el.inner_text()).strip() if el else ""
        d["jumlah_ulasan"] = re.sub(r"[^\d]", "", raw)

        spans = await item.query_selector_all("div.W4Efsd span.W4Efsd")
        tipe, alamat = "", ""
        for i, s in enumerate(spans):
            t = (await s.inner_text()).strip().replace("·", "").strip()
            if not t:
                continue
            if i == 0:
                tipe = t
            elif i == 1:
                alamat = t
        d["tipe"]   = tipe
        d["alamat"] = alamat

        el = await item.query_selector("a.hfpxzc")
        d["url"] = await el.get_attribute("href") if el else ""
    except Exception as e:
        log.debug(f"parse_kartu: {e}")
    return d


async def ambil_detail(page, url):
    detail = {"telepon": "", "website": "", "latitude": "", "longitude": ""}
    if not url:
        return detail
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1800)

        el = await page.query_selector('button[data-item-id^="phone"]')
        if el:
            detail["telepon"] = (await el.get_attribute("aria-label") or "").replace("Telepon: ", "").strip()

        el = await page.query_selector('a[data-item-id="authority"]')
        if el:
            detail["website"] = await el.get_attribute("href") or ""

        m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", page.url)
        if m:
            detail["latitude"]  = m.group(1)
            detail["longitude"] = m.group(2)
    except Exception as e:
        log.debug(f"ambil_detail: {e}")
    return detail


async def scrape_query_dengan_retry(page, query, retry=MAX_RETRY):
    """Coba scrape satu query, ulangi jika gagal."""
    for attempt in range(1, retry + 1):
        try:
            log.info(f"  Query: '{query}' (percobaan {attempt})")
            await page.goto(buat_url(query), wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2500)
            await scroll_panel(page)

            kartu_list = await page.query_selector_all('div.Nv2PK')
            log.info(f"    {len(kartu_list)} kartu ditemukan")

            hasil = []
            for kartu in kartu_list:
                d = await parse_kartu(kartu)
                if d.get("nama"):
                    hasil.append(d)
            return hasil

        except Exception as e:
            log.warning(f"  Gagal percobaan {attempt}: {e}")
            if attempt < retry:
                await asyncio.sleep(3 * attempt)  # backoff: 3s, 6s, 9s

    log.error(f"  Query '{query}' gagal setelah {retry} percobaan")
    return []


async def scrape_satu_kategori(browser, nama_kat, queries):
    """Loop semua query dalam satu kategori, deduplikasi, ambil detail."""
    log.info(f"\n{'='*55}")
    log.info(f"KATEGORI: {nama_kat.upper()} ({len(queries)} query)")
    log.info(f"{'='*55}")

    page = await browser.new_page()
    await page.set_extra_http_headers({
        "Accept-Language": "id-ID,id;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    })

    # --- Loop semua query, kumpulkan unik by nama ---
    nama_unik = {}
    for idx, query in enumerate(queries, 1):
        log.info(f"  [{idx}/{len(queries)}] {query}")
        items = await scrape_query_dengan_retry(page, query)

        baru = 0
        for item in items:
            nama = item.get("nama", "").strip()
            if nama and nama not in nama_unik:
                nama_unik[nama] = item
                baru += 1
        log.info(f"    +{baru} baru | total unik: {len(nama_unik)}")
        await asyncio.sleep(DELAY_QUERY)

    log.info(f"  Selesai kumpul query. Total unik: {len(nama_unik)}")

    # --- Loop ambil detail tiap tempat ---
    semua = []
    total = len(nama_unik)
    for i, (nama, item) in enumerate(nama_unik.items(), 1):
        log.info(f"  Detail [{i}/{total}]: {nama}")
        detail = await ambil_detail(page, item.get("url", ""))

        semua.append({
            "nama":          nama,
            "kategori":      nama_kat,
            "rating":        item.get("rating", ""),
            "jumlah_ulasan": item.get("jumlah_ulasan", ""),
            "tipe":          item.get("tipe", ""),
            "alamat":        item.get("alamat", ""),
            "telepon":       detail["telepon"],
            "website":       detail["website"],
            "latitude":      detail["latitude"],
            "longitude":     detail["longitude"],
            "url_maps":      item.get("url", ""),
            "diambil_pada":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        await asyncio.sleep(DELAY_KARTU)

    await page.close()
    return semua


# ============================================================
# SIMPAN PER KATEGORI
# ============================================================
def simpan_kategori(data, nama_kat):
    if not data:
        log.warning(f"Tidak ada data untuk: {nama_kat}")
        return
    df = pd.DataFrame(data)
    path = os.path.join(OUTPUT_DIR, f"{nama_kat}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    log.info(f"Tersimpan: {path} ({len(df)} baris)")


def gabung_dan_ekspor_excel():
    """Gabungkan semua CSV lalu buat satu file Excel."""
    import glob
    dfs = []
    for f in sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.csv"))):
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
            dfs.append(df)
        except Exception:
            pass

    if not dfs:
        return

    path_excel = os.path.join(OUTPUT_DIR, "Layanan_Umum_Gresik.xlsx")
    with pd.ExcelWriter(path_excel, engine="openpyxl") as writer:
        master = pd.concat(dfs, ignore_index=True)
        master.to_excel(writer, sheet_name="SEMUA", index=False)
        for df in dfs:
            if "kategori" in df.columns and not df.empty:
                kat = df["kategori"].iloc[0][:31]
                df.to_excel(writer, sheet_name=kat, index=False)

    log.info(f"Excel: {path_excel} ({len(master)} total baris)")


# ============================================================
# MAIN LOOP OTOMASI
# ============================================================
async def main(reset_progress=False):
    tracker = ProgressTracker()
    if reset_progress:
        tracker.reset()

    sisa = [k for k in KATEGORI if not tracker.sudah_selesai(k)]
    log.info(f"Total kategori: {len(KATEGORI)} | Sisa: {len(sisa)} | Selesai: {len(KATEGORI)-len(sisa)}")

    if not sisa:
        log.info("Semua kategori sudah selesai. Gunakan reset_progress=True untuk mulai ulang.")
        gabung_dan_ekspor_excel()
        return

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--lang=id-ID", "--no-sandbox"]
        )

        ringkasan = {}

        for idx, nama_kat in enumerate(sisa, 1):
            log.info(f"\n[{idx}/{len(sisa)}] Mulai: {nama_kat}")
            mulai = time.time()

            try:
                data = await scrape_satu_kategori(browser, nama_kat, KATEGORI[nama_kat])
                simpan_kategori(data, nama_kat)
                tracker.tandai_selesai(nama_kat)
                ringkasan[nama_kat] = len(data)

                durasi = round(time.time() - mulai, 1)
                log.info(f"Selesai '{nama_kat}' dalam {durasi}s | {len(data)} lokasi")

            except Exception as e:
                log.error(f"ERROR kategori '{nama_kat}': {e}")
                tracker.tandai_gagal(nama_kat, str(e))

            # Jeda antar kategori
            if idx < len(sisa):
                log.info(f"Jeda {DELAY_KATEGORI}s sebelum kategori berikutnya...")
                await asyncio.sleep(DELAY_KATEGORI)

        await browser.close()

    # Gabung semua & ekspor Excel
    gabung_dan_ekspor_excel()

    # Ringkasan akhir
    print("\n" + "="*55)
    print("RINGKASAN SCRAPING LAYANAN UMUM GRESIK")
    print("="*55)
    for k, v in ringkasan.items():
        print(f"  {k:<28} : {v:>4} lokasi")
    print(f"  {'─'*38}")
    print(f"  {'TOTAL':<28} : {sum(ringkasan.values()):>4} lokasi")
    print("="*55)
    print(f"Output: ./{OUTPUT_DIR}/")


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    # Ganti True jika ingin mulai dari awal (hapus progress)
    asyncio.run(main(reset_progress=False))