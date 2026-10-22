"""Index original detector outputs; never generate alternative entry rules.

This is an execution index, NOT a return backtest. Only the original minute
engine and original outcome tracker may turn these candidates into trades.
"""
from pathlib import Path
import argparse
import json
import sys
import time
import hashlib
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.replay_live_system import load_frame, Clock, HistoricalProvider, source_hashes
from sfp_orb_engine import config, orb_detector
from sfp_orb_engine.sfp_detector import SFPDetector
from sfp_orb_engine.orb_detector import ORBDetector
from sfp_orb_engine.execution_policy import completed_bars, higher_timeframe_trend


def prepass(symbol, root, output):
    clean = symbol.replace('/', '')
    target = output / (clean + '.json')
    hashes = source_hashes()
    input_hashes={tf:hashlib.sha256((root/f'{clean}_{tf}.csv.gz').read_bytes()).hexdigest() for tf in ('15m','1h') if (root/f'{clean}_{tf}.csv.gz').exists()}
    if target.exists():
        try:
            previous=json.loads(target.read_text())
            if previous['source_sha256']==hashes and previous.get('input_sha256')==input_hashes:return
        except (ValueError,KeyError):pass
    frames = {}
    for tf in ('15m', '1h'):
        path = root / f'{clean}_{tf}.csv.gz'
        if not path.exists():
            return
        frames[symbol, tf] = load_frame(path)
    sfp, orb = SFPDetector(), ORBDetector()
    clock = Clock('2025-01-01T00:00Z')
    provider = HistoricalProvider(frames, clock)
    candidates = []
    count = 0
    started = time.monotonic()
    cache = {}
    for month in ('2025-01','2025-06','2025-11'):
        start = pd.Timestamp(month+'-01',tz='UTC')
        end = start+pd.offsets.MonthBegin(1)
        for now in pd.date_range(start,end,freq='15min',inclusive='left'):
            if not config.is_market_open(symbol,now.to_pydatetime()) or not config.is_session_active_for_scan(symbol,now.to_pydatetime()):
                continue
            clock.current = now.to_pydatetime()
            df = completed_bars(provider.fetch_candles(symbol,'15m',300),15,clock.current)
            if len(df)<25 or (now-df.iloc[-1].datetime).total_seconds()>45*60:
                continue
            hourly = provider.fetch_candles(symbol,'1h',1000)
            as_of = df.iloc[-1].datetime+pd.Timedelta(minutes=15)
            key=(str(hourly.datetime.iloc[0]),str(hourly.datetime.iloc[-1]),as_of.floor('h'))
            if key not in cache:
                cache[key]=higher_timeframe_trend(hourly,as_of)
            trend=cache[key]
            if config.REQUIRE_PRO_TREND_AAA and trend not in {'BULLISH','BEARISH'}:
                continue
            count+=1
            candidate=sfp.detect_sfp(df,symbol,htf_trend=trend)
            if candidate is None and (now.weekday()<5 or config.WEEKEND_ORB_ENABLED):
                with patch.object(orb_detector,'datetime',clock.datetime_type()):
                    candidate=orb.detect_orb(df,symbol)
                if candidate:
                    candidate['htf_trend']=trend
                    expected='BULLISH' if candidate['direction']=='LONG' else 'BEARISH'
                    if trend==expected:
                        candidate['grade']='AAA (HTF ORB)'
                        candidate['trend_alignment']='PRO_TREND'
            if candidate:
                candidates.append({'window_start':now.isoformat(),'signal':candidate})
    temporary=target.with_name(target.name+'.partial')
    temporary.write_text(json.dumps({'symbol':symbol,'scope':'ORIGINAL_DETECTOR_INDEX_NOT_BACKTEST',
        'source_sha256':hashes,'input_sha256':input_hashes,'tested_windows':count,'candidates':candidates},default=str,indent=2))
    temporary.replace(target)
    print('INDEX',symbol,'candidates',len(candidates),'seconds',round(time.monotonic()-started),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--symbols',nargs='+')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    for symbol in args.symbols or config.ACTIVE_SYMBOLS:
        if symbol in config.EXCLUDED_SFP_SYMBOLS:continue
        prepass(symbol,args.data_root,args.output)


if __name__=='__main__':main()
