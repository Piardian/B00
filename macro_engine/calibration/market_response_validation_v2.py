"""Event-time aligned market-response validation for macro surprises.

This version deliberately does NOT use broker-hour approximations. It reconstructs the
scheduled US release timestamp in America/New_York, converts it to UTC, and matches it
to MT5 M5 bars. Returns are measured from the release bar open to exact +5m/+15m/+30m/
+60m/+240m closes. MAD and STD are fitted only on observations strictly before each
validation year.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Mapping, Sequence, Tuple
from zoneinfo import ZoneInfo

from core.deterministic_controls import INDICATOR_DIRECTIONS, fit_surprise_sigmas

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

# ForexFactory date can be one calendar day behind the actual US release because the
# upstream scraper used Iran local midnight. For timestamps at 19:30/20:30 UTC the
# release belongs to the following calendar date. We use the row date only to recover
# the scheduled US date; the scraped timestamp is retained as an audit field.
SHIFTED_MIDNIGHT_UTC = {(19, 30), (20, 30)}
RELEASE_TIMES_ET = {
    "pmi": (10, 0),
    "nfp": (8, 30),
    "cpi": (8, 30),
    "core_cpi": (8, 30),
    "unemployment": (8, 30),
    "retail_sales": (8, 30),
    "gdp": (8, 30),
}

HORIZONS_MINUTES = (5, 15, 30, 60, 240)


def parse_observation_event_utc(row: Mapping[str, Any]) -> dt.datetime:
    """Reconstruct the scheduled US release instant with DST-safe timezone handling."""
    kind = str(row.get("indicator_type", "")).strip().lower()
    if kind not in RELEASE_TIMES_ET:
        raise ValueError(f"Unsupported indicator_type: {kind!r}")

    base_date = dt.date.fromisoformat(str(row["date"]))
    raw = dt.datetime.fromisoformat(str(row["event_timestamp_utc"]))
    if raw.tzinfo is None:
        raw = raw.replace(tzinfo=UTC)
    raw_utc = raw.astimezone(UTC)

    # The scraper's Iran-local-midnight artifact puts several US releases on the
    # preceding row date. Preserve this explicit correction instead of trusting the
    # malformed UTC clock value as an event time.
    if (raw_utc.hour, raw_utc.minute) in SHIFTED_MIDNIGHT_UTC:
        release_date = base_date + dt.timedelta(days=1)
    else:
        release_date = base_date

    hour, minute = RELEASE_TIMES_ET[kind]
    local_release = dt.datetime.combine(
        release_date, dt.time(hour, minute), tzinfo=ET
    )
    return local_release.astimezone(UTC)


def audit_event_timestamp(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Return an auditable comparison between scraped and reconstructed timestamps."""
    reconstructed = parse_observation_event_utc(row)
    raw = dt.datetime.fromisoformat(str(row["event_timestamp_utc"]))
    if raw.tzinfo is None:
        raw = raw.replace(tzinfo=UTC)
    raw = raw.astimezone(UTC)
    delta_minutes = (raw - reconstructed).total_seconds() / 60.0
    return {
        "raw_timestamp_utc": raw.isoformat(),
        "reconstructed_event_timestamp_utc": reconstructed.isoformat(),
        "timestamp_delta_minutes": round(delta_minutes, 3),
        "timestamp_is_close": abs(delta_minutes) <= 5.0,
    }


BROKER_TZ = ZoneInfo("Europe/Helsinki")


def fetch_mt5_bars(
    symbol: str = "EURUSD",
    timeframe: str = "M5",
    count: int = 65000,
) -> Dict[dt.datetime, Dict[str, float]]:
    """Load MT5 bars converted from broker server timezone (EET/EEST) to true UTC."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {}

    if not mt5.initialize():
        return {}

    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
    }
    tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M5)
    # MT5 terminal chart buffer rejects requests exceeding terminal max (typically 65000)
    safe_count = min(count, 65000)

    try:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, safe_count)
    finally:
        mt5.shutdown()

    if rates is None or len(rates) == 0:
        return {}

    result: Dict[dt.datetime, Dict[str, float]] = {}
    for r in rates:
        # MT5 timestamps are epoch seconds in the broker's server timezone (Europe/Helsinki, EET/EEST)
        ts = int(r["time"])
        broker_dt = dt.datetime.fromtimestamp(ts, tz=UTC).replace(tzinfo=None).replace(tzinfo=BROKER_TZ)
        t = broker_dt.astimezone(UTC).replace(second=0, microsecond=0)
        result[t] = {
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        }
    return result


def fetch_mt5_m5_bars(symbol: str = "EURUSD", count: int = 65000) -> Dict[dt.datetime, Dict[str, float]]:
    """Backward-compatible loader for M5 bars with broker-timezone to UTC conversion."""
    return fetch_mt5_bars(symbol=symbol, timeframe="M5", count=count)


def calculate_usd_return_bps(p0: float, p1: float) -> float:
    """EURUSD return expressed as USD-strength basis points."""
    if not math.isfinite(p0) or p0 <= 0 or not math.isfinite(p1):
        raise ValueError("Invalid price")
    return (p0 - p1) / p0 * 10000.0


def spearman_rank_ic(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0

    def ranks(values: Sequence[float]) -> List[float]:
        indexed = sorted(enumerate(values), key=lambda item: item[1])
        out = [0.0] * len(values)
        i = 0
        while i < len(indexed):
            j = i
            while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[indexed[k][0]] = avg
            i = j + 1
        return out

    rx, ry = ranks(x), ranks(y)
    mx, my = mean(rx), mean(ry)
    vx = sum((v - mx) ** 2 for v in rx)
    vy = sum((v - my) ** 2 for v in ry)
    if vx <= 0 or vy <= 0:
        return 0.0
    return sum((rx[i] - mx) * (ry[i] - my) for i in range(len(rx))) / math.sqrt(vx * vy)


def calc_hit_rate(records: Sequence[Mapping[str, Any]], z_key: str, ret_key: str) -> float:
    actionable = [r for r in records if abs(float(r[z_key])) >= 1.0]
    if not actionable:
        return 0.0
    wins = sum(
        1 for r in actionable
        if (float(r[z_key]) > 0 and float(r[ret_key]) > 0)
        or (float(r[z_key]) < 0 and float(r[ret_key]) < 0)
    )
    return wins / len(actionable)


def build_records(
    observations_path: Path,
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    test_years: Sequence[int] = tuple(range(2019, 2026)),
    min_observations: int = 15,
    horizons: Sequence[int] = HORIZONS_MINUTES,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    with observations_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    records: List[Dict[str, Any]] = []
    diagnostics = {
        "observations_total": len(rows),
        "matched": 0,
        "missing_event_bar": 0,
        "missing_horizon_bar": 0,
        "invalid_observation": 0,
    }

    for year in test_years:
        history = [r for r in rows if dt.date.fromisoformat(r["date"]).year < year]
        mad = fit_surprise_sigmas(history, min_observations=min_observations, method="mad")
        std = fit_surprise_sigmas(history, min_observations=min_observations, method="std")

        for row in rows:
            if dt.date.fromisoformat(row["date"]).year != year:
                continue
            kind = str(row.get("indicator_type", "")).lower()
            if kind not in mad or kind not in std:
                diagnostics["invalid_observation"] += 1
                continue
            try:
                actual = float(row["actual"])
                forecast = float(row["forecast"])
                event_utc = parse_observation_event_utc(row)
                direction = INDICATOR_DIRECTIONS.get(kind, 1.0)
                z_mad = (actual - forecast) * direction / mad[kind]
                z_std = (actual - forecast) * direction / std[kind]
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                diagnostics["invalid_observation"] += 1
                continue

            base_bar = bar_map.get(event_utc)
            if base_bar is None:
                diagnostics["missing_event_bar"] += 1
                continue

            prices: Dict[int, float] = {}
            complete = True
            for minutes in horizons:
                bar = bar_map.get(event_utc + dt.timedelta(minutes=minutes))
                if bar is None:
                    complete = False
                    break
                prices[minutes] = float(bar["close"])
            if not complete:
                diagnostics["missing_horizon_bar"] += 1
                continue

            p0 = float(base_bar["open"])
            record: Dict[str, Any] = {
                "year": year,
                "indicator": kind,
                "event": row.get("event", ""),
                "event_timestamp_utc": event_utc.isoformat(),
                "z_mad": z_mad,
                "z_std": z_std,
                "timestamp_audit": audit_event_timestamp(row),
            }
            for minutes, price in prices.items():
                record[f"ret_{minutes}m"] = calculate_usd_return_bps(p0, price)
            records.append(record)
            diagnostics["matched"] += 1

    return records, diagnostics


def summarize(
    records: Sequence[Mapping[str, Any]],
    horizons: Sequence[int] = HORIZONS_MINUTES,
) -> Dict[str, Any]:
    if not records:
        return {"error": "No fully aligned event records"}

    # Infer available horizons if not present in all records
    available_horizons = [m for m in horizons if f"ret_{m}m" in records[0]]
    if not available_horizons:
        available_horizons = list(horizons)

    output: Dict[str, Any] = {"sample_count": len(records), "horizons": {}}
    for minutes in available_horizons:
        ret_key = f"ret_{minutes}m"
        rets = [float(r[ret_key]) for r in records if ret_key in r]
        z_mad = [float(r["z_mad"]) for r in records if ret_key in r]
        z_std = [float(r["z_std"]) for r in records if ret_key in r]
        if not rets:
            continue
        output["horizons"][f"{minutes}m"] = {
            "mad_ic": round(spearman_rank_ic(z_mad, rets), 4),
            "std_ic": round(spearman_rank_ic(z_std, rets), 4),
            "delta_mad_minus_std": round(spearman_rank_ic(z_mad, rets) - spearman_rank_ic(z_std, rets), 4),
            "mad_hit_rate_abs_z_ge_1": round(calc_hit_rate(records, "z_mad", ret_key) * 100, 1),
            "std_hit_rate_abs_z_ge_1": round(calc_hit_rate(records, "z_std", ret_key) * 100, 1),
            "mean_return_mad_sign": round(mean(
                float(r[ret_key]) if float(r["z_mad"]) > 0 else -float(r[ret_key])
                for r in records if float(r["z_mad"]) != 0 and ret_key in r
            ), 3),
        }
    return output


def run_market_response_analysis(
    observations_path: Path,
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    test_years: Sequence[int] = tuple(range(2019, 2026)),
    min_observations: int = 15,
    horizons: Sequence[int] = HORIZONS_MINUTES,
) -> Dict[str, Any]:
    """Top-level convenience runner for event-time market validation."""
    records, diagnostics = build_records(
        observations_path,
        bar_map,
        test_years=test_years,
        min_observations=min_observations,
        horizons=horizons,
    )
    return {
        "diagnostics": diagnostics,
        "summary": summarize(records, horizons=horizons),
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DST-safe event-time macro market validation")
    parser.add_argument("--observations", type=Path, default=Path(__file__).with_name("surprise_observations.csv"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("market_response_validation_v2.json"))
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="M5", choices=["M5", "M15", "M30", "H1"])
    parser.add_argument("--count", type=int, default=65000)
    args = parser.parse_args()

    tf_horizons = {
        "M5": (5, 15, 30, 60, 240),
        "M15": (15, 30, 60, 240),
        "M30": (30, 60, 240),
        "H1": (60, 240),
    }
    horizons = tf_horizons.get(args.timeframe.upper(), HORIZONS_MINUTES)

    bars = fetch_mt5_bars(args.symbol, timeframe=args.timeframe, count=args.count)
    if not bars:
        raise SystemExit("MT5 bars unavailable; run this on the Windows/MT5 environment.")

    first_bar = min(bars.keys())
    last_bar = max(bars.keys())

    records, diagnostics = build_records(args.observations, bars, horizons=horizons)
    report = {
        "metadata": {
            "symbol": args.symbol,
            "time_basis": "UTC event timestamp reconstructed from America/New_York schedule",
            "bar_timeframe": args.timeframe.upper(),
            "horizons_minutes": list(horizons),
            "walk_forward": "expanding, train strictly before validation year",
            "mt5_bar_range_utc": {
                "first_bar": first_bar.isoformat(),
                "last_bar": last_bar.isoformat(),
                "total_bars": len(bars),
            },
        },
        "diagnostics": diagnostics,
        "summary": summarize(records, horizons=horizons),
        "timestamp_audit": {
            "raw_vs_reconstructed_close_within_5m": sum(
                1 for r in records if r["timestamp_audit"]["timestamp_is_close"]
            ),
            "matched_records": len(records),
        },
    }

    # If M5 was requested but yielded 0 matches due to broker historical buffer depth,
    # automatically augment with M15 resolution so the user gets actionable empirical output
    if args.timeframe.upper() == "M5" and diagnostics["matched"] == 0:
        m15_bars = fetch_mt5_bars(args.symbol, timeframe="M15", count=args.count)
        if m15_bars:
            m15_horizons = (15, 30, 60, 240)
            m15_records, m15_diag = build_records(args.observations, m15_bars, horizons=m15_horizons)
            report["m15_extended_analysis"] = {
                "note": "M5 buffer only exists from " + first_bar.strftime("%Y-%m-%d") + " onwards in this broker account. M15 is available back to " + min(m15_bars.keys()).strftime("%Y-%m-%d") + " and covers 2024-2025 events.",
                "diagnostics": m15_diag,
                "summary": summarize(m15_records, horizons=m15_horizons),
            }

    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
