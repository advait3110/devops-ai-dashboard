"""Grafana health check - Grafana itself is opened/embedded from the frontend."""

from __future__ import annotations

from typing import Any

import httpx

from ..errors import status_payload

HINT = ("Start the monitoring stack ('docker compose --profile monitoring up -d') and set "
        "GRAFANA_URL=http://localhost:3000 in backend/.env.")


class GrafanaService:
    name = "grafana"
    label = "Grafana"

    def __init__(self, url: str) -> None:
        self.url = url

    async def status(self) -> dict[str, Any]:
        if not self.url:
            return status_payload(self.name, self.label, False, False, "Not configured", HINT)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.url}/api/health")
            data = resp.json()
            return status_payload(self.name, self.label, True, data.get("database") == "ok",
                                  f"Grafana {data.get('version', '?')}", url=self.url)
        except (httpx.HTTPError, ValueError) as exc:
            return status_payload(self.name, self.label, True, False,
                                  f"Unreachable: {exc.__class__.__name__}", HINT, url=self.url)
