from __future__ import annotations

from typing import Any, Dict, Mapping, Optional



def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _front_fed_funds_future(
    market_data: Optional[Mapping[str, Any]],
    dff: Optional[float],
) -> Dict[str, Any]:
    data = (market_data or {}).get("FED_FUNDS_FUTURES")
    if not isinstance(data, Mapping):
        return {
            "status": "UNAVAILABLE",
            "market_implied_rate_pct": None,
            "vs_dff_bps": None,
            "reprice_1d_bps": None,
            "reprice_5d_bps": None,
            "methodology_warning": "No Fed Funds futures observation supplied; no synthetic rate is substituted.",
        }

    price = _number(data.get("value"))
    if price is None:
        return {
            "status": "UNAVAILABLE",
            "market_implied_rate_pct": None,
            "vs_dff_bps": None,
            "reprice_1d_bps": None,
            "reprice_5d_bps": None,
            "methodology_warning": "Fed Funds futures price is missing/non-numeric.",
        }

    implied_rate = 100.0 - price
    previous_price = _number(data.get("prev"))
    five_day_price = _number(data.get("val_5d_ago"))
    previous_rate = 100.0 - previous_price if previous_price is not None else None
    five_day_rate = 100.0 - five_day_price if five_day_price is not None else None

    return {
        "status": "AVAILABLE",
        "source": data.get("source") or "caller-supplied 30-Day Fed Funds Futures (e.g. CME/ZQ=F)",
        "contract": data.get("contract_month") or data.get("contract"),
        "contract_price": round(price, 6),
        "market_implied_rate_pct": round(implied_rate, 6),
        "vs_dff_bps": None if dff is None else round((implied_rate - dff) * 100.0, 1),
        "reprice_1d_bps": None if previous_rate is None else round((implied_rate - previous_rate) * 100.0, 1),
        "reprice_5d_bps": None if five_day_rate is None else round((implied_rate - five_day_rate) * 100.0, 1),
        "methodology_note": "30-Day Fed Funds futures price is converted deterministically as 100 minus price. A front contract is an implied average policy rate for its delivery month, not a full meeting-probability curve.",
    }


def _fed_funds_futures_curve(
    market_data: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    raw = (market_data or {}).get("FED_FUNDS_FUTURES_CURVE")
    if raw is None:
        return {
            "status": "UNAVAILABLE",
            "contracts": [],
            "methodology_warning": "No multi-contract Fed Funds futures curve supplied.",
        }

    if isinstance(raw, Mapping):
        iterable = [dict(contract=str(k), price=v) for k, v in raw.items()]
    elif isinstance(raw, list):
        iterable = [item for item in raw if isinstance(item, Mapping)]
    else:
        return {
            "status": "UNAVAILABLE",
            "contracts": [],
            "methodology_warning": "Fed Funds futures curve must be a mapping or list of contract rows.",
        }

    rows = []
    for item in iterable:
        contract = item.get("contract_month") or item.get("contract")
        price = _number(item.get("price"))
        if not contract or price is None:
            continue
        implied_rate = 100.0 - price
        rows.append(
            {
                "contract": str(contract),
                "price": round(price, 6),
                "implied_rate_pct": round(implied_rate, 6),
            }
        )

    rows.sort(key=lambda row: row["contract"])
    if not rows:
        return {
            "status": "UNAVAILABLE",
            "contracts": [],
            "methodology_warning": "No valid contract rows in Fed Funds futures curve.",
        }

    return {
        "status": "AVAILABLE",
        "contracts": rows,
        "methodology_note": "Each contract is converted as 100 minus price. The curve describes market-implied average Fed Funds rates by delivery month; it is not converted into meeting probabilities.",
    }


def _usd_ois_curve(market_data: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    raw = (market_data or {}).get("USD_OIS_CURVE")
    if raw is None:
        return {
            "status": "UNAVAILABLE",
            "tenors": [],
            "methodology_warning": "No provider-backed USD OIS forward curve supplied; no synthetic OIS curve is constructed.",
        }

    if isinstance(raw, Mapping):
        iterable = [dict(tenor=str(k), rate=v) for k, v in raw.items()]
    elif isinstance(raw, list):
        iterable = [item for item in raw if isinstance(item, Mapping)]
    else:
        return {
            "status": "UNAVAILABLE",
            "tenors": [],
            "methodology_warning": "USD OIS curve must be a mapping or list of tenor rows.",
        }

    rows = []
    for item in iterable:
        tenor = item.get("tenor")
        rate = _number(item.get("rate"))
        if not tenor or rate is None:
            continue
        rows.append({"tenor": str(tenor), "rate_pct": round(rate, 6)})

    def _tenor_key(t_str: str) -> float:
        t = str(t_str).strip().upper()
        try:
            if t.endswith("D"):
                return float(t[:-1]) / 365.0
            if t.endswith("W"):
                return float(t[:-1]) * 7.0 / 365.0
            if t.endswith("M"):
                return float(t[:-1]) / 12.0
            if t.endswith("Y"):
                return float(t[:-1])
        except ValueError:
            pass
        return 999.0

    rows.sort(key=lambda row: _tenor_key(row["tenor"]))
    if not rows:
        return {
            "status": "UNAVAILABLE",
            "tenors": [],
            "methodology_warning": "No valid tenor rows in USD OIS curve.",
        }

    return {
        "status": "AVAILABLE",
        "tenors": rows,
        "source": (market_data or {}).get("USD_OIS_CURVE_SOURCE", "external provider supplied by caller"),
        "methodology_note": "OIS rates are consumed as provider observations; Begonya does not synthesize a forward OIS curve from Treasury yields or spot SOFR.",
    }


def build_policy_expectations(
    fred: Mapping[str, Any],
    market_data: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a deterministic policy-expectations panel without inventing forward rates."""
    dff = _number(fred.get("DFF"))
    sofr = _number(fred.get("SOFR"))
    front = _front_fed_funds_future(market_data, dff)
    curve = _fed_funds_futures_curve(market_data)
    ois = _usd_ois_curve(market_data)

    return {
        "methodology_version": "policy-expectations-v1",
        "effective_policy_rate": {
            "dff_pct": dff,
            "sofr_pct": sofr,
            "sofr_minus_dff_bps": None if dff is None or sofr is None else round((sofr - dff) * 100.0, 1),
            "source": "FRED DFF + New York Fed SOFR",
        },
        "front_fed_funds_future": front,
        "fed_funds_futures_curve": curve,
        "usd_ois_curve": ois,
        "interpretation_guardrails": {
            "no_meeting_probability_inference": True,
            "no_synthetic_ois": True,
            "no_trade_signal": True,
        },
    }
