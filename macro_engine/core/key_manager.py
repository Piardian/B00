import os
import time
import logging
import threading
from typing import List, Dict, Tuple, Optional, Type, Any
from pydantic import BaseModel
from google import genai
from google.genai import types

from config import GEMINI_KEYS, STRATEGIST_CASCADE, ANALYST_CASCADE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DualCascadeRouter")


class DualCascadeRouter:
    """
    4 API Anahtarı ve Kademeli Model Hiyerarşisini (Dual-Cascade) yöneten
    kesintisiz LLM Yürütme ve Yönlendirme Motoru.
    
    Hiyerarşi:
    - Baş Stratejist: Gemini 3.8 Flash -> 3.7 Flash -> 3.6 Flash -> 3.5 Flash -> 2.5 Flash
    - Analist Ajanlar: Gemini 3.8 Flash Lite -> 3.5 Flash Lite -> 3.1 Flash Lite -> 2.5 Flash
    - Kota dolduğunda sıradaki modele geçer.
    - Anahtar tükendiğinde sıradaki anahtara geçip hiyerarşiyi (3.8) baştan başlatır.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DualCascadeRouter, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.keys: List[str] = [k for k in GEMINI_KEYS if k and len(k) > 10]
        if not self.keys:
            raise ValueError("Geçerli hiçbir Google Gemini API anahtarı bulunamadı!")

        self.current_key_idx = 0
        self.exhausted_pairs: Dict[Tuple[str, str], float] = {}
        self.cooldown_seconds = 180  # 3 dakika sonra kota geçici olarak sıfırlanabilir
        self._initialized = True
        logger.info(f"DualCascadeRouter başlatıldı: {len(self.keys)} API Anahtarı devrede.")

    def _get_active_key(self) -> str:
        return self.keys[self.current_key_idx]

    def _rotate_key(self) -> str:
        with self._lock:
            prev_idx = self.current_key_idx
            self.current_key_idx = (self.current_key_idx + 1) % len(self.keys)
            logger.warning(
                f"🔄 [ANAHTAR ROTASYONU] Anahtar {prev_idx + 1} kotası doldu! "
                f"-> Sıradaki Anahtar {self.current_key_idx + 1} devreye alındı. Model hiyerarşisi (3.8) sıfırlandı."
            )
            return self.keys[self.current_key_idx]

    def _is_exhausted(self, key: str, model: str) -> bool:
        pair = (key, model)
        if pair in self.exhausted_pairs:
            if time.time() - self.exhausted_pairs[pair] < self.cooldown_seconds:
                return True
            else:
                del self.exhausted_pairs[pair]
        return False

    def _mark_exhausted(self, key: str, model: str):
        self.exhausted_pairs[(key, model)] = time.time()
        logger.warning(f"⚠️ [KOTA AŞIMI] Model '{model}' (Anahtar {self.keys.index(key) + 1}) kotası doldu.")

    def get_cascade_for_role(self, role: str) -> List[str]:
        if role.lower() in ["strategist", "chief", "master", "architect"]:
            return STRATEGIST_CASCADE
        return ANALYST_CASCADE

    def execute_structured(
        self,
        role: str,
        prompt: str,
        schema: Type[BaseModel],
        system_instruction: Optional[str] = None
    ) -> BaseModel:
        """
        Rol için belirlenmiş model kademesi ve 4 API anahtarı arasında
        otomatik geçiş yaparak garantili Pydantic çıktısı üretir.
        """
        models = self.get_cascade_for_role(role)
        attempts_across_keys = 0
        max_key_attempts = len(self.keys) * 2

        while attempts_across_keys < max_key_attempts:
            active_key = self._get_active_key()

            # Mevcut anahtar üzerinde modelleri sırayla dene (3.8 -> 3.7 -> 3.6 ...)
            for model_name in models:
                if self._is_exhausted(active_key, model_name):
                    continue

                try:
                    logger.info(
                        f"🤖 [LLM İSTEĞİ] Rol: {role} | Model: {model_name} | "
                        f"Anahtar: #{self.current_key_idx + 1}"
                    )
                    
                    client = genai.Client(
                        api_key=active_key,
                        http_options=types.HttpOptions(timeout=25000)
                    )
                    thinking_cfg = None
                    if "lite" not in model_name.lower() and any(m in model_name for m in ["3.8", "3.7", "3.6"]):
                        thinking_cfg = types.ThinkingConfig(thinking_budget=0)

                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=schema,
                        thinking_config=thinking_cfg
                    )
                    
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config
                    )

                    if response and response.text:
                        parsed_obj = schema.model_validate_json(response.text)
                        return parsed_obj

                except Exception as e:
                    err_str = str(e).lower()
                    is_rate_limit = any(term in err_str for term in [
                        "429", "resource_exhausted", "quota", "rate limit", "overloaded",
                        "not found", "503", "unavailable", "demand"
                    ])

                    if is_rate_limit:
                        self._mark_exhausted(active_key, model_name)
                        logger.info(f"➡️ Sıradaki modele geçiliyor... ({model_name} geçici olarak müsait değil)")
                        continue
                    else:
                        logger.error(f"Beklenmeyen API hatası ({model_name}): {e}")
                        continue

            # Bu anahtar için tüm modeller tükendiyse bir sonraki anahtara geç
            self._rotate_key()
            attempts_across_keys += 1

        raise RuntimeError("Tüm 4 API Anahtarı ve model hiyerarşisi tükendi! Lütfen kotanın yenilenmesini bekleyin.")
