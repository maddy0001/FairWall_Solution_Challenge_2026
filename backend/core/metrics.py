"""
backend/core/metrics.py
MetricResult dataclass and severity computation helpers.
Segment 2 — Bias Detection Engine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MetricStatus(str, Enum):
    PASS    = "pass"
    WARN    = "warn"
    FAIL    = "fail"


class SeverityLevel(str, Enum):
    NONE    = "none"      # all metrics pass — no intervention needed
    LOW     = "low"       # trust score 60-79 — flag only
    MEDIUM  = "medium"    # trust score 40-59 — threshold adjustment
    HIGH    = "high"      # trust score 0-39  — block + human review


@dataclass
class MetricResult:
    """
    Result for a single fairness metric computation.
    Produced by BiasEngine, consumed by TrustScoreCalculator and InterventionEngine.
    """
    name: str                      # e.g. "demographic_parity_diff"
    value: float                   # computed metric value
    threshold: float               # from domain profile
    status: MetricStatus           # PASS / WARN / FAIL
    affected_group: Optional[str]  # e.g. "female" or "age_group=senior"
    affected_attribute: Optional[str]  # e.g. "gender"
    severity: float                # 0.0–1.0, how far beyond threshold
    description: str               # human-readable explanation for Gemma prompt


def compute_status(value: float, threshold: float, metric_name: str) -> MetricStatus:
    """
    Classify a metric value as PASS / WARN / FAIL.

    Rules per metric type:
    - demographic_parity_diff and equal_opportunity_diff:
        lower is better (0 = perfectly fair)
        PASS  if value <= threshold
        WARN  if value <= threshold * 2
        FAIL  if value >  threshold * 2

    - selection_rate_disparity:
        higher is better (1.0 = perfectly equal rates)
        PASS  if value >= (1 - threshold)
        WARN  if value >= (1 - threshold * 2)
        FAIL  if value <  (1 - threshold * 2)
    """
    if metric_name == "selection_rate_disparity":
        pass_boundary = 1.0 - threshold
        warn_boundary = 1.0 - threshold * 2
        if value >= pass_boundary:
            return MetricStatus.PASS
        elif value >= warn_boundary:
            return MetricStatus.WARN
        else:
            return MetricStatus.FAIL
    else:
        # demographic_parity_diff, equal_opportunity_diff — lower is better
        if value <= threshold:
            return MetricStatus.PASS
        elif value <= threshold * 2:
            return MetricStatus.WARN
        else:
            return MetricStatus.FAIL


def compute_severity(value: float, threshold: float, metric_name: str) -> float:
    """
    Returns severity in 0.0–1.0 range.
    0.0 = perfectly fair, 1.0 = maximally biased.
    Used by TrustScoreCalculator for weighted penalty computation.
    """
    if metric_name == "selection_rate_disparity":
        # value close to 0 = very biased, close to 1 = fair
        ideal = 1.0
        worst = 0.0
        severity = (ideal - value) / (ideal - worst)
    else:
        # value close to 0 = fair, value close to 1 = very biased
        severity = min(value / max(threshold * 3, 0.001), 1.0)

    return round(max(0.0, min(1.0, severity)), 4)


def make_description(
    metric_name: str,
    value: float,
    threshold: float,
    status: MetricStatus,
    affected_group: Optional[str],
    affected_attribute: Optional[str],
) -> str:
    """
    Build a human-readable description for use in Gemma prompts.
    """
    group_str = f"{affected_attribute}={affected_group}" if affected_group else "some group"
    pct = round(abs(value) * 100, 1)

    if metric_name == "demographic_parity_diff":
        base = f"Demographic Parity: {pct}% difference in approval rates"
        if status != MetricStatus.PASS:
            base += f" (threshold: {round(threshold*100,1)}%) — {group_str} is disadvantaged"
    elif metric_name == "equal_opportunity_diff":
        base = f"Equal Opportunity: {pct}% difference in approval rates for qualified candidates"
        if status != MetricStatus.PASS:
            base += f" — qualified {group_str} candidates are less likely to be approved"
    elif metric_name == "selection_rate_disparity":
        pct_rate = round(value * 100, 1)
        base = f"Selection Rate: lowest group selected at {pct_rate}% the rate of the top group"
        if status != MetricStatus.PASS:
            base += f" — {group_str} is the most disadvantaged group"
    else:
        base = f"{metric_name}: value={value:.4f}, threshold={threshold:.4f}"

    return base


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.metrics import compute_status, compute_severity, MetricStatus
# assert compute_status(0.05, 0.10, 'demographic_parity_diff') == MetricStatus.PASS
# assert compute_status(0.15, 0.10, 'demographic_parity_diff') == MetricStatus.WARN
# assert compute_status(0.30, 0.10, 'demographic_parity_diff') == MetricStatus.FAIL
# assert compute_status(0.85, 0.20, 'selection_rate_disparity') == MetricStatus.PASS
# assert compute_status(0.65, 0.20, 'selection_rate_disparity') == MetricStatus.WARN
# assert compute_status(0.40, 0.20, 'selection_rate_disparity') == MetricStatus.FAIL
# print('ALL TESTS PASSED')
# "
