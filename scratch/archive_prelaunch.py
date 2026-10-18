import json
from pathlib import Path

DATA_DIR = Path("data")
LEDGER_FILE = DATA_DIR / "trade_ledger.json"
ARCHIVE_FILE = DATA_DIR / "trade_ledger_prelaunch_archive.json"

with open(LEDGER_FILE, "r", encoding="utf-8") as f:
    all_trades = json.load(f)

# The pre-launch dev / test trades took place on Oct 10 and Oct 11 before Begonya 00 went live
prelaunch = [t for t in all_trades if ("2026-10-10" in t.get("opened_at", "") or "2026-10-11" in t.get("opened_at", ""))]
begonya_live = [t for t in all_trades if not ("2026-10-10" in t.get("opened_at", "") or "2026-10-11" in t.get("opened_at", ""))]

print(f"Total trades: {len(all_trades)}")
print(f"Pre-launch test trades to archive: {len(prelaunch)}")
print(f"Official Begonya 00 live trades: {len(begonya_live)}")

# Save archive
with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
    json.dump(prelaunch, f, indent=2)

# Update official ledger
with open(LEDGER_FILE, "w", encoding="utf-8") as f:
    json.dump(begonya_live, f, indent=2)

# Compute new stats
net_r = sum(float(t.get("r_result", 0.0)) for t in begonya_live)
wins = sum(1 for t in begonya_live if t.get("r_result", 0.0) > 0)
losses = sum(1 for t in begonya_live if t.get("r_result", 0.0) < 0)
total_closed = len(begonya_live)

print("\nOfficial Begonya 00 Ledger Updated Successfully:")
print(f"Total Closed: {total_closed}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
print(f"Net R: {net_r:+.2f}R")
