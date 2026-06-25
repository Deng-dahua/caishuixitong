import sqlite3, json

conn = sqlite3.connect('C:/Users/26726/WorkBuddy/2026-06-22-10-40-26/caishuixitong/caishui.db')

# List all tables
print("=== TABLES ===")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(t[0])

# Check for invoice tables
for table_name in [t[0] for t in tables]:
    if 'invoice' in table_name.lower():
        print(f"\n=== {table_name} columns ===")
        cols = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        for c in cols:
            print(f"  {c[1]} ({c[2]})")
        
        # Count
        cnt = conn.execute(f"SELECT COUNT(*) FROM '{table_name}'").fetchone()[0]
        print(f"  Total rows: {cnt}")

conn.close()
