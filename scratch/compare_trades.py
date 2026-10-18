import json

with open('data/trade_ledger.json', 'r', encoding='utf-8') as f:
    closed = json.load(f)

# Trades from Oct 10 and 11 (the early test/dev trades before Begonya 00 launch on Oct 12)
early_trades = [t for t in closed if ('2026-10-10' in t.get('opened_at', '') or '2026-10-11' in t.get('opened_at', ''))]
begonya00_trades = [t for t in closed if not ('2026-10-10' in t.get('opened_at', '') or '2026-10-11' in t.get('opened_at', ''))]

early_r = sum(float(t.get('r_result', 0.0)) for t in early_trades)
early_sl = sum(1 for t in early_trades if t.get('close_reason') == 'STOP_LOSS')
early_tp = sum(1 for t in early_trades if t.get('close_reason') == 'TP2_HIT')
early_be = sum(1 for t in early_trades if t.get('close_reason') == 'BREAK_EVEN')

begonya_r = sum(float(t.get('r_result', 0.0)) for t in begonya00_trades)
begonya_sl = sum(1 for t in begonya00_trades if t.get('close_reason') == 'STOP_LOSS')
begonya_tp = sum(1 for t in begonya00_trades if t.get('close_reason') == 'TP2_HIT')
begonya_be = sum(1 for t in begonya00_trades if t.get('close_reason') == 'BREAK_EVEN')

print("=== EARLY DEV / TEST TRADES (Oct 10-11) ===")
print(f"Count: {len(early_trades)}")
print(f"SL count: {early_sl}")
print(f"TP2 count: {early_tp}")
print(f"BE count: {early_be}")
print(f"Net R: {early_r:.2f}R")

print("\n=== BEGONYA 00 OFFICIAL LIVE TRADES (From Oct 12 onwards) ===")
print(f"Count: {len(begonya00_trades)}")
print(f"SL count: {begonya_sl}")
print(f"TP2 count: {begonya_tp}")
print(f"BE count: {begonya_be}")
print(f"Net R: {begonya_r:.2f}R")
for t in begonya00_trades:
    print(f"  {t['symbol']} {t['direction']} -> {t.get('close_reason')} ({t.get('r_result')}R) opened={t.get('opened_at')[:16]}")
