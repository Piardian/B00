from __future__ import annotations

import math
from statistics import mean, median, pstdev
from typing import Any, Iterable, Mapping, Sequence


def forward_return(prices: Sequence[float], horizon: int = 1) -> float | None:
    if horizon <= 0 or len(prices) <= horizon:
        return None
    start = float(prices[0])
    end = float(prices[horizon])
    if start == 0 or not math.isfinite(start) or not math.isfinite(end):
        return None
    value = (end / start) - 1.0
    return value if math.isfinite(value) else None


def _direction_for_gate(gate: str) -> int:
    gate = gate.upper()
    if gate in {"SHORT_ONLY"}:
        return -1
    return 1


def evaluate_gate_signal(rows: Iterable[Mapping[str, Any]], horizon: int = 1) -> dict[str, Any]:
    """Describe realized outcomes for externally supplied deterministic gate signals.

    The function never ranks gates and never treats the sample as causal evidence. For
    SHORT_ONLY rows, realized returns are sign-adjusted so positive values mean the
    requested short direction moved favorably.
    """
    if horizon <= 0:
        raise ValueError("horizon must be > 0")

    buckets: dict[str, list[float]] = {}
    for row in rows:
        gate = str(row.get("gate", "UNKNOWN")).upper()
        prices = row.get("future_prices")
        if not isinstance(prices, (list, tuple)):
            continue
        ret = forward_return(prices, horizon)
        if ret is None:
            continue
        signed_ret = ret * _direction_for_gate(gate)
        buckets.setdefault(gate, []).append(signed_ret)

    report: dict[str, Any] = {
        "horizon": horizon,
        "interpretation": "positive_forward_return_rate means favorable movement for the requested gate direction",
        "by_gate": {},
    }
    for gate, values in buckets.items():
        positive = sum(1 for value in values if value > 0)
        report["by_gate"][gate] = {
            "n": len(values),
            "positive_return_rate": positive / len(values),
            "mean_direction_adjusted_return": mean(values),
            "median_direction_adjusted_return": median(values),
            "population_std_direction_adjusted_return": pstdev(values) if len(values) > 1 else 0.0,
        }
    return report
