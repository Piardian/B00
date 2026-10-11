"""Reproducible promotion-evidence runner for the macro + SMC stack.

This runner is deliberately conservative. It consumes already-materialized research
artifacts and refuses to manufacture evidence when holdout, execution, or SMC ledger
data are incomplete. It writes a single auditable JSON report and never changes
production gates.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from calibration.promotion_simulation import (
    DEFAULT_HOLDOUT_WINDOWS,
    FROZEN_MAD_THRESHOLD,
    evaluate_frozen_holdout,
    evaluate_incremental_smc_alpha,
)

UTC = dt.timezone.utc
REQUIRED_HOLDOUT_WINDOWS = tuple(window.name for window in DEFAULT_HOLDOUT_WINDOWS)


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


def _load_records(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return list(payload)
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return list(payload["records"])
    raise ValueError(f"Expected JSON list or object.records in {path}")


def _validate_holdout_coverage(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    timestamps = [_parse_time(r.get("event_time_utc") or r.get("event_timestamp_utc")) for r in records]
    valid = [t for t in timestamps if t is not None]
    source_min = min(valid).isoformat() if valid else None
    source_max = max(valid).isoformat() if valid else None

    windows: Dict[str, Any] = {}
    for window in DEFAULT_HOLDOUT_WINDOWS:
        count = sum(1 for t in valid if window.start <= t <= window.end)
        windows[window.name] = {
            "rows": count,
            "status": "PASS_DATA" if count > 0 else "INSUFFICIENT_DATA",
        }
    complete = all(windows[name]["status"] == "PASS_DATA" for name in REQUIRED_HOLDOUT_WINDOWS)
    return {
        "source_rows": len(records),
        "valid_timestamp_rows": len(valid),
        "source_min_utc": source_min,
        "source_max_utc": source_max,
        "windows": windows,
        "complete": complete,
    }


def build_promotion_report(
    holdout_records: Sequence[Mapping[str, Any]],
    *,
    smc_trades: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    holdout_coverage = _validate_holdout_coverage(holdout_records)
    holdout = evaluate_frozen_holdout(holdout_records)

    incremental = None
    incremental_status = "NOT_RUN"
    if smc_trades is not None:
        if smc_trades:
            incremental = evaluate_incremental_smc_alpha(smc_trades)
            incremental_status = "PASS_DATA"
        else:
            incremental_status = "INSUFFICIENT_DATA"

    holdout_ready = holdout_coverage["complete"]
    incremental_ready = incremental_status == "PASS_DATA"
    production_ready = bool(holdout_ready and incremental_ready)

    if production_ready:
        decision = "REQUIRES_EXECUTION_VALIDATION"
    elif not holdout_ready:
        decision = "HOLDOUT_INCOMPLETE"
    elif not incremental_ready:
        decision = "SMC_LEDGER_INCOMPLETE"
    else:
        decision = "NOT_READY"

    return {
        "methodology_version": "promotion-runner-v1",
        "production_activation": False,
        "decision": decision,
        "frozen_parameters": {
            "mad_threshold_abs_z": FROZEN_MAD_THRESHOLD,
            "holdout_fitting": False,
            "threshold_optimization": False,
        },
        "holdout_coverage": holdout_coverage,
        "holdout_evaluation": holdout,
        "incremental_smc_status": incremental_status,
        "incremental_smc_alpha": incremental,
        "promotion_ready": production_ready,
        "blocking_requirements": [
            "complete_2025_H2_and_2026_holdout",
            "actual_M5_M1_or_tick_execution_validation",
            "complete_SMC_trade_ledger",
            "stable_results_across_preregistered_execution_scenarios",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build auditable promotion evidence")
    parser.add_argument("holdout_records", type=Path)
    parser.add_argument("--smc-trades", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("promotion_report.json"))
    args = parser.parse_args()

    holdout_records = _load_records(args.holdout_records)
    smc_trades = _load_records(args.smc_trades) if args.smc_trades else None
    report = build_promotion_report(holdout_records, smc_trades=smc_trades)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
