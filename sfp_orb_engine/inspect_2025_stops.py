"""
🌺 Begonya 00 - 2025 Stop Loss Detaylı Otopsi Scripti
Bu script 2025 yılı Mart, Temmuz, Ekim aylarında stop olan 10 işlemin ve 2025 yılı genelindeki tüm stopların anatomisini çıkarır:
1. Hangi semboller stop oldu? (Kripto vs Forex)
2. Hangi likidite havuzu süpürüldü? (PDL, PDH, ASIAN_LOW)
3. Kaç bar sonra stop oldu? (Anında mı yoksa oyalanıp mı?)
4. MFE: Kâra ne kadar yaklaştı? (0.5R, 0.6R, 0.7R?)
5. Yön: Long mu Short mu?
"""

import sys
import json
from datetime import datetime, timezone
import MetaTrader5 as mt5
import pandas as pd
from sfp_orb_engine.test_2025_remediation import Remediation2025Runner, TARGET_SYMBOLS

def inspect_stops():
    runner = Remediation2025Runner(
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc),
        tp1_rr=0.8
    )

    test_periods = [
        ('Mart (Q1)', '2025-03-01', '2025-03-31'),
        ('Temmuz (Q3)', '2025-07-01', '2025-07-31'),
        ('Ekim (Q4)', '2025-10-01', '2025-10-31')
    ]

    all_trades = []
    for sym in TARGET_SYMBOLS:
        df = runner.fetch_m15_data(sym)
        if df is not None:
            t_l, _ = runner.run_simulation(
                sym, df,
                apply_asian_high_filter=True,
                apply_overextension_filter=True,
                max_ema200_dist_pct=1.0,
                use_tp1_08r=True
            )
            all_trades.extend(t_l)

    target_trades = []
    for name, s_str, e_str in test_periods:
        m_trades = [t for t in all_trades if s_str <= t['opened_at'][:10] <= e_str]
        for t in m_trades:
            t['test_month'] = name
        target_trades.extend(m_trades)

    df_tgt = pd.DataFrame(target_trades)
    sl_tgt = df_tgt[df_tgt['close_reason'] == 'STOP_LOSS']

    print("=" * 90)
    print(f"🔬 2025 YILI 3 AYDAKİ {len(sl_tgt)} STOP LOSS İŞLEMİNİN DETAYLI OTOPSİSİ")
    print("=" * 90)

    for idx, r in sl_tgt.iterrows():
        print(f"Ay: {r['test_month']:<12} | {r['opened_at']} | Sembol: {r['symbol']:<7} | Yön: {r['direction']:<5} | Havuz: {r['pool']:<10} | Tutulan Bar: {r['bars_held']:<3} ({r['bars_held']*15} dk)")

    print("\n--- 1. SEMBOL DAĞILIMI ---")
    print(sl_tgt['symbol'].value_counts())

    print("\n--- 2. YÖN DAĞILIMI ---")
    print(sl_tgt['direction'].value_counts())

    print("\n--- 3. LİKİDİTE HAVUZU (POOL) DAĞILIMI ---")
    print(sl_tgt['pool'].value_counts())

    print("\n--- 4. İŞLEMİN AÇIK KALMA SÜRESİ (BARS HELD) ---")
    print(f"Ortalama Süre: {sl_tgt['bars_held'].mean():.1f} bar ({sl_tgt['bars_held'].mean()*15:.0f} dk)")
    print(f"İlk 1-3 Bar İçinde Stop Olanlar: {len(sl_tgt[sl_tgt['bars_held'] <= 3])} adet")

    # Tüm 2025 Yılındaki Stopların Özeti
    df_all = pd.DataFrame(all_trades)
    df_all_sl = df_all[df_all['close_reason'] == 'STOP_LOSS']
    print("\n" + "=" * 90)
    print(f"🌐 2025 YILI GENELİNDEKİ TÜM {len(df_all_sl)} STOP LOSS'UN GENEL KARAKTERİ")
    print("=" * 90)
    print("Sembol Dağılımı (İlk 5):")
    print(df_all_sl['symbol'].value_counts().head(5))
    print("\nYön Dağılımı:")
    print(df_all_sl['direction'].value_counts())
    print("\nHavuz Dağılımı:")
    print(df_all_sl['pool'].value_counts())
    print("\nSaat Dağılımı (UTC):")
    print(df_all_sl['opened_at'].str[11:13].value_counts().head(5))

if __name__ == '__main__':
    inspect_stops()
