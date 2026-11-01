import json
from pathlib import Path

lines = Path("telemetry/engine_telemetry.jsonl").read_text(encoding="utf-8").strip().splitlines()

for l in lines:
    try:
        rec = json.loads(l)
        ts = rec.get("timestamp") or ""
        if ts >= "2026-10-22":
            data = rec.get("data", {})
            sym = data.get("symbol")
            if sym in ("EUR/USD", "GBP/USD", "XAU/USD"):
                print(f"{ts} | {sym} | event={rec.get('event')} | data={data}")
    except Exception:
        pass
