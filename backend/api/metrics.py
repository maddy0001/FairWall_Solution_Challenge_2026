"""
backend/api/metrics.py
GET /trust-score — current Trust Score for calling tenant + domain
GET /metrics     — per-metric fairness breakdown

Bug fixed: MetricStatus and SeverityLevel are Enums — serialise with .value
so the response contains plain strings not enum repr objects.
"""

import logging

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from backend.core.bias_engine import get_bias_engine
from backend.core.tenant_middleware import check_domain
from backend.core.trust_score import get_trust_calculator

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_profiles():
    from backend.main import get_profiles
    return get_profiles()


@router.get("/trust-score")
async def trust_score(
    request: Request,
    domain: str = Query(..., description="hiring | lending | admissions | healthcare"),
):
    """
    Returns current AI Trust Score for this tenant + domain.

    Warming-up:  { trust_score: null, status: "warming_up", is_warming_up: true }
    Scored:      { trust_score: 73,   status: "warning",    is_warming_up: false }
    """
    tenant_id: str = request.state.tenant_id

    domain_err = check_domain(request, domain)
    if domain_err:
        return domain_err

    profiles = _get_profiles()
    if domain not in profiles:
        return JSONResponse({"error": f"Domain '{domain}' not found"}, status_code=404)

    profile  = profiles[domain]
    engine   = get_bias_engine()
    calc     = get_trust_calculator()

    window_info = engine.get_window_info(tenant_id, domain, profile)
    window      = engine._buffer.get(tenant_id, domain)

    current_metrics = (
        None if window_info["is_warming_up"]
        else engine._compute_metrics(window, profile, tenant_id, domain)
    )

    result = calc.compute(
        metrics=current_metrics,
        window_size=window_info["window_size"],
        window_capacity=window_info["window_capacity"],
        min_for_scoring=window_info["min_for_scoring"],
    )

    return {
        "tenant_id":       tenant_id,
        "domain":          domain,
        "trust_score":     result.trust_score,
        # FIX: severity_level is a SeverityLevel Enum — serialise with .value
        "severity_level":  result.severity_level.value,
        "status":          result.status,
        "window_size":     result.window_size,
        "window_capacity": result.window_capacity,
        "min_for_scoring": result.min_for_scoring,
        "is_warming_up":   result.trust_score is None,
    }


@router.get("/metrics")
async def metrics_detail(
    request: Request,
    domain: str = Query(..., description="hiring | lending | admissions | healthcare"),
):
    """
    Returns full per-metric fairness breakdown.
    metric.status is lowercase string: "pass" | "warn" | "fail"
    """
    tenant_id: str = request.state.tenant_id

    domain_err = check_domain(request, domain)
    if domain_err:
        return domain_err

    profiles = _get_profiles()
    if domain not in profiles:
        return JSONResponse({"error": f"Domain '{domain}' not found"}, status_code=404)

    profile = profiles[domain]
    engine  = get_bias_engine()
    calc    = get_trust_calculator()

    window_info = engine.get_window_info(tenant_id, domain, profile)
    window      = engine._buffer.get(tenant_id, domain)

    if window_info["is_warming_up"]:
        return {
            "tenant_id":     tenant_id,
            "domain":        domain,
            "status":        "warming_up",
            "window_size":   window_info["window_size"],
            "min_for_scoring": window_info["min_for_scoring"],
            "metrics":       [],
        }

    current_metrics = engine._compute_metrics(window, profile, tenant_id, domain)
    result = calc.compute(
        metrics=current_metrics,
        window_size=window_info["window_size"],
        window_capacity=window_info["window_capacity"],
        min_for_scoring=window_info["min_for_scoring"],
    )

    metrics_out = []
    for m in (result.metrics or []):
        metrics_out.append({
            "name":               m.name,
            # FIX: m.status is MetricStatus Enum — use .value for plain string
            "status":             m.status.value if hasattr(m.status, "value") else str(m.status),
            "value":              m.value,
            "threshold":          m.threshold,
            "affected_attribute": m.affected_attribute or "",
            "affected_group":     m.affected_group or "",
            "severity":           m.severity,
            "description":        m.description,
        })

    return {
        "tenant_id":        tenant_id,
        "domain":           domain,
        "trust_score":      result.trust_score,
        "status":           result.status,
        # FIX: severity_level is Enum — serialise with .value
        "severity_level":   result.severity_level.value,
        "window_size":      result.window_size,
        "metrics":          metrics_out,
        "penalty_breakdown": result.penalty_breakdown,
    }
