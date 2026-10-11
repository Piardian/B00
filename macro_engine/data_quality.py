from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional


class DataUnavailableError(RuntimeError):
    """Required macro input is unavailable; never substitute synthetic market data."""


REQUIRED_MARKET_FIELDS = {
    "DXY", "GOLD", "BRENT", "US10Y", "US02Y", "BTC", "COPPER", "VIX",
    "HYG", "LQD",
}

RELATIVE_VALUE_MARKET_FIELDS = {
    "CA02Y", "DE02Y", "GB02Y", "AU02Y", "NZ02Y",
}

OPTIONAL_MARKET_FIELDS = {
    "IRON_ORE", "DAIRY_GDT", "SPX", "WTI", "FED_FUNDS_FUTURES", "SOL",
}

REQUIRED_FRED_FIELDS = {
    "WALCL", "WALCL_4W_AGO", "RRPONTSYD", "RRPONTSYD_4W_AGO",
    "WTREGEN", "WTREGEN_4W_AGO", "T10YIE", "DFII10", "DFF", "SOFR",
    "BAMLH0A0HYM2", "NFCI", "ICSA", "DE10Y", "DE10Y_4W_AGO",
}

# Extended economic regime panel. These are kept separate from the legacy
# liquidity/credit contract so old fixtures remain valid while live ingestion
# can fail closed when the new panel itself is requested.
REQUIRED_ECONOMIC_FRED_FIELDS = {
    "CPI_YOY", "CORE_CPI_YOY", "PCE_YOY", "CORE_PCE_YOY",
    "PAYEMS", "UNRATE", "AHE_YOY",
    "GDP_QOQ_SAAR", "INDPRO", "RSAFS",
    "DGS3MO", "DGS2", "DGS5", "DGS10", "DGS30",
    "T10Y2Y", "T10Y3M", "SOFR",
}

# ISM discontinued public redistribution of NAPM/NMFBAI on FRED.
# Kept optional with explicit UNAVAILABLE status unless an authorized proxy is configured.
OPTIONAL_ECONOMIC_FRED_FIELDS = {
    "ISM_MANUFACTURING_PMI", "ISM_SERVICES_ACTIVITY",
}


def _validate_present_market_fields(payload: Dict[str, Any]) -> None:
    for name, data in payload.items():
        if name in OPTIONAL_MARKET_FIELDS or name in REQUIRED_MARKET_FIELDS:
            if not isinstance(data, dict) or data.get("value") is None:
                raise DataUnavailableError(f"Invalid market payload for {name}")


def _validate_present_fred_fields(payload: Dict[str, Any]) -> None:
    for name, value in payload.items():
        if name in REQUIRED_FRED_FIELDS and value is None:
            raise DataUnavailableError(f"Invalid FRED payload for {name}")


def validate_market_payload(
    payload: Dict[str, Any],
    required_fields: Optional[Iterable[str]] = None,
) -> None:
    """Validate present structure, optionally enforcing a complete runtime field set."""
    if not isinstance(payload, dict):
        raise DataUnavailableError("Market payload must be a dictionary")
    _validate_present_market_fields(payload)
    if required_fields is None:
        return
    required = set(required_fields)
    missing = sorted(name for name in required if name not in payload)
    if missing:
        raise DataUnavailableError("Required market data unavailable: " + ", ".join(missing))
    for name in required:
        data = payload[name]
        if not isinstance(data, dict) or data.get("value") is None:
            raise DataUnavailableError(f"Invalid market payload for {name}")


def validate_fred_payload(
    payload: Dict[str, Any],
    required_fields: Optional[Iterable[str]] = None,
) -> None:
    """Validate present structure, optionally enforcing a complete runtime field set."""
    if not isinstance(payload, dict):
        raise DataUnavailableError("FRED payload must be a dictionary")
    _validate_present_fred_fields(payload)
    if required_fields is None:
        return
    required = set(required_fields)
    missing = sorted(name for name in required if name not in payload)
    if missing:
        raise DataUnavailableError("Required FRED data unavailable: " + ", ".join(missing))
    for name in required:
        value = payload[name]
        if value is None:
            raise DataUnavailableError(f"Invalid FRED payload for {name}")


def validate_finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise DataUnavailableError(f"Non-finite/non-numeric value for {name}: {value!r}")
    return float(value)


def validate_numeric_range(name: str, value: Any, minimum: float, maximum: float) -> float:
    numeric = validate_finite_number(name, value)
    if not minimum <= numeric <= maximum:
        raise DataUnavailableError(
            f"Out-of-range value for {name}: {numeric}; expected [{minimum}, {maximum}]"
        )
    return numeric
