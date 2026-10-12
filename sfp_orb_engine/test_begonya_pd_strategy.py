"""
🌺 Begonya 00 - Multi-Timeframe P/D (Begonya Usulü) + Makro Motor Test Scripti
Kullanıcı Talebi:
1. Düzeltme 1 (Aynı gün tekrar giriş yasağı) KALDIRILDI.
2. 4H katı trend uyumu yerine Begonya'daki gibi Multi-Timeframe P/D & Trend entegrasyonu:
   - Makro Kapısı Onayı (Range = 0 işlem, Yön Onayı Şart)
   - Makro LONG ise:
     * 4H: Long Trend ve 4H Discount bölgesinde
     * 1H: Long Trend ve 1H Discount bölgesinde
     * 15M: Long Trend/Sinyal ve 15M Discount bölgesinde
     -> O zaman LONG işlem al!
   - Makro SHORT ise:
     * 4H: Short Trend ve 4H Premium bölgesinde
     * 1H: Short Trend ve 1H Premium bölgesinde
     * 15M: Short Trend/Sinyal ve 15M Premium bölgesinde
     -> O zaman SHORT işlem al!
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

from .config import (
    get_asset_sl_buffer,
    is_crypto,
    ENTRY_MODEL,
    REQUIRE_ENTRY_REACTION,
)
from .entry_mechanics import calculate_ce_entry, is_slice_through_candle
from .macro_gated_3m_backtest import DailyMacroGateTable

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("Begonya00.BegonyaPD")

TARGET_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"
]


class BegonyaPDRunner:
    def __init__(
        self,
        start_dt: datetime,
        end_dt: datetime,
        initial_capital: float = 10000.0,
        risk_pct: float = 0.02,
        entry_model: str = ENTRY_MODEL,
        require_reaction: bool = REQUIRE_ENTRY_REACTION,
    ):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.entry_model = (entry_model or "midpoint").lower()
        self.require_reaction = require_reaction
        self.utc_from = start_dt
        self.utc_to = end_dt
        self.macro_table = DailyMacroGateTable(self.utc_from.date(), self.utc_to.date())

    def fetch_data_and_compute_pd(self, symbol: str) -> Optional[pd.DataFrame]:
        if not mt5.initialize():
            return None

        warmup_from = self.utc_from - timedelta(days=40)
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

        # PDH & PDL
        daily = df.groupby("date").agg({"high": "max", "low": "min"}).shift(1)
        df["pdh"] = df["date"].map(daily["high"]).fillna(0.0)
        df["pdl"] = df["date"].map(daily["low"]).fillna(0.0)

        # Asian High / Low
        asian_bars = df[df["hour"] < 6]
        df["ash"] = df["date"].map(asian_bars.groupby("date")["high"].max()).fillna(0.0)
        df["asl"] = df["date"].map(asian_bars.groupby("date")["low"].min()).fillna(0.0)

        # ATR 14
        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                np.abs(df["high"] - df["close"].shift(1)),
                np.abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = tr.rolling(14).mean().fillna(df["high"] - df["low"])

        # -------------------------------------------------------------
        # 1. 15M TREND & DEALING RANGE (P/D) - Begonya Usulü
        # -------------------------------------------------------------
        df["ema20_15m"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50_15m"] = df["close"].ewm(span=50, adjust=False).mean()
        df["trend_15m_long"] = df["ema20_15m"] > df["ema50_15m"]
        df["trend_15m_short"] = df["ema20_15m"] < df["ema50_15m"]

        # Begonya usulü son swingler ve günlük aralık bazlı equilibrium
        # Son 32 bar (8 saat) en yüksek ve en düşük
        df["high_15m"] = df["high"].rolling(32).max()
        df["low_15m"] = df["low"].rolling(32).min()
        df["eq_15m"] = (df["high_15m"] + df["low_15m"]) / 2.0
        df["disc_15m"] = df["close"] < df["eq_15m"]
        df["prem_15m"] = df["close"] > df["eq_15m"]

        # -------------------------------------------------------------
        # 2. 1H TREND & DEALING RANGE (P/D)
        # -------------------------------------------------------------
        df["ema20_1h"] = df["close"].ewm(span=80, adjust=False).mean()   # 20 * 4
        df["ema50_1h"] = df["close"].ewm(span=200, adjust=False).mean()  # 50 * 4
        df["trend_1h_long"] = df["ema20_1h"] > df["ema50_1h"]
        df["trend_1h_short"] = df["ema20_1h"] < df["ema50_1h"]

        # Son 96 bar (24 saat) dealing range
        df["high_1h"] = df["high"].rolling(96).max()
        df["low_1h"] = df["low"].rolling(96).min()
        df["eq_1h"] = (df["high_1h"] + df["low_1h"]) / 2.0
        df["disc_1h"] = df["close"] < df["eq_1h"]
        df["prem_1h"] = df["close"] > df["eq_1h"]

        # -------------------------------------------------------------
        # 3. 4H TREND & DEALING RANGE (P/D)
        # -------------------------------------------------------------
        df["ema50_4h"] = df["close"].ewm(span=200, adjust=False).mean()
        df["ema200_4h"] = df["close"].ewm(span=800, adjust=False).mean()
        df["trend_4h_long"] = df["ema50_4h"] > df["ema200_4h"]
        df["trend_4h_short"] = df["ema50_4h"] < df["ema200_4h"]

        # Son 192 bar (48 saat / 2 gün) 4H dealing range
        df["high_4h"] = df["high"].rolling(192).max()
        df["low_4h"] = df["low"].rolling(192).min()
        df["eq_4h"] = (df["high_4h"] + df["low_4h"]) / 2.0
        df["disc_4h"] = df["close"] < df["eq_4h"]
        df["prem_4h"] = df["close"] > df["eq_4h"]

        return df

    def run_simulation(self, symbol: str, df: pd.DataFrame, require_15m_ema_trend: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
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

        t4_long = df["trend_4h_long"].values
        t4_short = df["trend_4h_short"].values
        p4_disc = df["disc_4h"].values
        p4_prem = df["prem_4h"].values

        t1_long = df["trend_1h_long"].values
        t1_short = df["trend_1h_short"].values
        p1_disc = df["disc_1h"].values
        p1_prem = df["prem_1h"].values

        t15_long = df["trend_15m_long"].values
        t15_short = df["trend_15m_short"].values
        p15_disc = df["disc_15m"].values
        p15_prem = df["prem_15m"].values

        weekdays = df["weekday"].values
        hours = df["hour"].values
        dts = df["datetime"].dt.strftime("%Y-%m-%d %H:%M").values
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

            # Pozisyon Takibi
            if active_position is not None:
                p = active_position
                entry = p["entry"]
                sl = p["current_sl"]
                tp1 = p["tp1"]
                tp2 = p["tp2"]
                status = p["status"]
                p_dir = p["direction"]

                if status == "PENDING_LIMIT":
                    p["bars_waiting"] = p.get("bars_waiting", 0) + 1
                    if p["bars_waiting"] >= p.get("max_wait_bars", 32):
                        active_position = None
                        continue

                    is_long = (p_dir == "LONG")
                    stop_hit_before = (c_low <= sl) if is_long else (c_high >= sl)
                    reached_entry = (c_low <= entry and c_open >= sl) if is_long else (c_high >= entry and c_open <= sl)

                    if stop_hit_before and not reached_entry:
                        active_position = None
                        continue

                    if reached_entry:
                        if self.require_reaction:
                            z_low = p.get("zone_low", min(entry, sl))
                            z_high = p.get("zone_high", max(entry, sl))
                            if is_slice_through_candle(p_dir, c_open, c_high, c_low, c_close, z_low, z_high):
                                active_position = None
                                continue

                        p["status"] = "OPEN"
                        status = "OPEN"
                    else:
                        continue

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
                    fvg_low = highs[entry_idx] if has_fvg else None
                    fvg_high = lows[entry_idx - 2] if has_fvg else None
                    calc = calculate_ce_entry(
                        direction="SHORT",
                        curr_close=closes[entry_idx],
                        sweep_extreme=peak,
                        mss_trigger=mss_trigger,
                        atr=c_atr,
                        sl_buffer_atr=sl_buffer_atr,
                        has_fvg=has_fvg,
                        fvg_top=fvg_high,
                        fvg_bottom=fvg_low,
                        entry_model=self.entry_model,
                    )
                    sfp_sig = {
                        "strategy": "SFP",
                        "direction": "SHORT",
                        "grade": "AAA" if has_fvg else "A+",
                        "entry": calc["entry_price"],
                        "sl": calc["stop_loss"],
                        "tp1": calc["tp1"],
                        "tp2": calc["tp2"],
                        "risk_dist": calc["risk_dist"],
                        "is_limit": calc["is_limit"],
                        "zone_low": calc["zone_low"],
                        "zone_high": calc["zone_high"],
                        "pool": pool_name,
                        "trigger_time": dts[entry_idx],
                        "trigger_dt": dt_objs[entry_idx],
                        "check_idx": entry_idx
                    }

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
                    fvg_low = highs[entry_idx - 2] if has_fvg else None
                    fvg_high = lows[entry_idx] if has_fvg else None
                    calc = calculate_ce_entry(
                        direction="LONG",
                        curr_close=closes[entry_idx],
                        sweep_extreme=trough,
                        mss_trigger=mss_trigger,
                        atr=c_atr,
                        sl_buffer_atr=sl_buffer_atr,
                        has_fvg=has_fvg,
                        fvg_top=fvg_high,
                        fvg_bottom=fvg_low,
                        entry_model=self.entry_model,
                    )
                    sfp_sig = {
                        "strategy": "SFP",
                        "direction": "LONG",
                        "grade": "AAA" if has_fvg else "A+",
                        "entry": calc["entry_price"],
                        "sl": calc["stop_loss"],
                        "tp1": calc["tp1"],
                        "tp2": calc["tp2"],
                        "risk_dist": calc["risk_dist"],
                        "is_limit": calc["is_limit"],
                        "zone_low": calc["zone_low"],
                        "zone_high": calc["zone_high"],
                        "pool": pool_name,
                        "trigger_time": dts[entry_idx],
                        "trigger_dt": dt_objs[entry_idx],
                        "check_idx": entry_idx
                    }

            if sfp_sig is not None:
                sig_dt = sfp_sig["trigger_dt"]
                direction = sfp_sig["direction"]
                idx_k = sfp_sig["check_idx"]

                # 1. MAKRO KAPISI
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

                # 2. BEGONYA MULTI-TIMEFRAME TREND & P/D ŞARTI
                # Makro LONG: 4H Long & Discount, 1H Long & Discount, 15M Long & Discount
                # Makro SHORT: 4H Short & Premium, 1H Short & Premium, 15M Short & Premium
                if direction == "LONG":
                    cond_4h = t4_long[idx_k] and p4_disc[idx_k]
                    cond_1h = t1_long[idx_k] and p1_disc[idx_k]
                    cond_15m = p15_disc[idx_k] and (t15_long[idx_k] if require_15m_ema_trend else True)
                    if not (cond_4h and cond_1h and cond_15m):
                        gate_stats["VETO_MTF_PD_MISMATCH"] += 1
                        continue

                elif direction == "SHORT":
                    cond_4h = t4_short[idx_k] and p4_prem[idx_k]
                    cond_1h = t1_short[idx_k] and p1_prem[idx_k]
                    cond_15m = p15_prem[idx_k] and (t15_short[idx_k] if require_15m_ema_trend else True)
                    if not (cond_4h and cond_1h and cond_15m):
                        gate_stats["VETO_MTF_PD_MISMATCH"] += 1
                        continue

                gate_stats["APPROVED"] += 1

                entry_p = sfp_sig["entry"]
                sl_p = sfp_sig["sl"]
                tp1_p = sfp_sig["tp1"]
                tp2_p = sfp_sig["tp2"]
                risk_dist = sfp_sig["risk_dist"]
                if risk_dist <= 1e-8:
                    continue

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
                    "status": "OPEN" if not sfp_sig.get("is_limit", False) else "PENDING_LIMIT",
                    "bars_held": 0,
                    "bars_waiting": 0,
                    "zone_low": sfp_sig.get("zone_low", min(entry_p, sl_p)),
                    "zone_high": sfp_sig.get("zone_high", max(entry_p, sl_p)),
                    "pool": sfp_sig["pool"],
                    "macro_gate": macro_gate,
                    "is_weekend": bool(is_weekend),
                }

        return trades, gate_stats


def run_benchmark(year: int, require_15m_ema: bool = False, entry_model: str = ENTRY_MODEL):
    s_dt = datetime(year, 1, 1, 0, 0, tzinfo=timezone.utc)
    if year == 2026:
        e_dt = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
    else:
        e_dt = datetime(year, 12, 31, 23, 59, tzinfo=timezone.utc)

    runner = BegonyaPDRunner(s_dt, e_dt, entry_model=entry_model)
    all_trades = []
    veto_totals = {"VETO_MACRO_RANGE": 0, "VETO_DIRECTION_MISMATCH": 0, "VETO_MTF_PD_MISMATCH": 0, "APPROVED": 0}

    for s in TARGET_SYMBOLS:
        df = runner.fetch_data_and_compute_pd(s)
        if df is not None:
            t_l, v_s = runner.run_simulation(s, df, require_15m_ema_trend=require_15m_ema)
            all_trades.extend(t_l)
            for k in veto_totals:
                veto_totals[k] += v_s.get(k, 0)

    all_trades.sort(key=lambda x: x["opened_at"])
    tp2 = len([t for t in all_trades if t["close_reason"] == "TP2_HIT"])
    be = len([t for t in all_trades if t["close_reason"] == "BREAK_EVEN"])
    sl = len([t for t in all_trades if t["close_reason"] == "STOP_LOSS"])
    net_r = sum(t["r_result"] for t in all_trades)
    cnt = len(all_trades)
    wr = (tp2 + be) / cnt * 100 if cnt > 0 else 0.0

    print(f"=== {year} YILI SONUÇLARI (15M EMA Şartı: {require_15m_ema} | Model: {entry_model.upper()}) ===")
    print(f"Toplam İşlem: {cnt} | Win Rate: %{wr:.1f} | TP2: {tp2} | BE: {be} | SL: {sl} | Net R: {net_r:+.2f}R | Dolar: ${net_r*200:+,.0f}")
    print(f"Vetolar: {veto_totals}\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Begonya PD Strategy Multi-Year Backtest")
    parser.add_argument("--entry-model", type=str, choices=["midpoint", "close"], default=ENTRY_MODEL, help="Giriş modeli: midpoint (50%% CE) veya close")
    parser.add_argument("--year", type=int, default=None, help="Yıl (2025, 2026 veya belirtilmezse her ikisi)")
    parser.add_argument("--require-15m-ema", action="store_true", help="15M EMA trend teyidi şartı")
    args = parser.parse_args()

    if args.year:
        run_benchmark(args.year, require_15m_ema=args.require_15m_ema, entry_model=args.entry_model)
    else:
        run_benchmark(2026, require_15m_ema=args.require_15m_ema, entry_model=args.entry_model)
        run_benchmark(2025, require_15m_ema=args.require_15m_ema, entry_model=args.entry_model)
