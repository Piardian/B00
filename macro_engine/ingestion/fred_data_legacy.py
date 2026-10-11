import logging
import urllib.request
import json
from typing import Dict, Any
from config import FRED_API_KEY

logger = logging.getLogger("FredDataIngestion")

class FredDataIngestion:
    """
    Federal Reserve (FRED) resmi veritabanından makro likidite metriklerini çeker:
    - WALCL: Fed Toplam Varlıkları / Bilanço Büyüklüğü
    - RRPONTSYD: Gecelik Ters Repo (Reverse Repo / RRP) Hacmi
    - WTREGEN: Hazine Genel Hesabı (TGA - Treasury General Account)
    - T10YIE: 10 Yıllık Başa Baş Enflasyon Beklentisi (Breakeven Inflation)
    - M2SL: M2 Para Arzı
    """
    SERIES = {
        "WALCL": "Fed Balance Sheet (Assets)",
        "RRPONTSYD": "Overnight Reverse Repurchase Agreements (RRP)",
        "WTREGEN": "Treasury General Account (TGA)",
        "T10YIE": "10-Year Breakeven Inflation Rate",
        "DFII10": "10-Year TIPS Constant Maturity Rate (Direct Market Real Yield)",
        "BAMLH0A0HYM2": "ICE BofA US High Yield Index Option-Adjusted Spread (HY OAS)",
        "NFCI": "Chicago Fed National Financial Conditions Index",
        "ICSA": "Initial Jobless Claims (Haftalık Öncü İstihdam Başvuruları)",
        "M2SL": "M2 Money Supply"
    }

    def __init__(self, api_key: str = FRED_API_KEY):
        self.api_key = api_key

    def fetch_liquidity_metrics(self) -> Dict[str, Any]:
        """FRED serilerini sorgular veya güncel baz hat verilerini döndürür."""
        results = {}
        if self.api_key:
            for series_id in self.SERIES:
                try:
                    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={self.api_key}&file_type=json&sort_order=desc&limit=5"
                    req = urllib.request.Request(url, headers={"User-Agent": "MacroAGIAgent/1.0"})
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                        obs = data.get('observations', [])
                        if obs:
                            val = float(obs[0].get('value', 0.0))
                            results[series_id] = val
                except Exception as e:
                    logger.debug(f"FRED API {series_id} çekilemedi: {e}")

        # Eğer API anahtarı yoksa veya veriler eksikse, güncel ve 4 hafta önceki baz hat verilerini yükle
        baseline = {
            "WALCL": 7180000.0,           # Fed Bilançosu Güncel (~7.18T)
            "WALCL_4W_AGO": 7240000.0,    # 4 Hafta Önce (~7.24T -> QT ile -$60B küçüldü)
            "RRPONTSYD": 290.0,           # Ters Repo Güncel (~$290B)
            "RRPONTSYD_4W_AGO": 340.0,    # 4 Hafta Önce (~$340B -> -$50B sisteme likidite aktı)
            "WTREGEN": 780000.0,          # TGA Güncel (~$780B)
            "WTREGEN_4W_AGO": 730000.0,   # 4 Hafta Önce (~$730B -> +$50B vergi/borçlanma ile çekildi)
            "T10YIE": 2.15,               # 10Y Breakeven Enflasyon (~%2.15)
            "DFII10": 1.95,               # 10Y Doğrudan TIPS Reel Getirisi (~%1.95)
            "BAMLH0A0HYM2": 3.28,         # ABD Yüksek Getirili Şirket Tahvil Makası (HY OAS ~%3.28 Sakin Kredi Piyasası)
            "NFCI": -0.52,                # Chicago Fed Finansal Koşullar Endeksi (<-0.50 Gevşek/Akıcı Koşullar)
            "ICSA": 218.0,                # Haftalık İlk İşsizlik Başvuruları (~218K Sağlıklı İstihdam Bandı: 210K-230K)
            "DE10Y": 2.40,                # Almanya 10 Yıllık Gösterge Tahvil Faizi (Bund Yield ~%2.40)
            "DE10Y_4W_AGO": 2.48,         # Almanya 10Y 4 Hafta Önceki Faiz (~%2.48 -> -8 bps)
            "M2SL": 21100.0               # M2 Para Arzı (~21.1T)
        }

        for k, v in baseline.items():
            if k not in results or results[k] == 0.0:
                results[k] = v

        logger.info(
            f"🏛️ [FRED LİKİDİTE] Bilanço: ${results['WALCL']/1000000:.2f}T | "
            f"RRP: ${results['RRPONTSYD']:.1f}B | TGA: ${results['WTREGEN']/1000:.1f}B | "
            f"Breakeven Enflasyon: %{results['T10YIE']}"
        )
        return results
