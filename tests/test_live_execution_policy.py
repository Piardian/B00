from datetime import datetime, timezone
from unittest.mock import Mock

import pandas as pd
import pytest

from sfp_orb_engine import config
from sfp_orb_engine.execution_policy import (
    completed_bars, higher_timeframe_trend, risk_rejection, validate_signal,
)
from sfp_orb_engine.outcome_tracker import OutcomeTracker
from sfp_orb_engine.macro_gate_client import MacroGateClient
from sfp_orb_engine.engine import BegonyaEngine
from sfp_orb_engine.sfp_detector import SFPDetector


def signal(**changes):
    data = dict(symbol="EUR/USD", direction="LONG", strategy="SFP_IFVG_BREAKER",
                grade="AAA", entry=100., stop_loss=99., tp1=101.2, tp2=103.,
                htf_trend="BULLISH", breaker_confirmed=True, ifvg_confirmed=True,
                entry_source="FVG_50_CE", zone_low=99.5, zone_high=100.5,
                datetime="2000-01-03T07:00:00Z")
    data.update(changes)
    return data


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    import sfp_orb_engine.outcome_tracker as module
    monkeypatch.setattr(module, "ACTIVE_TRADES_FILE", tmp_path / "active.json")
    monkeypatch.setattr(module, "CLOSED_LEDGER_FILE", tmp_path / "closed.json")
    obj = OutcomeTracker(notifier=Mock())
    obj._notify_lifecycle = Mock()
    obj.register_trade(signal(), {"risk_multiplier": 0.5, "gate_bias": "LONG_ONLY"})
    obj.active_trades[0]["opened_at"] = "2000-01-03T07:00:10Z"
    return obj


def bar(minute=1, **changes):
    data = dict(datetime=f"2000-01-03T07:{minute:02d}:00Z", open=100.2,
                low=99.8, high=100.4, close=100.3)
    data.update(changes)
    return data


def test_signal_requires_actual_levels_and_confirmations():
    assert validate_signal(signal()) is None
    for changes, reason in [
        ({"htf_trend": "NEUTRAL"}, "HTF_TREND_REQUIRED"),
        ({"breaker_confirmed": False}, "BREAKER_REQUIRED"),
        ({"ifvg_confirmed": False}, "IFVG_REQUIRED"),
        ({"entry_source": "SWEEP_WICK_50_CE"}, "IFVG_ENTRY_REQUIRED"),
        ({"tp2": 101.99, "rr_ratio": 3}, "TP2_BELOW_MINIMUM"),
        ({"tp1": 99}, "INVALID_LEVEL_ORDER"),
        ({"entry": float("nan")}, "INVALID_PRICES"),
    ]:
        assert validate_signal(signal(**changes)) == reason


def test_strict_detector_does_not_fall_back_without_htf():
    df = pd.DataFrame({"close": [1.] * 40})
    assert SFPDetector().detect_sfp(df, "EUR/USD") is None


def test_macro_neutral_missing_and_corrupt_are_vetoed(tmp_path):
    path = tmp_path / "gate.json"
    client = MacroGateClient(path)
    assert not client.evaluate_gate("EUR/USD", "LONG")["allowed"]
    path.write_text("{broken")
    assert not client.evaluate_gate("EUR/USD", "LONG")["allowed"]
    path.write_text('{"execution_bias_gates":{"EURUSD":"NEUTRAL_RANGE"}}')
    assert not client.evaluate_gate("EUR/USD", "LONG")["allowed"]
    import json
    path.write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                               "execution_bias_gates":{"EURUSD":"LONG_ONLY"}}))
    assert client.evaluate_gate("EUR/USD", "LONG")["allowed"]
    assert not client.evaluate_gate("EUR/USD", "SHORT")["allowed"]


def test_only_completed_bars_and_complete_4h_history():
    times = pd.date_range("2000-01-01", periods=805, freq="h", tz="UTC")
    df = pd.DataFrame({"datetime": times, "close": range(1000, 1805)})
    now = times[-1]
    assert len(completed_bars(df, 60, now)) == 804
    assert higher_timeframe_trend(df, times[799]) == "UNKNOWN"
    assert higher_timeframe_trend(df, now) == "BULLISH"
    df.loc[804, "close"] = -1e9  # current / future bucket cannot affect decision
    assert higher_timeframe_trend(df, now) == "BULLISH"


def test_fill_is_not_closed_using_earlier_wicks_and_duplicate_is_ignored(tracker):
    b = bar(high=104.)
    tracker.check_trade_progress("EUR/USD", b)
    assert tracker.active_trades[0]["status"] == "OPEN"
    assert not tracker.closed_trades
    tracker.check_trade_progress("EUR/USD", b)
    assert tracker.active_trades[0]["status"] == "OPEN"
    tracker.check_trade_progress("EUR/USD", bar(2, low=99.5, high=103.1))
    assert tracker.closed_trades[0]["close_reason"] == "TP2_HIT"
    assert tracker.closed_trades[0]["net_r"] == pytest.approx(2.02)
    assert tracker.closed_trades[0]["weighted_net_r"] == pytest.approx(1.01)


def test_slice_through_cannot_erase_a_filled_stop(tracker):
    tracker.check_trade_progress("EUR/USD", bar(open=100.5, high=100.6, low=98.8, close=98.9))
    assert tracker.closed_trades[0]["close_reason"] == "STOP_LOSS"
    assert tracker.closed_trades[0]["net_r"] == pytest.approx(-1.08)
    assert tracker.closed_trades[0]["filled_at"]
    assert tracker.get_performance_stats()["total_trades"] == 1


def test_failed_reaction_exits_filled_position_and_pays_costs(tracker, monkeypatch):
    import sfp_orb_engine.outcome_tracker as module
    monkeypatch.setattr(module, 'evaluate_entry_candle_reaction', lambda *a: False)
    tracker.check_trade_progress("EUR/USD", bar(close=99.8))
    trade = tracker.closed_trades[0]
    assert trade['close_reason'] == 'ENTRY_REACTION_EXIT_FILLED'
    assert trade['gross_r'] == pytest.approx(-.2)
    assert trade['net_r'] == pytest.approx(-.28)
    assert tracker.get_performance_stats()['total_trades'] == 1


def test_stop_wins_over_target_when_ohlc_order_is_unknown(tracker):
    tracker.check_trade_progress("EUR/USD", bar())
    tracker.check_trade_progress("EUR/USD", bar(2, high=104, low=98))
    assert tracker.closed_trades[0]["close_reason"] == "STOP_LOSS"
    assert tracker.closed_trades[0]["ambiguous_exit_bar"]


def test_gap_waits_for_backfill_and_restart_keeps_cursor(tracker):
    tracker.check_trade_progress("EUR/USD", bar(3))
    assert "tracking_gap_at" in tracker.active_trades[0]
    assert "last_processed_bar" not in tracker.active_trades[0]
    for minute in (1, 2, 3):
        tracker.check_trade_progress("EUR/USD", bar(minute, low=100.1, high=100.3))
    assert "tracking_gap_at" not in tracker.active_trades[0]
    restored = OutcomeTracker(notifier=Mock())
    restored.check_trade_progress("EUR/USD", bar(2, high=104, low=98))
    assert restored.active_trades[0]["status"] == "PENDING_LIMIT"


def closed(reason="STOP_LOSS", net=-1.08, when="2000-01-03T07:00:00Z"):
    return dict(close_reason=reason, net_r=net, closed_at=when)


def test_risk_brakes_reset_on_trt_day_and_ignore_unfilled_and_future():
    now = datetime(2000, 1, 3, 12, tzinfo=timezone.utc)
    assert risk_rejection([closed()] * 3, [], "EUR/USD", .5, now) == "DAILY_LOSS_LIMIT"
    assert risk_rejection([closed(net=-.1)] * 3, [], "EUR/USD", .5, now) == "CONSECUTIVE_STOP_LIMIT"
    assert risk_rejection([closed(when="2000-01-03T21:01:00Z")] * 3, [], "EUR/USD", .5, now) is None
    assert risk_rejection([closed()] * 3, [], "EUR/USD", .5, "2000-01-03T21:01:00Z") is None
    assert risk_rejection([closed("ENTRY_REACTION_REJECTED", 0)] * 4, [], "EUR/USD", .5, now) is None


def test_currency_and_portfolio_limits_include_pending_orders():
    active = [dict(symbol="GBP/USD", status="PENDING_LIMIT", risk_multiplier=1)] * 2
    assert risk_rejection([], active, "EUR/USD", .5) == "CURRENCY_RISK_LIMIT"
    assert risk_rejection([], active, "AUD/JPY", 1.01) == "INVALID_RISK_MULTIPLIER"
    active += [dict(symbol="AUD/JPY", status="OPEN", risk_multiplier=1)]
    assert risk_rejection([], active, "EUR/CHF", .1) == "PORTFOLIO_RISK_LIMIT"


def test_pending_order_cancelled_when_daily_brake_activates(tracker):
    tracker.closed_trades = [closed()] * 3
    tracker.check_trade_progress("EUR/USD", bar())
    assert tracker.closed_trades[-1]["close_reason"] == "RISK_LIMIT_CANCELLED"
    assert tracker.closed_trades[-1]["net_r"] == 0


def test_engine_rejects_before_any_notification():
    engine = BegonyaEngine.__new__(BegonyaEngine)
    engine._log_telemetry = Mock()
    engine.notifier = Mock()
    engine._process_candidate(None, signal(htf_trend="NEUTRAL"))
    engine.notifier.send_notification.assert_not_called()
    assert engine._log_telemetry.call_args.args[1]["reason"] == "HTF_TREND_REQUIRED"


def test_news_freeze_does_not_skip_open_trade_tracking():
    engine = BegonyaEngine.__new__(BegonyaEngine)
    engine.outcome_tracker = Mock()
    engine.outcome_tracker.has_active_trade.return_value = True
    engine.outcome_tracker.active_trades = [dict(symbol="EUR/USD", opened_at="2000-01-03T07:00:00Z")]
    engine.news_guard = Mock()
    engine.news_guard.check_freeze.return_value = {"is_frozen": True}
    engine.data_provider = Mock()
    engine.data_provider.fetch_candles.return_value = pd.DataFrame([bar()])
    engine._log_telemetry = Mock()
    engine.scan_symbol("EUR/USD")
    engine.outcome_tracker.check_trade_progress.assert_called_once()


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_confirmed_setup_accepts_real_ifvg_and_rejects_missing_inversion(direction, monkeypatch):
    df = pd.DataFrame(dict(datetime=pd.date_range("2000-01-03", periods=40, freq="15min", tz="UTC"),
                           open=[100.] * 40, close=[100.] * 40, high=[100.5] * 40,
                           low=[99.5] * 40, volume=[100.] * 40))
    df.loc[35, ["open", "close", "high", "low"]] = [100.7, 100.7, 101., 100.5]
    df.loc[37, ["open", "close", "high", "low"]] = [100.1, 100., 100.2, 99.9]
    df.loc[38, ["open", "close", "high", "low"]] = [99.8, 100.1, 100.3, 98.]
    df.loc[39, ["open", "close", "high", "low"]] = [100.4, 101., 101.2, 100.2]
    if direction == "SHORT":
        old_high = df.high.copy()
        df["high"], df["low"] = 200-df.low, 200-old_high
        df["open"], df["close"] = 200-df.open, 200-df.close
    detector = SFPDetector()
    pool = {"price": 99. if direction == "LONG" else 101.,
            "pool_type": "PDL" if direction == "LONG" else "PDH", "pool_label": "previous day"}
    monkeypatch.setattr(detector, "find_pivots_and_pools", lambda frame: {
        "pdl": pool if direction == "LONG" else None,
        "pdh": pool if direction == "SHORT" else None})
    trend = "BULLISH" if direction == "LONG" else "BEARISH"
    result = detector.detect_sfp(df, "EUR/USD", trend)
    assert result is not None
    assert result["direction"] == direction
    assert validate_signal(result) is None
    # Removing the inversion gap prevents fallback to a wick-only setup.
    if direction == "LONG":
        df.loc[35, "low"] = 99.5
    else:
        df.loc[35, "high"] = 100.5
    assert detector.detect_sfp(df, "EUR/USD", trend) is None


def test_short_tracking_and_be_stop_apply_only_on_next_bar(tracker):
    trade = tracker.active_trades[0]
    trade.update(direction="SHORT", entry=100., original_sl=101., current_sl=101.,
                 tp1=99., tp2=97., zone_low=99.5, zone_high=100.5)
    tracker.check_trade_progress("EUR/USD", bar(open=100.2, high=100.3, low=99.8, close=99.9))
    assert trade["status"] == "OPEN"
    tracker.check_trade_progress("EUR/USD", bar(2, open=100, high=100.4, low=98.8, close=99.1))
    assert trade["status"] == "TP1_HIT"
    tracker.check_trade_progress("EUR/USD", bar(3, open=99.1, high=100.1, low=98.9, close=100))
    assert tracker.closed_trades[-1]["close_reason"] == "BREAK_EVEN"
    assert tracker.closed_trades[-1]["net_r"] == pytest.approx(.42)
