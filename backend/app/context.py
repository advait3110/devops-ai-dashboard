"""
Builds the "live context" sent to Gemini when the user enables
"Use live dashboard data" in the assistant.

This is a simple form of RAG (Retrieval-Augmented Generation): instead of
the model guessing, we RETRIEVE the current facts (metrics, alerts,
containers, pods, pipelines) and put them in the prompt. Then a question
like "Why is my laptop slow?" is answered from real numbers.

Only short summaries are sent (a few hundred tokens) - never full dumps.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from . import state
from .errors import IntegrationError


async def _safe(coro, default):
    try:
        return await asyncio.wait_for(coro, timeout=15)
    except (IntegrationError, asyncio.TimeoutError):
        return default


async def build_live_context() -> str:
    m = state.monitor.latest()
    info = state.monitor.info()
    lines = [
        f"Time: {datetime.now().isoformat(timespec='seconds')}",
        f"Host: {info['hostname']} ({info['os']} {info['os_release']}, "
        f"{info['cpu_logical_cores']} logical CPUs, {m['memory_total_gb']} GB RAM)",
        f"CPU {m['cpu_percent']}% | Memory {m['memory_percent']}% ({m['memory_used_gb']} GB used) | "
        f"Disk {m['disk_percent']}% of {m['disk_total_gb']} GB | Swap {m['swap_percent']}% | "
        f"Processes {m['process_count']}",
    ]

    procs = await asyncio.to_thread(state.monitor.top_processes, 5, "cpu")
    lines.append("Top processes by CPU: " + ", ".join(
        f"{p['name']}(pid {p['pid']}) cpu {p['cpu_percent']}% mem {p['memory_mb']}MB" for p in procs))

    firing = state.alerts.list("firing", limit=10)
    lines.append("Active alerts: " + ("; ".join(f"[{a['severity']}] {a['title']} - {a['message']}"
                                                  for a in firing) or "none"))

    if state.docker.enabled:
        containers = await _safe(state.docker.list_containers(), None)
        if containers is None:
            lines.append("Docker: unreachable")
        else:
            running = [c["name"] for c in containers if c["state"] == "running"]
            other = [f"{c['name']} ({c['status']})" for c in containers if c["state"] != "running"]
            lines.append(f"Docker: {len(running)} running [{', '.join(running[:10])}]; "
                         f"not running: {', '.join(other[:10]) or 'none'}")

    if state.kubernetes.enabled:
        pods = await _safe(state.kubernetes.pods(), None)
        if pods is None:
            lines.append("Kubernetes: unreachable")
        else:
            bad = [f"{p['namespace']}/{p['name']} {p['status']} restarts={p['restarts']}"
                   for p in pods if p["status"] not in ("Running", "Succeeded", "Completed")]
            lines.append(f"Kubernetes: {len(pods)} pods; problems: {'; '.join(bad[:10]) or 'none'}")
            events = await _safe(state.kubernetes.warning_events(limit=5), [])
            if events:
                lines.append("Recent k8s warnings: " + "; ".join(
                    f"{e['object']} {e['reason']}: {e['message'][:120]}" for e in events))

    if state.jenkins.configured:
        jobs = await _safe(state.jenkins.jobs(), [])
        if jobs:
            lines.append("Jenkins jobs: " + ", ".join(f"{j['name']}={j['status']}" for j in jobs[:10]))

    if state.github.configured:
        runs = await _safe(state.github.all_runs(5), [])
        if runs:
            lines.append("GitHub Actions latest runs: " + ", ".join(
                f"{r['repo']}:{r['workflow']}#{r['run_number']}={r['status']}" for r in runs[:6]))

    return "\n".join(lines)
