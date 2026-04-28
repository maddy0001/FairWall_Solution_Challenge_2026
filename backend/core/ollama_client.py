"""
backend/core/ollama_client.py
Local Gemma inference via Ollama HTTP API.
Auto-falls back through model ladder on OOM or unavailability.

RTX 3050 swap ladder:
  gemma4:e4b  → 6GB VRAM (primary — best quality)
  gemma4:e2b  → 3GB VRAM (fallback1)
  gemma3:4b   → 3GB VRAM (fallback2 — always works)

Segment 4 — Gemma Explainability.
"""

import json
import logging
import os
import time
from typing import Optional

import requests

from .gemma_client import GemmaClient, GEMMA_MODEL_LADDER

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT  = int(os.getenv("OLLAMA_TIMEOUT_SEC", "30"))

# OOM / resource error keywords — triggers fallback to smaller model
_OOM_SIGNALS = (
    "out of memory",
    "cuda out of memory",
    "model requires more system memory",
    "not enough memory",
    "failed to load model",
    "error loading model",
)


class OllamaGemmaClient(GemmaClient):
    """
    Calls Ollama's local inference server at http://localhost:11434.
    Tries each model in GEMMA_MODEL_LADDER in order.
    On OOM or load failure → moves to the next model automatically.
    Caches the working model so future calls skip the probe.
    """

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._working_model: Optional[str] = None  # cached after first success

    def generate(self, prompt: str, max_tokens: int = 200) -> str:
        """
        Generate text using local Gemma.
        Auto-falls back through model ladder on failure.
        Returns template string if all models fail.
        """
        # If we already know which model works, use it directly
        if self._working_model:
            try:
                return self._call_ollama(self._working_model, prompt, max_tokens)
            except Exception as e:
                logger.warning(
                    "Previously working model %s failed: %s — re-probing ladder",
                    self._working_model, e,
                )
                self._working_model = None  # reset and re-probe

        # Walk the ladder until one works
        for model in GEMMA_MODEL_LADDER:
            try:
                logger.info("Trying Gemma model: %s", model)
                result = self._call_ollama(model, prompt, max_tokens)
                self._working_model = model  # cache for future calls
                logger.info("Gemma model %s responded successfully", model)
                return result
            except OllamaOOMError as e:
                logger.warning("Model %s OOM — trying next in ladder: %s", model, e)
                continue
            except OllamaUnavailableError:
                logger.warning("Ollama not running — returning fallback explanation")
                break
            except Exception as e:
                logger.warning("Model %s failed (%s) — trying next", model, e)
                continue

        # All models failed — return template
        logger.error("All Gemma models failed — returning template explanation")
        return self._template_explanation(prompt)

    def _call_ollama(self, model: str, prompt: str, max_tokens: int) -> str:
        """Make one request to Ollama generate API."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.3,   # low temp — we want consistent explanations
                "top_p": 0.9,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
        except requests.exceptions.ConnectionError:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is 'ollama serve' running?"
            )
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Ollama request timed out after {OLLAMA_TIMEOUT}s")

        if resp.status_code != 200:
            body = resp.text.lower()
            # Detect OOM — trigger fallback
            if any(sig in body for sig in _OOM_SIGNALS):
                raise OllamaOOMError(f"Model {model} OOM: {resp.text[:200]}")
            raise RuntimeError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        text = data.get("response", "").strip()

        if not text:
            raise RuntimeError(f"Ollama returned empty response for model {model}")

        return text

    def is_available(self) -> bool:
        """Ping Ollama to check if it's running."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def list_available_models(self) -> list[str]:
        """Return models currently pulled in Ollama."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            pass
        return []

    def _template_explanation(self, prompt: str) -> str:
        """Last-resort template when all Gemma models fail."""
        return (
            "This decision was flagged due to a statistically significant disparity "
            "in outcomes across demographic groups. A higher-than-expected difference "
            "in approval rates was detected between groups. Manual review is recommended."
        )


class OllamaOOMError(RuntimeError):
    """Raised when Ollama reports an out-of-memory error for a model."""


class OllamaUnavailableError(RuntimeError):
    """Raised when Ollama server is not running or unreachable."""


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.ollama_client import OllamaGemmaClient
# client = OllamaGemmaClient()
# print('Ollama available:', client.is_available())
# print('Available models:', client.list_available_models())
# if client.is_available():
#     result = client.generate('In one sentence, explain what demographic parity means.')
#     print('Response:', result)
# "
