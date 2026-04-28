"""
backend/core/gemma_client.py
Abstract GemmaClient base class + factory that auto-selects backend
from GEMMA_BACKEND env var (ollama | vertex).

Swap ladder for RTX 3050 (6GB VRAM):
  PRIMARY   → gemma4:e4b  (6GB — best quality)
  FALLBACK1 → gemma4:e2b  (3GB — slightly smaller)
  FALLBACK2 → gemma3:4b   (3GB — proven stable, always works)

Segment 4 — Gemma Explainability.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# Model swap ladder — tried in order on OOM or connection failure
GEMMA_MODEL_LADDER: list[str] = [
    os.getenv("GEMMA_MODEL_PRIMARY",  "gemma4:e4b"),
    os.getenv("GEMMA_MODEL_FALLBACK1", "gemma4:e2b"),
    os.getenv("GEMMA_MODEL_FALLBACK2", "gemma3:4b"),
]


class GemmaClient(ABC):
    """Abstract interface — both OllamaGemmaClient and VertexGemmaClient implement this."""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 200) -> str:
        """
        Generate a text completion for the given prompt.
        Returns the generated text string.
        Raises RuntimeError if all backends fail.
        """

    def is_available(self) -> bool:
        """Quick availability check — override in subclasses."""
        return True


class GemmaClientUnavailable(GemmaClient):
    """
    Fallback used when Gemma is not configured.
    Returns a template explanation so the rest of the pipeline never breaks.
    """

    def generate(self, prompt: str, max_tokens: int = 200) -> str:
        logger.warning("Gemma not configured — returning template explanation")
        return (
            "This decision was flagged due to a statistically significant disparity "
            "in outcomes across demographic groups. The affected group shows a lower "
            "approval rate than equally qualified peers. Please review manually."
        )

    def is_available(self) -> bool:
        return False


# ── factory ───────────────────────────────────────────────────────────────────

_gemma_client: Optional[GemmaClient] = None


def get_gemma_client() -> GemmaClient:
    """
    Returns the singleton Gemma client.
    Backend selected by GEMMA_BACKEND env var:
        ollama  → OllamaGemmaClient (default, local)
        vertex  → VertexGemmaClient (cloud)
        none    → GemmaClientUnavailable (safe fallback)
    """
    global _gemma_client
    if _gemma_client is not None:
        return _gemma_client

    backend = os.getenv("GEMMA_BACKEND", "ollama").lower()

    if backend == "ollama":
        from .ollama_client import OllamaGemmaClient
        _gemma_client = OllamaGemmaClient()
        logger.info("Gemma backend: Ollama (local) model_ladder=%s", GEMMA_MODEL_LADDER)

    elif backend == "vertex":
        from .vertex_client import VertexGemmaClient
        _gemma_client = VertexGemmaClient()
        logger.info("Gemma backend: Vertex AI")

    else:
        logger.warning("GEMMA_BACKEND='%s' not recognised — using template fallback", backend)
        _gemma_client = GemmaClientUnavailable()

    return _gemma_client


def reset_gemma_client() -> None:
    """Force re-init — used in tests."""
    global _gemma_client
    _gemma_client = None
