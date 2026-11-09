"""
Prometheus metrics EXPOSED BY this backend (GET /metrics).

This makes the dashboard itself observable: Prometheus scrapes this endpoint
(see monitoring/prometheus/prometheus.yml) and Grafana charts request rate,
latency and the host gauges below.

Label values use the route TEMPLATE ("/api/docker/containers/{container}/logs")
instead of the real URL, otherwise every container id would create a new time
series (a "cardinality explosion" that wastes Prometheus memory).
"""

from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUESTS = Counter("devops_dashboard_http_requests_total", "HTTP requests handled",
                   ["method", "path", "status"])
LATENCY = Histogram("devops_dashboard_http_request_duration_seconds", "HTTP request latency",
                    ["method", "path"], buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
CPU = Gauge("devops_dashboard_host_cpu_percent", "Host CPU usage measured by psutil")
MEMORY = Gauge("devops_dashboard_host_memory_percent", "Host memory usage measured by psutil")
DISK = Gauge("devops_dashboard_host_disk_percent", "Host root disk usage measured by psutil")
ACTIVE_ALERTS = Gauge("devops_dashboard_active_alerts", "Alerts currently firing", ["severity"])
AI_REQUESTS = Counter("devops_dashboard_ai_requests_total", "Gemini API calls", ["kind", "outcome"])


def update_host_gauges(sample: dict) -> None:
    CPU.set(sample["cpu_percent"])
    MEMORY.set(sample["memory_percent"])
    DISK.set(sample["disk_percent"])


def update_alert_gauges(summary: dict) -> None:
    for sev in ("critical", "warning", "info"):
        ACTIVE_ALERTS.labels(severity=sev).set(summary.get(sev, 0))


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", None) or "unmatched"
            if path != "/metrics":
                REQUESTS.labels(request.method, path, str(status)).inc()
                LATENCY.labels(request.method, path).observe(time.perf_counter() - start)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
