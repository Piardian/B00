"""
🌺 Begonya 00 - Telegram Bildirim ve Islem Karti Modulu
Detayli Checklist Karti & Grafik Kaniti Gonderimi
"""

import requests
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger("Begonya00.Telegram")


class TelegramNotifier:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID

    def is_configured(self) -> bool:
        return bool(self.token and self.chat_id)

    def format_card(self, signal: Dict[str, Any], macro_eval: Dict[str, Any]) -> str:
        """
        Sinyal ve makro sonucunu Begonya & CLT hibrit 1M onay kartina donusturur.
        """
        strategy = signal.get("strategy", "UNKNOWN")
        direction = signal.get("direction", "LONG")
        symbol = signal.get("symbol", "ASSET")
        grade = signal.get("grade", "A+")
        entry = signal.get("entry", 0.0)
        sl = signal.get("stop_loss", 0.0)
        tp1 = signal.get("tp1", 0.0)
        tp2 = signal.get("tp2", 0.0)
        risk_pips = signal.get("risk_pips", 0.0)
        rr = signal.get("rr_ratio", 2.0)

        dir_icon = "🟢 LONG (ALIM GÖZLEM)" if direction == "LONG" else "🔴 SHORT (SATIM GÖZLEM)"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        regime = macro_eval.get("regime", "Makro Rejim")
        gate_bias = macro_eval.get("gate_bias", "NEUTRAL_RANGE")
        risk_mult = macro_eval.get("risk_multiplier", 1.0)

        lines = [
            "🌺 <b>BEGONYA 00 - HİBRİT RADAR ALARMI</b>",
            "📦 <b>KUTU TEST EDİLDİ - 1M ONAY SENDE!</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            f"🎯 <b>{symbol}</b> | {dir_icon} [{grade}]",
            f"⏰ <b>Zaman:</b> {now_str} TRT",
        ]

        if strategy == "SFP_VOLUME_ANOMALY" or "SFP" in strategy:
            vol_info = signal.get("volume_analysis", {})
            spike_ratio = vol_info.get("spike_ratio", 1.0)
            tier = vol_info.get("tier", "NORMAL")
            swept_lvl = signal.get("swept_level", 0.0)
            pool_label = signal.get("pool_label", "Likidite Seviyesi")
            wick_ratio = signal.get("sweep_wick_ratio", 0.0)
            tp1_note = signal.get("tp1_note", "1.5R")
            tp2_note = signal.get("tp2_note", f"{rr}R")

            lines.extend([
                f"📊 <b>Model:</b> SFP Likidite Avı [{grade}]",
                f"🎯 <b>Süpürülen Havuz:</b> 💎 <b>{pool_label}</b> (<code>{swept_lvl}</code>)",
                f"⚡ <b>Reaksiyon:</b> %{round(wick_ratio * 100, 1)} Fitil | {spike_ratio}x Hacim [{tier}]",
                "━━━━━━━━━━━━━━━━━━━━",
                "📋 <b>CHECKLIST:</b>",
                f"• Makro Kapı: ✅ <b>PASS</b> ({gate_bias})",
                "• HTF Likidite: ✅ <b>PASS</b> (Sweep Onaylandı)",
                "• 1M LTF Onayı: ⏳ <b>BEKLENİYOR (Sende!)</b>",
                "━━━━━━━━━━━━━━━━━━━━",
                "🔍 <b>1M ONAY REHBERİ:</b>",
                "• [ ] 1M'de ters gövdeli mum / MSS kırılımı var mı?",
                "• [ ] Kutu içinde hacim emilimi (Absorption) var mı?",
                "• ⚠️ <i>Kutu hacimle deliniyorsa: PAS GEÇ (GİRME)!</i>",
                "━━━━━━━━━━━━━━━━━━━━",
                "💰 <b>FİYAT SEVİYELERİ:</b>",
                f"• <b>Entry:</b> <code>{entry}</code> | <b>SL:</b> <code>{sl}</code> ({risk_pips} p)",
                f"• <b>Hedef 1 (TP1):</b> <code>{tp1}</code> ({tp1_note})",
                f"• <b>Hedef 2 (TP2):</b> <code>{tp2}</code> ({tp2_note})",
            ])

        elif strategy == "ORB_SESSION_BREAKOUT" or "ORB" in strategy:
            session_name = signal.get("session_name", "Aktif Seans")
            orb_h = signal.get("orb_high", 0.0)
            orb_l = signal.get("orb_low", 0.0)
            vol_info = signal.get("volume_analysis", {})
            vol_ratio = vol_info.get("spike_ratio", 1.0)

            tested_lvl = orb_h if direction == "LONG" else orb_l
            lvl_name = "Tavan (High)" if direction == "LONG" else "Taban (Low)"

            lines.extend([
                f"📊 <b>Model:</b> ORB Seans Motoru [{grade}]",
                f"🏛️ <b>Seans:</b> {session_name} (<code>{orb_l} - {orb_h}</code>)",
                f"⚡ <b>Test Edilen Kutu:</b> <code>{tested_lvl}</code> ({lvl_name} Retest)",
                "━━━━━━━━━━━━━━━━━━━━",
                "📋 <b>CHECKLIST:</b>",
                f"• Makro Kapı: ✅ <b>PASS</b> ({gate_bias})",
                f"• Kırılım Hacmi: 🚀 <b>{vol_ratio}x</b> Ort.",
                "• 1M Retest Onayı: ⏳ <b>BEKLENİYOR (Sende!)</b>",
                "━━━━━━━━━━━━━━━━━━━━",
                "🔍 <b>1M ONAY REHBERİ:</b>",
                f"• [ ] <code>{tested_lvl}</code> testinde 1M'de tepki mumu yaktı mı?",
                "• ⚠️ <i>Bandın içine geri dalıyorsa (Fakeout): GİRME!</i>",
                "━━━━━━━━━━━━━━━━━━━━",
                "💰 <b>FİYAT SEVİYELERİ:</b>",
                f"• <b>Retest Giriş:</b> <code>{entry}</code> | <b>SL:</b> <code>{sl}</code>",
                f"• <b>Hedef 1 (TP1):</b> <code>{tp1}</code> | <b>Hedef 2 (TP2):</b> <code>{tp2}</code>",
            ])

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━",
            f"🏛️ Makro: <b>{regime}</b> ({risk_mult}x) | <i>15M + 1M Grafikler Ekte</i>",
        ])

        return "\n".join(lines)

    def send_notification(
        self,
        signal: Dict[str, Any],
        macro_eval: Dict[str, Any],
        chart_path: Optional[Path] = None,
        chart_1m_path: Optional[Path] = None,
    ) -> bool:
        """
        Telegram'a karti ve hem 15m hem 1m grafik kanitlarini gonderir.
        Iki grafik de varsa sendMediaGroup ile album olarak iletir.
        """
        if not self.is_configured():
            logger.warning("Telegram token veya chat_id yapilandirilmamis.")
            return False

        caption = self.format_card(signal, macro_eval)
        # Telegram media caption strict limit is 1024 characters
        if len(caption) <= 1020:
            media_caption = caption
            media_parse_mode = "HTML"
            send_text_after = False
        else:
            media_caption = f"🌺 BEGONYA 00 - {signal.get('symbol')} {signal.get('direction')} [{signal.get('grade')}]\n📦 KUTU TEST EDİLDİ - 1M ONAY SENDE!\n(Detaylı kart aşağıda iletilmektedir)"
            media_parse_mode = None
            send_text_after = True

        # 1. Hem 15m hem 1m grafik mevcutsa sendMediaGroup ile album gonder
        if chart_path and chart_path.exists() and chart_1m_path and chart_1m_path.exists():
            try:
                url = f"https://api.telegram.org/bot{self.token}/sendMediaGroup"
                media_item_1 = {
                    "type": "photo",
                    "media": "attach://chart_15m",
                    "caption": media_caption,
                }
                if media_parse_mode:
                    media_item_1["parse_mode"] = media_parse_mode

                media = [
                    media_item_1,
                    {
                        "type": "photo",
                        "media": "attach://chart_1m",
                    },
                ]
                with open(chart_path, "rb") as f15, open(chart_1m_path, "rb") as f1:
                    files = {
                        "chart_15m": f15,
                        "chart_1m": f1,
                    }
                    data = {
                        "chat_id": self.chat_id,
                        "media": json.dumps(media),
                    }
                    resp = requests.post(url, data=data, files=files, timeout=25)
                    if resp.status_code == 200:
                        logger.info(f"✅ Telegram cift grafikli (15m + 1m) album gonderildi: {signal.get('symbol')}")
                        if send_text_after:
                            self._send_text_fallback(caption)
                        return True
                    else:
                        logger.warning(f"sendMediaGroup basarisiz: {resp.text}")
            except Exception as e:
                logger.error(f"Telegram sendMediaGroup hatasi: {e}")

        # 2. Tek fotograf ile gonderme (Varsa)
        target_chart = chart_path if (chart_path and chart_path.exists()) else chart_1m_path
        if target_chart and target_chart.exists():
            try:
                url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
                with open(target_chart, "rb") as photo_file:
                    files = {"photo": photo_file}
                    data = {
                        "chat_id": self.chat_id,
                        "caption": media_caption,
                    }
                    if media_parse_mode:
                        data["parse_mode"] = media_parse_mode
                    resp = requests.post(url, data=data, files=files, timeout=20)
                    if resp.status_code == 200:
                        logger.info(f"✅ Telegram fotografli sinyal gonderildi: {signal.get('symbol')}")
                        if send_text_after:
                            self._send_text_fallback(caption)
                        return True
                    else:
                        logger.warning(f"sendPhoto basarisiz: {resp.text}")
            except Exception as e:
                logger.error(f"Telegram sendPhoto hatasi: {e}")

    def _send_text_fallback(self, caption: str) -> bool:
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": caption,
                "parse_mode": "HTML",
            }
            resp = requests.post(url, json=payload, timeout=15)
            return resp.status_code == 200
        except Exception:
            return False

        # 3. Metin olarak gonderme (Fallback)
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": caption,
                "parse_mode": "HTML",
            }
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                logger.info(f"✅ Telegram metin sinyali gonderildi: {signal.get('symbol')}")
                return True
            else:
                logger.error(f"sendMessage basarisiz: {resp.text}")
        except Exception as e:
            logger.error(f"Telegram sendMessage hatasi: {e}")

        return False
