import sqlite3
import pandas as pd
from sfp_orb_engine.sfp_detector import SFPDetector
from sfp_orb_engine.strict_setup import confirm_structure
from sfp_orb_engine.entry_mechanics import (
    detect_structural_breaker_long, detect_structural_breaker_short,
    detect_ifvg_long, detect_ifvg_short
)
from sfp_orb_engine import config

conn = sqlite3.connect("data/execution_observations.sqlite3")

for sym in ["EUR/USD", "GBP/USD"]:
    query = f"SELECT bar_time, open, high, low, close, volume FROM bars WHERE symbol='{sym}' AND timeframe='15m' ORDER BY bar_time ASC"
    df = pd.read_sql_query(query, conn)
    df['datetime'] = pd.to_datetime(df['bar_time'])
    df = df.drop_duplicates(subset=['datetime']).sort_values('datetime').reset_index(drop=True)
    
    detector = SFPDetector()
    highs, lows = df.high.values, df.low.values
    opens, closes = df.open.values, df.close.values
    
    sweeps_count = 0
    breaker_count = 0
    ifvg_count = 0
    full_setup_count = 0
    
    for i in range(35, len(df)):
        if df.iloc[i]['datetime'] < pd.Timestamp('2026-10-22', tz='UTC'):
            continue
        atr = detector._calculate_atr(df.iloc[:i+1])
        for direction in ["LONG", "SHORT"]:
            long = direction == "LONG"
            for j in range(i - 1, max(24, i - 4), -1):
                pools = detector.find_pivots_and_pools(df.iloc[:j+1])
                names = ("pdl", "asian_low") if long else ("pdh", "asian_high")
                rng = max(highs[j] - lows[j], 1e-10)
                wick = (min(opens[j], closes[j]) - lows[j]) if long else (highs[j] - max(opens[j], closes[j]))
                if wick / rng < detector.min_wick_ratio:
                    continue
                for name in names:
                    pool = pools.get(name)
                    if not pool or pool["pool_type"] not in config.SFP_ALLOWED_POOLS:
                        continue
                    if name.startswith("asian") and not 7 <= df.iloc[j].datetime.hour <= 11:
                        continue
                    level = pool["price"]
                    swept = lows[j] < level < closes[j] if long else closes[j] < level < highs[j]
                    if not swept:
                        continue
                    sweeps_count += 1
                    
                    extreme = lows[j] if long else highs[j]
                    if any((lows[m] < extreme if long else highs[m] > extreme) for m in range(j+1, i+1)):
                        continue
                    trigger = max(highs[j], highs[j-1]) if long else min(lows[j], lows[j-1])
                    if any((closes[m] > trigger if long else closes[m] < trigger) for m in range(j+1, i)):
                        continue
                    if not (closes[i] > trigger if long else closes[i] < trigger):
                        continue
                    if abs(closes[i] - opens[i]) / max(highs[i] - lows[i], 1e-10) < 0.35:
                        continue
                        
                    b = (detect_structural_breaker_long if long else detect_structural_breaker_short)(
                        j, i, highs, lows, opens, closes
                    )
                    if b:
                        breaker_count += 1
                    
                    z = (detect_ifvg_long if long else detect_ifvg_short)(i, highs, lows, closes, atr)
                    if z:
                        ifvg_count += 1
                        
                    if b and z:
                        full_setup_count += 1
                        print(f"  FULL SETUP FOUND on {sym} at {df.iloc[i]['datetime']} ({direction})")

    print(f"{sym} Summary (since Oct 22):")
    print(f"  Sweeps meeting wick criteria: {sweeps_count}")
    print(f"  Breakers meeting trigger: {breaker_count}")
    print(f"  iFVGs meeting trigger: {ifvg_count}")
    print(f"  Full setups (Sweep + Breaker + iFVG): {full_setup_count}")

conn.close()
