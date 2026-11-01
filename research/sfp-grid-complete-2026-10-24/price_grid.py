"""Research-only price quantization. No entries selected, no broker orders sent.

Applying this changes entry/stop/target geometry and REQUIRES a new chronological
replay. It is not a bound on strategy returns and is not used in older studies.
"""
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

FIELDS=('entry','stop_loss','tp1','tp2')

def number(value):
    result=Decimal(str(value))
    if not result.is_finite() or result<=0:
        raise ValueError('Finite positive price, step or reward ratio required')
    return result

def normalize_for_research(signal, tick_size, min_tp1_r='1.2', min_tp2_r='2.0'):
    """Adverse entry rounding, outward stop and outward minimum-R targets.

    Buy entry rounds UP, sell entry DOWN. Long stop DOWN, short stop UP.
    No favorable entry-price improvement is credited. More/earlier fills can
    still result, so the old fill ledger CANNOT be carried across. Broker2025
    historical specs, stops/freeze levels, distance to bid/ask, volume/margin,
    latency and order acceptance remain separate unverified requirements.
    """
    direction=signal.get('direction')
    if direction not in ['LONG','SHORT']:
        raise ValueError('LONG or SHORT direction required')
    step=number(tick_size);r1=number(min_tp1_r);r2=number(min_tp2_r)
    if r2<=r1:raise ValueError('TP2 minimum must exceed TP1 minimum')
    original={name:number(signal[name]) for name in FIELDS}
    long=direction=='LONG';sgn=Decimal(1 if long else -1)
    e,sl,t1,t2=(original[k] for k in FIELDS)
    if not (sl<e<t1<t2 if long else t2<t1<e<sl):
        raise ValueError('Original stop-entry-target ordering invalid')
    def grid(value,rounding):
        return (value/step).to_integral_value(rounding=rounding)*step
    entry=grid(e,ROUND_CEILING if long else ROUND_FLOOR)
    stop=grid(sl,ROUND_FLOOR if long else ROUND_CEILING)
    risk=abs(entry-stop)
    if entry<=0 or stop<=0 or risk<=0:
        raise ValueError('Quantization creates invalid price or risk')
    outward=ROUND_CEILING if long else ROUND_FLOOR
    farther=max if long else min
    tp1=grid(farther(t1,entry+sgn*risk*r1),outward)
    tp2=grid(farther(t2,entry+sgn*risk*r2),outward)
    if not (tp1<tp2 if long else tp2<tp1):tp2=tp1+sgn*step
    if min(tp1,tp2)<=0:raise ValueError('Quantization creates nonpositive target')
    levels=dict(entry=entry,stop_loss=stop,tp1=tp1,tp2=tp2)
    if not (stop<entry<tp1<tp2 if long else tp2<tp1<entry<stop):
        raise ValueError('Quantized ordering invalid')
    actual1=abs(tp1-entry)/risk;actual2=abs(tp2-entry)/risk
    if actual1<r1 or actual2<r2:raise ValueError('Quantized reward ratio too small')
    revised=deepcopy(signal)
    revised.update({name:float(v) for name,v in levels.items()})
    revised.update(risk_pips=float(risk),risk_distance=float(risk),
                   tp1_r=float(actual1),rr_ratio=float(actual2))
    revised['research_price_grid']=dict(status='RESEARCH_ONLY_NOT_ORDER_ACCEPTANCE',
        tick_size=str(step),original_levels={name:str(v) for name,v in original.items()},
        entry_rounding='BUY_UP_SELL_DOWN',stop_rounding='OUTWARD',targets='OUTWARD_MIN_R',
        original_risk=str(abs(e-sl)),new_risk=str(risk),
        original_ledger_reusable=False,broker_order_acceptance_verified=False)
    return revised
