import pypyodbc  # pip install pypyodbc

mdb_path = r"E:\513430SXB.mdb"

conn = pypyodbc.connect(r"Driver={Microsoft Access Driver (*.mdb)};DBQ=%s;" % mdb_path)

cursor = conn.cursor()

cursor.execute("SELECT * FROM users")
for row in cursor.fetchall():
    print(row)

conn.close()
