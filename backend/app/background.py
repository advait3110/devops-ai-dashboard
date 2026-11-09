"""
Background tasks started when the backend starts (see main.py lifespan).

Only TWO lightweight asyncio tasks run - no Celery, no Redis, no threads
running forever:

1. system_loop       every SAMPLE_INTERVAL (5 s): psutil sample -> history,
                     threshold alerts, Prometheus gauges, webhook flush.
2. integration_loop  every INTEGRATION_POLL_INTERVAL (60 s): asks each
                     CONFIGURED tool for problems (crashed containers, failed
                     builds, CrashLoopBackOff pods, Prometheus alerts).
                     Tools that are not configured are skipped entirely.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from . import metrics, state
from .config import settings
from .errors import IntegrationError

log = logging.getLogger("background")

BAD_POD_REASONS = {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "OOMKilled",
                   "CreateContainerConfigError", "Error", "Evicted", "RunContainerError"}


async def system_loop() -> None:
    while True:
        try:
            sample = await asyncio.to_thread(state.monitor.sample)
            state.alerts.evaluate_system(sample)
            metrics.update_host_gauges(sample)
            metrics.update_alert_gauges(state.alerts.summary())
            await state.alerts.flush_notifications()
        except Exception:  # noqa: BLE001 - the loop must survive any error
            log.exception("system sampler failed")
        await asyncio.sleep(settings.sample_interval)


# ---------------------------------------------------------------------- #
# problem detectors: each returns {alert_key: {severity, title, message}}
# ---------------------------------------------------------------------- #
async def docker_problems() -> dict[str, dict[str, Any]]:
    problems = {}
    for c in await state.docker.list_containers():
        key = f"docker:{c['name']}"
        if c["state"] == "restarting":
            problems[key] = {"severity": "critical", "title": f"Container {c['name']} is restarting",
                             "message": f"{c['image']} - {c['status']}"}
        elif c["state"] == "exited" and c.get("exit_code") not in (None, 0):
            problems[key] = {"severity": "warning", "title": f"Container {c['name']} crashed",
                             "message": f"Exit code {c['exit_code']} ({c['image']})"}
        elif c.get("health") == "unhealthy":
            problems[key] = {"severity": "warning", "title": f"Container {c['name']} is unhealthy",
                             "message": c["status"]}
    return problems


async def kubernetes_problems() -> dict[str, dict[str, Any]]:
    problems = {}
    for p in await state.kubernetes.pods():
        if p["status"] in BAD_POD_REASONS:
            problems[f"k8s:pod:{p['namespace']}/{p['name']}"] = {
                "severity": "critical" if p["status"] in ("CrashLoopBackOff", "OOMKilled") else "warning",
                "title": f"Pod {p['name']} is {p['status']}",
                "message": f"namespace {p['namespace']}, restarts {p['restarts']}"}
    for n in await state.kubernetes.nodes():
        if not n["ready"]:
            problems[f"k8s:node:{n['name']}"] = {"severity": "critical", "title": f"Node {n['name']} NotReady",
                                                 "message": ", ".join(n["pressure"]) or "kubelet not ready"}
    return problems


async def jenkins_problems() -> dict[str, dict[str, Any]]:
    return {f"jenkins:{j['name']}": {
        "severity": "warning", "title": f"Jenkins job {j['name']} failed",
        "message": f"Build #{(j.get('last_build') or {}).get('number')} result {j['status']}"}
        for j in await state.jenkins.jobs() if j["status"] == "failed"}


async def github_problems() -> dict[str, dict[str, Any]]:
    latest: dict[tuple, dict] = {}
    for run in await state.github.all_runs():
        latest.setdefault((run["repo"], run["workflow"]), run)  # newest first
    return {f"github:{r['repo']}:{r['workflow']}": {
        "severity": "warning", "title": f"Workflow '{r['workflow']}' failed",
        "message": f"{r['repo']} on {r['branch']} ({r['commit']})"}
        for r in latest.values() if r["status"] == "failed"}


async def prometheus_problems() -> dict[str, dict[str, Any]]:
    return {f"prometheus:{a['name']}:{a.get('instance')}": {
        "severity": a["severity"] if a["severity"] in ("critical", "warning", "info") else "warning",
        "title": f"{a['name']} ({a.get('instance') or 'cluster'})",
        "message": a.get("summary") or ""}
        for a in await state.prometheus.alerts() if a["state"] == "firing"}


def _detectors() -> list[tuple[str, Any]]:
    checks = []
    if state.docker.enabled:
        checks.append(("docker", docker_problems))
    if state.kubernetes.enabled:
        checks.append(("kubernetes", kubernetes_problems))
    if state.jenkins.configured:
        checks.append(("jenkins", jenkins_problems))
    if state.github.configured:
        checks.append(("github", github_problems))
    if state.prometheus.configured:
        checks.append(("prometheus", prometheus_problems))
    return checks


async def check_integrations_once() -> None:
    for source, detector in _detectors():
        unreachable_key = f"{source}:unreachable"
        try:
            problems = await asyncio.wait_for(detector(), timeout=45)
        except (IntegrationError, asyncio.TimeoutError) as exc:
            message = exc.message if isinstance(exc, IntegrationError) else "check timed out"
            # Only connectivity problems become an alert; other alerts of the source stay as they were.
            state.alerts.fire(unreachable_key, "integration", "warning",
                              f"{source.capitalize()} is unreachable", message)
            continue
        except Exception:  # noqa: BLE001
            log.exception("%s check failed", source)
            continue
        state.alerts.resolve(unreachable_key)
        state.alerts.sync_source(source, problems)


async def integration_loop() -> None:
    await asyncio.sleep(5)  # let the server finish starting
    while True:
        try:
            await check_integrations_once()
            await state.alerts.flush_notifications()
        except Exception:  # noqa: BLE001
            log.exception("integration loop failed")
        await asyncio.sleep(settings.integration_poll_interval)
