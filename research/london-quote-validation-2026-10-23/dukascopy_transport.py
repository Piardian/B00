"""Public quote download with verified TLS and task-local DNS fallback."""
import socket,lzma,struct
import requests
import numpy as np
import pandas as pd
HOST='datafeed.dukascopy.com'

def resolve_fallback():
    try:socket.getaddrinfo(HOST,443);return None
    except socket.gaierror:
        r=requests.get('https://dns.google/resolve',params={'name':HOST,'type':'A'},timeout=15);r.raise_for_status()
        ips=[x['data'] for x in r.json().get('Answer',[]) if x['type']==1]
        if not ips:raise RuntimeError('No public DNS address')
        original=socket.getaddrinfo
        def lookup(host,*args,**kwargs):return original(ips[0] if host==HOST else host,*args,**kwargs)
        socket.getaddrinfo=lookup
        return dict(method='DNS-over-HTTPS A lookup; original HTTPS hostname and certificate verification retained',ip=ips[0])

def url(symbol,hour):
    return f'https://{HOST}/datafeed/{symbol}/{hour.year}/{hour.month-1:02}/{hour.day:02}/{hour.hour:02}h_ticks.bi5'

def decode(raw,hour,symbol):
    if not raw:return pd.DataFrame(columns=['time','bid','ask'])
    b=lzma.decompress(raw)
    if len(b)%20:raise RuntimeError('Partial tick record')
    scale=1000. if symbol.endswith('JPY') else 100000.
    d=np.frombuffer(b,dtype=np.dtype([('ms','>u4'),('ask','>u4'),('bid','>u4'),('av','>f4'),('bv','>f4')]))
    if (d['ms']>=3600000).any():raise RuntimeError('Tick time outside hour')
    f=pd.DataFrame(dict(time=hour+pd.to_timedelta(d['ms'].astype('int64'),unit='ms'),bid=d['bid'].astype(float)/scale,ask=d['ask'].astype(float)/scale))
    if not f.time.is_monotonic_increasing:raise RuntimeError('Unsorted tick tape')
    if not ((f.bid>0)&(f.ask>=f.bid)&np.isfinite(f.bid)&np.isfinite(f.ask)).all():raise RuntimeError('Invalid executable quotes')
    return f
