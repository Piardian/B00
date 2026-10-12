import os
import sys
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from sfp_orb_engine.config import get_asset_sl_buffer, is_crypto
from sfp_orb_engine.entry_mechanics import calculate_ce_entry, is_slice_through_candle
from sfp_orb_engine.macro_gated_3m_backtest import DailyMacroGateTable

SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP",
    "XAUUSD", "NAS100", "SP500", "US30",
    "BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD", "XRPUSD", "DOGUSD"
]

FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
    "EURJPY", "EURGBP"
]

EXCLUDED_SYMBOLS = ["GBPJPY", "AUDUSD"]

def run_test(use_macro_gate=True, use_mtf_pd=False):
    if not mt5.initialize():
        print("MT5 init failed")
        return

    utc_to = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
    utc_from = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    warmup_from = utc_from - timedelta(days=25)

    macro_table = DailyMacroGateTable(utc_from.date(), utc_to.date()) if use_macro_gate else None

    all_trades = []
    
    for sym in SYMBOLS:
        if sym in EXCLUDED_SYMBOLS:
            continue
            
        display_sym = f"{sym[:3]}/{sym[3:]}" if len(sym) == 6 and sym.isalpha() else sym
        sl_buffer_atr = get_asset_sl_buffer(display_sym)
        is_crypto_sym = is_crypto(sym)
        is_momentum = sym in ["BTCUSD", "ETHUSD", "NAS100", "XAUUSD"]

        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, warmup_from, utc_to)
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

        # PDH & PDL
        daily = df.groupby("date").agg({"high": "max", "low": "min"}).shift(1)
        df["pdh"] = df["date"].map(daily["high"]).fillna(0.0)
        df["pdl"] = df["date"].map(daily["low"]).fillna(0.0)

        # Asian (00:00 - 06:00 UTC)
        asian_bars = df[df["hour"] < 6]
        ash_map = asian_bars.groupby("date")["high"].max()
        asl_map = asian_bars.groupby("date")["low"].min()
        df["ash"] = df["date"].map(ash_map).fillna(0.0)
        df["asl"] = df["date"].map(asl_map).fillna(0.0)

        # HTF EMA
        df["htf_ema50"] = df["close"].ewm(span=200, adjust=False).mean()
        df["htf_ema200"] = df["close"].ewm(span=800, adjust=False).mean()

        # ATR 14
        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                np.abs(df["high"] - df["close"].shift(1)),
                np.abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = tr.rolling(14).mean().fillna(df["high"] - df["low"])
        df["vol_sma"] = df["volume"].rolling(20).mean().fillna(df["volume"])

        # P/D levels
        if use_mtf_pd:
            df["eq_15m"] = (df["high"].rolling(32).max() + df["low"].rolling(32).min()) / 2.0
            df["disc_15m"] = df["close"] < df["eq_15m"]
            df["prem_15m"] = df["close"] > df["eq_15m"]

            df["eq_1h"] = (df["high"].rolling(96).max() + df["low"].rolling(96).min()) / 2.0
            df["disc_1h"] = df["close"] < df["eq_1h"]
            df["prem_1h"] = df["close"] > df["eq_1h"]

            df["eq_4h"] = (df["high"].rolling(192).max() + df["low"].rolling(192).min()) / 2.0
            df["disc_4h"] = df["close"] < df["eq_4h"]
            df["prem_4h"] = df["close"] > df["eq_4h"]

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

        # ORB
        orb_high = np.zeros(n, dtype=float)
        orb_low = np.zeros(n, dtype=float)
        in_orb_window = np.zeros(n, dtype=bool)

        current_orb_h = 0.0
        current_orb_l = 0.0
        in_sess = False
        sess_expire = 0

        # ORB ONLY FOR FOREX!
        allow_orb_sym = sym in FOREX_SYMBOLS

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

        start_ts = pd.Timestamp(utc_from.replace(tzinfo=None))

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

            # Evaluate active position on bar i
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

            htf_bull = ema50s[i] > ema200s[i]
            htf_bear = ema50s[i] < ema200s[i]
            allow_short = htf_bear if is_momentum else (not htf_bull)
            allow_long = htf_bull if is_momentum else (not htf_bear)

            # Macro Gate Check
            cur_dt = pd.to_datetime(dates_raw[i]).to_pydatetime()
            if use_macro_gate and macro_table:
                gate_val = macro_table.get_gate(cur_dt, sym)
                if gate_val == "NEUTRAL_RANGE":
                    allow_short = False
                    allow_long = False
                elif gate_val == "SHORT_ONLY":
                    allow_long = False
                elif gate_val == "LONG_ONLY":
                    allow_short = False

            if use_mtf_pd:
                # Begonya MTF P/D filter
                if allow_long:
                    allow_long = df["disc_15m"].values[i] and df["disc_1h"].values[i] and df["disc_4h"].values[i]
                if allow_short:
                    allow_short = df["prem_15m"].values[i] and df["prem_1h"].values[i] and df["prem_4h"].values[i]

            sfp_sig = None
            orb_sig = None

            # TIMELINE-SAFE SFP:
            # Bar i confirms MSS of a sweep that occurred at j in [i-1, i-2, i-3]
            if sfp_session_active and (allow_short or allow_long):
                # Check SHORT SFP: sweep at j, confirmed at bar i
                if allow_short:
                    for j in [i-1, i-2, i-3]:
                        if j < 10:
                            continue
                        # Sweep conditions on candle j
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

                        # Check that no bar between j and i invalidated the sweep by creating a higher high
                        peak = highs[j]
                        if any(highs[m] > peak for m in range(j+1, i+1)):
                            continue

                        # MSS trigger is swing low around the sweep
                        mss_trig = min(lows[j], lows[j-1])

                        # Ensure this is the first bar closing below mss_trig
                        if any(closes[m] < mss_trig for m in range(j+1, i)):
                            continue

                        # Bar i MUST be the candle that closes below mss_trig with body displacement
                        if closes[i] < mss_trig:
                            b_disp = abs(closes[i] - opens[i]) / bar_rng
                            if b_disp >= 0.35:
                                has_fvg = (lows[i-2] > highs[i]) and ((lows[i-2] - highs[i]) >= c_atr * 0.10)
                                grade = "AAA" if (htf_bear and has_fvg) else ("A+" if (htf_bear or has_fvg) else "A")
                                if grade in ["AAA", "A+"]:
                                    fvg_r = (lows[i-2], highs[i]) if has_fvg else None
                                    ce = calculate_ce_entry(
                                        direction="SHORT",
                                        peak_or_valley=peak,
                                        trigger_price=mss_trig,
                                        close_price=closes[i],
                                        fvg_range=fvg_r,
                                        atr=c_atr,
                                        sl_buffer_atr=sl_buffer_atr,
                                        entry_model="midpoint",
                                        tp1_r=1.0,
                                        tp2_r=3.0,
                                    )
                                    sfp_sig = {
                                        "strategy": "SFP_VOLUME_ANOMALY",
                                        "direction": "SHORT",
                                        "grade": grade,
                                        "entry": ce["entry_price"],
                                        "sl": ce["stop_loss"],
                                        "tp1": ce["tp1"],
                                        "tp2": ce["tp2"],
                                        "risk": ce["risk_distance"],
                                        "zone_low": ce["zone_low"],
                                        "zone_high": ce["zone_high"],
                                        "is_limit": ce["is_limit"],
                                        "pool": p_name,
                                        "trigger_time": dts[i],
                                    }
                                    break

                # Check LONG SFP: sweep at j, confirmed at bar i
                if allow_long and sfp_sig is None:
                    for j in [i-1, i-2, i-3]:
                        if j < 10:
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
                                has_fvg = (lows[i] > highs[i-2]) and ((lows[i] - highs[i-2]) >= c_atr * 0.10)
                                grade = "AAA" if (htf_bull and has_fvg) else ("A+" if (htf_bull or has_fvg) else "A")
                                if grade in ["AAA", "A+"]:
                                    fvg_r = (lows[i], highs[i-2]) if has_fvg else None
                                    ce = calculate_ce_entry(
                                        direction="LONG",
                                        peak_or_valley=valley,
                                        trigger_price=mss_trig,
                                        close_price=closes[i],
                                        fvg_range=fvg_r,
                                        atr=c_atr,
                                        sl_buffer_atr=sl_buffer_atr,
                                        entry_model="midpoint",
                                        tp1_r=1.0,
                                        tp2_r=3.0,
                                    )
                                    sfp_sig = {
                                        "strategy": "SFP_VOLUME_ANOMALY",
                                        "direction": "LONG",
                                        "grade": grade,
                                        "entry": ce["entry_price"],
                                        "sl": ce["stop_loss"],
                                        "tp1": ce["tp1"],
                                        "tp2": ce["tp2"],
                                        "risk": ce["risk_distance"],
                                        "zone_low": ce["zone_low"],
                                        "zone_high": ce["zone_high"],
                                        "is_limit": ce["is_limit"],
                                        "pool": p_name,
                                        "trigger_time": dts[i],
                                    }
                                    break

            # ORB Breakout (Forex only, protected boundary SL)
            if orb_session_active and sfp_sig is None:
                o_h = orb_high[i]
                o_l = orb_low[i]
                vol_ratio = c_vol / max(c_vol_sma, 1e-8)

                if allow_long and c_close > o_h and closes[i-1] <= o_h:
                    if vol_ratio >= 2.0:
                        u_wick = (c_high - c_close) / bar_rng
                        if u_wick <= 0.35 and (c_close - c_open) / bar_rng >= 0.40:
                            ce = calculate_ce_entry(
                                direction="LONG",
                                peak_or_valley=o_l,  # Protective SL below range
                                trigger_price=o_h,
                                close_price=c_close,
                                orb_level=o_h,
                                atr=c_atr,
                                entry_model="midpoint",
                                tp1_r=1.0,
                                tp2_r=3.0,
                            )
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "LONG",
                                "grade": "A+",
                                "entry": ce["entry_price"],
                                "sl": ce["stop_loss"],
                                "tp1": ce["tp1"],
                                "tp2": ce["tp2"],
                                "risk": ce["risk_distance"],
                                "zone_low": ce["zone_low"],
                                "zone_high": ce["zone_high"],
                                "is_limit": ce["is_limit"],
                                "pool": "LONDON_ORB",
                                "trigger_time": dts[i],
                            }

                elif allow_short and c_close < o_l and closes[i-1] >= o_l:
                    if vol_ratio >= 2.0:
                        l_wick = (c_close - c_low) / bar_rng
                        if l_wick <= 0.35 and (c_open - c_close) / bar_rng >= 0.40:
                            ce = calculate_ce_entry(
                                direction="SHORT",
                                peak_or_valley=o_h,  # Protective SL above range
                                trigger_price=o_l,
                                close_price=c_close,
                                orb_level=o_l,
                                atr=c_atr,
                                entry_model="midpoint",
                                tp1_r=1.0,
                                tp2_r=3.0,
                            )
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "SHORT",
                                "grade": "A+",
                                "entry": ce["entry_price"],
                                "sl": ce["stop_loss"],
                                "tp1": ce["tp1"],
                                "tp2": ce["tp2"],
                                "risk": ce["risk_distance"],
                                "zone_low": ce["zone_low"],
                                "zone_high": ce["zone_high"],
                                "is_limit": ce["is_limit"],
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
                    "symbol": sym,
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

        all_trades.extend(trades)

    all_trades.sort(key=lambda x: x["opened_at"])
    total_trades = len(all_trades)
    tp2_cnt = sum(1 for t in all_trades if t["close_reason"] == "TP2_HIT")
    be_cnt = sum(1 for t in all_trades if t["close_reason"] == "BREAK_EVEN")
    sl_cnt = sum(1 for t in all_trades if t["close_reason"] == "STOP_LOSS")
    time_cnt = sum(1 for t in all_trades if t["close_reason"] == "TIME_EXIT")
    net_r = round(sum(t["r_result"] for t in all_trades), 2)
    win_cnt = tp2_cnt + be_cnt
    wr = round(win_cnt / total_trades * 100, 1) if total_trades > 0 else 0
    
    # Check time-travel trades
    time_travel_cnt = sum(1 for t in all_trades if t["closed_at"] <= t["opened_at"])

    print(f"=== RESULT (use_macro={use_macro_gate}, use_mtf_pd={use_mtf_pd}) ===")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {win_cnt} (TP2: {tp2_cnt}, BE: {be_cnt})")
    print(f"Stops: {sl_cnt} | Time Exits: {time_cnt}")
    print(f"Win Rate: {wr}% | Net R: {net_r}R")
    print(f"Time Travel Trades: {time_travel_cnt}")
    return all_trades

if __name__ == '__main__':
    print('Testing configuration with Macro Gate...')
    trades = run_test(use_macro_gate=True, use_mtf_pd=False)
