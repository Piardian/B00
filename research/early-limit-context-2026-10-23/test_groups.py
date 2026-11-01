import pytest
from study import stats


def row(day,value,filled=True):
    return dict(day=day,month=day[:7],status='CLOSED',filled_at=day if filled else None,net_r=value)


def test_no_fill_not_counted_as_win_or_trade():
    r=stats([row('2025-01-02',0,False)])
    assert r['fills']==0 and r['net_r']==0 and r['pf'] is None


def test_months_and_total_preserve_returns():
    r=stats([row('2025-01-02',1.),row('2025-11-02',-.5)])
    assert r['net_r']==.5 and r['monthly']['2025-11']['net_r']==-.5
    assert r['exploratory_day_bootstrap95_mean_setup_r'] is None


def test_identical_day_returns_have_identical_mean_ci():
    rows=[row(f'2025-01-{d:02}',.1) for d in range(2,7)]
    ci=stats(rows)['exploratory_day_bootstrap95_mean_setup_r']
    assert ci==pytest.approx([.1,.1])


def test_same_day_positions_resampled_as_one_cluster():
    rows=[row(f'2025-01-{d:02}',1.) for d in range(2,7)]
    rows += [row(f'2025-01-{d:02}',-1.) for d in range(2,7)]
    r=stats(rows)
    assert r['days']==5 and r['fills']==10
    assert r['exploratory_day_bootstrap95_mean_setup_r']==[0.,0.]
