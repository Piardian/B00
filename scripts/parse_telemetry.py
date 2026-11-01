import json
from pathlib import Path
from collections import Counter
from datetime import datetime

telem_file = Path("telemetry/engine_telemetry.jsonl")
lines = telem_file.read_text(encoding="utf-8").strip().splitlines()
print(f"Total telemetry records: {len(lines)}")

event_counter = Counter()
reasons_counter = Counter()
symbol_counter = Counter()
dates = []

oct22_events = []

for line in lines:
    try:
        record = json.loads(line)
        ev = record.get("event")
        ts = record.get("timestamp") or record.get("datetime")
        event_counter[ev] += 1
        
        data = record.get("data", {})
        sym = data.get("symbol")
        if sym:
            symbol_counter[sym] += 1
            
        reason = data.get("reason")
        if reason:
            reasons_counter[reason] += 1
            
        if ts:
            dates.append(ts)
            if "2026-10-22" <= ts:
                oct22_events.append(record)
    except Exception as e:
        pass

print("\n--- Event Distribution ---")
for ev, cnt in event_counter.most_common():
    print(f"  {ev}: {cnt}")

print("\n--- Rejection / Block Reasons ---")
for r, cnt in reasons_counter.most_common(20):
    print(f"  {r}: {cnt}")

print("\n--- Symbols in Telemetry ---")
for s, cnt in symbol_counter.most_common(20):
    print(f"  {s}: {cnt}")

if dates:
    print(f"\nDate Range: {min(dates)} to {max(dates)}")

print(f"\nTotal events on or after Oct 22: {len(oct22_events)}")

# Analyze what happened on or after Oct 22
oct22_counter = Counter()
oct22_reasons = Counter()
oct22_symbols = Counter()
for rec in oct22_events:
    ev = rec.get("event")
    oct22_counter[ev] += 1
    data = rec.get("data", {})
    if data.get("reason"):
        oct22_reasons[data.get("reason")] += 1
    if data.get("symbol"):
        oct22_symbols[data.get("symbol")] += 1

print("\n--- Events on or after Oct 22 ---")
for ev, cnt in oct22_counter.most_common():
    print(f"  {ev}: {cnt}")

print("\n--- Rejection Reasons on or after Oct 22 ---")
for r, cnt in oct22_reasons.most_common(20):
    print(f"  {r}: {cnt}")

print("\n--- Symbols on or after Oct 22 ---")
for s, cnt in oct22_symbols.most_common(20):
    print(f"  {s}: {cnt}")

# Check any CANDIDATE or SIGNAL events on or after Oct 22
candidates = [r for r in oct22_events if "CANDIDATE" in r.get("event", "") or "SIGNAL" in r.get("event", "")]
print(f"\nCandidates/Signals detected on or after Oct 22: {len(candidates)}")
for c in candidates[:10]:
    print(" ", c)
