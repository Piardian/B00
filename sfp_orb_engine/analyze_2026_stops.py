"""
🌺 Begonya 00 - 2026 Yılı Stop Loss Adli İnceleme ve Ortak Nokta Tespiti Scripti
Bu script, 2026 yılındaki 122 işlemin 69 Stop Loss'unu derinlemesine inceler:
1. MFE (Maximum Favorable Excursion): İşlem kâra geçip mi döndü, yoksa direkt mi stop oldu?
2. Pool Tipi: Asian High/Low mu, PDH/PDL mi?
3. SFP Bar Boyutu / Volatilite: Bar ATR'nin kaç katı büyüklükte?
4. Sinyal Saati (UTC): Hangi saat dilimlerinde yoğunlaşıyor?
5. FVG / Grade Durumu: AAA vs A+ stop oranları
6. 4H Trend Mesafesi: Fiyat EMA50/200'e ne kadar uzak veya yakın?
7. Hafta İçi vs Hafta Sonu
8. Parite Bazında Stop Nedenleri
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

from .config import get_asset_sl_buffer, is_crypto
from .macro_gated_3m_backtest import DailyMacroGateTable

TARGET_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"
]

def run_deep_stop_analysis():
    start_dt = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)

    if not mt5.initialize():
        print("MT5 başlatılamadı!")
        return

    macro_table = DailyMacroGateTable(start_dt.date(), end_dt.date())

    all_trades_detailed = []

    for symbol in TARGET_SYMBOLS:
        display_sym = f"{symbol[:3]}/{symbol[3:]}" if len(symbol) == 6 and symbol.isalpha() else symbol
        sl_buffer_atr = get_asset_sl_buffer(display_sym)
        is_crypto_sym = is_crypto(symbol)

        warmup_from = start_dt - timedelta(days=25)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, warmup_from, end_dt)
        if rates is None or len(rates) < 500:
            continue

        df = pd.DataFrame(rates)
        df["datetime"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df["date"] = df["datetime"].dt.date
        df["weekday"] = df["datetime"].dt.weekday
        df["hour"] = df["datetime"].dt.hour
        df["minute"] = df["datetime"].dt.minute

        # Günlük Seviyeler
        daily = df.groupby("date").agg({"high": "max", "low": "min"}).shift(1)
        df["pdh"] = df["date"].map(daily["high"]).fillna(0.0)
        df["pdl"] = df["date"].map(daily["low"]).fillna(0.0)

        asian_bars = df[df["hour"] < 6]
        ash_map = asian_bars.groupby("date")["high"].max()
        asl_map = asian_bars.groupby("date")["low"].min()
        df["ash"] = df["date"].map(ash_map).fillna(0.0)
        df["asl"] = df["date"].map(asl_map).fillna(0.0)

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
        df["vol_sma20"] = df["volume"].rolling(20).mean().fillna(df["volume"])

        n = len(df)
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        volumes = df["volume"].values
        vol_smas = df["vol_sma20"].values
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

        active_pos = None
        cooldown_until = 0
        stopped_out_dates = set()
        start_ts = pd.Timestamp(start_dt.replace(tzinfo=None))

        for i in range(100, n):
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]
            c_atr = atrs[i]
            wday = weekdays[i]
            h_val = hours[i]
            bar_rng = max(c_high - c_low, 1e-8)
            cur_date = dates_only[i]

            # Pozisyon Takibi & MFE Hesaplama
            if active_pos is not None:
                p = active_pos
                entry = p["entry"]
                sl = p["current_sl"]
                tp1 = p["tp1"]
                tp2 = p["tp2"]
                status = p["status"]
                p_dir = p["direction"]
                p["bars_held"] += 1
                risk_dist = p["risk_dist"]

                # MFE (Maximum Favorable Excursion) ve MAE
                if p_dir == "LONG":
                    cur_favorable = (c_high - entry) / risk_dist
                    cur_adverse = (entry - c_low) / risk_dist
                else:
                    cur_favorable = (entry - c_low) / risk_dist
                    cur_adverse = (c_high - entry) / risk_dist

                if cur_favorable > p["max_favorable_r"]:
                    p["max_favorable_r"] = cur_favorable
                if cur_adverse > p["max_adverse_r"]:
                    p["max_adverse_r"] = cur_adverse

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
                        r_res = 1.50
                    elif c_low <= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = 0.50
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                            stopped_out_dates.add(cur_date)
                    elif p["bars_held"] >= 192:
                        closed = True
                        close_reason = "TIME_EXIT"
                        r_res = (c_close - entry) / risk_dist

                elif p_dir == "SHORT":
                    if c_low <= tp1 and status == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry

                    if c_low <= tp2:
                        closed = True
                        close_reason = "TP2_HIT"
                        r_res = 1.50
                    elif c_high >= sl:
                        closed = True
                        if status == "TP1_HIT":
                            close_reason = "BREAK_EVEN"
                            r_res = 0.50
                        else:
                            close_reason = "STOP_LOSS"
                            r_res = -1.0
                            stopped_out_dates.add(cur_date)
                    elif p["bars_held"] >= 192:
                        closed = True
                        close_reason = "TIME_EXIT"
                        r_res = (entry - c_close) / risk_dist

                if closed:
                    p["closed_at"] = dts[i]
                    p["exit_price"] = c_close
                    p["close_reason"] = close_reason
                    p["r_result"] = round(float(r_res), 2)
                    p["max_favorable_r"] = round(float(p["max_favorable_r"]), 2)
                    p["max_adverse_r"] = round(float(p["max_adverse_r"]), 2)
                    all_trades_detailed.append(p)
                    active_pos = None
                    cooldown_until = i + 3
                continue

            bar_raw = pd.Timestamp(dates_raw[i]).tz_localize(None)
            if bar_raw < start_ts or i < cooldown_until:
                continue

            # Aynı gün tekrar giriş engeli
            if cur_date in stopped_out_dates:
                continue

            is_weekend = wday in [5, 6]
            if is_weekend:
                if not is_crypto_sym:
                    continue
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
            else:
                sfp_session_active = (13 <= h_val <= 17)

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

            # SHORT
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
                    sfp_bar_atr_ratio = bar_rng / max(c_atr, 1e-8)
                    vol_ratio = volumes[i] / max(vol_smas[i], 1.0)
                    dist_to_ema200_pct = (c_close - ema200s[i]) / ema200s[i] * 100

                    sfp_sig = {
                        "strategy": "SFP",
                        "direction": "SHORT",
                        "grade": grade,
                        "entry": closes[entry_idx],
                        "sl": peak + (c_atr * sl_buffer_atr),
                        "pool": pool_name,
                        "trigger_time": dts[entry_idx],
                        "trigger_dt": dt_objs[entry_idx],
                        "sfp_bar_atr_ratio": round(sfp_bar_atr_ratio, 2),
                        "vol_ratio": round(vol_ratio, 2),
                        "dist_to_ema200_pct": round(dist_to_ema200_pct, 2),
                        "wick_ratio": round(upper_wick, 2),
                        "hour": hours[entry_idx],
                        "weekday": weekdays[entry_idx],
                        "candle_span_to_entry": entry_idx - i,
                    }

            # LONG
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
                    sfp_bar_atr_ratio = bar_rng / max(c_atr, 1e-8)
                    vol_ratio = volumes[i] / max(vol_smas[i], 1.0)
                    dist_to_ema200_pct = (c_close - ema200s[i]) / ema200s[i] * 100

                    sfp_sig = {
                        "strategy": "SFP",
                        "direction": "LONG",
                        "grade": grade,
                        "entry": closes[entry_idx],
                        "sl": trough - (c_atr * sl_buffer_atr),
                        "pool": pool_name,
                        "trigger_time": dts[entry_idx],
                        "trigger_dt": dt_objs[entry_idx],
                        "sfp_bar_atr_ratio": round(sfp_bar_atr_ratio, 2),
                        "vol_ratio": round(vol_ratio, 2),
                        "dist_to_ema200_pct": round(dist_to_ema200_pct, 2),
                        "wick_ratio": round(lower_wick, 2),
                        "hour": hours[entry_idx],
                        "weekday": weekdays[entry_idx],
                        "candle_span_to_entry": entry_idx - i,
                    }

            if sfp_sig is not None:
                sig_dt = sfp_sig["trigger_dt"]
                direction = sfp_sig["direction"]
                macro_gate = macro_table.get_gate(sig_dt, symbol)

                if macro_gate in ["NEUTRAL_RANGE", "NO_TRADE", "DEFENSIVE_HOLD", "VETO"]:
                    continue
                if direction == "LONG" and macro_gate != "LONG_ONLY":
                    continue
                if direction == "SHORT" and macro_gate != "SHORT_ONLY":
                    continue

                entry_p = sfp_sig["entry"]
                sl_p = sfp_sig["sl"]
                risk_dist = abs(entry_p - sl_p)
                if risk_dist <= 1e-8:
                    continue

                if direction == "LONG":
                    tp1_p = entry_p + (risk_dist * 1.0)
                    tp2_p = entry_p + (risk_dist * 2.0)
                else:
                    tp1_p = entry_p - (risk_dist * 1.0)
                    tp2_p = entry_p - (risk_dist * 2.0)

                active_pos = {
                    "symbol": symbol,
                    "direction": direction,
                    "entry": entry_p,
                    "original_sl": sl_p,
                    "current_sl": sl_p,
                    "tp1": tp1_p,
                    "tp2": tp2_p,
                    "risk_dist": risk_dist,
                    "opened_at": sfp_sig["trigger_time"],
                    "closed_at": None,
                    "close_reason": None,
                    "r_result": 0.0,
                    "status": "OPEN",
                    "bars_held": 0,
                    "max_favorable_r": 0.0,
                    "max_adverse_r": 0.0,
                    "pool": sfp_sig["pool"],
                    "grade": sfp_sig["grade"],
                    "sfp_bar_atr_ratio": sfp_sig["sfp_bar_atr_ratio"],
                    "vol_ratio": sfp_sig["vol_ratio"],
                    "dist_to_ema200_pct": sfp_sig["dist_to_ema200_pct"],
                    "wick_ratio": sfp_sig["wick_ratio"],
                    "hour": sfp_sig["hour"],
                    "weekday": sfp_sig["weekday"],
                    "candle_span_to_entry": sfp_sig["candle_span_to_entry"],
                    "is_crypto": is_crypto_sym,
                }

    mt5.shutdown()

    # DETAYLI ANALİZ
    df_all = pd.DataFrame(all_trades_detailed)
    df_sl = df_all[df_all["close_reason"] == "STOP_LOSS"]
    df_win = df_all[df_all["close_reason"].isin(["TP2_HIT", "BREAK_EVEN"])]

    print(f"\n================================================================================")
    print(f"🔬 2026 YILI 69 STOP LOSS İŞLEMİNİN ADLİ İNCELEMESİ (FORENSIC ANALYSIS)")
    print(f"Toplam İşlem: {len(df_all)} | Kazananlar: {len(df_win)} | Stoplar: {len(df_sl)}")
    print(f"================================================================================")

    # 1. MFE DAĞILIMI (Kâra geçip mi döndü yoksa sıfırdan direkt mi vurdu?)
    print("\n--- 1. MFE (Maximum Favorable Excursion) - Stoplar Kâra Geçti mi? ---")
    mfe_0_to_03 = len(df_sl[df_sl["max_favorable_r"] < 0.3])
    mfe_03_to_05 = len(df_sl[(df_sl["max_favorable_r"] >= 0.3) & (df_sl["max_favorable_r"] < 0.5)])
    mfe_05_to_08 = len(df_sl[(df_sl["max_favorable_r"] >= 0.5) & (df_sl["max_favorable_r"] < 0.8)])
    mfe_08_plus = len(df_sl[df_sl["max_favorable_r"] >= 0.8])
    print(f"Direkt Stop (< 0.3R kâr gördü):      {mfe_0_to_03} adet (%{mfe_0_to_03/len(df_sl)*100:.1f})")
    print(f"Küçük Kâr Gördü (0.3R - 0.5R arası):  {mfe_03_to_05} adet (%{mfe_03_to_05/len(df_sl)*100:.1f})")
    print(f"İyi Kâr Gördü (0.5R - 0.8R arası):    {mfe_05_to_08} adet (%{mfe_05_to_08/len(df_sl)*100:.1f})")
    print(f"Neredeyse TP1 (>= 0.8R görüp döndü):  {mfe_08_plus} adet (%{mfe_08_plus/len(df_sl)*100:.1f})")

    # 2. POOL ANALİZİ (PDH/PDL vs Asian High/Low)
    print("\n--- 2. Likidite Havuzu Analizi (Pool) ---")
    pool_summary = df_all.groupby(["pool", "close_reason"]).size().unstack(fill_value=0)
    print(pool_summary)

    # 3. SAAT DİLİMİ ANALİZİ (UTC Saatleri)
    print("\n--- 3. Saat Dilimi Dağılımı (UTC Hour) ---")
    hour_summary = df_all.groupby(["hour", "close_reason"]).size().unstack(fill_value=0)
    print(hour_summary)

    # 4. GRADE ANALİZİ (AAA vs A+)
    print("\n--- 4. Kalite Notu (Grade: FVG Var mı Yok mu?) ---")
    grade_summary = df_all.groupby(["grade", "close_reason"]).size().unstack(fill_value=0)
    print(grade_summary)

    # 5. SFP BAR BÜYÜKLÜĞÜ (ATR ORANI)
    print("\n--- 5. SFP Mumunun Boyutu (Bar / ATR Oranı) ---")
    print(f"Kazananların Ortalama Bar/ATR Oranı: {df_win['sfp_bar_atr_ratio'].mean():.2f}")
    print(f"Stopların Ortalama Bar/ATR Oranı:    {df_sl['sfp_bar_atr_ratio'].mean():.2f}")
    large_bars = len(df_sl[df_sl["sfp_bar_atr_ratio"] > 1.8])
    print(f"Aşırı Büyük Mumla SFP Yapıp Stop Olanlar (Bar > 1.8 ATR): {large_bars} (%{large_bars/len(df_sl)*100:.1f})")

    # 6. DIST TO 4H EMA200 (Aşırı Şişmiş Trend mi?)
    print("\n--- 6. 4H Trendden Uzaklık (% Dist to EMA200) ---")
    print(f"Kazananların EMA200'den Uzaklığı: %{df_win['dist_to_ema200_pct'].abs().mean():.2f}")
    print(f"Stopların EMA200'den Uzaklığı:    %{df_sl['dist_to_ema200_pct'].abs().mean():.2f}")

    # 7. BARS HELD (Stop Olma Süresi)
    print("\n--- 7. Pozisyon Süresi (Bars Held - M15 Bar Sayısı) ---")
    print(f"Stopların Ortalama Açık Kalma Süresi: {df_sl['bars_held'].mean():.1f} bar ({df_sl['bars_held'].mean()*15/60:.1f} saat)")
    instant_sl = len(df_sl[df_sl["bars_held"] <= 4])
    print(f"İlk 1 Saatte (<=4 Bar) Stop Olanlar: {instant_sl} adet (%{instant_sl/len(df_sl)*100:.1f})")

    # 8. KRİPTO vs FOREX STOP DETAYLARI
    print("\n--- 8. Varlık Sınıfı Kıyaslaması (Crypto vs Forex Stopları) ---")
    df_sl_crypto = df_sl[df_sl["is_crypto"] == True]
    df_sl_forex = df_sl[df_sl["is_crypto"] == False]
    print(f"Forex Stop Sayısı: {len(df_sl_forex)} | Ortalama MFE: {df_sl_forex['max_favorable_r'].mean():.2f}R | Direkt Stop: {len(df_sl_forex[df_sl_forex['max_favorable_r'] < 0.3])}")
    print(f"Kripto Stop Sayısı: {len(df_sl_crypto)} | Ortalama MFE: {df_sl_crypto['max_favorable_r'].mean():.2f}R | Direkt Stop: {len(df_sl_crypto[df_sl_crypto['max_favorable_r'] < 0.3])}")

    # JSON kaydı
    report_dict = {
        "total_trades": len(df_all),
        "total_stops": len(df_sl),
        "mfe": {
            "under_03": int(mfe_0_to_03),
            "03_to_05": int(mfe_03_to_05),
            "05_to_08": int(mfe_05_to_08),
            "above_08": int(mfe_08_plus)
        },
        "pool_stops": pool_summary.to_dict(),
        "hour_stops": hour_summary.to_dict(),
        "grade_stops": grade_summary.to_dict(),
        "instant_sl_count": int(instant_sl),
    }
    Path("data/forensic_stop_2026.json").write_text(json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("data/detailed_trades_2026.json").write_text(df_all.to_json(orient="records", indent=2), encoding="utf-8")


if __name__ == "__main__":
    run_deep_stop_analysis()
