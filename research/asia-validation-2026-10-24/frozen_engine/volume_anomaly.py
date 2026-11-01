"""
🌺 Begonya 00 - Hacim & Volatilite Anomalisi Tespit Modulu
Rolling Z-Score, ATR Normalizasyonu, Hacim Patlamasi (Spike) ve Emilim (Absorption)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from .config import (
    VOLUME_ROLLING_WINDOW,
    VOLUME_TIER1_RATIO,
    VOLUME_TIER2_RATIO,
    VOLUME_TIER3_RATIO,
    VOLUME_ZSCORE_MIN,
)


class VolumeAnomalyDetector:
    def __init__(
        self,
        window: int = VOLUME_ROLLING_WINDOW,
        tier1_ratio: float = VOLUME_TIER1_RATIO,
        tier2_ratio: float = VOLUME_TIER2_RATIO,
        tier3_ratio: float = VOLUME_TIER3_RATIO,
        zscore_min: float = VOLUME_ZSCORE_MIN,
    ):
        self.window = window
        self.tier1_ratio = tier1_ratio
        self.tier2_ratio = tier2_ratio
        self.tier3_ratio = tier3_ratio
        self.zscore_min = zscore_min

    def analyze(self, df: pd.DataFrame, target_index: int = -1) -> Dict[str, Any]:
        """
        Verilen DataFrame'in hedef mumu icin hacim ve volatilite anomalisi metriklerini hesaplar.
        """
        if len(df) < self.window + 1:
            return {
                "is_anomaly": False,
                "tier": "INSUFFICIENT_DATA",
                "spike_ratio": 1.0,
                "z_score": 0.0,
                "atr_expansion_ratio": 1.0,
                "mean_volume": 0.0,
                "candle_volume": 0.0,
                "upper_wick_ratio": 0.0,
                "lower_wick_ratio": 0.0,
                "absorption_type": "NONE",
            }

        if target_index < 0:
            target_idx = len(df) + target_index
        else:
            target_idx = target_index

        start_idx = max(0, target_idx - self.window)
        baseline_slice = df.iloc[start_idx:target_idx]
        baseline_volumes = baseline_slice["volume"].replace(0, np.nan).dropna()

        if len(baseline_volumes) < 5:
            mean_vol = 1.0
            std_vol = 1.0
        else:
            mean_vol = float(baseline_volumes.mean())
            std_vol = float(baseline_volumes.std()) if float(baseline_volumes.std()) > 0 else 1.0

        # ATR / Range Temelli Volatilite Analizi
        baseline_ranges = (baseline_slice["high"] - baseline_slice["low"]).clip(lower=1e-6)
        mean_range = float(baseline_ranges.mean()) if len(baseline_ranges) > 0 else 1e-4

        target_row = df.iloc[target_idx]
        target_vol = float(target_row["volume"])
        target_high = float(target_row["high"])
        target_low = float(target_row["low"])
        target_open = float(target_row["open"])
        target_close = float(target_row["close"])

        target_range = max(target_high - target_low, 1e-8)
        atr_expansion = round(target_range / mean_range, 2) if mean_range > 0 else 1.0

        spike_ratio = round(target_vol / mean_vol, 2) if mean_vol > 0 else 1.0
        z_score = round((target_vol - mean_vol) / std_vol, 2) if std_vol > 0 else 0.0

        # Mum anatomisi (Fitil ve Govde Analizi)
        body_top = max(target_open, target_close)
        body_bottom = min(target_open, target_close)

        upper_wick_ratio = round((target_high - body_top) / target_range, 3)
        lower_wick_ratio = round((body_bottom - target_low) / target_range, 3)

        # Anomali Seviyesi (Hacim veya ATR Volatilite Genislemesi Bilesimi)
        tier = "NORMAL"
        is_anomaly = False

        if (spike_ratio >= self.tier3_ratio or z_score >= 3.0) or (spike_ratio >= 1.8 and atr_expansion >= 2.0):
            tier = "TIER_3_ULTRA"
            is_anomaly = True
        elif (spike_ratio >= self.tier2_ratio or z_score >= self.zscore_min) or (atr_expansion >= 1.8):
            tier = "TIER_2_HIGH"
            is_anomaly = True
        elif spike_ratio >= self.tier1_ratio or atr_expansion >= 1.4:
            tier = "TIER_1_MODERATE"
            is_anomaly = True

        # Kurumsal Emilim (Absorption) Tespiti
        # Yuksek hacimli/genis mumda belirgin tek tarafli fitil
        absorption_type = "NONE"
        if is_anomaly:
            if upper_wick_ratio >= 0.35 and upper_wick_ratio > lower_wick_ratio * 1.4:
                absorption_type = "BEARISH_ABSORPTION"
            elif lower_wick_ratio >= 0.35 and lower_wick_ratio > upper_wick_ratio * 1.4:
                absorption_type = "BULLISH_ABSORPTION"

        return {
            "is_anomaly": is_anomaly,
            "tier": tier,
            "spike_ratio": spike_ratio,
            "z_score": z_score,
            "atr_expansion_ratio": atr_expansion,
            "mean_volume": round(mean_vol, 1),
            "candle_volume": round(target_vol, 1),
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "absorption_type": absorption_type,
        }
