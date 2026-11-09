"""Module 4 - Container Monitoring endpoints (Docker + Kubernetes)."""

import asyncio

from fastapi import APIRouter, Query

from .. import state
from ..config import settings
from ..errors import IntegrationError

docker_router = APIRouter(prefix="/api/docker", tags=["Docker"])
k8s_router = APIRouter(prefix="/api/k8s", tags=["Kubernetes"])


def _require_actions() -> None:
    if not settings.allow_actions:
        raise IntegrationError("Actions are disabled (ALLOW_ACTIONS=false)", 403)


# -------------------------------- Docker --------------------------------- #
@docker_router.get("/info")
async def docker_info():
    return await state.docker.info()


@docker_router.get("/containers")
async def docker_containers():
    return await state.docker.list_containers()


@docker_router.get("/stats")
async def docker_stats():
    return await state.docker.stats()


@docker_router.get("/containers/{container}/logs")
async def docker_logs(container: str, tail: int = Query(200, ge=10, le=2000)):
    return {"container": container, "log": await state.docker.logs(container, tail)}


@docker_router.post("/containers/{container}/{action}")
async def docker_action(container: str, action: str):
    _require_actions()
    return await state.docker.action(container, action)


# ------------------------------ Kubernetes ------------------------------- #
@k8s_router.get("/overview")
async def k8s_overview():
    k = state.kubernetes
    context, nodes, pods, deployments = await asyncio.gather(
        k.current_context(), k.nodes(), k.pods(), k.deployments())
    phases: dict[str, int] = {}
    for p in pods:
        phases[p["status"]] = phases.get(p["status"], 0) + 1
    return {
        "context": context,
        "nodes": nodes,
        "pod_count": len(pods),
        "pod_status": phases,
        "deployment_count": len(deployments),
        "deployments_unavailable": sum(1 for d in deployments if d["available"] < d["desired"]),
        "namespaces": sorted({p["namespace"] for p in pods}),
    }


@k8s_router.get("/pods")
async def k8s_pods(namespace: str | None = None):
    pods, usage = await asyncio.gather(state.kubernetes.pods(namespace), state.kubernetes.pod_metrics())
    for p in pods:
        p["usage"] = usage.get(f"{p['namespace']}/{p['name']}")
    return pods


@k8s_router.get("/deployments")
async def k8s_deployments(namespace: str | None = None):
    return await state.kubernetes.deployments(namespace)


@k8s_router.get("/services")
async def k8s_services(namespace: str | None = None):
    return await state.kubernetes.services(namespace)


@k8s_router.get("/events")
async def k8s_events(namespace: str | None = None):
    return await state.kubernetes.warning_events(namespace)


@k8s_router.get("/pods/{namespace}/{pod}/logs")
async def k8s_pod_logs(namespace: str, pod: str, container: str | None = None,
                       tail: int = Query(200, ge=10, le=2000)):
    return {"pod": pod, "log": await state.kubernetes.pod_logs(namespace, pod, container, tail)}


@k8s_router.post("/deployments/{namespace}/{name}/restart")
async def k8s_restart(namespace: str, name: str):
    _require_actions()
    return await state.kubernetes.restart_deployment(namespace, name)
