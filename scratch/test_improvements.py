import sys
sys.path.insert(0, '.')
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

US_INDICES = ["NAS100", "SP500", "US30"]

EXCLUDED_SYMBOLS = ["GBPJPY", "AUDUSD"]

def run_improved_backtest(months=1, entry_model="close"):
    if not mt5.initialize():
        print("MT5 init failed")
        return

    utc_to = datetime(2026, 10, 11, 23, 59, tzinfo=timezone.utc)
    if months == 3:
        utc_from = datetime(2026, 7, 11, 0, 0, tzinfo=timezone.utc)
    else:
        utc_from = datetime(2026, 9, 11, 0, 0, tzinfo=timezone.utc)

    warmup_from = utc_from - timedelta(days=60)
    macro_table = DailyMacroGateTable(utc_from.date(), utc_to.date())

    all_trades = []

    for sym in SYMBOLS:
        if sym in EXCLUDED_SYMBOLS:
            continue

        display_sym = f"{sym[:3]}/{sym[3:]}" if len(sym) == 6 and sym.isalpha() else sym
        sl_buffer_atr = get_asset_sl_buffer(display_sym)
        is_crypto_sym = is_crypto(sym)
        is_index_sym = sym in US_INDICES
        is_forex_sym = sym in FOREX_SYMBOLS

        rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M15, warmup_from, utc_to)
        if rates is None or len(rates) < 1000:
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

        # Asian High/Low (00:00 - 06:00 UTC)
        asian_bars = df[df["hour"] < 6]
        df["ash"] = df["date"].map(asian_bars.groupby("date")["high"].max()).fillna(0.0)
        df["asl"] = df["date"].map(asian_bars.groupby("date")["low"].min()).fillna(0.0)

        # 4H EMA Trend (Span 50 & 200 in 4H = 50*16 = 800 and 200*16 = 3200 on M15)
        # Using 400 and 1600 rolling for robust MTF proxy
        df["htf_ema50"] = df["close"].ewm(span=400, adjust=False).mean()
        df["htf_ema200"] = df["close"].ewm(span=1600, adjust=False).mean()

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

        # 1. LONDON ORB (Forex Only, 07:00 UTC)
        london_orb_h = np.zeros(n, dtype=float)
        london_orb_l = np.zeros(n, dtype=float)
        in_london_orb = np.zeros(n, dtype=bool)

        # 2. NY ORB (US Indices Only, 13:30 UTC)
        ny_orb_h = np.zeros(n, dtype=float)
        ny_orb_l = np.zeros(n, dtype=float)
        in_ny_orb = np.zeros(n, dtype=bool)

        cur_lh, cur_ll = 0.0, 0.0
        in_l_sess, l_expire = False, 0

        cur_nyh, cur_nyl = 0.0, 0.0
        in_ny_sess, ny_expire = False, 0

        for i in range(n):
            wday = weekdays[i]
            h_val = hours[i]
            m_val = minutes[i]

            if wday in [5, 6]:
                continue

            # London ORB (Forex)
            if is_forex_sym:
                if h_val == 7 and m_val == 0:
                    cur_lh = highs[i]
                    cur_ll = lows[i]
                    in_l_sess = True
                    l_expire = i + 15
                elif in_l_sess and i <= l_expire:
                    london_orb_h[i] = cur_lh
                    london_orb_l[i] = cur_ll
                    in_london_orb[i] = True
                elif i > l_expire:
                    in_l_sess = False

            # NY ORB (Indices)
            if is_index_sym:
                if h_val == 13 and m_val == 30:
                    cur_nyh = highs[i]
                    cur_nyl = lows[i]
                    in_ny_sess = True
                    ny_expire = i + 15  # 13:45 - 17:30 UTC
                elif in_ny_sess and i <= ny_expire:
                    ny_orb_h[i] = cur_nyh
                    ny_orb_l[i] = cur_nyl
                    in_ny_orb[i] = True
                elif i > ny_expire:
                    in_ny_sess = False

        trades = []
        active_position = None
        cooldown_until = 0

        start_ts = pd.Timestamp(utc_from.replace(tzinfo=None))

        for i in range(200, n):
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

            # Active position check
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
                london_orb_active = False
                ny_orb_active = False
            else:
                sfp_session_active = (7 <= h_val <= 11) or (13 <= h_val <= 17)
                london_orb_active = is_forex_sym and in_london_orb[i] and (7 <= h_val <= 11)
                ny_orb_active = is_index_sym and in_ny_orb[i] and (13 <= h_val <= 17)

            pdh = pdhs[i]
            pdl = pdls[i]
            ash = ashs[i]
            asl = asls[i]
            if pdh == 0.0 or pdl == 0.0:
                continue

            # IMPROVEMENT 1: Katı 4H Pro-Trend Kuralı
            htf_bull = (c_close > ema50s[i]) and (ema50s[i] > ema200s[i])
            htf_bear = (c_close < ema50s[i]) and (ema50s[i] < ema200s[i])

            # Trend Boğa ise SHORT yasak! Trend Ayı ise LONG yasak!
            allow_short = htf_bear or (not htf_bull)
            allow_long = htf_bull or (not htf_bear)

            if htf_bull:
                allow_short = False  # Güçlü boğa trendinde tepe süpürme short'u VETO!
            if htf_bear:
                allow_long = False   # Güçlü ayı trendinde dip süpürme long'u VETO!

            # Macro Gate Check
            cur_dt = pd.to_datetime(dates_raw[i]).to_pydatetime()
            gate_val = macro_table.get_gate(cur_dt, sym)
            if gate_val in ["NEUTRAL_RANGE", "NO_TRADE", "DEFENSIVE_HOLD", "VETO"]:
                allow_short = False
                allow_long = False
            elif gate_val == "SHORT_ONLY":
                allow_long = False
            elif gate_val == "LONG_ONLY":
                allow_short = False

            sfp_sig = None
            orb_sig = None

            # IMPROVEMENT 4: Gerçek Swing Tabanlı MSS + SFP Causal Lookback
            if sfp_session_active and (allow_short or allow_long):
                # SHORT SFP: Tepe süpürmesi j'de, MSS teyidi bar i'de
                if allow_short:
                    for j in [i-1, i-2, i-3]:
                        if j < 15:
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

                        # GERÇEK SWING TABANLI MSS: Süpürmeden önceki salınım dibi (son 5 barın dibi)
                        mss_trig = np.min(lows[max(0, j-6):j])

                        if any(closes[m] < mss_trig for m in range(j+1, i)):
                            continue

                        if closes[i] < mss_trig:
                            b_disp = abs(closes[i] - opens[i]) / bar_rng
                            if b_disp >= 0.35:
                                has_fvg = (lows[i-2] > highs[i]) and ((lows[i-2] - highs[i]) >= c_atr * 0.10)
                                grade = "AAA" if (htf_bear and has_fvg) else ("A+" if (htf_bear or has_fvg) else "A")
                                if grade in ["AAA", "A+"]:
                                    fvg_r = (lows[i-2], highs[i]) if has_fvg else None
                                    ce_calc = calculate_ce_entry(
                                        direction="SHORT",
                                        peak_or_valley=peak,
                                        trigger_price=mss_trig,
                                        close_price=closes[i],
                                        fvg_range=fvg_r,
                                        atr=c_atr,
                                        sl_buffer_atr=sl_buffer_atr,
                                        entry_model=entry_model,
                                        tp1_r=1.0,
                                        tp2_r=3.0,
                                    )
                                    sfp_sig = {
                                        "strategy": "SFP_VOLUME_ANOMALY",
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
                                        "pool": "PDH" if highs[j] > j_pdh else "ASIAN_HIGH",
                                        "trigger_time": dts[i],
                                    }
                                    break

                # LONG SFP: Dip süpürmesi j'de, MSS teyidi bar i'de
                if allow_long and sfp_sig is None:
                    for j in [i-1, i-2, i-3]:
                        if j < 15:
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

                        # GERÇEK SWING TABANLI MSS: Süpürmeden önceki salınım tepesi
                        mss_trig = np.max(highs[max(0, j-6):j])

                        if any(closes[m] > mss_trig for m in range(j+1, i)):
                            continue

                        if closes[i] > mss_trig:
                            b_disp = abs(closes[i] - opens[i]) / bar_rng
                            if b_disp >= 0.35:
                                has_fvg = (lows[i] > highs[i-2]) and ((lows[i] - highs[i-2]) >= c_atr * 0.10)
                                grade = "AAA" if (htf_bull and has_fvg) else ("A+" if (htf_bull or has_fvg) else "A")
                                if grade in ["AAA", "A+"]:
                                    fvg_r = (lows[i], highs[i-2]) if has_fvg else None
                                    ce_calc = calculate_ce_entry(
                                        direction="LONG",
                                        peak_or_valley=valley,
                                        trigger_price=mss_trig,
                                        close_price=closes[i],
                                        fvg_range=fvg_r,
                                        atr=c_atr,
                                        sl_buffer_atr=sl_buffer_atr,
                                        entry_model=entry_model,
                                        tp1_r=1.0,
                                        tp2_r=3.0,
                                    )
                                    sfp_sig = {
                                        "strategy": "SFP_VOLUME_ANOMALY",
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
                                        "pool": "PDL" if lows[j] < j_pdl else "ASIAN_LOW",
                                        "trigger_time": dts[i],
                                    }
                                    break

            # IMPROVEMENT 3: ASYA SIKIŞMASI (COMPRESSION) KONTROLÜ (ORB İÇİN)
            asian_range = max(ash - asl, 0.0) if (ash > 0 and asl > 0) else 0.0
            # Asya seansı günlük ATR'nin %70'inden fazlasını tüketmişse ORB fakeout riski yüksektir
            asian_exhausted = (asian_range > c_atr * 0.70) if (c_atr > 0 and asian_range > 0) else False

            # LONDON ORB (Forex)
            if london_orb_active and sfp_sig is None and not asian_exhausted:
                o_h = london_orb_h[i]
                o_l = london_orb_l[i]
                vol_ratio = c_vol / max(c_vol_sma, 1e-8)

                if allow_long and c_close > o_h and closes[i-1] <= o_h:
                    if vol_ratio >= 2.0:
                        u_wick = (c_high - c_close) / bar_rng
                        if u_wick <= 0.35 and (c_close - c_open) / bar_rng >= 0.40:
                            ce_calc = calculate_ce_entry(
                                direction="LONG",
                                peak_or_valley=o_l,
                                trigger_price=o_h,
                                close_price=c_close,
                                orb_level=o_h,
                                atr=c_atr,
                                sl_buffer_atr=sl_buffer_atr,
                                entry_model=entry_model,
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

                elif allow_short and c_close < o_l and closes[i-1] >= o_l:
                    if vol_ratio >= 2.0:
                        l_wick = (c_close - c_low) / bar_rng
                        if l_wick <= 0.35 and (c_open - c_close) / bar_rng >= 0.40:
                            ce_calc = calculate_ce_entry(
                                direction="SHORT",
                                peak_or_valley=o_h,
                                trigger_price=o_l,
                                close_price=c_close,
                                orb_level=o_l,
                                atr=c_atr,
                                sl_buffer_atr=sl_buffer_atr,
                                entry_model=entry_model,
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

            # IMPROVEMENT 5: NEW YORK NAKİT SEANSI ORB (US Indices, 13:30 UTC)
            if ny_orb_active and sfp_sig is None and orb_sig is None:
                ny_h = ny_orb_h[i]
                ny_l = ny_orb_l[i]
                vol_ratio = c_vol / max(c_vol_sma, 1e-8)

                if allow_long and c_close > ny_h and closes[i-1] <= ny_h:
                    if vol_ratio >= 1.8:
                        u_wick = (c_high - c_close) / bar_rng
                        if u_wick <= 0.35 and (c_close - c_open) / bar_rng >= 0.40:
                            ce_calc = calculate_ce_entry(
                                direction="LONG",
                                peak_or_valley=ny_l,
                                trigger_price=ny_h,
                                close_price=c_close,
                                orb_level=ny_h,
                                atr=c_atr,
                                sl_buffer_atr=sl_buffer_atr,
                                entry_model=entry_model,
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
                                "pool": "NEW_YORK_ORB",
                                "trigger_time": dts[i],
                            }

                elif allow_short and c_close < ny_l and closes[i-1] >= ny_l:
                    if vol_ratio >= 1.8:
                        l_wick = (c_close - c_low) / bar_rng
                        if l_wick <= 0.35 and (c_open - c_close) / bar_rng >= 0.40:
                            ce_calc = calculate_ce_entry(
                                direction="SHORT",
                                peak_or_valley=ny_h,
                                trigger_price=ny_l,
                                close_price=c_close,
                                orb_level=ny_l,
                                atr=c_atr,
                                sl_buffer_atr=sl_buffer_atr,
                                entry_model=entry_model,
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
                                "pool": "NEW_YORK_ORB",
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
                    "status": "PENDING_LIMIT" if sig.get("is_limit", False) else "OPEN",
                    "zone_low": sig.get("zone_low", min(sig["entry"], sig["sl"])),
                    "zone_high": sig.get("zone_high", max(sig["entry"], sig["sl"])),
                    "bars_held": 0,
                    "bars_waiting": 0,
                    "max_wait_bars": 32,
                    "pool": sig.get("pool", ""),
                }

        all_trades.extend(trades)

    all_trades.sort(key=lambda x: x["opened_at"])
    tot = len(all_trades)
    tp2 = sum(1 for t in all_trades if t["close_reason"] == "TP2_HIT")
    be = sum(1 for t in all_trades if t["close_reason"] == "BREAK_EVEN")
    sl = sum(1 for t in all_trades if t["close_reason"] == "STOP_LOSS")
    r = round(sum(t["r_result"] for t in all_trades), 2)
    wr = round((tp2 + be) / tot * 100, 1) if tot > 0 else 0

    print(f"\n========================================================")
    print(f"RESULTS ({months}M, MODEL={entry_model.upper()})")
    print(f"Total Trades: {tot} | Wins: {tp2+be} (TP2: {tp2}, BE: {be}) | Stops: {sl}")
    print(f"Win Rate: %{wr:.1f} | Net R: {r:+.2f}R")
    print(f"========================================================")

    # Per symbol breakdown
    sym_map = {}
    for t in all_trades:
        s = t["symbol"]
        if s not in sym_map:
            sym_map[s] = {"trades": 0, "wins": 0, "sl": 0, "r": 0.0}
        sym_map[s]["trades"] += 1
        if t["r_result"] > 0:
            sym_map[s]["wins"] += 1
        elif t["r_result"] < 0:
            sym_map[s]["sl"] += 1
        sym_map[s]["r"] += t["r_result"]

    for s, st in sorted(sym_map.items()):
        swr = round(st["wins"] / st["trades"] * 100, 1) if st["trades"] else 0
        print(f"  {s:<7}: {st['trades']:2d} trades | WR: %{swr:4.1f} | Net R: {st['r']:+.2f}R")

    return all_trades

if __name__ == '__main__':
    print('Testing 1 Month with Improvements (Full universe)...')
    run_improved_backtest(months=1, entry_model="close")
