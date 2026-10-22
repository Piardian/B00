"""Deterministic entry rules shared by live execution and research helpers."""
from datetime import datetime, timezone, timedelta
import math
import pandas as pd

from . import config

TRT = timezone(timedelta(hours=3))
NO_FILL_REASONS = {
    "INVALID_GHOST_SIGNAL", "EXPIRED_NO_FILL", "TIMEOUT_NO_FILL",
    "ENTRY_REACTION_REJECTED", "RISK_LIMIT_CANCELLED",
}


def utc_time(value, *, legacy_local=False):
    dt = pd.Timestamp(value).to_pydatetime()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TRT if legacy_local else timezone.utc)
    return dt.astimezone(timezone.utc)


def completed_bars(frame, minutes, now=None):
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    now = utc_time(now or datetime.now(timezone.utc))
    df = df[df.datetime + pd.Timedelta(minutes=minutes) <= now]
    return df.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)


def higher_timeframe_features(frame, source_minutes=60):
    """UTC 4h features become available only at bucket close (no lookahead)."""
    df = frame.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    series = df.sort_values("datetime").drop_duplicates("datetime").set_index("datetime")["close"]
    groups = series.resample("4h", origin="start_day", label="left", closed="left")
    close = groups.last()[groups.count() == 240 // source_minutes].dropna()
    ema50 = close.ewm(span=50, adjust=False, min_periods=200).mean()
    ema200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
    result = pd.DataFrame({"ema50": ema50, "ema200": ema200, "htf_close": close})
    result["trend"] = "UNKNOWN"
    ready = ema200.notna()
    result.loc[ready, "trend"] = "NEUTRAL"
    result.loc[ready & (close > ema50) & (ema50 > ema200), "trend"] = "BULLISH"
    result.loc[ready & (close < ema50) & (ema50 < ema200), "trend"] = "BEARISH"
    result.index += pd.Timedelta(hours=4)
    result.index.name = "available_at"
    return result.reset_index()


def higher_timeframe_trend(hourly, as_of):
    df = completed_bars(hourly, 60, as_of)
    if df.empty:
        return "UNKNOWN"
    features = higher_timeframe_features(df)
    features = features[features.available_at <= utc_time(as_of)]
    return str(features.iloc[-1].trend) if len(features) else "UNKNOWN"


def validate_signal(signal):
    try:
        entry, sl, tp1, tp2 = (float(signal[k]) for k in ("entry", "stop_loss", "tp1", "tp2"))
        if not all(math.isfinite(v) and v > 0 for v in (entry, sl, tp1, tp2)):
            return "INVALID_PRICES"
        long = signal["direction"] == "LONG"
        if signal["direction"] not in ("LONG", "SHORT"):
            return "INVALID_DIRECTION"
        if not (sl < entry < tp1 < tp2 if long else tp2 < tp1 < entry < sl):
            return "INVALID_LEVEL_ORDER"
        risk = abs(entry - sl)
        if abs(tp1 - entry) / risk + 1e-9 < config.SFP_MIN_RR_TARGET_1:
            return "TP1_BELOW_MINIMUM"
        if abs(tp2 - entry) / risk + 1e-9 < config.SFP_MIN_RR_TARGET_2:
            return "TP2_BELOW_MINIMUM"
    except (KeyError, TypeError, ValueError):
        return "INVALID_SIGNAL"
    if config.REQUIRE_PRO_TREND_AAA:
        expected = "BULLISH" if long else "BEARISH"
        if signal.get("htf_trend") != expected or not signal.get("grade", "").startswith("AAA"):
            return "HTF_TREND_REQUIRED"
    if str(signal.get("strategy", "")).startswith("SFP"):
        if config.REQUIRE_STRUCTURAL_BREAKER and not signal.get("breaker_confirmed"):
            return "BREAKER_REQUIRED"
        if config.USE_IFVG_ENTRY and not signal.get("ifvg_confirmed"):
            return "IFVG_REQUIRED"
        if config.USE_IFVG_ENTRY and signal.get("entry_source") != "FVG_50_CE":
            return "IFVG_ENTRY_REQUIRED"
    return None


def currency_legs(symbol):
    clean = symbol.replace("/", "").upper()
    currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}
    return {clean[:3], clean[3:]} if len(clean) == 6 and clean[:3] in currencies and clean[3:] in currencies else {clean}


def risk_rejection(closed, active, symbol, risk_multiplier, now=None):
    now = utc_time(now or datetime.now(timezone.utc))
    day = now.astimezone(TRT).date()
    today = sorted((t for t in closed if t.get("close_reason") not in NO_FILL_REASONS
                    and utc_time(t["closed_at"], legacy_local=True) <= now
                    and utc_time(t["closed_at"], legacy_local=True).astimezone(TRT).date() == day),
                   key=lambda t: utc_time(t["closed_at"], legacy_local=True))
    # Use unweighted R conservatively, including legacy trades without a sizing record.
    if sum(float(t.get("net_r", t.get("r_result", 0))) for t in today) <= -config.MAX_DAILY_LOSS_R:
        return "DAILY_LOSS_LIMIT"
    streak = 0
    for t in reversed(today):
        if t.get("close_reason") != "STOP_LOSS":
            break
        streak += 1
    if streak >= config.MAX_CONSECUTIVE_STOPS:
        return "CONSECUTIVE_STOP_LIMIT"
    live = [t for t in active if t.get("status") in {"PENDING_LIMIT", "OPEN", "TP1_HIT", "TRAILING_ACTIVE"}]
    if any(t.get("tracking_gap_at") for t in live):
        return "UNRESOLVED_TRACKING_GAP"
    if not math.isfinite(risk_multiplier) or not 0 < risk_multiplier <= 1:
        return "INVALID_RISK_MULTIPLIER"
    def exposure(t):
        return float(t.get("risk_multiplier", 1.0))
    if sum(exposure(t) for t in live) + risk_multiplier > config.MAX_OPEN_RISK_R:
        return "PORTFOLIO_RISK_LIMIT"
    legs = currency_legs(symbol)
    for leg in legs:
        if sum(exposure(t) for t in live if leg in currency_legs(t["symbol"])) + risk_multiplier > config.MAX_CURRENCY_RISK_R:
            return "CURRENCY_RISK_LIMIT"
    return None
