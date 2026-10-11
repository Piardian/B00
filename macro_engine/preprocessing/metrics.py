from __future__ import annotations
import datetime as dt, json, tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from config import BIAS_GATE_FILE
from core.deterministic_controls import event_freeze_status, normalize_calendar_event, signed_surprise_zscore, validate_freshness, validate_numeric_range
from data_quality import (
    DataUnavailableError,
    RELATIVE_VALUE_MARKET_FIELDS,
    REQUIRED_MARKET_FIELDS,
    validate_fred_payload,
    validate_market_payload,
)
from preprocessing.metrics_legacy import MacroMetricsCalculator as _LegacyMacroMetricsCalculator

@contextmanager
def _fixed_legacy_date(as_of_date: Optional[dt.date], as_of_datetime: Optional[dt.datetime]=None, state: Optional[Mapping[str,Any]]=None):
    legacy=__import__("preprocessing.metrics_legacy",fromlist=["datetime"]); od,ot,og=legacy.datetime.date,legacy.datetime.datetime,legacy.BIAS_GATE_FILE
    d=as_of_date or (as_of_datetime.date() if as_of_datetime else dt.date.today()); t=as_of_datetime or dt.datetime.combine(d,dt.time.min,tzinfo=dt.timezone.utc)
    class FD(od):
        @classmethod
        def today(cls): return d
    class FDT(ot):
        @classmethod
        def now(cls,tz=None): return t.astimezone(tz) if tz else t.replace(tzinfo=None)
    temp=None
    try:
        if state is not None:
            temp=tempfile.TemporaryDirectory(prefix="begonya_macro_state_"); p=Path(temp.name)/"previous_regime_state.json"; p.write_text(json.dumps({"regime_state":dict(state)})); legacy.BIAS_GATE_FILE=p
        else: legacy.BIAS_GATE_FILE=BIAS_GATE_FILE
        legacy.datetime.date=FD; legacy.datetime.datetime=FDT; yield
    finally:
        legacy.datetime.date=od; legacy.datetime.datetime=ot; legacy.BIAS_GATE_FILE=og
        if temp: temp.cleanup()

class MacroMetricsCalculator(_LegacyMacroMetricsCalculator):
    DEFAULT_SURPRISE_SIGMAS={"cpi":.12,"core_cpi":.10,"nfp":50000.,"unemployment":.15,"pmi":1.5,"gdp":.50,"retail_sales":.40,"generic":1.0}
    # WTREGEN is FRED's weekly, Wednesday-ending Treasury General Account
    # series. Treating it as daily incorrectly rejects legitimate 5-7 day gaps
    # between observations. Keep the weekly freshness contract explicit.
    FRED_FREQUENCIES={"WALCL":"weekly","RRPONTSYD":"daily","WTREGEN":"weekly","T10YIE":"daily","DFII10":"weekly","DFF":"daily","BAMLH0A0HYM2":"daily","NFCI":"weekly","ICSA":"weekly","M2SL":"monthly","DE10Y":"monthly","EA_HICP_YOY":"monthly","ECB_DEPOSIT_RATE":"daily"}
    # NFCI is weekly-ending-Friday but the provider vintage can lag the observation date.
    # M2SL is monthly, but the H.6 release schedule can leave the latest observation ~2 months old
    # at month-start. Keep the generic monthly contract at 45d and allow only this series to 75d.
    FRED_MAX_AGE_DAYS={"NFCI":14,"M2SL":75,"DE10Y":75,"EA_HICP_YOY":75}
    # Monthly M2 and OECD DE10Y ages are observation-date age, not publication-date age.
    # These series stay explicitly research-only until release timestamps/vintages are available.
    def __init__(self,as_of_date:Optional[dt.date]=None,surprise_sigmas:Optional[Mapping[str,float]]=None): super().__init__(); self.as_of_date=as_of_date; self.surprise_sigmas=dict(surprise_sigmas or self.DEFAULT_SURPRISE_SIGMAS)
    @classmethod
    def from_calibration_profile(cls,profile_path:Optional[Path]=None,allow_default_fallback:bool=False,**kwargs:Any):
        p=profile_path or Path(__file__).resolve().parent.parent/"calibration"/"surprise_sigma_profile.json"
        if not p.exists():
            if allow_default_fallback:return cls(**kwargs)
            raise DataUnavailableError(f"Calibration profile unavailable: {p}")
        from calibration.surprise_sigma import load_calibration_profile
        return cls(surprise_sigmas=load_calibration_profile(p),**kwargs)
    def calculate_surprise_zscore(self,indicator_type:str,actual:float,forecast:float)->float:
        s=float(self.surprise_sigmas.get(indicator_type.lower(),self.surprise_sigmas.get("generic",1.0)))
        if indicator_type.lower()=="nfp" and max(abs(float(actual)),abs(float(forecast)))<10000:s/=1000
        return signed_surprise_zscore(indicator_type,actual,forecast,s)
    @staticmethod
    def calculate_real_yield(us10y:float,dfii10_tips:Optional[float]=None,breakeven_10y:Optional[float]=None)->Dict[str,Any]:
        if dfii10_tips is not None:y,src=round(dfii10_tips,3),"FRED DFII10 (Doğrudan 10Y TIPS Reel Getirisi)"
        else:
            if breakeven_10y is None:raise ValueError("DFII10 unavailable and no breakeven fallback supplied")
            y,src=round(us10y-breakeven_10y,3),f"Sentetik (US10Y {us10y}% - Breakeven {breakeven_10y}%)"
        p="High Fırsat Maliyeti (Reel Faiz >= %1.90; Yeni Long Kısıtlanır)" if y>=1.9 else "Low (Destekleyici; Negatif/Düşük Reel Faiz)" if y<1 else "Moderate (Dengeli)"
        return {"real_yield_pct":y,"yield_source":src,"pressure_on_gold":p,"description":f"10Y Reel Getiri: %{y} [{src}] (Altın baskısı: {p})"}
    @staticmethod
    def calculate_fed_forward_path(us02y:float,dff:Optional[float],us02y_5d:Optional[float]=None)->Dict[str,Any]:
        if dff is None:
            raise DataUnavailableError(
                "DFF is required for policy-path analysis; static policy-rate fallback is disabled."
            )
        gap=round((us02y-dff)*100,1)
        return {
            "fed_policy_rate_pct":round(dff,3),
            "fed_policy_rate_source":"FRED DFF",
            "us02y_yield":us02y,
            "implied_rate_gap_bps":gap,
            "delta_02y_5d_bps":None if us02y_5d is None else round((us02y-us02y_5d)*100,1),
            "rate_expectation_signal":"Market-implied easing" if gap<=-25 else "Market-implied tightening" if gap>=25 else "Near-policy / neutral pricing",
            "interpretation_warning":"US02Y-DFF is a market-vs-current-policy spread; it is not a meeting-count or guaranteed total rate-cut estimate.",
        }
    @staticmethod
    def _validate_key_ranges(market_data:Dict[str,Any],fred_data:Dict[str,Any])->None:
        for n,lo,hi in [("DXY",0,500),("GOLD",0,10000),("BRENT",0,500),("US10Y",-5,20),("US02Y",-5,20),("BTC",0,2000000),("COPPER",0,20),("VIX",0,200),("HYG",0,200),("LQD",0,300)]:
            x=market_data.get(n)
            if isinstance(x,dict) and x.get("value") is not None:validate_numeric_range(n,x["value"],lo,hi)
        for n,lo,hi in [("T10YIE",-10,20),("DFII10",-10,20),("DFF",0,20),("BAMLH0A0HYM2",0,50),("NFCI",-10,10),("ICSA",0,10000)]:
            if n in fred_data and fred_data[n] is not None:validate_numeric_range(n,fred_data[n],lo,hi)
    def _validate_fred_freshness(self,fred_data:Dict[str,Any],as_of:Optional[dt.date])->Dict[str,int]:
        if as_of is None:return {}
        obs=fred_data.get("data_quality",{}).get("observation_dates",{});return {f:validate_freshness(f,dt.date.fromisoformat(str(v)),as_of,self.FRED_FREQUENCIES.get(f,"unknown"),self.FRED_MAX_AGE_DAYS.get(f)) for f,v in obs.items()}
    def process_all_macro_data(self,market_data:Dict[str,Any],fred_data:Dict[str,Any],calendar_events:List[Dict[str,Any]],as_of_date:Optional[dt.date]=None,as_of_datetime:Optional[dt.datetime]=None,previous_regime_state:Optional[Mapping[str,Any]]=None,now_utc:Optional[dt.datetime]=None)->Dict[str,Any]:
        core_market_fields = set(REQUIRED_MARKET_FIELDS)
        missing_market = sorted(name for name in core_market_fields if name not in market_data)
        if missing_market:
            raise DataUnavailableError(
                "Core market inputs unavailable: " + ", ".join(missing_market)
            )

        core_fred_fields = {
            "WALCL", "WALCL_4W_AGO", "RRPONTSYD", "RRPONTSYD_4W_AGO",
            "WTREGEN", "WTREGEN_4W_AGO", "T10YIE", "DFII10", "DFF",
            "BAMLH0A0HYM2", "NFCI", "ICSA", "DE10Y", "DE10Y_4W_AGO",
        }
        missing_fred = sorted(name for name in core_fred_fields if name not in fred_data)
        if missing_fred:
            raise DataUnavailableError(
                "Core FRED inputs unavailable: " + ", ".join(missing_fred)
            )

        validate_market_payload(market_data, required_fields=core_market_fields)
        validate_fred_payload(fred_data)
        self._validate_key_ranges(market_data, fred_data)

        fred_provider = fred_data.get("data_quality", {}).get("provider")
        if fred_provider == "FRED_BASELINE":
            raise DataUnavailableError(
                "Non-authoritative FRED_BASELINE data cannot drive a production macro analysis."
            )

        as_of = as_of_date or self.as_of_date
        fresh = self._validate_fred_freshness(fred_data, as_of)
        ed = as_of_datetime or (
            dt.datetime.combine(as_of, dt.time.max, tzinfo=dt.timezone.utc)
            if as_of else None
        )
        events = [normalize_calendar_event(e) for e in calendar_events]
        freeze = event_freeze_status(events, now_utc=now_utc or ed) if (now_utc or ed) else None

        with _fixed_legacy_date(as_of, ed, previous_regime_state):
            r = super().process_all_macro_data(market_data, fred_data, events)

        if freeze is not None:
            r.setdefault("cross_pairs_analysis", {})["event_freeze"] = freeze
            r.setdefault("regime_state", {})["event_freeze_active"] = bool(freeze["active"])

        r["fed_forward_path_analysis"] = self.calculate_fed_forward_path(
            float(
                r.get("fed_forward_path_analysis", {}).get(
                    "us02y_yield", market_data["US02Y"]["value"]
                )
            ),
            fred_data.get("DFF"),
            market_data["US02Y"].get("val_5d_ago"),
        )

        # The 2Y-DFF gap is a policy-rate/yield spread, not a literal count of
        # expected FOMC cuts. Keep the distinction explicit in downstream text.
        fed_path = r["fed_forward_path_analysis"]
        gap = fed_path.get("implied_rate_gap_bps")
        fed_path["interpretation_warning"] = (
            "US02Y-DFF is a market-vs-current-policy spread; it is not a "
            "meeting-count or guaranteed total rate-cut estimate."
        )
        fed_path["implication"] = (
            f"US02Y-DFF farkı {gap:+.1f} bps; bu, piyasanın 2Y getirisi ile mevcut "
            "politika faizi arasındaki mesafeyi gösterir. Tek başına toplam faiz "
            "indirimi miktarı olarak yorumlanmaz."
            if isinstance(gap, (int, float))
            else "US02Y-DFF farkı hesaplanamadı; politika patikası güvenilir biçimde çıkarılamıyor."
        )

        # Do not let missing/failed relative-value feeds silently fall back to
        # legacy constants. Without the sovereign-yield panel, cross-pair
        # direction is not established.
        missing_relative_value = sorted(
            name for name in RELATIVE_VALUE_MARKET_FIELDS
            if not isinstance(market_data.get(name), dict)
            or market_data.get(name, {}).get("value") is None
            or market_data.get(name, {}).get("fallback_used")
        )
        if missing_relative_value:
            cross = r.setdefault("cross_pairs_analysis", {})
            pair_required_sovereigns = {
                "AUDCAD": ("AU02Y", "CA02Y"),
                "CADJPY": ("CA02Y",),
                "GBPJPY": ("GB02Y",),
                "AUDJPY": ("AU02Y",),
                "EURGBP": ("DE02Y", "GB02Y"),
                "EURAUD": ("DE02Y", "AU02Y"),
                "NZDCAD": ("NZ02Y", "CA02Y"),
                "EURJPY": ("DE02Y",),
                "USDCAD": ("CA02Y",),
                "USDJPY": (),
                "GBPUSD": ("GB02Y",),
                "AUDUSD": ("AU02Y",),
                "NZDUSD": ("NZ02Y",),
                "USDCHF": (),
                "EURCHF": ("DE02Y",),
                "GBPCHF": ("GB02Y",),
                "AUDCHF": ("AU02Y",),
                "CADCHF": ("CA02Y",),
                "NZDCHF": ("NZ02Y",),
                "CHFJPY": (),
            }
            # If ALL relative-value fields are missing, fail completely to neutral range
            all_missing = len(missing_relative_value) >= len(RELATIVE_VALUE_MARKET_FIELDS)
            existing_gates = dict(cross.get("cross_gates", {}) or {})
            
            for pair, req_sovs in pair_required_sovereigns.items():
                if all_missing or any(sov in missing_relative_value for sov in req_sovs):
                    existing_gates[pair] = "NEUTRAL_RANGE"
            
            cross["cross_gates"] = existing_gates
            
            if all_missing:
                cross["sovereign_yields"] = {
                    key: None
                    for key in ("US02Y", "CA02Y", "DE02Y", "GB02Y", "AU02Y", "NZ02Y")
                }
                cross["yield_spreads_bps"] = {}
                cross["currency_scores"] = {
                    currency: 0
                    for currency in ("AUD", "CAD", "NZD", "JPY", "EUR", "GBP", "USD", "CHF")
                }
                cross["currency_breakdown"] = {
                    currency: {
                        "score": 0,
                        "summary": "UNAVAILABLE: relative-value input missing",
                    }
                    for currency in ("AUD", "CAD", "NZD", "JPY", "EUR", "GBP", "USD", "CHF")
                }
                cross["data_quality"] = {
                    "status": "UNAVAILABLE",
                    "missing_fields": missing_relative_value,
                    "directional_gates_disabled": True,
                    "methodology_warning": (
                        "Relative-value market inputs are missing or fallback-derived; "
                        "no directional FX cross-pair gate is emitted."
                    ),
                }
            else:
                cross["data_quality"] = {
                    "status": "PARTIAL",
                    "missing_fields": missing_relative_value,
                    "directional_gates_disabled": False,
                    "methodology_warning": (
                        f"Partial relative-value inputs available. Missing: {', '.join(missing_relative_value)}. "
                        "Affected currency pairs are set to NEUTRAL_RANGE."
                    ),
                }

            r.setdefault("regime_state", {})["cross_pair_gates"] = dict(cross["cross_gates"])
            r["regime_state"]["cross_currency_scores"] = dict(cross.get("currency_scores", {}))
            r["regime_state"]["cross_currency_breakdown"] = dict(cross.get("currency_breakdown", {}))

        curve_consistency = {}
        source_pairs = (
            ("US02Y", "DGS2"),
            ("US10Y", "DGS10"),
        )
        for market_symbol, fred_symbol in source_pairs:
            market_value = market_data.get(market_symbol, {}).get("value")
            fred_value = fred_data.get(fred_symbol)
            if isinstance(market_value, (int, float)) and isinstance(fred_value, (int, float)):
                delta_bps = round((float(market_value) - float(fred_value)) * 100.0, 1)
                curve_consistency[market_symbol] = {
                    "market_value_pct": float(market_value),
                    "fred_value_pct": float(fred_value),
                    "difference_bps": delta_bps,
                    "status": "ALIGNED" if abs(delta_bps) <= 10.0 else "DIVERGENT",
                }
            else:
                curve_consistency[market_symbol] = {
                    "market_value_pct": market_value,
                    "fred_value_pct": fred_value,
                    "difference_bps": None,
                    "status": "UNAVAILABLE",
                }

        market_price_context = {}
        for symbol in (
            "GOLD", "BTC", "DXY", "BRENT", "SPX", "US10Y", "US02Y", "VIX"
        ):
            data = market_data.get(symbol)
            if not isinstance(data, dict) or data.get("value") is None:
                continue
            market_price_context[symbol] = {
                "value": data.get("value"),
                "prev": data.get("prev"),
                "val_5d_ago": data.get("val_5d_ago"),
                "month_ago": data.get("month_ago"),
                "change_pct": data.get("change_pct"),
                "change_pct_5d": data.get("change_pct_5d"),
                "change_pct_4w": data.get("change_pct_4w"),
                "source": data.get("source"),
                "fallback_used": bool(data.get("fallback_used")),
            }
        r["market_price_context"] = market_price_context
        r["market_source_consistency"] = {
            "treasury_curve": curve_consistency,
            "warning": (
                "Broker/market yield and FRED yield differ materially."
                if any(item.get("status") == "DIVERGENT" for item in curve_consistency.values())
                else None
            ),
        }
        r.setdefault("regime_state", {})["state_source"] = (
            "explicit_previous_regime_state"
            if previous_regime_state is not None
            else "default_inactive_state"
        )
        r["dxy_oil_correlation_method"] = "pearson_on_period_returns"

        # Replace static labor fallbacks with the authoritative FRED unemployment
        # rate and (when available) the actual calendar NFP release.
        unemp_rate = fred_data.get("UNRATE")
        nfp_actual = next(
            (
                float(item.get("actual"))
                for item in r.get("surprises", [])
                if item.get("indicator_type") == "nfp"
                and isinstance(item.get("actual"), (int, float))
            ),
            None,
        )
        payroll_change_k = fred_data.get("PAYEMS_MOM_CHANGE_K")
        if nfp_actual is not None and abs(nfp_actual) >= 10000:
            nfp_actual = nfp_actual / 1000.0
        claims_k = fred_data.get("ICSA")
        labor_strong = (
            isinstance(unemp_rate, (int, float))
            and isinstance(claims_k, (int, float))
            and float(unemp_rate) <= 4.3
            and float(claims_k) <= 240.0
        )
        ratio_delta = r.get("copper_gold_analysis", {}).get("delta_4w_pct")
        global_cycle = (
            "Manufacturing / cyclical momentum strengthening"
            if isinstance(ratio_delta, (int, float)) and ratio_delta > 2.0
            else "Manufacturing / cyclical momentum weakening"
            if isinstance(ratio_delta, (int, float)) and ratio_delta < -2.0
            else "Mixed / range-bound cyclical momentum"
        )
        brent_level = market_data.get("BRENT", {}).get("value")
        regime_diagnosis = "UNAVAILABLE"
        if labor_strong and isinstance(brent_level, (int, float)):
            regime_diagnosis = (
                "Late-Cycle Overheating with Global Divergence"
                if float(brent_level) >= 80.0 and global_cycle != "Manufacturing / cyclical momentum strengthening"
                else "Reflationary Growth"
            )
        elif not labor_strong and isinstance(brent_level, (int, float)) and float(brent_level) >= 80.0:
            regime_diagnosis = "Stagflation"
        elif not labor_strong:
            regime_diagnosis = "Deflationary Slowdown"

        r["cycle_diagnosis"] = {
            **r.get("cycle_diagnosis", {}),
            "unemployment_rate": None if unemp_rate is None else float(unemp_rate),
            "nfp_value": nfp_actual,
            "nfp_source": "calendar_surprise" if nfp_actual is not None else "UNAVAILABLE",
            "payroll_change_mom_k": (
                None if payroll_change_k is None else float(payroll_change_k)
            ),
            "icsa_claims": None if claims_k is None else float(claims_k),
            "is_labor_strong": labor_strong,
            "us_domestic_cycle": (
                "Late-Cycle Domestic Resilience"
                if labor_strong
                else "Labor-market cooling / weakening"
            ),
            "global_macro_cycle": global_cycle,
            "regime_diagnosis": regime_diagnosis,
            "rationale": (
                f"UNRATE={unemp_rate}, ICSA={claims_k}K; "
                f"PAYEMS MoM change={payroll_change_k}K; "
                f"cyclical momentum={global_cycle}."
            ),
        }

        real_yield_value = r.get("real_yield_info", {}).get("real_yield_pct")
        hy_oas_value = r.get("credit_spread_analysis", {}).get("hy_oas_spread_pct")
        policy_gap_bps = r["fed_forward_path_analysis"].get("implied_rate_gap_bps")
        repricing = r["fed_forward_path_analysis"].get(
            "repricing_direction", "Unavailable"
        )
        rate_path_expectation = (
            "Market-implied easing"
            if policy_gap_bps is not None and policy_gap_bps <= -25
            else "Market-implied tightening"
            if policy_gap_bps is not None and policy_gap_bps >= 25
            else repricing
        )
        equity_constraint = (
            f"Reel getiri %{float(real_yield_value):.2f} ise iskonto baskısı anlamlı."
            if isinstance(real_yield_value, (int, float)) and real_yield_value >= 1.90
            else f"Reel getiri %{float(real_yield_value):.2f}; reel faiz kaynaklı baskı daha sınırlı."
            if isinstance(real_yield_value, (int, float))
            else "Reel getiri verisi kullanılamıyor."
        )
        credit_context = (
            f"HY OAS %{float(hy_oas_value):.2f}."
            if isinstance(hy_oas_value, (int, float))
            else "HY OAS verisi kullanılamıyor."
        )

        r["fed_reaction_function"] = {
            "rate_path_expectation": rate_path_expectation,
            "policy_gap_bps": policy_gap_bps,
            "driver": (
                f"UNRATE={unemp_rate}, ICSA={claims_k}K, "
                f"PAYEMS MoM change={payroll_change_k}K; "
                f"DFF={fred_data.get('DFF')}, US02Y={market_data.get('US02Y', {}).get('value')}; "
                f"Brent={brent_level}."
            ),
            "equity_multiple_cap": (
                f"{equity_constraint} {credit_context} "
                "Bu panel yalnızca iskonto/kredi koşullarını tanımlar; tek başına hisse yön sinyali üretmez."
            ),
        }

        market_fallback_fields = sorted(
            name for name, data in market_data.items()
            if isinstance(data, dict) and data.get("fallback_used")
        )
        fallback_fields = ["DFF"] if "DFF" not in fred_data else []
        r["data_quality"] = {
            "fallback_used": bool(fallback_fields or market_fallback_fields),
            "synthetic_fallback_used": bool(fallback_fields or market_fallback_fields),
            "fallback_fields": fallback_fields + market_fallback_fields,
            "fred_provider": fred_provider or "UNSPECIFIED",
            "authoritative": not bool(fallback_fields or market_fallback_fields),
        }
        r["validation"] = {"fred_freshness_days": fresh}

        if float(market_data.get("VIX", {}).get("value", 0) or 0) >= 40 and isinstance(
            r.get("credit_spread_analysis"), dict
        ):
            stress = str(r["credit_spread_analysis"].get("stress_level", "")).lower()
            if "distress" in stress or "şiddetli kredi krizi" in stress:
                r.setdefault("gold_fiscal_dominance", {})["is_cash_dash"] = True
                r["gold_fiscal_dominance"]["gold_short_allowed"] = True

        return r
