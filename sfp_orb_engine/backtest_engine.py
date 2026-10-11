"""
🌺 Begonya 00 - 1 Yıllık Yüksek Hızlı ve Doğruluklu Kurumsal Backtest Motoru
SFP (SMC P/D, FVG Confluence, Volume Anomaly) & ORB Seans Kırılımları
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

from .config import (
    get_asset_sl_buffer,
    ORB_MIN_BREAKOUT_VOL_RATIO,
    DATA_DIR,
)

logger = logging.getLogger("Begonya00.Backtest")


class BacktestEngine:
    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD",
            "EURJPY", "GBPJPY", "XAUUSD", "NAS100", "BTCUSD", "ETHUSD"
        ]

    def fetch_historical_m15(self, symbol: str) -> Optional[pd.DataFrame]:
        """MT5 üzerinden son 1 yılın gerçek M15 barlarını çeker."""
        if not mt5.initialize():
            logger.error("MT5 initialize başarısız!")
            return None

        utc_to = datetime(2026, 10, 10, tzinfo=timezone.utc)
        utc_from = datetime(2025, 10, 10, tzinfo=timezone.utc)

        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, utc_from, utc_to)
        if rates is None or len(rates) < 200:
            logger.warning(f"{symbol} için MT5 verisi alınamadı!")
            return None

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # Ön-hesaplanan Vektöriyel İndikatörler
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                np.abs(df["high"] - df["close"].shift(1)),
                np.abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = tr.rolling(14).mean().fillna(df["high"] - df["low"])
        df["vol_sma"] = df["volume"].rolling(20).mean().fillna(df["volume"])

        return df

    def run_backtest_symbol(self, symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Numpy üzerinde ultra hızlı ve gerçekçi simülasyon."""
        n = len(df)
        if n < 200:
            return []

        display_sym = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 and symbol.isalpha() else symbol
        sl_buffer_atr = get_asset_sl_buffer(display_sym)

        # Numpy dizilerine dönüştür (100x hız artışı)
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        volumes = df["volume"].values
        vol_smas = df["vol_sma"].values
        atrs = df["atr"].values
        ema50s = df["ema50"].values
        ema200s = df["ema200"].values
        dts = df["datetime"].dt.strftime("%Y-%m-%d %H:%M").values
        hours = df["datetime"].dt.hour.values
        minutes = df["datetime"].dt.minute.values

        # 1. Swing Pivotlarını Vektöriyel Olarak Ön-Hesapla
        is_sh = np.zeros(n, dtype=bool)
        is_sh[1:-1] = (highs[1:-1] > highs[:-2]) & (highs[1:-1] > highs[2:])

        is_sl = np.zeros(n, dtype=bool)
        is_sl[1:-1] = (lows[1:-1] < lows[:-2]) & (lows[1:-1] < lows[2:])

        # 2. ORB Seans Açılışlarını Ön-İşle
        orb_high = np.zeros(n, dtype=float)
        orb_low = np.zeros(n, dtype=float)
        in_orb_window = np.zeros(n, dtype=bool)

        current_orb_h = 0.0
        current_orb_l = 0.0
        in_sess = False
        sess_expire = 0

        for i in range(n):
            h_val = hours[i]
            m_val = minutes[i]
            # Londra 07:00 UTC veya NY 13:30 UTC
            if (h_val == 7 and m_val == 0) or (h_val == 13 and m_val == 30):
                current_orb_h = highs[i]
                current_orb_l = lows[i]
                in_sess = True
                sess_expire = i + 14  # ~3.5 saatlik ORB işlem penceresi
            elif in_sess and i <= sess_expire:
                orb_high[i] = current_orb_h
                orb_low[i] = current_orb_l
                in_orb_window[i] = True
            elif i > sess_expire:
                in_sess = False

        trades = []
        active_position = None
        cooldown_until = 0

        # Adım adım simülasyon döngüsü
        for i in range(50, n):
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]
            c_atr = atrs[i]
            c_vol = volumes[i]
            c_vol_sma = vol_smas[i]
            c_ema50 = ema50s[i]
            c_ema200 = ema200s[i]
            c_time = dts[i]
            bar_range = max(c_high - c_low, 1e-8)

            # --- MEVCUT POZİSYON KONTROLÜ ---
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
                        r_res = (1.5 * 0.5) + (p["rr_ratio"] * 0.5)
                    elif c_low <= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.5 * 0.5) + 0.0  # +0.75R
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                    elif p["bars_held"] >= 192:  # 48 saat
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
                        r_res = (1.5 * 0.5) + (p["rr_ratio"] * 0.5)
                    elif c_high >= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.5 * 0.5) + 0.0  # +0.75R
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                    elif p["bars_held"] >= 192:
                        closed = True
                        close_reason = "TIME_EXIT"
                        r_res = (entry - c_close) / max(p["original_sl"] - entry, 1e-8)

                if closed:
                    p["closed_at"] = c_time
                    p["exit_price"] = c_close
                    p["close_reason"] = close_reason
                    p["r_result"] = round(float(r_res), 2)
                    trades.append(p)
                    active_position = None
                    cooldown_until = i + 3  # 45 dk bekleme

                continue

            if i < cooldown_until:
                continue

            # --- SİNYAL TARAMASI ---
            trend = "BULLISH" if c_ema50 > c_ema200 else ("BEARISH" if c_ema50 < c_ema200 else "NEUTRAL")
            vol_ratio = c_vol / max(c_vol_sma, 1e-8)
            is_vol_anomaly = (vol_ratio >= 1.4)

            sfp_sig = None
            orb_sig = None

            # 1. SFP Taraması
            sh_sub = np.where(is_sh[i-35:i])[0] + (i-35)
            sl_sub = np.where(is_sl[i-35:i])[0] + (i-35)

            p_high = highs[i-1]
            p_low = lows[i-1]
            p_close = closes[i-1]
            p_open = opens[i-1]

            # SHORT SFP (Tepe süpürme)
            if len(sh_sub) > 0 and len(sl_sub) > 0:
                recent_sh = np.max(highs[sh_sub[-3:]])
                recent_sl = np.min(lows[sl_sub[-3:]])
                eq = (recent_sh + recent_sl) / 2.0

                is_single = (c_high > recent_sh and c_close < recent_sh)
                is_two = (p_high > recent_sh and c_close < recent_sh and c_close < p_close and c_close < c_open)

                if (is_single or is_two) and c_close >= eq:
                    clv = (c_close - c_low) / bar_range
                    if (c_close <= c_open) or (clv <= 0.45):
                        upper_wick = c_high - max(c_open, c_close)
                        if (upper_wick / bar_range) >= 0.35:
                            # FVG kontrolü
                            has_fvg = (lows[i-2] > c_high) and ((lows[i-2] - c_high) >= c_atr * 0.15)
                            trend_align = "PRO_TREND" if trend == "BEARISH" else "COUNTER_TREND"

                            if has_fvg and trend_align == "PRO_TREND":
                                grade = "AAA"
                            elif has_fvg or trend_align == "PRO_TREND" or is_vol_anomaly:
                                grade = "A+"
                            else:
                                grade = "A"

                            peak = max(c_high, p_high) if is_two else c_high
                            sl_p = peak + (c_atr * sl_buffer_atr)
                            risk = max(sl_p - c_close, c_atr * 0.2)
                            tp1_p = c_close - (risk * 1.5)
                            tp2_p = c_close - (risk * 2.5)

                            sfp_sig = {
                                "symbol": symbol,
                                "strategy": "SFP_VOLUME_ANOMALY",
                                "direction": "SHORT",
                                "grade": grade,
                                "entry": c_close,
                                "original_sl": sl_p,
                                "current_sl": sl_p,
                                "tp1": tp1_p,
                                "tp2": tp2_p,
                                "risk_pips": round(risk, 5),
                                "rr_ratio": 2.5,
                                "status": "OPEN",
                                "bars_held": 0,
                                "opened_at": c_time,
                            }

                # LONG SFP (Dip süpürme)
                if sfp_sig is None:
                    is_single_l = (c_low < recent_sl and c_close > recent_sl)
                    is_two_l = (p_low < recent_sl and c_close > recent_sl and c_close > p_close and c_close > c_open)

                    if (is_single_l or is_two_l) and c_close <= eq:
                        clv = (c_close - c_low) / bar_range
                        if (c_close >= c_open) or (clv >= 0.55):
                            lower_wick = min(c_open, c_close) - c_low
                            if (lower_wick / bar_range) >= 0.35:
                                has_fvg = (c_low > highs[i-2]) and ((c_low - highs[i-2]) >= c_atr * 0.15)
                                trend_align = "PRO_TREND" if trend == "BULLISH" else "COUNTER_TREND"

                                if has_fvg and trend_align == "PRO_TREND":
                                    grade = "AAA"
                                elif has_fvg or trend_align == "PRO_TREND" or is_vol_anomaly:
                                    grade = "A+"
                                else:
                                    grade = "A"

                                valley = min(c_low, p_low) if is_two_l else c_low
                                sl_p = valley - (c_atr * sl_buffer_atr)
                                risk = max(c_close - sl_p, c_atr * 0.2)
                                tp1_p = c_close + (risk * 1.5)
                                tp2_p = c_close + (risk * 2.5)

                                sfp_sig = {
                                    "symbol": symbol,
                                    "strategy": "SFP_VOLUME_ANOMALY",
                                    "direction": "LONG",
                                    "grade": grade,
                                    "entry": c_close,
                                    "original_sl": sl_p,
                                    "current_sl": sl_p,
                                    "tp1": tp1_p,
                                    "tp2": tp2_p,
                                    "risk_pips": round(risk, 5),
                                    "rr_ratio": 2.5,
                                    "status": "OPEN",
                                    "bars_held": 0,
                                    "opened_at": c_time,
                                }

            # 2. ORB Taraması
            if in_orb_window[i]:
                o_h = orb_high[i]
                o_l = orb_low[i]
                o_range = max(o_h - o_l, c_atr * 0.2)

                # LONG ORB
                if c_close > o_h and vol_ratio >= ORB_MIN_BREAKOUT_VOL_RATIO:
                    body = abs(c_close - c_open) / bar_range
                    top_wick = (c_high - c_close) / bar_range
                    if body >= 0.40 and top_wick <= 0.35:
                        sl_p = o_h - (o_range * 0.5)
                        risk = max(c_close - sl_p, c_atr * 0.2)
                        tp1_p = c_close + o_range
                        tp2_p = c_close + (o_range * 2.0)
                        rr = round((tp2_p - c_close) / risk, 2)
                        grade = "A+" if trend == "BULLISH" else "A"

                        orb_sig = {
                            "symbol": symbol,
                            "strategy": "ORB_SESSION_BREAKOUT",
                            "direction": "LONG",
                            "grade": grade,
                            "entry": c_close,
                            "original_sl": sl_p,
                            "current_sl": sl_p,
                            "tp1": tp1_p,
                            "tp2": tp2_p,
                            "risk_pips": round(risk, 5),
                            "rr_ratio": rr,
                            "status": "OPEN",
                            "bars_held": 0,
                            "opened_at": c_time,
                        }

                # SHORT ORB
                elif c_close < o_l and vol_ratio >= ORB_MIN_BREAKOUT_VOL_RATIO:
                    body = abs(c_close - c_open) / bar_range
                    bot_wick = (c_close - c_low) / bar_range
                    if body >= 0.40 and bot_wick <= 0.35:
                        sl_p = o_l + (o_range * 0.5)
                        risk = max(sl_p - c_close, c_atr * 0.2)
                        tp1_p = c_close - o_range
                        tp2_p = c_close - (o_range * 2.0)
                        rr = round((c_close - tp2_p) / risk, 2)
                        grade = "A+" if trend == "BEARISH" else "A"

                        orb_sig = {
                            "symbol": symbol,
                            "strategy": "ORB_SESSION_BREAKOUT",
                            "direction": "SHORT",
                            "grade": grade,
                            "entry": c_close,
                            "original_sl": sl_p,
                            "current_sl": sl_p,
                            "tp1": tp1_p,
                            "tp2": tp2_p,
                            "risk_pips": round(risk, 5),
                            "rr_ratio": rr,
                            "status": "OPEN",
                            "bars_held": 0,
                            "opened_at": c_time,
                        }

            # Sinyal Seçimi: Grade A ve üzeri
            chosen = None
            if sfp_sig and sfp_sig["grade"] in ["AAA", "A+", "A"]:
                chosen = sfp_sig
            elif orb_sig and orb_sig["grade"] in ["AAA", "A+", "A"]:
                chosen = orb_sig

            if chosen:
                active_position = chosen

        return trades

    def run_full_portfolio_backtest(self) -> Dict[str, Any]:
        """Tüm portföy üzerinde son 1 yıllık backtesti koşturur ve karne üretir."""
        all_trades = []
        sym_reports = {}

        t_start = time.time()
        logger.info(f"🚀 1 Yıllık Portföy Backtesti Başlatılıyor ({len(self.symbols)} Enstrüman)...")

        for sym in self.symbols:
            logger.info(f"📊 {sym} M15 verisi işleniyor...")
            df = self.fetch_historical_m15(sym)
            if df is None:
                continue

            trades = self.run_backtest_symbol(sym, df)
            all_trades.extend(trades)

            total = len(trades)
            if total > 0:
                wins = sum(1 for t in trades if t["r_result"] > 0)
                losses = sum(1 for t in trades if t["r_result"] < 0)
                bes = sum(1 for t in trades if t["r_result"] == 0)
                net_r = sum(t["r_result"] for t in trades)
                win_rate = round((wins / total) * 100, 1)

                sym_reports[sym] = {
                    "total_trades": total,
                    "wins": wins,
                    "losses": losses,
                    "break_evens": bes,
                    "win_rate": win_rate,
                    "net_r": round(net_r, 2),
                    "expectancy": round(net_r / total, 2),
                }

        t_elapsed = round(time.time() - t_start, 2)
        scorecard = self._compute_portfolio_scorecard(all_trades, sym_reports, t_elapsed)
        return scorecard

    def _compute_portfolio_scorecard(self, trades: List[Dict[str, Any]], sym_reports: Dict[str, Any], elapsed_s: float) -> Dict[str, Any]:
        total = len(trades)
        if total == 0:
            return {"error": "Hiç işlem bulunamadı."}

        wins = [t for t in trades if t["r_result"] > 0]
        losses = [t for t in trades if t["r_result"] < 0]
        bes = [t for t in trades if t["r_result"] == 0]

        total_wins = len(wins)
        total_losses = len(losses)
        total_bes = len(bes)

        gross_profit_r = sum(t["r_result"] for t in wins)
        gross_loss_r = abs(sum(t["r_result"] for t in losses))
        net_r = round(gross_profit_r - gross_loss_r, 2)

        win_rate = round((total_wins / total) * 100, 1)
        profit_factor = round(gross_profit_r / max(gross_loss_r, 1e-5), 2)
        expectancy_r = round(net_r / total, 2)

        trades_sorted = sorted(trades, key=lambda x: str(x["opened_at"]))
        cumulative = 0.0
        peak = 0.0
        max_drawdown_r = 0.0

        consec_losses = 0
        max_consec_losses = 0
        consec_wins = 0
        max_consec_wins = 0

        monthly_returns = {}

        for t in trades_sorted:
            r = t["r_result"]
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_drawdown_r:
                max_drawdown_r = dd

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

            dt_str = str(t["opened_at"])[:7]
            monthly_returns[dt_str] = round(monthly_returns.get(dt_str, 0.0) + r, 2)

        sfp_trades = [t for t in trades if t["strategy"] == "SFP_VOLUME_ANOMALY"]
        orb_trades = [t for t in trades if t["strategy"] == "ORB_SESSION_BREAKOUT"]

        sfp_wins = sum(1 for t in sfp_trades if t["r_result"] > 0)
        sfp_net_r = round(sum(t["r_result"] for t in sfp_trades), 2)
        sfp_wr = round((sfp_wins / len(sfp_trades) * 100), 1) if sfp_trades else 0.0

        orb_wins = sum(1 for t in orb_trades if t["r_result"] > 0)
        orb_net_r = round(sum(t["r_result"] for t in orb_trades), 2)
        orb_wr = round((orb_wins / len(orb_trades) * 100), 1) if orb_trades else 0.0

        grade_stats = {}
        for g in ["AAA", "A+", "A"]:
            g_trades = [t for t in trades if t.get("grade") == g]
            if g_trades:
                g_wins = sum(1 for t in g_trades if t["r_result"] > 0)
                g_net_r = round(sum(t["r_result"] for t in g_trades), 2)
                grade_stats[g] = {
                    "count": len(g_trades),
                    "win_rate": round(g_wins / len(g_trades) * 100, 1),
                    "net_r": g_net_r,
                    "expectancy": round(g_net_r / len(g_trades), 2),
                }

        return {
            "period": "2025-10-10 - 2026-10-10 (1 Yıl)",
            "timeframe": "15m (M15)",
            "execution_time_seconds": elapsed_s,
            "total_trades": total,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_break_evens": total_bes,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "net_r": net_r,
            "expectancy_r": expectancy_r,
            "max_drawdown_r": round(max_drawdown_r, 2),
            "max_consecutive_wins": max_consec_wins,
            "max_consecutive_losses": max_consec_losses,
            "strategy_breakdown": {
                "SFP": {"trades": len(sfp_trades), "win_rate": sfp_wr, "net_r": sfp_net_r},
                "ORB": {"trades": len(orb_trades), "win_rate": orb_wr, "net_r": orb_net_r},
            },
            "grade_breakdown": grade_stats,
            "symbol_reports": sym_reports,
            "monthly_returns": monthly_returns,
        }


if __name__ == "__main__":
    engine = BacktestEngine()
    scorecard = engine.run_full_portfolio_backtest()
    print("\n" + "=" * 60)
    print("🌺 BEGONYA 00 - 1 YILLIK PORTFÖY BACKTEST KARNESİ")
    print("=" * 60)
    print(json.dumps(scorecard, indent=2, default=str))
