"""
╔══════════════════════════════════════════════════════════╗
║   SCRAPER BERITA GRESIK - OTOMATIS (VERSI PERBAIKAN)    ║
║   Sumber: 20+ portal berita lokal & nasional            ║
║   Filter: Berbasis KEYWORD (bukan hanya domain Gresik)  ║
║   Output: output/berita/  (dalam folder project)        ║
╚══════════════════════════════════════════════════════════╝

CARA PAKAI:
  1. pip install requests beautifulsoup4 pandas
  2. python Berita.py

OTOMASI HARIAN (cron Linux/Mac):
  0 7 * * * python /path/Berita.py

OTOMASI HARIAN (Windows Task Scheduler):
  - Buka Task Scheduler → Create Basic Task
  - Trigger: Daily, jam 07:00
  - Action: python C:/path/Berita.py
"""

import requests
import pandas as pd
import os, time, re, random, json
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote

# ══════════════════════════════════════════════════════
# PENGATURAN PATH — sesuai struktur project Dashboard-Gresik
# ══════════════════════════════════════════════════════
# Semua output masuk ke output/ (satu folder dengan scraper lain)
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")          # output/
BERITA_DIR  = os.path.join(OUTPUT_DIR, "berita")        # output/berita/
os.makedirs(OUTPUT_DIR,  exist_ok=True)
os.makedirs(BERITA_DIR,  exist_ok=True)

# ── File output utama (dibaca app.py) ─────────────────────────
BERITA_CSV      = os.path.join(OUTPUT_DIR, "gresik_berita.csv")          # output/gresik_berita.csv
TOPIK_CSV       = os.path.join(OUTPUT_DIR, "gresik_berita_topik.csv")    # output/gresik_berita_topik.csv
SUMBER_CSV      = os.path.join(OUTPUT_DIR, "gresik_berita_sumber.csv")   # output/gresik_berita_sumber.csv
STATUS_FILE     = os.path.join(OUTPUT_DIR, "scrape_status.json")          # output/scrape_status.json (shared)
LOG_FILE        = os.path.join(BERITA_DIR, "log_scraping.csv")           # output/berita/log_scraping.csv

# ── File arsip per-tanggal (disimpan di output/berita/) ───────
def path_arsip() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return os.path.join(BERITA_DIR, f"berita_gresik_{ts}.csv")

# ══════════════════════════════════════════════════════
# KATA KUNCI PENCARIAN
# ══════════════════════════════════════════════════════
KEYWORDS = [
    "gresik",
    "kabupaten gresik",
    "kota gresik",
    "petrokimia gresik",
    "semen gresik",
    "gkb",
    "driyorejo",
    "cerme gresik",
    "bungah gresik",
    "sidayu gresik",
    "panceng gresik",
    "ujungpangkah",
    "manyar gresik",
    "wringinanom",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9",
}

# ══════════════════════════════════════════════════════
# DAFTAR SUMBER BERITA
# ══════════════════════════════════════════════════════
SUMBER_BERITA = [

    # ── PORTAL LOKAL GRESIK ───────────────────────────────────
    {
        "nama" : "Gresik Satu",
        "url"  : "https://gresiksatu.com/",
        "tipe" : "lokal",
        "parse": "gresiksatu",
    },
    {
        "nama" : "Suara Gresik",
        "url"  : "https://suaragresik.com/",
        "tipe" : "lokal",
        "parse": "suaragresik",
    },
    {
        "nama" : "Gresik News",
        "url"  : "https://gresiknews.co/",
        "tipe" : "lokal",
        "parse": "generic",
    },
    {
        "nama" : "Memo Gresik",
        "url"  : "https://memo-gresik.com/",
        "tipe" : "lokal",
        "parse": "generic",
    },
    {
        "nama" : "Radar Gresik",
        "url"  : "https://radargresik.jawapos.com/",
        "tipe" : "lokal",
        "parse": "generic",
    },

    # ── PORTAL NASIONAL ───────────────────────────────────────
    {
        "nama" : "Detik - Gresik",
        "url"  : "https://www.detik.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "detik",
    },
    {
        "nama" : "Kompas - Gresik",
        "url"  : "https://regional.kompas.com/gresik",
        "tipe" : "nasional",
        "parse": "kompas",
    },
    {
        "nama" : "Tribun Jatim - Gresik",
        "url"  : "https://jatim.tribunnews.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "tribun",
    },
    {
        "nama" : "Jawa Pos - Gresik",
        "url"  : "https://www.jawapos.com/tag/gresik/",
        "tipe" : "nasional",
        "parse": "jawapos",
    },
    {
        "nama" : "CNN Indonesia - Gresik",
        "url"  : "https://www.cnnindonesia.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "cnn",
    },
    {
        "nama" : "Antara - Gresik",
        "url"  : "https://www.antaranews.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "antara",
    },
    {
        "nama" : "Kapanlagi - Gresik",
        "url"  : "https://www.kapanlagi.com/tag/gresik.html",
        "tipe" : "nasional",
        "parse": "generic",
    },
    {
        "nama" : "Tempo - Gresik",
        "url"  : "https://www.tempo.co/tag/gresik",
        "tipe" : "nasional",
        "parse": "tempo",
    },
    {
        "nama" : "VIVA - Gresik",
        "url"  : "https://www.viva.co.id/tag/gresik",
        "tipe" : "nasional",
        "parse": "generic",
    },
    {
        "nama" : "Okezone - Gresik",
        "url"  : "https://news.okezone.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "generic",
    },
    {
        "nama" : "IDN Times - Gresik",
        "url"  : "https://www.idntimes.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "generic",
    },
    {
        "nama" : "Suara.com - Gresik",
        "url"  : "https://www.suara.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "generic",
    },
    {
        "nama" : "Liputan6 - Gresik",
        "url"  : "https://www.liputan6.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "liputan6",
    },
    {
        "nama" : "Republika - Gresik",
        "url"  : "https://news.republika.co.id/tag/gresik",
        "tipe" : "nasional",
        "parse": "generic",
    },
    {
        "nama" : "Kumparan - Gresik",
        "url"  : "https://kumparan.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "kumparan",
    },
    {
        "nama" : "Sindonews - Gresik",
        "url"  : "https://jatim.sindonews.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "generic",
    },
    {
        "nama" : "Merdeka - Gresik",
        "url"  : "https://www.merdeka.com/tag/gresik",
        "tipe" : "nasional",
        "parse": "generic",
    },
]

# ══════════════════════════════════════════════════════
# GOOGLE NEWS RSS
# ══════════════════════════════════════════════════════
GOOGLE_NEWS_KEYWORDS = [
    "gresik",
    "petrokimia gresik",
    "semen gresik",
    "kabupaten gresik",
    "bupati gresik",
]

def scrape_google_news_rss(keyword):
    artikel  = []
    encoded  = quote(keyword)
    url      = f"https://news.google.com/rss/search?q={encoded}&hl=id&gl=ID&ceid=ID:id"
    try:
        r    = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "xml")
        for item in soup.find_all("item")[:20]:
            judul  = bersihkan(item.find("title").get_text()  if item.find("title")   else "")
            link   = item.find("link").get_text()             if item.find("link")    else ""
            tgl    = item.find("pubDate").get_text()          if item.find("pubDate") else "-"
            sumber = item.find("source").get_text()           if item.find("source")  else "Google News"
            desk_el= item.find("description")
            desk   = bersihkan(BeautifulSoup(desk_el.get_text(), "html.parser").get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({
                    "judul"    : judul,
                    "url"      : link,
                    "tanggal"  : ekstrak_tanggal(tgl),
                    "ringkasan": desk[:300],
                    "topik"    : kategorikan_topik(judul, desk),
                    "sumber"   : f"Google News ({sumber})",
                    "tipe"     : "google_news",
                })
    except Exception as e:
        print(f"    ⚠ Google News RSS gagal untuk '{keyword}': {e}")
    return artikel

# ══════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════
def get_html(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = r.apparent_encoding
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"    ⚠ Gagal fetch {url}: {e}")
        return None

def bersihkan(teks):
    if not teks:
        return ""
    teks = re.sub(r'\s+', ' ', str(teks)).strip()
    teks = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', teks)
    return teks[:500]

def ekstrak_tanggal(teks):
    if not teks:
        return "-"
    patterns = [
        r'\d{1,2}\s+\w+\s+\d{4}',
        r'\d{4}-\d{2}-\d{2}',
        r'\d{2}/\d{2}/\d{4}',
        r'\w+,\s+\d{1,2}\s+\w+\s+\d{4}',
        r'\d{1,2}\s+\w{3}\s+\d{4}',
        r'\w{3},\s+\d{2}\s+\w{3}\s+\d{4}',
    ]
    for p in patterns:
        m = re.search(p, str(teks))
        if m:
            return m.group(0)
    return str(teks)[:30] if teks else "-"

def kategorikan_topik(judul, isi=""):
    teks = (str(judul) + " " + str(isi)).lower()
    kategori_map = {
        "Ekonomi & UMKM"    : ["umkm","ekonomi","bisnis","investasi","industri","pabrik",
                                "perdagangan","ekspor","impor","pasar","toko","lapak"],
        "Infrastruktur"      : ["jalan","jembatan","infrastruktur","pembangunan","proyek",
                                "gedung","pelabuhan","bandara","tol"],
        "Pendidikan"         : ["sekolah","pendidikan","siswa","guru","universitas","kampus",
                                "mahasiswa","beasiswa","sd","smp","sma"],
        "Kesehatan"          : ["kesehatan","rumah sakit","puskesmas","covid","wabah","dokter",
                                "pasien","vaksin","stunting","gizi"],
        "Lingkungan"         : ["lingkungan","sampah","banjir","limbah","polusi","sungai",
                                "tambak","nelayan","ikan","pertanian"],
        "Sosial & Budaya"    : ["budaya","tradisi","festival","seni","wisata","pariwisata",
                                "kuliner","makanan","oleh-oleh","kerajinan"],
        "Politik & Pemda"    : ["bupati","dprd","pemda","pemerintah","politik","pilkada",
                                "anggaran","apbd","dinas","kecamatan"],
        "Keamanan & Hukum"   : ["polisi","hukum","kriminal","korupsi","penangkapan","tersangka",
                                "pengadilan","kejahatan","narkoba"],
        "Olahraga"           : ["olahraga","sepak bola","turnamen","atletik","juara","liga"],
        "Industri & Tambang" : ["semen gresik","petrokimia","pupuk","kawasan industri",
                                "gkb","maspion","pabrik"],
    }
    for kategori, kata_list in kategori_map.items():
        if any(k in teks for k in kata_list):
            return kategori
    return "Umum"

def cocok_keyword(judul, ringkasan="", tipe="nasional"):
    if tipe == "lokal":
        return True
    teks = (str(judul) + " " + str(ringkasan)).lower()
    return any(kw.lower() in teks for kw in KEYWORDS)

# ══════════════════════════════════════════════════════
# PARSER PER SUMBER
# ══════════════════════════════════════════════════════

def parse_detik(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("article, div.list-content__item, div.media__text")
    for item in items[:20]:
        try:
            a = item.select_one("a[href*='detik.com']") or item.select_one("a")
            if not a:
                continue
            judul   = bersihkan(a.get_text())
            url     = a.get("href", "")
            tgl_el  = item.select_one("span.date, div.date, span[class*='date']")
            tgl     = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            desk_el = item.select_one("div.media__desc, p")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({"judul": judul, "url": url,
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_kompas(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("div.article__list, div.latest--item, article, div.most--item")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            judul   = bersihkan(a.get("title", "") or a.get_text())
            url     = a.get("href", "")
            tgl_el  = item.select_one("span.article__date, div.article__date")
            tgl     = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            desk_el = item.select_one("p, div.article__subtitle")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else "https://kompas.com" + url,
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_tribun(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("div.lopa, li.list-berita, article, div.side--item")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            judul   = bersihkan(a.get("title", "") or a.get_text())
            url     = a.get("href", "")
            tgl_el  = item.select_one("span.time, time, div.time")
            tgl     = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            desk_el = item.select_one("p, div.txt")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else urljoin(url_sumber, url),
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_jawapos(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("article, div.latest-news--item, div.card-news, li.item")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            h     = item.select_one("h2,h3,h4")
            judul = bersihkan(h.get_text() if h else a.get_text())
            url   = a.get("href", "")
            tgl_el= item.select_one("time, span.date, div.date, span[class*='time']")
            tgl   = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else urljoin(url_sumber, url),
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": "",
                    "topik": kategorikan_topik(judul),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_antara(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("div.item, article, li.artikel, div.card")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            judul   = bersihkan(a.get("title", "") or a.get_text())
            url     = a.get("href", "")
            tgl_el  = item.select_one("span.date, time, div.date-time")
            tgl     = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            desk_el = item.select_one("p")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else urljoin(url_sumber, url),
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_cnn(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("article, div.container__item, div.card")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            h     = item.select_one("h2,h3,h4,span.title")
            judul = bersihkan(h.get_text() if h else a.get_text())
            url   = a.get("href", "")
            tgl_el= item.select_one("span.date, time")
            tgl   = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else "https://cnnindonesia.com" + url,
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": "",
                    "topik": kategorikan_topik(judul),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_tempo(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("div.card-box, article, div.media-item, li.item")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            h       = item.select_one("h2,h3,h4,div.title")
            judul   = bersihkan(h.get_text() if h else a.get_text())
            url     = a.get("href", "")
            tgl_el  = item.select_one("span.date, time, div.time, span[class*='date']")
            tgl     = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            desk_el = item.select_one("p, div.summary")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else urljoin(url_sumber, url),
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_liputan6(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("article, div.articles--iridescent-list--text-item, li.articles__item")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            h       = item.select_one("h2,h3,h4,span.articles--iridescent-list--text-item__title-text")
            judul   = bersihkan(h.get_text() if h else a.get_text())
            url     = a.get("href", "")
            tgl_el  = item.select_one("time, span.timeago, span[class*='date']")
            tgl     = bersihkan(tgl_el.get("datetime", "") or tgl_el.get_text()) if tgl_el else "-"
            desk_el = item.select_one("p, div.articles--iridescent-list--text-item__summary")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else urljoin(url_sumber, url),
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_kumparan(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("div[class*='CardLink'], article, div.stream-item")
    for item in items[:20]:
        try:
            a = item.select_one("a")
            if not a:
                continue
            h     = item.select_one("h2,h3,h4,div[class*='title'],span[class*='title']")
            judul = bersihkan(h.get_text() if h else a.get_text())
            url   = a.get("href", "")
            tgl_el= item.select_one("time, span[class*='time'], span[class*='date']")
            tgl   = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            if judul and len(judul) > 10:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else "https://kumparan.com" + url,
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": "",
                    "topik": kategorikan_topik(judul),
                    "sumber": nama_sumber, "tipe": "nasional"})
        except:
            pass
    return artikel

def parse_gresiksatu(soup, nama_sumber, url_sumber):
    artikel = []
    items = soup.select("article, div.jeg_post, div.post-item, div.td-module-thumb")
    for item in items[:25]:
        try:
            a = (item.select_one("h2 a, h3 a, a.jeg_post_title, a[rel='bookmark']")
                 or item.select_one("a"))
            if not a:
                continue
            judul   = bersihkan(a.get_text())
            url     = a.get("href", "")
            tgl_el  = item.select_one("time, span.date, div.td-post-date, span.jeg_meta_date")
            tgl     = bersihkan(tgl_el.get_text()) if tgl_el else "-"
            desk_el = item.select_one("div.jeg_post_excerpt p, div.td-excerpt, p.excerpt")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 10:
                artikel.append({"judul": judul, "url": url,
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "lokal"})
        except:
            pass
    return artikel

def parse_suaragresik(soup, nama_sumber, url_sumber):
    return parse_gresiksatu(soup, nama_sumber, url_sumber)

def parse_generic(soup, nama_sumber, url_sumber):
    artikel = []
    item_sels = [
        "article", "div.post", "div.news-item", "div.jeg_post",
        "li.item-berita", "div.card-news", "div.entry",
        "div[class*='article']", "div[class*='post-item']",
        "div[class*='card']", "li[class*='item']",
    ]
    items = []
    for sel in item_sels:
        items = soup.select(sel)
        if len(items) > 3:
            break

    if not items:
        for a in soup.select("a[href]")[:60]:
            href  = a.get("href", "")
            judul = bersihkan(a.get_text())
            if len(judul) > 20 and any(x in href for x in
                    ["/berita/", "/news/", "/artikel/", "/?p=", "/post/", "/read/"]):
                artikel.append({"judul": judul,
                    "url": href if href.startswith("http") else urljoin(url_sumber, href),
                    "tanggal": datetime.now().strftime("%Y-%m-%d"), "ringkasan": "",
                    "topik": kategorikan_topik(judul),
                    "sumber": nama_sumber, "tipe": "lokal"})
        return artikel[:20]

    for item in items[:25]:
        try:
            h = item.select_one("h1,h2,h3,h4")
            a = ((h.select_one("a") if h else None)
                 or item.select_one("a[rel='bookmark']")
                 or item.select_one("a"))
            if not a:
                continue
            judul   = bersihkan(h.get_text() if h else a.get_text())
            url     = a.get("href", "")
            if not url:
                continue
            tgl_el  = item.select_one(
                "time, span.date, div.date, span[class*='date'], "
                "span[class*='time'], div[class*='meta'] time"
            )
            tgl     = bersihkan(
                tgl_el.get("datetime", "") or tgl_el.get_text()
            ) if tgl_el else "-"
            desk_el = item.select_one("p, div.excerpt, div[class*='excerpt'], div[class*='desc']")
            desk    = bersihkan(desk_el.get_text()) if desk_el else ""
            if judul and len(judul) > 8:
                artikel.append({"judul": judul,
                    "url": url if url.startswith("http") else urljoin(url_sumber, url),
                    "tanggal": ekstrak_tanggal(tgl), "ringkasan": desk,
                    "topik": kategorikan_topik(judul, desk),
                    "sumber": nama_sumber, "tipe": "lokal"})
        except:
            pass
    return artikel

# ── Parser map ─────────────────────────────────────────────────
PARSER_MAP = {
    "detik"      : parse_detik,
    "kompas"     : parse_kompas,
    "tribun"     : parse_tribun,
    "jawapos"    : parse_jawapos,
    "antara"     : parse_antara,
    "cnn"        : parse_cnn,
    "tempo"      : parse_tempo,
    "liputan6"   : parse_liputan6,
    "kumparan"   : parse_kumparan,
    "gresiksatu" : parse_gresiksatu,
    "suaragresik": parse_suaragresik,
    "generic"    : parse_generic,
}

# ══════════════════════════════════════════════════════
# UPDATE STATUS (shared dengan scraper lain)
# ══════════════════════════════════════════════════════
def update_status(success: bool, message: str = "", total: int = 0):
    """Update output/scrape_status.json — dibaca app.py."""
    status = {}
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                status = json.load(f)
        except Exception:
            pass
    status["berita"] = {
        "success" : success,
        "message" : message,
        "total"   : total,
        "last_run": datetime.now().strftime("%d %B %Y %H:%M"),
    }
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

# ══════════════════════════════════════════════════════
# SCRAPE SEMUA SUMBER
# ══════════════════════════════════════════════════════
def scrape_semua():
    semua_artikel = []
    print(f"\n{'='*65}")
    print(f"  SCRAPING BERITA GRESIK — {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    print(f"{'='*65}\n")

    # ── 1. Portal berita ──────────────────────────────────────
    for sumber in SUMBER_BERITA:
        nama     = sumber["nama"]
        url      = sumber["url"]
        tipe     = sumber["tipe"]
        parse_fn = PARSER_MAP.get(sumber["parse"], parse_generic)

        print(f"  📰 {nama:<35} ", end="", flush=True)
        soup = get_html(url)
        if not soup:
            print("❌ gagal")
            continue

        artikel = parse_fn(soup, nama, url)
        artikel_relevan = [
            a for a in artikel
            if cocok_keyword(a["judul"], a.get("ringkasan", ""), tipe)
        ]
        semua_artikel.extend(artikel_relevan)
        print(f"✅ {len(artikel_relevan)} berita")
        time.sleep(random.uniform(1.0, 2.5))

    # ── 2. Google News RSS ────────────────────────────────────
    print(f"\n  🔍 GOOGLE NEWS RSS (keyword search):")
    for kw in GOOGLE_NEWS_KEYWORDS:
        print(f"  🔎 '{kw}'  ", end="", flush=True)
        gnews = scrape_google_news_rss(kw)
        semua_artikel.extend(gnews)
        print(f"✅ {len(gnews)} berita")
        time.sleep(random.uniform(0.5, 1.5))

    return semua_artikel

# ══════════════════════════════════════════════════════
# SIMPAN CSV + LAPORAN
# ══════════════════════════════════════════════════════
def simpan_dan_laporan(artikel_list):
    if not artikel_list:
        print("\n⚠ Tidak ada berita ditemukan.")
        update_status(False, "Tidak ada berita ditemukan", 0)
        return None

    df = pd.DataFrame(artikel_list)
    df = df.drop_duplicates(subset=["judul"])
    df["waktu_scrape"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    kolom = ["judul", "tanggal", "topik", "sumber", "tipe",
             "ringkasan", "url", "waktu_scrape"]
    df_out = df[[c for c in kolom if c in df.columns]]

    # ── 1. File utama (dibaca app.py) ─────────────────────────
    #    output/gresik_berita.csv
    df_out.to_csv(BERITA_CSV, index=False, encoding="utf-8-sig")

    # ── 2. Arsip per waktu ────────────────────────────────────
    #    output/berita/berita_gresik_YYYYMMDD_HHMM.csv
    arsip_path = path_arsip()
    df_out.to_csv(arsip_path, index=False, encoding="utf-8-sig")

    # ── 3. Ringkasan topik ────────────────────────────────────
    #    output/gresik_berita_topik.csv
    ringkasan_topik = (
        df.groupby("topik")
        .agg(
            jumlah_berita = ("judul", "count"),
            sumber_berita = ("sumber", lambda x: " | ".join(x.unique()[:5])),
            contoh_judul  = ("judul",  lambda x: " || ".join(x.unique()[:3])),
        )
        .reset_index()
        .sort_values("jumlah_berita", ascending=False)
    )
    ringkasan_topik.to_csv(TOPIK_CSV, index=False, encoding="utf-8-sig")

    # ── 4. Ringkasan sumber ───────────────────────────────────
    #    output/gresik_berita_sumber.csv
    ringkasan_sumber = (
        df.groupby(["sumber", "tipe"])
        .agg(
            jumlah_berita = ("judul", "count"),
            topik_dibahas = ("topik", lambda x: " | ".join(x.unique()[:5])),
        )
        .reset_index()
        .sort_values("jumlah_berita", ascending=False)
    )
    ringkasan_sumber.to_csv(SUMBER_CSV, index=False, encoding="utf-8-sig")

    # ── 5. Log otomasi ────────────────────────────────────────
    #    output/berita/log_scraping.csv
    log_baru = {
        "waktu"          : datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_berita"   : len(df),
        "topik_terbanyak": ringkasan_topik.iloc[0]["topik"] if len(ringkasan_topik) > 0 else "-",
        "file_output"    : os.path.basename(arsip_path),
        "keywords"       : "|".join(KEYWORDS),
    }
    if os.path.exists(LOG_FILE):
        df_log = pd.read_csv(LOG_FILE)
        df_log = pd.concat([df_log, pd.DataFrame([log_baru])], ignore_index=True)
    else:
        df_log = pd.DataFrame([log_baru])
    df_log.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")

    # ── 6. Update scrape_status.json ──────────────────────────
    update_status(True, f"Berhasil {len(df)} berita dari {df['sumber'].nunique()} portal",
                  len(df))

    # ── Print laporan ──────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  HASIL SCRAPING BERITA GRESIK")
    print(f"{'='*65}")
    print(f"  📰 Total berita unik    : {len(df)}")
    print(f"  🏷  Topik               : {df['topik'].nunique()} topik")
    print(f"  📡 Sumber berita        : {df['sumber'].nunique()} portal")
    print(f"\n  OUTPUT (semua di dalam folder output/):")
    print(f"  ├── gresik_berita.csv           ← file utama (dibaca dashboard)")
    print(f"  ├── gresik_berita_topik.csv     ← ringkasan per topik")
    print(f"  ├── gresik_berita_sumber.csv    ← ringkasan per sumber")
    print(f"  ├── scrape_status.json          ← status scraping (shared)")
    print(f"  └── berita/")
    print(f"      ├── {os.path.basename(arsip_path)}  ← arsip")
    print(f"      └── log_scraping.csv                ← log otomasi")
    print(f"{'='*65}")

    print(f"\n  TOPIK:\n")
    print(f"  {'Topik':<25} {'Jumlah':^8}  {'Contoh Judul'}")
    print(f"  {'-'*80}")
    for _, r in ringkasan_topik.iterrows():
        contoh = str(r["contoh_judul"]).split(" || ")[0][:45]
        print(f"  {str(r['topik']):<25} {r['jumlah_berita']:^8}  {contoh}")

    print(f"\n  BERITA TERBARU (10 Pertama):\n")
    for i, (_, r) in enumerate(df.head(10).iterrows(), 1):
        print(f"  {i:2}. [{r['topik']:<20}] {r['judul'][:55]}")
        print(f"      📍 {r['sumber']} | 📅 {r['tanggal']}")
        if r.get("ringkasan"):
            print(f"      📝 {str(r['ringkasan'])[:75]}...")
        print()

    return df

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   SCRAPER BERITA GRESIK — Dashboard-Gresik              ║")
    print(f"║   Mulai  : {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}                         ║")
    print(f"║   Sumber : {len(SUMBER_BERITA)} portal + Google News RSS                ║")
    print(f"║   Keyword: {len(KEYWORDS)} kata kunci                                ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║   Output : output/gresik_berita.csv                     ║")
    print(f"║   Arsip  : output/berita/berita_gresik_*.csv            ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    artikel = scrape_semua()
    df      = simpan_dan_laporan(artikel)

    print(f"\n✅ Selesai!")
    print(f"\n  CARA OTOMASI HARIAN:")
    print(f"  Windows (Task Scheduler):")
    print(f"    → Create Basic Task → Trigger: Daily jam 07:00")
    print(f"    → Action: python {os.path.abspath(__file__)}")
    print(f"  Linux/Mac (crontab -e):")
    print(f"    → 0 7 * * * python {os.path.abspath(__file__)}\n")


if __name__ == "__main__":
    main()