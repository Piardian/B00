"""Deterministic promotion-gate research tools for the macro + SMC stack.

The module is intentionally research-only. It does not activate production gates.
It provides three auditable layers:

1. Frozen-parameter holdout evaluation. The MAD threshold is fixed at |Z| >= 1.0;
   no threshold is learned from the holdout period.
2. Bar-based execution stress simulation for T0 market and delayed retest/limit
   entry. Ambiguous OHLC bars are fail-closed rather than resolved optimistically.
3. Incremental SMC-vs-SMC+macro comparison from an external trade ledger.

All outputs are diagnostics. A production promotion still requires a complete,
untouched holdout and a populated SMC trade ledger.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

UTC = dt.timezone.utc
FROZEN_MAD_THRESHOLD = 1.0
DEFAULT_HOLDOUT_START = dt.datetime(2025, 7, 1, tzinfo=UTC)
DEFAULT_HOLDOUT_END = dt.datetime(2026, 9, 17, 23, 59, 59, tzinfo=UTC)


@dataclass(frozen=True)
class Bar:
    timestamp: dt.datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class ExecutionScenario:
    name: str
    spread_bps: float
    slippage_bps: float
    entry_delay_bars: int
    max_wait_bars: int = 3


DEFAULT_EXECUTION_SCENARIOS = (
    ExecutionScenario("CALM_10BP", 10.0, 2.5, 0),
    ExecutionScenario("NEWS_30BP", 30.0, 5.0, 1),
    ExecutionScenario("NEWS_50BP", 50.0, 10.0, 1),
)


@dataclass(frozen=True)
class HoldoutWindow:
    name: str
    start: dt.datetime
    end: dt.datetime


DEFAULT_HOLDOUT_WINDOWS = (
    HoldoutWindow("2025_H2", dt.datetime(2025, 7, 1, tzinfo=UTC), dt.datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)),
    HoldoutWindow("2026_YTD", dt.datetime(2026, 1, 1, tzinfo=UTC), DEFAULT_HOLDOUT_END),
)


def _parse_time(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _side(value: Any) -> int:
    text = str(value).strip().upper()
    if text in {"LONG", "BUY", "1", "+1"}:
        return 1
    if text in {"SHORT", "SELL", "-1"}:
        return -1
    try:
        numeric = float(value)
        return 1 if numeric > 0 else -1 if numeric < 0 else 0
    except (TypeError, ValueError):
        return 0


def _metric(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {
            "trade_count": 0,
            "hit_rate_pct": None,
            "mean": None,
            "profit_factor": None,
            "max_drawdown": None,
            "trade_sharpe": None,
        }
    wins = [v for v in values if v > 0]
    losses = [abs(v) for v in values if v < 0]
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    std = pstdev(values) if len(values) > 1 else 0.0
    sharpe = (mean(values) / std * math.sqrt(len(values))) if std > 0 else None
    return {
        "trade_count": len(values),
        "hit_rate_pct": round(len(wins) / len(values) * 100.0, 2),
        "mean": round(mean(values), 6),
        "profit_factor": round(sum(wins) / sum(losses), 4) if losses else (999.0 if wins else 0.0),
        "max_drawdown": round(max_dd, 6),
        "trade_sharpe": None if sharpe is None else round(sharpe, 6),
    }


def _fingerprint(config: Mapping[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def evaluate_frozen_holdout(
    records: Sequence[Mapping[str, Any]],
    *,
    threshold: float = FROZEN_MAD_THRESHOLD,
    windows: Sequence[HoldoutWindow] = DEFAULT_HOLDOUT_WINDOWS,
    cost_bps: float = 15.0,
    min_window_rows: int = 1,
) -> Dict[str, Any]:
    """Evaluate a frozen MAD threshold without fitting anything on the holdout."""
    if threshold != FROZEN_MAD_THRESHOLD:
        raise ValueError("Promotion holdout threshold is frozen at |Z_MAD| >= 1.0")

    normalized = []
    for row in records:
        timestamp = _parse_time(row.get("event_time_utc") or row.get("event_timestamp_utc"))
        signal = _side(row.get("cluster_signal"))
        z = row.get("dominant_z_mad")
        outcome = row.get("post_30m_usd_bps")
        if timestamp is None or signal == 0 or not _finite(z) or not _finite(outcome):
            continue
        normalized.append((timestamp, signal, float(z), float(outcome)))

    results: Dict[str, Any] = {
        "methodology_version": "promotion-holdout-v1",
        "production_activation": False,
        "frozen_parameters": {
            "mad_threshold_abs_z": FROZEN_MAD_THRESHOLD,
            "cost_bps": cost_bps,
            "no_holdout_fitting": True,
            "parameter_fingerprint": _fingerprint({"mad_threshold_abs_z": FROZEN_MAD_THRESHOLD}),
        },
        "windows": {},
    }

    for window in windows:
        eligible = [item for item in normalized if window.start <= item[0] <= window.end]
        baseline = [signal * outcome - cost_bps for _, signal, _, outcome in eligible]
        gated = [signal * outcome - cost_bps for _, signal, z, outcome in eligible if abs(z) >= threshold]
        filtered_out = [signal * outcome - cost_bps for _, signal, z, outcome in eligible if abs(z) < threshold]
        status = "PASS_DATA" if len(eligible) >= min_window_rows else "INSUFFICIENT_DATA"
        results["windows"][window.name] = {
            "status": status,
            "partial_data": bool(0 < len(eligible) < min_window_rows),
            "coverage": {
                "rows_in_window": len(eligible),
                "min_required_rows": min_window_rows,
                "gated_rows": len(gated),
                "filtered_rows": len(filtered_out),
            },
            "baseline": _metric(baseline),
            "frozen_mad": _metric(gated),
            "filtered_pool": _metric(filtered_out),
        }

    return results


def _effective_market_price(mid_price: float, side: int, scenario: ExecutionScenario) -> float:
    adverse_bps = scenario.spread_bps / 2.0 + scenario.slippage_bps
    return mid_price * (1.0 + side * adverse_bps / 10000.0)


def _effective_exit_price(mid_price: float, side: int, scenario: ExecutionScenario) -> float:
    adverse_bps = scenario.spread_bps / 2.0 + scenario.slippage_bps
    return mid_price * (1.0 - side * adverse_bps / 10000.0)


def simulate_trade_path(
    bars: Sequence[Bar],
    *,
    event_time: dt.datetime,
    side: int,
    entry_zone: Sequence[float],
    stop_loss: float,
    take_profit: float,
    scenario: ExecutionScenario,
    mode: str,
) -> Dict[str, Any]:
    """Simulate a single OHLC path using conservative same-bar ambiguity handling."""
    if side not in (-1, 1):
        raise ValueError("side must be +1 or -1")
    if mode not in {"T0_MARKET", "T5_RETEST_LIMIT"}:
        raise ValueError("unsupported execution mode")
    if len(entry_zone) != 2 or not all(_finite(v) for v in entry_zone):
        raise ValueError("entry_zone must contain two finite prices")

    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    eligible = [bar for bar in ordered if bar.timestamp >= event_time]
    if not eligible:
        return {"status": "NO_BARS"}

    if mode == "T0_MARKET":
        index = min(scenario.entry_delay_bars, len(eligible) - 1)
        bar = eligible[index]
        entry_mid = bar.open
        entry_price = _effective_market_price(entry_mid, side, scenario)
        entry_index = ordered.index(bar)
    else:
        lower, upper = sorted(float(v) for v in entry_zone)
        target_price = (lower + upper) / 2.0
        start_index = min(scenario.entry_delay_bars, len(eligible) - 1)
        active = eligible[start_index: start_index + scenario.max_wait_bars]
        fill_bar = None
        entry_price = None
        entry_index = None
        for bar in active:
            touched = bar.low <= target_price <= bar.high
            if touched:
                fill_bar = bar
                entry_price = target_price
                entry_index = ordered.index(bar)
                break
        if fill_bar is None:
            return {"status": "NO_FILL"}

    if mode == "T5_RETEST_LIMIT":
        assert entry_price is not None
    assert entry_index is not None

    exit_index: Optional[int] = None
    exit_mid: Optional[float] = None
    exit_reason = "TIME_EXIT"
    ambiguous = False
    for current_index in range(entry_index, len(ordered)):
        bar = ordered[current_index]
        if side == 1:
            stop_hit = bar.low <= stop_loss
            target_hit = bar.high >= take_profit
        else:
            stop_hit = bar.high >= stop_loss
            target_hit = bar.low <= take_profit

        if stop_hit and target_hit:
            ambiguous = True
            exit_index = current_index
            exit_reason = "AMBIGUOUS_SAME_BAR"
            break
        if stop_hit:
            exit_index = current_index
            exit_mid = stop_loss
            exit_reason = "STOP"
            break
        if target_hit:
            exit_index = current_index
            exit_mid = take_profit
            exit_reason = "TARGET"
            break

    if ambiguous:
        return {
            "status": "AMBIGUOUS",
            "entry_price": entry_price,
            "exit_reason": exit_reason,
            "entry_timestamp": ordered[entry_index].timestamp.isoformat(),
            "exit_timestamp": ordered[exit_index].timestamp.isoformat() if exit_index is not None else None,
        }

    if exit_index is None:
        exit_index = len(ordered) - 1
        exit_mid = ordered[-1].close
        exit_reason = "TIME_EXIT"

    assert exit_mid is not None
    exit_price = _effective_exit_price(exit_mid, side, scenario)
    if entry_price <= 0 or exit_price <= 0:
        return {"status": "INVALID_PRICE"}
    pnl_pct = side * (exit_price - entry_price) / entry_price * 100.0
    risk_pct = abs(entry_price - stop_loss) / entry_price * 100.0
    realized_r = pnl_pct / risk_pct if risk_pct > 0 else None
    return {
        "status": "EXECUTED",
        "mode": mode,
        "entry_price": round(entry_price, 8),
        "exit_price": round(exit_price, 8),
        "entry_timestamp": ordered[entry_index].timestamp.isoformat(),
        "exit_timestamp": ordered[exit_index].timestamp.isoformat(),
        "exit_reason": exit_reason,
        "realized_r": None if realized_r is None else round(realized_r, 6),
        "pnl_pct": round(pnl_pct, 6),
        "ambiguous_bar": False,
    }


def compare_execution_modes(
    trade_specs: Sequence[Mapping[str, Any]],
    bars_by_trade: Mapping[str, Sequence[Bar]],
    *,
    scenarios: Sequence[ExecutionScenario] = DEFAULT_EXECUTION_SCENARIOS,
) -> Dict[str, Any]:
    """Compare fixed execution mechanisms without tuning thresholds."""
    results: Dict[str, Any] = {
        "methodology_version": "execution-stress-v1",
        "production_activation": False,
        "scenarios": {},
    }
    for scenario in scenarios:
        scenario_result: Dict[str, Any] = {}
        for mode in ("T0_MARKET", "T5_RETEST_LIMIT"):
            realized_r: List[float] = []
            counts = {"EXECUTED": 0, "NO_FILL": 0, "AMBIGUOUS": 0, "OTHER": 0}
            for spec in trade_specs:
                trade_id = str(spec.get("trade_id"))
                bars = bars_by_trade.get(trade_id, ())
                event_time = _parse_time(spec.get("event_time_utc"))
                side = _side(spec.get("side"))
                if event_time is None or side == 0:
                    counts["OTHER"] += 1
                    continue
                try:
                    result = simulate_trade_path(
                        bars,
                        event_time=event_time,
                        side=side,
                        entry_zone=spec["entry_zone"],
                        stop_loss=float(spec["stop_loss"]),
                        take_profit=float(spec["take_profit"]),
                        scenario=scenario,
                        mode=mode,
                    )
                except (KeyError, TypeError, ValueError):
                    counts["OTHER"] += 1
                    continue
                status = result.get("status")
                if status in counts:
                    counts[status] += 1
                else:
                    counts["OTHER"] += 1
                if status == "EXECUTED" and result.get("realized_r") is not None:
                    realized_r.append(float(result["realized_r"]))
            scenario_result[mode] = {
                "counts": counts,
                "metrics": _metric(realized_r),
            }
        results["scenarios"][scenario.name] = {
            "assumptions": {
                "spread_bps": scenario.spread_bps,
                "slippage_bps": scenario.slippage_bps,
                "entry_delay_bars": scenario.entry_delay_bars,
                "max_wait_bars": scenario.max_wait_bars,
            },
            "modes": scenario_result,
        }
    return results


def evaluate_incremental_smc_alpha(
    trades: Sequence[Mapping[str, Any]],
    *,
    threshold: float = FROZEN_MAD_THRESHOLD,
) -> Dict[str, Any]:
    """Compare pure SMC with SMC gated by frozen macro direction + MAD strength."""
    if threshold != FROZEN_MAD_THRESHOLD:
        raise ValueError("Incremental alpha threshold is frozen at |Z_MAD| >= 1.0")

    normalized = []
    for row in trades:
        smc_side = _side(row.get("smc_direction") or row.get("trade_direction"))
        macro_side = _side(row.get("macro_direction") or row.get("cluster_signal"))
        z = row.get("dominant_z_mad")
        r = row.get("realized_r")
        if smc_side == 0 or not _finite(r):
            continue
        normalized.append((smc_side, macro_side, float(z) if _finite(z) else None, float(r)))

    baseline = [r for _, _, _, r in normalized]
    gated = [r for smc, macro, z, r in normalized if macro == smc and z is not None and abs(z) >= threshold]
    overlap = [r for smc, macro, z, r in normalized if macro == smc and z is not None and abs(z) >= threshold]

    base_metrics = _metric(baseline)
    gated_metrics = _metric(gated)
    return {
        "methodology_version": "incremental-smc-alpha-v1",
        "production_activation": False,
        "frozen_parameters": {
            "mad_threshold_abs_z": FROZEN_MAD_THRESHOLD,
            "gate": "macro_direction == smc_direction AND |Z_MAD| >= 1.0",
            "parameter_fingerprint": _fingerprint({"mad_threshold_abs_z": FROZEN_MAD_THRESHOLD, "gate": "direction_alignment"}),
        },
        "baseline_smc": base_metrics,
        "smc_plus_macro": gated_metrics,
        "incremental": {
            "trade_count_delta": gated_metrics["trade_count"] - base_metrics["trade_count"],
            "mean_r_delta": None if base_metrics["mean"] is None or gated_metrics["mean"] is None else round(gated_metrics["mean"] - base_metrics["mean"], 6),
            "max_drawdown_delta": None if base_metrics["max_drawdown"] is None or gated_metrics["max_drawdown"] is None else round(gated_metrics["max_drawdown"] - base_metrics["max_drawdown"], 6),
            "trade_sharpe_delta": None if base_metrics["trade_sharpe"] is None or gated_metrics["trade_sharpe"] is None else round(gated_metrics["trade_sharpe"] - base_metrics["trade_sharpe"], 6),
            "coverage_pct": round(len(overlap) / len(baseline) * 100.0, 2) if baseline else 0.0,
        },
    }


def load_json_records(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return list(payload["records"])
    raise ValueError("Expected a JSON list or an object containing records")


def save_json_report(report: Mapping[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
