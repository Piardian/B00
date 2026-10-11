"""Generate a deterministic promotion decision from frozen research evidence.

This module exists to make the final gate explicit: data-complete evidence can still
return REQUIRES_EXECUTION_VALIDATION, and incomplete holdout data can never produce a
promotion pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from calibration.promotion_runner import build_promotion_report


def run(holdout_path: Path, smc_path: Path | None = None, output_path: Path | None = None) -> Mapping[str, Any]:
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    smc = json.loads(smc_path.read_text(encoding="utf-8")) if smc_path else None
    report = build_promotion_report(
        holdout if isinstance(holdout, list) else holdout.get("records", []),
        smc_trades=(smc if isinstance(smc, list) else smc.get("records", [])) if smc is not None else None,
    )
    if output_path is not None:
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


__all__ = ["run"]
