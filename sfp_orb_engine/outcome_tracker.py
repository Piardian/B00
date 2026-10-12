"""
🌺 Begonya 00 - Otonom Islem Yasam Dongusu ve Sonuc Takipcesi (Outcome Tracker / Paper Ledger)
Sinyallerin TP1, TP2, Break-Even ve SL durumlarini canli takip eder ve Telegram'a guncelleme atar.
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, NOTIFY_TRADE_LIFECYCLE, is_market_open, round_price
from .telegram_notifier import TelegramNotifier

logger = logging.getLogger("Begonya00.OutcomeTracker")

ACTIVE_TRADES_FILE = DATA_DIR / "active_trades.json"
CLOSED_LEDGER_FILE = DATA_DIR / "trade_ledger.json"


class OutcomeTracker:
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier or TelegramNotifier()
        self.active_trades = self._load_json(ACTIVE_TRADES_FILE)
        self.closed_trades = self._load_json(CLOSED_LEDGER_FILE)

    def has_active_trade(self, symbol: str) -> bool:
        """Belirtilen sembol icin su an aktif acik (OPEN veya TP1_HIT) pozisyon var mi?"""
        return any(t.get("symbol") == symbol and t.get("status") in ["OPEN", "TP1_HIT"] for t in self.active_trades)

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_json(self, path: Path, data: Any):
        try:
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Dosya kaydedilemedi ({path}): {e}")

    def register_trade(self, signal: Dict[str, Any]):
        """Yeni acilan sinyali canli takip listesine ekler."""
        symbol = signal.get("symbol")
        strategy = signal.get("strategy")
        direction = signal.get("direction")
        entry = round_price(float(signal.get("entry", 0.0)))
        sl = round_price(float(signal.get("stop_loss", 0.0)))
        tp1 = round_price(float(signal.get("tp1", 0.0)))
        tp2 = round_price(float(signal.get("tp2", 0.0)))
        risk_pips = round_price(float(signal.get("risk_pips", 0.0)))
        rr = float(signal.get("rr_ratio", 2.5))
        entry_candle_time = str(signal.get("datetime") or signal.get("candle_time") or "")

        trade_id = f"{symbol.replace('/', '')}_{int(time.time())}"

        trade = {
            "id": trade_id,
            "symbol": symbol,
            "strategy": strategy,
            "direction": direction,
            "grade": signal.get("grade", "A"),
            "entry": entry,
            "original_sl": sl,
            "current_sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp1_r": float(signal.get("tp1_r", 1.0)),
            "risk_pips": risk_pips,
            "rr_ratio": rr,
            "status": "OPEN",  # "OPEN", "TP1_HIT", "CLOSED"
            "entry_candle_time": entry_candle_time,
            "opened_at": datetime.now().isoformat(),
            "last_checked_at": datetime.now().isoformat(),
        }

        self.active_trades.append(trade)
        self._save_json(ACTIVE_TRADES_FILE, self.active_trades)
        logger.info(f"📝 Yeni islem takibe alindi: {trade_id} ({symbol} {direction}) [Giris Mum: {entry_candle_time}]")

    def check_trade_progress(self, symbol: str, current_bar: Dict[str, Any]):
        """
        Gelen son bar ile sembolun acik pozisyonlarini kontrol eder.
        Giris mumu icindeyken gecmis fitillere (hayali stoplara) carpilmamasi icin
        anlik close fiyatindan degerlendirme yapilir.
        """
        if not is_market_open(symbol):
            return

        high = float(current_bar.get("high", 0.0))
        low = float(current_bar.get("low", 0.0))
        close = float(current_bar.get("close", 0.0))
        bar_dt_str = str(current_bar.get("datetime") or "")

        remaining_trades = []

        for trade in self.active_trades:
            if trade["symbol"] != symbol or trade["status"] == "CLOSED":
                remaining_trades.append(trade)
                continue

            direction = trade["direction"]
            entry = trade["entry"]
            current_sl = trade["current_sl"]
            tp1 = trade["tp1"]
            tp2 = trade["tp2"]
            status = trade["status"]
            entry_candle_time = trade.get("entry_candle_time", "")

            # HAYALI STOP KORUMASI:
            # Eger henuz islemin acildigi giris mumu devam ediyorsa, islemin acilisindan once
            # olusmus gecmis fitillere (high/low) bakilmaz; anlik canli fiyata (close) bakilir!
            is_entry_bar = bool(entry_candle_time and bar_dt_str == entry_candle_time)
            eval_high = close if is_entry_bar else high
            eval_low = close if is_entry_bar else low

            trade["last_checked_at"] = datetime.now().isoformat()
            closed = False
            close_reason = ""
            r_result = 0.0

            tp1_r = float(trade.get("tp1_r", 1.0))
            tp2_r = float(trade.get("rr_ratio", 3.0))
            be_r = round(tp1_r * 0.5, 2)
            full_win_r = round((tp1_r * 0.5) + (tp2_r * 0.5), 2)

            event_type = ""
            event_details = ""

            # 1. LONG ISLEM KONTROLU
            if direction == "LONG":
                # TP2 Vuruldu mu? (Tam Kazanc)
                if eval_high >= tp2:
                    closed = True
                    close_reason = "TP2_HIT"
                    r_result = full_win_r
                    event_type = "TP2_HIT"
                    event_details = f"+{full_win_r}R Net Kâr Alındı! (%50 @ {tp1_r}R + %50 @ {tp2_r}R)"

                # TP1 Vuruldu mu? (Kısmi Kâr & Break-Even)
                elif eval_high >= tp1 and status == "OPEN":
                    trade["status"] = "TP1_HIT"
                    trade["tp1_hit_at"] = datetime.now().isoformat()
                    trade["current_sl"] = entry  # Stop'u basabasa cek
                    self._save_json(ACTIVE_TRADES_FILE, self.active_trades)
                    self._notify_lifecycle(
                        trade,
                        event_type="TP1",
                        details=f"Pozisyonun %50'si kapatıldı (+{be_r}R cepte), Stop Giriş Fiyatına (BE) çekildi!"
                    )

                # SL Vuruldu mu?
                elif eval_low <= current_sl:
                    closed = True
                    if status == "TP1_HIT":
                        close_reason = "BREAK_EVEN"
                        r_result = be_r  # TP1'de alınan %50 kâr cepte kaldı
                        event_type = "BREAK_EVEN"
                        event_details = f"TP1 sonrası kalan parça girişte kapandı. Net Kazanç: +{be_r}R"
                    else:
                        close_reason = "STOP_LOSS"
                        r_result = -1.0
                        event_type = "STOP_LOSS"
                        event_details = f"-1.0R Kayıp ({trade['risk_pips']} pip)"

            # 2. SHORT ISLEM KONTROLU
            elif direction == "SHORT":
                if eval_low <= tp2:
                    closed = True
                    close_reason = "TP2_HIT"
                    r_result = full_win_r
                    event_type = "TP2_HIT"
                    event_details = f"+{full_win_r}R Net Kâr Alındı! (%50 @ {tp1_r}R + %50 @ {tp2_r}R)"

                elif eval_low <= tp1 and status == "OPEN":
                    trade["status"] = "TP1_HIT"
                    trade["tp1_hit_at"] = datetime.now().isoformat()
                    trade["current_sl"] = entry
                    self._save_json(ACTIVE_TRADES_FILE, self.active_trades)
                    self._notify_lifecycle(
                        trade,
                        event_type="TP1",
                        details=f"Pozisyonun %50'si kapatıldı (+{be_r}R cepte), Stop Giriş Fiyatına (BE) çekildi!"
                    )

                elif eval_high >= current_sl:
                    closed = True
                    if status == "TP1_HIT":
                        close_reason = "BREAK_EVEN"
                        r_result = be_r
                        event_type = "BREAK_EVEN"
                        event_details = f"TP1 sonrası kalan parça girişte kapandı. Net Kazanç: +{be_r}R"
                    else:
                        close_reason = "STOP_LOSS"
                        r_result = -1.0
                        event_type = "STOP_LOSS"
                        event_details = f"-1.0R Kayıp ({trade['risk_pips']} pip)"

            if closed:
                trade["status"] = "CLOSED"
                trade["close_reason"] = close_reason
                trade["r_result"] = r_result
                trade["closed_at"] = datetime.now().isoformat()
                self.closed_trades.append(trade)
                self._save_json(CLOSED_LEDGER_FILE, self.closed_trades)
                logger.info(f"🏁 Islem kapandi: {trade['id']} -> {close_reason} ({r_result}R)")
                if event_type:
                    self._notify_lifecycle(trade, event_type=event_type, details=event_details)
            else:
                remaining_trades.append(trade)

        self.active_trades = remaining_trades
        self._save_json(ACTIVE_TRADES_FILE, self.active_trades)

    def get_monthly_counters(self, current_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """O anki aya ait TP1, TP2, BE ve SL sayaclarini ve net R performansini dondurur."""
        if current_dt is None:
            current_dt = datetime.now()
        month_key = current_dt.strftime("%Y-%m")

        month_closed = [
            t for t in self.closed_trades
            if (t.get("closed_at") or t.get("opened_at", ""))[:7] == month_key
        ]

        sl_count = sum(1 for t in month_closed if t.get("close_reason") == "STOP_LOSS")
        be_count = sum(1 for t in month_closed if t.get("close_reason") == "BREAK_EVEN")
        tp2_count = sum(1 for t in month_closed if t.get("close_reason") == "TP2_HIT")

        active_tp1 = sum(
            1 for t in self.active_trades
            if t.get("status") == "TP1_HIT" and (t.get("opened_at", ""))[:7] == month_key
        )
        closed_tp1 = sum(
            1 for t in month_closed
            if t.get("close_reason") in ["BREAK_EVEN", "TP2_HIT"] or t.get("tp1_hit") or t.get("tp1_hit_at")
        )
        tp1_count = active_tp1 + closed_tp1

        net_r = sum(float(t.get("r_result", 0.0)) for t in month_closed)

        tr_months = {
            1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
            7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
        }
        month_display = f"{tr_months.get(current_dt.month, '')} {current_dt.year}".strip()

        return {
            "month_display": month_display,
            "month_key": month_key,
            "tp1_count": tp1_count,
            "tp2_count": tp2_count,
            "be_count": be_count,
            "sl_count": sl_count,
            "net_r": round(net_r, 2),
        }

    def _notify_lifecycle(self, trade: Dict[str, Any], event_type: str, details: str):
        """Telegram'a anlik canli durum guncellemesi ve aylik TP/BE/SL sayaci atar."""
        if not NOTIFY_TRADE_LIFECYCLE:
            return

        if not self.notifier.is_configured():
            return

        counters = self.get_monthly_counters()

        # Olay tipine gore baslik ve sira belirle
        if event_type == "TP1":
            title = f"🎉 HEDEF 1 (TP1) VURULDU! (Bu Ayın {counters['tp1_count']}. TP'si)"
        elif event_type == "TP2_HIT":
            title = f"🏆 TAM KAZANÇ (TP2)! (Bu Ayın {counters['tp2_count']}. Tam Hedefi)"
        elif event_type == "BREAK_EVEN":
            title = f"🛡️ BAŞABAŞ KAPANDI (BE)! (Bu Ayın {counters['be_count']}. BE'si)"
        elif event_type == "STOP_LOSS":
            title = f"🛑 STOP LOSS OLDU! (Bu Ayın {counters['sl_count']}. Stop'u)"
        else:
            title = event_type

        lines = [
            "🌺 <b>BEGONYA 00 | İŞLEM GÜNCELLEMESİ</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"<b>DURUM:</b> {title}",
            f"🎯 <b>ENSTRÜMAN:</b> <code>{trade['symbol']}</code> ({trade['direction']})",
            f"📌 <b>GİRİŞ:</b> <code>{trade['entry']}</code>",
            f"ℹ️ <b>AÇIKLAMA:</b> {details}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>AYLIK SAYAÇ ({counters['month_display']}):</b>",
            f"🎯 <b>TP (Hedef):</b> <code>{counters['tp1_count']}</code> (Tam TP2: <code>{counters['tp2_count']}</code>)",
            f"🛡️ <b>BE (Başabaş):</b> <code>{counters['be_count']}</code>",
            f"🛑 <b>SL (Stop Loss):</b> <code>{counters['sl_count']}</code>",
            f"📈 <b>Aylık Net Kasa:</b> <code>{counters['net_r']:+.2f}R</code>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"⏰ <i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} TRT</i>",
        ]
        msg = "\n".join(lines)
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.notifier.token}/sendMessage"
            requests.post(url, json={"chat_id": self.notifier.chat_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            logger.error(f"Telegram durum guncellemesi hatasi: {e}")

    def get_performance_stats(self) -> Dict[str, Any]:
        """Kapanmis tum islemlerin Win-Rate ve R istatistiklerini hesaplar."""
        total = len(self.closed_trades)
        if total == 0:
            return {"total_trades": 0, "win_rate": 0.0, "total_r": 0.0}

        wins = sum(1 for t in self.closed_trades if t.get("r_result", 0.0) > 0)
        losses = sum(1 for t in self.closed_trades if t.get("r_result", 0.0) < 0)
        total_r = sum(t.get("r_result", 0.0) for t in self.closed_trades)
        win_rate = round((wins / total) * 100, 1)

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_r": round(total_r, 2),
        }
