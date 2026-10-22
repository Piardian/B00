from datetime import datetime, timezone
import json
import sqlite3
from unittest.mock import Mock

import pandas as pd
import pytest

from sfp_orb_engine.execution_observer import ExecutionObserver
from sfp_orb_engine.engine import BegonyaEngine
from scripts.analyze_execution_quality import measure_trade, build_report


def frame():
    return pd.DataFrame(dict(datetime=pd.date_range("2000-01-03T07:00Z", periods=3, freq="min"),
                             open=100., high=100.5, low=99.5, close=100.1, volume=10.))


def test_archive_deduplicates_and_preserves_revisions_without_forming_bars(tmp_path):
    path = tmp_path / "observation.db"
    observer = ExecutionObserver(path)
    data = frame()
    observer.archive_bars("EUR/USD", "1m", data, "2000-01-03T07:02:00Z")
    observer.archive_bars("EUR/USD", "1m", data, "2000-01-03T07:02:00Z")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM bars").fetchone()[0] == 2
    data.loc[0, "high"] = 101.
    observer.archive_bars("EUR/USD", "1m", data, "2000-01-03T07:02:00Z")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM bars").fetchone()[0] == 3


def test_macro_availability_is_observation_time_not_payload_time(tmp_path):
    observer = ExecutionObserver(tmp_path / "observation.db")
    gate = tmp_path / "macro.json"
    gate.write_text(json.dumps({"timestamp": "2025-01-01", "execution_bias_gates": {}}))
    observer.archive_macro(gate, "2026-10-22T14:00:00Z")
    observer.archive_macro(gate, "2026-10-22T14:01:00Z")
    with sqlite3.connect(observer.path) as db:
        rows = db.execute("SELECT available_at FROM macro_snapshots").fetchall()
    assert rows == [("2026-10-22T14:00:00Z",)]


def test_macro_return_to_previous_state_keeps_transition(tmp_path):
    observer = ExecutionObserver(tmp_path / "observation.db")
    gate = tmp_path / "macro.json"
    for minute, bias in [(0, "LONG_ONLY"), (1, "SHORT_ONLY"), (2, "LONG_ONLY")]:
        gate.write_text(json.dumps({"bias": bias}))
        observer.archive_macro(gate, f"2026-10-22T14:0{minute}:00Z")
    with sqlite3.connect(observer.path) as db:
        payloads = db.execute("SELECT payload FROM macro_snapshots ORDER BY available_at").fetchall()
    assert [json.loads(row[0])["bias"] for row in payloads] == ["LONG_ONLY", "SHORT_ONLY", "LONG_ONLY"]


def test_observation_failure_does_not_reject_an_entry():
    engine = BegonyaEngine.__new__(BegonyaEngine)
    engine.diagnostics = Mock()
    engine.diagnostics.archive_bars.side_effect = OSError("database locked")
    assert engine._observe("archive_bars", "EUR/USD", "1m", frame()) is None


def sample_trade():
    return dict(id="test", symbol="EUR/USD", direction="LONG", entry=100., original_sl=99.,
                tp1=101., tp2=103., filled_at="2000-01-03T06:00:00Z", closed_at="2000-01-03T07:00:00Z",
                close_reason="TRAILING_STOP", net_r=.795, policy_version="confirmed-v2")


def test_missing_history_leaves_outcome_unknown(tmp_path):
    result = measure_trade(sample_trade(), tmp_path / "missing.db", datetime(2000, 1, 3, 12, tzinfo=timezone.utc))
    assert result["mfe_r"] is None
    assert result["post_exit_status"] == "INCOMPLETE_HISTORY"
    assert result["tp2_within_4h"] is None
    assert result["actual_bid_ask_cost_r"] is None


def test_complete_post_exit_marks_same_bar_ambiguity_without_invented_profit(tmp_path):
    observer = ExecutionObserver(tmp_path / "observation.db")
    data = pd.DataFrame(dict(datetime=pd.date_range("2000-01-03T07:00Z", periods=240, freq="min"),
                             open=100., high=100.5, low=99.5, close=100.1, volume=10.))
    data.loc[0, ["high", "low"]] = [103.1, 98.9]
    observer.archive_bars("EUR/USD", "1m", data, "2000-01-03T12:00:00Z")
    result = measure_trade(sample_trade(), observer.path, datetime(2000, 1, 3, 12, tzinfo=timezone.utc))
    assert result["post_exit_status"] == "COMPLETE"
    assert result["tp2_within_4h"] is True
    assert result["same_bar_order_ambiguous"] is True
    assert result["original_sl_before_tp2"] is True
    assert "counterfactual_net_r" not in result


def test_legacy_partial_minute_boundaries_cannot_establish_exact_excursion(tmp_path):
    trade = sample_trade()
    trade["filled_at"] = "2000-01-03T06:00:10Z"
    observer = ExecutionObserver(tmp_path / "observation.db")
    result = measure_trade(trade, observer.path, datetime(2000, 1, 3, 12, tzinfo=timezone.utc))
    assert result["excursion_status"] == "INSUFFICIENT_OR_AMBIGUOUS_HISTORY"


def test_observer_keeps_recent_closed_symbols_under_observation(tmp_path):
    observer = ExecutionObserver(tmp_path / "observation.db")
    trade = sample_trade()
    trade["closed_at"] = datetime.now(timezone.utc).isoformat()
    observer.archive_trades([trade])
    assert observer.needs_capture("EUR/USD")
    assert not observer.needs_capture("GBP/USD")


def test_cost_is_model_buffer_not_a_claim_of_real_broker_cost(tmp_path):
    report = build_report([sample_trade()], tmp_path / "none.db",
                          datetime(2000, 1, 3, tzinfo=timezone.utc), datetime(2000, 1, 4, tzinfo=timezone.utc))
    assert report["trades"] == 1
    assert report["modeled_spread_buffer_r_median"] == pytest.approx(.02)
    assert report["actual_cost_observations"] == 0


def test_yahoo_futures_proxy_cannot_establish_original_gold_target_hits(tmp_path):
    observer = ExecutionObserver(tmp_path / "observation.db")
    observer.archive_bars("XAU/USD", "1m", frame(), "2000-01-03T12:00Z", source="historical_yahoo_1m; retrospective_download")
    trade = sample_trade()
    trade["symbol"] = "XAU/USD"
    result = measure_trade(trade, observer.path, datetime(2000, 1, 3, 12, tzinfo=timezone.utc))
    assert result["post_exit_status"] == "REJECTED_INSTRUMENT_PROXY"
    assert result["mfe_r"] is None


def test_price_scale_mismatch_is_not_reported_as_huge_mfe(tmp_path):
    observer = ExecutionObserver(tmp_path / "observation.db")
    data = frame()
    data.datetime = data.datetime - pd.Timedelta(hours=1)
    data[["open", "high", "low", "close"]] *= 40
    observer.archive_bars("EUR/USD", "1m", data, "2000-01-03T12:00Z")
    result = measure_trade(sample_trade(), observer.path, datetime(2000, 1, 3, 12, tzinfo=timezone.utc))
    assert result["price_series_status"] == "REJECTED_PRICE_SCALE_MISMATCH"
    assert result["mfe_r"] is None


def test_nas100_fallback_matches_shared_qqq_registry(monkeypatch):
    from sfp_orb_engine import data_provider
    requested = []
    hist = pd.DataFrame(dict(Open=700., High=701., Low=699., Close=700.5, Volume=1000.),
                        index=pd.date_range("2026-10-20T12:00Z", periods=30, freq="min", name="Datetime"))
    def ticker(name):
        requested.append(name)
        return Mock(history=Mock(return_value=hist))
    monkeypatch.setattr(data_provider.yf, "Ticker", ticker)
    bars = data_provider.MarketDataProvider()._fetch_yfinance("NAS100", "1m", 50)
    assert requested == ["QQQ"]
    assert bars.close.iloc[-1] == 700.5
