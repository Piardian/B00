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
  * Hafta İçi: ORB yalnızca Londra Seansı (07:00 - 11:00 UTC), YALNIZCA FOREX PARİTELERİNDE!
              SFP hem Londra (07:00 - 11:00 UTC) hem New York (13:00 - 17:00 UTC)
  * Hafta Sonu: ORB KAPALI
                SFP yalnızca Kripto paritelerinde açık (07:00-11:00 ve 13:00-17:00 UTC)
- Teyit & Nedensellik Standartları:
  * SFP: Kronolojik Geriye Bakışlı (Lookahead-free: Bar i'de MSS teyidi, emir bar i'de kurulur, yürütme i+1'den başlar)
  * Makro Yönetişim Kapısı (DailyMacroGateTable: DXY, Getiriler, VIX, Hisse ve Kripto Rotasyonu)
  * ORB: Dış sınır korumalı stop loss (Forex-only)
- Periyot: Son 1 Ay (2026-09-11 - 2026-10-11)
"""

import sys
import json
import logging
from datetime import datetime, timezone, timedelta, date
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

from .config import (
    get_asset_sl_buffer,
    is_crypto,
    ENTRY_MODEL,
    REQUIRE_ENTRY_REACTION,
    REQUIRE_PRO_TREND_AAA,
    USE_IFVG_ENTRY,
    REQUIRE_STRUCTURAL_BREAKER,
)
from .entry_mechanics import (
    calculate_ce_entry,
    is_slice_through_candle,
    detect_ifvg_short,
    detect_ifvg_long,
    detect_structural_breaker_short,
    detect_structural_breaker_long,
)
from .macro_gated_3m_backtest import DailyMacroGateTable

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

TIER1_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "NZDUSD", "EURGBP",
    "XAUUSD", "NAS100", "BTCUSD"
]

FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP"
]

EXCLUDED_SYMBOLS = ["GBPJPY", "AUDUSD"]  # Toksik / sahte iğneli parite filtresi


class Custom1MBacktestRunner:
    def __init__(
        self,
        initial_capital: float = 10000.0,
        risk_pct: float = 0.02,
        entry_model: str = ENTRY_MODEL,
        require_reaction: bool = REQUIRE_ENTRY_REACTION,
        use_macro_gate: bool = True,
        require_pro_trend: bool = REQUIRE_PRO_TREND_AAA,
        use_ifvg: bool = USE_IFVG_ENTRY,
        require_breaker: bool = REQUIRE_STRUCTURAL_BREAKER,
        months: int = 1,
    ):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.entry_model = (entry_model or "midpoint").lower()
        self.require_reaction = require_reaction
        self.use_macro_gate = use_macro_gate
        self.require_pro_trend = require_pro_trend
        self.use_ifvg = use_ifvg
        self.require_breaker = require_breaker
        self.months = months
        self.utc_to = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
        if months == 3:
            self.utc_from = datetime(2026, 7, 11, 0, 0, tzinfo=timezone.utc)
        elif months == 6:
            self.utc_from = datetime(2026, 4, 11, 0, 0, tzinfo=timezone.utc)
        elif months == 12:
            self.utc_from = datetime(2025, 10, 11, 0, 0, tzinfo=timezone.utc)
        else:
            self.utc_from = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)

        if self.use_macro_gate:
            self.macro_table = DailyMacroGateTable(self.utc_from.date(), self.utc_to.date())
        else:
            self.macro_table = None

    def fetch_m15_data(self, symbol: str) -> Optional[pd.DataFrame]:
        if not mt5.initialize():
            logger.error("MT5 başlatılamadı!")
            return None

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
        df["weekday"] = df["datetime"].dt.weekday
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

        # ORB Seans Aralıkları (YALNIZCA FOREX PARİTELERİ İÇİN LONDRA 07:00 UTC)
        allow_orb_sym = symbol in FOREX_SYMBOLS
        orb_high = np.zeros(n, dtype=float)
        orb_low = np.zeros(n, dtype=float)
        in_orb_window = np.zeros(n, dtype=bool)

        current_orb_h = 0.0
        current_orb_l = 0.0
        in_sess = False
        sess_expire = 0

        if allow_orb_sym:
            for i in range(n):
                wday = weekdays[i]
                h_val = hours[i]
                m_val = minutes[i]

                if wday in [5, 6]:
                    continue

                if h_val == 7 and m_val == 0:
                    current_orb_h = highs[i]
                    current_orb_l = lows[i]
                    in_sess = True
                    sess_expire = i + 15  # ~3.75 saatlik ORB penceresi (07:15 - 11:00 UTC)
                elif in_sess and i <= sess_expire:
                    orb_high[i] = current_orb_h
                    orb_low[i] = current_orb_l
                    in_orb_window[i] = True
                elif i > sess_expire:
                    in_sess = False

        trades = []
        active_position = None
        cooldown_until = 0

        start_ts = pd.Timestamp(self.utc_from.replace(tzinfo=None))

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

            # --- MEVCUT POZİSYON KONTROLÜ (BAR İÇİ NEDENSEL TAKİP) ---
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
                        r_res = (1.0 * 0.5) + (3.0 * 0.5)
                    elif c_low <= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.0 * 0.5) + (0.0 * 0.5)
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
                orb_session_active = False
            else:
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
                orb_session_active = allow_orb_sym and in_orb_window[i] and (7 <= h_val <= 11)

            pdh = pdhs[i]
            pdl = pdls[i]
            ash = ashs[i]
            asl = asls[i]
            if pdh == 0.0 or pdl == 0.0:
                continue

            # 1. DÜZELTME: Sıkı 4H Trend Uyumu (Grade AAA Zorunluluğu)
            htf_bull = (c_close > ema50s[i] > ema200s[i])
            htf_bear = (c_close < ema50s[i] < ema200s[i])
            if self.require_pro_trend:
                allow_short = htf_bear
                allow_long = htf_bull
            else:
                allow_short = htf_bear if is_momentum else (not htf_bull)
                allow_long = htf_bull if is_momentum else (not htf_bear)

            # MAKRO KAPISI DENETİMİ (DailyMacroGateTable)
            if self.use_macro_gate and self.macro_table:
                cur_dt = pd.to_datetime(dates_raw[i]).to_pydatetime()
                gate_val = self.macro_table.get_gate(cur_dt, symbol)
                if gate_val in ["NEUTRAL_RANGE", "NO_TRADE", "DEFENSIVE_HOLD", "VETO"]:
                    allow_short = False
                    allow_long = False
                elif gate_val == "SHORT_ONLY":
                    allow_long = False
                elif gate_val == "LONG_ONLY":
                    allow_short = False

            sfp_sig = None
            orb_sig = None

            # --- MODEL 1: KURUMSAL SFP + iFVG + BREAKER (LOOKAHEAD-FREE NEDENSEL GERİYE BAKIŞ) ---
            # Bar i: MSS / Breaker teyidini ve iFVG oluşumunu tamamlayan mumdur.
            # j in [i-1, i-2, i-3]: Likidite süpürmesini (sweep) yapan mumdur.
            if sfp_session_active and (allow_short or allow_long):
                # SHORT SFP: Tepe süpürme (j) + Bar i Breaker & iFVG Kırılımı
                if allow_short:
                    for j in [i-1, i-2, i-3]:
                        if j < 25:
                            continue
                        j_rng = max(highs[j] - lows[j], 1e-8)
                        j_u_wick = (highs[j] - max(opens[j], closes[j])) / j_rng
                        if j_u_wick < 0.45:
                            continue

                        j_pdh = pdhs[j]
                        j_ash = ashs[j]
                        sw_hi = False
                        p_name = ""
                        if highs[j] > j_pdh and closes[j] < j_pdh:
                            sw_hi = True
                            p_name = "PDH"
                        elif (7 <= hours[j] <= 11) and j_ash > 0.0 and highs[j] > j_ash and closes[j] < j_ash:
                            sw_hi = True
                            p_name = "ASIAN_HIGH"

                        if not sw_hi:
                            continue

                        peak = highs[j]
                        # Sweep'ten sonra bar i'ye kadar tepenin aşılmadığını kontrol et
                        if any(highs[m] > peak for m in range(j+1, i+1)):
                            continue

                        mss_trig = min(lows[j], lows[j-1])
                        # Bar i'den önce kırılım gerçekleşmemiş olmalı (Bar i ilk kırılım mumudur)
                        if any(closes[m] < mss_trig for m in range(j+1, i)):
                            continue

                        if closes[i] < mss_trig:
                            b_disp = abs(closes[i] - opens[i]) / bar_rng
                            if b_disp >= 0.35:
                                # 2. DÜZELTME: Yapısal Breaker Kırılımı Teyidi
                                if self.require_breaker and not detect_structural_breaker_short(j, i, highs, lows, opens, closes):
                                    continue

                                # 2. DÜZELTME: Inversion FVG (iFVG) %50 CE Giriş Bölgesi
                                target_zone = None
                                if self.use_ifvg:
                                    target_zone = detect_ifvg_short(i, highs, lows, closes, c_atr)
                                else:
                                    has_fvg = (lows[i-2] > highs[i]) and ((lows[i-2] - highs[i]) >= c_atr * 0.08)
                                    if has_fvg:
                                        target_zone = (float(lows[i-2]), float(highs[i]))

                                if target_zone is not None:
                                    grade = "AAA" if htf_bear else "A+"
                                    if self.require_pro_trend and grade != "AAA":
                                        continue

                                    ce_calc = calculate_ce_entry(
                                        direction="SHORT",
                                        peak_or_valley=peak,
                                        trigger_price=mss_trig,
                                        close_price=closes[i],
                                        fvg_range=target_zone,
                                        atr=c_atr,
                                        sl_buffer_atr=sl_buffer_atr,
                                        entry_model=self.entry_model,
                                        tp1_r=1.0,
                                        tp2_r=3.0,
                                    )
                                    sfp_sig = {
                                        "strategy": "SFP_IFVG_BREAKER",
                                        "direction": "SHORT",
                                        "grade": grade,
                                        "entry": ce_calc["entry_price"],
                                        "sl": ce_calc["stop_loss"],
                                        "tp1": ce_calc["tp1"],
                                        "tp2": ce_calc["tp2"],
                                        "risk": ce_calc["risk_distance"],
                                        "zone_low": ce_calc["zone_low"],
                                        "zone_high": ce_calc["zone_high"],
                                        "is_limit": ce_calc["is_limit"],
                                        "pool": p_name,
                                        "trigger_time": dts[i],
                                    }
                                    break

                # LONG SFP: Dip süpürme (j) + Bar i Breaker & iFVG Kırılımı
                if allow_long and sfp_sig is None:
                    for j in [i-1, i-2, i-3]:
                        if j < 25:
                            continue
                        j_rng = max(highs[j] - lows[j], 1e-8)
                        j_l_wick = (min(opens[j], closes[j]) - lows[j]) / j_rng
                        if j_l_wick < 0.45:
                            continue

                        j_pdl = pdls[j]
                        j_asl = asls[j]
                        sw_lo = False
                        p_name = ""
                        if lows[j] < j_pdl and closes[j] > j_pdl:
                            sw_lo = True
                            p_name = "PDL"
                        elif (7 <= hours[j] <= 11) and j_asl > 0.0 and lows[j] < j_asl and closes[j] > j_asl:
                            sw_lo = True
                            p_name = "ASIAN_LOW"

                        if not sw_lo:
                            continue

                        valley = lows[j]
                        if any(lows[m] < valley for m in range(j+1, i+1)):
                            continue

                        mss_trig = max(highs[j], highs[j-1])
                        if any(closes[m] > mss_trig for m in range(j+1, i)):
                            continue

                        if closes[i] > mss_trig:
                            b_disp = abs(closes[i] - opens[i]) / bar_rng
                            if b_disp >= 0.35:
                                # 2. DÜZELTME: Yapısal Breaker Kırılımı Teyidi
                                if self.require_breaker and not detect_structural_breaker_long(j, i, highs, lows, opens, closes):
                                    continue

                                # 2. DÜZELTME: Inversion FVG (iFVG) %50 CE Giriş Bölgesi
                                target_zone = None
                                if self.use_ifvg:
                                    target_zone = detect_ifvg_long(i, highs, lows, closes, c_atr)
                                else:
                                    has_fvg = (lows[i] > highs[i-2]) and ((lows[i] - highs[i-2]) >= c_atr * 0.08)
                                    if has_fvg:
                                        target_zone = (float(highs[i-2]), float(lows[i]))

                                if target_zone is not None:
                                    grade = "AAA" if htf_bull else "A+"
                                    if self.require_pro_trend and grade != "AAA":
                                        continue

                                    ce_calc = calculate_ce_entry(
                                        direction="LONG",
                                        peak_or_valley=valley,
                                        trigger_price=mss_trig,
                                        close_price=closes[i],
                                        fvg_range=target_zone,
                                        atr=c_atr,
                                        sl_buffer_atr=sl_buffer_atr,
                                        entry_model=self.entry_model,
                                        tp1_r=1.0,
                                        tp2_r=3.0,
                                    )
                                    sfp_sig = {
                                        "strategy": "SFP_IFVG_BREAKER",
                                        "direction": "LONG",
                                        "grade": grade,
                                        "entry": ce_calc["entry_price"],
                                        "sl": ce_calc["stop_loss"],
                                        "tp1": ce_calc["tp1"],
                                        "tp2": ce_calc["tp2"],
                                        "risk": ce_calc["risk_distance"],
                                        "zone_low": ce_calc["zone_low"],
                                        "zone_high": ce_calc["zone_high"],
                                        "is_limit": ce_calc["is_limit"],
                                        "pool": p_name,
                                        "trigger_time": dts[i],
                                    }
                                    break

            # Geliştirme 3: Asya Sıkışması (Compression) Kontrolü (ORB İçin)
            asian_range = max(ash - asl, 0.0) if (ash > 0 and asl > 0) else 0.0
            asian_exhausted = (asian_range > c_atr * 0.70) if (c_atr > 0 and asian_range > 0) else False

            # --- MODEL 2: ORB (YALNIZCA FOREX PARİTELERİ LONDRA SEANSI) ---
            if orb_session_active and sfp_sig is None and not asian_exhausted:
                o_h = orb_high[i]
                o_l = orb_low[i]
                vol_ratio = c_vol / max(c_vol_sma, 1e-8)

                # Bullish Breakout
                if allow_long and c_close > o_h and closes[i-1] <= o_h:
                    if vol_ratio >= 2.0:
                        u_wick = (c_high - c_close) / bar_rng
                        if u_wick <= 0.35 and (c_close - c_open) / bar_rng >= 0.40:
                            # Koruyucu SL: Açılış aralığının alt sınırının tamponlu altı (Dar midpoint yerine)
                            ce_calc = calculate_ce_entry(
                                direction="LONG",
                                peak_or_valley=o_l,
                                trigger_price=o_h,
                                close_price=c_close,
                                orb_level=o_h,
                                atr=c_atr,
                                sl_buffer_atr=sl_buffer_atr,
                                entry_model=self.entry_model,
                                tp1_r=1.0,
                                tp2_r=3.0,
                            )
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "LONG",
                                "grade": "A+",
                                "entry": ce_calc["entry_price"],
                                "sl": ce_calc["stop_loss"],
                                "tp1": ce_calc["tp1"],
                                "tp2": ce_calc["tp2"],
                                "risk": ce_calc["risk_distance"],
                                "zone_low": ce_calc["zone_low"],
                                "zone_high": ce_calc["zone_high"],
                                "is_limit": ce_calc["is_limit"],
                                "pool": "LONDON_ORB",
                                "trigger_time": dts[i],
                            }

                # Bearish Breakout
                elif allow_short and c_close < o_l and closes[i-1] >= o_l:
                    if vol_ratio >= 2.0:
                        l_wick = (c_close - c_low) / bar_rng
                        if l_wick <= 0.35 and (c_open - c_close) / bar_rng >= 0.40:
                            # Koruyucu SL: Açılış aralığının üst sınırının tamponlu üstü
                            ce_calc = calculate_ce_entry(
                                direction="SHORT",
                                peak_or_valley=o_h,
                                trigger_price=o_l,
                                close_price=c_close,
                                orb_level=o_l,
                                atr=c_atr,
                                sl_buffer_atr=sl_buffer_atr,
                                entry_model=self.entry_model,
                                tp1_r=1.0,
                                tp2_r=3.0,
                            )
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "SHORT",
                                "grade": "A+",
                                "entry": ce_calc["entry_price"],
                                "sl": ce_calc["stop_loss"],
                                "tp1": ce_calc["tp1"],
                                "tp2": ce_calc["tp2"],
                                "risk": ce_calc["risk_distance"],
                                "zone_low": ce_calc["zone_low"],
                                "zone_high": ce_calc["zone_high"],
                                "is_limit": ce_calc["is_limit"],
                                "pool": "LONDON_ORB",
                                "trigger_time": dts[i],
                            }

            sig = sfp_sig or orb_sig
            if sig is not None:
                entry = sig["entry"]
                sl = sig["sl"]
                direction = sig["direction"]
                risk = sig.get("risk", abs(entry - sl))
                tp1 = sig.get("tp1")
                tp2 = sig.get("tp2")

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
                    "status": "PENDING_LIMIT" if sig.get("is_limit", False) else "OPEN",
                    "zone_low": sig.get("zone_low", min(entry, sl)),
                    "zone_high": sig.get("zone_high", max(entry, sl)),
                    "bars_held": 0,
                    "bars_waiting": 0,
                    "max_wait_bars": 32,
                    "pool": sig.get("pool", ""),
                    "is_weekend": bool(is_weekend),
                }

        return trades


def run_full_portfolio_simulation(
    entry_model: str = ENTRY_MODEL,
    require_reaction: bool = True,
    use_macro_gate: bool = True,
    months: int = 1,
    tier1_only: bool = False,
) -> Dict[str, Any]:
    runner = Custom1MBacktestRunner(
        initial_capital=10000.0,
        risk_pct=0.02,
        entry_model=entry_model,
        require_reaction=require_reaction,
        use_macro_gate=use_macro_gate,
        months=months,
    )
    target_symbols = TIER1_SYMBOLS if tier1_only else SYMBOLS
    logger.info("=" * 70)
    logger.info(f"🌺 BEGONYA 00 - {runner.months} AYLIK KURUMSAL ÖZEL STRATEJİ & PORTFÖY TESTİ 🌺")
    logger.info(f"Evren: {'TIER-1 KURUMSAL (9 Parite)' if tier1_only else 'TAM EVREN (18 Parite)'}")
    logger.info(f"Entry Modeli: {runner.entry_model.upper()} | Reaksiyon Kalkanı: {'AÇIK' if runner.require_reaction else 'KAPALI'}")
    logger.info(f"Makro Kapı Yönetişimi: {'AÇIK (Günlük DXY/Yield/VIX Filtreli)' if runner.use_macro_gate else 'KAPALI'}")
    logger.info(f"Sermaye: ${runner.initial_capital:,.2f} | Risk: %{runner.risk_pct * 100:.1f} ($200 sabit)")
    logger.info("Kurallar: TP1 1.0R (%50 Kâr Al + BE) | TP2 3.0R (Kalan %50)")
    logger.info("Seanslar: Hafta İçi ORB Londra (07-11 UTC, Yalnızca Forex) | SFP Londra + NY (07-11 & 13-17 UTC)")
    logger.info("Hafta Sonu: ORB KAPALI | SFP Kripto Açık (07-11 & 13-17 UTC)")
    logger.info(f"Periyot: {runner.utc_from.strftime('%Y-%m-%d')} - {runner.utc_to.strftime('%Y-%m-%d')}")
    logger.info("=" * 70)

    all_trades = []
    symbol_stats = {}

    for sym in target_symbols:
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

    # Tarihe göre sırala
    all_trades.sort(key=lambda x: x["opened_at"])

    # Portföy Bakiyesi İlerlemesi
    balance_compounding = runner.initial_capital
    balance_fixed = runner.initial_capital
    peak_compounding = balance_compounding
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
            "closed_at": t["closed_at"],
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

    time_travel_trades = sum(1 for t in all_trades if t["closed_at"] <= t["opened_at"])

    # Strateji Ayrımı
    sfp_trades = [t for t in all_trades if "SFP" in t["strategy"]]
    orb_trades = [t for t in all_trades if "ORB" in t["strategy"]]

    sfp_net_r = round(sum(t["r_result"] for t in sfp_trades), 2)
    sfp_wins = sum(1 for t in sfp_trades if t["r_result"] > 0)
    orb_net_r = round(sum(t["r_result"] for t in orb_trades), 2)
    orb_wins = sum(1 for t in orb_trades if t["r_result"] > 0)

    summary = {
        "period": f"{runner.utc_from.strftime('%Y-%m-%d')} - {runner.utc_to.strftime('%Y-%m-%d')}",
        "universe": "TIER1_CORE_9" if tier1_only else "FULL_UNIVERSE_18",
        "entry_model": runner.entry_model.upper(),
        "macro_gate": "ENABLED" if runner.use_macro_gate else "DISABLED",
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
        "time_travel_trades": time_travel_trades,
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
            "ORB_LONDON_FOREX_ONLY": {
                "trades": len(orb_trades),
                "wins": orb_wins,
                "win_rate": f"%{round(orb_wins / len(orb_trades) * 100, 1)}" if orb_trades else "0%",
                "net_r": f"{orb_net_r}R",
            }
        },
        "top_performing_symbols": symbol_stats,
        "trade_log": trade_records,
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))

    out_file = Path("data") / f"custom_{runner.months}m_backtest_result.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # Geriye dönük uyumluluk için varsayılan dosyayı da güncelle
    legacy_file = Path("data") / "custom_1m_backtest_result.json"
    legacy_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Begonya 00 - Kurumsal Özel Strateji & Portföy Testi")
    parser.add_argument("--months", type=int, default=1, choices=[1, 3, 6, 12], help="Test periyodu (ay sayısı: 1, 3, 6, 12)")
    parser.add_argument("--entry-model", choices=["midpoint", "close"], default=ENTRY_MODEL, help="Giriş modeli: midpoint (50% CE) veya close (Market Kapanış)")
    parser.add_argument("--tier1", action="store_true", help="Yalnızca Tier-1 Kurumsal 9 Parite Evrenini test et")
    parser.add_argument("--no-reaction", action="store_true", help="Reaksiyon kalkanını devre dışı bırak")
    parser.add_argument("--no-macro", action="store_true", help="Makro Kapısı filtresini devre dışı bırak")
    args = parser.parse_args()
    run_full_portfolio_simulation(
        entry_model=args.entry_model,
        require_reaction=not args.no_reaction,
        use_macro_gate=not args.no_macro,
        months=args.months,
        tier1_only=args.tier1,
    )
