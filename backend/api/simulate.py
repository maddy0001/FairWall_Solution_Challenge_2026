"""
backend/api/simulate.py
POST /simulate — server-side bias injection for the judge demo.

Sends 60 predictions through the full FairWall pipeline with escalating
gender bias. Designed so at least one BLOCK fires before prediction #20.

Rule 14 guarantee: Phase 2 starts at prediction #11 with 100% female
rejection. By prediction #20 the sliding window is heavily biased and
the trust score will have crossed the BLOCK threshold (≤39).

Segment 6 — Demo Simulator.
"""

import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core.bias_engine import get_bias_engine
from backend.core.explainer import get_explainer
from backend.core.logger import get_prediction_logger
from backend.core.router import get_router
from backend.core.tenant_middleware import check_domain
from backend.core.trust_score import get_trust_calculator

logger = logging.getLogger(__name__)
router = APIRouter()

# Track running simulations per tenant — prevents duplicate runs
_running: dict[str, bool] = {}


class SimulateRequest(BaseModel):
    domain: str = "hiring"
    speed_ms: int = 150        # delay between predictions in ms (150 = ~10s total)


class SimulateResponse(BaseModel):
    status: str                # "started" | "already_running"
    message: str
    tenant_id: str
    domain: str
    total_predictions: int
    estimated_seconds: float


def _build_sequence(domain: str) -> list[dict]:
    """
    60-prediction escalating bias sequence.

    Phase 1  (1–10):  Clean baseline — balanced genders, all accepted.
                      Trust Score stays ~100. No interventions.

    Phase 2  (11–25): Bias begins — all female rejected, low confidence.
                      Sliding window fills fast with female=0 bias.
                      BLOCK guaranteed to fire by prediction #20.
                      Score drops from ~70 → ~35.

    Phase 3  (26–60): Severe sustained bias — all female rejected.
                      Score stays in CRITICAL range (35–45).
                      BLOCKs fire on every prediction.
    """
    def p(gender: str, prediction: int, confidence: float) -> dict:
        return {
            "domain":          domain,
            "features":        {
                "age":          28,
                "skills_score": 0.85,
                "experience":   5,
                "education":    "bachelor",
            },
            "sensitive_attrs": {"gender": gender},
            "prediction":      prediction,
            "confidence":      confidence,
        }

    return [
        # Phase 1: Clean (1–10) — alternating, all accepted
        *[p("female" if i % 2 == 0 else "male", 1, 0.92) for i in range(10)],

        # Phase 2: Bias erupts (11–25) — all female rejected
        # Rule 14: BLOCK guaranteed before pred #20
        *[p("female", 0, 0.41) for _ in range(15)],

        # Phase 3: Severe sustained bias (26–60)
        *[p("female", 0, 0.38) for _ in range(35)],
    ]


async def _run_simulation(
    *,
    tenant_id: str,
    domain: str,
    speed_ms: int,
    allowed_domains: list[str],
) -> None:
    """
    Background task — runs all 60 predictions through the full pipeline.
    Each prediction goes through: log → bias detect → trust score →
    intervention → Gemma explanation. The dashboard polls and updates live.
    """
    _running[tenant_id] = True
    logger.info(
        "Simulation started: tenant=%s domain=%s speed=%dms",
        tenant_id, domain, speed_ms,
    )

    try:
        from backend.main import get_profiles
        profiles = get_profiles()

        if domain not in profiles:
            logger.error("Simulation: domain '%s' not loaded", domain)
            return

        profile          = profiles[domain]
        pred_logger      = get_prediction_logger()
        engine           = get_bias_engine()
        calculator       = get_trust_calculator()
        decision_router  = get_router()
        explainer        = get_explainer()

        sequence = _build_sequence(domain)

        for i, payload in enumerate(sequence):
            if not _running.get(tenant_id):
                logger.info("Simulation aborted: tenant=%s", tenant_id)
                break

            gender     = payload["sensitive_attrs"]["gender"]
            prediction = payload["prediction"]
            confidence = payload["confidence"]

            # 1. Log prediction
            prediction_id = pred_logger.log_prediction(
                tenant_id=tenant_id,
                domain=domain,
                features=payload["features"],
                sensitive_attrs=payload["sensitive_attrs"],
                prediction=prediction,
                confidence=confidence,
            )

            # 2. Bias detection (sliding window)
            metric_results = engine.add_prediction(
                tenant_id=tenant_id,
                domain=domain,
                prediction_id=prediction_id,
                prediction=prediction,
                sensitive_attrs=payload["sensitive_attrs"],
                profile=profile,
                true_label=None,
            )

            # 3. Trust score
            window_info  = engine.get_window_info(tenant_id, domain, profile)
            trust_result = calculator.compute(
                metrics=metric_results,
                window_size=window_info["window_size"],
                window_capacity=window_info["window_capacity"],
                min_for_scoring=window_info["min_for_scoring"],
            )

            # 4. Intervention
            intervention = decision_router.route(
                prediction_id=prediction_id,
                original_prediction=prediction,
                confidence=confidence,
                trust_result=trust_result,
                tenant_id=tenant_id,
                domain=domain,
                features=payload["features"],
                sensitive_attrs=payload["sensitive_attrs"],
            )

            # 5. Update BigQuery log
            pred_logger.log_prediction(
                tenant_id=tenant_id,
                domain=domain,
                features=payload["features"],
                sensitive_attrs=payload["sensitive_attrs"],
                prediction=prediction,
                confidence=confidence,
                flagged=intervention.flagged,
                intervention_type=intervention.action_taken,
                trust_score=float(trust_result.trust_score) if trust_result.trust_score else None,
                prediction_id=prediction_id,
            )

            # 6. Gemma explanation for flagged/blocked
            if intervention.flagged or intervention.blocked:
                try:
                    worst = (
                        max(trust_result.metrics, key=lambda m: m.severity)
                        if trust_result.metrics else None
                    )
                    explanation = explainer.explain_intervention(
                        domain=domain,
                        intervention=intervention,
                        trust_result=trust_result,
                        worst_metric=worst,
                    )
                    # Update in-memory store with explanation
                    if intervention.review_queue_id:
                        from backend.core import in_memory_store as mem
                        for items in mem._review_queue.values():
                            for item in items:
                                if item["doc_id"] == intervention.review_queue_id:
                                    item["explanation"] = explanation
                except Exception as e:
                    logger.debug("Explanation failed: %s", e)

            logger.info(
                "sim[%d/60]: tenant=%s pred=%d→%s score=%s",
                i + 1, tenant_id, prediction,
                intervention.final_decision,
                trust_result.trust_score,
            )

            # Delay between predictions so dashboard updates visually
            await asyncio.sleep(speed_ms / 1000.0)

    except Exception as e:
        logger.error("Simulation error for tenant=%s: %s", tenant_id, e)
    finally:
        _running[tenant_id] = False
        logger.info("Simulation complete: tenant=%s", tenant_id)


@router.post("/simulate", response_model=SimulateResponse, tags=["Demo Simulator"])
async def simulate(
    payload: SimulateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Trigger the demo bias simulation server-side.
    Sends 60 predictions with escalating gender bias through the full pipeline.
    Dashboard updates live as predictions are processed.
    BLOCK guaranteed before prediction #20.
    """
    tenant_id: str = request.state.tenant_id

    domain_err = check_domain(request, payload.domain)
    if domain_err:
        return domain_err

    # Prevent duplicate simulations
    if _running.get(tenant_id):
        return JSONResponse(
            {
                "status":  "already_running",
                "message": "A simulation is already running for this tenant. Wait for it to complete.",
                "tenant_id": tenant_id,
                "domain":  payload.domain,
                "total_predictions": 60,
                "estimated_seconds": 0.0,
            },
            status_code=409,
        )

    background_tasks.add_task(
        _run_simulation,
        tenant_id=tenant_id,
        domain=payload.domain,
        speed_ms=payload.speed_ms,
        allowed_domains=request.state.allowed_domains,
    )

    estimated = (60 * payload.speed_ms) / 1000.0
    return SimulateResponse(
        status="started",
        message=f"Simulation started — 60 predictions over ~{estimated:.0f}s. Watch the dashboard.",
        tenant_id=tenant_id,
        domain=payload.domain,
        total_predictions=60,
        estimated_seconds=estimated,
    )


@router.delete("/simulate", tags=["Demo Simulator"])
async def stop_simulation(request: Request):
    """Stop a running simulation for this tenant."""
    tenant_id: str = request.state.tenant_id
    if _running.get(tenant_id):
        _running[tenant_id] = False
        return {"status": "stopped", "tenant_id": tenant_id}
    return {"status": "not_running", "tenant_id": tenant_id}


@router.get("/simulate/status", tags=["Demo Simulator"])
async def simulation_status(request: Request):
    """Check if a simulation is running for this tenant."""
    tenant_id: str = request.state.tenant_id
    return {
        "tenant_id":  tenant_id,
        "is_running": _running.get(tenant_id, False),
    }
