from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, Any, List, Optional
import aiohttp

from pathlib import Path
import json

logger = logging.getLogger("CalendarEventIngestion")


class CalendarEventIngestion:
    """Fetch high-impact calendar events with caching and fail-closed safety.

    If the calendar cannot be verified and no usable cache exists, a fail-closed
    sentinel event is emitted so event_freeze immediately freezes execution gates.
    """

    URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    CACHE_TTL_SECONDS = 900  # 15 dakika
    CACHE_FILE = Path(__file__).resolve().parent.parent / "gateways" / "calendar_cache.json"

    _cache: Optional[List[Dict[str, Any]]] = None
    _cache_time: Optional[dt.datetime] = None
    _last_status: str = "INITIALIZED"

    @classmethod
    def get_last_status(cls) -> str:
        return cls._last_status

    @classmethod
    def _load_disk_cache(cls) -> Optional[Tuple[dt.datetime, List[Dict[str, Any]]]]:
        if not cls.CACHE_FILE.exists():
            return None
        try:
            raw = json.loads(cls.CACHE_FILE.read_text(encoding="utf-8"))
            cache_time = dt.datetime.fromisoformat(raw["timestamp"])
            events = raw["events"]
            if isinstance(events, list):
                return cache_time, events
        except Exception:
            return None
        return None

    @classmethod
    def _save_disk_cache(cls, cache_time: dt.datetime, events: List[Dict[str, Any]]) -> None:
        try:
            cls.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "timestamp": cache_time.isoformat(),
                "events": events,
            }
            cls.CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Could not persist calendar cache to disk: %s", e)

    async def fetch_latest_events(self) -> List[Dict[str, Any]]:
        now = dt.datetime.now(dt.timezone.utc)

        # 1. Bellek içi veya diskteki taze önbellek kontrolü (15 dk TTL)
        if (
            CalendarEventIngestion._cache is not None
            and CalendarEventIngestion._cache_time is not None
            and (now - CalendarEventIngestion._cache_time).total_seconds() < self.CACHE_TTL_SECONDS
        ):
            CalendarEventIngestion._last_status = "CACHED"
            return list(CalendarEventIngestion._cache)

        disk_cached = self._load_disk_cache()
        if disk_cached is not None:
            disk_time, disk_events = disk_cached
            if (now - disk_time).total_seconds() < self.CACHE_TTL_SECONDS:
                CalendarEventIngestion._cache = disk_events
                CalendarEventIngestion._cache_time = disk_time
                CalendarEventIngestion._last_status = "CACHED"
                return list(disk_events)

        # 2. Canlı ağ sorgusu (Tam browser başlıkları ile 429 önleme)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(self.URL, timeout=8) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}")
                    data = await resp.json()
                    events = [e for e in data if e.get("impact") == "High"]
                    if not isinstance(events, list):
                        raise RuntimeError("Calendar payload is not a list")

                    # Başarılı: Önbelleği güncelle
                    CalendarEventIngestion._cache = events
                    CalendarEventIngestion._cache_time = now
                    CalendarEventIngestion._last_status = "LIVE"
                    self._save_disk_cache(now, events)
                    return list(events)
        except Exception as exc:
            # 3. Hata durumunda: 2 saate kadar bayat önbellek varsa uyararak kullan
            disk_cached = self._load_disk_cache()
            if disk_cached is not None:
                disk_time, disk_events = disk_cached
                if (now - disk_time).total_seconds() < 7200:
                    logger.warning(
                        "Economic calendar network error (%s); using unexpired cache from %s.",
                        exc,
                        disk_time.isoformat(),
                    )
                    CalendarEventIngestion._cache = disk_events
                    CalendarEventIngestion._cache_time = disk_time
                    CalendarEventIngestion._last_status = "CACHED_FALLBACK"
                    return list(disk_events)

            # 4. Önbellek de yoksa: FAIL-CLOSED! Boş dönüp alım-satıma izin vermek YASAKTIR.
            logger.error(
                "Economic calendar completely unavailable (%s); activating FAIL-CLOSED EVENT_FREEZE.",
                exc,
            )
            CalendarEventIngestion._last_status = "FAIL_CLOSED"
            # time=None olması deterministic_controls.py:event_freeze_status içinde
            # uncertain=True ve active=True üretir; böylece sistem güvenli moda kilitlenir.
            return [
                {
                    "title": "Ekonomik Takvim Alınamadı (Fail-Closed Güvenli Devre Kesici)",
                    "country": "USD",
                    "impact": "CRITICAL",
                    "time": None,
                    "uncertain": True,
                    "fail_closed": True,
                }
            ]
