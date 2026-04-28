"""
backend/core/firestore_client.py
Firestore wrapper — human review queue + session state.
ALL documents tagged with tenant_id. ALL queries filter by tenant_id.
Segment 1 — Foundation (structure only; queue ops added in Segment 3).
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from google.cloud import firestore
    _FS_AVAILABLE = True
except ImportError:
    _FS_AVAILABLE = False
    logger.warning("google-cloud-firestore not available — Firestore ops will be no-ops")


class FirestoreClient:
    """
    All reads and writes are scoped by tenant_id.
    Collections:
        review_queue   — blocked decisions pending human review
        interventions  — real-time intervention log for dashboard feed
    """

    def __init__(self, project: Optional[str] = None):
        self.project = project or os.getenv("GCP_PROJECT", "fairwall-2026")
        self._client: Optional[object] = None

    def _get_client(self):
        if self._client is None:
            if not _FS_AVAILABLE:
                raise RuntimeError("google-cloud-firestore not installed")
            self._client = firestore.Client(project=self.project)
        return self._client

    # ── review queue ──────────────────────────────────────────────────────────

    def add_to_review_queue(
        self,
        *,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        features: dict,
        sensitive_attrs: dict,
        original_prediction: int,
        trust_score: Optional[float],
        explanation: Optional[str] = None,
    ) -> str:
        """
        Add a blocked prediction to the human review queue.
        Every document includes tenant_id as a top-level field.
        Returns the Firestore document ID.
        """
        doc_id = f"review_{uuid.uuid4().hex[:8]}"
        doc = {
            "doc_id": doc_id,
            "prediction_id": prediction_id,
            "tenant_id": tenant_id,           # REQUIRED — used for all queries
            "domain": domain,
            "features": features,
            "sensitive_attrs": sensitive_attrs,
            "original_prediction": original_prediction,
            "trust_score": trust_score,
            "explanation": explanation,
            "status": "pending",              # pending | resolved
            "resolved_by": None,
            "resolution_note": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None,
        }
        try:
            db = self._get_client()
            db.collection("review_queue").document(doc_id).set(doc)
            return doc_id
        except Exception as e:
            logger.error("Firestore add_to_review_queue failed: %s", e)
            return doc_id  # return ID even on failure for audit trail

    def get_review_queue(
        self,
        tenant_id: str,
        domain: Optional[str] = None,
        status: str = "pending",
        limit: int = 50,
    ) -> list[dict]:
        """
        Fetch review queue items for a tenant.
        Always filters by tenant_id — never returns cross-tenant data.
        """
        try:
            db = self._get_client()
            query = (
                db.collection("review_queue")
                .where("tenant_id", "==", tenant_id)
                .where("status", "==", status)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            if domain:
                query = query.where("domain", "==", domain)
            return [doc.to_dict() for doc in query.stream()]
        except Exception as e:
            logger.error("Firestore get_review_queue failed: %s", e)
            return []

    def resolve_review_item(
        self,
        doc_id: str,
        tenant_id: str,
        resolved_by: str,
        resolution_note: Optional[str] = None,
    ) -> bool:
        """
        Mark a review queue item as resolved.
        Verifies tenant_id matches before updating — prevents cross-tenant modification.
        """
        try:
            db = self._get_client()
            ref = db.collection("review_queue").document(doc_id)
            doc = ref.get()
            if not doc.exists:
                logger.warning("resolve_review_item: doc %s not found", doc_id)
                return False
            if doc.to_dict().get("tenant_id") != tenant_id:
                logger.warning(
                    "resolve_review_item: tenant mismatch for doc %s", doc_id
                )
                return False
            ref.update({
                "status": "resolved",
                "resolved_by": resolved_by,
                "resolution_note": resolution_note,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            })
            return True
        except Exception as e:
            logger.error("Firestore resolve_review_item failed: %s", e)
            return False

    # ── real-time intervention feed ───────────────────────────────────────────

    def log_intervention_event(
        self,
        *,
        intervention_id: str,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        severity: str,
        action: str,
        trust_score: Optional[float],
        explanation: Optional[str],
    ) -> None:
        """
        Write a lightweight intervention event for the real-time dashboard feed.
        Dashboard polls GET /interventions which reads from this collection.
        """
        doc = {
            "intervention_id": intervention_id,
            "prediction_id": prediction_id,
            "tenant_id": tenant_id,           # REQUIRED
            "domain": domain,
            "severity": severity,
            "action": action,
            "trust_score": trust_score,
            "explanation": explanation,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            db = self._get_client()
            db.collection("interventions").document(intervention_id).set(doc)
        except Exception as e:
            logger.error("Firestore log_intervention_event failed: %s", e)

    def get_intervention_feed(
        self,
        tenant_id: str,
        domain: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Fetch recent intervention events for the dashboard feed.
        Always scoped by tenant_id.
        """
        try:
            db = self._get_client()
            query = (
                db.collection("interventions")
                .where("tenant_id", "==", tenant_id)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            if domain:
                query = query.where("domain", "==", domain)
            return [doc.to_dict() for doc in query.stream()]
        except Exception as e:
            logger.error("Firestore get_intervention_feed failed: %s", e)
            return []


# ── singleton ──────────────────────────────────────────────────────────────────
_fs_client: Optional[FirestoreClient] = None


def get_fs_client() -> FirestoreClient:
    global _fs_client
    if _fs_client is None:
        _fs_client = FirestoreClient()
    return _fs_client


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.firestore_client import get_fs_client
# c = get_fs_client()
# print('Firestore client created for project:', c.project)
# "
