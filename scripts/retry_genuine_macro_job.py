"""One real pending macro job, isolated free research credential, stop on daily quota."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--job', type=Path, required=True)
    p.add_argument('--research-env', type=Path, default=ROOT/'config/research.env')
    args = p.parse_args()
    from research_credentials import research_environment
    environment, profile = research_environment(args.research_env, ROOT)
    os.environ.update(environment)
    os.environ['BEGONYA_RESEARCH_STOP_ON_DAILY_QUOTA'] = '1'
    sys.path.insert(0, str(ROOT/'macro_engine'))
    from calibration.research_api_diagnostics import ResearchDailyQuotaExhausted
    from calibration.build_full_macro_archive import execute_job
    job = args.job.resolve()
    summary = {'job': str(job), 'at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), **profile}
    code = 0
    try:
        summary.update(status='GENUINE_MACRO_COMPLETED', decision=execute_job(str(job), allow_api=True))
    except ResearchDailyQuotaExhausted:
        summary.update(status='BLOCKED_DAILY_FREE_QUOTA', reason='Fresh provider HTTP 429; stopped before model fallback or repeated daily-quota requests')
        code = 2
    except Exception as exc:
        # Do not print provider error text, which could contain credentials.
        summary.update(status='GENUINE_MACRO_INCOMPLETE', error_type=type(exc).__name__)
        code = 2
    target = job.parents[2]/'latest_genuine_macro_retry.json'
    target.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
