"""
Proses sentimen untuk semua folder yang sudah ada ulasan_mentah.json
tapi belum punya ulasan_sentimen.json
"""
import re
import json
import os
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch

OUTPUT_DIR   = "output"
SUMMARY_FILE = "output/semua_tempat_summary.json"

# ── Salin fungsi dari googlemaps.py ──────────────────
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
LABEL_MAP = {"LABEL_0":"Negatif","LABEL_1":"Netral","LABEL_2":"Positif"}
KATEGORI_MAP = {
    "kantor":"Pemerintahan","dinas":"Pemerintahan","kecamatan":"Pemerintahan",
    "kelurahan":"Pemerintahan","bupati":"Pemerintahan","sekretariat":"Pemerintahan",
    "dprd":"Pemerintahan","polsek":"Pemerintahan","polres":"Pemerintahan",
    "koramil":"Pemerintahan","kodim":"Pemerintahan","kejaksaan":"Pemerintahan",
    "pengadilan":"Pemerintahan","rsud":"Kesehatan","rsu":"Kesehatan",
    "puskesmas":"Kesehatan","klinik":"Kesehatan","apotek":"Kesehatan",
    "rumah_sakit":"Kesehatan","sma":"Pendidikan","smk":"Pendidikan",
    "smp":"Pendidikan","universitas":"Pendidikan","kampus":"Pendidikan",
    "sekolah":"Pendidikan","madrasah":"Pendidikan","pesantren":"Pendidikan",
    "disdukcapil":"Pelayanan Publik","samsat":"Pelayanan Publik",
    "mall_pelayanan":"Pelayanan Publik","imigrasi":"Pelayanan Publik",
    "bpjs":"Pelayanan Publik","pos":"Pelayanan Publik","kua":"Pelayanan Publik",
    "bpn":"Pelayanan Publik","pajak":"Pelayanan Publik",
    "brilink":"Perbankan","atm":"Perbankan","bank":"Perbankan",
    "bri":"Perbankan","bni":"Perbankan","bca":"Perbankan",
    "mandiri":"Perbankan","btn":"Perbankan","bpr":"Perbankan",
    "pegadaian":"Perbankan","koperasi":"Perbankan",
    "wisata":"Wisata","pantai":"Wisata","taman":"Wisata",
    "museum":"Wisata","makam":"Wisata","masjid":"Wisata",
    "petrokimia":"Industri","semen":"Industri","pabrik":"Industri",
    "pelabuhan":"Industri","terminal":"Industri",
}

def get_kategori(folder_name):
    for key, kat in KATEGORI_MAP.items():
        if key in folder_name:
            return kat
    return "Lainnya"

def get_folder(nama):
    return re.sub(r'[^a-z0-9]+', '_', nama.lower()).strip('_')

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
    text = text.lower()
    for topic, keywords in TOPIC_RULES.items():
        for kw in keywords:
            if kw in text: return topic
    return "Lainnya"

def predict_sentiment(pipe, text):
    if not text or len(text.strip())<3: return {"label":"Netral","score":0.0}
    try:
        r = pipe(text[:512])[0]
        return {"label":LABEL_MAP.get(r["label"],r["label"]),"score":round(r["score"],4)}
    except: return {"label":"Error","score":0.0}

# ── Load model ────────────────────────────────────────
print("🤖 Memuat model IndoBERT...")
MODEL_NAME = "mdhugol/indonesia-bert-sentiment-classification"
tokenizer  = AutoTokenizer.from_pretrained(MODEL_NAME)
model      = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
pipe = pipeline(
    "sentiment-analysis", model=model, tokenizer=tokenizer,
    device=0 if torch.cuda.is_available() else -1,
    truncation=True, max_length=512,
)
print("✅ Model siap!\n")

# ── Proses semua folder ───────────────────────────────
all_summary = []
folders     = sorted(os.listdir(OUTPUT_DIR))
total       = len([f for f in folders if os.path.isdir(os.path.join(OUTPUT_DIR, f))])
diproses    = 0
diskip      = 0

for i, folder_name in enumerate(folders):
    folder_path   = os.path.join(OUTPUT_DIR, folder_name)
    if not os.path.isdir(folder_path):
        continue

    json_sentimen = os.path.join(folder_path, "ulasan_sentimen.json")
    json_mentah   = os.path.join(folder_path, "ulasan_mentah.json")

    # ── Sudah ada sentimen — langsung load ───────────
    if os.path.exists(json_sentimen):
        with open(json_sentimen,"r",encoding="utf-8") as f:
            data = json.load(f)
        all_summary.append({
            "key"           : folder_name,
            "kategori"      : data.get("kategori") or get_kategori(folder_name),
            "tempat"        : data.get("tempat", folder_name),
            "rating"        : data.get("rating", 0),
            "total_ulasan"  : data.get("total_ulasan", 0),
            "positif"       : data.get("positif", 0),
            "netral"        : data.get("netral", 0),
            "negatif"       : data.get("negatif", 0),
            "persen_positif": data.get("persen_positif", 0),
            "persen_netral" : data.get("persen_netral", 0),
            "persen_negatif": data.get("persen_negatif", 0),
        })
        print(f"[{i+1}/{total}] 📂 Load: {data.get('tempat', folder_name)}")
        continue

    # ── Belum ada sentimen — proses dari mentah ───────
    if not os.path.exists(json_mentah):
        diskip += 1
        continue

    with open(json_mentah,"r",encoding="utf-8") as f:
        place = json.load(f)

    nama    = place.get("title", folder_name)
    reviews = place.get("reviews", [])
    kat     = get_kategori(folder_name)

    print(f"[{i+1}/{total}] 🔍 Proses: {nama} ({len(reviews)} ulasan)")

    if not reviews:
        all_summary.append({
            "key":folder_name,"kategori":kat,"tempat":nama,
            "rating":place.get("totalScore",0),"total_ulasan":0,
            "positif":0,"netral":0,"negatif":0,
            "persen_positif":0,"persen_netral":0,"persen_negatif":0,
        })
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

    preproc = df["Ulasan"].apply(preprocess)
    df["teks_cleaned"]    = preproc.apply(lambda x: x["cleaned"])
    df["teks_normalized"] = preproc.apply(lambda x: x["normalized"])
    df["teks_final"]      = preproc.apply(lambda x: x["final"])
    df["topik"]           = df["teks_final"].apply(detect_topic)
    df = df[df["teks_final"].str.strip() != ""]

    sentiments           = [predict_sentiment(pipe, t) for t in df["teks_final"]]
    df["sentimen"]       = [s["label"] for s in sentiments]
    df["sentimen_score"] = [s["score"] for s in sentiments]

    total_u = len(df)
    positif = int((df["sentimen"]=="Positif").sum())
    netral  = int((df["sentimen"]=="Netral").sum())
    negatif = int((df["sentimen"]=="Negatif").sum())
    rating  = place.get("totalScore", 0)

    summary = {
        "kategori"      : kat,
        "tempat"        : nama,
        "rating"        : rating,
        "total_ulasan"  : total_u,
        "positif"       : positif,
        "netral"        : netral,
        "negatif"       : negatif,
        "persen_positif": round(positif/total_u*100,1) if total_u else 0,
        "persen_netral" : round(netral/total_u*100,1)  if total_u else 0,
        "persen_negatif": round(negatif/total_u*100,1) if total_u else 0,
        "ulasan"        : df[[
            "Kategori","Nama Reviewer","Bintang","Tanggal",
            "Ulasan","teks_final","topik","sentimen","sentimen_score"
        ]].to_dict(orient="records"),
    }

    # Simpan JSON sentimen
    with open(json_sentimen,"w",encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Simpan CSV sentimen
    df.to_csv(os.path.join(folder_path,"ulasan_sentimen.csv"), index=False, encoding="utf-8-sig")

    all_summary.append({k:v for k,v in summary.items() if k!="ulasan"} | {"key":folder_name})
    diproses += 1
    print(f"   ✅ {positif}P/{netral}N/{negatif}Neg")

# Simpan summary
with open(SUMMARY_FILE,"w",encoding="utf-8") as f:
    json.dump(all_summary, f, ensure_ascii=False, indent=2)

print(f"\n{'='*50}")
print(f"✅ Selesai! {diproses} diproses, {len(all_summary)} total tempat")
print(f"💾 {SUMMARY_FILE}")