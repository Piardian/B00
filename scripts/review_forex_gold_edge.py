"""Independent, read-only review of the published Forex/Gold candidate.

Does not invoke the publisher's main(), overwrite its ledger/report, call any
market/model API, change live configuration, or implement replacement entries.
Controlled variants reuse the candidate's own run_symbol function unchanged.
"""
from pathlib import Path
import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy import stats

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'data/forex_gold_independent_review_20261023'


def metrics(frame):
    values=frame.net_r.to_numpy(float);n=len(values)
    se=values.std(ddof=1)/np.sqrt(n)
    t=values.mean()/se
    cumulative=np.r_[0,np.cumsum(frame.sort_values('closed_at').net_r.to_numpy(float))]
    return {'n':n,'wins':int((values>0).sum()),'losses':int((values<0).sum()),
            'gross_r':float(frame.gross_r.sum()),'cost_r':float(frame.cost_r.sum()),
            'net_r':float(values.sum()),'win_rate_pct':float(100*(values>0).mean()),
            'profit_factor':float(values[values>0].sum()/-values[values<0].sum()),
            'expectancy_r':float(values.mean()),'t':float(t),
            'p_two_sided_iid':float(2*stats.t.sf(abs(t),n-1)),
            'ci95_mean_iid_r':list(map(float,stats.t.interval(.95,n-1,loc=values.mean(),scale=se))),
            'closed_equity_max_drawdown_r':float((np.maximum.accumulate(cumulative)-cumulative).max()),
            'by_symbol':{s:{'n':len(g),'net_r':float(g.net_r.sum())} for s,g in frame.groupby('symbol')},
            'by_year':{str(y):{'n':len(g),'net_r':float(g.net_r.sum())} for y,g in frame.groupby(pd.to_datetime(frame.opened_at).dt.year)},
            'close_reasons':frame.close_reason.value_counts().to_dict()}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    path=ROOT/'scripts/audit_forex_gold_hardened.py'
    spec=importlib.util.spec_from_file_location('candidate_under_review',path)
    candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
    recorded=pd.read_csv(ROOT/'data/forex_gold_verified_trades.csv')
    original_loader=candidate.load_forex_data
    source_frames={s:original_loader(p) for s,p in candidate.FILES.items()}
    raw_reader=pd.read_parquet
    raw_frames={s:raw_reader(p) for s,p in candidate.FILES.items()}
    slice_cancellations=[]
    original_slice=candidate.is_slice_through_candle

    def record_slice(*args):
        answer=original_slice(*args)
        if answer:
            local=inspect.currentframe().f_back.f_locals
            p=local['p']
            slice_cancellations.append({'symbol':p['symbol'],'signal_at':p['opened_at'],
                'bar_at':str(local['c_time']),'direction':p['direction'],'entry':p['entry'],
                'original_sl':p['original_sl'],
                'same_bar_stop_touched':bool(local['c_low']<=p['current_sl'] if p['direction']=='LONG' else local['c_high']>=p['current_sl'])})
        return answer

    with patch.object(candidate,'is_slice_through_candle',record_slice):
        frames=[candidate.run_symbol(s) for s in candidate.FILES]
    reproduced=pd.concat(frames).sort_values('opened_at').reset_index(drop=True)
    sort=['symbol','opened_at']
    left=reproduced.sort_values(sort).reset_index(drop=True)
    right=recorded.sort_values(sort).reset_index(drop=True)
    columns=['symbol','opened_at','closed_at','entry','original_sl','gross_r','cost_r','net_r','close_reason']
    parity=len(left)==len(right) and all(
        left[c].astype(str).equals(right[c].astype(str)) if c in ['symbol','opened_at','closed_at','close_reason']
        else np.allclose(left[c],right[c],rtol=0,atol=1e-8) for c in columns)
    if not parity:
        raise RuntimeError('Published ledger does not reproduce from the audited source/data; investigate before deriving statistics.')
    report={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'scope':'Audit of a separate candidate simulator; not a full original-engine or historical-macro backtest.',
            'source_csv_reproduced':parity,'recorded_ledger':metrics(recorded),
            'model_assumptions':{'candidate_tp1_r':1.2,'candidate_tp2_r':2.0,'candidate_buffer_atr':.1,
                                 'execution_bars_minutes':15,'macro_gates_replayed':False,
                                 'live_entry_detector_called':False,'live_outcome_tracker_called':False},
            'frozen_fill_cost_sensitivity':{},'controlled_reruns':{},'data':{},
            'source_hashes':{}}
    for p in [Path(__file__),path,ROOT/'data/forex_gold_verified_trades.csv',ROOT/'docs/FOREX_GOLD_AUDIT_REPORT.md',
              ROOT/'sfp_orb_engine/config.py',*candidate.FILES.values()]:
        report['source_hashes'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    for p in [path,ROOT/'data/forex_gold_verified_trades.csv',ROOT/'docs/FOREX_GOLD_AUDIT_REPORT.md']:
        target=OUT/'source_snapshots'/p.name;target.parent.mkdir(exist_ok=True)
        if not target.exists():target.write_bytes(p.read_bytes())
    for factor in [1.,1.5,2.]:
        changed=recorded.copy();changed['cost_r']*=factor;changed['net_r']=changed.gross_r-changed.cost_r
        report['frozen_fill_cost_sensitivity'][str(factor)]=metrics(changed)
    lo,hi,negative,_=candidate.block_bootstrap(recorded)
    report['publisher_bootstrap_recomputed']={'percentile_total_r_95':[float(lo),float(hi)],
                                              'fraction_nonpositive':float(negative),
                                              'note':'Resamples observed five-active-date blocks; nonpositive fraction is not posterior probability that an edge is absent.'}
    same_bar=[]
    warmup_invalid=[]
    exit_spread_diff=0
    for _,t in recorded.iterrows():
        frame=source_frames[t.symbol];opened=pd.Timestamp(t.opened_at,tz='UTC');closed=pd.Timestamp(t.closed_at,tz='UTC')
        position=frame.index.get_loc(opened);fill=frame.index[position+int(t.bars_waiting)]
        if closed==fill and t.close_reason=='TP2_HIT':same_bar.append(str(t.trade_id))
        h4=frame.close.resample('4h',origin='start_day',label='left',closed='left').last().dropna()
        available=h4.index+pd.Timedelta(hours=4)
        if (available<=opened).sum()<200:warmup_invalid.append(str(t.trade_id))
        if frame.loc[fill,'spread_dist']!=frame.loc[closed,'spread_dist']:exit_spread_diff+=1
    report['execution_diagnostics']={'same_fill_bar_tp2_ids':same_bar,
        'trades_before_200_h4_observations':warmup_invalid,
        'spread_at_fill_differs_from_spread_used_at_exit':exit_spread_diff,
        'slice_cancellations':slice_cancellations}

    # Assumption checks, not parameter fitting: fix a known raw broker clock,
    # require an actual 200-observation warmup, and stress all model costs.
    from scripts.normalize_broker_history import broker_to_utc
    for variant in ['warmup_200_h4_only','broker_clock_to_utc_only','clock_and_warmup', 'all_costs_1.5x_rerun','all_costs_2.0x_rerun']:
        originals_comm=dict(candidate.COMMISSION_DIST);originals_slip=dict(candidate.SLIPPAGE_DIST)
        factor=1.5 if variant=='all_costs_1.5x_rerun' else 2. if variant=='all_costs_2.0x_rerun' else 1.
        for s in candidate.FILES:
            candidate.COMMISSION_DIST[s]=originals_comm[s]*factor
            candidate.SLIPPAGE_DIST[s]=originals_slip[s]*factor
        def adjusted_reader(p,*args,**kwargs):
            s=next(s for s,f in candidate.FILES.items() if Path(p)==f)
            df=raw_frames[s].copy()
            if variant in ['broker_clock_to_utc_only','clock_and_warmup']:
                df.index=pd.DatetimeIndex(broker_to_utc(df.index))
            return df
        def adjusted_loader(p):
            df=original_loader(p)
            if factor!=1.:df['spread_dist']*=factor
            if variant in ['warmup_200_h4_only','clock_and_warmup']:
                h4=df.close.resample('4h',origin='start_day',label='left',closed='left').last().dropna()
                ready=pd.Series(np.arange(1,len(h4)+1)>=200,index=h4.index+pd.Timedelta(hours=4))
                available=ready.reindex(df.index,method='ffill').fillna(False).to_numpy(dtype=bool)
                df.loc[~available,'htf_trend']='NEUTRAL'
            return df
        with patch.object(candidate.pd,'read_parquet',adjusted_reader),patch.object(candidate,'load_forex_data',adjusted_loader):
            outputs=[candidate.run_symbol(s) for s in candidate.FILES]
        result=pd.concat(outputs).sort_values('opened_at').reset_index(drop=True)
        report['controlled_reruns'][variant]=metrics(result)
        candidate.COMMISSION_DIST.update(originals_comm);candidate.SLIPPAGE_DIST.update(originals_slip)
        print('CONTROLLED_ASSUMPTION_CHECK',variant,len(result),round(float(result.net_r.sum()),5),flush=True)
    for s,df in raw_frames.items():
        report['data'][s]={'rows':len(df),'first':str(df.index.min()),'last':str(df.index.max()),
                           'zero_spread_fraction':float((df.spread==0).mean()),
                           'median_spread_points':float(df.spread.median())}
    # Local M1 check on same-fill-bar profits, only where all 15 minute bars
    # are present and reconcile to the M15 source. No new historical IO.
    path_checks=[]
    from zoneinfo import ZoneInfo
    ny=ZoneInfo('America/New_York')
    for symbol in candidate.FILES:
        local=ROOT/'data/full_2025_study/prices_utc'/f'{symbol}_1m.csv.gz'
        if not local.exists():continue
        m1=pd.read_csv(local);utc=pd.to_datetime(m1.datetime,utc=True)
        # Align canonical UTC ticks to the candidate's original broker labels
        # solely to reconcile its M15 geometry and order its intrabar events.
        offsets=[2+int(bool(t.to_pydatetime().astimezone(ny).dst())) for t in utc]
        m1.index=utc+pd.to_timedelta(offsets,unit='h')
        report['source_hashes'][str(local)]=hashlib.sha256(local.read_bytes()).hexdigest()
        for _,t in recorded[(recorded.symbol==symbol) & (recorded.trade_id.isin(same_bar))].iterrows():
            at=pd.Timestamp(t.closed_at,tz='UTC');bars=m1[(m1.index>=at)&(m1.index<at+pd.Timedelta(minutes=15))]
            if len(bars)!=15:continue
            parent=source_frames[symbol].loc[at]
            if max(abs(bars.high.max()-parent.high),abs(bars.low.min()-parent.low),abs(bars.open.iloc[0]-parent.open),abs(bars.close.iloc[-1]-parent.close))>1e-8:continue
            spread=parent.spread_dist
            touches=(bars.low<=t.entry-spread) if t.direction=='LONG' else (bars.high>=t.entry+spread)
            targets=(bars.high>=t.tp2) if t.direction=='LONG' else (bars.low<=t.tp2)
            if not touches.any():continue
            first_fill=int(np.flatnonzero(touches)[0]);post=targets.iloc[first_fill:]
            path_checks.append({'trade_id':t.trade_id,'symbol':symbol,'direction':t.direction,
                                'entry':float(t.entry),'tp2':float(t.tp2),'credited_net_r':float(t.net_r),
                                'fill_bar_broker_label':str(at),
                                'first_possible_fill_minute_utc':str(bars.datetime.iloc[first_fill]),
                                'tp2_minutes_before_fill_utc':bars.datetime.iloc[:first_fill][targets.iloc[:first_fill]].tolist(),
                                'tp2_occurs_only_before_first_possible_fill':bool(targets.any() and not post.any()),
                                'full_m1_coverage_and_m15_geometry_match':True})
    report['m1_same_bar_profit_checks']=path_checks
    from sfp_orb_engine.macro_gate_client import MacroGateClient
    with tempfile.TemporaryDirectory(dir=OUT) as directory:
        gate=Path(directory)/'gate.json'
        gate.write_text(json.dumps({'timestamp':'2000-01-01 00:00:00',
                                   'execution_bias_gates':{'EURUSD':'LONG_ONLY'},
                                   'recommended_risk_multiplier':.5}))
        response=MacroGateClient(gate_path=gate).evaluate_gate('EUR/USD','LONG')
    report['operational_checks']={'year_2000_gate_with_direction_approved':bool(response['allowed']),
                                  'note':'Isolated temporary file; production gate was not changed.'}
    (OUT/'review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'source_csv_reproduced':parity,'recorded_metrics':report['recorded_ledger'],
                      'same_fill_bar_tp2':len(same_bar),'warmup_invalid':len(warmup_invalid),
                      'slice_cancellations':len(slice_cancellations),'m1_path_checks':path_checks}))


if __name__=='__main__':main()
