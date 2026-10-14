"""
🌺 Begonya 00 - 3 Aylık Makro Kapı Onaylı Kurumsal Backtest Motoru
Kullanıcı Talebi:
- Periyot: Son 3 Ay (2026-07-11 - 2026-10-11)
- Başlangıç Sermayesi: $10,000 USD
- İşlem Başına Risk: %2.0 ($200 per 1R sabit ve bileşik dinamik simülasyon)
- TP1: 1.0R (%50 Kâr Alınır, Stop BE'ye çekilir)
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
- MAKRO YÖNETİŞİM GEÇİDİ (KRİTİK TEST KURALI):
  * RANGE BANDINDA İSE (NEUTRAL_RANGE) -> HİÇBİR İŞLEM ALINMAZ (VETO)!
  * SADECE VE SADECE YÖN BELİRTTİYSE:
    - LONG_ONLY -> Yalnızca LONG işlemlere onay verilir.
    - SHORT_ONLY -> Yalnızca SHORT işlemlere onay verilir.
    - DEFENSIVE_HOLD / NO_TRADE / Yön Uyuşmazlığı -> İŞLEM REDDEDİLİR.
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
import yfinance as yf

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .config import get_asset_sl_buffer, is_crypto

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("Begonya00.MacroGated3MBacktest")

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


class DailyMacroGateTable:
    """
    3 Aylık Tarihsel Makro Kapı Tablosu Oluşturucu (Lookahead-free: Günlük bar kapanışıyla hesaplanır).
    Tüm veriler bar açılışından önce kesinleşmiş d-1 makro göstergeleri üzerinden yürütülür.
    """
    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.daily_gates: Dict[date, Dict[str, str]] = {}
        self.daily_evidence: Dict[date, Dict[str, Any]] = {}
        self._build_table()

    def _build_table(self):
        logger.info("📡 Tarihsel Makro Göstergeler İndiriliyor (DXY, US10Y, US02Y, SPX, VIX, Gold, BTC, ETH, SOL)...")
        # Isınma için 50 gün öncesi
        t_from = (self.start_date - timedelta(days=60)).strftime("%Y-%m-%d")
        t_to = (self.end_date + timedelta(days=2)).strftime("%Y-%m-%d")

        tickers = {
            "dxy": "DX-Y.NYB",
            "us10y": "^TNX",
            "us02y": "2YY=F",
            "spx": "^GSPC",
            "vix": "^VIX",
            "gold": "GC=F",
            "brent": "BZ=F",
            "btc": "BTC-USD",
            "eth": "ETH-USD",
            "sol": "SOL-USD"
        }

        series_dict = {}
        for k, ticker in tickers.items():
            try:
                hist = yf.Ticker(ticker).history(start=t_from, end=t_to, interval="1d")
                if not hist.empty:
                    series_dict[k] = hist["Close"]
            except Exception as e:
                logger.warning(f"Makro veri çekilemedi ({ticker}): {e}")

        df_macro = pd.DataFrame(series_dict).ffill().bfill()
        # Eksik makro sütunlar için güvenli sentetik fallback kalkanı
        default_cols = {
            "dxy": 103.5, "us10y": 4.10, "us02y": 3.90, "spx": 5800.0,
            "vix": 16.5, "gold": 2650.0, "brent": 76.0, "btc": 63000.0,
            "eth": 2500.0, "sol": 150.0
        }
        for col, default_val in default_cols.items():
            if col not in df_macro.columns:
                if col == "us02y" and "us10y" in df_macro.columns:
                    df_macro[col] = df_macro["us10y"] * 0.95
                else:
                    df_macro[col] = default_val

        df_macro["date"] = df_macro.index.date
        df_macro.drop_duplicates(subset=["date"], keep="last", inplace=True)
        df_macro.set_index("date", inplace=True)

        # Makro Momentum ve Farklar
        df_macro["dxy_roc_20d"] = df_macro["dxy"].pct_change(20) * 100
        df_macro["dxy_roc_5d"] = df_macro["dxy"].pct_change(5) * 100
        df_macro["delta_10y_5d"] = (df_macro["us10y"] - df_macro["us10y"].shift(5)) * 100
        df_macro["delta_02y_5d"] = (df_macro["us02y"] - df_macro["us02y"].shift(5)) * 100
        df_macro["real_yield"] = df_macro["us10y"] - 2.30  # Sentetik reel getiri
        df_macro["spx_sma50"] = df_macro["spx"].rolling(50).mean()
        df_macro["gold_roc_5d"] = df_macro["gold"].pct_change(5) * 100
        df_macro["brent_roc_20d"] = df_macro["brent"].pct_change(20) * 100
        df_macro["btc_roc_20d"] = df_macro["btc"].pct_change(20) * 100
        df_macro["btc_roc_5d"] = df_macro["btc"].pct_change(5) * 100
        df_macro["eth_btc_ratio"] = df_macro["eth"] / df_macro["btc"]
        df_macro["eth_btc_roc_5d"] = df_macro["eth_btc_ratio"].pct_change(5) * 100
        df_macro["sol_btc_ratio"] = df_macro["sol"] / df_macro["btc"]
        df_macro["sol_btc_roc_5d"] = df_macro["sol_btc_ratio"].pct_change(5) * 100

        # Her gün için kesinleşmiş (d-1 kapanışına dayalı) Deterministik Kapıları hesapla
        all_dates = pd.date_range(self.start_date, self.end_date, freq="D").date

        for cur_date in all_dates:
            # Lookahead-free: Güncel gün için karar alırken, en son tamamlanmış takvim gününün verisini kullan
            prior_dates = [d for d in df_macro.index if d < cur_date]
            if not prior_dates:
                continue
            as_of_date = max(prior_dates)
            row = df_macro.loc[as_of_date]

            dxy_20 = float(row.get("dxy_roc_20d", 0.0))
            dxy_5 = float(row.get("dxy_roc_5d", 0.0))
            d_02y_5d = float(row.get("delta_02y_5d", 0.0))
            d_10y_5d = float(row.get("delta_10y_5d", 0.0))
            real_y = float(row.get("real_yield", 2.0))
            vix_v = float(row.get("vix", 16.0))
            spx_v = float(row.get("spx", 5000.0))
            spx_sma = float(row.get("spx_sma50", 5000.0))
            gold_5 = float(row.get("gold_roc_5d", 0.0))
            brent_20 = float(row.get("brent_roc_20d", 0.0))
            btc_20 = float(row.get("btc_roc_20d", 0.0))
            btc_5 = float(row.get("btc_roc_5d", 0.0))
            eth_btc_5 = float(row.get("eth_btc_roc_5d", 0.0))
            sol_btc_5 = float(row.get("sol_btc_roc_5d", 0.0))

            # 1. Para Birimi Güç Puanları (3-Faktörlü Model - metrics_legacy.py)
            usd_score = 1 if (d_02y_5d >= 5.0 or dxy_5 > 0.4) else (-1 if (d_02y_5d <= -5.0 or dxy_5 < -0.4) else 0)
            jpy_score = 1 if vix_v >= 22.0 else (-1 if vix_v < 17.0 else 0)
            chf_score = 1 if (vix_v >= 22.0 or gold_5 > 1.0) else (-1 if vix_v < 17.0 else 0)
            eur_score = -1 if dxy_20 > 0.5 else (1 if dxy_20 < -0.5 else 0)
            gbp_score = 1 if (dxy_5 > 0 and vix_v < 18.0) else (-1 if dxy_5 < 0 else 0)
            aud_score = 1 if (vix_v < 17.0 and gold_5 > 0) else (-1 if vix_v >= 20.0 else 0)
            cad_score = 1 if brent_20 > 2.0 else (-1 if brent_20 < -2.0 else 0)
            nzd_score = aud_score

            def _calc_gate(base_s: int, quote_s: int, high_thresh: bool = False) -> str:
                diff = base_s - quote_s
                th = 2 if high_thresh else 1
                if diff >= th:
                    return "LONG_ONLY"
                elif diff <= -th:
                    return "SHORT_ONLY"
                return "NEUTRAL_RANGE"

            # 2. Forex Kapıları
            gates = {}
            # EURUSD
            if dxy_20 > 0.5:
                gates["EURUSD"] = "SHORT_ONLY"
            elif dxy_20 < -0.5:
                gates["EURUSD"] = "LONG_ONLY"
            else:
                gates["EURUSD"] = "NEUTRAL_RANGE"

            gates["GBPUSD"] = _calc_gate(gbp_score, usd_score)
            gates["USDJPY"] = _calc_gate(usd_score, jpy_score)
            gates["USDCHF"] = _calc_gate(usd_score, chf_score)
            gates["USDCAD"] = _calc_gate(usd_score, cad_score)
            gates["NZDUSD"] = _calc_gate(nzd_score, usd_score)
            gates["EURJPY"] = _calc_gate(eur_score, jpy_score)
            gates["EURGBP"] = _calc_gate(eur_score, gbp_score, high_thresh=True)

            # 3. Emtialar & Endeksler
            # XAUUSD (Gold)
            gold_bull = (real_y < 1.90) + (dxy_20 < -0.5) + (vix_v >= 20.0)
            gold_bear = (real_y >= 2.20) + (dxy_20 > 0.5)
            if gold_bull >= 2 and gold_bear == 0:
                gates["XAUUSD"] = "LONG_ONLY"
            elif gold_bear >= 2:
                gates["XAUUSD"] = "SHORT_ONLY"
            else:
                gates["XAUUSD"] = "NEUTRAL_RANGE"

            # SP500, NAS100, US30
            equity_bull = (spx_v > spx_sma) and (vix_v < 18.0)
            equity_bear = vix_v >= 24.0
            if equity_bull and not equity_bear:
                eq_gate = "LONG_ONLY"
            elif equity_bear:
                eq_gate = "SHORT_ONLY"
            else:
                eq_gate = "NEUTRAL_RANGE"

            gates["SP500"] = eq_gate
            gates["NAS100"] = eq_gate
            gates["US30"] = eq_gate

            # 4. Kripto Kapıları (BTC & Altcoin Rotasyonu)
            # BTC Gate
            btc_bull_factors = (dxy_20 < -0.5) + (spx_v > spx_sma) + (btc_20 > 0.0)
            btc_bear_factors = (dxy_20 > 0.5) + (vix_v >= 22.0) + (btc_20 < -5.0)
            if btc_bull_factors >= 2 and btc_bear_factors == 0:
                btc_g = "LONG_ONLY"
            elif btc_bear_factors >= 2:
                btc_g = "SHORT_ONLY"
            else:
                btc_g = "NEUTRAL_RANGE"

            gates["BTCUSD"] = btc_g

            # Altcoin Rotasyonu (ETH, SOL, LTC, XRP, DOGE):
            # Kural: BTC "LONG_ONLY" DEĞİLSE altcoinler ASLA LONG olamaz! (NEUTRAL_RANGE kalır)
            for alt in ["ETHUSD", "SOLUSD", "LTCUSD", "XRPUSD", "DOGUSD"]:
                if btc_g == "LONG_ONLY":
                    # Göreli güç kontrolü
                    rel_roc = sol_btc_5 if "SOL" in alt else (eth_btc_5 if "ETH" in alt else btc_5)
                    if rel_roc > 0:
                        gates[alt] = "LONG_ONLY"
                    else:
                        gates[alt] = "NEUTRAL_RANGE"
                elif btc_g == "SHORT_ONLY":
                    gates[alt] = "SHORT_ONLY"
                else:
                    gates[alt] = "NEUTRAL_RANGE"

            self.daily_gates[cur_date] = gates
            self.daily_evidence[cur_date] = {
                "dxy_20d": dxy_20,
                "dxy_5d": dxy_5,
                "vix": vix_v,
                "real_yield": real_y,
                "btc_gate": btc_g,
                "eur_gate": gates.get("EURUSD"),
                "as_of_date": str(as_of_date),
            }

        logger.info(f"✅ {len(self.daily_gates)} takvim günü için günlük makro kapıları başarıyla oluşturuldu.")

    def get_gate(self, dt_val: datetime, symbol: str) -> str:
        d = dt_val.date()
        day_gates = self.daily_gates.get(d)
        if not day_gates:
            # Fallback en yakın güne
            available = [k for k in self.daily_gates.keys() if k <= d]
            if available:
                day_gates = self.daily_gates[max(available)]
            else:
                return "NEUTRAL_RANGE"
        return day_gates.get(symbol, "NEUTRAL_RANGE")


class MacroGated3MBacktestRunner:
    def __init__(self, initial_capital: float = 10000.0, risk_pct: float = 0.02):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.utc_to = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
        self.utc_from = datetime(2026, 7, 11, 0, 0, tzinfo=timezone.utc)
        self.macro_table = DailyMacroGateTable(self.utc_from.date(), self.utc_to.date())

    def fetch_m15_data(self, symbol: str) -> Optional[pd.DataFrame]:
        if not mt5.initialize():
            logger.error("MT5 başlatılamadı!")
            return None

        # 25 gün öncesinden ısınma periyodu (4H HTF EMA ve pivotlar için)
        warmup_from = self.utc_from - timedelta(days=25)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, warmup_from, self.utc_to)
        if rates is None or len(rates) < 1000:
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

    def run_symbol_simulation(self, symbol: str, df: pd.DataFrame, use_macro_gate: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        if symbol in EXCLUDED_SYMBOLS:
            return [], {}

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
        dt_objs = df["datetime"].dt.to_pydatetime()
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

            if wday in [5, 6]:
                continue

            if h_val == 7 and m_val == 0:
                current_orb_h = highs[i]
                current_orb_l = lows[i]
                in_sess = True
                sess_expire = i + 15
            elif in_sess and i <= sess_expire:
                orb_high[i] = current_orb_h
                orb_low[i] = current_orb_l
                in_orb_window[i] = True
            elif i > sess_expire:
                in_sess = False

        trades = []
        active_position = None
        cooldown_until = 0

        gate_veto_stats = {
            "VETO_MACRO_RANGE": 0,
            "VETO_DIRECTION_MISMATCH": 0,
            "APPROVED": 0
        }

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
            cur_dt = dt_objs[i]

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
            if bar_raw < start_ts:
                continue

            if i < cooldown_until:
                continue

            # --- SEANS & GÜN KURALLARI ---
            is_weekend = wday in [5, 6]

            if is_weekend:
                if not is_crypto_sym:
                    continue
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
                orb_session_active = False
            else:
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
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

            # --- MODEL 1: KURUMSAL SFP (MSS + FVG + Volume Anomaly) ---
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

                # SHORT SFP
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
                                "trigger_dt": dt_objs[entry_idx],
                            }

                # LONG SFP
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
                                "trigger_dt": dt_objs[entry_idx],
                            }

            # --- MODEL 2: ORB BREAKOUT (YALNIZCA LONDRA SEANSI) ---
            if orb_session_active and sfp_sig is None:
                o_h = orb_high[i]
                o_l = orb_low[i]
                vol_ratio = c_vol / max(c_vol_sma, 1e-8)

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
                                "trigger_dt": cur_dt,
                            }
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
                                "trigger_dt": cur_dt,
                            }

            sig = sfp_sig or orb_sig
            if sig is not None:
                sig_dt = sig["trigger_dt"]
                direction = sig["direction"]
                macro_gate = self.macro_table.get_gate(sig_dt, symbol)

                # --- MAKRO KAPISI DENETİMİ (KULLANICI TALEBİ) ---
                if use_macro_gate:
                    # 1. RANGE BANDINDA İSE ASLA İŞLEM ALINMAZ!
                    if macro_gate in ["NEUTRAL_RANGE", "NO_TRADE", "DEFENSIVE_HOLD", "VETO"]:
                        gate_veto_stats["VETO_MACRO_RANGE"] += 1
                        continue  # REDDEDİLDİ (İşlem almaz)

                    # 2. YÖN DENETİMİ: Sadece Yön Belirttiyse ve Sinyalle Uyuşuyorsa Alır!
                    if direction == "LONG" and macro_gate != "LONG_ONLY":
                        gate_veto_stats["VETO_DIRECTION_MISMATCH"] += 1
                        continue  # REDDEDİLDİ (Short gate'te Long sinyali)

                    if direction == "SHORT" and macro_gate != "SHORT_ONLY":
                        gate_veto_stats["VETO_DIRECTION_MISMATCH"] += 1
                        continue  # REDDEDİLDİ (Long gate'te Short sinyali)

                    gate_veto_stats["APPROVED"] += 1

                entry = sig["entry"]
                sl = sig["sl"]

                if direction == "LONG":
                    risk = max(entry - sl, c_atr * 0.20, entry * 0.001)
                    tp1 = entry + (risk * 1.0)
                    tp2 = entry + (risk * 3.0)
                else:
                    risk = max(sl - entry, c_atr * 0.20, entry * 0.001)
                    tp1 = entry - (risk * 1.0)
                    tp2 = entry - (risk * 3.0)

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
                    "macro_gate": macro_gate,
                    "is_weekend": bool(is_weekend),
                }

        return trades, gate_veto_stats


def run_dual_3m_backtest():
    runner = MacroGated3MBacktestRunner(initial_capital=10000.0, risk_pct=0.02)
    logger.info("=" * 80)
    logger.info("🌺 BEGONYA 00 - 3 AYLIK MAKRO KAPILI vs HAM STRATEJİ KARŞILAŞTIRMA TESTİ 🌺")
    logger.info(f"Sermaye: ${runner.initial_capital:,.2f} | Risk: %{runner.risk_pct * 100:.1f} ($200 sabit ve dinamik)")
    logger.info("Hedefler: TP1 1.0R (%50 Kâr Al + BE) | TP2 3.0R (Kalan %50 Kâr Al)")
    logger.info("Kural: Range Bandındaysa (NEUTRAL_RANGE) -> İŞLEM YOK. Yalnızca Yön Belirttiyse -> İŞLEM VAR!")
    logger.info(f"Periyot: {runner.utc_from.strftime('%Y-%m-%d')} - {runner.utc_to.strftime('%Y-%m-%d')} (3 Ay / 92 Gün)")
    logger.info("=" * 80)

    cached_dfs = {}
    for sym in SYMBOLS:
        df = runner.fetch_m15_data(sym)
        if df is not None:
            cached_dfs[sym] = df
            logger.info(f"✔ {sym}: {len(df)} M15 barı yüklendi.")

    # 1. MAKRO KAPILI MODEL (Kullanıcının İstediği Katı Yön Onaylı Model)
    logger.info("\n🚀 1. SİMÜLASYON: MAKRO KAPILI MODEL (Yalnızca Yön Onayında İşlem, Range'de 0 İşlem)...")
    gated_trades = []
    gated_stats_by_sym = {}
    total_vetos = {"VETO_MACRO_RANGE": 0, "VETO_DIRECTION_MISMATCH": 0, "APPROVED": 0}

    for sym, df in cached_dfs.items():
        t_list, v_stats = runner.run_symbol_simulation(sym, df, use_macro_gate=True)
        gated_trades.extend(t_list)
        for k in total_vetos:
            total_vetos[k] += v_stats.get(k, 0)
        if t_list:
            net_r = sum(t["r_result"] for t in t_list)
            wins = sum(1 for t in t_list if t["r_result"] > 0)
            gated_stats_by_sym[sym] = {
                "trades": len(t_list),
                "wins": wins,
                "win_rate": round(wins / len(t_list) * 100, 1),
                "net_r": round(net_r, 2)
            }

    # 2. HAM / MAKRO KAPISIZ MODEL (Baseline Karşılaştırması İçin)
    logger.info("🚀 2. SİMÜLASYON: HAM MODEL (Makro Kapı Filtresi Olmadan)...")
    ungated_trades = []
    ungated_stats_by_sym = {}

    for sym, df in cached_dfs.items():
        t_list, _ = runner.run_symbol_simulation(sym, df, use_macro_gate=False)
        ungated_trades.extend(t_list)
        if t_list:
            net_r = sum(t["r_result"] for t in t_list)
            wins = sum(1 for t in t_list if t["r_result"] > 0)
            ungated_stats_by_sym[sym] = {
                "trades": len(t_list),
                "wins": wins,
                "win_rate": round(wins / len(t_list) * 100, 1),
                "net_r": round(net_r, 2)
            }

    # İşlemleri tarihe göre sırala
    gated_trades.sort(key=lambda x: x["opened_at"])
    ungated_trades.sort(key=lambda x: x["opened_at"])

    # Metrik Hesaplamaları
    def calc_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not trades:
            return {
                "total_trades": 0, "win_rate": 0.0, "net_r": 0.0,
                "tp2_count": 0, "be_count": 0, "sl_count": 0,
                "fixed_balance": 10000.0, "compounding_balance": 10000.0,
                "fixed_return_pct": 0.0, "compounding_return_pct": 0.0,
                "max_drawdown_pct": 0.0
            }
        tp2_cnt = sum(1 for t in trades if t["close_reason"] == "TP2_HIT")
        be_cnt = sum(1 for t in trades if t["close_reason"] == "BREAK_EVEN")
        sl_cnt = sum(1 for t in trades if t["close_reason"] == "STOP_LOSS")
        net_r = sum(t["r_result"] for t in trades)
        win_rate = (tp2_cnt + be_cnt) / len(trades) * 100

        # Sabit Bakiye: $200 per R
        fixed_bal = 10000.0 + (net_r * 200.0)

        # Bileşik Bakiye & Drawdown
        comp_bal = 10000.0
        peak = comp_bal
        max_dd = 0.0

        for t in trades:
            r = t["r_result"]
            pnl = comp_bal * (runner.risk_pct * r)
            comp_bal += pnl
            if comp_bal > peak:
                peak = comp_bal
            dd = (peak - comp_bal) / peak * 100
            if dd > max_dd:
                max_dd = dd

        return {
            "total_trades": len(trades),
            "tp2_count": tp2_cnt,
            "be_count": be_cnt,
            "sl_count": sl_cnt,
            "win_rate": round(win_rate, 1),
            "pure_tp2_rate": round(tp2_cnt / len(trades) * 100, 1),
            "net_r": round(net_r, 2),
            "fixed_balance": round(fixed_bal, 2),
            "compounding_balance": round(comp_bal, 2),
            "fixed_return_pct": round((fixed_bal - 10000.0) / 100.0, 2),
            "compounding_return_pct": round((comp_bal - 10000.0) / 100.0, 2),
            "max_drawdown_pct": round(max_dd, 2)
        }

    gated_res = calc_metrics(gated_trades)
    ungated_res = calc_metrics(ungated_trades)

    # Varlık Sınıfı Kırılımı (Makro Kapılı)
    asset_breakdown = {"Forex": {"trades": 0, "net_r": 0.0, "wins": 0}, "Metals_Indices": {"trades": 0, "net_r": 0.0, "wins": 0}, "Crypto": {"trades": 0, "net_r": 0.0, "wins": 0}}
    for t in gated_trades:
        sym = t["symbol"]
        r = t["r_result"]
        w = 1 if r > 0 else 0
        if is_crypto(sym):
            cat = "Crypto"
        elif sym in ["XAUUSD", "NAS100", "SP500", "US30"]:
            cat = "Metals_Indices"
        else:
            cat = "Forex"
        asset_breakdown[cat]["trades"] += 1
        asset_breakdown[cat]["net_r"] += r
        asset_breakdown[cat]["wins"] += w

    for cat in asset_breakdown:
        cnt = asset_breakdown[cat]["trades"]
        if cnt > 0:
            asset_breakdown[cat]["win_rate"] = round(asset_breakdown[cat]["wins"] / cnt * 100, 1)
            asset_breakdown[cat]["net_r"] = round(asset_breakdown[cat]["net_r"], 2)

    # Sonuçları JSON olarak kaydet
    final_output = {
        "period": "2026-07-11 to 2026-10-11",
        "initial_capital": 10000.0,
        "risk_per_trade_pct": 2.0,
        "macro_gate_rules": {
            "neutral_range_behavior": "STRICT_NO_TRADE (VETO)",
            "long_behavior": "APPROVED_ONLY_IF_LONG_ONLY",
            "short_behavior": "APPROVED_ONLY_IF_SHORT_ONLY"
        },
        "veto_stats": total_vetos,
        "macro_gated_results": gated_res,
        "ungated_baseline_results": ungated_res,
        "asset_breakdown": asset_breakdown,
        "symbol_performance": gated_stats_by_sym,
        "sample_gated_trades": gated_trades[:15]
    }

    out_file = Path("data/macro_gated_3m_result.json")
    out_file.write_text(json.dumps(final_output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"\n💾 Sonuçlar kaydedildi: {out_file.resolve()}")

    # Konsol Karne Çıktısı
    print("\n" + "=" * 80)
    print("🌺 BEGONYA 00 - 3 AYLIK MAKRO KAPILI OTONOM TEST ZİL KARNESİ 🌺")
    print("=" * 80)
    print(f"💰 Başlangıç Sermayesi: ${runner.initial_capital:,.2f} | Risk: %2.0 ($200 per 1R)")
    print(f"⏱️ Test Periyodu: 2026-07-11 - 2026-10-11 (3 Ay / Tam 92 Gün)")
    print("🛡️ Makro Kuralı: Range Bandında ASLA İşlem Yok. Yalnızca Yön Onayında İşlem Alındı.")
    print("-" * 80)
    print(f"📊 FİLTRE & VETO İSTATİSTİĞİ:")
    print(f"  • Toplam Üretilen Ham Sinyal: {total_vetos['APPROVED'] + total_vetos['VETO_MACRO_RANGE'] + total_vetos['VETO_DIRECTION_MISMATCH']}")
    print(f"  • 🚫 Range Bandı Veto (NEUTRAL_RANGE): {total_vetos['VETO_MACRO_RANGE']} sinyal engellendi!")
    print(f"  • 🚫 Yön Uyuşmazlığı Veto (Ters Yön): {total_vetos['VETO_DIRECTION_MISMATCH']} sinyal engellendi!")
    print(f"  • ✅ Makro Geçidinden Onay Alan: {total_vetos['APPROVED']} işlem gerçekleşti.")
    print("-" * 80)
    print(f"🏆 KARŞILAŞTIRMA TABLOSU (HAM vs MAKRO KAPILI):")
    print(f"{'Metrik':<30} | {'Ham Model (Kapısız)':<22} | {'Makro Kapılı Model':<22}")
    print("-" * 80)
    print(f"{'Toplam İşlem Sayısı':<30} | {ungated_res['total_trades']:<22} | {gated_res['total_trades']:<22}")
    print(f"{'Kazanma Oranı (Win Rate)':<30} | %{ungated_res['win_rate']:<21} | %{gated_res['win_rate']:<21}")
    print(f"{'Tam Hedef (TP2 +2.0R)':<30} | {ungated_res['tp2_count']} (%{ungated_res['pure_tp2_rate']}){'':<10} | {gated_res['tp2_count']} (%{gated_res['pure_tp2_rate']})")
    print(f"{'Başabaş Koruma (BE +0.5R)':<30} | {ungated_res['be_count']:<22} | {gated_res['be_count']:<22}")
    print(f"{'Zarar Durdur (SL -1.0R)':<30} | {ungated_res['sl_count']:<22} | {gated_res['sl_count']:<22}")
    print(f"{'Toplam Net R':<30} | {ungated_res['net_r']:+.2f}R{'':<17} | {gated_res['net_r']:+.2f}R")
    print(f"{'Sabit Bakiye ($200/R)':<30} | ${ungated_res['fixed_balance']:,.2f} (%{ungated_res['fixed_return_pct']:+.1f}){'':<5} | ${gated_res['fixed_balance']:,.2f} (%{gated_res['fixed_return_pct']:+.1f})")
    print(f"{'Bileşik Bakiye (%2/R)':<30} | ${ungated_res['compounding_balance']:,.2f} (%{ungated_res['compounding_return_pct']:+.1f}){'':<3} | ${gated_res['compounding_balance']:,.2f} (%{gated_res['compounding_return_pct']:+.1f})")
    print(f"{'Maksimum Drawdown (DD)':<30} | %{ungated_res['max_drawdown_pct']:<21} | %{gated_res['max_drawdown_pct']:<21}")
    print("=" * 80)


if __name__ == "__main__":
    run_dual_3m_backtest()
