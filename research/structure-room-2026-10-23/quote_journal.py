"""Optional paper/research adapter for exported quotes. No broker or order API.

Input JSONL: signal, as_of (timezone-aware), optional quote {bid, ask,
quote_at, source}, optional hourly records. No quote => UNPRICED, no synthetic ask.
Commission/slip are caller-supplied research assumptions, not realized fills.
"""
import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path
import pandas as pd
from cost_observer import observe
from features import opposing_room


def utc(value):
    at=pd.Timestamp(value)
    if at.tzinfo is None or pd.isna(at):raise ValueError('Timezone-aware event time required')
    return at.tz_convert('UTC')


def build_record(event,commission_usd,exit_slip_pips):
    s=dict(event['signal']);at=utc(event['as_of']);quote=event.get('quote')
    if s['symbol'].replace('/','') not in {'EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD'}:raise ValueError('Unsupported quote/commission contract')
    if any(not math.isfinite(v) or v<0 for v in [commission_usd,exit_slip_pips]):raise ValueError('Invalid cost assumptions')
    if s['direction'] not in {'LONG','SHORT'}:raise ValueError('Invalid direction')
    if not all(math.isfinite(s[k]) and s[k]>0 for k in ['entry','stop_loss','tp1','tp2']):raise ValueError('Invalid signal price')
    prices=[s['stop_loss'],s['entry'],s['tp1'],s['tp2']]
    if not (prices==sorted(prices) and len(set(prices))==4 if s['direction']=='LONG' else prices==sorted(prices,reverse=True) and len(set(prices))==4):raise ValueError('Invalid signal geometry')
    if not quote:
        cost=dict(status='UNPRICED',reason='MISSING_BID_ASK')
    else:
        if not quote.get('source'):raise ValueError('Quote source label required')
        cost=observe(s,float(quote['bid']),float(quote['ask']),utc(quote['quote_at']),at,
                     commission_usd=commission_usd,exit_slip_pips=exit_slip_pips)
    h=pd.DataFrame(event.get('hourly',[]))
    if h.empty:
        room=dict(status='UNKNOWN',reason='NO_H1_INPUT')
    else:
        h['datetime']=h['datetime'].map(utc)
        if h.datetime.duplicated().any() or not h.datetime.is_monotonic_increasing:raise ValueError('Invalid H1 chronology')
        if not all(math.isfinite(v) and v>0 for k in ['high','low'] for v in h[k]):raise ValueError('Invalid H1 values')
        if (h.high<h.low).any():raise ValueError('Invalid H1 range')
        room=opposing_room(s,h,at)
    return dict(schema_version=1,mode='OBSERVATION_ONLY',as_of=str(at),signal=s,
      quote=quote,cost=cost,room=room,
      cost_assumptions=dict(commission_usd_roundtrip=commission_usd,exit_slip_pips=exit_slip_pips,
                            status='CONFIGURED_ASSUMPTIONS_NOT_REALIZED_COST'),
      warning='Caller-provided quote provenance; not independently broker-certified. No trade decision or order is generated.')


def append_record(db_path,record):
    raw=json.dumps(record,sort_keys=True,ensure_ascii=False,allow_nan=False)
    key=hashlib.sha256(raw.encode('utf-8')).hexdigest()
    path=Path(db_path);path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS research_quote_context (event_hash TEXT PRIMARY KEY, as_of TEXT NOT NULL, payload TEXT NOT NULL)')
        cursor=db.execute('INSERT OR IGNORE INTO research_quote_context VALUES (?,?,?)',(key,record['as_of'],raw))
        return cursor.rowcount==1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--commission-usd',type=float,required=True)
    parser.add_argument('--exit-slip-pips',type=float,required=True)
    args=parser.parse_args();added=0
    with args.input.open(encoding='utf-8') as f:
        for line in f:
            if line.strip():added+=append_record(args.db,build_record(json.loads(line),args.commission_usd,args.exit_slip_pips))
    print(json.dumps(dict(inserted=added,db=str(args.db),mode='OBSERVATION_ONLY')))


if __name__=='__main__':main()
