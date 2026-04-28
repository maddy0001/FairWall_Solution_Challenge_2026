"""
backend/core/router.py
DecisionRouter — maps severity to the correct handler, writes to
Firestore (production) + in-memory store (dev fallback), returns InterventionResult.
"""

import logging
from typing import Optional

from .firestore_client import get_fs_client
from .in_memory_store import (
    add_intervention as mem_add_intervention,
    add_review_item  as mem_add_review,
)
from .intervention import (
    BlockAndRouteHandler,
    FlagHandler,
    InterventionResult,
    SeverityClassifier,
    ThresholdAdjuster,
)
from .logger import get_prediction_logger, generate_intervention_id
from .metrics import SeverityLevel
from .trust_score import TrustScoreResult

logger = logging.getLogger(__name__)

_classifier    = SeverityClassifier()
_flag_handler  = FlagHandler()
_adjust_handler = ThresholdAdjuster()
_block_handler = BlockAndRouteHandler()


class DecisionRouter:

    def route(
        self,
        *,
        prediction_id: str,
        original_prediction: int,
        confidence: float,
        trust_result: TrustScoreResult,
        tenant_id: str,
        domain: str,
        features: dict,
        sensitive_attrs: dict,
    ) -> InterventionResult:

        severity = _classifier.classify(trust_result)

        # No intervention during warm-up or healthy state
        if severity == SeverityLevel.NONE:
            return InterventionResult(
                original_prediction=original_prediction,
                final_prediction=original_prediction,
                final_decision="released",
                severity_level=SeverityLevel.NONE,
                action_taken="none",
                flagged=False,
                blocked=False,
                threshold_adjusted=False,
                adjustment_delta=0.0,
                affected_attribute=None,
                affected_group=None,
                review_queue_id=None,
                explanation=None,
            )

        # Route to correct handler
        if severity == SeverityLevel.LOW:
            result = _flag_handler.handle(original_prediction, trust_result)

        elif severity == SeverityLevel.MEDIUM:
            result = _adjust_handler.handle(original_prediction, trust_result, confidence)

        else:  # HIGH → BLOCK
            result = _block_handler.handle(original_prediction, trust_result)

            # Write to Firestore review queue (production)
            review_id = self._write_review_queue(
                prediction_id=prediction_id,
                tenant_id=tenant_id,
                domain=domain,
                features=features,
                sensitive_attrs=sensitive_attrs,
                original_prediction=original_prediction,
                trust_result=trust_result,
            )
            result.review_queue_id = review_id

        # Write intervention to Firestore feed + in-memory fallback
        self._write_intervention_feed(
            prediction_id=prediction_id,
            tenant_id=tenant_id,
            domain=domain,
            result=result,
            trust_result=trust_result,
        )

        # Log to BigQuery audit log
        self._log_intervention_bq(
            prediction_id=prediction_id,
            tenant_id=tenant_id,
            domain=domain,
            result=result,
            trust_result=trust_result,
        )

        return result

    # ── helpers ───────────────────────────────────────────────────────────────

    def _write_review_queue(
        self,
        *,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        features: dict,
        sensitive_attrs: dict,
        original_prediction: int,
        trust_result: TrustScoreResult,
    ) -> Optional[str]:
        import uuid
        doc_id = f"review_{uuid.uuid4().hex[:8]}"
        ts = float(trust_result.trust_score) if trust_result.trust_score else None

        # Always write to in-memory store (works without GCP)
        mem_add_review(
            doc_id=doc_id,
            prediction_id=prediction_id,
            tenant_id=tenant_id,
            domain=domain,
            features=features,
            sensitive_attrs=sensitive_attrs,
            original_prediction=original_prediction,
            trust_score=ts,
        )

        # Also write to Firestore if available
        try:
            fs = get_fs_client()
            fs.add_to_review_queue(
                prediction_id=prediction_id,
                tenant_id=tenant_id,
                domain=domain,
                features=features,
                sensitive_attrs=sensitive_attrs,
                original_prediction=original_prediction,
                trust_score=ts,
            )
        except Exception as e:
            logger.debug("Firestore review queue unavailable: %s", e)

        return doc_id

    def _write_intervention_feed(
        self,
        *,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        result: InterventionResult,
        trust_result: TrustScoreResult,
    ) -> None:
        intv_id = generate_intervention_id()
        ts = float(trust_result.trust_score) if trust_result.trust_score else None

        # Always write to in-memory store (works without GCP)
        mem_add_intervention(
            intervention_id=intv_id,
            prediction_id=prediction_id,
            tenant_id=tenant_id,
            domain=domain,
            severity=result.severity_level.value,
            action=result.action_taken,
            trust_score=ts,
            explanation=None,
            affected_attribute=result.affected_attribute,
            affected_group=result.affected_group,
        )

        # Also write to Firestore if available
        try:
            fs = get_fs_client()
            fs.log_intervention_event(
                intervention_id=intv_id,
                prediction_id=prediction_id,
                tenant_id=tenant_id,
                domain=domain,
                severity=result.severity_level.value,
                action=result.action_taken,
                trust_score=ts,
                explanation=None,
                affected_attribute=result.affected_attribute,
                affected_group=result.affected_group,
            )
        except Exception as e:
            logger.debug("Firestore intervention feed unavailable: %s", e)

    def _log_intervention_bq(
        self,
        *,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        result: InterventionResult,
        trust_result: TrustScoreResult,
    ) -> None:
        try:
            pl = get_prediction_logger()
            pl.log_intervention(
                prediction_id=prediction_id,
                tenant_id=tenant_id,
                domain=domain,
                severity=result.severity_level.value,
                action=result.action_taken,
                trust_score=float(trust_result.trust_score) if trust_result.trust_score else None,
                explanation=None,
            )
        except Exception as e:
            logger.debug("BigQuery intervention log unavailable: %s", e)


# ── singleton ──────────────────────────────────────────────────────────────────
_router: Optional[DecisionRouter] = None

def get_router() -> DecisionRouter:
    global _router
    if _router is None:
        _router = DecisionRouter()
    return _router
