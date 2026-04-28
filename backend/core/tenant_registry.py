"""
backend/core/tenant_registry.py
Hardcoded API key → tenant map. No database needed.
Segment 1 — Foundation.
"""

from typing import Optional

TENANT_REGISTRY: dict[str, dict] = {
    "fw-acme-corp-2026": {
        "tenant_id": "acme_corp",
        "name": "Acme Corp",
        "domains": ["hiring", "lending"],
        "plan": "enterprise",
    },
    "fw-university-2026": {
        "tenant_id": "university",
        "name": "State University",
        "domains": ["admissions"],
        "plan": "standard",
    },
    "fw-demo-key-2026": {
        "tenant_id": "demo",
        "name": "FairWall Demo",
        "domains": ["hiring", "lending", "admissions", "healthcare"],
        "plan": "demo",
    },
}


def resolve_tenant(api_key: str) -> Optional[dict]:
    """Return tenant dict for a given API key, or None if key is invalid."""
    return TENANT_REGISTRY.get(api_key)


def get_tenant_by_id(tenant_id: str) -> Optional[dict]:
    """Reverse lookup — find tenant dict by tenant_id (used for /tenant-info)."""
    for tenant in TENANT_REGISTRY.values():
        if tenant["tenant_id"] == tenant_id:
            return tenant
    return None


def is_domain_allowed(api_key: str, domain: str) -> bool:
    """Return True if the tenant associated with api_key is allowed to use domain."""
    tenant = resolve_tenant(api_key)
    if not tenant:
        return False
    return domain in tenant["domains"]


# ── test ──────────────────────────────────────────────────────────────────────
# python -c "from backend.core.tenant_registry import resolve_tenant; print(resolve_tenant('fw-demo-key-2026'))"
