"""
Koreksi Sentimen Berdasarkan Bintang — Google Maps
====================================================
Memperbaiki hasil sentimen yang sudah ada (ulasan_sentimen.json)
tanpa perlu load model IndoBERT lagi. Cepat dan aman dijalankan berkali-kali.

Jalankan:
    python koreksi_sentimen_bintang.py
"""

import json
import os

OUTPUT_DIR   = "output"
SUMMARY_FILE = os.path.join(OUTPUT_DIR, "semua_tempat_summary.json")


def koreksi_label(label_model: str, bintang) -> str:
    try:
        bintang = int(bintang)
    except (ValueError, TypeError):
        return label_model

    if bintang >= 4:
        if label_model == "Negatif":
            return "Positif"
        return label_model
    elif bintang <= 2 and bintang >= 1:
        if label_model == "Positif":
            return "Negatif"
        return label_model
    else:
        return label_model


def proses_semua():
    folders = sorted(os.listdir(OUTPUT_DIR))
    total_tempat_diubah = 0
    total_ulasan_diubah = 0
    summary_baru = []

    for folder_name in folders:
        folder_path = os.path.join(OUTPUT_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        json_path = os.path.join(folder_path, "ulasan_sentimen.json")
        if not os.path.exists(json_path):
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        ulasan_list = data.get("ulasan", [])
        if not ulasan_list:
            continue

        berubah_di_tempat_ini = False

        for u in ulasan_list:
            label_lama = u.get("sentimen", "")
            bintang    = u.get("Bintang", "")
            label_baru = koreksi_label(label_lama, bintang)
            if label_baru != label_lama:
                u["sentimen"] = label_baru
                berubah_di_tempat_ini = True
                total_ulasan_diubah += 1

        if berubah_di_tempat_ini:
            total_tempat_diubah += 1

        total_u = len(ulasan_list)
        positif = sum(1 for u in ulasan_list if u.get("sentimen") == "Positif")
        netral  = sum(1 for u in ulasan_list if u.get("sentimen") == "Netral")
        negatif = sum(1 for u in ulasan_list if u.get("sentimen") == "Negatif")

        data["positif"]        = positif
        data["netral"]         = netral
        data["negatif"]        = negatif
        data["persen_positif"] = round(positif / total_u * 100, 1) if total_u else 0
        data["persen_netral"]  = round(netral  / total_u * 100, 1) if total_u else 0
        data["persen_negatif"] = round(negatif / total_u * 100, 1) if total_u else 0

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        csv_path = os.path.join(folder_path, "ulasan_sentimen.csv")
        if os.path.exists(csv_path):
            import pandas as pd
            df = pd.read_csv(csv_path)
            if "sentimen" in df.columns and "Bintang" in df.columns:
                df["sentimen"] = [
                    koreksi_label(lbl, bt) for lbl, bt in zip(df["sentimen"], df["Bintang"])
                ]
                df.to_csv(csv_path, index=False, encoding="utf-8-sig")

        summary_baru.append({
            "key"           : folder_name,
            "kategori"      : data.get("kategori", "Lainnya"),
            "tempat"        : data.get("tempat", folder_name),
            "rating"        : data.get("rating", 0),
            "total_ulasan"  : total_u,
            "positif"       : positif,
            "netral"        : netral,
            "negatif"       : negatif,
            "persen_positif": data["persen_positif"],
            "persen_netral" : data["persen_netral"],
            "persen_negatif": data["persen_negatif"],
        })

        if berubah_di_tempat_ini:
            print(f"✅ Dikoreksi: {data.get('tempat', folder_name)}")

    if os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            summary_lama = json.load(f)
        key_baru = {s["key"] for s in summary_baru}
        for item in summary_lama:
            if item.get("key") not in key_baru:
                summary_baru.append(item)

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary_baru, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"Selesai!")
    print(f"Tempat yang dikoreksi : {total_tempat_diubah}")
    print(f"Ulasan yang dikoreksi : {total_ulasan_diubah}")
    print(f"Summary disimpan ke   : {SUMMARY_FILE}")


if __name__ == "__main__":
    proses_semua()