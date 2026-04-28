"""
backend/core/profile_loader.py
Loads all YAML domain profiles at startup into a dict[str, DomainProfile].
Segment 1 — Foundation.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class FairnessThresholds:
    demographic_parity_diff: float = 0.10
    equal_opportunity_diff: float = 0.10
    selection_rate_disparity: float = 0.20


@dataclass
class DomainProfile:
    domain: str
    sensitive_attributes: list[str]
    fairness_thresholds: FairnessThresholds
    regulatory_framework: str
    intervention_map: dict[str, str]  # low/medium/high → action name
    sliding_window_size: int = 30
    min_window_for_scoring: int = 10


def _parse_thresholds(raw: dict) -> FairnessThresholds:
    return FairnessThresholds(
        demographic_parity_diff=raw.get("demographic_parity_diff", 0.10),
        equal_opportunity_diff=raw.get("equal_opportunity_diff", 0.10),
        selection_rate_disparity=raw.get("selection_rate_disparity", 0.20),
    )


def load_profile(yaml_path: Path) -> DomainProfile:
    """Parse a single YAML file into a DomainProfile dataclass."""
    with open(yaml_path, "r") as f:
        raw = yaml.safe_load(f)

    required = ["domain", "sensitive_attributes", "fairness_thresholds",
                "regulatory_framework", "intervention_map"]
    for key in required:
        if key not in raw:
            raise ValueError(f"Profile {yaml_path.name} is missing required field: '{key}'")

    return DomainProfile(
        domain=raw["domain"],
        sensitive_attributes=raw["sensitive_attributes"],
        fairness_thresholds=_parse_thresholds(raw["fairness_thresholds"]),
        regulatory_framework=raw["regulatory_framework"],
        intervention_map=raw["intervention_map"],
        sliding_window_size=raw.get("sliding_window_size", 30),
        min_window_for_scoring=raw.get("min_window_for_scoring", 10),
    )


def load_all_profiles(profiles_dir: Optional[Path] = None) -> dict[str, DomainProfile]:
    """
    Load every .yaml file in profiles_dir.
    Returns dict keyed by domain name, e.g. {"hiring": DomainProfile(...), ...}
    """
    if profiles_dir is None:
        # Default: backend/profiles/ relative to this file
        profiles_dir = Path(__file__).parent.parent / "profiles"

    if not profiles_dir.exists():
        raise FileNotFoundError(f"Profiles directory not found: {profiles_dir}")

    profiles: dict[str, DomainProfile] = {}
    for yaml_file in sorted(profiles_dir.glob("*.yaml")):
        try:
            profile = load_profile(yaml_file)
            profiles[profile.domain] = profile
        except Exception as e:
            raise RuntimeError(f"Failed to load profile {yaml_file.name}: {e}") from e

    if not profiles:
        raise RuntimeError(f"No YAML profiles found in {profiles_dir}")

    return profiles


def get_profile(profiles: dict[str, DomainProfile], domain: str) -> DomainProfile:
    """Get a profile by domain name, raising a clear error if not found."""
    if domain not in profiles:
        available = list(profiles.keys())
        raise KeyError(f"Domain '{domain}' not found. Available: {available}")
    return profiles[domain]


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "
# from backend.core.profile_loader import load_all_profiles
# p = load_all_profiles()
# for name, profile in p.items():
#     print(name, profile.sliding_window_size, profile.regulatory_framework)
# "
