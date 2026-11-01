"""Supplementary integrity checks; never changes a strategy or observation."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import study as s

def canonical(x):return json.dumps(x,sort_keys=True,default=str,allow_nan=False)

def snapshot(m,h,at):
    hist=m.loc[m.datetime+pd.Timedelta(minutes=15)<=at].tail(300).reset_index(drop=True)
    hourly=h.loc[h.datetime+pd.Timedelta(hours=1)<=at].tail(1000).reset_index(drop=True)
    return hist,hourly

def main():
    plan=s.verify();c,d,e=s.engine();cases=s.read(s.HERE/'signals.json')
    quotes=s.read(s.HERE/'quote_markouts.json');coverage=s.read(s.HERE/'coverage.json')
    detector=d.SFPDetector();causal=0;reproduced=0;inputs={}
    for symbol in s.SYMBOLS:
        m,h,audit=s.load_prices(symbol)
        assert m.datetime.is_monotonic_increasing and not m.datetime.duplicated().any()
        assert h.datetime.is_monotonic_increasing and not h.datetime.duplicated().any()
        assert m.datetime.min().year>=2024 and m.datetime.max().year<=2026
        assert audit['m15_conflicting_fields']==0
        if symbol=='XAUUSD':assert audit['h1_ohlc_mismatches']==0
        inputs[symbol]=audit
        selected=[row for row in cases if row['symbol']==symbol]
        # Include empty signal windows as well as every measured candidate.
        controls=[pd.Timestamp(f'2025-{month:02}-15 10:00',tz='UTC') for month in range(1,12)]
        for at in [pd.Timestamp(row['available_at']) for row in selected]+controls:
            hist,hourly=snapshot(m,h,at)
            if hist.empty:continue
            trend=e.higher_timeframe_trend(hourly,at)
            observed=detector.detect_sfp(hist,symbol[:3]+'/'+symbol[3:],htf_trend=trend)
            mc=m.copy();hc=h.copy()
            mc.loc[mc.datetime+pd.Timedelta(minutes=15)>at,['open','high','low','close']]*=17
            hc.loc[hc.datetime+pd.Timedelta(hours=1)>at,['open','high','low','close']]*=.13
            mutated,mutated_h=snapshot(mc,hc,at)
            mutated_trend=e.higher_timeframe_trend(mutated_h,at)
            assert trend==mutated_trend
            assert canonical(observed)==canonical(detector.detect_sfp(mutated,symbol[:3]+'/'+symbol[3:],htf_trend=mutated_trend))
            causal+=1
        for row in selected:
            at=pd.Timestamp(row['available_at']);hist,hourly=snapshot(m,h,at)
            signal=detector.detect_sfp(hist,symbol[:3]+'/'+symbol[3:],htf_trend=e.higher_timeframe_trend(hourly,at))
            assert canonical(signal)==canonical(row['signal'])
            assert canonical(s.direction(signal,at,m))==canonical(row['direction'])
            assert pd.Timestamp(signal['datetime'])+pd.Timedelta(minutes=15)==at
            reproduced+=1
    assert sum(r['validated'] for r in coverage)==len(cases)
    assert len({r['case_id'] for r in cases})==len(cases)
    assert len(quotes)==len(cases)*3
    assert len(coverage)==33
    assert set(r['month'] for r in coverage)==set(s.MONTHS)
    for r in quotes:
        if r['status']=='FILLED_MARKOUT':
            assert np.isclose(r['net_markout_r'],r['price_markout_r']-r['commission_r']-r['slip_r'])
            assert pd.Timestamp(r['marked_at'])>=pd.Timestamp(r['filled_at'])+pd.Timedelta(hours=1)
        else:assert r['net_markout_r'] is None
    used=s.read(s.HERE/'used_tape_hashes.json')
    for path,digest in used.items():
        assert s.sha(path)==digest
        f=pd.read_parquet(path)
        assert f.time.is_monotonic_increasing
        assert ((f.bid>0)&(f.ask>=f.bid)).all()
    # Return values are observations, never a fabricated completed trade ledger.
    s.write(s.HERE/'integrity.json',dict(passed=True,all_signals_reproduced=reproduced,
        prefix_future_mutation_checks=causal,quote_ledger_records=len(quotes),
        used_quote_tapes_verified=len(used),coverage_asset_months=len(coverage),
        original_source_hashes_match=True,live_approved=False))
    print(s.read(s.HERE/'integrity.json'))

if __name__=='__main__':main()
