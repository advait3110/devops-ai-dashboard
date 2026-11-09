"""
Module 7 - Log Analysis.

Log sources (all real):
  app         this backend's own rotating log file (logs/app.log)
  file        files whitelisted in LOG_FILES, e.g. nginx=/var/log/nginx/error.log
  docker      'docker logs' of a container
  kubernetes  pod logs from the Kubernetes API
  system      Linux: journalctl / syslog,  Windows: Event Log via 'wevtutil'

Analysis (done locally, no AI needed):
  * detect the level of each line (critical / error / warning / info / debug)
  * count lines per level
  * group similar errors by replacing variable parts (numbers, ids, IPs,
    timestamps) with placeholders, so "timeout after 31ms" and
    "timeout after 87ms" count as the same problem
The AI is only called when the user presses "Explain with AI".

Security: arbitrary paths can NOT be requested from the browser - only the
names configured in LOG_FILES. Otherwise anyone could read /etc/shadow.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ..errors import IntegrationError
from ..utils.shell import CommandError, run, tool_available

# 1) An explicit level field written by the logger always wins:
#    "2026-11-08 10:00:01 WARNING ...", "[error]" (nginx), "level=warn" (Go/logfmt),
#    "E1108 10:00:01" (Kubernetes klog). Only the first 100 characters are checked,
#    so words inside the MESSAGE ("... ALERT FIRING [critical]") do not count.
_EXPLICIT = re.compile(
    r"\b(CRITICAL|FATAL|PANIC|EMERG|ERROR|ERR|WARNING|WARN|NOTICE|INFO|DEBUG|TRACE)\b"
    r"|\[(crit|emerg|alert|error|warn|notice|info|debug)\]"
    r"|\blevel[=:]\s*\"?(\w+)"
    r"|^([EWIF])\d{4}\s",
    re.I,
)
_EXPLICIT_MAP = {
    "critical": "critical", "fatal": "critical", "panic": "critical", "emerg": "critical",
    "crit": "critical", "alert": "critical", "f": "critical",
    "error": "error", "err": "error", "e": "error",
    "warning": "warning", "warn": "warning", "w": "warning",
    "notice": "info", "info": "info", "i": "info", "debug": "debug", "trace": "debug",
}

# 2) Fallback for free-text lines without a level field (build output, stack traces).
LEVEL_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("critical", re.compile(r"(?i)\b(fatal|panic)\b|OOMKilled|out of memory")),
    ("error", re.compile(r"(?i)\b(error|exception|traceback|failed|failure|denied|refused|"
                         r"crashloopbackoff|segfault)\b")),
    ("warning", re.compile(r"(?i)\b(warn|warning|deprecated|retry(ing)?|timeout|timed out)\b")),
]

_NORMALISERS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), ""),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b0x[0-9a-f]+\b|\b[0-9a-f]{12,64}\b", re.I), "<hex>"),
    (re.compile(r"\d+"), "<n>"),
    (re.compile(r"\s+"), " "),
]

SYSTEM_LOG_FILES = ["/var/log/syslog", "/var/log/messages"]


def detect_level(line: str) -> str:
    for match in _EXPLICIT.finditer(line[:100]):
        token = next(g for g in match.groups() if g).lower()
        # Upper-case words like ERROR are level fields; lower-case "error" in prose is not
        # (except inside [brackets], level=..., or klog prefixes, which are always fields).
        if match.group(1) and not match.group(1).isupper():
            continue
        if token in _EXPLICIT_MAP:
            return _EXPLICIT_MAP[token]
    for level, pattern in LEVEL_RULES:
        if pattern.search(line):
            return level
    return "info"


def normalise(line: str) -> str:
    for pattern, repl in _NORMALISERS:
        line = pattern.sub(repl, line)
    return line.strip()[:200]


def analyse(lines: list[str]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    groups: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for line in lines:
        level = detect_level(line)
        counts[level] += 1
        if level in ("error", "critical"):
            key = normalise(line)
            groups[key] += 1
            examples.setdefault(key, line[:300])
    total = len(lines)
    problems = counts["error"] + counts["critical"]
    return {
        "total_lines": total,
        "levels": {lvl: counts.get(lvl, 0) for lvl in ("critical", "error", "warning", "info", "debug")},
        "error_rate": round(problems / total * 100, 1) if total else 0.0,
        "top_errors": [{"pattern": k, "count": c, "example": examples[k]} for k, c in groups.most_common(5)],
    }


def tail_file(path: str | Path, lines: int = 300, block: int = 8192) -> str:
    """Read only the END of a file (works on multi-GB logs without loading them)."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        data, pos = b"", size
        while pos > 0 and data.count(b"\n") <= lines:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
    return b"\n".join(data.splitlines()[-lines:]).decode("utf-8", errors="replace")


def parse_wevtutil(text: str) -> str:
    """Turn 'wevtutil /f:text' multi-line records into one line per event."""
    events, current = [], {}
    desc_mode = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Event["):
            if current:
                events.append(current)
            current, desc_mode = {}, False
            continue
        if desc_mode:
            if line:
                current["Description"] = (current.get("Description", "") + " " + line).strip()
            continue
        if line.startswith("Description:"):
            desc_mode = True
            current["Description"] = line.split(":", 1)[1].strip()
        elif ":" in line:
            k, v = line.split(":", 1)
            current[k.strip()] = v.strip()
    if current:
        events.append(current)
    out = [f"{e.get('Date', '')} {e.get('Level', 'Information').upper()} "
           f"{e.get('Source', '')}: {e.get('Description', '')[:400]}" for e in events]
    return "\n".join(reversed(out))  # oldest first, like other logs


class LogService:
    def __init__(self, app_log: Path, files: dict[str, str], docker, kubernetes) -> None:
        self.app_log = app_log
        self.files = files
        self.docker = docker
        self.kubernetes = kubernetes

    async def sources(self) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = [
            {"id": "app", "label": "Dashboard backend", "type": "app", "targets": []},
        ]
        files = [{"value": name, "label": f"{name} ({path})", "available": os.path.isfile(path)}
                 for name, path in self.files.items()]
        if files:
            sources.append({"id": "file", "label": "Log files", "type": "file", "targets": files})

        sources.append({"id": "system", "label": "Operating system", "type": "system",
                        "targets": [], "available": self._system_mode() is not None})

        if self.docker.enabled:
            try:
                containers = await self.docker.list_containers()
                sources.append({"id": "docker", "label": "Docker containers", "type": "docker",
                                "targets": [{"value": c["name"], "label": f"{c['name']} ({c['state']})"}
                                            for c in containers]})
            except IntegrationError:
                pass
        if self.kubernetes.enabled:
            try:
                pods = await self.kubernetes.pods()
                sources.append({"id": "kubernetes", "label": "Kubernetes pods", "type": "kubernetes",
                                "targets": [{"value": f"{p['namespace']}/{p['name']}",
                                             "label": f"{p['namespace']}/{p['name']} ({p['status']})"}
                                            for p in pods]})
            except IntegrationError:
                pass
        return sources

    @staticmethod
    def _system_mode() -> str | None:
        if sys.platform == "win32":
            return "wevtutil" if tool_available("wevtutil") else None
        if tool_available("journalctl") and os.path.isdir("/run/systemd/system"):
            return "journalctl"
        for path in SYSTEM_LOG_FILES:
            if os.access(path, os.R_OK):
                return path
        return None

    async def read(self, source: str, target: str = "", tail: int = 300) -> str:
        tail = max(10, min(tail, 2000))
        if source == "app":
            return tail_file(self.app_log, tail) if self.app_log.exists() else ""
        if source == "file":
            if target not in self.files:
                raise IntegrationError("Unknown log file. Add it to LOG_FILES in backend/.env", 400)
            path = self.files[target]
            if not os.path.isfile(path):
                raise IntegrationError(f"File not found: {path}", 404)
            try:
                return tail_file(path, tail)
            except PermissionError as exc:
                raise IntegrationError(f"No permission to read {path}", 403) from exc
        if source == "docker":
            return await self.docker.logs(target, tail)
        if source == "kubernetes":
            ns, _, pod = target.partition("/")
            return await self.kubernetes.pod_logs(ns, pod, tail=tail)
        if source == "system":
            return await self._system_logs(tail)
        raise IntegrationError(f"Unknown log source '{source}'", 400)

    async def _system_logs(self, tail: int) -> str:
        mode = self._system_mode()
        try:
            if mode == "wevtutil":
                count = min(tail, 300)  # event records are long
                text = await run(["wevtutil", "qe", "System", f"/c:{count}", "/rd:true", "/f:text"], timeout=30)
                return parse_wevtutil(text)
            if mode == "journalctl":
                return await run(["journalctl", "-n", str(tail), "--no-pager", "-o", "short-iso"], timeout=20)
        except CommandError as exc:
            raise IntegrationError(f"Could not read system logs: {exc}", 503) from exc
        if mode:
            return tail_file(mode, tail)
        raise IntegrationError("No readable system log on this machine", 503,
                               "On Linux add your user to the 'adm' or 'systemd-journal' group.")
