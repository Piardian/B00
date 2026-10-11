"""Deterministic schema adapter for recovered point-in-time holdout macro observations.

Converts row-level observation CSV (such as holdout_macro_recovered.csv) into
canonical event cluster records compatible with historical_event_research.json,
evaluate_frozen_holdout, and the Begonya promotion runner.

Enforces:
1. Strict Point-in-Time (PIT) provenance validation.
2. Frozen pre-2025-07-01 calibration sigmas (zero holdout leakage).
3. Exact-horizon market outcomes via MT5 M30 bars or explicit bar maps.
4. Retention of full audit provenance metadata in each record.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from calibration.event_horizon import target_bar_open
from calibration.historical_event_research import (
    DEFAULT_HORIZONS,
    DEFAULT_PRE_WINDOWS,
    DEFAULT_VOL_LOOKBACK_BARS,
    _atr_bps,
    _cluster_observations,
    _cluster_signal,
    _outcome_path,
    _realized_vol_bps,
    _sign,
    _window_return_bps,
)
from calibration.market_response_validation_v2 import fetch_mt5_bars
from core.deterministic_controls import INDICATOR_DIRECTIONS, fit_surprise_sigmas

UTC = dt.timezone.utc
FROZEN_CALIBRATION_CUTOFF = dt.datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC)
DEFAULT_MIN_OBSERVATIONS = 15


def parse_pit_boolean(value: Any) -> bool:
    """Parse boolean point_in_time flag strictly."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    text = str(value).strip().lower()
    return text in {"true", "1", "yes"}


def validate_observation_row(row: Mapping[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate that an observation row satisfies PIT provenance and schema contracts."""
    pit = parse_pit_boolean(row.get("point_in_time"))
    if not pit:
        return False, "point_in_time is False or missing"

    required_fields = ("event_timestamp_utc", "indicator_type", "actual", "forecast", "source", "source_url")
    for f in required_fields:
        val = str(row.get(f, "")).strip()
        if not val:
            return False, f"missing required field: {f}"

    kind = str(row.get("indicator_type", "")).strip().lower()
    if kind not in INDICATOR_DIRECTIONS:
        return False, f"unrecognized indicator_type: {kind}"

    try:
        float(row["actual"])
        float(row["forecast"])
    except (TypeError, ValueError):
        return False, "actual or forecast cannot be converted to float"

    try:
        ts_text = str(row["event_timestamp_utc"]).strip().replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(ts_text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return False, "invalid event_timestamp_utc format"

    return True, None


def load_and_validate_recovered_csv(
    csv_path: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Read recovered CSV, returning (accepted_rows, rejected_rows)."""
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for row in all_rows:
        is_valid, reason = validate_observation_row(row)
        if is_valid:
            accepted.append(dict(row))
        else:
            rejected.append({"row": dict(row), "reason": reason})

    return accepted, rejected


def compute_frozen_sigmas(
    canonical_observations_path: Path,
    cutoff_utc: dt.datetime = FROZEN_CALIBRATION_CUTOFF,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Fit MAD and STD sigmas strictly on data before cutoff_utc.

    Enforces zero leakage from holdout data into sigma estimation.
    """
    with canonical_observations_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        pre_cutoff_rows = []
        for r in reader:
            ts_str = str(r.get("event_timestamp_utc", "")).strip().replace("Z", "+00:00")
            try:
                t = dt.datetime.fromisoformat(ts_str)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=UTC)
                if t < cutoff_utc:
                    pre_cutoff_rows.append(r)
            except ValueError:
                continue

    mad_sigmas = fit_surprise_sigmas(pre_cutoff_rows, min_observations=min_observations, method="mad")
    std_sigmas = fit_surprise_sigmas(pre_cutoff_rows, min_observations=min_observations, method="std")
    return mad_sigmas, std_sigmas


def adapt_holdout_observations(
    recovered_rows: Sequence[Mapping[str, Any]],
    mad_sigmas: Mapping[str, float],
    std_sigmas: Mapping[str, float],
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    *,
    timeframe_minutes: int = 30,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    pre_windows: Sequence[int] = DEFAULT_PRE_WINDOWS,
    vol_lookback_bars: int = DEFAULT_VOL_LOOKBACK_BARS,
) -> List[Dict[str, Any]]:
    """Cluster validated holdout observations and calculate exact-horizon market outcomes."""

    # Group directly by normalized event_timestamp_utc
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for r in recovered_rows:
        ts_text = str(r.get("event_timestamp_utc", "")).strip().replace("Z", "+00:00")
        try:
            t = dt.datetime.fromisoformat(ts_text)
            if t.tzinfo is None:
                t = t.replace(tzinfo=UTC)
            groups.setdefault(t.astimezone(UTC).isoformat(), []).append(r)
        except ValueError:
            continue

    clusters = [groups[k] for k in sorted(groups.keys())]
    records: List[Dict[str, Any]] = []

    for group in clusters:
        # Parse timestamp
        ts_str = str(group[0]["event_timestamp_utc"]).strip().replace("Z", "+00:00")
        event_time = dt.datetime.fromisoformat(ts_str)
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=UTC)
        event_time = event_time.astimezone(UTC)

        base = bar_map.get(event_time)
        if base is None:
            continue

        signal_info = _cluster_signal(group)
        signal = int(signal_info["cluster_signal"])
        indicators = sorted({str(r.get("indicator_type", "")).strip().lower() for r in group})

        mad_zs: List[float] = []
        std_zs: List[float] = []
        signed_surprises: List[float] = []
        provenance_list: List[Dict[str, Any]] = []

        for row in group:
            kind = str(row.get("indicator_type", "")).strip().lower()
            if kind not in mad_sigmas or kind not in std_sigmas:
                continue
            try:
                actual = float(row["actual"])
                forecast = float(row["forecast"])
                previous = float(row.get("previous", 0.0)) if str(row.get("previous", "")).strip() else None
                direction = INDICATOR_DIRECTIONS.get(kind, 1.0)
                raw = (actual - forecast) * direction
                signed_surprises.append(raw)
                mad_zs.append(raw / mad_sigmas[kind])
                std_zs.append(raw / std_sigmas[kind])
                provenance_list.append({
                    "indicator_type": kind,
                    "event": row.get("event"),
                    "actual": actual,
                    "forecast": forecast,
                    "previous": previous,
                    "surprise": raw,
                    "source": row.get("source"),
                    "source_url": row.get("source_url"),
                    "provider": row.get("provider"),
                    "point_in_time": True,
                })
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue

        if not mad_zs:
            continue

        dominant = max(range(len(mad_zs)), key=lambda idx: abs(mad_zs[idx]))
        record: Dict[str, Any] = {
            "event_time_utc": event_time.isoformat(),
            "year": event_time.year,
            "indicators": "+".join(indicators),
            "cluster_size": len(group),
            "cluster_signal": signal,
            "cluster_coherence": signal_info["cluster_coherence"],
            "cluster_all_aligned": signal_info["cluster_all_aligned"],
            "mean_signed_surprise": round(mean(signed_surprises), 8),
            "mean_abs_mad_z": round(mean(abs(z) for z in mad_zs), 6),
            "max_abs_mad_z": round(max(abs(z) for z in mad_zs), 6),
            "dominant_z_mad": round(mad_zs[dominant], 6),
            "dominant_z_std": round(std_zs[dominant], 6),
            "provenance_observations": provenance_list,
        }

        # Pre-event features
        for minutes in sorted({int(v) for v in pre_windows}):
            if minutes <= 0 or minutes % timeframe_minutes != 0:
                continue
            start = event_time - dt.timedelta(minutes=minutes)
            pre = _window_return_bps(bar_map, start, event_time)
            record[f"pre_{minutes}m_usd_bps"] = None if pre is None else round(pre, 4)
            record[f"pre_{minutes}m_abs_bps"] = None if pre is None else round(abs(pre), 4)
            record[f"pre_{minutes}m_aligned"] = None if pre is None or signal == 0 else (_sign(pre) == signal)

        record["pre_realized_vol_bps"] = _realized_vol_bps(
            bar_map, event_time, timeframe_minutes, vol_lookback_bars
        )
        record["pre_atr_bps"] = _atr_bps(
            bar_map, event_time, timeframe_minutes, vol_lookback_bars
        )

        # Exact-horizon outcomes
        outcome_complete = True
        for horizon in sorted({int(v) for v in horizons}):
            if horizon <= 0 or horizon % timeframe_minutes != 0:
                outcome_complete = False
                break
            outcome = _outcome_path(bar_map, event_time, timeframe_minutes, horizon)
            if outcome is None:
                outcome_complete = False
                break
            usd_final, mfe, mae, bar_count = outcome
            record[f"post_{horizon}m_usd_bps"] = round(usd_final, 4)
            record[f"post_{horizon}m_mfe_bps"] = round(mfe, 4)
            record[f"post_{horizon}m_mae_bps"] = round(mae, 4)
            record[f"post_{horizon}m_hit"] = bool(signal != 0 and signal * usd_final > 0)
            record[f"post_{horizon}m_observed_bars"] = bar_count

        if not outcome_complete:
            continue

        for horizon in sorted({int(v) for v in horizons}):
            ret = record[f"post_{horizon}m_usd_bps"]
            if signal != 0:
                record[f"trade_{horizon}m_gross_bps"] = round(signal * ret, 4)

        record["dominant_mad_actionable"] = abs(mad_zs[dominant]) >= 1.0
        record["dominant_mad_directional_hit_30m"] = bool(
            signal != 0
            and abs(mad_zs[dominant]) >= 1.0
            and 30 in horizons
            and signal * record.get("post_30m_usd_bps", 0.0) > 0
        )

        records.append(record)

    return records


def build_adapted_holdout_dataset(
    recovered_csv_path: Path,
    canonical_observations_path: Path,
    symbol: str = "EURUSD",
    bar_map: Optional[Mapping[dt.datetime, Mapping[str, float]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """End-to-end builder for recovered holdout dataset."""
    accepted, rejected = load_and_validate_recovered_csv(recovered_csv_path)
    mad_sigmas, std_sigmas = compute_frozen_sigmas(canonical_observations_path)

    if bar_map is None:
        bar_map = fetch_mt5_bars(symbol=symbol, timeframe="M30", count=65000)

    records = adapt_holdout_observations(accepted, mad_sigmas, std_sigmas, bar_map)

    diagnostics = {
        "recovered_observations_total": len(accepted) + len(rejected),
        "accepted_pit_observations": len(accepted),
        "rejected_observations": len(rejected),
        "rejection_details": rejected,
        "adapted_event_clusters": len(records),
        "actionable_clusters_mad_ge_1": sum(1 for r in records if r.get("dominant_mad_actionable")),
        "symbol": symbol,
        "timeframe": "M30",
        "frozen_calibration_cutoff_utc": FROZEN_CALIBRATION_CUTOFF.isoformat(),
        "sigmas_used": {
            k: {"sigma_mad": round(mad_sigmas[k], 4), "sigma_std": round(std_sigmas[k], 4)}
            for k in sorted(mad_sigmas.keys())
        },
    }

    return records, diagnostics


def export_adapted_holdout_json(
    output_path: Path,
    recovered_csv_path: Path,
    canonical_observations_path: Path,
    symbol: str = "EURUSD",
    bar_map: Optional[Mapping[dt.datetime, Mapping[str, float]]] = None,
) -> Path:
    """Build and write adapted holdout records to JSON."""
    records, diag = build_adapted_holdout_dataset(
        recovered_csv_path,
        canonical_observations_path,
        symbol=symbol,
        bar_map=bar_map,
    )
    payload = {
        "metadata": {
            "source_type": "recovered_holdout_macro",
            "symbol": symbol,
            "timeframe": "M30",
            "scope": "holdout_evaluation_only",
            "frozen_calibration_cutoff_utc": FROZEN_CALIBRATION_CUTOFF.isoformat(),
        },
        "diagnostics": diag,
        "records": records,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def main() -> int:
    root = Path(__file__).resolve().parent
    csv_path = root / "holdout_macro_recovered.csv"
    obs_path = root / "surprise_observations.csv"
    out_path = root / "holdout_macro_adapted.json"

    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        return 1

    path = export_adapted_holdout_json(out_path, csv_path, obs_path, symbol="EURUSD")
    print(f"Exported adapted holdout dataset to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

