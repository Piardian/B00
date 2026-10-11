"""
🌺 Begonya 00 - 2026 Yılı Tam Dönem Testi (No Same-Day Re-entry)
Kullanıcı Talebi:
- "bu haliyle sadece 2026 için test at"
- Uygulanan Kural: Aynı gün aynı paritede Stop olduktan sonra tekrar giriş yasağı (No Same-Day Re-entry)
- 0.5R Trailing BE KAPALI (Orijinal: TP1=1.0R'da %50 Kâr & BE, TP2=2.0R Kalan %50)
- Hafta İçi YALNIZCA New York Killzone (13:00 - 17:00 UTC) + Hafta Sonu Kripto
- Katı 4H Trend Uyumu (Bullish -> Yalnızca Long, Bearish -> Yalnızca Short)
- Makro Kapısı: Range Bandında (NEUTRAL_RANGE) -> 0 İşlem, Yön Onayı Şart
- Kasa: $10,000 USD | Risk: %2.0 ($200 per 1R)
- Periyot: 2026-01-01 -> 2026-10-11 (Yılbaşından Bugüne - 284 Gün)
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
logger = logging.getLogger("Begonya00.Test2026Full")

TARGET_SYMBOLS = [
    # Forex Majörler & Kaliteli Çaprazlar
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    # Kaliteli Kripto Majörleri
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"
]


class Remediation2026Runner:
    def __init__(self, start_dt: datetime, end_dt: datetime, initial_capital: float = 10000.0, risk_pct: float = 0.02, tp2_rr: float = 2.0):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.tp2_rr = tp2_rr
        self.utc_from = start_dt
        self.utc_to = end_dt
        self.macro_table = DailyMacroGateTable(self.utc_from.date(), self.utc_to.date())

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

        # 4H EMA Trend (200 ve 800 bar M15)
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

        return df

    def run_simulation(self, symbol: str, df: pd.DataFrame, use_macro_gate: bool = True, apply_no_reentry: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
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
        ema50s = df["htf_ema50"].values
        ema200s = df["htf_ema200"].values
        weekdays = df["weekday"].values
        hours = df["hour"].values
        dts = df["datetime"].dt.strftime("%Y-%m-%d %H:%M").values
        dates_only = df["date"].values
        dt_objs = df["datetime"].dt.to_pydatetime()
        dates_raw = df["datetime"].values

        trades = []
        active_position = None
        cooldown_until = 0

        # DÜZELTME 1: AYNI GÜN TEKRAR GİRİŞİ ENGELLEME
        # O gün bu sembolde Stop olunduysa gün sonuna kadar işlem alma
        stopped_out_dates = set()

        gate_stats = {
            "VETO_MACRO_RANGE": 0,
            "VETO_DIRECTION_MISMATCH": 0,
            "VETO_SAME_DAY_REENTRY": 0,
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
            cur_date = dates_only[i]

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
                        r_res = (1.0 * 0.5) + (self.tp2_rr * 0.5)
                    elif c_low <= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.0 * 0.5) + (0.0 * 0.5)
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                            # STOP OLUNDU -> O GÜNÜN LİSTESİNE EKLE
                            if apply_no_reentry:
                                stopped_out_dates.add(cur_date)
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
                        r_res = (1.0 * 0.5) + (self.tp2_rr * 0.5)
                    elif c_high >= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = (1.0 * 0.5) + (0.0 * 0.5)
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                            if apply_no_reentry:
                                stopped_out_dates.add(cur_date)
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

            # DÜZELTME 1 KONTROLÜ: O gün bu paritede zaten Stop olunduysa aynı gün tekrar girme!
            if apply_no_reentry and (cur_date in stopped_out_dates):
                gate_stats["VETO_SAME_DAY_REENTRY"] += 1
                continue

            is_weekend = wday in [5, 6]
            if is_weekend:
                if not is_crypto_sym:
                    continue
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
            else:
                # Hafta İçi: YALNIZCA NEW YORK KILLZONE (13:00 - 17:00 UTC)
                sfp_session_active = (13 <= h_val <= 17)

            if not sfp_session_active:
                continue

            pdh = pdhs[i]
            pdl = pdls[i]
            ash = ashs[i]
            asl = asls[i]
            if pdh == 0.0 or pdl == 0.0:
                continue

            # Katı 4H Trend Uyumu
            htf_bull = ema50s[i] > ema200s[i]
            htf_bear = ema50s[i] < ema200s[i]
            allow_long = htf_bull
            allow_short = htf_bear

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
                    grade = "AAA" if has_fvg else "A+"

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

            elif sweep_low and allow_long:
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
                    grade = "AAA" if has_fvg else "A+"

                    sfp_sig = {
                        "strategy": "SFP_VOLUME_ANOMALY",
                        "direction": "LONG",
                        "grade": grade,
                        "entry": closes[entry_idx],
                        "sl": trough - (c_atr * sl_buffer_atr),
                        "pool": pool_name,
                        "trigger_time": dts[entry_idx],
                        "trigger_dt": dt_objs[entry_idx],
                    }

            if sfp_sig is not None:
                sig_dt = sfp_sig["trigger_dt"]
                direction = sfp_sig["direction"]
                macro_gate = self.macro_table.get_gate(sig_dt, symbol)

                if use_macro_gate:
                    if macro_gate in ["NEUTRAL_RANGE", "NO_TRADE", "DEFENSIVE_HOLD", "VETO"]:
                        gate_stats["VETO_MACRO_RANGE"] += 1
                        continue

                    if direction == "LONG" and macro_gate != "LONG_ONLY":
                        gate_stats["VETO_DIRECTION_MISMATCH"] += 1
                        continue

                    if direction == "SHORT" and macro_gate != "SHORT_ONLY":
                        gate_stats["VETO_DIRECTION_MISMATCH"] += 1
                        continue

                gate_stats["APPROVED"] += 1

                entry_p = sfp_sig["entry"]
                sl_p = sfp_sig["sl"]
                risk_dist = abs(entry_p - sl_p)

                if risk_dist <= 1e-8:
                    continue

                if sfp_sig["direction"] == "LONG":
                    tp1_p = entry_p + (risk_dist * 1.0)
                    tp2_p = entry_p + (risk_dist * self.tp2_rr)
                else:
                    tp1_p = entry_p - (risk_dist * 1.0)
                    tp2_p = entry_p - (risk_dist * self.tp2_rr)

                active_position = {
                    "symbol": symbol,
                    "direction": sfp_sig["direction"],
                    "entry": entry_p,
                    "original_sl": sl_p,
                    "current_sl": sl_p,
                    "tp1": tp1_p,
                    "tp2": tp2_p,
                    "opened_at": sfp_sig["trigger_time"],
                    "closed_at": None,
                    "close_reason": None,
                    "r_result": 0.0,
                    "status": "OPEN",
                    "bars_held": 0,
                    "pool": sfp_sig.get("pool", ""),
                    "macro_gate": macro_gate,
                    "is_weekend": bool(is_weekend),
                }

        return trades, gate_stats


def run_period_test(period_name: str, start_dt: datetime, end_dt: datetime, runner: Remediation2026Runner = None) -> Dict[str, Any]:
    if runner is None:
        runner = Remediation2026Runner(start_dt, end_dt)

    logger.info(f"\n=======================================================")
    logger.info(f"🚀 {period_name} ({start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}) TESTİ KOŞULUYOR...")
    logger.info(f"=======================================================")

    all_trades = []
    veto_totals = {"VETO_MACRO_RANGE": 0, "VETO_DIRECTION_MISMATCH": 0, "VETO_SAME_DAY_REENTRY": 0, "APPROVED": 0}

    for sym in TARGET_SYMBOLS:
        df = runner.fetch_m15_data(sym)
        if df is not None:
            t_l, v_s = runner.run_simulation(sym, df, use_macro_gate=True, apply_no_reentry=True)
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
        "start": start_dt.strftime("%Y-%m-%d"),
        "end": end_dt.strftime("%Y-%m-%d"),
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
    # 2026 Yılı Boyunca Test (2026-01-01 -> 2026-10-11)
    full_start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    full_end = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)

    logger.info("📡 2026 Yılı Tam Dönem Runner Başlatılıyor...")
    full_runner = Remediation2026Runner(full_start, full_end)

    # 1. Tüm 2026 Yılı Testi (YTD)
    full_res = run_period_test("2026 Tam Yıl (YTD)", full_start, full_end, full_runner)

    # 2. Ay Ay Döküm
    monthly_definitions = [
        ("2026-01 (Ocak)", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc)),
        ("2026-02 (Şubat)", datetime(2026, 2, 1, tzinfo=timezone.utc), datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc)),
        ("2026-03 (Mart)", datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc)),
        ("2026-04 (Nisan)", datetime(2026, 4, 1, tzinfo=timezone.utc), datetime(2026, 4, 30, 23, 59, tzinfo=timezone.utc)),
        ("2026-05 (Mayıs)", datetime(2026, 5, 1, tzinfo=timezone.utc), datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc)),
        ("2026-06 (Haziran)", datetime(2026, 6, 1, tzinfo=timezone.utc), datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc)),
        ("2026-07 (Temmuz)", datetime(2026, 7, 1, tzinfo=timezone.utc), datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)),
        ("2026-08 (Ağustos)", datetime(2026, 8, 1, tzinfo=timezone.utc), datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)),
        ("2026-09 (Eylül)", datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)),
        ("2026-10 (Ekim MTD)", datetime(2026, 10, 1, tzinfo=timezone.utc), datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)),
    ]

    all_trades_full = full_res["trades_list"]

    # Aylık trade'leri ayır
    monthly_results = []
    for m_name, m_s, m_e in monthly_definitions:
        m_s_str = m_s.strftime("%Y-%m-%d")
        m_e_str = m_e.strftime("%Y-%m-%d")
        m_trades = [t for t in all_trades_full if m_s_str <= t["opened_at"][:10] <= m_e_str]

        cnt = len(m_trades)
        tp2_cnt = sum(1 for t in m_trades if t["close_reason"] == "TP2_HIT")
        be_cnt = sum(1 for t in m_trades if t["close_reason"] == "BREAK_EVEN")
        sl_cnt = sum(1 for t in m_trades if t["close_reason"] == "STOP_LOSS")
        net_r = sum(t["r_result"] for t in m_trades)
        wr = (tp2_cnt + be_cnt) / cnt * 100 if cnt > 0 else 0.0
        dol = net_r * 200.0

        monthly_results.append({
            "period": m_name,
            "trades": cnt,
            "win_rate": round(wr, 1),
            "tp2": tp2_cnt,
            "be": be_cnt,
            "sl": sl_cnt,
            "net_r": round(net_r, 2),
            "dollar": round(dol, 2)
        })

    print("\n" + "=" * 95)
    print("🌺 BEGONYA 00 - 2026 YILI TAM DÖNEM TESTİ ZİL KARNESİ (NO SAME-DAY RE-ENTRY) 🌺")
    print("=" * 95)
    print("💰 Başlangıç Sermayesi: $10,000.00 | Risk: %2.0 ($200 per 1R)")
    print("🛡️ Düzeltmeler: Sadece 1. Düzeltme (Aynı Gün Tekrar Giriş Yasağı) + NY Killzone + 4H Trend")
    print("🔒 2. Düzeltme (0.5R BE): KAPALI (TP1 = 1.0R'da %50 Kâr & BE, TP2 = 2.0R Kalan %50)")
    print("-" * 95)
    print(f"{'Dönem / Ay':<22} | {'İşlem':<6} | {'Win Rate':<10} | {'TP2':<5} | {'BE':<5} | {'SL':<5} | {'Net R':<10} | {'Kasa Değişimi'}")
    print("-" * 95)

    cum_dollar = 0.0
    for mr in monthly_results:
        cnt = mr["trades"]
        wr = mr["win_rate"]
        tp2 = mr["tp2"]
        be = mr["be"]
        sl = mr["sl"]
        net_r = mr["net_r"]
        dol = mr["dollar"]
        cum_dollar += dol

        status_icon = "🟢" if net_r > 0 else ("🟡" if net_r == 0 else "🔴")
        print(f"{status_icon} {mr['period']:<20} | {cnt:<6} | %{wr:<8.1f} | {tp2:<5} | {be:<5} | {sl:<5} | {net_r:>+6.2f}R | ${dol:>+8,.0f}")

    print("-" * 95)
    full_cnt = full_res["trades"]
    full_wr = full_res["win_rate"]
    full_tp2 = full_res["tp2"]
    full_be = full_res["be"]
    full_sl = full_res["sl"]
    full_r = full_res["net_r"]
    full_dol = full_res["dollar"]
    end_bal = 10000.0 + full_dol

    tot_icon = "🟢" if full_r > 0 else ("🟡" if full_r == 0 else "🔴")
    print(f"{tot_icon} {'2026 TOPLAM (YTD)':<20} | {full_cnt:<6} | %{full_wr:<8.1f} | {full_tp2:<5} | {full_be:<5} | {full_sl:<5} | {full_r:>+6.2f}R | ${full_dol:>+8,.0f}")
    print("=" * 95)
    print(f"💼 Bitiş Sermayesi: ${end_bal:,.2f} ({((end_bal - 10000)/10000)*100:+.2f}%)")
    print(f"🛡️ Filtrelenen Hatalı Aynı Gün Tekrar Girişleri: {full_res['vetos'].get('VETO_SAME_DAY_REENTRY', 0)} Sinyal")
    print(f"🚫 Makro Kapısı Range Engeli: {full_res['vetos'].get('VETO_MACRO_RANGE', 0)} Sinyal")
    print(f"🚫 Makro Kapısı Ters Yön Engeli: {full_res['vetos'].get('VETO_DIRECTION_MISMATCH', 0)} Sinyal")
    print("=" * 95)

    # JSON kaydet
    out_payload = {
        "monthly": monthly_results,
        "summary": {
            "period": "2026 YTD",
            "trades": full_cnt,
            "win_rate": full_wr,
            "tp2": full_tp2,
            "be": full_be,
            "sl": full_sl,
            "net_r": full_r,
            "dollar": full_dol,
            "ending_balance": end_bal,
            "vetos": full_res["vetos"]
        },
        "trades": [
            {
                "symbol": t["symbol"],
                "direction": t["direction"],
                "opened_at": t["opened_at"],
                "closed_at": t["closed_at"],
                "close_reason": t["close_reason"],
                "r_result": t["r_result"],
                "pool": t["pool"]
            } for t in all_trades_full
        ]
    }
    Path("data/test_2026_remediation_result.json").write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
