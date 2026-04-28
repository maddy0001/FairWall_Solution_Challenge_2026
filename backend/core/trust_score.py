"""
backend/core/trust_score.py
Aggregates MetricResult list into a single 0-100 AI Trust Score.
Null-safe — returns None during warm-up when metrics is None.
Segment 2 — Bias Detection Engine.
"""

from dataclasses import dataclass
from typing import Optional

from .metrics import MetricResult, MetricStatus, SeverityLevel


# ── weights must sum to 1.0 ───────────────────────────────────────────────────
METRIC_WEIGHTS: dict[str, float] = {
    "demographic_parity_diff": 0.40,   # highest weight — most direct legal risk
    "equal_opportunity_diff":  0.35,   # qualified candidates treated unequally
    "selection_rate_disparity": 0.25,  # 80% rule — EEOC benchmark
}


@dataclass
class TrustScoreResult:
    """
    Full trust score output — returned by GET /trust-score.
    trust_score is None during warm-up (window < min_window_for_scoring).
    """
    trust_score: Optional[int]     # 0-100, None if warming up
    status: str                    # "healthy" | "warning" | "critical" | "warming_up"
    severity_level: SeverityLevel  # NONE | LOW | MEDIUM | HIGH
    metrics: Optional[list[MetricResult]]
    window_size: int
    window_capacity: int
    min_for_scoring: int
    penalty_breakdown: Optional[dict]  # per-metric penalty for transparency


class TrustScoreCalculator:
    """
    Converts MetricResult list → single 0-100 AI Trust Score.

    Formula:
        score = 100
        for each metric:
            if FAIL: score -= weight * 100 * severity
            if WARN: score -= weight *  40 * severity
        score = clamp(round(score), 0, 100)

    Thresholds:
        80-100 → HEALTHY  (green)   severity=NONE
        50-79  → WARNING  (amber)   severity=LOW
        40-49  → WARNING  (amber)   severity=MEDIUM
        0-39   → CRITICAL (red)     severity=HIGH
    """

    def compute(
        self,
        metrics: Optional[list[MetricResult]],
        window_size: int,
        window_capacity: int,
        min_for_scoring: int,
    ) -> TrustScoreResult:
        """
        Main entry point.
        Pass metrics=None during warm-up — returns warming_up result.
        Pass metrics=[] when no sensitive attrs found — returns 100 (healthy).
        """
        if metrics is None:
            # Window still warming up
            return TrustScoreResult(
                trust_score=None,
                status="warming_up",
                severity_level=SeverityLevel.NONE,
                metrics=None,
                window_size=window_size,
                window_capacity=window_capacity,
                min_for_scoring=min_for_scoring,
                penalty_breakdown=None,
            )

        score = 100.0
        penalty_breakdown: dict[str, float] = {}

        for metric in metrics:
            weight = METRIC_WEIGHTS.get(metric.name, 0.10)  # default weight for unknown metrics

            if metric.status == MetricStatus.FAIL:
                penalty = weight * 100 * metric.severity
            elif metric.status == MetricStatus.WARN:
                penalty = weight * 40 * metric.severity
            else:
                penalty = 0.0

            score -= penalty
            penalty_breakdown[f"{metric.name}_{metric.affected_attribute or 'overall'}"] = round(penalty, 2)

        final_score = max(0, min(100, round(score)))
        status, severity_level = self._classify(final_score)

        return TrustScoreResult(
            trust_score=final_score,
            status=status,
            severity_level=severity_level,
            metrics=metrics,
            window_size=window_size,
            window_capacity=window_capacity,
            min_for_scoring=min_for_scoring,
            penalty_breakdown=penalty_breakdown,
        )

    def _classify(self, score: int) -> tuple[str, SeverityLevel]:
        if score >= 80:
            return "healthy", SeverityLevel.NONE
        elif score >= 50:
            return "warning", SeverityLevel.LOW
        elif score >= 40:
            return "warning", SeverityLevel.MEDIUM
        else:
            return "critical", SeverityLevel.HIGH


# ── singleton ──────────────────────────────────────────────────────────────────
_trust_calculator: Optional[TrustScoreCalculator] = None


def get_trust_calculator() -> TrustScoreCalculator:
    global _trust_calculator
    if _trust_calculator is None:
        _trust_calculator = TrustScoreCalculator()
    return _trust_calculator


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.trust_score import get_trust_calculator
# from backend.core.metrics import MetricResult, MetricStatus
# calc = get_trust_calculator()
#
# # Test warm-up
# r = calc.compute(None, 5, 30, 10)
# assert r.trust_score is None and r.status == 'warming_up'
#
# # Test healthy (no bias)
# r = calc.compute([], 15, 30, 10)
# assert r.trust_score == 100 and r.status == 'healthy'
#
# # Test with bias
# metrics = [
#     MetricResult('demographic_parity_diff', 0.35, 0.10, MetricStatus.FAIL, 'female', 'gender', 0.9, ''),
#     MetricResult('selection_rate_disparity', 0.45, 0.20, MetricStatus.FAIL, 'female', 'gender', 0.75, ''),
# ]
# r = calc.compute(metrics, 30, 30, 10)
# print(f'Score: {r.trust_score} Status: {r.status} Severity: {r.severity_level}')
# assert r.trust_score < 50, f'Expected critical, got {r.trust_score}'
# print('ALL TESTS PASSED')
# "
