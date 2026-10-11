from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yfinance as yf

from calibration.replay import run_replay
from config import MARKET_SYMBOLS
from ingestion.mt5_market_data import MT5MarketDataIngestion, mt5
from ingestion.fred_data import FredDataIngestion
from preprocessing.metrics import MacroMetricsCalculator
from data_quality import REQUIRED_MARKET_FIELDS
from ingestion.bank_of_england import BankOfEnglandDataIngestion
from ingestion.bank_of_canada import BankOfCanadaDataIngestion


class HistoricalMarketReplayIngestion(MT5MarketDataIngestion):
    """Research-only historical adapter. Production ingestion is untouched."""

    def _from_mt5(self, generic_name: str, as_of: dt.datetime, n_bars: int) -> Optional[Dict[str, Any]]:
        if mt5 is None or not self._check_connection():
            return None
        broker_sym = self.find_broker_symbol(generic_name)
        if not broker_sym:
            return None
        try:
            rates = mt5.copy_rates_from(broker_sym, mt5.TIMEFRAME_D1, as_of, n_bars)
            if rates is None:
                return None
            # D1 timestamps identify bar opens. A bar opened earlier today is
            # not necessarily closed at replay time; exclude the current day.
            rows = [
                r for r in rates
                if dt.datetime.fromtimestamp(int(r["time"]), tz=dt.timezone.utc).date()
                < as_of.date()
            ]
            if len(rows) < 2:
                return None
            closes = [float(r["close"]) for r in rows]
            return self._build_payload(generic_name, closes, as_of, f"MT5 Historical Broker Feed ({broker_sym})")
        except Exception:
            return None

    @staticmethod
    def _from_yfinance(generic_name: str, as_of: dt.datetime, n_bars: int) -> Optional[Dict[str, Any]]:
        ticker = MARKET_SYMBOLS.get(generic_name)
        if not ticker:
            return None
        try:
            start = as_of.date() - dt.timedelta(days=max(120, n_bars * 3))
            end = as_of.date() + dt.timedelta(days=1)
            hist = yf.Ticker(ticker).history(
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                auto_adjust=False,
            )
            if hist.empty:
                return None

            # Yahoo daily history can include the current day's unfinished bar.
            # Keep only completed calendar days for an intraday replay.
            idx = hist.index
            if getattr(idx, "tz", None) is not None:
                valid = [ts.date() < as_of.date() for ts in idx]
            else:
                valid = [ts.date() < as_of.date() for ts in idx]
            hist = hist.loc[valid]
            if hist.empty:
                return None

            closes = [float(x) for x in hist["Close"].dropna().tolist() if float(x) > 0][-n_bars:]
            if len(closes) < 2:
                return None
            return HistoricalMarketReplayIngestion._build_payload(
                generic_name, closes, as_of, f"Yahoo Finance Historical ({ticker})"
            )
        except Exception:
            return None

    @staticmethod
    def _build_payload(generic_name: str, closes: List[float], as_of: dt.datetime, source: str) -> Dict[str, Any]:
        current_val = closes[-1]
        prev_val = closes[-2]
        val_5d_ago = closes[-6] if len(closes) >= 6 else closes[0]
        month_ago_val = closes[-21] if len(closes) >= 21 else closes[0]
        pct = lambda a, b: round(((a - b) / b) * 100, 2) if b else 0.0

        if generic_name == "BTC" and current_val < 10000.0:
            raise ValueError("BTC historical symbol/value validation failed")
        if generic_name in {"BRENT", "WTI"} and current_val < 30.0:
            raise ValueError("oil historical symbol/value validation failed")
        if generic_name == "DXY" and not 70.0 <= current_val <= 150.0:
            raise ValueError("DXY historical symbol/value validation failed")

        return {
            "value": round(current_val, 4),
            "prev": round(prev_val, 4),
            "val_5d_ago": round(val_5d_ago, 4),
            "month_ago": round(month_ago_val, 4),
            "change_pct": pct(current_val, prev_val),
            "change_pct_5d": pct(current_val, val_5d_ago),
            "change_pct_4w": pct(current_val, month_ago_val),
            "pct_rank_60d": round(sum(1 for x in closes if x <= current_val) / len(closes) * 100, 1),
            "history_close": closes,
            "source": source,
            "snapshot_timestamp": as_of.isoformat(),
        }

    def fetch_symbol_snapshot(self, generic_name: str, as_of: dt.datetime, n_bars: int = 60) -> Optional[Dict[str, Any]]:
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of = as_of.astimezone(dt.timezone.utc)
        # Real broker history first; Yahoo is a real-data research fallback.
        return self._from_mt5(generic_name, as_of, n_bars) or self._from_yfinance(generic_name, as_of, n_bars)


def build_market_snapshot(ingestion: HistoricalMarketReplayIngestion, symbols: Iterable[str], as_of: dt.datetime) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}
    missing: List[str] = []
    for symbol in symbols:
        item = ingestion.fetch_symbol_snapshot(symbol, as_of)
        if item is None:
            missing.append(symbol)
        else:
            snapshot[symbol] = item
    if missing:
        raise RuntimeError("Historical market snapshot incomplete; no synthetic fallback permitted: " + ", ".join(sorted(missing)))
    snapshot["_metadata"] = {
        "timestamp": as_of.isoformat(),
        "source_policy": "MT5_FIRST_THEN_YAHOO_REAL_DATA_ONLY",
        "lookahead_policy": "D1_current_calendar_day_excluded_for_intraday_replay",
    }
    return snapshot

DEFAULT_REPLAY_SYMBOLS = [
    "DXY", "GOLD", "BRENT", "US10Y", "US02Y", "BTC", "COPPER", "VIX", "HYG", "LQD", "SOL"
]


def build_real_snapshot(as_of: dt.datetime, symbols: Iterable[str]) -> Dict[str, Any]:
    market = build_market_snapshot(HistoricalMarketReplayIngestion(), symbols, as_of)
    # FRED vintages are date-granular. For intraday replay, use the prior UTC
    # date so same-day releases/revisions cannot leak into an earlier timestamp.
    fred_vintage_end = as_of.date() - dt.timedelta(days=1)
    fred = FredDataIngestion().fetch_liquidity_metrics(as_of=fred_vintage_end)

    try:
        uk_bank_rate = BankOfEnglandDataIngestion().fetch_bank_rate(as_of)
    except Exception as exc:
        uk_bank_rate = {
            "status": "UNAVAILABLE",
            "value": None,
            "previous_value": None,
            "observation_date": None,
            "source": "Bank of England official Bank Rate (YWMB47D)",
            "error": str(exc),
        }
    fred["UK_BANK_RATE"] = uk_bank_rate.get("value")
    fred["UK_BANK_RATE_PREVIOUS"] = uk_bank_rate.get("previous_value")
    fred["UK_BANK_RATE_SOURCE_DATE"] = uk_bank_rate.get("observation_date")
    fred.setdefault("data_quality", {})["uk_bank_rate"] = uk_bank_rate

    try:
        ca_policy_rate = BankOfCanadaDataIngestion().fetch_policy_rate(as_of)
    except Exception as exc:
        ca_policy_rate = {
            "status": "UNAVAILABLE",
            "value": None,
            "previous_value": None,
            "observation_date": None,
            "source": "Bank of Canada official Target for the overnight rate (V39079)",
            "error": str(exc),
        }
    fred["CA_POLICY_RATE"] = ca_policy_rate.get("value")
    fred["CA_POLICY_RATE_PREVIOUS"] = ca_policy_rate.get("previous_value")
    fred["CA_POLICY_RATE_SOURCE_DATE"] = ca_policy_rate.get("observation_date")
    fred.setdefault("data_quality", {})["ca_policy_rate"] = ca_policy_rate
    return {
        "schema_version": 1,
        "timestamp": as_of.isoformat(),
        "market": market,
        "fred": fred,
        "calendar_events": [],
        "metadata": {
            "market_source_policy": market["_metadata"]["source_policy"],
            "fred_provider": fred.get("data_quality", {}).get("provider"),
            "fred_vintage_end": fred_vintage_end.isoformat(),
            "calendar_status": "UNAVAILABLE_HISTORICAL_PROVIDER",
            "promotion_eligible": False,
        },
    }


def load_rows(path: Path) -> List[Mapping[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Replay dataset must be a JSON list")
    return rows


def process_snapshot(
    market: Mapping[str, Any],
    fred: Mapping[str, Any],
    events: List[Dict[str, Any]],
    *,
    as_of_date: dt.date,
    as_of_datetime: dt.datetime,
    now_utc: dt.datetime,
    previous_regime_state: Mapping[str, Any],
) -> Dict[str, Any]:
    calculator = MacroMetricsCalculator(as_of_date=as_of_date)
    return calculator.process_all_macro_data(
        dict(market), dict(fred), events,
        as_of_date=as_of_date,
        as_of_datetime=as_of_datetime,
        previous_regime_state=previous_regime_state,
        now_utc=now_utc,
    )


def replay_dataset(path: Path) -> List[Dict[str, Any]]:
    return run_replay(load_rows(path), process_snapshot)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research-only historical macro replay")
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--as-of", type=str)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_REPLAY_SYMBOLS)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.as_of:
        as_of = dt.datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of = as_of.astimezone(dt.timezone.utc)
        snapshot = build_real_snapshot(as_of, args.symbols)
        result = process_snapshot(
            snapshot["market"], snapshot["fred"], snapshot["calendar_events"],
            as_of_date=as_of.date(), as_of_datetime=as_of,
            now_utc=as_of, previous_regime_state={},
        )
        from graph.macro_graph import MacroWorkflowEngine
        gate = MacroWorkflowEngine._build_deterministic_gates(result)
        output = {
            "timestamp": snapshot["timestamp"],
            "metadata": snapshot["metadata"],
            "execution_bias_gates": gate,
            "stress_diagnostics": {
                "t0_fast_stress_analysis": result.get("t0_fast_stress_analysis", {}),
                "credit_spread_analysis": result.get("credit_spread_analysis", {}),
                "systemic_stress": bool(
                    result.get("t0_fast_stress_analysis", {}).get("fast_stress_override", False)
                    or result.get("t0_fast_stress_analysis", {}).get("vix_level", 0.0) >= 25.0
                    or result.get("credit_spread_analysis", {}).get("stress_level") == "Şiddetli Kredi Krizi (Distress)"
                ),
                "regime_state": result.get("regime_state", {}),
            },
            "data_quality": result.get("data_quality", {}),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return
    if not args.dataset or not args.output:
        raise SystemExit("--dataset/--output or --as-of is required")
    results = replay_dataset(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"replay_rows={len(results)}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
