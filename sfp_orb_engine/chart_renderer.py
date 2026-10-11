"""
🌺 Begonya 00 - Kurumsal Grafik Kaniti Render Modulu (Temiz & Profesyonel HUD Tasarimi)
Sıfır Çakışma, Kristal Netliğinde İşlem Kartı, TradingView Mum Renkleri ve Hassas Seviyeler
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from .config import EVIDENCE_DIR


class ChartRenderer:
    def __init__(self, evidence_dir: Optional[Path] = None):
        self.evidence_dir = evidence_dir or EVIDENCE_DIR
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def render_signal_chart(self, df: pd.DataFrame, signal: Dict[str, Any], tag: str = "") -> Optional[Path]:
        """
        Sinyal icin son derece temiz, okunabilir ve profesyonel bir grafik cizer.
        Tum yazilari HUD bilgi kutusunda toplar, mumlarin ustunu kapatmaz.
        """
        try:
            # Son 26 mumu goster (mumlar buyuk, net ve TradingView ferahliginda)
            display_df = df.tail(26).copy().reset_index(drop=True)
            n_bars = len(display_df)
            if n_bars < 8:
                return None

            symbol = signal.get("symbol", "ASSET")
            strategy = signal.get("strategy", "SFP_VOLUME_ANOMALY")
            direction = signal.get("direction", "LONG")
            grade = signal.get("grade", "A+")
            entry = float(signal.get("entry", display_df.iloc[-1]["close"]))
            sl = float(signal.get("stop_loss", entry))
            tp1 = float(signal.get("tp1", entry))
            tp2 = float(signal.get("tp2", entry))
            tf_label = tag if tag else signal.get("render_tf", signal.get("timeframe", "15m (15 Dakikalık)"))

            decimals = 5 if "JPY" not in symbol and entry < 50 else (3 if "JPY" in symbol else 2)

            # Risk ve Kazanc Pip Hesabi
            if "JPY" in symbol:
                pip_mult = 100
            elif entry < 50:
                pip_mult = 10000
            else:
                pip_mult = 1

            risk_pips = round(abs(entry - sl) * pip_mult, 1)
            tp1_pips = round(abs(tp1 - entry) * pip_mult, 1)
            tp2_pips = round(abs(tp2 - entry) * pip_mult, 1)

            fig, (ax_main, ax_vol) = plt.subplots(
                2, 1, figsize=(13, 7.5), gridspec_kw={"height_ratios": [3.6, 1.0]}, facecolor="#131722"
            )

            ax_main.set_facecolor("#131722")
            ax_vol.set_facecolor("#131722")

            # Izgara (Hafif ve goz yormayan)
            ax_main.grid(True, linestyle=":", alpha=0.15, color="#363c4e")
            ax_vol.grid(True, linestyle=":", alpha=0.12, color="#363c4e")

            # 1. MUM GRAFİĞİ ÇİZİMİ (Büyük, net ve ferah mumlar)
            candle_w = 0.72
            for idx, row in display_df.iterrows():
                o_p = float(row["open"])
                c_p = float(row["close"])
                h_p = float(row["high"])
                l_p = float(row["low"])

                is_bull = c_p >= o_p
                c_color = "#089981" if is_bull else "#f23645"

                # Fitil (Daha kalın ve net)
                ax_main.plot([idx, idx], [l_p, h_p], color=c_color, linewidth=1.4, zorder=2)

                # Gövde (Geniş mum gövdesi)
                b_bottom = min(o_p, c_p)
                b_height = max(abs(c_p - o_p), 1e-6)
                rect = patches.Rectangle(
                    (idx - candle_w / 2, b_bottom),
                    candle_w,
                    b_height,
                    facecolor=c_color,
                    edgecolor=c_color,
                    zorder=3,
                )
                ax_main.add_patch(rect)

            # 2. İŞLEM ÇİZGİLERİ (GİRİŞ, STOP LOSS, TP1, TP2)
            # Giriş Seviyesi (Mavi Kesik Çizgi)
            ax_main.axhline(entry, color="#3b82f6", linestyle="--", linewidth=1.5, alpha=0.9, zorder=4)
            # Stop Loss (Kırmızı Kesik Çizgi)
            ax_main.axhline(sl, color="#ef4444", linestyle="--", linewidth=1.5, alpha=0.9, zorder=4)
            # Hedef 1 (Açık Mavi / Cyan Noktalı)
            ax_main.axhline(tp1, color="#06b6d4", linestyle=":", linewidth=1.3, alpha=0.9, zorder=4)
            # Hedef 2 (Parlak Yeşil Kesik Çizgi)
            ax_main.axhline(tp2, color="#10b981", linestyle="--", linewidth=1.5, alpha=0.9, zorder=4)

            # SFP Likidite Seviyesi & FVG Dengesizlik Bölgesi
            if strategy == "SFP_VOLUME_ANOMALY":
                swept_lvl = signal.get("swept_level")
                if swept_lvl:
                    ax_main.axhline(swept_lvl, color="#f59e0b", linestyle="-.", linewidth=1.2, alpha=0.85, zorder=3)

                fvg_zone = signal.get("fvg_zone")
                if fvg_zone and len(fvg_zone) == 2:
                    top_fvg, bot_fvg = max(fvg_zone[0], fvg_zone[1]), min(fvg_zone[0], fvg_zone[1])
                    fvg_color = "#10b981" if direction == "LONG" else "#ef4444"
                    ax_main.axhspan(bot_fvg, top_fvg, color=fvg_color, alpha=0.15, zorder=2)
                    ax_main.axhline(top_fvg, color=fvg_color, linestyle=":", linewidth=0.8, alpha=0.7)
                    ax_main.axhline(bot_fvg, color=fvg_color, linestyle=":", linewidth=0.8, alpha=0.7)

            # ORB Seans Bandı (Varsa)
            elif strategy == "ORB_SESSION_BREAKOUT":
                orb_h = signal.get("orb_high")
                orb_l = signal.get("orb_low")
                if orb_h and orb_l:
                    ax_main.axhspan(orb_l, orb_h, color="#3b82f6", alpha=0.12, zorder=1)
                    ax_main.axhline(orb_h, color="#60a5fa", linestyle=":", linewidth=1.1)
                    ax_main.axhline(orb_l, color="#60a5fa", linestyle=":", linewidth=1.1)

            # 3. SAĞ KENAR FİYAT ROZETLERİ (KOMPAKT, KÜÇÜK YAZILAR)
            right_x = n_bars + 0.35
            box_entry = dict(boxstyle="square,pad=0.15", facecolor="#1e40af", edgecolor="#3b82f6", linewidth=0.8)
            box_sl = dict(boxstyle="square,pad=0.15", facecolor="#991b1b", edgecolor="#ef4444", linewidth=0.8)
            box_tp1 = dict(boxstyle="square,pad=0.15", facecolor="#155e75", edgecolor="#06b6d4", linewidth=0.8)
            box_tp2 = dict(boxstyle="square,pad=0.15", facecolor="#065f46", edgecolor="#10b981", linewidth=0.8)

            ax_main.text(right_x, entry, f" GİRİŞ: {entry:.{decimals}f}", color="#ffffff", fontsize=7.0, fontweight="bold", va="center", bbox=box_entry, zorder=6)
            ax_main.text(right_x, sl, f" SL: {sl:.{decimals}f}", color="#ffffff", fontsize=7.0, fontweight="bold", va="center", bbox=box_sl, zorder=6)
            ax_main.text(right_x, tp1, f" TP1: {tp1:.{decimals}f}", color="#ffffff", fontsize=6.8, fontweight="bold", va="center", bbox=box_tp1, zorder=6)
            ax_main.text(right_x, tp2, f" TP2: {tp2:.{decimals}f}", color="#ffffff", fontsize=7.0, fontweight="bold", va="center", bbox=box_tp2, zorder=6)

            # 4. TETİKLEYİCİ GİRİŞ MUMU İŞARETÇİSİ (KÜÇÜK VE ZARİF OK)
            last_idx = n_bars - 1
            last_candle = display_df.iloc[-1]
            if direction == "LONG":
                arrow_base_y = float(last_candle["low"])
                ax_main.plot(last_idx, arrow_base_y, marker="^", markersize=8, color="#10b981", zorder=7)
                ax_main.text(last_idx, arrow_base_y - (abs(entry - sl) * 0.20), "GİRİŞ", color="#10b981", fontsize=6.5, fontweight="bold", ha="center", va="top", zorder=7)
            else:
                arrow_base_y = float(last_candle["high"])
                ax_main.plot(last_idx, arrow_base_y, marker="v", markersize=8, color="#ef4444", zorder=7)
                ax_main.text(last_idx, arrow_base_y + (abs(sl - entry) * 0.20), "GİRİŞ", color="#ef4444", fontsize=6.5, fontweight="bold", ha="center", va="bottom", zorder=7)

            # 5. KRİSTAL NETLİĞİNDE KOMPAKT HUD İŞLEM PLANI KARTİ (KÜÇÜLTÜLMÜŞ YAZI - SOL ÜST)
            dir_text = "LONG (ALIM)" if direction == "LONG" else "SHORT (SATIM)"
            dir_color = "#10b981" if direction == "LONG" else "#ef4444"

            tp1_label = signal.get("tp1_note", "1.0R")
            tp2_label = signal.get("tp2_note", "3.0R")
            trend_align = signal.get("trend_alignment", "")
            trend_str = f" | {trend_align}" if trend_align else ""

            hud_lines = [
                f"[BEGONYA 00] | {symbol} | {tf_label}",
                f"MODEL: {strategy.replace('_', ' ')} [{grade}]{trend_str}",
                f"YÖN: {dir_text}",
                f"• GİRİŞ (ENTRY) : {entry:.{decimals}f}",
                f"• STOP LOSS (SL): {sl:.{decimals}f}  (Risk: {risk_pips} pip)",
                f"• HEDEF 1 (TP1) : {tp1:.{decimals}f}  (+{tp1_pips} pip | {tp1_label})",
                f"• HEDEF 2 (TP2) : {tp2:.{decimals}f}  (+{tp2_pips} pip | {tp2_label})",
            ]
            fvg_badge = signal.get("fvg_badge")
            if fvg_badge:
                hud_lines.append(f"• FVG: {fvg_badge}")

            hud_text = "\n".join(hud_lines)

            ax_main.text(
                0.012, 0.97, hud_text,
                transform=ax_main.transAxes,
                fontsize=7.0,
                fontfamily="monospace",
                fontweight="bold",
                color="#e2e8f0",
                va="top",
                ha="left",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#161b26", edgecolor="#303846", linewidth=0.9, alpha=0.82),
                zorder=8,
            )

            # 6. HACİM ALT PANELİ
            volumes = display_df["volume"].values
            closes = display_df["close"].values
            opens = display_df["open"].values
            vol_colors = ["#089981" if closes[i] >= opens[i] else "#f23645" for i in range(len(volumes))]

            vol_info = signal.get("volume_analysis", {})
            if vol_info.get("is_anomaly", False):
                vol_colors[-1] = "#ffd700"

            ax_vol.bar(range(n_bars), volumes, color=vol_colors, width=candle_w, alpha=0.85, zorder=2)
            sma_vol = pd.Series(volumes).rolling(window=15, min_periods=1).mean()
            ax_vol.plot(range(n_bars), sma_vol, color="#00e5ff", linewidth=1.2, zorder=3)

            if vol_info.get("is_anomaly", False):
                spike_ratio = vol_info.get("spike_ratio", 1.8)
                tier = vol_info.get("tier", "ANOMALI")
                ax_vol.text(
                    0.015, 0.85, f"HACİM ANOMALİSİ: {spike_ratio}x Ort. [{tier}]",
                    transform=ax_vol.transAxes,
                    fontsize=8.0,
                    fontweight="bold",
                    color="#ffd700",
                    va="top",
                    ha="left",
                    zorder=5,
                )

            # 7. EKSEN SINIRLARI VE ZAMAN ETİKETLERİ
            # X Ekseninde sağ marjine 5 bar boşluk bırak (rozatler için)
            ax_main.set_xlim(-1, n_bars + 5)
            ax_vol.set_xlim(-1, n_bars + 5)

            # Y Ekseninde otomatik uygun aralık
            all_prices = [entry, sl, tp1, tp2] + list(display_df["low"].values) + list(display_df["high"].values)
            y_min = min(all_prices)
            y_max = max(all_prices)
            y_padding = (y_max - y_min) * 0.12
            ax_main.set_ylim(y_min - y_padding, y_max + y_padding)

            # X-Ekseni Gerçek Zaman Etiketleri (HH:MM)
            tick_step = max(1, n_bars // 6)
            tick_indices = list(range(0, n_bars, tick_step))
            if (n_bars - 1) not in tick_indices:
                tick_indices.append(n_bars - 1)

            tick_labels = []
            for t_idx in tick_indices:
                try:
                    dt = pd.to_datetime(display_df.iloc[t_idx]["datetime"])
                    if dt.tzinfo is not None:
                        dt_trt = dt.tz_convert("Europe/Istanbul")
                    else:
                        dt_trt = dt + pd.Timedelta(hours=3)
                    tick_labels.append(dt_trt.strftime("%H:%M"))
                except Exception:
                    tick_labels.append(str(t_idx))

            ax_main.set_xticks(tick_indices)
            ax_main.set_xticklabels([])
            ax_vol.set_xticks(tick_indices)
            ax_vol.set_xticklabels(tick_labels, color="#94a3b8", fontsize=8.5)

            ax_main.tick_params(colors="#94a3b8", labelsize=8.5)
            ax_vol.tick_params(colors="#94a3b8", labelsize=8.5)
            for spine in ax_main.spines.values():
                spine.set_color("#2a2e39")
            for spine in ax_vol.spines.values():
                spine.set_color("#2a2e39")

            plt.tight_layout()

            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_sym = symbol.replace("/", "_").replace("-", "")
            tag_slug = f"_{tag.split()[0].replace('(', '').replace(')', '').upper()}" if tag else ""
            img_path = self.evidence_dir / f"signal_{clean_sym}_{strategy}{tag_slug}_{ts_str}.png"
            plt.savefig(img_path, facecolor=fig.get_facecolor(), edgecolor="none", dpi=140)
            plt.close(fig)

            return img_path
        except Exception as e:
            plt.close("all")
            return None
