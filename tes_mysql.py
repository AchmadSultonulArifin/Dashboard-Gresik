import pymysql

for pw in ["Sultonul12", ""]:
    try:
        c = pymysql.connect(host="127.0.0.1", user="root", password=pw)
        print(f"BERHASIL dengan password: '{pw}'")
        cur = c.cursor()
        cur.execute("SHOW DATABASES")
        print([r[0] for r in cur.fetchall()])
        c.close()
        break
    except Exception as e:
        print(f"Gagal dengan password '{pw}':", e)