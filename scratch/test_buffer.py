import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta, date
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from sfp_orb_engine.config import get_asset_sl_buffer, is_crypto
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

def test_proper_buffer(buffer_mult=1.0, entry_type="midpoint"):
    if not mt5.initialize():
        return

    utc_to = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
    utc_from = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)
    warmup_from = utc_from - timedelta(days=25)

    macro_table = DailyMacroGateTable(utc_from.date(), utc_to.date())

    all_trades = []

    for sym in SYMBOLS:
        if sym in EXCLUDED_SYMBOLS:
            continue

        display_sym = f"{sym[:3]}/{sym[3:]}" if len(sym) == 6 and sym.isalpha() else sym
        sl_buffer_atr = get_asset_sl_buffer(display_sym) * buffer_mult
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

        daily = df.groupby("date").agg({"high": "max", "low": "min"}).shift(1)
        df["pdh"] = df["date"].map(daily["high"]).fillna(0.0)
        df["pdl"] = df["date"].map(daily["low"]).fillna(0.0)

        asian_bars = df[df["hour"] < 6]
        df["ash"] = df["date"].map(asian_bars.groupby("date")["high"].max()).fillna(0.0)
        df["asl"] = df["date"].map(asian_bars.groupby("date")["low"].min()).fillna(0.0)

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
        df["vol_sma"] = df["volume"].rolling(20).mean().fillna(df["volume"])

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

            cur_dt = pd.to_datetime(dates_raw[i]).to_pydatetime()
            gate_val = macro_table.get_gate(cur_dt, sym)
            if gate_val == "NEUTRAL_RANGE":
                allow_short = False
                allow_long = False
            elif gate_val == "SHORT_ONLY":
                allow_long = False
            elif gate_val == "LONG_ONLY":
                allow_short = False

            sfp_sig = None
            orb_sig = None

            # SFP sequential lookback
            if sfp_session_active and (allow_short or allow_long):
                if allow_short:
                    for j in [i-1, i-2, i-3]:
                        if j < 10:
                            continue
                        j_rng = max(highs[j] - lows[j], 1e-8)
                        if (highs[j] - max(opens[j], closes[j])) / j_rng < 0.45:
                            continue

                        j_pdh = pdhs[j]
                        j_ash = ashs[j]
                        sw_hi = (highs[j] > j_pdh and closes[j] < j_pdh) or ((7 <= hours[j] <= 11) and j_ash > 0.0 and highs[j] > j_ash and closes[j] < j_ash)
                        if not sw_hi:
                            continue

                        peak = highs[j]
                        if any(highs[m] > peak for m in range(j+1, i+1)):
                            continue

                        mss_trig = min(lows[j], lows[j-1])
                        if any(closes[m] < mss_trig for m in range(j+1, i)):
                            continue

                        if closes[i] < mss_trig:
                            b_disp = abs(closes[i] - opens[i]) / bar_rng
                            if b_disp >= 0.35:
                                has_fvg = (lows[i-2] > highs[i]) and ((lows[i-2] - highs[i]) >= c_atr * 0.10)
                                grade = "AAA" if (htf_bear and has_fvg) else ("A+" if (htf_bear or has_fvg) else "A")
                                if grade in ["AAA", "A+"]:
                                    # Proper buffer: peak + atr * sl_buffer_atr
                                    sl_dist = c_atr * sl_buffer_atr
                                    stop_loss = peak + sl_dist
                                    if entry_type == "midpoint":
                                        ref_low = min(mss_trig, closes[i])
                                        entry_p = (peak + ref_low) / 2.0
                                        is_lim = True
                                    else:
                                        entry_p = closes[i]
                                        is_lim = False
                                    
                                    risk = abs(stop_loss - entry_p)
                                    tp1 = entry_p - risk
                                    tp2 = entry_p - (risk * 3.0)

                                    sfp_sig = {
                                        "strategy": "SFP_VOLUME_ANOMALY",
                                        "direction": "SHORT",
                                        "grade": grade,
                                        "entry": entry_p,
                                        "sl": stop_loss,
                                        "tp1": tp1,
                                        "tp2": tp2,
                                        "risk": risk,
                                        "is_limit": is_lim,
                                        "trigger_time": dts[i],
                                    }
                                    break

                if allow_long and sfp_sig is None:
                    for j in [i-1, i-2, i-3]:
                        if j < 10:
                            continue
                        j_rng = max(highs[j] - lows[j], 1e-8)
                        if (min(opens[j], closes[j]) - lows[j]) / j_rng < 0.45:
                            continue

                        j_pdl = pdls[j]
                        j_asl = asls[j]
                        sw_lo = (lows[j] < j_pdl and closes[j] > j_pdl) or ((7 <= hours[j] <= 11) and j_asl > 0.0 and lows[j] < j_asl and closes[j] > j_asl)
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
                                    sl_dist = c_atr * sl_buffer_atr
                                    stop_loss = valley - sl_dist
                                    if entry_type == "midpoint":
                                        ref_high = max(mss_trig, closes[i])
                                        entry_p = (valley + ref_high) / 2.0
                                        is_lim = True
                                    else:
                                        entry_p = closes[i]
                                        is_lim = False

                                    risk = abs(entry_p - stop_loss)
                                    tp1 = entry_p + risk
                                    tp2 = entry_p + (risk * 3.0)

                                    sfp_sig = {
                                        "strategy": "SFP_VOLUME_ANOMALY",
                                        "direction": "LONG",
                                        "grade": grade,
                                        "entry": entry_p,
                                        "sl": stop_loss,
                                        "tp1": tp1,
                                        "tp2": tp2,
                                        "risk": risk,
                                        "is_limit": is_lim,
                                        "trigger_time": dts[i],
                                    }
                                    break

            # ORB
            if orb_session_active and sfp_sig is None:
                o_h = orb_high[i]
                o_l = orb_low[i]
                vol_ratio = c_vol / max(c_vol_sma, 1e-8)

                if allow_long and c_close > o_h and closes[i-1] <= o_h:
                    if vol_ratio >= 2.0:
                        u_wick = (c_high - c_close) / bar_rng
                        if u_wick <= 0.35 and (c_close - c_open) / bar_rng >= 0.40:
                            sl_dist = c_atr * sl_buffer_atr
                            stop_loss = o_l - sl_dist
                            entry_p = (o_h + c_close) / 2.0 if entry_type == "midpoint" else c_close
                            risk = abs(entry_p - stop_loss)
                            tp1 = entry_p + risk
                            tp2 = entry_p + (risk * 3.0)
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "LONG",
                                "grade": "A+",
                                "entry": entry_p,
                                "sl": stop_loss,
                                "tp1": tp1,
                                "tp2": tp2,
                                "risk": risk,
                                "is_limit": (entry_type == "midpoint"),
                                "trigger_time": dts[i],
                            }

                elif allow_short and c_close < o_l and closes[i-1] >= o_l:
                    if vol_ratio >= 2.0:
                        l_wick = (c_close - c_low) / bar_rng
                        if l_wick <= 0.35 and (c_open - c_close) / bar_rng >= 0.40:
                            sl_dist = c_atr * sl_buffer_atr
                            stop_loss = o_h + sl_dist
                            entry_p = (o_l + c_close) / 2.0 if entry_type == "midpoint" else c_close
                            risk = abs(stop_loss - entry_p)
                            tp1 = entry_p - risk
                            tp2 = entry_p - (risk * 3.0)
                            orb_sig = {
                                "strategy": "ORB_SESSION_BREAKOUT",
                                "direction": "SHORT",
                                "grade": "A+",
                                "entry": entry_p,
                                "sl": stop_loss,
                                "tp1": tp1,
                                "tp2": tp2,
                                "risk": risk,
                                "is_limit": (entry_type == "midpoint"),
                                "trigger_time": dts[i],
                            }

            sig = sfp_sig or orb_sig
            if sig is not None:
                active_position = {
                    "symbol": sym,
                    "strategy": sig["strategy"],
                    "direction": sig["direction"],
                    "grade": sig["grade"],
                    "opened_at": sig["trigger_time"],
                    "entry": sig["entry"],
                    "original_sl": sig["sl"],
                    "current_sl": sig["sl"],
                    "tp1": sig["tp1"],
                    "tp2": sig["tp2"],
                    "risk_pips": sig["risk"],
                    "status": "PENDING_LIMIT" if sig.get("is_limit") else "OPEN",
                    "bars_held": 0,
                    "bars_waiting": 0,
                    "max_wait_bars": 32,
                }

        all_trades.extend(trades)

    all_trades.sort(key=lambda x: x["opened_at"])
    tot = len(all_trades)
    tp2 = sum(1 for t in all_trades if t["close_reason"] == "TP2_HIT")
    be = sum(1 for t in all_trades if t["close_reason"] == "BREAK_EVEN")
    sl = sum(1 for t in all_trades if t["close_reason"] == "STOP_LOSS")
    r = round(sum(t["r_result"] for t in all_trades), 2)
    wr = round((tp2 + be) / tot * 100, 1) if tot > 0 else 0
    print(f"MULT={buffer_mult:.1f} | MODEL={entry_type:<8} -> Trades: {tot:2d} | Wins: {tp2+be:2d} (TP2:{tp2}, BE:{be}) | SL: {sl:2d} | WR: {wr:4.1f}% | Net R: {r:+.2f}R")
    return all_trades

if __name__ == '__main__':
    for model in ["midpoint", "close"]:
        for mult in [1.0, 1.5, 2.0]:
            test_proper_buffer(mult, model)
