import sys, os
sys.path.insert(0, os.path.abspath("."))
import psutil
import json
import datetime
from pathlib import Path

# Look for any recent log files in data, telemetry, orchestrator, root
log_files = []
for p in Path(".").rglob("*.log"):
    if not ".git" in str(p) and not ".system_generated" in str(p):
        log_files.append((p, p.stat().st_mtime))

log_files.sort(key=lambda x: x[1], reverse=True)
print("Recent log files:")
for f, m in log_files[:10]:
    print(f"  {f} - {datetime.datetime.fromtimestamp(m)}")

# Check orchestrator lock
lock = Path("orchestrator/begonya00_orchestrator.lock")
if lock.exists():
    print(f"Orchestrator lock content: {lock.read_text().strip()}")

# Check runtime lock
rt_lock = Path("data/runtime.lock")
if rt_lock.exists():
    print(f"Runtime lock content: {rt_lock.read_text().strip()}")
else:
    print("Runtime lock does NOT exist.")

# Check telemetry
telem = Path("telemetry/engine_telemetry.jsonl")
if telem.exists():
    with open(telem, "r", encoding="utf-8") as tf:
        lines = tf.readlines()
    print(f"Total telemetry lines: {len(lines)}")
    if lines:
        print("Last telemetry line:", lines[-1].strip()[:200])
