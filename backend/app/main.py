"""
DevOps AI Dashboard - FastAPI application entry point.

Run (development):
    cd backend
    uvicorn app.main:app --reload --port 8000

Interactive API docs (generated automatically by FastAPI from the code):
    http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import background
from .config import settings
from .errors import IntegrationError
from .logging_setup import setup_logging
from .metrics import MetricsMiddleware, metrics_response
from .routers import ai, alerts, cicd, containers, infrastructure, logs, overview, system

setup_logging(settings.log_dir)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the background loops on startup and stop them cleanly on shutdown."""
    log.info("Starting %s (%s)", settings.app_name, settings.environment)
    tasks = [
        asyncio.create_task(background.system_loop(), name="system_loop"),
        asyncio.create_task(background.integration_loop(), name="integration_loop"),
    ]
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("Stopped")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Centralised, AI-powered DevOps monitoring API.",
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(IntegrationError)
async def integration_error_handler(_: Request, exc: IntegrationError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "hint": exc.hint})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc.__class__.__name__}",
                                                  "hint": "See backend logs (Logs page > Dashboard backend)."})


for r in (overview.router, system.router, cicd.router, containers.docker_router, containers.k8s_router,
          infrastructure.router, ai.router, logs.router, alerts.router):
    app.include_router(r)


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus scrape endpoint (text exposition format)."""
    return metrics_response()


# Optional: serve the built React app from FastAPI (single-process mode).
# The normal production setup uses Nginx instead (frontend/nginx.conf).
if settings.serve_frontend_dir and Path(settings.serve_frontend_dir).is_dir():
    dist = Path(settings.serve_frontend_dir).resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": f"{settings.app_name} API is running", "docs": "/docs", "health": "/api/health"}
