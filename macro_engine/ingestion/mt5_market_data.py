import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger("MT5DirectFeed")

try:
    import MetaTrader5 as mt5
    MT5_LIB_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_LIB_AVAILABLE = False


class MT5MarketDataIngestion:
    """
    Yerel MetaTrader 5 terminaline bağlanarak broker'ın canlı tick ve bar
    verilerini çeker (yfinance web scraping bağımlılığını sıfıra indirir).
    """
    # MT5 Broker sembol eşleştirmeleri
    BROKER_SYMBOL_MAP = {
        "EURUSD": ["EURUSD", "EURUSDm", "EURUSD.pro", "EURUSD.ecn"],
        "GOLD": ["XAUUSD", "GOLD", "XAUUSDm", "GOLDm"],
        "DXY": ["USDX", "DXY", "DX", "DXYZ", "USDXm"],
        "BRENT": ["UKOIL", "BRENT", "UKOILm", "BRN"],
        "WTI": ["USOIL", "WTI", "USOILm", "CL"],
        "BTC": ["BTCUSD", "BTCUSDm", "BTC"]
    }

    def __init__(self):
        self.connected = False
        self._check_connection()

    def _check_connection(self) -> bool:
        if not MT5_LIB_AVAILABLE:
            self.connected = False
            return False
        try:
            if not mt5.terminal_info():
                self.connected = bool(mt5.initialize())
            else:
                self.connected = True
        except Exception as e:
            logger.debug(f"MT5 terminaline bağlanılamadı: {e}")
            self.connected = False
        return self.connected

    def find_broker_symbol(self, generic_name: str) -> Optional[str]:
        """Broker listesinde eşleşen aktif sembolü bulur."""
        if not self._check_connection():
            return None
        candidates = self.BROKER_SYMBOL_MAP.get(generic_name.upper(), [generic_name])
        for c in candidates:
            info = mt5.symbol_info(c)
            if info is not None:
                if not info.visible:
                    mt5.symbol_select(c, True)
                return c
        return None

    def fetch_symbol_bars(self, generic_name: str, n_bars: int = 60) -> Optional[Dict[str, Any]]:
        """Broker terminalinden D1 bar geçmişini ve anlık fiyatı çeker."""
        if not self._check_connection():
            return None

        broker_sym = self.find_broker_symbol(generic_name)
        if not broker_sym:
            return None

        try:
            rates = mt5.copy_rates_from_pos(broker_sym, mt5.TIMEFRAME_D1, 0, n_bars)
            if rates is None or len(rates) < 2:
                return None

            closes = [float(r['close']) for r in rates]
            current_val = closes[-1]
            
            # Fiyat Mantık Denetimi (Broker opsiyon/kaldıraç türevlerini ele)
            if generic_name.upper() == "BTC" and current_val < 10000.0:
                return None  # Mini/opsiyon sözleşmesi, yfinance'e devret
            if generic_name.upper() in ["BRENT", "WTI"] and current_val < 30.0:
                return None  # Sentetik/opsiyon sözleşmesi, yfinance'e devret
            if generic_name.upper() == "DXY" and (current_val < 70.0 or current_val > 150.0):
                return None  # Farklı bir endeks türevi, yfinance'e devret

            prev_val = closes[-2]
            val_5d_ago = closes[-6] if len(closes) >= 6 else closes[0]
            val_20d_ago = closes[-21] if len(closes) >= 21 else closes[0]

            pct_daily = round(((current_val - prev_val) / prev_val) * 100, 2) if prev_val else 0.0
            pct_5d = round(((current_val - val_5d_ago) / val_5d_ago) * 100, 2) if val_5d_ago else 0.0
            pct_4w = round(((current_val - val_20d_ago) / val_20d_ago) * 100, 2) if val_20d_ago else 0.0

            # 60D percentile
            pct_rank = round((sum(1 for x in closes if x <= current_val) / len(closes)) * 100, 1)

            logger.info(f"⚡ [MT5 BROKER FEED] {generic_name} ({broker_sym}): {current_val} (1G: %{pct_daily:+.2f})")
            return {
                "value": round(current_val, 4),
                "prev": round(prev_val, 4),
                "val_5d_ago": round(val_5d_ago, 4),
                "month_ago": round(val_20d_ago, 4),
                "change_pct": pct_daily,
                "change_pct_5d": pct_5d,
                "change_pct_4w": pct_4w,
                "pct_rank_60d": pct_rank,
                "history_close": closes,
                "source": f"MT5 Broker Feed ({broker_sym})"
            }
        except Exception as e:
            logger.debug(f"MT5 verisi çekilirken hata ({generic_name}): {e}")
            return None
