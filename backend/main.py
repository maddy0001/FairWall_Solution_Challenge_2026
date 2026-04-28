"""
backend/main.py
FastAPI application entry point — Segments 1-6 complete.
Registers TenantMiddleware, mounts all routers, exposes /health.
Serves React frontend as static files from /app/dist/client.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.core.tenant_middleware import TenantMiddleware
from backend.core.profile_loader import load_all_profiles
from backend.api.predict      import router as predict_router
from backend.api.metrics      import router as metrics_router
from backend.api.review       import router as review_router
from backend.api.interventions import router as interventions_router
from backend.api.explain      import router as explain_router
from backend.api.replay       import router as replay_router
from backend.api.simulate     import router as simulate_router

# ── env + logging ─────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── app state ──────────────────────────────────────────────────────────────────
_app_state: dict = {}

DIST_DIR = Path("/app/dist/client")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FairWall starting up...")
    profiles_dir = Path(__file__).parent / "profiles"
    profiles = load_all_profiles(profiles_dir)
    _app_state["profiles"] = profiles
    logger.info("Loaded %d domain profiles: %s", len(profiles), list(profiles.keys()))
    yield
    logger.info("FairWall shutting down.")
    _app_state.clear()


# ── app ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="FairWall — AI Fairness Firewall",
    description="Real-time fairness middleware that intercepts biased AI decisions before users.",
    version="1.2.0",
    lifespan=lifespan,
)

# ── middleware ─────────────────────────────────────────────────────────────────
app.add_middleware(TenantMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routers ───────────────────────────────────────────────────────────────
app.include_router(predict_router,       tags=["Predictions"])
app.include_router(metrics_router,       tags=["Metrics"])
app.include_router(review_router,        tags=["Review Queue"])
app.include_router(interventions_router, tags=["Interventions"])
app.include_router(explain_router,       tags=["Explainability"])
app.include_router(replay_router,        tags=["What-If Replay"])
app.include_router(simulate_router,      tags=["Demo Simulator"])


# ── health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {
        "status":         "ok",
        "version":        "1.2.0",
        "loaded_domains": list(_app_state.get("profiles", {}).keys()),
        "segment":        6,
    }


# ── Static frontend (React build) ─────────────────────────────────────────────
if DIST_DIR.exists():
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str, request: Request):
        # Don't intercept API routes
        if full_path.startswith(("predict", "metrics", "trust-score", "interventions",
                                  "review-queue", "resolve", "explain", "replay",
                                  "simulate", "health", "docs", "openapi", "redoc")):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        index = DIST_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built"}
else:
    logger.warning("Frontend dist not found at %s — API-only mode", DIST_DIR)


def get_profiles() -> dict:
    return _app_state.get("profiles", {})
