from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from config import FRED_API_KEY
from data_quality import DataUnavailableError

logger = logging.getLogger("InternationalRatesIngestion")


class InternationalRatesDataIngestion:
    """Official Reserve Bank of Australia (RBA) and Reserve Bank of New Zealand (RBNZ)
    sovereign interest rate ingestion via FRED authoritative national source series."""

    AU_SERIES = "IRSTCI01AUM156N"  # Immediate Rates: Less than 24 Hours: Central Bank Policy Rate for Australia
    NZ_SERIES = "IR3TIB01NZM156N"  # Interest Rates: 3-Month or 90-Day Rates and Yields: Interbank Rates for New Zealand

    def __init__(self, api_key: Optional[str] = None, timeout: int = 10):
        self.api_key = api_key if api_key is not None else FRED_API_KEY
        self.timeout = timeout

    def _fetch_series_observations(
        self,
        series_id: str,
        as_of: Optional[dt.datetime] = None,
        limit: int = 60,
    ) -> List[Tuple[dt.date, float]]:
        if not self.api_key:
            raise DataUnavailableError("FRED_API_KEY is not configured")

        as_of = as_of or dt.datetime.now(dt.timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of_date = as_of.date()

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
        url = (
            "https://api.stlouisfed.org/fred/series/observations?"
            + urllib.parse.urlencode(params)
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BegonyaMacroEngine/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise DataUnavailableError(
                f"FRED international rate request failed for {series_id}: {exc}"
            ) from None

        rows: List[Tuple[dt.date, float]] = []
        for obs in body.get("observations", []):
            raw_value = obs.get("value")
            if raw_value in (None, "", "."):
                continue
            try:
                value = float(raw_value)
                date = dt.date.fromisoformat(obs["date"])
                if date <= as_of_date:
                    rows.append((date, value))
            except (KeyError, TypeError, ValueError):
                continue

        if not rows:
            raise DataUnavailableError(
                f"No usable observation for {series_id} on or before {as_of_date.isoformat()}"
            )

        rows.sort(key=lambda x: x[0])
        return rows

    def _build_yield_payload(
        self,
        series_id: str,
        label: str,
        as_of: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        rows = self._fetch_series_observations(series_id, as_of=as_of, limit=60)
        closes = [v for _, v in rows]

        current_val = closes[-1]
        prev_val = closes[-2] if len(closes) > 1 else current_val
        val_5d_ago = closes[-6] if len(closes) >= 6 else closes[0]
        month_ago_val = closes[-21] if len(closes) >= 21 else closes[0]

        pct_change_daily = round(((current_val - prev_val) / prev_val) * 100, 2) if prev_val else 0.0
        pct_change_5d = round(((current_val - val_5d_ago) / val_5d_ago) * 100, 2) if val_5d_ago else 0.0
        pct_change_4w = round(((current_val - month_ago_val) / month_ago_val) * 100, 2) if month_ago_val else 0.0

        window_60d = closes[-60:]
        pct_rank_60d = round((sum(1 for x in window_60d if x <= current_val) / len(window_60d)) * 100, 1)

        return {
            "value": round(current_val, 4),
            "prev": round(prev_val, 4),
            "val_5d_ago": round(val_5d_ago, 4),
            "month_ago": round(month_ago_val, 4),
            "change_pct": pct_change_daily,
            "change_pct_5d": pct_change_5d,
            "change_pct_4w": pct_change_4w,
            "pct_rank_60d": pct_rank_60d,
            "history_close": closes,
            "source": f"FRED {label} ({series_id})",
            "fallback_used": False,
        }

    def fetch_au_yield(self, as_of: Optional[dt.datetime] = None) -> Dict[str, Any]:
        """Fetch Australian sovereign cash / short-term benchmark rate."""
        return self._build_yield_payload(self.AU_SERIES, "RBA Cash Rate", as_of=as_of)

    def fetch_nz_yield(self, as_of: Optional[dt.datetime] = None) -> Dict[str, Any]:
        """Fetch New Zealand sovereign short-term / interbank benchmark rate."""
        return self._build_yield_payload(self.NZ_SERIES, "RBNZ Interbank Rate", as_of=as_of)
