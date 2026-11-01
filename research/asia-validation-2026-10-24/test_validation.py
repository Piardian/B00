import json,os
import pandas as pd
import pytest
from study import HERE,ROOT,classify_ratio,stats
from price_rules import normalize_targets
from normalize_clock import broker_to_utc


@pytest.mark.parametrize('value,expected',[(0.,'TIGHT'),(.35,'TIGHT'),(.35000001,'LOOSE'),(.70,'LOOSE')])
def test_frozen_threshold(value,expected):assert classify_ratio(value)==expected


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-.01,.71])
def test_invalid_ratio_not_profitable_group(value):
    with pytest.raises(ValueError):classify_ratio(value)


def test_broker_offset_follows_us_not_uk_dst():
    r=broker_to_utc(pd.Series(['2025-02-03 10:00Z','2025-03-17 11:00Z','2025-03-31 10:00Z']))
    assert list(r.dt.hour)==[8,8,7]


def test_unresolved_cannot_publish_total_profit():
    r=stats([dict(status='UNRESOLVED',filled_at='2025-02-03 09:00Z',net_r=None,day='2025-02-03',month='2025-02',reason='GAP')])
    assert r['net_r'] is None and r['mean_r_per_setup'] is None and r['unresolved']==1


def test_discovery_33_signals_reproduce_with_frozen_detector():
    os.environ['ENTRY_MODEL']='MIDPOINT';os.environ['LIMIT_EXPIRY_BARS']='16'
    from frozen_engine.orb_detector import ORBDetector
    detector=ORBDetector();frames={}
    cases=json.loads((ROOT/'research/structure-room-2026-10-23/setups_frozen.json').read_text(encoding='utf-8'))
    assert len(cases)==33
    for c in cases:
        old=c['signal'];symbol=old['symbol'].replace('/','');at=pd.Timestamp(c['available_at'])
        for tf in ['15m','1h']:
            if (symbol,tf) not in frames:frames[symbol,tf]=pd.read_csv(ROOT/f'data/full_2025_study/prices_utc/{symbol}_{tf}.csv.gz',parse_dates=['datetime'])
        f=frames[symbol,'15m'];h=frames[symbol,'1h']
        k=int(f.datetime.searchsorted(at,side='left'));hk=int(h.datetime.searchsorted(at,side='left'))
        sig=detector.detect_orb(f.iloc[max(0,k-300):k].reset_index(drop=True),old['symbol'],hourly_history=h.iloc[max(0,hk-1000):hk],as_of=at)
        assert sig is not None,(symbol,at)
        revised=normalize_targets(sig,.001 if symbol=='USDJPY' else .00001)
        for key in ['entry','stop_loss','tp1','tp2']:assert revised[key]==old[key],(symbol,at,key)
