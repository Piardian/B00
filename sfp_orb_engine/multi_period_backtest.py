"""
🌺 Begonya 00 - Coklu Periyot Kurumsal Backtest Motoru (Multi-Period Backtest)
Son 1 Hafta, Son 1 Ay, Son 1 Yıl ve Maksimum Broker Geçmişi (~3 Yıl / 70.000 Bar)
MT5 Gerçek Broker M15 Verisi Üzerinde 4 Kural İle Doğrudan İcra
"""

import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

import MetaTrader5 as mt5
from .config import get_asset_sl_buffer, DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("Begonya00.MultiPeriodBacktest")


class MultiPeriodBacktestRunner:
    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD",
            "EURJPY", "XAUUSD", "NAS100", "BTCUSD"
        ]

    def fetch_full_history(self, symbol: str, bar_count: int = 70000) -> Optional[pd.DataFrame]:
        """Broker hafızasındaki maksimum M15 geçmişini çeker ve indikatörleri hesaplar."""
        if not mt5.initialize():
            logger.error("MT5 başlatılamadı!")
            return None

        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, bar_count)
        if rates is None or len(rates) < 1000:
            logger.warning(f"{symbol} için yetersiz veri! (None)")
            return None

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["date"] = df["datetime"].dt.date
        df["hour"] = df["datetime"].dt.hour

        # 1. Günlük Seviyeler (PDH & PDL)
        daily = df.groupby("date").agg({"high": "max", "low": "min"}).shift(1)
        df["pdh"] = df["date"].map(daily["high"]).fillna(0.0)
        df["pdl"] = df["date"].map(daily["low"]).fillna(0.0)

        # 2. Asya Seansı Seviyeleri (00:00 - 06:00 UTC)
        asian_bars = df[df["hour"] < 6]
        ash_map = asian_bars.groupby("date")["high"].max()
        asl_map = asian_bars.groupby("date")["low"].min()
        df["ash"] = df["date"].map(ash_map).fillna(0.0)
        df["asl"] = df["date"].map(asl_map).fillna(0.0)

        # 3. Yüksek Zaman Dilimi Trendi (4H Eşdeğeri: 200 ve 800 bar)
        df["htf_ema50"] = df["close"].ewm(span=200, adjust=False).mean()
        df["htf_ema200"] = df["close"].ewm(span=800, adjust=False).mean()

        # 4. ATR (14)
        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                np.abs(df["high"] - df["close"].shift(1)),
                np.abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = tr.rolling(14).mean().fillna(df["high"] - df["low"])

        return df

    def simulate_symbol(self, symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Ultra hızlı numpy vektörleri üzerinde 4 kurallı kurumsal simülasyon."""
        n = len(df)
        trades = []
        if n < 1000:
            return trades

        display_sym = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 and symbol.isalpha() else symbol
        sl_buffer_atr = get_asset_sl_buffer(display_sym)

        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        pdhs = df["pdh"].values
        pdls = df["pdl"].values
        ashs = df["ash"].values
        asls = df["asl"].values
        atrs = df["atr"].values
        ema50s = df["htf_ema50"].values
        ema200s = df["htf_ema200"].values
        hours = df["hour"].values
        dts = df["datetime"].dt.strftime("%Y-%m-%d %H:%M").values

        i = 800  # Isınma periyodu
        while i < n - 40:
            c = closes[i]
            h = highs[i]
            l = lows[i]
            atr = atrs[i]
            hour = hours[i]
            pdh = pdhs[i]
            pdl = pdls[i]
            ash = ashs[i]
            asl = asls[i]

            if pdh == 0.0 or pdl == 0.0:
                i += 1
                continue

            htf_bull = ema50s[i] > ema200s[i]
            htf_bear = ema50s[i] < ema200s[i]

            bar_rng = max(h - l, 1e-8)
            upper_wick = (h - max(opens[i], c)) / bar_rng
            lower_wick = (min(opens[i], c) - l) / bar_rng

            # KURAL 2: %45 Fitil Barajı (True Pin-Bar / Rejection)
            sweep_high = False
            pool_name = ""
            if upper_wick >= 0.45:
                if h > pdh and c < pdh:
                    sweep_high = True
                    pool_name = "PDH"
                elif (7 <= hour <= 11) and ash > 0.0 and h > ash and c < ash:
                    sweep_high = True
                    pool_name = "ASIAN_HIGH"

            sweep_low = False
            if lower_wick >= 0.45:
                if l < pdl and c > pdl:
                    sweep_low = True
                    pool_name = "PDL"
                elif (7 <= hour <= 11) and asl > 0.0 and l < asl and c > asl:
                    sweep_low = True
                    pool_name = "ASIAN_LOW"

            is_momentum = symbol in ["BTCUSD", "ETHUSD", "NAS100", "XAUUSD"]
            allow_short = htf_bear if is_momentum else (not htf_bull)
            allow_long = htf_bull if is_momentum else (not htf_bear)

            # KURAL 4: Prime Likidite Seansları (London 07-11 UTC & NY 13-17 UTC)
            in_active_session = (7 <= hour <= 11) or (13 <= hour <= 17)
            if not in_active_session:
                i += 1
                continue

            # SHORT: Tepe Süpürme + MSS Teyidi
            if sweep_high and allow_short:
                peak = h
                mss_trigger = min(l, lows[i-1])
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
                    has_fvg = (lows[entry_idx - 2] > highs[entry_idx]) and ((lows[entry_idx - 2] - highs[entry_idx]) >= atr * 0.10)
                    if htf_bear and has_fvg:
                        grade = "AAA"
                    elif htf_bear or has_fvg:
                        grade = "A+"
                    else:
                        grade = "A"

                    # Yalnızca Grade A+ ve Üzeri
                    if grade not in ["AAA", "A+"]:
                        i += 1
                        continue

                    # KURAL 3: Dinamik 2 Kademeli Çıkış (TP1 1.2R + BE, TP2 2.2R)
                    entry = closes[entry_idx]
                    sl = peak + (atr * sl_buffer_atr)
                    risk = max(sl - entry, atr * 0.2)
                    tp1 = entry - (risk * 1.2)
                    tp2 = entry - (risk * 2.2)

                    cur_sl = sl
                    pos_status = "OPEN"
                    for m in range(entry_idx + 1, min(entry_idx + 80, n)):
                        bh = highs[m]
                        bl = lows[m]

                        if bl <= tp1 and pos_status == "OPEN":
                            pos_status = "TP1"
                            cur_sl = entry

                        if bl <= tp2:
                            trades.append({
                                "symbol": symbol,
                                "direction": "SHORT",
                                "pool": pool_name,
                                "grade": grade,
                                "r_result": 1.7,
                                "reason": "TP2_HIT",
                                "opened_at": dts[i],
                            })
                            i = m + 4
                            break

                        elif bh >= cur_sl:
                            trades.append({
                                "symbol": symbol,
                                "direction": "SHORT",
                                "pool": pool_name,
                                "grade": grade,
                                "r_result": 0.6 if pos_status == "TP1" else -1.0,
                                "reason": "BREAK_EVEN" if pos_status == "TP1" else "STOP_LOSS",
                                "opened_at": dts[i],
                            })
                            i = m + 4
                            break

            # LONG: Dip Süpürme + MSS Teyidi
            elif sweep_low and allow_long:
                valley = l
                mss_trigger = max(h, highs[i-1])
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
                    has_fvg = (lows[entry_idx] > highs[entry_idx - 2]) and ((lows[entry_idx] - highs[entry_idx - 2]) >= atr * 0.10)
                    if htf_bull and has_fvg:
                        grade = "AAA"
                    elif htf_bull or has_fvg:
                        grade = "A+"
                    else:
                        grade = "A"

                    if grade not in ["AAA", "A+"]:
                        i += 1
                        continue

                    entry = closes[entry_idx]
                    sl = valley - (atr * sl_buffer_atr)
                    risk = max(entry - sl, atr * 0.2)
                    tp1 = entry + (risk * 1.2)
                    tp2 = entry + (risk * 2.2)

                    cur_sl = sl
                    pos_status = "OPEN"
                    for m in range(entry_idx + 1, min(entry_idx + 80, n)):
                        bh = highs[m]
                        bl = lows[m]

                        if bh >= tp1 and pos_status == "OPEN":
                            pos_status = "TP1"
                            cur_sl = entry

                        if bh >= tp2:
                            trades.append({
                                "symbol": symbol,
                                "direction": "LONG",
                                "pool": pool_name,
                                "grade": grade,
                                "r_result": 1.7,
                                "reason": "TP2_HIT",
                                "opened_at": dts[i],
                            })
                            i = m + 4
                            break

                        elif bl <= cur_sl:
                            trades.append({
                                "symbol": symbol,
                                "direction": "LONG",
                                "pool": pool_name,
                                "grade": grade,
                                "r_result": 0.6 if pos_status == "TP1" else -1.0,
                                "reason": "BREAK_EVEN" if pos_status == "TP1" else "STOP_LOSS",
                                "opened_at": dts[i],
                            })
                            i = m + 4
                            break

            i += 1

        return trades

    def evaluate_trades_subset(self, trades: List[Dict[str, Any]], period_name: str, start_dt_str: str) -> Dict[str, Any]:
        """Belirli bir zaman alt kümesindeki işlemleri analiz edip karne üretir."""
        filtered = [t for t in trades if str(t["opened_at"]) >= start_dt_str]
        total = len(filtered)
        if total == 0:
            return {
                "period_name": period_name,
                "start_date": start_dt_str,
                "total_trades": 0,
                "win_rate": 0.0,
                "net_r": 0.0,
                "profit_factor": 0.0,
                "message": "Bu periyotta sinyal oluşmadı."
            }

        wins = sum(1 for t in filtered if t["r_result"] > 0)
        losses = sum(1 for t in filtered if t["r_result"] < 0)
        win_rate = round((wins / total) * 100, 1)

        gross_win = sum(t["r_result"] for t in filtered if t["r_result"] > 0)
        gross_loss = abs(sum(t["r_result"] for t in filtered if t["r_result"] < 0))
        net_r = round(gross_win - gross_loss, 2)
        pf = round(gross_win / max(gross_loss, 1e-5), 2)
        exp = round(net_r / total, 2)

        # Sembol Raporları
        sym_map = {}
        for s in self.symbols:
            s_trades = [t for t in filtered if t["symbol"] == s]
            if s_trades:
                s_tot = len(s_trades)
                s_w = sum(1 for t in s_trades if t["r_result"] > 0)
                s_l = sum(1 for t in s_trades if t["r_result"] < 0)
                s_net = round(sum(t["r_result"] for t in s_trades), 2)
                s_gw = sum(t["r_result"] for t in s_trades if t["r_result"] > 0)
                s_gl = abs(sum(t["r_result"] for t in s_trades if t["r_result"] < 0))
                sym_map[s] = {
                    "trades": s_tot,
                    "wins": s_w,
                    "losses": s_l,
                    "win_rate": round(s_w / s_tot * 100, 1),
                    "net_r": s_net,
                    "profit_factor": round(s_gw / max(s_gl, 1e-5), 2),
                }

        # Havuz Raporları
        pool_map = {}
        for p in ["ASIAN_LOW", "ASIAN_HIGH", "PDH", "PDL"]:
            p_trades = [t for t in filtered if t.get("pool") == p]
            if p_trades:
                p_tot = len(p_trades)
                p_w = sum(1 for t in p_trades if t["r_result"] > 0)
                pool_map[p] = {
                    "trades": p_tot,
                    "win_rate": round(p_w / p_tot * 100, 1),
                    "net_r": round(sum(t["r_result"] for t in p_trades), 2),
                }

        # Grade Raporları
        grade_map = {}
        for g in ["A+", "AAA"]:
            g_trades = [t for t in filtered if t.get("grade") == g]
            if g_trades:
                g_tot = len(g_trades)
                g_w = sum(1 for t in g_trades if t["r_result"] > 0)
                grade_map[g] = {
                    "trades": g_tot,
                    "win_rate": round(g_w / g_tot * 100, 1),
                    "net_r": round(sum(t["r_result"] for t in g_trades), 2),
                }

        return {
            "period_name": period_name,
            "start_date": start_dt_str,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "net_r": net_r,
            "profit_factor": pf,
            "expectancy_r": exp,
            "pool_breakdown": pool_map,
            "grade_breakdown": grade_map,
            "symbol_reports": sym_map,
        }

    def run_all_periods(self) -> Dict[str, Any]:
        """Tüm sembolleri simüle eder ve 4 periyot karnesini üretir."""
        t0 = time.time()
        all_master_trades = []
        earliest_dates = []

        logger.info(f"⏳ MT5 Broker Verisi Çekiliyor ({len(self.symbols)} sembol x 70.000 bar)...")

        for sym in self.symbols:
            df = self.fetch_full_history(sym, bar_count=70000)
            if df is None:
                continue
            earliest_dates.append(str(df["datetime"].iloc[800])[:10])
            trades = self.simulate_symbol(sym, df)
            all_master_trades.extend(trades)

        elapsed = round(time.time() - t0, 2)
        logger.info(f"✅ Simülasyon tamamlandı ({elapsed} sn)! Toplam işlem: {len(all_master_trades)}")

        oldest_date = min(earliest_dates) if earliest_dates else "2023-12-18"

        # 4 Periyot Tanımları (2026-10-10 Referanslı)
        periods_def = [
            ("Son 1 Hafta", "2026-10-03"),
            ("Son 1 Ay", "2026-09-10"),
            ("Son 1 Yıl", "2025-10-10"),
            (f"Broker Maksimum Geçmişi (~3 Yıl / {oldest_date} - Günümüz)", oldest_date),
        ]

        results = {}
        for p_name, p_start in periods_def:
            results[p_name] = self.evaluate_trades_subset(all_master_trades, p_name, p_start)

        results["execution_time_seconds"] = elapsed
        results["total_master_trades"] = len(all_master_trades)
        results["oldest_available_broker_date"] = oldest_date
        return results


if __name__ == "__main__":
    runner = MultiPeriodBacktestRunner()
    res = runner.run_all_periods()
    print(json.dumps(res, indent=2, default=str))
