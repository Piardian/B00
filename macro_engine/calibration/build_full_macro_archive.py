"""Replay the ORIGINAL scheduler; execute its production graph jobs in isolation.

The planning pass records inputs, not decisions. Only successful real graph
invocations become gates. No placeholder model response or sizing is permitted.
"""
import argparse
from contextlib import ExitStack,contextmanager
from concurrent.futures import ProcessPoolExecutor, as_completed
import datetime as dt
import gzip
import hashlib
import json
import logging
from pathlib import Path
import sys
import bisect
from types import SimpleNamespace
from unittest.mock import patch

MACRO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(MACRO))
sys.path.append(str(MACRO.parent))
from calibration.full_system_reconstruction import StrictVintageFred, HistoricalMarket, calendar_for, STUDY, UTC
from config import MARKET_SYMBOLS
from data_quality import DataUnavailableError, REQUIRED_MARKET_FIELDS


@contextmanager
def frozen_live_clock(as_of):
    original_datetime,original_date=dt.datetime,dt.date
    local=as_of.astimezone(dt.timezone(dt.timedelta(hours=3)))
    class FrozenDate(original_date):
        @classmethod
        def today(cls):return local.date()
    class FrozenDateTime(original_datetime):
        @classmethod
        def now(cls,tz=None):return as_of.astimezone(tz) if tz else local.replace(tzinfo=None)
        @classmethod
        def utcnow(cls):return as_of.replace(tzinfo=None)
    with patch.object(dt,'date',FrozenDate),patch.object(dt,'datetime',FrozenDateTime):yield


def save(path,body):
    temporary=path.with_name(path.name+'.partial')
    temporary.write_bytes(gzip.compress(json.dumps(body,default=str).encode()));temporary.replace(path)


class HistoricalPolicy:
    def __init__(self,root):self.root=root;self.originals={}
    def get(self,label,original,as_of):
        path=self.root/'official_rates'/f'{label}_policy_{as_of.date()}.json'
        path.parent.mkdir(exist_ok=True)
        if path.exists():return json.loads(path.read_text())
        result=original(as_of);path.write_text(json.dumps(result));return result


def plan(month,root):
    from daemon import macro_scheduler as scheduler
    from graph import macro_graph
    from ingestion.bank_of_england import BankOfEnglandDataIngestion
    from ingestion.bank_of_canada import BankOfCanadaDataIngestion
    directory=root/'macro_jobs_contract'/month;directory.mkdir(parents=True,exist_ok=True)
    start=dt.datetime.fromisoformat(month+'-01T00:00:00+00:00')
    import pandas as pd
    end=(pd.Timestamp(start)+pd.offsets.MonthBegin(1)).to_pydatetime()
    current=[start-dt.timedelta(days=7)]
    policy=HistoricalPolicy(root)
    uk_original=BankOfEnglandDataIngestion().fetch_bank_rate
    ca_original=BankOfCanadaDataIngestion().fetch_policy_rate
    fred=StrictVintageFred(root);market=HistoricalMarket(fred,root)
    ingestion=macro_graph.MacroWorkflowEngine.__new__(macro_graph.MacroWorkflowEngine)
    from preprocessing.metrics import MacroMetricsCalculator
    ingestion.preprocessor=MacroMetricsCalculator();ingestion.fred_ingest=fred
    daily_failures={};prepared={};attempts=[]
    class HistoricalDateTime(dt.datetime):
        @classmethod
        def now(cls,tz=None):
            return current[0].astimezone(tz) if tz else (current[0]+dt.timedelta(hours=3)).replace(tzinfo=None)
    def advance(seconds):
        current[0]+=dt.timedelta(seconds=seconds)
        if current[0]>=end:raise KeyboardInterrupt
    class PlanningEngine:
        def run_pipeline(self):
            as_of=current[0]
            job=directory/(as_of.strftime('%Y%m%dT%H%M%S')+'.json.gz')
            if job.exists():
                body=json.loads(gzip.decompress(job.read_bytes()))
                if body['status']=='PREPROCESSING_FAILED':raise DataUnavailableError(body['error'])
                return {}
            date=as_of.date()
            if date in daily_failures:
                attempts.append({'as_of':as_of.isoformat(),'status':'SAME_DATE_INPUT_REJECTED','error':daily_failures[date]})
                raise DataUnavailableError(daily_failures[date])
            raw={}
            try:
                # Freshness failures depend only on date/vintage. Do not waste
                # market requests or LLM calls on inputs already rejected today.
                old=root/'macro_jobs_live'/month/job.name
                if not old.exists():old=root/'macro_jobs_publication'/month/job.name
                old_state={}
                if old.exists():
                    try:old_state=json.loads(gzip.decompress(old.read_bytes())).get('state',{})
                    except (ValueError,OSError):pass
                if old_state:
                    raw=old_state['raw_market'];f=old_state['raw_fred']
                else:
                    f=fred.fetch_liquidity_metrics(as_of.date())
                    for name in MARKET_SYMBOLS:
                        try:item=market.fetch_symbol_snapshot(name,as_of)
                        except Exception as exc:
                            if name in REQUIRED_MARKET_FIELDS:raise
                            item=None
                        if item is not None:raw[name]=item
                missing=REQUIRED_MARKET_FIELDS-set(raw)
                if missing:raise DataUnavailableError('Historical market input missing: '+','.join(sorted(missing)))
                ingestion.market_ingest=SimpleNamespace(fetch_current_prices=lambda:raw)
                ingestion._as_of_date=None;ingestion._as_of_datetime=None
                events=calendar_for(as_of)
                ingestion.fred_ingest=SimpleNamespace(fetch_liquidity_metrics=lambda as_of=None:f)
                with frozen_live_clock(as_of):
                    state=ingestion._node_ingestion_and_preprocessing({'calendar_events':events,'calendar_events_supplied':True,'previous_regime_state':{}})
                body={'status':'PREPARED_NOT_A_DECISION','as_of':as_of.isoformat(),'state':state}
                save(job,body)
                print('PREPARED',month,as_of.isoformat(),flush=True)
                return {}
            except Exception as exc:
                body={'status':'PREPROCESSING_FAILED','as_of':as_of.isoformat(),'error':str(exc)}
                # A date-only rejection is safe to cache only for freshness;
                # network errors may recover on later scheduler attempts.
                if isinstance(exc,DataUnavailableError) and ('Stale ' in str(exc) or 'isoformat' in str(exc)):
                    daily_failures[date]=str(exc)
                save(job,body)
                print('INPUT_REJECTED',month,as_of.isoformat(),type(exc).__name__,str(exc),flush=True)
                raise
    state={}
    def load_state():return dict(state)
    def save_state(value):state.clear();state.update(value)
    runner=scheduler.MacroEventScheduler.__new__(scheduler.MacroEventScheduler)
    runner.engine=PlanningEngine();runner.post_news_delay=180
    runner.state_file=directory/'scheduler_state.json';runner.cached_events=[];runner.last_calendar_fetch=0.
    runner._load_state=load_state;runner._save_state=save_state
    calendar_cache={}
    def cached_calendar(ttl_seconds=300):
        key=int(current[0].timestamp())//ttl_seconds
        if key not in calendar_cache:
            calendar_cache.clear();calendar_cache[key]=calendar_for(current[0])
        return calendar_cache[key]
    runner._get_calendar_events_cached=cached_calendar
    runner._acquire_file_lock=lambda *a,**k:True
    runner._release_file_lock=lambda *a:None
    fake_datetime=SimpleNamespace(datetime=HistoricalDateTime,timedelta=dt.timedelta)
    fake_time=SimpleNamespace(time=lambda:current[0].timestamp(),sleep=advance)
    logging.getLogger('MacroDaemon').setLevel(logging.CRITICAL)
    with ExitStack() as stack:
        stack.enter_context(patch.object(scheduler,'datetime',fake_datetime))
        stack.enter_context(patch.object(scheduler,'time',fake_time))
        stack.enter_context(patch.object(scheduler,'ENABLE_MACRO_TELEGRAM_NOTIFICATIONS',False))
        stack.enter_context(patch.object(BankOfEnglandDataIngestion,'fetch_bank_rate',lambda obj,as_of:policy.get('UK',uk_original,as_of or current[0])))
        stack.enter_context(patch.object(BankOfCanadaDataIngestion,'fetch_policy_rate',lambda obj,as_of:policy.get('CA',ca_original,as_of or current[0])))
        runner.start_daemon_loop(poll_interval_seconds=30)
    (directory/'rejected_repeated_attempts.json').write_text(json.dumps(attempts,indent=2))
    print('PLANNING_FINISHED',month,flush=True)


def execute_job(path_string,allow_api=True):
    from graph import macro_graph
    from ingestion.bank_of_england import BankOfEnglandDataIngestion
    from ingestion.bank_of_canada import BankOfCanadaDataIngestion
    path=Path(path_string);body=json.loads(gzip.decompress(path.read_bytes()))
    output=path.with_name(path.name.replace('.json.gz','.decision.json.gz'))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if output.exists():
        previous=json.loads(gzip.decompress(output.read_bytes()))
        if previous.get('input_sha256')==digest:return str(output)
    as_of=dt.datetime.fromisoformat(body['as_of']);state=body['state']
    graph=macro_graph.MacroWorkflowEngine()
    graph.market_ingest=SimpleNamespace(fetch_current_prices=lambda:state['raw_market'])
    graph.fred_ingest=SimpleNamespace(fetch_liquidity_metrics=lambda as_of:state['raw_fred'])
    captured=[]
    from calibration.llm_response_tape import ResponseTape
    tape=ResponseTape(path.parents[2])
    quality=state['raw_fred']['data_quality']
    try:
        with ExitStack() as stack:
            if __import__('os').environ.get('BEGONYA_RESEARCH_DIAGNOSTICS')=='1':
                from calibration.research_api_diagnostics import record_provider_outcomes
                stack.enter_context(record_provider_outcomes(path.parents[2],graph.specialists.router))
            stack.enter_context(patch.object(graph.specialists.router,'execute_structured',tape.wrapper(graph.specialists.router.execute_structured,as_of.isoformat(),allow_api=allow_api)))
            stack.enter_context(patch.object(macro_graph,'save_macro_gate_atomic',lambda payload,path:captured.append(payload)))
            stack.enter_context(patch.object(BankOfEnglandDataIngestion,'fetch_bank_rate',lambda obj,as_of:quality['uk_bank_rate']))
            stack.enter_context(patch.object(BankOfCanadaDataIngestion,'fetch_policy_rate',lambda obj,as_of:quality['ca_policy_rate']))
            stack.enter_context(frozen_live_clock(as_of))
            result=graph.run_pipeline(initial_events=state['calendar_events'])
        if not captured:raise RuntimeError('No actual production graph gate export')
        save(output,{'status':'REAL_PRODUCTION_GRAPH_COMPLETED','input_sha256':digest,'as_of':as_of.isoformat(),
                     'gate':captured[0],'result':result,'llm_requests':tape.records,'provenance':'RECOMPUTED_PRODUCTION_GRAPH_REAL_HISTORICAL_INPUTS_NOT_ORIGINAL_2025_ARCHIVE'})
        print('REAL_MACRO_COMPLETED',as_of.isoformat(),flush=True)
        return str(output)
    except Exception as exc:
        save(output.with_name(output.name.replace('.decision.','.failure.')),{'status':'GRAPH_FAILED','error':str(exc),'input_sha256':digest})
        raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=STUDY)
    p.add_argument('--months',nargs='+',default=['2025-01','2025-06','2025-11'])
    p.add_argument('--execute',action='store_true');p.add_argument('--workers',type=int,default=2)
    p.add_argument('--candidate-index',type=Path)
    p.add_argument('--execute-only',action='store_true')
    p.add_argument('--select-only',action='store_true')
    args=p.parse_args()
    if not args.execute_only:
        for month in args.months:plan(month,args.root)
    if args.execute:
        jobs=[]
        for month in args.months:
            for path in sorted((args.root/'macro_jobs_contract'/month).glob('*.json.gz')):
                if '.decision.' in path.name or '.failure.' in path.name:continue
                if json.loads(gzip.decompress(path.read_bytes()))['status']=='PREPARED_NOT_A_DECISION':jobs.append(str(path))
        if args.candidate_index:
            sys.path.insert(0,str(MACRO.parent))
            from sfp_orb_engine.execution_policy import validate_signal
            import pandas as pd
            ordered=sorted((dt.datetime.fromisoformat(json.loads(gzip.decompress(Path(p).read_bytes()))['as_of']),p) for p in jobs)
            times=[x[0] for x in ordered];needed=set()
            from calibration.gate_dependency import guaranteed_rejection
            proof_rows=[];prepared_cache={}
            for path in args.candidate_index.glob('*.json'):
                data=json.loads(path.read_text())
                for row in data['candidates']:
                    signal=row['signal']
                    if validate_signal(signal) is not None:continue
                    if float(signal.get('risk_pips',0))/float(signal.get('entry',1))<.00002:continue
                    left=pd.Timestamp(row['window_start'])
                    if left.strftime('%Y-%m') not in args.months:continue
                    for now in pd.date_range(left,left+pd.Timedelta(minutes=15),freq='min',inclusive='left'):
                        index=bisect.bisect_right(times,now.to_pydatetime())-1
                        if index>=0:
                            job=ordered[index][1]
                            if job not in prepared_cache:prepared_cache[job]=json.loads(gzip.decompress(Path(job).read_bytes()))
                            proof=guaranteed_rejection(prepared_cache[job]['state']['processed_metrics'],data['symbol'],signal['direction'])
                            if proof is not None:
                                proof_rows.append({'at':now.isoformat(),'macro_as_of':ordered[index][0].isoformat(),**proof})
                            else:needed.add(job)
            (args.root/'consumed_macro_jobs.json').write_text(json.dumps({'method':'Original graph evaluated at every prepared scheduler snapshot potentially consumed by a policy-valid detector candidate; unused outputs omitted, no previous_regime_state carry',
                'service_assumption':'Successful model inference at omitted unused scheduler cycles; not an operational outage replay',
                'jobs':sorted(needed),'prepared_total':len(jobs),'llm_independent_rejections':proof_rows},indent=2))
            jobs=sorted(needed)
            print('ACTUALLY_CONSUMABLE_MACRO_JOBS',len(jobs),flush=True)
        if args.select_only:return
        failures=[]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures={pool.submit(execute_job,path):path for path in jobs}
            for future in as_completed(futures):
                try:future.result()
                except Exception as exc:failures.append({'path':futures[future],'error':str(exc)})
        (args.root/'macro_graph_failures.json').write_text(json.dumps(failures,indent=2))
        if failures:raise RuntimeError('Macro graph failures must be reconciled with scheduler before a full replay')


if __name__=='__main__':main()
