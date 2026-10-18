import json

with open('data/active_trades.json', 'r', encoding='utf-8') as f:
    trades = json.load(f)
print(f"Total active trades: {len(trades)}")
for t in trades:
    print(f"ID: {t['id']}, Symbol: {t['symbol']}, Dir: {t['direction']}, Entry: {t['entry']}, SL: {t['current_sl']}, TP1: {t['tp1']}, TP2: {t['tp2']}, Status: {t['status']}, RR: {t.get('rr_ratio')}, Risk: {t.get('risk_pips')}")
