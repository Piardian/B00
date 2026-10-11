"""
🌺 Begonya 00 - 2024 Yılı 3 Farklı Ayda İyileştirme Testi (No Same-Day Re-entry)
Kullanıcı Talebi:
- Sadece 1. Düzeltme Uygulandı: Aynı gün aynı paritede Stop olduktan sonra tekrar giriş yasağı (No Same-Day Re-entry after SL)
- New York Killzone (13-17 UTC) + Katı 4H Trend Uyumu + Makro Kapısı (Range = 0 İşlem)
- TP1 = 1.0R (BE) | TP2 = 2.0R (Kalan %50)
- Kasa: $10,000 USD | Risk: %2.0 ($200 per 1R)
- 2024 Yılında 3 Temsili Ay Test Ediliyor:
  1. Test 1: 2024 Mart (2024-03-01 - 2024-03-31) -> Q1 Güçlü Trend & Halving Öncesi Dönem
  2. Test 2: 2024 Temmuz (2024-07-01 - 2024-07-31) -> Q3 Yaz Konsolidasyonu
  3. Test 3: 2024 Ekim (2024-10-01 - 2024-10-31) -> Q4 Kurumsal Volatilite Dönemi
  + 3 Aylık Birleşik Dönem Analizi
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
logger = logging.getLogger("Begonya00.Test2024Remediation")

TARGET_SYMBOLS = [
    # Forex Majörler & Kaliteli Çaprazlar
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    # Kaliteli Kripto Majörleri
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"
]


class Remediation2024Runner:
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

        # DÜZELTME 1: AYNI GÜN TEKRAR GİRİŞİ ENGELLEME LİSTESİ
        # (symbol, date) bazında o gün Stop olunduysa gün sonuna kadar işlem alma!
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
                    grade = "AAA" if has_fvg else "A+"

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


def run_month_test(month_name: str, start_dt: datetime, end_dt: datetime) -> Dict[str, Any]:
    runner = Remediation2024Runner(start_dt, end_dt)
    logger.info(f"\n=======================================================")
    logger.info(f"🚀 {month_name} ({start_dt.strftime('%Y-%m-%d')} - {end_dt.strftime('%Y-%m-%d')}) TESTİ KOŞULUYOR...")
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
            "month": month_name, "trades": 0, "win_rate": 0.0, "net_r": 0.0,
            "dollar": 0.0, "tp2": 0, "be": 0, "sl": 0, "vetos": veto_totals
        }

    tp2_cnt = sum(1 for t in all_trades if t["close_reason"] == "TP2_HIT")
    be_cnt = sum(1 for t in all_trades if t["close_reason"] == "BREAK_EVEN")
    sl_cnt = sum(1 for t in all_trades if t["close_reason"] == "STOP_LOSS")
    net_r = sum(t["r_result"] for t in all_trades)
    win_rate = (tp2_cnt + be_cnt) / len(all_trades) * 100
    dollar = net_r * 200.0

    return {
        "month": month_name,
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
    # 2024 Yılında 3 Temsili Ay:
    # 1. 2024 Mart (Q1 - Bitcoin Halving Rallisi & Dolar Dönemi)
    # 2. 2024 Temmuz (Q3 - Yaz Sezonu)
    # 3. 2024 Ekim (Q4 - Sonbahar Kurumsal Dönemi)
    test_periods = [
        ("Test 1: 2024 Mart (Q1)", datetime(2024, 3, 1, 0, 0, tzinfo=timezone.utc), datetime(2024, 3, 31, 23, 59, tzinfo=timezone.utc)),
        ("Test 2: 2024 Temmuz (Q3)", datetime(2024, 7, 1, 0, 0, tzinfo=timezone.utc), datetime(2024, 7, 31, 23, 59, tzinfo=timezone.utc)),
        ("Test 3: 2024 Ekim (Q4)", datetime(2024, 10, 1, 0, 0, tzinfo=timezone.utc), datetime(2024, 10, 31, 23, 59, tzinfo=timezone.utc))
    ]

    results = []
    for name, s_dt, e_dt in test_periods:
        res = run_month_test(name, s_dt, e_dt)
        results.append(res)

    print("\n" + "=" * 85)
    print("🌺 BEGONYA 00 - 2024 YILI 3 FARKLI AY İYİLEŞTİRME TESTİ ZİL KARNESİ 🌺")
    print("=" * 85)
    print("💰 Başlangıç Sermayesi: $10,000.00 | Risk: %2.0 ($200 per 1R)")
    print("🛡️ Düzeltmeler: Aynı Gün Tekrar Giriş Yasağı (No Same-Day Re-entry) + NY Killzone + 4H Trend")
    print("-" * 85)
    print(f"{'Dönem / Ay':<28} | {'İşlem':<6} | {'Win Rate':<10} | {'TP2':<5} | {'BE':<5} | {'SL':<5} | {'Net R':<10} | {'Kasa ($)'}")
    print("-" * 85)

    tot_trades = 0
    tot_tp2 = 0
    tot_be = 0
    tot_sl = 0
    tot_r = 0.0
    tot_dollar = 0.0

    for r in results:
        m = r["month"]
        cnt = r["trades"]
        wr = r["win_rate"]
        tp2 = r["tp2"]
        be = r["be"]
        sl = r["sl"]
        net_r = r["net_r"]
        dol = r["dollar"]

        tot_trades += cnt
        tot_tp2 += tp2
        tot_be += be
        tot_sl += sl
        tot_r += net_r
        tot_dollar += dol

        status_icon = "🟢" if net_r > 0 else ("🟡" if net_r == 0 else "🔴")
        print(f"{status_icon} {m:<26} | {cnt:<6} | %{wr:<8.1f} | {tp2:<5} | {be:<5} | {sl:<5} | {net_r:>+6.2f}R | ${dol:>+7,.0f}")

    print("-" * 85)
    tot_win_rate = (tot_tp2 + tot_be) / tot_trades * 100 if tot_trades > 0 else 0.0
    tot_icon = "🟢" if tot_r > 0 else ("🟡" if tot_r == 0 else "🔴")
    print(f"{tot_icon} {'3 AYIN TOPLAMI / ORTALAMASI':<26} | {tot_trades:<6} | %{tot_win_rate:<8.1f} | {tot_tp2:<5} | {tot_be:<5} | {tot_sl:<5} | {tot_r:>+6.2f}R | ${tot_dollar:>+7,.0f}")
    print("=" * 85)

    # JSON kaydı
    out_payload = {
        "tests": [
            {
                "month": r["month"],
                "trades": r["trades"],
                "win_rate": r["win_rate"],
                "tp2": r["tp2"],
                "be": r["be"],
                "sl": r["sl"],
                "net_r": r["net_r"],
                "dollar": r["dollar"],
                "vetos": r["vetos"]
            } for r in results
        ],
        "summary": {
            "total_trades": tot_trades,
            "win_rate": round(tot_win_rate, 1),
            "tp2_count": tot_tp2,
            "be_count": tot_be,
            "sl_count": tot_sl,
            "total_net_r": round(tot_r, 2),
            "total_dollar": round(tot_dollar, 2),
            "ending_balance": round(10000.0 + tot_dollar, 2)
        }
    }
    Path("data/test_2024_remediation_result.json").write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
