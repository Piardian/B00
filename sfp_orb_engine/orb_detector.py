"""
🌺 Begonya 00 - ORB (Opening Range Breakout) Seans Motoru
Londra, New York ve Tokyo Acilis Araligi Kirilim & Hacim Teyidi
"""

import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, time, timezone
from .config import (
    ORB_RANGE_MINUTES,
    ORB_SESSIONS,
    ORB_MIN_BREAKOUT_VOL_RATIO,
    ORB_SL_MODE,
    SFP_RR_TARGET_1,
    SFP_RR_TARGET_2,
    round_price,
    WEEKEND_ORB_ENABLED,
)
from .volume_anomaly import VolumeAnomalyDetector


class ORBDetector:
    def __init__(
        self,
        range_minutes: int = ORB_RANGE_MINUTES,
        min_vol_ratio: float = ORB_MIN_BREAKOUT_VOL_RATIO,
        volume_detector: Optional[VolumeAnomalyDetector] = None,
    ):
        self.range_minutes = range_minutes
        self.min_vol_ratio = min_vol_ratio
        self.volume_detector = volume_detector or VolumeAnomalyDetector()

    def _parse_session_time(self, t_str: str) -> time:
        parts = t_str.split(":")
        return time(int(parts[0]), int(parts[1]))

    def detect_orb(self, df: pd.DataFrame, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Verilen veri setindeki son barlar icin aktif seansin ORB kirilimini tespit eder.
        """
        # Hafta Sonu Korumasi: Cumartesi ve Pazar gunleri kriptoda sahte kirilimlari onlemek icin ORB kesinlikle kapalidir!
        if datetime.now(timezone.utc).weekday() in [5, 6] and not WEEKEND_ORB_ENABLED:
            return None

        if len(df) < 15:
            return None

        df = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
            df["datetime"] = pd.to_datetime(df["datetime"])

        last_bar = df.iloc[-1]
        last_dt = last_bar["datetime"]
        current_time = last_dt.time()
        current_date = last_dt.date()

        # Bugunun barlarini filtrele
        today_df = df[df["datetime"].dt.date == current_date]
        if len(today_df) < 3:
            return None

        # Hangi seanstayiz?
        for session_key, session_cfg in ORB_SESSIONS.items():
            s_open = self._parse_session_time(session_cfg["open_utc"])
            s_close = self._parse_session_time(session_cfg["close_utc"])
            s_orb_end = self._parse_session_time(session_cfg["orb_window_end_utc"])

            # Eger seans suresindeysek ve ORB olusum suresi tamamlandiysa
            is_in_session = False
            if s_open <= s_close:
                is_in_session = (s_open <= current_time <= s_close)
            else:  # Geceyi asan seans
                is_in_session = (current_time >= s_open or current_time <= s_close)

            if not is_in_session:
                continue

            # ORB Penceresi barlarini topla
            if s_open <= s_orb_end:
                orb_bars = today_df[(today_df["datetime"].dt.time >= s_open) & (today_df["datetime"].dt.time <= s_orb_end)]
            else:
                orb_bars = today_df[(today_df["datetime"].dt.time >= s_open) | (today_df["datetime"].dt.time <= s_orb_end)]

            if len(orb_bars) == 0:
                continue

            orb_high = float(orb_bars["high"].max())
            orb_low = float(orb_bars["low"].min())
            orb_mid = (orb_high + orb_low) / 2.0
            orb_range = max(orb_high - orb_low, 1e-6)

            # ORB sonrasi olusan barlar (kirilim kontrolu)
            post_orb_bars = today_df[today_df["datetime"].dt.time > s_orb_end]
            if len(post_orb_bars) == 0:
                continue

            trigger_bar = post_orb_bars.iloc[-1]
            prev_bar = post_orb_bars.iloc[-2] if len(post_orb_bars) >= 2 else orb_bars.iloc[-1]

            t_close = float(trigger_bar["close"])
            t_open = float(trigger_bar["open"])
            t_high = float(trigger_bar["high"])
            t_low = float(trigger_bar["low"])
            t_range = max(t_high - t_low, 1e-8)
            t_body = abs(t_close - t_open)
            p_close = float(prev_bar["close"])

            # Hacim analizi ve EMA-20 Trend Uyumu
            vol_info = self.volume_detector.analyze(df, target_index=len(df) - 1)
            vol_ratio = vol_info["spike_ratio"]
            ema20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1]) if len(df) >= 20 else t_close

            # 1. BULLISH ORB KIRILIMI
            if t_close > orb_high and p_close <= orb_high:
                # Trend Korumasi: Fiyat EMA-20 altindaysa sahte yukari kirilimdir (fakeout tuzağı)
                if t_close < ema20:
                    continue

                upper_wick = t_high - max(t_open, t_close)
                # Anti-Fakeout Filtresi: Üst fitil %35'ten fazlaysa sahte kırılım / tepe tuzağıdır
                if (upper_wick / t_range) > 0.35:
                    continue
                # Zayıf doji gövde veya kırmızı mumla kırılım kabul edilmez
                if (t_body / t_range) < 0.40 or t_close <= t_open:
                    continue

                entry = t_close
                sl = orb_mid if ORB_SL_MODE == "MIDPOINT" else orb_low
                risk = max(entry - sl, orb_range * 0.2, entry * 0.0015)
                tp1 = entry + (risk * SFP_RR_TARGET_1)
                tp2 = entry + (risk * SFP_RR_TARGET_2)

                grade = "A+" if vol_ratio >= 1.8 else ("A" if vol_ratio >= self.min_vol_ratio else "B+")

                return {
                    "strategy": "ORB_SESSION_BREAKOUT",
                    "setup_type": "BULLISH_ORB",
                    "direction": "LONG",
                    "session_name": session_cfg["name"],
                    "symbol": symbol,
                    "timeframe": "15m (15 Dakikalık)",
                    "grade": grade,
                    "datetime": trigger_bar["datetime"],
                    "entry": round_price(entry),
                    "stop_loss": round_price(sl),
                    "tp1": round_price(tp1),
                    "tp2": round_price(tp2),
                    "tp1_r": SFP_RR_TARGET_1,
                    "risk_pips": round_price(risk),
                    "rr_ratio": SFP_RR_TARGET_2,
                    "tp1_note": f"Standart {SFP_RR_TARGET_1}R",
                    "tp2_note": f"Standart {SFP_RR_TARGET_2}R",
                    "orb_high": round_price(orb_high),
                    "orb_low": round_price(orb_low),
                    "orb_range": round_price(orb_range),
                    "volume_analysis": vol_info,
                    "trigger_candle_index": len(df) - 1,
                }

            # 2. BEARISH ORB KIRILIMI
            if t_close < orb_low and p_close >= orb_low:
                # Trend Korumasi: Fiyat EMA-20 ustundeyse sahte asagi kirilimdir (fakeout tuzağı)
                if t_close > ema20:
                    continue

                lower_wick = min(t_open, t_close) - t_low
                # Anti-Fakeout Filtresi: Alt fitil %35'ten fazlaysa dip tuzağıdır
                if (lower_wick / t_range) > 0.35:
                    continue
                if (t_body / t_range) < 0.40 or t_close >= t_open:
                    continue

                entry = t_close
                sl = orb_mid if ORB_SL_MODE == "MIDPOINT" else orb_high
                risk = max(sl - entry, orb_range * 0.2, entry * 0.0015)
                tp1 = entry - (risk * SFP_RR_TARGET_1)
                tp2 = entry - (risk * SFP_RR_TARGET_2)

                grade = "A+" if vol_ratio >= 1.8 else ("A" if vol_ratio >= self.min_vol_ratio else "B+")

                return {
                    "strategy": "ORB_SESSION_BREAKOUT",
                    "setup_type": "BEARISH_ORB",
                    "direction": "SHORT",
                    "session_name": session_cfg["name"],
                    "symbol": symbol,
                    "timeframe": "15m (15 Dakikalık)",
                    "grade": grade,
                    "datetime": trigger_bar["datetime"],
                    "entry": round_price(entry),
                    "stop_loss": round_price(sl),
                    "tp1": round_price(tp1),
                    "tp2": round_price(tp2),
                    "tp1_r": SFP_RR_TARGET_1,
                    "risk_pips": round_price(risk),
                    "rr_ratio": SFP_RR_TARGET_2,
                    "tp1_note": f"Standart {SFP_RR_TARGET_1}R",
                    "tp2_note": f"Standart {SFP_RR_TARGET_2}R",
                    "orb_high": round_price(orb_high),
                    "orb_low": round_price(orb_low),
                    "orb_range": round_price(orb_range),
                    "volume_analysis": vol_info,
                    "trigger_candle_index": len(df) - 1,
                }

        return None
