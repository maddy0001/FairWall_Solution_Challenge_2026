"""
backend/core/bigquery_client.py
Thin wrapper around Google BigQuery — all operations are tenant-scoped.
Segment 1 — Foundation.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── lazy import so app still starts without GCP credentials during local dev ──
try:
    from google.cloud import bigquery
    _BQ_AVAILABLE = True
except ImportError:
    _BQ_AVAILABLE = False
    logger.warning("google-cloud-bigquery not installed — BigQuery operations will be no-ops")


class BigQueryClient:
    """
    Handles all BigQuery inserts and queries for FairWall.
    Every row written includes tenant_id.
    Every query filters by tenant_id.
    """

    def __init__(self, project: Optional[str] = None, dataset: Optional[str] = None):
        self.project = project or os.getenv("GCP_PROJECT", "fairwall-2026")
        self.dataset = dataset or os.getenv("BQ_DATASET", "fairwall_logs")
        self._client: Optional[Any] = None

    def _get_client(self):
        """Lazy-init BigQuery client so app starts without credentials in dev."""
        if self._client is None:
            if not _BQ_AVAILABLE:
                raise RuntimeError("google-cloud-bigquery is not installed")
            self._client = bigquery.Client(project=self.project)
        return self._client

    def _table_ref(self, table_name: str) -> str:
        return f"{self.project}.{self.dataset}.{table_name}"

    # ── predictions table ─────────────────────────────────────────────────────

    def insert_prediction(
        self,
        *,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        features: dict,          # stored as JSON string — REQUIRED for replay engine
        sensitive_attrs: dict,
        prediction: int,         # 0 or 1
        confidence: float,
        flagged: bool = False,
        intervention_type: Optional[str] = None,
        trust_score: Optional[float] = None,
    ) -> bool:
        """
        Insert one prediction record.
        features is stored as a JSON string — the replay engine (M8) reads it back.
        Returns True on success, False on failure (logs error, does not raise).
        """
        row = {
            "prediction_id": prediction_id,
            "tenant_id": tenant_id,
            "domain": domain,
            "features": json.dumps(features),        # full JSON — replay depends on this
            "sensitive_attrs": json.dumps(sensitive_attrs),
            "prediction": prediction,
            "confidence": round(confidence, 6),
            "flagged": flagged,
            "intervention_type": intervention_type,
            "trust_score": trust_score,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._insert_rows("predictions", [row])

    def get_prediction(self, prediction_id: str, tenant_id: str) -> Optional[dict]:
        """
        Fetch a single prediction record by ID, scoped to tenant.
        Used by replay engine (M8) to load original features.
        Returns None if not found.
        """
        query = f"""
            SELECT *
            FROM `{self._table_ref("predictions")}`
            WHERE prediction_id = @prediction_id
              AND tenant_id = @tenant_id
            LIMIT 1
        """
        params = [
            bigquery.ScalarQueryParameter("prediction_id", "STRING", prediction_id),
            bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id),
        ]
        rows = self._run_query(query, params)
        if not rows:
            return None
        row = rows[0]
        result = dict(row)
        # Deserialise JSON fields
        result["features"] = json.loads(result["features"])
        result["sensitive_attrs"] = json.loads(result["sensitive_attrs"])
        return result

    # ── interventions table ───────────────────────────────────────────────────

    def insert_intervention(
        self,
        *,
        intervention_id: str,
        prediction_id: str,
        tenant_id: str,
        domain: str,
        severity: str,
        action: str,
        trust_score: Optional[float],
        explanation: Optional[str] = None,
    ) -> bool:
        """Insert one intervention record. Always includes tenant_id."""
        row = {
            "intervention_id": intervention_id,
            "prediction_id": prediction_id,
            "tenant_id": tenant_id,
            "domain": domain,
            "severity": severity,
            "action": action,
            "trust_score": trust_score,
            "explanation": explanation,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._insert_rows("interventions", [row])

    def get_interventions(
        self,
        tenant_id: str,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch recent interventions for a tenant, optionally filtered by domain."""
        domain_filter = "AND domain = @domain" if domain else ""
        params = [bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id)]
        if domain:
            params.append(bigquery.ScalarQueryParameter("domain", "STRING", domain))

        query = f"""
            SELECT *
            FROM `{self._table_ref("interventions")}`
            WHERE tenant_id = @tenant_id
            {domain_filter}
            ORDER BY created_at DESC
            LIMIT {int(limit)}
        """
        return [dict(r) for r in self._run_query(query, params)]

    # ── internal helpers ──────────────────────────────────────────────────────

    def _insert_rows(self, table_name: str, rows: list[dict]) -> bool:
        try:
            client = self._get_client()
            table_ref = self._table_ref(table_name)
            errors = client.insert_rows_json(table_ref, rows)
            if errors:
                logger.error("BigQuery insert errors for %s: %s", table_name, errors)
                return False
            return True
        except Exception as e:
            logger.error("BigQuery insert_rows failed for %s: %s", table_name, e)
            return False

    def _run_query(self, query: str, params: list) -> list:
        try:
            client = self._get_client()
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            result = client.query(query, job_config=job_config).result()
            return list(result)
        except Exception as e:
            logger.error("BigQuery query failed: %s", e)
            return []


# ── singleton ─────────────────────────────────────────────────────────────────
# Imported by logger.py and other modules
_bq_client: Optional[BigQueryClient] = None


def get_bq_client() -> BigQueryClient:
    global _bq_client
    if _bq_client is None:
        _bq_client = BigQueryClient()
    return _bq_client


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.bigquery_client import get_bq_client
# c = get_bq_client()
# print('BQ client created for project:', c.project)
# "
