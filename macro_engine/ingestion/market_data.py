from __future__ import annotations

from typing import Any, Dict

from data_quality import (
    DataUnavailableError,
    REQUIRED_MARKET_FIELDS,
    RELATIVE_VALUE_MARKET_FIELDS,
    validate_market_payload,
)
from ingestion.market_data_legacy import MarketDataIngestion as _LegacyMarketDataIngestion


class MarketDataIngestion(_LegacyMarketDataIngestion):
    """Market ingestion that fails closed instead of substituting fixed prices."""

    def _get_fallback_price(self, name: str) -> Dict[str, Any]:
        # Core macro inputs must never fall back to fixed values.
        # Relative-value feeds are optional: their absence is surfaced to the
        # metrics layer, which must not manufacture directional FX gates.
        if name in RELATIVE_VALUE_MARKET_FIELDS:
            return dict(super()._get_fallback_price(name))
        raise DataUnavailableError(
            f"Market data unavailable for {name}; synthetic fallback is disabled."
        )

    def fetch_current_prices(self) -> Dict[str, Any]:
        results = super().fetch_current_prices()

        # Static fallback rows are not evidence. Drop them before the core
        # contract is validated; relative-value consumers will receive an
        # explicit unavailable state instead of a fabricated FX signal.
        for name in RELATIVE_VALUE_MARKET_FIELDS:
            data = results.get(name)
            if isinstance(data, dict) and data.get("fallback_used"):
                results.pop(name, None)

        validate_market_payload(results, required_fields=REQUIRED_MARKET_FIELDS)
        short_hist = sorted(
            f"{name}({len(data.get('history_close', []))})"
            for name, data in results.items()
            if isinstance(data, dict) and name in REQUIRED_MARKET_FIELDS
            and len(data.get("history_close", [])) < 6
        )
        if short_hist:
            raise DataUnavailableError(
                "Insufficient market history for deterministic deltas: " + ", ".join(short_hist)
            )
        return results
