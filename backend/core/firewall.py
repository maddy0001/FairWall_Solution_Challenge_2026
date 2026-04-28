"""
backend/core/firewall.py
The @fw.protect decorator — the universal FairWall plug-in interface.
Any Python AI model wraps with this decorator.
Segment 3 — Intervention Engine.

Usage:
    from backend.core.firewall import FairWall

    fw = FairWall(domain="hiring", sensitive_attrs=["gender", "age"], api_key="fw-acme-corp-2026")

    @fw.protect
    def my_hiring_model(candidate_features, **kwargs):
        return model.predict(candidate_features)

    # FairWall now intercepts every prediction.
    # Pass sensitive_attrs as a kwarg:
    result = my_hiring_model(features, sensitive_attrs={"gender": "female"})
"""

import logging
from functools import wraps
from typing import Any, Callable, Optional

from .bias_engine import get_bias_engine
from .logger import generate_prediction_id, get_prediction_logger
from .profile_loader import load_all_profiles
from .router import get_router
from .tenant_registry import resolve_tenant
from .trust_score import get_trust_calculator

logger = logging.getLogger(__name__)


class FairWall:
    """
    Universal plug-in interface for any Python AI model.
    Wraps the model function with the full FairWall pipeline.
    """

    def __init__(
        self,
        domain: str,
        sensitive_attrs: list[str],
        api_key: str,
        profiles_dir: Optional[Any] = None,
    ):
        self.domain = domain
        self.sensitive_attrs = sensitive_attrs
        self.api_key = api_key

        # Resolve tenant
        tenant = resolve_tenant(api_key)
        if not tenant:
            raise ValueError(f"Invalid API key: {api_key}")
        if domain not in tenant["domains"]:
            raise ValueError(
                f"Domain '{domain}' not allowed for tenant '{tenant['name']}'. "
                f"Allowed: {tenant['domains']}"
            )

        self.tenant_id = tenant["tenant_id"]
        self.tenant_name = tenant["name"]

        # Load domain profile
        from pathlib import Path
        if profiles_dir is None:
            profiles_dir = Path(__file__).parent.parent / "profiles"
        profiles = load_all_profiles(profiles_dir)
        if domain not in profiles:
            raise ValueError(f"Domain profile '{domain}' not found in {profiles_dir}")
        self.profile = profiles[domain]

        logger.info(
            "FairWall initialised: tenant=%s domain=%s attrs=%s",
            self.tenant_id, domain, sensitive_attrs,
        )

    def protect(self, func: Callable) -> Callable:
        """
        Decorator — wraps any prediction function with FairWall interception.

        The wrapped function must accept **kwargs.
        Pass sensitive_attrs as a keyword argument when calling.

        Example:
            @fw.protect
            def predict(features, **kwargs):
                return model.predict(features)

            result = predict(features, sensitive_attrs={"gender": "female"}, confidence=0.73)
        """
        fw_self = self  # capture self for the closure

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract FairWall-specific kwargs
            sensitive_attrs_values: dict = kwargs.pop("sensitive_attrs", {})
            confidence: float = kwargs.pop("confidence", 1.0)
            true_label: Optional[int] = kwargs.pop("true_label", None)

            # Run the original model
            original_prediction = func(*args, **kwargs)

            # Extract features from first positional arg if available
            features: dict = args[0] if args and isinstance(args[0], dict) else {}

            # Generate prediction ID
            prediction_id = generate_prediction_id()

            # Log to BigQuery
            pl = get_prediction_logger()
            pl.log_prediction(
                prediction_id=prediction_id,
                tenant_id=fw_self.tenant_id,
                domain=fw_self.domain,
                features=features,
                sensitive_attrs=sensitive_attrs_values,
                prediction=int(original_prediction),
                confidence=confidence,
            )

            # Run bias detection
            engine = get_bias_engine()
            metric_results = engine.add_prediction(
                tenant_id=fw_self.tenant_id,
                domain=fw_self.domain,
                prediction_id=prediction_id,
                prediction=int(original_prediction),
                sensitive_attrs=sensitive_attrs_values,
                profile=fw_self.profile,
                true_label=true_label,
            )

            # Compute trust score
            window_info = engine.get_window_info(fw_self.tenant_id, fw_self.domain, fw_self.profile)
            calculator = get_trust_calculator()
            trust_result = calculator.compute(
                metrics=metric_results,
                window_size=window_info["window_size"],
                window_capacity=window_info["window_capacity"],
                min_for_scoring=window_info["min_for_scoring"],
            )

            # Run intervention engine
            router = get_router()
            intervention = router.route(
                prediction_id=prediction_id,
                original_prediction=int(original_prediction),
                confidence=confidence,
                trust_result=trust_result,
                tenant_id=fw_self.tenant_id,
                domain=fw_self.domain,
                features=features,
                sensitive_attrs=sensitive_attrs_values,
            )

            # Log warning if blocked
            if intervention.blocked:
                logger.warning(
                    "FairWall BLOCKED prediction %s (tenant=%s domain=%s score=%s)",
                    prediction_id, fw_self.tenant_id, fw_self.domain,
                    trust_result.trust_score,
                )
                return None  # blocked — do not release prediction

            return intervention.final_prediction

        return wrapper


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.firewall import FairWall
# fw = FairWall(domain='hiring', sensitive_attrs=['gender'], api_key='fw-demo-key-2026')
# print('FairWall created for tenant:', fw.tenant_name)
#
# @fw.protect
# def fake_model(features, **kwargs):
#     return 0  # always rejects
#
# # Send 10 predictions — should see None after enough bias
# for i in range(10):
#     result = fake_model({'age':28,'skills':0.9}, sensitive_attrs={'gender':'female'})
#     print(f'Prediction {i+1}: {result}')
# "
