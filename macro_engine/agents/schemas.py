from typing import Literal, Optional
from pydantic import BaseModel, Field


class LiquidityOutput(BaseModel):
    """Ajan 1: Likidite ve Finansal Koşullar Analisti Çıktı Şeması"""
    liquidity_regime: Literal["Expanding", "Contracting", "Neutral"] = Field(description="Fed bilançosu, RRP, TGA ve DXY etkisiyle genel küresel likidite rejimi")
    yield_curve_dynamic: Literal["Bull Steepening", "Bear Steepening", "Bear Flattening", "Bull Flattening", "Range-bound Slope", "Inverted", "Normal"] = Field(description="US10Y - US02Y getiri eğrisi dinamik durumu")
    dollar_pressure: Literal["High", "Low", "Neutral"] = Field(description="DXY kaynaklı finansal sıkılaşma baskısı")
    credit_stress: Literal["Low / Benign", "Moderate", "High / Distress"] = Field(default="Low / Benign", description="HY OAS kredi stresi")
    financial_conditions_state: Literal["Accommodative / Loose", "Neutral", "Restrictive / Tight"] = Field(default="Accommodative / Loose", description="NFCI finansal koşullar rejimi")
    fast_stress_override: bool = Field(default=False, description="T-0 piyasa stresi")
    hyg_lqd_stress: str = Field(default="Normal / Benign", description="HYG/LQD canlı kredi durumu")
    confidence: float = Field(ge=0.0, le=1.0)
    key_driver: str = Field(description="En belirleyici likidite faktörü")
    summary: str = Field(description="Likidite koşullarının teknik özeti")


class GrowthOutput(BaseModel):
    """Ajan 2: Büyüme ve Enflasyon Dinamikleri Analisti Çıktı Şeması"""
    macro_quadrant: Literal["Goldilocks", "Reflation", "Late-Cycle Overheating", "Stagflation", "Deflation"]
    energy_shock_risk: bool
    growth_momentum: Literal["Accelerating", "Decelerating", "Stable"]
    inflation_risk: Literal["High", "Medium", "Low"]
    transatlantic_spread_bps: float = Field(default=238.0)
    eurusd_terms_of_trade_penalty: bool = Field(default=False)
    confidence: float = Field(ge=0.0, le=1.0)
    us_vs_global_divergence: str = Field(default="")
    summary: str


class AssetBiases(BaseModel):
    XAUUSD: Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"] = "Neutral"
    BTC: Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"] = "Neutral"
    DXY: Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"] = "Neutral"
    EURUSD: Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"] = "Neutral"
    US10Y: Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"] = "Neutral"
    SPX: Literal["Strong Bullish", "Bullish", "Neutral", "Bearish", "Strong Bearish"] = "Neutral"


class ExecutionGates(BaseModel):
    """Advisory only. These LLM-generated values are never authoritative for execution."""
    XAUUSD: Literal["LONG_ONLY", "SHORT_ONLY", "NEUTRAL_ALL", "NEUTRAL_RANGE", "DEFENSIVE_HOLD", "REDUCE_ONLY", "NO_TRADE"] = "NEUTRAL_ALL"
    BTC: Literal["LONG_ONLY", "SHORT_ONLY", "NEUTRAL_ALL", "NEUTRAL_RANGE", "DEFENSIVE_HOLD", "REDUCE_ONLY", "NO_TRADE"] = "NEUTRAL_ALL"
    EURUSD: Literal["LONG_ONLY", "SHORT_ONLY", "NEUTRAL_ALL", "NEUTRAL_RANGE", "DEFENSIVE_HOLD", "REDUCE_ONLY", "NO_TRADE"] = "NEUTRAL_ALL"
    SPX: Literal["LONG_ONLY", "SHORT_ONLY", "NEUTRAL_ALL", "NEUTRAL_RANGE", "DEFENSIVE_HOLD", "REDUCE_ONLY", "NO_TRADE"] = "NEUTRAL_RANGE"


class MacroStrategistOutput(BaseModel):
    """Ajan 3: Baş Makro Stratejist sentezi. Execution gates are advisory, not authoritative."""
    primary_regime: str
    asset_biases: AssetBiases
    volatility_risk_score: float = Field(ge=0.0, le=1.0)
    capital_preservation_mode: bool = False
    btc_decoupling_active: bool = False
    hysteresis_active: bool = False
    recommended_risk_multiplier: float = Field(default=1.0, ge=0.1, le=1.0)
    execution_bias_gates: ExecutionGates = Field(
        description="LLM advisory output only; deterministic_metrics_only gate layer overrides this field."
    )
    macro_rationale: str
    horizon_today: str = ""
    horizon_this_week: str = ""
    horizon_this_month: str = ""
    timestamp: Optional[str] = None
