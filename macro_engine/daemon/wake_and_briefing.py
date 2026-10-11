"""
Begonya Uyandırma & Makro Görev Yöneticisi (Wake & Run Wrapper)
Bilgisayar uyku (Sleep / Modern Standby) modunda olsa dahi:
1. Görev Zamanlayıcı tarafından sistem uyandırıldığında derhal ES_SYSTEM_REQUIRED çağrısı yaparak
   Windows'un 2 dakikalık otomatik uykuya dönmesini (unattended sleep timeout) engeller.
2. Ağ bağlantısının (Wi-Fi / Ethernet / DNS) oturmasını 60 saniyeye kadar bekler.
3. Sabah Makro Bülteni'ni veya D1 Bar Kapanışı analizini çalıştırıp Telegram'a iletir.
4. İşlem bitince sistem kilidini serbest bırakır.
"""

import os
import sys
import time
import ctypes
import logging
import argparse
import datetime
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.resolve()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from daemon.macro_scheduler import MacroEventScheduler

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

LOG_FILE = Path(__file__).parent / "wake_briefing.log"

logger = logging.getLogger("WakeBriefing")
logger.setLevel(logging.INFO)

file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - [WakeBriefing] - %(levelname)s - %(message)s'))
if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    logger.addHandler(file_handler)


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def prevent_sleep():
    """Windows'un işlem bitene kadar sistemi uykuya geçirmesini önler."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            )
            logger.info("🛡️ [GÜÇ YÖNETİMİ] Windows Uyku Kilidi Aktif Edildi (SetThreadExecutionState: ES_SYSTEM_REQUIRED).")
        except Exception as e:
            logger.warning(f"⚠️ Uyku kilidi aktif edilemedi: {e}")


def allow_sleep():
    """İşlem bittiğinde uyku kilidini kaldırır."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            logger.info("💤 [GÜÇ YÖNETİMİ] Windows Uyku Kilidi Kaldırıldı (Normal moda dönüldü).")
        except Exception as e:
            logger.warning(f"⚠️ Uyku kilidi serbest bırakılamadı: {e}")


def wait_for_network(max_wait_seconds: int = 60) -> bool:
    """Uykudan uyanış sonrası Wi-Fi / internet bağlantısının oturmasını bekler."""
    logger.info("🌐 İnternet bağlantısı kontrol ediliyor...")
    start_time = time.time()
    urls_to_test = [
        "https://api.telegram.org",
        "https://www.google.com",
        "https://1.1.1.1"
    ]
    
    while time.time() - start_time < max_wait_seconds:
        for test_url in urls_to_test:
            try:
                req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    if resp.status in (200, 301, 302, 404):
                        elapsed = round(time.time() - start_time, 1)
                        logger.info(f"✅ İnternet bağlantısı aktif! ({elapsed}s içinde doğrulandı -> {test_url})")
                        return True
            except Exception:
                pass
        logger.debug("Ağ henüz hazır değil, bekleniyor (2s)...")
        time.sleep(2)
        
    logger.error(f"❌ {max_wait_seconds} saniye içinde internet bağlantısı kurulamadı!")
    return False


def run_morning_wake_task():
    logger.info("=" * 60)
    logger.info("🌅 [WAKE GÖREVİ] Sabah Makro Bülteni Uyanma Rutini Başlatıldı")
    logger.info("=" * 60)
    prevent_sleep()
    try:
        from config import ENABLE_MACRO_TELEGRAM_NOTIFICATIONS
        if not ENABLE_MACRO_TELEGRAM_NOTIFICATIONS:
            logger.info("🔕 [WAKE GÖREVİ] Begonya 00 için sabah bülteni Telegram gönderimi devre dışı. Görev sonlandırıldı.")
            return

        net_ok = wait_for_network(max_wait_seconds=60)
        if not net_ok:
            logger.warning("⚠️ Ağ bağlantısı olmadan deneniyor...")

        scheduler = MacroEventScheduler()
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        state = scheduler._load_state()

        if state.get("last_morning_briefing_date") == today_str:
            logger.info(f"ℹ️ Bugünün ({today_str}) sabah bülteni zaten daha önce gönderilmiş. Mükerrer gönderim yapılmadı.")
            return

        logger.info(f"🚀 Sabah bülteni tetikleniyor (Tarih: {today_str})...")
        success = scheduler.send_morning_briefing()
        if success:
            logger.info("🎉 [BAŞARILI] Sabah makro bülteni Telegram'a başarıyla iletildi!")
        else:
            logger.warning("ℹ️ Sabah makro bülteni iletilemedi veya başka bir işlem tarafından rezerve edildi.")
    except Exception as e:
        logger.error(f"❌ Wake görevinde beklenmeyen hata: {e}", exc_info=True)
    finally:
        allow_sleep()
        logger.info("🏁 [TAMAMLANDI] Sabah uyanma rutini sonlandı.\n")


def run_daily_close_wake_task():
    logger.info("=" * 60)
    logger.info("🌙 [WAKE GÖREVİ] D1 Günlük Kapanış Uyanma Rutini Başlatıldı")
    logger.info("=" * 60)
    prevent_sleep()
    try:
        net_ok = wait_for_network(max_wait_seconds=60)
        if not net_ok:
            logger.warning("⚠️ Ağ bağlantısı olmadan deneniyor...")

        scheduler = MacroEventScheduler()
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        state = scheduler._load_state()

        if state.get("last_daily_close_date") == today_str:
            logger.info(f"ℹ️ Bugünün ({today_str}) D1 kapanış analizi zaten yapılmış. Mükerrer işlem yapılmadı.")
            return

        close_lock = scheduler.state_file.parent / "daily_close.lock"
        if not scheduler._acquire_file_lock(close_lock, max_age_seconds=600):
            logger.info("ℹ️ D1 Kapanış analizi şu anda başka bir işlem tarafından yürütülüyor. Mükerrer çağrı engellendi.")
            return

        try:
            state = scheduler._load_state()
            state["last_daily_close_date"] = today_str
            scheduler._save_state(state)
            logger.info(f"🚀 D1 Bar Kapanış döngüsü tetikleniyor (Tarih: {today_str})...")
            success = scheduler.run_cycle(trigger_source="Windows Wake Task (D1 Close)")
            if success:
                logger.info("🎉 [BAŞARILI] D1 Günlük kapanış analizi ve kapı güncellemesi tamamlandı!")
            else:
                logger.warning("⚠️ D1 Günlük kapanış analizi tamamlanamadı.")
        finally:
            scheduler._release_file_lock(close_lock)
    except Exception as e:
        logger.error(f"❌ D1 Close wake görevinde beklenmeyen hata: {e}", exc_info=True)
    finally:
        allow_sleep()
        logger.info("🏁 [TAMAMLANDI] D1 kapanış uyanma rutini sonlandı.\n")


def main():
    parser = argparse.ArgumentParser(description="Begonya Wake & Run Script")
    parser.add_argument("--d1-close", action="store_true", help="D1 Günlük Bar Kapanışını çalıştır")
    args = parser.parse_args()

    if args.d1_close:
        run_daily_close_wake_task()
    else:
        run_morning_wake_task()


if __name__ == "__main__":
    main()
