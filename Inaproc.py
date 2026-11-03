"""Inaproc.py - ambil produk TI (Laptop/PC/Server) dari katalog.inaproc.id ke folder output/.

Jalankan:  python Inaproc.py            (semua kategori di .env)
           python Inaproc.py --category Server --visible
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse


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
    "Toshiba", "Zyrex", "Itech", "Libera", "Evercoss", "Cisco",
    "Intel", "Synology", "QNAP", "Oracle", "Hikvision",
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
    return re.search(pattern, text, flags)


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

    m = _first(r"(\d{1,4})\s*GB\s*(?:RAM|DDR\d?|LPDDR\d?)", blob) or _first(
        r"RAM\D{0,15}(\d{1,4})\s*GB", blob
    )
    if not m:
        m = _first(r"[,\(\|]\s*(\d{1,3})\s*GB\s*[,\)\|]", blob)
    if m:
        out["ram_gb"] = int(m.group(1))

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


# =====================================================================================
#  SCRAPER: rekam respons JSON yang dimuat halaman (Selenium + Chrome DevTools)
#  Semua kategori di .env diproses otomatis; hasil ke folder  output/
# =====================================================================================
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
INSPECT_DIR = OUTPUT_DIR / "inspect"
CSV_PATH = OUTPUT_DIR / "data_inaproc.csv"

USER_AGENT = "ProcurementResearchBot/1.0 (riset harga publik)"

CONFIG = {
    "base_url": "https://katalog.inaproc.id",
    "delay_seconds": (2.0, 3.5),
    "max_rounds": 60,            # batas pengaman: berapa kali gulir/klik "berikutnya" per kategori
    "categories": {"Laptop": [], "PC": [], "Server": []},   # diisi dari .env
}

CSV_COLUMNS = ["category", "brand", "name", "price_idr", "provider_name", "cpu", "ram_gb",
               "storage_gb", "storage_type", "screen_inch", "os", "tkdn_pct",
               "warranty_years", "url"]


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
    for cat, key in (("Laptop", "INAPROC_URL_LAPTOP"), ("PC", "INAPROC_URL_PC"),
                     ("Server", "INAPROC_URL_SERVER")):
        val = os.environ.get(key, "").strip()
        CONFIG["categories"][cat] = [u.strip() for u in val.split("|") if u.strip()]


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


REQS: dict = {}
_SKIP_HDR = {"host", "content-length", "user-agent", "cookie", "referer", "origin",
             "connection", "accept-encoding"}


def harvest(driver, seen_keys: set) -> list[dict]:
    """Ambil respons JSON (XHR/fetch) baru + detail request-nya sejak panggilan terakhir."""
    out = []
    for entry in driver.get_log("performance"):
        try:
            msg = json.loads(entry["message"])["message"]
        except (KeyError, ValueError):
            continue
        method = msg.get("method")
        params = msg.get("params", {})

        if method == "Network.requestWillBeSent":
            rq = params.get("request", {})
            hdrs = {k: v for k, v in (rq.get("headers") or {}).items()
                    if k.lower() not in _SKIP_HDR and not k.startswith(":")
                    and not k.lower().startswith("sec-")}
            post = rq.get("postData")
            if post is None and rq.get("hasPostData"):
                try:
                    post = driver.execute_cdp_cmd(
                        "Network.getRequestPostData",
                        {"requestId": params.get("requestId")}).get("postData")
                except Exception:  # noqa: BLE001
                    post = None
            REQS[params.get("requestId")] = {
                "url": rq.get("url"), "method": rq.get("method", "GET"),
                "postData": post, "headers": hdrs}
            continue

        if method != "Network.responseReceived":
            continue
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
        out.append({"url": resp.get("url"), "status": resp.get("status"), "data": data,
                    "req": REQS.get(params["requestId"])})
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


def build_record(item: dict, label: str, base_url: str, source_url: str) -> dict | None:
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
    sku = pick(flat, SKU_KEYS)
    desc = pick(flat, DESC_KEYS)
    return {
        "url": url,
        "name": name,
        "brand": detect_brand(name, str(brand) if brand else None),
        "category": label,
        "price_idr": price,
        "provider_name": str(provider).strip() if provider else None,
        "provider_slug": str(provider_slug) if provider_slug else None,
        "product_slug": str(slug) if slug else None,
        "sku": str(sku) if sku else None,
        "description": str(desc)[:4000] if desc else None,
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


def ingest(captures: list[dict], label: str, source_url: str, records: dict, endpoints: dict) -> int:
    """Cari daftar produk di respons JSON; tambahkan ke records. Kembalikan jumlah produk baru."""
    added = 0
    for cap in captures:
        for lst in find_dict_lists(cap["data"]):
            recs = [r for r in (build_record(i, label, CONFIG["base_url"], source_url) for i in lst) if r]
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
_LOWER = "translate({0},'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
NEXT_XPATHS = [
    "//*[self::button or self::a][not(@disabled) and not(@aria-disabled='true')]"
    "[contains(" + _LOWER.format("@aria-label") + ",'next') or contains(" + _LOWER.format("@aria-label") + ",'berikutnya') "
    "or contains(" + _LOWER.format("@title") + ",'next') or @rel='next']",
    "//*[self::button or self::a][not(@disabled) and not(@aria-disabled='true')]"
    "[contains(normalize-space(.),'Selanjutnya') or contains(normalize-space(.),'Berikutnya') "
    "or contains(normalize-space(.),'Muat') or contains(normalize-space(.),'Lihat Lebih') "
    "or normalize-space(.)='›' or normalize-space(.)='»' or normalize-space(.)='>']",
    "//li[contains(@class,'active') or contains(@class,'selected')]"
    "/following-sibling::li[1]//*[self::a or self::button]",
]


def scroll_everything(driver) -> None:
    driver.execute_script("""
        window.scrollTo(0, document.body.scrollHeight);
        document.querySelectorAll('*').forEach(e => {
            if (e.scrollHeight > e.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(e).overflowY))
                e.scrollTop = e.scrollHeight;
        });
    """)
    time.sleep(1.5)


def click_next(driver) -> bool:
    from selenium.webdriver.common.by import By
    for xp in NEXT_XPATHS:
        for el in driver.find_elements(By.XPATH, xp):
            try:
                if el.is_displayed() and el.is_enabled():
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});arguments[0].click();", el)
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


# ------------------------------------------------------------------ replay API (semua halaman)
PAGE_KEYS = ["page", "pageNumber", "page_number", "pageNo", "pageIndex", "currentPage",
             "pageNum", "pageNr", "p", "halaman"]
OFFSET_KEYS = ["offset", "start", "skip", "from"]
SIZE_KEYS = ["limit", "size", "per_page", "perPage", "perpage", "pageSize", "page_size",
             "length", "take", "rows", "first"]
CURSOR_KEYS = ["after", "cursor", "nextCursor", "endCursor"]


def extract_records(data, label: str, source_url: str) -> list[dict]:
    best: list[dict] = []
    for lst in find_dict_lists(data):
        recs = [r for r in (build_record(i, label, CONFIG["base_url"], source_url) for i in lst) if r]
        if recs and len(recs) / len(lst) >= 0.5 and len(recs) > len(best):
            best = recs
    return best


def best_product_capture(captures: list[dict], label: str, source_url: str):
    best, best_n = None, 0
    for cap in captures:
        if not cap.get("req"):
            continue
        n = len(extract_records(cap["data"], label, source_url))
        if n > best_n:
            best, best_n = cap, n
    return best


def _find_key(d, names, depth: int = 0):
    """Cari kunci (abaikan huruf besar/kecil, _ dan -) di dict/list bersarang."""
    want = {_norm(n) for n in names}
    if depth > 6:
        return None, None
    if isinstance(d, dict):
        for k, v in d.items():
            if _norm(k) in want and not isinstance(v, (dict, list)):
                return d, k
        for v in d.values():
            c, k = _find_key(v, names, depth + 1)
            if k:
                return c, k
    elif isinstance(d, list):
        for v in d[:5]:
            c, k = _find_key(v, names, depth + 1)
            if k:
                return c, k
    return None, None


def _find_val(d, names, depth: int = 0):
    want = {_norm(n) for n in names}
    if depth > 8:
        return None
    if isinstance(d, dict):
        for k, v in d.items():
            if _norm(k) in want and not isinstance(v, (dict, list)):
                return v
        for v in d.values():
            r = _find_val(v, names, depth + 1)
            if r is not None:
                return r
    elif isinstance(d, list):
        for v in d[:5]:
            r = _find_val(v, names, depth + 1)
            if r is not None:
                return r
    return None


def fetch_json(driver, url: str, method: str, body, headers: dict):
    driver.set_script_timeout(40)
    js = ("const [url,method,body,headers,done]=arguments;"
          "fetch(url,{method:method,headers:headers,body:body,credentials:'include'})"
          ".then(r=>r.text()).then(t=>done(t)).catch(e=>done('ERR:'+e));")
    txt = driver.execute_async_script(js, url, method, body, headers)
    try:
        return json.loads(txt)
    except (TypeError, ValueError):
        return None


def paginate_api(driver, cap: dict, label: str, source_url: str, records: dict,
                 max_pages: int = 1000) -> int:
    """Putar ulang endpoint produk (page / offset / cursor) sampai data habis."""
    req = cap["req"]
    u = urlparse(req["url"])
    method = (req.get("method") or "GET").upper()
    headers = dict(req.get("headers") or {})
    body = None
    if method != "GET":
        try:
            body = json.loads(req.get("postData") or "")
        except ValueError:
            log("  [api] body POST kosong/bukan JSON, lewati replay API")
            return 0
        headers.setdefault("Content-Type", "application/json")
    query = dict(parse_qsl(u.query, keep_blank_values=True))
    store = body if body is not None else query

    pc, pk = _find_key(store, PAGE_KEYS)
    oc, ok = _find_key(store, OFFSET_KEYS)
    sc, sk = _find_key(store, SIZE_KEYS)
    ac, ak = _find_key(store, CURSOR_KEYS)
    if not (pk or ok or ak):
        log(f"  [api] parameter paginasi tidak ditemukan di {u.path}. Isi request:")
        log("  " + json.dumps(store, ensure_ascii=False)[:1200])
        return 0
    log(f"  [api] mode: {'page' if pk else 'offset' if ok else 'cursor'} "
        f"(kunci: {pk or ok or ak}, ukuran: {sk})")

    def call():
        url = urlunparse(u._replace(query=urlencode(query)))
        payload = json.dumps(body) if body is not None else None
        return fetch_json(driver, url, method, payload, headers)

    first_len = len(extract_records(cap["data"], label, source_url)) or 20
    size = int(sc[sk]) if sk and str(sc[sk]).isdigit() else first_len
    page0 = int(pc[pk]) if pk and str(pc[pk]).lstrip("-").isdigit() else 1

    def set_pos(n: int) -> None:
        if pk:
            pc[pk] = str(page0 + n) if isinstance(pc[pk], str) else page0 + n
        if ok:
            oc[ok] = str(n * size) if isinstance(oc[ok], str) else n * size

    # coba perbesar ukuran halaman (kalau server mengizinkan)
    if sk:
        original = sc[sk]
        for trial in (200, 100):
            sc[sk] = str(trial) if isinstance(original, str) else trial
            if not ak:
                set_pos(0)
            data = call()
            n = len(extract_records(data, label, source_url)) if data is not None else 0
            if n > size:
                size = min(n, trial)
                log(f"  [api] ukuran halaman dinaikkan -> {trial}")
                break
        else:
            sc[sk] = original

    added, stale = 0, 0
    for n in range(max_pages):
        if not ak:
            set_pos(n)
        data = call()
        recs = extract_records(data, label, source_url) if data is not None else []
        new = 0
        for r in recs:
            if r["url"] not in records:
                records[r["url"]] = r
                new += 1
        added += new
        log(f"  [api] halaman {n + 1}: {len(recs)} item, +{new} baru (total {added})")
        if not recs:
            break
        stale = 0 if new else stale + 1
        if stale >= 2:
            break
        if ak:   # mode cursor
            nxt = _find_val(data, ["endCursor", "nextCursor", "cursor"])
            has_next = _find_val(data, ["hasNextPage", "hasMore"])
            if not nxt or has_next is False:
                break
            ac[ak] = nxt
        time.sleep(random.uniform(0.8, 1.6))
    return added


# ------------------------------------------------------------------ crawl per kategori
def crawl_category(driver, label: str, url: str, allowed, records: dict, max_rounds: int, raw: list) -> int:
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
    total = ingest(captures, label, url, records, endpoints)
    api_done = False
    stale = 0
    for rnd in range(0, max_rounds + 1):
        if rnd > 0:
            scroll_everything(driver)
            clicked = click_next(driver)
            polite_sleep()
            captures = harvest(driver, seen_keys)
            raw.extend(captures)
            added = ingest(captures, label, url, records, endpoints)
            total += added
            log(f"  putaran {rnd}: +{added} produk (total {total}){' [klik berikutnya]' if clicked else ''}")
            stale = 0 if added else stale + 1
        # begitu endpoint produk terdeteksi -> ambil SEMUA halaman lewat API
        if not api_done:
            cap = best_product_capture(captures, label, url)
            if cap:
                api_done = True
                got = paginate_api(driver, cap, label, url, records)
                total += got
                if got:
                    break
        if stale >= 4:
            break
    for ep, n in endpoints.items():
        log(f"  sumber data: {ep} ({n} item)")
    if total == 0:
        describe_captures(raw)
    return total


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


def save_all(records: dict) -> tuple[int, Path]:
    """Simpan ke output/data_inaproc.csv (UTF-8 BOM, rapi di Excel). Hanya CSV."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged = load_existing()
    for r in records.values():
        merged[r["url"]] = record_to_row(r)

    def write(path: Path) -> None:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            w.writeheader()
            w.writerows(merged.values())

    try:
        write(CSV_PATH)
        return len(merged), CSV_PATH
    except PermissionError:       # di Windows: file sedang terbuka di Excel
        alt = OUTPUT_DIR / f"data_inaproc_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        write(alt)
        log(f"[!] {CSV_PATH.name} sedang terbuka di program lain (mis. Excel); hasil disimpan ke {alt.name}")
        return len(merged), alt


def main() -> None:
    ap = argparse.ArgumentParser(description="Ambil produk TI dari katalog.inaproc.id -> folder output/")
    ap.add_argument("--category", nargs="*", help="Laptop PC Server (default: semuanya)")
    ap.add_argument("--url", help="URL kategori tambahan/sementara (gunakan bersama --label)")
    ap.add_argument("--label", default="Lainnya", help="nama kategori untuk --url")
    ap.add_argument("--max-rounds", type=int, default=CONFIG["max_rounds"])
    ap.add_argument("--visible", action="store_true", help="tampilkan jendela Chrome (untuk memantau)")
    args = ap.parse_args()
    apply_env_overrides()

    jobs: list[tuple[str, str]] = []
    if args.url:
        jobs.append((args.label, args.url))
    else:
        for cat in args.category or list(CONFIG["categories"]):
            urls = CONFIG["categories"].get(cat, [])
            if not urls:
                log(f"[{cat}] dilewati: INAPROC_URL_{cat.upper()} belum diisi di .env")
            jobs += [(cat, u) for u in urls]
    if not jobs:
        sys.exit("Tidak ada URL kategori. Isi INAPROC_URL_LAPTOP / _PC / _SERVER di .env.")

    allowed = robots_checker(CONFIG["base_url"])
    driver = make_driver(args.visible)
    records: dict = {}
    raw: list = []
    try:
        for label, url in jobs:
            crawl_category(driver, label, url, allowed, records, args.max_rounds, raw)
    finally:
        driver.quit()

    n, out_path = save_all(records)
    by_cat: dict = {}
    for r in records.values():
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    log(f"\nSelesai. Baru pada putaran ini: {len(records)} {by_cat}. Total di file: {n}")
    log(f"CSV: {out_path}")
    if not records:      # file mentah hanya disimpan bila perlu diagnosis
        INSPECT_DIR.mkdir(parents=True, exist_ok=True)
        (INSPECT_DIR / "raw_responses.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        log("Tidak ada produk terdeteksi. Kirim output/inspect/raw_responses.json ke Claude.")


if __name__ == "__main__":
    main()