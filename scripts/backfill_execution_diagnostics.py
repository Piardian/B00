"""Download recent 1m data into a separate retrospective diagnostics archive.

This is not a reconstruction of the original live feed or a strategy backtest.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sfp_orb_engine.execution_observer import ExecutionObserver
from sfp_orb_engine.execution_policy import utc_time, completed_bars, NO_FILL_REASONS, TRT
from sfp_orb_engine.data_provider import MarketDataProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--symbols", nargs="+", help="Optional subset of the ledger's logical symbols")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Use a fresh output directory")
    args.output.mkdir(parents=True)
    (args.output / "frames").mkdir()
    start = datetime.fromisoformat(args.start).replace(tzinfo=TRT).astimezone(timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=TRT).astimezone(timezone.utc)
    ledger = json.loads((ROOT / "data/trade_ledger.json").read_text(encoding="utf-8"))
    trades = [t for t in ledger if t.get("close_reason") not in NO_FILL_REASONS and t.get("filled_at")
              and start <= utc_time(t["closed_at"], legacy_local=True) < end]
    provider = MarketDataProvider()
    observer = ExecutionObserver(args.output / "retrospective.sqlite3")
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(),
                "purpose": "Retrospective price-path diagnostics; not original-feed replay",
                "source": "Yahoo 1m via existing MarketDataProvider._fetch_yfinance",
                "provider_module_sha256": hashlib.sha256((ROOT / "sfp_orb_engine/data_provider.py").read_bytes()).hexdigest(),
                "live_ledger_sha256": hashlib.sha256((ROOT / "data/trade_ledger.json").read_bytes()).hexdigest(),
                "symbols": []}
    for symbol in dict.fromkeys(t["symbol"] for t in trades):
        if args.symbols and symbol not in args.symbols:
            continue
        observed = datetime.now(timezone.utc)
        # Use the existing source mapping, including its futures proxies.
        # Do not call fetch_candles: it would mix caches/feeds and write live caches.
        frame = completed_bars(provider._fetch_yfinance(symbol, "1m", 10000), 1, observed)
        row = {"symbol": symbol, "observed_at": observed.isoformat(), "rows": len(frame)}
        if len(frame):
            clean = symbol.replace("/", "")
            raw = frame.to_csv(index=False)
            (args.output / "frames" / f"{clean}_1m.csv").write_text(raw, encoding="utf-8")
            row.update(first=frame.datetime.min().isoformat(), last=frame.datetime.max().isoformat(),
                       sha256=hashlib.sha256(raw.encode()).hexdigest())
            source = "historical_yahoo_1m; retrospective_download; not_original_live_feed"
            if symbol == "NAS100":
                source += "; ticker=QQQ; shared_registry_proxy"
            observer.archive_bars(symbol, "1m", frame, observed.isoformat(), source)
        manifest["symbols"].append(row)
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(symbol, len(frame), row.get("first"), row.get("last"), flush=True)


if __name__ == "__main__":
    main()
