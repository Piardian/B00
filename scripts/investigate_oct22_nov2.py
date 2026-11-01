import sqlite3
import os
import json
from pathlib import Path
from datetime import datetime

print("=== 1. DB TABLES & LAST ENTRIES ===")
db_path = Path("data/execution_observations.sqlite3")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    for t in tables:
        tname = t[0]
        cur.execute(f"SELECT COUNT(*) FROM {tname}")
        cnt = cur.fetchone()[0]
        cur.execute(f"SELECT * FROM {tname} ORDER BY rowid DESC LIMIT 1")
        last_row = cur.fetchone()
        print(f"Table {tname}: count={cnt}")
        print(f"  Last row: {last_row}")
        
        # Check date range
        # Let's inspect column names
        cur.execute(f"PRAGMA table_info({tname})")
        cols = [c[1] for c in cur.fetchall()]
        print(f"  Columns: {cols}")
        if "first_seen_at" in cols:
            cur.execute(f"SELECT MIN(first_seen_at), MAX(first_seen_at) FROM {tname}")
            print(f"  first_seen_at range: {cur.fetchone()}")
        if "datetime" in cols:
            cur.execute(f"SELECT MIN(datetime), MAX(datetime) FROM {tname}")
            print(f"  datetime range: {cur.fetchone()}")
    conn.close()

print("\n=== 2. TELEMETRY LOGS ===")
telem_path = Path("data/engine_telemetry.jsonl")
if telem_path.exists():
    lines = telem_path.read_text(encoding="utf-8").strip().splitlines()
    print(f"Telemetry lines: {len(lines)}")
    if lines:
        print("First line:", lines[0][:200])
        print("Last 5 lines:")
        for l in lines[-5:]:
            print("  ", l[:200])
else:
    print("Telemetry file does not exist in data/engine_telemetry.jsonl")

# Look for other telemetry files
for p in Path("data").glob("*telem*"):
    print("Found telem file:", p)
for p in Path(".").glob("*telem*"):
    print("Found telem file:", p)

print("\n=== 3. ACTIVE TRADES & CLOSED LEDGER ===")
active_path = Path("data/active_trades.json")
if active_path.exists():
    data = json.loads(active_path.read_text(encoding="utf-8"))
    print(f"Active trades count: {len(data)}")
    print("Active trades:", data)

closed_path = Path("data/trade_ledger.json")
if closed_path.exists():
    trades = json.loads(closed_path.read_text(encoding="utf-8"))
    print(f"Closed trades count: {len(trades)}")
    if trades:
        print("Last 3 closed trades:")
        for t in trades[-3:]:
            print(f"  {t.get('symbol')} | {t.get('strategy')} | opened: {t.get('opened_at')} | closed: {t.get('closed_at')} | {t.get('close_reason')} | net_r: {t.get('net_r')}")

print("\n=== 4. RUNTIME LOCK & HEARTBEAT ===")
for lock in Path("data").glob("*.lock"):
    print(f"Lock file: {lock} -> {lock.read_text(encoding='utf-8')}")
for lock in Path("orchestrator").glob("*.lock"):
    print(f"Lock file: {lock} -> {lock.read_text(encoding='utf-8')}")
