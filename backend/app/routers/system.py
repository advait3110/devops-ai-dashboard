"""Module 2 - System Monitoring endpoints."""

import asyncio

from fastapi import APIRouter, Query

from .. import state
from ..config import settings

router = APIRouter(prefix="/api/system", tags=["System Monitoring"])


@router.get("/metrics")
async def current_metrics():
    """Latest psutil sample (taken by the background loop, so this is instant)."""
    return state.monitor.latest()


@router.get("/info")
async def system_info():
    return state.monitor.info()


@router.get("/history")
async def history(minutes: int = Query(15, ge=1, le=120)):
    return {"interval_seconds": settings.sample_interval,
            "points": state.monitor.history_points(minutes)}


@router.get("/processes")
async def processes(limit: int = Query(10, ge=1, le=50), sort: str = Query("cpu", pattern="^(cpu|memory)$")):
    return await asyncio.to_thread(state.monitor.top_processes, limit, sort)


@router.get("/disks")
async def disks():
    return await asyncio.to_thread(state.monitor.disks)
