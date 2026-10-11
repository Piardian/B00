import sys
import json
import logging

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from graph.macro_graph import MacroWorkflowEngine
from gateways.execution_bias_bridge import ExecutionBiasBridge

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MacroMain")

def print_separator(title=""):
    print("\n" + "=" * 70)
    if title:
        print(f" {title.center(66)} ")
        print("=" * 70)

def main():
    print_separator("MULTI-AGI MAKROEKONOMİ ANALİZ AJAN ORDUSU")
    print("📍 Mimari: LangGraph StateGraph + 4-Key Dual Gemini Cascade (3.8 -> 3.7 -> 3.6)")
    print("📍 Veri: yfinance, FRED (WALCL/RRP/TGA), ForexFactory Takvim Olayları")
    print("📍 Çıktı: Katı Pydantic Şemaları & MT5 Yön Filtresi (Execution Bias Gate)")
    
    # 1. Boru Hattını Başlat
    engine = MacroWorkflowEngine()
    
    # 2. Pipeline'ı Canlı Takvim Verileri ile Çalıştır
    result = engine.run_pipeline()
    
    liq = result.get("liquidity_output", {})
    growth = result.get("growth_output", {})
    strat = result.get("final_output", {})
    metrics = result.get("processed_metrics", {})
    
    # 3. Sonuçları Raporla
    print_separator("1. DETERMINISTIK METRİKLER (Z-SCORE, DELTA, SPREAD & T-0 STRES)")
    yc = metrics.get('yield_curve', {})
    ry = metrics.get('real_yield_info', {})
    cg = metrics.get('copper_gold_analysis', {})
    liq_dyn = metrics.get('liquidity_dynamics', {})
    credit = metrics.get('credit_spread_analysis', {})
    nfci_data = metrics.get('financial_conditions_analysis', {})
    dxy_t = metrics.get('dxy_trend_analysis', {})
    cycle = metrics.get('cycle_diagnosis', {})
    claims = metrics.get('jobless_claims_analysis', {})
    tot = metrics.get('terms_of_trade_energy_analysis', {})
    transatlantic = metrics.get('transatlantic_analysis', {})
    t0_stress = metrics.get('t0_fast_stress_analysis', {})
    btc_dec = metrics.get('btc_decoupling_analysis', {})
    fed_rf = metrics.get('fed_reaction_function', {})

    fwd_path = metrics.get('fed_forward_path_analysis', {})

    print(f"• İktisadi Döngü Teşhisi: {cycle.get('regime_diagnosis')}")
    print(f"  └─ ABD vs Küre Ayrışma: {cycle.get('us_domestic_cycle')} | {cycle.get('global_macro_cycle')}")
    print(f"• İstihdam Sağlığı      : İşsizlik: %{cycle.get('unemployment_rate')} | NFP: {cycle.get('nfp_value')}K | Haftalık ICSA: {claims.get('initial_claims_k')}K ({claims.get('status')})")
    print(f"• Getiri Eğrisi Tipi    : {yc.get('regime')} ({yc.get('spread_bps')} bps) | Kategori: {yc.get('risk_category')}")
    print(f"  └─ Eğim Trendi        : 5G Δ: {yc.get('delta_spread_5d_bps'):+.1f} bps | 20G Δ: {yc.get('delta_spread_20d_bps'):+.1f} bps | 1G Δ (Gürültü): {yc.get('delta_spread_1d_bps'):+.1f} bps")
    print(f"  └─ Trend Gücü         : {'✅ Teyitli Trend (>= ±5.0 bps)' if yc.get('is_trend_significant') else '⚠️ Gürültü Seviyesi (< ±5.0 bps - Range-bound)'}")
    print(f"• Fiyatlanan Faiz Patika: {fwd_path.get('repricing_direction')}")
    print(f"  └─ Fed İndirim Bekl.  : Toplam {abs(fwd_path.get('implied_rate_gap_bps', 0)):.0f} bps gevşeme fiyatlanıyor (2Y 5G Δ: {fwd_path.get('delta_02y_5d_bps'):+.1f} bps)")
    print(f"• Transatlantik Makas   : US10Y ({transatlantic.get('us10y')}%) - DE10Y Bund ({transatlantic.get('de10y_bund')}%) = +{transatlantic.get('spread_bps')} bps")
    print(f"  └─ Makas Yönü & Trend : 20G Δ: {transatlantic.get('delta_spread_20d_bps'):+.1f} bps -> {transatlantic.get('direction')}")
    print(f"• T-0 Anlık Piyasa Stres: {'⚠️ DEVREDE (FRED Baypas Edildi)' if t0_stress.get('fast_stress_override') else '✅ Sakin (Olağan Seyir)'}")
    print(f"  └─ Metrikler          : VIX: {t0_stress.get('vix_level')} (60G Dilim: %{btc_dec.get('vix_pct_60d', 0):.1f}) | HYG/LQD Rasyosu: {t0_stress.get('hyg_lqd_ratio')}")
    print(f"• BTC vs Altın Ayrışması: {'⚠️ AKTİF (BTC DEFENSIVE_HOLD moduna alındı)' if btc_dec.get('btc_decoupling_active') else 'Pasif (Altın & BTC Debasement Kalkanı Beraber)'}")
    print(f"  └─ Ayrışma Nedeni     : {btc_dec.get('rationale')}")
    print(f"• Kredi Makası (HY OAS) : %{credit.get('hy_oas_spread_pct')} -> Durum: {credit.get('stress_level')}")
    print(f"  └─ Hisse Piyasası İması: {credit.get('equity_implication')}")
    print(f"• Finansal Koşullar NFCI: {nfci_data.get('nfci_value')} -> {nfci_data.get('regime')}")
    print(f"  └─ Likidite Tamponu   : {nfci_data.get('buffer_effect')}")
    print(f"• DXY Momentum & Trend  : {dxy_t.get('level')} | 20G: %{dxy_t.get('delta_20d_pct')} ({dxy_t.get('momentum_regime')})")
    print(f"• EURUSD Enerji Kısıtı  : {'⚠️ VAR (NEUTRAL_RANGE)' if tot.get('eurusd_energy_penalty') else 'YOK'} [{tot.get('hysteresis_note')}]")
    print(f"  └─ Dış Ticaret Analizi: {tot.get('rationale')}")
    print(f"• 10Y Reel Getiri       : %{ry.get('real_yield_pct')} [{ry.get('yield_source')}] (Altın baskısı: {ry.get('pressure_on_gold')})")
    print(f"• Net Likidite & TGA    : ${liq_dyn.get('current_net_liquidity_billion'):,.1f}B | 4H Değişim: ${liq_dyn.get('delta_liquidity_billion'):,.1f}B (%{liq_dyn.get('delta_liquidity_pct_4w')})")
    print(f"  └─ TGA Sezonsallık    : {liq_dyn.get('tga_seasonality_note')}")
    print(f"• Bakır / Altın Rasyosu : {cg.get('current_ratio')} | 4H Değişim: %{cg.get('delta_4w_pct')} ({cg.get('momentum_signal')})")
    print("\n📊 STANDARTLAŞTIRILMIŞ VE SINIRLANDIRILMIŞ (CLIPPED) SÜRPRİZLER:")
    for s in metrics.get('surprises', []):
        print(f"  - {s.get('title'):<30}: Gerçekleşen: {s.get('actual')} | Beklenti: {s.get('forecast')} | Z-Score: {s.get('z_score'):>+5.2f}σ [{s.get('interpretation')}]")

    print_separator("2. AJAN 1: LİKİDİTE, KREDİ & TAHVİL ANALİZİ")
    print(f"• Likidite Rejimi       : {liq.get('liquidity_regime')}")
    print(f"• Getiri Eğrisi Dinamiği: {liq.get('yield_curve_dynamic')}")
    print(f"• T-0 Hızlı Stres Durumu: {'⚠️ OVERRIDE' if liq.get('fast_stress_override') else 'Normal'}")
    print(f"• Kredi Stresi          : {liq.get('credit_stress')} | HYG/LQD: {liq.get('hyg_lqd_stress')}")
    print(f"• Finansal Koşullar     : {liq.get('financial_conditions_state')}")
    print(f"• Dolar Baskısı         : {liq.get('dollar_pressure')}")
    print(f"• Güven Skoru           : %{liq.get('confidence', 0)*100:.0f}")
    print(f"• Ana Etken             : {liq.get('key_driver')}")
    print(f"• Özet                  : {liq.get('summary')}")

    print_separator("3. AJAN 2: BÜYÜME & EMTİA ANALİZİ")
    print(f"• Makro Dörtgen         : {growth.get('macro_quadrant')}")
    print(f"• ABD vs Küre Ayrışması : {growth.get('us_vs_global_divergence')}")
    print(f"• Transatlantik Faiz    : +{growth.get('transatlantic_spread_bps')} bps (US10Y - Bund10Y)")
    print(f"• Enerji Şoku Riski     : {'VAR (Riskli)' if growth.get('energy_shock_risk') else 'YOK (Sakin)'}")
    print(f"• EURUSD Ticaret Cezası : {'⚠️ VAR' if growth.get('eurusd_terms_of_trade_penalty') else 'YOK'}")
    print(f"• Büyüme İvmesi         : {growth.get('growth_momentum')}")
    print(f"• Enflasyon Riski       : {growth.get('inflation_risk')}")
    print(f"• Güven Skoru           : %{growth.get('confidence', 0)*100:.0f}")
    print(f"• Özet                  : {growth.get('summary')}")

    print_separator("4. AJAN 3: BAŞ MAKRO STRATEJİST SENTEZİ")
    print(f"• Birincil Rejim        : {strat.get('primary_regime')}")
    print(f"• Sistemik Risk Skoru   : {strat.get('volatility_risk_score')} / 1.0")
    print(f"• Sermaye Koruma Modu   : {'🛡️ AKTİF (Capital Preservation)' if strat.get('capital_preservation_mode') else 'NORMAL (Risk İştahı Açık)'}")
    print(f"• BTC Ayrışması (Decoup): {'⚠️ DEFENSIVE_HOLD Modunda' if strat.get('btc_decoupling_active') else 'Normal (Debasement Takibi)'}")
    print(f"• Histeresis Durumu     : {'✅ Korundu' if strat.get('hysteresis_active') else 'Standart'}")
    print(f"• Önerilen Risk Çarpanı : {strat.get('recommended_risk_multiplier', 1.0)}x")
    print("\n📊 VARLIK YÖN BEKLENTİLERİ (BIAS):")
    for asset, bias in strat.get('asset_biases', {}).items():
        print(f"  - {asset:<8}: {bias}")

    print("\n🛡️ İŞLEM İZİN VE SAVUNMA KAPILARI (EXECUTION GATES):")
    for asset, gate in strat.get('execution_bias_gates', {}).items():
        print(f"  - {asset:<8}: {gate}")

    print(f"\n📝 Stratejik Rapor:\n{strat.get('macro_rationale')}")

    # 4. Canlı MT5 Gate Testi
    print_separator("5. MT5 KÖPRÜSÜ DOĞRULAMA TESTİ")
    bridge = ExecutionBiasBridge()
    test_trades = [
        ("XAUUSD", "BUY"),
        ("XAUUSD", "SELL"),
        ("EURUSD", "BUY"),
        ("EURUSD", "SELL"),
        ("BTC", "BUY"),
        ("BTC", "SELL")
    ]
    for sym, act in test_trades:
        allowed, reason = bridge.is_trade_allowed(sym, act)
        status = "✅ İZİN VERİLDİ" if allowed else "⛔ ENGELLENDİ"
        print(f"[{status}] {sym:<6} {act:<4} -> {reason}")

    print_separator("SİSTEM ÇALIŞMASI BAŞARIYLA TAMAMLANDI")

if __name__ == "__main__":
    main()
