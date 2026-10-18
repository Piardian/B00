"""
🌺 Begonya 00 - Hibrit İntikal ve Performans Karşılaştırma Modülü (Hybrid Tracker)
Kullanıcının canlı LTF filtreleri, teyitleri ve manuel kararlarını
botun mekanik trade_ledger.json verisiyle birebir aynı şemada kaydeder ve
karşılaştırmalı performans karnesi üretir.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, round_price

logger = logging.getLogger("Begonya00.HybridTracker")

HYBRID_LEDGER_FILE = DATA_DIR / "hybrid_ledger.json"
CLOSED_LEDGER_FILE = DATA_DIR / "trade_ledger.json"


class HybridTracker:
    def __init__(self):
        self.hybrid_trades = self._load_json(HYBRID_LEDGER_FILE)
        self.bot_trades = self._load_json(CLOSED_LEDGER_FILE)

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Dosya okunamadı ({path}): {e}")
        return []

    def _save_json(self, path: Path, data: Any):
        try:
            path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Dosya kaydedilemedi ({path}): {e}")

    def record_user_trade(
        self,
        symbol: str,
        user_action: str,  # "ENTERED", "SKIPPED", "PARTIAL"
        user_close_reason: str,  # "TP2_HIT", "TP1_HIT", "STOP_LOSS", "BREAK_EVEN", "SKIPPED_NO_CONFIRM", "RUNNER_ACTIVE"
        user_r: float,
        user_notes: str = "",
        ltf_confirmation: bool = True,
        bot_trade_id: Optional[str] = None,
        custom_params: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Kullanıcıdan gelen bir hibrit işlemi kaydeder.
        Eğer bot_trade_id verilmişse veya son eşleşen bot işlemi varsa,
        botun mekanik verileriyle (entry, sl, tp, grade) tam eşleme yapar.
        """
        bot_ref = None
        if bot_trade_id:
            bot_ref = next((t for t in reversed(self.bot_trades) if t.get("id") == bot_trade_id), None)
        elif symbol:
            # En son aynı semboldeki bot işlemini bul
            bot_ref = next((t for t in reversed(self.bot_trades) if t.get("symbol") == symbol), None)

        now_iso = datetime.now().isoformat()
        custom_params = custom_params or {}

        if status is None:
            calc_status = "CLOSED" if user_action == "ENTERED" else "SKIPPED"
        else:
            calc_status = status

        if bot_ref:
            trade_id = f"{bot_ref.get('id')}_USER"
            trade_obj = {
                "id": trade_id,
                "bot_trade_id": bot_ref.get("id"),
                "symbol": bot_ref.get("symbol"),
                "strategy": bot_ref.get("strategy"),
                "direction": bot_ref.get("direction"),
                "grade": bot_ref.get("grade"),
                "entry": bot_ref.get("entry"),
                "original_sl": bot_ref.get("original_sl"),
                "current_sl": bot_ref.get("current_sl"),
                "tp1": bot_ref.get("tp1"),
                "tp2": bot_ref.get("tp2"),
                "tp1_r": bot_ref.get("tp1_r", 1.0),
                "risk_pips": bot_ref.get("risk_pips"),
                "rr_ratio": bot_ref.get("rr_ratio"),
                "status": calc_status,
                "executed_by": "USER_HYBRID",
                "entry_candle_time": bot_ref.get("entry_candle_time"),
                "opened_at": bot_ref.get("opened_at"),
                "last_checked_at": now_iso,
                "close_reason": user_close_reason,
                "r_result": float(user_r),
                "closed_at": now_iso if calc_status == "CLOSED" else None,
                "user_execution": {
                    "action": user_action,
                    "ltf_confirmation": ltf_confirmation,
                    "user_notes": user_notes,
                },
                "comparison": {
                    "bot_close_reason": bot_ref.get("close_reason"),
                    "bot_r_result": float(bot_ref.get("r_result", 0.0)),
                    "user_close_reason": user_close_reason,
                    "user_r_result": float(user_r),
                    "diff_r": round(float(user_r) - float(bot_ref.get("r_result", 0.0)), 2),
                },
            }
        else:
            # Tamamen manuel bağımsız kullanıcı işlemi
            clean_sym = symbol.replace("/", "")
            trade_id = f"{clean_sym}_{int(datetime.now().timestamp())}_USER"
            entry = float(custom_params.get("entry", 0.0))
            sl = float(custom_params.get("sl", 0.0))
            tp1 = float(custom_params.get("tp1", 0.0))
            tp2 = float(custom_params.get("tp2", 0.0))

            trade_obj = {
                "id": trade_id,
                "bot_trade_id": None,
                "symbol": symbol,
                "strategy": custom_params.get("strategy", "MANUAL_SMC"),
                "direction": custom_params.get("direction", "UNKNOWN"),
                "grade": custom_params.get("grade", "MANUAL"),
                "entry": entry,
                "original_sl": sl,
                "current_sl": sl,
                "tp1": tp1,
                "tp2": tp2,
                "tp1_r": float(custom_params.get("tp1_r", 1.0)),
                "risk_pips": float(custom_params.get("risk_pips", 0.0)),
                "rr_ratio": float(custom_params.get("rr_ratio", 2.0)),
                "status": "CLOSED" if user_action == "ENTERED" else "SKIPPED",
                "executed_by": "USER_DISCRETIONARY",
                "entry_candle_time": custom_params.get("entry_candle_time", now_iso),
                "opened_at": custom_params.get("opened_at", now_iso),
                "last_checked_at": now_iso,
                "close_reason": user_close_reason,
                "r_result": float(user_r),
                "closed_at": now_iso,
                "user_execution": {
                    "action": user_action,
                    "ltf_confirmation": ltf_confirmation,
                    "user_notes": user_notes,
                },
                "comparison": {
                    "bot_close_reason": "NO_BOT_TRADE",
                    "bot_r_result": 0.0,
                    "user_close_reason": user_close_reason,
                    "user_r_result": float(user_r),
                    "diff_r": float(user_r),
                },
            }

        # Varsa eskisiyle güncelle veya yeni ekle
        existing_idx = next((i for i, t in enumerate(self.hybrid_trades) if t.get("id") == trade_id), None)
        if existing_idx is not None:
            self.hybrid_trades[existing_idx] = trade_obj
        else:
            self.hybrid_trades.append(trade_obj)

        self._save_json(HYBRID_LEDGER_FILE, self.hybrid_trades)
        logger.info(f"✅ Kullanıcı hibrit işlemi kaydedildi: {trade_id} -> {user_close_reason} ({user_r}R)")
        return trade_obj

    def generate_comparison_summary(self) -> Dict[str, Any]:
        """Bot ile Kullanıcı arasındaki karşılaştırmalı istatistikleri üretir."""
        self.hybrid_trades = self._load_json(HYBRID_LEDGER_FILE)
        self.bot_trades = self._load_json(CLOSED_LEDGER_FILE)

        user_entered = [t for t in self.hybrid_trades if t.get("user_execution", {}).get("action") == "ENTERED"]
        user_skipped = [t for t in self.hybrid_trades if t.get("user_execution", {}).get("action") == "SKIPPED"]

        # Kullanıcı metrikleri
        user_wins = [t for t in user_entered if t.get("r_result", 0.0) > 0]
        user_losses = [t for t in user_entered if t.get("r_result", 0.0) < 0]
        user_net_r = sum(float(t.get("r_result", 0.0)) for t in self.hybrid_trades)
        user_win_rate = (len(user_wins) / len(user_entered) * 100) if user_entered else 0.0

        # Eşleşen bot işlemleri
        bot_matched_ids = [t.get("bot_trade_id") for t in self.hybrid_trades if t.get("bot_trade_id")]
        matched_bot_trades = [t for t in self.bot_trades if t.get("id") in bot_matched_ids]

        bot_wins = [t for t in matched_bot_trades if float(t.get("r_result", 0.0)) > 0]
        bot_losses = [t for t in matched_bot_trades if float(t.get("r_result", 0.0)) < 0]
        bot_net_r = sum(float(t.get("r_result", 0.0)) for t in matched_bot_trades)
        bot_win_rate = (len(bot_wins) / len(matched_bot_trades) * 100) if matched_bot_trades else 0.0

        # Filtreleme Başarısı (Kurtarılan R)
        saved_r = sum(
            abs(float(t.get("comparison", {}).get("bot_r_result", 0.0)))
            for t in user_skipped
            if float(t.get("comparison", {}).get("bot_r_result", 0.0)) < 0
        )

        return {
            "total_signals_evaluated": len(self.hybrid_trades),
            "user": {
                "entered_trades": len(user_entered),
                "skipped_trades": len(user_skipped),
                "wins": len(user_wins),
                "losses": len(user_losses),
                "win_rate": round(user_win_rate, 1),
                "net_r": round(user_net_r, 2),
                "saved_r": round(saved_r, 2),
            },
            "bot_matched": {
                "total_trades": len(matched_bot_trades),
                "wins": len(bot_wins),
                "losses": len(bot_losses),
                "win_rate": round(bot_win_rate, 1),
                "net_r": round(bot_net_r, 2),
            },
            "synergy_diff_r": round(user_net_r - bot_net_r, 2),
            "trades": self.hybrid_trades,
        }


if __name__ == "__main__":
    tracker = HybridTracker()
    summary = tracker.generate_comparison_summary()
    print("\n" + "=" * 60)
    print("[BEGONYA 00] HIBRIT vs MEKANIK BOT KARSILASTIRMA RAPORU")
    print("=" * 60)
    print(f"Toplam Degerlendirilen Sinyal : {summary['total_signals_evaluated']}")
    print(f"[*] Bot (Mekanik) Net R        : +{summary['bot_matched']['net_r']}R (Win Rate: %{summary['bot_matched']['win_rate']})")
    print(f"[+] Sen (Hibrit/LTF) Net R     : +{summary['user']['net_r']}R (Win Rate: %{summary['user']['win_rate']})")
    print(f"[v] Filtreleme ile Kurtarilan  : +{summary['user']['saved_r']}R (Zarardan Korunma)")
    print(f"[!] Hibrit Alfa Farki          : +{summary['synergy_diff_r']}R")
    print("-" * 60)
