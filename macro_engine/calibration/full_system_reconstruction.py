"""Historical IO adapters for the unmodified production macro graph.

No macro rules, LLM responses, or risk multipliers are fabricated. Network
outputs and graph exports are isolated from all live gate/cache paths.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import requests

MACRO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MACRO))
from ingestion.fred_data import FredDataIngestion
from data_quality import DataUnavailableError, REQUIRED_MARKET_FIELDS
from calibration.historical_market_replay import HistoricalMarketReplayIngestion
from config import MARKET_SYMBOLS

UTC = dt.timezone.utc
STUDY = MACRO.parent / "data/full_2025_study"


def vintage_dates():
    dates = set()
    for month in ["2025-01", "2025-06", "2025-11"]:
        start = pd.Timestamp(month+"-01")
        end = start+pd.offsets.MonthBegin(1)
        dates.update(t.date()-dt.timedelta(days=1) for t in pd.date_range(start-pd.Timedelta(days=65),end,freq="D"))
    return sorted(dates)


class StrictVintageFred(FredDataIngestion):
    """Only ALFRED vintage responses, never current/revised cache fallbacks."""
    def __init__(self, root=STUDY):
        super().__init__()
        self.raw_dir = root / "alfred_raw"
        self.raw_dir.mkdir(parents=True,exist_ok=True)
        self.frames = {}
        self.releases = {}

    def release_dates(self,series_id):
        if series_id not in self.releases:
            path=self.raw_dir/f'{series_id}_publication_versions.json.gz'
            if path.exists():body=json.loads(gzip.decompress(path.read_bytes()))
            else:
                response=requests.get('https://api.stlouisfed.org/fred/series/observations',params={
                    'series_id':series_id,'api_key':self.api_key,'file_type':'json','output_type':1,
                    'realtime_start':'2024-01-01','realtime_end':'2025-12-01',
                    'observation_start':'2023-01-01','observation_end':'2025-12-01','limit':100000},timeout=40)
                if response.status_code!=200:raise DataUnavailableError(f'Official publication versions unavailable: {series_id} HTTP {response.status_code}')
                body=response.json();path.write_bytes(gzip.compress(json.dumps(body).encode()))
            dates={}
            for row in body['observations']:
                if row.get('value') in {'.','',None}:continue
                date=row['date'];published=row['realtime_start']
                dates[date]=min(dates.get(date,published),published)
            self.releases[series_id]=dates
        return self.releases[series_id]

    def _get_observations(self,series_id,start,end,realtime_end=None,units=None):
        if realtime_end is None:
            raise DataUnavailableError("Historical FRED request needs an explicit vintage")
        key = (series_id, units or "lin")
        if key not in self.frames:
            path = self.raw_dir / f"{series_id}_{units or 'lin'}.json.gz"
            if path.exists():
                body = json.loads(gzip.decompress(path.read_bytes()))
            else:
                params=dict(series_id=series_id,api_key=self.api_key,file_type="json",output_type=2,
                            vintage_dates=",".join(d.isoformat() for d in vintage_dates()),
                            observation_start="2023-01-01",observation_end="2025-12-01",limit=100000)
                if units:params["units"]=units
                response=requests.get("https://api.stlouisfed.org/fred/series/observations",params=params,timeout=40)
                if response.status_code != 200:
                    raise DataUnavailableError(f"Strict ALFRED unavailable: {series_id}, HTTP {response.status_code}")
                body=response.json()
                if body.get("output_type") != 2:
                    raise DataUnavailableError("ALFRED response is not vintage-specific")
                path.write_bytes(gzip.compress(json.dumps(body).encode()))
                print("ALFRED",series_id,units or "lin","dates",body.get("count"),flush=True)
            self.frames[key]=body["observations"]
        suffix=realtime_end.strftime("%Y%m%d")
        rows=[]
        for row in self.frames[key]:
            date=dt.date.fromisoformat(row["date"])
            if not start<=date<=end:continue
            keys=[k for k in row if k.endswith("_"+suffix)]
            if keys and row[keys[0]] != ".":rows.append((date,float(row[keys[0]])))
        if not rows:raise DataUnavailableError(f"No real vintage observations: {series_id} {realtime_end}")
        return rows

    def fetch_liquidity_metrics(self,as_of=None):
        # ALFRED is date-granular; use the last fully elapsed UTC date to avoid
        # admitting same-day releases before their publication times.
        if as_of is None:raise DataUnavailableError("No historical as_of supplied")
        result=super().fetch_liquidity_metrics(as_of=as_of-dt.timedelta(days=1))
        quality=result['data_quality']
        for original,published,mapping in [('observation_dates','publication_dates',self.BASE_FRED_SERIES),
                                            ('economic_observation_dates','economic_publication_dates',self.ECONOMIC_FRED_SERIES)]:
            quality[published]={}
            for field,date in quality[original].items():
                if date=='UNAVAILABLE':continue
                release=self.release_dates(mapping[field]).get(date)
                if release is None:raise DataUnavailableError('No official publication timestamp for '+field+' '+date)
                quality[published][field]=release
        quality['publication_date_source']='ALFRED output_type=1 first numeric real-time version; original reference-period dates preserved'
        return result


class HistoricalMarket(HistoricalMarketReplayIngestion):
    def __init__(self,fred,root=STUDY):
        super().__init__()
        self.fred=fred
        self.root=root
        self.history={}

    def _relative_history(self,name,vintage):
        from ingestion.bank_of_england import BankOfEnglandDataIngestion
        from ingestion.bank_of_canada import BankOfCanadaDataIngestion
        from ingestion.ecb_data import ECBDataIngestion
        directory=self.root/'official_rates';directory.mkdir(exist_ok=True)
        path=directory/f'{name}_all_rows.json'
        if name=='GB02Y' and not path.exists():
            point=directory/f'GB02Y_{vintage}.json'
            if point.exists():return json.loads(point.read_text())
            payload=BankOfEnglandDataIngestion().fetch_2y_yield(dt.datetime.combine(vintage,dt.time.max,tzinfo=UTC))
            point.write_text(json.dumps(payload));return payload
        if path.exists():stored=json.loads(path.read_text())
        else:
            if name=='CA02Y':
                source=BankOfCanadaDataIngestion()
                response=requests.get(f'{source.ENDPOINT}/{source.YIELD_2Y_SERIES_CODE}/json',params={'start_date':'2023-01-01','end_date':'2025-12-01'},timeout=25)
                response.raise_for_status();rows=source._extract_rows(response.json(),series_code=source.YIELD_2Y_SERIES_CODE)
                label='Bank of Canada official historical 2Y '+source.YIELD_2Y_SERIES_CODE
            elif name=='GB02Y':
                source=BankOfEnglandDataIngestion()
                response=requests.get(source.ENDPOINT,params={'csv.x':'yes','Datefrom':'01/Jan/2023','Dateto':'01/Dec/2025','SeriesCodes':'IUDMNZC','CSVF':'TN','UsingCodes':'Y','VPD':'Y'},headers={'User-Agent':'BegonyaMacroEngine/1.0'},timeout=25)
                if response.status_code != 200:
                    point=self.root/'official_rates'/f'GB02Y_{vintage}.json'
                    if point.exists():return json.loads(point.read_text())
                    payload=source.fetch_2y_yield(dt.datetime.combine(vintage,dt.time.max,tzinfo=UTC))
                    point.write_text(json.dumps(payload));return payload
                response.raise_for_status();rows=source._parse_csv(response.text)
                label='Bank of England official IUDMNZC 2Y'
            else:
                source=ECBDataIngestion()
                response=requests.get(f'{source.ENDPOINT}/{source.SERIES_KEY}',params={'startPeriod':'2023-01-01','endPeriod':'2025-12-01','format':'csvdata'},timeout=25)
                response.raise_for_status()
                import io
                frame=pd.read_csv(io.StringIO(response.text)).sort_values('TIME_PERIOD')
                rows=[(dt.date.fromisoformat(d),float(v)) for d,v in zip(frame.TIME_PERIOD,frame.OBS_VALUE)]
                label='ECB official 2Y euro-area curve; same production benchmark'
            stored={'rows':[[d.isoformat(),v] for d,v in rows],'source':label}
            path.write_text(json.dumps(stored))
        rows=[r for r in stored['rows'] if r[0]<=vintage.isoformat()]
        if not rows:raise DataUnavailableError('No historical official relative-value observations: '+name)
        result=self._build_payload(name,[v for d,v in rows][-60:],dt.datetime.combine(vintage,dt.time.max,tzinfo=UTC),stored['source'])
        result['observation_date']=rows[-1][0];return result

    def _historical_quotes(self,name,as_of,n_bars):
        """Daily baselines plus only already-closed intraday quotes, no D1 lookahead."""
        directory=self.root/'market_history';directory.mkdir(exist_ok=True)
        if name not in self.history:
            path=directory/f'{name}.json.gz'
            if path.exists():body=json.loads(gzip.decompress(path.read_bytes()))
            else:
                from ingestion.mt5_market_data import mt5
                broker=self.find_broker_symbol(name)
                body={}
                if broker and mt5 is not None:
                    daily=mt5.copy_rates_range(broker,mt5.TIMEFRAME_D1,dt.datetime(2024,7,1,tzinfo=UTC),dt.datetime(2025,12,1,tzinfo=UTC))
                    intra=mt5.copy_rates_range(broker,mt5.TIMEFRAME_M15,dt.datetime(2024,11,1,tzinfo=UTC),dt.datetime(2025,12,1,tzinfo=UTC))
                    if daily is not None and len(daily)>60:
                        body={'source':'MT5 historical '+broker,'daily':[[int(r['time']),float(r['close'])] for r in daily],
                              'intraday':[[int(r['time'])+900,float(r['close'])] for r in intra] if intra is not None else []}
                if not body:
                    import yfinance as yf
                    ticker=yf.Ticker(MARKET_SYMBOLS[name])
                    daily=ticker.history(start='2024-07-01',end='2025-12-01',interval='1d',auto_adjust=False)
                    intra=ticker.history(start='2024-11-01',end='2025-12-01',interval='1h',auto_adjust=False)
                    if daily.empty:return None
                    body={'source':'Yahoo historical '+MARKET_SYMBOLS[name],
                          'daily':[[int(t.timestamp()),float(v)] for t,v in daily.Close.items()],
                          'intraday':[[int(t.timestamp())+3600,float(v)] for t,v in intra.Close.items()]}
                path.write_bytes(gzip.compress(json.dumps(body).encode()))
            self.history[name]=body
        body=self.history[name]
        if body['source'].startswith('MT5'):
            sys.path.insert(0,str(MACRO.parent))
            from scripts.normalize_broker_history import broker_to_utc
            daily_ends=broker_to_utc(pd.to_datetime([r[0]+86400 for r in body['daily']],unit='s',utc=True))
            intra_ends=broker_to_utc(pd.to_datetime([r[0] for r in body['intraday']],unit='s',utc=True))
            rows=[[int(t.timestamp()),r[1]] for t,r in zip(daily_ends,body['daily']) if t<=as_of]
            intra_rows=[[int(t.timestamp()),r[1]] for t,r in zip(intra_ends,body['intraday'])]
            quotes=[r for r in intra_rows if r[0]<=as_of.timestamp() and (not rows or r[0]>rows[-1][0])]
        else:
            rows=[r for r in body['daily'] if dt.datetime.fromtimestamp(r[0],UTC).date()<as_of.date()]
            quotes=[r for r in body['intraday'] if r[0]<=as_of.timestamp() and dt.datetime.fromtimestamp(r[0],UTC).date()==as_of.date()]
        closes=[r[1] for r in rows]
        quote_time=None
        if quotes:
            quote_time=quotes[-1][0];closes.append(quotes[-1][1])
        if len(closes)<2:return None
        payload=self._build_payload(name,closes[-n_bars:],as_of,body['source'])
        payload['intraday_quote_available_at']=dt.datetime.fromtimestamp(quote_time,UTC).isoformat() if quote_time else None
        payload['quote_policy']='Prior completed daily baselines plus last completed M15 broker / H1 Yahoo quote; no future daily close'
        return payload

    def fetch_symbol_snapshot(self,name,as_of,n_bars=60):
        vintage=as_of.date()-dt.timedelta(days=1)
        if name in {"AU02Y", "NZ02Y"}:
            from ingestion.international_rates import InternationalRatesDataIngestion
            series=InternationalRatesDataIngestion.AU_SERIES if name=="AU02Y" else InternationalRatesDataIngestion.NZ_SERIES
            rows=self.fred._get_observations(series,vintage-dt.timedelta(days=900),vintage,realtime_end=vintage)
            return self._build_payload(name,[value for date,value in rows][-60:],as_of,"Strict ALFRED vintage: production international benchmark "+series)
        if name in {"CA02Y", "DE02Y", "GB02Y"}:
            return self._relative_history(name,vintage)
            cache=self.root/"official_rates";cache.mkdir(exist_ok=True)
            path=cache/f"{name}_{vintage}.json"
            if path.exists():return json.loads(path.read_text())
            if name=="GB02Y":
                from ingestion.bank_of_england import BankOfEnglandDataIngestion
                payload=BankOfEnglandDataIngestion().fetch_2y_yield(dt.datetime.combine(vintage,dt.time.max,tzinfo=UTC))
            elif name=="CA02Y":
                from ingestion.bank_of_canada import BankOfCanadaDataIngestion
                source=BankOfCanadaDataIngestion()
                response=requests.get(f"{source.ENDPOINT}/{source.YIELD_2Y_SERIES_CODE}/json",params={"start_date":(vintage-dt.timedelta(days=120)).isoformat(),"end_date":vintage.isoformat()},timeout=20)
                response.raise_for_status()
                rows=source._extract_rows(response.json(),series_code=source.YIELD_2Y_SERIES_CODE)
                rows=[r for r in rows if r[0]<=vintage]
                payload=self._build_payload(name,[v for d,v in rows][-60:],as_of,"Bank of Canada official historical 2Y "+source.YIELD_2Y_SERIES_CODE)
            else:
                from ingestion.ecb_data import ECBDataIngestion
                source=ECBDataIngestion()
                response=requests.get(f"{source.ENDPOINT}/{source.SERIES_KEY}",params={"startPeriod":(vintage-dt.timedelta(days=120)).isoformat(),"endPeriod":vintage.isoformat(),"format":"csvdata"},timeout=25)
                response.raise_for_status()
                import io
                frame=pd.read_csv(io.StringIO(response.text)).sort_values("TIME_PERIOD")
                frame=frame[frame.TIME_PERIOD<=vintage.isoformat()]
                payload=self._build_payload(name,frame.OBS_VALUE.astype(float).tolist()[-60:],as_of,"ECB official historical 2Y euro-area curve; same production benchmark")
            path.write_text(json.dumps(payload));return payload
        if name == "US02Y":
            rows=self.fred._get_observations("DGS2",vintage-dt.timedelta(days=120),vintage,realtime_end=vintage)
            return self._build_payload(name,[value for date,value in rows][-60:],as_of,"FRED DGS2 historical vintage; same official source as production")
        return self._historical_quotes(name,as_of,n_bars)


_CALENDAR_FRAMES={}


def calendar_for(as_of,path=None):
    path=path or (STUDY/'forexfactory_2025_official.csv' if (STUDY/'forexfactory_2025_official.csv').exists() else STUDY/'forexfactory_history.csv')
    if str(path) not in _CALENDAR_FRAMES:
        frame=pd.read_csv(path,keep_default_na=False)
        times=pd.to_datetime(frame.DateTime,utc=True,format="mixed")
        _CALENDAR_FRAMES[str(path)]=(frame,times)
    frame,times=_CALENDAR_FRAMES[str(path)]
    # Production reads the high-impact events of the current calendar week.
    start=(pd.Timestamp(as_of).normalize()-pd.Timedelta(days=(as_of.weekday()+1)%7))
    stop=start+pd.Timedelta(days=7)
    if path.name=='forexfactory_2025_official.csv':
        manifest=json.loads((STUDY/'calendar_primary_manifest.json').read_text())
        cursor=start
        for period in sorted(manifest['months'],key=lambda row:row['coverage_start_utc']):
            left=pd.Timestamp(period['coverage_start_utc']);right=pd.Timestamp(period['coverage_end_utc_exclusive'])
            if right<=cursor:continue
            if left>cursor:break
            cursor=max(cursor,right)
            if cursor>=stop:break
        if cursor<stop:raise DataUnavailableError('Primary calendar has a coverage gap in requested week: '+start.isoformat())
    if times.min()>start or times.max()<stop-pd.Timedelta(days=1):
        raise DataUnavailableError('Historical calendar does not cover the full requested week: '+start.isoformat())
    selected=frame[(times>=start)&(times<stop)&frame.Impact.str.contains("High",case=False)]
    result=[]
    for _,row in selected.iterrows():
        timestamp=pd.Timestamp(row.DateTime).tz_convert("UTC")
        # Exact live weekly-feed contract: that feed has NO actual field.
        # Do not give the historical run information the live system never reads.
        result.append({"title":row.Event,"country":row.Currency,"impact":"High",
                       "date":timestamp.isoformat(),"forecast":row.Forecast,"previous":row.Previous})
    return result


def probe(as_of):
    from graph import macro_graph
    fred=StrictVintageFred()
    market=HistoricalMarket(fred)
    raw={}
    unavailable=[]
    for name in MARKET_SYMBOLS:
        try:item=market.fetch_symbol_snapshot(name,as_of)
        except Exception as exc:
            print("MARKET_UNAVAILABLE",name,type(exc).__name__,flush=True)
            item=None
        if item is not None:raw[name]=item
        else:unavailable.append(name)
    missing=REQUIRED_MARKET_FIELDS-set(raw)
    if missing:raise DataUnavailableError("Required historical market input missing: "+",".join(sorted(missing)))
    print("REAL_MARKET_READY",len(raw),"optional_unavailable",unavailable,flush=True)
    engine=macro_graph.MacroWorkflowEngine()
    engine.market_ingest=SimpleNamespace(fetch_current_prices=lambda:raw)
    engine.fred_ingest=fred
    captured=[]
    def capture(payload,path):
        captured.append(payload)
    events=calendar_for(as_of)
    # All atomic exports are intercepted, including hard-coded sibling paths.
    with patch.object(macro_graph,"save_macro_gate_atomic",capture):
        result=engine.run_pipeline(initial_events=events,as_of=as_of,previous_regime_state={})
    if not captured:raise RuntimeError("Production graph did not export a gate")
    output={"as_of":as_of.isoformat(),"gate":captured[0],"optional_market_unavailable":unavailable,
            "calendar_source":"historical ForexFactory dataset; actual filtered by release time; original capture time unverified",
            "macro_source":"Recomputed by production graph from historical inputs, not an original archived decision",
            "market_time_policy":"Completed D1 baselines and last completed M15 broker / H1 Yahoo quotes, with validated broker-to-UTC conversion; no future D1 close",
            "result":result}
    (STUDY/("macro_probe_"+as_of.strftime('%Y%m%dT%H%M')+".json")).write_text(json.dumps(output,default=str,indent=2))
    print("PRODUCTION_MACRO_PROBE_FINISHED",captured[0].get("recommended_risk_multiplier"),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--as-of",default="2025-01-06T07:30:00+00:00");args=p.parse_args()
    STUDY.mkdir(exist_ok=True)
    try:probe(dt.datetime.fromisoformat(args.as_of))
    except Exception as exc:
        (STUDY/"macro_production_probe_failure.json").write_text(json.dumps({"error":str(exc),"type":type(exc).__name__},indent=2))
        raise
