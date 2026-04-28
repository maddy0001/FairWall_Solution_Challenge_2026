"""
backend/core/sliding_window.py
Per-(tenant_id, domain) ring buffer using Python built-in collections.deque.
NO external packages — only stdlib.
Segment 2 — Bias Detection Engine.
"""

from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PredictionRecord:
    """
    One prediction stored in the sliding window.
    Only the fields needed for Fairlearn metric computation are kept.
    """
    prediction_id: str
    prediction: int              # 0 = rejected/denied, 1 = accepted/approved
    sensitive_attrs: dict        # e.g. {"gender": "female", "age_group": "senior"}
    true_label: Optional[int]    # ground truth if available; None if not


class SlidingWindowBuffer:
    """
    Per-(tenant_id, domain) ring buffer of PredictionRecord objects.

    Uses collections.deque(maxlen=N) so old records automatically
    drop off when the buffer is full — O(1) push, O(1) pop.

    Key design points:
    - One deque per (tenant_id, domain) pair — tenants never share data
    - push() returns the current window snapshot as a plain list
    - size() lets callers check warm-up state before computing metrics
    - Thread-safe enough for single-worker FastAPI (uvicorn default)
    """

    def __init__(self, default_window_size: int = 30):
        self.default_window_size = default_window_size
        # key: (tenant_id, domain) → deque of PredictionRecord
        self._buffers: dict[tuple[str, str], deque] = defaultdict(
            lambda: deque(maxlen=self.default_window_size)
        )
        # track per-(tenant,domain) window size in case profiles differ
        self._window_sizes: dict[tuple[str, str], int] = {}

    def push(
        self,
        tenant_id: str,
        domain: str,
        record: PredictionRecord,
        window_size: Optional[int] = None,
    ) -> list[PredictionRecord]:
        """
        Add a record to the buffer for (tenant_id, domain).
        If window_size differs from the current maxlen, the deque is resized.
        Returns the current window as a plain list (safe to iterate repeatedly).
        """
        key = (tenant_id, domain)

        # Resize if the profile specifies a different window size
        if window_size is not None and self._window_sizes.get(key) != window_size:
            existing = list(self._buffers[key])
            self._buffers[key] = deque(existing, maxlen=window_size)
            self._window_sizes[key] = window_size

        self._buffers[key].append(record)
        return list(self._buffers[key])

    def get(self, tenant_id: str, domain: str) -> list[PredictionRecord]:
        """Return current window snapshot without modifying the buffer."""
        return list(self._buffers[(tenant_id, domain)])

    def size(self, tenant_id: str, domain: str) -> int:
        """Return current number of records in the window."""
        return len(self._buffers[(tenant_id, domain)])

    def clear(self, tenant_id: str, domain: str) -> None:
        """Clear a tenant+domain buffer — used in tests and demo resets."""
        key = (tenant_id, domain)
        if key in self._buffers:
            self._buffers[key].clear()


# ── singleton — one buffer shared across all requests ─────────────────────────
_window_buffer: Optional[SlidingWindowBuffer] = None


def get_window_buffer() -> SlidingWindowBuffer:
    global _window_buffer
    if _window_buffer is None:
        _window_buffer = SlidingWindowBuffer()
    return _window_buffer


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.sliding_window import SlidingWindowBuffer, PredictionRecord
# buf = SlidingWindowBuffer(default_window_size=5)
# for i in range(7):
#     r = PredictionRecord(f'pred_{i}', i%2, {'gender': 'female' if i%2==0 else 'male'}, None)
#     window = buf.push('demo', 'hiring', r, window_size=5)
#     print(f'push {i}: window_size={len(window)}')
# assert buf.size('demo', 'hiring') == 5, 'maxlen not enforced'
# assert buf.size('other_tenant', 'hiring') == 0, 'tenant isolation broken'
# print('ALL TESTS PASSED')
# "
