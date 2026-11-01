"""
Rigorous comparative backtest: AAA+ Only vs AAA+ & A+ (All Confirmed)
Using real tick/M15 historical quote data with authentic broker spreads, commissions, and slippage.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

BEGONYA_DIR = Path(r"C:\Users\piard\Desktop\Begonya00")
sys.path.insert(0, str(BEGONYA_DIR))

from sfp_orb_engine.entry_mechanics import is_slice_through_candle

DATA_DIR = Path(r"C:\Users\piard\Desktop\MegalordProject\audit\raw-validation-2026-10-22\data")
FILES = {
    "EURUSD": DATA_DIR / "mt5_EURUSD_M15.parquet",
    "GBPUSD": DATA_DIR / "mt5_GBPUSD_M15.parquet",
    "XAUUSD": DATA_DIR / "mt5_XAUUSD_M15.parquet",
}

COMMISSION_DIST = {
    "EURUSD": 0.00006,  # 0.6 pips ($6/lot round turn)
    "GBPUSD": 0.00006,  # 0.6 pips
    "XAUUSD": 0.06,     # 6 cents on Gold
}

SLIPPAGE_DIST = {
    "EURUSD": 0.00002,  # 0.2 pips
    "GBPUSD": 0.00002,  # 0.2 pips
    "XAUUSD": 0.04,     # 4 cents
}

def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df.sort_index()
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df["volume"] = df["tick_volume"].astype(float)
    df["vol_sma"] = df["volume"].rolling(20).mean().fillna(df["volume"])
    
    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            np.abs(df["high"] - df["close"].shift(1)),
            np.abs(df["low"] - df["close"].shift(1))
        )
    )
    df["atr"] = tr.rolling(14).mean().fillna(df["high"] - df["low"])
    
    # 4H Macro HTF Features (closed='left', shifted by +4h to prevent lookahead bias)
    h4 = df["close"].resample("4h", origin="start_day", label="left", closed="left").last().dropna()
    h4_ema50 = h4.ewm(span=50, adjust=False).mean()
    h4_ema200 = h4.ewm(span=200, adjust=False).mean()
    
    h4_trend = pd.Series("NEUTRAL", index=h4.index)
    h4_trend[(h4 > h4_ema50) & (h4_ema50 > h4_ema200)] = "BULLISH"
    h4_trend[(h4 < h4_ema50) & (h4_ema50 < h4_ema200)] = "BEARISH"
    
    h4_trend_avail = h4_trend.copy()
    h4_trend_avail.index = h4_trend_avail.index + pd.Timedelta(hours=4)
    df["htf_trend"] = h4_trend_avail.reindex(df.index, method="ffill").fillna("NEUTRAL")
    
    if "spread" in df.columns:
        if "XAU" in path.name:
            df["spread_dist"] = df["spread"] * 0.01
        else:
            df["spread_dist"] = df["spread"] * 0.00001
    else:
        df["spread_dist"] = df["close"] * 0.0001
        
    return df

def run_simulation(start_date: str, end_date: str, allow_a_plus: bool = False):
    all_trades = []
    
    for symbol, path in FILES.items():
        df = load_data(path)
        
        # Filter to target range (with lookback buffer)
        sub_df = df.loc[start_date:end_date]
        if sub_df.empty:
            continue
        
        # We start indices within sub_df
        start_idx = df.index.get_loc(sub_df.index[0])
        end_idx = df.index.get_loc(sub_df.index[-1])
        
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        volumes = df["volume"].values
        vol_smas = df["vol_sma"].values
        atrs = df["atr"].values
        htf_trends = df["htf_trend"].values
        spreads = df["spread_dist"].values
        dts = df.index.values
        hours = df.index.hour.values
        
        comm_dist = COMMISSION_DIST[symbol]
        slip_dist = SLIPPAGE_DIST[symbol]
        tp1_r, tp2_r = 1.2, 2.0
        buffer_atr = 0.1
        
        active_pos = None
        
        for i in range(max(50, start_idx), end_idx + 1):
            c_time = pd.Timestamp(dts[i])
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]
            spread = spreads[i]
            
            # 1. Manage Active Position
            if active_pos is not None:
                p = active_pos
                entry = p["entry"]
                sl = p["current_sl"]
                tp1 = p["tp1"]
                tp2 = p["tp2"]
                risk_dist = p["risk_dist"]
                p_dir = p["direction"]
                is_long = (p_dir == "LONG")
                
                if p["status"] == "PENDING_LIMIT":
                    p["bars_waiting"] += 1
                    if p["bars_waiting"] >= 16:
                        active_pos = None
                        continue
                        
                    can_fill = (c_low <= entry - spread) if is_long else (c_high >= entry + spread)
                    if can_fill:
                        z_low = min(entry, sl)
                        z_high = max(entry, sl)
                        if is_slice_through_candle(p_dir, c_open, c_high, c_low, c_close, z_low, z_high):
                            active_pos = None
                            continue
                            
                        same_bar_sl = (c_low <= sl) if is_long else (c_high >= sl)
                        if same_bar_sl:
                            dyn_cost_r = (spread + comm_dist + slip_dist) / max(risk_dist, 1e-8)
                            p["closed_at"] = str(c_time)
                            p["close_reason"] = "SAME_BAR_STOP_LOSS"
                            p["exit_price"] = sl
                            p["gross_r"] = -1.0
                            p["cost_r"] = round(float(dyn_cost_r), 4)
                            p["net_r"] = round(-1.0 - dyn_cost_r, 4)
                            all_trades.append(p)
                            active_pos = None
                            continue
                        else:
                            p["status"] = "OPEN"
                    else:
                        if (c_low <= sl if is_long else c_high >= sl):
                            active_pos = None
                            continue
                        else:
                            continue
                            
                p["bars_held"] += 1
                closed = False
                close_reason = ""
                exit_price = 0.0
                r_res = 0.0
                
                if is_long:
                    sl_hit = (c_low <= sl)
                    tp1_hit = (c_high >= tp1)
                    tp2_hit = (c_high >= tp2)
                    
                    if sl_hit and (tp1_hit or tp2_hit):
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        r_res = (tp1_r * 0.5) if p["status"] == "TP1_HIT" else -1.0
                    elif sl_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        r_res = (tp1_r * 0.5) if p["status"] == "TP1_HIT" else -1.0
                    elif tp2_hit and p["status"] == "TP1_HIT":
                        closed = True
                        exit_price = tp2
                        close_reason = "TP2_HIT"
                        r_res = (tp1_r * 0.5) + (tp2_r * 0.5)
                    elif tp1_hit and p["status"] == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry
                        if tp2_hit:
                            closed = True
                            exit_price = tp2
                            close_reason = "TP2_HIT"
                            r_res = (tp1_r * 0.5) + (tp2_r * 0.5)
                    elif p["bars_held"] >= 96:
                        closed = True
                        exit_price = c_close
                        close_reason = "TIME_EXIT"
                        r_res = (c_close - entry) / max(risk_dist, 1e-8)
                else:  # SHORT
                    sl_hit = (c_high >= sl)
                    tp1_hit = (c_low <= tp1)
                    tp2_hit = (c_low <= tp2)
                    
                    if sl_hit and (tp1_hit or tp2_hit):
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        r_res = (tp1_r * 0.5) if p["status"] == "TP1_HIT" else -1.0
                    elif sl_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        r_res = (tp1_r * 0.5) if p["status"] == "TP1_HIT" else -1.0
                    elif tp2_hit and p["status"] == "TP1_HIT":
                        closed = True
                        exit_price = tp2
                        close_reason = "TP2_HIT"
                        r_res = (tp1_r * 0.5) + (tp2_r * 0.5)
                    elif tp1_hit and p["status"] == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry
                        if tp2_hit:
                            closed = True
                            exit_price = tp2
                            close_reason = "TP2_HIT"
                            r_res = (tp1_r * 0.5) + (tp2_r * 0.5)
                    elif p["bars_held"] >= 96:
                        closed = True
                        exit_price = c_close
                        close_reason = "TIME_EXIT"
                        r_res = (entry - c_close) / max(risk_dist, 1e-8)
                        
                if closed:
                    slip = slip_dist if "STOP" in close_reason else 0.0
                    tot_cost_dist = spread + comm_dist + slip
                    dyn_cost_r = tot_cost_dist / max(risk_dist, 1e-8)
                    
                    p["closed_at"] = str(c_time)
                    p["close_reason"] = close_reason
                    p["exit_price"] = round(float(exit_price), 5)
                    p["gross_r"] = round(float(r_res), 4)
                    p["cost_r"] = round(float(dyn_cost_r), 4)
                    p["net_r"] = round(float(r_res) - dyn_cost_r, 4)
                    all_trades.append(p)
                    active_pos = None
                continue
                
            # 2. SIGNAL SCANNING
            h_val = hours[i]
            is_active_session = (6 <= h_val <= 11) or (12 <= h_val <= 17)
            if not is_active_session:
                continue
                
            htf = htf_trends[i]
            
            # Filter condition based on mode
            if not allow_a_plus:
                # AAA+ ONLY: Must be strictly BULLISH or BEARISH (Pro-Trend)
                if htf not in ("BULLISH", "BEARISH"):
                    continue
            else:
                # A+ ALLOWED: Can trade NEUTRAL as well (or counter-trend A+)
                pass
                
            c_vol = volumes[i]
            c_vol_sma = vol_smas[i]
            c_atr = atrs[i]
            bar_range = max(c_high - c_low, 1e-8)
            
            p_high = highs[i-1]
            p_low = lows[i-1]
            p_close = closes[i-1]
            p_open = opens[i-1]
            
            sub_h = highs[i-30:i]
            sub_l = lows[i-30:i]
            recent_sh = np.max(sub_h)
            recent_sl = np.min(sub_l)
            eq = (recent_sh + recent_sl) / 2.0
            
            if c_vol < 1.3 * c_vol_sma:
                continue
                
            # SHORT: Premium
            short_eligible = (htf == "BEARISH") if not allow_a_plus else (htf in ("BEARISH", "NEUTRAL"))
            if short_eligible and c_close > eq:
                is_single = (c_high > recent_sh and c_close < recent_sh)
                is_two = (p_high > recent_sh and c_close < recent_sh and c_close < p_close and c_close < c_open)
                if is_single or is_two:
                    clv = (c_close - c_low) / bar_range
                    upper_wick = c_high - max(c_open, c_close)
                    if (upper_wick / bar_range) >= 0.35 and (c_close <= c_open or clv <= 0.45):
                        peak = max(c_high, p_high) if is_two else c_high
                        sl = peak + buffer_atr * c_atr
                        mid = (peak + c_close) / 2.0
                        risk_dist = sl - mid
                        if risk_dist > 0:
                            tp1 = mid - tp1_r * risk_dist
                            tp2 = mid - tp2_r * risk_dist
                            grade = "AAA" if htf == "BEARISH" else "A+"
                            active_pos = {
                                "symbol": symbol,
                                "direction": "SHORT",
                                "grade": grade,
                                "entry": round(mid, 5),
                                "original_sl": round(sl, 5),
                                "current_sl": round(sl, 5),
                                "tp1": round(tp1, 5),
                                "tp2": round(tp2, 5),
                                "risk_dist": round(risk_dist, 5),
                                "atr": round(float(c_atr), 5),
                                "status": "PENDING_LIMIT",
                                "bars_waiting": 0,
                                "bars_held": 0,
                                "opened_at": str(c_time),
                            }
                            continue
                            
            # LONG: Discount
            long_eligible = (htf == "BULLISH") if not allow_a_plus else (htf in ("BULLISH", "NEUTRAL"))
            if long_eligible and c_close < eq:
                is_single = (c_low < recent_sl and c_close > recent_sl)
                is_two = (p_low < recent_sl and c_close > recent_sl and c_close > p_close and c_close > c_open)
                if is_single or is_two:
                    clv = (c_close - c_low) / bar_range
                    lower_wick = min(c_open, c_close) - c_low
                    if (lower_wick / bar_range) >= 0.35 and (c_close >= c_open or clv >= 0.55):
                        trough = min(c_low, p_low) if is_two else c_low
                        sl = trough - buffer_atr * c_atr
                        mid = (trough + c_close) / 2.0
                        risk_dist = mid - sl
                        if risk_dist > 0:
                            tp1 = mid + tp1_r * risk_dist
                            tp2 = mid + tp2_r * risk_dist
                            grade = "AAA" if htf == "BULLISH" else "A+"
                            active_pos = {
                                "symbol": symbol,
                                "direction": "LONG",
                                "grade": grade,
                                "entry": round(mid, 5),
                                "original_sl": round(sl, 5),
                                "current_sl": round(sl, 5),
                                "tp1": round(tp1, 5),
                                "tp2": round(tp2, 5),
                                "risk_dist": round(risk_dist, 5),
                                "atr": round(float(c_atr), 5),
                                "status": "PENDING_LIMIT",
                                "bars_waiting": 0,
                                "bars_held": 0,
                                "opened_at": str(c_time),
                            }
                            continue
                            
    return pd.DataFrame(all_trades)

if __name__ == "__main__":
    months = ["2025-03", "2025-05", "2025-10"]
    for m in months:
        start = f"{m}-01"
        end = (pd.Period(m, freq="M").end_time).strftime("%Y-%m-%d 23:59:59")
        print(f"\n=================== TESTING {m} ({start} to {end}) ===================")
        
        # 1. Run AAA+ ONLY
        df_aaa = run_simulation(start, end, allow_a_plus=False)
        # 2. Run AAA+ & A+ (All confirmed)
        df_all = run_simulation(start, end, allow_a_plus=True)
        
        for label, df_res in [("GRADE AAA+ ONLY", df_aaa), ("GRADE AAA+ & A+ COMBINED", df_all)]:
            if df_res.empty:
                print(f"[{label}] 0 closed filled trades.")
                continue
            wins = len(df_res[df_res["net_r"] > 0])
            losses = len(df_res[df_res["net_r"] <= 0])
            total = len(df_res)
            win_rate = (wins / total) * 100
            gross_r = df_res["gross_r"].sum()
            cost_r = df_res["cost_r"].sum()
            net_r = df_res["net_r"].sum()
            ev = net_r / total
            
            print(f"--- {label} ---")
            print(f"Total Trades: {total} | Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
            print(f"Gross R: {gross_r:+.2f}R | Total Dynamic Friction (Spread+Comm+Slip): {cost_r:.2f}R | NET R: {net_r:+.2f}R")
            print(f"Expected Value per Trade: {ev:+.2f}R")
            if "grade" in df_res.columns:
                print("Breakdown by Grade:", df_res["grade"].value_counts().to_dict())
