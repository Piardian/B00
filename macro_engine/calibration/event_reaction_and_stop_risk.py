"""Research-only event reaction state and stop-risk diagnostics."""
from __future__ import annotations
from typing import Any, Dict, Iterable, Mapping, Optional

def _f(v: Any)->Optional[float]:
    try:
        x=float(v); return x if x==x and abs(x)!=float("inf") else None
    except (TypeError,ValueError): return None

def reaction_state(pre_bps:Optional[float],post_5m_bps:Optional[float],post_15m_bps:Optional[float],post_30m_bps:Optional[float],post_60m_bps:Optional[float],expected_sign:int)->Dict[str,Any]:
    values=[_f(x) for x in (post_5m_bps,post_15m_bps,post_30m_bps,post_60m_bps)]; valid=[x for x in values if x is not None]; s=1 if expected_sign>=0 else -1
    if not valid:return {"state":"UNOBSERVED","persistence_bars":0,"reversal":False,"reaction_strength_bps":None}
    aligned=[x*s>0 for x in valid]; persistence=0
    for ok in aligned:
        if ok:persistence+=1
        else:break
    reversal=_f(pre_bps) is not None and valid[0]*s<0
    state="PERSISTENT" if persistence==len(valid) else "REVERSAL" if reversal else "WHIPSAW" if any(aligned) and not all(aligned) else "WEAK"
    return {"state":state,"persistence_bars":persistence,"reversal":bool(reversal),"reaction_strength_bps":round(max(abs(x) for x in valid),4)}

def cross_asset_confirmation(asset_returns:Mapping[str,Any],expected_directions:Mapping[str,int],min_assets:int=2)->Dict[str,Any]:
    aligned=[];opposed=[];missing=[]
    for asset,direction in expected_directions.items():
        x=_f(asset_returns.get(asset))
        if x is None:missing.append(asset)
        elif x*float(direction)>0:aligned.append(asset)
        elif x*float(direction)<0:opposed.append(asset)
    n=len(aligned)+len(opposed)
    return {"aligned_assets":aligned,"opposed_assets":opposed,"missing_assets":missing,"observed_assets":n,"coherent":len(aligned)>=min_assets and not opposed,"confirmation_ratio":round(len(aligned)/n,4) if n else None}

def stop_risk_diagnostics(*,entry_to_poi_bps:Optional[float],atr_bps:Optional[float],adverse_excursion_bps:Optional[float],event_freeze_active:bool=False,setup_age_bars:Optional[int]=None,stale_after_bars:Optional[int]=None,pre_event_move_bps:Optional[float]=None)->Dict[str,Any]:
    atr=_f(atr_bps);mae=_f(adverse_excursion_bps);poi=_f(entry_to_poi_bps);pre=_f(pre_event_move_bps)
    return {"poi_distance_bps":poi,"atr_bps":atr,"mae_bps":mae,"mae_to_atr":round(abs(mae)/atr,4) if mae is not None and atr and atr>0 else None,"event_freeze_active":bool(event_freeze_active),"setup_age_bars":setup_age_bars,"stale":bool(stale_after_bars is not None and setup_age_bars is not None and setup_age_bars>stale_after_bars),"pre_event_move_bps":pre,"pre_event_move_to_atr":round(abs(pre)/atr,4) if pre is not None and atr and atr>0 else None}

def evaluate_pre_registered_filter(row:Mapping[str,Any])->Dict[str,Any]:
    reasons=[]
    if row.get("event_freeze_active") is True:reasons.append("EVENT_FREEZE")
    if row.get("cross_asset_coherent") is False:reasons.append("CROSS_ASSET_DISAGREEMENT")
    if row.get("reaction_state") in {"REVERSAL","WHIPSAW"}:reasons.append("ADVERSE_EVENT_REACTION")
    if row.get("setup_stale") is True:reasons.append("SETUP_STALE")
    if row.get("pre_move_extreme") is True:reasons.append("PRE_EVENT_MOVE_EXTREME")
    return {"no_trade":bool(reasons),"reasons":reasons,"methodology_version":"pre_registered-filter-v1","production_activation":False}

def enrich_records(records:Iterable[Mapping[str,Any]],*,expected_directions:Mapping[str,int])->list[Dict[str,Any]]:
    out=[]
    for source in records:
        r=dict(source);returns=r.get("cross_asset_returns")
        if isinstance(returns,Mapping):
            c=cross_asset_confirmation(returns,expected_directions);r["cross_asset_confirmation"]=c;r["cross_asset_coherent"]=c["coherent"]
        r["filter_diagnostic"]=evaluate_pre_registered_filter(r);out.append(r)
    return out
