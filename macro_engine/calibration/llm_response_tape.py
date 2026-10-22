"""Replay genuine, recorded structured responses only for identical model requests."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from unittest.mock import patch


class ResponseTape:
    def __init__(self,root):
        self.directory=root/'llm_response_tape';self.directory.mkdir(exist_ok=True)
        macro=Path(__file__).resolve().parents[1]
        self.router_sha=hashlib.sha256((macro/'core/key_manager.py').read_bytes()).hexdigest()
        self.records=[]
    def key(self,kwargs):
        from config import ANALYST_CASCADE,STRATEGIST_CASCADE
        request={**kwargs,'schema':kwargs['schema'].model_json_schema(),'router_sha256':self.router_sha,
                 'analyst_cascade':ANALYST_CASCADE,'strategist_cascade':STRATEGIST_CASCADE}
        return hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),request
    def store(self,kwargs,response,provenance):
        key,request=self.key(kwargs);path=self.directory/(key+'.json.gz')
        if not path.exists():
            payload={'request':request,'response':response,'provenance':provenance,'saved_wall_epoch':time.time(),
                     'request_sha256':key,'source':'GENUINE_PRODUCTION_STRUCTURED_RESPONSE_NO_FABRICATION'}
            with tempfile.NamedTemporaryFile(dir=self.directory,suffix='.partial',delete=False) as handle:
                handle.write(gzip.compress(json.dumps(payload,ensure_ascii=False).encode()));name=handle.name
            os.replace(name,path)
        return key
    def wrapper(self,original,source_as_of,allow_api=True):
        def execute(**kwargs):
            key,request=self.key(kwargs);path=self.directory/(key+'.json.gz')
            if path.exists():
                stored=json.loads(gzip.decompress(path.read_bytes()))
                if stored['request']!=request:raise RuntimeError('Recorded model request mismatch')
                result=kwargs['schema'].model_validate(stored['response'])
                self.records.append({'request_sha256':key,'role':kwargs['role'],'mode':'EXACT_REQUEST_RECORDED_RESPONSE','provenance':stored['provenance']})
                return result
            if not allow_api:
                raise RuntimeError('MISSING_GENUINE_RECORDED_MODEL_RESPONSE role='+kwargs['role']+' request_sha256='+key)
            result=original(**kwargs)
            self.store(kwargs,result.model_dump(),{'as_of':source_as_of,'type':'REAL_API_RESPONSE'})
            self.records.append({'request_sha256':key,'role':kwargs['role'],'mode':'REAL_API_RESPONSE'})
            return result
        return execute


def seed_recorded_responses(root):
    from agents.specialists import MacroSpecialists
    from agents.schemas import LiquidityOutput,GrowthOutput
    tape=ResponseTape(root);specialists=MacroSpecialists();count=0
    for path in root.glob('macro_jobs*/**/*.decision.json.gz'):
        try:body=json.loads(gzip.decompress(path.read_bytes()))
        except (ValueError,OSError):continue
        if body.get('status')!='REAL_PRODUCTION_GRAPH_COMPLETED':continue
        result=body.get('result',{});metrics=result.get('processed_metrics')
        if not metrics:continue
        outputs={'LiquidityOutput':result['liquidity_output'],'GrowthOutput':result['growth_output'],'MacroStrategistOutput':result['final_output']}
        def record(**kwargs):
            value=outputs[kwargs['schema'].__name__]
            tape.store(kwargs,value,{'source_file':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'type':'GENUINE_SAVED_PRODUCTION_GRAPH_OUTPUT'})
            return kwargs['schema'].model_validate(value)
        with patch.object(specialists.router,'execute_structured',record):
            liq=specialists.analyze_liquidity(metrics)
            growth=specialists.analyze_growth_and_commodities(metrics)
            specialists.synthesize_macro_regime(liq,growth,metrics)
        count+=1
    print('RECORDED_RESPONSE_TAPE_SEEDED',count,'real completed graphs',flush=True)
