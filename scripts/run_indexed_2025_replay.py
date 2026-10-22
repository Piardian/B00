"""Original minute engine, original trade tracker, actually inferred macro gates."""
from pathlib import Path
import argparse
import bisect
import gzip
import hashlib
import json
import sys
import time
import logging
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.replay_live_system import replay_month,source_hashes
from scripts.historical_market_calendar import broker_market_is_open
from sfp_orb_engine.config import ACTIVE_SYMBOLS,EXCLUDED_SFP_SYMBOLS
from sfp_orb_engine.macro_gate_client import MacroGateClient
from sfp_orb_engine.execution_policy import validate_signal


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--month',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--offline-models',action='store_true');args=p.parse_args()
    for name in ['Begonya00.Engine','Begonya00.OutcomeTracker','google_genai.models','httpx']:
        logging.getLogger(name).setLevel(logging.ERROR)
    sources=source_hashes();index=set();indexed=[]
    relevant={'engine','sfp_detector','entry_mechanics','strict_setup','execution_policy','orb_detector','config','volume_anomaly'}
    # The remaining crypto symbols cannot receive a directional execution gate:
    # the current export emits BTC and SOL only. Assert this on every read below.
    for path in (args.root/'candidate_index_utc').glob('*.json'):
        body=json.loads(path.read_text());symbol=body['symbol'];clean=symbol.replace('/','')
        for name in relevant:
            if body['source_sha256'][name]!=sources[name]:raise RuntimeError('Detector source changed: '+name)
        for tf in ('15m','1h'):
            actual=hashlib.sha256((args.root/'prices_utc'/f'{clean}_{tf}.csv.gz').read_bytes()).hexdigest()
            if body.get('input_sha256',{}).get(tf)!=actual:raise RuntimeError('Indexed detector input changed: '+clean+' '+tf)
        indexed.append(symbol)
        for row in body['candidates']:
            at=pd.Timestamp(row['window_start'])
            if at.strftime('%Y-%m')==args.month:index.add((symbol,at))
    expected=[s for s in ACTIVE_SYMBOLS if s not in EXCLUDED_SFP_SYMBOLS and (s.replace('/','') in {'BTCUSD','SOLUSD'} or not __import__('sfp_orb_engine.config',fromlist=['is_crypto']).is_crypto(s))]
    missing=set(expected)-set(indexed)
    if missing:raise RuntimeError('Missing original detector index: '+','.join(sorted(missing)))
    jobs=[]
    for path in (args.root/'macro_jobs_contract'/args.month).glob('*.json.gz'):
        if '.decision.' in path.name or '.failure.' in path.name:continue
        try:body=json.loads(gzip.decompress(path.read_bytes()))
        except Exception:raise RuntimeError('Unreadable macro job: '+str(path))
        if body.get('status')=='PREPARED_NOT_A_DECISION':jobs.append((pd.Timestamp(body['as_of']),path))
    jobs.sort();times=[r[0] for r in jobs];reads=[];cache={}
    sys.path.insert(0,str(ROOT/'macro_engine'))
    from calibration.gate_dependency import guaranteed_rejection
    from calibration.build_full_macro_archive import execute_job
    prepared={}
    class ActualArchiveClient(MacroGateClient):
        def __init__(self,clock,gate_path):super().__init__(gate_path);self.clock=clock;self.execution_engine=None
        def bind_engine(self,engine):self.execution_engine=engine
        def evaluate_gate(self,symbol,direction):
            now=pd.Timestamp(self.clock.current);ix=bisect.bisect_right(times,now)-1
            if self.execution_engine is not None:
                from sfp_orb_engine.execution_policy import risk_rejection
                tracker=self.execution_engine.outcome_tracker
                reason=risk_rejection(tracker.closed_trades,tracker.active_trades,symbol,1.0,self.clock.current)
                if reason in {'DAILY_LOSS_LIMIT','CONSECUTIVE_STOP_LIMIT','UNRESOLVED_TRACKING_GAP'}:
                    reads.append({'at':now.isoformat(),'symbol':symbol,'type':'PROVEN_EXISTING_RISK_VETO','reason':reason})
                    return {'allowed':False,'decision':'PROVEN_EXISTING_RISK_VETO','reason':reason,'risk_multiplier':0.0}
            if ix<0:raise RuntimeError('No historical production gate seed')
            at,job=jobs[ix];decision=job.with_name(job.name.replace('.json.gz','.decision.json.gz'))
            if job not in prepared:prepared[job]=json.loads(gzip.decompress(job.read_bytes()))
            proof=guaranteed_rejection(prepared[job]['state']['processed_metrics'],symbol,direction)
            if proof is not None:
                reads.append({'at':now.isoformat(),'source_as_of':at.isoformat(),'type':'PROVEN_LLM_INDEPENDENT_REJECTION','proof':proof})
                return {'allowed':False,'decision':'PROVEN_EXISTING_GATE_VETO','reason':proof['basis'],
                        'gate_bias':proof.get('deterministic_bias',proof.get('parent_gate')),'risk_multiplier':0.0}
            if decision not in cache:
                if not decision.exists():
                    print('NEED_REAL_MACRO_FOR_ENTRY',symbol,now.isoformat(),'snapshot',at.isoformat(),flush=True)
                    attempts=1 if args.offline_models else 3
                    for attempt in range(attempts):
                        try:execute_job(str(job),allow_api=not args.offline_models);break
                        except Exception:
                            if attempt==attempts-1:raise
                            print('WAITING_FOR_CONFIGURED_MODEL_RECOVERY',at.isoformat(),flush=True)
                            for _ in range(6):time.sleep(30)
                result=json.loads(gzip.decompress(decision.read_bytes()))
                if result.get('status')!='REAL_PRODUCTION_GRAPH_COMPLETED':raise RuntimeError('Invalid macro inference state')
                if result['input_sha256']!=hashlib.sha256(job.read_bytes()).hexdigest():raise RuntimeError('Macro decision input changed')
                cache[decision]=result
            result=cache[decision];gate=result['gate'];biases=gate['execution_bias_gates']
            for s in ACTIVE_SYMBOLS:
                clean=s.replace('/','')
                from sfp_orb_engine.config import is_crypto
                if is_crypto(s) and clean not in {'BTCUSD','SOLUSD'} and self._normalize_symbol(s) in biases:
                    raise RuntimeError('A symbol assumed permanently macro-neutral can receive a gate: '+s)
            if symbol=='SOL/USD' and not gate.get('crypto_rotation'):
                parent=biases.get('BTC','NEUTRAL_RANGE')
                # Original rotation cannot manufacture a SHORT gate from a
                # neutral/long/defensive parent. No historical funding proxy.
                if direction=='SHORT' and parent!='SHORT_ONLY':
                    reads.append({'at':now.isoformat(),'symbol':symbol,'source_as_of':at.isoformat(),'rotation_proof':'Original rotation target direction cannot approve this short from parent '+parent})
                    return {'allowed':False,'decision':'VETO_DIRECTION_OR_NEUTRAL','reason':'Original BTC parent gate precludes SOL short regardless of missing intraday funding','gate_bias':'NEUTRAL_RANGE','risk_multiplier':0.0}
                raise RuntimeError('Exact live rotation inputs needed; settled funding is not premiumIndex.lastFundingRate')
            self.gate_path.write_text(json.dumps(gate))
            reads.append({'at':now.isoformat(),'symbol':symbol,'source_as_of':at.isoformat(),'decision_sha256':hashlib.sha256(decision.read_bytes()).hexdigest()})
            return super().evaluate_gate(symbol,direction)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    from scripts.historical_news_events import build_news_input
    historical_news=build_news_input(args.root,ROOT/'config/news_events.json')
    result=replay_month(args.month,ACTIVE_SYMBOLS,args.root/'prices_utc',[],args.output,
                        macro_client_factory=ActualArchiveClient,candidate_index=index,market_calendar=broker_market_is_open,news_file=historical_news,frame_symbols=set(indexed),minimize_memory=True)
    result['scope']='Full current entry and lifecycle engine on real historical quote data and recomputed production macro outputs; not an original 2025 archive or broker order execution'
    result['macro_inference_assumption']='Only snapshots actually consumed by possible entries are inferred; unused outputs omitted with no regime-state carry. Current model/service routing, not historical outages.'
    result['source_sha256']=sources;result['indexed_symbols']=indexed
    result['price_provenance_sha256']=hashlib.sha256((args.root/'prices_utc/provenance.json').read_bytes()).hexdigest()
    result['calendar_provenance_sha256']=hashlib.sha256((args.root/'calendar_primary_manifest.json').read_bytes()).hexdigest()
    result['unpriced_active_tails']=[]
    active=json.loads((args.output/'state/active.json').read_text()) if (args.output/'state/active.json').exists() else []
    end=pd.Timestamp(args.month+'-01',tz='UTC')+pd.offsets.MonthBegin(1)
    for trade in active:
        last=pd.Timestamp(trade.get('last_processed_bar',trade['opened_at']))
        expected=last+pd.Timedelta(minutes=1)
        while expected<end and not broker_market_is_open(trade['symbol'],expected):expected+=pd.Timedelta(minutes=1)
        if expected<end-pd.Timedelta(minutes=1):
            result['unpriced_active_tails'].append({'id':trade['id'],'symbol':trade['symbol'],'next_required_minute':expected.isoformat()})
    result['complete_return_coverage']=not result['unresolved_gaps'] and not result['unpriced_active_tails']
    (args.output/'macro_reads.json').write_text(json.dumps(reads,indent=2))
    (args.output/'result.json').write_text(json.dumps(result,indent=2))
    print('ORIGINAL_ENGINE_REPLAY_FINISHED',json.dumps(result),flush=True)


if __name__=='__main__':main()
