"""
🌺 Begonya 00 - Otonom Islem Yasam Dongusu ve Sonuc Takipcesi (Outcome Tracker / Paper Ledger)
Sinyallerin TP1, TP2, Break-Even ve SL durumlarini canli takip eder ve Telegram'a guncelleme atar.
"""

import json
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .config import DATA_DIR, NOTIFY_TRADE_LIFECYCLE, is_market_open, round_price, is_crypto
from .telegram_notifier import TelegramNotifier
from . import config
from .execution_policy import utc_time, risk_rejection, NO_FILL_REASONS, TRT
from .entry_mechanics import is_slice_through_candle, evaluate_entry_candle_reaction

logger = logging.getLogger("Begonya00.OutcomeTracker")

ACTIVE_TRADES_FILE = DATA_DIR / "active_trades.json"
CLOSED_LEDGER_FILE = DATA_DIR / "trade_ledger.json"


def get_friction_config(symbol: str) -> Dict[str, float]:
    """
    Enstrümana göre piyasa sürtünme (Friction) katsayılarını döndürür:
    - spread_ratio: Fiyatın TP seviyesini aşması gereken asgari marj (oran olarak)
    - fee_r: İşlem başına komisyon + ortalama slipaj maliyeti (R cinsinden)
    """
    clean = symbol.replace("/", "").replace("-", "").upper()
    if is_crypto(symbol) or is_crypto(clean):
        return {"spread_ratio": 0.0004, "fee_r": 0.08}
    if "XAU" in clean or "GOLD" in clean:
        return {"spread_ratio": 0.0003, "fee_r": 0.08}
    return {"spread_ratio": 0.0002, "fee_r": 0.08}


class OutcomeTracker:
    def __init__(self, notifier: Optional[TelegramNotifier] = None):
        self.notifier = notifier or TelegramNotifier()
        self.active_trades = self._load_json(ACTIVE_TRADES_FILE)
        self.closed_trades = self._load_json(CLOSED_LEDGER_FILE)

    def has_active_trade(self, symbol: str) -> bool:
        """Belirtilen sembol icin su an aktif (PENDING_LIMIT, OPEN, TP1_HIT veya TRAILING_ACTIVE) pozisyon var mi?"""
        return any(t.get("symbol") == symbol and t.get("status") in ["PENDING_LIMIT", "OPEN", "TP1_HIT", "TRAILING_ACTIVE"] for t in self.active_trades)

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_json(self, path: Path, data: Any):
        try:
            import os
            import time
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            for attempt in range(5):
                try:
                    os.replace(tmp_path, path)
                    return
                except PermissionError:
                    time.sleep(0.05)
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Dosya kaydedilemedi ({path}): {e}")

    def register_trade(self, signal: Dict[str, Any], macro_eval=None):
        """Yeni acilan sinyali canli takip listesine ekler."""
        symbol = signal.get("symbol")
        strategy = signal.get("strategy")
        direction = signal.get("direction")
        entry = float(signal.get("entry", 0.0))
        sl = float(signal.get("stop_loss", 0.0))
        tp1 = float(signal.get("tp1", 0.0))
        tp2 = float(signal.get("tp2", 0.0))
        risk_pips = float(signal.get("risk_pips", 0.0))
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
            "tp1_r": abs(tp1-entry)/abs(entry-sl),
            "risk_pips": abs(entry - sl),
            "risk_multiplier": float((macro_eval or {}).get("risk_multiplier", 1.0)),
            "gate_bias": (macro_eval or {}).get("gate_bias"),
            "policy_version": config.EXECUTION_POLICY_VERSION,
            "zone_low": float(signal.get("zone_low", min(entry, sl))),
            "zone_high": float(signal.get("zone_high", max(entry, sl))),
            "rr_ratio": abs(tp2-entry)/abs(entry-sl),
            "status": "PENDING_LIMIT",  # "PENDING_LIMIT", "OPEN", "TP1_HIT", "TRAILING_ACTIVE", "CLOSED"
            "entry_candle_time": entry_candle_time,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "last_checked_at": datetime.now().isoformat(),
        }

        self.active_trades.append(trade)
        self._save_json(ACTIVE_TRADES_FILE, self.active_trades)
        logger.info(f"📝 Yeni emir limit takibe alindi (Retest Bekleniyor): {trade_id} ({symbol} {direction} @ {entry})")

    def check_trade_progress(self, symbol: str, current_bar: Dict[str, Any]):
        """Consume each completed UTC 1m bar once. Ambiguous OHLC exits use stop first.

        A penetrated resting limit is filled before reaction is evaluated.
        On its fill bar, stop has priority and targets are not credited. Failed
        reaction without a stop exits at close rather than erasing the fill.
        """
        bar_time = utc_time(current_bar["datetime"])
        event_time = bar_time + timedelta(minutes=1)
        if event_time > datetime.now(timezone.utc):
            return
        high, low, close, open_p = (float(current_bar[k]) for k in ("high", "low", "close", "open"))
        remaining = []
        for trade in self.active_trades:
            if trade["symbol"] != symbol:
                remaining.append(trade)
                continue
            opened = utc_time(trade["opened_at"], legacy_local=True)
            last = trade.get("last_processed_bar")
            if bar_time < opened or (last and bar_time <= utc_time(last)):
                remaining.append(trade)
                continue
            # Require an uninterrupted history, allowing only known market closure.
            expected = utc_time(last) + timedelta(minutes=1) if last else opened.replace(second=0, microsecond=0) + timedelta(minutes=1)
            if not last and opened.second == 0 and opened.microsecond == 0:
                expected = opened
            while expected < bar_time and not is_market_open(symbol, expected):
                expected += timedelta(minutes=1)
            if expected < bar_time:
                trade["tracking_gap_at"] = expected.isoformat()
                logger.warning("Missing 1m history for %s at %s; awaiting backfill", trade["id"], expected)
                remaining.append(trade)
                continue
            trade.pop("tracking_gap_at", None)
            trade["last_processed_bar"] = bar_time.isoformat()
            trade["last_checked_at"] = event_time.isoformat()
            long = trade["direction"] == "LONG"
            entry, sl = trade["entry"], trade["current_sl"]
            risk = abs(entry - trade["original_sl"])
            spread = entry * get_friction_config(symbol)["spread_ratio"]
            status = trade["status"]
            reason = None
            gross = 0.0
            if status == "PENDING_LIMIT":
                others = [t for t in self.active_trades if t is not trade]
                rejection = risk_rejection(self.closed_trades, others, symbol,
                    float(trade.get("risk_multiplier", 1.0)), event_time)
                touched = low <= entry - spread if long else high >= entry + spread
                expired = event_time >= opened + timedelta(minutes=15 * config.LIMIT_EXPIRY_BARS)
                if rejection:
                    reason = "RISK_LIMIT_CANCELLED"
                    trade["risk_rejection"] = rejection
                elif expired:
                    reason = "TIMEOUT_NO_FILL"
                elif touched:
                    # A resting limit cannot be cancelled retroactively after
                    # observing the fill candle's close. Record its penetration
                    # before evaluating stop/reaction. Targets in this candle
                    # remain uncredited because OHLC cannot establish ordering.
                    trade["status"] = "OPEN"
                    trade["filled_at"] = event_time.isoformat()
                    trade["fill_bar_started_at"] = bar_time.isoformat()
                    trade["fill_time_precision"] = "ONE_MINUTE_BAR"
                    trade["fill_model"] = "PASSIVE_LIMIT_PENETRATION_OHLC_CONSERVATIVE"
                    zone_low = trade.get("zone_low", min(entry, sl))
                    zone_high = trade.get("zone_high", max(entry, sl))
                    stop_touched = low <= sl if long else high >= sl
                    invalid = config.REQUIRE_ENTRY_REACTION and (
                        stop_touched or is_slice_through_candle(trade["direction"], open_p, high, low, close, zone_low, zone_high)
                        or not evaluate_entry_candle_reaction(trade["direction"], open_p, high, low, close, zone_low, zone_high))
                    if stop_touched:
                        reason, gross = "STOP_LOSS", -1.0
                    elif invalid:
                        # Reaction is only known now: flatten the filled trade
                        # at this close, with normal transaction costs.
                        reason = "ENTRY_REACTION_EXIT_FILLED"
                        gross = ((close - entry) if long else (entry - close)) / risk
                        trade["exit_price"] = close
                elif (high >= trade["tp1"] + spread if long else low <= trade["tp1"] - spread):
                    reason = "EXPIRED_NO_FILL"
            else:
                # OHLC cannot establish ordering. Use the stop already in force
                # at bar open before targets or a newly tightened stop.
                stop_hit = low <= sl if long else high >= sl
                tp2_hit = high >= trade["tp2"] + spread if long else low <= trade["tp2"] - spread
                tp1_hit = high >= trade["tp1"] + spread if long else low <= trade["tp1"] - spread
                tp1_r = abs(trade["tp1"] - entry) / risk
                if stop_hit:
                    if status == "OPEN":
                        reason, gross = "STOP_LOSS", -1.0
                    else:
                        reason = "TRAILING_STOP" if status == "TRAILING_ACTIVE" else "BREAK_EVEN"
                        gross = 0.5 * tp1_r + 0.5 * ((sl - entry) if long else (entry - sl)) / risk
                    trade["ambiguous_exit_bar"] = bool(tp2_hit or tp1_hit)
                elif tp2_hit:
                    reason = "TP2_HIT"
                    gross = 0.5 * tp1_r + 0.5 * abs(trade["tp2"] - entry) / risk
                elif tp1_hit and status == "OPEN":
                    trade.update(status="TP1_HIT", current_sl=entry, tp1_hit_at=event_time.isoformat())
                    self._notify_lifecycle(trade, "TP1", "Kapanmış 1m mumda TP1 teyit edildi; kalan yarının stopu girişte.")
                elif status == "TP1_HIT" and (high >= entry + 1.5*risk + spread if long else low <= entry - 1.5*risk - spread):
                    trade.update(status="TRAILING_ACTIVE", current_sl=entry + (0.75*risk if long else -0.75*risk), trailing_r=0.75)
                    self._notify_lifecycle(trade, "TRAILING_SL", "Kalan yarının stopu +0.75R seviyesinde; sonraki mumdan itibaren geçerli.")
            if reason:
                self._close_trade(trade, reason, gross, event_time)
            else:
                remaining.append(trade)
        self.active_trades = remaining
        self._save_json(ACTIVE_TRADES_FILE, remaining)

    def _close_trade(self, trade, reason, gross, event_time):
        fee = 0.0 if reason in NO_FILL_REASONS else get_friction_config(trade["symbol"])["fee_r"]
        net = round(gross - fee, 6)
        multiplier = float(trade.get("risk_multiplier", 1.0))
        trade.update(status="CLOSED", close_reason=reason, r_result=round(gross, 6),
                     gross_r=round(gross, 6), net_r=net, fee_r=fee,
                     weighted_net_r=round(net * multiplier, 6), closed_at=event_time.isoformat())
        self.closed_trades.append(trade)
        self._save_json(CLOSED_LEDGER_FILE, self.closed_trades)
        logger.info("Trade closed: %s -> %s (%+.3fR)", trade["id"], reason, net)
        if reason not in NO_FILL_REASONS:
            self._notify_lifecycle(trade, reason, f"Net sonuç: {net:+.3f}R; risk çarpanlı: {net * multiplier:+.3f}R")

    def get_monthly_counters(self, current_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """O anki aya ait TP1, TP2, BE ve SL sayaclarini hem Brut hem de Net R performansini dondurur."""
        if current_dt is None:
            current_dt = datetime.now()
        month_key = current_dt.strftime("%Y-%m")

        month_closed = [
            t for t in self.closed_trades
            if utc_time(t.get("closed_at") or t["opened_at"], legacy_local=True).astimezone(TRT).strftime("%Y-%m") == month_key
        ]

        sl_count = sum(1 for t in month_closed if t.get("close_reason") == "STOP_LOSS")
        be_count = sum(1 for t in month_closed if t.get("close_reason") in ["BREAK_EVEN", "TRAILING_STOP"])
        tp2_count = sum(1 for t in month_closed if t.get("close_reason") == "TP2_HIT")

        active_tp1 = sum(
            1 for t in self.active_trades
            if t.get("status") in ["TP1_HIT", "TRAILING_ACTIVE"] and utc_time(t["opened_at"], legacy_local=True).astimezone(TRT).strftime("%Y-%m") == month_key
        )
        closed_tp1 = sum(
            1 for t in month_closed
            if t.get("close_reason") in ["BREAK_EVEN", "TP2_HIT", "TRAILING_STOP"] or t.get("tp1_hit") or t.get("tp1_hit_at")
        )
        tp1_count = active_tp1 + closed_tp1

        valid_closed = [t for t in month_closed if t.get("close_reason") not in NO_FILL_REASONS]
        closed_gross_r = sum(float(t.get("gross_r", t.get("r_result", 0.0))) for t in valid_closed)
        closed_net_r = sum(float(t.get("net_r", float(t.get("r_result", 0.0)) - 0.08)) for t in valid_closed)

        active_locked_gross_r = sum(
            round(float(t.get("tp1_r", 1.0)) * 0.5, 2)
            for t in self.active_trades
            if t.get("status") in ["TP1_HIT", "TRAILING_ACTIVE"] and utc_time(t["opened_at"], legacy_local=True).astimezone(TRT).strftime("%Y-%m") == month_key
        )
        active_locked_net_r = sum(
            round((float(t.get("tp1_r", 1.0)) * 0.5) - 0.04, 2)
            for t in self.active_trades
            if t.get("status") in ["TP1_HIT", "TRAILING_ACTIVE"] and utc_time(t["opened_at"], legacy_local=True).astimezone(TRT).strftime("%Y-%m") == month_key
        )

        total_gross_r = round(closed_gross_r + active_locked_gross_r, 2)
        total_net_r = round(closed_net_r + active_locked_net_r, 2)

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
            "gross_r": round(closed_gross_r, 2),
            "net_r": round(closed_net_r, 2),
            "weighted_net_r": round(sum(t["weighted_net_r"] for t in valid_closed if "weighted_net_r" in t), 6),
            "weighted_trade_count": sum("weighted_net_r" in t for t in valid_closed),
            "total_gross_r": total_gross_r,
            "total_net_r": total_net_r,
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
        elif event_type == "TRAILING_SL":
            title = f"📈 İZ SÜREN STOP AKTİF! (Kâr Koruma)"
        elif event_type == "TRAILING_STOP":
            title = f"🏆 İZ SÜREN STOPLA KAPANDI! (+{trade.get('net_r', trade.get('r_result'))}R Net)"
        elif event_type == "TP2_HIT":
            title = f"🏆 TAM KAZANÇ (TP2)! (Bu Ayın {counters['tp2_count']}. Tam Hedefi)"
        elif event_type == "BREAK_EVEN":
            title = f"🛡️ BAŞABAŞ KAPANDI (BE)! (Bu Ayın {counters['be_count']}. BE'si)"
        elif event_type == "STOP_LOSS":
            title = f"🛑 STOP LOSS OLDU! (Bu Ayın {counters['sl_count']}. Stop'u)"
        else:
            title = event_type

        curr_sl = trade.get("current_sl", trade.get("original_sl", 0.0))
        entry_p = trade.get("entry", 0.0)
        tp1_p = trade.get("tp1", 0.0)
        tp2_p = trade.get("tp2", 0.0)
        st = trade.get("status", "OPEN")

        if st == "TRAILING_ACTIVE":
            sl_badge = f"🔒 Kilitli Kârda (+{trade.get('trailing_r', 0.75)}R)"
        elif st == "TP1_HIT":
            sl_badge = "🛡️ 0 Risk (Girişte / Başabaş)"
        else:
            sl_badge = "⚠️ Başlangıç SL"

        lines = [
            "🌺 <b>BEGONYA 00 | İŞLEM GÜNCELLEMESİ</b>",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"<b>DURUM:</b> {title}",
            f"🎯 <b>ENSTRÜMAN:</b> <code>{trade['symbol']}</code> ({trade['direction']})",
            f"📌 <b>GİRİŞ:</b> <code>{entry_p}</code> | <b>GÜNCEL SL:</b> <code>{curr_sl}</code> ({sl_badge})",
            f"🎯 <b>HEDEF 1:</b> <code>{tp1_p}</code> | <b>HEDEF 2 (TP2):</b> <code>{tp2_p}</code>",
            f"ℹ️ <b>AÇIKLAMA:</b> {details}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>AYLIK RESMİ SAYAÇ ({counters['month_display']}):</b>",
            f"🎯 <b>TP (Hedef):</b> <code>{counters['tp1_count']}</code> (Tam TP2: <code>{counters['tp2_count']}</code>)",
            f"🛡️ <b>BE / Kâr Stopu:</b> <code>{counters['be_count']}</code>",
            f"🛑 <b>SL (Stop Loss):</b> <code>{counters['sl_count']}</code>",
            f"📈 <b>Brüt Sonuç (işlem R toplamı):</b> <code>{counters['gross_r']:+.2f}R</code>",
            f"💰 <b>Net Sonuç (işlem R toplamı):</b> <code>{counters['net_r']:+.2f}R</code>",
            f"🔒 <b>Açık Kilitli Dahil Net Sonuç:</b> <code>{counters['total_net_r']:+.2f}R</code>",
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
        valid = [t for t in self.closed_trades if t.get("close_reason") not in NO_FILL_REASONS]
        total = len(valid)
        if total == 0:
            return {"total_trades": 0, "win_rate": 0.0, "total_r": 0.0}

        wins = sum(1 for t in valid if t.get("r_result", 0.0) > 0)
        losses = sum(1 for t in valid if t.get("r_result", 0.0) < 0)
        total_r = sum(t.get("net_r", t.get("r_result", 0.0)) for t in valid)
        win_rate = round((wins / total) * 100, 1)

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "total_r": round(total_r, 2),
        }
