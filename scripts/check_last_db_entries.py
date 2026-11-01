import sqlite3
import pandas as pd

conn = sqlite3.connect("data/execution_observations.sqlite3")
cur = conn.cursor()

print("--- Last 10 rows in bars table ---")
cur.execute("SELECT symbol, timeframe, bar_time, first_seen_at FROM bars ORDER BY first_seen_at DESC LIMIT 10")
for r in cur.fetchall():
    print(r)

print("\n--- Last 5 macro snapshots ---")
cur.execute("SELECT available_at, payload FROM macro_snapshots ORDER BY available_at DESC LIMIT 5")
for r in cur.fetchall():
    print(r[0])
    
conn.close()
