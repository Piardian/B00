"""
🌺 Begonya 00 - Kritik Haber Devre Kesicisi (News Guard)
Yüksek Etkili Ekonomik Haberlerde (CPI, NFP, FOMC vb.) İşlem Dondurma Kalkanı
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import CONFIG_DIR

logger = logging.getLogger("Begonya00.NewsGuard")
NEWS_FILE = CONFIG_DIR / "news_events.json"


class NewsGuard:
    def __init__(self, news_file: Optional[Path] = None):
        self.news_file = news_file or NEWS_FILE
        self.config = self._load_news_config()

    def _load_news_config(self) -> Dict[str, Any]:
        if self.news_file.exists():
            try:
                return json.loads(self.news_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"news_events.json okunamadi: {e}")
        return {
            "default_freeze_minutes_before": 15,
            "default_freeze_minutes_after": 15,
            "scheduled_events": [],
        }

    def check_freeze(self, symbol: str) -> Dict[str, Any]:
        """
        Guncel UTC zamani icin belirtilen sembolde haber dondurma korumasi olup olmadigini denetler.
        """
        now_utc = datetime.now(timezone.utc)
        events = self.config.get("scheduled_events", [])
        freeze_before = self.config.get("default_freeze_minutes_before", 15)
        freeze_after = self.config.get("default_freeze_minutes_after", 15)

        clean_sym = symbol.replace("/", "").replace("-", "").upper()

        for ev in events:
            ev_time_str = ev.get("event_time_utc")
            if not ev_time_str:
                continue

            try:
                # ISO format parse
                ev_time = datetime.fromisoformat(ev_time_str.replace("Z", "+00:00"))
                # Sembol etkileniyor mu?
                affects_all = ev.get("affects_all_symbols", False)
                affects_list = [s.upper() for s in ev.get("affects_symbols", [])]
                ev_currency = ev.get("currency", "USD").upper()

                symbol_affected = affects_all or (clean_sym in affects_list) or (ev_currency in clean_sym)
                if not symbol_affected:
                    continue

                # Zaman aralığı kontrolü
                custom_before = ev.get("freeze_minutes_before", freeze_before)
                custom_after = ev.get("freeze_minutes_after", freeze_after)

                window_start = ev_time - timedelta(minutes=custom_before)
                window_end = ev_time + timedelta(minutes=custom_after)

                if window_start <= now_utc <= window_end:
                    minutes_diff = round((ev_time - now_utc).total_seconds() / 60.0, 1)
                    phase = "ÖNCESİ" if minutes_diff > 0 else "SONRASI"
                    diff_abs = abs(minutes_diff)

                    return {
                        "is_frozen": True,
                        "event_id": ev.get("id"),
                        "event_name": ev.get("name", "Kritik Haber"),
                        "impact": ev.get("impact", "CRITICAL"),
                        "phase": phase,
                        "minutes_away": diff_abs,
                        "reason": f"Kritik Haber Kalkanı Aktif: {ev.get('name')} ({diff_abs} dk {phase})",
                    }

            except Exception as e:
                logger.debug(f"Haber zamani ayrirma hatasi: {e}")

        return {
            "is_frozen": False,
            "event_name": None,
            "reason": "Haber kalkanı temiz (İşlem yapılabilir).",
        }
