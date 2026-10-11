import json
from pathlib import Path

log_path = Path(r"C:\Users\piard\.gemini\antigravity\brain\969d1f32-4952-4f86-908a-64f048e38b01\.system_generated\tasks\task-1336.log")
data = json.loads(log_path.read_text(encoding="utf-8"))

for v, periods in data.items():
    print(f"\n=================== {v} ===================")
    for p, sub in periods.items():
        r = sub["raw"]
        f = sub["filtered"]
        print(f"[{p.upper()}] HAM: {r['net_r']} R | WR: %{r['wr']} | PF: {r['pf']} | Islem: {r['total_trades']} (FX: {r['fx_net_r']}R, Kripto: {r['crypto_net_r']}R)")
        print(f"      FIL: {f['net_r']} R | WR: %{f['wr']} | PF: {f['pf']} | Islem: {f['total_trades']}")
