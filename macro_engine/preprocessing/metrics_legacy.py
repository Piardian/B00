import math
import logging
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import HYSTERESIS_CONFIG, BIAS_GATE_FILE, NEWS_FREEZE_CONFIG

logger = logging.getLogger("MacroMetricsCalculator")

# Tarihsel 12 Aylık Standart Sapmalar (Z-Score birim denkleştirmesi)
HISTORICAL_SIGMAS = {
    "cpi": 0.12,           # Aylık % sapma std dev (~0.12%)
    "core_cpi": 0.10,      # Çekirdek TÜFE std dev (~0.10%)
    "nfp": 50.0,           # Bin (K) kişi sapma std dev (~50K)
    "unemployment": 0.15,  # İşsizlik oranı % sapma std dev (~0.15%)
    "pmi": 1.5,            # ISM / S&P PMI puan sapma std dev (~1.5 puan)
    "gdp": 0.50,           # GSYİH % sapma std dev
    "retail_sales": 0.40,  # Perakende satışlar % sapma std dev
    "generic": 1.0
}


class MacroMetricsCalculator:
    """
    Ham piyasa ve takvim verilerini matematiksel ve istatistiksel
    olarak standartlaştırılmış metrik rejimlerine dönüştürür.
    """

    @staticmethod
    def identify_indicator_type(title: str) -> str:
        """Haber başlığından göstergenin türünü güvenle tespit eder."""
        t = title.lower()
        if any(term in t for term in ["non-farm", "nfp", "payrolls", "employment change"]):
            return "nfp"
        elif any(term in t for term in ["unemployment rate", "jobless rate"]):
            return "unemployment"
        elif "core cpi" in t:
            return "core_cpi"
        elif "cpi" in t or "inflation" in t:
            return "cpi"
        elif "pmi" in t:
            return "pmi"
        elif "gdp" in t:
            return "gdp"
        elif "retail" in t:
            return "retail_sales"
        return "generic"

    @staticmethod
    def calculate_surprise_zscore(indicator_type: str, actual: float, forecast: float) -> float:
        """
        Standardize Edilmiş Sürpriz Endeksi (Z-Score):
        S = (Gerçekleşen - Beklenti) / σ_12m
        Uç değer distorsiyonlarını önlemek için [-4.0, +4.0] aralığına sınırlandırılır (clipped).
        """
        sigma = HISTORICAL_SIGMAS.get(indicator_type.lower(), 1.0)
        raw_diff = actual - forecast
        zscore = raw_diff / sigma
        
        # [-4.0, +4.0] sigma aralığına sınırla
        clipped_z = max(-4.0, min(4.0, round(zscore, 2)))
        return clipped_z

    @staticmethod
    def evaluate_yield_curve(
        us10y: float,
        us02y: float,
        us10y_prev: Optional[float] = None,
        us02y_prev: Optional[float] = None,
        us10y_5d: Optional[float] = None,
        us02y_5d: Optional[float] = None,
        us10y_20d: Optional[float] = None,
        us02y_20d: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Getiri Eğrisi Durumu (US10Y - US02Y spread ve çoklu zaman dilimli Slope Trendi):
        - 1 Günlük mikro hareketler (örn. 1.6 bps) istatistiksel gürültüdür (noise).
        - 5 Günlük (ΔSpread_5D) ve 20 Günlük (ΔSpread_20D) bileşik eğim teyidi aranır.
        - Değişim en az ±5.0 bps eşiğini aşmadıkça 'Range-bound Slope' olarak korunur, testere (whipsaw) engellenir.
        """
        spread_bps = round((us10y - us02y) * 100, 1)

        # 1 Günlük Değişimler
        u10_prev = us10y_prev if us10y_prev is not None else us10y
        u02_prev = us02y_prev if us02y_prev is not None else us02y
        prev_spread_bps = round((u10_prev - u02_prev) * 100, 1)
        delta_spread_1d = round(spread_bps - prev_spread_bps, 1)
        delta_10y_1d = round((us10y - u10_prev) * 100, 1)
        delta_02y_1d = round((us02y - u02_prev) * 100, 1)

        # 5 Günlük Değişimler (Slope Trend)
        u10_5d = us10y_5d if us10y_5d is not None else u10_prev
        u02_5d = us02y_5d if us02y_5d is not None else u02_prev
        spread_5d_bps = round((u10_5d - u02_5d) * 100, 1)
        delta_spread_5d = round(spread_bps - spread_5d_bps, 1)
        delta_10y_5d = round((us10y - u10_5d) * 100, 1)
        delta_02y_5d = round((us02y - u02_5d) * 100, 1)

        # 20 Günlük Değişimler (1 Aylık Ana Trend)
        u10_20d = us10y_20d if us10y_20d is not None else u10_5d
        u02_20d = us02y_20d if us02y_20d is not None else u02_5d
        spread_20d_bps = round((u10_20d - u02_20d) * 100, 1)
        delta_spread_20d = round(spread_bps - spread_20d_bps, 1)

        # Gürültü Filtresi: 5 günlük spread değişimi en az ±5.0 bps veya 20 günlük en az ±8.0 bps olmalı
        is_trend_significant = abs(delta_spread_5d) >= 5.0 or abs(delta_spread_20d) >= 8.0
        is_inverted = (spread_bps < 0)

        if not is_trend_significant:
            regime = "Inverted" if is_inverted else "Range-bound Slope"
            risk_category = "High Recession Risk" if is_inverted else "Stable / Noise Level"
            description = (
                f"Ters Getiri Eğrisi ({spread_bps} bps). Eğim yatay, geç döngü resesyon uyarısı."
                if is_inverted
                else f"Getiri Eğrisi Yatay / Gürültü Seviyesi ({spread_bps} bps | 5G Δ: {delta_spread_5d:+.1f} bps | 1G Δ: {delta_spread_1d:+.1f} bps). "
                f"Tekil gün oynamaları istatistiksel gürültü kabul edilir; rejim testeresi engellendi."
            )
        elif delta_spread_5d >= 5.0 or delta_spread_20d >= 8.0:
            # Eğri DİKLEŞİYOR (Steepening) - Ters eğriden çıkış veya pozitif eğride dikleşme
            # Dominant uç analizi: Dikleşmeyi 10Y faiz sıçraması mı (Bear Steepening) yoksa 2Y faiz çöküşü mü (Bull Steepening) sürüyor?
            if delta_10y_5d > 0 and delta_10y_5d >= abs(delta_02y_5d):
                regime = "Bear Steepening"
                risk_category = "Term Premium / Fiscal Supply or Inflation Risk"
                description = (
                    f"Bear Steepening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps | 10Y 5G Δ: {delta_10y_5d:+.1f} bps). "
                    f"Uzun vadeli faizler vade primi (term premium), Hazine tahvil arzı baskısı veya yapışkan enflasyon riskiyle yükseliyor."
                )
            elif delta_02y_5d < 0 and abs(delta_02y_5d) > delta_10y_5d:
                regime = "Bull Steepening"
                risk_category = "Recessionary Easing (Panik/Kriz İndirimi)"
                description = (
                    f"Bull Steepening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps | 2Y 5G Δ: {delta_02y_5d:+.1f} bps). "
                    f"DİKKAT: 2Y faizlerindeki çöküş Fed acil resesyon indirimine işaret eder; hisse senedi (SPX) için ralli değil düzeltme/çöküş riskidir!"
                )
            elif delta_10y_5d >= 0:
                regime = "Bear Steepening"
                risk_category = "Term Premium / Fiscal Supply or Inflation Risk"
                description = (
                    f"Bear Steepening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps | 10Y 5G Δ: {delta_10y_5d:+.1f} bps). "
                    f"Uzun vadeli faiz artışı getiri eğrisini dikleştiriyor."
                )
            else:
                regime = "Bull Steepening"
                risk_category = "Recessionary Easing (Panik/Kriz İndirimi)"
                description = (
                    f"Bull Steepening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps | 2Y 5G Δ: {delta_02y_5d:+.1f} bps). "
                    f"Kısa vadeli faiz düşüşü getiri eğrisini dikleştiriyor."
                )
        else:
            # Eğri YATIKLAŞIYOR (Flattening)
            # Dominant uç analizi: Yatıklaşmayı 2Y yükselişi mi (Bear Flattening) yoksa 10Y düşüşü mü (Bull Flattening) sürüyor?
            if delta_02y_5d > 0 and delta_02y_5d >= abs(delta_10y_5d):
                regime = "Bear Flattening"
                risk_category = "Monetary Tightening"
                description = f"Bear Flattening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps | 2Y 5G Δ: {delta_02y_5d:+.1f} bps). Kısa vadeli faizler Fed sıkılaşmasıyla yükseliyor."
            elif delta_10y_5d < 0 and abs(delta_10y_5d) > delta_02y_5d:
                regime = "Bull Flattening"
                risk_category = "Disinflation"
                description = f"Bull Flattening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps | 10Y 5G Δ: {delta_10y_5d:+.1f} bps). Uzun vadeli tahvillere güvenli liman girişi."
            elif delta_02y_5d >= 0:
                regime = "Bear Flattening"
                risk_category = "Monetary Tightening"
                description = f"Bear Flattening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps). Kısa uç faiz baskısı."
            else:
                regime = "Bull Flattening"
                risk_category = "Disinflation"
                description = f"Bull Flattening ({spread_bps} bps | 5G ΔSpread: {delta_spread_5d:+.1f} bps). Uzun uç getiri düşüşü."

        return {
            "spread_bps": spread_bps,
            "regime": regime,
            "risk_category": risk_category,
            "description": description,
            "delta_spread_1d_bps": delta_spread_1d,
            "delta_spread_5d_bps": delta_spread_5d,
            "delta_spread_20d_bps": delta_spread_20d,
            "delta_10y_5d_bps": delta_10y_5d,
            "delta_02y_5d_bps": delta_02y_5d,
            "is_trend_significant": is_trend_significant
        }

    @staticmethod
    def calculate_real_yield(
        us10y: float,
        dfii10_tips: Optional[float] = None,
        breakeven_10y: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Reel Getiri:
        1. Öncelik: FRED DFII10 (10-Year TIPS Constant Maturity - Doğrudan Piyasa Reel Faizi)
        2. İkincil / Yedek: US10Y Nominal Getiri - 10Y Breakeven Enflasyon Oranı (T10YIE)
        
        Reel faiz > %2.0 ise Altın (XAUUSD) üzerinde yüksek fırsat maliyeti baskısı oluşur.
        """
        if dfii10_tips is not None and dfii10_tips > 0:
            real_yield = round(dfii10_tips, 3)
            source = "FRED DFII10 (Doğrudan 10Y TIPS Reel Getirisi)"
        else:
            be = breakeven_10y if breakeven_10y is not None else 2.15
            real_yield = round(us10y - be, 3)
            source = f"Sentetik (US10Y {us10y}% - Breakeven {be}%)"

        if real_yield >= 1.90:
            pressure_on_gold = (
                "High Fırsat Maliyeti (Reel Faiz >= %1.90; Pozitif Taşıma Maliyeti & Süre Riski - "
                "Altında 'NEUTRAL_RANGE' Önerilir, Faiz Baskısı Bitene Dek Yeni Long Kısıtlanır)"
            )
        elif real_yield < 1.0:
            pressure_on_gold = "Low (Destekleyici; Negatif/Düşük Reel Faiz Altını Besler)"
        else:
            pressure_on_gold = "Moderate (Dengeli; Mali Hakimiyet ve Jeopolitik Talep Ön Planda)"

        return {
            "real_yield_pct": real_yield,
            "yield_source": source,
            "pressure_on_gold": pressure_on_gold,
            "description": f"10Y Reel Getiri: %{real_yield} [{source}] (Altın baskısı: {pressure_on_gold})"
        }

    @staticmethod
    def calculate_correlation(series_a: List[float], series_b: List[float]) -> float:
        """Pearson Korelasyon Katsayısı (-1.0 ile +1.0 arası)."""
        if len(series_a) != len(series_b) or len(series_a) < 3:
            return 0.0

        n = len(series_a)
        mean_a = sum(series_a) / n
        mean_b = sum(series_b) / n

        var_a = sum((x - mean_a) ** 2 for x in series_a)
        var_b = sum((y - mean_b) ** 2 for y in series_b)

        if var_a == 0 or var_b == 0:
            return 0.0

        cov = sum((series_a[i] - mean_a) * (series_b[i] - mean_b) for i in range(n))
        r = cov / (math.sqrt(var_a) * math.sqrt(var_b))
        return round(r, 2)

    def process_all_macro_data(
        self,
        market_data: Dict[str, Any],
        fred_data: Dict[str, Any],
        calendar_events: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Tüm ham verileri delta ve momentum destekli deterministik makro metrik paketine derler."""
        us10y_data = market_data.get("US10Y", {})
        us02y_data = market_data.get("US02Y", {})
        us10y = us10y_data.get("value", 3.88)
        us02y = us02y_data.get("value", 3.94)
        us10y_prev = us10y_data.get("prev", us10y)
        us02y_prev = us02y_data.get("prev", us02y)
        us10y_5d = us10y_data.get("val_5d_ago", us10y_prev)
        us02y_5d = us02y_data.get("val_5d_ago", us02y_prev)
        us10y_20d = us10y_data.get("month_ago", us10y_5d)
        us02y_20d = us02y_data.get("month_ago", us02y_5d)

        dfii10 = fred_data.get("DFII10")
        t10yie = fred_data.get("T10YIE", 2.15)
        dxy = market_data.get("DXY", {}).get("value", 104.2)
        brent = market_data.get("BRENT", {}).get("value", 78.4)
        gold = market_data.get("GOLD", {}).get("value", 2480.0)
        copper = market_data.get("COPPER", {}).get("value", 4.15)

        # 1. Getiri Eğrisi (Gürültü Filtreli 5G/20G Slope Trend Analizi)
        yield_curve = self.evaluate_yield_curve(
            us10y, us02y, us10y_prev, us02y_prev,
            us10y_5d, us02y_5d, us10y_20d, us02y_20d
        )

        # 2. Reel Getiri (Öncelik: FRED DFII10 Doğrudan TIPS Oranı)
        real_yield_info = self.calculate_real_yield(us10y, dfii10_tips=dfii10, breakeven_10y=t10yie)

        # 3. Bakır / Altın Rasyosu ve 4 Haftalık Momentum Deltası (Δ%)
        current_ratio = round((copper / gold) * 1000, 3) if gold else 1.50
        gold_month_ago = market_data.get("GOLD", {}).get("month_ago", gold)
        copper_month_ago = market_data.get("COPPER", {}).get("month_ago", copper)
        prev_ratio = round((copper_month_ago / gold_month_ago) * 1000, 3) if gold_month_ago else current_ratio
        ratio_delta_4w_pct = round(((current_ratio - prev_ratio) / prev_ratio) * 100, 2) if prev_ratio else 0.0

        copper_gold_analysis = {
            "current_ratio": current_ratio,
            "ratio_4w_ago": prev_ratio,
            "delta_4w_pct": ratio_delta_4w_pct,
            "momentum_signal": "Büyüme İvmeleniyor (İmalat Talebi)" if ratio_delta_4w_pct > 2.0 else "Büyüme Yavaşlıyor (Altına Kaçış)" if ratio_delta_4w_pct < -2.0 else "Nötr / Yatay"
        }

        # 4. 5 Günlük DXY x Brent Korelasyonu
        dxy_hist = market_data.get("DXY", {}).get("history_close", [])
        brent_hist = market_data.get("BRENT", {}).get("history_close", [])
        dxy_oil_corr = self.calculate_correlation(dxy_hist, brent_hist)

        # 5. Net Likidite ve 4 Haftalık Değişim Hızı (Δ Liquidity) + TGA Sezonsallık Filtresi
        walcl_b = fred_data.get("WALCL", 7180000.0) / 1000.0
        tga_b = fred_data.get("WTREGEN", 780000.0) / 1000.0
        rrp_b = fred_data.get("RRPONTSYD", 290.0)
        current_net_liq_b = round(walcl_b - tga_b - rrp_b, 1)

        walcl_4w_b = fred_data.get("WALCL_4W_AGO", walcl_b * 1000.0) / 1000.0
        tga_4w_b = fred_data.get("WTREGEN_4W_AGO", tga_b * 1000.0) / 1000.0
        rrp_4w_b = fred_data.get("RRPONTSYD_4W_AGO", rrp_b)
        prev_net_liq_b = round(walcl_4w_b - tga_4w_b - rrp_4w_b, 1)

        delta_liq_b = round(current_net_liq_b - prev_net_liq_b, 1)
        delta_liq_pct = round((delta_liq_b / prev_net_liq_b) * 100, 2) if prev_net_liq_b else 0.0

        # TGA Sezonsallık Denetimi (Nisan & Eylül Vergi Tahsilat Dönemi Tuzağı)
        import datetime
        now_dt = datetime.date.today()
        m, d = now_dt.month, now_dt.day
        is_tga_tax_season = (
            (m == 4 and 10 <= d <= 28) or  # Nisan Yıllık Bireysel Gelir Vergisi
            (m == 9 and 10 <= d <= 25) or  # Eylül Çeyreklik Kurumlar Vergisi
            (m == 6 and 10 <= d <= 25) or  # Haziran Çeyreklik Vergi
            (m == 1 and 10 <= d <= 25)     # Ocak Çeyreklik Vergi
        )
        tga_seasonality_note = (
            "⚠️ Takvimsel Vergi Tahsilat Dönemi: TGA'daki likidite çekilişi geçici bir kamu tahsilatıdır. "
            "Kalıcı bir likidite krizine işaret etmez; likidite daralması cezalandırılmamalıdır."
            if is_tga_tax_season
            else "TGA olağan bütçe harcama/borçlanma döngüsünde; takvimsel vergi distorsiyonu yok."
        )

        liquidity_dynamics = {
            "current_net_liquidity_billion": current_net_liq_b,
            "prev_4w_net_liquidity_billion": prev_net_liq_b,
            "delta_liquidity_billion": delta_liq_b,
            "delta_liquidity_pct_4w": delta_liq_pct,
            "is_tga_tax_season": is_tga_tax_season,
            "tga_seasonality_note": tga_seasonality_note,
            "flow_direction": "Likidite Piyasaya Akıyor (Genişleme)" if delta_liq_b > 0 else "Likidite Piyasadan Çekiliyor (Daralma)"
        }

        # 6. Düzeltilmiş ve Sınırlandırılmış (Clipped) Sürpriz Z-Skorları
        surprises = []
        for event in calendar_events:
            title = event.get('title', '')
            actual_str = str(event.get('actual', '')).replace('%', '').replace('K', '').strip()
            forecast_str = str(event.get('forecast', '')).replace('%', '').replace('K', '').strip()
            try:
                act = float(actual_str)
                fcst = float(forecast_str)
                ind_type = self.identify_indicator_type(title)
                z = self.calculate_surprise_zscore(ind_type, act, fcst)
                surprises.append({
                    "title": title,
                    "indicator_type": ind_type,
                    "actual": act,
                    "forecast": fcst,
                    "z_score": z,
                    "interpretation": "Ilımlı Pozitif" if 0.2 < z <= 1.0 else "Güçlü Pozitif" if z > 1.0 else "Ilımlı Negatif" if -1.0 <= z < -0.2 else "Güçlü Negatif" if z < -1.0 else "Nötr / Beklentiye Paralel"
                })
            except (ValueError, TypeError):
                continue

        # 7. Kredi Risk Primi (High Yield OAS - BAMLH0A0HYM2)
        hy_oas = fred_data.get("BAMLH0A0HYM2", 3.28)
        credit_spread_analysis = {
            "hy_oas_spread_pct": hy_oas,
            "stress_level": "Sakin / Düşük Risk (Benign)" if hy_oas < 3.8 else "Orta Düzey Kredi Baskısı" if hy_oas < 4.8 else "Şiddetli Kredi Krizi (Distress)",
            "equity_implication": (
                f"Kredi makası %{hy_oas:.2f} (Tarihsel ortalamanın altında, sakin). Şirketler rahat borçlanıyor, temerrüt riski yok. "
                "Kredi piyasası sakinken borsalarda (SPX) kalıcı çöküş veya kriz fiyatlaması beklenemez; SPX en fazla Neutral/ılımlı düzeltme alabilir."
                if hy_oas < 3.8
                else f"Kredi makası %{hy_oas:.2f} seviyesine fırladı; temerrüt riski hisseleri baskılayabilir."
            )
        }

        # 8. Finansal Koşullar Endeksi (Chicago Fed NFCI)
        nfci = fred_data.get("NFCI", -0.52)
        financial_conditions_analysis = {
            "nfci_value": nfci,
            "regime": "Gevşek / Akıcı (Accommodative)" if nfci < 0 else "Sıkı / Kısıtlayıcı (Restrictive)",
            "buffer_effect": (
                f"NFCI {nfci:.2f} (< 0). Bankacılık sistemi ve özel sektör likiditesi Fed bilanço küçülmesini (QT) dengeliyor; "
                "piyasa likidite şokundan korunuyor."
                if nfci < 0
                else f"NFCI {nfci:.2f} (> 0). Finansal koşullar tarihsel ortalamanın üzerinde sıkı."
            )
        }

        # 9. DXY Fiyat Seviyesi ve 5G / 20G Momentum Trendi
        dxy_data = market_data.get("DXY", {})
        dxy_val = dxy_data.get("value", 104.2)
        dxy_5d = dxy_data.get("val_5d_ago", dxy_val)
        dxy_20d = dxy_data.get("month_ago", dxy_5d)
        dxy_delta_5d_pct = round(((dxy_val - dxy_5d) / dxy_5d) * 100, 2) if dxy_5d else 0.0
        dxy_delta_20d_pct = round(((dxy_val - dxy_20d) / dxy_20d) * 100, 2) if dxy_20d else 0.0
        dxy_trend_analysis = {
            "level": dxy_val,
            "delta_5d_pct": dxy_delta_5d_pct,
            "delta_20d_pct": dxy_delta_20d_pct,
            "momentum_regime": "Düşüş Trendi / Zayıf Dolar" if (dxy_val < 100.0 or dxy_delta_20d_pct < -0.5) else "Yükseliş Trendi / Güçlü Dolar" if dxy_delta_20d_pct > 1.0 else "Nötr / Yatay Bant",
            "warning": (
                f"DXY {dxy_val:.2f} seviyesinde (100'ün altında) ve 20G momentumu %{dxy_delta_20d_pct:+.2f}. "
                "Dolar zayıflarken DXY'ye körü körüne Bullish, EURUSD'ye körü körüne Bearish verme! "
                "Piyasa ABD borç sürdürülebilirliğini (Fiscal Dominance / Debasement Trade) fiyatlıyor."
                if (dxy_val < 100.0 or dxy_delta_20d_pct < -0.5)
                else "DXY momentumu pozitif / stabil."
            )
        }

        # 10. Haftalık Öncü İstihdam (FRED ICSA - Initial Claims)
        icsa = fred_data.get("ICSA", 218.0)
        jobless_claims_analysis = {
            "initial_claims_k": icsa,
            "status": "Sağlıklı / Tam İstihdam Teyitli" if icsa <= 235.0 else "Ilımlı Zayıflama Uyarısı" if icsa <= 260.0 else "İstihdamda Kırılma / Resesyonel Artış",
            "leading_signal": (
                f"Haftalık ilk işsizlik başvuruları {icsa:.0f}K (210K-230K sağlıklı istihdam bandında). "
                "Aylık NFP verisinin gücü haftalık öncü veriyle teyit edilmektedir; istihdamda ani bir çatlama yok."
                if icsa <= 235.0
                else f"Haftalık başvurular {icsa:.0f}K seviyesine tırmandı! Bir sonraki NFP öncesi işgücü piyasasında zayıflama sinyali."
            )
        }

        # 11. Histeresis Destekli Dış Ticaret Hadleri & EURUSD Enerji Şoku Tuzağı (Terms-of-Trade)
        # Önceki rejim durumunu bias gate dosyasından oku (Regime Flickering / Titreme önleyici)
        prev_energy_penalty = False
        prev_cap_preservation = False
        if BIAS_GATE_FILE.exists():
            try:
                with open(BIAS_GATE_FILE, "r", encoding="utf-8") as f:
                    prev_gate = json.load(f)
                    prev_regime_state = prev_gate.get("regime_state", {})
                    prev_energy_penalty = prev_regime_state.get("energy_penalty_active", False)
                    prev_cap_preservation = prev_regime_state.get("capital_preservation_active", False)
            except Exception:
                pass

        enter_level = HYSTERESIS_CONFIG.get("BRENT_ENERGY_PENALTY_ENTER", 85.0)
        exit_level = HYSTERESIS_CONFIG.get("BRENT_ENERGY_PENALTY_EXIT", 81.0)
        is_global_mfg_slowing = ratio_delta_4w_pct < -2.0

        if prev_energy_penalty:
            # Zaten aktifse, ancak petrol çıkış seviyesinin (<$81) altına inerse ceza kalkar (~%5 histeresis bandı)
            eurusd_energy_penalty = not (brent < exit_level)
            hysteresis_note = f"Histeresis Aktif: Önceki durum korundu (Brent ${brent:.1f} >= ${exit_level:.1f} çıkış eşiği)"
        else:
            # Pasifse, ancak $85'i aşarsa ve sanayi zayıfsa aktifleşir
            eurusd_energy_penalty = (brent >= enter_level) and is_global_mfg_slowing
            hysteresis_note = f"Standart Eşik: Brent ${brent:.1f} (Giriş eşiği: ${enter_level:.1f})"

        terms_of_trade_energy_analysis = {
            "brent_level": brent,
            "eurusd_energy_penalty": eurusd_energy_penalty,
            "hysteresis_note": hysteresis_note,
            "recommended_eurusd_gate": "NEUTRAL_RANGE" if eurusd_energy_penalty else "DIRECTIONAL_ALLOWED",
            "rationale": (
                f"Brent petrol ${brent:.1f} ve küresel imalat zayıfken (Bakır/Altın %{ratio_delta_4w_pct:+.2f}) Euro Bölgesi enerji ithalatçısı olarak dış ticaret şoku yaşar. "
                "DXY'nin borç endişesiyle zayıflaması Euro'ya kalıcı güç kazandırmaz; debasement altını ve emtiayı beslerken enerji faturası Euro'yu baskılar. "
                "Bu sebeple EURUSD körlemesine LONG_ONLY yapılamaz; NEUTRAL_RANGE veya DEFENSIVE_HOLD olarak sınırlandırılmalıdır. "
                f"[{hysteresis_note}]"
                if eurusd_energy_penalty
                else "Enerji şoku baskısı yok; döviz pariteleri normal faiz farkı rejiminde."
            )
        }

        # 12. Transatlantik Faiz Makası (US 10Y vs Almanya 10Y Bund Spread & Trendi)
        de10y = fred_data.get("DE10Y", 2.40)
        de10y_prev = fred_data.get("DE10Y_4W_AGO", 2.48)
        transatlantic_spread_bps = round((us10y - de10y) * 100, 1)
        prev_transatlantic_spread_bps = round((us10y_20d - de10y_prev) * 100, 1)
        delta_transatlantic_20d_bps = round(transatlantic_spread_bps - prev_transatlantic_spread_bps, 1)

        transatlantic_analysis = {
            "us10y": us10y,
            "de10y_bund": de10y,
            "spread_bps": transatlantic_spread_bps,
            "delta_spread_20d_bps": delta_transatlantic_20d_bps,
            "direction": "ABD Lehine Genişliyor (Dolar Getiri Avantajı Artıyor)" if delta_transatlantic_20d_bps > 5.0 else "Euro/Almanya Lehine Daralıyor" if delta_transatlantic_20d_bps < -5.0 else "Dengeli / Yatay",
            "implication": (
                f"Transatlantik getiri makası +{transatlantic_spread_bps:.1f} bps (20G Δ: {delta_transatlantic_20d_bps:+.1f} bps). "
                "Almanya 10Y Bund faizlerine kıyasla ABD tahvillerinin sunduğu net getiri primi Dolar lehine sermaye akışını destekler. "
                "Enerji şokuyla birleştiğinde EURUSD için yukarı yönlü alan kapalıdır."
                if delta_transatlantic_20d_bps >= 0
                else f"Almanya Bund getirileri ABD'ye kıyasla daha güçlü (Makas daralıyor: {delta_transatlantic_20d_bps:+.1f} bps)."
            )
        }

        # 13. T-0 Anlık Piyasa Stresi Devre Kesicisi (Fast Stress Override)
        hyg_data = market_data.get("HYG", {})
        lqd_data = market_data.get("LQD", {})
        vix_data = market_data.get("VIX", {})
        brent_data = market_data.get("BRENT", {})

        hyg_val = hyg_data.get("value", 79.2)
        lqd_val = lqd_data.get("value", 105.5)
        hyg_prev = hyg_data.get("prev", hyg_val)
        lqd_prev = lqd_data.get("prev", lqd_val)
        hyg_5d = hyg_data.get("val_5d_ago", hyg_prev)
        lqd_5d = lqd_data.get("val_5d_ago", lqd_prev)

        current_hyg_lqd = round(hyg_val / lqd_val, 4) if lqd_val else 0.7507
        prev_hyg_lqd = round(hyg_prev / lqd_prev, 4) if lqd_prev else current_hyg_lqd
        hyg_lqd_5d = round(hyg_5d / lqd_5d, 4) if lqd_5d else current_hyg_lqd

        hyg_lqd_delta_1d_pct = round(((current_hyg_lqd - prev_hyg_lqd) / prev_hyg_lqd) * 100, 2) if prev_hyg_lqd else 0.0
        hyg_lqd_delta_5d_pct = round(((current_hyg_lqd - hyg_lqd_5d) / hyg_lqd_5d) * 100, 2) if hyg_lqd_5d else 0.0

        vix_val = vix_data.get("value", 14.5)
        vix_delta_1d_pct = vix_data.get("change_pct", 0.0)
        vix_delta_5d_pct = vix_data.get("change_pct_5d", 0.0)

        brent_delta_1d_pct = brent_data.get("change_pct", 0.0)
        brent_delta_5d_pct = brent_data.get("change_pct_5d", 0.0)

        fast_stress_triggers = []
        if hyg_lqd_delta_5d_pct < -1.5 or hyg_lqd_delta_1d_pct < -1.0:
            fast_stress_triggers.append(f"HYG/LQD Canlı Kredi Makası Bozuldu (1G: %{hyg_lqd_delta_1d_pct}, 5G: %{hyg_lqd_delta_5d_pct})")
        if vix_val > 22.0 or vix_delta_1d_pct > 15.0:
            fast_stress_triggers.append(f"VIX Oynaklık Patlaması (Seviye: {vix_val:.1f}, 1G Sıçrama: %{vix_delta_1d_pct:+.1f})")
        if brent_delta_1d_pct > 4.0 or brent_delta_5d_pct > 8.0:
            fast_stress_triggers.append(f"Brent Ani Emtia Şoku (1G Sıçrama: %{brent_delta_1d_pct:+.1f}, 5G: %{brent_delta_5d_pct:+.1f})")

        # A single VIX percentage jump from a low base is not sufficient to
        # declare systemic stress. Require either an extreme absolute VIX level
        # or confirmation from at least two independent stress channels.
        fast_stress_override = (vix_val >= 25.0) or (len(fast_stress_triggers) >= 2)

        t0_fast_stress_analysis = {
            "fast_stress_override": fast_stress_override,
            "triggers": fast_stress_triggers,
            "trigger_count": len(fast_stress_triggers),
            "confirmation_rule": "VIX>=25 alone OR >=2 independent stress triggers",
            "hyg_lqd_ratio": current_hyg_lqd,
            "hyg_lqd_delta_1d_pct": hyg_lqd_delta_1d_pct,
            "hyg_lqd_delta_5d_pct": hyg_lqd_delta_5d_pct,
            "vix_level": vix_val,
            "vix_delta_1d_pct": vix_delta_1d_pct,
            "vix_delta_5d_pct": vix_delta_5d_pct,
            "brent_delta_1d_pct": brent_delta_1d_pct,
            "warning": (
                "⚠️ [T-0 FAST STRESS OVERRIDE AKTİF] Canlı piyasada anlık stres şoku tespit edildi! "
                "FRED'in haftalık gecikmeli metrikleri (NFCI / OAS) baypas edilerek sistem acil savunma moduna geçirildi."
                if fast_stress_override
                else "T-0 anlık piyasa göstergeleri (VIX, HYG/LQD, Petrol) sakin; FRED verileri geçerli."
            )
        }

        # 14. BTC vs Altın Ayrışması (Bear Steepening & Volatilite Şoku - Dinamik Yüzdelik Dilimli)
        is_bear_steepening = (yield_curve.get("regime") == "Bear Steepening")
        delta_10y_5d = yield_curve.get("delta_10y_5d_bps", 0.0)
        vix_pct_60d = vix_data.get("pct_rank_60d", 50.0)
        brent_pct_60d = brent_data.get("pct_rank_60d", 50.0)

        # Mutlak VIX > 20 veya 60 günlük pencerede %80'in üzerinde oynaklık şoku
        is_volatility_shock = (vix_val > 20.0 or vix_pct_60d >= 80.0 or vix_delta_5d_pct > 10.0)
        is_duration_shock = is_bear_steepening and (is_volatility_shock or delta_10y_5d >= 10.0)
        is_systemic_stress = fast_stress_override or vix_val >= 25.0 or (credit_spread_analysis.get("stress_level") == "Şiddetli Kredi Krizi (Distress)")

        btc_decoupling_active = is_duration_shock or is_systemic_stress

        if is_duration_shock:
            recommended_btc_gate = "SHORT_ONLY"
            btc_rationale = (
                f"Bear Steepening esnasında 10Y faiz sıçraması ({delta_10y_5d:+.1f} bps) ve oynaklık (VIX: {vix_val:.1f}, 60G Dilim: %{vix_pct_60d:.1f}) fonlarda teminat tamamlama (margin call) dalgası başlatır. "
                "Altın merkez bankalarının fiziki rezerv talebiyle korunurken, BTC hafta sonu da nakde dönebilen en likit yüksek beta varlık olarak ilk satılan enstrümandır. "
                "Bu sebeple BTC'de Long yönlü işlemler yüksek risk barındırır; fonların tasfiye dalgasıyla SHORT_ONLY yönlü kırılımlar desteklenir."
            )
        elif is_systemic_stress:
            recommended_btc_gate = "DEFENSIVE_HOLD"
            btc_rationale = (
                f"T-0 hızlı piyasa stresi (Brent/VIX/Kredi şoku) ve sistemik sermaye koruma modunda (VIX: {vix_val:.1f}) fon tasfiyeleri riski nedeniyle BTC'de yönlü alım (Long) kilitlenir; "
                "kripto varlıklar yüksek beta risk primi nedeniyle DEFENSIVE_HOLD olarak korunmalıdır."
            )
        else:
            recommended_btc_gate = "LONG_ONLY_ALLOWED_IF_DEBASEMENT"
            btc_rationale = f"Tahvil oynaklığı sakin (VIX 60G Dilim: %{vix_pct_60d:.1f}); BTC'de egemen borç debasement tezi kontrollü risk ile geçerli."

        btc_decoupling_analysis = {
            "btc_decoupling_active": btc_decoupling_active,
            "is_bear_steepening": is_bear_steepening,
            "vix_level": vix_val,
            "vix_pct_60d": vix_pct_60d,
            "vix_5d_delta_pct": vix_delta_5d_pct,
            "us10y_5d_delta_bps": delta_10y_5d,
            "recommended_btc_gate": recommended_btc_gate,
            "rationale": btc_rationale
        }

        # 15. Fiyatlanan Faiz Patikası (FedWatch & Forward Easing / Hawkish Repricing)
        fed_policy_rate = 5.33  # Efektif Fed Fonlama Faizi (~%5.33)
        implied_rate_gap_bps = round((us02y - fed_policy_rate) * 100, 1)
        u02_5d = us02y_data.get("val_5d_ago", us02y_prev)
        delta_02y_5d_bps = round((us02y - u02_5d) * 100, 1)

        fed_forward_path_analysis = {
            "current_policy_rate": fed_policy_rate,
            "us02y_yield": us02y,
            "implied_rate_gap_bps": implied_rate_gap_bps,
            "delta_02y_5d_bps": delta_02y_5d_bps,
            "repricing_direction": (
                "Hawkish Repricing (Piyasa Faiz İndirimlerini Siliyor)"
                if delta_02y_5d_bps >= 8.0
                else "Dovish Repricing (Daha Fazla İndirim Fiyatlanıyor)"
                if delta_02y_5d_bps <= -8.0
                else "Sabit Fiyatlanan Patika (Beklentiler Dengeli)"
            ),
            "implication": (
                f"2Y tahvil faizi (%{us02y}) üzerinden piyasa Fed'den toplam {abs(implied_rate_gap_bps):.0f} bps gevşeme fiyatlamaktadır. "
                f"5G Δ: {delta_02y_5d_bps:+.1f} bps. "
                "Eğer getiri eğrisi dikleşirken faiz indirimleri siliniyorsa bu ikili bir şoktur; ancak indirimler korunuyorsa dikleşme arz baskısı kaynaklıdır."
            )
        }

        # 16. Fed Tepki Fonksiyonu (Reaction Function & Değerleme Tavanı)
        unemp_rate = 4.1
        nfp_val = 190.0
        for s in surprises:
            if s.get("indicator_type") == "unemployment":
                unemp_rate = s.get("actual", unemp_rate)
            elif s.get("indicator_type") == "nfp":
                nfp_val = s.get("actual", nfp_val)

        fed_reaction_function = {
            "rate_path_expectation": "Higher for Longer (Faiz İndirimleri Öteleniyor)",
            "driver": f"İstihdam canlı (%{unemp_rate} işsizlik, {nfp_val}K NFP, {icsa:.0f}K ICSA) ve enerji yüksek (${brent:.1f}). Fed erken gevşeyemez.",
            "equity_multiple_cap": (
                "Tahvil getirilerindeki yükseliş (%4.50+ nominal, %1.95 reel) hisse senetlerinin F/K çarpanlarını baskılar. "
                "Kredi makası sakin olduğu için çöküş olmasa bile, iskonto oranının yüksek kalması SPX'te ralli potansiyelini sınırlar; "
                "SPX için tavan 'Neutral' (Yatay Bant) olarak korunmalıdır."
            )
        }

        # 17. Ayrışmış Döngü Teşhisi (US Exceptionalism vs Küresel İmalat Yavaşlaması)
        is_labor_strong = (unemp_rate <= 4.3 and nfp_val >= 150.0 and icsa <= 240.0)
        cycle_diagnosis = {
            "unemployment_rate": unemp_rate,
            "nfp_value": nfp_val,
            "icsa_claims": icsa,
            "is_labor_strong": is_labor_strong,
            "us_domestic_cycle": "Late-Cycle Domestic Resilience (US Exceptionalism - Tüketim & Hizmet Canlı)",
            "global_macro_cycle": "Manufacturing Slowdown / Contractionary Pressure (Küresel Sanayi Zayıf)",
            "regime_diagnosis": (
                "Late-Cycle Overheating with Global Divergence"
                if is_labor_strong and brent >= 80.0
                else "Stagflation"
                if not is_labor_strong and brent >= 80.0
                else "Reflationary Growth"
                if is_labor_strong
                else "Deflationary Slowdown"
            ),
            "rationale": (
                f"ABD iç piyasasında işsizlik %{unemp_rate} ve NFP {nfp_val}K (haftalık başvurular {icsa:.0f}K) ile hizmetler canlıdır; "
                f"fakat Bakır/Altın rasyosundaki %{ratio_delta_4w_pct:+.2f}'lik düşüş küresel sanayinin yavaşladığını göstermektedir. "
                "Piyasa homojen bir rejimde değil, 'ABD İstisnacılığı' ile 'Küresel İmalat Yavaşlaması' arasındaki makasta hareket etmektedir."
            )
        }

        # 18. Kurumsal Asimetrik SHORT Kuralları (Borsa & Altın Kalkanı)
        # A) Endeksler (NAS100/SPX): VIX > 22 iken Short YASAK (Geç kalındı, tepki rallisi).
        # Short sadece VIX < 18 (Rehavet) ve Net Likidite Daralması varken aranır!
        is_equity_complacent = (vix_val < 18.0)
        is_liquidity_draining = (delta_liq_b < -30.0)
        equity_short_gate_allowed = (is_equity_complacent and is_liquidity_draining)
        equity_short_regime = {
            "vix_level": vix_val,
            "is_equity_complacent": is_equity_complacent,
            "is_liquidity_draining": is_liquidity_draining,
            "equity_short_allowed": equity_short_gate_allowed,
            "status_message": (
                f"✅ ENDEKS SHORT ONAYI: VIX rehavette ({vix_val:.1f} < 18) ve Fed likiditesi daralıyor (${delta_liq_b:+.1f}B). Zirve dönüşü short aranabilir."
                if equity_short_gate_allowed
                else f"🛑 ENDEKS SHORT YASAK: VIX ({vix_val:.1f} >= 22.0) seviyesinde ayı piyasası rallisi (short squeeze) riski nedeniyle gecikmiş short intihardır!"
                if vix_val >= 22.0
                else "Nötr endeks rejimi (Rehavet veya likidite daralması henüz olgunlaşmadı)."
            )
        }

        # B) Altın (XAUUSD): Mali Hakimiyet (Fiscal Dominance) ve Merkez Bankası Alımları Kalkanı
        is_cash_dash = (vix_val >= 40.0 and credit_spread_analysis.get("stress_level") == "Distress")
        gold_short_allowed = is_cash_dash
        gold_fiscal_dominance = {
            "gold_short_allowed": gold_short_allowed,
            "is_cash_dash": is_cash_dash,
            "status_message": (
                "⚠️ SİSTEMİK NAKİT YARIŞI: Dolar likidite donması nedeniyle geçici Altın Short izni aktif."
                if is_cash_dash
                else "🛑 ALTINDA SHORT KESİNLİKLE YASAK: Mali Hakimiyet ve merkez bankası fiziki rezerv talebi nedeniyle Altında SHORT istatistiksel intihardır (LONG_ONLY / HOLD)."
            )
        }

        # 19. Çapraz Kurlar & Göreli Değer (Relative Value) Makro Matrisi
        # A) 2 Yıllık Egemen Tahvil Faiz Farkları (Sovereign 2Y Yield Spreads)
        ca02y_data = market_data.get("CA02Y", {})
        de02y_data = market_data.get("DE02Y", {})
        gb02y_data = market_data.get("GB02Y", {})
        au02y_data = market_data.get("AU02Y", {})
        nz02y_data = market_data.get("NZ02Y", {})

        ca02y = ca02y_data.get("value", 3.10)
        ca02y_5d = ca02y_data.get("val_5d_ago", ca02y)
        de02y = de02y_data.get("value", 2.35)
        de02y_5d = de02y_data.get("val_5d_ago", de02y)
        gb02y = gb02y_data.get("value", 3.85)
        gb02y_5d = gb02y_data.get("val_5d_ago", gb02y)
        au02y = au02y_data.get("value", 3.65)
        au02y_5d = au02y_data.get("val_5d_ago", au02y)
        nz02y = nz02y_data.get("value", 3.80)
        nz02y_5d = nz02y_data.get("val_5d_ago", nz02y)

        # 2Y Spreads vs US02Y (bps cinsinden)
        ca_us_spread_2y = round((ca02y - us02y) * 100, 1)
        prev_ca_us_5d = round((ca02y_5d - u02_5d) * 100, 1)
        delta_ca_us_spread_5d = round(ca_us_spread_2y - prev_ca_us_5d, 1)

        de_us_spread_2y = round((de02y - us02y) * 100, 1)
        prev_de_us_5d = round((de02y_5d - u02_5d) * 100, 1)
        delta_de_us_spread_5d = round(de_us_spread_2y - prev_de_us_5d, 1)

        gb_us_spread_2y = round((gb02y - us02y) * 100, 1)
        prev_gb_us_5d = round((gb02y_5d - u02_5d) * 100, 1)
        delta_gb_us_spread_5d = round(gb_us_spread_2y - prev_gb_us_5d, 1)

        au_us_spread_2y = round((au02y - us02y) * 100, 1)
        prev_au_us_5d = round((au02y_5d - u02_5d) * 100, 1)
        delta_au_us_spread_5d = round(au_us_spread_2y - prev_au_us_5d, 1)

        au_ca_spread_2y = round((au02y - ca02y) * 100, 1)
        prev_au_ca_5d = round((au02y_5d - ca02y_5d) * 100, 1)
        delta_au_ca_spread_5d = round(au_ca_spread_2y - prev_au_ca_5d, 1)

        # AU-NZ 2Y Spread (Avustralya - Yeni Zelanda 2Y Faiz Makası - GDT Bayatlık Kalkanı)
        au_nz_spread_2y = round((au02y - nz02y) * 100, 1)
        prev_au_nz_5d = round((au02y_5d - nz02y_5d) * 100, 1)
        delta_au_nz_spread_5d = round(au_nz_spread_2y - prev_au_nz_5d, 1)

        # Seans Uyuşmazlığı & Gürültü Filtresi (Anti-Flickering / Hysteresis Bandı)
        desync_noise = HYSTERESIS_CONFIG.get("SPREAD_DESYNC_NOISE_BPS", 3.0)
        def _filter_spread_noise(delta_bps: float) -> float:
            return delta_bps if abs(delta_bps) >= desync_noise else 0.0

        sig_delta_ca_us = _filter_spread_noise(delta_ca_us_spread_5d)
        sig_delta_de_us = _filter_spread_noise(delta_de_us_spread_5d)
        sig_delta_gb_us = _filter_spread_noise(delta_gb_us_spread_5d)
        sig_delta_au_us = _filter_spread_noise(delta_au_us_spread_5d)
        sig_delta_au_ca = _filter_spread_noise(delta_au_ca_spread_5d)
        sig_delta_au_nz = _filter_spread_noise(delta_au_nz_spread_5d)

        # B) Emtia RoC & Ayrışmış Sektör Göstergeleri
        brent_roc_20d = brent_data.get("change_pct_4w", 0.0)
        brent_roc_5d = brent_data.get("change_pct_5d", 0.0)

        iron_ore_data = market_data.get("IRON_ORE", {})
        iron_ore_roc_20d = iron_ore_data.get("change_pct_4w", 0.0)
        iron_ore_roc_5d = iron_ore_data.get("change_pct_5d", 0.0)

        dairy_data = market_data.get("DAIRY_GDT", {})
        dairy_roc_20d = dairy_data.get("change_pct_4w", 0.0)
        dairy_roc_5d = dairy_data.get("change_pct_5d", 0.0)

        # C) Para Birimi Bağımsız 3 Faktörlü Puanlama (3-Factor Base Currency Scoring)
        # Faktör 1: Getiri Farkı İvmesi (Yield Spread Momentum)
        # Faktör 2: Dış Ticaret Haddi / Emtia (Terms of Trade & Commodities)
        # Faktör 3: Risk İştahı ve Güvenli Liman Talebi (Risk Appetite & Safe-Haven Sensitivity)

        cross_currency_breakdown: Dict[str, Dict[str, Any]] = {}

        # 1. CAD (Kanada Doları)
        cad_yield = 1 if sig_delta_ca_us > 0.0 else (-1 if sig_delta_ca_us < 0.0 else 0)
        cad_commodity = 1 if brent_roc_20d > 3.0 else (-1 if brent_roc_20d < -3.0 else 0)
        cad_risk = -1 if vix_val >= 24.0 else (1 if vix_val < 16.0 else 0)
        cad_raw = cad_yield + cad_commodity + (1 if cad_risk > 0 and cad_commodity > 0 else 0)
        cad_score = 1 if cad_raw >= 2 or (cad_commodity > 0 and cad_yield >= 0) else (-1 if cad_raw <= -2 or (cad_commodity < 0 and cad_yield <= 0) else 0)
        cross_currency_breakdown["CAD"] = {
            "score": cad_score,
            "yield_factor": f"CA-US 2Y Spread Delta: {sig_delta_ca_us:+.1f} bps ({cad_yield:+d})",
            "commodity_factor": f"Brent 20G RoC: {brent_roc_20d:+.1f}% ({cad_commodity:+d})",
            "risk_factor": f"VIX {vix_val:.1f} ({cad_risk:+d})",
            "summary": "Petrol ve 2Y getiri makası lehte" if cad_score > 0 else ("Petrol ve getiri baskısı aleyhte" if cad_score < 0 else "Dengeli/Nötr CAD")
        }

        # 2. AUD (Avustralya Doları)
        aud_yield = 1 if sig_delta_au_us > 0.0 else (-1 if sig_delta_au_us < 0.0 else 0)
        aud_commodity = 1 if (ratio_delta_4w_pct > 0.0 and iron_ore_roc_20d > 0.0) else (-1 if (ratio_delta_4w_pct < 0.0 and iron_ore_roc_20d < 0.0) else 0)
        aud_risk = -1 if vix_val >= 22.0 else (1 if vix_val < 16.0 else 0)
        aud_score = 1 if (aud_commodity > 0 and aud_risk >= 0) or (aud_yield > 0 and aud_commodity >= 0) else (-1 if (aud_commodity < 0 or aud_risk < 0 and aud_yield <= 0) else 0)
        cross_currency_breakdown["AUD"] = {
            "score": aud_score,
            "yield_factor": f"AU-US 2Y Spread Delta: {sig_delta_au_us:+.1f} bps ({aud_yield:+d})",
            "commodity_factor": f"Bakır/Altın: {ratio_delta_4w_pct:+.1f}% & Demir: {iron_ore_roc_20d:+.1f}% ({aud_commodity:+d})",
            "risk_factor": f"Yüksek Beta / VIX {vix_val:.1f} ({aud_risk:+d})",
            "summary": "Çin/Emtia ve Asya risk iştahı destekliyor" if aud_score > 0 else ("Emtia zayıflığı veya riskten kaçış baskılıyor" if aud_score < 0 else "Nötr AUD")
        }

        # 3. NZD (Yeni Zelanda Doları)
        nzd_yield = 1 if sig_delta_au_nz < 0.0 else (-1 if sig_delta_au_nz > 0.0 else 0) # AU-NZ daralması NZD lehine
        nzd_commodity = 1 if dairy_roc_20d > 0.0 else (-1 if dairy_roc_20d < 0.0 else 0)
        nzd_risk = -1 if vix_val >= 20.0 else (1 if vix_val < 16.0 else 0)
        if abs(dairy_roc_20d) >= 0.1:
            nzd_score = 1 if (nzd_commodity > 0 and nzd_risk >= 0) else (-1 if (nzd_commodity < 0 and nzd_risk <= 0) else 0)
        else:
            nzd_score = nzd_yield
        cross_currency_breakdown["NZD"] = {
            "score": nzd_score,
            "yield_factor": f"AU-NZ 2Y Spread Delta: {sig_delta_au_nz:+.1f} bps ({nzd_yield:+d})",
            "commodity_factor": f"GDT Süt RoC: {dairy_roc_20d:+.1f}% ({nzd_commodity:+d})",
            "risk_factor": f"Asya Risk İştahı / VIX {vix_val:.1f} ({nzd_risk:+d})",
            "summary": "GDT süt ihalesi ve AU-NZ faiz avantajı lehte" if nzd_score > 0 else ("Süt fiyatları veya faiz dezavantajı aleyhte" if nzd_score < 0 else "Dengeli NZD")
        }

        # 4. JPY (Japon Yeni)
        jpy_yield = 1 if delta_02y_5d_bps < -5.0 else (-1 if delta_02y_5d_bps > 5.0 else 0) # ABD 2Y düşerse Carry çözülür, JPY güçlenir
        jpy_safehaven = 1 if (vix_val >= 22.0 or vix_pct_60d >= 70.0 or fast_stress_override) else (-1 if vix_val < 17.0 else 0)
        jpy_score = 1 if (jpy_yield > 0 or jpy_safehaven > 0) else (-1 if (jpy_yield < 0 and jpy_safehaven < 0) else 0)
        cross_currency_breakdown["JPY"] = {
            "score": jpy_score,
            "yield_factor": f"US 2Y Faiz Yeniden Fiyatlama: {delta_02y_5d_bps:+.1f} bps ({jpy_yield:+d})",
            "safe_haven_factor": f"Güvenli Liman Talebi / VIX {vix_val:.1f} ({jpy_safehaven:+d})",
            "risk_factor": f"Carry Trade İştahı ({'Açık (JPY Zayıf)' if jpy_safehaven < 0 else 'Kapalı (JPY Güçlü)'})",
            "summary": "Carry çözülmesi ve güvenli liman girişi" if jpy_score > 0 else ("Taşıma getirisi faiz dezavantajı (Carry açığı)" if jpy_score < 0 else "Dengeli JPY")
        }

        # 5. EUR (Euro)
        eur_yield = 1 if sig_delta_de_us > 0.0 else (-1 if sig_delta_de_us < 0.0 else 0)
        eur_energy = -1 if eurusd_energy_penalty else 0
        eur_score = -1 if eurusd_energy_penalty else (1 if eur_yield > 0 else (-1 if eur_yield < 0 else 0))
        cross_currency_breakdown["EUR"] = {
            "score": eur_score,
            "yield_factor": f"DE-US 2Y Spread Delta: {sig_delta_de_us:+.1f} bps ({eur_yield:+d})",
            "commodity_factor": f"Enerji/Petrol Maliyet Cezası: {'AKTİF (-1)' if eurusd_energy_penalty else 'YOK (0)'}",
            "risk_factor": f"Transatlantik Büyüme Farkı ({'EUR Aleyhte' if eur_yield < 0 else 'EUR Lehte'})",
            "summary": "Enerji şoku veya Transatlantik makas baskılıyor" if eur_score < 0 else ("Transatlantik faiz makası lehte" if eur_score > 0 else "Dengeli EUR")
        }

        # 6. GBP (İngiliz Sterlini)
        gbp_yield = 1 if sig_delta_gb_us > 0.0 else (-1 if sig_delta_gb_us < 0.0 else 0)
        gbp_risk = -1 if vix_val >= 25.0 else (1 if vix_val < 17.0 else 0)
        gbp_score = 1 if gbp_yield > 0 and gbp_risk >= 0 else (-1 if gbp_yield < 0 else 0)
        cross_currency_breakdown["GBP"] = {
            "score": gbp_score,
            "yield_factor": f"GB-US 2Y Spread Delta: {sig_delta_gb_us:+.1f} bps ({gbp_yield:+d})",
            "commodity_factor": f"DXY Korelasyonu: {dxy_data.get('change_pct_5d', 0):+.2f}%",
            "risk_factor": f"Avrupa Risk İştahı / VIX {vix_val:.1f} ({gbp_risk:+d})",
            "summary": "Gilt faiz momentumu güçlü" if gbp_score > 0 else ("BOE faiz indirimi veya faiz erozyonu aleyhte" if gbp_score < 0 else "Dengeli GBP")
        }

        # 7. USD (Amerikan Doları)
        usd_yield = 1 if delta_02y_5d_bps >= 5.0 else (-1 if delta_02y_5d_bps <= -5.0 else 0)
        usd_momentum = 1 if dxy_data.get("change_pct_5d", 0) > 0.4 else (-1 if dxy_data.get("change_pct_5d", 0) < -0.4 else 0)
        usd_score = 1 if (usd_yield > 0 or usd_momentum > 0) else (-1 if (usd_yield < 0 or usd_momentum < 0) else 0)
        cross_currency_breakdown["USD"] = {
            "score": usd_score,
            "yield_factor": f"US 2Y Değişim: {delta_02y_5d_bps:+.1f} bps ({usd_yield:+d})",
            "commodity_factor": f"DXY 5G Momentum: {dxy_data.get('change_pct_5d', 0):+.2f}% ({usd_momentum:+d})",
            "risk_factor": f"Küresel Likidite ve US Exceptionalism",
            "summary": "Güçlü Dolar (Getiri ve DXY ivmesi lehte)" if usd_score > 0 else ("Zayıf Dolar (Getiri erozyonu veya gevşeme)" if usd_score < 0 else "Nötr USD")
        }

        # 8. CHF (İsviçre Frangı)
        gold_data = market_data.get("GOLD", {})
        chf_safehaven = 1 if (fast_stress_override or vix_val >= 22.0 or vix_pct_60d >= 70.0) else (-1 if vix_val < 17.0 else 0)
        gold_support = 1 if gold_data.get("change_pct_5d", 0) > 1.0 else 0
        chf_score = 1 if (chf_safehaven > 0 or (fast_stress_override and gold_support > 0)) else (-1 if (chf_safehaven < 0 and not fast_stress_override) else 0)
        cross_currency_breakdown["CHF"] = {
            "score": chf_score,
            "yield_factor": f"SNB Faiz Farkı (Düşük Politika Faizi Dezavantajı: {'Aktif' if chf_safehaven < 0 else 'Savunmada'})",
            "commodity_factor": f"Altın Desteği: {gold_data.get('change_pct_5d', 0):+.2f}% 5G ({gold_support:+d})",
            "risk_factor": f"Güvenli Liman Talebi / VIX {vix_val:.1f} ({chf_safehaven:+d})",
            "summary": "Sistemik stres ve güvenli liman alımları" if chf_score > 0 else ("Düşük oynaklıkta SNB faiz dezavantajı (Zayıf CHF)" if chf_score < 0 else "Dengeli CHF")
        }

        # D) Sentetik Çapraz & Majör Kur Kapıları (Relative Value Matrix)
        # Dengeli emtia-emtia veya aynı coğrafi bölge kurları için 2 puan ayrışma gerekirken,
        # Dolar Majörleri, Yen ve Frank gibi belirgin makro/carry ayrışması olan paritelerde
        # 1 puanlık net makro avantaj da yönlü kapıyı açar.
        high_threshold_pairs = {"AUDCAD", "NZDCAD", "EURGBP", "EURAUD"}

        def _calc_cross_bias(base_s: int, quote_s: int, pair_sym: str = "") -> str:
            diff = base_s - quote_s
            threshold = 2 if pair_sym in high_threshold_pairs else 1
            if diff >= threshold:
                return "LONG_ONLY"
            if diff <= -threshold:
                return "SHORT_ONLY"
            return "NEUTRAL_RANGE"

        cross_gates = {
            # Çapraz Kurlar
            "AUDCAD": _calc_cross_bias(aud_score, cad_score, "AUDCAD"),
            "CADJPY": _calc_cross_bias(cad_score, jpy_score, "CADJPY"),
            "GBPJPY": _calc_cross_bias(gbp_score, jpy_score, "GBPJPY"),
            "AUDJPY": _calc_cross_bias(aud_score, jpy_score, "AUDJPY"),
            "EURGBP": _calc_cross_bias(eur_score, gbp_score, "EURGBP"),
            "EURAUD": _calc_cross_bias(eur_score, aud_score, "EURAUD"),
            "NZDCAD": _calc_cross_bias(nzd_score, cad_score, "NZDCAD"),
            "EURJPY": _calc_cross_bias(eur_score, jpy_score, "EURJPY"),

            # Dolar Majörleri (SMC Universe Entegrasyonu)
            "USDCAD": _calc_cross_bias(usd_score, cad_score, "USDCAD"),
            "USDJPY": _calc_cross_bias(usd_score, jpy_score, "USDJPY"),
            "GBPUSD": _calc_cross_bias(gbp_score, usd_score, "GBPUSD"),
            "AUDUSD": _calc_cross_bias(aud_score, usd_score, "AUDUSD"),
            "NZDUSD": _calc_cross_bias(nzd_score, usd_score, "NZDUSD"),
            "USDCHF": _calc_cross_bias(usd_score, chf_score, "USDCHF"),

            # CHF Çaprazları (SMC Universe Entegrasyonu)
            "EURCHF": _calc_cross_bias(eur_score, chf_score, "EURCHF"),
            "GBPCHF": _calc_cross_bias(gbp_score, chf_score, "GBPCHF"),
            "AUDCHF": _calc_cross_bias(aud_score, chf_score, "AUDCHF"),
            "CADCHF": _calc_cross_bias(cad_score, chf_score, "CADCHF"),
            "NZDCHF": _calc_cross_bias(nzd_score, chf_score, "NZDCHF"),
            "CHFJPY": _calc_cross_bias(chf_score, jpy_score, "CHFJPY"),
        }

        # E) SOL / Kripto Göreli Güç & 4H CHoCH (Market Structure Shift) Kalkanı
        sol_data = market_data.get("SOL", {})
        sol_val = sol_data.get("value", 145.0)
        sol_5d = sol_data.get("val_5d_ago", 138.0)
        btc_val = market_data.get("BTC", {}).get("value", 58500.0)
        btc_5d = market_data.get("BTC", {}).get("val_5d_ago", 56500.0)

        sol_btc_current = round(sol_val / btc_val, 6) if btc_val else 0.002478
        sol_btc_prev_5d = round(sol_5d / btc_5d, 6) if btc_5d else sol_btc_current
        sol_btc_roc_5d = round(((sol_btc_current - sol_btc_prev_5d) / sol_btc_prev_5d) * 100, 2) if sol_btc_prev_5d else 0.0

        # 4H Market Structure Shift (CHoCH Kırılımı): Kripto tasfiyesinde 5G RoC gecikmesini önler!
        sol_btc_4h_structure_broken = bool(market_data.get("SOL_BTC_STRUCTURE_BROKEN", False))
        sol_btc_structure_bullish = (sol_btc_roc_5d > 0.0) and not sol_btc_4h_structure_broken

        # SOL Gate: Sadece BTC güvenli, SOL/BTC 5G ivmesi pozitif VE 4H yapısı bozulmamışsa LONG_ONLY
        if sol_btc_4h_structure_broken:
            sol_gate = "DEFENSIVE_HOLD"
            sol_rationale = f"🛑 SOL/BTC 4H swing low kırıldı (CHoCH / Yapı Bozuldu). 5G RoC'ye (+%{sol_btc_roc_5d:.2f}) bakılmaksızın Long kilitlendi."
        elif recommended_btc_gate == "LONG_ONLY_ALLOWED_IF_DEBASEMENT" and sol_btc_structure_bullish:
            sol_gate = "LONG_ONLY"
            sol_rationale = f"BTC long izinli, SOL/BTC 5G ivmesi pozitif (+%{sol_btc_roc_5d:.2f}) ve 4H yapı sağlam."
        elif recommended_btc_gate in ["SHORT_ONLY", "DEFENSIVE_HOLD"]:
            sol_gate = recommended_btc_gate
            sol_rationale = f"BTC savunma/short modunda ({recommended_btc_gate}); SOL yüksek beta nedeniyle kilitlendi."
        else:
            sol_gate = "NEUTRAL_RANGE"
            sol_rationale = f"SOL/BTC rasyosu ivmesi negatif (%{sol_btc_roc_5d:.2f} 5G); BTC ayrışması olmasa da SOL zayıf."

        cross_gates["SOL"] = sol_gate

        # 20. Kırmızı Bülten (Red-Folder) Devre Kesicisi (Event Risk Freeze)
        event_freeze_active = False
        active_event_info = ""
        freeze_before = NEWS_FREEZE_CONFIG.get("FREEZE_MINUTES_BEFORE", 15)
        freeze_after = NEWS_FREEZE_CONFIG.get("FREEZE_MINUTES_AFTER", 15)
        high_impact_keywords = NEWS_FREEZE_CONFIG.get("HIGH_IMPACT_KEYWORDS", [])
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        for ev in calendar_events:
            title = str(ev.get("title", "")).lower()
            impact = str(ev.get("impact", "")).upper()
            is_high = impact in ("CRITICAL", "HIGH", "RED") or any(kw in title for kw in high_impact_keywords)
            if not is_high:
                continue
            ev_time = ev.get("time") or ev.get("event_time_utc") or ""
            if ev_time and "T" in str(ev_time):
                try:
                    ev_dt = datetime.datetime.fromisoformat(str(ev_time).replace("Z", "+00:00"))
                    diff_min = (ev_dt - now_utc).total_seconds() / 60.0
                    if -freeze_after <= diff_min <= freeze_before:
                        event_freeze_active = True
                        active_event_info = f"{ev.get('title')} ({ev.get('country', 'USD')}) [Kalan: {diff_min:+.0f} dk]"
                        break
                except Exception:
                    pass

        cross_pairs_analysis = {
            "sovereign_yields": {
                "US02Y": us02y, "CA02Y": ca02y, "DE02Y": de02y, "GB02Y": gb02y, "AU02Y": au02y, "NZ02Y": nz02y
            },
            "yield_spreads_bps": {
                "CA_US_2Y": ca_us_spread_2y, "delta_CA_US_5d": delta_ca_us_spread_5d, "sig_delta_CA_US": sig_delta_ca_us,
                "DE_US_2Y": de_us_spread_2y, "delta_DE_US_5d": delta_de_us_spread_5d, "sig_delta_DE_US": sig_delta_de_us,
                "GB_US_2Y": gb_us_spread_2y, "delta_GB_US_5d": delta_gb_us_spread_5d, "sig_delta_GB_US": sig_delta_gb_us,
                "AU_US_2Y": au_us_spread_2y, "delta_AU_US_5d": delta_au_us_spread_5d, "sig_delta_AU_US": sig_delta_au_us,
                "AU_CA_2Y": au_ca_spread_2y, "delta_AU_CA_5d": delta_au_ca_spread_5d, "sig_delta_AU_CA": sig_delta_au_ca,
                "AU_NZ_2Y": au_nz_spread_2y, "delta_AU_NZ_5d": delta_au_nz_spread_5d, "sig_delta_AU_NZ": sig_delta_au_nz,
            },
            "commodity_rocs": {
                "brent_roc_20d": brent_roc_20d,
                "iron_ore_roc_20d": iron_ore_roc_20d,
                "dairy_gdt_roc_20d": dairy_roc_20d
            },
            "currency_scores": {
                "AUD": aud_score, "CAD": cad_score, "NZD": nzd_score,
                "JPY": jpy_score, "EUR": eur_score, "GBP": gbp_score, "USD": usd_score, "CHF": chf_score
            },
            "currency_breakdown": cross_currency_breakdown,
            "sol_btc_analysis": {
                "sol_btc_ratio": sol_btc_current,
                "sol_btc_roc_5d": sol_btc_roc_5d,
                "structure_broken_4h": sol_btc_4h_structure_broken,
                "structure_bullish": sol_btc_structure_bullish,
                "gate": sol_gate,
                "rationale": sol_rationale
            },
            "event_freeze": {
                "active": event_freeze_active,
                "info": active_event_info
            },
            "cross_gates": cross_gates
        }

        # Histeresis Durumu Hafızası
        regime_state = {
            "energy_penalty_active": eurusd_energy_penalty,
            "capital_preservation_active": prev_cap_preservation or fast_stress_override,
            "fast_stress_override": fast_stress_override,
            "btc_decoupling_active": btc_decoupling_active,
            "event_freeze_active": event_freeze_active,
            "active_event_info": active_event_info,
            "vix_pct_60d": vix_pct_60d,
            "brent_pct_60d": brent_pct_60d,
            "brent_level": brent,
            "brent_roc_20d": brent_roc_20d,
            "brent_roc_5d": brent_roc_5d,
            "spread_ca_us_2y_bps": ca_us_spread_2y,
            "spread_ca_us_2y_delta_5d": delta_ca_us_spread_5d,
            "spread_de_us_2y_bps": de_us_spread_2y,
            "spread_de_us_2y_delta_5d": delta_de_us_spread_5d,
            "spread_gb_us_2y_bps": gb_us_spread_2y,
            "spread_gb_us_2y_delta_5d": delta_gb_us_spread_5d,
            "spread_au_us_2y_bps": au_us_spread_2y,
            "spread_au_us_2y_delta_5d": delta_au_us_spread_5d,
            "spread_au_ca_2y_bps": au_ca_spread_2y,
            "spread_au_ca_2y_delta_5d": delta_au_ca_spread_5d,
            "spread_au_nz_2y_bps": au_nz_spread_2y,
            "spread_au_nz_2y_delta_5d": delta_au_nz_spread_5d,
            "iron_ore_roc_20d": iron_ore_roc_20d,
            "dairy_gdt_roc_20d": dairy_roc_20d,
            "sol_btc_roc_5d": sol_btc_roc_5d,
            "sol_btc_4h_structure_broken": sol_btc_4h_structure_broken,
            "sol_btc_structure_bullish": sol_btc_structure_bullish,
            "cross_currency_scores": cross_pairs_analysis["currency_scores"],
            "cross_currency_breakdown": cross_currency_breakdown,
            "cross_pair_gates": cross_gates,
            "copper_gold_delta_4w_pct": ratio_delta_4w_pct,
            "transatlantic_spread_bps": transatlantic_spread_bps,
            "equity_short_allowed": equity_short_gate_allowed,
            "gold_short_allowed": gold_short_allowed,
            "vix_complacent": is_equity_complacent
        }

        processed = {
            "yield_curve": yield_curve,
            "real_yield_info": real_yield_info,
            "copper_gold_analysis": copper_gold_analysis,
            "credit_spread_analysis": credit_spread_analysis,
            "financial_conditions_analysis": financial_conditions_analysis,
            "jobless_claims_analysis": jobless_claims_analysis,
            "terms_of_trade_energy_analysis": terms_of_trade_energy_analysis,
            "transatlantic_analysis": transatlantic_analysis,
            "t0_fast_stress_analysis": t0_fast_stress_analysis,
            "btc_decoupling_analysis": btc_decoupling_analysis,
            "cross_pairs_analysis": cross_pairs_analysis,
            "equity_short_regime": equity_short_regime,
            "gold_fiscal_dominance": gold_fiscal_dominance,
            "regime_state": regime_state,
            "fed_forward_path_analysis": fed_forward_path_analysis,
            "fed_reaction_function": fed_reaction_function,
            "dxy_trend_analysis": dxy_trend_analysis,
            "cycle_diagnosis": cycle_diagnosis,
            "dxy_oil_correlation": dxy_oil_corr,
            "liquidity_dynamics": liquidity_dynamics,
            "dxy_level": dxy_val,
            "brent_level": brent,
            "gold_level": gold,
            "surprises": surprises
        }

        logger.info(
            f"📊 [DÜZELTİLMİŞ METRİKLER] Döngü: {cycle_diagnosis['regime_diagnosis']} | "
            f"Transatlantik Spread: +{transatlantic_spread_bps:.1f} bps | VIX: {vix_val:.1f} | "
            f"T-0 Stres: {'⚠️ AKTİF' if fast_stress_override else 'Sakin'} | "
            f"EURUSD Enerji Cezası: {'VAR (NEUTRAL_RANGE)' if eurusd_energy_penalty else 'YOK'} | "
            f"BTC Ayrışması: {'⚠️ DEFENSIVE_HOLD' if btc_decoupling_active else 'Normal'}"
        )
        return processed
