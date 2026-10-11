from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any, Dict, List, Optional, Mapping

from core.deterministic_controls import resolve_execution_gate
from graph.macro_graph_legacy import MacroWorkflowEngine as _LegacyMacroWorkflowEngine
from graph.macro_graph_legacy import MacroGraphState, save_macro_gate_atomic
from config import BIAS_GATE_FILE
from preprocessing.economic_regimes import build_economic_regime_snapshot
from preprocessing.policy_expectations import build_policy_expectations
from preprocessing.crypto_rotation import evaluate_crypto_rotation
from ingestion.bank_of_england import BankOfEnglandDataIngestion
from ingestion.bank_of_canada import BankOfCanadaDataIngestion
from ingestion.crypto_rotation_data import CryptoRotationDataIngestion


class MacroWorkflowEngine(_LegacyMacroWorkflowEngine):
    """Production macro workflow with explicit state/time and deterministic execution gates."""

    def _node_ingestion_and_preprocessing(self, state: MacroGraphState) -> Dict[str, Any]:
        as_of = getattr(self, "_as_of_date", None)
        as_of_datetime = getattr(self, "_as_of_datetime", None)
        raw_market = self.market_ingest.fetch_current_prices()

        try:
            uk_bank_rate = BankOfEnglandDataIngestion().fetch_bank_rate(as_of_datetime)
        except Exception as exc:
            uk_bank_rate = {
                "status": "UNAVAILABLE",
                "value": None,
                "previous_value": None,
                "observation_date": None,
                "source": "Bank of England official Bank Rate (YWMB47D)",
                "error": str(exc),
            }

        try:
            ca_policy_rate = BankOfCanadaDataIngestion().fetch_policy_rate(as_of_datetime)
        except Exception as exc:
            ca_policy_rate = {
                "status": "UNAVAILABLE",
                "value": None,
                "previous_value": None,
                "observation_date": None,
                "source": "Bank of Canada official Target for the overnight rate (V39079)",
                "error": str(exc),
            }

        raw_fred = self.fred_ingest.fetch_liquidity_metrics(as_of=as_of)
        raw_fred["UK_BANK_RATE"] = uk_bank_rate.get("value")
        raw_fred["UK_BANK_RATE_PREVIOUS"] = uk_bank_rate.get("previous_value")
        raw_fred["UK_BANK_RATE_SOURCE_DATE"] = uk_bank_rate.get("observation_date")
        raw_fred.setdefault("data_quality", {})["uk_bank_rate"] = uk_bank_rate
        raw_fred["CA_POLICY_RATE"] = ca_policy_rate.get("value")
        raw_fred["CA_POLICY_RATE_PREVIOUS"] = ca_policy_rate.get("previous_value")
        raw_fred["CA_POLICY_RATE_SOURCE_DATE"] = ca_policy_rate.get("observation_date")
        raw_fred.setdefault("data_quality", {})["ca_policy_rate"] = ca_policy_rate

        supplied_events = state.get("calendar_events") or []
        events_provided = bool(state.get("calendar_events_supplied", False)) or bool(supplied_events)
        events = list(supplied_events) if events_provided else asyncio.run(self.cal_ingest.fetch_latest_events())

        previous_state = state.get("previous_regime_state") or {}
        processed = self.preprocessor.process_all_macro_data(
            raw_market,
            raw_fred,
            events,
            as_of_date=as_of,
            as_of_datetime=as_of_datetime,
            previous_regime_state=previous_state,
            now_utc=as_of_datetime,
        )
        processed["economic_regime_snapshot"] = build_economic_regime_snapshot(
            raw_fred,
            as_of=as_of,
            market_data=raw_market,
        )
        processed["policy_expectations"] = build_policy_expectations(
            raw_fred,
            market_data=raw_market,
        )

        # 8-Faktörlü Kripto Rotasyon Radarı (Canlı çalışmada veya test verisi sağlandığında)
        if isinstance(raw_market.get("CRYPTO_ROTATION_SNAPSHOT"), Mapping):
            processed["crypto_rotation_raw_snapshot"] = dict(raw_market["CRYPTO_ROTATION_SNAPSHOT"])
        elif as_of is None and type(self.market_ingest).__name__ == "MarketDataIngestion":
            try:
                processed["crypto_rotation_raw_snapshot"] = (
                    CryptoRotationDataIngestion().fetch_rotation_snapshot()
                )
            except Exception as rot_exc:
                processed["crypto_rotation_raw_snapshot"] = {
                    "status": "UNAVAILABLE",
                    "errors": [str(rot_exc)],
                }

        fred_dq = raw_fred.get("data_quality", {})
        processed["data_quality"]["fred_provider"] = fred_dq.get("provider", "FRED")
        processed["data_quality"]["ism_status"] = fred_dq.get("ism_status", "UNAVAILABLE")
        processed["data_quality"]["calendar_provider"] = "Caller" if events_provided else "ForexFactory"
        processed["data_quality"]["calendar_status"] = (
            "CALLER_SUPPLIED" if events_provided else getattr(self.cal_ingest, "get_last_status", lambda: "UNKNOWN")()
        )
        processed["data_quality"]["calendar_fail_closed"] = any(e.get("fail_closed") for e in events)

        return {
            "raw_market": raw_market,
            "raw_fred": raw_fred,
            "calendar_events": events,
            "processed_metrics": processed,
        }

    def _node_macro_strategist(self, state: MacroGraphState) -> Dict[str, Any]:
        result = super()._node_macro_strategist(state)
        final = result.get("final_output") or {}
        as_of = getattr(self, "_as_of_datetime", None)
        if as_of is not None:
            final["timestamp"] = as_of.isoformat()
            result["final_output"] = final
        return result

    @staticmethod
    def _build_deterministic_gates(metrics: Mapping[str, Any]) -> Dict[str, Any]:
        cross_analysis = metrics.get("cross_pairs_analysis", {})
        freeze = bool(cross_analysis.get("event_freeze", {}).get("active", False))
        fast_stress = bool(
            metrics.get("t0_fast_stress_analysis", {})
            .get("fast_stress_override", False)
        )

        real_yield = metrics.get("real_yield_info", {}).get("real_yield_pct")
        yield_curve = metrics.get("yield_curve", {})
        delta_10y_5d = yield_curve.get("delta_10y_5d_bps")
        bear_steepening = yield_curve.get("regime") == "Bear Steepening"

        dxy = metrics.get("dxy_trend_analysis", {})
        dxy_delta_20d = dxy.get("delta_20d_pct")
        liquidity = metrics.get("liquidity_dynamics", {})
        liquidity_delta = liquidity.get("delta_liquidity_billion")
        nfci = metrics.get("financial_conditions_analysis", {}).get("nfci_value")
        credit = metrics.get("credit_spread_analysis", {})
        credit_stress = str(credit.get("stress_level", ""))

        evidence: Dict[str, Any] = {}

        # XAUUSD: LONG_ONLY requires two independent supportive channels.
        gold_short = bool(
            metrics.get("gold_fiscal_dominance", {})
            .get("gold_short_allowed", False)
        )
        xau_bullish = []
        xau_bearish = []
        if isinstance(real_yield, (int, float)):
            (xau_bullish if float(real_yield) < 1.90 else xau_bearish).append(
                f"real_yield={'supportive' if float(real_yield) < 1.90 else 'restrictive'}:{float(real_yield):.2f}%"
            )
        if isinstance(dxy_delta_20d, (int, float)):
            (xau_bullish if float(dxy_delta_20d) < -0.5 else xau_bearish if float(dxy_delta_20d) > 0.5 else []).append(
                f"DXY_20d={float(dxy_delta_20d):+.2f}%"
            ) if abs(float(dxy_delta_20d)) > 0.5 else None
        if isinstance(liquidity_delta, (int, float)):
            (xau_bullish if float(liquidity_delta) > 0 else xau_bearish).append(
                f"net_liquidity_4w={float(liquidity_delta):+.1f}B"
            )
        if isinstance(nfci, (int, float)) and float(nfci) < 0:
            xau_bullish.append(f"NFCI={float(nfci):+.2f}")
        if bear_steepening:
            xau_bearish.append("bear_steepening")
        if isinstance(delta_10y_5d, (int, float)) and float(delta_10y_5d) >= 10.0:
            xau_bearish.append(f"10Y_5d={float(delta_10y_5d):+.1f}bps")
        xau_has_stress = bear_steepening or (isinstance(delta_10y_5d, (int, float)) and float(delta_10y_5d) >= 10.0)
        xau_liquidity_support = (
            isinstance(liquidity_delta, (int, float)) and float(liquidity_delta) >= 20.0
            and isinstance(nfci, (int, float)) and float(nfci) <= -0.30
        )

        if gold_short:
            xau_base = "SHORT_ONLY"
        elif len(xau_bullish) >= 2 and (not xau_bearish or (not xau_has_stress and xau_liquidity_support)):
            xau_base = "LONG_ONLY"
        else:
            xau_base = "NEUTRAL_RANGE"
        evidence["XAUUSD"] = {
            "bullish_factors": xau_bullish,
            "bearish_factors": xau_bearish,
            "minimum_for_long_only": 2,
        }

        # BTC: "no stress" is not enough. Require at least two independent
        # macro supports for LONG_ONLY and reject when clear bearish evidence exists.
        btc_bullish = []
        btc_bearish = []
        if isinstance(real_yield, (int, float)):
            (btc_bullish if float(real_yield) < 1.90 else btc_bearish).append(
                f"real_yield:{float(real_yield):.2f}%"
            )
        if isinstance(dxy_delta_20d, (int, float)):
            if float(dxy_delta_20d) < -0.5:
                btc_bullish.append(f"DXY_20d:{float(dxy_delta_20d):+.2f}%")
            elif float(dxy_delta_20d) > 0.5:
                btc_bearish.append(f"DXY_20d:{float(dxy_delta_20d):+.2f}%")
        if isinstance(liquidity_delta, (int, float)):
            (btc_bullish if float(liquidity_delta) > 0 else btc_bearish).append(
                f"net_liquidity_4w:{float(liquidity_delta):+.1f}B"
            )
        if isinstance(nfci, (int, float)):
            (btc_bullish if float(nfci) < 0 else btc_bearish).append(
                f"NFCI:{float(nfci):+.2f}"
            )
        if bear_steepening:
            btc_bearish.append("bear_steepening")
        if isinstance(delta_10y_5d, (int, float)) and float(delta_10y_5d) >= 10.0:
            btc_bearish.append(f"10Y_5d:{float(delta_10y_5d):+.1f}bps")
        if isinstance(credit_stress, str) and "Distress" in credit_stress:
            btc_bearish.append("credit_distress")

        has_severe_btc_risk = (
            bear_steepening
            or (isinstance(delta_10y_5d, (int, float)) and float(delta_10y_5d) >= 10.0)
            or (isinstance(credit_stress, str) and "Distress" in credit_stress)
        )
        btc_liquidity_support = (
            isinstance(liquidity_delta, (int, float)) and float(liquidity_delta) >= 20.0
            and isinstance(nfci, (int, float)) and float(nfci) <= -0.30
        )

        legacy_btc = metrics.get("btc_decoupling_analysis", {}).get(
            "recommended_btc_gate", "DEFENSIVE_HOLD"
        )
        if fast_stress:
            btc_base = "DEFENSIVE_HOLD"
        elif "SHORT_ONLY" in str(legacy_btc).upper() and bear_steepening:
            btc_base = "SHORT_ONLY"
        elif len(btc_bullish) >= 2 and (not btc_bearish or (not has_severe_btc_risk and btc_liquidity_support)):
            btc_base = "LONG_ONLY"
        else:
            btc_base = "NEUTRAL_RANGE"
        evidence["BTC"] = {
            "bullish_factors": btc_bullish,
            "bearish_factors": btc_bearish,
            "legacy_recommendation": legacy_btc,
            "minimum_for_long_only": 2,
        }

        # EURUSD: use both USD-side and EUR-side policy evidence.
        transatlantic = metrics.get("transatlantic_analysis", {})
        spread_bps = transatlantic.get("spread_bps")
        energy_penalty = bool(
            metrics.get("terms_of_trade_energy_analysis", {})
            .get("eurusd_energy_penalty", False)
        )
        euro_panel = metrics.get("economic_regime_snapshot", {}).get("euro_area_macro", {})
        us_minus_ecb = euro_panel.get("us_minus_ecb_policy_spread_bps")
        hicp_direction = euro_panel.get("hicp_direction")

        eur_bullish = []
        eur_bearish = []
        if isinstance(us_minus_ecb, (int, float)):
            if float(us_minus_ecb) < 100.0:
                eur_bullish.append(f"US-ECB policy spread:{float(us_minus_ecb):+.1f}bps")
            elif float(us_minus_ecb) > 100.0:
                eur_bearish.append(f"US-ECB policy spread:{float(us_minus_ecb):+.1f}bps")
        if isinstance(spread_bps, (int, float)):
            if float(spread_bps) < 100.0:
                eur_bullish.append(f"US-DE 10Y spread:{float(spread_bps):+.1f}bps")
            elif float(spread_bps) > 140.0:
                eur_bearish.append(f"US-DE 10Y spread:{float(spread_bps):+.1f}bps")
        if hicp_direction == "RISING":
            eur_bullish.append("EA HICP:RISING")
        elif hicp_direction == "FALLING":
            eur_bearish.append("EA HICP:FALLING")
        if energy_penalty:
            eur_bearish.append("EA energy penalty")

        dxy_confirm_bear = isinstance(dxy_delta_20d, (int, float)) and float(dxy_delta_20d) > 0.5
        dxy_confirm_bull = isinstance(dxy_delta_20d, (int, float)) and float(dxy_delta_20d) < -0.5

        if dxy_confirm_bear and (
            (isinstance(us_minus_ecb, (int, float)) and float(us_minus_ecb) > 100.0)
            or (isinstance(spread_bps, (int, float)) and float(spread_bps) > 140.0)
            or energy_penalty
        ):
            eur_base = "SHORT_ONLY"
        elif dxy_confirm_bull and (
            isinstance(us_minus_ecb, (int, float))
            and float(us_minus_ecb) < 100.0
            and isinstance(spread_bps, (int, float))
            and float(spread_bps) < 150.0
        ):
            eur_base = "LONG_ONLY"
        else:
            eur_base = "NEUTRAL_RANGE"

        evidence["EURUSD"] = {
            "gate_basis": "US-ECB policy spread + US-DE 10Y spread + DXY confirmation + EA inflation/energy context",
            "us_minus_ecb_policy_spread_bps": us_minus_ecb,
            "transatlantic_spread_bps": spread_bps,
            "dxy_delta_20d_pct": dxy_delta_20d,
            "hicp_direction": hicp_direction,
            "energy_penalty": energy_penalty,
            "bullish_factors": eur_bullish,
            "bearish_factors": eur_bearish,
        }

        # Work on a private copy so gate construction never mutates input metrics.
        cross_gates_raw = dict(cross_analysis.get("cross_gates", {}) or {})

        # GBPUSD: relative-value direction confirmed by policy spread or 2Y yield spread momentum.
        gbpusd_legacy = str(cross_gates_raw.get("GBPUSD", "NEUTRAL_RANGE"))
        uk_panel = metrics.get("economic_regime_snapshot", {}).get("uk_policy", {})
        us_minus_uk = uk_panel.get("us_minus_uk_policy_spread_bps")
        gb_spread_delta = metrics.get("cross_pairs_analysis", {}).get("yield_spreads_bps", {}).get("GB02Y_minus_US02Y_delta_5d")
        if gb_spread_delta is None:
            gb_spread_delta = metrics.get("regime_state", {}).get("spread_gb_us_2y_delta_5d")
        gbpusd_confirmed = False
        if isinstance(us_minus_uk, (int, float)):
            if gbpusd_legacy == "SHORT_ONLY":
                gbpusd_confirmed = float(us_minus_uk) > 25.0 or (
                    float(us_minus_uk) > 0.0 and isinstance(gb_spread_delta, (int, float)) and float(gb_spread_delta) < -5.0
                )
            elif gbpusd_legacy == "LONG_ONLY":
                gbpusd_confirmed = float(us_minus_uk) < -25.0 or (
                    float(us_minus_uk) < 0.0 and isinstance(gb_spread_delta, (int, float)) and float(gb_spread_delta) > 5.0
                )
        if gbpusd_legacy in ("SHORT_ONLY", "LONG_ONLY") and not gbpusd_confirmed:
            cross_gates_raw = dict(cross_gates_raw)
            cross_gates_raw["GBPUSD"] = "NEUTRAL_RANGE"
            cross_analysis["cross_gates"] = cross_gates_raw

        # USDCAD: relative-value direction confirmed by policy spread or 2Y yield spread momentum.
        usdcad_legacy = str(cross_gates_raw.get("USDCAD", "NEUTRAL_RANGE"))
        ca_panel = metrics.get("economic_regime_snapshot", {}).get("canada_policy", {})
        us_minus_ca = ca_panel.get("us_minus_ca_policy_spread_bps")
        usdcad_confirmed = False
        if isinstance(us_minus_ca, (int, float)):
            if usdcad_legacy == "LONG_ONLY":
                usdcad_confirmed = float(us_minus_ca) > 25.0
            elif usdcad_legacy == "SHORT_ONLY":
                usdcad_confirmed = float(us_minus_ca) < -25.0
        if usdcad_legacy in ("LONG_ONLY", "SHORT_ONLY") and not usdcad_confirmed:
            cross_gates_raw = dict(cross_gates_raw)
            cross_gates_raw["USDCAD"] = "NEUTRAL_RANGE"
            cross_analysis["cross_gates"] = cross_gates_raw

        # SPX: allow LONG_ONLY when credit stress is benign, liquidity/NFCI are accommodative, and cycle is expansionary
        spx_allowed = bool(
            metrics.get("equity_short_regime", {})
            .get("equity_short_allowed", False)
        )
        hy_oas = credit.get("hy_oas_spread_pct")
        cycle = metrics.get("cycle_diagnosis", {})
        cycle_regime = str(cycle.get("primary_regime", ""))

        spx_bullish = []
        spx_bearish = []
        if isinstance(hy_oas, (int, float)) and float(hy_oas) < 3.50:
            spx_bullish.append(f"HY_OAS_benign:{float(hy_oas):.2f}%")
        elif isinstance(hy_oas, (int, float)) and float(hy_oas) > 4.50:
            spx_bearish.append(f"HY_OAS_stress:{float(hy_oas):.2f}%")

        if isinstance(nfci, (int, float)) and float(nfci) < 0:
            spx_bullish.append(f"NFCI_accommodative:{float(nfci):+.2f}")
        elif isinstance(nfci, (int, float)) and float(nfci) > 0.20:
            spx_bearish.append(f"NFCI_tightening:{float(nfci):+.2f}")

        if isinstance(liquidity_delta, (int, float)) and float(liquidity_delta) > 0:
            spx_bullish.append(f"net_liquidity_expansion:{float(liquidity_delta):+.1f}B")

        if "Reflationary" in cycle_regime or "Goldilocks" in cycle_regime or "Recovery" in cycle_regime:
            spx_bullish.append(f"regime:{cycle_regime}")
        elif "Stagflation" in cycle_regime or "Deflationary" in cycle_regime:
            spx_bearish.append(f"regime:{cycle_regime}")

        if spx_allowed:
            spx_base = "SHORT_ONLY"
        elif not fast_stress and len(spx_bullish) >= 2 and not spx_bearish:
            spx_base = "LONG_ONLY"
        else:
            spx_base = "NEUTRAL_RANGE"

        evidence["SPX"] = {
            "gate_basis": "equity_regime: credit spreads + NFCI + liquidity + cycle",
            "bullish_factors": spx_bullish,
            "bearish_factors": spx_bearish,
            "equity_short_allowed": spx_allowed,
        }

        cross = cross_gates_raw
        base_gates = {
            "XAUUSD": xau_base,
            "BTC": btc_base,
            "EURUSD": eur_base,
            "SPX": spx_base,
        }
        base_gates.update(
            {
                str(k): str(v)
                for k, v in cross.items()
                if isinstance(v, str) and str(k) not in base_gates
            }
        )

        # If BTC is not long-permitted, a legacy SOL long gate must not bypass it.
        if base_gates.get("BTC") != "LONG_ONLY" and base_gates.get("SOL") == "LONG_ONLY":
            base_gates["SOL"] = "NEUTRAL_RANGE"
            evidence["SOL"] = {
                "gate_basis": "BTC parent gate is not LONG_ONLY; SOL cannot bypass parent crypto regime."
            }

        resolved: Dict[str, str] = {}
        reasons: Dict[str, str] = {}
        for symbol, base_bias in base_gates.items():
            decision = resolve_execution_gate(
                base_bias,
                event_freeze=freeze,
                systemic_stress=fast_stress,
                risk_score=0.0,
            )
            resolved[symbol] = decision["gate"]
            reasons[symbol] = decision["reason"]

        crypto_rotation_analysis: Dict[str, Any] = {}
        raw_rot_snap = metrics.get("crypto_rotation_raw_snapshot")
        if isinstance(raw_rot_snap, Mapping) and raw_rot_snap.get("coins"):
            btc_decoupling = bool(
                metrics.get("btc_decoupling_analysis", {}).get("btc_decoupling_active", False)
            )
            crypto_rotation_analysis = evaluate_crypto_rotation(
                raw_rot_snap,
                macro_btc_gate=resolved.get("BTC", btc_base),
                btc_decoupling_active=btc_decoupling,
                capital_preservation_mode=fast_stress or freeze,
            )
            evidence["CRYPTO_ROTATION"] = {
                "status": crypto_rotation_analysis.get("status"),
                "approved_long_symbols": crypto_rotation_analysis.get("approved_long_symbols", []),
                "approved_short_symbols": crypto_rotation_analysis.get("approved_short_symbols", []),
                "on_demand_smc_targets": crypto_rotation_analysis.get("on_demand_smc_targets", []),
                "btc_dominance_panel": crypto_rotation_analysis.get("btc_dominance_panel", {}),
                "bellwether_ratios": crypto_rotation_analysis.get("bellwether_ratios", {}),
                "meme_froth_warning": crypto_rotation_analysis.get("meme_froth_warning", False),
            }
            # SOL kapısını 8 faktörlü rotasyon motoruyla senkronize et (ör. Short Squeeze kalkanı devredeyse SOL Short'u durdur)
            sol_rot = crypto_rotation_analysis.get("coin_assessments", {}).get("SOL")
            if isinstance(sol_rot, Mapping) and not freeze and not fast_stress:
                rot_gate = str(sol_rot.get("rotation_gate", "NEUTRAL_RANGE"))
                resolved["SOL"] = rot_gate
                base_gates["SOL"] = rot_gate
                reasons["SOL"] = str(sol_rot.get("rationale", "8-factor crypto rotation"))

        return {
            "execution_bias_gates": resolved,
            "gate_reasons": reasons,
            "base_gates": base_gates,
            "evidence": evidence,
            "crypto_rotation_analysis": crypto_rotation_analysis,
            "source": "deterministic_metrics_only",
            "precedence": ["EVENT_FREEZE", "SYSTEMIC_STRESS", "BASE_BIAS"],
            "llm_execution_gates_ignored": True,
        }

    def _node_gate_export(self, state: MacroGraphState) -> Dict[str, Any]:
        """Export execution gates derived only from deterministic metrics; LLM gates are advisory and ignored."""
        final_dict = state.get("final_output") or {}
        metrics = state.get("processed_metrics", {})
        deterministic = self._build_deterministic_gates(metrics)
        regime_state = dict(metrics.get("regime_state", {}) or {})
        crypto_rot = deterministic.get("crypto_rotation_analysis", {})
        if crypto_rot:
            metrics["crypto_rotation"] = crypto_rot
            metrics["crypto_rotation_analysis"] = crypto_rot
            regime_state["crypto_rotation"] = {
                "status": crypto_rot.get("status"),
                "macro_btc_gate": crypto_rot.get("macro_btc_gate"),
                "target_macro_direction": crypto_rot.get("target_macro_direction"),
                "meme_froth_warning": crypto_rot.get("meme_froth_warning", False),
                "btc_dominance_panel": crypto_rot.get("btc_dominance_panel", {}),
                "bellwether_ratios": crypto_rot.get("bellwether_ratios", {}),
                "active_inflow_layers": crypto_rot.get("active_inflow_layers", []),
                "sector_breadth": crypto_rot.get("sector_breadth", {}),
                "approved_long_symbols": crypto_rot.get("approved_long_symbols", []),
                "approved_short_symbols": crypto_rot.get("approved_short_symbols", []),
                "on_demand_smc_targets": crypto_rot.get("on_demand_smc_targets", []),
                "top_rotation_candidates": crypto_rot.get("top_rotation_candidates", []),
                "vetoed_symbols": crypto_rot.get("vetoed_symbols", {}),
            }
            if isinstance(metrics.get("regime_state"), dict):
                metrics["regime_state"]["crypto_rotation"] = regime_state["crypto_rotation"]

        payload = {
            "timestamp": final_dict.get("timestamp") or metrics.get("data_quality", {}).get("as_of_datetime"),
            "primary_regime": final_dict.get("primary_regime"),
            "volatility_risk_score": final_dict.get("volatility_risk_score"),
            "capital_preservation_mode": final_dict.get("capital_preservation_mode", False),
            "btc_decoupling_active": metrics.get("btc_decoupling_analysis", {}).get("btc_decoupling_active", False),
            "hysteresis_active": bool(regime_state.get("energy_penalty_active")),
            "recommended_risk_multiplier": final_dict.get("recommended_risk_multiplier", 1.0),
            "execution_bias_gates": deterministic["execution_bias_gates"],
            "deterministic_execution_bias_gates": deterministic["execution_bias_gates"],
            "deterministic_base_gates": deterministic.get("base_gates", {}),
            "deterministic_gate_evidence": deterministic.get("evidence", {}),
            "deterministic_gate_reasons": deterministic.get("gate_reasons", {}),
            "deterministic_gate_source": deterministic["source"],
            "gate_precedence": deterministic["precedence"],
            "llm_execution_gates_ignored": True,
            "asset_biases": final_dict.get("asset_biases", {}),
            "regime_state": regime_state,
            "crypto_rotation": crypto_rot,
            "macro_rationale": final_dict.get("macro_rationale", ""),
            "horizon_today": final_dict.get("horizon_today", ""),
            "horizon_this_week": final_dict.get("horizon_this_week", ""),
            "horizon_this_month": final_dict.get("horizon_this_month", ""),
            "economic_regime_snapshot": metrics.get("economic_regime_snapshot", {}),
            "policy_expectations": metrics.get("policy_expectations", {}),
            "data_quality": metrics.get("data_quality", {}),
        }
        save_macro_gate_atomic(payload, BIAS_GATE_FILE)
        return {}

    def run_pipeline(
        self,
        initial_events: Optional[List[Dict[str, Any]]] = None,
        as_of: Optional[dt.datetime] = None,
        previous_regime_state: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run with caller-supplied events/state; no hidden persistent regime state is consulted."""
        self._as_of_datetime = as_of
        self._as_of_date = as_of.date() if as_of is not None else None
        initial_state = {
            "raw_market": {},
            "raw_fred": {},
            "calendar_events": list(initial_events or []),
            "calendar_events_supplied": initial_events is not None,
            "previous_regime_state": dict(previous_regime_state or {}),
            "processed_metrics": {},
            "liquidity_output": None,
            "growth_output": None,
            "final_output": None,
        }
        result = self.app.invoke(initial_state)
        det_gates = self._build_deterministic_gates(
            result.get("processed_metrics", {})
        )
        result["deterministic_execution_gates"] = det_gates
        if isinstance(result.get("processed_metrics"), dict) and det_gates.get("crypto_rotation_analysis"):
            result["processed_metrics"]["crypto_rotation"] = det_gates["crypto_rotation_analysis"]
        return result
