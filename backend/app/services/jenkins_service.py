"""
Module 3a - Jenkins pipeline monitoring.

Jenkins exposes every page as JSON by adding /api/json to the URL.
The `tree` query parameter asks only for the fields we need, which keeps the
response tiny (important when polling).

Authentication: username + API token (Jenkins > your user > Security >
API Token). With an API token Jenkins does not require a CSRF crumb for POSTs.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from ..errors import IntegrationError, status_payload
from ..utils.cache import ttl_cache

HINT = ("Run Jenkins (see docs/PHASES.md), create an API token, then set JENKINS_URL, "
        "JENKINS_USER and JENKINS_TOKEN in backend/.env.")

BUILD_FIELDS = "number,result,timestamp,duration,building,url"
JOB_FIELDS = f"name,url,color,_class,lastBuild[{BUILD_FIELDS}],healthReport[score,description]"
_JOB_RE = re.compile(r"^[\w .\-/]+$")


def build_status(build: dict | None) -> str:
    if not build:
        return "not_built"
    if build.get("building"):
        return "running"
    return {
        "SUCCESS": "success",
        "FAILURE": "failed",
        "UNSTABLE": "unstable",
        "ABORTED": "cancelled",
        "NOT_BUILT": "not_built",
    }.get(build.get("result") or "", "unknown")


def job_path(name: str) -> str:
    """'folder/my-job' -> '/job/folder/job/my-job' (Jenkins folder URL scheme)."""
    if not _JOB_RE.match(name) or ".." in name:
        raise IntegrationError("Invalid job name", 400)
    return "".join(f"/job/{quote(part)}" for part in name.split("/") if part)


class JenkinsService:
    name = "jenkins"
    label = "Jenkins"

    def __init__(self, url: str, user: str, token: str) -> None:
        self.url, self.user, self.token = url, user, token

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def _request(self, method: str, path: str, params: dict | None = None,
                       as_text: bool = False, timeout: float = 15) -> Any:
        if not self.configured:
            raise IntegrationError("Jenkins is not configured", 503, HINT)
        auth = (self.user, self.token) if self.user and self.token else None
        async with httpx.AsyncClient(base_url=self.url, auth=auth, timeout=timeout,
                                     follow_redirects=True) as client:
            try:
                resp = await client.request(method, path, params=params)
            except httpx.HTTPError as exc:
                raise IntegrationError(f"Jenkins unreachable at {self.url}: {exc.__class__.__name__}",
                                       503, HINT) from exc
        if resp.status_code in (401, 403):
            raise IntegrationError("Jenkins rejected the credentials", 502, HINT)
        if resp.status_code == 404:
            raise IntegrationError("Jenkins job or build not found", 404)
        if resp.status_code >= 400:
            raise IntegrationError(f"Jenkins returned HTTP {resp.status_code}", 502)
        if method != "GET":
            return {"status_code": resp.status_code, "location": resp.headers.get("Location")}
        return resp.text if as_text else resp.json()

    async def status(self) -> dict[str, Any]:
        if not self.configured:
            return status_payload(self.name, self.label, False, False, "Not configured", HINT)
        try:
            data = await self._request("GET", "/api/json", params={"tree": "mode,nodeDescription"})
            return status_payload(self.name, self.label, True, True,
                                  data.get("nodeDescription") or "Connected", url=self.url)
        except IntegrationError as exc:
            return status_payload(self.name, self.label, True, False, exc.message, HINT, url=self.url)

    @ttl_cache(ttl=10)
    async def jobs(self) -> list[dict[str, Any]]:
        tree = f"jobs[{JOB_FIELDS},jobs[{JOB_FIELDS}]]"  # top level + one folder level
        data = await self._request("GET", "/api/json", params={"tree": tree})
        result: list[dict[str, Any]] = []

        def add(job: dict, prefix: str = "") -> None:
            full = f"{prefix}{job['name']}"
            if job.get("jobs") is not None and "Folder" in job.get("_class", ""):
                for child in job["jobs"]:
                    add(child, f"{full}/")
                return
            last = job.get("lastBuild")
            health = (job.get("healthReport") or [{}])[0]
            result.append({
                "name": full,
                "url": job.get("url"),
                "type": job.get("_class", "").split(".")[-1],
                "status": build_status(last),
                "last_build": last,
                "health_score": health.get("score"),
                "health": health.get("description"),
            })

        for job in data.get("jobs", []):
            add(job)
        return result

    async def builds(self, job: str, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._request("GET", f"{job_path(job)}/api/json",
                                   params={"tree": f"builds[{BUILD_FIELDS}]{{0,{limit}}}"})
        return [{**b, "status": build_status(b)} for b in data.get("builds", [])]

    async def console(self, job: str, number: int | str = "lastBuild", max_lines: int = 400) -> str:
        if not (str(number).isdigit() or number in ("lastBuild", "lastFailedBuild")):
            raise IntegrationError("Invalid build number", 400)
        text = await self._request("GET", f"{job_path(job)}/{number}/consoleText", as_text=True, timeout=30)
        lines = text.splitlines()
        return "\n".join(lines[-max_lines:])

    async def trigger(self, job: str) -> dict[str, Any]:
        result = await self._request("POST", f"{job_path(job)}/build")
        self.jobs.cache_clear()  # type: ignore[attr-defined]
        return {"queued": True, **result}
