"""
🌺 Begonya 00 - Motor Calistirici (CLI Entrypoint)
"""

import argparse
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .engine import BegonyaEngine
from .telegram_notifier import TelegramNotifier
from .chart_renderer import ChartRenderer
from .macro_gate_client import MacroGateClient


def test_telegram_card():
    print("\n🌺 Begonya 00 Telegram ve Grafik Testi Baslatiliyor...")
    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print("❌ Telegram yapilandirilmamis (TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik).")
        return

    macro_client = MacroGateClient()
    renderer = ChartRenderer()

    # Canli EUR/USD guncel fiyatina yakin baz al
    from .data_provider import MarketDataProvider
    from .config import PRIMARY_TIMEFRAME
    provider = MarketDataProvider()
    live_df = provider.fetch_candles("EUR/USD", interval=PRIMARY_TIMEFRAME, outputsize=10)
    if live_df is not None and len(live_df) > 0:
        base_price = round(float(live_df.iloc[-1]["close"]), 5)
    else:
        base_price = 1.12030

    now = datetime.now()
    dates = [now - timedelta(minutes=5 * (40 - i)) for i in range(41)]
    prices = [base_price + np.sin(i / 5.0) * 0.0015 + (i * 0.00003) for i in range(41)]

    # SFP Likidite Ignesi olustur (son mumu sahte kirilim yap)
    candles = []
    for i in range(40):
        p = prices[i]
        candles.append({
            "datetime": dates[i],
            "open": p,
            "high": p + 0.0004,
            "low": p - 0.0003,
            "close": p + 0.0001,
            "volume": 1200.0 + (i * 15.0),
        })

    # Son bar: Bullish SFP mumu (asagi igneleme, guclu alici fitili ve hacim patlamasi)
    prev_low = min(c["low"] for c in candles[-15:])
    candles.append({
        "datetime": dates[40],
        "open": prev_low + 0.0002,
        "high": prev_low + 0.0005,
        "low": prev_low - 0.0008,     # Seviye altina igneleme (Liquidity Sweep)
        "close": prev_low + 0.0003,   # Seviye ustunde kapanis (Rejection)
        "volume": 3650.0,              # 2.8x Hacim patlamasi
    })

    df = pd.DataFrame(candles)

    mock_signal = {
        "strategy": "SFP_VOLUME_ANOMALY",
        "setup_type": "BULLISH_SFP",
        "direction": "LONG",
        "symbol": "EUR/USD",
        "timeframe": "15m (15 Dakikalık)",
        "grade": "A+",
        "datetime": dates[40],
        "entry": round(prev_low + 0.0003, 5),
        "stop_loss": round(prev_low - 0.0010, 5),
        "tp1": round(prev_low + 0.0022, 5),
        "tp2": round(prev_low + 0.0035, 5),
        "risk_pips": 13.0,
        "rr_ratio": 2.5,
        "swept_level": round(prev_low, 5),
        "sweep_wick_ratio": 0.44,
        "volume_analysis": {
            "is_anomaly": True,
            "tier": "TIER_3_ULTRA",
            "spike_ratio": 2.85,
            "z_score": 3.12,
            "absorption_type": "BULLISH_ABSORPTION",
        },
    }

    macro_eval = macro_client.evaluate_gate("EUR/USD", "LONG")
    # Test amaciyla izin verildi goster
    if not macro_eval["allowed"]:
        macro_eval["allowed"] = True
        macro_eval["gate_bias"] = "TEST_OVERRIDE"

    chart_path = renderer.render_signal_chart(df, mock_signal, tag="15m")
    chart_1m_path = renderer.render_signal_chart(df.tail(25), mock_signal, tag="1m")
    print(f"📊 15m Grafik render edildi: {chart_path}")
    print(f"📊 1m Grafik render edildi: {chart_1m_path}")

    ok = notifier.send_notification(mock_signal, macro_eval, chart_path=chart_path, chart_1m_path=chart_1m_path)
    if ok:
        print("✅ Test sinyal karti ve cift grafik albümü basariyla Telegram'a iletildi!")
    else:
        print("⚠️ Telegram'a gonderim basarisiz oldu.")


def main():
    parser = argparse.ArgumentParser(description="Begonya 00 SFP & ORB Engine")
    parser.add_argument("--live", action="store_true", help="Canli otonom donguyu baslat")
    parser.add_argument("--scan-once", action="store_true", help="Tum evreni bir kez tara")
    parser.add_argument("--test-card", action="store_true", help="Telegram test karti ve grafik gonder")

    args = parser.parse_args()

    if args.test_card:
        test_telegram_card()
        return

    engine = BegonyaEngine()

    if args.scan_once:
        print("\n🌺 Begonya 00 Tekil Tarama Baslatiliyor...")
        findings = engine.scan_universe()
        print(f"Tarama tamamlandi. Bulunan toplam sinyal: {len(findings)}")
    else:
        # Varsayilan veya --live
        engine.run_loop()


if __name__ == "__main__":
    main()
