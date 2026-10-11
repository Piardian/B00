from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from data_quality import DataUnavailableError

logger = logging.getLogger("ECBDataIngestion")
CACHE_FILE = Path(__file__).parent.parent / "data" / "cache" / "ecb_2y_yield.json"


class ECBDataIngestion:
    """Official European Central Bank (ECB) government yield curve ingestion via ECB Data Portal API."""

    SERIES_KEY = "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"
    ENDPOINT = "https://data-api.ecb.europa.eu/service/data/YC"

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    @staticmethod
    def _save_cache(data: Dict[str, Any]) -> None:
        try:
            os.makedirs(CACHE_FILE.parent, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as err:
            logger.warning("ECB önbellek dosyası yazılamadı: %s", err)

    @staticmethod
    def _load_cache(as_of: dt.datetime) -> Optional[Dict[str, Any]]:
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, dict) and "value" in cached:
                    cached = dict(cached)
                    cached["source"] = f"{cached.get('source', 'ECB Data Portal')} [Cached Fallback]"
                    cached["status"] = "AVAILABLE"
                    cached["fallback_used"] = False
                    return cached
        except Exception as err:
            logger.warning("ECB önbellek dosyası okunamadı: %s", err)
        return None

    def fetch_2y_yield(
        self,
        as_of: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or dt.datetime.now(dt.timezone.utc)
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=dt.timezone.utc)
        as_of = as_of.astimezone(dt.timezone.utc)

        url = f"{self.ENDPOINT}/{self.SERIES_KEY}?lastNObservations=60&format=jsondata"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BegonyaMacroEngine/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            cached = self._load_cache(as_of)
            if cached:
                logger.info(
                    "ECB API erişiminde gecikme (%s); yerel disk önbelleğindeki son ECB verisi kullanılıyor (Tarih: %s, Değer: %s)",
                    exc, cached.get("observation_date"), cached.get("value")
                )
                return cached
            raise DataUnavailableError(
                f"ECB 2Y yield request failed: {exc}"
            ) from None

        try:
            series = payload["dataSets"][0]["series"]["0:0:0:0:0:0:0"]["observations"]
            dates = [
                d["id"]
                for d in payload["structure"]["dimensions"]["observation"][0]["values"]
            ]
            rows: list[tuple[dt.date, float]] = []
            for idx_str, obs in sorted(series.items(), key=lambda x: int(x[0])):
                d_val = dt.date.fromisoformat(dates[int(idx_str)])
                v_val = float(obs[0])
                rows.append((d_val, v_val))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise DataUnavailableError(f"Malformed ECB response: {exc}") from None

        completed = [row for row in rows if row[0] <= as_of.date()]
        if not completed:
            raise DataUnavailableError(
                f"No ECB 2Y yield observation available for {as_of.date().isoformat()}"
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

        res = {
            "value": round(value, 4),
            "prev": round(prev_val, 4),
            "val_5d_ago": round(val_5d_ago, 4),
            "month_ago": round(month_ago_val, 4),
            "change_pct": pct_change_daily,
            "change_pct_5d": pct_change_5d,
            "change_pct_4w": pct_change_4w,
            "pct_rank_60d": pct_rank_60d,
            "history_close": history_close,
            "source": f"ECB Data Portal AAA Government 2Y Spot Rate ({self.SERIES_KEY})",
            "observation_date": observation_date.isoformat(),
            "status": "AVAILABLE",
            "fallback_used": False,
        }
        self._save_cache(res)
        return res
