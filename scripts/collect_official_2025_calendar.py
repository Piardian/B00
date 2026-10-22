"""Download primary calendar data and preserve the live weekly-feed field contract."""
import calendar
import gzip
import hashlib
import json
from pathlib import Path
import re
import time
import pandas as pd
from curl_cffi import requests


def main():
    root=Path(__file__).resolve().parents[1]/'data/full_2025_study'
    cache=root/'calendar_raw';cache.mkdir(exist_ok=True)
    months=['2024-12','2025-01','2025-02','2025-05','2025-06','2025-07','2025-10','2025-11','2025-12']
    records=[];manifest=[];seen=set()
    for month in months:
        year,number=map(int,month.split('-'));slug=calendar.month_abbr[number].lower()+'.'+str(year)
        url='https://www.forexfactory.com/calendar?month='+slug
        path=cache/(month+'.html.gz');old=cache/(month+'.html')
        if path.exists():html=gzip.decompress(path.read_bytes()).decode()
        elif old.exists():html=old.read_text(encoding='utf-8');path.write_bytes(gzip.compress(html.encode()))
        else:
            response=requests.get(url,impersonate='chrome',timeout=30)
            if response.status_code!=200:raise RuntimeError(f'Primary calendar unavailable: {month}, HTTP {response.status_code}')
            html=response.text;path.write_bytes(gzip.compress(html.encode()));time.sleep(1)
        match=re.search(r'window\.calendarComponentStates\[1\]\s*=\s*\{\s*days:\s*',html)
        if not match:raise RuntimeError('No primary calendar data assignment: '+month)
        days,_=json.JSONDecoder().raw_decode(html[match.end():])
        if len(days)!=calendar.monthrange(year,number)[1]:raise RuntimeError('Incomplete primary calendar month: '+month)
        stamps=[int(day['dateline']) for day in days]
        count=0
        for day in days:
            for event in day['events']:
                if event['id'] in seen:continue
                seen.add(event['id']);count+=1
                records.append({'DateTime':pd.Timestamp(int(event['dateline']),unit='s',tz='UTC').isoformat(),
                    'Currency':event['currency'],'Impact':event['impactName'].capitalize(),'Event':event['name'],
                    'Actual':event.get('actual',''),'Forecast':event.get('forecast',''),'Previous':event.get('previous',''),
                    'Revision':event.get('revision',''),'EventId':event['id'],'TimeMasked':event.get('timeMasked',False),
                    'SourceMonth':month,'Detail':''})
        manifest.append({'month':month,'source':url,'days':len(days),'events':count,'raw_sha256':hashlib.sha256(html.encode()).hexdigest(),
                         'coverage_start_utc':pd.Timestamp(min(stamps),unit='s',tz='UTC').isoformat(),
                         'coverage_end_utc_exclusive':pd.Timestamp(max(stamps)+86400,unit='s',tz='UTC').isoformat()})
        print('OFFICIAL_CALENDAR',month,len(days),count,flush=True)
    frame=pd.DataFrame(records).sort_values('DateTime')
    output=root/'forexfactory_2025_official.csv';frame.to_csv(output,index=False)
    (root/'calendar_primary_manifest.json').write_text(json.dumps({'months':manifest,
        'live_macro_field_contract':['country','date','forecast','impact','previous','title'],
        'actual_not_exported_to_macro':'Live weekly JSON has no actual field; historical actual is retained for audit only',
        'original_2025_capture_timestamps_verified':False},indent=2))


if __name__=='__main__':main()
