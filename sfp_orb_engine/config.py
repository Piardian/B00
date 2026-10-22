"""
🌺 Begonya 00 (Cift Sifir) - Yapilandirma Modulu
SFP + Hacim Anomalisi ve ORB Seans Motoru
"""

import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- GENEL PROJE YOLLARI ---
DATA_DIR = BASE_DIR / "data"
EVIDENCE_DIR = BASE_DIR / "evidence"
TELEMETRY_DIR = BASE_DIR / "telemetry"
SHARED_DIR = BASE_DIR / "shared"
CONFIG_DIR = BASE_DIR / "config"
MACRO_GATE_FILE = SHARED_DIR / "macro_bias_gate.json"
SYMBOL_MAP_FILE = CONFIG_DIR / "symbol_map.json"

for d in [DATA_DIR, EVIDENCE_DIR, TELEMETRY_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- TWELVE DATA API AYARLARI ---
TWELVE_DATA_KEYS = [
    k for k in [
        os.getenv("TWELVE_DATA_API_KEY"),
        os.getenv("TWELVE_DATA_API_KEY_2"),
        os.getenv("TWELVE_DATA_API_KEY_3"),
    ] if k and k.strip()
]

# --- TELEGRAM AYARLARI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
REQUIRE_TELEGRAM_READINESS = os.getenv("REQUIRE_TELEGRAM_READINESS", "false").lower() == "true"
# TP/SL/BE pozisyon guncellemeleri Telegram'a canli bildirim olarak iletilir
NOTIFY_TRADE_LIFECYCLE = True

def round_price(val: float) -> float:
    """Parite fiyat büyüklüğüne göre dinamik ondalık yuvarlama (Memecoin 8 hane, Majör 2 hane)."""
    abs_val = abs(val)
    if abs_val == 0:
        return 0.0
    if abs_val >= 100:
        return round(val, 2)
    elif abs_val >= 1:
        return round(val, 4)
    elif abs_val >= 0.01:
        return round(val, 5)
    elif abs_val >= 0.0001:
        return round(val, 7)
    else:
        return round(val, 8)


# --- EVREN (SYMBOLS: BEGONYA VE SWING-BOS-CORE 60+ PARİTE TAM EVRENİ) ---
def load_all_universe_symbols() -> list:
    symbols = []
    if SYMBOL_MAP_FILE.exists():
        try:
            import json
            data = json.loads(SYMBOL_MAP_FILE.read_text(encoding="utf-8"))
            mappings = data.get("mappings", {})
            for k in mappings.keys():
                if k == "NAS100":
                    symbols.append("NAS100")
                elif k.startswith("USD") and len(k) == 6:
                    symbols.append(f"USD/{k[3:]}")
                elif k.endswith("USD"):
                    base = k[:-3]
                    symbols.append(f"{base}/USD")
                elif len(k) == 6:
                    symbols.append(f"{k[:3]}/{k[3:]}")
                else:
                    symbols.append(k)
        except Exception:
            pass

    for extra in ["QQQ", "SPY"]:
        if extra not in symbols:
            symbols.append(extra)

    return symbols if len(symbols) >= 10 else [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "USD/CHF",
        "EUR/JPY", "GBP/JPY", "XAU/USD", "QQQ", "SPY", "BTC/USD", "ETH/USD", "SOL/USD"
    ]

ACTIVE_SYMBOLS = ["EUR/USD", "GBP/USD", "XAU/USD"]

# --- ZAMAN DILIMLERI (TERCIH 2: BEGONYA ILE %100 SENKRON 15 DAKIKA) ---
PRIMARY_TIMEFRAME = "15m"       # Islem tetikleme zaman dilimi (Begonya ile tam eszamanli)
CONFIRMATION_TIMEFRAME = "1h"   # Trend & Yapi teyit dilimi
HIGHER_TIMEFRAME = "4h"         # HTF Rejim dilimi
ZERO_API_MODE = True            # Begonya'nin taranmis dosyalarindan diskten oku (0 API maliyeti)

# --- SFP (SWING FAILURE PATTERN) PARAMETRELERI ---
SFP_SWING_LOOKBACK = 15        # Swing High / Low tespit penceresi (bar sayisi)
SFP_MAX_SWEEP_BARS = 3         # Sweep'ten sonra kapanisin seviye icine donmesi icin maksimum bar
SFP_MIN_WICK_RATIO = 0.45      # Mumun fitil / toplam aralik orani (min red teyidi: %45 - Pin-bar / Hammer teyidi)
SFP_SL_BUFFER_ATR = 0.15       # Stop Loss'a eklenecek ATR carpan tamponu (varsayilan)
SFP_RR_TARGET_1 = 1.2          # TP1 Risk / Kazanc Orani (1.2R: %50 Kâr Al + BE)
SFP_RR_TARGET_2 = 2.0          # TP2 Risk / Kazanc Orani (2.0R: Kalan %50 Ana Hedef)
SFP_MIN_RR_TARGET_1 = 1.2      # Zorunlu Minimum TP1 RR Eşiği
SFP_MIN_RR_TARGET_2 = 2.0      # Zorunlu Minimum TP2 RR Eşiği

# --- ENTRY & İCRAAT PARAMETRELERİ (MODEL A: %50 CE SNIPER + iFVG + BREAKER) ---
ENTRY_MODEL = os.getenv("ENTRY_MODEL", "MIDPOINT")  # "MIDPOINT" (%50 Consequent Encroachment) veya "CLOSE" (Market Kapanışı)
LIMIT_EXPIRY_BARS = int(os.getenv("LIMIT_EXPIRY_BARS", "16"))  # 15 dakikalık 16 bar = 4 saatlik limit emir geçerlilik süresi
REQUIRE_ENTRY_REACTION = True       # Slice-Through / Tepkisiz bölge delinmesi durumunda limiti iptal et
REQUIRE_PRO_TREND_AAA = True        # Yalnızca 4H EMA50/200 Pro-Trend (Grade AAA) işlemlerine izin ver
USE_IFVG_ENTRY = True               # Standart FVG yerine Inversion FVG (iFVG) %50 CE Limit girişi kullan
REQUIRE_STRUCTURAL_BREAKER = True   # Sweep öncesi son zıt yönlü Order Block (Breaker) gövde kırılımı zorunlu

# Conservative operational limits; these are not fitted to historical returns.
MAX_DAILY_LOSS_R = 3.0
MAX_CONSECUTIVE_STOPS = 3
MAX_OPEN_RISK_R = 3.0
MAX_CURRENCY_RISK_R = 2.0

# Toksik / Aşırı Sahte İğne Üreten Parite Filtresi (SFP Taramasından Muaf)
EXCLUDED_SFP_SYMBOLS = ["GBP/JPY", "GBPJPY", "AUD/USD", "AUDUSD"]

# MODEL 2: İzin Verilen Likidite Havuzları (PDH/PDL + ASIAN_HIGH/ASIAN_LOW)
SFP_ALLOWED_POOLS = ["PDH", "PDL", "ASIAN_HIGH", "ASIAN_LOW"]

# Enstrüman Bazlı Dinamik SL Tamponu (ATR Çarpanı)
# İkincil likidite iğnelerini ve mikro stop avlarını önlemek için
ASSET_SL_BUFFER_MAP = {
    # Emtialar ve Kripto (Derin likidite avı ve çift iğne toleransı)
    "XAU/USD": 0.35,
    "ETH/USD": 0.35,
    "BTC/USD": 0.35,
    "SOL/USD": 0.35,
    # Çaprazlar ve Endeksler
    "GBP/JPY": 0.25,
    "EUR/JPY": 0.25,
    "SPY": 0.22,
    "QQQ": 0.22,
    "NAS100": 0.22,
    # Forex Majörler (Dar ve hassas tampon)
    "EUR/USD": 0.15,
    "USD/CHF": 0.15,
    "GBP/USD": 0.18,
    "AUD/USD": 0.18,
    "USD/CAD": 0.18,
    "USD/JPY": 0.20,
    "NZD/USD": 0.18,
}
DEFAULT_SL_BUFFER_ATR = 0.20

CRYPTO_SYMBOLS = [
    "BTC", "ETH", "SOL", "LTC", "AVAX", "NEAR", "APT", "SEI", "ARB", "OP",
    "XRP", "ADA", "DASH", "BCH", "LINK", "DOT", "FET", "RENDER", "TAO",
    "VIRTUAL", "WLD", "ARKM", "IO", "UNI", "AAVE", "PENDLE", "INJ", "CHZ",
    "RVN", "GALA", "SAND", "DOGE", "PEPE", "SHIB", "WIF", "BONK", "FLOKI", "PENGU", "SUI"
]

def is_crypto(symbol: str) -> bool:
    clean = symbol.replace("/", "").replace("-", "").upper()
    return any(c in clean for c in CRYPTO_SYMBOLS)

def is_session_active_for_scan(symbol: str, dt_utc: Optional[datetime] = None) -> bool:
    """
    Model 2 Seans Mimarisi (London Judas):
    - Hafta İçi (Pazartesi - Cuma): Yalnızca Forex ve Endeksler taranır, SADECE Londra Seansı (07:00 - 11:00 UTC).
      Kriptolar hafta içi taranmaz.
    - Hafta Sonu (Cumartesi / Pazar): Yalnızca Kripto Pariteleri taranır (07:00 - 11:00 UTC ve 13:00 - 17:00 UTC seans pencereleri).
      Forex ve hisse piyasaları hafta sonu taranmaz.
    """
    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)

    weekday = dt_utc.weekday()  # 0: Pzt ... 4: Cuma, 5: Cmt, 6: Pzr
    hour = dt_utc.hour
    crypto = is_crypto(symbol)

    # 1. Hafta Sonu (Cumartesi & Pazar)
    if weekday in [5, 6]:
        if not crypto:
            return False
        # Hafta sonu kripto seans saatleri: 07-11 UTC ve 13-17 UTC
        return (7 <= hour <= 11) or (13 <= hour <= 17)

    # 2. Hafta İçi (Pazartesi - Cuma)
    else:
        if crypto:
            return False  # Kriptolar hafta içi taranmaz (yalnızca hafta sonu)
        # Forex & Endeksler: Londra (07:00 - 11:00 UTC) ve New York (13:00 - 17:00 UTC) Seansları
        return (7 <= hour <= 11) or (13 <= hour <= 17)

def is_market_open(symbol: str, dt_utc: Optional[datetime] = None) -> bool:
    """
    Genel piyasa açık/kapalı kontrolü (Outcome Tracker açık pozisyon takibi için).
    Hafta sonu kapalı olan Forex, Emtia ve Hisse/Endeks piyasalarını filtreler.
    Kripto paralar 7/24 kesintisiz açıktır.
    """
    if is_crypto(symbol):
        return True  # Kripto 7/24 kesintisiz açık

    if dt_utc is None:
        dt_utc = datetime.now(timezone.utc)

    weekday = dt_utc.weekday()  # 0: Pazartesi ... 4: Cuma, 5: Cumartesi, 6: Pazar
    hour = dt_utc.hour

    # 1. Cumartesi: Tüm geleneksel piyasalar kapalı
    if weekday == 5:
        return False

    # 2. Cuma gecesi: FX & Emtia 21:00 UTC (TRT 00:00 Cumartesi) sonrasında kapanır
    if weekday == 4 and hour >= 21:
        return False

    # 3. Pazar: FX piyasası 21:00 UTC'ye (TRT Pazartesi 00:00) kadar kapalıdır
    if weekday == 6 and hour < 21:
        return False

    # 4. Hisse ve Endeksler (QQQ, SPY vb.) hafta sonu tamamen kapalıdır
    clean = symbol.replace("/", "").replace("-", "").upper()
    if clean in ["NAS100", "QQQ", "SPY", "SPX", "US30", "GER40"]:
        if weekday in [5, 6]:
            return False

    return True

def get_asset_sl_buffer(symbol: str) -> float:
    # 1. Özel tanımlı listede varsa
    if symbol in ASSET_SL_BUFFER_MAP:
        return ASSET_SL_BUFFER_MAP[symbol]

    clean = symbol.replace("/", "").replace("-", "").upper()

    # 2. Altın & Değerli Metaller
    if any(m in clean for m in ["XAU", "GOLD", "SILVER", "XAG"]):
        return 0.35

    # 3. Kripto Paralar (Tüm Altcoinler)
    if is_crypto(symbol):
        return 0.35

    # 4. Endeksler
    if clean in ["NAS100", "QQQ", "SPY", "SPX", "US30", "GER40"]:
        return 0.22

    # 5. JPY Çaprazları
    if clean.endswith("JPY"):
        return 0.25

    # 6. FX Çaprazları
    if clean in ["EURGBP", "EURAUD", "AUDCAD", "CADCHF", "NZDCAD", "EURCHF", "GBPCHF", "AUDCHF", "NZDCHF", "CADJPY", "AUDJPY", "CHFJPY"]:
        return 0.20

    # 7. Forex Majörler
    if clean in ["EURUSD", "USDCHF"]:
        return 0.15
    if clean in ["GBPUSD", "AUDUSD", "USDCAD", "NZDUSD", "USDJPY"]:
        return 0.18

    return DEFAULT_SL_BUFFER_ATR

# --- HACIM ANOMALISI PARAMETRELERI ---
VOLUME_ROLLING_WINDOW = 20     # Ortalama hacim hesaplama periyodu
VOLUME_TIER1_RATIO = 1.4       # 1.4x ortalama hacim (Orta Anomali)
VOLUME_TIER2_RATIO = 1.8       # 1.8x ortalama hacim (Yuksek Anomali)
VOLUME_TIER3_RATIO = 2.5       # 2.5x ortalama hacim (Klimaks / Ultra Anomali)
VOLUME_ZSCORE_MIN = 1.5        # Minimum Z-Score anomali siniri

# --- ORB (OPENING RANGE BREAKOUT) PARAMETRELERI ---
ORB_ENABLED = True
ORB_RANGE_MINUTES = 15         # Acilis araligini belirleyen ilk dakika sayisi (15 dk)

# Seans Saatleri (UTC bazinda - TRT = UTC+3)
# Londra: 07:00 UTC (10:00 TRT)
# New York: 13:30 UTC (16:30 TRT)
# Tokyo: 00:00 UTC (03:00 TRT)
ORB_SESSIONS = {
    "LONDON": {
        "name": "Londra Seansı",
        "open_utc": "07:00",
        "close_utc": "15:30",
        "orb_window_end_utc": "07:15",
    },
    "NEW_YORK": {
        "name": "New York Seansı",
        "open_utc": "13:30",
        "close_utc": "21:00",
        "orb_window_end_utc": "13:45",
    },
    "TOKYO": {
        "name": "Tokyo / Asya Seansı",
        "open_utc": "00:00",
        "close_utc": "06:00",
        "orb_window_end_utc": "00:15",
    }
}

WEEKEND_ORB_ENABLED = False        # Hafta sonu kripto yatay bandında sahte kırılımları önlemek için ORB kapalı, yalnızca SFP aktif!
ORB_MIN_BREAKOUT_VOL_RATIO = 2.0    # Kırılım mumu için minimum kurumsal hacim katı (min 2.0x)
ORB_SL_MODE = "MIDPOINT"            # "MIDPOINT" (Range %50) veya "OPPOSITE" (Karsi bant)
ORB_TP1_MULT = 1.0                  # Range yuksekligi x 1.0
ORB_TP2_MULT = 2.0                  # Range yuksekligi x 2.0

# --- TARAMA PERIYODU ---
SCAN_INTERVAL_SECONDS = 60        # Canli tarama dongusu (saniye)
SIGNAL_COOLDOWN_MINUTES = 45      # Ayni paritede ayni yonde yeni sinyal icin bekleme
