"""Source-specific market availability for historical quotes, never synthetic bars.

The5ers published hours match the observed 2025 bid-tick closures. The live
Binance crypto feed remains 24/7. QQQ/SPY data is regular NYSE session data.
"""
import datetime as dt
from zoneinfo import ZoneInfo
from sfp_orb_engine.config import is_crypto
from sfp_orb_engine.execution_policy import utc_time

NY=ZoneInfo('America/New_York')


def broker_market_is_open(symbol,when):
    if is_crypto(symbol):return True
    local=utc_time(when).astimezone(NY)
    clean=symbol.replace('/','')
    if clean in {'QQQ','SPY','NAS100'}:
        return local.weekday()<5 and (9*60+30)<=local.hour*60+local.minute<16*60
    server=local.replace(tzinfo=None)+dt.timedelta(hours=7)
    if server.weekday()>=5:return False
    minute=server.hour*60+server.minute
    if clean=='XAUUSD':return 65<=minute<23*60+50
    return 5<=minute<23*60+55
