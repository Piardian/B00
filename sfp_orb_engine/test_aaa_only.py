"""
🌺 Begonya 00 - Yalnızca Grade AAA Analizi ve Backtesti
SADECE GRADE AAA İşlemleri Alındığında Sistemin Karnesi Ne Olur?
"""

import time
import json
import logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from .config import get_asset_sl_buffer

def run_aaa_comparison():
    symbols = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD",
        "EURJPY", "GBPJPY", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD"
    ]

    if not mt5.initialize():
        print("MT5 başlatılamadı!")
        return

    utc_to = datetime(2026, 10, 10, tzinfo=timezone.utc)
    utc_from = datetime(2025, 10, 10, tzinfo=timezone.utc)

    all_aaa_trades = []
    symbol_breakdown = {}

    for sym in symbols:
        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, utc_from, utc_to)
        if rates is None or len(rates) < 1000:
            continue

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["date"] = df["datetime"].dt.date
        df["hour"] = df["datetime"].dt.hour

        daily = df.groupby("date").agg({"high": "max", "low": "min"}).shift(1)
        df["pdh"] = df["date"].map(daily["high"]).fillna(0.0)
        df["pdl"] = df["date"].map(daily["low"]).fillna(0.0)

        asian_bars = df[df["hour"] < 6]
        df["ash"] = df["date"].map(asian_bars.groupby("date")["high"].max()).fillna(0.0)
        df["asl"] = df["date"].map(asian_bars.groupby("date")["low"].min()).fillna(0.0)

        df["htf_ema50"] = df["close"].ewm(span=200, adjust=False).mean()
        df["htf_ema200"] = df["close"].ewm(span=800, adjust=False).mean()

        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                np.abs(df["high"] - df["close"].shift(1)),
                np.abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = tr.rolling(14).mean().fillna(df["high"] - df["low"])

        display_sym = f"{sym[:3]}/{sym[3:]}" if len(sym) == 6 and sym.isalpha() else sym
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

        n = len(df)
        sym_trades = []

        i = 800
        while i < n - 40:
            c, h, l, atr, hour = closes[i], highs[i], lows[i], atrs[i], hours[i]
            pdh, pdl, ash, asl = pdhs[i], pdls[i], ashs[i], asls[i]

            if pdh == 0 or pdl == 0:
                i += 1
                continue

            bar_rng = max(h - l, 1e-8)
            upper_wick = (h - max(opens[i], c)) / bar_rng
            lower_wick = (min(opens[i], c) - l) / bar_rng

            in_sess = (7 <= hour <= 11) or (13 <= hour <= 18)
            if not in_sess:
                i += 1
                continue

            htf_bull = ema50s[i] > ema200s[i]
            htf_bear = ema50s[i] < ema200s[i]

            is_momentum = sym in ["BTCUSD", "ETHUSD", "NAS100", "XAUUSD"]
            allow_short = htf_bear if is_momentum else (not htf_bull)
            allow_long = htf_bull if is_momentum else (not htf_bear)

            # SHORT AAA: Tepe Süpürme + HTF Ayı (Pro-Trend) + MSS + FVG
            if upper_wick >= 0.35 and ((h > pdh and c < pdh) or (ash > 0 and h > ash and c < ash)) and allow_short:
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
                    
                    # SADECE GRADE AAA: Hem Pro-Trend (htf_bear) Hem de FVG Dengesizliği ŞART!
                    is_aaa = htf_bear and has_fvg
                    if not is_aaa:
                        i += 1
                        continue

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
                            t = {
                                "symbol": sym,
                                "direction": "SHORT",
                                "r_result": 1.7,
                                "reason": "TP2_HIT",
                                "opened_at": dts[i],
                            }
                            sym_trades.append(t)
                            all_aaa_trades.append(t)
                            i = m + 4
                            break

                        elif bh >= cur_sl:
                            t = {
                                "symbol": sym,
                                "direction": "SHORT",
                                "r_result": 0.6 if pos_status == "TP1" else -1.0,
                                "reason": "BREAK_EVEN" if pos_status == "TP1" else "STOP_LOSS",
                                "opened_at": dts[i],
                            }
                            sym_trades.append(t)
                            all_aaa_trades.append(t)
                            i = m + 4
                            break

            # LONG AAA: Dip Süpürme + HTF Boğa (Pro-Trend) + MSS + FVG
            elif lower_wick >= 0.35 and ((l < pdl and c > pdl) or (asl > 0 and l < asl and c > asl)) and allow_long:
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
                    
                    # SADECE GRADE AAA: Hem Pro-Trend (htf_bull) Hem de FVG Dengesizliği ŞART!
                    is_aaa = htf_bull and has_fvg
                    if not is_aaa:
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
                            t = {
                                "symbol": sym,
                                "direction": "LONG",
                                "r_result": 1.7,
                                "reason": "TP2_HIT",
                                "opened_at": dts[i],
                            }
                            sym_trades.append(t)
                            all_aaa_trades.append(t)
                            i = m + 4
                            break

                        elif bl <= cur_sl:
                            t = {
                                "symbol": sym,
                                "direction": "LONG",
                                "r_result": 0.6 if pos_status == "TP1" else -1.0,
                                "reason": "BREAK_EVEN" if pos_status == "TP1" else "STOP_LOSS",
                                "opened_at": dts[i],
                            }
                            sym_trades.append(t)
                            all_aaa_trades.append(t)
                            i = m + 4
                            break

            i += 1

        tot = len(sym_trades)
        if tot > 0:
            w = sum(1 for t in sym_trades if t["r_result"] > 0)
            net = sum(t["r_result"] for t in sym_trades)
            wr = round(w / tot * 100, 1)
            gw = sum(t["r_result"] for t in sym_trades if t["r_result"] > 0)
            gl = abs(sum(t["r_result"] for t in sym_trades if t["r_result"] < 0))
            pf = round(gw / max(gl, 1e-5), 2)
            symbol_breakdown[sym] = {
                "trades": tot,
                "wins": w,
                "losses": tot - w,
                "win_rate": wr,
                "net_r": round(net, 2),
                "profit_factor": pf,
            }

    mt5.shutdown()

    tot_all = len(all_aaa_trades)
    if tot_all == 0:
        print("Hiç AAA işlem bulunamadı!")
        return

    wins_all = sum(1 for t in all_trades if t["r_result"] > 0) if "all_trades" in locals() else sum(1 for t in all_aaa_trades if t["r_result"] > 0)
    net_all = sum(t["r_result"] for t in all_aaa_trades)
    wr_all = round(wins_all / tot_all * 100, 1)
    gw_all = sum(t["r_result"] for t in all_aaa_trades if t["r_result"] > 0)
    gl_all = abs(sum(t["r_result"] for t in all_aaa_trades if t["r_result"] < 0))
    pf_all = round(gw_all / max(gl_all, 1e-5), 2)

    report = {
        "title": "SADECE GRADE AAA (Kurumsal Pro-Trend + FVG) 1 YILLIK BACKTEST KARNESİ",
        "total_trades": tot_all,
        "wins": wins_all,
        "losses": tot_all - wins_all,
        "win_rate": wr_all,
        "profit_factor": pf_all,
        "net_r": round(net_all, 2),
        "expectancy_r": round(net_all / tot_all, 2),
        "symbols": symbol_breakdown,
    }
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    run_aaa_comparison()
