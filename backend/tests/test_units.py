"""Unit tests for the pure logic (no external tools needed). Run: pytest -q"""

import struct

from app.services.alert_service import AlertManager, ThresholdRule
from app.services.docker_service import (
    _exit_code,
    _health_from_status,
    _parse_size,
    _state_from_status,
    demux_docker_stream,
)
from app.services.gemini_service import smart_excerpt
from app.services.github_service import run_status
from app.services.jenkins_service import build_status, job_path
from app.services.kubernetes_service import _cpu_to_millicores, _mem_to_mib
from app.services.log_service import analyse, detect_level, parse_wevtutil, tail_file
from app.utils.redact import redact


def test_redact_removes_common_secrets():
    text = ("password=hunter2 token: abc123 AKIAABCDEFGHIJKLMNOP "
            "https://bob:secret@github.com ghp_" + "a" * 36)
    out = redact(text)
    for secret in ("hunter2", "abc123", "AKIAABCDEFGHIJKLMNOP", "secret@", "ghp_aaaa"):
        assert secret not in out


def test_detect_level():
    assert detect_level("2024-01-01 ERROR db connection refused") == "error"
    assert detect_level("WARNING: disk almost full") == "warning"
    assert detect_level("pod OOMKilled") == "critical"
    assert detect_level("INFO server started") == "info"
    # explicit level field wins over words inside the message
    assert detect_level("2026-11-08 20:52:00 WARNING alerts: ALERT FIRING [critical] Pod x") == "warning"
    assert detect_level("2026/11/08 18:01:02 [error] 31#31: connect() failed") == "error"
    assert detect_level('time=1 level=warn msg="disk slow"') == "warning"
    assert detect_level("E1108 10:00:01.123 kubelet.go:1] sync failed") == "error"
    assert detect_level("INFO request completed, 0 errors") == "info"
    # free text without a level field falls back to keywords
    assert detect_level("Traceback (most recent call last):") == "error"


def test_analyse_groups_similar_errors():
    lines = [f"ERROR timeout after {n}ms to 10.0.0.{n}" for n in range(5)] + ["INFO ok"]
    result = analyse(lines)
    assert result["levels"]["error"] == 5
    assert result["top_errors"][0]["count"] == 5
    assert result["error_rate"] == round(5 / 6 * 100, 1)


def test_tail_file_reads_only_end(tmp_path):
    f = tmp_path / "big.log"
    f.write_text("\n".join(f"line {i}" for i in range(10_000)))
    out = tail_file(f, 3).splitlines()
    assert out == ["line 9997", "line 9998", "line 9999"]


def test_parse_wevtutil():
    sample = """Event[0]:
  Log Name: System
  Source: Service Control Manager
  Date: 2026-11-08T10:00:00.000
  Level: Error
  Description:
The Print Spooler service terminated unexpectedly.

Event[1]:
  Log Name: System
  Source: Kernel-General
  Date: 2026-11-08T09:00:00.000
  Level: Information
  Description:
The system time has changed.
"""
    lines = parse_wevtutil(sample).splitlines()
    assert len(lines) == 2
    assert "ERROR Service Control Manager" in lines[1]  # newest last
    assert detect_level(lines[1]) == "error"


def test_smart_excerpt_keeps_errors():
    text = "\n".join(["noise " * 20] * 2000 + ["FATAL: database is down"] + ["noise"] * 10)
    out = smart_excerpt(text, limit=5000)
    assert "FATAL: database is down" in out
    assert len(out) <= 5000


def test_docker_helpers():
    assert _state_from_status("Up 3 hours (healthy)") == "running"
    assert _state_from_status("Exited (137) 2 minutes ago") == "exited"
    assert _exit_code("Exited (137) 2 minutes ago") == 137
    assert _health_from_status("Up 1 minute (unhealthy)") == "unhealthy"
    assert round(_parse_size("1.5GiB")) == round(1.5 * 1024 ** 3)
    frame = b"\x01\x00\x00\x00" + struct.pack(">I", 5) + b"hello"
    frame += b"\x02\x00\x00\x00" + struct.pack(">I", 6) + b" world"
    assert demux_docker_stream(frame) == "hello world"


def test_ci_status_mapping():
    assert build_status({"building": True}) == "running"
    assert build_status({"result": "FAILURE"}) == "failed"
    assert build_status(None) == "not_built"
    assert job_path("folder/my job") == "/job/folder/job/my%20job"
    assert run_status({"status": "completed", "conclusion": "failure"}) == "failed"
    assert run_status({"status": "in_progress"}) == "running"


def test_k8s_unit_conversion():
    assert _cpu_to_millicores("250m") == 250
    assert _cpu_to_millicores("1") == 1000
    assert _cpu_to_millicores("1500000n") == 1
    assert _mem_to_mib("1Gi") == 1024
    assert _mem_to_mib("2048Ki") == 2


def test_alert_state_machine(tmp_path):
    am = AlertManager(tmp_path / "a.db", [ThresholdRule("system:cpu", "cpu_percent", "CPU", 80)],
                      for_samples=3)
    for _ in range(2):
        am.evaluate_system({"cpu_percent": 95})
    assert am.summary()["firing"] == 0  # not yet: needs 3 samples
    am.evaluate_system({"cpu_percent": 95})
    assert am.summary()["firing"] == 1
    am.evaluate_system({"cpu_percent": 96})
    assert len(am.list()) == 1  # no duplicate
    am.evaluate_system({"cpu_percent": 78})  # inside hysteresis band: still firing
    assert am.summary()["firing"] == 1
    am.evaluate_system({"cpu_percent": 40})
    assert am.summary()["firing"] == 0
    assert am.list()[0]["status"] == "resolved"


def test_alert_sync_source(tmp_path):
    am = AlertManager(tmp_path / "a.db", [])
    am.sync_source("docker", {"docker:web": {"severity": "warning", "title": "web crashed"}})
    assert am.summary()["warning"] == 1
    am.sync_source("docker", {})
    assert am.summary()["firing"] == 0
