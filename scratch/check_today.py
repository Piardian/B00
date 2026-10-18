import json

with open('data/trade_ledger.json', 'r', encoding='utf-8') as f:
    closed = json.load(f)

with open('data/active_trades.json', 'r', encoding='utf-8') as f:
    active = json.load(f)

today_closed = [t for t in closed if '2026-10-17' in t.get('closed_at', '') or '2026-10-17' in t.get('opened_at', '')]
print(f"Today's closed trades: {len(today_closed)}")
for t in today_closed:
    print(t['symbol'], t['direction'], t.get('close_reason'), t.get('r_result'), t.get('opened_at'), t.get('closed_at'))

today_active = [t for t in active if '2026-10-17' in t.get('opened_at', '')]
print(f"\nToday's active trades: {len(today_active)}")
for t in today_active:
    print(t['symbol'], t['direction'], t.get('status'), t.get('current_sl'), t.get('entry'), t.get('opened_at'))
