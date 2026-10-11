"""
🌺 Begonya 00 - Multi-Timeframe (4H, 1H, 15M) Trend + P/D Test Script
Kullanıcı Talebi:
- Düzeltme 1 (Aynı gün tekrar giriş yasağı) kaldırıldı!
- Makro kapıdan geçtikten sonra:
  * Makro LONG ise:
    - 4H Trend LONG ve 4H DISCOUNT
    - 1H Trend LONG ve 1H DISCOUNT
    - 15M Trend/Sinyal LONG ve 15M DISCOUNT
    -> İşlem al!
  * Makro SHORT ise:
    - 4H Trend SHORT ve 4H PREMIUM
    - 1H Trend SHORT ve 1H PREMIUM
    - 15M Trend/Sinyal SHORT ve 15M PREMIUM
    -> İşlem al!
"""

import sys
import json
import logging
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .config import get_asset_sl_buffer, is_crypto
from .macro_gated_3m_backtest import DailyMacroGateTable

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("Begonya00.TestMTFPD")

TARGET_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"
]


class MTFPDRunner:
    def __init__(self, start_dt: datetime, end_dt: datetime, initial_capital: float = 10000.0, risk_pct: float = 0.02, strict_15m_ema: bool = False):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.strict_15m_ema = strict_15m_ema
        self.utc_from = start_dt
        self.utc_to = end_dt
        self.macro_table = DailyMacroGateTable(self.utc_from.date(), self.utc_to.date())

    def fetch_m15_data(self, symbol: str) -> Optional[pd.DataFrame]:
        if not mt5.initialize():
            logger.error("MT5 başlatılamadı!")
            return None

        warmup_from = self.utc_from - timedelta(days=35)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, warmup_from, self.utc_to)
        if rates is None or len(rates) < 1000:
            return None

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["date"] = df["datetime"].dt.date
        df["weekday"] = df["datetime"].dt.weekday
        df["hour"] = df["datetime"].dt.hour
        df["minute"] = df["datetime"].dt.minute

        # Günlük Seviyeler (PDH & PDL)
        daily = df.groupby("date").agg({"high": "max", "low": "min"}).shift(1)
        df["pdh"] = df["date"].map(daily["high"]).fillna(0.0)
        df["pdl"] = df["date"].map(daily["low"]).fillna(0.0)

        # Asya Seansı Seviyeleri (00:00 - 06:00 UTC)
        asian_bars = df[df["hour"] < 6]
        ash_map = asian_bars.groupby("date")["high"].max()
        asl_map = asian_bars.groupby("date")["low"].min()
        df["ash"] = df["date"].map(ash_map).fillna(0.0)
        df["asl"] = df["date"].map(asl_map).fillna(0.0)

        # ATR (14)
        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                np.abs(df["high"] - df["close"].shift(1)),
                np.abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = tr.rolling(14).mean().fillna(df["high"] - df["low"])

        # =========================================================
        # 1. 4H TREND & P/D (Dealing Range)
        # 4H = 16 bar M15. Son 5 gün = 480 bar
        # =========================================================
        df["ema50_4h"] = df["close"].ewm(span=200, adjust=False).mean()
        df["ema200_4h"] = df["close"].ewm(span=800, adjust=False).mean()
        df["trend_4h_bull"] = df["ema50_4h"] > df["ema200_4h"]
        df["trend_4h_bear"] = df["ema50_4h"] < df["ema200_4h"]

        df["high_4h"] = df["high"].rolling(480).max()
        df["low_4h"] = df["low"].rolling(480).min()
        df["eq_4h"] = (df["high_4h"] + df["low_4h"]) / 2.0
        df["pd_4h_discount"] = df["close"] < df["eq_4h"]
        df["pd_4h_premium"] = df["close"] > df["eq_4h"]

        # =========================================================
        # 2. 1H TREND & P/D (Dealing Range)
        # 1H = 4 bar M15. Son 24 saat = 96 bar
        # =========================================================
        df["ema20_1h"] = df["close"].ewm(span=80, adjust=False).mean()
        df["ema50_1h"] = df["close"].ewm(span=200, adjust=False).mean()
        df["trend_1h_bull"] = df["ema20_1h"] > df["ema50_1h"]
        df["trend_1h_bear"] = df["ema20_1h"] < df["ema50_1h"]

        df["high_1h"] = df["high"].rolling(96).max()
        df["low_1h"] = df["low"].rolling(96).min()
        df["eq_1h"] = (df["high_1h"] + df["low_1h"]) / 2.0
        df["pd_1h_discount"] = df["close"] < df["eq_1h"]
        df["pd_1h_premium"] = df["close"] > df["eq_1h"]

        # =========================================================
        # 3. 15M TREND & P/D (Dealing Range)
        # 15M = 1 bar. Son 32 bar (8 saat seans döngüsü)
        # =========================================================
        df["ema20_15m"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50_15m"] = df["close"].ewm(span=50, adjust=False).mean()
        df["trend_15m_bull"] = df["ema20_15m"] > df["ema50_15m"]
        df["trend_15m_bear"] = df["ema20_15m"] < df["ema50_15m"]

        df["high_15m"] = df["high"].rolling(32).max()
        df["low_15m"] = df["low"].rolling(32).min()
        df["eq_15m"] = (df["high_15m"] + df["low_15m"]) / 2.0
        df["pd_15m_discount"] = df["close"] < df["eq_15m"]
        df["pd_15m_premium"] = df["close"] > df["eq_15m"]

        return df

    def run_simulation(self, symbol: str, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        display_sym = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 and symbol.isalpha() else symbol
        sl_buffer_atr = get_asset_sl_buffer(display_sym)
        is_crypto_sym = is_crypto(symbol)

        n = len(df)
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        pdhs = df["pdh"].values
        pdls = df["pdl"].values
        ashs = df["ash"].values
        asls = df["asl"].values
        atrs = df["atr"].values

        # 4H
        t4_bulls = df["trend_4h_bull"].values
        t4_bears = df["trend_4h_bear"].values
        p4_discs = df["pd_4h_discount"].values
        p4_prems = df["pd_4h_premium"].values

        # 1H
        t1_bulls = df["trend_1h_bull"].values
        t1_bears = df["trend_1h_bear"].values
        p1_discs = df["pd_1h_discount"].values
        p1_prems = df["pd_1h_premium"].values

        # 15M
        t15_bulls = df["trend_15m_bull"].values
        t15_bears = df["trend_15m_bear"].values
        p15_discs = df["pd_15m_discount"].values
        p15_prems = df["pd_15m_premium"].values

        weekdays = df["weekday"].values
        hours = df["hour"].values
        dts = df["datetime"].dt.strftime("%Y-%m-%d %H:%M").values
        dates_only = df["date"].values
        dt_objs = df["datetime"].dt.to_pydatetime()
        dates_raw = df["datetime"].values

        trades = []
        active_position = None
        cooldown_until = 0

        # DÜZELTME 1 KALDIRILDI: stopped_out_dates yok!
        gate_stats = {
            "VETO_MACRO_RANGE": 0,
            "VETO_DIRECTION_MISMATCH": 0,
            "VETO_MTF_PD_MISMATCH": 0,
            "APPROVED": 0
        }

        start_ts = pd.Timestamp(self.utc_from.replace(tzinfo=None))

        for i in range(100, n):
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]
            c_atr = atrs[i]
            wday = weekdays[i]
            h_val = hours[i]
            bar_rng = max(c_high - c_low, 1e-8)

            # --- MEVCUT POZİSYON KONTROLÜ (BAR İÇİ TAKİP) ---
            if active_position is not None:
                p = active_position
                entry = p["entry"]
                sl = p["current_sl"]
                tp1 = p["tp1"]
                tp2 = p["tp2"]
                status = p["status"]
                p_dir = p["direction"]
                p["bars_held"] += 1

                closed = False
                close_reason = ""
                r_res = 0.0

                if p_dir == "LONG":
                    if c_high >= tp1 and status == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry

                    if c_high >= tp2:
                        closed = True
                        close_reason = "TP2_HIT"
                        r_res = (1.0 * 0.5) + (2.0 * 0.5)
                    elif c_low <= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.0 * 0.5) + (0.0 * 0.5)
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                    elif p["bars_held"] >= 192:
                        closed = True
                        close_reason = "TIME_EXIT"
                        r_res = (c_close - entry) / max(entry - p["original_sl"], 1e-8)

                elif p_dir == "SHORT":
                    if c_low <= tp1 and status == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry

                    if c_low <= tp2:
                        closed = True
                        close_reason = "TP2_HIT"
                        r_res = (1.0 * 0.5) + (2.0 * 0.5)
                    elif c_high >= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.0 * 0.5) + (0.0 * 0.5)
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                    elif p["bars_held"] >= 192:
                        closed = True
                        close_reason = "TIME_EXIT"
                        r_res = (entry - c_close) / max(p["original_sl"] - entry, 1e-8)

                if closed:
                    p["closed_at"] = dts[i]
                    p["exit_price"] = c_close
                    p["close_reason"] = close_reason
                    p["r_result"] = round(float(r_res), 2)
                    trades.append(p)
                    active_position = None
                    cooldown_until = i + 3
                continue

            bar_raw = pd.Timestamp(dates_raw[i]).tz_localize(None)
            if bar_raw < start_ts or i < cooldown_until:
                continue

            is_weekend = wday in [5, 6]
            if is_weekend:
                if not is_crypto_sym:
                    continue
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
            else:
                sfp_session_active = (13 <= h_val <= 17)

            if not sfp_session_active:
                continue

            pdh = pdhs[i]
            pdl = pdls[i]
            ash = ashs[i]
            asl = asls[i]
            if pdh == 0.0 or pdl == 0.0:
                continue

            upper_wick = (c_high - max(c_open, c_close)) / bar_rng
            lower_wick = (min(c_open, c_close) - c_low) / bar_rng

            sfp_sig = None
            sweep_high = False
            pool_name = ""
            if upper_wick >= 0.45:
                if c_high > pdh and c_close < pdh:
                    sweep_high = True
                    pool_name = "PDH"
                elif ash > 0.0 and c_high > ash and c_close < ash:
                    sweep_high = True
                    pool_name = "ASIAN_HIGH"

            sweep_low = False
            if lower_wick >= 0.45:
                if c_low < pdl and c_close > pdl:
                    sweep_low = True
                    pool_name = "PDL"
                elif asl > 0.0 and c_low < asl and c_close > asl:
                    sweep_low = True
                    pool_name = "ASIAN_LOW"

            # SHORT SFP (High sweep)
            if sweep_high:
                peak = c_high
                mss_trigger = min(c_low, lows[i-1])
                mss_ok = False
                entry_idx = -1

                for k in range(1, 4):
                    if i + k < n and closes[i+k] < mss_trigger:
                        b_rng = max(highs[i+k] - lows[i+k], 1e-8)
                        body_r = abs(closes[i+k] - opens[i+k]) / b_rng
                        if body_r >= 0.35:
                            mss_ok = True
                            entry_idx = i + k
                            break

                if mss_ok:
                    has_fvg = (lows[entry_idx - 2] > highs[entry_idx]) and ((lows[entry_idx - 2] - highs[entry_idx]) >= c_atr * 0.10)
                    sfp_sig = {
                        "strategy": "SFP",
                        "direction": "SHORT",
                        "grade": "AAA" if has_fvg else "A+",
                        "entry": closes[entry_idx],
                        "sl": peak + (c_atr * sl_buffer_atr),
                        "pool": pool_name,
                        "trigger_time": dts[entry_idx],
                        "trigger_dt": dt_objs[entry_idx],
                        "check_idx": entry_idx
                    }

            # LONG SFP (Low sweep)
            elif sweep_low:
                trough = c_low
                mss_trigger = max(c_high, highs[i-1])
                mss_ok = False
                entry_idx = -1

                for k in range(1, 4):
                    if i + k < n and closes[i+k] > mss_trigger:
                        b_rng = max(highs[i+k] - lows[i+k], 1e-8)
                        body_r = abs(closes[i+k] - opens[i+k]) / b_rng
                        if body_r >= 0.35:
                            mss_ok = True
                            entry_idx = i + k
                            break

                if mss_ok:
                    has_fvg = (highs[entry_idx - 2] < lows[entry_idx]) and ((lows[entry_idx] - highs[entry_idx - 2]) >= c_atr * 0.10)
                    sfp_sig = {
                        "strategy": "SFP",
                        "direction": "LONG",
                        "grade": "AAA" if has_fvg else "A+",
                        "entry": closes[entry_idx],
                        "sl": trough - (c_atr * sl_buffer_atr),
                        "pool": pool_name,
                        "trigger_time": dts[entry_idx],
                        "trigger_dt": dt_objs[entry_idx],
                        "check_idx": entry_idx
                    }

            if sfp_sig is not None:
                sig_dt = sfp_sig["trigger_dt"]
                direction = sfp_sig["direction"]
                idx_check = sfp_sig["check_idx"]

                # 1. MAKRO KAPISI KONTROLÜ
                macro_gate = self.macro_table.get_gate(sig_dt, symbol)
                if macro_gate in ["NEUTRAL_RANGE", "NO_TRADE", "DEFENSIVE_HOLD", "VETO"]:
                    gate_stats["VETO_MACRO_RANGE"] += 1
                    continue

                if direction == "LONG" and macro_gate != "LONG_ONLY":
                    gate_stats["VETO_DIRECTION_MISMATCH"] += 1
                    continue

                if direction == "SHORT" and macro_gate != "SHORT_ONLY":
                    gate_stats["VETO_DIRECTION_MISMATCH"] += 1
                    continue

                # 2. MULTI-TIMEFRAME TREND & P/D (PREMIUM / DISCOUNT) KONTROLÜ
                # Kullanıcı Kuralı:
                # Makro Long ise: 4H Long & Discount, 1H Long & Discount, 15M Long & Discount
                # Makro Short ise: 4H Short & Premium, 1H Short & Premium, 15M Short & Premium
                if direction == "LONG":
                    c_4h = t4_bulls[idx_check] and p4_discs[idx_check]
                    c_1h = t1_bulls[idx_check] and p1_discs[idx_check]
                    c_15m = p15_discs[idx_check] and (t15_bulls[idx_check] if self.strict_15m_ema else True)
                    if not (c_4h and c_1h and c_15m):
                        gate_stats["VETO_MTF_PD_MISMATCH"] += 1
                        continue

                elif direction == "SHORT":
                    c_4h = t4_bears[idx_check] and p4_prems[idx_check]
                    c_1h = t1_bears[idx_check] and p1_prems[idx_check]
                    c_15m = p15_prems[idx_check] and (t15_bears[idx_check] if self.strict_15m_ema else True)
                    if not (c_4h and c_1h and c_15m):
                        gate_stats["VETO_MTF_PD_MISMATCH"] += 1
                        continue

                gate_stats["APPROVED"] += 1

                entry_p = sfp_sig["entry"]
                sl_p = sfp_sig["sl"]
                risk_dist = abs(entry_p - sl_p)
                if risk_dist <= 1e-8:
                    continue

                if direction == "LONG":
                    tp1_p = entry_p + (risk_dist * 1.0)
                    tp2_p = entry_p + (risk_dist * 2.0)
                else:
                    tp1_p = entry_p - (risk_dist * 1.0)
                    tp2_p = entry_p - (risk_dist * 2.0)

                active_position = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry": entry_p,
                    "original_sl": sl_p,
                    "current_sl": sl_p,
                    "tp1": tp1_p,
                    "tp2": tp2_p,
                    "risk_dist": risk_dist,
                    "opened_at": sfp_sig["trigger_time"],
                    "closed_at": None,
                    "close_reason": None,
                    "r_result": 0.0,
                    "status": "OPEN",
                    "bars_held": 0,
                    "pool": sfp_sig["pool"],
                    "macro_gate": macro_gate,
                    "is_weekend": bool(is_weekend),
                }

        return trades, gate_stats


def run_test_period(period_name: str, start_dt: datetime, end_dt: datetime, strict_15m: bool = False) -> Dict[str, Any]:
    runner = MTFPDRunner(start_dt, end_dt, strict_15m_ema=strict_15m)
    logger.info(f"\n=======================================================")
    logger.info(f"🚀 {period_name} ({start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}) MTF P/D TESTİ...")
    logger.info(f"=======================================================")

    all_trades = []
    veto_totals = {"VETO_MACRO_RANGE": 0, "VETO_DIRECTION_MISMATCH": 0, "VETO_MTF_PD_MISMATCH": 0, "APPROVED": 0}

    for sym in TARGET_SYMBOLS:
        df = runner.fetch_m15_data(sym)
        if df is not None:
            t_l, v_s = runner.run_simulation(sym, df)
            all_trades.extend(t_l)
            for k in veto_totals:
                veto_totals[k] += v_s.get(k, 0)

    all_trades.sort(key=lambda x: x["opened_at"])

    if not all_trades:
        return {
            "period": period_name, "trades": 0, "win_rate": 0.0, "net_r": 0.0,
            "dollar": 0.0, "tp2": 0, "be": 0, "sl": 0, "vetos": veto_totals, "trades_list": []
        }

    tp2_cnt = sum(1 for t in all_trades if t["close_reason"] == "TP2_HIT")
    be_cnt = sum(1 for t in all_trades if t["close_reason"] == "BREAK_EVEN")
    sl_cnt = sum(1 for t in all_trades if t["close_reason"] == "STOP_LOSS")
    net_r = sum(t["r_result"] for t in all_trades)
    win_rate = (tp2_cnt + be_cnt) / len(all_trades) * 100
    dollar = net_r * 200.0

    return {
        "period": period_name,
        "trades": len(all_trades),
        "win_rate": round(win_rate, 1),
        "tp2": tp2_cnt,
        "be": be_cnt,
        "sl": sl_cnt,
        "net_r": round(net_r, 2),
        "dollar": round(dollar, 2),
        "vetos": veto_totals,
        "trades_list": all_trades
    }


def main():
    # 2026 YTD ve 2025 Testleri
    print("Test başlatılıyor...")

if __name__ == "__main__":
    main()
