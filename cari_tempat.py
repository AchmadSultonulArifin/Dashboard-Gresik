"""
Mencari daftar tempat Google Maps berdasarkan kategori
Output:
output/master_tempat.csv
"""

import os
import pandas as pd
from dotenv import load_dotenv
from apify_client import ApifyClient

# ======================================================
# KONFIGURASI
# ======================================================

load_dotenv()

API_TOKEN = os.getenv("APIFY_API_TOKEN")

client = ApifyClient(API_TOKEN)

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

MASTER_FILE = os.path.join(OUTPUT_DIR, "master_tempat.csv")


# ======================================================
# KATEGORI YANG AKAN DICARI
# ======================================================

KATEGORI = {

    "Pemerintahan":[
        "kantor pemerintah gresik",
        "kantor dinas gresik",
        "kantor kecamatan gresik",
        "kantor kelurahan gresik"
    ],

    "Kesehatan":[
        "rumah sakit gresik",
        "puskesmas gresik",
        "klinik gresik"
    ],

    "Pendidikan":[
        "sd gresik",
        "smp gresik",
        "sma gresik",
        "smk gresik",
        "universitas gresik"
    ],

    "Pelayanan Publik":[
        "mall pelayanan publik gresik",
        "kantor pos gresik",
        "samsat gresik"
    ],

    "Perbankan":[
        "bank bca gresik",
        "bank bri gresik",
        "bank mandiri gresik",
        "bank bni gresik"
    ],

    "Wisata":[
        "wisata gresik",
        "pantai gresik",
        "museum gresik"
    ],

    "Olahraga":[
        "stadion gresik",
        "gor gresik"
    ]

}


# ======================================================
# SCRAPING TEMPAT
# ======================================================

semua_tempat = []

for kategori, keyword_list in KATEGORI.items():

    print(f"\n========== {kategori} ==========")

    for keyword in keyword_list:

        print("Cari :", keyword)

        run_input = {

            "searchStringsArray":[keyword],

            "locationQuery":"Gresik, Jawa Timur, Indonesia",

            "maxCrawledPlacesPerSearch":30,

            "includeReviews":False,

            "language":"id"

        }

        run = client.actor(
            "compass/crawler-google-places"
        ).call(run_input=run_input)

        dataset = client.dataset(run.default_dataset_id)

        for item in dataset.iterate_items():

            semua_tempat.append({

                "kategori":kategori,

                "nama":item.get("title",""),

                "alamat":item.get("address",""),

                "rating":item.get("totalScore",""),

                "jumlah_ulasan":item.get("reviewsCount","")

            })



# ======================================================
# HAPUS DUPLIKAT
# ======================================================

df = pd.DataFrame(semua_tempat)

df.drop_duplicates(
    subset=["nama"],
    inplace=True
)

df.sort_values(
    ["kategori","nama"],
    inplace=True
)

df.to_csv(
    MASTER_FILE,
    index=False,
    encoding="utf-8-sig"
)

print("\n======================================")
print(df.head())
print("======================================")

print(f"\nTotal tempat : {len(df)}")

print(f"Disimpan ke : {MASTER_FILE}")