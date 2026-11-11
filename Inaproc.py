"""Inaproc.py - ambil SEMUA produk kategori "Peralatan Elektronik" dari katalog.inaproc.id ke output/.

Langkah (sekali di awal, lalu rutin):
  1) python Inaproc.py --temukan --visible   -> baca menu Kategori, simpan daftar subkategori
                                                 ke output/kategori_inaproc.csv (periksa/ubah kolom "aktif")
  2) python Inaproc.py                       -> ambil produk semua subkategori yang aktif
Opsi:      --category "Router" "Printer Ink Jet"   (hanya subkategori tertentu)
           --kelompok "Networking"                 (hanya satu kelompok)
           --detail                                (isi spesifikasi lengkap dari halaman tiap produk)
           --lanjutkan                             (lewati subkategori yang file CSV-nya sudah ada)
           --url URL --label NAMA                  (satu URL kategori manual)
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse


# ---------------------------------------------------------------- harga
_PRICE_RE = re.compile(r"(\d[\d\.\,]*)")



def parse_price(raw: Any) -> int | None:
    """'Rp 12.345.678', 'Rp12.345.678,00', 12345678.0 -> 12345678 (rupiah bulat)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(round(raw)) if raw > 0 else None
    text = str(raw)
    m = _PRICE_RE.search(text)
    if not m:
        return None
    num = m.group(1)
    # Format Indonesia: titik = ribuan, koma = desimal.
    if "," in num and "." in num:
        num = num.replace(".", "").split(",")[0]
    elif "," in num:
        head, _, tail = num.rpartition(",")
        num = head.replace(",", "") if len(tail) <= 2 else num.replace(",", "")
    else:
        parts = num.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            num = "".join(parts)  # 12.345.678
        elif len(parts) == 2 and len(parts[1]) <= 2:
            num = parts[0]  # 12345.50
        else:
            num = "".join(parts)
    try:
        value = int(num)
    except ValueError:
        return None
    return value if value > 0 else None


# ---------------------------------------------------------------- merek
BRANDS = [
    "Acer", "Advan", "Apple", "Asus", "AXIOO", "Dell", "Fujitsu", "Gigabyte",
    "Hewlett Packard Enterprise", "HPE", "HP", "Huawei", "Infinix", "Inspur",
    "Lenovo", "LG", "MSI", "Positron", "Razer", "SPC", "Samsung", "Supermicro",
    "Toshiba", "Zyrex", "Itech", "Libera", "Evercoss", "Huawei", "Cisco",
    "Intel", "Synology", "QNAP", "Oracle", "Hikvision",
    "Canon", "Epson", "Brother", "Ricoh", "Xerox", "Kyocera", "Sharp", "Panasonic", "Sony",
    "Nikon", "Fujifilm", "GoPro", "DJI", "Logitech", "Rapoo", "A4Tech", "BenQ", "ViewSonic",
    "AOC", "Philips", "TP-Link", "D-Link", "Mikrotik", "Ubiquiti", "Netgear", "Tenda", "Ruijie",
    "Aruba", "Juniper", "Fortinet", "Palo Alto", "Sophos", "Dahua", "Western Digital", "Seagate",
    "Kingston", "SanDisk", "Transcend", "ADATA", "Crucial", "Wacom", "Huion", "Zebra", "Honeywell",
    "Epson", "Optoma", "Vivitek", "Hisense", "Polycom", "Jabra", "Poly",
]
_BRAND_PATTERNS = [
    (b, re.compile(rf"(?<![A-Za-z]){re.escape(b)}(?![A-Za-z])", re.I)) for b in BRANDS
]


def detect_brand(name: str, explicit: str | None = None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    for brand, pat in _BRAND_PATTERNS:
        if pat.search(name or ""):
            return "HPE" if brand == "Hewlett Packard Enterprise" else brand
    return None


# ------------------------------------------------------------ spesifikasi
def _first(pattern: str, text: str, flags=re.I):
    m = re.search(pattern, text, flags)
    return m


def extract_specs(name: str, spec_pairs: dict[str, str]) -> dict[str, Any]:
    """Standarkan atribut kunci dari teks nama + pasangan kunci/nilai spesifikasi."""
    blob = " | ".join([name or ""] + [f"{k}: {v}" for k, v in spec_pairs.items()])
    out: dict[str, Any] = {}

    m = _first(
        r"(Core\s*(?:Ultra\s*)?i[3579][-\s]?\w*|Ryzen\s*[3579]\s*\w*|Xeon[\w\-\s]*|"
        r"Celeron\s*\w*|Pentium\s*\w*|Athlon\s*\w*|EPYC\s*\w*|Apple\s*M\d\w*)",
        blob,
    )
    if m:
        out["cpu"] = re.sub(r"\s+", " ", m.group(1)).strip(" -|")

    # RAM: ambil angka GB yang diikuti kata RAM/DDR/LPDDR atau yang berdiri sendiri < 512.
    m = _first(r"(\d{1,4})\s*GB\s*(?:RAM|DDR\d?|LPDDR\d?)", blob) or _first(
        r"RAM\D{0,15}(\d{1,4})\s*GB", blob
    )
    if not m:
        m = _first(r"[,\(\|]\s*(\d{1,3})\s*GB\s*[,\)\|]", blob)
    if m:
        out["ram_gb"] = int(m.group(1))

    # Storage (SSD/HDD/NVMe/TB).
    m = _first(r"(\d+(?:[.,]\d+)?)\s*(TB|GB)\s*(?:SSD|NVMe|M\.2|HDD|eMMC)", blob) or _first(
        r"(?:SSD|NVMe|HDD|Storage|Penyimpanan)\D{0,15}(\d+(?:[.,]\d+)?)\s*(TB|GB)", blob
    )
    if m:
        size = float(m.group(1).replace(",", "."))
        gb = int(size * 1024) if m.group(2).upper() == "TB" else int(size)
        out["storage_gb"] = gb
        t = _first(r"(SSD|NVMe|HDD|eMMC)", blob)
        if t:
            out["storage_type"] = t.group(1).upper().replace("NVME", "NVMe")

    m = _first(r"(\d{2}(?:[.,]\d)?)\s*(?:inch|inci|\"|”)", blob)
    if m:
        out["screen_inch"] = float(m.group(1).replace(",", "."))

    m = _first(r"((?:Windows|Win)\s*\d+\s*(?:Home|Pro|SL|Single Language)?|FreeDOS|DOS|Linux|Ubuntu)", blob)
    if m:
        out["os"] = re.sub(r"\s+", " ", m.group(1)).strip()

    m = _first(r"TKDN\D{0,12}(\d{1,3}(?:[.,]\d+)?)\s*%", blob)
    if m:
        out["tkdn_pct"] = float(m.group(1).replace(",", "."))

    m = _first(r"(?:garansi|warranty)\D{0,12}(\d+)\s*(?:tahun|thn|year|yr)", blob)
    if m:
        out["warranty_years"] = int(m.group(1))

    return out


# ---------------------------------------------------------------- kategori
def classify_category(name: str, category_hint: str | None = None) -> str:
    text = f"{category_hint or ''} {name or ''}".lower()
    if re.search(r"\bserver\b|poweredge|proliant|thinksystem|\brack\b", text):
        return "Server"
    if re.search(r"laptop|notebook|chromebook|ultrabook|thinkpad|ideapad|vivobook|zenbook", text):
        return "Laptop"
    if re.search(r"\bpc\b|desktop|all[- ]in[- ]one|\baio\b|workstation|mini pc|komputer", text):
        return "PC"
    return "Lainnya"


def slugify(text: str) -> str:
    """'Printer Ink Jet' -> 'printer_ink_jet'. Aturan yang SAMA dipakai n8n untuk nama file per kategori."""
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_") or "lainnya"


# Nama di menu -> nama lama agar data Laptop/PC/Server yang sudah ada tetap nyambung.
CATEGORY_ALIAS = {
    "laptop/notebook": "Laptop",
    "desktop, aio dan mini pc": "PC",
}


def category_label(subkategori: str) -> str:
    key = re.sub(r"\s+", " ", str(subkategori or "")).strip()
    return CATEGORY_ALIAS.get(key.lower(), key)


def ringkas_spesifikasi(pairs: dict, description: str | None = None, limit: int = 400) -> str | None:
    """Ringkasan spesifikasi umum (untuk produk non-komputer: printer, router, kamera, dst)."""
    if pairs:
        s = "; ".join(f"{k}: {v}" for k, v in pairs.items() if str(v).strip())
    else:
        s = description or ""
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] or None


# =====================================================================================
#  SCRAPER: rekam respons JSON yang dimuat halaman (Selenium + Chrome DevTools)
#  Semua kategori di .env diproses otomatis; hasil ke folder  output/
# =====================================================================================
import argparse
import base64
import csv
import hashlib
import os
import random
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
INSPECT_DIR = OUTPUT_DIR / "inspect"
CSV_PATH = OUTPUT_DIR / "data_inaproc.csv"
KATEGORI_CSV = OUTPUT_DIR / "kategori_inaproc.csv"      # daftar subkategori hasil --temukan

USER_AGENT = "ProcurementResearchBot/1.0 (riset harga publik)"

CONFIG = {
    "base_url": "https://katalog.inaproc.id",
    "induk_kategori": "Peralatan Elektronik",   # kategori induk di menu; ubah lewat INAPROC_INDUK_KATEGORI
    "delay_seconds": (2.0, 3.5),
    "max_rounds": 60,            # batas pengaman: berapa kali gulir/klik "berikutnya" per kategori
    "categories": {"Laptop": [], "PC": [], "Server": []},   # opsional, dari .env (cadangan manual)
}

CSV_COLUMNS = ["category", "kelompok", "brand", "name", "price_idr", "provider_name", "cpu", "ram_gb",
               "storage_gb", "storage_type", "screen_inch", "os", "tkdn_pct",
               "warranty_years", "spesifikasi", "url"]
KATEGORI_COLUMNS = ["aktif", "kelompok", "subkategori", "category_id", "url"]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ .env
def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def apply_env_overrides() -> None:
    """INAPROC_BASE_URL, INAPROC_URL_LAPTOP / _PC / _SERVER (beberapa URL dipisah tanda |)."""
    load_env_file(BASE_DIR / ".env")
    base = os.environ.get("INAPROC_BASE_URL", "").strip()
    if base:
        p = urlparse(base if "://" in base else "https://" + base)
        CONFIG["base_url"] = f"{p.scheme}://{p.netloc}"
    induk = os.environ.get("INAPROC_INDUK_KATEGORI", "").strip()
    if induk:
        CONFIG["induk_kategori"] = induk
    # Semua INAPROC_URL_<KODE>=... dibaca. Nama subkategori = INAPROC_NAME_<KODE> bila ada,
    # lalu nama ramah bawaan di bawah, lalu <KODE> itu sendiri.
    ramah = {"LAPTOP": "Laptop", "PC": "PC", "SERVER": "Server", "STORAGE": "Storage", "DISPLAY": "Display",
             "UPS": "UPS", "NETWORKING": "Networking", "PRINTER": "Printer", "SCANNER": "Scanner",
             "KAMERA": "Kamera", "TELEVISI": "Televisi", "PRESENTASI": "Presentasi"}
    CONFIG["categories"] = {}
    for key, val in os.environ.items():
        if not key.startswith("INAPROC_URL_"):
            continue
        kode = key[len("INAPROC_URL_"):]
        nama = os.environ.get("INAPROC_NAME_" + kode, "").strip() or ramah.get(kode.upper(), kode.upper())
        urls = [u.strip() for u in val.split("|") if u.strip()]
        if urls:
            CONFIG["categories"][nama] = CONFIG["categories"].get(nama, []) + urls


def robots_checker(base_url: str):
    rp = urllib.robotparser.RobotFileParser()
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        import requests
        r = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if r.status_code == 200:
            rp.parse(r.text.splitlines())
            log(f"[robots] {robots_url} dibaca.")
            return lambda url: rp.can_fetch(USER_AGENT, url)
        if r.status_code in (404, 410):
            return lambda url: True
    except Exception as exc:  # noqa: BLE001
        log(f"[robots] gagal membaca {robots_url}: {exc}")
    log("[robots] robots.txt tidak terbaca - lanjut dengan jeda konservatif.")
    return lambda url: True


def polite_sleep() -> None:
    lo, hi = CONFIG["delay_seconds"]
    time.sleep(random.uniform(lo, hi))


# ------------------------------------------------------------------ browser
def make_driver(visible: bool = False):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    if not visible:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1366,900")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--lang=id-ID")
    opts.add_argument(f"--user-agent={USER_AGENT}")
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    local = BASE_DIR / "chromedriver.exe"
    if os.environ.get("INAPROC_USE_LOCAL_DRIVER") == "1" and local.exists():
        driver = webdriver.Chrome(service=Service(str(local)), options=opts)
    else:
        driver = webdriver.Chrome(options=opts)     # Selenium Manager mengurus driver otomatis
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


def harvest(driver, seen_keys: set) -> list[dict]:
    """Ambil respons JSON (XHR/fetch) baru yang dimuat halaman sejak panggilan terakhir."""
    out = []
    for entry in driver.get_log("performance"):
        try:
            msg = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        if msg.get("method") != "Network.responseReceived":
            continue
        params = msg["params"]
        resp = params.get("response", {})
        if "json" not in (resp.get("mimeType") or "") or params.get("type") not in ("XHR", "Fetch"):
            continue
        try:
            body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": params["requestId"]})
            text = body["body"]
            if body.get("base64Encoded"):
                text = base64.b64decode(text).decode("utf-8", "replace")
            data = json.loads(text)
        except Exception:  # noqa: BLE001  (body sudah dibuang / bukan JSON valid)
            continue
        key = (resp.get("url"), hashlib.md5(text.encode("utf-8", "replace")).hexdigest())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append({"url": resp.get("url"), "status": resp.get("status"), "data": data})
    return out


# ------------------------------------------------------------------ normalisasi JSON -> produk
PROVIDER_WORDS = ("penyedia", "seller", "toko", "shop", "store", "vendor", "merchant", "supplier")
NAME_KEYS = ["namaproduk", "productname", "namabarang", "nama", "name", "title", "judul"]
PRICE_KEYS = ["harga", "price", "hargatayang", "hargasatuan", "hargaproduk", "hargaaktif",
              "hargajual", "hargamin", "pricemin", "minprice", "lowprice"]
PRICE_SUBKEYS = ("min", "nilai", "value", "amount", "angka", "tayang", "satuan", "jual")
PRICE_BAD = ("diskon", "discount", "ongkir", "coret", "ppn", "persen", "percent")
BRAND_KEYS = ["merek", "brand", "namamerek", "brandname"]
ID_KEYS = ["id", "kdproduk", "kodeproduk", "productid", "produkid", "idproduk", "uuid", "kode"]
SLUG_KEYS = ["slug", "produkslug", "productslug", "slugproduk"]
URL_KEYS = ["url", "link", "producturl", "tautan", "href", "permalink"]
SKU_KEYS = ["sku", "kodesku", "partnumber"]
DESC_KEYS = ["deskripsi", "description", "keterangan"]
SPEC_WORDS = ("spesifikasi", "specification", "spec", "atribut", "attribute")


def _norm(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def flatten(obj, prefix: str = "", depth: int = 0, out: dict | None = None) -> dict:
    out = {} if out is None else out
    if isinstance(obj, dict) and depth < 4:
        for k, v in obj.items():
            flatten(v, f"{prefix}.{k}" if prefix else str(k), depth + 1, out)
    else:
        out[prefix] = obj
    return out


def _is_provider_path(path: str) -> bool:
    return any(w in path.lower() for w in PROVIDER_WORDS)


def _scalar(v) -> bool:
    return isinstance(v, (str, int, float)) and not isinstance(v, bool) and v != ""


def pick(flat: dict, cands: list[str], provider: bool = False):
    items = sorted(flat.items(), key=lambda kv: kv[0].count("."))   # kunci dangkal didahulukan
    for cand in cands:
        for k, v in items:
            if _norm(k.split(".")[-1]) == cand and _is_provider_path(k) == provider and _scalar(v):
                return v
    return None


def pick_price(flat: dict) -> int | None:
    for k, v in sorted(flat.items(), key=lambda kv: kv[0].count(".")):
        if _is_provider_path(k):
            continue
        parts = [_norm(p) for p in k.split(".")]
        direct = parts[-1] in PRICE_KEYS
        nested = len(parts) >= 2 and parts[-2] in PRICE_KEYS and parts[-1] in PRICE_SUBKEYS
        if (direct or nested) and not any(b in parts[-1] for b in PRICE_BAD):
            price = parse_price(v) if _scalar(v) else None
            if price:
                return price
    for k, v in flat.items():       # cadangan: kunci apa pun yang memuat "harga"/"price"
        last = _norm(k.split(".")[-1])
        if ("harga" in last or "price" in last) and not any(b in last for b in PRICE_BAD) \
                and not _is_provider_path(k) and _scalar(v):
            price = parse_price(v)
            if price:
                return price
    return None


def spec_pairs(flat: dict) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for k, v in flat.items():
        segs = k.split(".")
        last = _norm(segs[-1])
        in_spec_parent = any(any(w in _norm(s) for w in SPEC_WORDS) for s in segs[:-1])
        is_spec_leaf = any(w in last for w in SPEC_WORDS)
        if isinstance(v, list) and is_spec_leaf:
            for e in v:
                if isinstance(e, dict):
                    nm = next((e[x] for x in ("nama", "name", "key", "label", "atribut", "judul", "title")
                               if _scalar(e.get(x))), None)
                    val = next((e[x] for x in ("nilai", "value", "isi", "val") if _scalar(e.get(x))), None)
                    if nm and val is not None:
                        pairs[str(nm)] = str(val)
        elif _scalar(v) and in_spec_parent:
            pairs[segs[-1]] = str(v)
        elif isinstance(v, str) and is_spec_leaf and v.strip():
            pairs["Spesifikasi"] = v.strip()[:2000]
    return pairs


def build_record(item: dict, label: str, base_url: str, source_url: str, kelompok: str = "") -> dict | None:
    flat = flatten(item)
    name = pick(flat, NAME_KEYS)
    price = pick_price(flat)
    if not name or not price:
        return None
    name = re.sub(r"\s+", " ", str(name)).strip()
    pairs = spec_pairs(flat)
    provider = pick(flat, ["namapenyedia", "namatoko", "sellername", "shopname", "storename",
                           "vendorname", "penyedia", "seller", "toko", "shop", "store",
                           "vendor", "nama", "name"], provider=True)
    provider_slug = pick(flat, ["penyediaslug", "slugpenyedia", "slug", "urlslug"], provider=True)
    slug = pick(flat, SLUG_KEYS)
    pid = pick(flat, ID_KEYS)
    link = pick(flat, URL_KEYS)
    if isinstance(link, str) and link:
        url = urljoin(base_url + "/", link)
    elif provider_slug and slug:
        url = f"{base_url}/{provider_slug}/{slug}"
    else:
        url = f"{source_url}#id={pid or slug or name}"       # cadangan agar tiap produk punya kunci unik
    brand = pick(flat, BRAND_KEYS) or pairs.get("Merek") or pairs.get("Brand")
    return {
        "url": url,
        "name": name,
        "brand": detect_brand(name, str(brand) if brand else None),
        "category": label,
        "kelompok": kelompok or None,
        "spesifikasi": ringkas_spesifikasi(pairs, str(pick(flat, DESC_KEYS) or "")),
        "price_idr": price,
        "provider_name": str(provider).strip() if provider else None,
        "provider_slug": str(provider_slug) if provider_slug else None,
        "product_slug": str(slug) if slug else None,
        "sku": str(pick(flat, SKU_KEYS)) if pick(flat, SKU_KEYS) else None,
        "description": (str(pick(flat, DESC_KEYS))[:4000] if pick(flat, DESC_KEYS) else None),
        "specs": extract_specs(name, pairs),
        "spec_raw": pairs,
        "source_id": str(pid) if pid else None,
    }


def find_dict_lists(obj, depth: int = 0):
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:5]):
            yield obj
        else:
            for x in obj[:50]:
                yield from find_dict_lists(x, depth + 1)
    elif isinstance(obj, dict) and depth < 7:
        for v in obj.values():
            yield from find_dict_lists(v, depth + 1)


def ingest(captures: list[dict], label: str, source_url: str, records: dict, endpoints: dict,
           kelompok: str = "") -> int:
    """Cari daftar produk di respons JSON; tambahkan ke records. Kembalikan jumlah produk baru."""
    added = 0
    for cap in captures:
        for lst in find_dict_lists(cap["data"]):
            recs = [r for r in (build_record(i, label, CONFIG["base_url"], source_url, kelompok)
                                for i in lst) if r]
            if not recs or len(recs) / len(lst) < 0.5:      # bukan daftar produk (menu, banner, dst)
                continue
            ep = cap["url"].split("?")[0]
            endpoints[ep] = endpoints.get(ep, 0) + len(recs)
            for r in recs:
                if r["url"] not in records:
                    records[r["url"]] = r
                    added += 1
    return added


# ------------------------------------------------------------------ navigasi halaman
NEXT_XPATHS = [
    "//button[not(@disabled)][contains(normalize-space(.),'Selanjutnya') or contains(normalize-space(.),'Berikutnya') "
    "or contains(normalize-space(.),'Muat') or contains(normalize-space(.),'Lihat Lebih') "
    "or @aria-label='Next' or @aria-label='next' or @aria-label='Berikutnya']",
    "//a[contains(normalize-space(.),'Selanjutnya') or contains(normalize-space(.),'Berikutnya') "
    "or @aria-label='Next' or @aria-label='next' or @aria-label='Berikutnya']",
]


def click_next(driver) -> bool:
    from selenium.webdriver.common.by import By
    for xp in NEXT_XPATHS:
        for el in driver.find_elements(By.XPATH, xp):
            try:
                if el.is_displayed() and el.is_enabled():
                    driver.execute_script("arguments[0].click();", el)
                    return True
            except Exception:  # noqa: BLE001
                continue
    return False


def describe_captures(captures: list[dict]) -> None:
    """Diagnosis bila tidak ada produk terdeteksi: tampilkan isi respons JSON yang tertangkap."""
    log(f"  [debug] {len(captures)} respons JSON tertangkap. Contoh:")
    for cap in captures[:15]:
        desc = type(cap["data"]).__name__
        for lst in find_dict_lists(cap["data"]):
            desc = f"list[{len(lst)}] kunci: {list(lst[0].keys())[:8]}"
            break
        log(f"     - {cap['url'][:110]} -> {desc}")


def crawl_category(driver, label: str, url: str, allowed, records: dict, max_rounds: int, raw: list,
                   kelompok: str = "") -> int:
    from selenium.webdriver.support.ui import WebDriverWait

    if not allowed(url):
        log(f"[robots] dilarang: {url}")
        return 0
    log(f"[{label}] {url}")
    seen_keys: set = set()
    endpoints: dict = {}
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception as exc:  # noqa: BLE001
        log(f"  gagal membuka halaman: {exc.__class__.__name__}")
        return 0
    time.sleep(4)
    captures = harvest(driver, seen_keys)
    raw.extend(captures)
    total = ingest(captures, label, url, records, endpoints, kelompok)
    stale = 0
    for rnd in range(1, max_rounds + 1):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        clicked = click_next(driver)
        polite_sleep()
        new_caps = harvest(driver, seen_keys)
        raw.extend(new_caps)
        added = ingest(new_caps, label, url, records, endpoints, kelompok)
        total += added
        log(f"  putaran {rnd}: +{added} produk (total {total}){' [klik berikutnya]' if clicked else ''}")
        stale = 0 if added else stale + 1
        if stale >= 2:
            break
    for ep, n in endpoints.items():
        log(f"  sumber data: {ep} ({n} item)")
    if total == 0:
        describe_captures(raw)
    return total


# ------------------------------------------------------------------ penemuan kategori
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
NAME_FIELDS = ("nama", "name", "title", "label", "namakategori", "categoryname")
ID_FIELDS = ("id", "categoryid", "kategoriid", "idkategori", "uuid", "kode")


def category_id_from_url(url: str) -> str | None:
    q = parse_qs(urlparse(url).query)
    for k, v in q.items():
        if k.lower() == "categoryid" and v:
            return v[0]
    m = UUID_RE.search(url or "")
    return m.group(0) if m else None


def _node_name(d: dict) -> str | None:
    for k, v in d.items():
        if _norm(k) in NAME_FIELDS and isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _node_id(d: dict) -> str | None:
    for k, v in d.items():
        if _norm(k) in ID_FIELDS and isinstance(v, str) and UUID_RE.fullmatch(v.strip()):
            return v.strip()
    return None


def _node_children(d: dict) -> list:
    best: list = []
    for v in d.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v) and len(v) > len(best):
            if any(_node_name(x) for x in v):
                best = v
    return best


def find_node(obj, target: str, depth: int = 0):
    """Cari simpul pohon kategori bernama `target` (sudah dinormalisasi) yang punya anak."""
    if depth > 14:
        return None
    if isinstance(obj, dict):
        nm = _node_name(obj)
        if nm and _norm(nm) == target and _node_children(obj):
            return obj
        for v in obj.values():
            hit = find_node(v, target, depth + 1)
            if hit:
                return hit
    elif isinstance(obj, list):
        for x in obj:
            hit = find_node(x, target, depth + 1)
            if hit:
                return hit
    return None


def tree_leaves(node: dict, path: list[str]) -> list[tuple[list[str], str, str]]:
    """Simpul terdalam yang punya id: [(jalur_induk, nama, id)]."""
    out = []
    for ch in _node_children(node):
        nm = _node_name(ch)
        if not nm:
            continue
        sub = tree_leaves(ch, path + [nm])
        if sub:
            out += sub
        elif _node_id(ch):
            out.append((path, nm, _node_id(ch)))
    return out


def rows_from_tree(captures: list[dict], induk: str, base_url: str) -> list[dict]:
    target = _norm(induk)
    for cap in captures:
        node = find_node(cap["data"], target)
        if not node:
            continue
        rows = [{"kelompok": path[0] if path else induk, "subkategori": nm, "category_id": cid,
                 "url": f"{base_url}/search?categoryId={cid}"}
                for path, nm, cid in tree_leaves(node, [])]
        if rows:
            return rows
    return []


# Dijalankan di browser: kumpulkan semua tautan ...categoryId=... yang tampil di KANAN daftar kiri menu.
# Teks tebal bukan-tautan = judul kelompok (mis. "Komputer dan Aksesoris", "Networking").
MENU_JS = r"""
const kiri = arguments[0].getBoundingClientRect();
const out = [];
let group = '';
const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
let n;
while ((n = walker.nextNode())) {
  const r = n.getBoundingClientRect();
  if (!r.width || !r.height || r.left < kiri.right - 4) continue;
  const isA = n.tagName === 'A';
  if (!isA && n.closest('a')) continue;
  const own = Array.from(n.childNodes).filter(c => c.nodeType === 3)
                   .map(c => c.textContent.trim()).join(' ').trim();
  const text = (isA ? n.textContent : own).replace(/\s+/g, ' ').trim();
  if (!text || text.length > 90) continue;
  const bold = parseInt(getComputedStyle(n).fontWeight, 10) >= 600;
  const href = isA ? (n.getAttribute('href') || '') : '';
  if (isA && /categoryid=/i.test(href)) {
    out.push({group: group, text: text, href: href, bold: bold});
    if (bold) group = text;
  } else if (!isA && bold) {
    group = text;
  }
}
return out;
"""


def _xp(text: str) -> str:
    return f'"{text}"' if "'" in text else f"'{text}'"


def discover_dom(driver, induk: str) -> list[dict]:
    """Buka menu Kategori, pilih kategori induk, baca semua subkategori beserta tautannya."""
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By

    def tampak(xp: str) -> list:
        hasil = []
        for el in driver.find_elements(By.XPATH, xp):
            try:
                if el.is_displayed():
                    hasil.append(el)
            except Exception:  # noqa: BLE001
                continue
        return hasil

    pemicu = tampak("//*[self::button or self::a or self::div or self::span][normalize-space(.)='Kategori']")
    if pemicu:
        driver.execute_script("arguments[0].click();", pemicu[0])
        time.sleep(2)
    kandidat = tampak(f"//*[normalize-space(.)={_xp(induk)}]")
    if not kandidat:
        log(f"  menu '{induk}' tidak terlihat di halaman")
        return []
    kiri = min(kandidat, key=lambda e: e.rect["x"])
    try:
        ActionChains(driver).move_to_element(kiri).click().perform()
    except Exception:  # noqa: BLE001
        driver.execute_script("arguments[0].click();", kiri)
    time.sleep(2.5)

    items = driver.execute_script(MENU_JS, kiri) or []
    base = CONFIG["base_url"]
    leaves: list[dict] = []
    heads: list[dict] = []
    for it in items:
        cid = category_id_from_url(it["href"])
        if not cid:
            continue
        row = {"kelompok": it["group"] or induk, "subkategori": it["text"], "category_id": cid,
               "url": urljoin(base + "/", it["href"])}
        (heads if it["bold"] else leaves).append(row)
    ada_anak = {r["kelompok"] for r in leaves}
    for h in heads:            # judul kelompok yang tautan dan tidak punya anak = kategori itu sendiri
        if h["subkategori"] not in ada_anak:
            h["kelompok"] = h["subkategori"]
            leaves.append(h)
    return leaves


def temukan_kategori(driver, induk: str) -> list[dict]:
    base = CONFIG["base_url"]
    seen_keys: set = set()
    log(f"[temukan] membuka {base} dan membaca menu kategori '{induk}' ...")
    driver.get(base + "/")
    try:
        from selenium.webdriver.support.ui import WebDriverWait
        WebDriverWait(driver, 20).until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:  # noqa: BLE001
        pass
    time.sleep(5)
    caps = harvest(driver, seen_keys)
    rows: list[dict] = []
    try:
        rows = discover_dom(driver, induk)
    except Exception as exc:  # noqa: BLE001
        log(f"  baca menu (DOM) gagal: {exc.__class__.__name__}: {str(exc)[:120]}")
    caps += harvest(driver, seen_keys)
    if rows:
        log(f"  {len(rows)} subkategori ditemukan dari menu di halaman")
    else:
        rows = rows_from_tree(caps, induk, base)
        if rows:
            log(f"  {len(rows)} subkategori ditemukan dari respons JSON (periksa URL-nya di kategori_inaproc.csv)")
    if not rows:
        INSPECT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            driver.save_screenshot(str(INSPECT_DIR / "menu.png"))
        except Exception:  # noqa: BLE001
            pass
        keep = [c for c in caps if induk.lower() in json.dumps(c["data"], ensure_ascii=False).lower()][:3]
        dump = {"respons_json": [{"url": c["url"], "status": c["status"]} for c in caps], "memuat_induk": keep}
        (INSPECT_DIR / "kategori_raw.json").write_text(json.dumps(dump, ensure_ascii=False)[:3_000_000],
                                                       encoding="utf-8")
        log("  Tidak ada subkategori terbaca. Kirim output/inspect/menu.png dan kategori_raw.json ke Claude.")
    return rows


def baca_manifest() -> list[dict]:
    if not KATEGORI_CSV.exists():
        return []
    with open(KATEGORI_CSV, newline="", encoding="utf-8-sig") as fh:
        return [r for r in csv.DictReader(fh) if r.get("url")]


def simpan_manifest(rows: list[dict]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lama = {r.get("category_id"): r.get("aktif", "1") for r in baca_manifest()}
    uniq: dict = {}
    for r in rows:
        cid = r["category_id"]
        if cid not in uniq:
            uniq[cid] = {"aktif": lama.get(cid, "1"), "kelompok": r["kelompok"],
                         "subkategori": r["subkategori"], "category_id": cid, "url": r["url"]}
    path = KATEGORI_CSV
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=KATEGORI_COLUMNS)
            w.writeheader()
            w.writerows(uniq.values())
    except PermissionError:
        path = OUTPUT_DIR / f"kategori_inaproc_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=KATEGORI_COLUMNS)
            w.writeheader()
            w.writerows(uniq.values())
        log(f"[!] {KATEGORI_CSV.name} sedang terbuka di program lain; disimpan ke {path.name}")
    return path


def susun_pekerjaan(args) -> list[tuple[str, str, str]]:
    """Daftar (label, kelompok, url). Sumber: output/kategori_inaproc.csv (kolom aktif=1) + cadangan .env."""
    if args.url:
        return [(args.label, "", args.url)]
    names = {n.strip().lower() for n in (args.category or [])}
    kel = {k.strip().lower() for k in (args.kelompok or [])}
    jobs: list[tuple[str, str, str]] = []
    for r in baca_manifest():
        if str(r.get("aktif", "1")).strip().lower() not in ("1", "ya", "y", "true", "aktif", ""):
            continue
        label = category_label(r["subkategori"])
        if names and not ({label.lower(), r["subkategori"].strip().lower()} & names):
            continue
        if kel and r.get("kelompok", "").strip().lower() not in kel:
            continue
        jobs.append((label, r.get("kelompok", ""), r["url"]))
    if not kel:       # cadangan manual dari .env (INAPROC_URL_LAPTOP/_PC/_SERVER), tanpa duplikat
        ada = {category_id_from_url(u) for _, _, u in jobs}
        for cat, urls in CONFIG["categories"].items():
            if names and cat.lower() not in names:
                continue
            for u in urls:
                if category_id_from_url(u) not in ada:
                    jobs.append((cat, "", u))
    return jobs


# ------------------------------------------------------------------ simpan
def record_to_row(r: dict) -> dict:
    row = {**{k: r.get(k) for k in CSV_COLUMNS}, **(r.get("specs") or {})}
    return {k: row.get(k) for k in CSV_COLUMNS}


def load_existing() -> dict:
    """Baca CSV lama (kunci = url) agar hasil baru digabung, bukan menimpa."""
    rows: dict = {}
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if row.get("url"):
                    rows[row["url"]] = row
    return rows


def write_csv(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


CATEGORY_DIR = OUTPUT_DIR / "inaproc"          # satu folder berisi satu CSV per subkategori


def category_file(label: str) -> Path:
    return CATEGORY_DIR / f"{slugify(label)}.csv"


def pindah_file_lama() -> None:
    """Pindahkan output/data_inaproc_<nama>.csv (susunan lama) ke output/inaproc/<nama>.csv."""
    for p in OUTPUT_DIR.glob("data_inaproc_*.csv"):
        nama = p.stem[len("data_inaproc_"):]
        if re.fullmatch(r"\d{8}_\d{6}", nama):      # cadangan bertanda waktu: biarkan
            continue
        CATEGORY_DIR.mkdir(parents=True, exist_ok=True)
        tujuan = CATEGORY_DIR / f"{nama}.csv"
        try:
            if tujuan.exists():
                tujuan.unlink()
            p.replace(tujuan)
            log(f"[pindah] {p.name} -> inaproc/{tujuan.name}")
        except OSError as exc:
            log(f"[!] gagal memindah {p.name}: {exc}")


def sudah_ada(label: str) -> bool:
    p = category_file(label)
    if not p.exists():
        return False
    with open(p, encoding="utf-8-sig") as fh:
        return sum(1 for _ in fh) > 1


def save_all(records: dict) -> tuple[int, Path]:
    """Simpan ke output/: data_inaproc.csv (semua) + inaproc/<subkategori>.csv (kecil, untuk n8n).
    Hanya CSV (UTF-8 BOM, rapi di Excel). Hasil baru digabung dengan CSV lama per URL."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged = load_existing()
    for r in records.values():
        merged[r["url"]] = record_to_row(r)
    rows = list(merged.values())

    main_path = CSV_PATH
    try:
        write_csv(CSV_PATH, rows)
    except PermissionError:       # di Windows: file sedang terbuka di Excel
        main_path = OUTPUT_DIR / f"data_inaproc_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        write_csv(main_path, rows)
        log(f"[!] {CSV_PATH.name} sedang terbuka di program lain (mis. Excel); hasil disimpan ke {main_path.name}")

    labels = {r["category"] for r in records.values()}
    for label in sorted(labels):          # hanya file subkategori yang disentuh putaran ini
        slug = slugify(label)
        part = [r for r in rows if slugify(r.get("category")) == slug]
        path = category_file(label)
        try:
            write_csv(path, part)
            log(f"  {path.name}: {len(part)} produk")
        except PermissionError:
            log(f"[!] {path.name} sedang terbuka di program lain - dilewati")
    return len(rows), main_path


# ------------------------------------------------------------------ spesifikasi lengkap (halaman detail)
def find_spec_pairs(obj, depth: int = 0, out: dict | None = None) -> dict:
    """Cari pasangan nama/nilai spesifikasi di mana pun dalam JSON halaman detail produk."""
    out = {} if out is None else out
    if depth > 8:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(w in _norm(k) for w in SPEC_WORDS):
                if isinstance(v, list):
                    for e in v:
                        if isinstance(e, dict):
                            nm = next((e[x] for x in ("nama", "name", "key", "label", "atribut", "judul", "title")
                                       if _scalar(e.get(x))), None)
                            val = next((e[x] for x in ("nilai", "value", "isi", "val") if _scalar(e.get(x))), None)
                            if nm and val is not None:
                                out[str(nm)] = str(val)
                elif isinstance(v, dict):
                    for kk, vv in v.items():
                        if _scalar(vv):
                            out[str(kk)] = str(vv)
                elif isinstance(v, str) and v.strip():
                    out.setdefault("Spesifikasi", v.strip()[:1500])
            find_spec_pairs(v, depth + 1, out)
    elif isinstance(obj, list):
        for x in obj[:200]:
            find_spec_pairs(x, depth + 1, out)
    return out


def ambil_detail(driver, url: str) -> dict:
    """Buka halaman produk, tangkap JSON-nya, kembalikan pasangan spesifikasi."""
    seen: set = set()
    harvest(driver, seen)                      # buang log sebelumnya
    driver.get(url)
    time.sleep(3.5)
    pairs: dict = {}
    for cap in harvest(driver, seen):
        find_spec_pairs(cap["data"], out=pairs)
    return pairs


def lengkapi_detail(driver, jobs: list, allowed, maks: int, ulang: bool) -> None:
    """Untuk tiap subkategori: kunjungi halaman produk yang spesifikasinya masih kosong, isi spesifikasi lengkap."""
    total = 0
    for label, _kel, _url in jobs:
        path = category_file(label)
        if not path.exists():
            continue
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        target = [r for r in rows if r.get("url", "").startswith("http")
                  and (ulang or len(r.get("spesifikasi") or "") < 40)]
        log(f"[detail] {label}: {len(target)} produk perlu dilengkapi dari {len(rows)}")
        diubah: dict = {}
        for i, r in enumerate(target, 1):
            if maks and total >= maks:
                break
            if not allowed(r["url"]):
                continue
            try:
                pairs = ambil_detail(driver, r["url"])
            except Exception as exc:  # noqa: BLE001
                log(f"  [!] {exc.__class__.__name__} pada {r['url'][:80]}")
                continue
            total += 1
            if pairs:
                r["spesifikasi"] = ringkas_spesifikasi(pairs, None, 1000)
                for k, v in extract_specs(r.get("name") or "", pairs).items():
                    if k in r and not r.get(k):
                        r[k] = v
                diubah[r["url"]] = {**r, "specs": {}}
            polite_sleep()
            if i % 25 == 0 and diubah:                       # simpan berkala
                save_all(diubah)
                log(f"  {i}/{len(target)} diproses, {len(diubah)} terisi")
        if diubah:
            save_all(diubah)
            log(f"  {label}: {len(diubah)} produk kini punya spesifikasi lengkap")
        if maks and total >= maks:
            log(f"[detail] berhenti: batas {maks} produk tercapai (lanjutkan dengan menjalankan perintah yang sama)")
            break


def main() -> None:
    ap = argparse.ArgumentParser(description="Ambil produk Peralatan Elektronik dari katalog.inaproc.id -> output/")
    ap.add_argument("--temukan", action="store_true",
                    help="baca menu Kategori & simpan daftar subkategori ke output/kategori_inaproc.csv")
    ap.add_argument("--category", nargs="*", help="hanya subkategori ini (nama seperti di menu)")
    ap.add_argument("--kelompok", nargs="*", help="hanya kelompok ini (mis. Networking)")
    ap.add_argument("--detail", action="store_true",
                    help="kunjungi halaman tiap produk untuk mengambil spesifikasi LENGKAP (lambat; bisa dilanjutkan)")
    ap.add_argument("--maks-detail", type=int, default=0, help="batasi jumlah produk per proses --detail (0 = semua)")
    ap.add_argument("--detail-ulang", action="store_true", help="ambil ulang walau spesifikasi sudah terisi")
    ap.add_argument("--lanjutkan", action="store_true", help="lewati subkategori yang file CSV-nya sudah ada")
    ap.add_argument("--url", help="URL kategori manual (gunakan bersama --label)")
    ap.add_argument("--label", default="Lainnya", help="nama kategori untuk --url")
    ap.add_argument("--max-rounds", type=int, default=CONFIG["max_rounds"])
    ap.add_argument("--visible", action="store_true", help="tampilkan jendela Chrome (untuk memantau)")
    args = ap.parse_args()
    apply_env_overrides()

    allowed = robots_checker(CONFIG["base_url"])

    if args.temukan:
        if not allowed(CONFIG["base_url"] + "/"):
            sys.exit("robots.txt melarang membuka halaman utama.")
        driver = make_driver(args.visible)
        try:
            rows = temukan_kategori(driver, CONFIG["induk_kategori"])
        finally:
            driver.quit()
        if not rows:
            sys.exit(1)
        path = simpan_manifest(rows)
        per_kel: dict = {}
        for r in rows:
            per_kel[r["kelompok"]] = per_kel.get(r["kelompok"], 0) + 1
        log(f"\n{len(set(r['category_id'] for r in rows))} subkategori tersimpan di {path}")
        for k, n in per_kel.items():
            log(f"  - {k}: {n}")
        log("Buka file itu, ubah kolom 'aktif' menjadi 0 untuk yang tidak perlu, lalu jalankan:  python Inaproc.py")
        return

    pindah_file_lama()
    jobs = susun_pekerjaan(args)
    if not jobs:
        sys.exit("Belum ada daftar subkategori. Jalankan dulu:  python Inaproc.py --temukan --visible")
    if not KATEGORI_CSV.exists():
        log("[info] output/kategori_inaproc.csv belum ada - hanya URL dari .env yang diambil. "
            "Jalankan --temukan untuk seluruh Peralatan Elektronik.")
    if args.detail:
        driver = make_driver(args.visible)
        try:
            lengkapi_detail(driver, jobs, allowed, args.maks_detail, args.detail_ulang)
        finally:
            driver.quit()
        return
    if args.lanjutkan:
        sisa = [j for j in jobs if not sudah_ada(j[0])]
        log(f"[lanjutkan] {len(jobs) - len(sisa)} subkategori dilewati (file sudah ada)")
        jobs = sisa
    if not jobs:
        sys.exit("Semua subkategori sudah ada. Hapus --lanjutkan untuk mengambil ulang.")
    log(f"{len(jobs)} subkategori akan diambil.")

    driver = make_driver(args.visible)
    semua: dict = {}
    ringkasan: dict = {}
    try:
        for i, (label, kel, url) in enumerate(jobs, 1):
            log(f"\n=== {i}/{len(jobs)}  {kel or '-'} > {label}")
            batch: dict = {}
            raw: list = []
            try:
                crawl_category(driver, label, url, allowed, batch, args.max_rounds, raw, kel)
            except Exception as exc:  # noqa: BLE001
                log(f"  [!] gagal pada '{label}': {exc.__class__.__name__}: {str(exc)[:120]} - browser dimulai ulang")
                try:
                    driver.quit()
                except Exception:  # noqa: BLE001
                    pass
                driver = make_driver(args.visible)
            if batch:
                save_all(batch)           # simpan per subkategori: kalau berhenti di tengah, hasil aman
                semua.update(batch)
            elif raw:
                INSPECT_DIR.mkdir(parents=True, exist_ok=True)
                (INSPECT_DIR / f"raw_{slugify(label)}.json").write_text(
                    json.dumps(raw[:30], ensure_ascii=False), encoding="utf-8")
            ringkasan[label] = len(batch)
    finally:
        driver.quit()

    log(f"\nSelesai. Produk baru/terbarui: {len(semua)}")
    for label, n in ringkasan.items():
        log(f"  {label}: {n}{'   <-- 0, periksa' if n == 0 else ''}")
    log(f"CSV: {CSV_PATH}")
    kosong = [k for k, n in ringkasan.items() if n == 0]
    if kosong:
        log(f"{len(kosong)} subkategori kosong (mungkin memang tidak ada produk). "
            "Detail respons ada di output/inspect/raw_<nama>.json bila perlu diperiksa.")


if __name__ == "__main__":
    main()