from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, Mapping, Sequence

from calibration.surprise_sigma import load_observations_csv
from core.deterministic_controls import (
    INDICATOR_DIRECTIONS,
    chronological_split,
    fit_surprise_sigmas,
)


DEFAULT_REQUIRED_INDICATORS = (
    "nfp",
    "cpi",
    "core_cpi",
    "unemployment",
    "pmi",
    "gdp",
    "retail_sales",
)


def evaluate_rows(sigmas: Mapping[str, float], rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    zscores: list[float] = []
    grouped_z: Dict[str, list[float]] = {}
    for row in rows:
        kind = str(row.get("indicator_type", "")).lower()
        if kind not in sigmas:
            continue
        try:
            act = float(row["actual"])
            fc = float(row["forecast"])
            sigma = float(sigmas[kind])
            if sigma <= 0 or not math.isfinite(sigma):
                continue
            direction = INDICATOR_DIRECTIONS.get(kind, 1.0)
            # Pure raw float, unclipped, unrounded for unbiased econometric validation
            z = ((act - fc) * direction) / sigma
        except (KeyError, TypeError, ValueError):
            continue
        zscores.append(z)
        grouped_z.setdefault(kind, []).append(z)

    n = len(zscores)
    if not n:
        return {
            "sample_count": 0,
            "small_sample": True,
            "mean_z": 0.0,
            "se_mean_z": 0.0,
            "t_stat_mean_zero": 0.0,
            "std_z": 0.0,
            "msnr": 0.0,
            "pct_within_1sigma": 0.0,
            "pct_within_2sigma": 0.0,
            "by_indicator": {},
        }

    std_val = pstdev(zscores)
    se_val = std_val / math.sqrt(n)
    mean_val = mean(zscores)

    by_indicator: Dict[str, Any] = {}
    for ind, zs in grouped_z.items():
        k_n = len(zs)
        k_std = pstdev(zs)
        k_mean = mean(zs)
        by_indicator[ind] = {
            "sample_count": k_n,
            "mean_z": round(k_mean, 4),
            "std_z": round(k_std, 4),
            "msnr": round(mean(z * z for z in zs), 4),
            "pct_within_1sigma": round(sum(abs(z) <= 1.0 for z in zs) / k_n * 100.0, 2),
            "pct_within_2sigma": round(sum(abs(z) <= 2.0 for z in zs) / k_n * 100.0, 2),
        }

    return {
        "sample_count": n,
        "small_sample": n < 30,
        "mean_z": round(mean_val, 4),
        "se_mean_z": round(se_val, 4),
        "t_stat_mean_zero": round(mean_val / se_val, 4) if se_val > 0 else 0.0,
        "std_z": round(std_val, 4),
        "msnr": round(mean(z * z for z in zscores), 4),
        "pct_within_1sigma": round(sum(abs(z) <= 1.0 for z in zscores) / n * 100.0, 2),
        "pct_within_2sigma": round(sum(abs(z) <= 2.0 for z in zscores) / n * 100.0, 2),
        "by_indicator": by_indicator,
    }


def run_expanding_walk_forward(
    rows: Iterable[Mapping[str, Any]],
    *,
    calibration_start: dt.date,
    first_validation_year: int,
    last_validation_year: int,
    min_observations: int = 30,
    required_indicators: Sequence[str] = DEFAULT_REQUIRED_INDICATORS,
) -> Dict[str, Any]:
    normalized = list(rows)
    folds: list[Dict[str, Any]] = []

    for year in range(first_validation_year, last_validation_year + 1):
        calibration_end = dt.date(year - 1, 12, 31)
        validation_end = dt.date(year, 12, 31)
        split = chronological_split(normalized, calibration_end, validation_end)
        calibration = [
            r for r in split["calibration"]
            if dt.date.fromisoformat(str(r["date"])) >= calibration_start
        ]
        validation = split["validation"]

        methods: Dict[str, Any] = {}
        for method in ("mad", "std"):
            sigmas = fit_surprise_sigmas(
                calibration,
                min_observations=min_observations,
                method=method,
            )
            missing = [ind for ind in required_indicators if ind.lower() not in sigmas]
            methods[method] = {
                "status": "ok" if not missing else "insufficient_data",
                "missing_indicators": missing,
                "sigmas": sigmas,
                "validation": evaluate_rows(sigmas, validation) if not missing else evaluate_rows({}, validation),
            }

        delta_std_target_error = None
        if (
            methods.get("mad", {}).get("status") == "ok"
            and methods.get("std", {}).get("status") == "ok"
        ):
            mad_std = methods["mad"]["validation"]["std_z"]
            std_std = methods["std"]["validation"]["std_z"]
            # Negative means MAD is closer to unit variance 1.0
            delta_std_target_error = round(abs(mad_std - 1.0) - abs(std_std - 1.0), 4)

        folds.append({
            "validation_year": year,
            "calibration_end": calibration_end.isoformat(),
            "validation_end": validation_end.isoformat(),
            "calibration_sample_count": len(calibration),
            "validation_sample_count": len(validation),
            "small_sample": len(validation) < 30,
            "delta_std_target_error": delta_std_target_error,
            "methods": methods,
        })

    return {
        "methodology": "expanding_walk_forward",
        "calibration_start": calibration_start.isoformat(),
        "first_validation_year": first_validation_year,
        "last_validation_year": last_validation_year,
        "folds": folds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run expanding walk-forward validation for surprise sigma estimators.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).with_name("surprise_observations.csv"),
    )
    parser.add_argument("--calibration-start", type=dt.date.fromisoformat, default=dt.date(2016, 1, 1))
    parser.add_argument("--first-validation-year", type=int, default=2020)
    parser.add_argument("--last-validation-year", type=int, default=2025)
    parser.add_argument("--min-observations", type=int, default=30)
    parser.add_argument("--required-indicator", action="append", default=[])
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("walk_forward_validation.json"))
    args = parser.parse_args()

    if args.first_validation_year <= args.calibration_start.year:
        parser.error("first validation year must be after calibration start year")
    if args.last_validation_year < args.first_validation_year:
        parser.error("last validation year must be >= first validation year")

    rows = load_observations_csv(args.input)
    required_indicators = tuple(args.required_indicator) if args.required_indicator else DEFAULT_REQUIRED_INDICATORS
    report = run_expanding_walk_forward(
        rows,
        calibration_start=args.calibration_start,
        first_validation_year=args.first_validation_year,
        last_validation_year=args.last_validation_year,
        min_observations=args.min_observations,
        required_indicators=required_indicators,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Walk-forward validation written to {args.output}\n")
    print(f"{'YEAR':<6} | {'METHOD':<8} | {'N_VAL':<8} | {'MEAN(Z)':<8} | {'STD(Z)':<8} | {'MSNR':<8} | {'IN 1SIG':<8} | {'IN 2SIG':<8} | {'DELTA_ERR'}")
    print("-" * 92)
    for f in report["folds"]:
        y = f["validation_year"]
        sm_note = " *" if f["small_sample"] else ""
        delta_str = f"{f['delta_std_target_error']:+7.4f}" if f.get("delta_std_target_error") is not None else "   N/A "
        for m in ("mad", "std"):
            info = f["methods"][m]
            if info["status"] != "ok":
                print(f"{y:<6} | {m.upper():<8} | {str(f['validation_sample_count']) + sm_note:<8} | INSUFFICIENT DATA ({', '.join(info['missing_indicators'])})")
            else:
                v = info["validation"]
                d_col = delta_str if m == "mad" else "       "
                print(f"{y:<6} | {m.upper():<8} | {str(v['sample_count']) + sm_note:<8} | {v['mean_z']:>+7.4f}  | {v['std_z']:>7.4f}  | {v['msnr']:>7.4f}  | {v['pct_within_1sigma']:>6.2f}%  | {v['pct_within_2sigma']:>6.2f}%  | {d_col}")
        print("-" * 92)
    print("* Note: N < 30 labeled as small_sample; delta_err = |Std(Z_mad)-1.0| - |Std(Z_std)-1.0| (negative = MAD closer to 1.0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
