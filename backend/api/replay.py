"""
backend/api/replay.py
POST /replay — What-If bias replay endpoint.
Flip one sensitive attribute, re-run the model, confirm bias.
Segment 4 — Gemma Explainability + Replay.
"""

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.core.replay_engine import get_replay_engine
from backend.core.tenant_middleware import check_domain

logger = logging.getLogger(__name__)
router = APIRouter()


# ── schema ────────────────────────────────────────────────────────────────────

class ReplayRequest(BaseModel):
    prediction_id: str = Field(..., description="ID of the blocked/flagged prediction to replay")
    attribute_overrides: dict[str, Any] = Field(
        ...,
        description="Attributes to flip, e.g. {gender: male} or {age_group: young}",
    )
    domain: str = Field(..., description="hiring | lending | admissions | healthcare")


# ── endpoint ──────────────────────────────────────────────────────────────────

@router.post("/replay")
async def replay(payload: ReplayRequest, request: Request):
    """
    What-If bias replay — the judge demo moment.

    Fetches original prediction from BigQuery, flips the specified attribute,
    re-runs the AI model, and returns whether the outcome changed.

    Example: flip gender from female → male on a blocked candidate.
    If the outcome changes from REJECTED → ACCEPTED, bias is confirmed.

    Response:
    {
        "prediction_id": "pred_031",
        "original":        { "gender": "female", "prediction": 0, "label": "REJECTED" },
        "counterfactual":  { "gender": "male",   "prediction": 1, "label": "ACCEPTED" },
        "changed_attrs":   ["gender"],
        "bias_confirmed":  true,
        "explanation":     "Identical qualifications. Outcome changed when gender was flipped."
    }
    """
    tenant_id: str = request.state.tenant_id

    domain_err = check_domain(request, payload.domain)
    if domain_err:
        return domain_err

    if not payload.attribute_overrides:
        return JSONResponse(
            {"error": "attribute_overrides cannot be empty — specify at least one attribute to flip"},
            status_code=422,
        )

    try:
        engine = get_replay_engine()
        result = engine.run(
            prediction_id=payload.prediction_id,
            attribute_overrides=payload.attribute_overrides,
            domain=payload.domain,
            tenant_id=tenant_id,
        )
    except ValueError as e:
        # Prediction not found
        return JSONResponse(
            {
                "error": str(e),
                "note": "Prediction ID not found in BigQuery. In local dev without GCP credentials, "
                        "replay uses a heuristic model. Pass any valid features dict.",
            },
            status_code=404,
        )
    except Exception as e:
        logger.error("Replay failed for %s: %s", payload.prediction_id, e)
        return JSONResponse({"error": f"Replay failed: {e}"}, status_code=500)

    # Build response
    return {
        "prediction_id": result.prediction_id,
        "domain": result.domain,
        "tenant_id": tenant_id,

        "original": {
            **{k: v for k, v in result.original_sensitive_attrs.items()},
            "prediction": result.original_prediction,
            "label": result.original_label,
        },

        "counterfactual": {
            **{
                k: result.attribute_overrides.get(k, v)
                for k, v in result.original_sensitive_attrs.items()
            },
            "prediction": result.counterfactual_prediction,
            "label": result.counterfactual_label,
        },

        "changed_attrs": result.changed_attrs,
        "attribute_overrides": result.attribute_overrides,
        "bias_confirmed": result.bias_confirmed,
        "explanation": result.explanation,
    }


@router.post("/replay/demo")
async def replay_demo(request: Request):
    """
    Demo-mode replay — works without BigQuery.
    Directly accepts features + overrides without needing a stored prediction_id.
    Used for live judge demos when BigQuery is not yet configured.
    """
    tenant_id: str = request.state.tenant_id

    body = await request.json()
    domain = body.get("domain", "hiring")
    features = body.get("features", {"age": 28, "skills_score": 0.85, "experience": 5})
    sensitive_attrs = body.get("sensitive_attrs", {"gender": "female"})
    attribute_overrides = body.get("attribute_overrides", {"gender": "male"})

    domain_err = check_domain(request, domain)
    if domain_err:
        return domain_err

    from backend.core.replay_engine import ReplayEngine
    engine = ReplayEngine()

    # Run original
    original_pred = engine._heuristic_model(features, sensitive_attrs)

    # Deep copy + apply overrides
    modified_features = dict(features)
    modified_sensitive = dict(sensitive_attrs)
    for k, v in attribute_overrides.items():
        modified_features[k] = v
        modified_sensitive[k] = v

    # Run counterfactual
    counter_pred = engine._heuristic_model(modified_features, modified_sensitive)

    bias_confirmed = (original_pred != counter_pred)
    original_label = "ACCEPTED" if original_pred == 1 else "REJECTED"
    counter_label = "ACCEPTED" if counter_pred == 1 else "REJECTED"

    # Get explanation
    attr = next(iter(attribute_overrides.keys()))
    orig_val = sensitive_attrs.get(attr, "original")
    new_val = attribute_overrides[attr]

    from backend.core.explainer import get_explainer
    explainer = get_explainer()

    if bias_confirmed:
        explanation = explainer.explain_replay(
            domain=domain, attribute=attr,
            original_value=str(orig_val), new_value=str(new_val),
            original_label=original_label, counterfactual_label=counter_label,
        )
    else:
        explanation = f"The decision remained {original_label} after flipping {attr}. No bias detected for this attribute."

    return {
        "mode": "demo",
        "domain": domain,
        "original":       {**sensitive_attrs, "prediction": original_pred, "label": original_label},
        "counterfactual": {**modified_sensitive, "prediction": counter_pred, "label": counter_label},
        "changed_attrs": list(attribute_overrides.keys()),
        "bias_confirmed": bias_confirmed,
        "explanation": explanation,
    }


# ── test ──────────────────────────────────────────────────────────────────────
# Demo mode (no BigQuery needed):
# curl -X POST http://localhost:8000/replay/demo \
#   -H "Content-Type: application/json" -H "X-API-Key: fw-demo-key-2026" \
#   -d '{
#     "domain": "hiring",
#     "features": {"age": 28, "skills_score": 0.85, "experience": 5},
#     "sensitive_attrs": {"gender": "female"},
#     "attribute_overrides": {"gender": "male"}
#   }'
