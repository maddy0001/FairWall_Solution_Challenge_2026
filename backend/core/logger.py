"""
backend/core/logger.py
FairWall prediction logger — wraps BigQuery client.
Generates prediction IDs, stores full features JSON.
Segment 1 — Foundation.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .bigquery_client import get_bq_client

logger = logging.getLogger(__name__)


def generate_prediction_id() -> str:
    """Generate a unique prediction ID like 'pred_a3f2c1d8'."""
    return f"pred_{uuid.uuid4().hex[:8]}"


def generate_intervention_id() -> str:
    """Generate a unique intervention ID like 'intv_b7e4a2f1'."""
    return f"intv_{uuid.uuid4().hex[:8]}"


class PredictionLogger:
    """
    Logs every prediction that passes through FairWall to BigQuery.
    Stores the complete features dict as JSON — the replay engine (M8) depends on this.
    """

    def __init__(self):
        self._bq = get_bq_client()

    def log_prediction(
        self,
        *,
        tenant_id: str,
        domain: str,
        features: dict,           # FULL dict — must not be truncated
        sensitive_attrs: dict,
        prediction: int,
        confidence: float = 1.0,
        flagged: bool = False,
        intervention_type: Optional[str] = None,
        trust_score: Optional[float] = None,
        prediction_id: Optional[str] = None,
    ) -> str:
        """
        Write one prediction record to BigQuery.
        Returns the prediction_id (generated if not provided).
        Does NOT raise on failure — logs error and returns ID anyway.
        """
        pid = prediction_id or generate_prediction_id()

        success = self._bq.insert_prediction(
            prediction_id=pid,
            tenant_id=tenant_id,
            domain=domain,
            features=features,
            sensitive_attrs=sensitive_attrs,
            prediction=prediction,
            confidence=confidence,
            flagged=flagged,
            intervention_type=intervention_type,
            trust_score=trust_score,
        )

        if not success:
            logger.error(
                "Failed to log prediction %s for tenant %s domain %s",
                pid, tenant_id, domain,
            )

        return pid

    def log_intervention(
        self,
        *,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        severity: str,
        action: str,
        trust_score: Optional[float],
        explanation: Optional[str] = None,
    ) -> str:
        """
        Write one intervention record to BigQuery.
        Returns the intervention_id.
        """
        iid = generate_intervention_id()

        success = self._bq.insert_intervention(
            intervention_id=iid,
            prediction_id=prediction_id,
            tenant_id=tenant_id,
            domain=domain,
            severity=severity,
            action=action,
            trust_score=trust_score,
            explanation=explanation,
        )

        if not success:
            logger.error(
                "Failed to log intervention %s for prediction %s",
                iid, prediction_id,
            )

        return iid


# ── singleton ──────────────────────────────────────────────────────────────────
_prediction_logger: Optional[PredictionLogger] = None


def get_prediction_logger() -> PredictionLogger:
    global _prediction_logger
    if _prediction_logger is None:
        _prediction_logger = PredictionLogger()
    return _prediction_logger


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.logger import get_prediction_logger, generate_prediction_id
# pid = generate_prediction_id()
# print('Generated ID:', pid)
# print('Logger created:', get_prediction_logger())
# "
