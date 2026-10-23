import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from scripts import replay_live_system as replay
from sfp_orb_engine.execution_policy import completed_bars


def test_out_of_requested_dates_is_not_counted_as_history():
    start, end = replay.bounds("2025-01")
    df = pd.DataFrame({"datetime": [pd.Timestamp("2026-07-16T16:16Z")]})
    result = replay.frame_summary(df, start, end)
    assert result["returned_rows"] == 1
    assert result["in_range_rows"] == 0
    assert result["out_of_range_rows"] == 1


def test_missing_macro_cannot_be_reported_as_zero_trade_success(tmp_path):
    result = replay.audit_month("2025-01", ["EUR/USD"], tmp_path, [])
    assert result["status"] == "BLOCKED_MISSING_INPUTS"
    assert result["metrics"] is None
    assert "NO_POINT_IN_TIME_MACRO_GATE_AT_START" in result["blockers"]


def test_provider_cannot_expose_future_completed_candles():
    clock = replay.Clock("2000-01-03T07:01Z")
    df = pd.DataFrame({"datetime": pd.date_range("2000-01-03T07:00Z", periods=3, freq="min"),
                       "close": [100., 200., 300.]})
    provider = replay.HistoricalProvider({("EUR/USD", "1m"): df}, clock)
    visible = provider.fetch_candles("EUR/USD", "1m", 1000)
    assert len(visible) == 2
    assert completed_bars(visible, 1, clock.current).close.tolist() == [100.]


@pytest.mark.parametrize('minimize_memory', [False, True])
@pytest.mark.parametrize('use_candidate_index', [False, True])
@pytest.mark.parametrize('cost_multiplier', [1., 1.5, 2.])
def test_replay_uses_live_ledger_and_never_changes_production_files(tmp_path, monkeypatch, minimize_memory, use_candidate_index, cost_multiplier):
    # Synthetic data is strictly a harness unit test, not a historical return.
    from sfp_orb_engine import engine as engine_module
    from sfp_orb_engine import outcome_tracker as tracker_module
    from sfp_orb_engine.sfp_detector import SFPDetector
    start = pd.Timestamp("2000-01-03T07:00:00Z")
    end = start + pd.Timedelta(minutes=4)
    data = tmp_path / "data"
    data.mkdir()
    for tf, freq, count in [("1m", "min", 1004), ("15m", "15min", 304), ("1h", "h", 1004)]:
        times = pd.date_range(end=start + pd.Timedelta(minutes=3), periods=count, freq=freq)
        df = pd.DataFrame(dict(datetime=times, open=100.2, low=99.8, high=100.4, close=100.3, volume=100.))
        if tf == "1m":
            df.loc[df.datetime == start + pd.Timedelta(minutes=1), "high"] = 103.1
        df.to_csv(data / f"EURUSD_{tf}.csv", index=False)
    candidate = dict(symbol="EUR/USD", direction="LONG", strategy="SFP_IFVG_BREAKER", grade="AAA",
                     datetime=start-pd.Timedelta(minutes=15), entry=100., stop_loss=99., tp1=101.2, tp2=103.,
                     risk_pips=1., htf_trend="BULLISH", breaker_confirmed=True, ifvg_confirmed=True,
                     entry_source="FVG_50_CE", zone_low=99.5, zone_high=100.5)
    gates = [{"available_at": start.to_pydatetime(), "provenance": "UNIT_TEST_ONLY",
              "gate": {"timestamp": start.isoformat(), "execution_bias_gates": {"EURUSD": "LONG_ONLY"}, "recommended_risk_multiplier": .5}}]
    ledger_path = tracker_module.CLOSED_LEDGER_FILE
    before = ledger_path.read_bytes() if ledger_path.exists() else None
    monkeypatch.setattr(replay, "bounds", lambda month: (start, end))
    monkeypatch.setattr(engine_module, "higher_timeframe_trend", lambda *a: "BULLISH")
    monkeypatch.setattr(SFPDetector, "detect_sfp", lambda *a, **kw: candidate.copy())
    candidate_index = {('EUR/USD', start.floor('15min'))} if use_candidate_index else None
    result = replay.replay_month("unit-test", ["EUR/USD"], data, gates, tmp_path / "run", minimize_memory=minimize_memory, candidate_index=candidate_index, friction_multiplier=cost_multiplier)
    assert result["closed_filled_trades"] == 1
    assert result["net_r"] == pytest.approx(2.1 - .08*cost_multiplier)
    assert result["weighted_net_r"] == pytest.approx((2.1 - .08*cost_multiplier)*.5)
    assert result['friction_assumptions']['broker_costs_verified'] is False
    assert tracker_module.CLOSED_LEDGER_FILE == ledger_path
    assert (ledger_path.read_bytes() if ledger_path.exists() else None) == before
    saved = json.loads((tmp_path / "run/state/closed.json").read_text())
    assert saved[0]["close_reason"] == "TP2_HIT"
