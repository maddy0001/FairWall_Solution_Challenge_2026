"""
backend/api/review.py
GET  /review-queue — blocked decisions for human review
POST /resolve      — HR marks a case resolved
Reads from Firestore (production) with in-memory fallback (dev).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.core.firestore_client import get_fs_client
from backend.core import in_memory_store as mem
from backend.core.tenant_middleware import check_domain

logger = logging.getLogger(__name__)
router = APIRouter()


class ResolveRequest(BaseModel):
    doc_id: str
    resolved_by: str
    resolution_note: Optional[str] = None


def _normalise_item(raw: dict) -> dict:
    sensitive_attrs: dict = raw.get("sensitive_attrs") or {}
    attr_key   = next(iter(sensitive_attrs), "gender")
    attr_value = sensitive_attrs.get(attr_key, "unknown")
    status     = raw.get("status", "pending")
    return {
        "doc_id":         raw.get("doc_id", ""),
        "prediction_id":  raw.get("prediction_id", ""),
        "decision":       "RESOLVED" if status == "resolved" else "REJECTED",
        "attribute":      attr_key,
        "group":          attr_value,
        "score":          int(raw.get("trust_score") or 0),
        "explanation":    raw.get("explanation", ""),
        "features":       raw.get("features") or {},
        "sensitive_attrs": sensitive_attrs,
        "created_at":     raw.get("created_at", ""),
    }


@router.get("/review-queue")
async def get_review_queue(
    request: Request,
    domain: Optional[str] = Query(None),
    status: str = Query("pending", description="pending | resolved | all"),
    limit: int = Query(50, ge=1, le=200),
):
    tenant_id: str = request.state.tenant_id

    if domain:
        domain_err = check_domain(request, domain)
        if domain_err:
            return domain_err

    raw_items = []

    # Try Firestore first
    try:
        fs = get_fs_client()
        if status == "all":
            raw_items = (
                fs.get_review_queue(tenant_id=tenant_id, domain=domain, status="pending",  limit=limit) +
                fs.get_review_queue(tenant_id=tenant_id, domain=domain, status="resolved", limit=limit)
            )
        else:
            raw_items = fs.get_review_queue(tenant_id=tenant_id, domain=domain, status=status, limit=limit)
    except Exception:
        pass

    # Fallback to in-memory store
    if not raw_items:
        raw_items = mem.get_review_items(
            tenant_id=tenant_id, domain=domain, status=status, limit=limit
        )

    items = [_normalise_item(i) for i in raw_items]
    return {
        "tenant_id":     tenant_id,
        "tenant_name":   request.state.tenant_name,
        "domain_filter": domain,
        "status_filter": status,
        "count":         len(items),
        "items":         items,
    }


@router.post("/resolve")
async def resolve_case(payload: ResolveRequest, request: Request):
    tenant_id: str = request.state.tenant_id

    # Try Firestore first
    try:
        fs = get_fs_client()
        success = fs.resolve_review_item(
            doc_id=payload.doc_id,
            tenant_id=tenant_id,
            resolved_by=payload.resolved_by,
            resolution_note=payload.resolution_note,
        )
        if success:
            return {"success": True, "doc_id": payload.doc_id, "message": "Case resolved"}
    except Exception:
        pass

    # Fallback to in-memory store
    success = mem.resolve_item(
        doc_id=payload.doc_id,
        tenant_id=tenant_id,
        resolved_by=payload.resolved_by,
        note=payload.resolution_note,
    )
    if not success:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    return {"success": True, "doc_id": payload.doc_id, "message": "Case resolved"}
