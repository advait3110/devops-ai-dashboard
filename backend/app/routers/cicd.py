"""Module 3 - CI/CD Monitoring endpoints (Jenkins + GitHub Actions)."""

from fastapi import APIRouter, Query

from .. import state
from ..config import settings
from ..errors import IntegrationError

router = APIRouter(prefix="/api/cicd", tags=["CI/CD"])


def _require_actions() -> None:
    if not settings.allow_actions:
        raise IntegrationError("Actions are disabled (ALLOW_ACTIONS=false)", 403)


# ------------------------------- Jenkins --------------------------------- #
@router.get("/jenkins/jobs")
async def jenkins_jobs():
    return await state.jenkins.jobs()


@router.get("/jenkins/builds")
async def jenkins_builds(job: str, limit: int = Query(10, ge=1, le=50)):
    return await state.jenkins.builds(job, limit)


@router.get("/jenkins/console")
async def jenkins_console(job: str, build: str = "lastBuild"):
    return {"job": job, "build": build, "log": await state.jenkins.console(job, build)}


@router.post("/jenkins/build")
async def jenkins_trigger(job: str):
    _require_actions()
    return await state.jenkins.trigger(job)


# ---------------------------- GitHub Actions ----------------------------- #
@router.get("/github/repos")
async def github_repos():
    return state.github.repos


@router.get("/github/runs")
async def github_runs(repo: str | None = None, limit: int = Query(15, ge=1, le=50)):
    if repo:
        return await state.github.runs(repo, limit)
    return await state.github.all_runs(limit)


@router.get("/github/jobs")
async def github_jobs(repo: str, run_id: int):
    return await state.github.jobs(repo, run_id)


@router.get("/github/logs")
async def github_job_logs(repo: str, job_id: int):
    return {"repo": repo, "job_id": job_id, "log": await state.github.job_logs(repo, job_id)}


@router.post("/github/rerun")
async def github_rerun(repo: str, run_id: int):
    _require_actions()
    return await state.github.rerun_failed(repo, run_id)
