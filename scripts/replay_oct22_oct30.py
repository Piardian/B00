import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
import pandas as pd
from sfp_orb_engine.sfp_detector import SFPDetector
from sfp_orb_engine.orb_detector import ORBDetector
from sfp_orb_engine.execution_policy import higher_timeframe_trend, validate_signal
from sfp_orb_engine import config

conn = sqlite3.connect("data/execution_observations.sqlite3")

# Check symbols in bars table
cur = conn.cursor()
cur.execute("SELECT symbol, timeframe, MIN(bar_time), MAX(bar_time), COUNT(*) FROM bars GROUP BY symbol, timeframe")
print("=== Bars in Database ===")
for row in cur.fetchall():
    print(row)

# Let's inspect 15m bars for EUR/USD, GBP/USD, XAU/USD between Oct 22 and Oct 31
for sym in ["EUR/USD", "GBP/USD", "XAU/USD"]:
    query = f"""
    SELECT bar_time, open, high, low, close, volume 
    FROM bars 
    WHERE symbol='{sym}' AND timeframe='15m'
    ORDER BY bar_time ASC
    """
    df_15m = pd.read_sql_query(query, conn)
    df_15m['datetime'] = pd.to_datetime(df_15m['bar_time'])
    # drop duplicates
    df_15m = df_15m.drop_duplicates(subset=['datetime']).sort_values('datetime').reset_index(drop=True)
    
    query_1h = f"""
    SELECT bar_time, open, high, low, close, volume 
    FROM bars 
    WHERE symbol='{sym}' AND timeframe='1h'
    ORDER BY bar_time ASC
    """
    df_1h = pd.read_sql_query(query_1h, conn)
    df_1h['datetime'] = pd.to_datetime(df_1h['bar_time'])
    df_1h = df_1h.drop_duplicates(subset=['datetime']).sort_values('datetime').reset_index(drop=True)
    
    print(f"\n================ {sym} Analysis ================")
    print(f"15m bars: {len(df_15m)} from {df_15m['datetime'].min()} to {df_15m['datetime'].max()}")
    print(f"1h bars:  {len(df_1h)} from {df_1h['datetime'].min()} to {df_1h['datetime'].max()}")
    
    # Filter to Oct 22 onwards
    df_15m_oct = df_15m[df_15m['datetime'] >= pd.Timestamp('2026-10-22', tz='UTC')].copy()
    print(f"15m bars since Oct 22: {len(df_15m_oct)}")
    
    # Let's run SFPDetector and ORBDetector on every bar since Oct 22!
    detector = SFPDetector()
    orb = ORBDetector()
    
    sfp_candidates = []
    orb_candidates = []
    
    for idx in range(35, len(df_15m)):
        current_time = df_15m.iloc[idx]['datetime']
        if current_time < pd.Timestamp('2026-10-22', tz='UTC'):
            continue
            
        sub_df = df_15m.iloc[:idx+1].copy()
        
        # calculate HTF trend at this bar
        hourly_sub = df_1h[df_1h['datetime'] <= current_time].copy()
        htf = higher_timeframe_trend(hourly_sub, current_time + pd.Timedelta(minutes=15)) if len(hourly_sub) >= 200 else "NEUTRAL"
        
        # SFP test
        try:
            res_sfp = detector.detect_sfp(sub_df, sym, htf_trend=htf)
            if res_sfp:
                val_res = validate_signal(res_sfp)
                sfp_candidates.append((current_time, htf, res_sfp, val_res))
        except Exception as e:
            print(f"Error in SFP on {current_time}: {e}")
            break
            
        # ORB test
        try:
            res_orb = orb.detect_orb_breakout(sub_df, sym)
            if res_orb:
                res_orb['htf_trend'] = htf
                val_orb = validate_signal(res_orb)
                orb_candidates.append((current_time, htf, res_orb, val_orb))
        except Exception as e:
            print(f"Error in ORB on {current_time}: {e}")
            break
            
    print(f"SFP Detections for {sym} since Oct 22: {len(sfp_candidates)}")
    for t, htf, sfp, v in sfp_candidates:
        print(f"  [SFP] {t} | HTF={htf} | dir={sfp['direction']} | grade={sfp.get('grade')} | swept={sfp.get('swept_level')} | validation={v}")
        
    print(f"ORB Detections for {sym} since Oct 22: {len(orb_candidates)}")
    for t, htf, orb_sig, v in orb_candidates:
        print(f"  [ORB] {t} | HTF={htf} | dir={orb_sig['direction']} | grade={orb_sig.get('grade')} | validation={v}")

conn.close()
