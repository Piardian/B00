"""
🌺 Begonya 00 - 1 Aylık Kurumsal Özel Strateji & Portföy Backtest Motoru
Kullanıcı Parametreleri:
- Başlangıç Sermayesi: $10,000 USD
- İşlem Başına Risk: %2.0 ($200 sabit ve bileşik dinamik simülasyonu)
- TP1: 1.0R (%50 Kâr Alınır, Stop Başabaşa / BE Çekilir)
- TP2: 3.0R (Kalan %50 Kâr Alınır)
- Sonuç Mantığı:
  * TP2_HIT: +2.0R (+%4.0 kâr / +$400)
  * BREAK_EVEN: +0.5R (+%1.0 kâr / +$100)
  * STOP_LOSS: -1.0R (-%2.0 zarar / -$200)
- Seans & Hafta Sonu Kuralları:
  * Hafta İçi: ORB yalnızca Londra Seansı (07:00 - 11:00 UTC), Min 2.0x Hacim Kırılımı
              SFP hem Londra (07:00 - 11:00 UTC) hem New York (13:00 - 17:00 UTC)
  * Hafta Sonu: ORB KAPALI
                SFP yalnızca Kripto paritelerinde açık (07:00-11:00 ve 13:00-17:00 UTC)
- Teyit Standartları:
  * SFP: MSS (Market Structure Shift) Gövde Kırılımı + FVG Dengesizlik + HTF 4H Trend Teyidi (Grade A+ ve AAA)
- Periyot: Son 1 Ay (2026-09-11 - 2026-10-11)
"""

import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
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

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("Begonya00.Custom1MBacktest")

SYMBOLS = [
    # Forex Majörler & Çaprazlar
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    # Emtialar & Endeksler
    "XAUUSD", "NAS100", "SP500", "US30",
    # Kriptolar
    "BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD", "XRPUSD", "DOGUSD"
]

EXCLUDED_SYMBOLS = ["GBPJPY", "AUDUSD"]  # Toksik / sahte iğneli parite filtresi


class Custom1MBacktestRunner:
    def __init__(self, initial_capital: float = 10000.0, risk_pct: float = 0.02):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.utc_to = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
        self.utc_from = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)

    def fetch_m15_data(self, symbol: str) -> Optional[pd.DataFrame]:
        if not mt5.initialize():
            logger.error("MT5 başlatılamadı!")
            return None

        # 30 gün öncesinden ısınma periyodu (4H HTF EMA ve pivotlar için)
        warmup_from = self.utc_from - timedelta(days=25)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, warmup_from, self.utc_to)
        if rates is None or len(rates) < 500:
            return None

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["date"] = df["datetime"].dt.date
        df["weekday"] = df["datetime"].dt.weekday  # 0: Pzt ... 4: Cuma, 5: Cmt, 6: Pzr
        df["hour"] = df["datetime"].dt.hour
        df["minute"] = df["datetime"].dt.minute

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

        # 3. Yüksek Zaman Dilimi Trendi (4 Saatlik Eşdeğeri: 200 ve 800 barlık EMA)
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
        df["vol_sma"] = df["volume"].rolling(20).mean().fillna(df["volume"])

        return df

    def run_symbol(self, symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        if symbol in EXCLUDED_SYMBOLS:
            return []

        display_sym = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 and symbol.isalpha() else symbol
        sl_buffer_atr = get_asset_sl_buffer(display_sym)
        is_crypto_sym = is_crypto(symbol)
        is_momentum = symbol in ["BTCUSD", "ETHUSD", "NAS100", "XAUUSD"]

        n = len(df)
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        volumes = df["volume"].values
        vol_smas = df["vol_sma"].values
        pdhs = df["pdh"].values
        pdls = df["pdl"].values
        ashs = df["ash"].values
        asls = df["asl"].values
        atrs = df["atr"].values
        ema50s = df["htf_ema50"].values
        ema200s = df["htf_ema200"].values
        weekdays = df["weekday"].values
        hours = df["hour"].values
        minutes = df["minute"].values
        dts = df["datetime"].dt.strftime("%Y-%m-%d %H:%M").values
        dates_raw = df["datetime"].values

        # ORB Seans Aralıkları (Yalnızca Hafta İçi Londra 07:00 UTC)
        orb_high = np.zeros(n, dtype=float)
        orb_low = np.zeros(n, dtype=float)
        in_orb_window = np.zeros(n, dtype=bool)

        current_orb_h = 0.0
        current_orb_l = 0.0
        in_sess = False
        sess_expire = 0

        for i in range(n):
            wday = weekdays[i]
            h_val = hours[i]
            m_val = minutes[i]

            # Hafta sonu ORB tamamen kapalıdır
            if wday in [5, 6]:
                continue

            # Hafta İçi: YALNIZCA LONDRA SEANSI (07:00 UTC Açılışı)
            if h_val == 7 and m_val == 0:
                current_orb_h = highs[i]
                current_orb_l = lows[i]
                in_sess = True
                sess_expire = i + 15  # ~3.75 saatlik ORB işlem penceresi (07:15 - 11:00 UTC)
            elif in_sess and i <= sess_expire:
                orb_high[i] = current_orb_h
                orb_low[i] = current_orb_l
                in_orb_window[i] = True
            elif i > sess_expire:
                in_sess = False

        trades = []
        active_position = None
        cooldown_until = 0

        # Başlangıç tarihi filtresi (Son 1 Ay: 2026-09-11'den itibaren)
        start_ts = np.datetime64(self.utc_from.replace(tzinfo=None))

        for i in range(100, n):
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]
            c_atr = atrs[i]
            c_vol = volumes[i]
            c_vol_sma = vol_smas[i]
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
                    # TP1 Kontrolü (1.0R): Vurulunca %50 kâr alınır, Stop BE'ye çekilir
                    if c_high >= tp1 and status == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry

                    if c_high >= tp2:
                        closed = True
                        close_reason = "TP2_HIT"
                        # %50 @ 1.0R + %50 @ 3.0R = +2.0R Net
                        r_res = (1.0 * 0.5) + (3.0 * 0.5)
                    elif c_low <= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            # %50 @ 1.0R + %50 @ BE (0.0R) = +0.5R Net
                            r_res = (1.0 * 0.5) + (0.0 * 0.5)
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                    elif p["bars_held"] >= 192:  # 48 saat zaman aşımı
                        closed = True
                        close_reason = "TIME_EXIT"
                        r_res = (c_close - entry) / max(entry - p["original_sl"], 1e-8)

                elif p_dir == "SHORT":
                    # TP1 Kontrolü (1.0R): Vurulunca %50 kâr alınır, Stop BE'ye çekilir
                    if c_low <= tp1 and status == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry

                    if c_low <= tp2:
                        closed = True
                        close_reason = "TP2_HIT"
                        # %50 @ 1.0R + %50 @ 3.0R = +2.0R Net
                        r_res = (1.0 * 0.5) + (3.0 * 0.5)
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
                    cooldown_until = i + 3  # 45 dk bekleme

                continue

            # Yalnızca son 1 aylık pencere içindeki sinyalleri işle
            bar_raw = pd.Timestamp(dates_raw[i]).tz_localize(None)
            if bar_raw < pd.Timestamp(self.utc_from.replace(tzinfo=None)):
                continue

            if i < cooldown_until:
                continue

            # --- SEANS & GÜN KURALLARI ---
            is_weekend = wday in [5, 6]

            # 1. Hafta Sonu Kuralları:
            # - Kripto dışı hiçbir enstrüman taranmaz
            # - Kriptoda ORB tamamen KAPALIDIR
            # - Kriptoda SFP aktiftir (07-11 UTC ve 13-17 UTC seans pencereleri)
            if is_weekend:
                if not is_crypto_sym:
                    continue
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
                orb_session_active = False  # Hafta sonu ORB kapalı!
            else:
                # 2. Hafta İçi Kuralları:
                # - SFP: Hem Londra (07-11 UTC) hem New York (13-17 UTC) Killzone'larında aktif
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
                # - ORB: SADECE LONDRA SEANSI (07-11 UTC)
                orb_session_active = in_orb_window[i] and (7 <= h_val <= 11)

            pdh = pdhs[i]
            pdl = pdls[i]
            ash = ashs[i]
            asl = asls[i]
            if pdh == 0.0 or pdl == 0.0:
                continue

            htf_bull = ema50s[i] > ema200s[i]
            htf_bear = ema50s[i] < ema200s[i]
            allow_short = htf_bear if is_momentum else (not htf_bull)
            allow_long = htf_bull if is_momentum else (not htf_bear)

            upper_wick = (c_high - max(c_open, c_close)) / bar_rng
            lower_wick = (min(c_open, c_close) - c_low) / bar_rng

            sfp_sig = None
            orb_sig = None

            # --- MODEL 1: KURUMSAL SFP (PDH/PDL/ASIAN + MSS + FVG) ---
            if sfp_session_active:
                sweep_high = False
                pool_name = ""
                if upper_wick >= 0.45:
                    if c_high > pdh and c_close < pdh:
                        sweep_high = True
                        pool_name = "PDH"
                    elif (7 <= h_val <= 11) and ash > 0.0 and c_high > ash and c_close < ash:
                        sweep_high = True
                        pool_name = "ASIAN_HIGH"

                sweep_low = False
                if lower_wick >= 0.45:
                    if c_low < pdl and c_close > pdl:
                        sweep_low = True
                        pool_name = "PDL"
                    elif (7 <= h_val <= 11) and asl > 0.0 and c_low < asl and c_close > asl:
                        sweep_low = True
                        pool_name = "ASIAN_LOW"

                # SHORT: Tepe Süpürme + MSS Teyidi
                if sweep_high and allow_short:
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
                        if htf_bear and has_fvg:
                            grade = "AAA"
                        elif htf_bear or has_fvg:
                            grade = "A+"
                        else:
                            grade = "A"

                        if grade in ["AAA", "A+"]:
                            sfp_sig = {
                                "strategy": "SFP_VOLUME_ANOMALY",
                                "direction": "SHORT",
                                "grade": grade,
                                "entry": closes[entry_idx],
                                "sl": peak + (c_atr * sl_buffer_atr),
                                "pool": pool_name,
                                "trigger_time": dts[entry_idx],
                            }

                # LONG: Dip Süpürme + MSS Teyidi
                elif sweep_low and allow_long:
                    valley = c_low
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
                        has_fvg = (lows[entry_idx] > highs[entry_idx - 2]) and ((lows[entry_idx] - highs[entry_idx - 2]) >= c_atr * 0.10)
                        if htf_bull and has_fvg:
                            grade = "AAA"
                        elif htf_bull or has_fvg:
                            grade = "A+"
                        else:
                            grade = "A"

                        if grade in ["AAA", "A+"]:
                            sfp_sig = {
                                "strategy": "SFP_VOLUME_ANOMALY",
                                "direction": "LONG",
                                "grade": grade,
                                "entry": closes[entry_idx],
                                "sl": valley - (c_atr * sl_buffer_atr),
                                "pool": pool_name,
                                "trigger_time": dts[entry_idx],
                            }

            # --- MODEL 2: ORB (YALNIZCA HAFTA İÇİ LONDRA SEANSI) ---
            if orb_session_active and sfp_sig is None:
                o_h = orb_high[i]
                o_l = orb_low[i]
                vol_ratio = c_vol / max(c_vol_sma, 1e-8)

                # Bullish Breakout
                if c_close > o_h and closes[i-1] <= o_h:
                    if vol_ratio >= 2.0:
                        u_wick = (c_high - c_close) / bar_rng
                        if u_wick <= 0.35 and (c_close - c_open) / bar_rng >= 0.40:
                            mid_sl = (o_h + o_l) / 2.0
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "LONG",
                                "grade": "A+",
                                "entry": c_close,
                                "sl": mid_sl,
                                "pool": "LONDON_ORB",
                                "trigger_time": dts[i],
                            }

                # Bearish Breakout
                elif c_close < o_l and closes[i-1] >= o_l:
                    if vol_ratio >= 2.0:
                        l_wick = (c_close - c_low) / bar_rng
                        if l_wick <= 0.35 and (c_open - c_close) / bar_rng >= 0.40:
                            mid_sl = (o_h + o_l) / 2.0
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "SHORT",
                                "grade": "A+",
                                "entry": c_close,
                                "sl": mid_sl,
                                "pool": "LONDON_ORB",
                                "trigger_time": dts[i],
                            }

            sig = sfp_sig or orb_sig
            if sig is not None:
                entry = sig["entry"]
                sl = sig["sl"]
                direction = sig["direction"]

                if direction == "LONG":
                    risk = max(entry - sl, c_atr * 0.20, entry * 0.001)
                    tp1 = entry + (risk * 1.0)  # TP1 tam 1.0R
                    tp2 = entry + (risk * 3.0)  # TP2 tam 3.0R
                else:
                    risk = max(sl - entry, c_atr * 0.20, entry * 0.001)
                    tp1 = entry - (risk * 1.0)  # TP1 tam 1.0R
                    tp2 = entry - (risk * 3.0)  # TP2 tam 3.0R

                active_position = {
                    "symbol": symbol,
                    "strategy": sig["strategy"],
                    "direction": direction,
                    "grade": sig["grade"],
                    "opened_at": sig["trigger_time"],
                    "entry": entry,
                    "original_sl": sl,
                    "current_sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "risk_pips": risk,
                    "rr_ratio": 3.0,
                    "status": "OPEN",
                    "bars_held": 0,
                    "pool": sig.get("pool", ""),
                    "is_weekend": bool(is_weekend),
                }

        return trades


def run_full_portfolio_simulation():
    runner = Custom1MBacktestRunner(initial_capital=10000.0, risk_pct=0.02)
    logger.info("=" * 70)
    logger.info("🌺 BEGONYA 00 - 1 AYLIK KURUMSAL ÖZEL STRATEJİ & PORTFÖY TESTİ 🌺")
    logger.info(f"Sermaye: ${runner.initial_capital:,.2f} | Risk: %{runner.risk_pct * 100:.1f} ($200 sabit)")
    logger.info("Kurallar: TP1 1.0R (%50 Kâr Al + BE) | TP2 3.0R (Kalan %50)")
    logger.info("Seanslar: Hafta İçi ORB Londra (07-11 UTC) | SFP Londra + NY (07-11 & 13-17 UTC)")
    logger.info("Hafta Sonu: ORB KAPALI | SFP Kripto Açık (07-11 & 13-17 UTC)")
    logger.info(f"Periyot: {runner.utc_from.strftime('%Y-%m-%d')} - {runner.utc_to.strftime('%Y-%m-%d')}")
    logger.info("=" * 70)

    all_trades = []
    symbol_stats = {}

    for sym in SYMBOLS:
        df = runner.fetch_m15_data(sym)
        if df is None:
            continue

        sym_trades = runner.run_symbol(sym, df)
        if sym_trades:
            all_trades.extend(sym_trades)
            net_r = sum(t["r_result"] for t in sym_trades)
            win_cnt = sum(1 for t in sym_trades if t["r_result"] > 0)
            symbol_stats[sym] = {
                "trades": len(sym_trades),
                "wins": win_cnt,
                "win_rate": round(win_cnt / len(sym_trades) * 100, 1),
                "net_r": round(net_r, 2),
            }

    # Tüm işlemleri tarih sırasına diz
    all_trades.sort(key=lambda x: x["opened_at"])

    # Portföy Bakiyesi İlerlemesi (Bileşik ve Sabit)
    balance_compounding = runner.initial_capital
    balance_fixed = runner.initial_capital
    peak_compounding = balance_compounding
    peak_fixed = balance_fixed
    max_dd_pct = 0.0

    tp2_hits = 0
    be_hits = 0
    sl_hits = 0
    time_exits = 0

    trade_records = []

    for idx, t in enumerate(all_trades, 1):
        r_res = t["r_result"]
        reason = t["close_reason"]

        if reason == "TP2_HIT":
            tp2_hits += 1
        elif reason == "BREAK_EVEN":
            be_hits += 1
        elif reason == "STOP_LOSS":
            sl_hits += 1
        else:
            time_exits += 1

        # 1. Sabit Risk ($200 / 1R)
        dollar_pnl_fixed = r_res * (runner.initial_capital * runner.risk_pct)
        balance_fixed += dollar_pnl_fixed

        # 2. Dinamik Bileşik Risk (%2 of Current Balance)
        risk_dollars_dyn = balance_compounding * runner.risk_pct
        dollar_pnl_dyn = r_res * risk_dollars_dyn
        balance_compounding += dollar_pnl_dyn

        if balance_compounding > peak_compounding:
            peak_compounding = balance_compounding
        dd_compounding = (peak_compounding - balance_compounding) / peak_compounding * 100
        if dd_compounding > max_dd_pct:
            max_dd_pct = dd_compounding

        trade_records.append({
            "idx": idx,
            "date": t["opened_at"],
            "symbol": t["symbol"],
            "strategy": t["strategy"],
            "direction": t["direction"],
            "reason": reason,
            "r_result": r_res,
            "dollar_pnl_fixed": round(dollar_pnl_fixed, 2),
            "dollar_pnl_dyn": round(dollar_pnl_dyn, 2),
            "balance_fixed": round(balance_fixed, 2),
            "balance_dyn": round(balance_compounding, 2),
        })

    total_trades = len(all_trades)
    profitable_trades = tp2_hits + be_hits
    total_net_r = round(sum(t["r_result"] for t in all_trades), 2)
    win_rate = round(profitable_trades / total_trades * 100, 1) if total_trades > 0 else 0.0
    tp2_rate = round(tp2_hits / total_trades * 100, 1) if total_trades > 0 else 0.0

    net_profit_fixed = round(balance_fixed - runner.initial_capital, 2)
    pct_gain_fixed = round((net_profit_fixed / runner.initial_capital) * 100, 1)

    net_profit_dyn = round(balance_compounding - runner.initial_capital, 2)
    pct_gain_dyn = round((net_profit_dyn / runner.initial_capital) * 100, 1)

    # Strateji Ayrımı
    sfp_trades = [t for t in all_trades if "SFP" in t["strategy"]]
    orb_trades = [t for t in all_trades if "ORB" in t["strategy"]]

    sfp_net_r = round(sum(t["r_result"] for t in sfp_trades), 2)
    sfp_wins = sum(1 for t in sfp_trades if t["r_result"] > 0)
    orb_net_r = round(sum(t["r_result"] for t in orb_trades), 2)
    orb_wins = sum(1 for t in orb_trades if t["r_result"] > 0)

    summary = {
        "initial_capital": runner.initial_capital,
        "risk_percentage": f"%{runner.risk_pct * 100:.1f}",
        "total_trades": total_trades,
        "tp2_hits": tp2_hits,
        "be_hits": be_hits,
        "sl_hits": sl_hits,
        "time_exits": time_exits,
        "win_rate": f"%{win_rate}",
        "tp2_rate": f"%{tp2_rate}",
        "total_net_r": f"{total_net_r}R",
        "fixed_model": {
            "risk_per_trade": f"${runner.initial_capital * runner.risk_pct:.2f}",
            "ending_balance": f"${balance_fixed:,.2f}",
            "net_profit_dollar": f"${net_profit_fixed:+,.2f}",
            "net_return_pct": f"%{pct_gain_fixed:+.1f}",
        },
        "compounding_model": {
            "ending_balance": f"${balance_compounding:,.2f}",
            "net_profit_dollar": f"${net_profit_dyn:+,.2f}",
            "net_return_pct": f"%{pct_gain_dyn:+.1f}",
            "max_drawdown_pct": f"%{max_dd_pct:.2f}",
        },
        "strategy_breakdown": {
            "SFP_INSTITUTIONAL": {
                "trades": len(sfp_trades),
                "wins": sfp_wins,
                "win_rate": f"%{round(sfp_wins / len(sfp_trades) * 100, 1)}" if sfp_trades else "0%",
                "net_r": f"{sfp_net_r}R",
            },
            "ORB_LONDON_ONLY": {
                "trades": len(orb_trades),
                "wins": orb_wins,
                "win_rate": f"%{round(orb_wins / len(orb_trades) * 100, 1)}" if orb_trades else "0%",
                "net_r": f"{orb_net_r}R",
            }
        },
        "top_performing_symbols": symbol_stats,
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # JSON Çıktısını diske kaydet
    out_file = Path("data") / "custom_1m_backtest_result.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    run_full_portfolio_simulation()
