"""Deterministic research pipeline for macro edge diagnostics."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence
from calibration.loss_attribution import attribute_losses
from calibration.historical_filter_lab import run_walk_forward_filter_lab

def run_research_pipeline(records:Sequence[Mapping[str,Any]],*,filter_dataset:Sequence[Mapping[str,Any]]|None=None,test_years:Sequence[int]=(2022,2023,2024,2025),quantile:float=.75)->Dict[str,Any]:
    result={"methodology_version":"research-pipeline-v2","production_activation":False,"loss_attribution":attribute_losses(records,group_by=("symbol","year")),"filter_lab":None,"conclusion":"diagnostic_only"}
    if filter_dataset is not None:result["filter_lab"]=run_walk_forward_filter_lab(filter_dataset,test_years=test_years,quantile=quantile)
    return result

def load_json_records(path:Path)->list[dict[str,Any]]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload,dict) and isinstance(payload.get("records"),list):return list(payload["records"])
    if isinstance(payload,list):return list(payload)
    raise ValueError("Expected a JSON list or an object containing records")

def save_report(report:Mapping[str,Any],path:Path)->None:path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
