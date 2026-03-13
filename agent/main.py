"""
FastAPI application entry-point for the OpsClaw agent service.

Run locally:
    python -m agent.main          # or: uvicorn agent.main:app --reload
"""

from __future__ import annotations
import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from agent import config
from agent.routes import router as chat_router
from agent.routes.dashboard import router as dashboard_router
from agent.routes.upload import router as upload_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="OpsClaw — Conut Operations Agent",
    version="1.0.0",
    description=(
        "AI-powered Chief of Operations agent for the Conut bakery chain. "
        "Provides a chatbot API backed by AWS Bedrock (Claude) and "
        "dashboard data endpoints for the frontend."
    ),
)

# CORS — allow the React/Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(chat_router)
app.include_router(dashboard_router)
app.include_router(upload_router)


def _is_loopback_request(request: Request) -> bool:
    client_host = request.client.host if request.client else ""
    return client_host in {"127.0.0.1", "::1", "localhost"}


@app.middleware("http")
async def require_cloudfront_origin_header(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    if not config.origin_protection_enabled() or _is_loopback_request(request):
        return await call_next(request)

    header_value = request.headers.get(config.ORIGIN_VERIFY_HEADER_NAME)
    if header_value and secrets.compare_digest(
        header_value,
        config.ORIGIN_VERIFY_HEADER_VALUE,
    ):
        return await call_next(request)

    return JSONResponse(
        status_code=403,
        content={"detail": "Forbidden"},
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "local_mode": config.LOCAL_MODE,
        "model": config.BEDROCK_MODEL_ID,
    }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    log.info(
        "Starting OpsClaw agent — LOCAL_MODE=%s  port=%s",
        config.LOCAL_MODE,
        config.PORT,
    )
    uvicorn.run(
        "agent.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
    )
