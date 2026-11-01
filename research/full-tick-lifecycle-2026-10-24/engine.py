"""Chronological quote replay of fixed early-limit lifecycle; research only.

Observed bid/ask is source data. Commission/slip remain configured assumptions.
No broker orders, queue model or account returns. R is initial quote-price risk.
"""
import math
import pandas as pd
from reaction_rules_frozen import entry_reaction


def replay(signal,available_at,tape,point,ttl_minutes=240,spread_mult=1.,spread_floor_pips=0.,fee_mult=1.,slip_mult=1.):
    for value in [point,ttl_minutes,spread_mult,fee_mult,slip_mult]:
        if not math.isfinite(value) or value<=0:raise ValueError('Positive finite contract values required')
    if not math.isfinite(spread_floor_pips) or spread_floor_pips<0:raise ValueError('Invalid spread floor')
    symbol=signal['symbol'].replace('/','');long=signal['direction']=='LONG';sign=1 if long else -1
    if signal['direction'] not in {'LONG','SHORT'}:raise ValueError('Invalid direction')
    entry=float(signal['entry']);initial_stop=float(signal['stop_loss']);tp1=float(signal['tp1']);tp2=float(signal['tp2'])
    if not all(math.isfinite(p) and p>0 for p in [entry,initial_stop,tp1,tp2]):raise ValueError('Invalid signal prices')
    if not(initial_stop<entry<tp1<tp2 if long else tp2<tp1<entry<initial_stop):raise ValueError('Invalid geometry')
    risk=abs(entry-initial_stop);pip=.01 if symbol.endswith('JPY') else .0001
    slip=.2*pip*slip_mult;half_fee_usd=2.*fee_mult
    start=pd.Timestamp(available_at);expiry=min(pd.Timestamp(signal['entry_deadline_utc']),start+pd.Timedelta(minutes=ttl_minutes))
    day=start.tz_convert('Europe/London').date();flat=pd.Timestamp(f'{day} 16:30',tz='Europe/London').tz_convert('UTC')
    f=tape[(tape.time>=start)&(tape.time<=flat+pd.Timedelta(seconds=5))]
    filled=None;fill_minute=None;partial=False;tp1_minute=None;trailing=False;remaining=1.
    stop=initial_stop;pending_stop=None;gross=0.;commission=0.;slippage=0.;events=[]
    current_minute=None;current_minute_ns=None;bar=None;previous_time=start;marketable=None;reaction_close_at=None;last_raw_spread=None

    def factor(price):return price if symbol.startswith('USD') else 1.
    def result(status,reason,at):
        return dict(status=status,reason=reason,filled_at=str(filled) if filled is not None else None,
          closed_at=str(at),gross_r=gross,commission_r=commission,market_slippage_r=slippage,
          net_r=gross-commission if status=='CLOSED' else None,remaining_qty=remaining if filled is not None else 0.,
          marketable_opening=marketable,fill_quote_spread_pips=last_raw_spread,
          reaction_close_at=str(reaction_close_at) if reaction_close_at is not None else None,events=events)
    def close(qty,price,reason,at,market=False):
        nonlocal gross,commission,slippage,remaining
        if market:price-=sign*slip;slippage+=qty*slip/risk
        fee=qty*half_fee_usd*factor(price)/100000/risk
        gross+=qty*sign*(price-entry)/risk;commission+=fee;remaining-=qty
        events.append(dict(type=reason,at=str(at),qty=qty,price=price,commission_r=fee,stop=stop))

    if f.empty:return result('UNRESOLVED','NO_QUOTES',start)
    if not f.time.is_monotonic_increasing:return result('UNRESOLVED','UNSORTED_QUOTES',start)
    if f.iloc[0].time>start+pd.Timedelta(seconds=5):return result('UNRESOLVED','OPENING_QUOTE_LATE',start)
    for q in f.itertuples(index=False):
        at=q.time;bid=float(q.bid);raw_ask=float(q.ask)
        if not(math.isfinite(bid) and math.isfinite(raw_ask) and 0<bid<=raw_ask):return result('UNRESOLVED','INVALID_QUOTE',at)
        # Once pending expiry is reached, no later quote is needed for a timer
        # cancellation. Only an earlier unobserved interval can hide a fill.
        gap_end=min(at,expiry) if filled is None else at
        if gap_end.value-previous_time.value>60_000_000_000:return result('UNRESOLVED','QUOTE_GAP_BEFORE_TERMINAL',at)
        if filled is None and at>=expiry:return result('CLOSED','NO_FILL_DEADLINE',expiry)
        previous_time=at
        ask=bid+max((raw_ask-bid)*spread_mult,spread_floor_pips*pip)
        executable=bid if long else ask;minute_ns=(at.value//60_000_000_000)*60_000_000_000
        minute=pd.Timestamp(minute_ns,tz='UTC') if minute_ns!=current_minute_ns else current_minute
        if marketable is None:marketable=bool(entry>=ask if long else entry<=bid)
        pending_reaction=False
        if current_minute!=minute:
            if filled is not None and current_minute==fill_minute:
                if not entry_reaction(signal,bar):
                    pending_reaction=True;reaction_close_at=current_minute+pd.Timedelta(minutes=1)
                    events.append(dict(type='REACTION_CLOSE_KNOWN',at=str(reaction_close_at),executed_on_next_quote=str(at)))
            if pending_stop is not None:
                stop=pending_stop;pending_stop=None
                events.append(dict(type='STOP_UPDATE',at=str(at),new_stop=stop))
            current_minute=minute;current_minute_ns=minute_ns;bar=dict(open=bid,high=bid,low=bid,close=bid)
        else:
            bar['high']=max(bar['high'],bid);bar['low']=min(bar['low'],bid);bar['close']=bid
        if filled is None:
            hit=ask<=entry-point+point*1e-7 if long else bid>=entry+point-point*1e-7
            if not hit:continue
            filled=at;fill_minute=minute;fee=half_fee_usd*factor(entry)/100000/risk;commission+=fee
            last_raw_spread=(raw_ask-bid)/pip
            events.append(dict(type='LIMIT_FILL',at=str(at),qty=1.,price=entry,bid=bid,ask=ask,raw_ask=raw_ask,commission_r=fee))
        if at>=flat:
            close(remaining,executable,'INTRADAY_FLAT',at,True);return result('CLOSED','INTRADAY_FLAT',at)
        stop_hit=executable<=stop if long else executable>=stop
        if stop_hit:
            reason='FILL_TICK_STOP' if at==filled else 'STOP_OR_BE_TRAIL'
            close(remaining,executable,reason,at,True);return result('CLOSED',reason,at)
        if pending_reaction:
            close(remaining,executable,'REACTION_EXIT',at,True);return result('CLOSED','REACTION_EXIT',at)
        if minute==fill_minute:continue  # Original lifecycle forbids fill-M1 TP.
        hit2=executable>=tp2 if long else executable<=tp2
        hit1=executable>=tp1 if long else executable<=tp1
        if hit2:
            if not partial:close(.5,tp1,'TP1',at)
            close(remaining,tp2,'TP2',at);return result('CLOSED','TP2',at)
        if hit1 and not partial:
            close(.5,tp1,'TP1',at);partial=True;tp1_minute=minute;pending_stop=entry
        elif partial and not trailing and minute>tp1_minute and (executable>=entry+1.5*risk if long else executable<=entry-1.5*risk):
            pending_stop=entry+sign*.75*risk;trailing=True
    # The tape can finish just after pending expiry but cannot be assumed flat
    # while a filled position or an unexpired order remains.
    return result('UNRESOLVED','NO_QUOTES_TO_TERMINAL',f.iloc[-1].time)
