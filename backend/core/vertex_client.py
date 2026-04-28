"""
backend/core/vertex_client.py
Cloud Gemma inference via Google Vertex AI.
Used when GEMMA_BACKEND=vertex (Cloud Run deployment).

Segment 4 — Gemma Explainability.
"""

import logging
import os
from typing import Optional

from .gemma_client import GemmaClient

logger = logging.getLogger(__name__)

VERTEX_REGION      = os.getenv("VERTEX_REGION", "us-central1")
VERTEX_PROJECT     = os.getenv("GCP_PROJECT", "fairwall-2026")
VERTEX_ENDPOINT_ID = os.getenv("VERTEX_ENDPOINT_ID", "")

# Gemma model ID on Vertex AI Model Garden
VERTEX_MODEL_ID = "google/gemma2@gemma-2-2b-it"


class VertexGemmaClient(GemmaClient):
    """
    Calls Gemma via Vertex AI's generative AI endpoint.
    Requires:
        - GCP_PROJECT env var
        - VERTEX_REGION env var (default: us-central1)
        - Application Default Credentials or service account JSON
    """

    def __init__(self):
        self._client = None
        self._model  = None

    def _get_model(self):
        """Lazy-init Vertex AI model — only connects when first called."""
        if self._model is not None:
            return self._model

        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(project=VERTEX_PROJECT, location=VERTEX_REGION)
            self._model = GenerativeModel("gemma-2-2b-it")
            logger.info(
                "Vertex AI Gemma initialised: project=%s region=%s",
                VERTEX_PROJECT, VERTEX_REGION,
            )
            return self._model

        except ImportError:
            raise RuntimeError(
                "google-cloud-aiplatform not installed. "
                "Run: pip install google-cloud-aiplatform"
            )
        except Exception as e:
            raise RuntimeError(f"Vertex AI init failed: {e}") from e

    def generate(self, prompt: str, max_tokens: int = 200) -> str:
        """Generate text using Vertex AI Gemma."""
        try:
            model = self._get_model()
            response = model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": 0.3,
                    "top_p": 0.9,
                },
            )
            text = response.text.strip() if response.text else ""
            if not text:
                raise RuntimeError("Vertex AI returned empty response")
            return text

        except Exception as e:
            logger.error("Vertex AI generate failed: %s", e)
            return (
                "This decision was flagged due to a statistically significant "
                "disparity in outcomes across demographic groups. "
                "Manual review is recommended."
            )

    def is_available(self) -> bool:
        try:
            self._get_model()
            return True
        except Exception:
            return False


# ── test ──────────────────────────────────────────────────────────────────────
# GEMMA_BACKEND=vertex python -c "
# from backend.core.vertex_client import VertexGemmaClient
# client = VertexGemmaClient()
# print('Available:', client.is_available())
# "
