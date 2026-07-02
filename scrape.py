import asyncio
import json
import re
import os
import pandas as pd
from twscrape import API, gather
from transformers import pipeline

# ── Konfigurasi ──────────────────────────────────────────────
AUTH_TOKEN = "968c93d28e17989053561806825a189dbd5c626c"
CT0        = "510f8665689d9b840303b04670e6f5c64b642388245d5a43d23c230400c32169b36eff87ba1cd7dd1452e0896202fe6e7c753629a2d50bb86205b801b35c1018ad90cce107803eebb6396d5fa8919ddd"

KEYWORDS = [
    "Gresik",
    "Kabupaten Gresik",
    "Kota Gresik",
    "Gresik Jawa Timur",
]

JUMLAH_TWEET = 50   # per keyword, total bisa sampai 200

os.makedirs("output", exist_ok=True)

# ── Model sentimen IndoBERT ───────────────────────────────────
print("Memuat model sentimen IndoBERT...")
sentimen_model = pipeline(
    "text-classification",
    model="mdhugol/indonesia-bert-sentiment-classification"
)
LABEL_MAP = {"LABEL_0": "positif", "LABEL_1": "netral", "LABEL_2": "negatif"}

# ── Fungsi cleaning ───────────────────────────────────────────
def bersihkan_tweet(teks):
    teks = re.sub(r"http\S+", "", teks)
    teks = re.sub(r"@\w+", "", teks)
    teks = re.sub(r"#(\w+)", r"\1", teks)
    teks = re.sub(r"[^\w\s]", "", teks)
    return re.sub(r"\s+", " ", teks).strip().lower()

# ── Fungsi sentimen ───────────────────────────────────────────
def cek_sentimen(teks):
    if not teks or len(teks) < 5:
        return "netral", 0.0
    h = sentimen_model(teks[:512])[0]
    return LABEL_MAP.get(h["label"], "netral"), round(h["score"], 3)

# ── Fungsi kategorisasi topik otomatis ───────────────────────
def deteksi_topik(teks):
    teks = teks.lower()
    if any(k in teks for k in ["banjir", "longsor", "gempa", "bencana", "rob"]):
        return "bencana"
    if any(k in teks for k in ["pabrik", "industri", "petrokimia", "semen", "pupuk"]):
        return "industri"
    if any(k in teks for k in ["kuliner", "makanan", "nasi", "soto", "bandeng", "otak-otak"]):
        return "kuliner"
    if any(k in teks for k in ["wisata", "pantai", "religi", "sunan giri", "ziarah"]):
        return "wisata"
    if any(k in teks for k in ["pemda", "bupati", "pemkab", "pemerintah", "apbd", "dinas"]):
        return "pemerintahan"
    if any(k in teks for k in ["persegres", "sepak bola", "bola", "liga"]):
        return "olahraga"
    if any(k in teks for k in ["macet", "jalan", "tol", "infrastruktur", "proyek"]):
        return "infrastruktur"
    return "umum"

# ── Main scraping + analisis ──────────────────────────────────
async def main():
    api = API()
    await api.pool.add_account_cookies(
        "akun_gresik",
        f"auth_token={AUTH_TOKEN}; ct0={CT0}"
    )

    semua_data = []
    id_sudah   = set()   # hindari duplikat antar keyword

    for keyword in KEYWORDS:
        print(f"\n🔍 Scraping: '{keyword}' (target {JUMLAH_TWEET} tweet)...")
        tweets = await gather(
            api.search(f"{keyword} lang:id", limit=JUMLAH_TWEET)
        )

        for t in tweets:
            if t.id in id_sudah:
                continue
            id_sudah.add(t.id)

            teks_bersih          = bersihkan_tweet(t.rawContent)
            label, skor          = cek_sentimen(teks_bersih)
            topik                = deteksi_topik(t.rawContent)

            semua_data.append({
                "id"          : t.id,
                "username"    : t.user.username,
                "teks_asli"   : t.rawContent,
                "teks_bersih" : teks_bersih,
                "sentimen"    : label,
                "skor"        : skor,
                "topik"       : topik,
                "likes"       : t.likeCount,
                "retweets"    : t.retweetCount,
                "tanggal"     : str(t.date)[:10],
                "keyword"     : keyword,
            })

        print(f"  Terkumpul unik: {len(semua_data)} tweet")

    # ── Simpan hasil ──────────────────────────────────────────
    df = pd.DataFrame(semua_data)
    df.to_csv("output/gresik_sentimen.csv", index=False, encoding="utf-8-sig")

    with open("output/gresik_tweets.json", "w", encoding="utf-8") as f:
        json.dump(semua_data, f, ensure_ascii=False, indent=2)

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