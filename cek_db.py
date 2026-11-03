import sqlite3

c = sqlite3.connect("accounts.db")
tabel = c.execute("select name from sqlite_master where type='table'").fetchall()
print("Tabel:", tabel)

if ("users",) in tabel:
    for row in c.execute("select id, username, email, role from users"):
        print(row)
else:
    print("Tabel users tidak ada di accounts.db")