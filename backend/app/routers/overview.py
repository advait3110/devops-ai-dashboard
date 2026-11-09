"""Module 1 - Dashboard overview + health + integration status."""

import asyncio
import time

from fastapi import APIRouter

from .. import state
from ..config import settings
from ..errors import IntegrationError
from ..utils.cache import ttl_cache

router = APIRouter(tags=["Dashboard"])
STARTED = time.time()


@ttl_cache(ttl=15)
async def _cached_statuses():
    return await state.integration_statuses()


async def _safe(coro, default=None):
    try:
        return await asyncio.wait_for(coro, timeout=20)
    except (IntegrationError, asyncio.TimeoutError):
        return default


@router.get("/api/health")
async def health():
    """Liveness/readiness probe used by Docker, Kubernetes and Jenkins smoke tests."""
    return {"status": "ok", "uptime_seconds": int(time.time() - STARTED),
            "environment": settings.environment}


@router.get("/api/integrations")
async def integrations():
    return await _cached_statuses()


@router.get("/api/overview")
async def overview():
    statuses = await _cached_statuses()
    connected = {s["name"] for s in statuses if s["connected"]}

    async def docker_summary():
        if "docker" not in connected:
            return None
        containers = await state.docker.list_containers()
        return {
            "total": len(containers),
            "running": sum(1 for c in containers if c["state"] == "running"),
            "stopped": sum(1 for c in containers if c["state"] != "running"),
            "unhealthy": sum(1 for c in containers if c.get("health") == "unhealthy"),
        }

    async def k8s_summary():
        if "kubernetes" not in connected:
            return None
        pods, deployments, nodes = await asyncio.gather(
            state.kubernetes.pods(), state.kubernetes.deployments(), state.kubernetes.nodes())
        return {
            "nodes": len(nodes),
            "nodes_ready": sum(1 for n in nodes if n["ready"]),
            "pods": len(pods),
            "pods_running": sum(1 for p in pods if p["status"] in ("Running", "Succeeded", "Completed")),
            "deployments": len(deployments),
        }

    async def pipelines():
        items = []
        if "jenkins" in connected:
            for j in (await _safe(state.jenkins.jobs(), []))[:6]:
                lb = j.get("last_build") or {}
                items.append({"tool": "jenkins", "name": j["name"], "status": j["status"],
                              "number": lb.get("number"), "time": (lb.get("timestamp") or 0) / 1000,
                              "url": j.get("url")})
        if "github" in connected:
            for r in (await _safe(state.github.all_runs(6), []))[:6]:
                items.append({"tool": "github", "name": f"{r['repo']} - {r['workflow']}",
                              "status": r["status"], "number": r["run_number"],
                              "time": r["created_at"], "url": r["url"]})
        return items

    docker_s, k8s_s, pipes = await asyncio.gather(
        _safe(docker_summary()), _safe(k8s_summary()), _safe(pipelines(), []))

    return {
        "system": state.monitor.latest(),
        "host": state.monitor.info(),
        "history": state.monitor.history_points(15),
        "alerts": state.alerts.summary(),
        "recent_alerts": state.alerts.list(limit=6),
        "integrations": statuses,
        "docker": docker_s,
        "kubernetes": k8s_s,
        "pipelines": pipes,
    }
