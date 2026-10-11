"""CI-safe promotion evidence contract check.

This checker verifies that research artifacts cannot silently become production
permissions. It is intentionally independent from live trading code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


REQUIRED_WINDOWS = ("2025_H2", "2026_YTD")
REQUIRED_SCENARIOS = ("CALM_10BP", "NEWS_30BP", "NEWS_50BP")


def validate_report(report: Mapping[str, Any]) -> None:
    if report.get("production_activation") is not False:
        raise AssertionError("promotion report must keep production_activation=false")
    frozen = report.get("frozen_parameters", {})
    if frozen.get("mad_threshold_abs_z") != 1.0:
        raise AssertionError("MAD threshold must remain frozen at 1.0")
    holdout = report.get("holdout_coverage", {}).get("windows", {})
    for name in REQUIRED_WINDOWS:
        status = holdout.get(name, {}).get("status")
        if status not in {"PASS_DATA", "INSUFFICIENT_DATA"}:
            raise AssertionError(f"invalid holdout status for {name}: {status!r}")


def validate_evidence_template(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("production_activation") is not False:
        raise AssertionError("template must never enable production")
    execution = payload.get("execution_stress", {})
    scenarios = tuple(execution.get("scenarios", ()))
    for scenario in REQUIRED_SCENARIOS:
        if scenario not in scenarios:
            raise AssertionError(f"missing execution scenario {scenario}")


__all__ = ["validate_report", "validate_evidence_template"]
