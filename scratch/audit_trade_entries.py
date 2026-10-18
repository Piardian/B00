import json

with open('data/trade_ledger.json', 'r', encoding='utf-8') as f:
    closed = json.load(f)

print("=== CHECKING ENTRY vs TP1 vs OPEN TIME ===")
for t in closed[-15:]:
    sym = t['symbol']
    direction = t['direction']
    entry = t['entry']
    sl = t['original_sl']
    tp1 = t['tp1']
    tp2 = t['tp2']
    opened = t.get('opened_at')
    tp1_at = t.get('tp1_hit_at')
    reason = t.get('close_reason')
    r_res = t.get('r_result')
    print(f"\n[{sym} {direction}] opened={opened}")
    print(f"   Entry={entry}, SL={sl}, TP1={tp1}, TP2={tp2}")
    print(f"   TP1 hit at={tp1_at}")
    print(f"   Closed={t.get('closed_at')} reason={reason} r={r_res}")
