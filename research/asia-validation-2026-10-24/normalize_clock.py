"""Keep original exports intact; validate and normalize broker wall time to UTC."""
import argparse
from pathlib import Path
import hashlib
import json
import sys
import datetime as dt
from zoneinfo import ZoneInfo
import pandas as pd

NY=ZoneInfo('America/New_York')


def broker_to_utc(values):
    stamps=pd.to_datetime(values,utc=True)
    # This broker follows the New York close: winter UTC+2, US summer UTC+3.
    # Verified independently against TwelveData including the US/EU DST gaps.
    offsets=[2+int(bool((x.to_pydatetime()-dt.timedelta(hours=2)).astimezone(NY).dst())) for x in stamps]
    return stamps-pd.to_timedelta(offsets,unit='h')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from sfp_orb_engine.config import ACTIVE_SYMBOLS,is_crypto,EXCLUDED_SFP_SYMBOLS
    manifest={}
    for symbol in ACTIVE_SYMBOLS:
        if symbol in EXCLUDED_SFP_SYMBOLS:continue
        clean=symbol.replace('/','')
        for tf in ('1m','15m','1h'):
            source=args.source/f'{clean}_{tf}.csv.gz'
            if not source.exists():continue
            target=args.output/source.name
            raw_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            df=pd.read_csv(source)
            if not is_crypto(symbol) and clean not in {'QQQ','SPY','NAS100'}:
                df.datetime=broker_to_utc(df.datetime)
                method='Broker wall time minus verified UTC+2/UTC+3 US DST offset'
            else:
                df.datetime=pd.to_datetime(df.datetime,utc=True)
                method='Source UTC retained'
            if df.datetime.duplicated().any():raise RuntimeError(f'Ambiguous broker clock in {source.name}')
            temp=target.with_name(target.name+'.partial')
            df.to_csv(temp,index=False,compression='gzip');temp.replace(target)
            manifest[source.name]={'source_sha256':raw_hash,'rows':len(df),'clock_policy':method,
                                   'normalized_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
            print('UTC',source.name,len(df),flush=True)
    (args.output/'provenance.json').write_text(json.dumps({'source':'Binance official archives; TwelveData QQQ/SPY; MT5 real broker bid ticks and native 15m/H1',
        'volume_semantics':'Binance base traded volume; ETF actual source volume; broker real tick count',
        'broker_timezone_validation':'../broker_timezone_validation.json; independent price correlation at US/EU DST discrepancies',
        'limitations':['Broker quotes are not the archived live TwelveData forex feed','Native broker month exports need UTC end-boundary supplementation before a full coverage certificate'],
        'files':manifest},indent=2))


if __name__=='__main__':main()
