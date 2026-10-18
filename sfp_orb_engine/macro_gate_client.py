"""
🌺 Begonya 00 - Makro Kapı ve Hiyerarşik Yönetişim İstemcisi
shared/macro_bias_gate.json entegrasyonu ve Yönsel Veto Filtresi
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .config import MACRO_GATE_FILE, SYMBOL_MAP_FILE

logger = logging.getLogger("Begonya00.MacroGate")


class MacroGateClient:
    def __init__(self, gate_path: Optional[Path] = None):
        self.gate_path = gate_path or MACRO_GATE_FILE
        self.symbol_map = self._load_symbol_map()

    def _load_symbol_map(self) -> Dict[str, Any]:
        if SYMBOL_MAP_FILE.exists():
            try:
                data = json.loads(SYMBOL_MAP_FILE.read_text(encoding="utf-8"))
                return data.get("mappings", {})
            except Exception as e:
                logger.warning(f"symbol_map.json okunamadi: {e}")
        return {}

    def _normalize_symbol(self, symbol: str) -> str:
        clean = symbol.replace("/", "").replace("-", "").upper()
        if "BTC" in clean:
            return "BTC"
        if "ETH" in clean:
            return "ETH"
        if "SOL" in clean:
            return "SOL"
        if clean in ["QQQ", "SPY", "NAS100"]:
            return "SPX"
        return clean

    def get_macro_state(self) -> Dict[str, Any]:
        """Makro kapı durumunu okur."""
        if not self.gate_path.exists():
            return {
                "active": False,
                "primary_regime": "UNKNOWN",
                "risk_multiplier": 1.0,
                "capital_preservation_mode": False,
                "execution_bias_gates": {},
            }

        try:
            raw = json.loads(self.gate_path.read_text(encoding="utf-8"))
            return {
                "active": True,
                "timestamp": raw.get("timestamp"),
                "primary_regime": raw.get("primary_regime", "Neutral"),
                "volatility_risk_score": raw.get("volatility_risk_score", 0.5),
                "capital_preservation_mode": raw.get("capital_preservation_mode", False),
                "risk_multiplier": float(raw.get("recommended_risk_multiplier", 1.0)),
                "execution_bias_gates": raw.get("execution_bias_gates", {}),
                "deterministic_bias_gates": raw.get("deterministic_execution_bias_gates", {}),
                "gate_conviction_multipliers": raw.get("gate_conviction_multipliers", {}),
            }
        except Exception as e:
            logger.error(f"Makro kapı JSON okuma hatası: {e}")
            return {
                "active": False,
                "primary_regime": "ERROR",
                "risk_multiplier": 1.0,
                "capital_preservation_mode": False,
                "execution_bias_gates": {},
            }

    def evaluate_gate(self, symbol: str, direction: str) -> Dict[str, Any]:
        """
        Sinyalin makro kapıdan geçip geçemeyeceğini denetler.
        direction: "LONG" veya "SHORT"
        """
        state = self.get_macro_state()
        norm_sym = self._normalize_symbol(symbol)
        gates = state.get("execution_bias_gates", {})
        det_gates = state.get("deterministic_bias_gates", {})
        conv_map = state.get("gate_conviction_multipliers", {}) or {}

        gate_bias = det_gates.get(norm_sym) or gates.get(norm_sym) or "NEUTRAL_RANGE"
        regime = state.get("primary_regime", "Unknown")
        risk_mult = state.get("risk_multiplier", 1.0)
        cap_pres = state.get("capital_preservation_mode", False)

        # 1. Sermaye Koruma Modu Kontrolü
        if cap_pres:
            return {
                "allowed": False,
                "decision": "VETO_CAPITAL_PRESERVATION",
                "reason": "Sermaye Koruma Modu (Stres Devre Kesicisi) aktif. Tüm işlemler engellendi.",
                "gate_bias": gate_bias,
                "regime": regime,
                "risk_multiplier": 0.0,
            }

        # 2. VETO / NO_TRADE / DEFENSIVE_HOLD Kontrolü
        if gate_bias in ["VETO", "CASH", "NO_TRADE", "DEFENSIVE_HOLD", "REDUCE_ONLY"]:
            return {
                "allowed": False,
                "decision": "VETO_MACRO",
                "reason": f"Makro kapı {norm_sym} için {gate_bias} savunma seviyesinde.",
                "gate_bias": gate_bias,
                "regime": regime,
                "risk_multiplier": 0.0,
            }

        effective_mult = (
            round(risk_mult * 0.50, 3)
            if gate_bias == "NEUTRAL_RANGE"
            else round(risk_mult * float(conv_map.get(norm_sym, 1.0)), 3)
        )

        # 3. Yönsel İzin Kontrolü
        if direction.upper() == "LONG":
            if gate_bias in ["LONG_ONLY", "NEUTRAL_RANGE"]:
                return {
                    "allowed": True,
                    "decision": "APPROVED",
                    "reason": f"Makro rejim ({regime}) LONG yönüyle uyumlu ({gate_bias}, Risk: {effective_mult}x).",
                    "gate_bias": gate_bias,
                    "regime": regime,
                    "risk_multiplier": effective_mult,
                }
            else:
                return {
                    "allowed": False,
                    "decision": "VETO_DIRECTION_MISMATCH",
                    "reason": f"Makro kapı {norm_sym} için SHORT_ONLY kısıtında. LONG sinyali reddedildi.",
                    "gate_bias": gate_bias,
                    "regime": regime,
                    "risk_multiplier": 0.0,
                }

        elif direction.upper() == "SHORT":
            if gate_bias in ["SHORT_ONLY", "NEUTRAL_RANGE"]:
                return {
                    "allowed": True,
                    "decision": "APPROVED",
                    "reason": f"Makro rejim ({regime}) SHORT yönüyle uyumlu ({gate_bias}, Risk: {effective_mult}x).",
                    "gate_bias": gate_bias,
                    "regime": regime,
                    "risk_multiplier": effective_mult,
                }
            else:
                return {
                    "allowed": False,
                    "decision": "VETO_DIRECTION_MISMATCH",
                    "reason": f"Makro kapı {norm_sym} için LONG_ONLY kısıtında. SHORT sinyali reddedildi.",
                    "gate_bias": gate_bias,
                    "regime": regime,
                    "risk_multiplier": 0.0,
                }

        return {
            "allowed": False,
            "decision": "UNKNOWN_DIRECTION",
            "reason": f"Bilinmeyen yön: {direction}",
            "gate_bias": gate_bias,
            "regime": regime,
            "risk_multiplier": 0.0,
        }
