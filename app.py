from flask import Flask, render_template, jsonify
import pandas as pd
import os

app = Flask(__name__)

# Twitter
CSV_PATH = "output/gresik_sentimen.csv"

# Instagram
INSTAGRAM_PATH = "output/gresik_instagram.csv"


def load_data():
    """Membaca data CSV dengan aman"""

    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()

    try:
        df = pd.read_csv(CSV_PATH)

        if "tanggal" in df.columns:
            df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")

        if "likes" not in df.columns:
            df["likes"] = 0

        if "retweets" not in df.columns:
            df["retweets"] = 0

        return df

    except Exception as e:
        print("Error membaca CSV:", e)
        return pd.DataFrame()
    
def load_instagram():
    #"""Membaca data Instagram"""

    if not os.path.exists(INSTAGRAM_PATH):
        return pd.DataFrame()

    try:
        df = pd.read_csv(INSTAGRAM_PATH)
        df = df.fillna("")

        if "tanggal" in df.columns:
            df["tanggal"] = pd.to_datetime(
                df["tanggal"],
                errors="coerce"
            )

        if "likes" not in df.columns:
            df["likes"] = 0

        if "comments" not in df.columns:
            df["comments"] = 0

        return df

    except Exception as e:
        print("Error membaca Instagram:", e)
        return pd.DataFrame()


@app.route("/")
def index():
    df = load_data()
    df_ig = load_instagram()
    if df.empty:
        return render_template("index.html", kosong=True)
    total = len(df)
    total_instagram = len(df_ig)

    sentimen = df["sentimen"].value_counts().to_dict()

    topik = df["topik"].value_counts().head(6).to_dict()

    tweet_viral = (
            df.nlargest(5, "likes")[
                ["username", "teks_asli", "sentimen", "likes", "tanggal"]
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
        post_terbaru=post_terbaru,
    )


@app.route("/twitter")
def twitter():

    df = load_data()

    if df.empty:
        return render_template(
            "twitter.html",
            data=[],
            total=0
        )

    total = len(df)

    sentimen = df["sentimen"].value_counts().to_dict()

    topik = (
        df["topik"]
        .value_counts()
        .head(10)
        .to_dict()
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

    data = (
        df.sort_values(
            "tanggal",
            ascending=False
        )
        .to_dict("records")
    )

    return render_template(
        "twitter.html",
        total=total,
        sentimen=sentimen,
        topik=topik,
        tweet_viral=tweet_viral,
        data=data
    )

@app.route("/instagram")
def instagram():

    df = load_instagram()

    if df.empty:
        return render_template(
            "instagram.html",
            data=[],
            total=0,
            total_like=0,
            total_comment=0,
            rata_like=0,
            topik={}
        )

    total = len(df)

    total_like = int(df["likes"].sum())
    total_comment = int(df["comments"].sum())
    rata_like = round(df["likes"].mean(),1)

    # nanti kalau sudah ada hasil topik instagram
    if "topik" in df.columns:
        topik = (
            df["topik"]
            .value_counts()
            .head(10)
            .to_dict()
        )
    else:
        topik = {}

    data = (
        df.sort_values(
            "tanggal",
            ascending=False
        )
        .to_dict("records")
    )

    return render_template(
        "instagram.html",
        total=total,
        total_like=total_like,
        total_comment=total_comment,
        rata_like=rata_like,
        topik=topik,
        data=data
    )

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