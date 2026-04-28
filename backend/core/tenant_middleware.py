"""
backend/core/tenant_middleware.py
FastAPI middleware — validates X-API-Key header and injects tenant_id into
request.state for all downstream modules.
Segment 1 — Foundation.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .tenant_registry import resolve_tenant


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Reads X-API-Key from every request (except excluded paths).
    On valid key → injects tenant_id, tenant_name, allowed_domains into request.state.
    On invalid key → returns 401.
    """

    # Paths that don't need an API key — includes frontend routes and static assets
    EXCLUDED_PREFIXES: tuple = (
        "/assets/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
    EXCLUDED_EXACT: set[str] = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public endpoints and static files
        if path in self.EXCLUDED_EXACT:
            return await call_next(request)
        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        api_key = request.headers.get("X-API-Key", "").strip()
        tenant = resolve_tenant(api_key)

        if not tenant:
            # For browser requests (no API key), serve the frontend
            accept = request.headers.get("accept", "")
            if "text/html" in accept:
                return await call_next(request)
            return JSONResponse(
                {"error": "Invalid or missing API key", "code": "INVALID_KEY"},
                status_code=401,
            )

        # Inject into request state
        request.state.tenant_id = tenant["tenant_id"]
        request.state.tenant_name = tenant["name"]
        request.state.allowed_domains = tenant["domains"]
        request.state.api_key = api_key

        return await call_next(request)


def check_domain(request: Request, domain: str) -> JSONResponse | None:
    if domain not in request.state.allowed_domains:
        return JSONResponse(
            {
                "error": f"Domain '{domain}' is not enabled for this tenant",
                "allowed": request.state.allowed_domains,
                "code": "DOMAIN_NOT_ALLOWED",
            },
            status_code=403,
        )
    return None
