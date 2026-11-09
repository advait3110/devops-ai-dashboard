"""
Central configuration.

Every setting is read from environment variables (or the backend/.env file).
Nothing is hard-coded, so the same code runs on a laptop, in Docker and in
Kubernetes - only the environment changes (12-factor app principle).

Each integration is OFF / "not configured" until its variables are filled in.
That is what lets us add tools to the project one at a time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
load_dotenv(BASE_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _list(name: str, sep: str = ",") -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(sep) if item.strip()]


def _mapping(name: str) -> dict[str, str]:
    """Parse "name=path;name2=path2" into a dict (used for whitelisted log files)."""
    result: dict[str, str] = {}
    for pair in _list(name, sep=";"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            result[key.strip()] = value.strip()
    return result


@dataclass(frozen=True)
class Settings:
    # ---- general -------------------------------------------------------
    app_name: str = "DevOps AI Dashboard"
    environment: str = "development"
    cors_origins: list[str] = field(default_factory=list)
    data_dir: Path = BASE_DIR / "data"
    log_dir: Path = BASE_DIR / "logs"
    allow_actions: bool = True  # start/stop containers, trigger builds, ...
    serve_frontend_dir: str = ""  # optional: serve the built React app

    # ---- system monitoring (psutil) -----------------------------------
    sample_interval: int = 5  # seconds between metric samples
    history_size: int = 720  # 720 x 5s = 1 hour kept in RAM
    integration_poll_interval: int = 60  # seconds between tool health checks

    # ---- AI (Google Gemini) -------------------------------------------
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_model: str = "gemini-3.5-flash-lite"
    gemini_timeout: float = 60.0

    # ---- containers ---------------------------------------------------
    docker_enabled: bool = False
    kubernetes_enabled: bool = False
    kube_context: str = ""

    # ---- CI/CD ----------------------------------------------------------
    jenkins_url: str = ""
    jenkins_user: str = ""
    jenkins_token: str = ""
    github_token: str = ""
    github_repos: list[str] = field(default_factory=list)
    github_api_url: str = "https://api.github.com"

    # ---- monitoring stack -----------------------------------------------
    prometheus_url: str = ""
    grafana_url: str = ""

    # ---- AWS -------------------------------------------------------------
    aws_enabled: bool = False
    aws_region: str = "ap-south-1"

    # ---- logs --------------------------------------------------------------
    log_files: dict[str, str] = field(default_factory=dict)

    # ---- alerts ------------------------------------------------------------
    cpu_threshold: float = 85.0
    memory_threshold: float = 85.0
    disk_threshold: float = 90.0
    alert_for_samples: int = 3  # breach must last N samples before firing
    alert_webhook_url: str = ""
    alert_webhook_format: str = "slack"  # slack | discord | generic

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            app_name=_str("APP_NAME", "DevOps AI Dashboard"),
            environment=_str("APP_ENV", "development"),
            cors_origins=_list("CORS_ORIGINS")
            or ["http://localhost:5173", "http://127.0.0.1:5173"],
            data_dir=Path(_str("DATA_DIR") or BASE_DIR / "data"),
            log_dir=Path(_str("LOG_DIR") or BASE_DIR / "logs"),
            allow_actions=_bool("ALLOW_ACTIONS", True),
            serve_frontend_dir=_str("SERVE_FRONTEND_DIR"),
            sample_interval=max(1, _int("SAMPLE_INTERVAL", 5)),
            history_size=max(60, _int("HISTORY_SIZE", 720)),
            integration_poll_interval=max(15, _int("INTEGRATION_POLL_INTERVAL", 60)),
            gemini_api_key=_str("GEMINI_API_KEY"),
            gemini_model=_str("GEMINI_MODEL", "gemini-3.8-flash"),
            gemini_fallback_model=_str("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite"),
            gemini_timeout=_float("GEMINI_TIMEOUT", 60.0),
            docker_enabled=_bool("DOCKER_ENABLED", False),
            kubernetes_enabled=_bool("KUBERNETES_ENABLED", False),
            kube_context=_str("KUBE_CONTEXT"),
            jenkins_url=_str("JENKINS_URL").rstrip("/"),
            jenkins_user=_str("JENKINS_USER"),
            jenkins_token=_str("JENKINS_TOKEN"),
            github_token=_str("GITHUB_TOKEN"),
            github_repos=_list("GITHUB_REPOS"),
            github_api_url=_str("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
            prometheus_url=_str("PROMETHEUS_URL").rstrip("/"),
            grafana_url=_str("GRAFANA_URL").rstrip("/"),
            aws_enabled=_bool("AWS_ENABLED", False),
            aws_region=_str("AWS_REGION", "ap-south-1"),
            log_files=_mapping("LOG_FILES"),
            cpu_threshold=_float("ALERT_CPU_THRESHOLD", 85.0),
            memory_threshold=_float("ALERT_MEMORY_THRESHOLD", 85.0),
            disk_threshold=_float("ALERT_DISK_THRESHOLD", 90.0),
            alert_for_samples=max(1, _int("ALERT_FOR_SAMPLES", 3)),
            alert_webhook_url=_str("ALERT_WEBHOOK_URL"),
            alert_webhook_format=_str("ALERT_WEBHOOK_FORMAT", "slack").lower(),
        )


settings = Settings.from_env()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.log_dir.mkdir(parents=True, exist_ok=True)
