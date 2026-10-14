"""Audit persisted Begonya 00 backtest summaries without changing strategy code."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS = (
    ROOT / "data" / "optimized_1y_backtest_result.json",
    ROOT / "data" / "custom_12m_backtest_result.json",
)


def load_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return data


def audit(path: Path) -> list[str]:
    data = load_object(path)
    lines = [f"## {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"]
    lines.append(f"- Period: {data.get('period', 'NOT_RECORDED')}")
    if "macro_gated_results" in data and "ungated_results" in data:
        gated = data["macro_gated_results"]
        ungated = data["ungated_results"]
        lines.extend([
            f"- Macro-gated: trades={gated.get('total_trades', 'N/A')}, "
            f"net_R={gated.get('net_r', 'N/A')}, max_DD_pct={gated.get('max_drawdown_pct', 'N/A')}",
            f"- Ungated: trades={ungated.get('total_trades', 'N/A')}, "
            f"net_R={ungated.get('net_r', 'N/A')}, max_DD_pct={ungated.get('max_drawdown_pct', 'N/A')}",
        ])
        if isinstance(gated.get("net_r"), (int, float)) and gated["net_r"] < 0:
            lines.append("- FINDING: Macro-gated result is negative net R; do not describe the strategy as profitable from this report.")
        if isinstance(ungated.get("net_r"), (int, float)) and ungated["net_r"] < 0:
            lines.append("- FINDING: Ungated result is negative net R.")
        if isinstance(gated.get("max_drawdown_pct"), (int, float)) and gated["max_drawdown_pct"] >= 30:
            lines.append("- RISK: Macro-gated reported drawdown is at least 30%; review risk sizing and equity-curve calculation.")
        veto = data.get("veto_stats")
        if isinstance(veto, dict):
            lines.append(f"- Veto/approval counts: {json.dumps(veto, sort_keys=True)}")
    else:
        lines.extend([
            f"- Trades: {data.get('total_trades', 'N/A')}",
            f"- Win rate: {data.get('win_rate', 'N/A')}",
            f"- Net R: {data.get('total_net_r', 'N/A')}",
            f"- Fixed-model result: {json.dumps(data.get('fixed_model', {}), sort_keys=True)}",
        ])
        breakdown = data.get("strategy_breakdown")
        if isinstance(breakdown, dict):
            for name, result in sorted(breakdown.items()):
                lines.append(
                    f"- Strategy {name}: trades={result.get('trades', 'N/A')}, "
                    f"net_R={result.get('net_r', 'N/A')}"
                )
                if result.get("trades") == 0:
                    lines.append(f"- COVERAGE GAP: {name} has zero reported trades; this report does not validate that strategy leg.")
    lines.append("- Scope: persisted summary audit only; raw candles, fills, slippage, and look-ahead behavior are not revalidated here.")
    return lines


def main() -> int:
    print("# Begonya 00 Backtest Audit")
    failures = 0
    for path in DEFAULT_REPORTS:
        if not path.exists():
            print(f"\n## MISSING: {path}")
            failures += 1
            continue
        try:
            print("\n" + "\n".join(audit(path)))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"\n## INVALID REPORT: {path}: {exc}")
            failures += 1
    print("\n## Interpretation")
    print("- This tool reports stored metrics; it does not repair or optimize a strategy.")
    print("- Different reports must not be compared unless date range, universe, execution rules, and costs match.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
