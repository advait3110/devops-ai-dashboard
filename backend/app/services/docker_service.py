"""
Module 4a - Docker container monitoring.

Two real transports, chosen automatically:

1. Docker CLI ("docker ps", "docker stats", ...)  -> used on your laptop
   (Docker Desktop on Windows, Docker Engine on Linux). No Python SDK needed.
2. Docker Engine REST API over the Unix socket /var/run/docker.sock
   -> used when the backend itself runs inside a container (docker-compose
   mounts the socket). httpx can talk HTTP over a Unix socket natively.

Both return the same normalised dictionaries, so the rest of the app does not
care which transport was used.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import struct
from typing import Any

import httpx

from ..errors import IntegrationError, status_payload
from ..utils.shell import CommandError, run, tool_available

SOCKET_PATH = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_EXIT_RE = re.compile(r"Exited \((\-?\d+)\)")

HINT = ("Install/start Docker Desktop (or Docker Engine) and set DOCKER_ENABLED=true "
        "in backend/.env. In docker-compose the socket /var/run/docker.sock is mounted.")


def _validate_id(container: str) -> str:
    # Blocks option injection such as "--help" and path tricks.
    if not _ID_RE.match(container):
        raise IntegrationError("Invalid container id or name", 400)
    return container


def _parse_size(text: str) -> float:
    """'12.5MiB' -> bytes."""
    m = re.match(r"\s*([\d.]+)\s*([KMGT]?i?B)", text or "")
    if not m:
        return 0.0
    units = {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
             "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3, "TIB": 1024 ** 4}
    return float(m.group(1)) * units.get(m.group(2).upper(), 1)


def _state_from_status(status: str) -> str:
    s = (status or "").lower()
    if s.startswith("up"):
        return "paused" if "paused" in s else "running"
    if s.startswith("exited"):
        return "exited"
    if s.startswith("restarting"):
        return "restarting"
    if s.startswith("created"):
        return "created"
    return s.split(" ")[0] if s else "unknown"


def _health_from_status(status: str) -> str | None:
    for h in ("unhealthy", "healthy", "health: starting"):
        if h in (status or "").lower():
            return "starting" if "starting" in h else h
    return None


def _exit_code(status: str) -> int | None:
    m = _EXIT_RE.search(status or "")
    return int(m.group(1)) if m else None


def demux_docker_stream(raw: bytes) -> str:
    """
    The Engine API multiplexes stdout/stderr when a container has no TTY:
    every frame = 8-byte header [stream, 0, 0, 0, size(4 bytes big-endian)] + payload.
    """
    out, i = [], 0
    if len(raw) >= 8 and raw[0] in (0, 1, 2) and raw[1:4] == b"\x00\x00\x00":
        while i + 8 <= len(raw):
            size = struct.unpack(">I", raw[i + 4:i + 8])[0]
            out.append(raw[i + 8:i + 8 + size])
            i += 8 + size
        return b"".join(out).decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")  # TTY containers are not multiplexed


class DockerService:
    name = "docker"
    label = "Docker"

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    # ------------------------------------------------------------------ #
    @property
    def mode(self) -> str | None:
        if tool_available("docker"):
            return "cli"
        if os.path.exists(SOCKET_PATH):
            return "socket"
        return None

    def _require(self) -> str:
        if not self.enabled:
            raise IntegrationError("Docker integration is disabled", 503, HINT)
        mode = self.mode
        if not mode:
            raise IntegrationError("Docker CLI not found and no Docker socket available", 503, HINT)
        return mode

    async def _api(self, method: str, path: str, timeout: float = 15, **kwargs) -> httpx.Response:
        transport = httpx.AsyncHTTPTransport(uds=SOCKET_PATH)
        async with httpx.AsyncClient(transport=transport, base_url="http://docker",
                                     timeout=timeout) as client:
            try:
                resp = await client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise IntegrationError(f"Docker socket error: {exc}", 503, HINT) from exc
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("message", resp.text)
            except ValueError:
                msg = resp.text
            raise IntegrationError(f"Docker API: {msg}", 502 if resp.status_code >= 500 else resp.status_code)
        return resp

    async def _cli(self, *args: str, timeout: float = 20, merge_stderr: bool = False) -> str:
        try:
            return await run(["docker", *args], timeout=timeout, merge_stderr=merge_stderr)
        except CommandError as exc:
            raise IntegrationError(f"Docker: {exc}", 503, HINT) from exc

    # ------------------------------------------------------------------ #
    async def status(self) -> dict[str, Any]:
        if not self.enabled:
            return status_payload(self.name, self.label, False, False, "Disabled", HINT)
        try:
            info = await self.info()
            return status_payload(self.name, self.label, True, True,
                                  f"Engine {info['server_version']} via {info['mode']}")
        except IntegrationError as exc:
            return status_payload(self.name, self.label, True, False, exc.message, exc.hint or HINT)

    async def info(self) -> dict[str, Any]:
        mode = self._require()
        if mode == "cli":
            data = json.loads(await self._cli("info", "--format", "{{json .}}", timeout=10))
        else:
            data = (await self._api("GET", "/info")).json()
        if data.get("ServerErrors"):
            raise IntegrationError("Docker daemon is not running: " + "; ".join(data["ServerErrors"]), 503, HINT)
        return {
            "mode": mode,
            "server_version": data.get("ServerVersion", "?"),
            "containers": data.get("Containers", 0),
            "running": data.get("ContainersRunning", 0),
            "paused": data.get("ContainersPaused", 0),
            "stopped": data.get("ContainersStopped", 0),
            "images": data.get("Images", 0),
            "os": data.get("OperatingSystem", ""),
            "cpus": data.get("NCPU"),
            "memory_gb": round((data.get("MemTotal") or 0) / 1024 ** 3, 1),
        }

    async def list_containers(self) -> list[dict[str, Any]]:
        mode = self._require()
        items: list[dict[str, Any]] = []
        if mode == "cli":
            out = await self._cli("ps", "-a", "--no-trunc", "--format", "{{json .}}")
            for line in out.splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                status = c.get("Status", "")
                items.append({
                    "id": c.get("ID", "")[:12],
                    "name": c.get("Names", "").split(",")[0],
                    "image": c.get("Image", ""),
                    "state": (c.get("State") or _state_from_status(status)).lower(),
                    "status": status,
                    "health": _health_from_status(status),
                    "exit_code": _exit_code(status),
                    "ports": c.get("Ports", ""),
                    "created": c.get("CreatedAt", ""),
                    "compose_project": _label(c.get("Labels", ""), "com.docker.compose.project"),
                })
        else:
            for c in (await self._api("GET", "/containers/json", params={"all": "1"})).json():
                status = c.get("Status", "")
                ports = ", ".join(
                    f"{p.get('PublicPort')}->{p.get('PrivatePort')}/{p.get('Type')}" if p.get("PublicPort")
                    else f"{p.get('PrivatePort')}/{p.get('Type')}"
                    for p in c.get("Ports", [])
                )
                items.append({
                    "id": c["Id"][:12],
                    "name": (c.get("Names") or ["/?"])[0].lstrip("/"),
                    "image": c.get("Image", ""),
                    "state": c.get("State", _state_from_status(status)),
                    "status": status,
                    "health": _health_from_status(status),
                    "exit_code": _exit_code(status),
                    "ports": ports,
                    "created": c.get("Created"),
                    "compose_project": (c.get("Labels") or {}).get("com.docker.compose.project"),
                })
        order = {"running": 0, "restarting": 1, "paused": 2}
        items.sort(key=lambda x: (order.get(x["state"], 3), x["name"]))
        return items

    async def stats(self) -> dict[str, dict[str, Any]]:
        """CPU / memory per running container (one snapshot, ~1-2 s)."""
        mode = self._require()
        result: dict[str, dict[str, Any]] = {}
        if mode == "cli":
            out = await self._cli("stats", "--no-stream", "--format", "{{json .}}", timeout=30)
            for line in out.splitlines():
                if not line.strip():
                    continue
                s = json.loads(line)
                used, _, limit = (s.get("MemUsage") or "0B / 0B").partition("/")
                result[s.get("ID", "")[:12]] = {
                    "cpu_percent": float((s.get("CPUPerc") or "0").rstrip("%") or 0),
                    "memory_percent": float((s.get("MemPerc") or "0").rstrip("%") or 0),
                    "memory_used_mb": round(_parse_size(used) / 1024 ** 2, 1),
                    "memory_limit_mb": round(_parse_size(limit) / 1024 ** 2, 1),
                    "net_io": s.get("NetIO", ""),
                    "block_io": s.get("BlockIO", ""),
                    "pids": s.get("PIDs", ""),
                }
            return result

        running = [c for c in await self.list_containers() if c["state"] == "running"]

        async def one(cid: str) -> None:
            s = (await self._api("GET", f"/containers/{cid}/stats", params={"stream": "false"})).json()
            cpu, pre = s.get("cpu_stats", {}), s.get("precpu_stats", {})
            cpu_delta = cpu.get("cpu_usage", {}).get("total_usage", 0) - pre.get("cpu_usage", {}).get("total_usage", 0)
            sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
            online = cpu.get("online_cpus") or 1
            mem = s.get("memory_stats", {})
            usage = mem.get("usage", 0) - (mem.get("stats", {}).get("inactive_file", 0))
            limit = mem.get("limit", 0) or 1
            result[cid] = {
                "cpu_percent": round(cpu_delta / sys_delta * online * 100, 2) if sys_delta > 0 else 0.0,
                "memory_percent": round(usage / limit * 100, 2),
                "memory_used_mb": round(usage / 1024 ** 2, 1),
                "memory_limit_mb": round(limit / 1024 ** 2, 1),
                "net_io": "", "block_io": "", "pids": s.get("pids_stats", {}).get("current", ""),
            }

        await asyncio.gather(*(one(c["id"]) for c in running), return_exceptions=True)
        return result

    async def logs(self, container: str, tail: int = 200) -> str:
        mode = self._require()
        container = _validate_id(container)
        tail = max(1, min(tail, 2000))
        if mode == "cli":
            return await self._cli("logs", "--tail", str(tail), "--timestamps", container, merge_stderr=True)
        resp = await self._api("GET", f"/containers/{container}/logs",
                               params={"stdout": 1, "stderr": 1, "tail": tail, "timestamps": 1})
        return demux_docker_stream(resp.content)

    async def action(self, container: str, action: str) -> dict[str, str]:
        if action not in {"start", "stop", "restart"}:
            raise IntegrationError("Unsupported action", 400)
        mode = self._require()
        container = _validate_id(container)
        if mode == "cli":
            await self._cli(action, container, timeout=60)
        else:
            await self._api("POST", f"/containers/{container}/{action}", timeout=60)
        return {"container": container, "action": action, "result": "ok"}


def _label(labels: str, key: str) -> str | None:
    for item in (labels or "").split(","):
        if item.startswith(key + "="):
            return item.split("=", 1)[1]
    return None
