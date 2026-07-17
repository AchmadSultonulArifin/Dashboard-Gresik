# ============================================================
#  Facebook Scraper — All in One
#  Scraping → Cleaning → Analisis → Sentimen → Grafik → Laporan
#  Jalankan: python main.py
# ============================================================
#
#  Install dulu:
#  pip install facebook-scraper pandas openpyxl matplotlib seaborn textblob deep-translator
#
# ============================================================

import os
import re
import json
import time
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from facebook_scraper import get_posts

# ── Coba import opsional (sentimen) ──────────────────────────
try:
    from textblob import TextBlob
    from deep_translator import GoogleTranslator
    SENTIMEN_TERSEDIA = True
except ImportError:
    SENTIMEN_TERSEDIA = False
    print("[INFO] Library sentimen tidak ditemukan. Langkah sentimen dilewati.")
    print("       Jalankan: pip install textblob deep-translator\n")


# ============================================================
#  KONFIGURASI — ubah sesuai kebutuhan
# ============================================================

TARGET_PAGE     = "Gresik Media"   # nama halaman / page Facebook publik
JUMLAH_HALAMAN  = 3           # jumlah halaman yang di-scroll (1 hal ≈ 10 post)
GUNAKAN_LOGIN   = False       # True jika butuh login untuk akses lebih banyak data
EMAIL           = ""          # isi jika GUNAKAN_LOGIN = True
PASSWORD        = ""          # isi jika GUNAKAN_LOGIN = True
OUTPUT_FOLDER   = "output"      # folder penyimpanan hasil


# ============================================================
#  BAGIAN 1 — SCRAPING
# ============================================================

def scraping():
    print("=" * 55)
    print(" LANGKAH 1: SCRAPING DATA")
    print("=" * 55)
    print(f"Target  : {TARGET_PAGE}")
    print(f"Halaman : {JUMLAH_HALAMAN}\n")

    hasil = []

    try:
        opsi = {
            "pages": JUMLAH_HALAMAN,
            "extra_info": True,
            "timeout": 30,
        }
        if GUNAKAN_LOGIN and EMAIL and PASSWORD:
            opsi["credentials"] = (EMAIL, PASSWORD)
            print("[INFO] Login menggunakan akun Facebook...\n")

        for post in get_posts(TARGET_PAGE, **opsi):
            data_post = {
                "id"       : post.get("post_id", ""),
                "teks"     : post.get("text", ""),
                "waktu"    : str(post.get("time", "")),
                "likes"    : post.get("likes", 0) or 0,
                "komentar" : post.get("comments", 0) or 0,
                "shares"   : post.get("shares", 0) or 0,
                "link"     : post.get("post_url", ""),
            }
            hasil.append(data_post)
            cuplikan = str(data_post["teks"])[:60].replace("\n", " ")
            print(f"  [{len(hasil):02d}] {cuplikan}...")
            time.sleep(0.5)  # jeda kecil agar tidak kena rate limit

    except Exception as e:
        print(f"\n[ERROR] Scraping gagal: {e}")
        print("Tips: coba ganti TARGET_PAGE atau aktifkan GUNAKAN_LOGIN.\n")

    print(f"\n✓ Berhasil mengambil {len(hasil)} post dari '{TARGET_PAGE}'.")
    return hasil


# ============================================================
#  BAGIAN 2 — SIMPAN DATA MENTAH
# ============================================================

def simpan_mentah(data, folder):
    print("\n" + "=" * 55)
    print(" LANGKAH 2: SIMPAN DATA MENTAH")
    print("=" * 55)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    path_json = os.path.join(folder, f"mentah_{ts}.json")
    with open(path_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ JSON   → {path_json}")

    # CSV
    path_csv = os.path.join(folder, f"mentah_{ts}.csv")
    pd.DataFrame(data).to_csv(path_csv, index=False, encoding="utf-8-sig")
    print(f"  ✓ CSV    → {path_csv}")

    return path_csv


# ============================================================
#  BAGIAN 3 — CLEANING
# ============================================================

def cleaning(path_csv):
    print("\n" + "=" * 55)
    print(" LANGKAH 3: CLEANING DATA")
    print("=" * 55)

    df = pd.read_csv(path_csv)
    awal = len(df)

    # Hapus duplikat berdasarkan ID post
    df = df.drop_duplicates(subset=["id"])

    # Hapus baris tanpa teks
    df = df.dropna(subset=["teks"])
    df = df[df["teks"].str.strip() != ""]

    # Bersihkan teks: hapus karakter non-standar & spasi ganda
    def bersihkan(t):
        t = re.sub(r'[^\w\s.,!?()\-\'":/]', ' ', str(t))
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    df["teks_bersih"] = df["teks"].apply(bersihkan)

    # Konversi waktu
    df["waktu"] = pd.to_datetime(df["waktu"], errors="coerce")

    # Isi nilai kosong di kolom angka
    for kolom in ["likes", "komentar", "shares"]:
        df[kolom] = pd.to_numeric(df[kolom], errors="coerce").fillna(0).astype(int)

    print(f"  Sebelum cleaning : {awal} baris")
    print(f"  Setelah cleaning : {len(df)} baris")
    print(f"  Dihapus          : {awal - len(df)} baris")

    path_bersih = os.path.join(os.path.dirname(path_csv), "data_bersih.csv")
    df.to_csv(path_bersih, index=False, encoding="utf-8-sig")
    print(f"  ✓ Tersimpan → {path_bersih}")

    return df


# ============================================================
#  BAGIAN 4 — ANALISIS
# ============================================================

def analisis(df):
    print("\n" + "=" * 55)
    print(" LANGKAH 4: ANALISIS DATA")
    print("=" * 55)

    print(f"\n  Total post      : {len(df)}")
    print(f"  Total likes     : {df['likes'].sum():,}")
    print(f"  Rata-rata likes : {df['likes'].mean():.1f}")
    print(f"  Rata-rata komen : {df['komentar'].mean():.1f}")
    print(f"  Rata-rata share : {df['shares'].mean():.1f}")

    print("\n  --- Top 5 Post Paling Viral ---")
    top5 = df.sort_values("likes", ascending=False).head(5)
    for i, (_, row) in enumerate(top5.iterrows(), 1):
        cuplikan = str(row["teks"])[:70].replace("\n", " ")
        print(f"  {i}. Likes: {row['likes']:,} | {cuplikan}...")

    if df["waktu"].notna().any():
        df_valid = df.dropna(subset=["waktu"])
        df_valid = df_valid.copy()
        df_valid["hari"] = df_valid["waktu"].dt.day_name()
        df_valid["jam"]  = df_valid["waktu"].dt.hour
        hari_terbaik = df_valid.groupby("hari")["likes"].mean().idxmax()
        jam_terbaik  = df_valid.groupby("jam")["likes"].mean().idxmax()
        print(f"\n  Hari terbaik untuk posting : {hari_terbaik}")
        print(f"  Jam terbaik untuk posting  : {jam_terbaik:02d}:00")

    return df


# ============================================================
#  BAGIAN 5 — ANALISIS SENTIMEN (opsional)
# ============================================================

def sentimen(df):
    if not SENTIMEN_TERSEDIA:
        print("\n[SKIP] Langkah sentimen dilewati (library tidak tersedia).")
        df["sentimen"] = "netral"
        return df

    print("\n" + "=" * 55)
    print(" LANGKAH 5: ANALISIS SENTIMEN")
    print("=" * 55)
    print("  Menerjemahkan & menganalisis teks... (butuh waktu)\n")

    def cek_sentimen(teks):
        try:
            teks_en = GoogleTranslator(source="auto", target="en").translate(
                str(teks)[:400]
            )
            skor = TextBlob(teks_en).sentiment.polarity
            if skor > 0.1:
                return "positif"
            elif skor < -0.1:
                return "negatif"
            else:
                return "netral"
        except Exception:
            return "netral"

    df = df.copy()
    df["sentimen"] = df["teks_bersih"].apply(cek_sentimen)

    hasil_sentimen = df["sentimen"].value_counts()
    for label, jumlah in hasil_sentimen.items():
        pct = jumlah / len(df) * 100
        print(f"  {label.capitalize():10s}: {jumlah} post ({pct:.1f}%)")

    return df


# ============================================================
#  BAGIAN 6 — VISUALISASI GRAFIK
# ============================================================

def visualisasi(df, folder):
    print("\n" + "=" * 55)
    print(" LANGKAH 6: VISUALISASI GRAFIK")
    print("=" * 55)

    sns.set_theme(style="whitegrid", palette="muted")
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Analisis Data Facebook — @{TARGET_PAGE}", fontsize=15, y=1.01)

    # 1. Distribusi Likes
    axes[0, 0].hist(df["likes"], bins=20, color="#4A90D9", edgecolor="white")
    axes[0, 0].set_title("Distribusi Likes")
    axes[0, 0].set_xlabel("Jumlah Likes")
    axes[0, 0].set_ylabel("Frekuensi")

    # 2. Likes vs Komentar
    axes[0, 1].scatter(df["likes"], df["komentar"], alpha=0.5, color="#E87040", s=40)
    axes[0, 1].set_title("Likes vs Komentar")
    axes[0, 1].set_xlabel("Likes")
    axes[0, 1].set_ylabel("Komentar")

    # 3. Post per Bulan
    df_valid = df.dropna(subset=["waktu"]).copy()
    if not df_valid.empty:
        df_valid["bulan"] = df_valid["waktu"].dt.to_period("M").astype(str)
        per_bulan = df_valid.groupby("bulan").size()
        per_bulan.plot(kind="bar", ax=axes[1, 0], color="#5BAD6F")
        axes[1, 0].set_title("Jumlah Post per Bulan")
        axes[1, 0].set_xlabel("")
        axes[1, 0].tick_params(axis="x", rotation=45)
    else:
        axes[1, 0].text(0.5, 0.5, "Data waktu tidak tersedia",
                        ha="center", va="center", transform=axes[1, 0].transAxes)

    # 4. Distribusi Sentimen
    if "sentimen" in df.columns and df["sentimen"].nunique() > 1:
        warna = {"positif": "#4CAF50", "negatif": "#F44336", "netral": "#9E9E9E"}
        sentimen_counts = df["sentimen"].value_counts()
        colors = [warna.get(k, "#ccc") for k in sentimen_counts.index]
        sentimen_counts.plot(
            kind="pie", ax=axes[1, 1], autopct="%1.0f%%",
            colors=colors, startangle=90
        )
        axes[1, 1].set_title("Distribusi Sentimen")
        axes[1, 1].set_ylabel("")
    else:
        axes[1, 1].text(0.5, 0.5, "Sentimen: semua netral\natau tidak tersedia",
                        ha="center", va="center", transform=axes[1, 1].transAxes)

    plt.tight_layout()
    path_grafik = os.path.join(folder, "grafik_analisis.png")
    plt.savefig(path_grafik, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  ✓ Grafik → {path_grafik}")

    return path_grafik


# ============================================================
#  BAGIAN 7 — LAPORAN EXCEL
# ============================================================

def laporan_excel(df, folder):
    print("\n" + "=" * 55)
    print(" LANGKAH 7: BUAT LAPORAN EXCEL")
    print("=" * 55)

    path_excel = os.path.join(folder, "laporan_final.xlsx")

    with pd.ExcelWriter(path_excel, engine="openpyxl") as writer:
        # Sheet 1: semua data
        df.to_excel(writer, sheet_name="Data Lengkap", index=False)

        # Sheet 2: ringkasan statistik
        ringkasan = pd.DataFrame({
            "Metrik": [
                "Target Halaman", "Total Post", "Total Likes",
                "Rata-rata Likes", "Rata-rata Komentar", "Rata-rata Shares",
                "Post Likes Tertinggi", "Waktu Mulai", "Waktu Akhir"
            ],
            "Nilai": [
                TARGET_PAGE,
                len(df),
                int(df["likes"].sum()),
                round(df["likes"].mean(), 1),
                round(df["komentar"].mean(), 1),
                round(df["shares"].mean(), 1),
                int(df["likes"].max()),
                str(df["waktu"].min()),
                str(df["waktu"].max()),
            ]
        })
        ringkasan.to_excel(writer, sheet_name="Ringkasan", index=False)

        # Sheet 3: top 10 post
        kolom_tampil = ["teks", "waktu", "likes", "komentar", "shares", "link"]
        kolom_ada = [k for k in kolom_tampil if k in df.columns]
        top10 = df.sort_values("likes", ascending=False).head(10)[kolom_ada]
        top10.to_excel(writer, sheet_name="Top 10 Post", index=False)

        # Sheet 4: sentimen (jika ada)
        if "sentimen" in df.columns:
            sentimen_df = df[["teks_bersih", "likes", "sentimen"]]
            sentimen_df.to_excel(writer, sheet_name="Sentimen", index=False)

    print(f"  ✓ Laporan → {path_excel}")
    return path_excel


# ============================================================
#  MAIN — Jalankan semua langkah
# ============================================================
print("MASUK KE MAIN")
if __name__ == "__main__":
    mulai = datetime.now()

    print("\n" + "=" * 55)
    print("  FACEBOOK SCRAPER — ALL IN ONE")
    print(f"  Target : {TARGET_PAGE}")
    print(f"  Mulai  : {mulai.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # Buat folder output jika belum ada
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Jalankan semua langkah
    data_mentah   = scraping()

    if not data_mentah:
        print("\n[BERHENTI] Tidak ada data yang berhasil diambil.")
        print("Cek koneksi internet atau ganti TARGET_PAGE.\n")
        exit(1)

    path_csv      = simpan_mentah(data_mentah, OUTPUT_FOLDER)
    df            = cleaning(path_csv)
    df            = analisis(df)
    df            = sentimen(df)
    path_grafik   = visualisasi(df, OUTPUT_FOLDER)
    path_excel    = laporan_excel(df, OUTPUT_FOLDER)

    # Simpan data final (dengan kolom sentimen)
    path_final = os.path.join(OUTPUT_FOLDER, "data_final.csv")
    df.to_csv(path_final, index=False, encoding="utf-8-sig")

    selesai = datetime.now()
    durasi  = (selesai - mulai).seconds

    print("\n" + "=" * 55)
    print("  SELESAI!")
    print(f"  Durasi       : {durasi} detik")
    print(f"  Total post   : {len(df)}")
    print(f"\n  File output di folder '{OUTPUT_FOLDER}/':")
    print(f"    - data_bersih.csv")
    print(f"    - data_final.csv")
    print(f"    - grafik_analisis.png")
    print(f"    - laporan_final.xlsx")
    print("=" * 55 + "\n")