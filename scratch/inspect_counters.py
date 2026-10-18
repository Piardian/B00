import json
from datetime import datetime

with open('data/trade_ledger.json', 'r', encoding='utf-8') as f:
    closed_trades = json.load(f)

with open('data/active_trades.json', 'r', encoding='utf-8') as f:
    active_trades = json.load(f)

month_key = "2026-10"

month_closed = [
    t for t in closed_trades
    if (t.get("closed_at") or t.get("opened_at", ""))[:7] == month_key
]

sl_count = sum(1 for t in month_closed if t.get("close_reason") == "STOP_LOSS")
be_count = sum(1 for t in month_closed if t.get("close_reason") == "BREAK_EVEN")
tp2_count = sum(1 for t in month_closed if t.get("close_reason") == "TP2_HIT")

active_tp1 = sum(
    1 for t in active_trades
    if t.get("status") == "TP1_HIT" and (t.get("opened_at", ""))[:7] == month_key
)
closed_tp1 = sum(
    1 for t in month_closed
    if t.get("close_reason") in ["BREAK_EVEN", "TP2_HIT"] or t.get("tp1_hit") or t.get("tp1_hit_at")
)
tp1_count = active_tp1 + closed_tp1
net_r = sum(float(t.get("r_result", 0.0)) for t in month_closed)

print("=== MONTHLY COUNTERS (October 2026) ===")
print(f"Total closed trades in month: {len(month_closed)}")
print(f"sl_count: {sl_count}")
print(f"be_count: {be_count}")
print(f"tp2_count: {tp2_count}")
print(f"active_tp1: {active_tp1}")
print(f"closed_tp1: {closed_tp1}")
print(f"tp1_count: {tp1_count}")
print(f"net_r: {net_r:.2f}R")

print("\n=== RECENT CLOSED TRADES ===")
for t in month_closed[-15:]:
    print(f"ID: {t['id']}, sym: {t['symbol']}, reason: {t.get('close_reason')}, r: {t.get('r_result')}, opened: {t.get('opened_at')}, closed: {t.get('closed_at')}")
