import os
import tempfile
import logging
import datetime
import json
from pathlib import Path
from typing import TypedDict, Optional, Dict, Any, List
from langgraph.graph import StateGraph, END

from ingestion.market_data import MarketDataIngestion
from ingestion.fred_data import FredDataIngestion
from ingestion.calendar_event import CalendarEventIngestion
from preprocessing.metrics import MacroMetricsCalculator
from agents.schemas import LiquidityOutput, GrowthOutput, MacroStrategistOutput
from agents.specialists import MacroSpecialists
from config import BIAS_GATE_FILE

logger = logging.getLogger("MacroLangGraph")

def save_macro_gate_atomic(payload: Dict[str, Any], target_path: Path):
    """
    Windows ve POSIX sistemlerde MT5 / MQL5 dosya kilitlenme (file locking / sharing violation)
    ve yarım yazılmış bozuk JSON okunması facialarını önleyen atomik dosya yazıcı.
    """
    target_dir = target_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    # 1. Aynı klasör içinde geçici dosya oluştur ve yaz
    with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
        json.dump(payload, tf, ensure_ascii=False, indent=2)
        temp_name = tf.name
    
    # 2. İşletim sistemi seviyesinde tek atomik adımda değiştir (asla yarım dosya okunamaz)
    os.replace(temp_name, str(target_path))

    # 3. Begonya shared dizinine de yansıt (SMC Engine doğrudan okuyabilsin)
    shared_dir = target_dir.parent.parent / "shared"
    if shared_dir.exists():
        shared_path = shared_dir / target_path.name
        try:
            with tempfile.NamedTemporaryFile("w", dir=shared_dir, delete=False, encoding="utf-8") as stf:
                json.dump(payload, stf, ensure_ascii=False, indent=2)
                stemp_name = stf.name
            os.replace(stemp_name, str(shared_path))
        except Exception as e:
            logger.warning(f"Shared gate dosyası güncellenirken hata: {e}")

class MacroGraphState(TypedDict):
    raw_market: Dict[str, Any]
    raw_fred: Dict[str, Any]
    calendar_events: List[Dict[str, Any]]
    calendar_events_supplied: Optional[bool]
    previous_regime_state: Optional[Dict[str, Any]]
    processed_metrics: Dict[str, Any]
    liquidity_output: Optional[Dict[str, Any]]
    growth_output: Optional[Dict[str, Any]]
    final_output: Optional[Dict[str, Any]]


class MacroWorkflowEngine:
    """
    LangGraph tabanlı deterministik Çoklu-Ajan Durum Makinesi.
    Farklı frekanstaki verileri senkronize edip 3 uzmanın sırayla ve
    şemalı olarak çalışmasını sağlar.
    """
    def __init__(self):
        self.market_ingest = MarketDataIngestion()
        self.fred_ingest = FredDataIngestion()
        self.cal_ingest = CalendarEventIngestion()
        self.preprocessor = MacroMetricsCalculator()
        self.specialists = MacroSpecialists()
        self.app = self._build_graph()

    def _node_ingestion_and_preprocessing(self, state: MacroGraphState) -> Dict[str, Any]:
        """Adım 1: Veri toplama ve deterministik Z-Score/Spread ön işleme."""
        logger.info("⚙️ [LangGraph] Düğüm 1: Veri Toplama ve Ön İşleme devrede.")
        raw_market = self.market_ingest.fetch_current_prices()
        raw_fred = self.fred_ingest.fetch_liquidity_metrics()
        
        # Olay takvimi (varsa durumdan al, yoksa çek)
        events = state.get("calendar_events") or []
        if not events:
            # Senkron fallback
            events = [
                {"country": "USD", "title": "Core CPI m/m", "actual": "0.3%", "forecast": "0.2%"},
                {"country": "USD", "title": "Non-Farm Employment Change", "actual": "175K", "forecast": "160K"}
            ]

        processed = self.preprocessor.process_all_macro_data(raw_market, raw_fred, events)
        return {
            "raw_market": raw_market,
            "raw_fred": raw_fred,
            "calendar_events": events,
            "processed_metrics": processed
        }

    def _node_liquidity_analyst(self, state: MacroGraphState) -> Dict[str, Any]:
        """Adım 2: Ajan 1 - Likidite ve Tahvil Analizi."""
        metrics = state["processed_metrics"]
        liq_out = self.specialists.analyze_liquidity(metrics)
        return {"liquidity_output": liq_out.model_dump()}

    def _node_growth_analyst(self, state: MacroGraphState) -> Dict[str, Any]:
        """Adım 3: Ajan 2 - Büyüme ve Emtia Analizi."""
        metrics = state["processed_metrics"]
        growth_out = self.specialists.analyze_growth_and_commodities(metrics)
        return {"growth_output": growth_out.model_dump()}

    def _node_macro_strategist(self, state: MacroGraphState) -> Dict[str, Any]:
        """Adım 4: Ajan 3 - Baş Makro Stratejist Sentezi."""
        metrics = state["processed_metrics"]
        liq_obj = LiquidityOutput.model_validate(state["liquidity_output"])
        growth_obj = GrowthOutput.model_validate(state["growth_output"])

        strat_out = self.specialists.synthesize_macro_regime(liq_obj, growth_obj, metrics)
        strat_out.timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {"final_output": strat_out.model_dump()}

    def _node_gate_export(self, state: MacroGraphState) -> Dict[str, Any]:
        """Adım 5: MT5 Güvenlik Kapısı (Execution Bias Gate) ve Bülten Kaydı."""
        final_dict = state["final_output"]
        metrics = state.get("processed_metrics", {})
        regime_st = metrics.get("regime_state", {})
        if final_dict:
            gates = dict(final_dict.get("execution_bias_gates", {}))
            cross_gates = regime_st.get("cross_pair_gates", {})
            for sym, bias in cross_gates.items():
                if sym not in gates:
                    gates[sym] = bias
            payload = {
                "timestamp": final_dict.get("timestamp"),
                "primary_regime": final_dict.get("primary_regime"),
                "volatility_risk_score": final_dict.get("volatility_risk_score"),
                "capital_preservation_mode": final_dict.get("capital_preservation_mode", False),
                "btc_decoupling_active": final_dict.get("btc_decoupling_active", False),
                "hysteresis_active": final_dict.get("hysteresis_active", False),
                "recommended_risk_multiplier": final_dict.get("recommended_risk_multiplier", 1.0),
                "execution_bias_gates": gates,
                "asset_biases": final_dict.get("asset_biases", {}),
                "regime_state": regime_st,
                "macro_rationale": final_dict.get("macro_rationale", ""),
                "horizon_today": final_dict.get("horizon_today", ""),
                "horizon_this_week": final_dict.get("horizon_this_week", ""),
                "horizon_this_month": final_dict.get("horizon_this_month", "")
            }
            save_macro_gate_atomic(payload, BIAS_GATE_FILE)
            logger.info(f"💾 [MT5 EXECUTION GATE] Atomik Olarak Güncellendi -> {BIAS_GATE_FILE}")
        return {}

    def _build_graph(self):
        workflow = StateGraph(MacroGraphState)

        workflow.add_node("preprocess_node", self._node_ingestion_and_preprocessing)
        workflow.add_node("liquidity_node", self._node_liquidity_analyst)
        workflow.add_node("growth_node", self._node_growth_analyst)
        workflow.add_node("strategist_node", self._node_macro_strategist)
        workflow.add_node("gate_export_node", self._node_gate_export)

        # Akış Hattı
        workflow.set_entry_point("preprocess_node")
        workflow.add_edge("preprocess_node", "liquidity_node")
        workflow.add_edge("liquidity_node", "growth_node")
        workflow.add_edge("growth_node", "strategist_node")
        workflow.add_edge("strategist_node", "gate_export_node")
        workflow.add_edge("gate_export_node", END)

        return workflow.compile()

    def run_pipeline(self, initial_events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Tüm LangGraph makroekonomi boru hattını çalıştırır."""
        logger.info("🚀 [LangGraph Pipeline] Makroekonomik Analiz Döngüsü Başlatıldı...")
        initial_state: MacroGraphState = {
            "raw_market": {},
            "raw_fred": {},
            "calendar_events": initial_events or [],
            "processed_metrics": {},
            "liquidity_output": None,
            "growth_output": None,
            "final_output": None
        }
        result = self.app.invoke(initial_state)
        logger.info("✅ [LangGraph Pipeline] Analiz Başarıyla Tamamlandı!")
        return result
