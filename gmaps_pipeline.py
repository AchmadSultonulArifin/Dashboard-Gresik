"""
Google Maps Pipeline — Kabupaten Gresik
=========================================
Menu:
  1. Buat master tempat (cari_tempat)
  2. Scraping ulasan (googlemaps)
  3. Proses sentimen (sentimen_GM)
  4. Scan & update summary (scan_output)
  5. Jalankan semua (1→2→3→4)
"""
import re
import json
import os
import sys
import time
import warnings
warnings.filterwarnings("ignore")
from apify_client import ApifyClient
from dotenv import load_dotenv
import pandas as pd
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
except ImportError:
    os.system("pip install transformers torch")
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
# ════════════════════════════════════════════════════
# KONFIGURASI
# ════════════════════════════════════════════════════
load_dotenv()
TOKENS = [t for t in [
    os.getenv("APIFY_API_TOKEN_1"),
    os.getenv("APIFY_API_TOKEN_2"),
    os.getenv("APIFY_API_TOKEN_3"),
] if t]
print(f"✅ {len(TOKENS)} token Apify terbaca")
OUTPUT_DIR      = "output"
MASTER_FILE     = "output/master_tempat.csv"
CHECKPOINT_FILE = "output/checkpoint.txt"
SUMMARY_FILE    = "output/semua_tempat_summary.json"
token_index = 0
# ════════════════════════════════════════════════════
# APIFY — ROTASI TOKEN
# ════════════════════════════════════════════════════
def get_client():
    return ApifyClient(TOKENS[token_index])
def rotate_token():
    global token_index
    token_index = (token_index + 1) % len(TOKENS)
    print(f"🔄 Rotasi ke token {token_index + 1}")
def run_actor(run_input: dict, max_retry: int = None) -> list:
    if max_retry is None:
        max_retry = len(TOKENS)
    for attempt in range(max_retry):
        try:
            client = get_client()
            run    = client.actor("compass/crawler-google-places").call(run_input=run_input)
            return list(client.dataset(run.default_dataset_id).iterate_items())
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ["402","limit","quota","payment","credit","exceed","usage","subscription"]):
                print(f"⚠️  Token {token_index+1} kena limit, rotasi...")
                rotate_token()
            elif any(k in err for k in ["dns","connect","network","timeout","host"]):
                print(f"⚠️  Koneksi terputus (attempt {attempt+1}), tunggu 10 detik...")
                time.sleep(10)
            else:
                print(f"❌ Error: {e}")
                raise
    print("❌ Semua token habis, skip.")
    return []
# ════════════════════════════════════════════════════
# CHECKPOINT
# ════════════════════════════════════════════════════
def get_checkpoint() -> int:
    if os.path.exists(CHECKPOINT_FILE):
        try: return int(open(CHECKPOINT_FILE).read().strip())
        except: return 0
    return 0
def save_checkpoint(i: int):
    with open(CHECKPOINT_FILE, "w") as f: f.write(str(i))
def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE): os.remove(CHECKPOINT_FILE)
# ════════════════════════════════════════════════════
# HELPER
# ════════════════════════════════════════════════════
def get_folder(nama):
    return re.sub(r'[^a-z0-9]+', '_', nama.lower()).strip('_')
EXCLUDE_KEYWORDS = [
    "indomaret","alfamart","minimarket","spbu","toko","warung",
    "resto","kafe","salon","barbershop","laundry","bengkel",
    "dealer","hotel","kost",
]
def is_valid_tempat(nama: str) -> bool:
    n = nama.lower()
    return not any(ex in n for ex in EXCLUDE_KEYWORDS)
# ════════════════════════════════════════════════════
# NLP — PREPROCESSING & TOPIK
# ════════════════════════════════════════════════════
SLANG_DICT = {
    "yg":"yang","dgn":"dengan","utk":"untuk","krn":"karena",
    "sdh":"sudah","blm":"belum","tdk":"tidak","ga":"tidak",
    "gak":"tidak","nggak":"tidak","ngga":"tidak","gk":"tidak",
    "bgt":"banget","bngt":"banget","sgt":"sangat","skrg":"sekarang",
    "klo":"kalau","klu":"kalau","kl":"kalau","tp":"tapi",
    "tpi":"tapi","ttg":"tentang","dr":"dari","dlm":"dalam",
    "dg":"dengan","sm":"sama","jg":"juga","hrs":"harus",
    "msh":"masih","lbh":"lebih","krng":"kurang","byk":"banyak",
    "plg":"paling","pd":"pada","spy":"supaya","sy":"saya",
    "gue":"saya","gw":"saya","loe":"kamu","lu":"kamu",
    "lo":"kamu","ok":"oke","oks":"oke","mantap":"bagus",
    "mantul":"bagus","keren":"bagus","jos":"bagus",
    "wkwk":"","haha":"","hehe":"","wkwkwk":"",
    "antri":"antrian","ngantri":"antrian",
    "rmh sakit":"rumah sakit","rs":"rumah sakit","kmr":"kamar",
}
STOPWORDS_ID = {
    "yang","dan","di","ke","dari","ini","itu","ada","dengan",
    "untuk","pada","adalah","dalam","tidak","juga","sudah",
    "saya","kami","kita","mereka","dia","ia","anda","kamu",
    "akan","bisa","dapat","oleh","atau","tapi","namun","tetapi",
    "jika","kalau","karena","saat","ketika","setelah","sebelum",
    "lebih","sangat","sekali","masih","belum","baru","lagi",
    "pun","nya","lah","kah","pula","sih","deh","dong",
}
TOPIC_RULES = {
    "Pelayanan"    : ["pelayanan","layanan","petugas","pegawai","ramah","cepat","lambat","antri","antrian","administrasi","birokrasi","loket"],
    "Fasilitas"    : ["fasilitas","gedung","ruangan","toilet","parkir","kursi","wifi","ac","bersih","kotor","nyaman"],
    "Kesehatan"    : ["dokter","perawat","rumah sakit","puskesmas","obat","pasien","bpjs","igd","rawat"],
    "Administrasi" : ["ktp","kk","akta","nik","dokumen","berkas","izin","surat","disdukcapil"],
    "Infrastruktur": ["jalan","bangunan","renovasi","akses","lift","tangga","trotoar","parkiran"],
    "Keamanan"     : ["satpam","aman","keamanan","polisi","security"],
}
def clean_text(text):
    if not text or not isinstance(text, str): return ""
    text = text.lower()
    text = re.sub(r'http\S+|www\S+','',text)
    text = re.sub(r'@\w+|#\w+','',text)
    text = text.encode('ascii','ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9\s]',' ',text)
    text = re.sub(r'\b\d+\b','',text)
    return re.sub(r'\s+',' ',text).strip()
def normalize_slang(text):
    return ' '.join(SLANG_DICT.get(w,w) for w in text.split()).strip()
def remove_stopwords(text):
    return ' '.join(w for w in text.split() if w not in STOPWORDS_ID and len(w)>1)
def preprocess(text):
    s1=clean_text(text); s2=normalize_slang(s1); s3=remove_stopwords(s2)
    return {"cleaned":s1,"normalized":s2,"final":s3}
def detect_topic(text):
    text=text.lower()
    for topic,kws in TOPIC_RULES.items():
        for kw in kws:
            if kw in text: return topic
    return "Lainnya"
# ════════════════════════════════════════════════════
# INDOBERT
# ════════════════════════════════════════════════════
LABEL_MAP = {"LABEL_0":"Negatif","LABEL_1":"Netral","LABEL_2":"Positif"}
def load_indobert():
    print("\n🤖 Memuat model IndoBERT...")
    MODEL = "mdhugol/indonesia-bert-sentiment-classification"
    tok   = AutoTokenizer.from_pretrained(MODEL)
    mod   = AutoModelForSequenceClassification.from_pretrained(MODEL)
    pipe  = pipeline("sentiment-analysis", model=mod, tokenizer=tok,
                     device=0 if torch.cuda.is_available() else -1,
                     truncation=True, max_length=512)
    print("✅ IndoBERT siap!")
    return pipe
def predict(pipe, text):
    if not text or len(text.strip())<3: return {"label":"Netral","score":0.0}
    try:
        r = pipe(text[:512])[0]
        return {"label":LABEL_MAP.get(r["label"],r["label"]),"score":round(r["score"],4)}
    except: return {"label":"Error","score":0.0}

# ════════════════════════════════════════════════════
# MODUL 1 — CARI TEMPAT
# ════════════════════════════════════════════════════
def cari_tempat():
    # ✅ Skip jika master sudah ada dan tidak kosong
    if os.path.exists(MASTER_FILE):
        try:
            df_cek = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
            if len(df_cek) > 0:
                print(f"\n✅ Master sudah ada ({len(df_cek)} tempat), skip modul 1.")
                return
        except Exception:
            pass  # file rusak, buat ulang

    print("\n" + "="*55)
    print("📍 MODUL 1 — BUAT MASTER TEMPAT")
    print("="*55)
    # ... sisa kode tetap sama
    SEARCHES = {
        "Pemerintahan" : ["kantor bupati gresik","kantor kecamatan gresik","kantor kelurahan gresik","sekretariat daerah gresik","dinas gresik"],
        "Kesehatan"    : ["rumah sakit gresik","puskesmas gresik"],
        "Pendidikan"   : ["SMA negeri gresik","SMK negeri gresik","universitas gresik"],
        "Pelayanan Publik":["disdukcapil gresik","samsat gresik","mall pelayanan publik gresik","kantor imigrasi gresik","bpjs gresik"],
        "Olahraga"     : ["gor gresik","stadion gresik","lapangan olahraga gresik"],
        "Wisata"       : ["wisata gresik","pantai gresik"],
        "Perbankan"    : ["bank gresik","bri gresik","bni gresik","mandiri gresik","bca gresik"],
        "Industri"     : ["petrokimia gresik","semen gresik"],
    }
    semua = []
    for kategori, pencarian in SEARCHES.items():
        print(f"\n===== {kategori} =====")
        for keyword in pencarian:
            print(f"Cari: {keyword}")
            items = run_actor({
                "searchStringsArray"       : [keyword],
                "locationQuery"            : "Gresik, Jawa Timur",
                "maxCrawledPlacesPerSearch": 20,
                "includeReviews"           : False
            })
            for item in items:
                nama = item["title"]
                if is_valid_tempat(nama):
                    semua.append({"kategori":kategori,"nama":nama})
                else:
                    print(f"   ⛔ Skip: {nama}")
    df = pd.DataFrame(semua).drop_duplicates("nama")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(MASTER_FILE, index=False, encoding="utf-8-sig")
    print(f"\n✅ Master tempat dibuat: {len(df)} tempat → {MASTER_FILE}")
# ════════════════════════════════════════════════════
# MODUL 2 — SCRAPING ULASAN
# ════════════════════════════════════════════════════
def scraping_ulasan(force: bool = False):
    print("\n" + "="*55)
    print("🌐 MODUL 2 — SCRAPING ULASAN GOOGLE MAPS")
    print("="*55)
    if not os.path.exists(MASTER_FILE):
        print("⚠️  Master belum ada, jalankan modul 1 dulu.")
        return []
    master  = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")

    if len(master) == 0:
        print("❌ Master tempat kosong — semua token Apify habis limit.")
        print("   Tunggu reset kredit bulan depan atau cek console.apify.com")
        return []

    results = []
    start   = get_checkpoint()

    if start > 0:
        print(f"⏩ Lanjut dari tempat ke-{start+1}\n")
        for i in range(start):
            row       = master.iloc[i]
            json_path = os.path.join(OUTPUT_DIR, get_folder(row["nama"]), "ulasan_mentah.json")
            if os.path.exists(json_path):
                with open(json_path,"r",encoding="utf-8") as f:
                    place = json.load(f)
                    place["kategori"] = row["kategori"]
                    results.append(place)
    else:
        print("⏳ Mulai dari awal...\n")
    for i, (_, row) in enumerate(master.iterrows()):
        if i < start: continue
        print(f"[{i+1}/{len(master)}] 📍 {row['nama']}")
        folder_cek = os.path.join(OUTPUT_DIR, get_folder(row["nama"]))
        json_cek   = os.path.join(folder_cek, "ulasan_mentah.json")
        if os.path.exists(json_cek) and not force:
            print(f"   📂 Cache ada, skip.")
            with open(json_cek,"r",encoding="utf-8") as f:
                place = json.load(f)
                place["kategori"] = row["kategori"]
                results.append(place)
        else:
            if force and os.path.exists(json_cek):
                print(f"   🔄 Force update, scrape ulang...")
            data = run_actor({
                "searchStringsArray"       : [row["nama"]],
                "maxCrawledPlacesPerSearch": 1,
                "includeReviews"           : True,
                "maxReviews"               : 30,
                "language"                 : "id"
            })

            if data:
                data[0]["kategori"] = row["kategori"]
                results.extend(data)
                nama   = data[0].get("title", row["nama"])
                folder = os.path.join(OUTPUT_DIR, get_folder(nama))
                os.makedirs(folder, exist_ok=True)
                with open(os.path.join(folder,"ulasan_mentah.json"),"w",encoding="utf-8") as f:
                    json.dump(data[0], f, ensure_ascii=False, indent=2)
            else:
                print("   ⚠️  Tidak ada data.")
                
        save_checkpoint(i+1)
    clear_checkpoint()
    print(f"\n✅ Scraping selesai: {len(results)} tempat")
    return results

# ════════════════════════════════════════════════════
# MODUL 3 — PROSES SENTIMEN
# ════════════════════════════════════════════════════
def proses_sentimen(results: list = None, pipe=None, force: bool = False):  # ← tambah force
    print("\n" + "="*55)
    print("🧠 MODUL 3 — PROSES SENTIMEN INDOBERT")
    print("="*55)

    if pipe is None:
        pipe = load_indobert()

    if results is None:
        master_map = {}
        if os.path.exists(MASTER_FILE):
            df_m = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
            for _, row in df_m.iterrows():
                master_map[get_folder(str(row["nama"]))] = row["kategori"]
        results = []
        for folder_name in sorted(os.listdir(OUTPUT_DIR)):
            folder_path = os.path.join(OUTPUT_DIR, folder_name)
            if not os.path.isdir(folder_path): continue
            json_mentah = os.path.join(folder_path, "ulasan_mentah.json")
            if os.path.exists(json_mentah):
                with open(json_mentah,"r",encoding="utf-8") as f:
                    place = json.load(f)
                    place["kategori"] = master_map.get(folder_name, "Lainnya")
                    results.append(place)

    all_summary = []
    for place in results:
        nama    = place.get("title","unknown")
        folder  = os.path.join(OUTPUT_DIR, get_folder(nama))
        os.makedirs(folder, exist_ok=True)
        reviews = place.get("reviews",[])
        kat     = place.get("kategori","Lainnya")

        print(f"\n📍 {nama} [{kat}]")

        json_out = os.path.join(folder,"ulasan_sentimen.json")

        if os.path.exists(json_out) and not force:
            # ← SEBELUMNYA tidak ada "and not force"
            print("   📂 Sudah ada sentimen, skip.")
            with open(json_out,"r",encoding="utf-8") as f:
                data = json.load(f)
            all_summary.append({
                k:v for k,v in data.items() if k!="ulasan"
            } | {"key":get_folder(nama),"kategori":kat})
            continue

        if force and os.path.exists(json_out):
            print("   🔄 Force update, proses sentimen ulang...")

        if not reviews:
            print("   ⚠️  Tidak ada ulasan.")
            continue

        rows = []
        for r in reviews:
            rows.append({
                "Kategori"     : kat,
                "Tempat"       : nama,
                "Rating Tempat": place.get("totalScore",""),
                "Total Ulasan" : place.get("reviewsCount",""),
                "Nama Reviewer": r.get("name") or "",
                "Bintang"      : r.get("stars") or "",
                "Tanggal"      : r.get("publishedAtDate") or "",
                "Ulasan"       : (r.get("text") or "").replace("\n"," "),
            })

        df = pd.DataFrame(rows)
        df = df[df["Ulasan"].str.strip() != ""]
        preproc               = df["Ulasan"].apply(preprocess)
        df["teks_cleaned"]    = preproc.apply(lambda x: x["cleaned"])
        df["teks_normalized"] = preproc.apply(lambda x: x["normalized"])
        df["teks_final"]      = preproc.apply(lambda x: x["final"])
        df["topik"]           = df["teks_final"].apply(detect_topic)
        df = df[df["teks_final"].str.strip() != ""]

        print(f"   🔍 Analisis {len(df)} ulasan...")
        sentiments           = [predict(pipe,t) for t in df["teks_final"]]
        df["sentimen"]       = [s["label"] for s in sentiments]
        df["sentimen_score"] = [s["score"] for s in sentiments]

        total   = len(df)
        positif = int((df["sentimen"]=="Positif").sum())
        netral  = int((df["sentimen"]=="Netral").sum())
        negatif = int((df["sentimen"]=="Negatif").sum())
        rating  = place.get("totalScore",0)

        print(f"   ⭐ {rating} | ✅{positif} ➖{netral} ❌{negatif}")

        summary = {
            "key"           : get_folder(nama),
            "kategori"      : kat,
            "tempat"        : nama,
            "rating"        : rating,
            "total_ulasan"  : total,
            "positif"       : positif,
            "netral"        : netral,
            "negatif"       : negatif,
            "persen_positif": round(positif/total*100,1),
            "persen_netral" : round(netral/total*100,1),
            "persen_negatif": round(negatif/total*100,1),
            "ulasan"        : df[[
                "Kategori","Nama Reviewer","Bintang","Tanggal",
                "Ulasan","teks_final","topik","sentimen","sentimen_score"
            ]].to_dict(orient="records"),
        }

        with open(json_out,"w",encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        df.to_csv(os.path.join(folder,"ulasan_sentimen.csv"), index=False, encoding="utf-8-sig")
        print(f"   💾 {json_out}")

        all_summary.append({k:v for k,v in summary.items() if k!="ulasan"})

    _simpan_summary(all_summary)
    return all_summary
# ════════════════════════════════════════════════════
# MODUL 4 — SCAN & UPDATE SUMMARY
# ════════════════════════════════════════════════════
def scan_output():
    print("\n" + "="*55)
    print("🔍 MODUL 4 — SCAN & UPDATE SUMMARY")
    print("="*55)
    master_map = {}
    if os.path.exists(MASTER_FILE):
        df_m = pd.read_csv(MASTER_FILE, encoding="utf-8-sig")
        for _, row in df_m.iterrows():
            master_map[get_folder(str(row["nama"]))] = {
                "kategori": str(row.get("kategori","Lainnya")),
                "nama"    : str(row["nama"]),
            }
    print(f"✅ Master: {len(master_map)} tempat")
    summary = []
    for folder_name in sorted(os.listdir(OUTPUT_DIR)):
        folder_path = os.path.join(OUTPUT_DIR, folder_name)
        if not os.path.isdir(folder_path): continue
        info     = master_map.get(folder_name, {})
        kategori = info.get("kategori","Lainnya")
        json_sentimen = os.path.join(folder_path,"ulasan_sentimen.json")
        json_mentah   = os.path.join(folder_path,"ulasan_mentah.json")
        if os.path.exists(json_sentimen):
            with open(json_sentimen,"r",encoding="utf-8") as f:
                data = json.load(f)
            nama = data.get("tempat") or info.get("nama") or folder_name
            summary.append({
                "key"           : folder_name,
                "kategori"      : kategori,
                "tempat"        : nama,
                "rating"        : float(data.get("rating") or 0),
                "total_ulasan"  : int(data.get("total_ulasan") or 0),
                "positif"       : int(data.get("positif") or 0),
                "netral"        : int(data.get("netral") or 0),
                "negatif"       : int(data.get("negatif") or 0),
                "persen_positif": float(data.get("persen_positif") or 0),
                "persen_netral" : float(data.get("persen_netral") or 0),
                "persen_negatif": float(data.get("persen_negatif") or 0),
            })
            print(f"✅ {nama} [{kategori}]")
        elif os.path.exists(json_mentah):
            with open(json_mentah,"r",encoding="utf-8") as f:
                data = json.load(f)
            nama = data.get("title") or info.get("nama") or folder_name
            summary.append({
                "key"           : folder_name,
                "kategori"      : kategori,
                "tempat"        : nama,
                "rating"        : float(data.get("totalScore") or 0),
                "total_ulasan"  : int(data.get("reviewsCount") or 0),
                "positif"       : 0, "netral":0, "negatif":0,
                "persen_positif": 0.0,"persen_netral":0.0,"persen_negatif":0.0,
            })
            print(f"⚠️  {nama} [{kategori}] (belum sentimen)")
    _simpan_summary(summary)
    print(f"\n✅ Summary: {len(summary)} tempat → {SUMMARY_FILE}")
    return summary
def _simpan_summary(summary: list):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(SUMMARY_FILE,"w",encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
# ════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════
def tampilkan_menu():
    print("\n" + "="*55)
    print("  🗺️  GOOGLE MAPS PIPELINE — GRESIK")
    print("="*55)
    print("  1. Buat master tempat")
    print("  2. Scraping ulasan")
    print("  3. Proses sentimen")
    print("  4. Scan & update summary")
    print("  5. Jalankan semua (1→2→3→4)")
    print("  0. Keluar")
    print("="*55)
    return input("Pilih menu: ").strip()


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "all":
            # Pakai cache — tidak update ulasan baru
            cari_tempat()
            results = scraping_ulasan(force=False)
            pipe    = load_indobert()
            proses_sentimen(results, pipe, force=False)
            scan_output()
        elif arg == "update":
            # ✅ Ambil ulasan baru — scrape & sentimen ulang semua
            results = scraping_ulasan(force=True)
            pipe    = load_indobert()
            proses_sentimen(results, pipe, force=True)
            scan_output()
        elif arg == "scrape":
            scraping_ulasan(force=False)
        elif arg == "scrape-update":
            scraping_ulasan(force=True)
        elif arg == "sentimen":
            pipe = load_indobert()
            proses_sentimen(pipe=pipe, force=False)
        elif arg == "scan":
            scan_output()
        sys.exit(0)

    # Mode interaktif
    while True:
        pilihan = tampilkan_menu()
        if pilihan == "1":
            cari_tempat()
        elif pilihan == "2":
            scraping_ulasan(force=False)
        elif pilihan == "3":
            pipe = load_indobert()
            proses_sentimen(pipe=pipe, force=False)
        elif pilihan == "4":
            scan_output()
        elif pilihan == "5":
            # Tanya dulu mau update atau pakai cache
            mode = input("  Update ulasan baru? (y/n): ").strip().lower()
            force = mode == "y"
            cari_tempat()
            results = scraping_ulasan(force=force)
            pipe    = load_indobert()
            proses_sentimen(results, pipe, force=force)
            scan_output()
        elif pilihan == "0":
            print("👋 Keluar.")
            break