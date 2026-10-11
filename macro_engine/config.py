import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.resolve()
ENV_FILE = BASE_DIR / ".env"
ROOT_ENV = BASE_DIR.parent / ".env"

# Only project-local and process environment configuration is allowed.
if ROOT_ENV.exists():
    load_dotenv(ROOT_ENV)
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()

GEMINI_KEYS = [
    k for k in [
        os.getenv("GEMINI_USER_A_KEY", ""),
        os.getenv("GEMINI_USER_B_KEY", ""),
        os.getenv("GEMINI_USER_C_KEY", ""),
        os.getenv("GEMINI_USER_D_KEY", ""),
        os.getenv("GEMINI_API_KEY", ""),
    ] if k
]

STRATEGIST_CASCADE = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

ANALYST_CASCADE = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
]

FRED_API_KEY = os.getenv("FRED_API_KEY", "")
TRADING_ECONOMICS_API_KEY = os.getenv("TRADING_ECONOMICS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# Begonya 00 için Makro Ekonomik / Sabah Bülteni Telegram Bildirimleri (Varsayılan: Kapalı)
ENABLE_MACRO_TELEGRAM_NOTIFICATIONS = os.getenv("ENABLE_MACRO_TELEGRAM_NOTIFICATIONS", "false").lower() == "true"

MARKET_SYMBOLS = {
    "DXY": "DX-Y.NYB",
    "GOLD": "GC=F",
    "BRENT": "BZ=F",
    "WTI": "CL=F",
    "US10Y": "^TNX",
    "US02Y": "2YY=F",
    "BTC": "BTC-USD",
    "SPX": "^GSPC",
    "COPPER": "HG=F",
    "VIX": "^VIX",
    "HYG": "HYG",
    "LQD": "LQD",
    "EUR_BOND": "IBGM.AS",
    "SOL": "SOL-USD",
    "CA02Y": "CAD2Y=X",
    "DE02Y": "DE02Y=X",
    "GB02Y": "GB02Y=X",
    "AU02Y": "AU02Y=X",
    "IRON_ORE": "TIO=F",
    "DAIRY_GDT": "DC=F",
    "NZ02Y": "NZD2Y=X",
    "FED_FUNDS_FUTURES": "ZQ=F",
}

OPTIONAL_POLICY_SYMBOLS = {
    "FED_FUNDS_FUTURES": "ZQ=F",
}

HYSTERESIS_CONFIG = {
    "BRENT_ENERGY_PENALTY_ENTER": 85.0,
    "BRENT_ENERGY_PENALTY_EXIT": 81.0,
    "RISK_PRESERVATION_ENTER": 0.65,
    "RISK_PRESERVATION_EXIT": 0.50,
    "SPREAD_DESYNC_NOISE_BPS": 3.0,
}

NEWS_FREEZE_CONFIG = {
    "FREEZE_MINUTES_BEFORE": 15,
    "FREEZE_MINUTES_AFTER": 15,
    "HIGH_IMPACT_KEYWORDS": [
        "non-farm", "nfp", "payrolls", "unemployment rate",
        "cpi", "consumer price index", "core cpi", "pce",
        "fomc", "interest rate decision", "rate decision",
        "ecb", "boe", "rba", "rbnz", "boc", "boj"
    ]
}

PORTFOLIO_EXPOSURE_CONFIG = {
    "MAX_USD_CONCURRENT_LEGS": 2,
    "MAX_JPY_CONCURRENT_LEGS": 2,
    "MAX_CRYPTO_CONCURRENT_LEGS": 1,
    "MAX_TOTAL_PORTFOLIO_RISK": 2.5
}

MT5_SCALPER_DIR = Path(
    os.getenv("MT5_SCALPER_DIR", str(BASE_DIR.parent / "mt5_scalper"))
).resolve()
BIAS_GATE_FILE = BASE_DIR / "gateways" / "macro_bias_gate.json"
