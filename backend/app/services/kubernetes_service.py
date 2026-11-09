"""
Module 4b - Kubernetes workload monitoring (works with Minikube).

Key idea: every Kubernetes object is served by the API server as JSON.
* On a laptop we call   kubectl get --raw /api/v1/pods
  which re-uses your kubeconfig (minikube writes it for you).
* Inside the cluster we call https://kubernetes.default.svc/api/v1/pods
  with the pod's ServiceAccount token (read-only RBAC in k8s/rbac.yaml).

Both return the SAME raw JSON, so one set of parsers serves both modes.
No heavy Kubernetes Python client is required.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from ..errors import IntegrationError, status_payload
from ..utils.shell import CommandError, run, tool_available

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
HINT = ("Start Minikube ('minikube start'), make sure 'kubectl get pods -A' works, then set "
        "KUBERNETES_ENABLED=true in backend/.env.")


def _check_name(value: str, what: str) -> str:
    if not _NAME_RE.match(value or ""):
        raise IntegrationError(f"Invalid {what}", 400)
    return value


def _age(ts: str | None) -> str:
    if not ts:
        return "-"
    created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    secs = int((datetime.now(timezone.utc) - created).total_seconds())
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit}"
    return f"{secs}s"


class KubernetesService:
    name = "kubernetes"
    label = "Kubernetes"

    def __init__(self, enabled: bool, context: str = "", allow_actions: bool = True) -> None:
        self.enabled = enabled
        self.context = context
        self.allow_actions = allow_actions

    # ------------------------------------------------------------------ #
    @property
    def in_cluster(self) -> bool:
        return bool(os.getenv("KUBERNETES_SERVICE_HOST")) and os.path.exists(f"{SA_DIR}/token")

    @property
    def mode(self) -> str | None:
        if self.in_cluster:
            return "in-cluster"
        if tool_available("kubectl"):
            return "kubectl"
        return None

    def _require(self) -> str:
        if not self.enabled:
            raise IntegrationError("Kubernetes integration is disabled", 503, HINT)
        mode = self.mode
        if not mode:
            raise IntegrationError("kubectl not found and not running inside a cluster", 503, HINT)
        return mode

    def _kubectl(self, *args: str) -> list[str]:
        cmd = ["kubectl"]
        if self.context:
            cmd += ["--context", self.context]
        return cmd + list(args)

    async def _raw(self, path: str, params: dict | None = None, as_text: bool = False,
                   method: str = "GET", body: dict | None = None) -> Any:
        mode = self._require()
        if params:
            path = f"{path}?{urlencode(params)}"
        if mode == "kubectl":
            if method != "GET":
                raise IntegrationError("Only GET is supported through kubectl --raw", 500)
            try:
                out = await run(self._kubectl("get", "--raw", path, "--request-timeout=15s"), timeout=25)
            except CommandError as exc:
                raise IntegrationError(f"Kubernetes: {exc}", 503, HINT) from exc
            return out if as_text else json.loads(out)

        host = os.environ["KUBERNETES_SERVICE_HOST"]
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        with open(f"{SA_DIR}/token", encoding="utf-8") as f:
            token = f.read().strip()
        headers = {"Authorization": f"Bearer {token}"}
        if body is not None:
            headers["Content-Type"] = "application/strategic-merge-patch+json"
        async with httpx.AsyncClient(verify=f"{SA_DIR}/ca.crt", timeout=20) as client:
            try:
                resp = await client.request(method, f"https://{host}:{port}{path}",
                                            headers=headers, json=body)
            except httpx.HTTPError as exc:
                raise IntegrationError(f"Kubernetes API unreachable: {exc}", 503, HINT) from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"Kubernetes API {resp.status_code}: {resp.text[:300]}",
                                   502 if resp.status_code >= 500 else resp.status_code)
        return resp.text if as_text else resp.json()

    @staticmethod
    def _ns_path(base: str, kind: str, namespace: str | None) -> str:
        if namespace:
            _check_name(namespace, "namespace")
            return f"{base}/namespaces/{namespace}/{kind}"
        return f"{base}/{kind}"

    # ------------------------------------------------------------------ #
    async def status(self) -> dict[str, Any]:
        if not self.enabled:
            return status_payload(self.name, self.label, False, False, "Disabled", HINT)
        try:
            version = await self._raw("/version")
            return status_payload(self.name, self.label, True, True,
                                  f"{version.get('gitVersion', '?')} via {self.mode}")
        except IntegrationError as exc:
            return status_payload(self.name, self.label, True, False, exc.message, HINT)

    async def current_context(self) -> str:
        if self.mode != "kubectl":
            return "in-cluster"
        if self.context:
            return self.context
        try:
            return (await run(["kubectl", "config", "current-context"], timeout=10)).strip()
        except CommandError:
            return "unknown"

    async def namespaces(self) -> list[str]:
        data = await self._raw("/api/v1/namespaces")
        return sorted(i["metadata"]["name"] for i in data.get("items", []))

    async def nodes(self) -> list[dict[str, Any]]:
        data = await self._raw("/api/v1/nodes")
        nodes = []
        for n in data.get("items", []):
            conds = {c["type"]: c["status"] for c in n.get("status", {}).get("conditions", [])}
            labels = n["metadata"].get("labels", {})
            roles = [k.split("/", 1)[1] for k in labels if k.startswith("node-role.kubernetes.io/")]
            cap = n.get("status", {}).get("capacity", {})
            nodes.append({
                "name": n["metadata"]["name"],
                "ready": conds.get("Ready") == "True",
                "pressure": [t for t in ("MemoryPressure", "DiskPressure", "PIDPressure") if conds.get(t) == "True"],
                "roles": roles or ["worker"],
                "version": n.get("status", {}).get("nodeInfo", {}).get("kubeletVersion"),
                "os_image": n.get("status", {}).get("nodeInfo", {}).get("osImage"),
                "cpu": cap.get("cpu"),
                "memory": cap.get("memory"),
                "age": _age(n["metadata"].get("creationTimestamp")),
            })
        return nodes

    async def pods(self, namespace: str | None = None) -> list[dict[str, Any]]:
        data = await self._raw(self._ns_path("/api/v1", "pods", namespace))
        pods = []
        for p in data.get("items", []):
            st = p.get("status", {})
            cstats = st.get("containerStatuses", []) or []
            ready = sum(1 for c in cstats if c.get("ready"))
            restarts = sum(c.get("restartCount", 0) for c in cstats)
            reason = st.get("reason")
            for c in cstats:  # waiting/terminated reasons are the useful ones
                waiting = c.get("state", {}).get("waiting")
                term = c.get("state", {}).get("terminated")
                if waiting and waiting.get("reason"):
                    reason = waiting["reason"]
                    break
                if term and term.get("reason") and st.get("phase") != "Succeeded":
                    reason = term["reason"]
            if p["metadata"].get("deletionTimestamp"):
                reason = "Terminating"
            pods.append({
                "name": p["metadata"]["name"],
                "namespace": p["metadata"]["namespace"],
                "phase": st.get("phase", "Unknown"),
                "status": reason or st.get("phase", "Unknown"),
                "ready": f"{ready}/{len(p.get('spec', {}).get('containers', []))}",
                "restarts": restarts,
                "node": p.get("spec", {}).get("nodeName"),
                "ip": st.get("podIP"),
                "age": _age(p["metadata"].get("creationTimestamp")),
                "containers": [c["name"] for c in p.get("spec", {}).get("containers", [])],
                "images": [c.get("image") for c in p.get("spec", {}).get("containers", [])],
            })
        pods.sort(key=lambda x: (x["namespace"], x["name"]))
        return pods

    async def deployments(self, namespace: str | None = None) -> list[dict[str, Any]]:
        data = await self._raw(self._ns_path("/apis/apps/v1", "deployments", namespace))
        out = []
        for d in data.get("items", []):
            spec, st = d.get("spec", {}), d.get("status", {})
            out.append({
                "name": d["metadata"]["name"],
                "namespace": d["metadata"]["namespace"],
                "desired": spec.get("replicas", 0),
                "ready": st.get("readyReplicas", 0),
                "available": st.get("availableReplicas", 0),
                "updated": st.get("updatedReplicas", 0),
                "images": [c.get("image") for c in spec.get("template", {}).get("spec", {}).get("containers", [])],
                "age": _age(d["metadata"].get("creationTimestamp")),
            })
        return sorted(out, key=lambda x: (x["namespace"], x["name"]))

    async def services(self, namespace: str | None = None) -> list[dict[str, Any]]:
        data = await self._raw(self._ns_path("/api/v1", "services", namespace))
        out = []
        for s in data.get("items", []):
            spec = s.get("spec", {})
            out.append({
                "name": s["metadata"]["name"],
                "namespace": s["metadata"]["namespace"],
                "type": spec.get("type"),
                "cluster_ip": spec.get("clusterIP"),
                "ports": ", ".join(
                    f"{p.get('port')}{':' + str(p['nodePort']) if p.get('nodePort') else ''}/{p.get('protocol', 'TCP')}"
                    for p in spec.get("ports", [])),
                "age": _age(s["metadata"].get("creationTimestamp")),
            })
        return sorted(out, key=lambda x: (x["namespace"], x["name"]))

    async def warning_events(self, namespace: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        data = await self._raw(self._ns_path("/api/v1", "events", namespace),
                               params={"fieldSelector": "type=Warning"})
        events = []
        for e in data.get("items", []):
            obj = e.get("involvedObject", {})
            events.append({
                "namespace": e["metadata"].get("namespace"),
                "object": f"{obj.get('kind', '')}/{obj.get('name', '')}",
                "reason": e.get("reason"),
                "message": e.get("message"),
                "count": e.get("count") or 1,
                "last_seen": e.get("lastTimestamp") or e.get("eventTime") or e["metadata"].get("creationTimestamp"),
            })
        events.sort(key=lambda x: x["last_seen"] or "", reverse=True)
        return events[:limit]

    async def pod_metrics(self) -> dict[str, dict[str, str]]:
        """Needs metrics-server: 'minikube addons enable metrics-server'."""
        try:
            data = await self._raw("/apis/metrics.k8s.io/v1beta1/pods")
        except IntegrationError:
            return {}
        result = {}
        for item in data.get("items", []):
            cpu_n = mem_ki = 0
            for c in item.get("containers", []):
                cpu, mem = c["usage"].get("cpu", "0"), c["usage"].get("memory", "0")
                cpu_n += _cpu_to_millicores(cpu)
                mem_ki += _mem_to_mib(mem)
            key = f"{item['metadata']['namespace']}/{item['metadata']['name']}"
            result[key] = {"cpu": f"{cpu_n}m", "memory": f"{mem_ki:.0f}Mi"}
        return result

    async def pod_logs(self, namespace: str, pod: str, container: str | None = None,
                       tail: int = 200) -> str:
        _check_name(namespace, "namespace")
        _check_name(pod, "pod name")
        params: dict[str, Any] = {"tailLines": max(1, min(tail, 2000)), "timestamps": "true"}
        if container:
            params["container"] = _check_name(container, "container name")
        path = f"/api/v1/namespaces/{namespace}/pods/{pod}/log"
        try:
            text = await self._raw(path, params=params, as_text=True)
        except IntegrationError:
            text = ""
        if not text.strip():
            # A crash-looping container is often between restarts: its CURRENT log is
            # empty, but the PREVIOUS run (the one that crashed) explains the failure.
            try:
                previous = await self._raw(path, params={**params, "previous": "true"}, as_text=True)
                if previous.strip():
                    return "[log of the previous (crashed) container]\n" + previous
            except IntegrationError:
                pass
        return text

    async def restart_deployment(self, namespace: str, name: str) -> dict[str, str]:
        if not self.allow_actions:
            raise IntegrationError("Actions are disabled (ALLOW_ACTIONS=false)", 403)
        _check_name(namespace, "namespace")
        _check_name(name, "deployment name")
        if self._require() == "kubectl":
            try:
                out = await run(self._kubectl("rollout", "restart", f"deployment/{name}", "-n", namespace), timeout=30)
            except CommandError as exc:
                raise IntegrationError(f"Kubernetes: {exc}", 502) from exc
            return {"result": out.strip()}
        # Same thing kubectl does: bump an annotation so a new ReplicaSet rolls out.
        now = datetime.now(timezone.utc).isoformat()
        patch = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}}}}
        await self._raw(f"/apis/apps/v1/namespaces/{namespace}/deployments/{name}", method="PATCH", body=patch)
        return {"result": f"deployment.apps/{name} restarted"}


def _cpu_to_millicores(value: str) -> int:
    if value.endswith("n"):
        return int(int(value[:-1]) / 1_000_000)
    if value.endswith("u"):
        return int(int(value[:-1]) / 1000)
    if value.endswith("m"):
        return int(value[:-1])
    return int(float(value) * 1000)


def _mem_to_mib(value: str) -> float:
    units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "K": 1 / 1024, "M": 1, "G": 1024}
    for suffix, factor in units.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * factor
    return float(value) / 1024 ** 2
