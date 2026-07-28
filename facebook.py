"""
====================================================================
  ANALISIS SENTIMEN MEDIA SOSIAL — KELUHAN WARGA GRESIK
  Menggunakan IndoBERT via HuggingFace Transformers Pipeline
====================================================================
  INSTALL:
      pip install playwright pandas python-dotenv
      pip install transformers torch sentencepiece

      playwright install chromium

  SETUP .env:
      FB_EMAIL=emailmu@gmail.com
      FB_PASSWORD=passwordmu

  CARA PAKAI:
      python gresik_analisis.py                  # semua langkah
      python gresik_analisis.py --langkah 1      # scraping saja
      python gresik_analisis.py --langkah 2      # sentimen saja
      python gresik_analisis.py --langkah 3      # laporan saja
      python gresik_analisis.py --langkah 2,3    # sentimen + laporan

  Output:
      output/data_facebook_gresik.csv
      output/data_sentimen_gresik.csv
      output/laporan_sentimen_gresik.txt
====================================================================
"""

import argparse
import asyncio
import os
import random
import sys
import time
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
#  KONFIGURASI GLOBAL
# ══════════════════════════════════════════════════════════════════
FB_EMAIL    = os.getenv("FB_EMAIL",    "")
FB_PASSWORD = os.getenv("FB_PASSWORD", "")

TARGET_URLS = [
    "https://www.facebook.com/pemkabgresik/posts",
    "https://www.facebook.com/dishubgresik/posts",
    "https://www.facebook.com/dinkesgresik/posts",
    "https://www.facebook.com/groups/infogresik/",
    "https://www.facebook.com/groups/wargagresik/",
    "https://www.facebook.com/kominfogresik/posts",
    "https://www.facebook.com/bpbdgresik/posts",
]

JUMLAH_POST_PER_HALAMAN = 20

# ── Model IndoBERT ─────────────────────────────────────────────────
# Urutan prioritas: coba satu per satu hingga berhasil dimuat
INDOBERT_MODELS = [
    # Fine-tuned sentiment khusus IndoBERT
    "mdhuggins/indobert-base-p2-finetuned-sentiment",
    # IndoBERT sentiment SMSA (lebih ringan)
    "ayameRushia/bert-base-indonesian-1.5G-sentiment-analysis-smsa",
    # Multilingual fallback
    "nlptown/bert-base-multilingual-uncased-sentiment",
]

# Panjang maksimal token yang dikirim ke model (IndoBERT max 512)
MAX_TOKENS_MODEL = 256
# Batch size pipeline — sesuaikan dengan RAM GPU/CPU
PIPELINE_BATCH   = 16

OUTPUT_DIR    = "output"
FILE_RAW      = os.path.join(OUTPUT_DIR, "data_facebook_gresik.csv")
FILE_SENTIMEN = os.path.join(OUTPUT_DIR, "data_sentimen_gresik.csv")
FILE_LAPORAN  = os.path.join(OUTPUT_DIR, "laporan_sentimen_gresik.txt")

# ══════════════════════════════════════════════════════════════════
#  KATA-KATA ANALISIS
# ══════════════════════════════════════════════════════════════════
KEYWORDS_SCRAPING = [
    "jalan","jembatan","banjir","drainase","macet","trotoar",
    "puskesmas","rumah sakit","dokter","bpjs","posyandu",
    "sekolah","guru","beasiswa","pendidikan",
    "sampah","limbah","polusi","sungai","jorok",
    "ktp","kk","akte","pelayanan","antri","birokrasi",
    "pdam","air bersih","listrik","pln","mati lampu",
    "angkot","bus","terminal","parkir",
    "bansos","pkh","blt","sembako",
    "gresik",
]

KATEGORI_KEYWORDS = {
    "Infrastruktur"      : ["jalan","jembatan","trotoar","aspal","berlubang","retak","rusak","longsor","gorong","drainase","saluran air"],
    "Banjir & Lingkungan": ["banjir","genangan","sungai","limbah","polusi","sampah","jorok","kotor","tumpukan sampah","pencemaran"],
    "Kesehatan"          : ["puskesmas","rumah sakit","dokter","bpjs","posyandu","obat","rawat","pasien","antrian","pelayanan kesehatan"],
    "Pendidikan"         : ["sekolah","guru","beasiswa","pendidikan","siswa","murid","belajar","spp","uang sekolah","buku","kelas"],
    "Transportasi"       : ["angkot","bus","terminal","parkir","macet","kemacetan","lalu lintas","angkutan","ojek","motor"],
    "Administrasi"       : ["ktp","kk","akte","akta","pelayanan","antri","birokrasi","disdukcapil","kelurahan","kecamatan","perizinan","izin"],
    "Utilitas"           : ["pdam","air bersih","listrik","pln","mati lampu","air mati","gangguan listrik","meteran"],
    "Bantuan Sosial"     : ["bansos","pkh","blt","sembako","raskin","miskin","tidak mampu","subsidi","kartu","keluarga harapan"],
}

KATA_NEGATIF = [
    "rusak","buruk","parah","jelek","kotor","jorok","bau","macet","banjir",
    "longsor","retak","berlubang","mati","mati lampu","mati air","antri",
    "lama","lambat","mahal","tidak","gak","ga","nggak","ndk","ndak","belum",
    "gagal","kurang","kecewa","mengecewakan","keluhan","komplain","masalah",
    "susah","sulit","capek","bosan","jengkel","marah","kesal","tolong",
    "protes","demo","keberatan","bahaya","darurat","mohon","harap",
]
KATA_POSITIF = [
    "bagus","baik","mantap","keren","oke","lancar","bersih","terimakasih",
    "terima kasih","makasih","alhamdulillah","senang","puas","berhasil",
    "sukses","selesai","tuntas","terpenuhi","terlayani","responsif",
    "cepat tanggap","terbantu","memuaskan","luar biasa","hebat","bravo",
]
KATA_SARAN = [
    "sebaiknya","seharusnya","mohon","harap","tolong diperbaiki",
    "perlu diperbaiki","usul","saran","usulan","masukan",
    "diharapkan","semoga","mudah-mudahan","agar","supaya",
]
KATA_URGENSI_TINGGI = [
    "darurat","bahaya","segera","urgent","kritis","meninggal","korban",
    "berbahaya","mengancam","bertahun","berbulan","lama tidak","sudah lama",
    "tidak pernah","tidak ada","terendam","ambruk","rubuh","putus",
]

# ══════════════════════════════════════════════════════════════════
#  HELPER UMUM
# ══════════════════════════════════════════════════════════════════
def header(judul: str):
    garis = "═" * 60
    print(f"\n{garis}\n   {judul}\n{garis}")

def info(msg):  print(f"   {msg}")
def ok(msg):    print(f"   ✅ {msg}")
def warn(msg):  print(f"   ⚠️  {msg}")
def err(msg):   print(f"   ❌ {msg}")

def mengandung_keyword(teks: str) -> bool:
    t = teks.lower()
    return any(k in t for k in KEYWORDS_SCRAPING)

def deteksi_kategori(teks: str) -> str:
    t = teks.lower()
    skor = {kat: sum(1 for k in kws if k in t)
            for kat, kws in KATEGORI_KEYWORDS.items()}
    best = max(skor, key=skor.get)
    return best if skor[best] > 0 else "Umum"

def sentimen_keyword(teks: str) -> dict:
    t   = teks.lower()
    neg = sum(1 for k in KATA_NEGATIF if k in t)
    pos = sum(1 for k in KATA_POSITIF if k in t)
    sar = sum(1 for k in KATA_SARAN   if k in t)
    if neg > pos and neg >= 1:
        return {"sentimen": "Negatif", "skor": round(min(neg * 0.15, 1.0), 2)}
    if pos > neg:
        return {"sentimen": "Positif", "skor": round(min(pos * 0.2,  1.0), 2)}
    if sar >= 1:
        return {"sentimen": "Saran",   "skor": 0.5}
    return     {"sentimen": "Netral",  "skor": 0.5}

def deteksi_urgensi(teks: str) -> str:
    t = teks.lower()
    if any(k in t for k in KATA_URGENSI_TINGGI):
        return "tinggi"
    neg_count = sum(1 for k in KATA_NEGATIF if k in t)
    return "sedang" if neg_count >= 2 else "rendah"

# ══════════════════════════════════════════════════════════════════
#  INDOBERT PIPELINE
# ══════════════════════════════════════════════════════════════════

# Label mapping berbeda tiap model — normalisasi ke Positif/Negatif/Netral
LABEL_MAP = {
    # mdhuggins/indobert
    "LABEL_0"  : "Negatif",
    "LABEL_1"  : "Netral",
    "LABEL_2"  : "Positif",
    # ayameRushia smsa
    "negative" : "Negatif",
    "neutral"  : "Netral",
    "positive" : "Positif",
    # nlptown (1-5 stars)
    "1 star"   : "Negatif",
    "2 stars"  : "Negatif",
    "3 stars"  : "Netral",
    "4 stars"  : "Positif",
    "5 stars"  : "Positif",
}

_pipeline_cache = None   # cache agar tidak load ulang

def muat_pipeline():
    """Load IndoBERT pipeline, coba model satu per satu."""
    global _pipeline_cache
    if _pipeline_cache is not None:
        return _pipeline_cache

    try:
        from transformers import pipeline as hf_pipeline
    except ImportError:
        err("transformers belum terinstall.")
        err("Jalankan: pip install transformers torch sentencepiece")
        return None

    for model_name in INDOBERT_MODELS:
        info(f"Memuat model: {model_name} ...")
        try:
            # truncation=True agar teks panjang tidak error
            nlp = hf_pipeline(
                task            = "sentiment-analysis",
                model           = model_name,
                tokenizer       = model_name,
                truncation      = True,
                max_length      = MAX_TOKENS_MODEL,
                batch_size      = PIPELINE_BATCH,
                # Gunakan GPU jika tersedia (device=0), CPU jika tidak (device=-1)
                device          = _deteksi_device(),
            )
            ok(f"Model berhasil dimuat: {model_name}")
            _pipeline_cache = nlp
            return nlp
        except Exception as e:
            warn(f"Gagal muat {model_name}: {e}")
            continue

    err("Semua model gagal dimuat. Fallback ke keyword saja.")
    return None

def _deteksi_device() -> int:
    """Kembalikan 0 jika CUDA tersedia, -1 jika CPU."""
    try:
        import torch
        return 0 if torch.cuda.is_available() else -1
    except ImportError:
        return -1

def normalisasi_label(raw_label: str) -> str:
    """Normalisasi label model ke Positif/Negatif/Netral."""
    lower = raw_label.lower().strip()
    # Cek di map
    for key, val in LABEL_MAP.items():
        if key.lower() == lower:
            return val
    # Cek mengandung kata
    if "neg"  in lower: return "Negatif"
    if "pos"  in lower: return "Positif"
    if "neu"  in lower: return "Netral"
    return "Netral"

def indobert_batch(nlp, teks_list: list[str]) -> list[dict]:
    """
    Jalankan pipeline IndoBERT untuk list teks.
    Kembalikan list dict: {sentimen_bert, skor_bert}
    """
    DEFAULT = {"sentimen_bert": "Netral", "skor_bert": 0.5}
    if nlp is None:
        return [DEFAULT] * len(teks_list)

    # Potong teks agar tidak over-token (kasar, tokenizer yg potong persisnya)
    teks_clean = [t[:512] for t in teks_list]
    try:
        results = nlp(teks_clean)
        output  = []
        for r in results:
            label = normalisasi_label(r["label"])
            skor  = round(float(r["score"]), 4)
            output.append({"sentimen_bert": label, "skor_bert": skor})
        return output
    except Exception as e:
        warn(f"Error pipeline: {e}")
        return [DEFAULT] * len(teks_list)

# ══════════════════════════════════════════════════════════════════
#  GABUNG SENTIMEN: BERT + KEYWORD → FINAL
# ══════════════════════════════════════════════════════════════════
def gabung_sentimen(row: dict) -> str:
    """
    Strategi penggabungan:
    - Jika BERT confidence tinggi (>0.80) → ikut BERT
    - Jika BERT confidence sedang (0.55–0.80):
        - Jika BERT == keyword → ikut keduanya
        - Jika BERT Netral tapi keyword Negatif → ikut keyword (BERT sering salah di keluhan informal)
        - Selainnya → ikut BERT
    - Jika BERT confidence rendah (<0.55) → ikut keyword
    - Jika keyword = Saran → tetap Saran (BERT tidak punya label ini)
    """
    bert = row.get("sentimen_bert", "Netral")
    kw   = row.get("sentimen_kw",   "Netral")
    skor = float(row.get("skor_bert", 0.5))

    # Saran hanya bisa dari keyword
    if kw == "Saran":
        return "Saran"

    if skor >= 0.80:
        return bert

    if skor >= 0.55:
        if bert == kw:
            return bert
        if bert == "Netral" and kw == "Negatif":
            return "Negatif"   # keluhan informal sering lolos BERT
        return bert

    # confidence rendah → keyword lebih andal untuk teks informal
    return kw

# ══════════════════════════════════════════════════════════════════
#  LANGKAH 1 — SCRAPING FACEBOOK
# ══════════════════════════════════════════════════════════════════
async def _tutup_popup(page):
    for sel in [
        '[data-testid="cookie-policy-manage-dialog-accept-button"]',
        'button:has-text("Allow all cookies")',
        'button:has-text("Accept all")',
        'button:has-text("Setuju")',
        'button:has-text("Terima")',
        'button:has-text("OK")',
    ]:
        try:
            el = page.locator(sel)
            if await el.is_visible(timeout=2000):
                await el.click()
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue

async def _klik_login(page) -> bool:
    for sel in [
        '[data-testid="royal_login_button"]',
        'button[type="submit"]',
        'input[type="submit"]',
        '//button[contains(text(),"Log in")]',
        '//button[contains(text(),"Masuk")]',
        '//input[@value="Log In"]',
        '//input[@value="Masuk"]',
    ]:
        try:
            el = page.locator(f"xpath={sel}") if sel.startswith("//") else page.locator(sel)
            if await el.is_visible(timeout=2000):
                await el.click()
                return True
        except Exception:
            continue
    return False

async def langkah1_scraping() -> list[dict]:
    header("LANGKAH 1 — SCRAPING FACEBOOK GRESIK")

    if not FB_EMAIL or not FB_PASSWORD:
        err("FB_EMAIL / FB_PASSWORD belum diset di .env")
        return []

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        err("playwright belum terinstall.")
        err("pip install playwright && playwright install chromium")
        return []

    semua_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled",
                  "--no-sandbox","--disable-dev-shm-usage","--disable-gpu"],
        )
        ctx = await browser.new_context(
            viewport   = {"width": 1280, "height": 900},
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale = "id-ID",
        )
        page = await ctx.new_page()

        # ── Login ──────────────────────────────────────────────
        info("Membuka Facebook...")
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await _tutup_popup(page)

        try:
            await page.wait_for_selector('input[name="email"]', timeout=10000)
            await page.fill('input[name="email"]', FB_EMAIL)
        except Exception:
            await page.fill('#email', FB_EMAIL)

        await page.wait_for_timeout(500)
        try:
            await page.fill('input[name="pass"]', FB_PASSWORD)
        except Exception:
            await page.fill('#pass', FB_PASSWORD)

        await page.wait_for_timeout(800)
        if not await _klik_login(page):
            await page.keyboard.press("Enter")

        info("Menunggu login selesai...")
        for i in range(60):
            await page.wait_for_timeout(1000)
            url = page.url
            if "facebook.com" in url and "login" not in url and "checkpoint" not in url:
                ok("Login berhasil!")
                break
            if i == 59:
                err("Timeout login. Periksa kredensial atau selesaikan verifikasi manual.")
                await browser.close()
                return []

        await page.wait_for_timeout(2000)

        # ── Scraping per halaman ───────────────────────────────
        for url in TARGET_URLS:
            nama = url.rstrip("/").split("/")[-1]
            print(f"\n📥 [{nama}]  {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                await _tutup_popup(page)

                if "login" in page.url or "checkpoint" in page.url:
                    warn("Halaman meminta login ulang — skip.")
                    continue

                konten = await page.content()
                if "grup privat" in konten.lower() or "private group" in konten.lower():
                    warn("Grup privat — skip.")
                    continue

                post_count   = 0
                scroll_count = 0
                teks_set     = set()

                while post_count < JUMLAH_POST_PER_HALAMAN and scroll_count < 25:
                    posts = await page.query_selector_all(
                        '[data-ad-preview="message"],'
                        'div[data-ad-comet-preview="message"],'
                        '[data-testid="post_message"] p,'
                        'div[class*="xdj266r"],'
                        'div[class*="x11i5rnm"]'
                    )
                    for el in posts:
                        try:
                            teks = (await el.inner_text()).strip()
                            if len(teks) < 20 or teks in teks_set:
                                continue
                            if not mengandung_keyword(teks):
                                continue
                            link_el  = await el.query_selector('a[href*="/posts/"]')
                            url_post = ""
                            if link_el:
                                url_post = await link_el.get_attribute("href") or ""
                            teks_set.add(teks)
                            semua_data.append({
                                "sumber"       : nama,
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

                ok(f"Terkumpul: {post_count} postingan relevan")

            except Exception as e:
                err(f"Gagal ({nama}): {e}")
                continue

        await browser.close()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = pd.DataFrame(semua_data)
    df.to_csv(FILE_RAW, index=False, encoding="utf-8-sig")
    print(f"\n💾 Tersimpan → {FILE_RAW}  ({len(semua_data)} baris)")
    return semua_data


# ══════════════════════════════════════════════════════════════════
#  LANGKAH 2 — ANALISIS SENTIMEN (IndoBERT + Keyword)
# ══════════════════════════════════════════════════════════════════
def langkah2_sentimen(df: pd.DataFrame | None = None) -> pd.DataFrame:
    header("LANGKAH 2 — ANALISIS SENTIMEN (IndoBERT + Keyword)")

    # ── Baca data ─────────────────────────────────────────────
    if df is None:
        if not os.path.exists(FILE_RAW):
            err(f"File tidak ditemukan: {FILE_RAW}")
            err("Jalankan langkah 1 dulu.")
            return pd.DataFrame()
        df = pd.read_csv(FILE_RAW, encoding="utf-8-sig")
        info(f"Data dimuat: {len(df)} baris")

    df["teks"] = df["teks"].fillna("").astype(str)
    df = df[df["teks"].str.len() >= 20].reset_index(drop=True)
    info(f"Setelah filter: {len(df)} baris\n")

    # ── 1. Keyword analysis ───────────────────────────────────
    print("🔑 Analisis keyword...")
    kw_results       = df["teks"].apply(sentimen_keyword)
    df["sentimen_kw"]= kw_results.apply(lambda x: x["sentimen"])
    df["skor_kw"]    = kw_results.apply(lambda x: x["skor"])
    df["kategori"]   = df["teks"].apply(deteksi_kategori)
    df["urgensi"]    = df["teks"].apply(deteksi_urgensi)
    ok("Keyword selesai")

    # ── 2. IndoBERT pipeline ──────────────────────────────────
    print("\n🤖 Memuat IndoBERT pipeline...")
    t0  = time.time()
    nlp = muat_pipeline()

    if nlp is not None:
        print(f"   Model siap dalam {time.time()-t0:.1f}s")
        print(f"\n🔄 Inferensi IndoBERT ({len(df)} teks, batch={PIPELINE_BATCH})...")

        teks_list  = df["teks"].tolist()
        bert_hasil = []
        total      = len(teks_list)

        for i in range(0, total, PIPELINE_BATCH):
            batch = teks_list[i : i + PIPELINE_BATCH]
            hasil = indobert_batch(nlp, batch)
            bert_hasil.extend(hasil)

            done = min(i + PIPELINE_BATCH, total)
            pct  = done / total * 100
            bar  = "█" * int(pct / 5)
            print(f"\r   [{bar:<20}] {done}/{total} ({pct:.0f}%)", end="", flush=True)

        print()
        df["sentimen_bert"] = [r["sentimen_bert"] for r in bert_hasil]
        df["skor_bert"]     = [r["skor_bert"]     for r in bert_hasil]
        ok(f"IndoBERT selesai dalam {time.time()-t0:.1f}s")
    else:
        warn("Pipeline tidak tersedia — menggunakan keyword saja")
        df["sentimen_bert"] = df["sentimen_kw"]
        df["skor_bert"]     = df["skor_kw"]

    # ── 3. Gabung → sentimen final ────────────────────────────
    print("\n🔀 Menggabungkan hasil BERT + keyword...")
    df["sentimen_final"] = df.apply(gabung_sentimen, axis=1)

    # Tandai jika BERT dan keyword berbeda (untuk audit)
    df["konflik_label"] = df["sentimen_bert"] != df["sentimen_kw"]

    df["tanggal_analisis"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 4. Simpan ────────────────────────────────────────────
    kolom = [c for c in [
        "sumber","tanggal_ambil","tanggal_analisis",
        "kategori","sentimen_final",
        "sentimen_bert","skor_bert",
        "sentimen_kw","skor_kw",
        "konflik_label","urgensi",
        "teks","url",
    ] if c in df.columns]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df[kolom].to_csv(FILE_SENTIMEN, index=False, encoding="utf-8-sig")
    print(f"\n💾 Tersimpan → {FILE_SENTIMEN}")

    # Ringkasan cepat
    print()
    smt = df["sentimen_final"].value_counts()
    for s, n in smt.items():
        pct = n / len(df) * 100
        print(f"   {s:<12} {n:>4}  ({pct:5.1f}%)")

    return df


# ══════════════════════════════════════════════════════════════════
#  LANGKAH 3 — LAPORAN
# ══════════════════════════════════════════════════════════════════
def langkah3_laporan(df: pd.DataFrame | None = None):
    header("LANGKAH 3 — LAPORAN AKHIR")

    if df is None:
        if not os.path.exists(FILE_SENTIMEN):
            err(f"File tidak ditemukan: {FILE_SENTIMEN}")
            err("Jalankan langkah 2 dulu.")
            return
        df = pd.read_csv(FILE_SENTIMEN, encoding="utf-8-sig")
        info(f"Data dimuat: {len(df)} baris")

    if df.empty:
        warn("Tidak ada data.")
        return

    total = len(df)
    smt   = df["sentimen_final"].value_counts()
    kat   = df["kategori"].value_counts()  if "kategori" in df.columns else pd.Series()
    urg   = df["urgensi"].value_counts()   if "urgensi"  in df.columns else pd.Series()
    src   = df["sumber"].value_counts()    if "sumber"   in df.columns else pd.Series()

    konflik     = int(df["konflik_label"].sum()) if "konflik_label" in df.columns else 0
    urg_tinggi  = int(urg.get("tinggi", 0))
    avg_skor    = df["skor_bert"].mean()          if "skor_bert"    in df.columns else 0

    bar = lambda pct: "█" * int(pct / 4)

    lines = [
        "═" * 64,
        "   LAPORAN ANALISIS SENTIMEN LAYANAN PUBLIK — GRESIK",
        f"   Dihasilkan : {datetime.now().strftime('%d %B %Y, %H:%M WIB')}",
        f"   Model      : IndoBERT (HuggingFace Transformers Pipeline)",
        "═" * 64,
        "",
        f"  Total postingan dianalisis   : {total}",
        f"  Rata-rata confidence BERT    : {avg_skor:.2%}",
        f"  Konflik label BERT vs KW     : {konflik}  ({konflik/total*100:.1f}%)",
        f"  Postingan urgensi TINGGI     : {urg_tinggi}",
        "",
        "─" * 64,
        "  DISTRIBUSI SENTIMEN FINAL",
        "─" * 64,
    ]
    for s, n in smt.items():
        pct = n / total * 100
        lines.append(f"  {s:<14} {n:>4}  ({pct:5.1f}%)  {bar(pct)}")

    if not kat.empty:
        lines += ["", "─" * 64, "  DISTRIBUSI KATEGORI LAYANAN", "─" * 64]
        for k, n in kat.items():
            pct = n / total * 100
            lines.append(f"  {k:<26} {n:>4}  ({pct:5.1f}%)  {bar(pct)}")

    if not urg.empty:
        lines += ["", "─" * 64, "  DISTRIBUSI URGENSI", "─" * 64]
        for u, n in urg.items():
            pct = n / total * 100
            lines.append(f"  {u:<10} {n:>4}  ({pct:5.1f}%)")

    if not src.empty:
        lines += ["", "─" * 64, "  POSTINGAN PER SUMBER", "─" * 64]
        for s, n in src.items():
            lines.append(f"  {s:<32} {n:>4}")

    # ── Top urgensi tinggi ─────────────────────────────────────
    if urg_tinggi > 0 and "urgensi" in df.columns:
        lines += ["", "─" * 64, "  TOP POSTINGAN URGENSI TINGGI (maks 10)", "─" * 64]
        top = df[df["urgensi"] == "tinggi"].head(10)
        for _, row in top.iterrows():
            kat_v = row.get("kategori",       "?")
            smt_v = row.get("sentimen_final", "?")
            skor  = row.get("skor_bert",       0)
            teks  = row.get("teks",           "")[:120]
            lines += ["", f"  [{kat_v}] [{smt_v}] confidence={skor:.0%}", f"  {teks}"]

    # ── Negatif per kategori ───────────────────────────────────
    if "kategori" in df.columns:
        df_neg = df[df["sentimen_final"] == "Negatif"]
        if not df_neg.empty:
            neg_kat = df_neg["kategori"].value_counts()
            lines  += ["", "─" * 64, "  KELUHAN NEGATIF PER KATEGORI", "─" * 64]
            for k, n in neg_kat.items():
                pct = n / len(df_neg) * 100
                lines.append(f"  {k:<26} {n:>4}  ({pct:5.1f}%)")

    # ── Perbandingan BERT vs Keyword ───────────────────────────
    if konflik > 0:
        lines += [
            "", "─" * 64,
            "  CONTOH KONFLIK LABEL (BERT ≠ Keyword) — maks 5",
            "─" * 64,
        ]
        contoh = df[df["konflik_label"] == True].head(5)
        for _, row in contoh.iterrows():
            lines += [
                "",
                f"  BERT={row.get('sentimen_bert','?')} ({row.get('skor_bert',0):.0%})  "
                f"KW={row.get('sentimen_kw','?')}  "
                f"FINAL={row.get('sentimen_final','?')}",
                f"  {row.get('teks','')[:100]}",
            ]

    lines += ["", "═" * 64]
    laporan = "\n".join(lines)

    print("\n" + laporan)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(FILE_LAPORAN, "w", encoding="utf-8") as f:
        f.write(laporan)
    ok(f"Laporan disimpan → {FILE_LAPORAN}")


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════
async def _main(langkah_pilihan: set[int]):
    df_raw      = None
    df_sentimen = None

    if 1 in langkah_pilihan:
        data   = await langkah1_scraping()
        df_raw = pd.DataFrame(data) if data else None

    if 2 in langkah_pilihan:
        # langkah2 tidak async — jalankan langsung
        df_sentimen = langkah2_sentimen(df_raw)

    if 3 in langkah_pilihan:
        langkah3_laporan(df_sentimen)

    header("SELESAI")
    print(f"  Output folder: {OUTPUT_DIR}/")
    for f in [FILE_RAW, FILE_SENTIMEN, FILE_LAPORAN]:
        if os.path.exists(f):
            size = os.path.getsize(f) / 1024
            print(f"  • {f}  ({size:.1f} KB)")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Analisis sentimen media sosial keluhan warga Gresik (IndoBERT)"
    )
    parser.add_argument(
        "--langkah", "-l",
        type    = str,
        default = "1,2,3",
        help    = "Langkah yang dijalankan, pisahkan koma: 1,2,3 (default semua)",
    )
    args = parser.parse_args()

    try:
        langkah_set = {int(x.strip()) for x in args.langkah.split(",")}
    except ValueError:
        print("❌ Format --langkah tidak valid. Contoh: --langkah 2,3")
        sys.exit(1)

    if not langkah_set.issubset({1, 2, 3}):
        print("❌ Langkah tidak valid. Pilih dari: 1, 2, 3")
        sys.exit(1)

    device_label = "GPU (CUDA)" if _deteksi_device() == 0 else "CPU"

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   🏙️   ANALISIS SENTIMEN WARGA GRESIK — IndoBERT   🏙️  ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║   Langkah  : {str(sorted(langkah_set)):<44}║")
    print(f"║   Device   : {device_label:<44}║")
    print(f"║   Waktu    : {datetime.now().strftime('%d %b %Y %H:%M'):<44}║")
    print("╚══════════════════════════════════════════════════════════╝")

    asyncio.run(_main(langkah_set))


if __name__ == "__main__":
    main()