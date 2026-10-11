"""Research-only deterministic loss attribution for macro trade records."""
from __future__ import annotations
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence
LOSS_CATEGORIES=("MACRO_DIRECTION_WRONG","CROSS_ASSET_DECOUPLING","WHIPSAW","SETUP_STALENESS","ENTRY_QUALITY_FAILURE","EXIT_OR_STOP_MANAGEMENT","UNEXPLAINED")
_LOSS_OUTCOMES={"LOSS","STOP","STOPPED","SL","STOP_LOSS"}
_FAILURE_MODE_MAP={"POI_STALENESS_AND_MARKET_FATIGUE":("SETUP_STALENESS","stale_poi"),"PREMIUM_OVERBOUGHT_REVERSAL":("ENTRY_QUALITY_FAILURE","premium_overbought"),"HTF_COUNTER_TREND":("ENTRY_QUALITY_FAILURE","htf_context_conflict"),"LOCAL_SMC_SUPPORT":("ENTRY_QUALITY_FAILURE","local_context_conflict"),"US_YIELD_MACRO_REVERSAL":("MACRO_DIRECTION_WRONG","macro_regime_reversal"),"US_YIELD_MACRO_REVERSAL_OR_MACRO_REVERSAL":("MACRO_DIRECTION_WRONG","macro_regime_reversal")}
def _text(v:Any)->str:return str(v or "").strip().upper()
def _nested(r:Mapping[str,Any])->Mapping[str,Any]:
 v=r.get("post_trade_macro_attribution");return v if isinstance(v,Mapping) else {}
def _lookup(r:Mapping[str,Any],k:str)->Any:
 p=_nested(r);return p[k] if k in p else r.get(k)
def _is_loss(r:Mapping[str,Any])->bool:return _text(_lookup(r,"trade_actual_outcome")) in _LOSS_OUTCOMES
def _explicit_category(v:Any)->Optional[str]:
 t=_text(v)
 if not t or t in {"NONE","NONE_PENDING","N/A","NA"}:return None
 for k,(c,_) in _FAILURE_MODE_MAP.items():
  if t==k or k in t:return c
 if "WHIPSAW" in t:return "WHIPSAW"
 if "DECOUPLING" in t or "CROSS_ASSET" in t:return "CROSS_ASSET_DECOUPLING"
 if "POI_STALENESS" in t or "STALE" in t or "MARKET_FATIGUE" in t:return "SETUP_STALENESS"
 if "PREMIUM_OVERBOUGHT" in t or "ENTRY" in t or "POI" in t:return "ENTRY_QUALITY_FAILURE"
 if "EXIT" in t or "STOP" in t or "TP" in t or "BREAKEVEN" in t:return "EXIT_OR_STOP_MANAGEMENT"
 if "MACRO_DIRECTION" in t or "DIRECTION_WRONG" in t:return "MACRO_DIRECTION_WRONG"
 return None
def classify_loss(r:Mapping[str,Any])->Dict[str,Any]:
 if not _is_loss(r):return {"is_loss":False,"category":None,"evidence":None}
 raw=_text(_lookup(r,"failure_attribution"));c=_explicit_category(raw)
 if c:
  mode=next((m for k,(cat,m) in _FAILURE_MODE_MAP.items() if cat==c and (raw==k or k in raw)),None)
  return {"is_loss":True,"category":c,"failure_mode":mode,"evidence":"failure_attribution"}
 if _lookup(r,"was_whipsawed") is True:return {"is_loss":True,"category":"WHIPSAW","failure_mode":"whipsaw","evidence":"was_whipsawed"}
 if _lookup(r,"decoupling_detected") is True:return {"is_loss":True,"category":"CROSS_ASSET_DECOUPLING","failure_mode":"cross_asset_decoupling","evidence":"decoupling_detected"}
 if _lookup(r,"macro_directional_accuracy") is False:return {"is_loss":True,"category":"MACRO_DIRECTION_WRONG","failure_mode":"macro_direction_wrong","evidence":"macro_directional_accuracy"}
 e=_text(_lookup(r,"exit_reason"))
 if any(x in e for x in ("STOP","SL","BREAKEVEN","TP")):return {"is_loss":True,"category":"EXIT_OR_STOP_MANAGEMENT","failure_mode":"exit_or_stop","evidence":"exit_reason"}
 return {"is_loss":True,"category":"UNEXPLAINED","failure_mode":None,"evidence":None}
def _group_value(r:Mapping[str,Any],k:str)->str:return _text(_lookup(r,k)) or "UNKNOWN"
def attribute_losses(records:Iterable[Mapping[str,Any]],*,group_by:Sequence[str]=())->Dict[str,Any]:
 rows=list(records);losses=[(r,x) for r in rows if (x:=classify_loss(r))["is_loss"]];counts=Counter(x["category"] for _,x in losses);modes=Counter(x["failure_mode"] for _,x in losses if x["failure_mode"]);n=len(losses);u=counts.get("UNEXPLAINED",0)
 out={"methodology_version":"loss-attribution-v2","production_activation":False,"records_seen":len(rows),"losses":n,"categories":{},"failure_modes":dict(sorted(modes.items())),"evidence_coverage_pct":round((n-u)/n*100,2) if n else 0.0,"unexplained_pct":round(u/n*100,2) if n else 0.0,"groups":{}}
 for c in LOSS_CATEGORIES:
  z=counts.get(c,0);out["categories"][c]={"count":z,"pct_of_losses":round(z/n*100,2) if n else 0.0}
 if group_by:
  g=defaultdict(Counter)
  for r,x in losses:g["|".join(f"{k}={_group_value(r,k)}" for k in group_by)][x["category"]]+=1
  out["groups"]={k:{"losses":sum(v.values()),"categories":dict(v)} for k,v in sorted(g.items())}
 return out
