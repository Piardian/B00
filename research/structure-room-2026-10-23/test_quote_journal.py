import json
import sqlite3
import pytest
from quote_journal import build_record,append_record


def event():
    return dict(signal=dict(symbol='EUR/USD',direction='LONG',entry=1.1,stop_loss=1.099,tp1=1.1012,tp2=1.102),
                as_of='2025-01-02 09:00:00+00:00')


def test_missing_quotes_never_fabricate_cost():
    r=build_record(event(),4.,.2)
    assert r['cost']==dict(status='UNPRICED',reason='MISSING_BID_ASK')
    assert r['room']['status']=='UNKNOWN'


def test_quote_adapter_uses_supplied_ask_and_labels_assumptions():
    e=event();e['quote']=dict(bid=1.1,ask=1.10005,quote_at=e['as_of'],source='unit-test synthetic quotes')
    r=build_record(e,4.,.2)
    assert r['cost']['spread_pips']==pytest.approx(.5)
    assert r['cost_assumptions']['status']=='CONFIGURED_ASSUMPTIONS_NOT_REALIZED_COST'


def test_future_quote_unpriced():
    e=event();e['quote']=dict(bid=1.1,ask=1.10005,quote_at='2025-01-02 09:01:00+00:00',source='test')
    assert build_record(e,4.,.2)['cost']['status']=='UNPRICED'


def test_timezone_required():
    e=event();e['as_of']='2025-01-02 09:00:00'
    with pytest.raises(ValueError):build_record(e,4.,.2)


def test_append_is_idempotent_and_preserves_unpriced_record(tmp_path):
    path=tmp_path/'journal.sqlite';r=build_record(event(),4.,.2)
    assert append_record(path,r)
    assert not append_record(path,r)
    with sqlite3.connect(path) as db:
        data=db.execute('SELECT payload FROM research_quote_context').fetchall()
    assert len(data)==1 and json.loads(data[0][0])['cost']['status']=='UNPRICED'


def test_nan_price_rejected():
    e=event();e['signal']['entry']=float('nan')
    with pytest.raises(ValueError):build_record(e,4.,.2)


def test_missing_quote_does_not_bypass_cost_validation():
    with pytest.raises(ValueError):build_record(event(),float('nan'),.2)


def test_unsupported_contract_not_priced_as_forex():
    e=event();e['signal']['symbol']='BTC/USD'
    with pytest.raises(ValueError):build_record(e,4.,.2)
