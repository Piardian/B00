"""Audit historical inputs and replay the actual live engine in isolation.

No alternative strategy, macro proxy, interpolated candles, or production writes.
Run without --run for a three-month input audit. See docs/EXACT_REPLAY_2025.md.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sfp_orb_engine import config
from sfp_orb_engine.execution_policy import utc_time, TRT, NO_FILL_REASONS

MONTHS = ("2025-01", "2025-06", "2025-11")


def bounds(month):
    start = pd.Timestamp(month + "-01", tz="UTC")
    return start, start + pd.offsets.MonthBegin(1)


def frame_summary(frame, start, end):
    if frame is None or frame.empty:
        return {"returned_rows": 0, "in_range_rows": 0, "out_of_range_rows": 0}
    times = pd.to_datetime(frame.datetime, utc=True)
    inside = times.ge(start) & times.lt(end)
    selected = times[inside]
    return {"returned_rows": len(frame), "in_range_rows": int(inside.sum()),
            "out_of_range_rows": int((~inside).sum()),
            "first_returned": times.min().isoformat(), "last_returned": times.max().isoformat(),
            "first_in_range": selected.min().isoformat() if len(selected) else None,
            "last_in_range": selected.max().isoformat() if len(selected) else None,
            "duplicate_timestamps": int(times.duplicated().sum()),
            "sha256": hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()}


def load_frame(path):
    if not path.exists() and path.suffix == '.csv' and path.with_suffix('.csv.gz').exists():
        path = path.with_suffix('.csv.gz')
    df = pd.read_csv(path)
    required = {"datetime", "open", "high", "low", "close", "volume"}
    if not required <= set(df.columns):
        raise ValueError(f"Missing columns: {path}")
    df["datetime"] = pd.to_datetime(df.datetime, utc=True)
    for col in required - {"datetime"}:
        df[col] = pd.to_numeric(df[col], errors="raise")
    if df[list(required - {"datetime"})].isna().any().any() or df.datetime.duplicated().any():
        raise ValueError(f"NaN or duplicate data: {path}")
    return df.sort_values("datetime").reset_index(drop=True)


def load_gates(path):
    if path is None:
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if not row.get("provenance") or not isinstance(row.get("gate"), dict):
            raise ValueError("Gate rows need provenance and an original gate payload")
        row["available_at"] = utc_time(row["available_at"])
    return sorted(rows, key=lambda row: row["available_at"])


def source_hashes():
    names = ["engine", "outcome_tracker", "sfp_detector", "entry_mechanics", "strict_setup",
             "execution_policy", "orb_detector", "macro_gate_client", "news_guard", "config", "data_provider", "volume_anomaly",
             "execution_observer", "orb_session_context"]
    return {name: hashlib.sha256((ROOT / "sfp_orb_engine" / f"{name}.py").read_bytes()).hexdigest() for name in names}


def audit_month(month, symbols, data_root, gates, mt5=None):
    start, end = bounds(month)
    rows = []
    blockers = []
    if not any(r["available_at"] <= start for r in gates):
        blockers.append("NO_POINT_IN_TIME_MACRO_GATE_AT_START")
    excluded = {x.replace("/", "") for x in config.EXCLUDED_SFP_SYMBOLS}
    for symbol in symbols:
        clean = symbol.replace("/", "")
        if clean in excluded:
            rows.append({"symbol": symbol, "status": "EXCLUDED_BY_LIVE_CONFIG"})
            continue
        for tf in ("1m", "15m", "1h"):
            query_start = start - pd.Timedelta(days=65) if tf != "1m" else start
            frame = None
            source = None
            if data_root:
                path = data_root / f"{clean}_{tf}.csv"
                if path.exists() or path.with_suffix('.csv.gz').exists():
                    frame = load_frame(path)
                    source = str(path)
            elif mt5 is not None:
                source = "MT5 copy_rates_range; broker quotes are not certified live-feed history"
                rates = mt5.copy_rates_range(clean, {"1m": mt5.TIMEFRAME_M1, "15m": mt5.TIMEFRAME_M15, "1h": mt5.TIMEFRAME_H1}[tf],
                                            query_start.to_pydatetime(), end.to_pydatetime())
                if rates is not None and len(rates):
                    frame = pd.DataFrame(rates)
                    frame["datetime"] = pd.to_datetime(frame.time, unit="s", utc=True)
            summary = frame_summary(frame, query_start, end)
            rows.append({"symbol": symbol, "timeframe": tf, "requested_start": query_start.isoformat(),
                         "requested_end_exclusive": end.isoformat(), "source": source, **summary})
            if summary["in_range_rows"] == 0:
                blockers.append(f"NO_VALID_{tf}:{symbol}")
            elif frame is not None:
                during = frame[(frame.datetime >= start) & (frame.datetime < end)]
                if during.empty:
                    blockers.append(f"NO_MONTH_{tf}:{symbol}")
                # A single timestamp does not establish one month's coverage.
                elif during.datetime.max() - during.datetime.min() < pd.Timedelta(days=20):
                    blockers.append(f"SHORT_MONTH_COVERAGE_{tf}:{symbol}")
    if data_root is None:
        blockers.append("NO_ARCHIVED_LIVE_FEED_INPUT_MANIFEST")
    else:
        manifest = data_root / "provenance.json"
        if not manifest.exists():
            blockers.append("NO_ARCHIVED_LIVE_FEED_INPUT_MANIFEST")
        else:
            provenance = json.loads(manifest.read_text(encoding="utf-8"))
            if not provenance.get("source") or not provenance.get("volume_semantics"):
                blockers.append("INCOMPLETE_INPUT_PROVENANCE")
    return {"month": month, "status": "BLOCKED_MISSING_INPUTS" if blockers else "INPUT_AUDIT_PASSED",
            "blockers": blockers, "coverage": rows, "metrics": None}


class Clock:
    def __init__(self, now):
        self.current = utc_time(now)

    def datetime_type(self):
        clock = self
        class HistoricalDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return clock.current.astimezone(tz)
                return clock.current.astimezone(TRT).replace(tzinfo=None)

            @classmethod
            def utcnow(cls):
                return clock.current.replace(tzinfo=None)
        return HistoricalDateTime

    def pandas_proxy(self):
        clock = self
        class HistoricalTimestamp:
            def __new__(cls, *args, **kwargs):
                return pd.Timestamp(*args, **kwargs)

            @classmethod
            def now(cls, tz=None):
                value = pd.Timestamp(clock.current)
                return value.tz_convert(tz) if tz else value.tz_convert(TRT).tz_localize(None)

        class Proxy:
            Timestamp = HistoricalTimestamp

            def __getattr__(self, name):
                return getattr(pd, name)
        return Proxy()


class HistoricalProvider:
    def __init__(self, frames, clock):
        self.frames = frames
        self.clock = clock

    def fetch_candles(self, symbol, interval="15m", outputsize=70):
        df = self.frames.get((symbol, interval))
        if df is None:
            return None
        # Match live provider's tail including a possible current candle.
        # Production completed_bars removes that candle before any decision.
        times = df.datetime
        stop = int(times.searchsorted(pd.Timestamp(self.clock.current), side="right"))
        return df.iloc[max(0, stop-outputsize):stop].copy()


class NullNotifier:
    def is_configured(self):
        return False

    def send_notification(self, *args, **kwargs):
        return False


def replay_month(month, symbols, data_root, gates, output, macro_client_factory=None, candidate_index=None, market_calendar=None, news_file=None, frame_symbols=None, minimize_memory=False, friction_multiplier=1.0):
    """Use original engine methods with injected historical IO and time only."""
    from sfp_orb_engine import engine as engine_module, outcome_tracker as tracker_module
    from sfp_orb_engine import execution_policy, news_guard, orb_detector
    from sfp_orb_engine.sfp_detector import SFPDetector
    from sfp_orb_engine.orb_detector import ORBDetector
    from sfp_orb_engine.macro_gate_client import MacroGateClient
    from sfp_orb_engine.news_guard import NewsGuard

    if not math.isfinite(friction_multiplier) or friction_multiplier < 1:
        raise ValueError('Cost stress multiplier must be finite and at least one')
    start, end = bounds(month)
    clock = Clock(start)
    frames = {}
    excluded = {x.replace("/", "") for x in config.EXCLUDED_SFP_SYMBOLS}
    for symbol in symbols:
        if frame_symbols is not None and symbol not in frame_symbols:
            continue
        if symbol.replace("/", "") in excluded:
            continue
        for tf in ("1m", "15m", "1h"):
            frame=load_frame(data_root / f"{symbol.replace('/', '')}_{tf}.csv")
            if minimize_memory and tf=='1m':
                frame=frame[(frame.datetime>=start-pd.Timedelta(days=1))&(frame.datetime<end)].reset_index(drop=True)
            frames[symbol, tf]=frame
    output.mkdir(parents=True, exist_ok=False)
    state = output / "state"
    state.mkdir()
    gate_path = state / "macro_gate.json"
    with ExitStack() as stack:
        if friction_multiplier != 1.0:
            original_friction = tracker_module.get_friction_config
            def stressed_friction(symbol):
                return {key: value * friction_multiplier for key, value in original_friction(symbol).items()}
            stack.enter_context(patch.object(tracker_module, 'get_friction_config', stressed_friction))
        for module in (engine_module, tracker_module, execution_policy, news_guard, orb_detector, config):
            stack.enter_context(patch.object(module, "datetime", clock.datetime_type()))
        stack.enter_context(patch.object(engine_module, "pd", clock.pandas_proxy()))
        fake_time = SimpleNamespace(time=lambda: clock.current.timestamp())
        stack.enter_context(patch.object(engine_module, "time", fake_time))
        stack.enter_context(patch.object(tracker_module, "time", fake_time))
        if market_calendar is not None:
            stack.enter_context(patch.object(tracker_module,'is_market_open',market_calendar))
        for module, key, value in (
            (tracker_module, "ACTIVE_TRADES_FILE", state / "active.json"),
            (tracker_module, "CLOSED_LEDGER_FILE", state / "closed.json"),
            (engine_module, "HISTORY_FILE", state / "signals.json"),
            (engine_module, "TELEMETRY_DIR", state),
        ):
            stack.enter_context(patch.object(module, key, value))
        engine = engine_module.BegonyaEngine.__new__(engine_module.BegonyaEngine)
        engine.symbols = symbols
        engine.data_provider = HistoricalProvider(frames, clock)
        engine.sfp_detector = SFPDetector()
        engine.orb_detector = ORBDetector()
        engine.macro_client = macro_client_factory(clock,gate_path) if macro_client_factory else MacroGateClient(gate_path, now=lambda: clock.current)
        engine.news_guard = NewsGuard(news_file=news_file)
        engine.notifier = NullNotifier()
        engine.chart_renderer = SimpleNamespace(render_signal_chart=lambda *args, **kwargs: None)
        engine.outcome_tracker = tracker_module.OutcomeTracker(notifier=engine.notifier)
        if hasattr(engine.macro_client,'bind_engine'):
            engine.macro_client.bind_engine(engine)
        engine.signal_history = {}
        index = -1
        candidate_symbols_by_window = {}
        if candidate_index is not None:
            for candidate_symbol, window in candidate_index:
                candidate_symbols_by_window.setdefault(window, set()).add(candidate_symbol)
        ordered_symbols = list(dict.fromkeys(symbols))
        # Same 60s scan cadence and symbol ordering. No synthetic signals or fills.
        for now in pd.date_range(start, end, freq="min", inclusive="left"):
            clock.current = now.to_pydatetime()
            while index + 1 < len(gates) and gates[index + 1]["available_at"] <= clock.current:
                index += 1
                gate_path.write_text(json.dumps(gates[index]["gate"]), encoding="utf-8")
            if index < 0 and macro_client_factory is None:
                raise ValueError("No historical macro snapshot at replay time")
            # Use scan_symbol rather than scan_universe so data/programming errors
            # invalidate the run instead of silently skipping a symbol.
            active_symbols = {t['symbol'] for t in engine.outcome_tracker.active_trades}
            window_symbols = candidate_symbols_by_window.get(now.floor('15min'), set()) if candidate_index is not None else None
            for symbol in dict.fromkeys(ordered_symbols + [t['symbol'] for t in engine.outcome_tracker.active_trades]):
                if window_symbols is not None and symbol not in active_symbols:
                    if symbol not in window_symbols:
                        continue
                engine.scan_symbol(symbol)
            if now.hour==0 and now.minute==0:
                progress={'at':now.isoformat(),'closed':len(engine.outcome_tracker.closed_trades),'active':len(engine.outcome_tracker.active_trades)}
                (output/'progress.json').write_text(json.dumps(progress))
                print('REPLAY',month,progress,flush=True)
        closed = engine.outcome_tracker.closed_trades
        active = engine.outcome_tracker.active_trades
        filled = [t for t in closed if t.get("close_reason") not in NO_FILL_REASONS]
        result = {"month": month, "status": "REPLAY_COMPLETED",
                  "friction_assumptions": {"multiplier": friction_multiplier,
                      "model": "CONSTANT_RATIO_SPREAD_FIXED_R_FEE_PAPER_ONLY", "broker_costs_verified": False},
                  "closed_filled_trades": len(filled), "net_r": sum(t["net_r"] for t in filled),
                  "weighted_net_r": sum(t["weighted_net_r"] for t in filled),
                  "wins": sum(t["net_r"] > 0 for t in filled),
                  "stop_losses": sum(t["close_reason"] == "STOP_LOSS" for t in filled),
                  "open_at_month_end": len(active),
                  "unresolved_gaps": sum(bool(t.get("tracking_gap_at")) for t in active),
                  "end_policy": "Open positions retained; no invented month-end liquidation",
                  "clock_model": "60s scans at minute boundary, fixed symbol order, no measured IO latency",
                  "scope": "Live paper-engine replay; not broker execution or a macro reconstruction"}
        (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", nargs="+", default=list(MONTHS))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--macro-archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output already exists; choose a fresh directory")
    args.output.mkdir(parents=True)
    gates = load_gates(args.macro_archive)
    mt5 = None
    if args.data_root is None:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            raise SystemExit("MT5 unavailable; no data substituted")
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
              "source_sha256": source_hashes(), "universe": config.ACTIVE_SYMBOLS,
              "selection": "January, June, November fixed before outcome inspection",
              "macro_archive": str(args.macro_archive) if args.macro_archive else None,
              "months": []}
    report["effective_config"] = {key: getattr(config, key) for key in (
        "ENTRY_MODEL", "LIMIT_EXPIRY_BARS", "REQUIRE_ENTRY_REACTION", "REQUIRE_PRO_TREND_AAA",
        "USE_IFVG_ENTRY", "REQUIRE_STRUCTURAL_BREAKER", "SFP_MIN_RR_TARGET_1", "SFP_MIN_RR_TARGET_2",
        "MAX_DAILY_LOSS_R", "MAX_CONSECUTIVE_STOPS", "MAX_OPEN_RISK_R", "MAX_CURRENCY_RISK_R",
        "SCAN_INTERVAL_SECONDS", "SIGNAL_COOLDOWN_MINUTES", "EXCLUDED_SFP_SYMBOLS", "WEEKEND_ORB_ENABLED")}
    report["news_config_sha256"] = hashlib.sha256((ROOT / "config/news_events.json").read_bytes()).hexdigest()
    snapshot = args.output / "source_snapshot"
    snapshot.mkdir()
    for name in report["source_sha256"]:
        (snapshot / f"{name}.py").write_bytes((ROOT / "sfp_orb_engine" / f"{name}.py").read_bytes())
    (snapshot / "replay_live_system.py").write_bytes(Path(__file__).read_bytes())
    for month in args.months:
        result = audit_month(month, config.ACTIVE_SYMBOLS, args.data_root, gates, mt5)
        report["months"].append(result)
        (args.output / "input_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(month, result["status"], "blockers", len(result["blockers"]), flush=True)
        if args.run and not result["blockers"]:
            result["replay"] = replay_month(month, config.ACTIVE_SYMBOLS, args.data_root, gates, args.output / month)
    (args.output / "input_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.run and any(r["blockers"] for r in report["months"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
