"""
backend/core/bias_engine.py
Computes Fairlearn fairness metrics on every prediction using SlidingWindowBuffer.
Returns None during warm-up (window < min_window_for_scoring).
Segment 2 — Bias Detection Engine.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
    MetricFrame,
    selection_rate,
)

from .metrics import (
    MetricResult,
    MetricStatus,
    SeverityLevel,
    compute_severity,
    compute_status,
    make_description,
)
from .profile_loader import DomainProfile, FairnessThresholds
from .sliding_window import PredictionRecord, SlidingWindowBuffer, get_window_buffer

logger = logging.getLogger(__name__)


class BiasEngine:
    """
    Manages the sliding window buffer and computes fairness metrics.

    Called after every prediction in POST /predict.
    Returns None if window is still warming up.
    Returns list[MetricResult] once enough data is collected.
    """

    def __init__(self, buffer: Optional[SlidingWindowBuffer] = None):
        self._buffer = buffer or get_window_buffer()

    def add_prediction(
        self,
        tenant_id: str,
        domain: str,
        prediction_id: str,
        prediction: int,
        sensitive_attrs: dict,
        profile: DomainProfile,
        true_label: Optional[int] = None,
    ) -> Optional[list[MetricResult]]:
        """
        Add one prediction to the sliding window and compute metrics.

        Returns:
            None  — window still warming up (< min_window_for_scoring)
            list  — current MetricResult list (may be empty if no sensitive attr data)
        """
        record = PredictionRecord(
            prediction_id=prediction_id,
            prediction=prediction,
            sensitive_attrs=sensitive_attrs,
            true_label=true_label,
        )

        window = self._buffer.push(
            tenant_id=tenant_id,
            domain=domain,
            record=record,
            window_size=profile.sliding_window_size,
        )

        current_size = len(window)

        if current_size < profile.min_window_for_scoring:
            logger.debug(
                "Window warming up: %d/%d for tenant=%s domain=%s",
                current_size, profile.min_window_for_scoring, tenant_id, domain,
            )
            return None  # warming up — callers must handle None safely

        return self._compute_metrics(window, profile, tenant_id, domain)

    def _compute_metrics(
        self,
        window: list[PredictionRecord],
        profile: DomainProfile,
        tenant_id: str,
        domain: str,
    ) -> list[MetricResult]:
        """
        Compute all 3 fairness metrics on the current window snapshot.
        Iterates over every sensitive attribute listed in the profile.
        """
        if not window:
            return []

        results: list[MetricResult] = []
        thresholds = profile.fairness_thresholds

        # Build arrays from the window
        y_pred = np.array([r.prediction for r in window])

        # Use true_label if available; fall back to y_pred for DPD/SRD
        # (Equal Opportunity needs true labels — skipped if unavailable)
        y_true = np.array([
            r.true_label if r.true_label is not None else r.prediction
            for r in window
        ])

        # Determine which sensitive attributes are actually present in this window
        all_attrs_in_window: set[str] = set()
        for r in window:
            all_attrs_in_window.update(r.sensitive_attrs.keys())

        # Only compute metrics for attributes that are in the profile AND in the window
        attrs_to_check = [
            attr for attr in profile.sensitive_attributes
            if attr in all_attrs_in_window
        ]

        if not attrs_to_check:
            logger.debug(
                "No matching sensitive attributes in window for domain=%s. "
                "Profile attrs: %s, Window attrs: %s",
                domain, profile.sensitive_attributes[:5], list(all_attrs_in_window)[:5],
            )
            return []

        for attr in attrs_to_check:
            attr_results = self._compute_for_attribute(
                attr=attr,
                window=window,
                y_pred=y_pred,
                y_true=y_true,
                thresholds=thresholds,
            )
            results.extend(attr_results)

        # De-duplicate: if multiple attributes all pass, keep all.
        # If multiple fail, keep worst (highest severity) per metric type.
        results = _deduplicate_results(results)

        logger.debug(
            "Metrics computed: tenant=%s domain=%s window=%d attrs=%s results=%d",
            tenant_id, domain, len(window), attrs_to_check, len(results),
        )

        return results

    def _compute_for_attribute(
        self,
        attr: str,
        window: list[PredictionRecord],
        y_pred: np.ndarray,
        y_true: np.ndarray,
        thresholds: FairnessThresholds,
    ) -> list[MetricResult]:
        """Compute all metrics for one sensitive attribute."""
        results = []

        # Build sensitive feature array for this attribute
        sensitive_feature = np.array([
            r.sensitive_attrs.get(attr, "unknown") for r in window
        ])

        groups = np.unique(sensitive_feature)
        if len(groups) < 2:
            # Only one group present — can't compute disparity
            return []

        try:
            # ── Metric 1: Demographic Parity Difference ───────────────────
            dpd = self._safe_demographic_parity(y_pred, sensitive_feature)
            if dpd is not None:
                # Find worst affected group
                mf_dpd = MetricFrame(
                    metrics=selection_rate,
                    y_true=y_true,
                    y_pred=y_pred,
                    sensitive_features=sensitive_feature,
                )
                rates = mf_dpd.by_group
                worst_group = str(rates.idxmin())

                status = compute_status(abs(dpd), thresholds.demographic_parity_diff, "demographic_parity_diff")
                severity = compute_severity(abs(dpd), thresholds.demographic_parity_diff, "demographic_parity_diff")
                results.append(MetricResult(
                    name="demographic_parity_diff",
                    value=round(dpd, 4),
                    threshold=thresholds.demographic_parity_diff,
                    status=status,
                    affected_group=worst_group,
                    affected_attribute=attr,
                    severity=severity,
                    description=make_description(
                        "demographic_parity_diff", abs(dpd),
                        thresholds.demographic_parity_diff,
                        status, worst_group, attr,
                    ),
                ))

            # ── Metric 2: Equal Opportunity Difference ────────────────────
            has_true_labels = any(r.true_label is not None for r in window)
            if has_true_labels:
                eod = self._safe_equal_opportunity(y_true, y_pred, sensitive_feature)
                if eod is not None:
                    status = compute_status(abs(eod), thresholds.equal_opportunity_diff, "equal_opportunity_diff")
                    severity = compute_severity(abs(eod), thresholds.equal_opportunity_diff, "equal_opportunity_diff")
                    results.append(MetricResult(
                        name="equal_opportunity_diff",
                        value=round(eod, 4),
                        threshold=thresholds.equal_opportunity_diff,
                        status=status,
                        affected_group=None,
                        affected_attribute=attr,
                        severity=severity,
                        description=make_description(
                            "equal_opportunity_diff", abs(eod),
                            thresholds.equal_opportunity_diff,
                            status, None, attr,
                        ),
                    ))

            # ── Metric 3: Selection Rate Disparity ────────────────────────
            srd = self._safe_selection_rate_disparity(y_pred, sensitive_feature)
            if srd is not None:
                mf_srd = MetricFrame(
                    metrics=selection_rate,
                    y_true=y_true,
                    y_pred=y_pred,
                    sensitive_features=sensitive_feature,
                )
                rates_srd = mf_srd.by_group
                worst_srd_group = str(rates_srd.idxmin())

                status = compute_status(srd, thresholds.selection_rate_disparity, "selection_rate_disparity")
                severity = compute_severity(srd, thresholds.selection_rate_disparity, "selection_rate_disparity")
                results.append(MetricResult(
                    name="selection_rate_disparity",
                    value=round(srd, 4),
                    threshold=thresholds.selection_rate_disparity,
                    status=status,
                    affected_group=worst_srd_group,
                    affected_attribute=attr,
                    severity=severity,
                    description=make_description(
                        "selection_rate_disparity", srd,
                        thresholds.selection_rate_disparity,
                        status, worst_srd_group, attr,
                    ),
                ))

        except Exception as e:
            logger.warning("Metric computation failed for attr=%s: %s", attr, e)

        return results

    # ── safe wrappers (handle edge cases) ─────────────────────────────────────

    def _safe_demographic_parity(
        self, y_pred: np.ndarray, sensitive: np.ndarray
    ) -> Optional[float]:
        try:
            return float(demographic_parity_difference(
                y_true=np.ones_like(y_pred),  # DPD doesn't use y_true
                y_pred=y_pred,
                sensitive_features=sensitive,
            ))
        except Exception as e:
            logger.debug("demographic_parity_difference failed: %s", e)
            return None

    def _safe_equal_opportunity(
        self, y_true: np.ndarray, y_pred: np.ndarray, sensitive: np.ndarray
    ) -> Optional[float]:
        try:
            # Requires at least one positive true label per group
            if y_true.sum() < 2:
                return None
            return float(equalized_odds_difference(
                y_true=y_true,
                y_pred=y_pred,
                sensitive_features=sensitive,
            ))
        except Exception as e:
            logger.debug("equalized_odds_difference failed: %s", e)
            return None

    def _safe_selection_rate_disparity(
        self, y_pred: np.ndarray, sensitive: np.ndarray
    ) -> Optional[float]:
        """Returns min_group_rate / max_group_rate (1.0 = equal, 0.0 = worst)."""
        try:
            mf = MetricFrame(
                metrics=selection_rate,
                y_true=np.ones_like(y_pred),
                y_pred=y_pred,
                sensitive_features=sensitive,
            )
            rates = mf.by_group
            max_rate = float(rates.max())
            min_rate = float(rates.min())
            if max_rate == 0:
                return None
            return min_rate / max_rate
        except Exception as e:
            logger.debug("selection_rate_disparity failed: %s", e)
            return None

    def get_window_info(self, tenant_id: str, domain: str, profile: DomainProfile) -> dict:
        """Returns current window state — used by GET /trust-score."""
        size = self._buffer.size(tenant_id, domain)
        return {
            "window_size": size,
            "window_capacity": profile.sliding_window_size,
            "min_for_scoring": profile.min_window_for_scoring,
            "is_warming_up": size < profile.min_window_for_scoring,
        }


def _deduplicate_results(results: list[MetricResult]) -> list[MetricResult]:
    """
    When multiple sensitive attributes are checked, we may get duplicate
    metric types. Keep the worst (highest severity) result per metric name.
    """
    worst: dict[str, MetricResult] = {}
    for r in results:
        if r.name not in worst or r.severity > worst[r.name].severity:
            worst[r.name] = r
    return list(worst.values())


# ── singleton ──────────────────────────────────────────────────────────────────
_bias_engine: Optional[BiasEngine] = None


def get_bias_engine() -> BiasEngine:
    global _bias_engine
    if _bias_engine is None:
        _bias_engine = BiasEngine()
    return _bias_engine


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.bias_engine import get_bias_engine
# from backend.core.profile_loader import load_all_profiles
# engine = get_bias_engine()
# profiles = load_all_profiles()
# profile = profiles['hiring']
# # Send 15 biased predictions (women all rejected, men all accepted)
# for i in range(15):
#     gender = 'female' if i < 8 else 'male'
#     pred = 0 if gender == 'female' else 1
#     result = engine.add_prediction('demo','hiring',f'pred_{i}',pred,{'gender':gender},profile)
#     if result is not None:
#         print(f'Pred {i}: got {len(result)} metrics')
#         for r in result:
#             print(f'  {r.name}: {r.value:.3f} [{r.status}] severity={r.severity}')
# "
