"""Exact mapping between event time, bar-open timestamps, and horizon closes."""

from __future__ import annotations

import datetime as dt


def target_bar_open(event_time: dt.datetime, interval_minutes: int, horizon_minutes: int) -> dt.datetime:
    """Return the bar-open timestamp whose CLOSE occurs exactly at the requested horizon.

    For an event at t on bars of length I, the event bar's close is t+I. Therefore
    a horizon H maps to bar open t + H - I. H must be a positive multiple of I.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if horizon_minutes <= 0 or horizon_minutes % interval_minutes != 0:
        raise ValueError(
            f"horizon_minutes={horizon_minutes} must be a positive multiple of interval_minutes={interval_minutes}"
        )
    if event_time.tzinfo is None:
        raise ValueError("event_time must be timezone-aware")
    return event_time + dt.timedelta(minutes=horizon_minutes - interval_minutes)


def target_bar_sequence(
    event_time: dt.datetime,
    interval_minutes: int,
    horizon_minutes: int,
) -> list[dt.datetime]:
    """Return all bar-open timestamps included in an outcome through horizon H."""
    target = target_bar_open(event_time, interval_minutes, horizon_minutes)
    count = horizon_minutes // interval_minutes
    return [event_time + dt.timedelta(minutes=i * interval_minutes) for i in range(count)]
