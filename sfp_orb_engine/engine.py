"""
🌺 Begonya 00 - Ana Orkestrasyon ve Islem Motoru (Engine Core)
SFP + Hacim/ATR Anomalisi, ORB Seans Motoru, News Guard ve Outcome Tracker Koordinasyonu
"""

import time
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .config import (
    ACTIVE_SYMBOLS,
    PRIMARY_TIMEFRAME,
    SCAN_INTERVAL_SECONDS,
    SIGNAL_COOLDOWN_MINUTES,
    DATA_DIR,
    TELEMETRY_DIR,
    is_market_open,
    is_session_active_for_scan,
    EXCLUDED_SFP_SYMBOLS,
    WEEKEND_ORB_ENABLED,
)
from .data_provider import MarketDataProvider
from .volume_anomaly import VolumeAnomalyDetector
from .sfp_detector import SFPDetector
from .orb_detector import ORBDetector
from .macro_gate_client import MacroGateClient
from .chart_renderer import ChartRenderer
from .telegram_notifier import TelegramNotifier
from .news_guard import NewsGuard
from .outcome_tracker import OutcomeTracker

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Begonya00.Engine")

HISTORY_FILE = DATA_DIR / "signal_history.json"
RUNTIME_LOCK_FILE = DATA_DIR / "runtime.lock"


class BegonyaEngine:
    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or ACTIVE_SYMBOLS
        self.data_provider = MarketDataProvider()
        self.vol_detector = VolumeAnomalyDetector()
        self.sfp_detector = SFPDetector(volume_detector=self.vol_detector)
        self.orb_detector = ORBDetector(volume_detector=self.vol_detector)
        self.macro_client = MacroGateClient()
        self.chart_renderer = ChartRenderer()
        self.notifier = TelegramNotifier()
        self.news_guard = NewsGuard()
        self.outcome_tracker = OutcomeTracker(notifier=self.notifier)
        self.signal_history = self._load_history()
        self._is_running = True

    def _load_history(self) -> Dict[str, Any]:
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_history(self):
        try:
            HISTORY_FILE.write_text(json.dumps(self.signal_history, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Sinyal gecmisi kaydedilemedi: {e}")

    def _is_on_cooldown(self, symbol: str, strategy: str, direction: str, candle_time: Optional[str] = None) -> bool:
        # 1. Aynı bar/mum için TEKRAR ASLA sinyal gönderme (Kalıcı çift sinyal önleme)
        if candle_time:
            candle_key = f"{symbol}_{strategy}_{direction}_{candle_time}"
            if candle_key in self.signal_history:
                return True

        # 2. Zaman bazlı cooldown (30 dakika)
        key = f"{symbol}_{strategy}_{direction}"
        if key in self.signal_history:
            last_ts = self.signal_history[key].get("timestamp", 0)
            elapsed_min = (time.time() - last_ts) / 60.0
            if elapsed_min < SIGNAL_COOLDOWN_MINUTES:
                return True
        return False

    def _record_signal_in_history(self, symbol: str, strategy: str, direction: str, signal_data: Dict[str, Any]):
        key = f"{symbol}_{strategy}_{direction}"
        now_ts = time.time()
        record = {
            "timestamp": now_ts,
            "time_str": datetime.now().isoformat(),
            "signal": signal_data,
        }
        self.signal_history[key] = record

        candle_time = signal_data.get("candle_time") or signal_data.get("timestamp")
        if candle_time:
            candle_key = f"{symbol}_{strategy}_{direction}_{candle_time}"
            self.signal_history[candle_key] = record

        self._save_history()

    def _log_telemetry(self, event_type: str, payload: Dict[str, Any]):
        try:
            log_line = {
                "timestamp": datetime.now().isoformat(),
                "event": event_type,
                "data": payload,
            }
            log_file = TELEMETRY_DIR / "engine_telemetry.jsonl"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_line, default=str) + "\n")
        except Exception:
            pass

    def scan_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Tek bir sembol icin barlari ceker, haber kontrolu yapar, SFP & ORB tarar
        ve acik islemlerin kâr/zarar takibini gerceklestirir.
        """
        # 0. Toksik / Fazla Gürültü Üreten Parite Filtresi (GBPJPY, ETHUSD vb.)
        clean_sym = symbol.replace("/", "").replace("-", "").upper()
        if any(clean_sym == ex.replace("/", "").replace("-", "").upper() for ex in EXCLUDED_SFP_SYMBOLS):
            return None

        # 0b. Hafta Sonu & Kapalı Piyasa Koruması (Hafta sonu kapalı forex/hisse taranmaz)
        if not is_market_open(symbol):
            return None

        # 1. Kritik Haber Kalkanı (News Guard)
        news_check = self.news_guard.check_freeze(symbol)
        if news_check["is_frozen"]:
            logger.warning(f"🛡️ Haber Kalkanı Devrede: {symbol} - {news_check['reason']}")
            return None

        # 2. Canlı Bar Verisini Çek
        df = self.data_provider.fetch_candles(symbol, interval=PRIMARY_TIMEFRAME, outputsize=70)
        if df is None or len(df) < 25:
            return None

        # 3. Açık İşlemlerin TP1 / TP2 / SL Takibi (Outcome Tracker)
        last_bar_dict = df.iloc[-1].to_dict()
        self.outcome_tracker.check_trade_progress(symbol, last_bar_dict)

        # 3a. AKTİF POZİSYON KORUMASI: Bu paritede açık işlem sürerken mükerrer yeni işlem taranmaz!
        if self.outcome_tracker.has_active_trade(symbol):
            return None

        # 3b. Seans Taraması Kontrolü (Hafta İçi: Yalnızca Forex Londra 07-11 UTC / Hafta Sonu: Kripto 07-11 ve 13-17 UTC)
        if not is_session_active_for_scan(symbol):
            return None

        # 4. SFP + Hacim/ATR Anomalisi Taraması (PDH/PDL Öncelikli)
        sfp_res = self.sfp_detector.detect_sfp(df, symbol)
        if sfp_res:
            pool_lbl = sfp_res.get("pool_label", "Swing")
            logger.info(f"🎯 SFP Tespit Edildi: {symbol} -> {sfp_res['direction']} [{sfp_res['grade']} | {pool_lbl}]")
            self._process_candidate(df, sfp_res)
            return sfp_res

        # 5. ORB Seans Motoru Taraması
        # Hafta Sonu Kuralı: Hafta sonu kripto piyasasında düşük hacimli yatay bant nedeniyle
        # sahte kırılımları (fakeout) önlemek için ORB modeli kesin olarak devre dışıdır.
        # Hafta sonu YALNIZCA SFP (Likidite Avı & Hacim Anomalisi) modeli çalışır!
        dt_utc = datetime.now(timezone.utc)
        is_weekend = dt_utc.weekday() in [5, 6]
        if not is_weekend or WEEKEND_ORB_ENABLED:
            orb_res = self.orb_detector.detect_orb(df, symbol)
            if orb_res:
                logger.info(f"⚡ ORB Kırılımı Tespit Edildi: {symbol} -> {orb_res['direction']} [{orb_res['grade']}]")
                self._process_candidate(df, orb_res)
                return orb_res

        return None

    def _process_candidate(self, df, candidate: Dict[str, Any]):
        symbol = candidate["symbol"]
        strategy = candidate["strategy"]
        direction = candidate["direction"]

        # 0. Mum Bayatlık Kontrolü (45 dakikadan eski tetikleyici mumlar elenir)
        candle_dt = candidate.get("candle_time") or candidate.get("datetime")
        if candle_dt:
            try:
                c_time = pd.to_datetime(candle_dt)
                if c_time.tzinfo is not None:
                    c_time = c_time.tz_localize(None)
                now_utc = datetime.utcnow()
                age_minutes = (now_utc - c_time).total_seconds() / 60.0
                if age_minutes > 45:
                    logger.info(f"⏳ Bayat mum ({age_minutes:.1f} dk eski) sinyali elendi: {symbol} {strategy} {c_time}")
                    return
            except Exception:
                pass

        # 0b. Aktif Pozisyon Çift Kontrolü (Aynı sembolde ikinci açık pozisyon açılamaz)
        if self.outcome_tracker.has_active_trade(symbol):
            logger.info(f"🛡️ Aktif açık işlem var ({symbol}). Yeni sinyal reddedildi.")
            return

        # 0c. Karşı-Trend Kalkanı (Counter-Trend Filter)
        trend_align = candidate.get("trend_alignment")
        if trend_align == "COUNTER_TREND" and "Ultra" not in candidate.get("grade", ""):
            logger.info(f"🛡️ Karşı-Trend Engeli: {symbol} {strategy} {direction} ana trende zıt olduğu için elendi.")
            return

        # 0d. Yetersiz Risk Mesafesi Koruması (Sıfır Risk / Hatalı İğne Stop Engeli)
        entry_val = float(candidate.get("entry", 0.0))
        risk_val = float(candidate.get("risk_pips", 0.0))
        if entry_val <= 0 or risk_val <= 0 or (risk_val / entry_val) < 0.00002:
            logger.info(f"🛡️ Yetersiz Risk Mesafesi ({symbol} risk={risk_val}, entry={entry_val}). Elendi.")
            return

        # 1. Grade Filtresi (Yalnızca Grade A+ ve Üzeri: AAA ve A+ Sinyalleri Kabul Edilir)
        grade = candidate.get("grade", "B")
        if not (grade.startswith("AAA") or grade.startswith("A+")):
            logger.info(f"ℹ️ Grade A+ altı sinyal ({grade}) elendi: {symbol} {strategy} {direction}")
            return

        # 2. Cooldown ve Tekrarlayan Mum Kontrolü (Aynı muma 2. kez sinyal atılmaz)
        candle_time_str = str(candidate.get("candle_time") or candidate.get("timestamp") or "")
        if self._is_on_cooldown(symbol, strategy, direction, candle_time=candle_time_str):
            logger.info(f"⏳ Cooldown aktif ({symbol} {strategy} {direction}). Bildirim atlanıyor.")
            return

        # 3. Makro Yönetişim Kapısı Değerlendirmesi
        macro_eval = self.macro_client.evaluate_gate(symbol, direction)
        if not macro_eval["allowed"]:
            logger.warning(
                f"🛡️ Makro Kapı Engeli: {symbol} {direction} VETO edildi. Sebep: {macro_eval['reason']}"
            )
            self._log_telemetry("MACRO_VETO", {"signal": candidate, "macro_eval": macro_eval})
            return

        logger.info(f"✅ Makro Kapı Onayı Alındı: {symbol} | Risk Çarpanı: {macro_eval['risk_multiplier']}x")

        # 4. Yüksek Görünürlüklü İki Grafik Üretimi (15m Yapısal Görünüm + 1m Mikro İcra)
        # Hem 15m hem de 1m çizimleri Telegram'a swipeable albüm olarak tek mesajda iletilir!
        candidate_15m = dict(candidate)
        candidate_15m["render_tf"] = "15m (Yapısal Görünüm)"
        chart_15m_path = self.chart_renderer.render_signal_chart(df, candidate_15m, tag="15m")

        df_1m = self.data_provider.fetch_candles(symbol, interval="1m", outputsize=50)
        chart_1m_path = None
        if df_1m is not None and len(df_1m) >= 20:
            candidate_1m = dict(candidate)
            candidate_1m["render_tf"] = "1m (Mikro İcra)"
            chart_1m_path = self.chart_renderer.render_signal_chart(df_1m, candidate_1m, tag="1m")

        # 5. Telegram Bildirimi Gönderimi (15m + 1m Çift Grafik Albümü)
        notified = self.notifier.send_notification(
            candidate, macro_eval, chart_path=chart_15m_path, chart_1m_path=chart_1m_path
        )

        # 6. Canlı İşlem Takipçisine (Outcome Tracker) Kaydet
        self.outcome_tracker.register_trade(candidate)

        # 7. Geçmişe Kaydetme ve Telemetri
        self._record_signal_in_history(symbol, strategy, direction, candidate)
        self._log_telemetry("SIGNAL_DISPATCHED", {
            "signal": candidate,
            "macro_eval": macro_eval,
            "notified": notified,
            "chart_15m_path": str(chart_15m_path) if chart_15m_path else None,
            "chart_1m_path": str(chart_1m_path) if chart_1m_path else None,
        })

    def scan_universe(self) -> List[Dict[str, Any]]:
        """Aktif tüm evreni bir kere tarar."""
        findings = []
        for symbol in self.symbols:
            try:
                res = self.scan_symbol(symbol)
                if res:
                    findings.append(res)
            except Exception as e:
                logger.error(f"Sembol tarama hatası ({symbol}): {e}")
        return findings

    def run_loop(self):
        """Otonom sürekli çalışma döngüsü."""
        logger.info("=" * 65)
        logger.info("🌺 BEGONYA 00: KURUMSAL SFP (PDH/PDL) & ORB + NEWS GUARD AKTİF")
        logger.info(f"Takip Edilen Semboller: {len(self.symbols)} adet | Zaman Dilimi: {PRIMARY_TIMEFRAME}")
        logger.info(f"Tarama Aralığı: {SCAN_INTERVAL_SECONDS} sn | 0 API Maliyeti Modu")
        logger.info("=" * 65)

        # 1. Telegram ONLINE Bildirimi Gönder
        try:
            self.notifier.send_status_update(
                status="ONLINE",
                details="🟢 <b>Begonya 00 Canlı Tarama Motoru Aktif Edildi.</b>\n"
                        f"🎯 <b>Evren:</b> <code>{len(self.symbols)} Enstrüman</code> ({PRIMARY_TIMEFRAME})\n"
                        "🛡️ 4H Trend, 1M iFVG/Breaker ve Makro Kapı Filtreleri Nöbette."
            )
        except Exception as e:
            logger.warning(f"Telegram ONLINE bildirimi hatası: {e}")

        try:
            RUNTIME_LOCK_FILE.write_text(json.dumps({"pid": sys.platform, "started_at": datetime.now().isoformat()}), encoding="utf-8")
        except Exception:
            pass

        def sig_handler(signum, frame):
            logger.info("🛑 Durdurma sinyali alındı...")
            self._is_running = False

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        try:
            while self._is_running:
                start_t = time.time()
                try:
                    findings = self.scan_universe()
                    perf = self.outcome_tracker.get_performance_stats()
                    if perf["total_trades"] > 0:
                        logger.info(f"📊 Performans Durumu: {perf['total_trades']} İşlem | Win-Rate: %{perf['win_rate']} | Net R: {perf['total_r']}R")
                except Exception as e:
                    logger.error(f"Döngü hatası: {e}")

                elapsed = time.time() - start_t
                sleep_time = max(1.0, SCAN_INTERVAL_SECONDS - elapsed)
                time.sleep(sleep_time)
        finally:
            try:
                RUNTIME_LOCK_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            logger.info("Begonya 00 motoru güvenle sonlandırıldı.")
            # 2. Telegram OFFLINE Bildirimi Gönder
            try:
                self.notifier.send_status_update(
                    status="OFFLINE",
                    details="🔴 <b>Begonya 00 Canlı Motoru Kapatıldı / Çevrimdışı.</b>\n"
                            "⚠️ Otonom tarama ve canlı işlem takibi durduruldu."
                )
            except Exception as e:
                logger.warning(f"Telegram OFFLINE bildirimi hatası: {e}")
