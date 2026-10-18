import sys, os
sys.path.insert(0, os.path.abspath("."))
from sfp_orb_engine.engine import BegonyaEngine
from sfp_orb_engine.config import is_crypto, is_market_open, is_session_active_for_scan
import pandas as pd
from datetime import datetime

engine = BegonyaEngine()
forex_symbols = [s for s in engine.symbols if not is_crypto(s)]

print("Scanning historical bars from Oct 12 to Oct 16 across Forex pairs...")

detected_setups = []

for s in forex_symbols:
    try:
        # Fetch 5 days of 15m data
        df = engine.data_provider.fetch_candles(s, interval="15m", outputsize=350)
        if df is None or len(df) < 50:
            continue
        
        # Test bar-by-bar for the last 200 bars (covers roughly Oct 13-16)
        n = len(df)
        for i in range(50, n):
            sub_df = df.iloc[:i+1].copy()
            bar_time = sub_df.iloc[-1]["datetime"]
            
            # Check market open and session
            dt_utc = pd.to_datetime(bar_time)
            if dt_utc.tzinfo is not None:
                dt_utc = dt_utc.tz_localize(None)
            
            # Check SFP
            sfp_res = engine.sfp_detector.detect_sfp(sub_df, s)
            if sfp_res:
                grade = sfp_res.get("grade", "B")
                entry_val = float(sfp_res.get("entry", 0.0))
                risk_val = float(sfp_res.get("risk_pips", 0.0))
                ratio = (risk_val / entry_val) if entry_val > 0 else 0
                pass_risk = (entry_val > 0 and risk_val > 0 and ratio >= 0.0015)
                pass_grade = (grade.startswith("AAA") or grade.startswith("A+"))
                
                # Check session active
                sess_active_old = (7 <= dt_utc.hour <= 11)
                sess_active_new = (7 <= dt_utc.hour <= 11) or (13 <= dt_utc.hour <= 17)
                
                # Macro gate check
                macro = engine.macro_client.evaluate_gate(s, sfp_res["direction"])
                
                detected_setups.append({
                    "symbol": s,
                    "time": str(bar_time),
                    "hour": dt_utc.hour,
                    "strategy": "SFP",
                    "direction": sfp_res["direction"],
                    "grade": grade,
                    "pass_grade": pass_grade,
                    "entry": entry_val,
                    "risk": risk_val,
                    "ratio": ratio,
                    "pass_risk_0015": pass_risk,
                    "sess_old": sess_active_old,
                    "sess_new": sess_active_new,
                    "macro_allowed": macro["allowed"],
                    "macro_reason": macro.get("reason", "")
                })
    except Exception as e:
        print(f"Error on {s}: {e}")

print(f"Total SFP setups detected across history: {len(detected_setups)}")
df_res = pd.DataFrame(detected_setups)
if not df_res.empty:
    print("\nSample detected setups:")
    print(df_res[["symbol", "time", "direction", "grade", "pass_grade", "risk", "ratio", "pass_risk_0015", "sess_old", "macro_allowed"]].tail(25).to_string())
    
    print("\n--- Summary of Bottlenecks ---")
    grade_ok = df_res[df_res["pass_grade"] == True]
    print(f"Setups with Grade AAA / A+: {len(grade_ok)}")
    
    killed_by_risk = grade_ok[grade_ok["pass_risk_0015"] == False]
    print(f"Grade AAA/A+ KILLED by (risk/entry < 0.0015) filter: {len(killed_by_risk)}")
    
    killed_by_sess_old = grade_ok[grade_ok["sess_old"] == False]
    print(f"Grade AAA/A+ KILLED by London-only (07-11) session window: {len(killed_by_sess_old)}")
    
    surviving_old = grade_ok[(grade_ok["pass_risk_0015"] == True) & (grade_ok["sess_old"] == True) & (grade_ok["macro_allowed"] == True)]
    print(f"Grade AAA/A+ surviving under OLD rules: {len(surviving_old)}")
    
    surviving_fixed = grade_ok[(grade_ok["risk"] > 0) & (grade_ok["sess_new"] == True) & (grade_ok["macro_allowed"] == True)]
    print(f"Grade AAA/A+ surviving under FIXED rules (London+NY session, realistic risk filter): {len(surviving_fixed)}")
