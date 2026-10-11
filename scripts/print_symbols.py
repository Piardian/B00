import json
from pathlib import Path

log_path = Path(r"C:\Users\piard\.gemini\antigravity\brain\969d1f32-4952-4f86-908a-64f048e38b01\.system_generated\tasks\task-1336.log")
data = json.loads(log_path.read_text(encoding="utf-8"))
v2_1y = data["v2_weekend_crypto_both_sessions"]["1y"]["raw"]["symbols"]

print("\n--- V2 1 YILLIK SEMBOL PERFORMANSI ---")
for s, st in sorted(v2_1y.items(), key=lambda x: x[1]["net_r"], reverse=True):
    print(f"{s:<8}: Net R: {st['net_r']:>6} R | WR: %{st['wr']:<4} | PF: {st['pf']:<4} | Islem: {st['trades']} (W: {st['wins']}, L: {st['losses']})")

v1_1y = data["v1_weekend_crypto_london_only"]["1y"]["raw"]["symbols"]
print("\n--- V1 1 YILLIK SEMBOL PERFORMANSI ---")
for s, st in sorted(v1_1y.items(), key=lambda x: x[1]["net_r"], reverse=True):
    print(f"{s:<8}: Net R: {st['net_r']:>6} R | WR: %{st['wr']:<4} | PF: {st['pf']:<4} | Islem: {st['trades']} (W: {st['wins']}, L: {st['losses']})")
