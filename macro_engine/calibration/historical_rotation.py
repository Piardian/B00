"""Research inputs only: settled funding is NOT live premiumIndex.lastFundingRate.

Never use this snapshot to certify a full live-equivalent rotation replay.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import gzip, hashlib, io, json, sys, zipfile
import pandas as pd
import requests
MACRO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(MACRO))
from ingestion.crypto_rotation_data import CRYPTO_ROTATION_UNIVERSE
from data_quality import DataUnavailableError


def historical_rotation(as_of,root):
    as_of=pd.Timestamp(as_of).tz_convert('UTC');left=as_of-pd.Timedelta(hours=24)
    cache=root/'rotation_raw';cache.mkdir(exist_ok=True)
    output=cache/(as_of.strftime('%Y%m%dT%H%M%S')+'.snapshot.json.gz')
    if output.exists():return json.loads(gzip.decompress(output.read_bytes()))
    def get(endpoint,params):
        path=cache/(hashlib.sha256(json.dumps([endpoint,params],sort_keys=True).encode()).hexdigest()+'.json.gz')
        if path.exists():return json.loads(gzip.decompress(path.read_bytes()))
        response=requests.get('https://fapi.binance.com'+endpoint,params=params,timeout=25)
        response.raise_for_status();body=response.json()
        if not isinstance(body,list):raise DataUnavailableError('No historical list: '+endpoint)
        path.write_bytes(gzip.compress(json.dumps(body).encode()));return body
    def futures_minutes(symbol):
        rows=get('/fapi/v1/klines',dict(symbol=symbol,interval='1m',startTime=int(left.timestamp()*1000),endTime=int(as_of.timestamp()*1000)-1,limit=1500))
        rows=[r for r in rows if int(r[0])+60000<=int(as_of.timestamp()*1000)]
        if len(rows)!=1440:raise DataUnavailableError('Incomplete futures minutes: '+symbol+' '+str(len(rows)))
        return rows
    def collect(name,meta):
        frames=[]
        for month in sorted(set(pd.date_range((as_of-pd.Timedelta(days=6)).normalize(),as_of,freq='D').strftime('%Y-%m'))):
            path=root/'prices/binance_zips'/f"{meta['spot_symbol']}-1m-{month}.zip"
            if not path.exists():raise DataUnavailableError('Missing actual spot archive: '+str(path))
            with zipfile.ZipFile(path) as archive:df=pd.read_csv(archive.open(archive.namelist()[0]),header=None)
            stamps=pd.to_numeric(df[0],errors='coerce');df=df[stamps.notna()].copy();stamps=stamps[stamps.notna()]
            df['datetime']=pd.to_datetime(stamps,unit='us' if stamps.max()>1e14 else 'ms',utc=True)
            df=df[(df.datetime+pd.Timedelta(minutes=1)<=as_of)&(df.datetime>=(as_of-pd.Timedelta(days=6)).normalize())]
            df=df.rename(columns={1:'open',2:'high',3:'low',4:'close',5:'base_volume',7:'quote_volume'})
            cols=['open','high','low','close','base_volume','quote_volume']
            for col in cols:df[col]=pd.to_numeric(df[col])
            frames.append(df.set_index('datetime')[cols])
        spot=pd.concat(frames).sort_index()
        def bars(period,count):
            frame=spot.resample(period).agg(dict(open='first',high='max',low='min',close='last',base_volume='sum',quote_volume='sum')).dropna().tail(count)
            if len(frame)!=count:raise DataUnavailableError('Incomplete spot rotation bars: '+name)
            return [{'timestamp':int(t.timestamp()*1000),**row.to_dict()} for t,row in frame.iterrows()]
        future=meta['futures_symbol'];fut=futures_minutes(future)
        funding=get('/fapi/v1/fundingRate',dict(symbol=future,startTime=int(left.timestamp()*1000),endTime=int(as_of.timestamp()*1000)-1,limit=100))
        if not funding:raise DataUnavailableError('No real funding '+future)
        oi_frames=[]
        for day in pd.date_range((as_of-pd.Timedelta(hours=25)).normalize(),as_of.normalize(),freq='D'):
            filename=f"{future}-metrics-{day.strftime('%Y-%m-%d')}.zip";path=cache/filename
            if not path.exists():
                response=requests.get(f'https://data.binance.vision/data/futures/um/daily/metrics/{future}/{filename}',timeout=25)
                response.raise_for_status();path.write_bytes(response.content)
            with zipfile.ZipFile(path) as archive:frame=pd.read_csv(archive.open(archive.namelist()[0]))
            frame['time']=pd.to_datetime(frame.create_time,utc=True)
            oi_frames.append(frame[(frame.time<as_of)&(frame.time.dt.minute==0)])
        oi=pd.concat(oi_frames).sort_values('time').tail(25)
        if len(oi)!=25:raise DataUnavailableError('No complete actual hourly OI: '+future)
        recent=spot[spot.index>=left]
        if len(recent)!=1440:raise DataUnavailableError('Incomplete actual spot rolling volume: '+name)
        return name,{**meta,'spot_last_price':float(recent.close.iloc[-1]),'spot_quote_volume_24h':float(recent.quote_volume.sum()),
            'spot_price_change_24h_pct':100*(float(recent.close.iloc[-1])/float(recent.open.iloc[0])-1),
            'futures_quote_volume_24h':sum(float(r[7]) for r in fut),'funding_rate':float(sorted(funding,key=lambda r:int(r['fundingTime']))[-1]['fundingRate']),
            'mark_price':None,'bars_1h':bars('1h',26),'bars_4h':bars('4h',32),'deep_fetched':True,
            'oi_history_1h':[dict(timestamp=int(r.time.timestamp()*1000),sum_open_interest=float(r.sum_open_interest),sum_open_interest_value=float(r.sum_open_interest_value)) for r in oi.itertuples()]}
    snapshot=dict(status='RESEARCH_ONLY_FUNDING_FIELD_MISMATCH',replay_eligible=False,universe_size=len(CRYPTO_ROTATION_UNIVERSE),coins={},errors=[])
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(collect,name,meta) for name,meta in CRYPTO_ROTATION_UNIVERSE.items()]
        for future in as_completed(futures):
            name,data=future.result();snapshot['coins'][name]=data;print('REAL_ROTATION_INPUT',name,flush=True)
    rows=futures_minutes('BTCDOMUSDT');price=float(rows[-1][4]);boundary=int(as_of.floor('4h').timestamp()*1000)
    prior=[r for r in rows if int(r[0])+60000<=boundary]
    if not prior:raise DataUnavailableError('Missing actual BTCDOM prior close')
    snapshot['btc_dominance']=dict(btc_dominance_pct=None,eth_dominance_pct=None,btcdom_index_price=price,
        btcdom_change_24h_pct=100*(price/float(rows[0][1])-1),btcdom_change_4h_pct=100*(price/float(prior[-1][4])-1),source='Official historical Binance BTCDOM')
    snapshot['provenance']=dict(as_of=as_of.isoformat(),resolution='Real elapsed minutes; current H1/H4 formed only from elapsed M1; hourly samples of official 5m OI records',
        unavailable_unused='CoinGecko dominance percentage and mark price; original gate uses BTCDOM and available actual spot bars')
    output.write_bytes(gzip.compress(json.dumps(snapshot).encode()));return snapshot


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--as-of',required=True);p.add_argument('--root',type=Path,required=True);args=p.parse_args()
    historical_rotation(args.as_of,args.root)
