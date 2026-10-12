import sys
import json
from pathlib import Path
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

for name, filename in [("CLOSE MODEL", "data/custom_3m_close_result.json"), ("MIDPOINT MODEL", "data/custom_3m_backtest_result.json")]:
    p = Path(filename)
    if not p.exists():
        continue
    data = json.loads(p.read_text(encoding="utf-8"))
    monthly = defaultdict(lambda: {"trades": 0, "tp2": 0, "be": 0, "sl": 0, "net_r": 0.0})

    for t in data.get("trade_log", []):
        m = t["date"][:7]
        monthly[m]["trades"] += 1
        res = t.get("reason", "")
        if res == "TP2_HIT":
            monthly[m]["tp2"] += 1
        elif res == "BREAK_EVEN":
            monthly[m]["be"] += 1
        elif res == "STOP_LOSS":
            monthly[m]["sl"] += 1
        monthly[m]["net_r"] += t["r_result"]

    print(f"\n==================================================")
    print(f"{name} ({data['period']})")
    print(f"Total: {data['total_trades']} Trades | Net: {data['total_net_r']} | WR: {data['win_rate']}")
    print(f"==================================================")
    for m, s in sorted(monthly.items()):
        wins = s["tp2"] + s["be"]
        wr = round(wins / s["trades"] * 100, 1) if s["trades"] else 0
        print(f"Month: {m} | Trades: {s['trades']:2d} | TP2: {s['tp2']:2d} | BE: {s['be']:2d} | SL: {s['sl']:2d} | WR: %{wr:4.1f} | Net R: {s['net_r']:+.2f}R")
