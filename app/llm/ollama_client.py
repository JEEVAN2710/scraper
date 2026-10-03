"""Ollama LLM Provider implementation for local CPU-friendly inference."""

import logging
from typing import Any, Dict, Optional
import httpx

from app.config.settings import Settings, get_settings
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Local Ollama client communicating via Ollama's REST API."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = self.settings.OLLAMA_MODEL
        self.timeout = self.settings.OLLAMA_TIMEOUT

    def get_model_name(self) -> str:
        """Return the active model name."""
        return self.model

    def check_availability(self) -> Dict[str, Any]:
        """Check if the local Ollama server is running and check pulled models."""
        url = f"{self.base_url}/api/tags"
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    is_loaded = any(self.model in m for m in models)
                    return {
                        "available": True,
                        "base_url": self.base_url,
                        "target_model": self.model,
                        "model_pulled": is_loaded,
                        "installed_models": models,
                    }
                return {
                    "available": False,
                    "error": f"Ollama HTTP status {res.status_code}",
                    "target_model": self.model,
                }
        except Exception as exc:
            logger.debug("Ollama is not currently responding at %s: %s", self.base_url, exc)
            return {
                "available": False,
                "error": str(exc),
                "target_model": self.model,
                "instruction": f"Run 'ollama run {self.model}' in your terminal to start Ollama locally.",
            }

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Send prompt to Ollama's /api/generate endpoint with low temperature for factual precision."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.15,  # Low-hallucination, natural humanized tone
                "num_predict": 200,   # Optimal length for concise executive synthesis on CPU
                "num_thread": 4,      # Multi-threaded CPU inference
            },
        }
        if system:
            payload["system"] = system

        try:
            req_timeout = max(float(self.timeout), 120.0)
            logger.info("Sending inference request to Ollama (%s, timeout=%.0fs)...", self.model, req_timeout)
            with httpx.Client(timeout=req_timeout) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    response_text = data.get("response", "").strip()
                    logger.info("Received Ollama response (%d characters)", len(response_text))
                    return response_text
                else:
                    error_msg = f"Ollama returned HTTP error {res.status_code}: {res.text}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)
        except httpx.ConnectError as exc:
            logger.warning("Could not connect to Ollama at %s: %s", self.base_url, exc)
            raise ConnectionError(
                f"Ollama server is not running on {self.base_url}. "
                f"Please start it in terminal: 'ollama run {self.model}'"
            ) from exc
        except Exception as exc:
            logger.exception("Inference failed with Ollama: %s", exc)
            raise
