"""CLI verifier for the research promotion evidence contract."""

from __future__ import annotations

import argparse
from pathlib import Path

from calibration.promotion_ci_check import validate_evidence_template, validate_report
from calibration.promotion_runner import _load_records, build_promotion_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify promotion evidence contract")
    parser.add_argument("template", type=Path)
    parser.add_argument("--holdout", type=Path)
    args = parser.parse_args()

    validate_evidence_template(args.template)
    if args.holdout:
        report = build_promotion_report(_load_records(args.holdout))
        validate_report(report)
        print(report["decision"])
    else:
        print("TEMPLATE_OK")


if __name__ == "__main__":
    main()
