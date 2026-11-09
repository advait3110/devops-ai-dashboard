"""
Module 3b - GitHub Actions monitoring.

Uses the official GitHub REST API (api.github.com):
  GET  /repos/{owner}/{repo}/actions/runs              -> workflow runs
  GET  /repos/{owner}/{repo}/actions/runs/{id}/jobs    -> jobs + steps
  GET  /repos/{owner}/{repo}/actions/jobs/{id}/logs    -> raw job log (redirect)
  POST /repos/{owner}/{repo}/actions/runs/{id}/rerun-failed-jobs

A fine-grained personal access token with "Actions: read" (and "write" for
re-runs) is recommended. Public repos work without a token but are limited
to 60 requests/hour, so responses are cached.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from ..errors import IntegrationError, status_payload
from ..utils.cache import ttl_cache

HINT = ("Set GITHUB_REPOS=owner/repo (comma separated) and GITHUB_TOKEN "
        "(fine-grained token with Actions read access) in backend/.env.")
_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


def run_status(run: dict) -> str:
    if run.get("status") != "completed":
        return "running" if run.get("status") == "in_progress" else "queued"
    return {
        "success": "success",
        "failure": "failed",
        "cancelled": "cancelled",
        "timed_out": "failed",
        "skipped": "cancelled",
        "action_required": "unstable",
        "neutral": "success",
        "startup_failure": "failed",
    }.get(run.get("conclusion") or "", "unknown")


class GitHubActionsService:
    name = "github"
    label = "GitHub Actions"

    def __init__(self, token: str, repos: list[str], api_url: str = "https://api.github.com") -> None:
        self.token = token
        self.api_url = api_url
        self.repos = [r for r in repos if _REPO_RE.match(r)]

    @property
    def configured(self) -> bool:
        return bool(self.repos)

    def _check_repo(self, repo: str) -> str:
        if repo not in self.repos:
            raise IntegrationError(f"Repository '{repo}' is not in GITHUB_REPOS", 400, HINT)
        return repo

    async def _get(self, path: str, params: dict | None = None, as_text: bool = False) -> Any:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(base_url=self.api_url, headers=headers, timeout=20,
                                     follow_redirects=True) as client:
            try:
                resp = await client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise IntegrationError(f"GitHub unreachable: {exc.__class__.__name__}", 503) from exc
        if resp.status_code == 401:
            raise IntegrationError("GitHub token is invalid or expired", 502, HINT)
        if resp.status_code == 403 and resp.headers.get("x-ratelimit-remaining") == "0":
            raise IntegrationError("GitHub API rate limit reached - add a GITHUB_TOKEN", 429, HINT)
        if resp.status_code == 404:
            raise IntegrationError("Not found (private repo needs a token with access)", 404, HINT)
        if resp.status_code >= 400:
            raise IntegrationError(f"GitHub returned HTTP {resp.status_code}", 502)
        return resp.text if as_text else resp.json()

    async def status(self) -> dict[str, Any]:
        if not self.configured:
            return status_payload(self.name, self.label, False, False, "Not configured", HINT)
        try:
            data = await self._get("/rate_limit")
            core = data.get("resources", {}).get("core", {})
            return status_payload(self.name, self.label, True, True,
                                  f"{len(self.repos)} repo(s), API quota {core.get('remaining')}/{core.get('limit')}")
        except IntegrationError as exc:
            return status_payload(self.name, self.label, True, False, exc.message, HINT)

    @ttl_cache(ttl=30)
    async def runs(self, repo: str, limit: int = 15) -> list[dict[str, Any]]:
        self._check_repo(repo)
        data = await self._get(f"/repos/{repo}/actions/runs", params={"per_page": limit})
        return [{
            "id": r["id"],
            "repo": repo,
            "workflow": r.get("name"),
            "title": r.get("display_title"),
            "branch": r.get("head_branch"),
            "event": r.get("event"),
            "commit": (r.get("head_sha") or "")[:7],
            "actor": (r.get("actor") or {}).get("login"),
            "run_number": r.get("run_number"),
            "status": run_status(r),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "url": r.get("html_url"),
        } for r in data.get("workflow_runs", [])]

    async def all_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.configured:
            raise IntegrationError("GitHub Actions is not configured", 503, HINT)
        result = []
        for repo in self.repos:
            result.extend(await self.runs(repo, limit))
        result.sort(key=lambda r: r["created_at"] or "", reverse=True)
        return result

    async def jobs(self, repo: str, run_id: int) -> list[dict[str, Any]]:
        self._check_repo(repo)
        data = await self._get(f"/repos/{repo}/actions/runs/{int(run_id)}/jobs")
        return [{
            "id": j["id"],
            "name": j.get("name"),
            "status": run_status(j),
            "started_at": j.get("started_at"),
            "completed_at": j.get("completed_at"),
            "url": j.get("html_url"),
            "steps": [{"name": s.get("name"), "number": s.get("number"), "status": run_status(s)}
                      for s in j.get("steps", [])],
        } for j in data.get("jobs", [])]

    async def job_logs(self, repo: str, job_id: int, max_lines: int = 400) -> str:
        self._check_repo(repo)
        text = await self._get(f"/repos/{repo}/actions/jobs/{int(job_id)}/logs", as_text=True)
        return "\n".join(text.splitlines()[-max_lines:])

    async def rerun_failed(self, repo: str, run_id: int) -> dict[str, Any]:
        self._check_repo(repo)
        if not self.token:
            raise IntegrationError("Re-running workflows requires GITHUB_TOKEN", 403, HINT)
        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}",
                   "X-GitHub-Api-Version": "2022-11-28"}
        async with httpx.AsyncClient(base_url=self.api_url, headers=headers, timeout=20) as client:
            resp = await client.post(f"/repos/{repo}/actions/runs/{int(run_id)}/rerun-failed-jobs")
        if resp.status_code >= 400:
            try:
                reason = resp.json().get("message", "")
            except ValueError:
                reason = resp.text[:200]
            raise IntegrationError(f"GitHub refused the re-run (HTTP {resp.status_code}): {reason}", 502)
        self.runs.cache_clear()  # type: ignore[attr-defined]
        return {"rerun": True}
