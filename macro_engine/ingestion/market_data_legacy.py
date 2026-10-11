import logging
from typing import Dict, Any, Optional
import yfinance as yf
from config import MARKET_SYMBOLS
from data_quality import OPTIONAL_MARKET_FIELDS
from ingestion.mt5_market_data import MT5MarketDataIngestion

logger = logging.getLogger("MarketDataIngestion")

class MarketDataIngestion:
    """
    MT5 broker doğrudan veri akışı ve yfinance hibrit köprüsü üzerinden
    saatlik/günlük makro piyasa verilerini çeker.
    """
    def __init__(self):
        self.symbols = MARKET_SYMBOLS
        self.mt5_feed = MT5MarketDataIngestion()

    def fetch_current_prices(self) -> Dict[str, Any]:
        """
        DXY, US10Y, US02Y, Altın, Petrol, BTC ve Bakır verilerini çeker (MT5 öncelikli, yf yedekli).
        """
        results = {}
        logger.info("📡 Piyasa verileri çekiliyor (MT5 Doğrudan Broker Feed + yfinance Yedekli)...")

        for name, ticker in self.symbols.items():
            # 1. Öncelik: Yerel MT5 Broker Feed
            mt5_data = self.mt5_feed.fetch_symbol_bars(name, n_bars=60)
            if mt5_data:
                results[name] = mt5_data
                continue

            # 2. Öncelik: Resmi Merkez Bankası API'leri (Sovereign 2Y Yields)
            if name == "CA02Y":
                try:
                    from ingestion.bank_of_canada import BankOfCanadaDataIngestion
                    results[name] = BankOfCanadaDataIngestion().fetch_2y_yield()
                    continue
                except Exception as bce:
                    logger.warning("CA02Y Bank of Canada verisi çekilemedi: %s", bce)
            elif name == "GB02Y":
                try:
                    from ingestion.bank_of_england import BankOfEnglandDataIngestion
                    results[name] = BankOfEnglandDataIngestion().fetch_2y_yield()
                    continue
                except Exception as boe_err:
                    logger.warning("GB02Y Bank of England verisi çekilemedi: %s", boe_err)
            elif name == "DE02Y":
                try:
                    from ingestion.ecb_data import ECBDataIngestion
                    results[name] = ECBDataIngestion().fetch_2y_yield()
                    continue
                except Exception as ecb_err:
                    logger.warning("DE02Y ECB verisi çekilemedi: %s", ecb_err)
            elif name == "AU02Y":
                try:
                    from ingestion.international_rates import InternationalRatesDataIngestion
                    results[name] = InternationalRatesDataIngestion().fetch_au_yield()
                    continue
                except Exception as au_err:
                    logger.warning("AU02Y RBA verisi çekilemedi: %s", au_err)
            elif name == "NZ02Y":
                try:
                    from ingestion.international_rates import InternationalRatesDataIngestion
                    results[name] = InternationalRatesDataIngestion().fetch_nz_yield()
                    continue
                except Exception as nz_err:
                    logger.warning("NZ02Y RBNZ verisi çekilemedi: %s", nz_err)

            if name in ("CA02Y", "GB02Y", "DE02Y", "AU02Y", "NZ02Y"):
                # Merkez bankası API'si ve önbellek kullanılamadıysa; yfinance'de 404 delisted hatası üretmek yerine güvenli fallback atanır
                if name in OPTIONAL_MARKET_FIELDS:
                    logger.info("%s resmi merkez bankası ve önbellek verisi yok; opsiyonel veri atlanıyor.", name)
                    continue
                results[name] = self._get_fallback_price(name)
                continue

            # 3. Öncelik: yfinance Web Verisi
            try:
                t = yf.Ticker(ticker)
                # 3 aylık günlük veriyi al (60 günlük dinamik yüzdelik dilim ve trend için)
                hist = t.history(period="3mo", interval="1d")
                if not hist.empty and len(hist) >= 1:
                    current_val = float(hist['Close'].iloc[-1])
                    prev_val = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_val
                    val_5d_ago = float(hist['Close'].iloc[-6]) if len(hist) >= 6 else float(hist['Close'].iloc[0])
                    month_ago_val = float(hist['Close'].iloc[-21]) if len(hist) >= 21 else float(hist['Close'].iloc[0])
                    pct_change_daily = round(((current_val - prev_val) / prev_val) * 100, 2) if prev_val else 0.0
                    pct_change_5d = round(((current_val - val_5d_ago) / val_5d_ago) * 100, 2) if val_5d_ago else 0.0
                    pct_change_4w = round(((current_val - month_ago_val) / month_ago_val) * 100, 2) if month_ago_val else 0.0
                    
                    # 60 Günlük Yuvarlanan Yüzdelik Dilim (Rolling 60D Percentile Rank)
                    window_60d = hist['Close'].tail(60).tolist()
                    pct_rank_60d = round((sum(1 for x in window_60d if x <= current_val) / len(window_60d)) * 100, 1)

                    results[name] = {
                        "value": round(current_val, 4),
                        "prev": round(prev_val, 4),
                        "val_5d_ago": round(val_5d_ago, 4),
                        "month_ago": round(month_ago_val, 4),
                        "change_pct": pct_change_daily,
                        "change_pct_5d": pct_change_5d,
                        "change_pct_4w": pct_change_4w,
                        "pct_rank_60d": pct_rank_60d,
                        "history_close": hist['Close'].tolist(),
                        "source": f"yfinance ({ticker})",
                        "fallback_used": False
                    }
                else:
                    if name in OPTIONAL_MARKET_FIELDS:
                        logger.info("%s (%s) unavailable; optional market input omitted.", name, ticker)
                        continue
                    results[name] = self._get_fallback_price(name)
            except Exception as e:
                if name in OPTIONAL_MARKET_FIELDS:
                    logger.warning(f"{name} ({ticker}) verisi çekilemedi; opsiyonel veri atlanıyor: {e}")
                    continue
                logger.warning(f"{name} ({ticker}) verisi çekilemedi: {e}. Yedek değer kullanılıyor.")
                results[name] = self._get_fallback_price(name)

        return results

    def _get_fallback_price(self, name: str) -> Dict[str, Any]:
        """Piyasa kapalıyken veya veri çekilemediğinde güvenli referans değerler."""
        fallbacks = {
            "DXY": {"value": 104.20, "prev": 104.10, "val_5d_ago": 103.90, "month_ago": 103.50, "change_pct": 0.10, "change_pct_5d": 0.29, "change_pct_4w": 0.68, "history_close": [103.9, 104.0, 104.1, 104.2]},
            "GOLD": {"value": 2480.50, "prev": 2470.00, "val_5d_ago": 2450.00, "month_ago": 2400.00, "change_pct": 0.42, "change_pct_5d": 1.24, "change_pct_4w": 3.35, "history_close": [2450.0, 2460.0, 2470.0, 2480.5]},
            "BRENT": {"value": 78.40, "prev": 79.10, "val_5d_ago": 80.00, "month_ago": 82.00, "change_pct": -0.88, "change_pct_5d": -2.00, "change_pct_4w": -4.39, "history_close": [80.0, 79.5, 79.1, 78.4]},
            "WTI": {"value": 74.20, "prev": 74.90, "val_5d_ago": 75.50, "month_ago": 77.00, "change_pct": -0.93, "change_pct_5d": -1.72, "change_pct_4w": -3.64, "history_close": [75.5, 75.1, 74.9, 74.2]},
            "US10Y": {"value": 3.88, "prev": 3.92, "val_5d_ago": 3.95, "month_ago": 4.05, "change_pct": -1.02, "change_pct_5d": -1.77, "change_pct_4w": -4.20, "history_close": [3.95, 3.94, 3.92, 3.88]},
            "US02Y": {"value": 3.94, "prev": 3.96, "val_5d_ago": 4.00, "month_ago": 4.15, "change_pct": -0.51, "change_pct_5d": -1.50, "change_pct_4w": -5.06, "history_close": [4.00, 3.98, 3.96, 3.94]},
            "BTC": {"value": 58500.0, "prev": 57800.0, "val_5d_ago": 56500.0, "month_ago": 60000.0, "change_pct": 1.21, "change_pct_5d": 3.54, "change_pct_4w": -2.50, "history_close": [56500.0, 57000.0, 57800.0, 58500.0]},
            "SPX": {"value": 5580.0, "prev": 5550.0, "val_5d_ago": 5500.0, "month_ago": 5450.0, "change_pct": 0.54, "change_pct_5d": 1.45, "change_pct_4w": 2.38, "history_close": [5500.0, 5520.0, 5550.0, 5580.0]},
            "COPPER": {"value": 4.15, "prev": 4.12, "val_5d_ago": 4.08, "month_ago": 4.25, "change_pct": 0.73, "change_pct_5d": 1.72, "change_pct_4w": -2.35, "history_close": [4.08, 4.10, 4.12, 4.15]},
            "VIX": {"value": 14.50, "prev": 14.80, "val_5d_ago": 15.20, "month_ago": 16.00, "change_pct": -2.03, "change_pct_5d": -4.61, "change_pct_4w": -9.38, "history_close": [15.2, 15.0, 14.8, 14.5]},
            "HYG": {"value": 79.20, "prev": 79.15, "val_5d_ago": 79.10, "month_ago": 78.80, "change_pct": 0.06, "change_pct_5d": 0.13, "change_pct_4w": 0.51, "history_close": [79.1, 79.12, 79.15, 79.20]},
            "LQD": {"value": 105.50, "prev": 105.40, "val_5d_ago": 105.30, "month_ago": 104.80, "change_pct": 0.09, "change_pct_5d": 0.19, "change_pct_4w": 0.67, "history_close": [105.3, 105.35, 105.4, 105.5]},
            "EUR_BOND": {"value": 181.00, "prev": 180.80, "val_5d_ago": 180.50, "month_ago": 179.80, "change_pct": 0.11, "change_pct_5d": 0.28, "change_pct_4w": 0.67, "history_close": [180.5, 180.6, 180.8, 181.0]},
            "SOL": {"value": 145.0, "prev": 142.0, "val_5d_ago": 138.0, "month_ago": 135.0, "change_pct": 2.11, "change_pct_5d": 5.07, "change_pct_4w": 7.41, "history_close": [138.0, 140.0, 142.0, 145.0]},
            "CA02Y": {"value": 3.10, "prev": 3.12, "val_5d_ago": 3.15, "month_ago": 3.25, "change_pct": -0.64, "change_pct_5d": -1.59, "change_pct_4w": -4.62, "history_close": [3.15, 3.14, 3.12, 3.10]},
            "DE02Y": {"value": 2.35, "prev": 2.37, "val_5d_ago": 2.40, "month_ago": 2.50, "change_pct": -0.84, "change_pct_5d": -2.08, "change_pct_4w": -6.00, "history_close": [2.40, 2.38, 2.37, 2.35]},
            "GB02Y": {"value": 3.85, "prev": 3.88, "val_5d_ago": 3.90, "month_ago": 4.02, "change_pct": -0.77, "change_pct_5d": -1.28, "change_pct_4w": -4.23, "history_close": [3.90, 3.89, 3.88, 3.85]},
            "AU02Y": {"value": 3.65, "prev": 3.68, "val_5d_ago": 3.70, "month_ago": 3.80, "change_pct": -0.81, "change_pct_5d": -1.35, "change_pct_4w": -3.95, "history_close": [3.70, 3.69, 3.68, 3.65]},
            "IRON_ORE": {"value": 102.5, "prev": 101.8, "val_5d_ago": 100.2, "month_ago": 98.5, "change_pct": 0.69, "change_pct_5d": 2.29, "change_pct_4w": 4.06, "history_close": [100.2, 101.0, 101.8, 102.5]},
            "DAIRY_GDT": {"value": 3250.0, "prev": 3230.0, "val_5d_ago": 3200.0, "month_ago": 3150.0, "change_pct": 0.62, "change_pct_5d": 1.56, "change_pct_4w": 3.17, "history_close": [3200.0, 3215.0, 3230.0, 3250.0]},
            "NZ02Y": {"value": 3.80, "prev": 3.82, "val_5d_ago": 3.85, "month_ago": 3.95, "change_pct": -0.52, "change_pct_5d": -1.30, "change_pct_4w": -3.80, "history_close": [3.85, 3.84, 3.82, 3.80]}
        }
        result = dict(fallbacks.get(name, {
            "value": 100.0,
            "prev": 100.0,
            "val_5d_ago": 100.0,
            "month_ago": 100.0,
            "change_pct": 0.0,
            "change_pct_5d": 0.0,
            "change_pct_4w": 0.0,
            "history_close": [100.0, 100.0],
        }))
        result["source"] = "LEGACY_STATIC_FALLBACK"
        result["fallback_used"] = True
        return result
