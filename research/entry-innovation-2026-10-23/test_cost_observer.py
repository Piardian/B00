import pytest
from cost_observer import observe

S=dict(symbol='EUR/USD',direction='LONG',entry=1.1,stop_loss=1.099,tp1=1.1012,tp2=1.102)
NOW='2025-01-02 09:00:00+00:00'


def test_cost_contract_and_partial_reward():
    r=observe(S,1.1,1.10005,NOW,NOW)
    assert r['spread_pips']==pytest.approx(.5)
    assert r['total_cost_budget_r']==pytest.approx(.11)
    assert r['weighted_full_target_gross_r']==pytest.approx(1.6)
    assert r['binary_full_win_full_loss_breakeven_winrate']==pytest.approx(1.11/2.6)


@pytest.mark.parametrize('q',['2025-01-02 08:59:54+00:00','2025-01-02 09:00:01+00:00'])
def test_stale_or_future_quote_unpriced(q):
    r=observe(S,1.1,1.10005,q,NOW)
    assert r['status']=='UNPRICED' and 'total_cost_budget_r' not in r


def test_reject_crossed_quotes():
    with pytest.raises(ValueError):observe(S,1.2,1.1,NOW,NOW)
