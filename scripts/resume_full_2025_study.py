"""Resume the original-engine study using genuine model outputs; no surrogate gates."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
MONTHS=['2025-01','2025-06','2025-11']


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT/'data/full_2025_study')
    parser.add_argument('--offline-models',action='store_true');parser.add_argument('--retry-provider-now',action='store_true')
    parser.add_argument('--research-env',type=Path)
    parser.add_argument('--check-setup',action='store_true',help='Validate local configuration without API calls')
    parser.add_argument('--months',nargs='+',choices=MONTHS)
    parser.add_argument('--candidate-index',type=Path,help='Validated index for the current active universe')
    parser.add_argument('--cost-multiplier',type=float,choices=[1.,1.5,2.],default=1.)
    args=parser.parse_args();root=args.root.resolve()
    scope_path=root/'requested_scope.json'
    scope_config=json.loads(scope_path.read_text()) if scope_path.exists() else {}
    selected=scope_config.get('requested_months')
    args.months=args.months or selected or MONTHS
    if not args.months or any(month not in MONTHS for month in args.months):
        raise ValueError('Invalid requested month scope')
    child_env=None;profile={'credential_profile':'EXISTING_LIVE_KEYS'}
    if args.research_env:
        from research_credentials import research_environment
        try:child_env,profile=research_environment(args.research_env,ROOT)
        except ValueError as exc:
            print(json.dumps({'status':'BLOCKED_RESEARCH_SETUP_REQUIRED','reason':str(exc),'api_calls_made':0}));return 2
    if args.check_setup:
        print(json.dumps({'status':'LOCAL_SETUP_CHECKED',**profile,'api_calls_made':0}));return 0
    quota_path=root/('research_model_quota.json' if args.research_env else 'model_quota_all_keys.json')
    quota=json.loads(quota_path.read_text()) if quota_path.exists() else {}
    if args.research_env and str(quota.get('project_number','')) != str(profile.get('research_project_id','')):
        # Quotas belong to a project. An old research project's exhausted
        # counter must not block a newly supplied project credential.
        quota={}
    observed=dt.datetime.fromisoformat(quota['observed_at_utc']) if quota else None
    delays=[int(float(row.get('retry_delay','0s').rstrip('s'))) for row in quota.get('results',[]) if row.get('http_status')==429]
    reset=observed+dt.timedelta(seconds=max(delays)) if observed and delays else None
    status={'scope':'Original current engine on real historical data and genuine reconstructed model responses; not original archived 2025 decisions',
            'updated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'months':{},'status':'PREPARED',
            'provider_reset_at_utc':reset.isoformat() if reset else None,'entry_rules_replaced':False,
            'requested_months':args.months,'user_budget_usd':scope_config.get('user_budget_usd'),
            'automatic_continuation_authorized':scope_config.get('automatic_continuation_authorized',False),
            'background_replay_running':False,**profile}
    previous_path=root/'resume_status.json'
    if set(args.months)!=set(MONTHS) and previous_path.exists():
        previous=json.loads(previous_path.read_text())
        if (previous.get('credential_profile')==profile['credential_profile'] and
            previous.get('research_project_id')==profile.get('research_project_id')):
            status['months']={m:row for m,row in previous.get('months',{}).items() if m not in args.months}
            for month,row in status['months'].items():
                metrics=row.get('metrics')
                if metrics:
                    hashes=metrics.get('source_sha256',{})
                    source_matches=bool(hashes) and all(
                        hashlib.sha256((ROOT/'sfp_orb_engine'/f'{name}.py').read_bytes()).hexdigest()==digest
                        for name,digest in hashes.items())
                    provenance_matches=all(
                        metrics.get(field)==hashlib.sha256((root/path).read_bytes()).hexdigest()
                        for field,path in [('price_provenance_sha256','prices_utc/provenance.json'),
                                           ('calendar_provenance_sha256','calendar_primary_manifest.json')])
                    cost_matches=metrics.get('friction_assumptions',{}).get('multiplier')==args.cost_multiplier
                    if not source_matches or not provenance_matches or not cost_matches:
                        status['months'][month]={'status':'SOURCE_OR_INPUT_CHANGED_REPLAY_REQUIRED','metrics':None}
    if reset and dt.datetime.now(dt.timezone.utc)<reset and not args.offline_models and not args.retry_provider_now:
        previous_path=root/'resume_status.json'
        if previous_path.exists():
            status['months']=json.loads(previous_path.read_text()).get('months',{})
        status['status']='BLOCKED_DAILY_MODEL_QUOTA'
        status['reason']='Configured provider daily project/model quota is exhausted. No further API requests made.'
        status['monthly_return_must_not_be_inferred_from_partial_ledger']=True
        (root/'resume_status.json').write_text(json.dumps(status,indent=2));print(json.dumps(status));return 2
    stamp=dt.datetime.now().strftime('%Y%m%dT%H%M%S')
    attempts=root/'replay_attempts'/stamp;attempts.mkdir(parents=True,exist_ok=False)
    for month in dict.fromkeys(args.months):
        output=attempts/month;log=attempts/(month+'.log')
        command=[sys.executable,'-u',str(ROOT/'scripts/run_indexed_2025_replay.py'),'--root',str(root),'--month',month,'--output',str(output)]
        if args.candidate_index:command.extend(['--candidate-index',str(args.candidate_index.resolve())])
        command.extend(['--cost-multiplier',str(args.cost_multiplier)])
        if args.offline_models:command.append('--offline-models')
        status['status']='RUNNING';status['current_month']=month;status['background_replay_running']=True
        (root/'resume_status.json').write_text(json.dumps(status,indent=2))
        with log.open('w',encoding='utf-8') as handle:result=subprocess.run(command,cwd=ROOT,env=child_env,stdout=handle,stderr=subprocess.STDOUT)
        complete=output/'result.json'
        row={'output':str(output),'log':str(log),'exit_code':result.returncode,'metrics':None}
        if complete.exists():
            payload=json.loads(complete.read_text());row['status']=payload['status'];row['metrics']=payload
        else:
            row['status']='INCOMPLETE_NO_MONTHLY_RETURN'
            progress=output/'progress.json'
            if progress.exists():row['last_reported_progress']=json.loads(progress.read_text())
        status['months'][month]=row
        (root/'resume_status.json').write_text(json.dumps(status,indent=2))
        print('STUDY_MONTH',month,row['status'],flush=True)
    status.pop('current_month',None)
    status['background_replay_running']=False
    simulated=all(status['months'].get(month,{}).get('metrics') is not None and
                  status['months'][month].get('exit_code')==0 for month in args.months)
    complete=simulated and all(status['months'][month]['metrics'].get('complete_return_coverage',False) for month in args.months)
    status['status']=('RECONSTRUCTED_STUDY_COMPLETED' if complete else
                      'BLOCKED_UNRESOLVED_PRICE_COVERAGE' if simulated else
                      'BLOCKED_MISSING_GENUINE_MODEL_OUTPUTS')
    status['monthly_return_must_not_be_inferred_from_partial_ledger']=not complete
    (root/'resume_status.json').write_text(json.dumps(status,indent=2))
    return 0 if complete else 2


if __name__=='__main__':sys.exit(main())
