from __future__ import annotations

from itertools import product
from typing import Any, Callable, Iterable, Mapping


def grid(func: Callable[..., Any], parameters: Mapping[str, Iterable[Any]]) -> list[dict[str, Any]]:
    """Return deterministic parameter-sensitivity rows without selecting a preferred result."""
    names = list(parameters)
    values = [list(parameters[name]) for name in names]
    rows = []
    for combo in product(*values):
        kwargs = dict(zip(names, combo))
        rows.append({"parameters": kwargs, "result": func(**kwargs)})
    return rows


def summarize_binary_outcomes(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    values = [bool(row.get("result")) for row in rows]
    if not values:
        return {"n": 0, "positive_rate": 0.0}
    return {"n": len(values), "positive_rate": sum(values) / len(values)}
