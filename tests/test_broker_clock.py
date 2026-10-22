import pandas as pd
from scripts.normalize_broker_history import broker_to_utc


def test_broker_clock_uses_verified_us_dst_not_european_dst():
    original=pd.Series(['2025-01-06T10:00Z','2025-06-06T10:00Z','2025-11-06T10:00Z',
                        '2025-03-28T10:00Z','2025-10-28T10:00Z'])
    assert broker_to_utc(original).dt.strftime('%H:%M').tolist()==['08:00','07:00','08:00','07:00','07:00']


def test_verified_source_closures_are_not_turned_into_fake_minute_bars():
    from scripts.historical_market_calendar import broker_market_is_open
    assert broker_market_is_open('EUR/USD','2025-06-02T20:54Z')
    assert not broker_market_is_open('EUR/USD','2025-06-02T20:55Z')
    assert not broker_market_is_open('EUR/USD','2025-06-02T21:04Z')
    assert broker_market_is_open('EUR/USD','2025-06-02T21:05Z')
    assert not broker_market_is_open('XAU/USD','2025-06-02T21:30Z')
    assert broker_market_is_open('XAU/USD','2025-06-02T22:05Z')
    assert not broker_market_is_open('EUR/USD','2025-01-05T22:04Z')
    assert broker_market_is_open('EUR/USD','2025-01-05T22:05Z')
    assert broker_market_is_open('BTC/USD','2025-06-02T21:00Z')
