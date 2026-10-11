"""
🌺 Begonya 00 - Ultra Hızlı Gelişmiş Kurumsal Backtest Motoru
SMC MSS + PDH/PDL/Asian Sweeps + HTF 4H Trend Alignment + Dynamic Risk:Reward
Gerçek MT5 Broker M15 Verisi (2025-10-10 - 2026-10-10)
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
logger = logging.getLogger("Begonya00.InstitutionalBacktest")


class InstitutionalBacktestEngine:
    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD",
            "EURJPY", "XAUUSD", "NAS100", "BTCUSD"
        ]

    def fetch_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """MT5 üzerinden son 1 yılın M15 verisini çeker ve özellikleri hesaplar."""
        if not mt5.initialize():
            logger.error("MT5 başlatılamadı!")
            return None

        utc_to = datetime(2026, 10, 10, tzinfo=timezone.utc)
        utc_from = datetime(2025, 10, 10, tzinfo=timezone.utc)

        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, utc_from, utc_to)
        if rates is None or len(rates) < 1000:
            logger.warning(f"{symbol} için yetersiz veri!")
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

        # 3. Yüksek Zaman Dilimi Trendi (4 Saatlik EMA Eşdeğeri: 200 ve 800 bar)
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

    def backtest_symbol(self, symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Ultra hızlı numpy vektörleri üzerinde kurumsal simülasyon."""
        n = len(df)
        trades = []
        if n < 1000:
            return trades

        display_sym = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 and symbol.isalpha() else symbol
        sl_buffer_atr = get_asset_sl_buffer(display_sym)

        # Numpy dizileri
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

            # --- A. TEPE LİKİDİTE SÜPÜRMESİ (PDH veya Asya Zirvesi + %45 Üst Fitil Barajı) ---
            sweep_high = False
            pool_name = ""
            if upper_wick >= 0.45:
                if h > pdh and c < pdh:
                    sweep_high = True
                    pool_name = "PDH"
                elif (7 <= hour <= 11) and ash > 0.0 and h > ash and c < ash:
                    sweep_high = True
                    pool_name = "ASIAN_HIGH"

            # --- B. DİP LİKİDİTE SÜPÜRMESİ (PDL veya Asya Dibi + %45 Alt Fitil Barajı) ---
            sweep_low = False
            if lower_wick >= 0.45:
                if l < pdl and c > pdl:
                    sweep_low = True
                    pool_name = "PDL"
                elif (7 <= hour <= 11) and asl > 0.0 and l < asl and c > asl:
                    sweep_low = True
                    pool_name = "ASIAN_LOW"

            is_momentum = symbol in ["BTCUSD", "ETHUSD", "NAS100", "XAUUSD"]

            # SHORT: Tepe Süpürme + HTF Filtresi + MSS Teyidi
            # Momentum varlıklarında kesin ayı trendi (htf_bear) şart; forexte boğa olmaması yeterli
            allow_short = htf_bear if is_momentum else (not htf_bull)
            allow_long = htf_bull if is_momentum else (not htf_bear)

            # Yalnızca yüksek likiditeli prime seanslarda (Londra 07:00-11:00 UTC veya NY 13:00-17:00 UTC) işlem al
            in_active_session = (7 <= hour <= 11) or (13 <= hour <= 17)
            if not in_active_session:
                i += 1
                continue

            if sweep_high and allow_short:
                peak = h
                mss_trigger = min(l, lows[i-1])
                mss_ok = False
                entry_idx = -1

                for k in range(1, 4):
                    if i + k < n and closes[i+k] < mss_trigger:
                        # Displacement Kontrolü: Mum gövdesi en az %35 olmalı
                        b_rng = max(highs[i+k] - lows[i+k], 1e-8)
                        body_r = abs(closes[i+k] - opens[i+k]) / b_rng
                        if body_r >= 0.35:
                            mss_ok = True
                            entry_idx = i + k
                            break

                if mss_ok:
                    # Grade Belirleme: FVG ve Pro-Trend Uyumu
                    has_fvg = (lows[entry_idx - 2] > highs[entry_idx]) and ((lows[entry_idx - 2] - highs[entry_idx]) >= atr * 0.10)
                    if htf_bear and has_fvg:
                        grade = "AAA"
                    elif htf_bear or has_fvg:
                        grade = "A+"
                    else:
                        grade = "A"

                    # KULLANICI TALİMATI: SADECE GRADE A+ VE ÜZERİ İŞLEMLERİ AL
                    if grade not in ["AAA", "A+"]:
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
                            # %50 @ 1.2R + %50 @ 2.2R = +1.7R
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

            # LONG: Dip Süpürme + HTF Filtresi + MSS Teyidi
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
                    # Grade Belirleme: FVG ve Pro-Trend Uyumu
                    has_fvg = (lows[entry_idx] > highs[entry_idx - 2]) and ((lows[entry_idx] - highs[entry_idx - 2]) >= atr * 0.10)
                    if htf_bull and has_fvg:
                        grade = "AAA"
                    elif htf_bull or has_fvg:
                        grade = "A+"
                    else:
                        grade = "A"

                    # KULLANICI TALİMATI: SADECE GRADE A+ VE ÜZERİ İŞLEMLERİ AL
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

    def run_full_portfolio(self) -> Dict[str, Any]:
        """Tüm portföyde backtesti koşturur."""
        all_trades = []
        sym_reports = {}
        t0 = time.time()

        for sym in self.symbols:
            df = self.fetch_data(sym)
            if df is None:
                continue

            trades = self.backtest_symbol(sym, df)
            all_trades.extend(trades)

            total = len(trades)
            if total > 0:
                wins = sum(1 for t in trades if t["r_result"] > 0)
                losses = sum(1 for t in trades if t["r_result"] < 0)
                net_r = sum(t["r_result"] for t in trades)
                win_rate = round((wins / total) * 100, 1)
                gross_win = sum(t["r_result"] for t in trades if t["r_result"] > 0)
                gross_loss = abs(sum(t["r_result"] for t in trades if t["r_result"] < 0))
                pf = round(gross_win / max(gross_loss, 1e-5), 2)

                sym_reports[sym] = {
                    "trades": total,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": win_rate,
                    "net_r": round(net_r, 2),
                    "profit_factor": pf,
                    "expectancy": round(net_r / total, 2),
                }

        elapsed = round(time.time() - t0, 2)
        total_tr = len(all_trades)
        if total_tr == 0:
            return {"error": "İşlem bulunamadı."}

        total_wins = sum(1 for t in all_trades if t["r_result"] > 0)
        total_losses = sum(1 for t in all_trades if t["r_result"] < 0)
        overall_wr = round((total_wins / total_tr) * 100, 1)

        gross_profit = sum(t["r_result"] for t in all_trades if t["r_result"] > 0)
        gross_loss = abs(sum(t["r_result"] for t in all_trades if t["r_result"] < 0))
        net_portfolio_r = round(gross_profit - gross_loss, 2)
        overall_pf = round(gross_profit / max(gross_loss, 1e-5), 2)
        expectancy = round(net_portfolio_r / total_tr, 2)

        # Drawdown Analizi
        sorted_trades = sorted(all_trades, key=lambda x: str(x["opened_at"]))
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        consec_losses = 0
        max_consec_losses = 0
        consec_wins = 0
        max_consec_wins = 0

        monthly_returns = {}

        for t in sorted_trades:
            r = t["r_result"]
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

            if r > 0:
                consec_wins += 1
                consec_losses = 0
                if consec_wins > max_consec_wins:
                    max_consec_wins = consec_wins
            elif r < 0:
                consec_losses += 1
                consec_wins = 0
                if consec_losses > max_consec_losses:
                    max_consec_losses = consec_losses

            m_key = str(t["opened_at"])[:7]
            monthly_returns[m_key] = round(monthly_returns.get(m_key, 0.0) + r, 2)

        pool_stats = {}
        for p_name in ["PDH", "PDL", "ASIAN_HIGH", "ASIAN_LOW"]:
            p_trades = [t for t in all_trades if t.get("pool") == p_name]
            if p_trades:
                p_w = sum(1 for t in p_trades if t["r_result"] > 0)
                p_net = round(sum(t["r_result"] for t in p_trades), 2)
                pool_stats[p_name] = {
                    "trades": len(p_trades),
                    "win_rate": round(p_w / len(p_trades) * 100, 1),
                    "net_r": p_net,
                }

        grade_stats = {}
        for g_name in ["AAA", "A+"]:
            g_trades = [t for t in all_trades if t.get("grade") == g_name]
            if g_trades:
                g_w = sum(1 for t in g_trades if t["r_result"] > 0)
                g_net = round(sum(t["r_result"] for t in g_trades), 2)
                grade_stats[g_name] = {
                    "trades": len(g_trades),
                    "win_rate": round(g_w / len(g_trades) * 100, 1),
                    "net_r": g_net,
                }

        scorecard = {
            "period": "2025-10-10 - 2026-10-10 (1 Yıl)",
            "execution_time_seconds": elapsed,
            "total_trades": total_tr,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "win_rate": overall_wr,
            "profit_factor": overall_pf,
            "net_portfolio_r": net_portfolio_r,
            "expectancy_r": expectancy,
            "max_drawdown_r": round(max_dd, 2),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "grade_breakdown": grade_stats,
            "pool_breakdown": pool_stats,
            "symbol_reports": sym_reports,
            "monthly_returns": monthly_returns,
        }

        return scorecard


if __name__ == "__main__":
    engine = InstitutionalBacktestEngine()
    card = engine.run_full_portfolio()
    print(json.dumps(card, indent=2, default=str))
