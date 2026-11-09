"""API tests using FastAPI's TestClient (runs the real app in-process)."""

import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ.setdefault("LOG_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import state  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs the lifespan (background loops)
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_system_metrics(client):
    data = client.get("/api/system/metrics").json()
    assert 0 <= data["cpu_percent"] <= 100
    assert data["memory_total_gb"] > 0
    assert client.get("/api/system/processes?limit=3").status_code == 200
    assert isinstance(client.get("/api/system/disks").json(), list)


def test_overview(client):
    data = client.get("/api/overview").json()
    assert {"system", "alerts", "integrations", "pipelines"} <= set(data)
    names = {i["name"] for i in data["integrations"]}
    assert {"gemini", "docker", "kubernetes", "jenkins", "github", "prometheus"} <= names


def test_unconfigured_integration_returns_hint(client):
    if state.jenkins.configured:
        pytest.skip("Jenkins configured in this environment")
    r = client.get("/api/cicd/jenkins/jobs")
    assert r.status_code == 503
    assert r.json()["hint"]


def test_logs_app_source(client):
    r = client.get("/api/logs?source=app&tail=50")
    assert r.status_code == 200
    assert "analysis" in r.json()


def test_logs_reject_unknown_file(client):
    r = client.get("/api/logs?source=file&target=../../etc/passwd")
    assert r.status_code == 400


def test_alert_test_endpoint(client):
    assert client.post("/api/alerts/test").json()["sent"] is True
    alerts = client.get("/api/alerts?status=firing").json()
    assert any(a["key"] == "test:notification" for a in alerts)
    alert_id = next(a["id"] for a in alerts if a["key"] == "test:notification")
    assert client.post(f"/api/alerts/{alert_id}/resolve").status_code == 200


def test_ai_chat_uses_gemini(client, monkeypatch):
    captured = {}

    async def fake_generate(system, contents, temperature=0.4):
        captured["contents"] = contents
        return {"text": "Restart the container.", "model": "test-model"}

    monkeypatch.setattr(state.gemini, "api_key", "test-key")
    monkeypatch.setattr(state.gemini, "generate", fake_generate)
    r = client.post("/api/ai/chat", json={
        "messages": [{"role": "user", "content": "why is my cpu high? password=abc"}],
        "use_live_data": True})
    assert r.status_code == 200
    assert r.json()["reply"] == "Restart the container."
    sent = captured["contents"][-1]["parts"][0]["text"]
    assert "LIVE DASHBOARD DATA" in sent and "CPU" in sent
    assert "abc" not in sent  # secret was redacted


def test_prometheus_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "devops_dashboard" in r.text
