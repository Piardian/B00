"""
🌺 Begonya 00 - Gelismis SFP (Swing Failure Pattern) Tespit Motoru
PDH/PDL (Dünün Tepesi/Dibi), Asya Seansı Uçları ve Likidite Havuzları Önceliği
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from datetime import time
from .config import (
    SFP_SWING_LOOKBACK,
    SFP_MIN_WICK_RATIO,
    SFP_SL_BUFFER_ATR,
    SFP_RR_TARGET_1,
    SFP_RR_TARGET_2,
    SFP_MIN_RR_TARGET_1,
    SFP_MIN_RR_TARGET_2,
    get_asset_sl_buffer,
    SFP_ALLOWED_POOLS,
    round_price,
    ENTRY_MODEL,
    USE_IFVG_ENTRY,
    REQUIRE_STRUCTURAL_BREAKER,
)
from .volume_anomaly import VolumeAnomalyDetector
from .entry_mechanics import (
    calculate_ce_entry,
    detect_ifvg_short,
    detect_ifvg_long,
    detect_structural_breaker_short,
    detect_structural_breaker_long,
)


class SFPDetector:
    def __init__(
        self,
        swing_lookback: int = SFP_SWING_LOOKBACK,
        min_wick_ratio: float = SFP_MIN_WICK_RATIO,
        volume_detector: Optional[VolumeAnomalyDetector] = None,
    ):
        self.swing_lookback = swing_lookback
        self.min_wick_ratio = min_wick_ratio
        self.volume_detector = volume_detector or VolumeAnomalyDetector()

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        if len(df) < period + 1:
            return float((df["high"] - df["low"]).mean()) if len(df) > 0 else 0.001
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        tr = np.maximum(high[1:] - low[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
        atr = float(np.mean(tr[-period:]))
        return atr if atr > 0 else 0.001

    def _detect_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        15 dakikalık barlarda EMA-20, EMA-50 ve HTF EMA-200 ile kısa/orta/uzun vadeli trend yapısını okur.
        """
        if len(df) < 25:
            return {"trend": "NEUTRAL", "ema20": 0.0, "ema50": 0.0, "htf_bull": False, "htf_bear": False}

        close_series = df["close"]
        ema20 = float(close_series.ewm(span=20, adjust=False).mean().iloc[-1])
        ema50 = float(close_series.ewm(span=50, adjust=False).mean().iloc[-1])
        ema200 = float(close_series.ewm(span=200, adjust=False).mean().iloc[-1]) if len(df) >= 50 else ema50
        curr_close = float(close_series.iloc[-1])

        htf_bull = (curr_close > ema50) and (ema50 > ema200)
        htf_bear = (curr_close < ema50) and (ema50 < ema200)

        # Boğa Trendi: Fiyat > EMA20 > EMA50
        if curr_close > ema20 > ema50:
            return {"trend": "BULLISH", "ema20": ema20, "ema50": ema50, "htf_bull": htf_bull, "htf_bear": htf_bear}
        # Ayı Trendi: Fiyat < EMA20 < EMA50
        elif curr_close < ema20 < ema50:
            return {"trend": "BEARISH", "ema20": ema20, "ema50": ema50, "htf_bull": htf_bull, "htf_bear": htf_bear}
        else:
            return {"trend": "NEUTRAL", "ema20": ema20, "ema50": ema50, "htf_bull": htf_bull, "htf_bear": htf_bear}

    def _find_magnetic_targets(
        self,
        direction: str,
        entry: float,
        risk: float,
        atr: float,
        pools_data: Dict[str, Any],
        curr_close: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Fiyat hareketinin önündeki en yakın karşı likidite havuzunu (Opposing Pool) bularak
        sabit RR yerine hedefleri yapısal/manyetik seviyelere kenetler.
        Hedeflerin kesinlikle hem entry hem de o anki fiyatın (curr_close) önünde olduğunu garanti eder.
        """
        default_tp1 = entry - (risk * SFP_RR_TARGET_1) if direction == "SHORT" else entry + (risk * SFP_RR_TARGET_1)
        default_tp2 = entry - (risk * SFP_RR_TARGET_2) if direction == "SHORT" else entry + (risk * SFP_RR_TARGET_2)
        default_rr = SFP_RR_TARGET_2
        tp1_r = SFP_RR_TARGET_1

        tp1 = default_tp1
        tp2 = default_tp2
        tp1_note = f"Standart {SFP_RR_TARGET_1}R"
        tp2_note = f"Standart {default_rr}R"

        opposing_candidates = []
        if direction == "SHORT":
            # Hedef aşağıda: Karşı dipler (PDL, Asya Dibi, Swing Lows)
            # cand['price'] kesinlikle hem entry hem de o anki fiyatın altında olmalıdır!
            opposing_cutoff = min(entry, curr_close) if curr_close is not None else entry
            min_dist = atr * 0.15

            if pools_data.get("pdl") and pools_data["pdl"]["price"] < opposing_cutoff - min_dist:
                opposing_candidates.append(pools_data["pdl"])
            if pools_data.get("asian_low") and pools_data["asian_low"]["price"] < opposing_cutoff - min_dist:
                opposing_candidates.append(pools_data["asian_low"])
            for sl in pools_data.get("swing_lows", []):
                if sl["price"] < opposing_cutoff - min_dist:
                    opposing_candidates.append(sl)

            # En yakından en uzağa sırala (fiyat yüksekten düşüğe)
            opposing_candidates.sort(key=lambda x: x["price"], reverse=True)

            for cand in opposing_candidates:
                p_dist = entry - cand["price"]
                p_rr = p_dist / risk if risk > 0 else 0

                # TP1 aralığı (Zorunlu Minimum 1.0R): Dönüş olabilecek ilk likidite havuzunun hemen önüne koy
                if 1.0 <= p_rr <= 1.8 and tp1_note.startswith("Standart"):
                    tp1 = cand["price"] + (atr * 0.05)
                    tp1_r = round(p_rr, 2)
                    tp1_note = f"Manyetik Likidite ({cand['pool_label']} {round(p_rr, 2)}R)"

                # TP2 aralığı (Zorunlu Minimum 3.0R): Ana hedef havuzunun hemen önüne koy
                elif p_rr >= 3.0 and tp2_note.startswith("Standart"):
                    tp2 = cand["price"] + (atr * 0.05)
                    default_rr = round(p_rr, 2)
                    tp2_note = f"Manyetik Likidite ({cand['pool_label']} {round(p_rr, 2)}R)"
                    break

        elif direction == "LONG":
            # Hedef yukarıda: Karşı tepeler (PDH, Asya Zirvesi, Swing Highs)
            opposing_cutoff = max(entry, curr_close) if curr_close is not None else entry
            min_dist = atr * 0.15

            if pools_data.get("pdh") and pools_data["pdh"]["price"] > opposing_cutoff + min_dist:
                opposing_candidates.append(pools_data["pdh"])
            if pools_data.get("asian_high") and pools_data["asian_high"]["price"] > opposing_cutoff + min_dist:
                opposing_candidates.append(pools_data["asian_high"])
            for sh in pools_data.get("swing_highs", []):
                if sh["price"] > opposing_cutoff + min_dist:
                    opposing_candidates.append(sh)

            # En yakından en uzağa sırala (fiyat düşükten yükseğe)
            opposing_candidates.sort(key=lambda x: x["price"])

            for cand in opposing_candidates:
                p_dist = cand["price"] - entry
                p_rr = p_dist / risk if risk > 0 else 0

                # TP1 aralığı (Zorunlu Minimum 1.0R):
                if 1.0 <= p_rr <= 1.8 and tp1_note.startswith("Standart"):
                    tp1 = cand["price"] - (atr * 0.05)
                    tp1_r = round(p_rr, 2)
                    tp1_note = f"Manyetik Likidite ({cand['pool_label']} {round(p_rr, 2)}R)"

                # TP2 aralığı (Zorunlu Minimum 3.0R):
                elif p_rr >= 3.0 and tp2_note.startswith("Standart"):
                    tp2 = cand["price"] - (atr * 0.05)
                    default_rr = round(p_rr, 2)
                    tp2_note = f"Manyetik Likidite ({cand['pool_label']} {round(p_rr, 2)}R)"
                    break

        return {
            "tp1": tp1,
            "tp2": tp2,
            "tp1_r": tp1_r,
            "rr_ratio": default_rr,
            "tp1_note": tp1_note,
            "tp2_note": tp2_note,
        }

    def find_pivots_and_pools(self, df: pd.DataFrame, k: int = 3) -> Dict[str, Any]:
        """
        Grafikteki standart pivotlarin yani sira PDH/PDL, Asya Uclari ve Equal Highs/Lows havuzlarini cikarir.
        """
        n = len(df)
        highs = df["high"].values
        lows = df["low"].values
        dates = pd.to_datetime(df["datetime"])

        swing_highs = []
        swing_lows = []

        # 1. Standart Swing Pivotlari
        for i in range(k, n - k):
            current_h = highs[i]
            if all(current_h >= highs[i - j] for j in range(1, k + 1)) and all(current_h > highs[i + j] for j in range(1, k + 1)):
                swing_highs.append({
                    "index": i,
                    "price": float(current_h),
                    "datetime": dates.iloc[i],
                    "pool_type": "SWING_HIGH",
                    "pool_label": "Swing Zirvesi",
                })

            current_l = lows[i]
            if all(current_l <= lows[i - j] for j in range(1, k + 1)) and all(current_l < lows[i + j] for j in range(1, k + 1)):
                swing_lows.append({
                    "index": i,
                    "price": float(current_l),
                    "datetime": dates.iloc[i],
                    "pool_type": "SWING_LOW",
                    "pool_label": "Swing Dibi",
                })

        # 2. PDH (Previous Day High) ve PDL (Previous Day Low)
        current_date = dates.iloc[-1].date()
        unique_dates = sorted(list(set(dates.dt.date)))

        pdh = None
        pdl = None
        if len(unique_dates) >= 2:
            prev_date = unique_dates[-2]
            prev_day_bars = df[dates.dt.date == prev_date]
            if len(prev_day_bars) >= 5:
                pdh_price = float(prev_day_bars["high"].max())
                pdl_price = float(prev_day_bars["low"].min())
                pdh = {
                    "price": pdh_price,
                    "datetime": prev_day_bars.iloc[0]["datetime"],
                    "pool_type": "PDH",
                    "pool_label": "Dünün Zirvesi (PDH)",
                    "index": 0,
                }
                pdl = {
                    "price": pdl_price,
                    "datetime": prev_day_bars.iloc[0]["datetime"],
                    "pool_type": "PDL",
                    "pool_label": "Dünün Dibi (PDL)",
                    "index": 0,
                }

        # 3. Asya Seansı Uçları (00:00 - 06:00 UTC)
        asian_high = None
        asian_low = None
        today_bars = df[dates.dt.date == current_date]
        if len(today_bars) >= 4:
            asian_bars = today_bars[(today_bars["datetime"].dt.time >= time(0, 0)) & (today_bars["datetime"].dt.time <= time(6, 0))]
            if len(asian_bars) >= 4:
                asian_high = {
                    "price": float(asian_bars["high"].max()),
                    "datetime": asian_bars.iloc[-1]["datetime"],
                    "pool_type": "ASIAN_HIGH",
                    "pool_label": "Asya Seansı Zirvesi",
                    "index": 0,
                }
                asian_low = {
                    "price": float(asian_bars["low"].min()),
                    "datetime": asian_bars.iloc[-1]["datetime"],
                    "pool_type": "ASIAN_LOW",
                    "pool_label": "Asya Seansı Dibi",
                    "index": 0,
                }

        return {
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "pdh": pdh,
            "pdl": pdl,
            "asian_high": asian_high,
            "asian_low": asian_low,
        }

    def _calculate_smc_dealing_range(self, pools_data: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
        """
        SMC Dealing Range (Piyasa Yapısı Denge Alanı):
        Son majör Swing High ve Swing Low seviyelerini baz alarak Equilibrium (%50) hesaplar.
        Körleme periyot ortalaması yerine gerçek yapısal kırılım alanlarını kullanır.
        """
        sh_prices = [sh["price"] for sh in pools_data.get("swing_highs", [])[-8:]]
        sl_prices = [sl["price"] for sl in pools_data.get("swing_lows", [])[-8:]]

        if pools_data.get("pdh"):
            sh_prices.append(pools_data["pdh"]["price"])
        if pools_data.get("pdl"):
            sl_prices.append(pools_data["pdl"]["price"])

        if not sh_prices or not sl_prices:
            curr_close = float(df["close"].iloc[-1])
            return {"equilibrium": curr_close, "major_high": curr_close, "major_low": curr_close, "is_valid": False}

        major_high = max(sh_prices)
        major_low = min(sl_prices)
        range_height = max(major_high - major_low, 1e-6)
        equilibrium = (major_high + major_low) / 2.0

        return {
            "major_high": major_high,
            "major_low": major_low,
            "range_height": range_height,
            "equilibrium": equilibrium,
            "is_valid": True,
        }

    def find_fair_value_gaps(
        self,
        df: pd.DataFrame,
        lookback: int = 30,
        min_gap_atr: float = 0.08,
    ) -> List[Dict[str, Any]]:
        """
        Son 30 bardaki 3-mumlu Fair Value Gap (FVG / İmbalance) dengesizlik alanlarını tespit eder.
        """
        n = len(df)
        if n < 4:
            return []

        atr = self._calculate_atr(df, period=14)
        min_size = atr * min_gap_atr
        start_idx = max(2, n - lookback)
        fvgs = []

        for i in range(start_idx, n):
            c1 = df.iloc[i - 2]
            c2 = df.iloc[i - 1]
            c3 = df.iloc[i]

            c1_h = float(c1["high"])
            c1_l = float(c1["low"])
            c3_h = float(c3["high"])
            c3_l = float(c3["low"])

            # 1. Bullish FVG (Yukarı Yönlü Kurumsal Dengesizlik)
            if c3_l > c1_h:
                gap_size = c3_l - c1_h
                if gap_size >= min_size:
                    fvgs.append({
                        "type": "BULLISH_FVG",
                        "top": float(c3_l),
                        "bottom": float(c1_h),
                        "size": float(gap_size),
                        "index": i - 1,
                        "datetime": c2["datetime"],
                    })

            # 2. Bearish FVG (Aşağı Yönlü Kurumsal Dengesizlik)
            elif c1_l > c3_h:
                gap_size = c1_l - c3_h
                if gap_size >= min_size:
                    fvgs.append({
                        "type": "BEARISH_FVG",
                        "top": float(c1_l),
                        "bottom": float(c3_h),
                        "size": float(gap_size),
                        "index": i - 1,
                        "datetime": c2["datetime"],
                    })

        return fvgs

    def check_fvg_confluence(
        self,
        direction: str,
        df: pd.DataFrame,
        curr_idx: int,
        target_price: float,
        fvgs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        SFP işlemi için FVG (Dengesizlik) teyidi olup olmadığını analiz eder:
        1. Displacement FVG: SFP dönüş mumu taze bir FVG bıraktı mı?
        2. Mitigation Rejection: Süpürülen tepe/dip noktası mevcut bir FVG bölgesinden mi tepti?
        """
        curr_bar = df.iloc[curr_idx]
        curr_high = float(curr_bar["high"])
        curr_low = float(curr_bar["low"])

        if direction == "SHORT":
            for f in fvgs:
                if f["type"] == "BEARISH_FVG":
                    # Taze dönüş mumu FVG bıraktıysa (Displacement)
                    if f["index"] >= curr_idx - 2:
                        return {
                            "has_confluence": True,
                            "confluence_type": "DISPLACEMENT_FVG",
                            "badge": "Ayı FVG Displacement",
                            "fvg": f,
                        }
                    # Veya süpürülen seviye Bearish FVG bölgesinden reddedildiyse
                    elif (f["bottom"] <= target_price <= f["top"]) or (f["bottom"] <= curr_high <= f["top"]):
                        return {
                            "has_confluence": True,
                            "confluence_type": "MITIGATION_REJECTION",
                            "badge": "Bearish FVG Reddi",
                            "fvg": f,
                        }

        elif direction == "LONG":
            for f in fvgs:
                if f["type"] == "BULLISH_FVG":
                    if f["index"] >= curr_idx - 2:
                        return {
                            "has_confluence": True,
                            "confluence_type": "DISPLACEMENT_FVG",
                            "badge": "Boğa FVG Displacement",
                            "fvg": f,
                        }
                    elif (f["bottom"] <= target_price <= f["top"]) or (f["bottom"] <= curr_low <= f["top"]):
                        return {
                            "has_confluence": True,
                            "confluence_type": "MITIGATION_REACTION",
                            "badge": "Bullish FVG Tepkisi",
                            "fvg": f,
                        }

        return {
            "has_confluence": False,
            "confluence_type": "NONE",
            "badge": "Standart SFP",
            "fvg": None,
        }

    def detect_sfp(self, df: pd.DataFrame, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Son bar icin SFP yapisini ve supurulen likidite havuzunu analiz eder.
        SMC Dealing Range (P/D), FVG Confluence, Mum Kapanis Anatomisi (CLV) ve 2-Bar Kurumsal Pencere teyitlidir.
        """
        if len(df) < 25:
            return None

        pools_data = self.find_pivots_and_pools(df, k=3)
        swing_highs = pools_data["swing_highs"]
        swing_lows = pools_data["swing_lows"]
        pdh = pools_data["pdh"]
        pdl = pools_data["pdl"]
        asian_high = pools_data["asian_high"]
        asian_low = pools_data["asian_low"]

        atr = self._calculate_atr(df, period=14)
        trend_info = self._detect_trend(df)
        market_trend = trend_info["trend"]
        sl_buffer = get_asset_sl_buffer(symbol)
        smc_range = self._calculate_smc_dealing_range(pools_data, df)
        equilibrium = smc_range["equilibrium"]
        fvgs = self.find_fair_value_gaps(df, lookback=30)

        n = len(df)
        curr_idx = n - 1
        curr_bar = df.iloc[curr_idx]

        curr_high = float(curr_bar["high"])
        curr_low = float(curr_bar["low"])
        curr_close = float(curr_bar["close"])
        curr_open = float(curr_bar["open"])
        curr_time = curr_bar["datetime"]
        bar_range = max(curr_high - curr_low, 1e-8)

        prev_bar = df.iloc[curr_idx - 1] if curr_idx >= 1 else None
        prev_high = float(prev_bar["high"]) if prev_bar is not None else 0.0
        prev_low = float(prev_bar["low"]) if prev_bar is not None else 0.0
        prev_close = float(prev_bar["close"]) if prev_bar is not None else 0.0
        prev_open = float(prev_bar["open"]) if prev_bar is not None else 0.0

        vol_info = self.volume_detector.analyze(df, target_index=curr_idx)

        # Aday Havuzlari Birlestir (Oncelik: PDH -> Asian High -> Recent Swings)
        high_targets = []
        if pdh:
            high_targets.append(pdh)
        if asian_high:
            high_targets.append(asian_high)
        recent_sh = [sh for sh in swing_highs if sh["index"] < curr_idx - 1 and (curr_idx - sh["index"]) <= 60]
        high_targets.extend(reversed(recent_sh))

        low_targets = []
        if pdl:
            low_targets.append(pdl)
        if asian_low:
            low_targets.append(asian_low)
        recent_sl = [sl for sl in swing_lows if sl["index"] < curr_idx - 1 and (curr_idx - sl["index"]) <= 60]
        low_targets.extend(reversed(recent_sl))

        # MODEL 2: Yalnızca izin verilen kurumsal havuzları filtrele (Saf London Judas: ASIAN_HIGH, ASIAN_LOW)
        if SFP_ALLOWED_POOLS:
            high_targets = [t for t in high_targets if t.get("pool_type") in SFP_ALLOWED_POOLS]
            low_targets = [t for t in low_targets if t.get("pool_type") in SFP_ALLOWED_POOLS]

        # 1. BEARISH SFP (Zirve Likiditesi Süpürme -> SHORT)
        for target in high_targets:
            target_price = target["price"]

            # Tek Mumlu Sweep veya 2-Mumlu Kurumsal Sweep
            is_single_bar_sweep = (curr_high > target_price and curr_close < target_price)
            is_two_bar_sweep = (
                prev_bar is not None and
                prev_high > target_price and
                curr_close < target_price and
                curr_close < prev_close and
                curr_close < curr_open
            )

            if not (is_single_bar_sweep or is_two_bar_sweep):
                continue

            # A. Mum Kapanış Anatomisi ve CLV (Rejection Displacement)
            clv = (curr_close - curr_low) / bar_range
            is_valid_rejection = (curr_close <= curr_open) or (clv <= 0.45)
            if not is_valid_rejection:
                continue

            # B. SMC Dealing Range (Premium vs Discount Filtresi)
            if smc_range["is_valid"] and curr_close < equilibrium and target["pool_type"] not in ["PDH", "ASIAN_HIGH"]:
                continue

            # C. FVG (Fair Value Gap / Dengesizlik) Confluence Analizi
            fvg_conf = self.check_fvg_confluence("SHORT", df, curr_idx, target_price, fvgs)

            # İç swing tepeleri için: Ne hacim anomalisi ne de FVG teyidi yoksa testereden kaçınmak için pas geç
            if target["pool_type"] == "SWING_HIGH" and not (vol_info["is_anomaly"] or fvg_conf["has_confluence"]):
                continue

            # Geliştirme 1: Katı HTF Pro-Trend Kuralı (Güçlü Boğa Trendinde Tepe Short VETO)
            if trend_info.get("htf_bull", False):
                continue

            # Geliştirme 4: Gerçek Yapısal Swing-Tabanlı MSS Teyidi (Sweep öncesi son 5-6 barın salınım dibi)
            preceding_low = float(df["low"].iloc[max(0, curr_idx - 6):curr_idx].min())
            if curr_close > preceding_low and not is_two_bar_sweep:
                continue

            peak_high = max(curr_high, prev_high) if is_two_bar_sweep else curr_high
            upper_wick = peak_high - max(curr_open, curr_close)
            upper_wick_ratio = upper_wick / max(peak_high - curr_low, 1e-8)

            if upper_wick_ratio >= self.min_wick_ratio:
                # Pro-Trend vs Counter-Trend
                if market_trend == "BULLISH" and target["pool_type"] == "SWING_HIGH":
                    if not (vol_info.get("tier") == "TIER_3_ULTRA" or vol_info.get("absorption_type") == "BEARISH_ABSORPTION"):
                        continue

                trend_alignment = "PRO_TREND" if market_trend == "BEARISH" else ("COUNTER_TREND" if market_trend == "BULLISH" else "NEUTRAL")

                fvg_tuple = (fvg_conf["fvg"]["top"], fvg_conf["fvg"]["bottom"]) if (fvg_conf.get("has_confluence") and fvg_conf.get("fvg")) else None
                if USE_IFVG_ENTRY:
                    ifvg_zone = detect_ifvg_short(curr_idx, df["high"].values, df["low"].values, df["close"].values, atr)
                    if ifvg_zone is not None:
                        fvg_tuple = ifvg_zone

                ce_calc = calculate_ce_entry(
                    direction="SHORT",
                    peak_or_valley=peak_high,
                    trigger_price=target_price,
                    close_price=curr_close,
                    fvg_range=fvg_tuple,
                    atr=atr,
                    sl_buffer_atr=sl_buffer,
                    entry_model=ENTRY_MODEL,
                    tp1_r=SFP_RR_TARGET_1,
                    tp2_r=SFP_RR_TARGET_2,
                )
                entry = ce_calc["entry_price"]
                stop_loss = ce_calc["stop_loss"]
                risk = ce_calc["risk_distance"]

                magnetic_tps = self._find_magnetic_targets("SHORT", entry, risk, atr, pools_data, curr_close=curr_close)
                tp1 = magnetic_tps["tp1"]
                tp2 = magnetic_tps["tp2"]
                rr_ratio = magnetic_tps["rr_ratio"]

                # Katı Hedef ve Seviye Tutarlılık Kalkanı (Sanity Filter):
                # SHORT işlemde hedefler güncel fiyattan yukarıda olamaz; giriş fiyattan kopuk olamaz!
                if tp1 >= curr_close or tp2 >= curr_close or (entry - curr_close) > atr * 1.5:
                    continue

                setup_type = "BEARISH_SFP_2BAR" if (is_two_bar_sweep and not is_single_bar_sweep) else "BEARISH_SFP"
                pool_prefix = "2-Mumlu " if is_two_bar_sweep and not is_single_bar_sweep else ""

                is_institutional = target["pool_type"] in ["PDH", "ASIAN_HIGH"]

                # Kalite Derecelendirmesi (Trend Filtresi Destekli)
                if trend_alignment == "COUNTER_TREND":
                    if vol_info.get("tier") == "TIER_3_ULTRA" and vol_info.get("absorption_type") == "BEARISH_ABSORPTION":
                        grade = "A+ (Ultra Hacim Dönüşü)"
                    else:
                        grade = "A (Karşı-Trend Filtreli)"
                elif fvg_conf["has_confluence"] and trend_alignment == "PRO_TREND" and (is_institutional or vol_info["is_anomaly"]):
                    grade = "AAA (Kurumsal Pro-Trend + FVG)"
                elif fvg_conf["has_confluence"] and (is_institutional or trend_alignment == "PRO_TREND"):
                    grade = "A+ (FVG Teyitli)"
                elif trend_alignment == "PRO_TREND" and (is_institutional or vol_info["is_anomaly"]):
                    grade = "AAA (Kurumsal Pro-Trend)"
                elif is_institutional and vol_info["is_anomaly"]:
                    grade = "AAA (Kurumsal)"
                elif trend_alignment == "PRO_TREND" or (is_institutional and vol_info["tier"] in ["TIER_2_HIGH", "TIER_3_ULTRA"]):
                    grade = "A+"
                else:
                    grade = "A"

                fvg_zone = [fvg_conf["fvg"]["top"], fvg_conf["fvg"]["bottom"]] if fvg_conf["fvg"] else None

                return {
                    "strategy": "SFP_VOLUME_ANOMALY",
                    "setup_type": setup_type,
                    "direction": "SHORT",
                    "symbol": symbol,
                    "timeframe": "15m (15 Dakikalık)",
                    "grade": grade,
                    "trend_alignment": trend_alignment,
                    "market_trend": market_trend,
                    "smc_zone": "PREMIUM",
                    "equilibrium": round_price(equilibrium),
                    "fvg_confluence": fvg_conf["has_confluence"],
                    "fvg_badge": fvg_conf["badge"],
                    "fvg_zone": fvg_zone,
                    "datetime": curr_time,
                    "entry": round_price(entry),
                    "entry_model": ce_calc["entry_model"],
                    "entry_source": ce_calc["entry_source"],
                    "is_limit": ce_calc["is_limit"],
                    "market_close_entry": round_price(curr_close),
                    "stop_loss": round_price(stop_loss),
                    "tp1": round_price(tp1),
                    "tp2": round_price(tp2),
                    "risk_pips": round_price(risk),
                    "tp1_r": magnetic_tps.get("tp1_r", SFP_RR_TARGET_1),
                    "rr_ratio": rr_ratio,
                    "tp1_note": magnetic_tps["tp1_note"],
                    "tp2_note": magnetic_tps["tp2_note"],
                    "sl_buffer_atr": round(sl_buffer, 2),
                    "swept_level": round_price(target_price),
                    "swept_level_time": target.get("datetime", curr_time),
                    "pool_type": target["pool_type"],
                    "pool_label": f"{pool_prefix}{target['pool_label']}",
                    "sweep_wick_ratio": round(upper_wick_ratio, 3),
                    "volume_analysis": vol_info,
                    "atr": round_price(atr),
                    "trigger_candle_index": curr_idx,
                }

        # 2. BULLISH SFP (Dip Likiditesi Süpürme -> LONG)
        for target in low_targets:
            target_price = target["price"]

            is_single_bar_sweep = (curr_low < target_price and curr_close > target_price)
            is_two_bar_sweep = (
                prev_bar is not None and
                prev_low < target_price and
                curr_close > target_price and
                curr_close > prev_close and
                curr_close > curr_open
            )

            if not (is_single_bar_sweep or is_two_bar_sweep):
                continue

            # A. Mum Kapanış Anatomisi ve CLV (Rejection Displacement)
            clv = (curr_close - curr_low) / bar_range
            is_valid_rejection = (curr_close >= curr_open) or (clv >= 0.55)
            if not is_valid_rejection:
                continue

            # B. SMC Dealing Range (Premium vs Discount Filtresi)
            if smc_range["is_valid"] and curr_close > equilibrium and target["pool_type"] not in ["PDL", "ASIAN_LOW"]:
                continue

            # C. FVG Confluence Analizi
            fvg_conf = self.check_fvg_confluence("LONG", df, curr_idx, target_price, fvgs)

            # İç swing dipleri için: Ne hacim anomalisi ne de FVG teyidi yoksa pas geç
            if target["pool_type"] == "SWING_LOW" and not (vol_info["is_anomaly"] or fvg_conf["has_confluence"]):
                continue

            # Geliştirme 1: Katı HTF Pro-Trend Kuralı (Güçlü Ayı Trendinde Dip Long VETO)
            if trend_info.get("htf_bear", False):
                continue

            # Geliştirme 4: Gerçek Yapısal Swing-Tabanlı MSS Teyidi (Sweep öncesi son 5-6 barın salınım tepesi)
            preceding_high = float(df["high"].iloc[max(0, curr_idx - 6):curr_idx].max())
            if curr_close < preceding_high and not is_two_bar_sweep:
                continue

            valley_low = min(curr_low, prev_low) if is_two_bar_sweep else curr_low
            lower_wick = min(curr_open, curr_close) - valley_low
            lower_wick_ratio = lower_wick / max(curr_high - valley_low, 1e-8)

            if lower_wick_ratio >= self.min_wick_ratio:
                if market_trend == "BEARISH" and target["pool_type"] == "SWING_LOW":
                    if not (vol_info.get("tier") == "TIER_3_ULTRA" or vol_info.get("absorption_type") == "BULLISH_ABSORPTION"):
                        continue

                trend_alignment = "PRO_TREND" if market_trend == "BULLISH" else ("COUNTER_TREND" if market_trend == "BEARISH" else "NEUTRAL")

                fvg_tuple = (fvg_conf["fvg"]["bottom"], fvg_conf["fvg"]["top"]) if (fvg_conf.get("has_confluence") and fvg_conf.get("fvg")) else None
                if USE_IFVG_ENTRY:
                    ifvg_zone = detect_ifvg_long(curr_idx, df["high"].values, df["low"].values, df["close"].values, atr)
                    if ifvg_zone is not None:
                        fvg_tuple = ifvg_zone

                ce_calc = calculate_ce_entry(
                    direction="LONG",
                    peak_or_valley=valley_low,
                    trigger_price=target_price,
                    close_price=curr_close,
                    fvg_range=fvg_tuple,
                    atr=atr,
                    sl_buffer_atr=sl_buffer,
                    entry_model=ENTRY_MODEL,
                    tp1_r=SFP_RR_TARGET_1,
                    tp2_r=SFP_RR_TARGET_2,
                )
                entry = ce_calc["entry_price"]
                stop_loss = ce_calc["stop_loss"]
                risk = ce_calc["risk_distance"]

                magnetic_tps = self._find_magnetic_targets("LONG", entry, risk, atr, pools_data, curr_close=curr_close)
                tp1 = magnetic_tps["tp1"]
                tp2 = magnetic_tps["tp2"]
                rr_ratio = magnetic_tps["rr_ratio"]

                # Katı Hedef ve Seviye Tutarlılık Kalkanı (Sanity Filter):
                # LONG işlemde hedefler güncel fiyattan aşağıda olamaz; giriş fiyattan kopuk olamaz!
                if tp1 <= curr_close or tp2 <= curr_close or (curr_close - entry) > atr * 1.5:
                    continue

                setup_type = "BULLISH_SFP_2BAR" if (is_two_bar_sweep and not is_single_bar_sweep) else "BULLISH_SFP"
                pool_prefix = "2-Mumlu " if is_two_bar_sweep and not is_single_bar_sweep else ""

                is_institutional = target["pool_type"] in ["PDL", "ASIAN_LOW"]

                # Kalite Derecelendirmesi (Trend Filtresi Destekli)
                if trend_alignment == "COUNTER_TREND":
                    if vol_info.get("tier") == "TIER_3_ULTRA" and vol_info.get("absorption_type") == "BULLISH_ABSORPTION":
                        grade = "A+ (Ultra Hacim Dönüşü)"
                    else:
                        grade = "A (Karşı-Trend Filtreli)"
                elif fvg_conf["has_confluence"] and trend_alignment == "PRO_TREND" and (is_institutional or vol_info["is_anomaly"]):
                    grade = "AAA (Kurumsal Pro-Trend + FVG)"
                elif fvg_conf["has_confluence"] and (is_institutional or trend_alignment == "PRO_TREND"):
                    grade = "A+ (FVG Teyitli)"
                elif trend_alignment == "PRO_TREND" and (is_institutional or vol_info["is_anomaly"]):
                    grade = "AAA (Kurumsal Pro-Trend)"
                elif is_institutional and vol_info["is_anomaly"]:
                    grade = "AAA (Kurumsal)"
                elif trend_alignment == "PRO_TREND" or (is_institutional and vol_info["tier"] in ["TIER_2_HIGH", "TIER_3_ULTRA"]):
                    grade = "A+"
                else:
                    grade = "A"

                fvg_zone = [fvg_conf["fvg"]["top"], fvg_conf["fvg"]["bottom"]] if fvg_conf["fvg"] else None

                return {
                    "strategy": "SFP_VOLUME_ANOMALY",
                    "setup_type": setup_type,
                    "direction": "LONG",
                    "symbol": symbol,
                    "timeframe": "15m (15 Dakikalık)",
                    "grade": grade,
                    "trend_alignment": trend_alignment,
                    "market_trend": market_trend,
                    "smc_zone": "DISCOUNT",
                    "equilibrium": round_price(equilibrium),
                    "fvg_confluence": fvg_conf["has_confluence"],
                    "fvg_badge": fvg_conf["badge"],
                    "fvg_zone": fvg_zone,
                    "datetime": curr_time,
                    "entry": round_price(entry),
                    "entry_model": ce_calc["entry_model"],
                    "entry_source": ce_calc["entry_source"],
                    "is_limit": ce_calc["is_limit"],
                    "market_close_entry": round_price(curr_close),
                    "stop_loss": round_price(stop_loss),
                    "tp1": round_price(tp1),
                    "tp2": round_price(tp2),
                    "risk_pips": round_price(risk),
                    "tp1_r": magnetic_tps.get("tp1_r", SFP_RR_TARGET_1),
                    "rr_ratio": rr_ratio,
                    "tp1_note": magnetic_tps["tp1_note"],
                    "tp2_note": magnetic_tps["tp2_note"],
                    "sl_buffer_atr": round(sl_buffer, 2),
                    "swept_level": round_price(target_price),
                    "swept_level_time": target.get("datetime", curr_time),
                    "pool_type": target["pool_type"],
                    "pool_label": f"{pool_prefix}{target['pool_label']}",
                    "sweep_wick_ratio": round(lower_wick_ratio, 3),
                    "volume_analysis": vol_info,
                    "atr": round_price(atr),
                    "trigger_candle_index": curr_idx,
                }

        return None
