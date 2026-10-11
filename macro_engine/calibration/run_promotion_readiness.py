"""Execute the frozen promotion-readiness test against repository data."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from calibration.promotion_simulation import evaluate_frozen_holdout

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "historical_event_research.json"
HOLDOUT_ADAPTED = ROOT / "holdout_macro_adapted.json"
SMC_LEDGER_CANDIDATES = (
    ROOT / "smc_historical_trade_ledger.json",
    ROOT / "smc_historical_trade_ledger.csv",
    ROOT.parent.parent / "benchmark" / "smc_historical_trade_ledger.json",
)
EXECUTION_DATA_CANDIDATES = (
    ROOT / "execution_bars_m1_m5.json",
    ROOT / "execution_bars_m1_m5.csv",
)


def load_records() -> tuple[list[dict], dict]:
    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    records = list(payload.get("records", [])) if isinstance(payload, dict) else list(payload)
    if not isinstance(records, list):
        raise ValueError("historical_event_research.json has no records list")

    recovered_holdout_info = {
        "integrated": False,
        "recovered_clusters_count": 0,
        "recovered_file": None,
    }

    if HOLDOUT_ADAPTED.exists():
        try:
            h_payload = json.loads(HOLDOUT_ADAPTED.read_text(encoding="utf-8"))
            h_records = h_payload.get("records", []) if isinstance(h_payload, dict) else h_payload
            if isinstance(h_records, list) and h_records:
                existing_times = {str(r.get("event_time_utc")) for r in records}
                added = 0
                for hr in h_records:
                    if str(hr.get("event_time_utc")) not in existing_times:
                        records.append(hr)
                        added += 1
                recovered_holdout_info = {
                    "integrated": True,
                    "recovered_clusters_count": added,
                    "recovered_file": str(HOLDOUT_ADAPTED.name),
                }
        except Exception:
            pass

    return records, recovered_holdout_info


def coverage(records: list[dict]) -> dict:
    timestamps = []
    for row in records:
        value = row.get("event_time_utc")
        if not value:
            continue
        try:
            ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            timestamps.append(ts.astimezone(timezone.utc))
        except ValueError:
            continue

    windows = {
        "2025_H2": (datetime(2025, 7, 1, tzinfo=timezone.utc), datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)),
        "2026_YTD": (datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 9, 17, 23, 59, 59, tzinfo=timezone.utc)),
    }
    return {
        "dataset_rows": len(records),
        "earliest_event_utc": min(timestamps).isoformat() if timestamps else None,
        "latest_event_utc": max(timestamps).isoformat() if timestamps else None,
        "window_rows": {
            name: sum(1 for ts in timestamps if start <= ts <= end)
            for name, (start, end) in windows.items()
        },
    }


def first_existing(candidates: tuple[Path, ...]) -> str | None:
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def main() -> int:
    records, holdout_info = load_records()
    # A full half-year holdout window requires at least 15 clusters for complete PASS_DATA status.
    # Partial holdout data (e.g. 4 clusters in July 2025) is evaluated but remains INSUFFICIENT_DATA.
    holdout = evaluate_frozen_holdout(records, min_window_rows=15)
    cov = coverage(records)
    smc_ledger = first_existing(SMC_LEDGER_CANDIDATES)
    execution_data = first_existing(EXECUTION_DATA_CANDIDATES)

    report = {
        "methodology_version": "promotion-readiness-run-v1",
        "promotion_status": "BLOCKED_PENDING_DATA",
        "recovered_holdout_integration": holdout_info,
        "frozen_holdout": holdout,
        "coverage": cov,
        "required_data": {
            "smc_trade_ledger": smc_ledger,
            "execution_m1_m5_or_ticks": execution_data,
        },
        "checks": {
            "threshold_frozen": holdout["frozen_parameters"]["mad_threshold_abs_z"] == 1.0,
            "no_holdout_fitting": holdout["frozen_parameters"]["no_holdout_fitting"] is True,
            "holdout_2025_h2_populated": holdout["windows"]["2025_H2"]["status"] == "PASS_DATA",
            "holdout_2026_ytd_populated": holdout["windows"]["2026_YTD"]["status"] == "PASS_DATA",
            "smc_ledger_available": smc_ledger is not None,
            "execution_data_available": execution_data is not None,
        },
    }
    report["promotion_status"] = (
        "READY_FOR_PROMOTION_REVIEW"
        if all(report["checks"].values())
        else "BLOCKED_PENDING_DATA"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
