from flask import Flask, render_template, jsonify
from flask import request
import pandas as pd
import json
import os
import re 

app = Flask(__name__)

# Twitter
CSV_PATH = "output/gresik_sentimen.csv"

# Instagram
INSTAGRAM_POST = "output/gresik_ig_postingan.csv"

INSTAGRAM_SENTIMEN = "output/gresik_ig_sentimen.csv"


def load_data():
    """Membaca data CSV dengan aman"""

    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()

    try:
        df = pd.read_csv(CSV_PATH)
        
        

        if "teks_asli" in df.columns:
            df["teks_asli"] = df["teks_asli"].astype(str)

        if "username" in df.columns:
            df["username"] = df["username"].astype(str)

        if "tanggal" in df.columns:
            df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")

        if "likes" not in df.columns:
            df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0)

        if "retweets" not in df.columns:
            df["retweets"] = pd.to_numeric(df["retweets"], errors="coerce").fillna(0)
        if "skor" in df.columns:
            df["skor"] = pd.to_numeric(df["skor"], errors="coerce").fillna(0)
        else:
            df["skor"] = 0.0

        return df

    except Exception as e:
        print("Error membaca CSV:", e)
        return pd.DataFrame()
    

def load_instagram():

    if not os.path.exists(INSTAGRAM_POST):
        return pd.DataFrame()

    try:
        df = pd.read_csv(INSTAGRAM_POST)
        df = df.fillna("")

        # Pastikan semua kolom ada
        kolom_wajib = [
            "keyword",
            "shortcode",
            "link_postingan",
            "username",
            "caption",
            "tanggal",
            "likes",
            "comments"
        ]

        for kolom in kolom_wajib:
            if kolom not in df.columns:
                df[kolom] = ""

        df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0).astype(int)
        df["comments"] = pd.to_numeric(df["comments"], errors="coerce").fillna(0).astype(int)

        df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")

        return df

    except Exception as e:
        print("Error membaca data Instagram:", e)
        return pd.DataFrame()

def load_instagram_sentimen():

    if not os.path.exists(INSTAGRAM_SENTIMEN):
        return pd.DataFrame()

    return pd.read_csv(INSTAGRAM_SENTIMEN)


def ringkasan_twitter():

        df = load_data()

        if df.empty:
            return []

        hasil = []

        for tanggal, grup in df.groupby(df["tanggal"].dt.date):

            hasil.append({

                "tanggal": tanggal.strftime("%d %B %Y"),

                "jumlah": len(grup),

                "positif": (grup["sentimen"]=="positif").sum(),

                "netral": (grup["sentimen"]=="netral").sum(),

                "negatif": (grup["sentimen"]=="negatif").sum(),

                "skor": round(grup["skor"].mean(),3),

                "likes": int(grup["likes"].sum()),

                "replies": int(grup["replies"].sum()),

                "retweets": int(grup["retweets"].sum())

            })

        return hasil
    
def ringkasan_instagram():

        post = load_instagram()
        sentimen = load_instagram_sentimen()

        if post.empty or sentimen.empty:
            return []

        hasil = []

        for tanggal, grup_post in post.groupby(post["tanggal"].dt.date):

            komentar = sentimen[
                sentimen["shortcode"].isin(grup_post["shortcode"])
            ]

            hasil.append({

                "tanggal": tanggal.strftime("%d %B %Y"),

                "postingan": len(grup_post),

                "likes": int(grup_post["likes"].sum()),

                "komentar": int(grup_post["comments"].sum()),

                "positif": (komentar["sentimen"]=="positif").sum(),

                "netral": (komentar["sentimen"]=="netral").sum(),

                "negatif": (komentar["sentimen"]=="negatif").sum(),

                "skor": round(komentar["skor"].mean(),3)

            })

        return hasil


@app.route("/")
def index():
    df = load_data()
    df_ig = load_instagram()
    ringkasan_tw = ringkasan_twitter()
    ringkasan_ig = ringkasan_instagram()
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    if df.empty:
        return render_template("index.html")
    total = len(df)
    total_instagram = len(df_ig)

    sentimen = df["sentimen"].value_counts().to_dict()

    topik = df["topik"].value_counts().head(6).to_dict()

    rata_skor = round(df["skor"].mean(), 3)

    tweet_viral = (
            df.nlargest(5, "likes")[
                ["username", "teks_asli", "sentimen","skor", "likes", "tanggal"]
            ]
            .to_dict("records")
    )
    if not df_ig.empty:
        total_like = int(df_ig["likes"].sum())
        total_comment = int(df_ig["comments"].sum())
        rata_like = round(df_ig["likes"].mean(), 1)
        post_terbaru = (
        df_ig.sort_values("tanggal", ascending=False)
        .head(5)
        .to_dict("records")
    )
    else:
        total_like = 0
        total_comment = 0
        rata_like = 0
        post_terbaru = []
    update_terakhir = df["tanggal"].max().strftime("%d %B %Y")

    per_hari = (
            df.groupby(["tanggal", "sentimen"])
            .size()
            .reset_index(name="jumlah")
        )

    per_hari["tanggal"] = (
            pd.to_datetime(per_hari["tanggal"])
            .dt.strftime("%Y-%m-%d")
        )

    chart_data = per_hari.to_dict("records")
    
    return render_template(
        "index.html",
        total=total,
        sentimen=sentimen,
        topik=topik,
        tweet_viral=tweet_viral,
        chart_data=chart_data,
        update_terakhir=update_terakhir,
        kosong=False,
        total_instagram=total_instagram,
        total_like=total_like,
        total_comment=total_comment,
        rata_like=rata_like,
        rata_skor=rata_skor,
        post_terbaru=post_terbaru,
        ringkasan_tw = ringkasan_twitter(),
        ringkasan_ig = ringkasan_instagram()
    )


@app.route("/tweets")
def twitter():

    df = load_data()
    # ===========================
    # RINGKASAN PER HARI
    # ===========================

    ringkasan = (
        df.groupby(df["tanggal"].dt.date)
        .agg(
            jumlah_tweet=("id", "count"),
            rata_skor=("skor", "mean"),
            total_like=("likes", "sum"),
            total_reply=("replies", "sum"),
            total_retweet=("retweets", "sum")
        )
        .reset_index()
    )

    # Jumlah sentimen per hari
    sentimen = (
        df.groupby([df["tanggal"].dt.date, "sentimen"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    ringkasan = ringkasan.merge(
        sentimen,
        on="tanggal",
        how="left"
    )

    ringkasan["rata_skor"] = ringkasan["rata_skor"].round(3)

    if df.empty:
        return render_template(
            "tweets.html",
            data=[],
            total=0
        )

    total = len(df)

    # Hanya ambil 3 sentimen yang valid
    df_sentimen = df[
                        df["sentimen"].isin([
                            "positif",
                            "netral",
                            "negatif"
                        ])
                    ]

    sentimen = (
                    df_sentimen["sentimen"]
                    .value_counts()
                    .to_dict()
                )

    topik = (
        df["topik"]
        .value_counts()
        .head(10)
        .to_dict()
    )

    rata_skor = round(df["skor"].mean(), 3)

    tweet_viral = (
        df.nlargest(5, "likes")[
            [
                "username",
                "teks_asli",
                "sentimen",
                "likes",
                "tanggal"
            ]
        ]
        .to_dict("records")
    )

    data = (
        df.sort_values(
            "tanggal",
            ascending=False
        )
        .to_dict("records")
    )

    tweet_viral = (
                    df.nlargest(5, "likes")[
                        [
                            "username",
                            "teks_asli",
                            "sentimen",
                            "likes",
                            "tanggal"
                        ]
                    ]
                    .to_dict("records")
                )
    per_hari = (
                    df.groupby(["tanggal", "sentimen"])
                    .size()
                    .reset_index(name="jumlah")
                )

    per_hari["tanggal"] = (
                                pd.to_datetime(per_hari["tanggal"])
                                .dt.strftime("%Y-%m-%d")
                            )
    chart_data = per_hari.to_dict("records")

    print("Sentimen :", sentimen)
    print("Topik :", topik)

    return render_template(
        "tweets.html",
        total=total,
        sentimen=sentimen,
        topik=topik,
        tweet_viral=tweet_viral,
        chart_data=chart_data,
        data=data,
        rata_skor=rata_skor,
        ringkasan=ringkasan.to_dict("records"),

    )

def load_ringkasan():
    df = load_data()

    if df.empty:
        return pd.DataFrame()

    df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")

    # Ringkasan dasar
    ringkasan = (
        df.groupby(df["tanggal"].dt.date)
        .agg(
            jumlah_tweet=("id", "count"),
            rata_skor=("skor", "mean"),
            total_like=("likes", "sum"),
            total_reply=("replies", "sum"),
            total_retweet=("retweets", "sum")
        )
        .reset_index()
    )

    # Hitung sentimen per hari
    sentimen = (
        df.groupby([df["tanggal"].dt.date, "sentimen"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )

    ringkasan = ringkasan.merge(
        sentimen,
        on="tanggal",
        how="left"
    )

    ringkasan["rata_skor"] = ringkasan["rata_skor"].round(3)

    return ringkasan

@app.route("/instagram")
def instagram():

    df_post = load_instagram()
    df_sentimen = load_instagram_sentimen()
    ringkasan = load_ringkasan()

    # Ambil rata-rata skor sentimen tiap postingan
    skor_post = (
        df_sentimen
        .groupby("shortcode")
        .agg(
            skor=("skor", "mean"),
            sentimen=("sentimen", lambda x: x.value_counts().idxmax())
        )
        .reset_index()
    )

    # Gabungkan dengan data postingan
    df_post = df_post.merge(
        skor_post,
        on="shortcode",
        how="left"
    )

    df_post["skor"] = df_post["skor"].fillna(0).round(3)
    df_post["sentimen"] = df_post["sentimen"].fillna("netral")

    if df_post.empty:
        return render_template(
            "instagram.html",
            data=[],
            total=0,
            total_like=0,
            total_comment=0,
            rata_like=0,
            sentimen={},
            topik={},
            keyword={}
        )

    total = len(df_post)
    total_like = int(df_post["likes"].sum())
    total_comment = int(df_post["comments"].sum())
    rata_like = round(df_post["likes"].mean(), 1)

    # ===========================
    # PERIODE DATA
    # ===========================

    periode_awal = df_post["tanggal"].min()
    periode_akhir = df_post["tanggal"].max()

    periode = (
                f"{periode_awal.strftime('%d %B %Y')} - "
                f"{periode_akhir.strftime('%d %B %Y')}"
            )


    lama_hari = (periode_akhir - periode_awal).days + 1

    # grafik sentimen
    sentimen = df_sentimen["sentimen"].value_counts().to_dict()

    #Hitung rata skor
    rata_skor = round(df_sentimen["skor"].mean(),3)

    # grafik topik
    topik = df_sentimen["topik"].value_counts().head(10).to_dict()

    # grafik keyword
    keyword = df_sentimen["keyword"].value_counts().to_dict()

    data = (
        df_post.sort_values("tanggal", ascending=False)
        .to_dict("records")
    )

    return render_template(
        "instagram.html",
        data=data,
        total=total,
        total_like=total_like,
        total_comment=total_comment,
        rata_like=rata_like,
        sentimen=sentimen,
        topik=topik,
        keyword=keyword,
        periode=periode,
        lama_hari=lama_hari,
        rata_skor=rata_skor,
        ringkasan=ringkasan.to_dict("records")
    )


# Route overview (sudah ada, tidak perlu diubah)
@app.route("/googlemaps")
def googlemaps():
    semua = load_google_maps()
    
    # DEBUG — cek tipe data
    for i, t in enumerate(semua):
        for k, v in t.items():
            if v is None or not isinstance(v, (str, int, float, bool, list, dict)):
                print(f"[{i}] {t.get('nama','?')} -> {k}: {type(v)} = {v}")
    
    print(f"Total tempat: {len(semua)}")
    return render_template("googlemaps.html", tempat=semua)

# ✅ Tambahkan route detail ini
@app.route("/googlemaps/<key>")
def googlemaps_detail(key):
    data = load_detail_tempat(key)
    if not data:
        return "Tempat tidak ditemukan", 404
    return render_template("googlemaps_detail.html", data=data, key=key)

# ✅ Tambahkan API detail ini
@app.route("/api/googlemaps/<key>")
def api_googlemaps_detail(key):
    data = load_detail_tempat(key)
    if not data:
        return jsonify({"error": "tidak ditemukan"}), 404
    return jsonify(data)

# ✅ GANTI DENGAN INI
SUMMARY_FILE = "output/semua_tempat_summary.json"

def load_google_maps() -> list:
    if not os.path.exists(SUMMARY_FILE):
        return []
    try:
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            semua = json.load(f)
        hasil = []
        for t in semua:
            if "key" not in t:
                t["key"] = re.sub(r'[^a-z0-9]+', '_', str(t.get("tempat","")).lower()).strip('_')
            hasil.append({
                "id"            : str(t.get("key") or ""),
                "key"           : str(t.get("key") or ""),
                "nama"          : str(t.get("tempat") or t.get("key") or ""),
                "kategori"      : str(t.get("kategori") or "Lainnya"),
                "rating"        : float(t.get("rating") or 0),
                "total_ulasan"  : int(t.get("total_ulasan") or 0),
                "positif"       : int(t.get("positif") or 0),
                "netral"        : int(t.get("netral") or 0),
                "negatif"       : int(t.get("negatif") or 0),
                "persen_positif": float(t.get("persen_positif") or 0),
                "persen_netral" : float(t.get("persen_netral") or 0),
                "persen_negatif": float(t.get("persen_negatif") or 0),
            })
        return hasil
    except Exception as e:
        print("Error load summary:", e)
        return []

def load_detail_tempat(key: str) -> dict:
    """Load detail ulasan satu tempat."""
    path = os.path.join("output", key, "ulasan_sentimen.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error load detail {key}:", e)
        return {}

@app.route("/api/data")
def api_data():

    df = load_data()

    if df.empty:
        return jsonify([])

    return jsonify(
        df.tail(100).to_dict("records")
    )

@app.route("/api/instagram")
def api_instagram():

    df = load_instagram()

    if df.empty:
        return jsonify([])

    return jsonify(
        df.to_dict("records")
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)