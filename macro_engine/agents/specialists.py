import logging
from typing import Dict, Any
from core.key_manager import DualCascadeRouter
from agents.schemas import LiquidityOutput, GrowthOutput, MacroStrategistOutput

logger = logging.getLogger("MacroSpecialistAgents")

class MacroSpecialists:
    def __init__(self):
        self.router = DualCascadeRouter()

    def analyze_liquidity(self, metrics: Dict[str, Any]) -> LiquidityOutput:
        """
        Ajan 1: Likidite, Kredi ve Finansal Koşullar Analisti
        Getiri eğrisi trendi, Net Likidite Deltası (Δ4W), HY OAS Kredi Makası, NFCI ve DXY analiz edilir.
        """
        yc = metrics.get('yield_curve', {})
        liq_dyn = metrics.get('liquidity_dynamics', {})
        ry = metrics.get('real_yield_info', {})
        credit = metrics.get('credit_spread_analysis', {})
        nfci_data = metrics.get('financial_conditions_analysis', {})
        dxy_trend = metrics.get('dxy_trend_analysis', {})
        t0_stress = metrics.get('t0_fast_stress_analysis', {})

        prompt = f"""
        Aşağıdaki dinamik ve delta destekli likidite metriklerini kurumsal bir tahvil/likidite uzmanı olarak değerlendir:
        
        [T-0 ANLIK PİYASA STRESİ DEVRE KESİCİSİ (FAST STRESS OVERRIDE)]:
        - Fast Stress Devrede mi?: {t0_stress.get('fast_stress_override')}
        - Tetikleyiciler: {t0_stress.get('triggers')}
        - HYG / LQD Kredi Oranı: {t0_stress.get('hyg_lqd_ratio')} (1G: %{t0_stress.get('hyg_lqd_delta_1d_pct')}, 5G: %{t0_stress.get('hyg_lqd_delta_5d_pct')})
        - VIX Seviyesi & Değişimi: {t0_stress.get('vix_level')} (1G: %{t0_stress.get('vix_delta_1d_pct')}, 5G: %{t0_stress.get('vix_delta_5d_pct')})
        - Uyarı: {t0_stress.get('warning')}
        
        [GETİRİ EĞRİSİ VE ÇOKLU ZAMAN DİLİMLİ SLOPE TRENDİ]:
        - Eğri Rejimi: {yc.get('regime')} ({yc.get('spread_bps')} bps)
        - Risk Kategorisi: {yc.get('risk_category')}
        - 5 Günlük Spread Değişimi (ΔSpread_5D): {yc.get('delta_spread_5d_bps')} bps
        - 20 Günlük Spread Değişimi (ΔSpread_20D): {yc.get('delta_spread_20d_bps')} bps
        - 1 Günlük Mikro Değişim (Gürültü): {yc.get('delta_spread_1d_bps')} bps
        - 10Y 5G Değişimi: {yc.get('delta_10y_5d_bps')} bps | 2Y 5G Değişimi: {yc.get('delta_02y_5d_bps')} bps
        - Teknik Tanım: {yc.get('description')}
        - 10Y Doğrudan Reel Getiri: %{ry.get('real_yield_pct')} [{ry.get('yield_source')}] ({ry.get('pressure_on_gold')})
        
        [HAFTALIK ÖNCÜ İSTİHDAM (FRED ICSA)]:
        - Haftalık İlk İşsizlik Başvuruları: {metrics.get('jobless_claims_analysis', {}).get('initial_claims_k')}K
        - İstihdam Öncü Durumu: {metrics.get('jobless_claims_analysis', {}).get('status')}
        - Sinyal: {metrics.get('jobless_claims_analysis', {}).get('leading_signal')}
        
        [KREDİ PİYASASI & ŞİRKET TAHVİL MAKASI (HY OAS)]:
        - ABD Yüksek Getirili Şirket Makası (BAMLH0A0HYM2): %{credit.get('hy_oas_spread_pct')}
        - Kredi Stres Seviyesi: {credit.get('stress_level')}
        - Kredi Piyasası Mesajı: {credit.get('equity_implication')}
        
        [FİNANSAL KOŞULLAR ENDEKSİ (CHICAGO FED NFCI)]:
        - NFCI Değeri: {nfci_data.get('nfci_value')} ({nfci_data.get('regime')})
        - Likidite Tamponu: {nfci_data.get('buffer_effect')}
        
        [LİKİDİTE AKIŞ HIZI (DELTA LIQUIDITY)]:
        - Güncel Net Likidite: ${liq_dyn.get('current_net_liquidity_billion'):,.1f}B
        - 4 Haftalık Net Likidite Değişimi (Δ): ${liq_dyn.get('delta_liquidity_billion'):,.1f}B (%{liq_dyn.get('delta_liquidity_pct_4w')})
        - Akış Yönü: {liq_dyn.get('flow_direction')}
        - TGA Sezonsallık Durumu: {liq_dyn.get('tga_seasonality_note')}
        
        [DÖVİZ VE DXY MOMENTUMU]:
        - DXY Seviyesi: {dxy_trend.get('level')} | 20G Momentum: %{dxy_trend.get('delta_20d_pct')} ({dxy_trend.get('momentum_regime')})
        - Uyarı Notu: {dxy_trend.get('warning')}
        
        ANALİZ KURALLARI:
        1. T-0 stres ile haftalık kredi/finansal koşullarını ayrı zaman ufukları olarak raporla; birini diğerinin "geçersiz kılması" varsayımını yapma.
        2. DXY seviyesi ve momentumunu birlikte değerlendir; tek başına psikolojik eşik kullanarak yön zorlaması yapma.
        3. HY OAS ile HYG/LQD'yi birlikte değerlendir; benign bir kredi spreadini "temerrüt riski yok" şeklinde yorumlama.
        4. ICSA'yı kendi haftalık işsizlik başvurusu serisi olarak kullan; NFP'nin gerçekleşmesini teyit ettiği iddiasında bulunma.
        5. TGA VERGİ SEZONSALLIĞI: Eğer is_tga_tax_season True ise ({liq_dyn.get('is_tga_tax_season')}), bunun likidite ölçümünü etkileyebileceğini belirt; kalıcı kriz sonucu çıkarma.
        """
        system_instruction = (
            "Sen Wall Street düzeyinde çalışan bir Baş Likidite, Kredi ve Tahvil Piyasası Analistisin. "
            "Fed bilançosuna, T-0 anlık piyasa stresine (HYG/LQD, VIX), haftalık ICSA istihdamına ve Chicago Fed NFCI endeksine bakarsın."
        )

        logger.info("🌊 [Ajan 1: Likidite Analisti] Çalışıyor...")
        return self.router.execute_structured(
            role="analyst",
            prompt=prompt,
            schema=LiquidityOutput,
            system_instruction=system_instruction
        )

    def analyze_growth_and_commodities(self, metrics: Dict[str, Any]) -> GrowthOutput:
        """
        Ajan 2: Büyüme ve Emtia Analisti
        ABD İstisnacılığı ile Küresel İmalat Yavaşlaması ve Transatlantik Faiz Makasını modeller.
        """
        cg = metrics.get('copper_gold_analysis', {})
        cycle = metrics.get('cycle_diagnosis', {})
        energy_tot = metrics.get('terms_of_trade_energy_analysis', {})
        transatlantic = metrics.get('transatlantic_analysis', {})

        prompt = f"""
        Aşağıdaki büyüme, emtia ve döngü ayrışması verilerini değerlendir:
        
        [ABD İSTİSNACILIĞI VS KÜRESEL DÖNGÜ AYRIŞMASI]:
        - ABD İç Piyasası: {cycle.get('us_domestic_cycle')} (İşsizlik: %{cycle.get('unemployment_rate')}, NFP: {cycle.get('nfp_value')}K, ICSA: {cycle.get('icsa_claims')}K)
        - Küresel Sanayi Döngüsü: {cycle.get('global_macro_cycle')} (Bakır/Altın 4H Δ: %{cg.get('delta_4w_pct')})
        - Döngü Teşhisi: {cycle.get('regime_diagnosis')}
        - Rasyonel: {cycle.get('rationale')}
        
        [TRANSATLANTİK FAİZ MAKASI (US10Y - ALMANYA 10Y BUND)]:
        - US 10Y: %{transatlantic.get('us10y')} | Almanya 10Y Bund: %{transatlantic.get('de10y_bund')}
        - Makas: +{transatlantic.get('spread_bps')} bps (20G Δ: {transatlantic.get('delta_spread_20d_bps')} bps)
        - Yön: {transatlantic.get('direction')}
        - İma: {transatlantic.get('implication')}
        
        [DIŞ TİCARET HADLERİ & ENERJİ ŞOKU (HİSTERESİS KORUMALI)]:
        - Brent Petrol: ${metrics.get('brent_level')}
        - EURUSD Enerji Cezası: {'VAR' if energy_tot.get('eurusd_energy_penalty') else 'YOK'}
        - Histeresis Durumu: {energy_tot.get('hysteresis_note')}
        - Enerji Analizi: {energy_tot.get('rationale')}
        
        [STANDARTLAŞTIRILMIŞ SÜRPRİZLER (Z-SCORES)]:
        {metrics.get('surprises')}
        
        ANALİZ KURALLARI:
        1. Makro dörtgeni yalnızca istihdamdan çıkarma; enflasyon, büyüme, aktivite ve enerji göstergelerini birlikte değerlendir.
        2. ABD-küresel ayrışması varsa bunu ilgili ölçülebilir kanıtlarla açıkla; Bakır/Altın oranını tek başına küresel büyümenin kesin kanıtı gibi sunma.
        3. Transatlantik spread seviyesini ve yönünü aktar; enerji/terms-of-trade cezasını ayrı bir kanal olarak değerlendir.
        4. Bir ekonomik rejim için kanıtlar çatışıyorsa "MIXED" veya belirsizlik belirt; zorunlu etiketleme yapma.
        """
        system_instruction = (
            "Sen Bridgewater Associates standartlarında çalışan bir Kıdemli Makro Dörtgen ve Emtia Analistisin. "
            "ABD İstisnacılığı ile küresel sanayi yavaşlaması arasındaki makası ve Transatlantik faiz makasını teşhis edersin."
        )

        logger.info("📈 [Ajan 2: Büyüme & Emtia Analisti] Çalışıyor...")
        return self.router.execute_structured(
            role="analyst",
            prompt=prompt,
            schema=GrowthOutput,
            system_instruction=system_instruction
        )

    def synthesize_macro_regime(
        self,
        liquidity: LiquidityOutput,
        growth: GrowthOutput,
        metrics: Dict[str, Any]
    ) -> MacroStrategistOutput:
        """
        Ajan 3: Baş Makro Stratejist & Karar Motoru
        Ajan 1 ve Ajan 2 çıktılarını çapraz kontrol eder; BTC decoupling, histeresis, EURUSD enerji tuzağı ve Fed reaksiyon fonksiyonunu yansıtır.
        """
        yc = metrics.get('yield_curve', {})
        ry = metrics.get('real_yield_info', {})
        liq_dyn = metrics.get('liquidity_dynamics', {})
        cg = metrics.get('copper_gold_analysis', {})
        credit = metrics.get('credit_spread_analysis', {})
        nfci_data = metrics.get('financial_conditions_analysis', {})
        dxy_trend = metrics.get('dxy_trend_analysis', {})
        cycle = metrics.get('cycle_diagnosis', {})
        claims = metrics.get('jobless_claims_analysis', {})
        tot_energy = metrics.get('terms_of_trade_energy_analysis', {})
        transatlantic = metrics.get('transatlantic_analysis', {})
        t0_stress = metrics.get('t0_fast_stress_analysis', {})
        btc_dec = metrics.get('btc_decoupling_analysis', {})
        regime_st = metrics.get('regime_state', {})
        fed_rf = metrics.get('fed_reaction_function', {})
        cross_analysis = metrics.get('cross_pairs_analysis', {})
        cross_gates = cross_analysis.get('cross_gates', {}) or regime_st.get('cross_pair_gates', {}) or {}
        market_price_context = metrics.get('market_price_context', {})
        economic_panel = metrics.get('economic_regime_snapshot', {})
        policy_panel = metrics.get('policy_expectations', {})

        prompt = f"""
        Aşağıdaki iki uzman analist raporunu, doğrulanmış piyasa fiyat bağlamını, tam ekonomik paneli,
        politika beklentilerini ve çapraz piyasa metriklerini değerlendirip makro sentez üret:

        [DOĞRULANMIŞ PİYASA FİYAT BAĞLAMI]:
        {market_price_context}

        FİYAT KURALı:
        - Bu bağlamda bulunmayan hiçbir kesin fiyat, destek, direnç, hedef veya fiyat aralığı uydurma.
        - Teknik destek/direnç bu makro katmanda hesaplanmıyorsa fiyat seviyesi verme.
        - Makro yön ile teknik giriş seviyesini birbirine karıştırma.
        
        [TAM EKONOMİK PANEL - AYRI BOYUTLAR]:
        - Enflasyon: {economic_panel.get('inflation_regime', {})}
        - İstihdam: {economic_panel.get('labor_regime', {})}
        - Büyüme: {economic_panel.get('growth_regime', {})}
        - Sanayi & Reel İvme: INDPRO + GDPC1 + Bakır/Altın rasyosu aktif (Not: FRED kamu API'sinden kaldırılan eski ISM PMI serisi yapısal olarak INDPRO/Bakır-Altın ile ikame edilmiştir, bunu veri eksikliği olarak raporlama)
        - Getiri Eğrisi: {economic_panel.get('rate_curve_regime', {})}
        - Politika Rejimi: {economic_panel.get('policy_regime', {})}

        [POLİTİKA BEKLENTİLERİ]:
        {policy_panel}

        [AJAN 1 - LİKİDİTE, KREDİ VE TAHVİL]:
        - Likidite Rejimi: {liquidity.liquidity_regime}
        - Getiri Eğrisi Dinamiği: {liquidity.yield_curve_dynamic}
        - T-0 Fast Stress Override: {liquidity.fast_stress_override}
        - Kredi Stresi (HY OAS): {liquidity.credit_stress} (%{credit.get('hy_oas_spread_pct')})
        - Finansal Koşullar (NFCI): {liquidity.financial_conditions_state} ({nfci_data.get('nfci_value')})
        - Dolar Baskısı: {liquidity.dollar_pressure}
        - Özet: {liquidity.summary}
        
        [AJAN 2 - BÜYÜME VE EMTİA]:
        - Makro Dörtgen: {growth.macro_quadrant}
        - ABD vs Küresel Ayrışma: {growth.us_vs_global_divergence}
        - Enerji Şoku Riski: {growth.energy_shock_risk}
        - Transatlantik Faiz Makası (US-DE Bund): +{growth.transatlantic_spread_bps} bps
        - EURUSD Enerji Cezası: {growth.eurusd_terms_of_trade_penalty}
        - Büyüme İvmesi: {growth.growth_momentum}
        - Enflasyon Riski: {growth.inflation_risk}
        - Özet: {growth.summary}
        
        [KRİTİK DOĞRULAMA VE HİPOTEZ TESTİ METRİKLERİ]:
        - Gerçek Döngü Teşhisi: {cycle.get('regime_diagnosis')} (İşsizlik: %{cycle.get('unemployment_rate')}, NFP: {cycle.get('nfp_value')}K, ICSA: {claims.get('initial_claims_k')}K)
        - DXY Durumu: Seviye {dxy_trend.get('level')}, 20G: %{dxy_trend.get('delta_20d_pct')} ({dxy_trend.get('momentum_regime')})
        - Transatlantik Faiz Makası: +{transatlantic.get('spread_bps')} bps ({transatlantic.get('direction')})
        - EURUSD Enerji Şoku / Dış Ticaret Hadleri: {tot_energy.get('rationale')}
        - Önerilen EURUSD Kapısı: {tot_energy.get('recommended_eurusd_gate')}
        - BTC vs Altın Ayrışması (Decoupling): {btc_dec.get('btc_decoupling_active')} | Önerilen BTC Kapısı: {btc_dec.get('recommended_btc_gate')}
        - BTC Ayrışma Nedeni: {btc_dec.get('rationale')}
        - T-0 Hızlı Piyasa Stresi: {t0_stress.get('warning')}
        - Fed Tepki Fonksiyonu: {fed_rf.get('rate_path_expectation')} | {fed_rf.get('equity_multiple_cap')}
        - Kredi Makası (HY OAS): %{credit.get('hy_oas_spread_pct')} ({credit.get('stress_level')})
        - 10Y Reel Getiri: %{ry.get('real_yield_pct')} [{ry.get('yield_source')}]
        - 4H Net Likidite Deltası (Δ): ${liq_dyn.get('delta_liquidity_billion')}B (%{liq_dyn.get('delta_liquidity_pct_4w')}) | TGA Notu: {liq_dyn.get('tga_seasonality_note')}
        - Bakır/Altın Momentum Deltası: %{cg.get('delta_4w_pct')}
        - Para Birimi Güç Puanları (3-Faktör): {regime_st.get('cross_currency_scores', {})}
        - Dolar Majörleri Kapıları: USDJPY: {cross_gates.get('USDJPY', 'NEUTRAL_RANGE')}, GBPUSD: {cross_gates.get('GBPUSD', 'NEUTRAL_RANGE')}, USDCAD: {cross_gates.get('USDCAD', 'NEUTRAL_RANGE')}, USDCHF: {cross_gates.get('USDCHF', 'NEUTRAL_RANGE')}
        - UK Policy Evidence: {economic_panel.get('uk_policy', {})}
        - Canada Policy Evidence: {economic_panel.get('canada_policy', {})}
        
        ANALİZ SÖZLEŞMESİ:
        1. VERİYİ ÖNCELE: Sonucu önceden varsayma. Her yönsel çıkarımı, onu destekleyen ölçülebilir faktörlerle açıkla.
        2. TEK FAKTÖR YETMEZ: Bir varlık/parite için LONG/SHORT yönü tek bir göstergeye dayanıyorsa bunu düşük güven olarak belirt ve çatışma varsa nötr kal.
        3. BAĞIMSIZ KANIT: Faiz/reel getiri, dolar momentumu, likidite/kredi, emtia/dış ticaret ve risk iştahı gibi farklı mekanizmaların aynı yönde olup olmadığını kontrol et.
        4. VERİ EKSİKLİĞİ: Yalnızca aktif canlı piyasa/makro beslemelerinde gerçek bir kopukluk veya bayat veri varsa uyar; FRED'den kalıcı olarak kaldırılmış eski ISM PMI serilerini (INDPRO ve Bakır/Altın ile ikame edildiği için) raporda "Veri Eksikliği" maddesi olarak yazma.
        5. GATE AYRIMI: execution_bias_gates alanı yalnızca advisory analizdir. Gerçek execution kararı deterministic gate katmanından gelir.
        6. BTC: Debasement teması tek başına LONG gerekçesi değildir; likidite, reel faiz, dolar, kredi ve T-0 stres ile birlikte değerlendir.
        7. XAUUSD: Reel getiri, dolar, risk iştahı ve enerji/enflasyon kanallarını birlikte değerlendir; yapısal görüşü kısa vadeli işlem yönüyle karıştırma.
        8. EURUSD: US-DE faiz farkı seviyesini, değişimini, DXY momentumunu ve Euro enerji/terms-of-trade durumunu birlikte değerlendir.
        9. USD MAJÖRLERİ / ÇAPRAZLAR: Ülke faiz farkının hem seviyesi hem değişimi; mevcut emtia/risk faktörleri ve veri yeterliliği ile birlikte değerlendir. Bir ülkenin yalnızca tek faktörü güçlü diye "ONLY" yönü dayatma.
        10. FİYAT: [DOĞRULANMIŞ PİYASA FİYAT BAĞLAMI] dışında kesin fiyat, destek, direnç, hedef veya fiyat aralığı uydurma. Teknik seviye bu katmanda hesaplanmıyorsa sayı verme.
        11. ZAMAN UFKU:
           - horizon_today: Makro yön, risk durumu ve hangi teyidin bekleneceği. Kesin fiyat verme.
           - horizon_this_week: Faiz, likidite, kredi ve yaklaşan makro olayların yön etkisi. Kesin fiyat verme.
           - horizon_this_month: Makro rejim ve senaryo rotası. Kesin fiyat verme.
        12. ÇATIŞMA RAPORU: Bullish ve bearish kanıtlar birlikte varsa ikisini de belirt; yapay kesinlik üretme.
        """
        system_instruction = (
            "Sen küresel bir makro yatırım komitesi için kanıt-odaklı sentez üreten kıdemli bir makro stratejistsin. "
            "Veri kaynaklarını, zaman ufuklarını, çelişkili sinyalleri ve belirsizliği açıkça ayır; sonuçları önceden varsayma."
        )

        logger.info("🧠 [Ajan 3: Baş Makro Stratejist] Asimetrik Rejim Sentezi Üretiyor...")
        return self.router.execute_structured(
            role="strategist",
            prompt=prompt,
            schema=MacroStrategistOutput,
            system_instruction=system_instruction
        )
