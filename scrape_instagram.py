import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
import instaloader
from dotenv import load_dotenv
load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME") 
IG_PASSWORD = os.getenv("IG_PASSWORD")
OUTPUT_PATH = os.path.join("output", "gresik_instagram.json")
SESSION_DIR = "ig_session"
JEDA_ANTAR_POST = 5  # detik, jangan diperkecil - ini yang mencegah rate-limit
# Ambil postingan 7 hari terakhir
JUMLAH_HARI = int(os.getenv("JUMLAH_HARI", "7"))

BATAS_TANGGAL = (
    datetime.now(timezone.utc)
    - timedelta(days=JUMLAH_HARI)
)

def login(loader: instaloader.Instaloader) -> bool:
    if not IG_USERNAME:
        print("IG_USERNAME tidak diisi di .env, scraping tanpa login.")
        return False

    os.makedirs(SESSION_DIR, exist_ok=True)
    session_file = os.path.join(SESSION_DIR, IG_USERNAME)

    # Coba pakai session yang sudah tersimpan dulu
    try:
        loader.load_session_from_file(IG_USERNAME, session_file)
        print(f"Pakai session tersimpan untuk {IG_USERNAME} (tidak perlu login ulang).")
        return True
    except FileNotFoundError:
        pass

    # Kalau belum ada session tersimpan, baru login pakai password
    if IG_PASSWORD:
        try:
            loader.login(IG_USERNAME, IG_PASSWORD)
            loader.save_session_to_file(session_file)
            print(f"Login berhasil sebagai {IG_USERNAME}, session disimpan di {session_file}")
            return True
        except Exception as e:
            print(f"Login gagal, lanjut tanpa login. Detail: {e}")
            return False
    else:
        print("IG_PASSWORD tidak diisi, scraping tanpa login.")
        return False

def _post_to_dict(post, username_fallback: str = "") -> dict:
    return {

        "source": "instagram",
        "id": post.shortcode,
        "author": post.owner_username or username_fallback,
        "text": post.caption if post.caption else "",
        "likes": post.likes,
        "comments": post.comments,
        "date": post.date_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        "url": f"https://www.instagram.com/p/{post.shortcode}/",
        "scraped_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }

def scrape_profile(loader: instaloader.Instaloader, username: str, limit: int) -> list:
    print(f"Mengambil profil: {username}")

    try:
        profile = instaloader.Profile.from_username(loader.context, username)
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"Akun '{username}' tidak ditemukan.")
        return []
    except Exception as e:
        print(f"Gagal ambil profil: {e}")
        return []
    print(f"Followers: {profile.followers} | Posts: {profile.mediacount}")
    hasil = []

    jumlah = 0

    for post in profile.get_posts():

        # Stop jika postingan lebih lama dari 7 hari
        if post.date_utc < BATAS_TANGGAL:
            break

        try:
            data = _post_to_dict(post, username_fallback=username)
            hasil.append(data)

            jumlah += 1

            print(
                f"[{jumlah}] "
                f"{data['date']} "
                f"likes={data['likes']}"
            )

        except Exception as e:
            print(e)

        time.sleep(JEDA_ANTAR_POST)

        if jumlah >= limit:
            break


def scrape_hashtag(loader: instaloader.Instaloader, hashtag: str, limit: int) -> list:
    print(f"DEBUG: Mencoba akses hashtag #{hashtag}")
    hasil = []
    try:
        print(f"DEBUG: Status login: {loader.test_login()}")
        posts = instaloader.Hashtag.from_name(loader.context, hashtag).get_posts()
        print("DEBUG: Berhasil mendapatkan objek hashtag, mulai loop...")

        jumlah = 0

        for post in posts:

            if post.date_utc < BATAS_TANGGAL:
                break

            try:
                data = _post_to_dict(post)

                hasil.append(data)

                jumlah += 1

                print(
                    f"[{jumlah}] "
                    f"{data['date']} "
                    f"@{data['author']}"
                )

            except Exception as e:
                print(e)

            time.sleep(JEDA_ANTAR_POST)

            if jumlah >= limit:
                break
            return hasil

    except Exception as e:
        import traceback
        print("ERROR TERDETEKSI:")
        traceback.print_exc()

    return hasil

def simpan_json(data_baru: list, path: str) -> None:
    if not data_baru:
        print("Tidak ada data baru untuk disimpan.")
        return
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data_lama = []

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                data_lama = json.load(f)
            except json.JSONDecodeError:
                data_lama = []
    id_lama = {d["id"] for d in data_lama}
    tambahan = [d for d in data_baru if d["id"] not in id_lama]
    gabungan = data_lama + tambahan
    with open(path, "w", encoding="utf-8") as f:
        json.dump(gabungan, f, ensure_ascii=False, indent=2)
    print(f"\n{len(tambahan)} post baru ditambahkan. Total sekarang: {len(gabungan)} post.")
    print(f"Tersimpan di: {path}")

print("="*50)
print(f"Ambil postingan {JUMLAH_HARI} hari terakhir")
print(f"Batas tanggal : {BATAS_TANGGAL}")
print("="*50)

def main():
    print("--- Memulai proses scraping ---")

    DEFAULT_MODE = "hashtag"
    DEFAULT_TARGET = "Gresik"
    DEFAULT_LIMIT = 5

    parser = argparse.ArgumentParser(description="Scraper Instagram untuk Dashboard Gresik")
    parser.add_argument("--mode", choices=["profile", "hashtag"], default=DEFAULT_MODE)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    if not args.target:
        print("Target belum diisi. Gunakan --target atau isi IG_TARGET di .env")
        return

    # loader dibuat DI SINI, sebelum tahu mode-nya apa,
    # supaya selalu ada isinya apa pun mode yang dipilih
    loader = instaloader.Instaloader()
    berhasil_login = login(loader)

    if not berhasil_login:
        print("\nLogin Instagram gagal.")
        print("Silakan selesaikan checkpoint di browser terlebih dahulu.")
        return

    targets = [t.strip() for t in args.target.split(",")]
    all_data = []

    for t in targets:
        print(f"\n--- Memproses target: {t} ---")
        if args.mode == "profile":
            data = scrape_profile(loader, t, args.limit)
        else:
            data = scrape_hashtag(loader, t, args.limit)
        all_data.extend(data)

    simpan_json(all_data, OUTPUT_PATH)

    


if __name__ == "__main__":
    main()