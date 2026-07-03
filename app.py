from flask import Flask, render_template, jsonify
import pandas as pd
import os

app = Flask(__name__)

CSV_PATH = "output/gresik_sentimen.csv"


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


@app.route("/")
def index():

    df = load_data()

    if df.empty:
        return render_template("index.html", kosong=True)

    total = len(df)

    sentimen = df["sentimen"].value_counts().to_dict()

    topik = df["topik"].value_counts().head(6).to_dict()

    tweet_viral = (
        df.nlargest(5, "likes")[
            ["username", "teks_asli", "sentimen", "likes", "tanggal"]
        ]
        .to_dict("records")
    )

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
    )


@app.route("/tweets")
def tweets():

    df = load_data()

    if df.empty:
        return render_template(
            "tweets.html",
            data=[],
            total=0
        )

    data = (
        df.sort_values("tanggal", ascending=False)
        .head(200)
        .to_dict("records")
    )

    return render_template(
        "tweets.html",
        data=data,
        total=len(df)
    )


@app.route("/topik")
def topik():

    df = load_data()

    if df.empty:
        return render_template(
            "topik.html",
            data=[]
        )

    per_topik = (
        df.groupby(["topik", "sentimen"])
        .size()
        .reset_index(name="jumlah")
    )

    return render_template(
        "topik.html",
        data=per_topik.to_dict("records")
    )


@app.route("/api/data")
def api_data():

    df = load_data()

    if df.empty:
        return jsonify([])

    return jsonify(
        df.tail(100).to_dict("records")
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)