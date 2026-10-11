from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Mapping, Optional

from data_quality import DataUnavailableError, REQUIRED_ECONOMIC_FRED_FIELDS


MAX_AGE_DAYS = {
    "daily": 3,
    "monthly": 45,
    "quarterly": 120,
}

FREQUENCIES = {
    "CPI_YOY": "monthly",
    "CORE_CPI_YOY": "monthly",
    "PCE_YOY": "monthly",
    "CORE_PCE_YOY": "monthly",
    "PAYEMS": "monthly",
    "UNRATE": "monthly",
    "AHE_YOY": "monthly",
    "GDP_QOQ_SAAR": "quarterly",
    "INDPRO": "monthly",
    "RSAFS": "monthly",
    "DGS3MO": "daily",
    "DGS2": "daily",
    "DGS5": "daily",
    "DGS10": "daily",
    "DGS30": "daily",
    "T10Y2Y": "daily",
    "T10Y3M": "daily",
    "SOFR": "daily",
    "ISM_MANUFACTURING_PMI": "monthly",
    "ISM_SERVICES_ACTIVITY": "monthly",
    "EA_HICP_YOY": "monthly",
    "ECB_DEPOSIT_RATE": "daily",
}


def _num(data: Mapping[str, Any], key: str) -> Optional[float]:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _delta(data: Mapping[str, Any], key: str) -> Optional[float]:
    current = _num(data, key)
    prior = _num(data, f"{key}_4W_AGO")
    if current is None or prior is None:
        return None
    return round(current - prior, 6)


def _pct_change(data: Mapping[str, Any], key: str) -> Optional[float]:
    current = _num(data, key)
    prior = _num(data, f"{key}_4W_AGO")
    if current is None or prior is None or prior == 0:
        return None
    return (current / prior - 1.0) * 100.0


def _direction(delta: Optional[float], threshold: float) -> str:
    if delta is None:
        return "UNAVAILABLE"
    val = round(delta, 6)
    thresh = round(threshold, 6)
    if val >= thresh:
        return "RISING"
    if val <= -thresh:
        return "FALLING"
    return "STABLE"


def _pmi_state(value: Optional[float], delta: Optional[float]) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value > 50.0:
        return "EXPANDING" if delta is None or delta >= 0.0 else "EXPANDING_COOLING"
    if value < 50.0:
        return "CONTRACTING" if delta is None or delta <= 0.0 else "CONTRACTING_RECOVERING"
    return "NEUTRAL_50"


def _freshness(fred: Mapping[str, Any], as_of: Optional[dt.date]) -> Dict[str, int]:
    if as_of is None:
        return {}
    metadata = fred.get("data_quality", {})
    dates = metadata.get("economic_observation_dates", {}) if isinstance(metadata, Mapping) else {}
    ages: Dict[str, int] = {}
    for field, raw_date in dates.items():
        observation_date = dt.date.fromisoformat(str(raw_date))
        age = (as_of - observation_date).days
        allowed = MAX_AGE_DAYS[FREQUENCIES.get(field, "monthly")]
        if age < 0:
            raise DataUnavailableError(f"Future economic observation for {field}: {observation_date}")
        if age > allowed:
            raise DataUnavailableError(
                f"Stale economic observation for {field}: age={age}d > allowed={allowed}d"
            )
        ages[field] = age
    return ages


def _missing_fields(fred: Mapping[str, Any]) -> list[str]:
    return [key for key in sorted(REQUIRED_ECONOMIC_FRED_FIELDS) if not isinstance(fred.get(key), (int, float))]


def _fed_futures_panel(market_data: Optional[Mapping[str, Any]], dff: Optional[float]) -> Dict[str, Any]:
    data = (market_data or {}).get("FED_FUNDS_FUTURES")
    if not isinstance(data, Mapping) or not isinstance(data.get("value"), (int, float)):
        return {
            "status": "UNAVAILABLE",
            "source": "Yahoo Finance ZQ=F optional front 30-Day Fed Funds future",
            "market_implied_rate_pct": None,
            "vs_dff_bps": None,
            "reprice_1d_bps": None,
            "reprice_5d_bps": None,
            "methodology_warning": "Fed Funds futures feed unavailable; no synthetic rate is substituted.",
        }

    price = float(data["value"])
    implied_rate = 100.0 - price
    prev_price = data.get("prev")
    five_day_price = data.get("val_5d_ago")
    prev_implied = 100.0 - float(prev_price) if isinstance(prev_price, (int, float)) else None
    five_day_implied = 100.0 - float(five_day_price) if isinstance(five_day_price, (int, float)) else None
    return {
        "status": "AVAILABLE",
        "source": "Yahoo Finance ZQ=F; CME/CBOT 30-Day Fed Funds Futures",
        "contract_price": price,
        "market_implied_rate_pct": round(implied_rate, 4),
        "vs_dff_bps": None if dff is None else round((implied_rate - dff) * 100.0, 1),
        "reprice_1d_bps": None if prev_implied is None else round((implied_rate - prev_implied) * 100.0, 1),
        "reprice_5d_bps": None if five_day_implied is None else round((implied_rate - five_day_implied) * 100.0, 1),
        "interpretation": "lower_future_rate" if dff is not None and implied_rate < dff else "higher_future_rate" if dff is not None and implied_rate > dff else "near_policy",
        "methodology_note": "Implied rate is deterministic: 100 - futures price. Front-month only; not equivalent to a full CME FedWatch meeting probability curve.",
    }


def build_economic_regime_snapshot(
    fred: Mapping[str, Any],
    as_of: Optional[dt.date] = None,
    market_data: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a deterministic economic panel without inventing a composite score."""
    missing = _missing_fields(fred)
    if missing:
        return {
            "status": "UNAVAILABLE",
            "missing_fields": missing,
            "methodology_warning": "Economic regime panel withheld; required provider observations are missing.",
        }

    ages = _freshness(fred, as_of)

    inflation_delta = {
        "cpi_yoy_pp_4w": _delta(fred, "CPI_YOY"),
        "core_cpi_yoy_pp_4w": _delta(fred, "CORE_CPI_YOY"),
        "pce_yoy_pp_4w": _delta(fred, "PCE_YOY"),
        "core_pce_yoy_pp_4w": _delta(fred, "CORE_PCE_YOY"),
    }
    inflation_directions = [
        _direction(_delta(fred, "CPI_YOY"), 0.10),
        _direction(_delta(fred, "CORE_CPI_YOY"), 0.10),
        _direction(_delta(fred, "PCE_YOY"), 0.10),
        _direction(_delta(fred, "CORE_PCE_YOY"), 0.10),
    ]
    non_unknown_infl = [x for x in inflation_directions if x != "UNAVAILABLE"]
    inflation_signal = "MIXED"
    if non_unknown_infl and all(x == "RISING" for x in non_unknown_infl):
        inflation_signal = "RISING"
    elif non_unknown_infl and all(x == "FALLING" for x in non_unknown_infl):
        inflation_signal = "FALLING"
    elif non_unknown_infl and all(x == "STABLE" for x in non_unknown_infl):
        inflation_signal = "STABLE"

    payroll_change = _delta(fred, "PAYEMS")
    unemployment_change = _delta(fred, "UNRATE")
    wage_change_pp = _delta(fred, "AHE_YOY")
    claims_change = _delta(fred, "ICSA")
    if payroll_change is not None and unemployment_change is not None and claims_change is not None:
        if payroll_change < -100.0 or unemployment_change >= 0.20 or claims_change >= 15.0:
            labor_regime = "WEAKENING"
        elif payroll_change > 0.0 and unemployment_change <= 0.10 and claims_change < 10.0:
            labor_regime = "RESILIENT"
        else:
            labor_regime = "COOLING"
    else:
        labor_regime = "UNAVAILABLE"

    industrial_change = _pct_change(fred, "INDPRO")
    retail_change = _pct_change(fred, "RSAFS")
    gdp_growth = _num(fred, "GDP_QOQ_SAAR")
    if gdp_growth is not None and industrial_change is not None and retail_change is not None:
        if gdp_growth < 0.0 and industrial_change < 0.0 and retail_change < 0.0:
            growth_regime = "CONTRACTING"
        elif gdp_growth > 0.0 and industrial_change > 0.0 and retail_change > 0.0:
            growth_regime = "EXPANDING"
        else:
            growth_regime = "MIXED"
    else:
        growth_regime = "UNAVAILABLE"

    two_year = _num(fred, "DGS2")
    three_month = _num(fred, "DGS3MO")
    five_year = _num(fred, "DGS5")
    ten_year = _num(fred, "DGS10")
    thirty_year = _num(fred, "DGS30")
    two_ten_spread = _num(fred, "T10Y2Y")
    three_ten_spread = _num(fred, "T10Y3M")
    two_ten_delta = _delta(fred, "T10Y2Y")
    three_ten_delta = _delta(fred, "T10Y3M")
    curve_move = "STABLE"
    if two_ten_delta is not None:
        if two_ten_delta > 0.10:
            curve_move = "STEEPENING"
        elif two_ten_delta < -0.10:
            curve_move = "FLATTENING"

    dff = _num(fred, "DFF")
    sofr = _num(fred, "SOFR")
    policy_gap_bps = (two_year - dff) * 100.0 if two_year is not None and dff is not None else None
    sofr_gap_bps = (sofr - dff) * 100.0 if sofr is not None and dff is not None else None

    ea_hicp = _num(fred, "EA_HICP_YOY")
    ea_hicp_delta = _delta(fred, "EA_HICP_YOY")
    ecb_deposit_rate = _num(fred, "ECB_DEPOSIT_RATE")
    ecb_deposit_delta = _delta(fred, "ECB_DEPOSIT_RATE")
    us_minus_ecb_bps = (
        (dff - ecb_deposit_rate) * 100.0
        if dff is not None and ecb_deposit_rate is not None
        else None
    )

    uk_bank_rate = _num(fred, "UK_BANK_RATE")
    uk_bank_rate_previous = _num(fred, "UK_BANK_RATE_PREVIOUS")
    us_minus_uk_bps = (
        (dff - uk_bank_rate) * 100.0
        if dff is not None and uk_bank_rate is not None
        else None
    )

    ca_policy_rate = _num(fred, "CA_POLICY_RATE")
    ca_policy_rate_previous = _num(fred, "CA_POLICY_RATE_PREVIOUS")
    us_minus_ca_bps = (
        (dff - ca_policy_rate) * 100.0
        if dff is not None and ca_policy_rate is not None
        else None
    )

    manufacturing_pmi = _num(fred, "ISM_MANUFACTURING_PMI")
    manufacturing_pmi_delta = _delta(fred, "ISM_MANUFACTURING_PMI")
    services_activity = _num(fred, "ISM_SERVICES_ACTIVITY")
    services_activity_delta = _delta(fred, "ISM_SERVICES_ACTIVITY")
    manufacturing_state = _pmi_state(manufacturing_pmi, manufacturing_pmi_delta)
    services_state = _pmi_state(services_activity, services_activity_delta)
    if manufacturing_state == "UNAVAILABLE" and services_state == "UNAVAILABLE":
        pmi_signal = "UNAVAILABLE"
    elif manufacturing_state.startswith("EXPANDING") and services_state.startswith("EXPANDING"):
        pmi_signal = "BROAD_EXPANSION"
    elif manufacturing_state.startswith("CONTRACTING") and services_state.startswith("CONTRACTING"):
        pmi_signal = "BROAD_CONTRACTION"
    else:
        pmi_signal = "MIXED"

    return {
        "status": "COMPLETE",
        "methodology_version": "economic-panel-v2",
        "point_in_time_vintage_end": fred.get("data_quality", {}).get("vintage_end"),
        "freshness_days": ages,
        "inflation_regime": {
            "signal": inflation_signal,
            "cpi_yoy_pct": _num(fred, "CPI_YOY"),
            "core_cpi_yoy_pct": _num(fred, "CORE_CPI_YOY"),
            "pce_yoy_pct": _num(fred, "PCE_YOY"),
            "core_pce_yoy_pct": _num(fred, "CORE_PCE_YOY"),
            "deltas_pp_4w": inflation_delta,
            "directions": inflation_directions,
            "cross_measure_confirmation": len(set(non_unknown_infl)) == 1 if non_unknown_infl else False,
        },
        "labor_regime": {
            "signal": labor_regime,
            "payems_change_thousand_4w": payroll_change,
            "unemployment_change_pp_4w": unemployment_change,
            "wage_growth_yoy_pct": _num(fred, "AHE_YOY"),
            "wage_growth_change_pp_4w": wage_change_pp,
            "initial_claims_k": _num(fred, "ICSA"),
            "initial_claims_change_k_4w": claims_change,
        },
        "growth_regime": {
            "signal": growth_regime,
            "real_gdp_qoq_saar_pct": gdp_growth,
            "industrial_production_change_pct_4w": industrial_change,
            "retail_sales_change_pct_4w": retail_change,
        },
        "pmi_regime": {
            "signal": pmi_signal,
            "manufacturing_pmi": manufacturing_pmi,
            "manufacturing_pmi_change_4w": manufacturing_pmi_delta,
            "manufacturing_state": manufacturing_state,
            "services_business_activity": services_activity,
            "services_business_activity_change_4w": services_activity_delta,
            "services_state": services_state,
            "services_measure_note": (
                "ISM series discontinued on FRED; marked UNAVAILABLE (no synthetic data injected)."
                if pmi_signal == "UNAVAILABLE"
                else "NMFBAI is the ISM Non-Manufacturing Business Activity Index, used as a services-sector activity proxy; no synthetic headline Services PMI is constructed."
            ),
        },
        "rate_curve_regime": {
            "dgs3mo_pct": three_month,
            "dgs2_pct": two_year,
            "dgs5_pct": five_year,
            "dgs10_pct": ten_year,
            "dgs30_pct": thirty_year,
            "two_ten_spread_bps": None if two_ten_spread is None else two_ten_spread * 100.0,
            "three_ten_spread_bps": None if three_ten_spread is None else three_ten_spread * 100.0,
            "two_ten_change_bps_4w": None if two_ten_delta is None else two_ten_delta * 100.0,
            "three_ten_change_bps_4w": None if three_ten_delta is None else three_ten_delta * 100.0,
            "curve_move": curve_move,
            "two_ten_inverted": bool(two_ten_spread is not None and two_ten_spread < 0.0),
            "three_ten_inverted": bool(three_ten_spread is not None and three_ten_spread < 0.0),
            "two_year_minus_dff_bps": policy_gap_bps,
        },
        "canada_policy": {
            "status": "COMPLETE" if ca_policy_rate is not None else "UNAVAILABLE",
            "policy_rate_pct": ca_policy_rate,
            "previous_policy_rate_pct": ca_policy_rate_previous,
            "us_minus_ca_policy_spread_bps": us_minus_ca_bps,
            "source": fred.get("data_quality", {}).get("ca_policy_rate", {}).get(
                "source", "Bank of Canada official Target for the overnight rate (V39079)"
            ),
            "observation_date": fred.get("CA_POLICY_RATE_SOURCE_DATE"),
            "pit_note": fred.get("data_quality", {}).get("ca_policy_rate", {}).get("pit_rule"),
        },
        "uk_policy": {
            "status": "COMPLETE" if uk_bank_rate is not None else "UNAVAILABLE",
            "bank_rate_pct": uk_bank_rate,
            "previous_bank_rate_pct": uk_bank_rate_previous,
            "us_minus_uk_policy_spread_bps": us_minus_uk_bps,
            "source": fred.get("data_quality", {}).get("uk_bank_rate", {}).get(
                "source", "Bank of England official Bank Rate (YWMB47D)"
            ),
            "observation_date": fred.get("UK_BANK_RATE_SOURCE_DATE"),
            "pit_note": fred.get("data_quality", {}).get("uk_bank_rate", {}).get("pit_rule"),
        },
        "euro_area_macro": {
            "status": "COMPLETE" if ea_hicp is not None and ecb_deposit_rate is not None else "PARTIAL",
            "hicp_yoy_pct": ea_hicp,
            "hicp_change_pp_4w": ea_hicp_delta,
            "hicp_direction": (
                "RISING" if ea_hicp_delta is not None and ea_hicp_delta >= 0.10
                else "FALLING" if ea_hicp_delta is not None and ea_hicp_delta <= -0.10
                else "STABLE" if ea_hicp_delta is not None
                else "UNAVAILABLE"
            ),
            "ecb_deposit_rate_pct": ecb_deposit_rate,
            "ecb_deposit_rate_change_pp_4w": ecb_deposit_delta,
            "us_minus_ecb_policy_spread_bps": us_minus_ecb_bps,
            "source_note": "Euro-area HICP from Eurostat via FRED; ECB Deposit Facility Rate from ECB via FRED.",
        },
        "policy_regime": {
            "dff_pct": dff,
            "sofr_pct": sofr,
            "sofr_minus_dff_bps": sofr_gap_bps,
            "two_year_minus_dff_bps": policy_gap_bps,
            "market_vs_policy": (
                "NEAR_POLICY" if policy_gap_bps is None or abs(policy_gap_bps) < 25.0
                else "MARKET_PRICES_LOWER_POLICY_PATH" if policy_gap_bps < 0.0
                else "MARKET_PRICES_HIGHER_POLICY_PATH"
            ),
            "money_market_note": "SOFR is the secured overnight benchmark and is treated as a money-market anchor, not as a forward OIS curve.",
            "fed_funds_futures": _fed_futures_panel(market_data, dff),
        },
        "interpretation_guardrails": {
            "no_composite_score": True,
            "no_causal_claim": True,
            "no_market_trade_signal": True,
            "note": "Dimensions are reported separately; aggregation into an execution decision remains downstream and deterministic.",
        },
    }
