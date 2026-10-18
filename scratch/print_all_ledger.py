import json

with open('data/trade_ledger.json', 'r', encoding='utf-8') as f:
    closed_trades = json.load(f)

print(f"Total trades in ledger: {len(closed_trades)}")
for i, t in enumerate(closed_trades):
    print(f"[{i+1}] ID: {t.get('id')}, sym: {t.get('symbol')}, status: {t.get('status')}, reason: {t.get('close_reason')}, r: {t.get('r_result')}, opened: {t.get('opened_at')}, closed: {t.get('closed_at')}")
