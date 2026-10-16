"""
Olay Odaklı Makro Arka Plan Servisi (Event-Driven Macro Daemon)
Tetikleme Mantığı:
1. Periyodik: Günlük (D1) seans kapanışında günde 1 kez.
2. Olay Odaklı: Ekonomik takvimdeki yüksek etkili (Kırmızı Bayrak) bir veri
   açıklandıktan 3 dakika sonra (T + 180s) piyasa şoku sindirildiğinde 1 kez.
"""

import os
import sys
import time
import json
import logging
import argparse
import datetime
from pathlib import Path

# Proje kök dizinini ekle
ROOT_DIR = Path(__file__).parent.parent.resolve()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
from graph.macro_graph import MacroWorkflowEngine
from ingestion.calendar_event import CalendarEventIngestion
from gateways.telegram_notifier import send_telegram_message, format_morning_briefing
from config import BIAS_GATE_FILE

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MacroDaemon] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MacroDaemon")

STATE_FILE = Path(__file__).parent / "scheduler_state.json"
GLOBAL_STATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".begonya"))) / "Begonya"
GLOBAL_STATE_FILE = GLOBAL_STATE_DIR / "macro_scheduler_global_state.json"
GLOBAL_BRIEFING_LOCK = GLOBAL_STATE_DIR / "morning_briefing_global.lock"


class MacroEventScheduler:
    def __init__(self, post_news_delay_seconds: int = 180):
        self.post_news_delay = post_news_delay_seconds
        self.state_file = STATE_FILE
        self.engine = MacroWorkflowEngine()
        self.calendar = CalendarEventIngestion()
        self.cached_events = []
        self.last_calendar_fetch = 0.0

    def _load_state(self) -> dict:
        local_state = {}
        try:
            if self.state_file.exists():
                with open(self.state_file, "r", encoding="utf-8") as f:
                    local_state = json.load(f)
        except Exception as e:
            logger.warning(f"State dosyası okunamadı: {e}")

        global_state = {}
        try:
            if GLOBAL_STATE_FILE.exists():
                with open(GLOBAL_STATE_FILE, "r", encoding="utf-8") as f:
                    global_state = json.load(f)
        except Exception:
            pass

        base = {
            "last_morning_briefing_date": "",
            "last_london_session_date": "",
            "last_ny_session_date": "",
            "last_daily_close_date": "",
            "last_cycle_timestamp": 0.0,
            "executed_news_events": []
        }
        base.update(local_state)

        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        if global_state.get("last_morning_briefing_date") == today_str:
            base["last_morning_briefing_date"] = today_str
        if global_state.get("last_daily_close_date") == today_str:
            base["last_daily_close_date"] = today_str

        return base

    def _save_state(self, state: dict):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Local state dosyası yazılamadı: {e}")

        try:
            GLOBAL_STATE_DIR.mkdir(parents=True, exist_ok=True)
            with open(GLOBAL_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Global state dosyası yazılamadı: {e}")

    def run_cycle(self, trigger_source: str = "Manual / Scheduled"):
        """Tam makro analiz döngüsünü çalıştırır ve atomik kapıyı günceller."""
        logger.info(f"🚀 [MAKRO DÖNGÜ BAŞLATILDI] Tetikleyici: {trigger_source}")
        start_time = time.time()
        try:
            result = self.engine.run_pipeline()
            strat = result.get("final_output", {})
            regime = strat.get("primary_regime", "Bilinmiyor")
            deterministic = result.get("deterministic_execution_gates", {})
            gates = deterministic.get("execution_bias_gates", {})
            elapsed = round(time.time() - start_time, 2)
            logger.info(
                f"✅ [MAKRO DÖNGÜ TAMAMLANDI - {elapsed}s] Rejim: {regime} | "
                f"Deterministic Kapılar: XAUUSD={gates.get('XAUUSD')}, "
                f"EURUSD={gates.get('EURUSD')}, BTC={gates.get('BTC')}"
            )
            try:
                state = self._load_state()
                state["last_cycle_timestamp"] = time.time()
                self._save_state(state)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"❌ Makro analiz döngüsünde hata: {e}", exc_info=True)
            return False

    def _acquire_file_lock(self, lock_path: Path, max_age_seconds: int = 900) -> bool:
        """Atomik dosya kilidi edinir; eski/donmuş kilitleri temizler."""
        for _ in range(2):
            try:
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(f"{os.getpid()}:{time.time()}")
                return True
            except FileExistsError:
                try:
                    mtime = lock_path.stat().st_mtime
                    if time.time() - mtime > max_age_seconds:
                        logger.warning(f"⚠️ Eski/donmuş kilit dosyası ({lock_path.name}) temizleniyor...")
                        lock_path.unlink(missing_ok=True)
                        continue
                except Exception:
                    pass
                return False
            except Exception as e:
                logger.warning(f"Kilit edinme hatası: {e}")
                return False
        return False

    def _release_file_lock(self, lock_path: Path):
        """Dosya kilidini serbest bırakır."""
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass

    def send_morning_briefing(self, force: bool = False) -> bool:
        """Sabah 09:00 analizini çalıştırır ve Telegram'a detaylı bülten iletir."""
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        state = self._load_state()
        if not force and state.get("last_morning_briefing_date") == today_str:
            logger.info(f"ℹ️ [SABAH BÜLTENİ] Bugünün ({today_str}) bülteni zaten gönderilmiş veya işlemde. Mükerrer gönderim engellendi.")
            return True

        from config import ENABLE_MACRO_TELEGRAM_NOTIFICATIONS
        if not ENABLE_MACRO_TELEGRAM_NOTIFICATIONS:
            logger.info("🔕 [SABAH BÜLTENİ] Begonya 00 için sabah bülteni/gündem Telegram bildirimleri kapalı. Telegram gönderimi atlandı.")
            state = self._load_state()
            state["last_morning_briefing_date"] = today_str
            self._save_state(state)
            return True

        lock_path = self.state_file.parent / "morning_briefing.lock"
        if not self._acquire_file_lock(lock_path, max_age_seconds=900):
            logger.info("ℹ️ [SABAH BÜLTENİ] Başka bir yerel işlem sabah bültenini hazırlıyor. Mükerrer çalıştırma atlandı.")
            return False

        if not self._acquire_file_lock(GLOBAL_BRIEFING_LOCK, max_age_seconds=900):
            logger.info("ℹ️ [SABAH BÜLTENİ] Sistem çapında başka bir süreç (Begonya / B00) sabah bültenini hazırlıyor. Mükerrer çalıştırma atlandı.")
            self._release_file_lock(lock_path)
            return False

        state = self._load_state()
        state["last_morning_briefing_date"] = today_str
        self._save_state(state)

        try:
            logger.info("☀️ [SABAH BÜLTENİ] 09:00 Makro Analizi ve Telegram Raporlama Başlatıldı...")
            result = self.engine.run_pipeline()
            events = []
            try:
                events = asyncio.run(self.calendar.fetch_latest_events())
            except Exception as e:
                logger.debug(f"Bülten için takvim çekilirken hata: {e}")
            
            msg = format_morning_briefing(result, events)
            sent = send_telegram_message(msg)
            if sent:
                logger.info("☀️ [SABAH BÜLTENİ] Telegram Sabah Makro Bülteni Başarıyla Gönderildi!")
            else:
                logger.warning("⚠️ [SABAH BÜLTENİ] Telegram bülteni gönderiminde kısmi veya tam aksaklık oldu. Mükerrer fırtınayı önlemek için tarih kilidi korunuyor.")
            return sent
        except Exception as e:
            logger.error(f"❌ [SABAH BÜLTENİ] Beklenmeyen hata oluştu: {e}", exc_info=True)
            return False
        finally:
            self._release_file_lock(lock_path)
            self._release_file_lock(GLOBAL_BRIEFING_LOCK)


    def _get_calendar_events_cached(self, ttl_seconds: int = 300) -> list:
        """Ekonomik takvim olaylarını 5 dakika önbellekli olarak çeker."""
        now_ts = time.time()
        if not self.cached_events or (now_ts - self.last_calendar_fetch) > ttl_seconds:
            try:
                self.cached_events = asyncio.run(self.calendar.fetch_latest_events())
                self.last_calendar_fetch = now_ts
            except Exception as ce:
                logger.debug(f"Takvim çekilirken hata: {ce}")
        return self.cached_events

    def get_upcoming_triggers(self) -> list:
        """Bugünkü kırmızı bayraklı olayları, sabah bültenini ve D1 kapanışını listeler."""
        triggers = []
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        state = self._load_state()

        # 1. Sabah 09:00 Makro Bülten Tetikleyicisi
        morning_target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if state.get("last_morning_briefing_date") == today_str or morning_target < now:
            morning_target += datetime.timedelta(days=1)
        triggers.append({
            "name": "Sabah Makro Bülteni (09:00)",
            "scheduled_time": morning_target,
            "type": "MORNING_BRIEFING"
        })

        # 2. Londra Seans Açılışı (10:30 TRT)
        london_target = now.replace(hour=10, minute=30, second=0, microsecond=0)
        if state.get("last_london_session_date") == today_str or london_target < now:
            london_target += datetime.timedelta(days=1)
        triggers.append({
            "name": "Londra Seans Açılışı (10:30)",
            "scheduled_time": london_target,
            "type": "LONDON_SESSION"
        })

        # 3. New York Seans Açılışı (16:00 TRT)
        ny_target = now.replace(hour=16, minute=0, second=0, microsecond=0)
        if state.get("last_ny_session_date") == today_str or ny_target < now:
            ny_target += datetime.timedelta(days=1)
        triggers.append({
            "name": "New York Seans Açılışı (16:00)",
            "scheduled_time": ny_target,
            "type": "NY_SESSION"
        })

        # 4. Günlük D1 Kapanış Tetikleyicisi (Her gece 23:55)
        d1_target = now.replace(hour=23, minute=55, second=0, microsecond=0)
        if state.get("last_daily_close_date") == today_str or d1_target < now:
            d1_target += datetime.timedelta(days=1)
        triggers.append({
            "name": "D1 Günlük Bar Kapanışı (23:55)",
            "scheduled_time": d1_target,
            "type": "DAILY_CLOSE"
        })

        # 5. Yüksek Etkili Olaylar (Kırmızı Bayrak)
        events = self._get_calendar_events_cached(ttl_seconds=300)
        for ev in events:
            title = ev.get('title', 'Ekonomik Olay')
            time_str = ev.get('time', '')
            if time_str and ":" in time_str:
                try:
                    t_parts = time_str.split(":")
                    ev_time = now.replace(hour=int(t_parts[0]), minute=int(t_parts[1]), second=0, microsecond=0)
                    trigger_time = ev_time + datetime.timedelta(seconds=self.post_news_delay)
                    if trigger_time > now:
                        triggers.append({
                            "name": f"Haber Tetiklemesi (+3dk): {title}",
                            "scheduled_time": trigger_time,
                            "type": "EVENT_DRIVEN"
                        })
                except Exception:
                    pass

        triggers.sort(key=lambda x: x["scheduled_time"])
        return triggers

    def start_daemon_loop(self, poll_interval_seconds: int = 30):
        """Arka planda tetikleyicileri izleyen ana döngü."""
        logger.info("🛡️ [DAEMON BAŞLATILDI] Olay Odaklı Makro Tetikleyici devrede.")
        logger.info(f"⚙️ Kontrol aralığı: {poll_interval_seconds}s | Haber sonrası gecikme: {self.post_news_delay}s")

        # İlk çalıştırma (Sistem başlarken kapıyı güncel tut)
        self.run_cycle(trigger_source="Daemon Startup Baseline")

        while True:
            try:
                now = datetime.datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                state = self._load_state()

                # 1. Sabah 09:00 Bülteni Kontrolü (Tarih kilitli, asla ıskalanmaz)
                # Saat 09:00 ile 18:00 arasında ise ve bugünün bülteni henüz gönderilmediyse:
                if (now.hour >= 9 and now.hour < 18) and state.get("last_morning_briefing_date") != today_str:
                    logger.info(f"🔔 [ZAMANLAYICI TETİKLENDİ] Sabah Makro Bülteni (09:00) | Tarih: {today_str}")
                    self.send_morning_briefing()

                # 2. Londra Seans Açılışı Kontrolü (10:30 TRT)
                if ((now.hour == 10 and now.minute >= 30) or (now.hour > 10 and now.hour < 15)) and state.get("last_london_session_date") != today_str:
                    logger.info(f"🔔 [ZAMANLAYICI TETİKLENDİ] Londra Seans Açılışı (10:30) | Tarih: {today_str}")
                    self.run_cycle(trigger_source="Londra Seans Açılışı (10:30)")
                    state = self._load_state()
                    state["last_london_session_date"] = today_str
                    self._save_state(state)

                # 3. New York Seans Açılışı Kontrolü (16:00 TRT)
                if (now.hour >= 16 and now.hour < 23) and state.get("last_ny_session_date") != today_str:
                    logger.info(f"🔔 [ZAMANLAYICI TETİKLENDİ] New York Seans Açılışı (16:00) | Tarih: {today_str}")
                    self.run_cycle(trigger_source="New York Seans Açılışı (16:00)")
                    state = self._load_state()
                    state["last_ny_session_date"] = today_str
                    self._save_state(state)

                # 4. Günlük D1 Kapanış Kontrolü (Her gece 23:55 veya sonrası)
                if (now.hour == 23 and now.minute >= 55) and state.get("last_daily_close_date") != today_str:
                    logger.info(f"🔔 [ZAMANLAYICI TETİKLENDİ] D1 Günlük Bar Kapanışı (23:55) | Tarih: {today_str}")
                    close_lock = self.state_file.parent / "daily_close.lock"
                    if self._acquire_file_lock(close_lock, max_age_seconds=600):
                        try:
                            state = self._load_state()
                            state["last_daily_close_date"] = today_str
                            self._save_state(state)
                            self.run_cycle(trigger_source="D1 Günlük Bar Kapanışı (23:55)")
                        finally:
                            self._release_file_lock(close_lock)

                # 5. Seans İçi Emniyet Tazelemesi (09:00 - 23:00 arası son analizden bu yana > 4 saat geçtiyse)
                last_cycle = state.get("last_cycle_timestamp", 0.0)
                if (now.hour >= 9 and now.hour < 23) and (time.time() - last_cycle > 4 * 3600):
                    logger.info("🔔 [ZAMANLAYICI TETİKLENDİ] Seans İçi 4 Saatlik Emniyet Tazelemesi")
                    self.run_cycle(trigger_source="Seans İçi 4 Saatlik Emniyet Tazelemesi")
                    state = self._load_state()

                # 6. Yüksek Etkili Haber / Olay Tetikleyicileri (Kırmızı Bayrak)
                events = self._get_calendar_events_cached(ttl_seconds=300)
                executed_events = set(state.get("executed_news_events", []))

                for ev in events:
                    title = ev.get('title', 'Ekonomik Olay')
                    time_str = ev.get('time', '')
                    if time_str and ":" in time_str:
                        try:
                            t_parts = time_str.split(":")
                            ev_time = now.replace(hour=int(t_parts[0]), minute=int(t_parts[1]), second=0, microsecond=0)
                            trigger_time = ev_time + datetime.timedelta(seconds=self.post_news_delay)
                            event_key = f"{title}_{today_str}_{t_parts[0]}:{t_parts[1]}"

                            if event_key not in executed_events:
                                time_diff = (now - trigger_time).total_seconds()
                                # Olay anından itibaren [0s, 900s] (15 dakika) içinde yakalandıysa tetikle
                                if 0 <= time_diff <= 900:
                                    logger.info(f"🔔 [HABER TETİKLENDİ] {title} (+3dk gecikme ile)")
                                    self.run_cycle(trigger_source=f"Haber: {title}")
                                    executed_events.add(event_key)
                                    state["executed_news_events"] = list(executed_events)[-100:]
                                    self._save_state(state)
                        except Exception as ee:
                            logger.debug(f"Haber tetikleyici hatası: {ee}")

                time.sleep(poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("🛑 Daemon kullanıcı tarafından durduruldu.")
                break
            except Exception as e:
                logger.error(f"Daemon döngüsünde beklenmeyen hata: {e}")
                time.sleep(poll_interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Olay Odaklı Makro Arka Plan Servisi")
    parser.add_argument("--once", action="store_true", help="Tek bir makro analiz döngüsü çalıştır ve çık")
    parser.add_argument("--daemon", action="store_true", help="Arka plan izleme döngüsünü başlat")
    parser.add_argument("--status", action="store_true", help="Yaklaşan tetikleyicileri listele")
    parser.add_argument("--briefing", action="store_true", help="Sabah makro bültenini hemen oluştur ve Telegram'a gönder")
    args = parser.parse_args()

    scheduler = MacroEventScheduler()

    if args.briefing:
        scheduler.send_morning_briefing()
    elif args.once:
        scheduler.run_cycle(trigger_source="CLI --once")
    elif args.status:
        triggers = scheduler.get_upcoming_triggers()
        print("\n" + "=" * 60)
        print("          YAKLAŞAN MAKRO TETİKLEYİCİ TAKVİMİ          ")
        print("=" * 60)
        for i, t in enumerate(triggers, 1):
            print(f"{i}. [{t['type']:<12}] {t['scheduled_time'].strftime('%Y-%m-%d %H:%M:%S')} -> {t['name']}")
        print("=" * 60 + "\n")
    else:
        # Varsayılan: Tek çalıştırma veya --daemon modu
        scheduler.start_daemon_loop()


if __name__ == "__main__":
    main()
