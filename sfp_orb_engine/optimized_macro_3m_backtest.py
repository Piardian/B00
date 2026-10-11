"""
🌺 Begonya 00 - Optimize Edilmiş 3 Aylık Makro Kapılı Kurumsal Backtest
Kullanıcı Ayarları ve Optimizasyonlar:
1. Varlık Havuzu: Yalnızca Forex Majörler/Çaprazlar + Kaliteli Kriptolar (BTC, ETH, SOL, XRP).
   Toksik Endeksler (US30, SP500, NAS100), Altın (XAUUSD) ve Memecoinler (DOGE, LTC) ÇIKARILDI!
2. Model: YALNIZCA SFP (Swing Failure Pattern + Hacim Anomalisi + MSS + FVG).
   Zarar üreten London ORB TAMAMEN KAPATILDI!
3. Risk & Kâr Seviyeleri:
   - Başlangıç Sermayesi: $10,000 USD
   - İşlem Başına Risk: %2.0 ($200 per 1R sabit ve dinamik bileşik)
   - TP1: 1.0R (%50 Kâr Alınır, Stop Başabaşa / BE Çekilir)
   - TP2: 2.0R (Kalan %50 Kâr Alınır - Manyetik Likidite)
   * Kazanç Mantığı:
     - TP2_HIT: +1.5R Net (+%3.0 / +$300)
     - BREAK_EVEN: +0.5R Net (+%1.0 / +$100)
     - STOP_LOSS: -1.0R Net (-%2.0 / -$200)
4. Makro Yönetişim Kuralı:
   - Range Bandındaysa (NEUTRAL_RANGE) -> 0 İŞLEM (VETO)!
   - Sadece Yön Belirttiğinde (LONG_ONLY -> Long, SHORT_ONLY -> Short) -> İŞLEM AÇILIR!
5. Periyot: Son 3 Ay (2026-07-11 - 2026-10-11)
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
logger = logging.getLogger("Begonya00.Optimized3MBacktest")

OPTIMIZED_SYMBOLS = [
    # Forex Majörler & Kaliteli Çaprazlar
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    # Kaliteli Kripto Majörleri
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"
]


class Optimized3MBacktestRunner:
    def __init__(self, initial_capital: float = 10000.0, risk_pct: float = 0.02, tp2_rr: float = 2.0):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.tp2_rr = tp2_rr
        self.utc_to = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
        self.utc_from = datetime(2026, 7, 11, 0, 0, tzinfo=timezone.utc)
        self.macro_table = DailyMacroGateTable(self.utc_from.date(), self.utc_to.date())

    def fetch_m15_data(self, symbol: str) -> Optional[pd.DataFrame]:
        if not mt5.initialize():
            logger.error("MT5 başlatılamadı!")
            return None

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

        # 4H EMA eşdeğeri (200 ve 800 M15 barı)
        df["htf_ema50"] = df["close"].ewm(span=200, adjust=False).mean()
        df["htf_ema200"] = df["close"].ewm(span=800, adjust=False).mean()

        # ATR (14)
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

    def run_simulation(self, symbol: str, df: pd.DataFrame, use_macro_gate: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        display_sym = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 and symbol.isalpha() else symbol
        sl_buffer_atr = get_asset_sl_buffer(display_sym)
        is_crypto_sym = is_crypto(symbol)
        is_momentum = symbol in ["BTCUSD", "ETHUSD"]

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
        dts = df["datetime"].dt.strftime("%Y-%m-%d %H:%M").values
        dt_objs = df["datetime"].dt.to_pydatetime()
        dates_raw = df["datetime"].values

        trades = []
        active_position = None
        cooldown_until = 0

        gate_stats = {
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
                        # %50 @ 1.0R + %50 @ TP2_RR
                        r_res = (1.0 * 0.5) + (self.tp2_rr * 0.5)
                    elif c_low <= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.0 * 0.5) + (0.0 * 0.5)  # +0.5R
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
                        r_res = (1.0 * 0.5) + (self.tp2_rr * 0.5)
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

            # Seans Pencereleri: SFP hem Londra (07-11 UTC) hem New York (13-17 UTC)
            is_weekend = wday in [5, 6]
            if is_weekend:
                if not is_crypto_sym:
                    continue
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
            else:
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)

            if not sfp_session_active:
                continue

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

            # SFP Fitil ve Likidite Havuzu Tespiti
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

            # SHORT SFP (MSS Teyidi + FVG)
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
                    grade = "AAA" if (htf_bear and has_fvg) else ("A+" if (htf_bear or has_fvg) else "A")

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

            # LONG SFP (MSS Teyidi + FVG)
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
                    grade = "AAA" if (htf_bull and has_fvg) else ("A+" if (htf_bull or has_fvg) else "A")

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

            if sfp_sig is not None:
                sig_dt = sfp_sig["trigger_dt"]
                direction = sfp_sig["direction"]
                macro_gate = self.macro_table.get_gate(sig_dt, symbol)

                # MAKRO KAPISI SÜZGECİ
                if use_macro_gate:
                    # 1. Range Bandındaysa Asla İşlem Alınmaz!
                    if macro_gate in ["NEUTRAL_RANGE", "NO_TRADE", "DEFENSIVE_HOLD", "VETO"]:
                        gate_stats["VETO_MACRO_RANGE"] += 1
                        continue

                    # 2. Yön Uyuşmazlığı Vetosu
                    if direction == "LONG" and macro_gate != "LONG_ONLY":
                        gate_stats["VETO_DIRECTION_MISMATCH"] += 1
                        continue

                    if direction == "SHORT" and macro_gate != "SHORT_ONLY":
                        gate_stats["VETO_DIRECTION_MISMATCH"] += 1
                        continue

                    gate_stats["APPROVED"] += 1

                entry = sfp_sig["entry"]
                sl = sfp_sig["sl"]

                if direction == "LONG":
                    risk = max(entry - sl, c_atr * 0.20, entry * 0.001)
                    tp1 = entry + (risk * 1.0)
                    tp2 = entry + (risk * self.tp2_rr)
                else:
                    risk = max(sl - entry, c_atr * 0.20, entry * 0.001)
                    tp1 = entry - (risk * 1.0)
                    tp2 = entry - (risk * self.tp2_rr)

                active_position = {
                    "symbol": symbol,
                    "strategy": sfp_sig["strategy"],
                    "direction": direction,
                    "grade": sfp_sig["grade"],
                    "opened_at": sfp_sig["trigger_time"],
                    "entry": entry,
                    "original_sl": sl,
                    "current_sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "risk_pips": risk,
                    "rr_ratio": self.tp2_rr,
                    "status": "OPEN",
                    "bars_held": 0,
                    "pool": sfp_sig.get("pool", ""),
                    "macro_gate": macro_gate,
                    "is_weekend": bool(is_weekend),
                }

        return trades, gate_stats


def run_optimized_comparison():
    runner_tp2 = Optimized3MBacktestRunner(initial_capital=10000.0, risk_pct=0.02, tp2_rr=2.0)
    runner_tp3 = Optimized3MBacktestRunner(initial_capital=10000.0, risk_pct=0.02, tp2_rr=3.0)

    logger.info("=" * 80)
    logger.info("🌺 BEGONYA 00 - OPTİMİZE EDİLMİŞ 3 AYLIK MAKRO TESTİ (SFP ONLY + TEMİZ SEPET) 🌺")
    logger.info(f"Sermaye: $10,000.00 | Risk: %2.0 ($200 per 1R) | Periyot: 2026-07-11 - 2026-10-11")
    logger.info("Filtreler: ORB Kapalı | Endeksler/Altın/Memecoin Hariç | Range Bandı Vetosu Aktif")
    logger.info("=" * 80)

    # Verileri yükle
    dfs = {}
    for sym in OPTIMIZED_SYMBOLS:
        df = runner_tp2.fetch_m15_data(sym)
        if df is not None:
            dfs[sym] = df
            logger.info(f"✔ {sym}: {len(df)} M15 barı yüklendi.")

    # 1. OPTİMİZE MODEL (TP2 = 2.0R, Makro Kapılı)
    opt_trades_2r = []
    vetos_2r = {"VETO_MACRO_RANGE": 0, "VETO_DIRECTION_MISMATCH": 0, "APPROVED": 0}
    for sym, df in dfs.items():
        t_l, v_s = runner_tp2.run_simulation(sym, df, use_macro_gate=True)
        opt_trades_2r.extend(t_l)
        for k in vetos_2r:
            vetos_2r[k] += v_s.get(k, 0)

    # 2. KARŞILAŞTIRMA (TP2 = 3.0R, Makro Kapılı)
    opt_trades_3r = []
    for sym, df in dfs.items():
        t_l, _ = runner_tp3.run_simulation(sym, df, use_macro_gate=True)
        opt_trades_3r.extend(t_l)

    # 3. HAM MODEL (TP2 = 2.0R, Kapısız)
    ungated_trades_2r = []
    for sym, df in dfs.items():
        t_l, _ = runner_tp2.run_simulation(sym, df, use_macro_gate=False)
        ungated_trades_2r.extend(t_l)

    opt_trades_2r.sort(key=lambda x: x["opened_at"])
    opt_trades_3r.sort(key=lambda x: x["opened_at"])
    ungated_trades_2r.sort(key=lambda x: x["opened_at"])

    def calc_metrics(trades: List[Dict[str, Any]], tp2_target: float = 2.0) -> Dict[str, Any]:
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0, "net_r": 0.0, "fixed_balance": 10000.0, "compounding_balance": 10000.0}
        tp2_cnt = sum(1 for t in trades if t["close_reason"] == "TP2_HIT")
        be_cnt = sum(1 for t in trades if t["close_reason"] == "BREAK_EVEN")
        sl_cnt = sum(1 for t in trades if t["close_reason"] == "STOP_LOSS")
        net_r = sum(t["r_result"] for t in trades)
        win_rate = (tp2_cnt + be_cnt) / len(trades) * 100

        fixed_bal = 10000.0 + (net_r * 200.0)

        comp_bal = 10000.0
        peak = comp_bal
        max_dd = 0.0
        for t in trades:
            r = t["r_result"]
            pnl = comp_bal * (0.02 * r)
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

    m_opt_2r = calc_metrics(opt_trades_2r, tp2_target=2.0)
    m_opt_3r = calc_metrics(opt_trades_3r, tp2_target=3.0)
    m_ungated_2r = calc_metrics(ungated_trades_2r, tp2_target=2.0)

    # Aylık Kırılım (Optimize Model TP2=2R)
    monthly_stats = {}
    for t in opt_trades_2r:
        m_key = t["opened_at"][:7]
        monthly_stats.setdefault(m_key, []).append(t)

    # Parite Kırılımı
    sym_stats = {}
    for sym in OPTIMIZED_SYMBOLS:
        sub = [t for t in opt_trades_2r if t["symbol"] == sym]
        if sub:
            wins = sum(1 for t in sub if t["r_result"] > 0)
            net_r = sum(t["r_result"] for t in sub)
            sym_stats[sym] = {
                "trades": len(sub),
                "wins": wins,
                "win_rate": round(wins / len(sub) * 100, 1),
                "net_r": round(net_r, 2),
                "tp2": sum(1 for t in sub if t["close_reason"] == "TP2_HIT"),
                "be": sum(1 for t in sub if t["close_reason"] == "BREAK_EVEN"),
                "sl": sum(1 for t in sub if t["close_reason"] == "STOP_LOSS"),
            }

    # Çıktıyı JSON'a kaydet
    out_payload = {
        "period": "2026-07-11 to 2026-10-11",
        "initial_capital": 10000.0,
        "optimized_macro_gated_tp2_2r": m_opt_2r,
        "macro_gated_tp2_3r": m_opt_3r,
        "ungated_tp2_2r": m_ungated_2r,
        "symbol_breakdown": sym_stats,
        "monthly_breakdown": {
            m: {
                "trades": len(t_list),
                "wins": sum(1 for t in t_list if t["r_result"] > 0),
                "win_rate": round(sum(1 for t in t_list if t["r_result"] > 0) / len(t_list) * 100, 1),
                "net_r": round(sum(t["r_result"] for t in t_list), 2),
                "dollar": round(sum(t["r_result"] for t in t_list) * 200, 2),
            } for m, t_list in sorted(monthly_stats.items())
        }
    }

    out_file = Path("data/optimized_macro_3m_result.json")
    out_file.write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ekrana Yazdır
    print("\n" + "=" * 80)
    print("🌺 BEGONYA 00 - OPTİMİZE EDİLMİŞ 3 AYLIK MAKRO KARNESİ 🌺")
    print("=" * 80)
    print(f"💰 Başlangıç: $10,000.00 | Risk: %2.0 ($200 per 1R) | Periyot: Son 3 Ay (92 Gün)")
    print("🛡️ Kapsam: Yalnızca Forex Majörler + Kaliteli Kripto | ORB KAPALI (SFP Only) | TP2 = 2.0R")
    print("-" * 80)
    print(f"🏆 MODEL KARŞILAŞTIRMASI:")
    print(f"{'Metrik':<28} | {'Optimize Model (TP2=2R)':<24} | {'Eski Model (TP2=3R)':<22}")
    print("-" * 80)
    print(f"{'Toplam İşlem Sayısı':<28} | {m_opt_2r['total_trades']:<24} | {m_opt_3r['total_trades']:<22}")
    print(f"{'Kazanma Oranı (Win Rate)':<28} | %{m_opt_2r['win_rate']:<23} | %{m_opt_3r['win_rate']:<21}")
    print(f"{'Tam Hedef (TP2 Vurulan)':<28} | {m_opt_2r['tp2_count']} (%{m_opt_2r['pure_tp2_rate']}){'':<14} | {m_opt_3r['tp2_count']} (%{m_opt_3r['pure_tp2_rate']})")
    print(f"{'Başabaş Koruma (BE)':<28} | {m_opt_2r['be_count']:<24} | {m_opt_3r['be_count']:<22}")
    print(f"{'Zarar Durdur (SL)':<28} | {m_opt_2r['sl_count']:<24} | {m_opt_3r['sl_count']:<22}")
    print(f"{'Toplam Net R':<28} | {m_opt_2r['net_r']:+.2f}R{'':<19} | {m_opt_3r['net_r']:+.2f}R")
    print(f"{'Sabit Bakiye ($200/R)':<28} | ${m_opt_2r['fixed_balance']:,.2f} (%{m_opt_2r['fixed_return_pct']:+.1f}){'':<7} | ${m_opt_3r['fixed_balance']:,.2f} (%{m_opt_3r['fixed_return_pct']:+.1f})")
    print(f"{'Bileşik Bakiye (%2/R)':<28} | ${m_opt_2r['compounding_balance']:,.2f} (%{m_opt_2r['compounding_return_pct']:+.1f}){'':<5} | ${m_opt_3r['compounding_balance']:,.2f} (%{m_opt_3r['compounding_return_pct']:+.1f})")
    print(f"{'Maksimum Drawdown (DD)':<28} | %{m_opt_2r['max_drawdown_pct']:<23} | %{m_opt_3r['max_drawdown_pct']:<21}")
    print("-" * 80)
    print("📅 AYLIK NET PERFORMANS (OPTİMİZE MODEL):")
    for m, t_list in sorted(monthly_stats.items()):
        net_r = sum(t["r_result"] for t in t_list)
        wins = sum(1 for t in t_list if t["r_result"] > 0)
        dollar = net_r * 200
        print(f"  • {m}: {len(t_list)} İşlem | Win: %{wins/len(t_list)*100:.1f} | Net R: {net_r:+.2f}R (${dollar:+,.0f})")
    print("=" * 80)


if __name__ == "__main__":
    run_optimized_comparison()
