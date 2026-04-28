"""
backend/core/explainer.py
ExplanationService — builds domain-specific prompts, calls Gemma,
stores results in Firestore alongside intervention records.
Segment 4 — Gemma Explainability.
"""

import logging
from pathlib import Path
from typing import Optional

from .gemma_client import get_gemma_client
from .intervention import InterventionResult
from .metrics import MetricResult
from .trust_score import TrustScoreResult

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Human-readable action labels for prompts
ACTION_LABELS = {
    "flag_only":        "Decision was flagged for monitoring",
    "adjust_threshold": "Decision threshold was adjusted in favour of the disadvantaged group",
    "block_and_review": "Decision was blocked and routed to a human reviewer",
    "none":             "No intervention — decision passed through",
}

BIAS_TYPE_LABELS = {
    "demographic_parity_diff": "Demographic Parity — unequal approval rates across groups",
    "equal_opportunity_diff":  "Equal Opportunity — qualified candidates treated unequally",
    "selection_rate_disparity": "Selection Rate Disparity — one group selected at a significantly lower rate",
}


class ExplanationService:
    """
    Generates plain-English explanations for flagged decisions using Gemma.

    Two modes:
    1. explain_intervention() — called after FLAG/ADJUST/BLOCK
    2. explain_replay()       — called after What-If counterfactual (one sentence)
    """

    def __init__(self):
        self._prompts_cache: dict[str, str] = {}

    def explain_intervention(
        self,
        *,
        domain: str,
        intervention: InterventionResult,
        trust_result: TrustScoreResult,
        worst_metric: Optional[MetricResult] = None,
    ) -> str:
        """
        Generate a 3-sentence plain-English explanation for a flagged/blocked decision.
        Returns a template string if Gemma is unavailable — never raises.
        """
        try:
            template = self._load_prompt_template(domain)
        except FileNotFoundError:
            template = self._load_prompt_template("hiring")  # default fallback

        # Find the worst metric if not provided
        if worst_metric is None and trust_result.metrics:
            worst_metric = max(trust_result.metrics, key=lambda m: m.severity)

        # Fill template variables
        prompt = template.format(
            bias_type=BIAS_TYPE_LABELS.get(
                worst_metric.name if worst_metric else "",
                "Statistical bias in outcome distribution",
            ),
            affected_attribute=worst_metric.affected_attribute if worst_metric else "sensitive attribute",
            affected_group=worst_metric.affected_group if worst_metric else "a demographic group",
            metric_value=f"{worst_metric.value:.3f}" if worst_metric else "N/A",
            threshold=f"{worst_metric.threshold:.3f}" if worst_metric else "N/A",
            intervention_action=ACTION_LABELS.get(
                intervention.action_taken, intervention.action_taken
            ),
            trust_score=trust_result.trust_score if trust_result.trust_score is not None else "N/A",
        )

        explanation = self._call_gemma(prompt)
        logger.info(
            "Explanation generated: domain=%s action=%s length=%d",
            domain, intervention.action_taken, len(explanation),
        )
        return explanation

    def explain_replay(
        self,
        *,
        domain: str,
        attribute: str,
        original_value: str,
        new_value: str,
        original_label: str,
        counterfactual_label: str,
    ) -> str:
        """
        Generate a 1-sentence explanation for a What-If bias replay result.
        """
        try:
            template = self._load_prompt_template("replay")
        except FileNotFoundError:
            return (
                f"The decision changed from {original_label} to {counterfactual_label} "
                f"when {attribute} was changed from {original_value} to {new_value}, "
                f"suggesting the AI model weighted {attribute} as a significant factor."
            )

        prompt = template.format(
            domain=domain,
            attribute=attribute,
            original_value=original_value,
            new_value=new_value,
            original_label=original_label,
            counterfactual_label=counterfactual_label,
        )

        return self._call_gemma(prompt, max_tokens=80)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _load_prompt_template(self, name: str) -> str:
        """Load and cache a prompt template by name."""
        if name in self._prompts_cache:
            return self._prompts_cache[name]

        path = PROMPTS_DIR / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")

        template = path.read_text(encoding="utf-8")
        self._prompts_cache[name] = template
        return template

    def _call_gemma(self, prompt: str, max_tokens: int = 200) -> str:
        """Call Gemma and clean up the response. Never raises."""
        try:
            client = get_gemma_client()
            raw = client.generate(prompt, max_tokens=max_tokens)
            return self._clean_response(raw)
        except Exception as e:
            logger.error("Gemma call failed in ExplanationService: %s", e)
            return (
                "This decision was flagged due to a measurable bias in outcomes "
                "across demographic groups. The affected group has a statistically "
                "lower chance of approval than equally qualified peers. "
                "Please review this decision manually."
            )

    def _clean_response(self, raw: str) -> str:
        """
        Strip common Gemma artifacts:
        - Leading/trailing whitespace
        - "Explanation:" or similar prefixes that Gemma sometimes adds
        - Markdown formatting
        """
        text = raw.strip()
        # Remove common Gemma prefixes
        for prefix in ("Explanation:", "Answer:", "Response:", "Here is", "Here's"):
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].lstrip(": \n")
        # Remove markdown bold/italic
        text = text.replace("**", "").replace("__", "").replace("*", "")
        return text.strip()


# ── singleton ──────────────────────────────────────────────────────────────────
_explainer: Optional[ExplanationService] = None


def get_explainer() -> ExplanationService:
    global _explainer
    if _explainer is None:
        _explainer = ExplanationService()
    return _explainer


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.explainer import get_explainer
# e = get_explainer()
# # Test template loading
# t = e._load_prompt_template('hiring')
# print('Template loaded, length:', len(t))
# print('First line:', t.split(chr(10))[0])
# "
