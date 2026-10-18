import json

with open('data/trade_ledger.json', 'r', encoding='utf-8') as f:
    closed = json.load(f)

print(f"Total closed trades: {len(closed)}")
for t in closed[-10:]:
    opened = str(t.get('opened_at', ''))[:16]
    closed_at = str(t.get('closed_at', ''))[:16]
    print(f"ID: {t['id']}, sym: {t['symbol']}, reason: {t.get('close_reason')}, r: {t.get('r_result')}, opened: {opened}, closed: {closed_at}")
