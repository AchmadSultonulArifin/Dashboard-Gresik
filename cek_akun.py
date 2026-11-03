import sqlite3
import pymysql

print("=== MySQL: dashboard_gresik ===")
c = pymysql.connect(host="127.0.0.1", user="root", password="", database="dashboard_gresik")
cur = c.cursor()
cur.execute("SHOW TABLES")
tabel = [r[0] for r in cur.fetchall()]
print("Tabel:", tabel)
if "users" in tabel:
    cur.execute("SELECT id, username, email, role FROM users")
    for row in cur.fetchall():
        print(row)
c.close()

print("\n=== SQLite: tabel accounts ===")
s = sqlite3.connect("accounts.db")
cols = [r[1] for r in s.execute("PRAGMA table_info(accounts)")]
print("Kolom:", cols)
for row in s.execute("SELECT * FROM accounts LIMIT 10"):
    print(row)