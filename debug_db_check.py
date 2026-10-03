import sqlite3

conn = sqlite3.connect('pos.db')
print('alembic_version', conn.execute("SELECT * FROM alembic_version").fetchall())
print('tables', conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall())
conn.close()
