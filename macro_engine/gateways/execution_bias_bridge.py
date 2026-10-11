from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Tuple, Dict, Any

from config import BIAS_GATE_FILE
from core.deterministic_controls import GATE_VALUES

logger = logging.getLogger("ExecutionBiasBridge")


class ExecutionBiasBridge:
    """Fail-closed execution bridge; only deterministic gate output is authoritative."""

    MAX_GATE_AGE_MINUTES = 60

    def __init__(self, gate_file_path: Path = BIAS_GATE_FILE):
        self.gate_file = gate_file_path

    def load_gate_data(self) -> Dict[str, Any]:
        if not self.gate_file.exists():
            return {}
        try:
            with open(self.gate_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Gate dosyası okunamadı: %s", exc)
            return {}

    def _validate_gate_contract(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        if data.get("deterministic_gate_source") != "deterministic_metrics_only":
            return False, "Deterministic gate source missing or untrusted."
        gates = data.get("deterministic_execution_bias_gates")
        if not isinstance(gates, dict):
            return False, "Deterministic execution gate payload missing."
        for symbol, gate in gates.items():
            if not isinstance(symbol, str) or not isinstance(gate, str) or gate not in GATE_VALUES:
                return False, f"Invalid deterministic gate contract for {symbol!r}: {gate!r}"

        raw_timestamp = data.get("timestamp")
        if not raw_timestamp:
            return False, "Gate timestamp missing."
        try:
            stamp = dt.datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                now = dt.datetime.now()
                age_minutes = (now - stamp).total_seconds() / 60.0
            else:
                now_utc = dt.datetime.now(dt.timezone.utc)
                age_minutes = (now_utc - stamp.astimezone(dt.timezone.utc)).total_seconds() / 60.0
        except (TypeError, ValueError):
            return False, "Gate timestamp invalid."
        if age_minutes < -5.0 or age_minutes > self.MAX_GATE_AGE_MINUTES:
            return False, f"Gate is stale: age={age_minutes:.1f} minutes."
        return True, "ok"

    def is_trade_allowed(self, symbol: str, requested_action: str) -> Tuple[bool, str]:
        data = self.load_gate_data()
        valid, reason = self._validate_gate_contract(data)
        if not valid:
            return False, f"Macro execution gate fail-closed: {reason}"

        gates = data["deterministic_execution_bias_gates"]
        sym_key = symbol.upper()
        allowed_bias = gates.get(sym_key)
        if allowed_bias is None:
            return False, f"No deterministic gate defined for {sym_key}; trade denied."

        req_upper = requested_action.upper()
        if allowed_bias == "LONG_ONLY":
            return req_upper in {"BUY", "LONG"}, f"Deterministic gate for {sym_key}: LONG_ONLY"
        if allowed_bias == "SHORT_ONLY":
            return req_upper in {"SELL", "SHORT"}, f"Deterministic gate for {sym_key}: SHORT_ONLY"
        if allowed_bias in {"DEFENSIVE_HOLD", "NO_TRADE", "REDUCE_ONLY", "NEUTRAL_RANGE", "NEUTRAL_ALL"}:
            return False, f"Deterministic gate for {sym_key}: {allowed_bias}; new trade denied."
        return False, f"Unknown deterministic gate {allowed_bias}; trade denied."

    def get_risk_profile(self) -> Dict[str, Any]:
        data = self.load_gate_data()
        return {
            "capital_preservation_mode": data.get("capital_preservation_mode", False),
            "recommended_risk_multiplier": data.get("recommended_risk_multiplier", 1.0),
            "volatility_risk_score": data.get("volatility_risk_score"),
            "primary_regime": data.get("primary_regime", "Unknown"),
            "deterministic_gate_source": data.get("deterministic_gate_source"),
        }
