"""
7 Katmanlı (39 Coin - Meme, DeFi, Gaming, AI, L1/L2, Klasik Majörler Dahil)
Kripto Sermaye Akışı, Türev (Open Interest + Funding) ve Sektör Rotasyon Veri Çekici.

Mimari:
1. AŞAMA (Bulk Radar - Sadece 3 HTTP İsteği):
   39 coinin tamamı için 24s Spot Ticker, 24s Futures Ticker ve Anlık Funding Rate
   verilerini tek seferde çeker; Sektör Genişliği (Sector Breadth) ve Katman Şelalesini
   (Layer 0 -> Layer 6 Meme) 39 coinin tamamı üzerinden hesaplar.
2. AŞAMA (Hedefli Derin Analiz - Targeted Deep Check):
   Yalnızca çekirdek öncüler (BTC, ETH, SOL, SUI) ve ön elemeden geçen finalist coinler
   için 1H/4H Spot Klines (RVOL) ve Futures Open Interest geçmişini çeker.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set
import requests

logger = logging.getLogger("CryptoRotationDataIngestion")


def _entry(
    coin: str,
    layer: int,
    layer_name: str,
    sector: str,
    spot_symbol: Optional[str] = None,
    futures_symbol: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "coin": coin,
        "spot_symbol": spot_symbol or f"{coin}USDT",
        "futures_symbol": futures_symbol or f"{coin}USDT",
        "smc_symbol": f"{coin}USD",
        "layer": layer,
        "layer_name": layer_name,
        "sector": sector,
    }


CRYPTO_ROTATION_UNIVERSE: Dict[str, Dict[str, Any]] = {
    # Katman 0: Çekirdek Rezerv
    "BTC": _entry("BTC", 0, "LAYER_0_ANCHOR", "CORE_RESERVE"),
    # Katman 1: Büyük-Cap Öncü
    "ETH": _entry("ETH", 1, "LAYER_1_BELLWETHER", "LARGE_CAP_SMART_CONTRACT"),
    # Katman 2: Majör L1 & L2 Altyapı (8 Coin)
    "SOL": _entry("SOL", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    "SUI": _entry("SUI", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    "AVAX": _entry("AVAX", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    "NEAR": _entry("NEAR", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    "APT": _entry("APT", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    "SEI": _entry("SEI", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    "ARB": _entry("ARB", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    "OP": _entry("OP", 2, "LAYER_2_MAJOR_L1_L2", "HIGH_BETA_L1_L2"),
    # Katman 3: Klasik Ödeme & Köklü Majörler (7 Coin)
    "XRP": _entry("XRP", 3, "LAYER_3_LEGACY_PAYMENT", "LEGACY_PAYMENT_INFRA"),
    "ADA": _entry("ADA", 3, "LAYER_3_LEGACY_PAYMENT", "LEGACY_PAYMENT_INFRA"),
    "LTC": _entry("LTC", 3, "LAYER_3_LEGACY_PAYMENT", "LEGACY_PAYMENT_INFRA"),
    "DASH": _entry("DASH", 3, "LAYER_3_LEGACY_PAYMENT", "LEGACY_PAYMENT_INFRA"),
    "BCH": _entry("BCH", 3, "LAYER_3_LEGACY_PAYMENT", "LEGACY_PAYMENT_INFRA"),
    "LINK": _entry("LINK", 3, "LAYER_3_LEGACY_PAYMENT", "LEGACY_PAYMENT_INFRA"),
    "DOT": _entry("DOT", 3, "LAYER_3_LEGACY_PAYMENT", "LEGACY_PAYMENT_INFRA"),
    # Katman 4: AI, Compute & DePIN (7 Coin)
    "FET": _entry("FET", 4, "LAYER_4_AI_NARRATIVE", "AI_SECTOR"),
    "RENDER": _entry("RENDER", 4, "LAYER_4_AI_NARRATIVE", "AI_SECTOR"),
    "TAO": _entry("TAO", 4, "LAYER_4_AI_NARRATIVE", "AI_SECTOR"),
    "VIRTUAL": _entry("VIRTUAL", 4, "LAYER_4_AI_NARRATIVE", "AI_SECTOR"),
    "WLD": _entry("WLD", 4, "LAYER_4_AI_NARRATIVE", "AI_SECTOR"),
    "ARKM": _entry("ARKM", 4, "LAYER_4_AI_NARRATIVE", "AI_SECTOR"),
    "IO": _entry("IO", 4, "LAYER_4_AI_NARRATIVE", "AI_SECTOR"),
    # Katman 5: DeFi, Gaming & Mid-Cap Utility (8 Coin)
    "UNI": _entry("UNI", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    "AAVE": _entry("AAVE", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    "PENDLE": _entry("PENDLE", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    "INJ": _entry("INJ", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    "CHZ": _entry("CHZ", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    "RVN": _entry("RVN", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    "GALA": _entry("GALA", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    "SAND": _entry("SAND", 5, "LAYER_5_DEFI_GAMING_MIDCAP", "DEFI_GAMING_MIDCAP"),
    # Katman 6: Meme Coinler - En Alt Taban / Yüksek Beta Risk İştahı (7 Coin)
    "DOGE": _entry("DOGE", 6, "LAYER_6_MEME_HIGH_BETA", "MEME_SECTOR"),
    "PEPE": _entry(
        "PEPE",
        6,
        "LAYER_6_MEME_HIGH_BETA",
        "MEME_SECTOR",
        spot_symbol="PEPEUSDT",
        futures_symbol="1000PEPEUSDT",
    ),
    "SHIB": _entry(
        "SHIB",
        6,
        "LAYER_6_MEME_HIGH_BETA",
        "MEME_SECTOR",
        spot_symbol="SHIBUSDT",
        futures_symbol="1000SHIBUSDT",
    ),
    "WIF": _entry("WIF", 6, "LAYER_6_MEME_HIGH_BETA", "MEME_SECTOR"),
    "BONK": _entry(
        "BONK",
        6,
        "LAYER_6_MEME_HIGH_BETA",
        "MEME_SECTOR",
        spot_symbol="BONKUSDT",
        futures_symbol="1000BONKUSDT",
    ),
    "FLOKI": _entry(
        "FLOKI",
        6,
        "LAYER_6_MEME_HIGH_BETA",
        "MEME_SECTOR",
        spot_symbol="FLOKIUSDT",
        futures_symbol="1000FLOKIUSDT",
    ),
    "PENGU": _entry("PENGU", 6, "LAYER_6_MEME_HIGH_BETA", "MEME_SECTOR"),
}


class CryptoRotationDataIngestion:
    """
    2 Aşamalı (Bulk Pre-Screen + Finalist Deep Check) Kripto Rotasyon Veri Çekici.
    """

    SPOT_BASE = "https://api.binance.com"
    FUTURES_BASE = "https://fapi.binance.com"
    COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"

    def __init__(self, timeout_seconds: float = 6.0, max_deep_finalists: int = 39):
        self.timeout = timeout_seconds
        self.max_deep_finalists = max_deep_finalists

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _select_deep_fetch_coins(
        bulk_metrics: Dict[str, Dict[str, Any]],
        max_finalists: int,
    ) -> Set[str]:
        """
        39 coin içinden 1H/4H mum ve OI geçmişi çekilecek coinleri seçer.
        Varsayılan olarak 39 coinin tamamı paralel (ThreadPoolExecutor) çekilir;
        böylece Stealth Accumulation (Gizli Toplama) ve sektör RVOL hesabında kör nokta kalmaz.
        """
        if max_finalists >= len(bulk_metrics):
            return set(bulk_metrics.keys())

        selected: Set[str] = {"BTC", "ETH", "SOL", "SUI", "LTC", "DASH"}
        btc_chg = float(bulk_metrics.get("BTC", {}).get("spot_price_change_24h_pct", 0.0))

        by_sector: Dict[str, List[Dict[str, Any]]] = {}
        for coin, item in bulk_metrics.items():
            if coin in ("BTC", "ETH"):
                continue
            rs_24h = float(item.get("spot_price_change_24h_pct", 0.0)) - btc_chg
            item["_prelim_rs_24h"] = rs_24h
            by_sector.setdefault(item["sector"], []).append(item)

        for _, members in by_sector.items():
            sorted_by_rs = sorted(members, key=lambda x: x["_prelim_rs_24h"], reverse=True)
            for m in sorted_by_rs[:2]:
                selected.add(m["coin"])
            if sorted_by_rs:
                selected.add(sorted_by_rs[-1]["coin"])

        if len(selected) > max_finalists + 4:
            core = {"BTC", "ETH", "SOL", "SUI", "LTC", "DASH"}
            others = sorted(
                [c for c in selected if c not in core],
                key=lambda c: abs(bulk_metrics[c].get("_prelim_rs_24h", 0.0)),
                reverse=True,
            )
            selected = core.union(others[: max(4, max_finalists - len(core))])

        return selected

    def _fetch_coin_detail(self, coin: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        spot_sym = meta["spot_symbol"]
        fut_sym = meta["futures_symbol"]

        klines_1h = self._get_json(
            f"{self.SPOT_BASE}/api/v3/klines",
            params={"symbol": spot_sym, "interval": "1h", "limit": 26},
        )
        klines_4h = self._get_json(
            f"{self.SPOT_BASE}/api/v3/klines",
            params={"symbol": spot_sym, "interval": "4h", "limit": 32},
        )

        oi_hist: List[Dict[str, Any]] = []
        try:
            oi_hist = self._get_json(
                f"{self.FUTURES_BASE}/futures/data/openInterestHist",
                params={"symbol": fut_sym, "period": "1h", "limit": 25},
            )
        except Exception as exc:
            logger.debug(f"{coin} ({fut_sym}) OI geçmişi çekilemedi: {exc}")

        def parse_klines(raw_klines: List[Any]) -> List[Dict[str, float]]:
            parsed = []
            for row in raw_klines:
                parsed.append(
                    {
                        "timestamp": float(row[0]),
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                        "base_volume": float(row[5]),
                        "quote_volume": float(row[7]),
                    }
                )
            return parsed

        bars_1h = parse_klines(klines_1h) if isinstance(klines_1h, list) else []
        bars_4h = parse_klines(klines_4h) if isinstance(klines_4h, list) else []

        oi_points: List[Dict[str, float]] = []
        if isinstance(oi_hist, list):
            for item in oi_hist:
                try:
                    oi_points.append(
                        {
                            "timestamp": float(item.get("timestamp", 0)),
                            "sum_open_interest": float(item.get("sumOpenInterest", 0.0)),
                            "sum_open_interest_value": float(
                                item.get("sumOpenInterestValue", 0.0)
                            ),
                        }
                    )
                except (TypeError, ValueError):
                    continue

        return {
            "bars_1h": bars_1h,
            "bars_4h": bars_4h,
            "oi_history_1h": oi_points,
            "deep_fetched": True,
        }

    def fetch_rotation_snapshot(self, deep_fetch_all: bool = True) -> Dict[str, Any]:
        """
        Önce 3 toplu (bulk) çağrıyla 39 coinin tamamını tarar, ardından paralel
        ThreadPoolExecutor ile 39 coinin tamamı için 1H/4H mum ve OI geçmişini çeker.
        """
        snapshot: Dict[str, Any] = {
            "status": "AVAILABLE",
            "universe_size": len(CRYPTO_ROTATION_UNIVERSE),
            "btc_dominance": {
                "btc_dominance_pct": None,
                "eth_dominance_pct": None,
                "btcdom_index_price": None,
                "btcdom_change_24h_pct": None,
                "btcdom_change_4h_pct": None,
                "source": "Binance BTCDOMUSDT + CoinGecko Global",
            },
            "coins": {},
            "errors": [],
        }

        try:
            # AŞAMA 1: Toplu (Bulk) 24s Spot Ticker, Futures Ticker ve Funding Rate
            spot_24h_raw = self._get_json(f"{self.SPOT_BASE}/api/v3/ticker/24hr")
            fut_24h_raw = self._get_json(f"{self.FUTURES_BASE}/fapi/v1/ticker/24hr")
            premium_raw = self._get_json(f"{self.FUTURES_BASE}/fapi/v1/premiumIndex")

            spot_24h_map = {
                item["symbol"]: item
                for item in (spot_24h_raw if isinstance(spot_24h_raw, list) else [])
                if isinstance(item, dict) and "symbol" in item
            }
            fut_24h_map = {
                item["symbol"]: item
                for item in (fut_24h_raw if isinstance(fut_24h_raw, list) else [])
                if isinstance(item, dict) and "symbol" in item
            }
            premium_map = {
                item["symbol"]: item
                for item in (premium_raw if isinstance(premium_raw, list) else [])
                if isinstance(item, dict) and "symbol" in item
            }

            # BTCDOMUSDT Endeksi
            btcdom_ticker = fut_24h_map.get("BTCDOMUSDT")
            if btcdom_ticker:
                snapshot["btc_dominance"]["btcdom_index_price"] = float(
                    btcdom_ticker.get("lastPrice", 0.0)
                )
                snapshot["btc_dominance"]["btcdom_change_24h_pct"] = float(
                    btcdom_ticker.get("priceChangePercent", 0.0)
                )

            try:
                btcdom_4h = self._get_json(
                    f"{self.FUTURES_BASE}/fapi/v1/klines",
                    params={"symbol": "BTCDOMUSDT", "interval": "4h", "limit": 3},
                )
                if isinstance(btcdom_4h, list) and len(btcdom_4h) >= 2:
                    prev_close = float(btcdom_4h[-2][4])
                    curr_close = float(btcdom_4h[-1][4])
                    if prev_close > 0:
                        snapshot["btc_dominance"]["btcdom_change_4h_pct"] = round(
                            ((curr_close - prev_close) / prev_close) * 100.0, 3
                        )
            except Exception as exc:
                logger.debug(f"BTCDOMUSDT 4h klines çekilemedi: {exc}")

            try:
                cg_data = self._get_json(self.COINGECKO_GLOBAL_URL)
                mcap_pct = cg_data.get("data", {}).get("market_cap_percentage", {})
                if isinstance(mcap_pct.get("btc"), (int, float)):
                    snapshot["btc_dominance"]["btc_dominance_pct"] = round(
                        float(mcap_pct["btc"]), 2
                    )
                if isinstance(mcap_pct.get("eth"), (int, float)):
                    snapshot["btc_dominance"]["eth_dominance_pct"] = round(
                        float(mcap_pct["eth"]), 2
                    )
            except Exception as exc:
                logger.debug(f"CoinGecko BTC.D çekilemedi: {exc}")

            # 39 Coinin tamamı için Bulk kayıtları hazırla
            for coin, meta in CRYPTO_ROTATION_UNIVERSE.items():
                spot_sym = meta["spot_symbol"]
                fut_sym = meta["futures_symbol"]
                s_tick = spot_24h_map.get(spot_sym, {})
                f_tick = fut_24h_map.get(fut_sym, {})
                p_tick = premium_map.get(fut_sym, {})

                last_spot_price = float(s_tick.get("lastPrice", 0.0) or 0.0)
                snapshot["coins"][coin] = {
                    **meta,
                    "spot_last_price": last_spot_price,
                    "spot_quote_volume_24h": float(s_tick.get("quoteVolume", 0.0) or 0.0),
                    "spot_price_change_24h_pct": float(
                        s_tick.get("priceChangePercent", 0.0) or 0.0
                    ),
                    "futures_quote_volume_24h": float(
                        f_tick.get("quoteVolume", 0.0) or 0.0
                    ),
                    "funding_rate": float(p_tick.get("lastFundingRate", 0.0) or 0.0),
                    "mark_price": float(p_tick.get("markPrice", last_spot_price) or 0.0),
                    "bars_1h": [],
                    "bars_4h": [],
                    "oi_history_1h": [],
                    "deep_fetched": False,
                }

            # AŞAMA 2: 39 Coinin Tamamı İçin Paralel 1H/4H Klines + OI History Çekimi
            target_coins = (
                set(CRYPTO_ROTATION_UNIVERSE.keys())
                if deep_fetch_all
                else self._select_deep_fetch_coins(
                    snapshot["coins"], self.max_deep_finalists
                )
            )
            snapshot["deep_fetched_coins"] = sorted(target_coins)

            with ThreadPoolExecutor(max_workers=8) as pool:
                future_to_coin = {
                    pool.submit(
                        self._fetch_coin_detail, coin, CRYPTO_ROTATION_UNIVERSE[coin]
                    ): coin
                    for coin in target_coins
                    if coin in CRYPTO_ROTATION_UNIVERSE
                }
                for fut in as_completed(future_to_coin):
                    coin = future_to_coin[fut]
                    try:
                        detail = fut.result()
                        snapshot["coins"][coin].update(detail)
                    except Exception as coin_exc:
                        err_msg = f"{coin}: {coin_exc}"
                        logger.warning(f"Kripto detay verisi eksik ({err_msg})")
                        snapshot["errors"].append(err_msg)

            if "BTC" not in snapshot["coins"] or "ETH" not in snapshot["coins"]:
                snapshot["status"] = "UNAVAILABLE"
            elif len(snapshot["errors"]) > 10:
                snapshot["status"] = "PARTIAL"

        except Exception as exc:
            logger.warning(f"Kripto rotasyon veri çekimi başarısız: {exc}")
            snapshot["status"] = "UNAVAILABLE"
            snapshot["errors"].append(str(exc))

        return snapshot
