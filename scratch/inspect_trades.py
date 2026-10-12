import sys
sys.path.insert(0, '.')
import scratch.test_fix
import pandas as pd
import MetaTrader5 as mt5

trades = scratch.test_fix.run_test(use_macro_gate=True, use_mtf_pd=False)

print("\n" + "="*80)
print(f"{'SYM':<7} | {'STRAT':<12} | {'DIR':<5} | {'OPENED':<16} | {'CLOSED':<16} | {'RESULT':<10} | {'ENTRY':<10} | {'SL':<10} | {'RISK':<8} | {'BARS':<4}")
print("="*80)

for t in trades:
    sym = t['symbol']
    strat = "SFP" if "SFP" in t['strategy'] else "ORB"
    d = t['direction']
    op = t['opened_at']
    cl = t['closed_at']
    res = f"{t['close_reason']} ({t['r_result']:+.1f}R)"
    entry = f"{t['entry']:.5f}"
    sl = f"{t['original_sl']:.5f}"
    risk = f"{t['risk_pips']:.5f}"
    bars = t['bars_held']
    print(f"{sym:<7} | {strat:<12} | {d:<5} | {op:<16} | {cl:<16} | {res:<16} | {entry:<10} | {sl:<10} | {risk:<8} | {bars:<4}")
