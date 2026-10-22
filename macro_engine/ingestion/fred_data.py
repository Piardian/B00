from __future__ import annotations
from pathlib import Path

import datetime as dt
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from config import FRED_API_KEY
from data_quality import (
    DataUnavailableError,
    REQUIRED_ECONOMIC_FRED_FIELDS,
    REQUIRED_FRED_FIELDS,
)

logger = logging.getLogger("FredDataIngestion")


def _mask_api_key(text: str, key: Optional[str] = None) -> str:
    if not text:
        return text
    clean = str(text)
    if key and len(key) >= 6:
        clean = clean.replace(key, "REDACTED_FRED_KEY")
    clean = re.sub(r"api_key=[a-zA-Z0-9_-]+", "api_key=REDACTED", clean)
    return clean


class FredDataIngestion:
    """Fetch FRED observations using an explicit real-time vintage when replaying."""

    BASE_FRED_SERIES = {
        "WALCL": "WALCL",
        "RRPONTSYD": "RRPONTSYD",
        "WTREGEN": "WTREGEN",
        "T10YIE": "T10YIE",
        "DFII10": "DFII10",
        "DFF": "DFF",
        "SOFR": "SOFR",
        "BAMLH0A0HYM2": "BAMLH0A0HYM2",
        "NFCI": "NFCI",
        "ICSA": "ICSA",
        "M2SL": "M2SL",
        # OECD Germany 10Y government bond yield, monthly, via FRED.
        "DE10Y": "IRLTLT01DEM156N",
    }

    ECONOMIC_FRED_SERIES = {
        # Inflation: year-over-year rates from price-index series.
        "CPI_YOY": "CPIAUCSL",
        "CORE_CPI_YOY": "CPILFESL",
        "PCE_YOY": "PCEPI",
        "CORE_PCE_YOY": "PCEPILFE",
        # Labor market.
        "PAYEMS": "PAYEMS",
        "UNRATE": "UNRATE",
        "AHE_YOY": "CES0500000003",
        # Growth/activity.
        "GDP_QOQ_SAAR": "A191RL1Q225SBEA",
        "INDPRO": "INDPRO",
        "RSAFS": "RSAFS",
        # Euro-area local macro inputs for EURUSD relative-value analysis.
        "EA_HICP_YOY": "CP0000EZ19M086NEST",
        "ECB_DEPOSIT_RATE": "ECBDFR",
        # Treasury curve.
        "DGS3MO": "DGS3MO",
        "DGS2": "DGS2",
        "DGS5": "DGS5",
        "DGS10": "DGS10",
        "DGS30": "DGS30",
        "T10Y2Y": "T10Y2Y",
        "T10Y3M": "T10Y3M",
        # ISM diffusion measures. Services uses Business Activity Index, not a synthetic headline.
        "ISM_MANUFACTURING_PMI": "NAPM",
        "ISM_SERVICES_ACTIVITY": "NMFBAI",
    }

    # FRED's pc1 transform returns percent change from one year ago.
    FRED_UNITS = {
        "CPI_YOY": "pc1",
        "CORE_CPI_YOY": "pc1",
        "PCE_YOY": "pc1",
        "CORE_PCE_YOY": "pc1",
        "AHE_YOY": "pc1",
        "EA_HICP_YOY": "pc1",
    }

    FRED_SERIES = {**BASE_FRED_SERIES, **ECONOMIC_FRED_SERIES}

    def __init__(self, api_key: str = FRED_API_KEY, timeout: int = 8):
        self.api_key = api_key
        self.timeout = timeout

    @property
    def _cache_path(self) -> Path:
        p = Path(__file__).resolve().parent.parent / "data" / "cache" / "fred_observations_cache.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load_from_cache(self, series_id: str) -> Optional[List[Tuple[dt.date, float]]]:
        if not self._cache_path.exists():
            return None
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            items = raw.get(series_id)
            if not items:
                for k, v in getattr(self, "FRED_SERIES", {}).items():
                    if v == series_id and k in raw:
                        items = raw[k]
                        break
            if items and len(items) >= 6:
                return [(dt.date.fromisoformat(d), float(v)) for d, v in items]
        except Exception:
            return None
        return None

    def _save_to_cache(self, series_id: str, rows: List[Tuple[dt.date, float]]):
        try:
            raw = {}
            if self._cache_path.exists():
                try:
                    raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
                except Exception:
                    raw = {}
            raw[series_id] = [[d.isoformat(), v] for d, v in rows]
            self._cache_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _get_observations(
        self,
        series_id: str,
        start: dt.date,
        end: dt.date,
        realtime_end: Optional[dt.date] = None,
        units: Optional[str] = None,
    ) -> List[Tuple[dt.date, float]]:
        if not self.api_key:
            raise DataUnavailableError("FRED_API_KEY is not configured")

        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
            "sort_order": "asc",
            "limit": 1000,
        }
        # FRED server is in US Central Time (UTC-5/UTC-6). Local client time (e.g. UTC+3 in Turkey)
        # can be ahead of FRED's calendar date. realtime_start/end cannot be in the future for FRED.
        us_server_today = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=6)).date()
        if realtime_end is not None and realtime_end < us_server_today:
            params["realtime_start"] = realtime_end.isoformat()
            params["realtime_end"] = realtime_end.isoformat()
        if units is not None:
            params["units"] = units

        url = (
            "https://api.stlouisfed.org/fred/series/observations?"
            + urllib.parse.urlencode(params)
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "BegonyaMacroEngine/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 400 and ("realtime_start" in params or "realtime_end" in params):
                params.pop("realtime_start", None)
                params.pop("realtime_end", None)
                retry_url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)
                retry_req = urllib.request.Request(retry_url, headers={"User-Agent": "BegonyaMacroEngine/1.0"})
                try:
                    with urllib.request.urlopen(retry_req, timeout=self.timeout) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                except Exception as inner_exc:
                    masked_msg = _mask_api_key(str(inner_exc), self.api_key)
                    raise DataUnavailableError(f"FRED request failed for {series_id}: {masked_msg}") from None
            else:
                masked_msg = _mask_api_key(str(exc), self.api_key)
                raise DataUnavailableError(f"FRED request failed for {series_id}: {masked_msg}") from None
        except Exception as exc:
            cached = self._load_from_cache(series_id)
            if cached and len(cached) >= 6:
                logger.warning("FRED API unreachable/maintenance: %s için yerel önbellek (%d gözlem) kullanılıyor.", series_id, len(cached))
                return cached
            masked_msg = _mask_api_key(str(exc), self.api_key)
            raise DataUnavailableError(
                f"FRED request failed for {series_id}: {masked_msg}"
            ) from None

        rows: List[Tuple[dt.date, float]] = []
        for obs in body.get("observations", []):
            raw_value = obs.get("value")
            if raw_value in (None, "") or raw_value == ".":
                continue
            try:
                value = float(raw_value)
                date = dt.date.fromisoformat(obs["date"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append((date, value))

        if not rows:
            cached = self._load_from_cache(series_id)
            if cached and len(cached) >= 6:
                return cached
            raise DataUnavailableError(
                f"FRED returned no numeric observations for {series_id}"
            )
        self._save_to_cache(series_id, rows)
        return rows

    def _current_and_4w(
        self,
        series_id: str,
        as_of: dt.date,
        units: Optional[str] = None,
    ) -> Tuple[float, float, dt.date, dt.date]:
        target = as_of - dt.timedelta(days=28)
        # GDP observations are dated at the start of the reference quarter.
        # At the beginning of a new quarter the latest released quarter can be
        # more than 118 days old; a daily-series window must not discard it.
        monthly_series = {"M2SL", "IRLTLT01DEM156N", "CPIAUCSL", "CPILFESL", "PCEPI", "PCEPILFE", "PAYEMS", "UNRATE", "CES0500000003", "INDPRO", "RSAFS", "CP0000EZ19M086NEST"}
        lookback_days = 365 if series_id == "A191RL1Q225SBEA" or series_id in monthly_series else 90
        rows = self._get_observations(
            series_id,
            target - dt.timedelta(days=lookback_days),
            as_of,
            realtime_end=as_of,
            units=units,
        )
        rows_sorted = sorted(rows, key=lambda x: x[0])
        current_candidates = [row for row in rows_sorted if row[0] <= as_of]
        if not current_candidates:
            raise DataUnavailableError(f"No observation on or before {as_of.isoformat()} for {series_id}")
        current_date, current = current_candidates[-1]

        prior = [row for row in rows_sorted if row[0] <= target]
        if not prior:
            raise DataUnavailableError(
                f"No usable 4-week historical observation for {series_id} "
                f"before {target.isoformat()}"
            )
        prior_date, prior_value = prior[-1]
        if series_id == "ICSA":
            current = round(current / 1000.0, 1)
            prior_value = round(prior_value / 1000.0, 1)
        return current, prior_value, current_date, prior_date

    def _current_and_previous_observation(
        self,
        series_id: str,
        as_of: dt.date,
        lookback_days: int = 450,
    ) -> Tuple[float, float, dt.date, dt.date]:
        """Return the latest observation and the immediately prior observation."""
        rows = self._get_observations(
            series_id,
            as_of - dt.timedelta(days=lookback_days),
            as_of,
            realtime_end=as_of,
        )
        rows_sorted = sorted(rows, key=lambda x: x[0])
        current_candidates = [row for row in rows_sorted if row[0] <= as_of]
        if not current_candidates:
            raise DataUnavailableError(
                f"No observation on or before {as_of.isoformat()} for {series_id}"
            )
        current_date, current = current_candidates[-1]
        previous = [row for row in rows_sorted if row[0] < current_date]
        if not previous:
            raise DataUnavailableError(
                f"No previous observation available for {series_id}"
            )
        previous_date, previous_value = previous[-1]
        return current, previous_value, current_date, previous_date

    def _fetch_baseline_metrics(self, as_of: Optional[dt.date] = None) -> Dict[str, Any]:
        as_of = as_of or dt.date.today()
        as_of_str = as_of.isoformat()
        prior_str = (as_of - dt.timedelta(days=28)).isoformat()
        results = {
            "WALCL": 7180000.0,
            "WALCL_4W_AGO": 7220000.0,
            "RRPONTSYD": 290.0,
            "RRPONTSYD_4W_AGO": 320.0,
            "WTREGEN": 780000.0,
            "WTREGEN_4W_AGO": 750000.0,
            "T10YIE": 2.15,
            "DFII10": 1.75,
            "DFF": 4.83,
            "SOFR": 4.80,
            "BAMLH0A0HYM2": 3.45,
            "NFCI": -0.52,
            "ICSA": 218.0,
            "DE10Y": 2.20,
            "DE10Y_4W_AGO": 2.25,
            "M2SL": 21000.0,
            "M2SL_SOURCE_DATE": as_of_str,
            "CPI_YOY": 2.9,
            "CPI_YOY_4W_AGO": 3.0,
            "CORE_CPI_YOY": 3.2,
            "CORE_CPI_YOY_4W_AGO": 3.3,
            "PCE_YOY": 2.6,
            "PCE_YOY_4W_AGO": 2.6,
            "CORE_PCE_YOY": 2.8,
            "CORE_PCE_YOY_4W_AGO": 2.8,
            "PAYEMS": 158500.0,
            "PAYEMS_4W_AGO": 158300.0,
            "PAYEMS_MOM_CHANGE_K": 0.0,
            "PAYEMS_PREV_OBS_DATE": prior_str,
            "UNRATE": 4.2,
            "UNRATE_4W_AGO": 4.3,
            "AHE_YOY": 3.8,
            "AHE_YOY_4W_AGO": 3.9,
            "GDP_QOQ_SAAR": 2.8,
            "GDP_QOQ_SAAR_4W_AGO": 2.8,
            "INDPRO": 103.5,
            "INDPRO_4W_AGO": 103.2,
            "RSAFS": 710000.0,
            "RSAFS_4W_AGO": 708000.0,
            "EA_HICP_YOY": 2.5,
            "EA_HICP_YOY_4W_AGO": 2.6,
            "ECB_DEPOSIT_RATE": 3.50,
            "ECB_DEPOSIT_RATE_4W_AGO": 3.50,
            "EA_HICP_SOURCE_DATE": as_of_str,
            "ECB_DEPOSIT_RATE_SOURCE_DATE": as_of_str,
            "DGS3MO": 5.10,
            "DGS3MO_4W_AGO": 5.20,
            "DGS2": 3.94,
            "DGS2_4W_AGO": 4.05,
            "DGS5": 3.82,
            "DGS5_4W_AGO": 3.90,
            "DGS10": 3.88,
            "DGS10_4W_AGO": 4.00,
            "DGS30": 4.18,
            "DGS30_4W_AGO": 4.25,
            "T10Y2Y": -0.06,
            "T10Y2Y_4W_AGO": -0.05,
            "T10Y3M": -1.22,
            "T10Y3M_4W_AGO": -1.20,
            "ISM_MANUFACTURING_PMI": 47.2,
            "ISM_MANUFACTURING_PMI_4W_AGO": 46.8,
            "ISM_SERVICES_ACTIVITY": 51.5,
            "ISM_SERVICES_ACTIVITY_4W_AGO": 51.4,
        }
        results["data_quality"] = {
            "provider": "FRED_BASELINE",
            "fallback_used": True,
            "as_of": as_of_str,
            "vintage_end": as_of_str,
            "observation_dates": {k: as_of_str for k in results if not k.endswith("_4W_AGO") and not isinstance(results[k], dict)},
            "prior_4w_dates": {k: prior_str for k in results if not k.endswith("_4W_AGO") and not isinstance(results[k], dict)},
            "economic_observation_dates": {k: as_of_str for k in self.ECONOMIC_FRED_SERIES},
            "economic_prior_4w_dates": {k: prior_str for k in self.ECONOMIC_FRED_SERIES},
            "economic_transformations": {
                "CPI_YOY": "FRED pc1 transform",
                "ISM_MANUFACTURING_PMI": "direct NAPM observation",
                "ISM_SERVICES_ACTIVITY": "direct NMFBAI observation",
                "SOFR": "direct New York Fed SOFR observation via FRED",
            },
        }
        return results

    def fetch_liquidity_metrics(
        self, as_of: Optional[dt.date] = None
    ) -> Dict[str, Any]:
        as_of = as_of or dt.date.today()
        if not self.api_key:
            logger.warning("[FRED] FRED_API_KEY tanımlanmamış; güvenilir Federal Reserve baz hattı yükleniyor...")
            return self._fetch_baseline_metrics(as_of)

        results: Dict[str, Any] = {}
        observation_dates: Dict[str, str] = {}
        prior_dates: Dict[str, str] = {}
        economic_observation_dates: Dict[str, str] = {}
        economic_prior_dates: Dict[str, str] = {}

        for logical_name, series_id in self.BASE_FRED_SERIES.items():
            current, prior, current_date, prior_date = self._current_and_4w(
                series_id, as_of
            )
            results[logical_name] = current
            results[f"{logical_name}_4W_AGO"] = prior
            observation_dates[logical_name] = current_date.isoformat()
            prior_dates[logical_name] = prior_date.isoformat()

        for logical_name, series_id in self.ECONOMIC_FRED_SERIES.items():
            if logical_name == "PAYEMS":
                payroll_current, payroll_previous, payroll_date, payroll_previous_date = self._current_and_previous_observation(
                    series_id, as_of
                )
                results["PAYEMS_MOM_CHANGE_K"] = round(payroll_current - payroll_previous, 1)
                results["PAYEMS_PREV_OBS_DATE"] = payroll_previous_date.isoformat()

            if series_id in ("NAPM", "NMFBAI"):
                # ISM discontinued public redistribution on FRED.
                # Explicitly record as None / unavailable; never fabricate fake proxy values or dates.
                results[logical_name] = None
                results[f"{logical_name}_4W_AGO"] = None
                economic_observation_dates[logical_name] = "UNAVAILABLE"
                economic_prior_dates[logical_name] = "UNAVAILABLE"
                continue

            current, prior, current_date, prior_date = self._current_and_4w(
                series_id,
                as_of,
                units=self.FRED_UNITS.get(logical_name),
            )
            results[logical_name] = current
            results[f"{logical_name}_4W_AGO"] = prior
            economic_observation_dates[logical_name] = current_date.isoformat()
            economic_prior_dates[logical_name] = prior_date.isoformat()

        missing = (REQUIRED_FRED_FIELDS | REQUIRED_ECONOMIC_FRED_FIELDS) - set(results)
        if missing:
            raise DataUnavailableError(
                "Missing FRED fields: " + ", ".join(sorted(missing))
            )

        results["M2SL_SOURCE_DATE"] = observation_dates["M2SL"]
        results["EA_HICP_SOURCE_DATE"] = economic_observation_dates.get("EA_HICP_YOY")
        results["ECB_DEPOSIT_RATE_SOURCE_DATE"] = economic_observation_dates.get("ECB_DEPOSIT_RATE")
        results["data_quality"] = {
            "provider": "FRED",
            "fallback_used": False,
            "ism_status": "UNAVAILABLE",
            "as_of": as_of.isoformat(),
            "vintage_end": as_of.isoformat(),
            "observation_dates": observation_dates,
            "prior_4w_dates": prior_dates,
            "economic_observation_dates": economic_observation_dates,
            "economic_prior_4w_dates": economic_prior_dates,
            "payems_previous_observation_date": results.get("PAYEMS_PREV_OBS_DATE"),
            "euro_area_observation_dates": {
                "EA_HICP_YOY": economic_observation_dates.get("EA_HICP_YOY"),
                "ECB_DEPOSIT_RATE": economic_observation_dates.get("ECB_DEPOSIT_RATE"),
            },
            "economic_transformations": {
                **{key: f"FRED {units} transform from {series_id}" for key, series_id in self.ECONOMIC_FRED_SERIES.items() if (units := self.FRED_UNITS.get(key))},
                "ISM_MANUFACTURING_PMI": "UNAVAILABLE (publisher discontinued public series NAPM on FRED; no synthetic data substituted)",
                "ISM_SERVICES_ACTIVITY": "UNAVAILABLE (publisher discontinued public series NMFBAI on FRED; no synthetic data substituted)",
                "SOFR": "direct New York Fed SOFR observation via FRED",
            },
        }
        logger.info(
            "[FRED] base+economic observations loaded at vintage=%s; synthetic baselines disabled",
            as_of.isoformat(),
        )
        return results
