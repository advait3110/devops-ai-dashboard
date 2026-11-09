"""
Module 2 - System Monitoring (psutil).

psutil reads CPU, memory, disk, network and process information directly
from the operating system (/proc on Linux, Win32 APIs on Windows), so this
module works on both without any extra agent.

How it stays lightweight:
* One background task calls sample() every SAMPLE_INTERVAL seconds.
* cpu_percent(interval=None) is NON-blocking: it compares with the previous
  call instead of sleeping for 1 second (the old code slept on every request).
* History is kept in a collections.deque with a fixed maxlen (ring buffer),
  so memory usage is constant: 720 samples ~ 150 KB.
"""

from __future__ import annotations

import os
import platform
import socket
import time
from collections import deque
from typing import Any

import psutil

GB = 1024 ** 3


def _root_path() -> str:
    """'/' on Linux/macOS, 'C:\\' (the system drive) on Windows."""
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


class SystemMonitor:
    def __init__(self, history_size: int = 720) -> None:
        self.history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self.root = _root_path()
        self._last_net: tuple[float, Any] | None = None
        self._last_disk_io: tuple[float, Any] | None = None
        psutil.cpu_percent(interval=None)  # prime the CPU counter

    # ------------------------------------------------------------------ #
    def sample(self) -> dict[str, Any]:
        """Take one measurement and append it to the history ring buffer."""
        now = time.time()
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage(self.root)

        net_rx = net_tx = 0.0
        net = psutil.net_io_counters()
        if self._last_net:
            elapsed = max(now - self._last_net[0], 1e-6)
            net_rx = max(0.0, (net.bytes_recv - self._last_net[1].bytes_recv) / elapsed)
            net_tx = max(0.0, (net.bytes_sent - self._last_net[1].bytes_sent) / elapsed)
        self._last_net = (now, net)

        read_bps = write_bps = 0.0
        try:
            dio = psutil.disk_io_counters()
        except Exception:  # some VMs/containers do not expose disk counters
            dio = None
        if dio and self._last_disk_io:
            elapsed = max(now - self._last_disk_io[0], 1e-6)
            read_bps = max(0.0, (dio.read_bytes - self._last_disk_io[1].read_bytes) / elapsed)
            write_bps = max(0.0, (dio.write_bytes - self._last_disk_io[1].write_bytes) / elapsed)
        if dio:
            self._last_disk_io = (now, dio)

        try:
            load1, load5, load15 = psutil.getloadavg()
        except (AttributeError, OSError):
            load1 = load5 = load15 = 0.0

        point = {
            "timestamp": now,
            "cpu_percent": round(psutil.cpu_percent(interval=None), 1),
            "memory_percent": round(mem.percent, 1),
            "memory_used_gb": round(mem.used / GB, 2),
            "memory_total_gb": round(mem.total / GB, 2),
            "swap_percent": round(swap.percent, 1),
            "disk_percent": round(disk.percent, 1),
            "disk_used_gb": round(disk.used / GB, 1),
            "disk_total_gb": round(disk.total / GB, 1),
            "net_rx_bps": round(net_rx),
            "net_tx_bps": round(net_tx),
            "disk_read_bps": round(read_bps),
            "disk_write_bps": round(write_bps),
            "load_avg": [round(load1, 2), round(load5, 2), round(load15, 2)],
            "process_count": len(psutil.pids()),
        }
        self.history.append(point)
        return point

    def latest(self) -> dict[str, Any]:
        return self.history[-1] if self.history else self.sample()

    def history_points(self, minutes: int = 15) -> list[dict[str, Any]]:
        cutoff = time.time() - minutes * 60
        return [p for p in self.history if p["timestamp"] >= cutoff]

    # ------------------------------------------------------------------ #
    @staticmethod
    def info() -> dict[str, Any]:
        boot = psutil.boot_time()
        freq = None
        try:
            f = psutil.cpu_freq()
            freq = round(f.current) if f else None
        except Exception:
            pass
        return {
            "hostname": socket.gethostname(),
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "cpu_model": platform.processor() or platform.machine(),
            "cpu_physical_cores": psutil.cpu_count(logical=False),
            "cpu_logical_cores": psutil.cpu_count(logical=True),
            "cpu_freq_mhz": freq,
            "boot_time": boot,
            "uptime_seconds": int(time.time() - boot),
        }

    @staticmethod
    def disks() -> list[dict[str, Any]]:
        result = []
        seen = set()
        for part in psutil.disk_partitions(all=False):
            if part.mountpoint in seen or "cdrom" in part.opts or not part.fstype:
                continue
            if part.fstype in ("squashfs", "overlay", "tmpfs", "devtmpfs", "iso9660"):
                continue  # read-only images / RAM disks are always "100 % full"
            if part.mountpoint.startswith(("/snap", "/boot/efi", "/var/lib/docker")):
                continue
            seen.add(part.mountpoint)
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue
            result.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": round(usage.total / GB, 1),
                "used_gb": round(usage.used / GB, 1),
                "free_gb": round(usage.free / GB, 1),
                "percent": usage.percent,
            })
        return result

    @staticmethod
    def top_processes(limit: int = 10, sort: str = "cpu") -> list[dict[str, Any]]:
        """
        psutil caches Process objects inside process_iter(), so cpu_percent is
        measured since the previous call (the first call returns 0.0).
        """
        cores = psutil.cpu_count() or 1
        procs = []
        for p in psutil.process_iter(["pid", "name", "username", "status",
                                      "cpu_percent", "memory_percent", "memory_info"]):
            info = p.info
            if info["pid"] == 0:  # 'System Idle Process' on Windows
                continue
            mem_info = info.get("memory_info")
            procs.append({
                "pid": info["pid"],
                "name": info.get("name") or "?",
                "user": (info.get("username") or "").split("\\")[-1],
                "status": info.get("status"),
                "cpu_percent": round((info.get("cpu_percent") or 0.0) / cores, 1),
                "memory_percent": round(info.get("memory_percent") or 0.0, 1),
                "memory_mb": round(mem_info.rss / 1024 ** 2, 1) if mem_info else 0,
            })
        key = "memory_percent" if sort == "memory" else "cpu_percent"
        procs.sort(key=lambda x: x[key], reverse=True)
        return procs[:limit]
