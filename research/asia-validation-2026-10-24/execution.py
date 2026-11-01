"""Research prototype: causal entry alternatives on explicitly assumed bid/ask.

Not a production bot, original-policy replica or historical broker-cost certificate.
"""
import pandas as pd
import math


def reaction(direction, b):
    width=max(b['high']-b['low'],1e-12)
    if direction=='LONG':
        return (min(b['open'],b['close'])-b['low'])/width>=.30 or b['close']>b['open']
    return (b['high']-max(b['open'],b['close']))/width>=.30 or b['close']<b['open']


def entry_reaction(signal, b):
    width=max(b['high']-b['low'],1e-12)
    zone_low=signal.get('zone_low',min(signal['entry'],signal['stop_loss']))
    zone_high=signal.get('zone_high',max(signal['entry'],signal['stop_loss']))
    body=abs(b['close']-b['open'])/width
    if signal['direction']=='LONG':
        sliced=b['close']<b['open'] and body>=.60 and b['close']<zone_low and (b['close']-b['low'])/width<=.22
    else:
        sliced=b['close']>b['open'] and body>=.60 and b['close']>zone_high and (b['high']-b['close'])/width<=.22
    return not sliced and reaction(signal['direction'],b)


def replay(signal, available_at, bars, policy, spread_pips=.5, slip_pips=.2, commission_usd=4.):
    if policy not in {'passive','reaction_retest','break_retest'}:raise ValueError('Unknown entry policy')
    if signal['direction'] not in {'LONG','SHORT'}:raise ValueError('Invalid direction')
    if any(not math.isfinite(v) or v<0 for v in (spread_pips,slip_pips,commission_usd)):raise ValueError('Invalid costs')
    symbol=signal['symbol'].replace('/','');long=signal['direction']=='LONG';sign=1 if long else -1
    pip=.01 if symbol.endswith('JPY') else .0001;tick=pip/10
    spread=spread_pips*pip;slip=slip_pips*pip
    entry=float(signal['entry']);sl=float(signal['stop_loss']);risk=abs(entry-sl)
    tp1=float(signal['tp1']);tp2=float(signal['tp2'])
    if not all(math.isfinite(v) and v>0 for v in (entry,sl,tp1,tp2)) or risk<=0:raise ValueError('Invalid prices')
    if not (sl<entry<tp1<tp2 if long else tp2<tp1<entry<sl):raise ValueError('Invalid geometry')
    start=pd.Timestamp(available_at);day=start.tz_convert('Europe/London').date()
    deadline=pd.Timestamp(signal['entry_deadline_utc'])
    flat=pd.Timestamp(f'{day} 16:30',tz='Europe/London').tz_convert('UTC')
    expiry=min(deadline,start+pd.Timedelta(hours=4))
    state='PENDING' if policy=='passive' else 'WATCH'
    filled=None;confirmed=None;gross=0.;commission_price=0.;remaining=1.;partial=False;trailing=False
    close_parts=[];expected=start;initial_sl=sl

    def currency_factor(price):return price if symbol.startswith('USD') else 1.
    def close(qty,price):
        nonlocal gross,commission_price,remaining
        gross+=qty*sign*(price-entry)/risk
        commission_price+=qty*(commission_usd/2)*currency_factor(price)/100000
        remaining-=qty;close_parts.append({'qty':qty,'price':price})
    def result(reason,at,status='CLOSED'):
        return dict(status=status,reason=reason,filled_at=str(filled) if filled is not None else None,
                    confirmed_at=str(confirmed) if confirmed is not None else None,closed_at=str(at),
                    gross_r=gross,commission_r=commission_price/risk,
                    net_r=gross-commission_price/risk if status=='CLOSED' else None,
                    original_entry=entry,original_stop=initial_sl,parts=close_parts)

    selected=bars[(bars.datetime>=start)&(bars.datetime<=flat)]
    for b in selected.to_dict('records'):
        at=b['datetime']
        if not all(math.isfinite(b[k]) and b[k]>0 for k in ('open','high','low','close')) or not b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']:
            return result('INVALID_OHLC',at,'UNRESOLVED')
        if at!=expected:return result('MISSING_M1_AT_'+str(expected),at,'UNRESOLVED')
        expected=at+pd.Timedelta(minutes=1)
        # These are exit-side executable quotes: bid for long, ask for short.
        eo=b['open']+(0 if long else spread)
        eh=b['high']+(0 if long else spread)
        el=b['low']+(0 if long else spread)
        ec=b['close']+(0 if long else spread)
        touch=(b['low']+spread<=entry-tick) if long else (b['high']>=entry+tick)
        stop=(el<=sl) if long else (eh>=sl)
        if filled is None:
            if at>=expiry:return result('NO_FILL_DEADLINE',at)
            if state in {'WATCH','WAIT_BREAK'}:
                # No resting order exists during confirmation: no retroactive fill.
                if stop:return result('SETUP_INVALIDATED_BEFORE_ORDER',at)
                if state=='WATCH' and touch and entry_reaction(signal,b):
                    confirmed=at+pd.Timedelta(minutes=1)
                    break_level=b['high'] if long else b['low']
                    if policy=='reaction_retest':
                        if (b['close']+spread>entry if long else b['close']<entry):state='PENDING'
                    else:state='WAIT_BREAK'
                elif state=='WAIT_BREAK' and (b['close']>break_level if long else b['close']<break_level):
                    if (b['close']+spread>entry if long else b['close']<entry):state='PENDING'
                continue  # Order can become eligible only on the next M1 bar.
            if not touch:continue
            filled=at
            commission_price+=(commission_usd/2)*currency_factor(entry)/100000
            if stop:
                price=min(sl,eo)-slip if long else max(sl,eo)+slip
                close(remaining,price);return result('FILL_BAR_STOP',at+pd.Timedelta(minutes=1))
            # Preserve an adverse-reaction market exit for every entry policy.
            if not entry_reaction(signal,b):
                close(remaining,ec-sign*slip);return result('REACTION_EXIT',at+pd.Timedelta(minutes=1))
            continue  # No target credit from unknown ordering inside the fill bar.
        if at>=flat:
            close(remaining,eo-sign*slip);return result('INTRADAY_FLAT',at)
        if stop:
            price=min(sl,eo)-slip if long else max(sl,eo)+slip
            close(remaining,price);return result('STOP_OR_BE_TRAIL',at+pd.Timedelta(minutes=1))
        hit2=eh>=tp2 if long else el<=tp2
        hit1=eh>=tp1 if long else el<=tp1
        if hit2:
            if not partial:close(.5,tp1)
            close(remaining,tp2);return result('TP2',at+pd.Timedelta(minutes=1))
        if hit1 and not partial:
            close(.5,tp1);partial=True;sl=entry
        elif partial and not trailing and (eh>=entry+1.5*risk if long else el<=entry-1.5*risk):
            sl=entry+sign*.75*risk;trailing=True
    return result('NO_QUOTE_FOR_FLAT_OR_DEADLINE',flat,'UNRESOLVED')
