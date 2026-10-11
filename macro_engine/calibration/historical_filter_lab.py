"""Walk-forward, deterministic filter tests for the historical macro research dataset.

This module is deliberately conservative: filters are pre-registered, thresholds for
continuous features are learned from data strictly before each test year, and no
optimization is performed. It is a research evaluator, not a production signal gate.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

DEFAULT_TEST_YEARS = (2022, 2023, 2024, 2025)
COSTS_BPS = (0.0, 10.0, 15.0)


def _finite_float(row: Mapping[str, Any], key: str) -> Optional[float]:
    try:
        value = float(row.get(key, ""))
        return value if value == value and abs(value) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n", ""}:
        return False
    return bool(value)


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _trade_rows(rows: Iterable[Mapping[str, Any]], predicate: Callable[[Mapping[str, Any]], bool]) -> List[Mapping[str, Any]]:
    return [r for r in rows if int(float(r.get("cluster_signal", 0))) != 0 and predicate(r)]


def _metrics(rows: Sequence[Mapping[str, Any]], cost_bps: float = 0.0) -> Dict[str, Any]:
    gross = []
    for row in rows:
        signal = 1.0 if float(row["cluster_signal"]) > 0 else -1.0
        gross.append(signal * float(row["post_30m_usd_bps"]))
    net = [x - cost_bps for x in gross]
    if not net:
        return {
            "trade_count": 0,
            "hit_rate_pct": None,
            "mean_gross_bps": None,
            "mean_net_bps": None,
            "profit_factor": None,
            "max_drawdown_bps": None,
        }
    wins = [x for x in net if x > 0]
    losses = [abs(x) for x in net if x < 0]
    pf = (sum(wins) / sum(losses)) if losses else (999.0 if wins else 0.0)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in net:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trade_count": len(net),
        "hit_rate_pct": round(len(wins) / len(net) * 100.0, 2),
        "mean_gross_bps": round(mean(gross), 4),
        "mean_net_bps": round(mean(net), 4),
        "profit_factor": round(pf, 3),
        "max_drawdown_bps": round(max_dd, 4),
    }


def _baseline(_: Mapping[str, Any]) -> bool:
    return True


def _coherent(row: Mapping[str, Any]) -> bool:
    return _as_bool(row.get("cluster_all_aligned", False))


def _mad_actionable(row: Mapping[str, Any]) -> bool:
    return _as_bool(row.get("dominant_mad_actionable", False))


def _pre_not_extreme(row: Mapping[str, Any], threshold: Optional[float]) -> bool:
    value = _finite_float(row, "pre_60m_abs_bps")
    return threshold is not None and value is not None and value <= threshold


def _vol_not_extreme(row: Mapping[str, Any], threshold: Optional[float]) -> bool:
    value = _finite_float(row, "pre_realized_vol_bps")
    return threshold is not None and value is not None and value <= threshold


def _atr_not_extreme(row: Mapping[str, Any], threshold: Optional[float]) -> bool:
    value = _finite_float(row, "pre_atr_bps")
    return threshold is not None and value is not None and value <= threshold


def _pre_not_already_aligned(row: Mapping[str, Any]) -> bool:
    aligned = row.get("pre_60m_aligned")
    if aligned is None or str(aligned).strip() == "":
        return False
    return not _as_bool(aligned)


def _load_dataset(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("records", []))
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run_walk_forward_filter_lab(
    dataset: Sequence[Mapping[str, Any]],
    *,
    test_years: Sequence[int] = DEFAULT_TEST_YEARS,
    quantile: float = 0.75,
) -> Dict[str, Any]:
    """Evaluate fixed candidate filters using only prior-year rows to learn thresholds."""
    rows = sorted(dataset, key=lambda r: str(r.get("event_time_utc", "")))
    years = tuple(sorted({int(y) for y in test_years}))
    results: Dict[str, Any] = {
        "method": {
            "selection": "cluster_signal != 0 baseline",
            "threshold_learning": f"train-only empirical q={quantile:.2f}",
            "test_years": list(years),
            "cost_scenarios_bps": list(COSTS_BPS),
            "no_rule_optimization": True,
        },
        "by_year": {},
        "pooled_oos": {},
    }

    pooled: Dict[str, List[Mapping[str, Any]]] = {}
    for year in years:
        train = [r for r in rows if int(r.get("year", 0)) < year]
        test = [r for r in rows if int(r.get("year", 0)) == year]
        if not train:
            continue

        pre_values = [v for r in train if (v := _finite_float(r, "pre_60m_abs_bps")) is not None]
        vol_values = [v for r in train if (v := _finite_float(r, "pre_realized_vol_bps")) is not None]
        atr_values = [v for r in train if (v := _finite_float(r, "pre_atr_bps")) is not None]
        pre_q = _quantile(pre_values, quantile)
        vol_q = _quantile(vol_values, quantile)
        atr_q = _quantile(atr_values, quantile)

        rules: Dict[str, Callable[[Mapping[str, Any]], bool]] = {
            "baseline_sign": _baseline,
            "coherent_events": _coherent,
            "mad_actionable": _mad_actionable,
            "pre_move_not_extreme": lambda r, q=pre_q: _pre_not_extreme(r, q),
            "volatility_not_extreme": lambda r, q=vol_q: _vol_not_extreme(r, q),
            "atr_not_extreme": lambda r, q=atr_q: _atr_not_extreme(r, q),
            "pre_move_not_already_aligned": _pre_not_already_aligned,
            "coherent_and_mad": lambda r: _coherent(r) and _mad_actionable(r),
            "coherent_and_pre_move_not_extreme": lambda r, q=pre_q: _coherent(r) and _pre_not_extreme(r, q),
            "coherent_and_vol_not_extreme": lambda r, q=vol_q: _coherent(r) and _vol_not_extreme(r, q),
        }

        year_result: Dict[str, Any] = {
            "train_count": len(train),
            "test_count": len(test),
            "train_thresholds": {
                "pre_60m_abs_bps_q": None if pre_q is None else round(pre_q, 4),
                "pre_realized_vol_bps_q": None if vol_q is None else round(vol_q, 4),
                "pre_atr_bps_q": None if atr_q is None else round(atr_q, 4),
            },
            "filters": {},
        }

        for name, predicate in rules.items():
            selected = _trade_rows(test, predicate)
            per_cost = {str(int(cost)): _metrics(selected, cost_bps=cost) for cost in COSTS_BPS}
            year_result["filters"][name] = per_cost
            pooled.setdefault(name, []).extend(selected)
        results["by_year"][str(year)] = year_result

    for name, selected in sorted(pooled.items()):
        results["pooled_oos"][name] = {
            str(int(cost)): _metrics(selected, cost_bps=cost) for cost in COSTS_BPS
        }

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic historical filter lab")
    parser.add_argument("dataset", type=Path, nargs="?", default=Path(__file__).with_name("historical_event_research.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("historical_filter_lab.json"))
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_TEST_YEARS))
    parser.add_argument("--quantile", type=float, default=0.75)
    args = parser.parse_args()
    if not 0.5 <= args.quantile <= 0.95:
        raise SystemExit("--quantile must be between 0.50 and 0.95")

    dataset = _load_dataset(args.dataset)
    report = run_walk_forward_filter_lab(dataset, test_years=args.years, quantile=args.quantile)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
