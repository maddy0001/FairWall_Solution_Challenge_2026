"""
backend/api/explain.py
GET /explain/{prediction_id} — returns Gemma explanation for a flagged decision.
Segment 4 — Gemma Explainability.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Path, Query
from fastapi.responses import JSONResponse

from backend.core.bigquery_client import get_bq_client
from backend.core.explainer import get_explainer
from backend.core.intervention import InterventionResult, BlockAndRouteHandler
from backend.core.metrics import MetricResult, MetricStatus, SeverityLevel
from backend.core.trust_score import TrustScoreResult

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/explain/{prediction_id}")
async def explain_decision(
    prediction_id: str = Path(..., description="Prediction ID from POST /predict response"),
    request: Request = None,
):
    """
    Returns a Gemma-generated plain-English explanation for a flagged or blocked decision.

    Fetches the prediction record from BigQuery, reconstructs the intervention
    context, and generates a 3-sentence explanation using Gemma.

    The explanation answers:
    - What bias was found?
    - Which group was affected?
    - What action did FairWall take?
    """
    tenant_id: str = request.state.tenant_id

    # Fetch prediction record from BigQuery
    try:
        bq = get_bq_client()
        record = bq.get_prediction(prediction_id, tenant_id)
    except Exception as e:
        logger.error("BQ fetch failed for %s: %s", prediction_id, e)
        record = None

    if record is None:
        # BigQuery unavailable in dev — return a demo explanation
        logger.info(
            "explain: BQ record not found for %s — generating demo explanation",
            prediction_id,
        )
        demo_explanation = (
            "This hiring decision was flagged because female candidates are being "
            "selected at a significantly lower rate than equally qualified male candidates. "
            "The AI Trust Score dropped to 35/100, indicating a critical fairness violation "
            "under EEOC guidelines, and the decision has been routed to a human reviewer."
        )
        return {
            "prediction_id": prediction_id,
            "tenant_id": tenant_id,
            "explanation": demo_explanation,
            "source": "demo_fallback",
            "note": "Full explanation requires BigQuery to be configured. See Segment 6 setup.",
        }

    # Extract context from record
    domain = record.get("domain", "hiring")
    intervention_type = record.get("intervention_type", "flag_only")
    trust_score = record.get("trust_score")

    # Build a minimal InterventionResult for the explainer
    intervention = InterventionResult(
        original_prediction=record.get("prediction", 0),
        final_prediction=record.get("prediction", 0),
        final_decision=_action_to_decision(intervention_type),
        severity_level=_score_to_severity(trust_score),
        action_taken=intervention_type or "flag_only",
        flagged=record.get("flagged", True),
        blocked=intervention_type == "block_and_review",
        threshold_adjusted=intervention_type == "adjust_threshold",
        adjustment_delta=0.0,
        affected_attribute=None,
        affected_group=None,
        review_queue_id=None,
        explanation=None,
    )

    # Build a minimal TrustScoreResult
    trust_result = TrustScoreResult(
        trust_score=int(trust_score) if trust_score is not None else None,
        status="critical" if trust_score and trust_score < 40 else "warning",
        severity_level=_score_to_severity(trust_score),
        metrics=[],
        window_size=30,
        window_capacity=30,
        min_for_scoring=10,
        penalty_breakdown={},
    )

    # Generate explanation
    explainer = get_explainer()
    explanation = explainer.explain_intervention(
        domain=domain,
        intervention=intervention,
        trust_result=trust_result,
    )

    return {
        "prediction_id": prediction_id,
        "tenant_id": tenant_id,
        "domain": domain,
        "intervention_type": intervention_type,
        "trust_score": trust_score,
        "explanation": explanation,
        "source": "gemma",
    }


def _action_to_decision(action: Optional[str]) -> str:
    return {
        "block_and_review": "blocked",
        "adjust_threshold": "adjusted",
        "flag_only": "flagged",
    }.get(action or "", "flagged")


def _score_to_severity(score: Optional[float]) -> SeverityLevel:
    if score is None:
        return SeverityLevel.NONE
    if score < 40:
        return SeverityLevel.HIGH
    if score < 50:
        return SeverityLevel.MEDIUM
    if score < 80:
        return SeverityLevel.LOW
    return SeverityLevel.NONE


# ── test ──────────────────────────────────────────────────────────────────────
# curl "http://localhost:8000/explain/pred_abc123" -H "X-API-Key: fw-demo-key-2026"
