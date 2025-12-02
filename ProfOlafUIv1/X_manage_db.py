import sqlite3

conn = sqlite3.connect("dababase.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
#cursor.execute("SELECT * FROM conf_rank;")
print(cursor.fetchall())  # list of tables
conn.close()