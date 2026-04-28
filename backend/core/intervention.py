"""
backend/core/intervention.py
SeverityClassifier + 3 intervention handlers: FlagHandler, ThresholdAdjuster,
BlockAndRouteHandler.
Segment 3 — Intervention Engine.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from .metrics import MetricResult, MetricStatus, SeverityLevel
from .trust_score import TrustScoreResult

logger = logging.getLogger(__name__)


# ── Intervention result ───────────────────────────────────────────────────────

@dataclass
class InterventionResult:
    """
    Output of the Intervention Engine for one prediction.
    Returned by DecisionRouter.route() and consumed by POST /predict.
    """
    original_prediction: int           # what the AI model said
    final_prediction: int              # what FairWall releases (may differ for MEDIUM)
    final_decision: str                # "released" | "flagged" | "adjusted" | "blocked"
    severity_level: SeverityLevel
    action_taken: str                  # "none" | "flag_only" | "adjust_threshold" | "block_and_review"
    flagged: bool
    blocked: bool
    threshold_adjusted: bool
    adjustment_delta: float            # +0.1 for MEDIUM — how much threshold shifted
    affected_attribute: Optional[str]  # which sensitive attr triggered the intervention
    affected_group: Optional[str]      # which group is disadvantaged
    review_queue_id: Optional[str]     # Firestore doc ID when blocked (set by router)
    explanation: Optional[str]         # filled in Segment 4 by Gemma


# ── Severity classifier ───────────────────────────────────────────────────────

class SeverityClassifier:
    """
    Maps TrustScoreResult → SeverityLevel.
    Uses trust_score thresholds defined in CLAUDE.md:
        80-100 → NONE
        50-79  → LOW
        40-49  → MEDIUM
        0-39   → HIGH

    Also escalates severity if multiple metrics fail simultaneously,
    regardless of the numeric score.
    """

    def classify(self, trust_result: TrustScoreResult) -> SeverityLevel:
        """Primary entry point — returns severity for the current trust state."""

        # During warm-up, no intervention
        if trust_result.trust_score is None:
            return SeverityLevel.NONE

        score = trust_result.trust_score

        # Count hard FAILs across metrics
        fail_count = 0
        if trust_result.metrics:
            fail_count = sum(
                1 for m in trust_result.metrics
                if m.status == MetricStatus.FAIL
            )

        # Escalate: 2+ simultaneous metric failures → always HIGH
        if fail_count >= 2:
            return SeverityLevel.HIGH

        # Otherwise use numeric score
        if score >= 80:
            return SeverityLevel.NONE
        elif score >= 50:
            return SeverityLevel.LOW
        elif score >= 40:
            return SeverityLevel.MEDIUM
        else:
            return SeverityLevel.HIGH

    def get_worst_metric(
        self, trust_result: TrustScoreResult
    ) -> Optional[MetricResult]:
        """Return the metric with the highest severity (worst bias)."""
        if not trust_result.metrics:
            return None
        return max(trust_result.metrics, key=lambda m: m.severity)


# ── Intervention handlers ─────────────────────────────────────────────────────

class FlagHandler:
    """
    LOW severity — flag the decision and release it.
    The AI decision passes through but is marked for monitoring.
    HR dashboard shows it in the intervention feed.
    """

    def handle(
        self,
        original_prediction: int,
        trust_result: TrustScoreResult,
    ) -> InterventionResult:
        worst = _get_worst(trust_result)
        logger.info(
            "FlagHandler: flagging prediction (score=%s, attr=%s)",
            trust_result.trust_score,
            worst.affected_attribute if worst else None,
        )
        return InterventionResult(
            original_prediction=original_prediction,
            final_prediction=original_prediction,   # not changed
            final_decision="flagged",
            severity_level=SeverityLevel.LOW,
            action_taken="flag_only",
            flagged=True,
            blocked=False,
            threshold_adjusted=False,
            adjustment_delta=0.0,
            affected_attribute=worst.affected_attribute if worst else None,
            affected_group=worst.affected_group if worst else None,
            review_queue_id=None,
            explanation=None,
        )


class ThresholdAdjuster:
    """
    MEDIUM severity — adjust classification threshold in favour of the
    disadvantaged group and flip the prediction if the model was on the boundary.

    Logic:
    - If original_prediction == 0 (rejected/denied) AND confidence indicates
      the model was uncertain (close to boundary), flip to 1 (accepted).
    - If confidence is high and model was clearly rejecting, flag but release.
    - The +0.1 adjustment is a proxy: in a real system you'd re-run inference
      with a lowered decision threshold. Here we simulate it by flipping
      low-confidence rejections.
    """

    ADJUSTMENT_DELTA = 0.10
    CONFIDENCE_BOUNDARY = 0.65   # below this = "uncertain" rejection → flip

    def handle(
        self,
        original_prediction: int,
        trust_result: TrustScoreResult,
        confidence: float = 1.0,
    ) -> InterventionResult:
        worst = _get_worst(trust_result)
        attr = worst.affected_attribute if worst else None
        group = worst.affected_group if worst else None

        # Flip low-confidence rejections
        if original_prediction == 0 and confidence <= self.CONFIDENCE_BOUNDARY:
            final_pred = 1
            decision = "adjusted"
            adjusted = True
            logger.info(
                "ThresholdAdjuster: flipped rejection → acceptance (confidence=%.2f, attr=%s)",
                confidence, attr,
            )
        else:
            final_pred = original_prediction
            decision = "flagged"
            adjusted = False
            logger.info(
                "ThresholdAdjuster: high-confidence rejection — flagging only (confidence=%.2f)",
                confidence,
            )

        return InterventionResult(
            original_prediction=original_prediction,
            final_prediction=final_pred,
            final_decision=decision,
            severity_level=SeverityLevel.MEDIUM,
            action_taken="adjust_threshold",
            flagged=True,
            blocked=False,
            threshold_adjusted=adjusted,
            adjustment_delta=self.ADJUSTMENT_DELTA if adjusted else 0.0,
            affected_attribute=attr,
            affected_group=group,
            review_queue_id=None,
            explanation=None,
        )


class BlockAndRouteHandler:
    """
    HIGH severity — block the decision entirely.
    The prediction is NOT released to the end user.
    A review queue entry is created in Firestore.
    The decision waits for a human reviewer.
    """

    def handle(
        self,
        original_prediction: int,
        trust_result: TrustScoreResult,
    ) -> InterventionResult:
        worst = _get_worst(trust_result)
        attr = worst.affected_attribute if worst else None
        group = worst.affected_group if worst else None

        logger.warning(
            "BlockAndRouteHandler: BLOCKING prediction — score=%s attr=%s group=%s",
            trust_result.trust_score, attr, group,
        )

        return InterventionResult(
            original_prediction=original_prediction,
            final_prediction=-1,           # -1 = blocked, not released
            final_decision="blocked",
            severity_level=SeverityLevel.HIGH,
            action_taken="block_and_review",
            flagged=True,
            blocked=True,
            threshold_adjusted=False,
            adjustment_delta=0.0,
            affected_attribute=attr,
            affected_group=group,
            review_queue_id=None,          # set by DecisionRouter after Firestore write
            explanation=None,              # set by Gemma in Segment 4
        )


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_worst(trust_result: TrustScoreResult) -> Optional[MetricResult]:
    """Return the metric with the highest severity."""
    if not trust_result.metrics:
        return None
    return max(trust_result.metrics, key=lambda m: m.severity)


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.intervention import SeverityClassifier, FlagHandler, BlockAndRouteHandler
# from backend.core.metrics import MetricResult, MetricStatus, SeverityLevel
# from backend.core.trust_score import TrustScoreResult
#
# classifier = SeverityClassifier()
#
# # Test None (warming up)
# r = TrustScoreResult(None,'warming_up',SeverityLevel.NONE,None,5,30,10,None)
# assert classifier.classify(r) == SeverityLevel.NONE
#
# # Test HIGH from score
# r = TrustScoreResult(35,'critical',SeverityLevel.HIGH,[],30,30,10,{})
# assert classifier.classify(r) == SeverityLevel.HIGH
#
# # Test LOW
# r = TrustScoreResult(72,'warning',SeverityLevel.LOW,[],30,30,10,{})
# assert classifier.classify(r) == SeverityLevel.LOW
#
# print('intervention.py — ALL TESTS PASSED')
# "
