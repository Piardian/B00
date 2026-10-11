"""
Unit tests for the 8-Factor Crypto Capital Flow & Sector Rotation Engine
(macro_engine/preprocessing/crypto_rotation.py).
"""
from preprocessing.crypto_rotation import evaluate_crypto_rotation
from ingestion.crypto_rotation_data import CRYPTO_ROTATION_UNIVERSE


def _make_bars(
    base_close: float,
    change_4h_pct: float,
    change_24h_pct: float,
    rvol: float,
    count: int = 35,
) -> list:
    """Builds synthetic 1H or 4H kline bars producing exact 4h/24h changes and RVOL."""
    bars = []
    # Base historical bars with quote_volume = 1000.0
    start_price = base_close / (1.0 + change_24h_pct / 100.0)
    price_4h_ago = base_close / (1.0 + change_4h_pct / 100.0)
    for i in range(count):
        if i == count - 1:
            c = base_close
            qv = 1000.0 * rvol
        elif i == count - 2:
            c = (base_close + price_4h_ago) / 2.0
            qv = 1000.0 * rvol
        elif i == count - 5:
            c = price_4h_ago
            qv = 1000.0
        else:
            c = start_price
            qv = 1000.0
        bars.append({"open": c, "high": c * 1.002, "low": c * 0.998, "close": c, "quote_volume": qv})
    return bars


def _make_oi_hist(change_4h_pct: float, change_24h_pct: float) -> list:
    base_oi = 100_000.0
    oi_4h_ago = base_oi * (1.0 + (change_24h_pct - change_4h_pct) / 100.0)
    oi_now = oi_4h_ago * (1.0 + change_4h_pct / 100.0)
    hist = []
    for i in range(10):
        if i == 0:
            val = base_oi
        elif i == 5:
            val = oi_4h_ago
        elif i == 9:
            val = oi_now
        else:
            val = base_oi
        hist.append({"sum_open_interest": val, "sum_open_interest_value": val * 10.0})
    return hist


def _set_coin(
    snap: dict,
    sym: str,
    chg24: float,
    chg4: float,
    rvol: float,
    oi4: float = 1.0,
    oi24: float = 2.0,
    funding_pct: float = 0.01,
    spot_vol: float = 50_000_000.0,
    fut_vol: float = 100_000_000.0,
) -> None:
    snap["coins"][sym].update({
        "spot_last_price": 100.0,
        "spot_price_change_24h_pct": chg24,
        "spot_quote_volume_24h": spot_vol,
        "futures_quote_volume_24h": fut_vol,
        "funding_rate": funding_pct / 100.0,
        "bars_1h": _make_bars(100.0, chg4, chg24, rvol),
        "bars_4h": _make_bars(100.0, chg4, chg24, rvol),
        "oi_history_1h": _make_oi_hist(oi4, oi24),
        "deep_fetched": True,
    })


def _build_base_snapshot(
    btc_change_24h: float = 2.0,
    eth_change_24h: float = 3.5,
    btcdom_change_4h: float = -0.35,
    btcdom_change_24h: float = -0.80,
) -> dict:
    coins = {}
    for sym, meta in CRYPTO_ROTATION_UNIVERSE.items():
        coins[sym] = {
            **meta,
            "spot_last_price": 10.0,
            "spot_price_change_24h_pct": 1.0,
            "spot_quote_volume_24h": 50_000_000.0,
            "futures_quote_volume_24h": 100_000_000.0,
            "funding_rate": 0.0001,  # +0.01%
            "bars_1h": [],
            "bars_4h": [],
            "oi_history_1h": [],
            "deep_fetched": False,
        }

    snap = {
        "status": "AVAILABLE",
        "btc_dominance": {
            "btc_dominance_pct": 56.4,
            "btcdom_change_24h_pct": btcdom_change_24h,
            "btcdom_change_4h_pct": btcdom_change_4h,
        },
        "coins": coins,
    }
    _set_coin(snap, "BTC", btc_change_24h, btc_change_24h * 0.4, rvol=1.35, oi4=2.0, oi24=4.0)
    _set_coin(snap, "ETH", eth_change_24h, eth_change_24h * 0.45, rvol=1.45, oi4=2.5, oi24=5.0)
    return snap


def test_organic_sector_rotation_approves_sector_diversified_top_3_on_demand_smc_targets():
    """
    When BTC.D is falling (ALT_CAPITAL_DISPERSION), ETH/BTC > 0, and both HIGH_BETA_L1_L2
    and AI_SECTOR have strong RS vs BTC/ETH + organic Spot RVOL + rising OI with normal funding,
    Sector Diversification picks the #1 leader from AI_SECTOR (TAO), the #1 leader from HIGH_BETA_L1_L2 (SOL),
    and fills the 3rd slot with the next highest leader (RENDER) for 3 On-Demand SMC targets.
    """
    snap = _build_base_snapshot(btc_change_24h=2.0, eth_change_24h=3.6)

    # Activate Layer 2 so waterfall reaches higher beta layers
    for l2_sym in ["SOL", "AVAX", "SUI", "NEAR", "APT"]:
        _set_coin(snap, l2_sym, chg24=4.2, chg4=1.8, rvol=1.45, oi4=2.5, oi24=5.0)

    # Activate AI_SECTOR (5 out of 7 coins advancing with strong RVOL & organic OI)
    ai_profiles = {
        "TAO": {"chg24": 8.2, "chg4": 2.4, "rvol": 2.6, "oi4": 4.2, "fund": 0.012},
        "RENDER": {"chg24": 7.4, "chg4": 2.1, "rvol": 2.4, "oi4": 3.8, "fund": 0.010},
        "FET": {"chg24": 5.9, "chg4": 1.8, "rvol": 1.8, "oi4": 3.0, "fund": 0.011},
        "WLD": {"chg24": 5.1, "chg4": 1.6, "rvol": 1.5, "oi4": 2.2, "fund": 0.009},
        "ARKM": {"chg24": 4.6, "chg4": 1.5, "rvol": 1.4, "oi4": 2.0, "fund": 0.008},
    }
    for sym, p in ai_profiles.items():
        _set_coin(snap, sym, chg24=p["chg24"], chg4=p["chg4"], rvol=p["rvol"], oi4=p["oi4"], funding_pct=p["fund"])

    res = evaluate_crypto_rotation(snap, macro_btc_gate="LONG_ONLY")

    assert res["status"] == "AVAILABLE"
    assert res["btc_dominance_panel"]["dominance_regime"] == "ALT_CAPITAL_DISPERSION"
    assert res["coin_assessments"]["TAO"]["rotation_gate"] == "LONG_ONLY"
    assert res["coin_assessments"]["TAO"]["active_rotation_score"] >= 65
    assert res["coin_assessments"]["TAO"]["derivatives_regime"] == "ORGANIC_CAPITAL_INFLOW"
    assert len(res["on_demand_smc_targets"]) == 3
    target_coins = [t["coin"] for t in res["on_demand_smc_targets"]]
    assert target_coins[0] == "TAO"
    assert "SOL" in target_coins
    assert "RENDER" in target_coins


def test_late_short_chase_penalty_and_micro_rs_hold():
    """
    Verifies that:
    1. A coin that already capitulated (-11% 24h with -6.0% 4h OI flush) gets CAPITULATION_OI_FLUSHED
       and late_chase_penalty (-15 pts), ranking below a fresh SHORT_BUILDUP_DISTRIBUTION coin (-4.5% 24h, rising OI).
    2. A coin with 1H micro RS bounce (>= +0.65% vs BTC) gets MICRO_RS_REVERSAL_HOLD vetoed from shorting.
    """
    snap = _build_base_snapshot(btc_change_24h=-1.5, eth_change_24h=-2.5, btcdom_change_4h=0.3, btcdom_change_24h=0.9)
    for sym in ["SOL", "SUI", "AVAX", "NEAR", "APT", "ARB", "OP"]:
        _set_coin(snap, sym, chg24=-4.5, chg4=-1.8, rvol=1.6, oi4=1.5, oi24=3.0, funding_pct=0.005)

    # BCH already capitulated (-11.5% 24h, OI flushed -6.2% in 4h)
    _set_coin(snap, "BCH", chg24=-11.5, chg4=-3.2, rvol=1.7, oi4=-6.2, oi24=-10.0, funding_pct=-0.001)
    for sym in ["XRP", "ADA", "DOT", "LINK", "DASH"]:
        _set_coin(snap, sym, chg24=-3.5, chg4=-1.2, rvol=1.3, oi4=-0.5, oi24=-1.0, funding_pct=0.004)

    res = evaluate_crypto_rotation(snap, macro_btc_gate="SHORT_ONLY")
    arb_eval = res["coin_assessments"]["ARB"]
    bch_eval = res["coin_assessments"]["BCH"]

    assert arb_eval["derivatives_regime"] == "SHORT_BUILDUP_DISTRIBUTION"
    assert bch_eval["derivatives_regime"] == "CAPITULATION_OI_FLUSHED"
    assert bch_eval["score_breakdown"]["late_chase_penalty"] == -15
    assert arb_eval["short_rotation_score"] > bch_eval["short_rotation_score"]



def test_dash_ltc_contra_rs_and_short_squeeze_veto():
    """
    Reproduces the DASH / LTC failure mode:
    Even when Macro is SHORT_ONLY, if LTC or DASH is outperforming BTC (ALT/BTC > 0)
    with strong Spot RVOL and/or negative funding + rising OI, shorting MUST be vetoed.
    """
    snap = _build_base_snapshot(btc_change_24h=-1.2, eth_change_24h=-1.8, btcdom_change_4h=0.2, btcdom_change_24h=0.5)

    # LTC is pumping +4.5% against BTC (-1.2%) -> ALT/BTC 24h = +5.7% with RVOL 2.1x and negative funding
    _set_coin(snap, "LTC", chg24=4.5, chg4=2.2, rvol=2.1, oi4=6.4, oi24=10.0, funding_pct=-0.025)
    # DASH is also outperforming BTC with positive RS
    _set_coin(snap, "DASH", chg24=2.8, chg4=1.4, rvol=1.65, oi4=2.8, oi24=5.0, funding_pct=-0.010)

    res = evaluate_crypto_rotation(snap, macro_btc_gate="SHORT_ONLY")

    ltc_eval = res["coin_assessments"]["LTC"]
    dash_eval = res["coin_assessments"]["DASH"]

    assert ltc_eval["rotation_gate"] == "NEUTRAL_RANGE"
    assert ltc_eval["smc_handoff_allowed"] is False
    assert any("RS_CONTRA_SHORT_VETO" in r or "SHORT_SQUEEZE_DANGER" in r for r in ltc_eval["veto_reasons_short"])
    assert ltc_eval["derivatives_regime"] == "SHORT_SQUEEZE_DANGER"

    assert dash_eval["rotation_gate"] == "NEUTRAL_RANGE"
    assert dash_eval["smc_handoff_allowed"] is False
    assert any("RS_CONTRA_SHORT_VETO" in r or "SHORT_SQUEEZE_DANGER" in r for r in dash_eval["veto_reasons_short"])

    target_coins = [t["coin"] for t in res["on_demand_smc_targets"]]
    assert "LTC" not in target_coins
    assert "DASH" not in target_coins


def test_leverage_squeeze_trap_vetoes_long():
    """
    Price ↑↑ (+9.5%), Spot RVOL weak (0.90x), OI ↑↑ (+9.0% 4h / +15% 24h), Funding extreme positive (+0.045%)
    -> LEVERAGE_SQUEEZE_TRAP vetoes LONG_ONLY even if Macro is LONG_ONLY.
    """
    snap = _build_base_snapshot(btc_change_24h=1.5, eth_change_24h=2.5)
    for sym in ["SOL", "AVAX", "NEAR", "APT", "SEI", "ARB"]:
        _set_coin(snap, sym, chg24=4.5, chg4=1.6, rvol=1.5, oi4=2.0, oi24=4.0)

    # SUI has a leverage squeeze trap: huge price + OI + funding, but dry spot volume
    _set_coin(
        snap,
        "SUI",
        chg24=9.5,
        chg4=4.8,
        rvol=0.90,
        oi4=9.0,
        oi24=15.0,
        funding_pct=0.045,
        spot_vol=8_000_000.0,
        fut_vol=120_000_000.0,
    )

    res = evaluate_crypto_rotation(snap, macro_btc_gate="LONG_ONLY")
    sui_eval = res["coin_assessments"]["SUI"]

    assert sui_eval["derivatives_regime"] == "LEVERAGE_SQUEEZE_TRAP"
    assert sui_eval["rotation_gate"] == "NEUTRAL_RANGE"
    assert any("LEVERAGE_SQUEEZE_TRAP" in r for r in sui_eval["veto_reasons_long"])
    target_coins = [t["coin"] for t in res["on_demand_smc_targets"]]
    assert "SUI" not in target_coins


def test_single_coin_outlier_without_sector_breadth_is_blocked():
    """
    Rule 7: Tek Coin != Rotasyon.
    If CHZ pumps +8% with volume, but the rest of DEFI_GAMING_MIDCAP is flat/underperforming BTC,
    CHZ is flagged as is_single_coin_outlier / NO_SECTOR_BREADTH and does not pass.
    """
    snap = _build_base_snapshot(btc_change_24h=1.5, eth_change_24h=2.2)
    _set_coin(snap, "CHZ", chg24=8.0, chg4=3.0, rvol=2.4, oi4=4.0, oi24=7.0, funding_pct=0.01)

    res = evaluate_crypto_rotation(snap, macro_btc_gate="LONG_ONLY")
    chz_eval = res["coin_assessments"]["CHZ"]

    assert chz_eval["is_single_coin_outlier"] is True
    assert chz_eval["rotation_gate"] == "NEUTRAL_RANGE"
    assert any("NO_SECTOR_BREADTH" in r for r in chz_eval["veto_reasons_long"])
    target_coins = [t["coin"] for t in res["on_demand_smc_targets"]]
    assert "CHZ" not in target_coins


def test_meme_late_cycle_froth_warning_blocks_layer_6_when_majors_stall():
    """
    When MEME_SECTOR is surging with high funding while ETH/BTC < 0 and HIGH_BETA_L1_L2
    is underperforming BTC, meme_froth_warning triggers and vetoes new Layer 6 Meme longs.
    """
    snap = _build_base_snapshot(btc_change_24h=1.5, eth_change_24h=0.5)
    # HIGH_BETA_L1_L2 is stalling (all underperforming BTC +1.5%)
    for sym in ["SOL", "SUI", "AVAX", "NEAR", "APT", "SEI", "ARB", "OP"]:
        _set_coin(snap, sym, chg24=0.2, chg4=-0.1, rvol=0.9)

    # MEME_SECTOR is overheating across all 7 meme coins with high positive funding
    for sym in ["DOGE", "PEPE", "SHIB", "WIF", "BONK", "FLOKI", "PENGU"]:
        _set_coin(snap, sym, chg24=10.5, chg4=4.2, rvol=2.5, oi4=5.0, oi24=10.0, funding_pct=0.040)

    res = evaluate_crypto_rotation(snap, macro_btc_gate="LONG_ONLY")

    assert res["meme_froth_warning"] is True
    pepe_eval = res["coin_assessments"]["PEPE"]
    assert pepe_eval["rotation_gate"] == "NEUTRAL_RANGE"
    assert any("MEME_LATE_CYCLE_FROTH_VETO" in r for r in pepe_eval["veto_reasons_long"])


def test_morning_briefing_renders_short_only_altcoin_rotation():
    """
    Ensure format_morning_briefing renders SHORT_ONLY altcoin rotation direction,
    weakest sector breadth, On-Demand SMC short targets, and Eylem Planı item.
    """
    from gateways.telegram_notifier import format_morning_briefing

    snap = _build_base_snapshot(btc_change_24h=-2.0, eth_change_24h=-3.5)
    snap["btcdom_change_24h_pct"] = 1.15
    for sym in ["ARB", "BCH", "SOL"]:
        _set_coin(snap, sym, chg24=-7.5, chg4=-2.8, rvol=1.65, oi4=-2.5, oi24=-5.0, funding_pct=0.008)
    _set_coin(snap, "LTC", chg24=3.2, chg4=1.5, rvol=1.80, oi4=3.0, oi24=6.0, funding_pct=-0.015)

    rot = evaluate_crypto_rotation(snap, macro_btc_gate="SHORT_ONLY")
    pipeline_result = {
        "regime_state": {"cycle_regime": "STAGFLATION_RISK", "crypto_rotation": rot},
        "deterministic_execution_gates": {
            "execution_bias_gates": {
                "XAUUSD": "NEUTRAL_RANGE",
                "BTC": "SHORT_ONLY",
                "EURUSD": "NEUTRAL_RANGE",
                "SPX_NAS100": "NEUTRAL_RANGE",
            },
            "crypto_rotation_analysis": rot,
        },
        "processed_metrics": {
            "crypto_rotation_analysis": rot,
            "crypto_rotation": rot,
        },
        "final_output": {"macro_rationale": "Test rationale"},
    }
    msg = format_morning_briefing(pipeline_result, upcoming_events=[])
    assert "KRİPTO SERMAYE AKIŞI & 8-FAKTÖR ALTCOIN ROTASYONU" in msg
    assert "SHORT_ONLY (Göreli Zayıflık & Sermaye Çıkışı Rotasyonu)" in msg
    assert "En Zayıf Sektör (Short Genişliği)" in msg
    assert "On-Demand SMC Hedefleri (≥65 Puan)" in msg
    assert "Altcoin Rotasyonu (SHORT_ONLY):" in msg
    assert "Short-Squeeze Kalkanı" in msg

