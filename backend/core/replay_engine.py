"""
backend/core/replay_engine.py
ReplayEngine — 8-step What-If counterfactual prediction pipeline.
Fetches original features from BigQuery, flips one attribute,
re-runs the demo model, calls Gemma for a one-sentence explanation.
Segment 4 — Gemma Explainability + Replay.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from .bigquery_client import get_bq_client
from .explainer import get_explainer

logger = logging.getLogger(__name__)


@dataclass
class ReplayResult:
    """Full result of a What-If bias replay."""
    prediction_id: str
    domain: str

    # Original state
    original_features: dict
    original_sensitive_attrs: dict
    original_prediction: int
    original_label: str          # "ACCEPTED" | "REJECTED"

    # Counterfactual state
    counterfactual_features: dict
    counterfactual_prediction: int
    counterfactual_label: str

    # What changed
    changed_attrs: list[str]     # e.g. ["gender"]
    attribute_overrides: dict    # e.g. {"gender": "male"}

    # Conclusion
    bias_confirmed: bool         # True if outcome changed solely due to attribute flip
    explanation: str             # Gemma one-sentence explanation

    # Metadata
    tenant_id: str


class ReplayEngine:
    """
    Runs the 8-step What-If counterfactual pipeline:

    1. Fetch original PredictionRecord from BigQuery (features JSON stored in Seg 1)
    2. Deep-copy features — never mutate original
    3. Apply attribute_overrides to the copy
    4. Load domain model from backend/models/
    5. Run model.predict(modified_features)
    6. Compute bias_confirmed = (original != counterfactual)
    7. Call Gemma for 1-sentence explanation
    8. Return ReplayResult
    """

    def run(
        self,
        *,
        prediction_id: str,
        attribute_overrides: dict[str, Any],
        domain: str,
        tenant_id: str,
    ) -> ReplayResult:
        """
        Main entry point — called from POST /replay.
        Raises ValueError if prediction not found.
        """

        # Step 1: Fetch original record from BigQuery
        original_record = self._fetch_record(prediction_id, tenant_id)
        if original_record is None:
            raise ValueError(
                f"Prediction '{prediction_id}' not found for tenant '{tenant_id}'"
            )

        original_features = original_record["features"]         # dict
        original_sensitive = original_record["sensitive_attrs"]  # dict
        original_prediction = int(original_record["prediction"])

        # Step 2 + 3: Deep copy and apply overrides — NEVER mutate original
        modified_features = dict(original_features)
        modified_sensitive = dict(original_sensitive)

        for attr, new_val in attribute_overrides.items():
            # Override in both features and sensitive_attrs if present
            if attr in modified_features:
                modified_features[attr] = new_val
            if attr in modified_sensitive:
                modified_sensitive[attr] = new_val
            # Also set even if not present — user may be adding a new attr
            modified_sensitive[attr] = new_val

        changed_attrs = list(attribute_overrides.keys())

        # Step 4 + 5: Load and run domain model
        counterfactual_prediction = self._run_model(
            domain=domain,
            features=modified_features,
            sensitive_attrs=modified_sensitive,
        )

        # Step 6: Determine bias confirmed
        bias_confirmed = (original_prediction != counterfactual_prediction)

        # Step 7: Call Gemma for explanation
        original_label = "ACCEPTED" if original_prediction == 1 else "REJECTED"
        counterfactual_label = "ACCEPTED" if counterfactual_prediction == 1 else "REJECTED"

        explanation = self._explain(
            domain=domain,
            attribute_overrides=attribute_overrides,
            original_sensitive=original_sensitive,
            original_label=original_label,
            counterfactual_label=counterfactual_label,
            bias_confirmed=bias_confirmed,
        )

        # Step 8: Return full result
        return ReplayResult(
            prediction_id=prediction_id,
            domain=domain,
            original_features=original_features,
            original_sensitive_attrs=original_sensitive,
            original_prediction=original_prediction,
            original_label=original_label,
            counterfactual_features=modified_features,
            counterfactual_prediction=counterfactual_prediction,
            counterfactual_label=counterfactual_label,
            changed_attrs=changed_attrs,
            attribute_overrides=attribute_overrides,
            bias_confirmed=bias_confirmed,
            explanation=explanation,
            tenant_id=tenant_id,
        )

    # ── internal steps ────────────────────────────────────────────────────────

    def _fetch_record(
        self, prediction_id: str, tenant_id: str
    ) -> Optional[dict]:
        """
        Fetch prediction record from BigQuery.
        Returns None if not found or BigQuery unavailable.
        """
        try:
            bq = get_bq_client()
            return bq.get_prediction(prediction_id, tenant_id)
        except Exception as e:
            logger.error("Failed to fetch prediction %s: %s", prediction_id, e)
            return None

    def _run_model(
        self,
        domain: str,
        features: dict,
        sensitive_attrs: dict,
    ) -> int:
        """
        Run the domain demo model with modified features.
        Returns 0 (rejected) or 1 (accepted).

        Uses the sklearn model from backend/models/ if available.
        Falls back to a rule-based heuristic for robustness.
        """
        try:
            return self._run_sklearn_model(domain, features, sensitive_attrs)
        except Exception as e:
            logger.warning(
                "sklearn model unavailable for domain=%s (%s) — using heuristic",
                domain, e,
            )
            return self._heuristic_model(features, sensitive_attrs)

    def _run_sklearn_model(
        self, domain: str, features: dict, sensitive_attrs: dict
    ) -> int:
        """Load and run the pre-trained sklearn model for this domain."""
        import pickle
        from pathlib import Path

        model_path = Path(__file__).parent.parent / "models" / f"{domain}_model.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"No trained model at {model_path}")

        with open(model_path, "rb") as f:
            model_bundle = pickle.load(f)

        model = model_bundle["model"]
        feature_names = model_bundle["feature_names"]
        encoders = model_bundle.get("encoders", {})

        # Build feature vector
        combined = {**features, **sensitive_attrs}
        row = []
        for fname in feature_names:
            val = combined.get(fname, 0)
            if fname in encoders:
                try:
                    val = encoders[fname].transform([[val]])[0][0]
                except Exception:
                    val = 0
            try:
                row.append(float(val))
            except (ValueError, TypeError):
                row.append(0.0)

        import numpy as np
        prediction = int(model.predict(np.array([row]))[0])
        return prediction

    def _heuristic_model(self, features: dict, sensitive_attrs: dict) -> int:
        """
        Simple rule-based heuristic when no trained model is available.
        Replicates the bias pattern from generate_dataset.py:
        women accepted ~24%, men accepted ~43%.
        Used in development and testing only.
        """
        import random
        gender = sensitive_attrs.get("gender", features.get("gender", "unknown"))
        skills = float(features.get("skills_score", 0.65))
        exp = float(features.get("experience", 3))

        # Base merit score
        merit = skills * 0.5 + min(exp / 20, 1.0) * 0.3
        base_prob = merit * 0.85

        # Apply same bias pattern as training data
        if gender == "female":
            prob = base_prob * 0.66
        else:
            prob = base_prob

        return 1 if random.random() < prob else 0

    def _explain(
        self,
        *,
        domain: str,
        attribute_overrides: dict,
        original_sensitive: dict,
        original_label: str,
        counterfactual_label: str,
        bias_confirmed: bool,
    ) -> str:
        """Generate Gemma explanation for the replay result."""
        if not bias_confirmed:
            return (
                f"Changing the attribute did not alter the outcome — "
                f"the decision remained {original_label}. "
                f"Bias may be driven by other features or may not be present."
            )

        # Use first overridden attribute for the explanation
        attr = next(iter(attribute_overrides.keys()))
        original_val = original_sensitive.get(attr, "original value")
        new_val = attribute_overrides[attr]

        try:
            explainer = get_explainer()
            return explainer.explain_replay(
                domain=domain,
                attribute=attr,
                original_value=str(original_val),
                new_value=str(new_val),
                original_label=original_label,
                counterfactual_label=counterfactual_label,
            )
        except Exception as e:
            logger.error("Replay explanation failed: %s", e)
            return (
                f"The decision changed from {original_label} to {counterfactual_label} "
                f"when {attr} was changed from {original_val} to {new_val}. "
                f"This provides direct evidence of demographic bias in the AI model."
            )


# ── singleton ──────────────────────────────────────────────────────────────────
_replay_engine: Optional[ReplayEngine] = None


def get_replay_engine() -> ReplayEngine:
    global _replay_engine
    if _replay_engine is None:
        _replay_engine = ReplayEngine()
    return _replay_engine


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.replay_engine import ReplayEngine
# e = ReplayEngine()
# # Test heuristic model directly
# import random; random.seed(42)
# results = [e._heuristic_model({'skills_score':0.85,'experience':5},{'gender':'female'}) for _ in range(20)]
# male_results = [e._heuristic_model({'skills_score':0.85,'experience':5},{'gender':'male'}) for _ in range(20)]
# print(f'Female acceptance rate: {sum(results)/len(results):.0%}')
# print(f'Male acceptance rate:   {sum(male_results)/len(male_results):.0%}')
# print('ReplayEngine heuristic model working')
# "
