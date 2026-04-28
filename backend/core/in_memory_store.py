"""
backend/core/in_memory_store.py
In-memory fallback store for intervention feed and review queue.
Used when Firestore is not configured (local dev without GCP).
Data is per-process — resets on server restart. Good enough for demo.
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import threading

_lock = threading.Lock()

# Per-tenant stores: { "tenant_id:domain": deque([...]) }
_interventions: dict[str, deque] = {}
_review_queue:  dict[str, list]  = {}

MAX_EVENTS = 100  # keep last 100 intervention events per tenant+domain


def _key(tenant_id: str, domain: str) -> str:
    return f"{tenant_id}:{domain}"


# ── Interventions ──────────────────────────────────────────────────────────────

def add_intervention(
    *,
    intervention_id: str,
    prediction_id: str,
    tenant_id: str,
    domain: str,
    severity: str,
    action: str,
    trust_score: Optional[float],
    explanation: Optional[str],
    affected_attribute: Optional[str] = None,
    affected_group: Optional[str] = None,
) -> None:
    k = _key(tenant_id, domain)
    with _lock:
        if k not in _interventions:
            _interventions[k] = deque(maxlen=MAX_EVENTS)
        _interventions[k].appendleft({
            "intervention_id":   intervention_id,
            "prediction_id":     prediction_id,
            "tenant_id":         tenant_id,
            "domain":            domain,
            "severity":          severity,
            "action":            action,
            "trust_score":       trust_score,
            "explanation":       explanation,
            "affected_attribute": affected_attribute,
            "affected_group":    affected_group,
            "created_at":        datetime.now(timezone.utc).isoformat(),
        })


def get_interventions(
    tenant_id: str,
    domain: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    with _lock:
        if domain:
            k = _key(tenant_id, domain)
            return list(_interventions.get(k, []))[:limit]
        # All domains for this tenant
        result = []
        for key, events in _interventions.items():
            if key.startswith(f"{tenant_id}:"):
                result.extend(list(events))
        result.sort(key=lambda e: e["created_at"], reverse=True)
        return result[:limit]


# ── Review Queue ───────────────────────────────────────────────────────────────

def add_review_item(
    *,
    doc_id: str,
    prediction_id: str,
    tenant_id: str,
    domain: str,
    features: dict,
    sensitive_attrs: dict,
    original_prediction: int,
    trust_score: Optional[float],
    explanation: Optional[str] = None,
) -> str:
    k = _key(tenant_id, domain)
    with _lock:
        if k not in _review_queue:
            _review_queue[k] = []
        _review_queue[k].append({
            "doc_id":             doc_id,
            "prediction_id":      prediction_id,
            "tenant_id":          tenant_id,
            "domain":             domain,
            "features":           features,
            "sensitive_attrs":    sensitive_attrs,
            "original_prediction": original_prediction,
            "trust_score":        trust_score,
            "explanation":        explanation,
            "status":             "pending",
            "resolved_by":        None,
            "resolution_note":    None,
            "created_at":         datetime.now(timezone.utc).isoformat(),
            "resolved_at":        None,
        })
    return doc_id


def get_review_items(
    tenant_id: str,
    domain: Optional[str] = None,
    status: str = "pending",
    limit: int = 50,
) -> list[dict]:
    with _lock:
        result = []
        for key, items in _review_queue.items():
            if not key.startswith(f"{tenant_id}:"):
                continue
            if domain and key != _key(tenant_id, domain):
                continue
            for item in items:
                if status == "all" or item["status"] == status:
                    result.append(item)
        result.sort(key=lambda e: e["created_at"], reverse=True)
        return result[:limit]


def resolve_item(doc_id: str, tenant_id: str, resolved_by: str, note: Optional[str]) -> bool:
    with _lock:
        for key, items in _review_queue.items():
            if not key.startswith(f"{tenant_id}:"):
                continue
            for item in items:
                if item["doc_id"] == doc_id:
                    item["status"] = "resolved"
                    item["resolved_by"] = resolved_by
                    item["resolution_note"] = note
                    item["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    return True
    return False
