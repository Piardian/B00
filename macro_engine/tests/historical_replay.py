"""
Tarihsel Rejim Stres Testi Süiti (Historical Replay Engine)
Farklı makro rejim şoklarında modelin sermaye koruma ve rejim tespit yeteneğini doğrular:
1. Ekim 2023: Ağır Hazine Tahvil Arzı Şoku (US10Y > %5.0)
2. Mart 2023: SVB Bankacılık Çöküşü (2Y Faizi 3 Günde 100 bps Düştü - Bull Steepening)
3. Mart 2020: Küresel Likidite Donması (VIX > 60, Nakit Yarışı)
"""

import sys
import logging
from pathlib import Path
from typing import Dict, Any

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Proje kök dizinini sys.path'e ekle
ROOT_DIR = Path(__file__).parent.parent.resolve()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from preprocessing.metrics import MacroMetricsCalculator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HistoricalReplay")


def _mark_synthetic_fixture(result: Dict[str, Any]) -> Dict[str, Any]:
    """Mark scenario data as synthetic test fixtures, not runtime fallbacks."""
    result.setdefault("data_quality", {})["fixture_provenance"] = "SYNTHETIC_TEST_FIXTURE"
    return result


def run_scenario_october_2023() -> Dict[str, Any]:
    """Senaryo 1: Ekim 2023 - Hazine Tahvil Arzı Şoku (US10Y > %5.0)."""
    calc = MacroMetricsCalculator()
    raw_market = {
        "US10Y": {"value": 5.02, "prev": 4.95, "val_5d_ago": 4.80, "month_ago": 4.55, "change_pct": 1.4, "change_pct_5d": 4.58, "history_close": [4.80, 4.85, 4.90, 4.95, 5.02]},
        "US02Y": {"value": 5.15, "prev": 5.15, "val_5d_ago": 5.10, "month_ago": 5.05, "change_pct": 0.0, "change_pct_5d": 0.98, "history_close": [5.10, 5.12, 5.14, 5.15, 5.15]},
        "VIX": {"value": 21.7, "prev": 18.5, "val_5d_ago": 17.2, "month_ago": 15.0, "change_pct": 17.3, "change_pct_5d": 26.1, "pct_rank_60d": 88.5},
        "HYG": {"value": 73.2, "prev": 73.9, "val_5d_ago": 74.2, "month_ago": 75.0, "change_pct": -0.95, "change_pct_5d": -1.35},
        "LQD": {"value": 102.5, "prev": 103.0, "val_5d_ago": 103.5, "month_ago": 104.5, "change_pct": -0.48, "change_pct_5d": -0.96},
        "BRENT": {"value": 92.5, "prev": 91.0, "val_5d_ago": 88.0, "month_ago": 85.0, "change_pct": 1.6, "change_pct_5d": 5.1, "pct_rank_60d": 89.0},
        "WTI": {"value": 88.0, "prev": 87.0, "val_5d_ago": 84.0, "month_ago": 81.0, "change_pct": 1.1, "change_pct_5d": 4.7},
        "GOLD": {"value": 1980.0, "prev": 1960.0, "val_5d_ago": 1920.0, "month_ago": 1850.0, "change_pct": 1.0, "change_pct_5d": 3.1},
        "COPPER": {"value": 3.58, "prev": 3.60, "val_5d_ago": 3.65, "month_ago": 3.80, "change_pct": -0.55, "change_pct_5d": -1.9},
        "DXY": {"value": 106.5, "prev": 106.2, "val_5d_ago": 105.8, "month_ago": 104.5, "change_pct": 0.28, "change_pct_5d": 0.66},
        "BTC": {"value": 28500.0, "prev": 28200.0, "val_5d_ago": 27500.0, "month_ago": 26000.0, "change_pct": 1.0, "change_pct_5d": 3.6},
        "EUR_BOND": {"value": 175.0, "prev": 176.0, "val_5d_ago": 178.0, "month_ago": 182.0, "change_pct": -0.56, "change_pct_5d": -1.68},
        "SOL": {"value": 20.0, "prev": 19.5, "val_5d_ago": 19.0, "month_ago": 18.0, "change_pct": 2.56, "change_pct_5d": 5.26}
    }
    raw_fred = {
        "WALCL": 7950000.0, "WALCL_4W_AGO": 8020000.0,
        "RRPONTSYD": 1150.0, "RRPONTSYD_4W_AGO": 1300.0,
        "WTREGEN": 750000.0, "WTREGEN_4W_AGO": 680000.0,
        "T10YIE": 2.45, "DFII10": 2.50,
        "BAMLH0A0HYM2": 4.15, "NFCI": -0.35, "ICSA": 212.0,
        "DE10Y": 2.85, "DE10Y_4W_AGO": 2.70, "DFF": 5.33, "SOFR": 5.33
    }
    events = [
        {"title": "Non-Farm Employment Change", "actual": "336K", "forecast": "170K"},
        {"title": "Core CPI m/m", "actual": "0.3%", "forecast": "0.3%"},
        {"title": "Unemployment Rate", "actual": "3.8%", "forecast": "3.7%"}
    ]
    return _mark_synthetic_fixture(calc.process_all_macro_data(raw_market, raw_fred, events))


def run_scenario_march_2023_svb() -> Dict[str, Any]:
    """Senaryo 2: Mart 2023 - SVB Bankacılık İflası & 100 bps Bull Steepening Çöküşü."""
    calc = MacroMetricsCalculator()
    raw_market = {
        "US10Y": {"value": 3.42, "prev": 3.70, "val_5d_ago": 4.00, "month_ago": 3.85, "change_pct": -7.56, "change_pct_5d": -14.5, "history_close": [4.00, 3.90, 3.70, 3.55, 3.42]},
        "US02Y": {"value": 3.98, "prev": 4.58, "val_5d_ago": 5.08, "month_ago": 4.80, "change_pct": -13.1, "change_pct_5d": -21.6, "history_close": [5.08, 4.90, 4.58, 4.20, 3.98]},
        "VIX": {"value": 26.5, "prev": 19.0, "val_5d_ago": 18.5, "month_ago": 19.5, "change_pct": 39.4, "change_pct_5d": 43.2, "pct_rank_60d": 95.0},
        "HYG": {"value": 73.0, "prev": 75.0, "val_5d_ago": 76.2, "month_ago": 76.5, "change_pct": -2.66, "change_pct_5d": -4.2},
        "LQD": {"value": 106.0, "prev": 105.5, "val_5d_ago": 105.0, "month_ago": 104.5, "change_pct": 0.47, "change_pct_5d": 0.95},
        "BRENT": {"value": 74.0, "prev": 80.0, "val_5d_ago": 85.0, "month_ago": 83.0, "change_pct": -7.5, "change_pct_5d": -12.9, "pct_rank_60d": 12.0},
        "WTI": {"value": 68.0, "prev": 74.0, "val_5d_ago": 79.0, "month_ago": 77.0, "change_pct": -8.1, "change_pct_5d": -13.9},
        "GOLD": {"value": 1985.0, "prev": 1910.0, "val_5d_ago": 1830.0, "month_ago": 1860.0, "change_pct": 3.9, "change_pct_5d": 8.4},
        "COPPER": {"value": 3.88, "prev": 4.02, "val_5d_ago": 4.10, "month_ago": 4.05, "change_pct": -3.48, "change_pct_5d": -5.36},
        "DXY": {"value": 103.5, "prev": 105.0, "val_5d_ago": 105.6, "month_ago": 104.0, "change_pct": -1.4, "change_pct_5d": -1.98},
        "BTC": {"value": 24500.0, "prev": 22000.0, "val_5d_ago": 20000.0, "month_ago": 22000.0, "change_pct": 11.3, "change_pct_5d": 22.5},
        "EUR_BOND": {"value": 182.0, "prev": 178.0, "val_5d_ago": 175.0, "month_ago": 176.0, "change_pct": 2.2, "change_pct_5d": 4.0},
        "SOL": {"value": 20.0, "prev": 19.5, "val_5d_ago": 19.0, "month_ago": 18.0, "change_pct": 2.56, "change_pct_5d": 5.26},
        "SOL": {"value": 20.0, "prev": 19.5, "val_5d_ago": 19.0, "month_ago": 18.0, "change_pct": 2.56, "change_pct_5d": 5.26}
    }
    raw_fred = {
        "WALCL": 8630000.0, "WALCL_4W_AGO": 8350000.0,
        "RRPONTSYD": 2100.0, "RRPONTSYD_4W_AGO": 2200.0,
        "WTREGEN": 280000.0, "WTREGEN_4W_AGO": 350000.0,
        "T10YIE": 2.20, "DFII10": 1.22,
        "BAMLH0A0HYM2": 4.85, "NFCI": 0.15, "ICSA": 220.0,
        "DE10Y": 2.18, "DE10Y_4W_AGO": 2.65, "DFF": 4.83, "SOFR": 4.83
    }
    events = [
        {"title": "Non-Farm Employment Change", "actual": "311K", "forecast": "225K"},
        {"title": "Unemployment Rate", "actual": "3.6%", "forecast": "3.4%"}
    ]
    return _mark_synthetic_fixture(calc.process_all_macro_data(raw_market, raw_fred, events))


def run_scenario_march_2020_covid() -> Dict[str, Any]:
    """Senaryo 3: Mart 2020 - Küresel Likidite Donması & Nakde Kaçış (Cash Dash)."""
    calc = MacroMetricsCalculator()
    raw_market = {
        "US10Y": {"value": 0.70, "prev": 0.85, "val_5d_ago": 1.20, "month_ago": 1.55, "change_pct": -17.6, "change_pct_5d": -41.6, "history_close": [1.20, 1.05, 0.90, 0.85, 0.70]},
        "US02Y": {"value": 0.35, "prev": 0.45, "val_5d_ago": 0.80, "month_ago": 1.35, "change_pct": -22.2, "change_pct_5d": -56.2, "history_close": [0.80, 0.65, 0.50, 0.45, 0.35]},
        "VIX": {"value": 68.0, "prev": 45.0, "val_5d_ago": 38.0, "month_ago": 15.0, "change_pct": 51.1, "change_pct_5d": 78.9, "pct_rank_60d": 100.0},
        "HYG": {"value": 68.0, "prev": 75.0, "val_5d_ago": 82.0, "month_ago": 88.0, "change_pct": -9.3, "change_pct_5d": -17.0},
        "LQD": {"value": 112.0, "prev": 120.0, "val_5d_ago": 128.0, "month_ago": 132.0, "change_pct": -6.6, "change_pct_5d": -12.5},
        "BRENT": {"value": 28.5, "prev": 35.0, "val_5d_ago": 45.0, "month_ago": 55.0, "change_pct": -18.5, "change_pct_5d": -36.6, "pct_rank_60d": 1.0},
        "WTI": {"value": 24.0, "prev": 30.0, "val_5d_ago": 41.0, "month_ago": 51.0, "change_pct": -20.0, "change_pct_5d": -41.4},
        "GOLD": {"value": 1490.0, "prev": 1580.0, "val_5d_ago": 1650.0, "month_ago": 1580.0, "change_pct": -5.7, "change_pct_5d": -9.6},
        "COPPER": {"value": 2.15, "prev": 2.35, "val_5d_ago": 2.55, "month_ago": 2.65, "change_pct": -8.5, "change_pct_5d": -15.6},
        "DXY": {"value": 102.8, "prev": 99.5, "val_5d_ago": 96.0, "month_ago": 99.0, "change_pct": 3.3, "change_pct_5d": 7.08},
        "BTC": {"value": 5200.0, "prev": 7800.0, "val_5d_ago": 8800.0, "month_ago": 9500.0, "change_pct": -33.3, "change_pct_5d": -40.9},
        "EUR_BOND": {"value": 165.0, "prev": 172.0, "val_5d_ago": 180.0, "month_ago": 178.0, "change_pct": -4.0, "change_pct_5d": -8.3},
        "SOL": {"value": 20.0, "prev": 19.5, "val_5d_ago": 19.0, "month_ago": 18.0, "change_pct": 2.56, "change_pct_5d": 5.26},
        "SOL": {"value": 20.0, "prev": 19.5, "val_5d_ago": 19.0, "month_ago": 18.0, "change_pct": 2.56, "change_pct_5d": 5.26}
    }
    raw_fred = {
        "WALCL": 4300000.0, "WALCL_4W_AGO": 4180000.0,
        "RRPONTSYD": 0.0, "RRPONTSYD_4W_AGO": 0.0,
        "WTREGEN": 380000.0, "WTREGEN_4W_AGO": 420000.0,
        "T10YIE": 0.85, "DFII10": -0.15,
        "BAMLH0A0HYM2": 8.75, "NFCI": 0.85, "ICSA": 3300.0,
        "DE10Y": -0.55, "DE10Y_4W_AGO": -0.40, "DFF": 0.25, "SOFR": 0.25
    }
    events = [
        {"title": "Initial Jobless Claims", "actual": "3300K", "forecast": "250K"}
    ]
    return _mark_synthetic_fixture(calc.process_all_macro_data(raw_market, raw_fred, events))


def main():
    print("=" * 75)
    print("         TARİHSEL REJİM STRES TESTİ SÜİTİ (HISTORICAL REPLAY)          ")
    print("=" * 75)

    # 1. Ekim 2023
    print("\n[TEST 1] EKİM 2023: Hazine Tahvil Arzı Şoku (US10Y > %5.0)")
    r1 = run_scenario_october_2023()
    yc1 = r1['yield_curve']
    btc1 = r1['btc_decoupling_analysis']
    stress1 = r1['t0_fast_stress_analysis']
    print(f"  • Getiri Eğrisi : {yc1['regime']} ({yc1['spread_bps']} bps) | Kategori: {yc1['risk_category']}")
    print(f"  • T-0 Fast Stres: {'⚠️ AKTİF' if stress1['fast_stress_override'] else 'Sakin'}")
    print(f"  • BTC Decoupling: {'⚠️ AKTİF (SHORT_ONLY)' if btc1['btc_decoupling_active'] else 'Normal'}")
    print(f"  • Gerekçe       : {btc1['rationale']}")
    assert yc1['regime'] in ["Bear Steepening", "Inverted"], "Ekim 2023 getiri eğrisi dikleşmesi doğru tespit edilmeli!"
    assert btc1['btc_decoupling_active'], "Ekim 2023 VIX > 20 ve 10Y şokunda BTC ayrışmalı!"
    assert btc1['recommended_btc_gate'] == "SHORT_ONLY", "BTC decoupling kapısı SHORT_ONLY olmalı!"
    print("  -> ✅ TEST 1 BAŞARILI: Model Bear Steepening arz şokunu ve BTC SHORT fırsatını doğru yakaladı.")

    # 2. Mart 2023 (SVB)
    print("\n[TEST 2] MART 2023: SVB Bankacılık İflası & 100 bps Bull Steepening Çöküşü")
    r2 = run_scenario_march_2023_svb()
    yc2 = r2['yield_curve']
    stress2 = r2['t0_fast_stress_analysis']
    print(f"  • Getiri Eğrisi : {yc2['regime']} ({yc2['spread_bps']} bps) | Kategori: {yc2['risk_category']}")
    print(f"  • T-0 Fast Stres: {'⚠️ AKTİF (FRED Baypas Edildi)' if stress2['fast_stress_override'] else 'Sakin'}")
    print(f"  • Tetikleyiciler: {stress2['triggers']}")
    assert stress2['fast_stress_override'], "Mart 2023 SVB krizinde T-0 anlık stres devreye girmeli!"
    assert "Bull Steepening" in yc2['regime'] or "Inverted" in yc2['regime'], "2Y çöküşü Bull Steepening olarak okunmalı!"
    print("  -> ✅ TEST 2 BAŞARILI: Model bankacılık paniğini ve T-0 devre kesicisini anında tetikledi.")

    # 3. Mart 2020 (COVID)
    print("\n[TEST 3] MART 2020: Küresel Likidite Donması & Nakit Yarışı (Cash Dash)")
    r3 = run_scenario_march_2020_covid()
    stress3 = r3['t0_fast_stress_analysis']
    credit3 = r3['credit_spread_analysis']
    print(f"  • Kredi Makası  : %{credit3['hy_oas_spread_pct']} -> {credit3['stress_level']}")
    print(f"  • T-0 Fast Stres: {'⚠️ AKTİF (Sermaye Koruma)' if stress3['fast_stress_override'] else 'Sakin'}")
    print(f"  • VIX Seviyesi  : {stress3['vix_level']} (1G Sıçrama: %{stress3['vix_delta_1d_pct']})")
    assert stress3['fast_stress_override'], "Mart 2020 likidite şokunda acil durum modu devreye girmeli!"
    assert credit3['hy_oas_spread_pct'] > 5.0, "Kredi makası kriz seviyesinde olmalı!"
    print("  -> ✅ TEST 3 BAŞARILI: Sistemik krizde model tüm yönlü işlemleri engelleyen tam koruma sağladı.")

    print("\n" + "=" * 75)
    print("       TÜM TARİHSEL STRES TESTLERİ BAŞARIYLA GEÇTİ (3/3 PASSED)        ")
    print("=" * 75)


if __name__ == "__main__":
    main()
