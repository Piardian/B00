import json

with open('data/signal_history.json', 'r', encoding='utf-8') as f:
    hist = json.load(f)

oct16_17 = {k: v for k, v in hist.items() if '2026-10-16' in v.get('time_str', '') or '2026-10-17' in v.get('time_str', '')}
print(f"Total signals on Oct 16-17: {len(oct16_17)}")
for k, v in oct16_17.items():
    s = v.get('signal', {})
    print(f"Key: {k}")
    print(f"  Time: {v.get('time_str')}")
    print(f"  Symbol: {s.get('symbol')} {s.get('direction')} [{s.get('grade')}]")
    print(f"  Entry: {s.get('entry')}, SL: {s.get('stop_loss')}, TP1: {s.get('tp1')}, TP2: {s.get('tp2')}, RR: {s.get('rr_ratio')}, Risk: {s.get('risk_pips')}")
