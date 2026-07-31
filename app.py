from flask import Flask, render_template, jsonify
from flask import request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask import redirect, url_for, flash
from dotenv import load_dotenv
import pandas as pd
import json
import os
import re 

load_dotenv()
app = Flask(__name__)
#Login dan Log out
# ── Konfigurasi MySQL ──────────────────────────────
app.config["SECRET_KEY"]       = os.getenv("SECRET_KEY", "rahasia123")
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}"
    f"@{os.getenv('MYSQL_HOST')}/{os.getenv('MYSQL_DB')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db           = SQLAlchemy(app)
bcrypt       = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view     = "login"
login_manager.login_message  = "Silakan login terlebih dahulu."

# Twitter
CSV_PATH = "output/gresik_sentimen.csv"
STATUS_FILE_PATH = "output/scrape_status.json"

# Instagram
INSTAGRAM_POST = "output/gresik_ig_postingan.csv"

INSTAGRAM_SENTIMEN = "output/gresik_ig_sentimen.csv"

#Google Maps
SUMMARY_FILE = "output/semua_tempat_summary.json"

#  Facebook
FACEBOOK_SENTIMEN = "output/data_sentimen_gresik.csv"

# ── Context Processor: tersedia di semua template ──
@app.context_processor
def inject_update_terakhir():
    from datetime import datetime
    
    # Twitter — dari CSV
    update_twitter = "-"
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH, usecols=["tanggal"])
            df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")
            update_twitter = df["tanggal"].max().strftime("%d %B %Y")
        except Exception:
            pass
    
    # Google Maps — dari waktu file terakhir dimodifikasi
    update_gmaps = "-"
    if os.path.exists(SUMMARY_FILE):
        try:
            mtime = os.path.getmtime(SUMMARY_FILE)
            update_gmaps = pd.Timestamp(mtime, unit="s").strftime("%d %B %Y")
        except Exception:
            pass
    
    # Instagram — dari CSV postingan
    update_instagram = "-"
    if os.path.exists(INSTAGRAM_POST):
        try:
            df_ig = pd.read_csv(INSTAGRAM_POST, usecols=["tanggal"])
            df_ig["tanggal"] = pd.to_datetime(df_ig["tanggal"], errors="coerce")
            update_instagram = df_ig["tanggal"].max().strftime("%d %B %Y")
        except Exception:
            pass

    return dict(
        update_twitter=update_twitter,
        update_gmaps=update_gmaps,
        update_instagram=update_instagram,
        scrape_status=load_scrape_status(),
    )

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

        # Perbaikan: kondisi dibalik jadi "if IN columns"
        if "likes" in df.columns:
            df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0)
        else:
            df["likes"] = 0

        if "retweets" in df.columns:
            df["retweets"] = pd.to_numeric(df["retweets"], errors="coerce").fillna(0)
        else:
            df["retweets"] = 0

        # Tambahan: bersihkan kolom replies yang sebelumnya terlewat
        if "replies" in df.columns:
            df["replies"] = pd.to_numeric(df["replies"], errors="coerce").fillna(0)
        else:
            df["replies"] = 0

        if "skor" in df.columns:
            df["skor"] = pd.to_numeric(df["skor"], errors="coerce").fillna(0)
        else:
            df["skor"] = 0.0

        return df
    
    except Exception as e:
        print("Error membaca CSV:", e)
        return pd.DataFrame()

def load_scrape_status():
    """Baca status terakhir scraping semua platform."""
    if not os.path.exists(STATUS_FILE_PATH):
        return {}
    try:
        with open(STATUS_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
    
# ══════════════════════════════════════════════════════════════
# GANTI fungsi load_instagram() yang lama dengan ini
# ══════════════════════════════════════════════════════════════
def parse_likes(nilai):
    """
    Parse angka likes dari berbagai format:
    - "1.234"      → 1234   (titik sebagai pemisah ribuan)
    - "1,234"      → 1234   (koma sebagai pemisah ribuan)
    - "1.2K"       → 1200
    - "1.2M"       → 1200000
    - "-893499..." → 0      (angka negatif = invalid, set 0)
    - ""  / NaN    → 0
    """
    if nilai is None:
        return 0
    s = str(nilai).strip().upper()
    if not s or s in ("NAN", "NONE", "", "-"):
        return 0
    try:
        # Handle K / M suffix
        if s.endswith("K"):
            return max(0, int(float(s[:-1]) * 1_000))
        if s.endswith("M"):
            return max(0, int(float(s[:-1]) * 1_000_000))
        # Hapus pemisah ribuan (titik atau koma) secara aman:
        # Jika ada titik DAN koma → titik = ribuan, koma = desimal (format EU)
        # Jika hanya titik dan digit setelah titik > 2 → titik = ribuan
        s_clean = s.replace(",", "")          # buang koma
        if s_clean.count(".") == 1:
            bagian = s_clean.split(".")
            if len(bagian[1]) >= 3:           # "1.234" → ribuan
                s_clean = s_clean.replace(".", "")
            else:                             # "1.5" → desimal
                pass
        else:
            s_clean = s_clean.replace(".", "")
 
        hasil = int(float(s_clean))
        return max(0, hasil)                  # buang nilai negatif
    except (ValueError, OverflowError):
        return 0
    
def load_instagram():
    if not os.path.exists(INSTAGRAM_POST):
        return pd.DataFrame()
    try:
        df = pd.read_csv(INSTAGRAM_POST)
        df = df.fillna("")
 
        kolom_wajib = [
            "keyword", "shortcode", "link_postingan",
            "username", "caption", "tanggal", "likes", "comments"
        ]
        for kolom in kolom_wajib:
            if kolom not in df.columns:
                df[kolom] = ""
 
        # ✅ FIX: Gunakan parse_likes yang aman, bukan pd.to_numeric langsung
        df["likes"]    = df["likes"].apply(parse_likes)
        df["comments"] = pd.to_numeric(df["comments"], errors="coerce").fillna(0).astype(int)
        df["tanggal"]  = pd.to_datetime(df["tanggal"], errors="coerce")
 
        return df
    
    except Exception as e:
        print("Error membaca data Instagram:", e)
        return pd.DataFrame()

def load_instagram_sentimen():

    if not os.path.exists(INSTAGRAM_SENTIMEN):
        return pd.DataFrame()

    return pd.read_csv(INSTAGRAM_SENTIMEN)

#RINGKASAN IG DAN TWEETS
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

#BERANDA
@app.route("/")
@login_required
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

#TWEET
@app.route("/tweets")
@login_required
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
#INSTAGRAM
@app.route("/instagram")
@login_required
def instagram():
    df_post    = load_instagram()
    df_sentimen = load_instagram_sentimen()
    ringkasan  = load_ringkasan()
 
    skor_post = (
        df_sentimen
        .groupby("shortcode")
        .agg(
            skor=("skor", "mean"),
            sentimen=("sentimen", lambda x: x.value_counts().idxmax())
        )
        .reset_index()
    )
 
    df_post = df_post.merge(skor_post, on="shortcode", how="left")
    df_post["skor"]     = df_post["skor"].fillna(0).round(3)
    df_post["sentimen"] = df_post["sentimen"].fillna("netral")
 
    if df_post.empty:
        return render_template(
            "instagram.html",
            data=[], total=0, total_like=0,
            total_comment=0, rata_like=0,
            sentimen={}, topik={}, keyword={}
        )
 
    total         = len(df_post)
 
    # ✅ FIX: Pastikan likes sudah bersih sebelum sum
    likes_bersih  = df_post["likes"].apply(parse_likes)
    total_like    = int(likes_bersih.sum())
    total_comment = int(df_post["comments"].sum())
    rata_like     = round(likes_bersih.mean(), 1) if total > 0 else 0
 
    # Debug — hapus setelah dipastikan benar
    print(f"[DEBUG] likes sample: {df_post['likes'].head(10).tolist()}")
    print(f"[DEBUG] total_like  : {total_like}")
 
    last_update = df_post["tanggal"].max().strftime("%d %B %Y")
 
    sentimen  = df_sentimen["sentimen"].value_counts().to_dict()
    rata_skor = round(df_sentimen["skor"].mean(), 3)
    topik     = df_sentimen["topik"].value_counts().head(10).to_dict()
    keyword   = df_sentimen["keyword"].value_counts().to_dict()
 
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
        last_update=last_update,
        rata_skor=rata_skor,
        ringkasan=ringkasan.to_dict("records")
    )


# Route overview 
@app.route("/googlemaps")
@login_required
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

# API GoggleMaps
@app.route("/api/googlemaps/<key>")
def api_googlemaps_detail(key):
    data = load_detail_tempat(key)
    if not data:
        return jsonify({"error": "tidak ditemukan"}), 404
    return jsonify(data)


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
#API Data
@app.route("/api/data")
def api_data():

    df = load_data()

    if df.empty:
        return jsonify([])

    return jsonify(
        df.tail(100).to_dict("records")
    )
#API INSTAGRAM
@app.route("/api/instagram")
def api_instagram():

    df = load_instagram()

    if df.empty:
        return jsonify([])

    return jsonify(
        df.to_dict("records")
    )
#API STATUS
@app.route("/api/scrape-status")
@login_required
def scrape_status():
    def cek_file(path, kolom_total=None):
        if not os.path.exists(path):
            return {"success": False, "message": "File tidak ditemukan", "last_run": "-", "total": 0}
        import time
        mtime    = os.path.getmtime(path)
        last_run = pd.Timestamp(mtime, unit="s").strftime("%d %b %Y %H:%M")
        total    = 0
        try:
            if path.endswith(".csv"):
                df    = pd.read_csv(path)
                total = len(df)
            elif path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    data  = json.load(f)
                total = len(data) if isinstance(data, list) else 1
        except Exception:
            pass
        return {"success": True, "last_run": last_run, "total": total}

    return jsonify({
        "twitter"  : cek_file("output/gresik_sentimen.csv"),
        "instagram": cek_file("output/gresik_ig_sentimen.csv"),
        "gmaps"    : cek_file("output/semua_tempat_summary.json"),
    })

# ── Model User ─────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id         = db.Column(db.Integer, primary_key=True)
    username   = db.Column(db.String(50), unique=True, nullable=False)
    email      = db.Column(db.String(100), unique=True, nullable=False)
    password   = db.Column(db.String(255), nullable=False)
    role       = db.Column(db.String(20), default="user")
    created_at = db.Column(db.DateTime, server_default=db.func.now())

#LOGIN USER
@login_manager.user_loader
def load_user(user_id):
    if not user_id:
        return None
    try:
        return User.query.get(int(user_id))
    except (ValueError, TypeError):
        return None


# ── Buat tabel jika belum ada ──────────────────────
with app.app_context():
    db.create_all()

#ROUTE LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")
        user     = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        flash("Email atau password salah.", "danger")
    return render_template("login.html")

#ROUTE LOG OUT
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Berhasil logout.", "success")
    return redirect(url_for("login"))

#ROUTE REGISTER
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email    = request.form.get("email")
        password = request.form.get("password")

        # Cek apakah email sudah terdaftar
        if User.query.filter_by(email=email).first():
            flash("Email sudah terdaftar.", "danger")
            return redirect(url_for("register"))

        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(username=username, email=email, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash("Akun berhasil dibuat, silakan login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

from flask import session
#ROUTE FORGOT PASSWORD
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        if user:
            session['reset_email'] = email
            flash("Email ditemukan. Silakan reset kata sandi.", "success")
            return redirect(url_for('reset_password'))
        else:
            flash("Email tidak terdaftar.", "danger")
    return render_template("forgot_password.html")

#ROUTE RESET PASSWORD
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if 'reset_email' not in session:
        flash("Sesi tidak valid. Ulangi proses lupa kata sandi.", "danger")
        return redirect(url_for('forgot_password'))
    if request.method == "POST":
        password_baru = request.form.get("password")
        konfirmasi    = request.form.get("konfirmasi")
        if password_baru != konfirmasi:
            flash("Kata sandi tidak cocok.", "danger")
            return redirect(url_for('reset_password'))
        email = session.get('reset_email')
        user  = User.query.filter_by(email=email).first()
        if user:
            user.password = bcrypt.generate_password_hash(password_baru).decode('utf-8')
            db.session.commit()
            session.pop('reset_email', None)
            flash("Kata sandi berhasil diubah. Silakan login.", "success")
            return redirect(url_for('login'))
        flash("Terjadi kesalahan.", "danger")
    return render_template("reset_password.html")

#ROUTE PROFIL
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        aksi = request.form.get("aksi")

        # ── Ubah informasi profil (username & email) ──
        if aksi == "update_profile":
            username_baru = request.form.get("username", "").strip()
            email_baru    = request.form.get("email", "").strip()

            if not username_baru or not email_baru:
                flash("Nama pengguna dan email tidak boleh kosong.", "danger")
                return redirect(url_for("profile"))

            # Cek username/email bentrok dengan user lain
            cek_username = User.query.filter(
                User.username == username_baru, User.id != current_user.id
            ).first()
            cek_email = User.query.filter(
                User.email == email_baru, User.id != current_user.id
            ).first()

            if cek_username:
                flash("Nama pengguna sudah digunakan.", "danger")
                return redirect(url_for("profile"))
            if cek_email:
                flash("Email sudah digunakan.", "danger")
                return redirect(url_for("profile"))

            current_user.username = username_baru
            current_user.email    = email_baru
            db.session.commit()
            flash("Profil berhasil diperbarui.", "success")
            return redirect(url_for("profile"))

        # ── Ganti password ──
        elif aksi == "ganti_password":
            password_lama   = request.form.get("password_lama", "")
            password_baru   = request.form.get("password_baru", "")
            konfirmasi_baru = request.form.get("konfirmasi_baru", "")

            if not bcrypt.check_password_hash(current_user.password, password_lama):
                flash("Kata sandi lama salah.", "danger")
                return redirect(url_for("profile"))

            if password_baru != konfirmasi_baru:
                flash("Konfirmasi kata sandi baru tidak cocok.", "danger")
                return redirect(url_for("profile"))

            if len(password_baru) < 8:
                flash("Kata sandi baru minimal 8 karakter.", "danger")
                return redirect(url_for("profile"))

            current_user.password = bcrypt.generate_password_hash(password_baru).decode("utf-8")
            db.session.commit()
            flash("Kata sandi berhasil diubah.", "success")
            return redirect(url_for("profile"))

    return render_template("profile.html")

#Restart Token
@app.route("/settings/token/<platform>", methods=["POST"])
@login_required
def settings_token(platform):
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    # Baca .env yang ada
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
    
    def update_env(lines, key, value):
        found = False
        for i, line in enumerate(lines):
            if line.startswith(key + '='):
                lines[i] = f"{key}={value}\n"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}\n")
        return lines

    if platform == 'twitter':
        mapping = {
            'AUTH_TOKEN':   'auth_token',
            'CT0':          'ct0',
            'AUTH_TOKEN_2': 'auth_token_2',
            'CT0_2':        'ct0_2',
        }
        for env_key, form_key in mapping.items():
            val = request.form.get(form_key, '')
            if val:
                lines = update_env(lines, env_key, val)

    elif platform == 'instagram':
        mapping = {
                'IG_SESSIONID':  'ig_sessionid',
                'IG_CSRFTOKEN':  'ig_csrftoken',
                'IG_DS_USER_ID': 'ig_ds_user_id',
                'IG_MID':        'ig_mid',
                'IG_DID':        'ig_did',
                'IG_RUR':        'ig_rur',
            }
        for env_key, form_key in mapping.items():
            val = request.form.get(form_key, '')
            if val:
                lines = update_env(lines, env_key, val)

    elif platform == 'gmaps':
        mapping = {
                'APIFY_API_TOKEN_1': 'apify_token_1',
                'APIFY_API_TOKEN_2': 'apify_token_2',
                'APIFY_API_TOKEN_3': 'apify_token_3',
            }
        for env_key, form_key in mapping.items():
            val = request.form.get(form_key, '')
            if val:
                lines = update_env(lines, env_key, val)

    with open(env_path, 'w') as f:
        f.writelines(lines)

    flash(f"Token {platform} berhasil disimpan.", "success")
    return redirect(request.referrer or url_for('index'))



# ══════════════════════════════════════════════════════════════════
# Tambahkan ini ke app.py — letakkan setelah route /instagram
# ══════════════════════════════════════════════════════════════════
def load_facebook():
    """Membaca hasil analisis sentimen Facebook."""
    if not os.path.exists(FACEBOOK_SENTIMEN):
        return pd.DataFrame()
    try:
        df = pd.read_csv(FACEBOOK_SENTIMEN, encoding="utf-8-sig")
        df = df.fillna("")

        # Pastikan kolom wajib ada
        kolom_wajib = [
            "sumber", "tanggal_ambil", "tanggal_analisis",
            "kategori", "sentimen_final",
            "sentimen_bert", "skor_bert",
            "sentimen_kw", "skor_kw",
            "konflik_label", "urgensi",
            "teks", "url",
        ]
        for kolom in kolom_wajib:
            if kolom not in df.columns:
                df[kolom] = ""

        # Konversi tipe data
        df["skor_bert"] = pd.to_numeric(df["skor_bert"], errors="coerce").fillna(0)
        df["skor_kw"]   = pd.to_numeric(df["skor_kw"],   errors="coerce").fillna(0)
        df["tanggal_ambil"] = pd.to_datetime(df["tanggal_ambil"], errors="coerce")

        return df
    except Exception as e:
        print("Error membaca data Facebook:", e)
        return pd.DataFrame()


@app.route("/facebook")
@login_required
def facebook():
    df = load_facebook()

    if df.empty:
        return render_template(
            "facebook.html",
            data=[],
            total=0,
            sentimen={},
            kategori={},
            urgensi={},
            sumber={},
            rata_skor=0,
            update_terakhir="-",
            urgensi_tinggi=[],
            chart_data=[],
        )

    total     = len(df)
    rata_skor = round(df["skor_bert"].mean(), 3)

    sentimen = df["sentimen_final"].value_counts().to_dict()

    persen_negatif = round(
        sentimen.get("negatif",0)/total*100,1
    )

    persen_positif = round(
        sentimen.get("positif",0)/total*100,1
    )

    avg_confidence = round(
        df["skor_bert"].mean()*100,
        1
    )

    konflik_label = (
        df["konflik_label"]
        .astype(str)
        .str.lower()
        .isin(["true","1","ya"])
        .sum()
    )

    jumlah_urgensi_tinggi = (
        df["urgensi"]
        .str.lower()
        .eq("tinggi")
        .sum()
    )

    # Distribusi sentimen, kategori, urgensi, sumber
    sentimen = df["sentimen_final"].value_counts().to_dict()
    kategori = df["kategori"].value_counts().to_dict()
    urgensi  = df["urgensi"].value_counts().to_dict()
    sumber   = df["sumber"].value_counts().to_dict()


    # Update terakhir
    update_terakhir = "-"
    if "tanggal_ambil" in df.columns and df["tanggal_ambil"].notna().any():
        update_terakhir = df["tanggal_ambil"].max().strftime("%d %B %Y")

    # Post urgensi tinggi
    urgensi_tinggi = (
        df[df["urgensi"] == "tinggi"]
        .sort_values("skor_bert", ascending=False)
        .head(10)
        .to_dict("records")
    )

    # Chart sentimen per sumber
    chart_data = (
        df.groupby(["sumber", "sentimen_final"])
        .size()
        .reset_index(name="jumlah")
        .to_dict("records")
    )

    # Tabel data lengkap
    data = (
        df.sort_values("tanggal_ambil", ascending=False)
        .to_dict("records")
    )

    return render_template(
        "facebook.html",
        data=data,
        total=total,
        sentimen=sentimen,
        kategori=kategori,
        urgensi=urgensi,
        sumber=sumber,
        rata_skor=rata_skor,
        update_terakhir=update_terakhir,
        urgensi_tinggi=urgensi_tinggi,
        chart_data=chart_data,
        persen_negatif=persen_negatif,
        persen_positif=persen_positif,
        avg_confidence=avg_confidence,
        konflik_label=konflik_label,
        jumlah_urgensi_tinggi=jumlah_urgensi_tinggi,
    )


@app.route("/api/facebook")
@login_required
def api_facebook():
    df = load_facebook()
    if df.empty:
        return jsonify([])
    return jsonify(df.tail(100).to_dict("records"))


#MAIN
if __name__ == "__main__":
    app.run(debug=True, port=5000)