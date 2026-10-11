from __future__ import annotations

import csv
import datetime as dt
import io
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from data_quality import DataUnavailableError


class BankOfEnglandDataIngestion:
    """Official Bank Rate ingestion from the Bank of England database."""

    SERIES_CODE = "YWMB47D"
    ENDPOINT = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    @staticmethod
    def _parse_date(raw: str) -> Optional[dt.date]:
        raw = str(raw).strip()
        for fmt in ("%d %b %Y", "%d %b %y", "%d/%b/%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def _parse_csv(cls, payload: str) -> list[tuple[dt.date, float]]:
        rows: list[tuple[dt.date, float]] = []
        reader = csv.reader(io.StringIO(payload))
        for row in reader:
            if len(row) < 2:
                continue
            date_value = cls._parse_date(row[0])
            if date_value is None:
                continue
            try:
                rate = float(str(row[1]).strip())
            except (TypeError, ValueError):
                continue
            rows.append((date_value, rate))
        return rows

    def fetch_bank_rate(
        self,
        as_of: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        """Return the latest official Bank Rate known strictly before the replay day.

        The source records rate-change dates, not intraday decision timestamps.
        Therefore an intraday replay never applies a rate change occurring later
        on the same calendar day.
        """
        as_of = as_of or dt.datetime.now(dt.timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of = as_of.astimezone(dt.timezone.utc)

        end_date = as_of.date()
        params = {
            "csv.x": "yes",
            "Datefrom": "01/Jan/2000",
            "Dateto": end_date.strftime("%d/%b/%Y"),
            "SeriesCodes": self.SERIES_CODE,
            "CSVF": "TN",
            "UsingCodes": "Y",
            "VPD": "Y",
        }
        url = self.ENDPOINT + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BegonyaMacroEngine/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8-sig", errors="replace")
        except Exception as exc:
            raise DataUnavailableError(
                f"Bank of England Bank Rate request failed: {exc}"
            ) from None

        rows = self._parse_csv(body)
        completed = [row for row in rows if row[0] < as_of.date()]
        if not completed:
            raise DataUnavailableError(
                f"No Bank Rate observation available before {as_of.date().isoformat()}"
            )

        change_date, rate = completed[-1]
        previous_rows = [row for row in completed if row[0] < change_date]
        previous_rate = previous_rows[-1][1] if previous_rows else rate

        return {
            "value": round(rate, 4),
            "previous_value": round(previous_rate, 4),
            "change_pp": round(rate - previous_rate, 4),
            "observation_date": change_date.isoformat(),
            "source": "Bank of England official Bank Rate (YWMB47D)",
            "pit_rule": "latest rate-change date strictly before replay calendar day",
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

        start_date = as_of.date() - dt.timedelta(days=90)
        params = {
            "csv.x": "yes",
            "Datefrom": start_date.strftime("%d/%b/%Y"),
            "Dateto": as_of.date().strftime("%d/%b/%Y"),
            "SeriesCodes": "IUDMNZC",
            "CSVF": "TN",
            "UsingCodes": "Y",
            "VPD": "Y",
        }
        url = self.ENDPOINT + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BegonyaMacroEngine/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8-sig", errors="replace")
        except Exception as exc:
            raise DataUnavailableError(
                f"Bank of England 2Y yield request failed: {exc}"
            ) from None

        rows = self._parse_csv(body)
        completed = [row for row in rows if row[0] <= as_of.date()]
        if not completed:
            raise DataUnavailableError(
                f"No Bank of England 2Y yield observation available for {as_of.date().isoformat()}"
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
            "source": "Bank of England official 2Y Gilt yield (IUDMNZC)",
            "observation_date": observation_date.isoformat(),
            "status": "AVAILABLE",
            "fallback_used": False,
        }
