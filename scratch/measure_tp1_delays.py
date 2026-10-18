import json
import datetime

with open('data/trade_ledger.json', 'r', encoding='utf-8') as f:
    closed = json.load(f)

print("=== CHECKING TP1 HIT DELAYS ===")
for t in closed:
    opened = t.get('opened_at')
    tp1_at = t.get('tp1_hit_at')
    if opened and tp1_at:
        t_open = datetime.datetime.fromisoformat(opened)
        t_tp1 = datetime.datetime.fromisoformat(tp1_at)
        diff_sec = (t_tp1 - t_open).total_seconds()
        print(f"Trade {t['symbol']} ({t['direction']}):")
        print(f"  Entry: {t['entry']}, SL: {t['original_sl']}, TP1: {t['tp1']}, TP2: {t['tp2']}")
        print(f"  Opened at: {opened}")
        print(f"  TP1 at:    {tp1_at}")
        print(f"  DELAY:     {diff_sec:.1f} seconds ({diff_sec/60:.2f} minutes)")
