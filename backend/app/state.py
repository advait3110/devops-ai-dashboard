"""
Creates ONE instance of every service (simple dependency container).

Routers import these objects instead of creating their own, so all requests
share the same metric history, alert database and configuration.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .config import settings
from .services.alert_service import AlertManager, ThresholdRule
from .services.aws_service import AWSService
from .services.docker_service import DockerService
from .services.gemini_service import GeminiService
from .services.github_service import GitHubActionsService
from .services.grafana_service import GrafanaService
from .services.jenkins_service import JenkinsService
from .services.kubernetes_service import KubernetesService
from .services.log_service import LogService
from .services.prometheus_service import PrometheusService
from .services.system_service import SystemMonitor

monitor = SystemMonitor(settings.history_size)
docker = DockerService(settings.docker_enabled)
kubernetes = KubernetesService(settings.kubernetes_enabled, settings.kube_context, settings.allow_actions)
jenkins = JenkinsService(settings.jenkins_url, settings.jenkins_user, settings.jenkins_token)
github = GitHubActionsService(settings.github_token, settings.github_repos, settings.github_api_url)
prometheus = PrometheusService(settings.prometheus_url)
grafana = GrafanaService(settings.grafana_url)
aws = AWSService(settings.aws_enabled, settings.aws_region)
gemini = GeminiService(settings.gemini_api_key, settings.gemini_model,
                       settings.gemini_fallback_model, settings.gemini_timeout)
logs = LogService(settings.log_dir / "app.log", settings.log_files, docker, kubernetes)
alerts = AlertManager(
    settings.data_dir / "alerts.db",
    rules=[
        ThresholdRule("system:cpu", "cpu_percent", "CPU usage", settings.cpu_threshold, "warning"),
        ThresholdRule("system:memory", "memory_percent", "Memory usage", settings.memory_threshold, "warning"),
        ThresholdRule("system:disk", "disk_percent", "Disk usage", settings.disk_threshold, "critical"),
    ],
    for_samples=settings.alert_for_samples,
    webhook_url=settings.alert_webhook_url,
    webhook_format=settings.alert_webhook_format,
)

INTEGRATIONS = [gemini, docker, kubernetes, jenkins, github, prometheus, grafana, aws]


async def integration_statuses() -> list[dict[str, Any]]:
    """Check every integration in parallel; one slow tool cannot block the others."""

    async def safe(service) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(service.status(), timeout=20)
        except Exception as exc:  # noqa: BLE001 - status must never crash the API
            return {"name": service.name, "label": service.label, "configured": True,
                    "connected": False, "detail": f"Status check failed: {exc}", "hint": ""}

    return list(await asyncio.gather(*(safe(s) for s in INTEGRATIONS)))
