import asyncio
import json
import re
import os
import pandas as pd
from twscrape import API, gather
from transformers import pipeline
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from datetime import datetime, timedelta

# ── Konfigurasi ──────────────────────────────────────────────
# Ambil dari Environment Variable terlebih dahulu
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
CT0 = os.getenv("CT0")
AUTH_TOKEN_2 = os.getenv("AUTH_TOKEN_2")
CT0_2 = os.getenv("CT0_2")

# Jika dijalankan di localhost dan env belum ada,
# gunakan token yang Anda isi sendiri.
if not AUTH_TOKEN:
    AUTH_TOKEN = "968c93d28e17989053561806825a189dbd5c626c"

if not CT0:
    CT0 = "510f8665689d9b840303b04670e6f5c64b642388245d5a43d23c230400c32169b36eff87ba1cd7dd1452e0896202fe6e7c753629a2d50bb86205b801b35c1018ad90cce107803eebb6396d5fa8919ddd"

if not AUTH_TOKEN_2:
    AUTH_TOKEN_2 = "27f954988a150a6b096587c08a085cb37077b620"

if not CT0_2:
    CT0_2 = "8e8f35fe50397d06a1b8a08bf37568766fc5895bbfdd2ea0e62b4431b7b72e5ee37097329557df87785ffc73c686695ee92b8d0234beb3087a6ce8db6c394ee4e6c5ec04dd46f79d6021a4006ac3cd7a"

if not AUTH_TOKEN or not CT0:
    raise ValueError("AUTH_TOKEN atau CT0 belum diatur.")
KEYWORDS = [
    # ==========================
    # 1. Keyword Utama
    # ==========================
    "Gresik",
    "Kabupaten Gresik",
    "Pemkab Gresik",
    "Gresik Kota",
    "Gresik Jawa Timur",

    # ==========================
    # 2. Pemerintahan
    # ==========================
    "Bupati Gresik",
    "Wakil Bupati Gresik",
    "Pemkab Gresik",
    "Setda Gresik",
    "DPRD Gresik",
    "Diskominfo Gresik",
    "Dispendik Gresik",
    "Dinas Kesehatan Gresik",
    "Dinas PU Gresik",
    "BPBD Gresik",
    "Satpol PP Gresik",
    "Polres Gresik",
    "Kodim Gresik",
    "KPU Gresik",
    "Bawaslu Gresik",

    # ==========================
    # 3. Infrastruktur
    # ==========================
    "jalan Gresik",
    "jembatan Gresik",
    "macet Gresik",
    "banjir Gresik",
    "drainase Gresik",
    "perbaikan jalan Gresik",
    "lampu jalan Gresik",
    "trotoar Gresik",
    "pelabuhan Gresik",
    "terminal Gresik",

    # ==========================
    # 4. Pendidikan
    # ==========================
    "sekolah Gresik",
    "SMP Gresik",
    "SMA Gresik",
    "Universitas Gresik",
    "beasiswa Gresik",
    "PPDB Gresik",

    # ==========================
    # 5. Kesehatan
    # ==========================
    "RSUD Ibnu Sina Gresik",
    "rumah sakit Gresik",
    "Puskesmas Gresik",
    "DBD Gresik",
    "Covid Gresik",
    "stunting Gresik",
    "BPJS Gresik",

    # ==========================
    # 6. Keamanan
    # ==========================
    "kecelakaan Gresik",
    "kriminal Gresik",
    "pencurian Gresik",
    "kebakaran Gresik",
    "longsor Gresik",
    "gempa Gresik",

    # ==========================
    # 7. Ekonomi
    # ==========================
    "UMKM Gresik",
    "pasar Gresik",
    "investasi Gresik",
    "harga beras Gresik",
    "harga cabai Gresik",
    "nelayan Gresik",
    "tambak Gresik",

    # ==========================
    # 8. Industri
    # ==========================
    "Petrokimia Gresik",
    "Semen Indonesia",
    "Freeport Gresik",
    "JIIPE",
    "KIG Gresik",
    "industri Gresik",
    "pabrik Gresik",

    # ==========================
    # 9. Wisata
    # ==========================
    "Wisata Gresik",
    "Makam Sunan Giri",
    "Makam Maulana Malik Ibrahim",
    "Pantai Delegan",
    "Bukit Jamur",
    "Setigi",

    # ==========================
    # 10. Olahraga
    # ==========================
    "Persegres",
    "stadion Gresik",
    "PORPROV Gresik",

    # ==========================
    # 11. Budaya
    # ==========================
    "Hari Jadi Gresik",
    "Dandangan Gresik",
    "Tradisi Gresik",
    "Haul Sunan Giri",

    # ==========================
    # 12. Kecamatan
    # ==========================
    "Manyar Gresik",
    "Kebomas Gresik",
    "Driyorejo Gresik",
    "Menganti Gresik",
    "Cerme Gresik",
    "Benjeng Gresik",
    "Balongpanggang Gresik",
    "Duduksampeyan Gresik",
    "Sidayu Gresik",
    "Ujungpangkah Gresik",
    "Panceng Gresik",
    "Bungah Gresik",
    "Sangkapura Gresik",
    "Tambak Gresik",
    "Wringinanom Gresik",
    "Kedamean Gresik",

    # ==========================
    # 14. Bencana
    # ==========================
    "banjir Gresik",
    "rob Gresik",
    "angin kencang Gresik",
    "kebakaran Gresik",
    "gempa Gresik",

    # ==========================
    # 15. Pelayanan Publik
    # ==========================
    "PDAM Gresik",
    "PLN Gresik",
    "Disdukcapil Gresik",
    "SIM Gresik",
    "Samsat Gresik",
]

JUMLAH_TWEET = 50

os.makedirs("output", exist_ok=True)

# ── Model sentimen IndoBERT ───────────────────────────────────
print("Memuat model sentimen IndoBERT...")
sentimen_model = pipeline(
    "text-classification",
    model="mdhugol/indonesia-bert-sentiment-classification"
)
LABEL_MAP = {"LABEL_0": "positif", "LABEL_1": "netral", "LABEL_2": "negatif"}
# ============================
# Stopword & Stemmer
# ============================

stop_factory = StopWordRemoverFactory()
stopwords = set(stop_factory.get_stop_words())

stem_factory = StemmerFactory()
stemmer = stem_factory.create_stemmer()

NORMALISASI = {
    "gk":"tidak",
    "ga":"tidak",
    "nggak":"tidak",
    "tdk":"tidak",
    "yg":"yang",
    "dr":"dari",
    "dgn":"dengan",
    "utk":"untuk",
    "aja":"saja",
    "bgt":"banget",
    "krn":"karena",
    "tp":"tapi",
    "udh":"sudah",
    "blm":"belum",
    "sm":"sama",
}
# ── Fungsi cleaning ───────────────────────────────────────────
def bersihkan_tweet(teks):
    teks = re.sub(r"http\S+", "", teks)
    teks = re.sub(r"@\w+", "", teks)
    teks = re.sub(r"#(\w+)", r"\1", teks)
    teks = re.sub(r"[^\w\s]", "", teks)
    return re.sub(r"\s+", " ", teks).strip().lower()

def preprocessing(teks):
    # Normalisasi
    kata = []
    for w in teks.split():
        kata.append(NORMALISASI.get(w, w))

    # Stopword
    kata = [w for w in kata if w not in stopwords]

    # Stemming
    kata = [stemmer.stem(w) for w in kata]

    return " ".join(kata)

# ── Fungsi sentimen ───────────────────────────────────────────
def cek_sentimen(teks):
    if not teks or len(teks) < 5:
        return "netral", 0.0
    h = sentimen_model(teks[:512])[0]
    return LABEL_MAP.get(h["label"], "netral"), round(h["score"], 3)

# ── Fungsi kategorisasi topik otomatis ───────────────────────
def deteksi_topik(teks):
    teks = teks.lower()

    kategori = {
        "bencana": [
            "banjir","rob","gempa","longsor","angin",
            "kebakaran","bencana"
        ],

        "pemerintahan":[
            "bupati","wakil bupati","pemkab",
            "dprd","diskominfo","dinas",
            "setda","apbd","perda"
        ],

        "infrastruktur":[
            "jalan","jembatan","trotoar",
            "drainase","lampu jalan",
            "terminal","pelabuhan",
            "macet","tol"
        ],

        "kesehatan":[
            "rsud","rumah sakit","puskesmas",
            "bpjs","stunting","dbd","covid"
        ],

        "pendidikan":[
            "sekolah","kampus","universitas",
            "ppdb","beasiswa","smp","sma"
        ],

        "ekonomi":[
            "pasar","umkm","harga",
            "cabai","beras","investasi"
        ],

        "industri":[
            "petrokimia","freeport",
            "jiipe","semen",
            "pabrik","industri"
        ],

        "wisata":[
            "pantai","wisata",
            "setigi","bukit jamur",
            "sunan giri","ziarah"
        ],

        "olahraga":[
            "persegres","liga",
            "stadion","bola"
        ]
    }

    for nama, daftar in kategori.items():
        if any(k in teks for k in daftar):
            return nama

    return "umum"

async def safe_search(api, query, limit):
    for i in range(3):  # retry 3x kalau kena limit
        try:
            return await gather(api.search(query, limit=limit))
        except Exception as e:
            print(f"⚠️ Retry {i+1} karena: {e}")
            await asyncio.sleep(30)
    return []


# ── Main scraping + analisis ──────────────────────────────────
async def main():
    api = API()
    

# Akun pertama
    await api.pool.add_account_cookies(
        "akun_gresik_1",
        f"auth_token={AUTH_TOKEN}; ct0={CT0}"
    )

    # Akun kedua
    await api.pool.add_account_cookies(
        "akun_gresik_2",
        f"auth_token={AUTH_TOKEN_2}; ct0={CT0_2}"
    )
    
    semua_data = []
    id_sudah = set()

    for keyword in KEYWORDS:
        print(f"\n🔍 Scraping: '{keyword}' (target {JUMLAH_TWEET} tweet)...")
        hari_ini = datetime.now()
        tujuh_hari_lalu = hari_ini - timedelta(days=7)

        query = (
            f'"{keyword}" '
            f'since:{tujuh_hari_lalu.strftime("%Y-%m-%d")} '
            f'until:{(hari_ini + timedelta(days=1)).strftime("%Y-%m-%d")}'
        )

        print(query)

        tweets = await safe_search(
            api,
            query,
            20
        )

        print("Ditemukan:", len(tweets))
        for t in tweets:
            if t.id in id_sudah:
                continue
            id_sudah.add(t.id)

            teks_bersih = bersihkan_tweet(t.rawContent)
            teks_prepro = preprocessing(teks_bersih)
            label, skor = cek_sentimen(teks_prepro)
            topik       = deteksi_topik(t.rawContent)

            semua_data.append({
                "id"          : t.id,
                "username"    : t.user.username,
                "teks_asli"   : t.rawContent,
                "teks_bersih" : teks_bersih,
                "sentimen"    : label,
                "skor"        : skor,
                "topik"       : topik,
                "likes"       : t.likeCount,
                "replies"     : t.replyCount,
                "retweets"    : t.retweetCount,
                "tanggal"     : str(t.date)[:10],
                "keyword"     : keyword,
                "teks_preprocessing": teks_prepro,
            })

        print(f"  Terkumpul unik: {len(semua_data)} tweet")
        await asyncio.sleep(20)

    # ── Simpan hasil ──────────────────────────────────────────

    if not semua_data:
        print("Tidak ada tweet yang berhasil diambil.")
        return

    df_baru = pd.DataFrame(semua_data)

    csv_path = "output/gresik_sentimen.csv"
    json_path = "output/gresik_tweets.json"

    # ===========================
    # CSV
    # ===========================
    if os.path.exists(csv_path):
        df_lama = pd.read_csv(csv_path)

        # Gabungkan data lama dan baru
        df = pd.concat([df_lama, df_baru], ignore_index=True)

        # Hilangkan tweet yang sama berdasarkan id
        df = df.drop_duplicates(subset="id", keep="last")
    else:
        df = df_baru

    # Simpan kembali
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # ===========================
    # JSON
    # ===========================
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                data_lama = json.load(f)
            except:
                data_lama = []
    else:
        data_lama = []

    # Gabungkan
    data_baru = data_lama + semua_data

    # Hapus duplikat berdasarkan id
    unik = {}
    for item in data_baru:
        unik[item["id"]] = item

    data_baru = list(unik.values())

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            data_baru,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"Total tweet tersimpan : {len(df)}")

    # ── Ringkasan di terminal ─────────────────────────────────
    total = len(df)
    print(f"\n{'='*45}")
    print(f"  HASIL ANALISIS SENTIMEN — GRESIK")
    print(f"{'='*45}")
    print(f"  Total tweet unik : {total}")

    print(f"\n  Sentimen:")
    for label, jml in df["sentimen"].value_counts().items():
        bar = "█" * int(jml / total * 30)
        print(f"  {label:10s} {jml:4d} ({jml/total*100:5.1f}%)  {bar}")

    print(f"\n  Topik terpopuler:")
    for topik, jml in df["topik"].value_counts().head(5).items():
        print(f"  {topik:15s} {jml:4d} tweet")

    print(f"\n  Tweet paling banyak di-like:")
    top3 = df.nlargest(3, "likes")[["username", "likes", "sentimen", "teks_asli"]]
    for _, r in top3.iterrows():
        print(f"  @{r['username']} ({r['likes']} likes) [{r['sentimen']}]")
        print(f"  → {r['teks_asli'][:80]}...")

    print(f"\n  File disimpan:")
    print(f"  output/gresik_sentimen.csv")
    print(f"  output/gresik_tweets.json")

asyncio.run(main())