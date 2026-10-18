import sys, os
sys.path.insert(0, os.path.abspath("."))
import json
import datetime
from pathlib import Path

# Check active trades file modification time
act_path = Path("data/active_trades.json")
ledger_path = Path("data/trade_ledger.json")

print(f"data/active_trades.json mtime: {datetime.datetime.fromtimestamp(act_path.stat().st_mtime)}")
print(f"data/trade_ledger.json mtime: {datetime.datetime.fromtimestamp(ledger_path.stat().st_mtime)}")

with open(act_path, "r", encoding="utf-8") as f:
    trades = json.load(f)

for t in trades:
    print(f"Trade {t['symbol']}: last_checked_at = {t.get('last_checked_at')}, status = {t.get('status')}")
