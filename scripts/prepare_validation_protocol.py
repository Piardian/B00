"""Freeze current strategy and audit available costs/data without fabricating returns."""
import datetime as dt
import argparse
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.replay_live_system import source_hashes
from sfp_orb_engine.config import ACTIVE_SYMBOLS, EXECUTION_POLICY_VERSION
from sfp_orb_engine.outcome_tracker import get_friction_config

STUDY = ROOT/'data/full_2025_study'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=STUDY/'validation_protocol_20261023')
    out = parser.parse_args().output.resolve()
    out.mkdir(exist_ok=True)
    target = out/'protocol.json'
    if target.exists():
        raise RuntimeError('Protocol already frozen; never overwrite a forward evaluation start')
    sources = {f'sfp_orb_engine/{name}.py': digest for name, digest in source_hashes().items()}
    for directory in ['agents','core','graph','ingestion','gateways']:
        for path in (ROOT/'macro_engine'/directory).rglob('*.py'):
            sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ['macro_engine/config.py', 'macro_engine/core/key_manager.py',
                 'macro_engine/agents/specialists.py', 'macro_engine/graph/macro_graph.py',
                 'scripts/replay_live_system.py', 'scripts/run_indexed_2025_replay.py']:
        sources[name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    snapshots = out/'sources'
    snapshots.mkdir(exist_ok=True)
    for name in sources:
        (snapshots/name.replace('/', '__')).write_bytes((ROOT/name).read_bytes())
    report = dict(frozen_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                  policy=EXECUTION_POLICY_VERSION, symbols=ACTIVE_SYMBOLS,
                  source_sha256=sources, parameter_optimization_permitted=False,
                  periods={'2025-01': 'CURRENT_ENGINE_REFERENCE_INCOMPLETE',
                           '2025-11': 'RETROSPECTIVE_VALIDATION_NOT_UNSEEN',
                           '2026-11': 'FUTURE_FORWARD_OUT_OF_SAMPLE_NOT_YET_AVAILABLE'},
                  selection_contamination='Legacy candidate used Dec 2024-Oct 2026 including all 2025. A later 2025 month cannot be called untouched OOS.',
                  true_oos_start_utc='2026-11-01T00:00:00+00:00',
                  true_oos_end_utc_exclusive='2026-12-01T00:00:00+00:00',
                  future_window_reason='First full UTC month after the strategy/source freeze; selected before any future return is observed.',
                  required_source_match=True, required_policy_match=True,
                  initial_unknown_macro_policy='BLOCK_FULL_RETURN_REPORT',
                  required_cost_scenarios=[1.0, 1.5, 2.0],
                  real_cost_validation_complete=False, live_money_ready=False,
                  automatic_continuation_authorized=False, paid_use_authorized=False,
                  data={}, costs={})
    for symbol in ACTIVE_SYMBOLS:
        clean = symbol.replace('/', '')
        report['costs'][symbol] = {
            'paper_assumptions': get_friction_config(symbol),
            'historical_bid_ask_available_in_canonical_m1': False,
            'actual_historical_commission_swap_and_slippage_verified': False,
            'multiplying_fixed_paper_fee_is_not_real_broker_cost_validation': True,
        }
        report['data'][symbol] = {}
        for tf in ['1m', '15m', '1h']:
            path = STUDY/'prices_utc'/f'{clean}_{tf}.csv.gz'
            frame = pd.read_csv(path)
            times = pd.to_datetime(frame.datetime, utc=True)
            report['data'][symbol][tf] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'duplicates': int(times.duplicated().sum()),
                'missing_ohlc_cells': int(frame[['open','high','low','close']].isna().sum().sum()),
                'periods': {},
            }
            for month in ['2025-01', '2025-11']:
                start = pd.Timestamp(month+'-01', tz='UTC')
                selected = times[(times >= start) & (times < start+pd.offsets.MonthBegin(1))]
                report['data'][symbol][tf]['periods'][month] = dict(
                    rows=len(selected), first=str(selected.min()), last=str(selected.max()),
                    full_market_minute_coverage_certified=False)
    report['cost_reference'] = {
        'url':'https://the5ers.com/faqs/what-are-the-spreads-and-commissions/',
        'accessed_date':'2026-10-23', 'published_last_updated':'2026-07-22',
        'current_forex_round_trip_usd_per_lot':4,
        'current_metals_commission_method':'PERCENTAGE_OF_NOTIONAL',
        'not_a_verified_2025_account_tariff':True,
        'legacy_assumptions':'6 USD/FX lot; 0.06 XAUUSD price distance, unverified',
    }
    report['evidence_requirements'] = [
        'Complete input coverage and genuine macro decisions; no partial month as full return',
        'Actual engine entry and lifecycle; no surrogate entry strategy',
        'Bid/ask, historical contract/account costs and swaps reconciled or explicitly unresolved',
        'No parameter or asset changes during the frozen forward window',
        'Report uncertainty with blocks accounting for USD clustering; no IID-only edge claim',
        'Positive lower 95% blocked expectancy bound under baseline and 1.5x verified-cost model before strong statistical edge claim',
        'A month or small trade count alone cannot establish a durable edge',
    ]
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'status':'STRATEGY_FROZEN_INPUT_COST_AUDIT_COMPLETED',
                      'protocol':str(target), 'real_cost_validation_complete':False,
                      'true_oos_month':'2026-11'}))


if __name__ == '__main__':
    main()
