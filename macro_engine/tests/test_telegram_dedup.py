"""
Test Suite: Telegram Bildirimleri ve Sabah Bülteni Mükerrer Gönderim (Deduplication) Koruması
Doğrulanan senaryolar:
1. split_text_into_chunks(): Uzun bülten metinlerinin 3700 karakter altı mantıksal parçalara bölünmesi.
2. Global state senkronizasyonu: Global state dosyasındaki tarihin okunması ve mükerrer çağrının önlenmesi.
3. Önleyici kilit: Gönderim hatasında dahi tarih kilidinin silinmemesi (retry storm engelleme).
4. Atomik kilit: Eşzamanlı iki sürecin sabah bültenini aynı anda göndermesinin engellenmesi.
"""

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
MACRO_DIR = Path(__file__).parent.parent.resolve()
if str(MACRO_DIR) not in sys.path:
    sys.path.insert(0, str(MACRO_DIR))

from gateways.telegram_notifier import split_text_into_chunks, send_telegram_message
from daemon.macro_scheduler import MacroEventScheduler


class TelegramDeduplicationTests(unittest.TestCase):
    def test_split_text_into_chunks_under_limit(self):
        short_text = "Kısa bir makro analiz mesajı."
        chunks = split_text_into_chunks(short_text, max_chunk_len=3700)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], short_text)

    def test_split_text_into_chunks_large_text(self):
        # 10,000 karakterlik yapay bülten metni
        section1 = "🌺 <b>BEGONYA | GÜNLÜK MAKRO BÜLTEN</b>\n" + ("A" * 3000)
        section2 = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 <b>EYLEM PLANI</b>\n" + ("B" * 3000)
        section3 = "\n📝 <b>BAŞ STRATEJİST RAPORU:</b>\n" + ("C" * 3000)
        full_text = section1 + section2 + section3

        chunks = split_text_into_chunks(full_text, max_chunk_len=3700)
        self.assertGreater(len(chunks), 1)
        for i, chunk in enumerate(chunks, 1):
            self.assertLessEqual(len(chunk), 4096, f"Chunk {i} exceeds Telegram 4096 character limit")
            if i == 1:
                self.assertIn("Devamı Aşağıda", chunk)
            else:
                self.assertIn(f"Bölüm {i}/", chunk)

    def test_global_state_sync_prevents_duplicate_morning_briefing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            local_state_file = tmp_path / "local_state.json"
            global_state_file = tmp_path / "global_state.json"
            global_lock_file = tmp_path / "global.lock"

            import datetime
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            # Global state'e bugün gönderildi yazılmış
            with open(global_state_file, "w", encoding="utf-8") as f:
                json.dump({"last_morning_briefing_date": today_str}, f)

            with patch("daemon.macro_scheduler.GLOBAL_STATE_FILE", global_state_file), \
                 patch("daemon.macro_scheduler.GLOBAL_BRIEFING_LOCK", global_lock_file):

                scheduler = MacroEventScheduler()
                scheduler.state_file = local_state_file

                # send_telegram_message mock'u
                with patch("daemon.macro_scheduler.send_telegram_message") as mock_send, \
                     patch.object(scheduler.engine, "run_pipeline") as mock_pipeline:

                    result = scheduler.send_morning_briefing(force=False)
                    self.assertTrue(result)
                    # Global state bugünü içerdiği için Telegram gönderimi ve pipeline ASLA çağrılmamalıdır
                    mock_send.assert_not_called()
                    mock_pipeline.assert_not_called()

    def test_failure_does_not_clear_date_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            local_state_file = tmp_path / "local_state.json"
            global_state_file = tmp_path / "global_state.json"
            global_lock_file = tmp_path / "global.lock"

            with patch("daemon.macro_scheduler.GLOBAL_STATE_FILE", global_state_file), \
                 patch("daemon.macro_scheduler.GLOBAL_BRIEFING_LOCK", global_lock_file), \
                 patch("daemon.macro_scheduler.ENABLE_MACRO_TELEGRAM_NOTIFICATIONS", True):

                scheduler = MacroEventScheduler()
                scheduler.state_file = local_state_file

                # Pipeline başarılı ama Telegram gönderimi başarısız simülasyonu
                with patch.object(scheduler.engine, "run_pipeline", return_value={"final_output": {}, "processed_metrics": {}}), \
                     patch("daemon.macro_scheduler.send_telegram_message", return_value=False):

                    result = scheduler.send_morning_briefing(force=False)
                    self.assertFalse(result)

                    # Önleyici kilit sayesinde bugünün tarihi state'te kalmalı, silinmemeli
                    today_str = scheduler._load_state().get("last_morning_briefing_date")
                    import datetime
                    self.assertEqual(today_str, datetime.datetime.now().strftime("%Y-%m-%d"))

    def test_concurrent_lock_rejection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            local_state_file = tmp_path / "local_state.json"
            global_state_file = tmp_path / "global_state.json"
            global_lock_file = tmp_path / "global.lock"

            # Global kilit dosyasını önceden oluştur (başka bir süreç çalışıyor)
            with open(global_lock_file, "w", encoding="utf-8") as f:
                f.write("99999:9999999999")

            with patch("daemon.macro_scheduler.GLOBAL_STATE_FILE", global_state_file), \
                 patch("daemon.macro_scheduler.GLOBAL_BRIEFING_LOCK", global_lock_file), \
                 patch("daemon.macro_scheduler.ENABLE_MACRO_TELEGRAM_NOTIFICATIONS", True):

                scheduler = MacroEventScheduler()
                scheduler.state_file = local_state_file

                with patch("daemon.macro_scheduler.send_telegram_message") as mock_send:
                    # Kilit meşgul olduğu için işlem reddedilmeli
                    res = scheduler.send_morning_briefing(force=False)
                    self.assertFalse(res)
                    mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
