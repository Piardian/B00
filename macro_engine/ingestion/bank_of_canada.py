from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from data_quality import DataUnavailableError


class BankOfCanadaDataIngestion:
    """Official Bank of Canada policy-rate ingestion via the Valet API."""

    SERIES_CODE = "V39079"
    YIELD_2Y_SERIES_CODE = "BD.CDN.2YR.DQ.YLD"
    ENDPOINT = "https://www.bankofcanada.ca/valet/observations"

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    @staticmethod
    def _extract_rows(payload: Any, series_code: str = "V39079") -> list[tuple[dt.date, float]]:
        observations = payload.get("observations", []) if isinstance(payload, dict) else []
        rows: list[tuple[dt.date, float]] = []
        for item in observations:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("d") or item.get("date")
            series = item.get(series_code, {})
            raw_value = (
                series.get("v")
                if isinstance(series, dict)
                else series
            )
            try:
                date = dt.date.fromisoformat(str(raw_date))
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            rows.append((date, value))
        return rows

    def fetch_policy_rate(
        self,
        as_of: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or dt.datetime.now(dt.timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of = as_of.astimezone(dt.timezone.utc)

        params = {
            "start_date": "2000-01-01",
            "end_date": as_of.date().isoformat(),
        }
        url = (
            f"{self.ENDPOINT}/{self.SERIES_CODE}/json?"
            + urllib.parse.urlencode(params)
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BegonyaMacroEngine/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise DataUnavailableError(
                f"Bank of Canada policy-rate request failed: {exc}"
            ) from None

        rows = self._extract_rows(payload)
        completed = [row for row in rows if row[0] < as_of.date()]
        if not completed:
            raise DataUnavailableError(
                f"No Bank of Canada policy-rate observation before {as_of.date().isoformat()}"
            )

        observation_date, value = completed[-1]
        previous_rows = [row for row in completed if row[0] < observation_date]
        previous_value = previous_rows[-1][1] if previous_rows else value

        return {
            "value": round(value, 4),
            "previous_value": round(previous_value, 4),
            "change_pp": round(value - previous_value, 4),
            "observation_date": observation_date.isoformat(),
            "source": "Bank of Canada official Target for the overnight rate (V39079)",
            "pit_rule": "latest daily observation strictly before replay calendar day",
            "status": "AVAILABLE",
        }

    def fetch_2y_yield(
        self,
        as_of: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or dt.datetime.now(dt.timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of = as_of.astimezone(dt.timezone.utc)

        params = {
            "recent": "60",
        }
        url = (
            f"{self.ENDPOINT}/{self.YIELD_2Y_SERIES_CODE}/json?"
            + urllib.parse.urlencode(params)
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BegonyaMacroEngine/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise DataUnavailableError(
                f"Bank of Canada 2Y yield request failed: {exc}"
            ) from None

        rows = self._extract_rows(payload, series_code=self.YIELD_2Y_SERIES_CODE)
        completed = [row for row in rows if row[0] <= as_of.date()]
        if not completed:
            raise DataUnavailableError(
                f"No Bank of Canada 2Y yield observation available for {as_of.date().isoformat()}"
            )

        observation_date, value = completed[-1]
        prev_val = completed[-2][1] if len(completed) >= 2 else value
        val_5d_ago = completed[-6][1] if len(completed) >= 6 else completed[0][1]
        month_ago_val = completed[-21][1] if len(completed) >= 21 else completed[0][1]

        pct_change_daily = round(((value - prev_val) / prev_val) * 100, 2) if prev_val else 0.0
        pct_change_5d = round(((value - val_5d_ago) / val_5d_ago) * 100, 2) if val_5d_ago else 0.0
        pct_change_4w = round(((value - month_ago_val) / month_ago_val) * 100, 2) if month_ago_val else 0.0

        history_close = [r[1] for r in completed]
        pct_rank_60d = round((sum(1 for x in history_close if x <= value) / len(history_close)) * 100, 1) if history_close else 50.0

        return {
            "value": round(value, 4),
            "prev": round(prev_val, 4),
            "val_5d_ago": round(val_5d_ago, 4),
            "month_ago": round(month_ago_val, 4),
            "change_pct": pct_change_daily,
            "change_pct_5d": pct_change_5d,
            "change_pct_4w": pct_change_4w,
            "pct_rank_60d": pct_rank_60d,
            "history_close": history_close,
            "source": f"Bank of Canada Valet API ({self.YIELD_2Y_SERIES_CODE})",
            "observation_date": observation_date.isoformat(),
            "status": "AVAILABLE",
            "fallback_used": False,
        }
