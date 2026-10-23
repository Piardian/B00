"""Legacy M15 candidate diagnostics, NOT a full live-system backtest.

Known noncausal fill/target ordering and missing live strategy gates invalidate
its results as evidence of executable edge. Kept for reproducibility only.
The report is computed from the saved ledger; see independent review.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

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


def run_symbol(symbol: str, tp1_r: float = 1.2, tp2_r: float = 2.0, buffer_atr: float = 0.1) -> pd.DataFrame:
    path = FILES[symbol]
    df = load_forex_data(path)
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
                        # Dynamic broker friction in R
                        dyn_cost_r = (spread + comm_dist + slip_dist) / max(risk_dist, 1e-8)
                        p["closed_at"] = str(c_time)
                        p["close_reason"] = "SAME_BAR_STOP_LOSS"
                        p["exit_price"] = sl
                        p["gross_r"] = -1.0
                        p["cost_r"] = round(float(dyn_cost_r), 4)
                        p["net_r"] = round(-1.0 - dyn_cost_r, 4)
                        trades.append(p)
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
                # Dynamic cost calculation
                # Stop orders incur spread and slippage. TP limit orders don't pay taker spread.
                slip = slip_dist if "STOP" in close_reason else 0.0
                tot_cost_dist = spread + comm_dist + slip
                dyn_cost_r = tot_cost_dist / max(risk_dist, 1e-8)
                
                p["closed_at"] = str(c_time)
                p["close_reason"] = close_reason
                p["exit_price"] = round(float(exit_price), 5)
                p["gross_r"] = round(float(r_res), 4)
                p["cost_r"] = round(float(dyn_cost_r), 4)
                p["net_r"] = round(float(r_res) - dyn_cost_r, 4)
                trades.append(p)
                active_pos = None
            continue
            
        # 2. SİNYAL TARAMASI
        # Seans Filtresi: Londra (06:00 - 11:00 UTC) ve New York (12:00 - 17:00 UTC)
        h_val = hours[i]
        is_active_session = (6 <= h_val <= 11) or (12 <= h_val <= 17)
        if not is_active_session:
            continue
            
        htf = htf_trends[i]
        if htf not in ("BULLISH", "BEARISH"):
            continue
            
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
            
        # SHORT: HTF Bearish + Premium
        if htf == "BEARISH" and c_close > eq:
            is_single = (c_high > recent_sh and c_close < recent_sh)
            is_two = (p_high > recent_sh and c_close < recent_sh and c_close < p_close and c_close < c_open)
            if not (is_single or is_two):
                continue
            clv = (c_close - c_low) / bar_range
            upper_wick = c_high - max(c_open, c_close)
            if (upper_wick / bar_range) < 0.35 or not (c_close <= c_open or clv <= 0.45):
                continue
                
            peak = max(c_high, p_high) if is_two else c_high
            sl = peak + buffer_atr * c_atr
            mid = (peak + c_close) / 2.0
            risk_dist = sl - mid
            if risk_dist <= 0:
                continue
            tp1 = mid - tp1_r * risk_dist
            tp2 = mid - tp2_r * risk_dist
            
            active_pos = {
                "symbol": symbol,
                "direction": "SHORT",
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
            
        # LONG: HTF Bullish + Discount
        elif htf == "BULLISH" and c_close < eq:
            is_single = (c_low < recent_sl and c_close > recent_sl)
            is_two = (p_low < recent_sl and c_close > recent_sl and c_close > p_close and c_close > c_open)
            if not (is_single or is_two):
                continue
            clv = (c_close - c_low) / bar_range
            lower_wick = min(c_open, c_close) - c_low
            if (lower_wick / bar_range) < 0.35 or not (c_close >= c_open or clv >= 0.55):
                continue
                
            valley = min(c_low, p_low) if is_two else c_low
            sl = valley - buffer_atr * c_atr
            mid = (valley + c_close) / 2.0
            risk_dist = mid - sl
            if risk_dist <= 0:
                continue
            tp1 = mid + tp1_r * risk_dist
            tp2 = mid + tp2_r * risk_dist
            
            active_pos = {
                "symbol": symbol,
                "direction": "LONG",
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
            
    return pd.DataFrame(trades)


def block_bootstrap(trades_df: pd.DataFrame, block_days: int = 5, n_iter: int = 10000, seed: int = 42):
    """5-Day Block Bootstrap resampling to handle cross-asset & intraday clustering."""
    rng = np.random.default_rng(seed)
    df = trades_df.copy()
    df["date"] = pd.to_datetime(df["opened_at"]).dt.date
    unique_dates = np.array(sorted(df["date"].unique()))
    
    # Group dates into 5-day sequential blocks
    blocks = []
    for i in range(0, len(unique_dates), block_days):
        b_dates = set(unique_dates[i:i + block_days])
        b_trades = df[df["date"].isin(b_dates)]["net_r"].values
        blocks.append(b_trades)
        
    n_blocks = len(blocks)
    boot_totals = np.empty(n_iter)
    
    for b in range(n_iter):
        idx = rng.integers(0, n_blocks, size=n_blocks)
        sampled = np.concatenate([blocks[j] for j in idx])
        boot_totals[b] = np.sum(sampled)
        
    ci_lower = np.percentile(boot_totals, 2.5)
    ci_upper = np.percentile(boot_totals, 97.5)
    p_negative = np.mean(boot_totals <= 0)
    return ci_lower, ci_upper, p_negative, boot_totals


def main():
    print("=" * 110)
    print("   LEGACY CANDIDATE ONLY - KNOWN NONCAUSAL FILLS - NOT LIVE EDGE PROOF")
    print("   Data: Real MT5 Broker Data (EURUSD, GBPUSD, XAUUSD)")
    print("   Cost Model: Transaction-level Dynamic Broker Spread + $6/lot Comm + 0.2 pip Slippage")
    print("=" * 110)
    
    all_dfs = []
    for sym in ["EURUSD", "GBPUSD", "XAUUSD"]:
        tdf = run_symbol(sym)
        all_dfs.append(tdf)
        
    tot = pd.concat(all_dfs).sort_values("opened_at").reset_index(drop=True)
    tot["trade_id"] = [f"TR_{i+1:04d}" for i in range(len(tot))]
    tot["dt"] = pd.to_datetime(tot["opened_at"])
    tot["year"] = tot["dt"].dt.year
    tot["year_month"] = tot["dt"].dt.to_period("M").astype(str)
    
    # Save Trade Ledger CSV
    out_csv = BEGONYA_DIR / "data" / "forex_gold_verified_trades.csv"
    tot.to_csv(out_csv, index=False)
    print(f"\n[Legacy Candidate Ledger] {len(tot)} trades saved with dynamic costs: {out_csv}")
    
    n = len(tot)
    w = tot[tot["net_r"] > 0]
    l = tot[tot["net_r"] < 0]
    be = tot[tot["net_r"] == 0]
    
    tot_gross = tot["gross_r"].sum()
    tot_cost = tot["cost_r"].sum()
    tot_net = tot["net_r"].sum()
    
    gw = w["net_r"].sum()
    gl = abs(l["net_r"].sum())
    pf = (gw / gl) if gl > 0 else 999.0
    
    r_vals = tot["net_r"].values
    mean_r = np.mean(r_vals)
    std_r = np.std(r_vals, ddof=1)
    se = std_r / np.sqrt(n)
    
    # Exact Student's t distribution two-tailed p-value
    t_stat = mean_r / se
    df_t = n - 1
    p_two_tailed = 2 * (1 - stats.t.cdf(abs(t_stat), df=df_t))
    p_one_tailed = 1 - stats.t.cdf(t_stat, df=df_t)
    
    # Max Drawdown
    cum_r = np.r_[0., np.cumsum(tot.sort_values("closed_at", kind="stable")["net_r"].values)]
    peak = np.maximum.accumulate(cum_r)
    dd = peak - cum_r
    max_dd = np.max(dd)
    
    # 5-Day Block Bootstrap
    ci_low_boot, ci_high_boot, p_boot_neg, boot_totals = block_bootstrap(tot, block_days=5, n_iter=10000)
    
    print("\n--- EXACT STATISTICAL RE-CALCULATION ---")
    print(f"Total Closed Trades : {n}")
    print(f"Gross R Sum         : {tot_gross:+.2f} R")
    print(f"Total Dynamic Costs : -{tot_cost:.2f} R (Mean: -{tot_cost/n:.3f}R per trade)")
    print(f"Total Net R         : {tot_net:+.2f} R")
    print(f"Profit Factor (PF)  : {pf:.2f}")
    print(f"Win Rate            : {len(w)/n*100:.1f}% ({len(w)}W / {len(l)}L / {len(be)}BE)")
    print(f"Mean Net R per Trade: {mean_r:+.3f} R")
    print(f"Standard Error (SE) : {se:.3f} R")
    print(f"t-statistic         : {t_stat:.2f} (df = {df_t})")
    print(f"p-value (two-tailed): {p_two_tailed:.4f} (Corrected from prior typo)")
    print(f"p-value (one-tailed): {p_one_tailed:.4f}")
    ci_lo, ci_hi = stats.t.interval(.95, df_t, loc=mean_r, scale=se)
    print(f"Student t 95% CI    : [{ci_lo:+.3f}R; {ci_hi:+.3f}R]")
    print(f"5-Day Block Boot 95%: [{ci_low_boot:+.2f}R; {ci_high_boot:+.2f}R] (Portfolio Total)")
    print(f"P(Bootstrap Net <=0): {p_boot_neg*100:.2f}%")
    print(f"Maximum Drawdown    : {max_dd:.2f} R")
    
    # Breakdown by Symbol
    print("\n--- SYMBOL BREAKDOWN (DYNAMIC COSTS) ---")
    sym_rows = []
    for s, g in tot.groupby("symbol"):
        sw = g[g["net_r"] > 0]
        sl = g[g["net_r"] < 0]
        gw_s = sw["net_r"].sum()
        gl_s = abs(sl["net_r"].sum())
        spf = (gw_s / gl_s) if gl_s > 0 else 999.0
        sym_rows.append({
            "Symbol": s, "N": len(g), "WR%": f"{len(sw)/len(g)*100:.1f}%",
            "Gross R": f"{g['gross_r'].sum():+.2f}R",
            "Cost R": f"-{g['cost_r'].sum():.2f}R",
            "Net R": f"{g['net_r'].sum():+.2f}R",
            "PF": f"{spf:.2f}",
            "SameBarSL": len(g[g['close_reason'] == 'SAME_BAR_STOP_LOSS'])
        })
    print(pd.DataFrame(sym_rows).to_string(index=False))
    
    # Breakdown by Year
    print("\n--- ACCURATE YEARLY BREAKDOWN ---")
    year_rows = []
    for y, g in tot.groupby("year"):
        sw = g[g["net_r"] > 0]
        sl = g[g["net_r"] < 0]
        gw_y = sw["net_r"].sum()
        gl_y = abs(sl["net_r"].sum())
        ypf = (gw_y / gl_y) if gl_y > 0 else 999.0
        period_label = f"Dec 2-31, 2024 (1 month)" if y == 2024 else (f"Full Year 2025" if y == 2025 else "Jan 1 - Oct 21, 2026")
        year_rows.append({
            "Year": str(y), "Period": period_label, "N": len(g),
            "WR%": f"{len(sw)/len(g)*100:.1f}%",
            "Net R": f"{g['net_r'].sum():+.2f}R", "PF": f"{ypf:.2f}"
        })
    print(pd.DataFrame(year_rows).to_string(index=False))
    
    # Generate Markdown Report
    rep_md = BEGONYA_DIR / "docs" / "FOREX_GOLD_AUDIT_REPORT.md"
    from scripts.forex_gold_report import write_report
    write_report(out_csv, rep_md)
    print(f"\n[Audit Report] Generated: {rep_md}")

if __name__ == "__main__":
    main()
