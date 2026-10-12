"""
Begonya 00 - Entry Mechanics Unit Tests
Test Model A (%50 CE Consequent Encroachment), Dynamic Stop Buffer,
Slice-Through Detection, and Limit State Machine.
"""

import pytest
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sfp_orb_engine.entry_mechanics import (
    calculate_ce_entry,
    is_slice_through_candle,
    evaluate_entry_candle_reaction,
    LimitExecutionSimulator,
)


def test_calculate_ce_entry_short_fvg():
    """Short SFP with FVG: entry should be midpoint (50% CE) of the FVG."""
    res = calculate_ce_entry(
        direction="SHORT",
        peak_or_valley=1.1050,
        trigger_price=1.1000,
        close_price=1.0980,
        fvg_range=(1.1030, 1.1010),  # top=1.1030, bottom=1.1010 -> CE=1.1020
        atr=0.0020,
        sl_buffer_atr=0.15,
        entry_model="midpoint",
        tp1_r=1.0,
        tp2_r=3.0,
    )
    assert res["entry_price"] == 1.1020
    assert res["stop_loss"] > 1.1050  # SL above peak
    assert res["is_limit"] is True
    assert res["entry_source"] == "FVG_50_CE"
    assert res["risk_distance"] == pytest.approx(res["stop_loss"] - res["entry_price"], rel=1e-4)
    assert res["tp2"] < res["entry_price"]


def test_calculate_ce_entry_long_sweep_wick():
    """Long SFP without FVG: entry should be midpoint of sweep valley and trigger."""
    res = calculate_ce_entry(
        direction="LONG",
        peak_or_valley=1.0500,  # Valley low
        trigger_price=1.0540,   # Swept low level
        close_price=1.0550,     # Candle closed at 1.0550
        fvg_range=None,
        atr=0.0020,
        sl_buffer_atr=0.15,
        entry_model="midpoint",
        tp1_r=1.0,
        tp2_r=3.0,
    )
    # Midpoint between valley (1.0500) and max(1.0540, 1.0550) = (1.0500 + 1.0550)/2 = 1.0525
    assert res["entry_price"] == 1.0525
    assert res["stop_loss"] < 1.0500  # SL below valley
    assert res["is_limit"] is True
    assert res["entry_source"] == "SWEEP_WICK_50_CE"
    assert res["risk_distance"] == pytest.approx(res["entry_price"] - res["stop_loss"], rel=1e-4)
    assert res["tp2"] > res["entry_price"]


def test_calculate_ce_entry_close_model():
    """Close model (backward compatibility): entry at market close."""
    res = calculate_ce_entry(
        direction="LONG",
        peak_or_valley=1.0500,
        trigger_price=1.0540,
        close_price=1.0550,
        entry_model="close",
    )
    assert res["entry_price"] == 1.0550
    assert res["is_limit"] is False
    assert res["entry_source"] == "MARKET_CLOSE"


def test_slice_through_candle_detection():
    """Should detect aggressive slice through candles without rejection wicks."""
    # Bearish candle slicing downward through a LONG zone [1.0520, 1.0540]
    sliced = is_slice_through_candle(
        direction="LONG",
        open_p=1.0560,
        high_p=1.0562,
        low_p=1.0500,
        close_p=1.0505,  # Closes well below zone_low (1.0520) with 90% bearish body
        zone_low=1.0520,
        zone_high=1.0540,
    )
    assert sliced is True

    # Clean rejection hammer (bouncing off zone)
    bounced = is_slice_through_candle(
        direction="LONG",
        open_p=1.0535,
        high_p=1.0545,
        low_p=1.0515,  # Touches zone
        close_p=1.0540,  # Closes bullish
        zone_low=1.0520,
        zone_high=1.0540,
    )
    assert bounced is False


def test_limit_execution_simulator_journey():
    """Test full lifecycle of limit execution: Pending -> Retest Fill -> TP1 BE -> TP2."""
    sim = LimitExecutionSimulator(
        order_id="EURUSD_TEST_1",
        symbol="EURUSD",
        direction="LONG",
        entry_price=1.0525,
        stop_loss=1.0495,  # Risk = 30 pips
        tp1=1.0555,        # 1.0R
        tp2=1.0615,        # 3.0R
        zone_low=1.0500,
        zone_high=1.0540,
        is_limit=True,
        expiry_bars=10,
    )

    assert sim.status == "PENDING"

    # Bar 1: Price still above entry (no fill yet)
    st = sim.process_bar(open_p=1.0550, high_p=1.0560, low_p=1.0530, close_p=1.0545, bar_time="T1")
    assert st == "PENDING"

    # Bar 2: Price dips into 1.0525 -> Clean limit fill!
    st = sim.process_bar(open_p=1.0540, high_p=1.0545, low_p=1.0520, close_p=1.0535, bar_time="T2")
    assert st == "OPEN"
    assert sim.current_sl == 1.0495

    # Bar 3: Price rallies to hit TP1 (1.0555) -> BE armed!
    st = sim.process_bar(open_p=1.0535, high_p=1.0560, low_p=1.0530, close_p=1.0558, bar_time="T3")
    assert st == "TP1_HIT"
    assert sim.current_sl == 1.0525  # SL moved to entry price (BE)!

    # Bar 4: Price surges to TP2 (1.0615) -> TP2 Hit!
    st = sim.process_bar(open_p=1.0558, high_p=1.0620, low_p=1.0550, close_p=1.0618, bar_time="T4")
    assert st == "CLOSED"
    assert sim.closed_reason == "TP2_HIT"
    assert sim.r_result == 2.0


def test_limit_execution_simulator_slice_through_cancel():
    """Test slice-through cancellation before toxic fill."""
    sim = LimitExecutionSimulator(
        order_id="EURUSD_TEST_2",
        symbol="EURUSD",
        direction="LONG",
        entry_price=1.0525,
        stop_loss=1.0495,
        tp1=1.0555,
        tp2=1.0615,
        zone_low=1.0520,
        zone_high=1.0540,
        is_limit=True,
    )

    # Next bar violently crashes through zone without wick
    st = sim.process_bar(
        open_p=1.0560,
        high_p=1.0562,
        low_p=1.0480,
        close_p=1.0485,
        bar_time="T1"
    )
    assert st == "CLOSED"
    assert sim.closed_reason == "CANCELLED_SLICE_THROUGH"
    assert sim.r_result == 0.0  # Zero loss! Saved by slice-through guard!
