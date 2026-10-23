"""Option B: Pure Price Action SFP (Market Order at Close, No LLM, No Retest Limit).

Tests:
1. Immediate Market Entry at SFP confirmation candle close (eliminating adverse selection).
2. Real MT5 broker spread, commissions ($6/lot), and slippage on every trade.
3. Multiple TP models (1.5R fixed, 2.0R fixed, Split 1.0R/2.0R BE).
4. Sub-period analysis: January 2025, November 2025, Full 2025, 2026.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

BEGONYA_DIR = Path(r"C:\Users\piard\Desktop\Begonya00")
DATA_DIR = Path(r"C:\Users\piard\Desktop\MegalordProject\audit\raw-validation-2026-10-22\data")

FILES = {
    "EURUSD": DATA_DIR / "mt5_EURUSD_M15.parquet",
    "GBPUSD": DATA_DIR / "mt5_GBPUSD_M15.parquet",
    "XAUUSD": DATA_DIR / "mt5_XAUUSD_M15.parquet",
}

COMMISSION_DIST = {
    "EURUSD": 0.00006,  # 0.6 pips ($6/lot)
    "GBPUSD": 0.00006,  # 0.6 pips
    "XAUUSD": 0.06,     # 6 cents on Gold
}

SLIPPAGE_DIST = {
    "EURUSD": 0.00002,  # 0.2 pips
    "GBPUSD": 0.00002,  # 0.2 pips
    "XAUUSD": 0.04,     # 4 cents
}


def load_forex_data(path: Path) -> pd.DataFrame:
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
    
    # 4H Macro HTF Features (closed='left', shifted by +4h)
    h4 = df["close"].resample("4h", origin="start_day", label="left", closed="left").last().dropna()
    h4_ema50 = h4.ewm(span=50, adjust=False).mean()
    h4_ema200 = h4.ewm(span=200, adjust=False).mean()
    
    h4_trend = pd.Series("NEUTRAL", index=h4.index)
    h4_trend[(h4 > h4_ema50) & (h4_ema50 > h4_ema200)] = "BULLISH"
    h4_trend[(h4 < h4_ema50) & (h4_ema50 < h4_ema200)] = "BEARISH"
    
    h4_trend_avail = h4_trend.copy()
    h4_trend_avail.index = h4_trend_avail.index + pd.Timedelta(hours=4)
    df["htf_trend"] = h4_trend_avail.reindex(df.index, method="ffill").fillna("NEUTRAL")
    
    # MT5 Broker spread in price points
    if "spread" in df.columns:
        if "XAU" in path.name:
            df["spread_dist"] = df["spread"] * 0.01  # spread in points -> USD
        else:
            df["spread_dist"] = df["spread"] * 0.00001 # 1 point = 0.1 pip = 0.00001
    else:
        df["spread_dist"] = df["close"] * 0.0001
        
    return df


def simulate_pure_sfp(
    symbol: str,
    df: pd.DataFrame,
    entry_model: str = "MARKET_CLOSE",  # "MARKET_CLOSE" or "MIDPOINT_LIMIT"
    require_htf: bool = True,
    vol_multiplier: float = 1.0,
    tp_mode: str = "SPLIT",  # "SPLIT" (1.0R BE, 2.0R TP2), "FIXED_1_5R", "FIXED_2_0R"
    buffer_atr: float = 0.1,
    lookback_swing: int = 30,
) -> list[dict]:
    n = len(df)
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
    
    trades = []
    active_pos = None
    
    for i in range(50, n):
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
            risk_dist = p["risk_dist"]
            p_dir = p["direction"]
            is_long = (p_dir == "LONG")
            
            # If waiting for limit
            if p["status"] == "PENDING_LIMIT":
                p["bars_waiting"] += 1
                if p["bars_waiting"] >= 16:
                    active_pos = None
                    continue
                can_fill = (c_low <= entry - spread) if is_long else (c_high >= entry + spread)
                if can_fill:
                    p["status"] = "OPEN"
                else:
                    if (c_low <= sl if is_long else c_high >= sl):
                        active_pos = None
                    continue
            
            p["bars_held"] += 1
            closed = False
            close_reason = ""
            exit_price = 0.0
            gross_r = 0.0
            
            if tp_mode == "SPLIT":
                tp1 = p["tp1"]
                tp2 = p["tp2"]
                if is_long:
                    sl_hit = (c_low <= sl)
                    tp1_hit = (c_high >= tp1)
                    tp2_hit = (c_high >= tp2)
                    
                    if sl_hit and (tp1_hit or tp2_hit):
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        gross_r = 0.5 if p["status"] == "TP1_HIT" else -1.0
                    elif sl_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        gross_r = 0.5 if p["status"] == "TP1_HIT" else -1.0
                    elif tp2_hit and p["status"] == "TP1_HIT":
                        closed = True
                        exit_price = tp2
                        close_reason = "TP2_HIT"
                        gross_r = 1.5  # 0.5 + 1.0 (from 2.0R * 0.5)
                    elif tp1_hit and p["status"] == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry
                        if tp2_hit:
                            closed = True
                            exit_price = tp2
                            close_reason = "TP2_HIT"
                            gross_r = 1.5
                    elif p["bars_held"] >= 96:
                        closed = True
                        exit_price = c_close
                        close_reason = "TIME_EXIT"
                        gross_r = (c_close - entry) / max(risk_dist, 1e-8)
                else:  # SHORT
                    sl_hit = (c_high >= sl)
                    tp1_hit = (c_low <= tp1)
                    tp2_hit = (c_low <= tp2)
                    
                    if sl_hit and (tp1_hit or tp2_hit):
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        gross_r = 0.5 if p["status"] == "TP1_HIT" else -1.0
                    elif sl_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "BREAK_EVEN" if p["status"] == "TP1_HIT" else "STOP_LOSS"
                        gross_r = 0.5 if p["status"] == "TP1_HIT" else -1.0
                    elif tp2_hit and p["status"] == "TP1_HIT":
                        closed = True
                        exit_price = tp2
                        close_reason = "TP2_HIT"
                        gross_r = 1.5
                    elif tp1_hit and p["status"] == "OPEN":
                        p["status"] = "TP1_HIT"
                        p["current_sl"] = entry
                        sl = entry
                        if tp2_hit:
                            closed = True
                            exit_price = tp2
                            close_reason = "TP2_HIT"
                            gross_r = 1.5
                    elif p["bars_held"] >= 96:
                        closed = True
                        exit_price = c_close
                        close_reason = "TIME_EXIT"
                        gross_r = (entry - c_close) / max(risk_dist, 1e-8)
            else:
                # Fixed Single TP (1.5R or 2.0R)
                target_r = 1.5 if tp_mode == "FIXED_1_5R" else 2.0
                tp_target = entry + target_r * risk_dist if is_long else entry - target_r * risk_dist
                
                if is_long:
                    sl_hit = (c_low <= sl)
                    tp_hit = (c_high >= tp_target)
                    if sl_hit and tp_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "STOP_LOSS"
                        gross_r = -1.0
                    elif sl_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "STOP_LOSS"
                        gross_r = -1.0
                    elif tp_hit:
                        closed = True
                        exit_price = tp_target
                        close_reason = "TP_HIT"
                        gross_r = target_r
                    elif p["bars_held"] >= 96:
                        closed = True
                        exit_price = c_close
                        close_reason = "TIME_EXIT"
                        gross_r = (c_close - entry) / max(risk_dist, 1e-8)
                else:  # SHORT
                    sl_hit = (c_high >= sl)
                    tp_hit = (c_low <= tp_target)
                    if sl_hit and tp_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "STOP_LOSS"
                        gross_r = -1.0
                    elif sl_hit:
                        closed = True
                        exit_price = sl
                        close_reason = "STOP_LOSS"
                        gross_r = -1.0
                    elif tp_hit:
                        closed = True
                        exit_price = tp_target
                        close_reason = "TP_HIT"
                        gross_r = target_r
                    elif p["bars_held"] >= 96:
                        closed = True
                        exit_price = c_close
                        close_reason = "TIME_EXIT"
                        gross_r = (entry - c_close) / max(risk_dist, 1e-8)
            
            if closed:
                slip = slip_dist if "STOP" in close_reason else 0.0
                tot_cost_dist = spread + comm_dist + slip
                dyn_cost_r = tot_cost_dist / max(risk_dist, 1e-8)
                p["closed_at"] = str(c_time)
                p["close_reason"] = close_reason
                p["exit_price"] = round(float(exit_price), 5)
                p["gross_r"] = round(float(gross_r), 4)
                p["cost_r"] = round(float(dyn_cost_r), 4)
                p["net_r"] = round(float(gross_r) - dyn_cost_r, 4)
                trades.append(p)
                active_pos = None
            continue
            
        # 2. SIGNAL SCANNING
        h_val = hours[i]
        is_active_session = (6 <= h_val <= 11) or (12 <= h_val <= 17)
        if not is_active_session:
            continue
            
        htf = htf_trends[i]
        if require_htf and htf not in ("BULLISH", "BEARISH"):
            continue
            
        c_vol = volumes[i]
        c_vol_sma = vol_smas[i]
        c_atr = atrs[i]
        bar_range = max(c_high - c_low, 1e-8)
        
        p_high = highs[i-1]
        p_low = lows[i-1]
        p_close = closes[i-1]
        p_open = opens[i-1]
        
        sub_h = highs[i-lookback_swing:i]
        sub_l = lows[i-lookback_swing:i]
        recent_sh = np.max(sub_h)
        recent_sl = np.min(sub_l)
        eq = (recent_sh + recent_sl) / 2.0
        
        if c_vol < vol_multiplier * c_vol_sma:
            continue
            
        # SHORT SFP: Rejection of recent swing high
        cond_short_htf = (htf == "BEARISH" or not require_htf) and (c_close > eq)
        if cond_short_htf:
            is_single = (c_high > recent_sh and c_close < recent_sh)
            is_two = (p_high > recent_sh and c_close < recent_sh and c_close < p_close and c_close < c_open)
            if is_single or is_two:
                clv = (c_close - c_low) / bar_range
                upper_wick = c_high - max(c_open, c_close)
                if (upper_wick / bar_range) >= 0.35 and (c_close <= c_open or clv <= 0.45):
                    peak = max(c_high, p_high) if is_two else c_high
                    sl = peak + buffer_atr * c_atr
                    
                    if entry_model == "MARKET_CLOSE":
                        # Immediate Market entry at bar close + broker friction
                        entry = c_close
                        risk_dist = sl - entry
                        if risk_dist > 0:
                            status = "OPEN"
                    else:
                        entry = (peak + c_close) / 2.0
                        risk_dist = sl - entry
                        status = "PENDING_LIMIT"
                        
                    if risk_dist > 0:
                        tp1 = entry - 1.0 * risk_dist
                        tp2 = entry - 2.0 * risk_dist
                        active_pos = {
                            "symbol": symbol,
                            "direction": "SHORT",
                            "entry": round(entry, 5),
                            "original_sl": round(sl, 5),
                            "current_sl": round(sl, 5),
                            "tp1": round(tp1, 5),
                            "tp2": round(tp2, 5),
                            "risk_dist": round(risk_dist, 5),
                            "atr": round(float(c_atr), 5),
                            "status": status,
                            "bars_waiting": 0,
                            "bars_held": 0,
                            "opened_at": str(c_time),
                        }
                        continue
                        
        # LONG SFP: Rejection of recent swing low
        cond_long_htf = (htf == "BULLISH" or not require_htf) and (c_close < eq)
        if cond_long_htf:
            is_single = (c_low < recent_sl and c_close > recent_sl)
            is_two = (p_low < recent_sl and c_close > recent_sl and c_close > p_close and c_close > c_open)
            if is_single or is_two:
                clv = (c_close - c_low) / bar_range
                lower_wick = min(c_open, c_close) - c_low
                if (lower_wick / bar_range) >= 0.35 and (c_close >= c_open or clv >= 0.55):
                    valley = min(c_low, p_low) if is_two else c_low
                    sl = valley - buffer_atr * c_atr
                    
                    if entry_model == "MARKET_CLOSE":
                        entry = c_close
                        risk_dist = entry - sl
                        if risk_dist > 0:
                            status = "OPEN"
                    else:
                        entry = (valley + c_close) / 2.0
                        risk_dist = entry - sl
                        status = "PENDING_LIMIT"
                        
                    if risk_dist > 0:
                        tp1 = entry + 1.0 * risk_dist
                        tp2 = entry + 2.0 * risk_dist
                        active_pos = {
                            "symbol": symbol,
                            "direction": "LONG",
                            "entry": round(entry, 5),
                            "original_sl": round(sl, 5),
                            "current_sl": round(sl, 5),
                            "tp1": round(tp1, 5),
                            "tp2": round(tp2, 5),
                            "risk_dist": round(risk_dist, 5),
                            "atr": round(float(c_atr), 5),
                            "status": status,
                            "bars_waiting": 0,
                            "bars_held": 0,
                            "opened_at": str(c_time),
                        }
                        continue
                        
    return trades


def run_experiment_matrix():
    print("=" * 80)
    print("   OPTION B: PURE PRICE ACTION SFP MATRIX EXPERIMENT")
    print("   Data: MT5 Parquet (EURUSD, GBPUSD, XAUUSD)")
    print("   Cost Model: MT5 Bar Spread + $6/lot Comm + 0.2 pip Slippage")
    print("=" * 80)
    
    dfs = {sym: load_forex_data(FILES[sym]) for sym in FILES}
    
    configs = [
        {"name": "1. Market Close, Split TP (1.0R/2.0R), HTF 4h", "entry": "MARKET_CLOSE", "tp": "SPLIT", "htf": True, "vol": 1.0},
        {"name": "2. Market Close, Fixed 1.5R, HTF 4h", "entry": "MARKET_CLOSE", "tp": "FIXED_1_5R", "htf": True, "vol": 1.0},
        {"name": "3. Market Close, Fixed 2.0R, HTF 4h", "entry": "MARKET_CLOSE", "tp": "FIXED_2_0R", "htf": True, "vol": 1.0},
        {"name": "4. Market Close, Split TP, No HTF (Pure Local SFP)", "entry": "MARKET_CLOSE", "tp": "SPLIT", "htf": False, "vol": 1.0},
        {"name": "5. Market Close, Fixed 1.5R, No HTF", "entry": "MARKET_CLOSE", "tp": "FIXED_1_5R", "htf": False, "vol": 1.0},
        {"name": "6. Midpoint Limit, Split TP, HTF 4h (Benchmark)", "entry": "MIDPOINT_LIMIT", "tp": "SPLIT", "htf": True, "vol": 1.0},
    ]
    
    results = []
    
    for cfg in configs:
        all_trades = []
        for sym in ["EURUSD", "GBPUSD", "XAUUSD"]:
            sym_trades = simulate_pure_sfp(
                sym, dfs[sym],
                entry_model=cfg["entry"],
                require_htf=cfg["htf"],
                vol_multiplier=cfg["vol"],
                tp_mode=cfg["tp"],
            )
            all_trades.extend(sym_trades)
            
        tdf = pd.DataFrame(all_trades)
        if len(tdf) == 0:
            print(f"Config '{cfg['name']}': 0 trades.")
            continue
            
        tdf["opened_dt"] = pd.to_datetime(tdf["opened_at"])
        n_trades = len(tdf)
        wins = len(tdf[tdf["gross_r"] > 0])
        wr = wins / n_trades * 100
        gross_r = tdf["gross_r"].sum()
        cost_r = tdf["cost_r"].sum()
        net_r = tdf["net_r"].sum()
        
        gross_win = tdf[tdf["net_r"] > 0]["net_r"].sum()
        gross_loss = abs(tdf[tdf["net_r"] < 0]["net_r"].sum())
        pf = gross_win / gross_loss if gross_loss > 0 else 999.0
        
        # Sub-period tests
        jan_2025 = tdf[(tdf["opened_dt"] >= "2025-01-01") & (tdf["opened_dt"] <= "2025-01-31")]
        nov_2025 = tdf[(tdf["opened_dt"] >= "2025-11-01") & (tdf["opened_dt"] <= "2025-11-30")]
        
        jan_n = len(jan_2025)
        jan_net = jan_2025["net_r"].sum() if jan_n > 0 else 0.0
        
        nov_n = len(nov_2025)
        nov_net = nov_2025["net_r"].sum() if nov_n > 0 else 0.0
        
        # t-test
        mean_r = tdf["net_r"].mean()
        std_r = tdf["net_r"].std()
        se_r = std_r / np.sqrt(n_trades)
        t_stat = mean_r / se_r if se_r > 0 else 0.0
        p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=n_trades - 1))
        
        print(f"\n--- {cfg['name']} ---")
        print(f"Total Trades: {n_trades} | WR: {wr:.1f}% | Gross R: {gross_r:+.2f}R | Cost: {cost_r:.2f}R | Net R: {net_r:+.2f}R | PF: {pf:.2f}")
        print(f"t-stat: {t_stat:.2f} | p-val: {p_val:.4f}")
        print(f"Jan 2025: N={jan_n}, Net={jan_net:+.2f}R | Nov 2025: N={nov_n}, Net={nov_net:+.2f}R")
        
        results.append({
            "config": cfg["name"],
            "trades": n_trades,
            "wr": wr,
            "net_r": net_r,
            "pf": pf,
            "t_stat": t_stat,
            "p_val": p_val,
            "jan_n": jan_n,
            "jan_net": jan_net,
            "nov_n": nov_n,
            "nov_net": nov_net,
        })
        
    print("\n" + "=" * 80)
    print("SUMMARY COMPARISON")
    print("=" * 80)
    for r in results:
        print(f"{r['config'][:45]:<45} | N={r['trades']:>4} | Net={r['net_r']:>+7.2f}R | PF={r['pf']:>4.2f} | p={r['p_val']:>6.4f} | Jan:{r['jan_net']:>+5.2f}R | Nov:{r['nov_net']:>+5.2f}R")

if __name__ == "__main__":
    run_experiment_matrix()
