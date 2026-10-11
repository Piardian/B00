"""
8 Faktörlü Deterministik Kripto Sermaye Akışı, 7 Katmanlı Risk Şelalesi (Meme Coinler Dahil)
ve On-Demand Seçici SMC Hedef Belirleme Motoru.

 "Önce şu coin yükseldi, sırada bu var" tahminciliği yerine:
 1. Relative Strength (ALT/BTC & ALT/ETH)
 2. Volume Expansion & Stealth Absorption (1H / 4H Spot RVOL)
 3. Market-Cap Risk Layer Waterfall (Layer 0 BTC -> Layer 1 ETH -> Layer 2 L1/L2 -> Layer 3 Legacy -> Layer 4 AI -> Layer 5 DeFi/Gaming -> Layer 6 Meme)
 4. BTC Dominance (BTC.D)
 5. ETH/BTC & Çapraz Öncüler (SOL/ETH, SUI/SOL)
 6. Open Interest + Funding Rate (Sağlıklı Giriş vs. Kaldıraç/Short Squeeze Ayrımı)
 7. Sector Breadth (Tek Coin Hareketi != Sektör Rotasyonu; 39 Coin Üzerinden Ölçüm)
 8. Birleşik ROTATION_SCORE (0-100) ve On-Demand SMC Hedef Listesi (Max 2 Hedef Coin)
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Mapping, Optional

ROTATION_SCORE_THRESHOLD = 65
MAX_ON_DEMAND_SMC_TARGETS = 3


def _pct_change(curr: Optional[float], prev: Optional[float]) -> float:
    if curr is None or prev is None or prev == 0:
        return 0.0
    return round(((curr - prev) / prev) * 100.0, 2)


def _compute_bar_metrics(
    bars_1h: List[Dict[str, float]],
    bars_4h: List[Dict[str, float]],
    fallback_price: float = 0.0,
    fallback_change_24h_pct: float = 0.0,
) -> Dict[str, float]:
    """1H ve 4H spot mumlarından fiyat değişimi ve RVOL hesaplar; yalnızca bulk veri varsa 24s veriyi kullanır."""
    if not bars_1h and not bars_4h:
        return {
            "close": fallback_price,
            "change_1h_pct": round(fallback_change_24h_pct / 12.0, 2),
            "change_4h_pct": round(fallback_change_24h_pct / 4.0, 2),
            "change_24h_pct": round(fallback_change_24h_pct, 2),
            "change_5d_pct": round(fallback_change_24h_pct * 1.5, 2),
            "rvol_1h": 1.0,
            "rvol_4h": 1.0,
            "effective_rvol": 1.0,
        }

    close_now = bars_1h[-1]["close"] if bars_1h else (bars_4h[-1]["close"] if bars_4h else fallback_price)
    close_1h_ago = bars_1h[-2]["close"] if len(bars_1h) >= 2 else close_now
    close_4h_ago = (
        bars_1h[-5]["close"]
        if len(bars_1h) >= 5
        else (bars_4h[-2]["close"] if len(bars_4h) >= 2 else close_now)
    )
    close_24h_ago = (
        bars_1h[-25]["close"]
        if len(bars_1h) >= 25
        else (bars_4h[-7]["close"] if len(bars_4h) >= 7 else close_now)
    )
    close_5d_ago = (
        bars_4h[-31]["close"]
        if len(bars_4h) >= 31
        else (bars_4h[0]["close"] if bars_4h else close_now)
    )

    rvol_1h = 1.0
    if len(bars_1h) >= 6:
        baseline_1h = [b["quote_volume"] for b in bars_1h[:-2][-20:] if b.get("quote_volume", 0) > 0]
        avg_1h = (sum(baseline_1h) / len(baseline_1h)) if baseline_1h else 0.0
        curr_1h_vol = max(bars_1h[-1].get("quote_volume", 0.0), bars_1h[-2].get("quote_volume", 0.0))
        if avg_1h > 0:
            rvol_1h = round(curr_1h_vol / avg_1h, 2)

    rvol_4h = 1.0
    if len(bars_4h) >= 6:
        baseline_4h = [b["quote_volume"] for b in bars_4h[:-2][-20:] if b.get("quote_volume", 0) > 0]
        avg_4h = (sum(baseline_4h) / len(baseline_4h)) if baseline_4h else 0.0
        curr_4h_vol = max(bars_4h[-1].get("quote_volume", 0.0), bars_4h[-2].get("quote_volume", 0.0))
        if avg_4h > 0:
            rvol_4h = round(curr_4h_vol / avg_4h, 2)

    calc_24h = _pct_change(close_now, close_24h_ago)
    if calc_24h == 0.0 and fallback_change_24h_pct != 0.0:
        calc_24h = round(fallback_change_24h_pct, 2)

    return {
        "close": close_now,
        "change_1h_pct": _pct_change(close_now, close_1h_ago),
        "change_4h_pct": _pct_change(close_now, close_4h_ago),
        "change_24h_pct": calc_24h,
        "change_5d_pct": _pct_change(close_now, close_5d_ago),
        "rvol_1h": rvol_1h,
        "rvol_4h": rvol_4h,
        "effective_rvol": round(max(rvol_1h, rvol_4h), 2),
    }


def _compute_oi_metrics(oi_hist_1h: List[Dict[str, float]]) -> Dict[str, float]:
    if not oi_hist_1h:
        return {"oi_value_usd": 0.0, "oi_change_4h_pct": 0.0, "oi_change_24h_pct": 0.0}
    curr_oi = oi_hist_1h[-1].get("sum_open_interest", 0.0)
    curr_val = oi_hist_1h[-1].get("sum_open_interest_value", 0.0)
    oi_4h_ago = (
        oi_hist_1h[-5].get("sum_open_interest", curr_oi)
        if len(oi_hist_1h) >= 5
        else oi_hist_1h[0].get("sum_open_interest", curr_oi)
    )
    oi_24h_ago = oi_hist_1h[0].get("sum_open_interest", curr_oi)
    return {
        "oi_value_usd": round(curr_val, 2),
        "oi_change_4h_pct": _pct_change(curr_oi, oi_4h_ago),
        "oi_change_24h_pct": _pct_change(curr_oi, oi_24h_ago),
    }


def _check_ratio_4h_structure(alt_bars_4h: List[Dict[str, float]], btc_bars_4h: List[Dict[str, float]]) -> Dict[str, bool]:
    """ALT/BTC 4H sentetik rasyosunun son swing yapısını kontrol eder."""
    n = min(len(alt_bars_4h), len(btc_bars_4h))
    if n < 8:
        return {"bullish": False, "bearish": False, "swing_low_broken": False, "swing_high_broken": False}

    ratios: List[float] = []
    for i in range(-n, 0):
        b_close = btc_bars_4h[i].get("close", 0.0)
        a_close = alt_bars_4h[i].get("close", 0.0)
        if b_close > 0:
            ratios.append(a_close / b_close)

    if len(ratios) < 8:
        return {"bullish": False, "bearish": False, "swing_low_broken": False, "swing_high_broken": False}

    curr_ratio = ratios[-1]
    prior_window = ratios[-7:-1]
    recent_low = min(prior_window)
    recent_high = max(prior_window)
    sma_short = sum(ratios[-4:]) / 4.0
    sma_long = sum(ratios[-8:]) / 8.0

    swing_low_broken = curr_ratio < recent_low * 0.997
    swing_high_broken = curr_ratio > recent_high * 1.003

    return {
        "bullish": (sma_short >= sma_long or swing_high_broken) and not swing_low_broken,
        "bearish": (sma_short <= sma_long or swing_low_broken) and not swing_high_broken,
        "swing_low_broken": swing_low_broken,
        "swing_high_broken": swing_high_broken,
    }


def evaluate_crypto_rotation(
    raw_snapshot: Mapping[str, Any],
    macro_btc_gate: str = "NEUTRAL_RANGE",
    btc_decoupling_active: bool = False,
    capital_preservation_mode: bool = False,
    max_on_demand_targets: int = MAX_ON_DEMAND_SMC_TARGETS,
) -> Dict[str, Any]:
    """
    8 Faktörlü Kripto Sermaye Akışı, 7 Katmanlı Risk Şelalesi (Meme Coinler Dahil)
    ve On-Demand SMC Hedef Motoru.
    """
    coins_raw = raw_snapshot.get("coins", {}) if isinstance(raw_snapshot, Mapping) else {}
    if not coins_raw or "BTC" not in coins_raw or "ETH" not in coins_raw:
        return {
            "status": "UNAVAILABLE",
            "macro_btc_gate": macro_btc_gate,
            "approved_long_symbols": [],
            "approved_short_symbols": [],
            "on_demand_smc_targets": [],
            "vetoed_symbols": {},
            "sector_breadth": {},
            "layer_waterfall": {},
            "coin_assessments": {},
        }

    # 1. Her coin için temel fiyat, RVOL ve OI metriklerini çıkar
    parsed_coins: Dict[str, Dict[str, Any]] = {}
    for coin, data in coins_raw.items():
        bar_m = _compute_bar_metrics(
            data.get("bars_1h", []),
            data.get("bars_4h", []),
            fallback_price=float(data.get("spot_last_price", 0.0) or data.get("mark_price", 0.0) or 0.0),
            fallback_change_24h_pct=float(data.get("spot_price_change_24h_pct", 0.0) or 0.0),
        )
        oi_m = _compute_oi_metrics(data.get("oi_history_1h", []))
        spot_vol_24h = float(data.get("spot_quote_volume_24h", 0.0) or 0.0)
        fut_vol_24h = float(data.get("futures_quote_volume_24h", 0.0) or 0.0)
        spot_to_fut_ratio = round(spot_vol_24h / fut_vol_24h, 3) if fut_vol_24h > 0 else 1.0
        funding_rate_pct = round(float(data.get("funding_rate", 0.0) or 0.0) * 100.0, 4)

        parsed_coins[coin] = {
            **bar_m,
            **oi_m,
            "coin": coin,
            "spot_symbol": data.get("spot_symbol", f"{coin}USDT"),
            "futures_symbol": data.get("futures_symbol", f"{coin}USDT"),
            "smc_symbol": data.get("smc_symbol", f"{coin}USD"),
            "layer": int(data.get("layer", 3)),
            "layer_name": data.get("layer_name", "LAYER_3_LEGACY_PAYMENT"),
            "sector": data.get("sector", "LEGACY_PAYMENT_INFRA"),
            "spot_quote_volume_24h": spot_vol_24h,
            "futures_quote_volume_24h": fut_vol_24h,
            "spot_to_futures_vol_ratio": spot_to_fut_ratio,
            "funding_rate_pct": funding_rate_pct,
            "deep_fetched": bool(data.get("deep_fetched", bool(data.get("bars_1h")))),
            "bars_4h": data.get("bars_4h", []),
        }

    btc_m = parsed_coins["BTC"]
    eth_m = parsed_coins["ETH"]
    sol_m = parsed_coins.get("SOL", eth_m)
    sui_m = parsed_coins.get("SUI", sol_m)

    # 2. Çapraz Öncüler (ETH/BTC, SOL/ETH, SUI/SOL) ve Relative Strength (ALT/BTC, ALT/ETH)
    eth_btc_24h = round(eth_m["change_24h_pct"] - btc_m["change_24h_pct"], 2)
    eth_btc_5d = round(eth_m["change_5d_pct"] - btc_m["change_5d_pct"], 2)
    sol_eth_24h = round(sol_m["change_24h_pct"] - eth_m["change_24h_pct"], 2)
    sui_sol_24h = round(sui_m["change_24h_pct"] - sol_m["change_24h_pct"], 2)

    for coin, cm in parsed_coins.items():
        cm["rs_vs_btc_1h_pct"] = round(cm["change_1h_pct"] - btc_m["change_1h_pct"], 2)
        cm["rs_vs_btc_4h_pct"] = round(cm["change_4h_pct"] - btc_m["change_4h_pct"], 2)
        cm["rs_vs_btc_24h_pct"] = round(cm["change_24h_pct"] - btc_m["change_24h_pct"], 2)
        cm["rs_vs_btc_5d_pct"] = round(cm["change_5d_pct"] - btc_m["change_5d_pct"], 2)
        cm["rs_vs_eth_4h_pct"] = round(cm["change_4h_pct"] - eth_m["change_4h_pct"], 2)
        cm["rs_vs_eth_24h_pct"] = round(cm["change_24h_pct"] - eth_m["change_24h_pct"], 2)
        cm["ratio_structure_4h"] = _check_ratio_4h_structure(cm["bars_4h"], btc_m["bars_4h"])

    # 3. BTC Dominance (BTC.D) Analizi
    dom_info = raw_snapshot.get("btc_dominance", {}) if isinstance(raw_snapshot, Mapping) else {}
    btcdom_24h = dom_info.get("btcdom_change_24h_pct")
    btcdom_4h = dom_info.get("btcdom_change_4h_pct")
    btc_dom_pct = dom_info.get("btc_dominance_pct")

    if btcdom_24h is None:
        alt_avg_24h = sum(
            c["change_24h_pct"] for k, c in parsed_coins.items() if k != "BTC"
        ) / max(1, len(parsed_coins) - 1)
        btcdom_24h = round((btc_m["change_24h_pct"] - alt_avg_24h) * 0.35, 2)
    if btcdom_4h is None:
        alt_avg_4h = sum(
            c["change_4h_pct"] for k, c in parsed_coins.items() if k != "BTC"
        ) / max(1, len(parsed_coins) - 1)
        btcdom_4h = round((btc_m["change_4h_pct"] - alt_avg_4h) * 0.35, 2)

    btcdom_falling = float(btcdom_24h) <= -0.05 or float(btcdom_4h) <= -0.05
    btcdom_rising = float(btcdom_24h) >= 0.10 or float(btcdom_4h) >= 0.08

    if btc_m["change_24h_pct"] >= -0.5 and btcdom_falling:
        dominance_regime = "ALT_CAPITAL_DISPERSION"
    elif btc_m["change_24h_pct"] > 0.5 and btcdom_rising:
        dominance_regime = "BTC_CONCENTRATION"
    elif btc_m["change_24h_pct"] < -0.5 and btcdom_rising:
        dominance_regime = "ALT_RISK_OFF_BLEED"
    elif btc_m["change_24h_pct"] < -0.5 and btcdom_falling:
        dominance_regime = "ALT_DECOUPLED_RESILIENCE"
    else:
        dominance_regime = "NEUTRAL_DOMINANCE"

    # 4. Sektör Genişliği (Sector Breadth - 39 Coin Üzerinden)
    sector_groups: Dict[str, List[Dict[str, Any]]] = {}
    for coin, cm in parsed_coins.items():
        if coin in ("BTC", "ETH"):
            continue
        sector_groups.setdefault(cm["sector"], []).append(cm)

    sector_breadth: Dict[str, Dict[str, Any]] = {}
    for sector_name, members in sector_groups.items():
        count = len(members)
        outperforming_btc = [
            m["coin"]
            for m in members
            if m["rs_vs_btc_24h_pct"] > 0.0 or (m["rs_vs_btc_4h_pct"] > 0.25 and m["effective_rvol"] >= 1.2)
        ]
        underperforming_btc = [
            m["coin"]
            for m in members
            if m["rs_vs_btc_24h_pct"] < 0.0 and m["rs_vs_btc_4h_pct"] <= 0.0
        ]
        deep_members = [m for m in members if m.get("deep_fetched") and m["effective_rvol"] != 1.0]
        rvol_pool = deep_members if deep_members else members
        avg_rvol = round(sum(m["effective_rvol"] for m in rvol_pool) / max(1, len(rvol_pool)), 2)
        avg_rs_btc_24h = round(sum(m["rs_vs_btc_24h_pct"] for m in members) / max(1, count), 2)
        avg_funding = round(sum(m["funding_rate_pct"] for m in members) / max(1, count), 4)
        long_breadth_ratio = round(len(outperforming_btc) / max(1, count), 2)
        short_breadth_ratio = round(len(underperforming_btc) / max(1, count), 2)

        confirmed_long = long_breadth_ratio >= 0.60 and avg_rvol >= 1.15
        confirmed_short = short_breadth_ratio >= 0.60

        sector_breadth[sector_name] = {
            "sector": sector_name,
            "member_count": count,
            "members": [m["coin"] for m in members],
            "outperforming_coins": outperforming_btc,
            "underperforming_coins": underperforming_btc,
            "long_breadth_ratio": long_breadth_ratio,
            "short_breadth_ratio": short_breadth_ratio,
            "avg_rvol": avg_rvol,
            "avg_rs_vs_btc_24h_pct": avg_rs_btc_24h,
            "avg_funding_rate_pct": avg_funding,
            "confirmed_long_rotation": confirmed_long,
            "confirmed_short_rotation": confirmed_short,
            "status": (
                "SECTOR_INFLOW_CONFIRMED"
                if confirmed_long
                else "SECTOR_OUTFLOW_CONFIRMED"
                if confirmed_short
                else "FRAGMENTED_SINGLE_COIN_MOVES"
            ),
        }

    # 5. Market-Cap Risk Layer Waterfall (Katman 0 BTC -> Katman 6 Meme)
    layer_groups: Dict[int, List[Dict[str, Any]]] = {}
    for coin, cm in parsed_coins.items():
        layer_groups.setdefault(cm["layer"], []).append(cm)

    layer_waterfall: Dict[str, Dict[str, Any]] = {}
    active_inflow_layers: List[int] = []
    for layer_idx in sorted(layer_groups.keys()):
        l_members = layer_groups[layer_idx]
        l_name = l_members[0]["layer_name"]
        avg_rs = round(sum(m["rs_vs_btc_24h_pct"] for m in l_members) / len(l_members), 2)
        deep_l = [m for m in l_members if m.get("deep_fetched") and m["effective_rvol"] != 1.0]
        rvol_l = deep_l if deep_l else l_members
        avg_rvol = round(sum(m["effective_rvol"] for m in rvol_l) / max(1, len(rvol_l)), 2)
        inflow_active = (layer_idx == 0 and btc_m["change_24h_pct"] > 0) or (
            avg_rs > 0.0 and avg_rvol >= 1.15
        )
        if inflow_active:
            active_inflow_layers.append(layer_idx)
        layer_waterfall[l_name] = {
            "layer_index": layer_idx,
            "coins": [m["coin"] for m in l_members],
            "avg_rs_vs_btc_24h_pct": avg_rs,
            "avg_rvol": avg_rvol,
            "inflow_active": inflow_active,
        }

    # Meme Köpük / Geç Döngü Uyarısı (Froth Detector)
    meme_sec = sector_breadth.get("MEME_SECTOR", {})
    l1_sec = sector_breadth.get("HIGH_BETA_L1_L2", {})
    meme_froth_warning = (
        float(meme_sec.get("avg_rs_vs_btc_24h_pct", 0.0)) >= 3.0
        and float(meme_sec.get("avg_funding_rate_pct", 0.0)) >= 0.030
        and eth_btc_24h < 0.0
        and float(l1_sec.get("avg_rs_vs_btc_24h_pct", 0.0)) <= 0.0
    )

    # 6. Her Coin İçin 8 Faktörlü ROTATION_SCORE ve Veto Kalkanı Değerlendirmesi
    macro_gate_up = (macro_btc_gate or "NEUTRAL_RANGE").upper()
    if capital_preservation_mode or "DEFENSIVE" in macro_gate_up or "HOLD" in macro_gate_up:
        target_macro_dir = "DEFENSIVE_HOLD"
    elif "LONG" in macro_gate_up and not btc_decoupling_active:
        target_macro_dir = "LONG"
    elif "SHORT" in macro_gate_up:
        target_macro_dir = "SHORT"
    else:
        target_macro_dir = "NEUTRAL"

    coin_assessments: Dict[str, Dict[str, Any]] = {}
    approved_long_symbols: List[str] = []
    approved_short_symbols: List[str] = []
    vetoed_symbols: Dict[str, str] = {}

    for coin, cm in parsed_coins.items():
        if coin == "BTC":
            continue

        sec_info = sector_breadth.get(cm["sector"], {})
        ratio_struct = cm["ratio_structure_4h"]
        rvol = cm["effective_rvol"]
        rs_btc_1h = cm["rs_vs_btc_1h_pct"]
        rs_btc_4h = cm["rs_vs_btc_4h_pct"]
        rs_btc_24h = cm["rs_vs_btc_24h_pct"]
        rs_eth_24h = cm["rs_vs_eth_24h_pct"]
        oi_4h = cm["oi_change_4h_pct"]
        oi_24h = cm["oi_change_24h_pct"]
        funding = cm["funding_rate_pct"]
        price_4h = cm["change_4h_pct"]
        price_24h = cm["change_24h_pct"]
        spot_fut_ratio = cm["spot_to_futures_vol_ratio"]

        # --- Türev (Open Interest + Funding + Spot Hacim) Rejim Sınıflandırması ---
        is_leverage_squeeze_trap = (
            price_24h >= 5.0
            and (rvol < 1.20 or spot_fut_ratio < 0.12)
            and (oi_24h >= 12.0 or oi_4h >= 8.0 or funding >= 0.035)
            and funding >= 0.028
        )
        is_short_squeeze_danger = (
            (rs_btc_24h >= 0.5 or rs_btc_4h >= 0.5)
            and (rvol >= 1.25 or oi_4h >= 1.5 or spot_fut_ratio >= 0.25)
            and funding < -0.003
        )
        is_organic_inflow = (
            (price_4h > 0 or price_24h > 0)
            and rvol >= 1.30
            and oi_4h >= 0.5
            and oi_24h <= 25.0
            and funding <= 0.025
        )
        is_capitulation_oi_flushed = (
            (price_24h <= -9.0 or rs_btc_24h <= -8.5)
            and (oi_4h <= -4.5 or oi_24h <= -9.0)
            and not is_short_squeeze_danger
        )
        is_short_buildup_distribution = (
            (rs_btc_24h <= -0.8 or rs_btc_4h <= -0.3)
            and (price_4h < 0.0 or price_24h < 0.0)
            and oi_4h >= -1.5
            and rvol >= 1.20
            and not is_short_squeeze_danger
            and not is_capitulation_oi_flushed
        )
        is_organic_distribution = (
            (rs_btc_24h < 0.0 or rs_btc_4h < 0.0)
            and (price_4h < 0.0 or price_24h < 0.0)
            and not is_short_squeeze_danger
            and not is_capitulation_oi_flushed
        )

        if is_leverage_squeeze_trap:
            derivatives_regime = "LEVERAGE_SQUEEZE_TRAP"
        elif is_short_squeeze_danger:
            derivatives_regime = "SHORT_SQUEEZE_DANGER"
        elif is_organic_inflow:
            derivatives_regime = "ORGANIC_CAPITAL_INFLOW"
        elif is_capitulation_oi_flushed:
            derivatives_regime = "CAPITULATION_OI_FLUSHED"
        elif is_short_buildup_distribution:
            derivatives_regime = "SHORT_BUILDUP_DISTRIBUTION"
        elif is_organic_distribution:
            derivatives_regime = "ORGANIC_DISTRIBUTION_FLUSH"
        else:
            derivatives_regime = "NEUTRAL_DERIVATIVES"

        # --- Hacim Anomalisi ve Fiyat-Hacim Emilimi (Stealth Accumulation) ---
        is_stealth_accumulation = (
            rvol >= 2.20
            and 0.10 <= abs(price_4h) <= 3.20
            and rs_btc_4h >= 0.0
        )
        is_unconfirmed_spike = abs(price_24h) >= 8.0 and rvol < 1.15
        if is_stealth_accumulation:
            volume_regime = "STEALTH_ACCUMULATION"
        elif is_unconfirmed_spike:
            volume_regime = "UNCONFIRMED_PRICE_SPIKE"
        elif rvol >= 1.80:
            volume_regime = "STRONG_VOLUME_EXPANSION"
        elif rvol >= 1.25:
            volume_regime = "MODERATE_VOLUME_EXPANSION"
        else:
            volume_regime = "NORMAL_OR_LOW_VOLUME"

        # 1. Relative Strength (Max 25 Puan)
        rs_long_pts = 0
        if rs_btc_24h > 0 and rs_btc_4h > 0:
            rs_long_pts += 15 if rs_btc_24h >= 2.0 else 11
        elif rs_btc_4h > 0.3 or rs_btc_1h > 0.3:
            rs_long_pts += 8
        if rs_eth_24h >= 0 or cm["rs_vs_eth_4h_pct"] >= 0:
            rs_long_pts += 5
        if ratio_struct["bullish"]:
            rs_long_pts += 5
        rs_long_pts = min(25, rs_long_pts)

        rs_short_pts = 0
        if rs_btc_24h < 0 and rs_btc_4h < 0:
            # Taze/Aktif göreceli zayıflık (-1.5% ile -8.0% arası tatlı bölge)
            if -8.5 <= rs_btc_24h <= -1.5:
                rs_short_pts += 15
            elif rs_btc_24h < -8.5:
                rs_short_pts += 12
            else:
                rs_short_pts += 10
        elif rs_btc_4h < -0.3 or rs_btc_1h < -0.3:
            rs_short_pts += 7
        if rs_eth_24h < 0 or cm["rs_vs_eth_4h_pct"] < 0:
            rs_short_pts += 5
        if ratio_struct["bearish"]:
            rs_short_pts += 5
        rs_short_pts = min(25, rs_short_pts)

        # 2. Volume Expansion & Absorption (Max 20 Puan)
        if is_stealth_accumulation:
            vol_long_pts = 20
        elif is_unconfirmed_spike:
            vol_long_pts = 0
        elif rvol >= 2.5:
            vol_long_pts = 20
        elif rvol >= 1.8:
            vol_long_pts = 16
        elif rvol >= 1.3:
            vol_long_pts = 13
        elif rvol >= 1.0:
            vol_long_pts = 8
        else:
            vol_long_pts = 3

        if is_capitulation_oi_flushed:
            vol_short_pts = 6
        elif rvol >= 1.8 and rs_btc_4h <= -0.3:
            vol_short_pts = 20
        elif rvol >= 1.35 and (rs_btc_4h < 0 or rs_btc_24h <= -1.2):
            vol_short_pts = 16
        elif rvol >= 1.15 and rs_btc_24h < 0:
            vol_short_pts = 11
        else:
            vol_short_pts = 4

        # 3. Market-Cap Layer Waterfall (Max 10 Puan)
        upper_layers_healthy = (eth_btc_24h >= -0.5) or (1 in active_inflow_layers) or (2 in active_inflow_layers)
        if cm["layer"] == 6 and meme_froth_warning:
            layer_long_pts = 0
        elif cm["layer"] in active_inflow_layers and upper_layers_healthy:
            layer_long_pts = 10
        elif cm["layer"] in (1, 2) and rs_btc_4h > 0:
            layer_long_pts = 8
        elif upper_layers_healthy:
            layer_long_pts = 6
        else:
            layer_long_pts = 2

        layer_short_pts = 10 if (cm["layer"] >= 2 and eth_btc_24h <= 0 and rs_btc_4h < 0) else 5

        # 4. BTC Dominance (Max 10 Puan)
        if dominance_regime == "ALT_CAPITAL_DISPERSION":
            dom_long_pts = 10
            dom_short_pts = 2
        elif dominance_regime == "ALT_DECOUPLED_RESILIENCE":
            dom_long_pts = 8
            dom_short_pts = 0
        elif dominance_regime == "ALT_RISK_OFF_BLEED":
            dom_long_pts = 2
            dom_short_pts = 10
        elif dominance_regime == "BTC_CONCENTRATION":
            dom_long_pts = 4
            dom_short_pts = 7
        else:
            dom_long_pts = 6
            dom_short_pts = 6

        # 5. ETH/BTC & Cross-Tier Bellwethers (Max 10 Puan)
        bell_long_pts = 0
        if eth_btc_24h > 0 or eth_btc_5d > 0:
            bell_long_pts += 5
        if (cm["layer"] >= 2 and sol_eth_24h >= 0) or (cm["coin"] == "SUI" and sui_sol_24h > 0):
            bell_long_pts += 5
        elif rs_eth_24h > 0:
            bell_long_pts += 4
        bell_long_pts = min(10, bell_long_pts)

        bell_short_pts = 0
        if eth_btc_24h < 0:
            bell_short_pts += 5
        if sol_eth_24h < 0 and rs_eth_24h < 0:
            bell_short_pts += 5
        elif rs_eth_24h < 0:
            bell_short_pts += 3
        bell_short_pts = min(10, bell_short_pts)

        # 6. Open Interest + Funding (Max 15 Puan)
        if derivatives_regime == "ORGANIC_CAPITAL_INFLOW":
            deriv_long_pts = 15
            deriv_short_pts = 2
        elif derivatives_regime == "SHORT_SQUEEZE_DANGER":
            deriv_long_pts = 14
            deriv_short_pts = 0
        elif derivatives_regime == "LEVERAGE_SQUEEZE_TRAP":
            deriv_long_pts = 0
            deriv_short_pts = 12
        elif derivatives_regime == "SHORT_BUILDUP_DISTRIBUTION":
            deriv_long_pts = 2
            deriv_short_pts = 15
        elif derivatives_regime == "ORGANIC_DISTRIBUTION_FLUSH":
            deriv_long_pts = 2
            deriv_short_pts = 12
        elif derivatives_regime == "CAPITULATION_OI_FLUSHED":
            deriv_long_pts = 4
            deriv_short_pts = 5
        else:
            deriv_long_pts = 9 if funding <= 0.015 else 5
            deriv_short_pts = 8 if funding >= 0.0 else 4

        # 7. Sector Breadth (Max 10 Puan)
        if coin == "ETH":
            sec_long_pts = 10 if eth_btc_24h > 0 else 4
            sec_short_pts = 10 if eth_btc_24h < 0 else 4
            is_single_coin_outlier = False
        else:
            long_br = float(sec_info.get("long_breadth_ratio", 0.0))
            short_br = float(sec_info.get("short_breadth_ratio", 0.0))
            is_single_coin_outlier = (rs_btc_24h > 1.0 and long_br < 0.50) or (
                rs_btc_24h < -1.0 and short_br < 0.50
            )
            if sec_info.get("confirmed_long_rotation"):
                sec_long_pts = 10
            elif long_br >= 0.50:
                sec_long_pts = 6
            else:
                sec_long_pts = 0

            if sec_info.get("confirmed_short_rotation"):
                sec_short_pts = 10
            elif short_br >= 0.50:
                sec_short_pts = 6
            else:
                sec_short_pts = 0

        # --- Geç Kalınmış / Aşırı Şişmiş Hareket Cezası (FOMO & Oversold Chase Penalty) ---
        late_long_fomo_penalty = (
            15
            if (price_24h >= 18.0 or (rs_btc_24h >= 14.0 and funding >= 0.025))
            else 0
        )
        late_short_chase_penalty = (
            15
            if (price_24h <= -12.0 or is_capitulation_oi_flushed)
            else (8 if rs_btc_24h <= -9.2 else 0)
        )

        long_score = max(
            0,
            rs_long_pts
            + vol_long_pts
            + layer_long_pts
            + dom_long_pts
            + bell_long_pts
            + deriv_long_pts
            + sec_long_pts
            - late_long_fomo_penalty,
        )
        short_score = max(
            0,
            rs_short_pts
            + vol_short_pts
            + layer_short_pts
            + dom_short_pts
            + bell_short_pts
            + deriv_short_pts
            + sec_short_pts
            - late_short_chase_penalty,
        )

        # MUTLAK VETO KALKANLARI
        veto_reasons_long: List[str] = []
        veto_reasons_short: List[str] = []

        if rs_btc_24h < -0.5 and rs_btc_4h < -0.25:
            veto_reasons_long.append(
                f"RS_UNDERPERFORMING_BTC (ALT/BTC 24s: %{rs_btc_24h:+.2f}, 4s: %{rs_btc_4h:+.2f})"
            )
        if rs_btc_1h <= -0.65:
            veto_reasons_long.append(
                f"MICRO_RS_BREAKDOWN_HOLD (Son 1s ALT/BTC %{rs_btc_1h:+.2f} sert aşağı kırıldı; 15m long girişi bekletiliyor)"
            )
        if ratio_struct["swing_low_broken"]:
            veto_reasons_long.append("ALT_BTC_4H_SWING_LOW_BROKEN (CHoCH)")
        if is_leverage_squeeze_trap:
            veto_reasons_long.append(
                f"LEVERAGE_SQUEEZE_TRAP (Spot RVOL: {rvol}x zayıf, OI 24s: %{oi_24h:+.1f}, Funding: %{funding:+.4f})"
            )
        if is_unconfirmed_spike:
            veto_reasons_long.append(
                f"UNCONFIRMED_PRICE_SPIKE (Fiyat %{price_24h:+.1f} ama Spot RVOL {rvol}x)"
            )
        if cm["layer"] == 6 and meme_froth_warning:
            veto_reasons_long.append(
                "MEME_LATE_CYCLE_FROTH_VETO (ETH/L1 zayıflarken Meme katmanında aşırı kaldıraç köpüğü)"
            )
        if coin != "ETH" and not sec_info.get("confirmed_long_rotation") and float(sec_info.get("long_breadth_ratio", 0.0)) < 0.50:
            veto_reasons_long.append(
                f"NO_SECTOR_BREADTH ({cm['sector']} sepetinde tekil hareket; sektör genişliği %{float(sec_info.get('long_breadth_ratio', 0.0))*100:.0f})"
            )

        # Short Veto Kuralları (DASH ve LTC Kalkanı + 1H Mikro Dönüş Kalkanı)
        if rs_btc_24h > 0.5 or (rs_btc_4h > 0.4 and rvol >= 1.25):
            veto_reasons_short.append(
                f"RS_CONTRA_SHORT_VETO ({coin} piyasaya karşı güçleniyor: ALT/BTC 24s %{rs_btc_24h:+.2f}, 4s %{rs_btc_4h:+.2f}, RVOL {rvol}x)"
            )
        if rs_btc_1h >= 0.65:
            veto_reasons_short.append(
                f"MICRO_RS_REVERSAL_HOLD (Son 1s ALT/BTC %{rs_btc_1h:+.2f} yukarı döndü; 15m short girişi bekletiliyor)"
            )
        if is_short_squeeze_danger:
            veto_reasons_short.append(
                f"SHORT_SQUEEZE_DANGER (ALT/BTC pozitif + Spot RVOL {rvol}x + Negatif Funding %{funding:+.4f} -> Short Sıkıştırması!)"
            )
        if dominance_regime == "ALT_DECOUPLED_RESILIENCE" and rs_btc_4h > 0:
            veto_reasons_short.append(
                "ALT_DECOUPLED_RESILIENCE (BTC düşerken BTC.D düşüyor ve ALT/BTC yükseliyor -> Short Yasak!)"
            )
        if ratio_struct["swing_high_broken"]:
            veto_reasons_short.append("ALT_BTC_4H_SWING_HIGH_BROKEN (Yukarı Kırılım)")

        smc_symbol = cm["smc_symbol"]
        if target_macro_dir == "DEFENSIVE_HOLD":
            rotation_gate = "DEFENSIVE_HOLD"
            active_score = 0
            gate_reason = "Makro Sermaye Koruma / Defensive Hold aktif."
        elif target_macro_dir == "LONG":
            active_score = long_score
            if veto_reasons_long:
                rotation_gate = "NEUTRAL_RANGE"
                gate_reason = f"LONG Rotasyon Vetosu: {' | '.join(veto_reasons_long)}"
                vetoed_symbols[smc_symbol] = gate_reason
            elif long_score >= ROTATION_SCORE_THRESHOLD:
                rotation_gate = "LONG_ONLY"
                gate_reason = (
                    f"ROTASYON ONAYLI LONG (Skor: {long_score}/100 | ALT/BTC 24s: %{rs_btc_24h:+.2f}, 1s: %{rs_btc_1h:+.2f} | "
                    f"RVOL: {rvol}x [{volume_regime}] | Türev: {derivatives_regime} | Sektör: {cm['sector']})"
                )
                approved_long_symbols.append(smc_symbol)
            else:
                rotation_gate = "NEUTRAL_RANGE"
                gate_reason = f"Rotasyon Skoru Yetersiz ({long_score}/{ROTATION_SCORE_THRESHOLD})"
        elif target_macro_dir == "SHORT":
            active_score = short_score
            if veto_reasons_short:
                rotation_gate = "NEUTRAL_RANGE"
                gate_reason = f"🛑 SHORT ROTASYON KALKANI (VETO): {' | '.join(veto_reasons_short)}"
                vetoed_symbols[smc_symbol] = gate_reason
            elif (
                short_score >= ROTATION_SCORE_THRESHOLD
                and (rs_btc_24h <= -0.8 or rs_btc_4h <= -0.4)
                and rvol >= 1.15
            ):
                rotation_gate = "SHORT_ONLY"
                gate_reason = (
                    f"ROTASYON ONAYLI SHORT (Skor: {short_score}/100 | ALT/BTC 24s: %{rs_btc_24h:+.2f}, 1s: %{rs_btc_1h:+.2f} | "
                    f"RVOL: {rvol}x | Türev: {derivatives_regime} | Sektör: {cm['sector']})"
                )
                approved_short_symbols.append(smc_symbol)
            else:
                rotation_gate = "NEUTRAL_RANGE"
                gate_reason = f"Short Rotasyon / Göreli Zayıflık Skoru Yetersiz ({short_score}/{ROTATION_SCORE_THRESHOLD}, RVOL: {rvol}x)"
        else:
            active_score = max(long_score, short_score)
            rotation_gate = "NEUTRAL_RANGE"
            gate_reason = f"Makro BTC Kapısı Yönsüz ({macro_btc_gate}); altcoin rotasyonu beklemede."

        coin_assessments[coin] = {
            "coin": coin,
            "spot_symbol": cm["spot_symbol"],
            "futures_symbol": cm["futures_symbol"],
            "smc_symbol": smc_symbol,
            "layer": cm["layer"],
            "layer_name": cm["layer_name"],
            "sector": cm["sector"],
            "price": cm["close"],
            "change_1h_pct": cm["change_1h_pct"],
            "change_4h_pct": cm["change_4h_pct"],
            "change_24h_pct": cm["change_24h_pct"],
            "rs_vs_btc_1h_pct": rs_btc_1h,
            "rs_vs_btc_4h_pct": rs_btc_4h,
            "rs_vs_btc_24h_pct": rs_btc_24h,
            "rs_vs_btc_5d_pct": cm["rs_vs_btc_5d_pct"],
            "rs_vs_eth_24h_pct": rs_eth_24h,
            "rvol_1h": cm["rvol_1h"],
            "rvol_4h": cm["rvol_4h"],
            "effective_rvol": rvol,
            "volume_regime": volume_regime,
            "oi_value_usd": cm["oi_value_usd"],
            "oi_change_4h_pct": oi_4h,
            "oi_change_24h_pct": oi_24h,
            "funding_rate_pct": funding,
            "spot_to_futures_vol_ratio": spot_fut_ratio,
            "derivatives_regime": derivatives_regime,
            "is_single_coin_outlier": is_single_coin_outlier,
            "long_rotation_score": long_score,
            "short_rotation_score": short_score,
            "active_rotation_score": active_score,
            "score_breakdown": {
                "relative_strength": rs_long_pts if target_macro_dir != "SHORT" else rs_short_pts,
                "volume_anomaly": vol_long_pts if target_macro_dir != "SHORT" else vol_short_pts,
                "market_cap_layer": layer_long_pts if target_macro_dir != "SHORT" else layer_short_pts,
                "btc_dominance": dom_long_pts if target_macro_dir != "SHORT" else dom_short_pts,
                "eth_btc_bellwether": bell_long_pts if target_macro_dir != "SHORT" else bell_short_pts,
                "oi_and_funding": deriv_long_pts if target_macro_dir != "SHORT" else deriv_short_pts,
                "sector_breadth": sec_long_pts if target_macro_dir != "SHORT" else sec_short_pts,
                "late_chase_penalty": -late_long_fomo_penalty if target_macro_dir != "SHORT" else -late_short_chase_penalty,
            },
            "veto_reasons_long": veto_reasons_long,
            "veto_reasons_short": veto_reasons_short,
            "rotation_gate": rotation_gate,
            "smc_handoff_allowed": rotation_gate in ("LONG_ONLY", "SHORT_ONLY"),
            "rationale": gate_reason,
        }

    ranked_candidates = sorted(
        coin_assessments.values(),
        key=lambda x: (
            1 if x["smc_handoff_allowed"] else 0,
            x["active_rotation_score"],
            x["effective_rvol"],
            abs(x["rs_vs_btc_4h_pct"]),
        ),
        reverse=True,
    )

    # ON-DEMAND SMC HEDEFLERİ (Sektör Çeşitlendirmeli: Katman 2-6 Altcoin Sektörlerinden Max 3 Lider)
    approved_candidates = [
        item for item in ranked_candidates if item["smc_handoff_allowed"] and item["layer"] >= 2
    ]
    if not approved_candidates:
        approved_candidates = [item for item in ranked_candidates if item["smc_handoff_allowed"]]
    diversified_items: List[Dict[str, Any]] = []
    seen_sectors: set[str] = set()

    # 1. Tur: Farklı sektörlerin 1 numaralı liderlerini seç (Sektör Tekelleşmesini Önle)
    for item in approved_candidates:
        if len(diversified_items) >= max_on_demand_targets:
            break
        if item["sector"] not in seen_sectors:
            diversified_items.append(item)
            seen_sectors.add(item["sector"])

    # 2. Tur (Fallback): Eğer onay alan sektör sayısı max_on_demand_targets'tan azsa kalan yuvaları en yüksek skorlularla doldur
    if len(diversified_items) < max_on_demand_targets:
        picked_coins = {x["coin"] for x in diversified_items}
        for item in approved_candidates:
            if len(diversified_items) >= max_on_demand_targets:
                break
            if item["coin"] not in picked_coins:
                diversified_items.append(item)
                picked_coins.add(item["coin"])

    on_demand_smc_targets = [
        {
            "coin": item["coin"],
            "smc_symbol": item["smc_symbol"],
            "spot_symbol": item["spot_symbol"],
            "futures_symbol": item["futures_symbol"],
            "direction": "long" if item["rotation_gate"] == "LONG_ONLY" else "short",
            "rotation_gate": item["rotation_gate"],
            "rotation_score": item["active_rotation_score"],
            "rs_vs_btc_1h_pct": item["rs_vs_btc_1h_pct"],
            "rs_vs_btc_4h_pct": item["rs_vs_btc_4h_pct"],
            "rs_vs_btc_24h_pct": item["rs_vs_btc_24h_pct"],
            "rs_vs_eth_24h_pct": item["rs_vs_eth_24h_pct"],
            "effective_rvol": item["effective_rvol"],
            "volume_regime": item["volume_regime"],
            "derivatives_regime": item["derivatives_regime"],
            "funding_rate_pct": item["funding_rate_pct"],
            "oi_change_4h_pct": item["oi_change_4h_pct"],
            "layer": item["layer"],
            "layer_name": item["layer_name"],
            "sector": item["sector"],
            "rationale": item["rationale"],
        }
        for item in diversified_items
    ]

    return {
        "status": raw_snapshot.get("status", "AVAILABLE"),
        "evaluated_at_epoch_ms": int(time.time() * 1000),
        "universe_size": len(parsed_coins),
        "macro_btc_gate": macro_btc_gate,
        "target_macro_direction": target_macro_dir,
        "rotation_score_threshold": ROTATION_SCORE_THRESHOLD,
        "meme_froth_warning": meme_froth_warning,
        "btc_dominance_panel": {
            "btc_dominance_pct": btc_dom_pct,
            "btcdom_change_4h_pct": btcdom_4h,
            "btcdom_change_24h_pct": btcdom_24h,
            "dominance_regime": dominance_regime,
        },
        "bellwether_ratios": {
            "eth_btc_24h_pct": eth_btc_24h,
            "eth_btc_5d_pct": eth_btc_5d,
            "sol_eth_24h_pct": sol_eth_24h,
            "sui_sol_24h_pct": sui_sol_24h,
        },
        "active_inflow_layers": active_inflow_layers,
        "layer_waterfall": layer_waterfall,
        "sector_breadth": sector_breadth,
        "approved_long_symbols": approved_long_symbols,
        "approved_short_symbols": approved_short_symbols,
        "on_demand_smc_targets": on_demand_smc_targets,
        "vetoed_symbols": vetoed_symbols,
        "top_rotation_candidates": [
            {
                "coin": item["coin"],
                "smc_symbol": item["smc_symbol"],
                "rotation_gate": item["rotation_gate"],
                "active_rotation_score": item["active_rotation_score"],
                "rs_vs_btc_24h_pct": item["rs_vs_btc_24h_pct"],
                "effective_rvol": item["effective_rvol"],
                "derivatives_regime": item["derivatives_regime"],
                "sector": item["sector"],
                "rationale": item["rationale"],
            }
            for item in ranked_candidates[:8]
        ],
        "coin_assessments": coin_assessments,
    }
