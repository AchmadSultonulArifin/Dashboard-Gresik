from flask import Flask, render_template, jsonify
import pandas as pd
import os

app = Flask(__name__)
CSV_PATH = "output/gresik_sentimen.csv"

def load_data():
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH)
    df["tanggal"] = pd.to_datetime(df["tanggal"])
    return df

@app.route("/")
def index():
    df = load_data()
    if df.empty:
        return render_template("index.html", kosong=True)

    total        = len(df)
    sentimen     = df["sentimen"].value_counts().to_dict()
    topik        = df["topik"].value_counts().head(6).to_dict()
    tweet_viral  = df.nlargest(5, "likes")[
        ["username","teks_asli","sentimen","likes","tanggal"]
    ].to_dict("records")
    update_terakhir = df["tanggal"].max().strftime("%d %B %Y")

    # Data chart sentimen per hari
    per_hari = (
        df.groupby(["tanggal", "sentimen"])
        .size().reset_index(name="jumlah")
    )
    chart_data = per_hari.to_dict("records")

    return render_template("index.html",
        total=total,
        sentimen=sentimen,
        topik=topik,
        tweet_viral=tweet_viral,
        chart_data=chart_data,
        update_terakhir=update_terakhir,
        kosong=False
    )

@app.route("/tweets")
def tweets():
    df = load_data()
    data = df.sort_values("tanggal", ascending=False).head(200).to_dict("records")
    return render_template("tweets.html", data=data, total=len(df))

@app.route("/topik")
def topik():
    df = load_data()
    per_topik = df.groupby(["topik", "sentimen"]).size().reset_index(name="jumlah")
    return render_template("topik.html", data=per_topik.to_dict("records"))

@app.route("/api/data")
def api_data():
    df = load_data()
    return jsonify(df.tail(100).to_dict("records"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)