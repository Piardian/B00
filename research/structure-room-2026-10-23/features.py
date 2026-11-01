"""Causal structural entry and target-room research. No order API."""
import math
import pandas as pd
from execution import entry_reaction
from price_rules import normalize_targets
from cost_observer import observe


def opposing_room(signal, hourly, as_of):
    """Confirmed H1 2-left/2-right pivots, using only completed bars.

    Last 100 completed H1 bars; no level is an unknown, not unlimited room.
    """
    at=pd.Timestamp(as_of);sign=1 if signal['direction']=='LONG' else -1
    frame=hourly[hourly.datetime+pd.Timedelta(hours=1)<=at].tail(100)
    levels=[];records=frame.to_dict('records')
    field='high' if sign==1 else 'low'
    for i in range(2,len(records)-2):
        window=records[i-2:i+3]
        if any(window[j+1]['datetime']-window[j]['datetime']!=pd.Timedelta(hours=1) for j in range(4)):continue
        value=records[i][field]
        neighbors=[r[field] for j,r in enumerate(window) if j!=2]
        pivot=value>max(neighbors) if sign==1 else value<min(neighbors)
        if pivot and sign*(value-signal['entry'])>0:levels.append(value)
    if not levels:return dict(status='UNKNOWN',reason='NO_CONFIRMED_OPPOSING_H1_PIVOT',level=None,room_r=None,tp1_has_room=None)
    level=min(levels) if sign==1 else max(levels)
    risk=abs(signal['entry']-signal['stop_loss'])
    tick=.001 if 'JPY' in signal['symbol'] else .00001
    return dict(status='KNOWN',level=level,room_r=sign*(level-signal['entry'])/risk,
                tp1_has_room=bool(sign*(level-signal['tp1'])>=tick-1e-12))


def cost_record(signal,bid,spread_pips,at,market=False,quote_source='ASSUMED_SPREAD_ON_BID_M1'):
    pip=.01 if 'JPY' in signal['symbol'] else .0001
    observation=observe(signal,bid,bid+spread_pips*pip,at,at,exit_slip_pips=.4 if market else .2)
    return dict(**observation,quote_source=quote_source,quote_at=str(at),observed_at=str(at),
                spread_is_historical=False,entry_slippage_pips=.2 if market else 0.,exit_slippage_pips=.2)


def structural_entry(signal,available_at,bars,spread_pips):
    """Touch/reaction -> later closed M1 breaks reaction extreme -> next open.

    New structural stop is the reaction extreme plus one tick. Short stop uses
    ask equivalent. No order exists until next open; no retrospective fills.
    """
    start=pd.Timestamp(available_at);deadline=min(pd.Timestamp(signal['entry_deadline_utc']),start+pd.Timedelta(hours=4))
    long=signal['direction']=='LONG';sign=1 if long else -1
    pip=.01 if 'JPY' in signal['symbol'] else .0001;tick=pip/10;spread=spread_pips*pip
    frame=bars[(bars.datetime>=start)&(bars.datetime<=deadline)]
    rows=frame.to_dict('records');expected=start;reaction_bar=None
    for i,b in enumerate(rows):
        at=b['datetime']
        if at!=expected:return dict(status='UNRESOLVED',reason='MISSING_CONFIRMATION_M1',at=str(expected))
        expected=at+pd.Timedelta(minutes=1)
        if at>=deadline:break
        if not all(math.isfinite(b[k]) and b[k]>0 for k in ['open','high','low','close']):
            return dict(status='UNRESOLVED',reason='INVALID_CONFIRMATION_OHLC',at=str(at))
        if not b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:
            return dict(status='UNRESOLVED',reason='INVALID_CONFIRMATION_OHLC',at=str(at))
        if reaction_bar is None:
            original_stop=b['low']<=signal['stop_loss'] if long else b['high']+spread>=signal['stop_loss']
            if original_stop:return dict(status='SKIPPED',reason='ORIGINAL_STRUCTURE_BROKEN')
            touch=b['low']+spread<=signal['entry']-tick if long else b['high']>=signal['entry']+tick
            if touch and entry_reaction(signal,b):reaction_bar=b
            continue
        stop=reaction_bar['low']-tick if long else reaction_bar['high']+spread+tick
        if (b['low']<=stop if long else b['high']+spread>=stop):
            return dict(status='SKIPPED',reason='M1_STRUCTURE_BROKEN_BEFORE_ENTRY')
        broken=b['close']>reaction_bar['high'] if long else b['close']<reaction_bar['low']
        if not broken:continue
        entry_at=at+pd.Timedelta(minutes=1)
        if entry_at>=deadline:return dict(status='SKIPPED',reason='CONFIRMATION_TOO_LATE')
        if i+1>=len(rows) or rows[i+1]['datetime']!=entry_at:
            return dict(status='UNRESOLVED',reason='MISSING_NEXT_OPEN',at=str(entry_at))
        # Only next open is consulted here, never its future high/low/close.
        bid=float(rows[i+1]['open'])
        if not math.isfinite(bid) or bid<=0:return dict(status='UNRESOLVED',reason='INVALID_NEXT_OPEN')
        entry=bid+(spread+.2*pip if long else -.2*pip)
        if sign*(entry-stop)<=tick:return dict(status='SKIPPED',reason='GAP_INVALIDATES_NEW_STOP')
        revised=dict(signal,entry=entry,stop_loss=stop,
                     tp1=entry+sign*1.2*abs(entry-stop),tp2=entry+sign*2*abs(entry-stop))
        revised=normalize_targets(revised,tick)
        return dict(status='READY',signal=revised,at=str(entry_at),bid=bid,
                    reaction_at=str(reaction_bar['datetime']),confirmation_at=str(entry_at),
                    original_risk=abs(signal['entry']-signal['stop_loss']),new_risk=abs(entry-stop))
    return dict(status='SKIPPED',reason='NO_CONFIRMED_ENTRY')
