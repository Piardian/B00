from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from calibration.surprise_sigma import calibrate_from_csv, write_calibration_profile


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit empirical surprise sigmas from a PIT calibration dataset.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).with_name("surprise_observations.csv"),
        help="Provider-backed PIT CSV input",
    )
    parser.add_argument("--calibration-end", required=True, type=parse_date)
    parser.add_argument("--validation-end", required=True, type=parse_date)
    parser.add_argument("--min-observations", type=int, default=30)
    parser.add_argument("--required-indicator", action="append", default=[])
    parser.add_argument(
        "--method",
        choices=["mad", "std"],
        default="mad",
        help="Empirical scale estimation method: 'mad' (Robust Median Absolute Deviation) or 'std' (Classical Std Dev)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("surprise_sigma_profile.json"),
    )
    args = parser.parse_args()

    if args.calibration_end >= args.validation_end:
        parser.error("--calibration-end must be before --validation-end")

    profile = calibrate_from_csv(
        args.input,
        args.calibration_end,
        args.validation_end,
        min_observations=args.min_observations,
        required_indicators=tuple(args.required_indicator),
        method=args.method,
    )
    write_calibration_profile(profile, args.output)
    print(f"Fitted {len(profile['sigmas'])} empirical sigmas [{args.method}] to {args.output}")
    print(f"Samples: {profile['sample_counts']}")
    if "validation_performance" in profile:
        perf = profile["validation_performance"]["aggregate"]
        print(f"OOS Validation (2024-2025, N={perf['sample_count']}): Std(Z)={perf['std_z']}, MSNR={perf['msnr']}, Within 1-Sigma={perf['pct_within_1sigma']}%, Within 2-Sigma={perf['pct_within_2sigma']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
