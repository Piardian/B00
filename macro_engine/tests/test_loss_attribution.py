from calibration.loss_attribution import attribute_losses, classify_loss


def _record(outcome="LOSS", **post):
    return {"symbol": "EURUSD", "timestamp_utc": "2026-09-05T10:00:00Z", "post_trade_macro_attribution": {"trade_actual_outcome": outcome, **post}}


def test_non_loss_is_ignored():
    result = classify_loss(_record("WIN", failure_attribution="NONE"))
    assert result == {"is_loss": False, "category": None, "evidence": None}


def test_explicit_poi_staleness_has_precedence():
    result = classify_loss(_record(failure_attribution="POI_STALENESS_AND_MARKET_FATIGUE", decoupling_detected=True))
    assert result["category"] == "SETUP_STALENESS"
    assert result["evidence"] == "failure_attribution"


def test_explicit_premium_is_entry_quality_failure():
    result = classify_loss(_record(failure_attribution="PREMIUM_OVERBOUGHT_REVERSAL"))
    assert result["category"] == "ENTRY_QUALITY_FAILURE"


def test_whipsaw_flag_is_used_when_no_explicit_attribution():
    result = classify_loss(_record(was_whipsawed=True))
    assert result["category"] == "WHIPSAW"


def test_decoupling_is_used_when_direction_is_correct():
    result = classify_loss(_record(decoupling_detected=True, macro_directional_accuracy=True))
    assert result["category"] == "CROSS_ASSET_DECOUPLING"


def test_wrong_macro_direction_is_classified():
    result = classify_loss(_record(macro_directional_accuracy=False))
    assert result["category"] == "MACRO_DIRECTION_WRONG"


def test_stop_exit_is_last_structured_fallback():
    result = classify_loss(_record(macro_directional_accuracy=True, exit_reason="STOP_LOSS"))
    assert result["category"] == "EXIT_OR_STOP_MANAGEMENT"


def test_unknown_loss_remains_unexplained():
    result = classify_loss(_record(macro_directional_accuracy=True))
    assert result["category"] == "UNEXPLAINED"
    assert result["evidence"] is None


def test_aggregation_and_grouping():
    records = [
        _record("WIN", failure_attribution="NONE", symbol="EURUSD"),
        {"symbol": "EURUSD", "post_trade_macro_attribution": {"trade_actual_outcome": "LOSS", "macro_directional_accuracy": False}},
        {"symbol": "XAUUSD", "post_trade_macro_attribution": {"trade_actual_outcome": "LOSS", "decoupling_detected": True}},
        {"symbol": "XAUUSD", "post_trade_macro_attribution": {"trade_actual_outcome": "LOSS"}},
    ]
    report = attribute_losses(records, group_by=("symbol",))
    assert report["records_seen"] == 4
    assert report["losses"] == 3
    assert report["categories"]["MACRO_DIRECTION_WRONG"]["count"] == 1
    assert report["categories"]["CROSS_ASSET_DECOUPLING"]["count"] == 1
    assert report["categories"]["UNEXPLAINED"]["count"] == 1
    assert report["evidence_coverage_pct"] == 66.67
    assert report["unexplained_pct"] == 33.33
    assert report["production_activation"] is False
    assert report["groups"]["symbol=EURUSD"]["losses"] == 1
    assert report["groups"]["symbol=XAUUSD"]["losses"] == 2


def test_generator_input_is_supported():
    records = (_record(macro_directional_accuracy=False) for _ in range(2))
    report = attribute_losses(records)
    assert report["records_seen"] == 2
    assert report["losses"] == 2
