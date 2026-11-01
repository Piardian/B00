from pathlib import Path
from datetime import datetime,timezone
import json
import pandas as pd
import requests
from dukascopy_transport import resolve_fallback,url,decode
BASE=Path(__file__).resolve().parent
def main():
    result=dict(at_utc=datetime.now(timezone.utc).isoformat())
    try:
        result['dns']=resolve_fallback();h=pd.Timestamp('2025-02-03 08:00Z')
        r=requests.get(url('EURUSD',h),timeout=20)
        result.update(http_status=r.status_code,retry_after=r.headers.get('Retry-After'))
        if r.status_code==200:
            f=decode(r.content,h,'EURUSD');f.to_parquet(BASE/'public_probe_quotes.parquet')
            result.update(status='REAL_QUOTES_AVAILABLE',rows=len(f))
        else:result['status']='PROVIDER_UNAVAILABLE_NO_QUOTE_SUBSTITUTION'
    except Exception as exc:result.update(status='PUBLIC_SOURCE_UNAVAILABLE',error=str(exc))
    (BASE/'public_probe.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
