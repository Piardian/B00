from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Dict, Iterable, Mapping

from data_quality import DataUnavailableError


REPLAY_SCHEMA_VERSION = 1


def _parse_timestamp(raw_ts: Any) -> dt.datetime:
    if raw_ts is None:
        raise DataUnavailableError("Replay snapshot timestamp is required")
    try:
        ts = dt.datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise DataUnavailableError(f"Invalid replay timestamp: {raw_ts!r}") from exc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def validate_snapshot_no_lookahead(snapshot: Mapping[str, Any], as_of: dt.datetime) -> None:
    ts = _parse_timestamp(snapshot.get("timestamp") or snapshot.get("as_of"))
    ref = as_of if as_of.tzinfo else as_of.replace(tzinfo=dt.timezone.utc)
    ref = ref.astimezone(dt.timezone.utc)
    if ts > ref:
        raise DataUnavailableError(
            f"Look-ahead leakage detected: snapshot={ts.isoformat()} > as_of={ref.isoformat()}"
        )


def validate_replay_dataset(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    validated = []
    for row in rows:
        if row.get("schema_version", REPLAY_SCHEMA_VERSION) != REPLAY_SCHEMA_VERSION:
            raise ValueError("Unsupported replay schema version")
        row_ts = _parse_timestamp(row.get("timestamp"))
        market = row.get("market")
        fred = row.get("fred")
        if not isinstance(market, Mapping) or not market:
            raise DataUnavailableError("Replay row requires a non-empty market snapshot")
        if not isinstance(fred, Mapping) or not fred:
            raise DataUnavailableError("Replay row requires a non-empty FRED snapshot")
        validate_snapshot_no_lookahead(market, row_ts)
        validate_snapshot_no_lookahead(fred, row_ts)
        events = row.get("calendar_events", [])
        if not isinstance(events, list):
            raise DataUnavailableError("Replay calendar_events must be a list")
        for event in events:
            if not isinstance(event, Mapping):
                raise DataUnavailableError("Replay calendar event must be a mapping")
            # Scheduled events may occur after the replay timestamp; only a populated
            # actual value is disallowed before that event's publication timestamp.
            event_ts_raw = event.get("event_time_utc") or event.get("time")
            actual = event.get("actual")
            if event_ts_raw and actual not in (None, ""):
                event_ts = _parse_timestamp(event_ts_raw)
                if event_ts > row_ts:
                    raise DataUnavailableError(
                        "Look-ahead leakage detected: calendar actual exists before event time"
                    )
        validated.append(row)
    return validated


def chronological_rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    validated = validate_replay_dataset(rows)
    return sorted(validated, key=lambda row: _parse_timestamp(row["timestamp"]))


def run_replay(
    rows: Iterable[Mapping[str, Any]],
    processor: Callable[..., Dict[str, Any]],
) -> list[Dict[str, Any]]:
    """Run deterministic replay rows after validation; processor must accept explicit inputs."""
    results: list[Dict[str, Any]] = []
    state: Dict[str, Any] = {}
    for row in chronological_rows(rows):
        as_of = _parse_timestamp(row["timestamp"])
        result = processor(
            row["market"],
            row["fred"],
            list(row.get("calendar_events", [])),
            as_of_date=as_of.date(),
            as_of_datetime=as_of,
            now_utc=as_of,
            previous_regime_state=dict(state),
        )
        state = dict(result.get("regime_state", {}))
        results.append(result)
    return results
