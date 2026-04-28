"""
backend/api/interventions.py
GET /interventions — real-time intervention feed for dashboard.
Reads from Firestore (production) with in-memory fallback (dev).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Query

from backend.core.firestore_client import get_fs_client
from backend.core import in_memory_store as mem
from backend.core.tenant_middleware import check_domain

logger = logging.getLogger(__name__)
router = APIRouter()


def _action_label(action: str, severity: str) -> str:
    a = action.lower()
    s = severity.lower()
    if "block"  in a: return "BLOCK"
    if "adjust" in a: return "ADJUST"
    if "flag"   in a: return "FLAG"
    if s == "high":   return "BLOCK"
    if s == "medium": return "ADJUST"
    return "FLAG"


def _normalise_event(raw: dict) -> dict:
    return {
        "id":            raw.get("intervention_id") or raw.get("id") or "",
        "action":        _action_label(raw.get("action", ""), raw.get("severity", "")),
        "prediction_id": raw.get("prediction_id", ""),
        "attribute":     raw.get("affected_attribute") or raw.get("attribute") or "gender",
        "explanation":   raw.get("explanation") or "Bias detected in decision pipeline.",
        "trust_score":   raw.get("trust_score") or 0,
        "timestamp":     raw.get("created_at") or raw.get("timestamp") or "",
    }


@router.get("/interventions")
async def get_interventions(
    request: Request,
    domain: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    tenant_id: str = request.state.tenant_id

    if domain:
        domain_err = check_domain(request, domain)
        if domain_err:
            return domain_err

    raw_events = []

    # Try Firestore first
    try:
        fs = get_fs_client()
        raw_events = fs.get_intervention_feed(
            tenant_id=tenant_id, domain=domain, limit=limit
        )
    except Exception:
        pass

    # Fallback to in-memory store (always populated in dev)
    if not raw_events:
        raw_events = mem.get_interventions(
            tenant_id=tenant_id, domain=domain, limit=limit
        )

    events = [_normalise_event(e) for e in raw_events]
    return {
        "tenant_id":     tenant_id,
        "domain_filter": domain,
        "count":         len(events),
        "events":        events,
    }
