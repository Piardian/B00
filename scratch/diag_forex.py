import sys, os
sys.path.insert(0, os.path.abspath("."))
from sfp_orb_engine.engine import BegonyaEngine
from sfp_orb_engine.config import is_crypto
import pandas as pd
from datetime import datetime

engine = BegonyaEngine()
forex_symbols = [s for s in engine.symbols if not is_crypto(s)]
print(f"Testing {len(forex_symbols)} Forex & Index symbols on live data...")

found_sfp = 0
found_orb = 0

for s in forex_symbols:
    try:
        df = engine.data_provider.fetch_candles(s, interval="15m", outputsize=70)
        if df is None or len(df) < 25:
            continue
        
        sfp_res = engine.sfp_detector.detect_sfp(df, s)
        if sfp_res:
            found_sfp += 1
            entry_val = float(sfp_res.get("entry", 0.0))
            risk_val = float(sfp_res.get("risk_pips", 0.0))
            ratio = (risk_val / entry_val) if entry_val > 0 else 0
            grade = sfp_res.get("grade", "B")
            pass_risk = (entry_val > 0 and risk_val > 0 and ratio >= 0.0015)
            pass_grade = (grade.startswith("AAA") or grade.startswith("A+"))
            
            print(f"\n🎯 SFP DETECTED: {s} {sfp_res['direction']}")
            print(f"   Grade: {grade} (Pass: {pass_grade})")
            print(f"   Entry: {entry_val}, Risk: {risk_val}")
            print(f"   Ratio (risk/entry): {ratio:.6f} vs required 0.0015 (Pass: {pass_risk})")
            
            # Check candle age
            candle_dt = sfp_res.get("candle_time") or sfp_res.get("datetime")
            print(f"   Candle Time: {candle_dt}")
            
            # Check macro gate
            macro = engine.macro_client.evaluate_gate(s, sfp_res['direction'])
            print(f"   Macro Gate: allowed={macro['allowed']}, reason={macro.get('reason')}")

        orb_res = engine.orb_detector.detect_orb(df, s)
        if orb_res:
            found_orb += 1
            print(f"\n⚡ ORB DETECTED: {s} {orb_res['direction']} grade={orb_res.get('grade')}")

    except Exception as e:
        print(f"Error on {s}: {e}")

print(f"\nSummary: Found SFP: {found_sfp}, Found ORB: {found_orb}")
