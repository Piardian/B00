"""
🌺 Begonya 00 - Akilli Veri Saglayicisi (Tercih 2: Begonya Paylasimli 15m Cache & 0 API Kredisi)
Begonya'nin taranmis canli JSON dosyalarini dogrudan diskten okur.
"""

import time
import json
import logging
import os
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import requests

from .config import TWELVE_DATA_KEYS, DATA_DIR, ZERO_API_MODE, is_crypto

logger = logging.getLogger("Begonya00.DataProvider")

LOCAL_CANDLE_CACHE = DATA_DIR / "candles"
LOCAL_CANDLE_CACHE.mkdir(parents=True, exist_ok=True)

SHARED_CANDLE_DIRS = [
    Path(os.getenv("CANDLE_DATA_DIR", r"C:\Users\piard\.gemini\antigravity\scratch\swing-bos-core\data")),
    Path(r"C:\Users\piard\.gemini\antigravity\scratch\Begonya\smc_engine\data"),
    LOCAL_CANDLE_CACHE,
]


class MarketDataProvider:
    def __init__(self, api_keys: Optional[List[str]] = None):
        self.api_keys = api_keys or TWELVE_DATA_KEYS
        self.current_key_idx = 0
        self.last_call_time = 0.0
        self.zero_api_mode = ZERO_API_MODE

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    def fetch_candles(
        self,
        symbol: str,
        interval: str = "15m",
        outputsize: int = 60,
    ) -> Optional[pd.DataFrame]:
        """
        Begonya Veri Saglayicisi:
        1. Kriptolar icin canli Binance REST API (Tamamen Ucretsiz - 0 Kredi - Sifir Gecikme)
        2. Forex/Endeksler icin Begonya Paylasimli Canli JSON (Bayatlik Kontrollu - 0 Kredi)
        3. Yahoo Finance Fallback (Tamamen Ucretsiz - 0 Kredi)
        4. TwelveData Fallback
        """
        clean_sym = self._normalize_symbol(symbol)

        # 1. Kripto Pariteleri: Canlı Binance API (Anlık, taze, 0 kredi maliyeti)
        if is_crypto(symbol) or is_crypto(clean_sym):
            df_binance = self._fetch_binance(clean_sym, interval, outputsize)
            if df_binance is not None and len(df_binance) >= 20:
                self._save_local_cache(clean_sym, interval, df_binance)
                return df_binance

        # 2. Begonya Paylaşımlı Canlı JSON Dosyası (Disk Okuması - Taze ise 0 Kredi)
        df_shared = self._load_from_shared_cache(clean_sym, interval, outputsize)
        if df_shared is not None and len(df_shared) >= 20:
            return df_shared

        # 3. Yahoo Finance Fallback (Tamamen Ücretsiz - 0 Kredi)
        df_yf = self._fetch_yfinance(symbol, interval, outputsize)
        if df_yf is not None and len(df_yf) >= 20:
            self._save_local_cache(clean_sym, interval, df_yf)
            return df_yf

        # 4. TwelveData (Eğer ZERO_API_MODE kapalıysa ve kesin gerekirse)
        if not self.zero_api_mode:
            df_td = self._fetch_twelve_data(symbol, interval, outputsize)
            if df_td is not None and len(df_td) >= 20:
                self._save_local_cache(clean_sym, interval, df_td)
                return df_td

        return None

    def _load_from_shared_cache(self, clean_sym: str, interval: str, outputsize: int) -> Optional[pd.DataFrame]:
        """Begonya ve swing-bos-core paylaşımlı klasöründen canlı JSON okur (bayatlık korumalı)."""
        now_ts = time.time()
        for base_dir in SHARED_CANDLE_DIRS:
            if not base_dir.exists():
                continue

            file_path = base_dir / f"{clean_sym}_{interval}.json"
            if not file_path.exists():
                continue

            # Dosya mtime bayatlık kontrolü:
            # 1m için maksimum 10 dakika (600s)
            # 15m için maksimum 45 dakika (2700s)
            # 1h için maksimum 3 saat (10800s)
            file_age_sec = now_ts - file_path.stat().st_mtime
            if interval in ["1m", "1min"] and file_age_sec > 600:
                continue
            elif interval in ["15m", "15min"] and file_age_sec > 2700:
                continue
            elif interval in ["1h", "1hour"] and file_age_sec > 10800:
                continue

            try:
                raw = json.loads(file_path.read_text(encoding="utf-8"))
                if not raw or len(raw) < 15:
                    continue

                df = pd.DataFrame(raw)
                if "timestamp" in df.columns:
                    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
                elif "datetime" in df.columns:
                    df["datetime"] = pd.to_datetime(df["datetime"])
                else:
                    continue

                # Son mum zamanı bayatlık kontrolü:
                # Disk dosyası güncellenmiş görünse bile içindeki son bar bayat ise reddet!
                last_dt = df["datetime"].iloc[-1]
                if last_dt.tzinfo is not None:
                    last_dt = last_dt.tz_localize(None)
                now_utc = datetime.utcnow()
                bar_age_min = (now_utc - last_dt).total_seconds() / 60.0

                if interval in ["1m", "1min"] and bar_age_min > 15:
                    continue
                elif interval in ["15m", "15min"] and bar_age_min > 45:
                    continue

                for col in ["open", "high", "low", "close"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                # Hacim yoksa oynaklık/aralık bazlı kurumsal aktivite hacmi üret
                if "volume" not in df.columns or df["volume"].sum() == 0:
                    df["volume"] = ((df["high"] - df["low"]) * 100000).clip(lower=100.0).round(1)
                else:
                    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(100.0)

                df = df.sort_values("datetime").tail(outputsize).reset_index(drop=True)
                return df[["datetime", "open", "high", "low", "close", "volume"]]

            except Exception as e:
                logger.debug(f"Shared cache okuma hatasi ({clean_sym}_{interval}): {e}")

        return None

    def _fetch_binance(self, clean_sym: str, interval: str, outputsize: int) -> Optional[pd.DataFrame]:
        binance_sym = clean_sym
        if binance_sym.endswith("USDT"):
            pass
        elif binance_sym.endswith("USD"):
            binance_sym = binance_sym[:-3] + "USDT"
        else:
            binance_sym = binance_sym + "USDT"

        if interval in ["1m", "1min"]:
            b_interval = "1m"
        elif interval in ["15m", "15min"]:
            b_interval = "15m"
        else:
            b_interval = "1h"

        url = f"https://api.binance.com/api/v3/klines?symbol={binance_sym}&interval={b_interval}&limit={outputsize}"

        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                raw = resp.json()
                rows = []
                for b in raw:
                    rows.append({
                        "datetime": pd.to_datetime(b[0], unit="ms"),
                        "open": float(b[1]),
                        "high": float(b[2]),
                        "low": float(b[3]),
                        "close": float(b[4]),
                        "volume": float(b[5]),
                    })
                df = pd.DataFrame(rows)
                if not df.empty:
                    return df.sort_values("datetime").reset_index(drop=True)
        except Exception:
            pass
        return None

    def _fetch_yfinance(self, symbol: str, interval: str, outputsize: int) -> Optional[pd.DataFrame]:
        yf_symbol = symbol.replace("/", "") + "=X" if "/" in symbol else symbol
        if symbol == "XAU/USD":
            yf_symbol = "GC=F"
        elif symbol in ["QQQ", "SPY"]:
            yf_symbol = symbol
        elif "BTC" in symbol:
            yf_symbol = "BTC-USD"
        elif "ETH" in symbol:
            yf_symbol = "ETH-USD"
        elif "SOL" in symbol:
            yf_symbol = "SOL-USD"

        if interval in ["1m", "1min"]:
            yf_interval = "1m"
            period = "1d"
        elif interval in ["5m", "5min"]:
            yf_interval = "5m"
            period = "5d"
        elif interval in ["15m", "15min"]:
            yf_interval = "15m"
            period = "5d"
        else:
            yf_interval = "1h"
            period = "1mo"

        try:
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period=period, interval=yf_interval)
            if not hist.empty and len(hist) >= 15:
                hist = hist.tail(outputsize).reset_index()
                col_name = "Datetime" if "Datetime" in hist.columns else "Date"
                hist = hist.rename(columns={
                    col_name: "datetime",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                })
                hist["datetime"] = pd.to_datetime(hist["datetime"]).dt.tz_localize(None)
                if hist["volume"].sum() == 0:
                    hist["volume"] = ((hist["high"] - hist["low"]) * 100000).clip(lower=100.0).round(1)
                return hist[["datetime", "open", "high", "low", "close", "volume"]]
        except Exception:
            pass
        return None

    def _fetch_twelve_data(self, symbol: str, interval: str, outputsize: int) -> Optional[pd.DataFrame]:
        if not self.api_keys:
            return None
        td_interval = "15min" if interval in ["15m", "15min"] else "1h"
        api_key = self.api_keys[self.current_key_idx % len(self.api_keys)]
        url = "https://api.twelvedata.com/time_series"
        params = {"symbol": symbol, "interval": td_interval, "outputsize": outputsize, "apikey": api_key}
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if "values" in data and isinstance(data["values"], list):
                    df = pd.DataFrame(data["values"])
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                        else:
                            df[col] = 100.0
                    return df.sort_values("datetime").reset_index(drop=True)
        except Exception:
            pass
        return None

    def _save_local_cache(self, clean_sym: str, interval: str, df: pd.DataFrame):
        try:
            cache_file = LOCAL_CANDLE_CACHE / f"{clean_sym}_{interval}.json"
            df_copy = df.copy()
            df_copy["datetime"] = df_copy["datetime"].astype(str)
            cache_file.write_text(json.dumps(df_copy.to_dict(orient="records")), encoding="utf-8")
        except Exception:
            pass
