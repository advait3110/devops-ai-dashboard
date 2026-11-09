"""Module 5 - Infrastructure Monitoring endpoints (Prometheus, Grafana, AWS)."""

from fastapi import APIRouter, Query

from .. import state
from ..config import settings
from ..services.prometheus_service import PRESET_QUERIES

router = APIRouter(prefix="/api/infra", tags=["Infrastructure"])


@router.get("/prometheus/presets")
async def presets():
    return PRESET_QUERIES


@router.get("/prometheus/targets")
async def targets():
    return await state.prometheus.targets()


@router.get("/prometheus/alerts")
async def prom_alerts():
    return await state.prometheus.alerts()


@router.get("/prometheus/query")
async def query(q: str = Query(..., min_length=1, max_length=1000)):
    return await state.prometheus.query(q)


@router.get("/prometheus/query_range")
async def query_range(q: str = Query(..., min_length=1, max_length=1000),
                      minutes: int = Query(30, ge=1, le=1440), step: int | None = Query(None, ge=5, le=3600)):
    return await state.prometheus.query_range(q, minutes, step)


@router.get("/grafana")
async def grafana():
    status = await state.grafana.status()
    return {**status, "url": settings.grafana_url,
            "dashboard_path": "/d/devops-ai-overview/devops-ai-overview"}


@router.get("/aws")
async def aws_summary():
    return await state.aws.summary()
