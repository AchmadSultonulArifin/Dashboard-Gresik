"""
scrape_instagram.py

Scraper Instagram untuk Dashboard Gresik.
Menyimpan hasil ke output/gresik_instagram.json dengan skema yang seragam
dengan gresik_tweets.json, supaya mudah digabung di merge_data.py.

CARA PAKAI (test dulu dengan 1 akun spesifik, lebih stabil daripada hashtag):
    python scrape_instagram.py --mode profile --target namaakun --limit 10

Setelah yakin stabil, boleh coba mode hashtag (lebih rawan rate-limit):
    python scrape_instagram.py --mode hashtag --target gresik --limit 20

Tanpa argumen, script akan pakai nilai default dari file .env.
"""

import argparse
import json
import os
import time
from datetime import datetime

import instaloader
from dotenv import load_dotenv

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME") 
IG_PASSWORD = os.getenv("IG_PASSWORD")

IG_USERNAME = os.getenv("slton902") or None
IG_PASSWORD = os.getenv("Sultonul12") or None
DEFAULT_MODE = os.getenv("IG_TARGET_MODE", "profile")
DEFAULT_TARGET = os.getenv("IG_TARGET", "")
DEFAULT_LIMIT = int(os.getenv("IG_LIMIT", "10"))

OUTPUT_PATH = os.path.join("output", "gresik_instagram.json")
JEDA_ANTAR_POST = 5  # detik, jangan diperkecil - ini yang mencegah rate-limit


def login(loader: instaloader.Instaloader) -> None:
    """Login opsional. Tanpa login tetap bisa scrape akun publik,
    tapi limitnya lebih ketat dan lebih cepat kena block sementara."""
    if IG_USERNAME and IG_PASSWORD:
        try:
            loader.login(IG_USERNAME, IG_PASSWORD)
            print(f"Login berhasil sebagai {IG_USERNAME}")
        except Exception as e:
            print(f"Login gagal, lanjut tanpa login. Detail: {e}")
    else:
        print("IG_USERNAME/IG_PASSWORD tidak diisi di .env, scraping tanpa login.")


def _post_to_dict(post, username_fallback: str = "") -> dict:
    """Ubah objek Post dari instaloader jadi dict dengan skema seragam."""
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
    """Mode paling stabil - scrape postingan dari SATU akun spesifik.
    Cocok untuk testing awal sebelum coba mode hashtag."""
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
    for i, post in enumerate(profile.get_posts()):
        try:
            data = _post_to_dict(post, username_fallback=username)
            hasil.append(data)
            print(f"[{i + 1}/{limit}] {data['date']} | likes={data['likes']} comments={data['comments']}")
        except Exception as e:
            print(f"Lewati satu post karena error: {e}")

        time.sleep(JEDA_ANTAR_POST)

        if i + 1 >= limit:
            break

    return hasil


def scrape_hashtag(loader: instaloader.Instaloader, hashtag: str, limit: int) -> list:
    """Mode hashtag - lebih rawan rate-limit dibanding mode profile.
    Baru pakai ini setelah mode profile terbukti jalan stabil."""
    print(f"Mengambil hashtag: #{hashtag}")
    try:
        posts = instaloader.Hashtag.from_name(loader.context, hashtag).get_posts()
    except Exception as e:
        print(f"Gagal ambil hashtag #{hashtag}: {e}")
        return []

    hasil = []
    for i, post in enumerate(posts):
        try:
            data = _post_to_dict(post)
            hasil.append(data)
            print(f"[{i + 1}/{limit}] @{data['author']} | likes={data['likes']}")
        except Exception as e:
            print(f"Lewati satu post karena error: {e}")

        time.sleep(JEDA_ANTAR_POST)

        if i + 1 >= limit:
            break

    return hasil


def simpan_json(data_baru: list, path: str) -> None:
    """Simpan hasil scraping, digabung dengan data lama (kalau ada)
    supaya history tidak tertimpa tiap kali script dijalankan ulang."""
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


def main():
    parser = argparse.ArgumentParser(description="Scraper Instagram untuk Dashboard Gresik")
    parser.add_argument("--mode", choices=["profile", "hashtag"], default=DEFAULT_MODE,
                         help="profile = scrape 1 akun, hashtag = scrape berdasarkan tagar")
    parser.add_argument("--target", default=DEFAULT_TARGET,
                         help="username akun atau daftar tagar dipisah koma (contoh: gresik,kulinergresik)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                         help="jumlah maksimal post per tagar")
    args = parser.parse_args()

    if not args.target:
        print("Target belum diisi. Gunakan --target atau isi IG_TARGET di .env")
        return

    loader = instaloader.Instaloader()
    login(loader)

    # Memecah target menjadi list jika dipisah koma
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