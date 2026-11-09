"""
Module 5 - Infrastructure monitoring with Prometheus.

Prometheus SCRAPES (pulls) metrics every 15 s from:
  * node-exporter        -> host CPU / memory / disk / network
  * this backend /metrics -> dashboard's own metrics (prometheus_client)
  * itself
and stores them as time series. We query it through its HTTP API using PromQL:
  GET /api/v1/query?query=...            instant value
  GET /api/v1/query_range?query=...      series for charts
  GET /api/v1/targets                    what is being scraped and is it UP
  GET /api/v1/alerts                     alerts from monitoring/prometheus/alert_rules.yml
Grafana reads the same Prometheus data for richer dashboards.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..errors import IntegrationError, status_payload

HINT = ("Start the monitoring stack: 'docker compose --profile monitoring up -d', "
        "then set PROMETHEUS_URL=http://localhost:9090 in backend/.env.")

# Ready-made PromQL queries shown as buttons in the UI.
PRESET_QUERIES: dict[str, dict[str, str]] = {
    "node_cpu": {
        "label": "Node CPU usage %",
        "query": '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)',
        "unit": "%",
    },
    "node_memory": {
        "label": "Node memory usage %",
        "query": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
        "unit": "%",
    },
    "node_disk": {
        "label": "Root filesystem usage %",
        "query": '(1 - node_filesystem_avail_bytes{mountpoint="/",fstype!="rootfs"} '
                 '/ node_filesystem_size_bytes{mountpoint="/",fstype!="rootfs"}) * 100',
        "unit": "%",
    },
    "node_network_rx": {
        "label": "Network receive (bytes/s)",
        "query": 'sum by (instance) (rate(node_network_receive_bytes_total{device!="lo"}[1m]))',
        "unit": "B/s",
    },
    "api_request_rate": {
        "label": "Dashboard API requests/s",
        "query": "sum(rate(devops_dashboard_http_requests_total[1m]))",
        "unit": "req/s",
    },
    "api_latency_p95": {
        "label": "Dashboard API p95 latency (s)",
        "query": "histogram_quantile(0.95, sum by (le) "
                 "(rate(devops_dashboard_http_request_duration_seconds_bucket[5m])))",
        "unit": "s",
    },
    "targets_up": {
        "label": "Scrape targets up",
        "query": "up",
        "unit": "",
    },
}


class PrometheusService:
    name = "prometheus"
    label = "Prometheus"

    def __init__(self, url: str) -> None:
        self.url = url

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def _get(self, path: str, params: dict | None = None) -> Any:
        if not self.configured:
            raise IntegrationError("Prometheus is not configured", 503, HINT)
        async with httpx.AsyncClient(base_url=self.url, timeout=15) as client:
            try:
                resp = await client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise IntegrationError(f"Prometheus unreachable at {self.url}", 503, HINT) from exc
        try:
            body = resp.json()
        except ValueError as exc:
            raise IntegrationError(f"Prometheus returned HTTP {resp.status_code}", 502) from exc
        if body.get("status") != "success":
            raise IntegrationError(f"PromQL error: {body.get('error', 'unknown')}", 400)
        return body.get("data")

    async def status(self) -> dict[str, Any]:
        if not self.configured:
            return status_payload(self.name, self.label, False, False, "Not configured", HINT)
        try:
            info = await self._get("/api/v1/status/buildinfo")
            return status_payload(self.name, self.label, True, True,
                                  f"Prometheus {info.get('version', '?')}", url=self.url)
        except IntegrationError as exc:
            return status_payload(self.name, self.label, True, False, exc.message, HINT, url=self.url)

    async def query(self, promql: str) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/query", params={"query": promql})
        if data.get("resultType") == "scalar":
            return [{"metric": {}, "value": float(data["result"][1])}]
        return [{"metric": r.get("metric", {}), "value": _num(r["value"][1])}
                for r in data.get("result", []) if "value" in r]

    async def query_range(self, promql: str, minutes: int = 30, step: int | None = None) -> list[dict[str, Any]]:
        minutes = max(1, min(minutes, 24 * 60))
        step = step or max(15, minutes * 60 // 120)  # ~120 points per series
        end = time.time()
        data = await self._get("/api/v1/query_range", params={
            "query": promql, "start": end - minutes * 60, "end": end, "step": step})
        return [{
            "metric": r.get("metric", {}),
            "points": [[float(t), _num(v)] for t, v in r.get("values", [])],
        } for r in data.get("result", [])]

    async def targets(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/targets", params={"state": "active"})
        return [{
            "job": t.get("labels", {}).get("job"),
            "instance": t.get("labels", {}).get("instance"),
            "health": t.get("health"),
            "last_scrape": t.get("lastScrape"),
            "scrape_duration": t.get("lastScrapeDuration"),
            "last_error": t.get("lastError"),
            "url": t.get("scrapeUrl"),
        } for t in data.get("activeTargets", [])]

    async def alerts(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/alerts")
        return [{
            "name": a.get("labels", {}).get("alertname"),
            "severity": a.get("labels", {}).get("severity", "warning"),
            "instance": a.get("labels", {}).get("instance"),
            "state": a.get("state"),
            "summary": a.get("annotations", {}).get("summary") or a.get("annotations", {}).get("description"),
            "active_at": a.get("activeAt"),
            "value": a.get("value"),
        } for a in data.get("alerts", [])]


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, 4)  # NaN -> None
