/* Module 4 - Container Monitoring: Docker containers and Kubernetes (Minikube) workloads. */
import { Play, RotateCw, Square } from "lucide-react";
import { useState } from "react";
import { api, qs } from "../api";
import LogDrawer from "../components/LogDrawer";
import { Empty, KeyValue, Loading, Notice, PageHeader, Panel, Status, Tabs } from "../components/ui";
import usePolling from "../hooks/usePolling";
import useToast from "../hooks/useToast";
import { timeAgo } from "../utils/format";

function Docker({ openLog, notify }) {
  const info = usePolling(() => api.get("/api/docker/info"), 30000);
  const list = usePolling(() => api.get("/api/docker/containers"), 5000);
  const stats = usePolling(() => api.get("/api/docker/stats"), 10000);
  const [busy, setBusy] = useState(null);

  if (info.error && !info.data) return <Notice error={info.error} />;
  if (!list.data) return <Loading />;

  const act = async (c, action) => {
    setBusy(`${c.name}:${action}`);
    try {
      await api.post(`/api/docker/containers/${encodeURIComponent(c.name)}/${action}`);
      notify(`${c.name}: ${action} done`);
      list.refresh();
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(null);
    }
  };

  const d = info.data;
  return (
    <>
      {d && (
        <div className="summary-strip">
          <div><b>{d.running}</b> running</div>
          <div><b>{d.stopped}</b> stopped</div>
          <div><b>{d.images}</b> images</div>
          <div className="muted">Docker {d.server_version} on {d.os}, {d.cpus} CPUs, {d.memory_gb} GB</div>
        </div>
      )}
      <Panel title="Containers" flush>
        {list.data.length === 0 ? (
          <Empty>No containers. Start the stack with: docker compose up -d</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Name</th><th>State</th><th>Image</th><th>CPU</th><th>Memory</th><th>Ports</th><th className="num">Actions</th></tr>
              </thead>
              <tbody>
                {list.data.map((c) => {
                  const s = stats.data?.[c.id];
                  const crashed = c.state === "exited" && c.exit_code;
                  return (
                    <tr key={c.id}>
                      <td>
                        <div>{c.name}</div>
                        <div className="cell-sub">{c.compose_project ? `compose: ${c.compose_project}` : c.id}</div>
                      </td>
                      <td>
                        <Status value={c.health === "unhealthy" ? "unhealthy" : c.state} />
                        <div className="cell-sub">{c.status}</div>
                      </td>
                      <td className="mono-cell">{c.image}</td>
                      <td>{s ? `${s.cpu_percent.toFixed(1)}%` : "-"}</td>
                      <td>{s ? `${s.memory_used_mb} MB` : "-"}</td>
                      <td className="mono-cell small">{c.ports || "-"}</td>
                      <td className="num actions">
                        <button
                          className={`btn sm ${crashed ? "ai" : "ghost"}`}
                          onClick={() =>
                            openLog({
                              title: `Container ${c.name}`,
                              source: "docker logs",
                              context: `Docker container ${c.name}, image ${c.image}, status "${c.status}"`,
                              load: () => api.get(`/api/docker/containers/${encodeURIComponent(c.name)}/logs?tail=300`).then((r) => r.log),
                            })
                          }
                        >
                          {crashed ? "Diagnose" : "Logs"}
                        </button>
                        {c.state === "running" ? (
                          <>
                            <button className="btn ghost sm icon" title="Restart" aria-label={`Restart ${c.name}`}
                              disabled={!!busy} onClick={() => act(c, "restart")}><RotateCw size={14} /></button>
                            <button className="btn ghost sm icon" title="Stop" aria-label={`Stop ${c.name}`}
                              disabled={!!busy} onClick={() => act(c, "stop")}><Square size={14} /></button>
                          </>
                        ) : (
                          <button className="btn ghost sm icon" title="Start" aria-label={`Start ${c.name}`}
                            disabled={!!busy} onClick={() => act(c, "start")}><Play size={14} /></button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}

function Kubernetes({ openLog, notify }) {
  const [ns, setNs] = useState("");
  const overview = usePolling(() => api.get("/api/k8s/overview"), 15000);
  const pods = usePolling(() => api.get(`/api/k8s/pods?${qs({ namespace: ns })}`), 10000, [ns]);
  const deps = usePolling(() => api.get(`/api/k8s/deployments?${qs({ namespace: ns })}`), 15000, [ns]);
  const svcs = usePolling(() => api.get(`/api/k8s/services?${qs({ namespace: ns })}`), 30000, [ns]);
  const events = usePolling(() => api.get(`/api/k8s/events?${qs({ namespace: ns })}`), 30000, [ns]);

  if (overview.error && !overview.data) return <Notice error={overview.error} />;
  if (!overview.data) return <Loading />;
  const o = overview.data;

  const restart = async (d) => {
    try {
      const r = await api.post(`/api/k8s/deployments/${d.namespace}/${d.name}/restart`);
      notify(r.result);
      deps.refresh();
    } catch (e) {
      notify(e.message, "error");
    }
  };

  return (
    <>
      <div className="summary-strip">
        <div className="muted">Context <b>{o.context}</b></div>
        <div><b>{o.pod_count}</b> pods</div>
        <div><b>{o.deployment_count}</b> deployments{o.deployments_unavailable ? `, ${o.deployments_unavailable} not available` : ""}</div>
        <label className="inline-field">
          Namespace
          <select value={ns} onChange={(e) => setNs(e.target.value)}>
            <option value="">All namespaces</option>
            {o.namespaces.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>

      <div className="grid two">
        <Panel title="Nodes">
          {o.nodes.map((n) => (
            <div key={n.name} className="node">
              <Status value={n.ready ? "ready" : "notready"} label={n.name} />
              <KeyValue items={[
                ["Roles", n.roles.join(", ")],
                ["Kubelet", n.version],
                ["Capacity", `${n.cpu} CPU, ${n.memory}`],
                ["Pressure", n.pressure.length ? n.pressure.join(", ") : "none"],
              ]} />
            </div>
          ))}
        </Panel>
        <Panel title="Warning events" subtitle="Why pods are failing, straight from the cluster" flush>
          {(events.data || []).length === 0 ? (
            <Empty>No warning events.</Empty>
          ) : (
            <ul className="event-list">
              {events.data.slice(0, 8).map((e, i) => (
                <li key={i}>
                  <div><b>{e.reason}</b> on {e.object} <span className="muted">x{e.count}, {timeAgo(e.last_seen)}</span></div>
                  <div className="cell-sub">{e.message}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Pods" subtitle="CPU and memory need metrics-server: minikube addons enable metrics-server" flush>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Pod</th><th>Status</th><th>Ready</th><th>Restarts</th><th>CPU / Mem</th><th>Age</th><th className="num">Actions</th></tr>
            </thead>
            <tbody>
              {(pods.data || []).map((p) => {
                const bad = !["Running", "Succeeded", "Completed"].includes(p.status);
                return (
                  <tr key={`${p.namespace}/${p.name}`}>
                    <td><div>{p.name}</div><div className="cell-sub">{p.namespace}</div></td>
                    <td><Status value={p.status} /></td>
                    <td>{p.ready}</td>
                    <td className={p.restarts > 3 ? "tone-crit-text" : ""}>{p.restarts}</td>
                    <td>{p.usage ? `${p.usage.cpu} / ${p.usage.memory}` : "-"}</td>
                    <td className="muted">{p.age}</td>
                    <td className="num actions">
                      <button
                        className={`btn sm ${bad ? "ai" : "ghost"}`}
                        onClick={() =>
                          openLog({
                            title: `Pod ${p.name}`,
                            source: "kubectl logs",
                            context: `Kubernetes pod ${p.namespace}/${p.name}, status ${p.status}, restarts ${p.restarts}, images ${p.images.join(", ")}`,
                            load: () => api.get(`/api/k8s/pods/${p.namespace}/${p.name}/logs?tail=300`).then((r) => r.log),
                          })
                        }
                      >
                        {bad ? "Diagnose" : "Logs"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Deployments" flush>
          <table className="table">
            <thead><tr><th>Deployment</th><th>Ready</th><th>Image</th><th className="num">Action</th></tr></thead>
            <tbody>
              {(deps.data || []).map((d) => (
                <tr key={`${d.namespace}/${d.name}`}>
                  <td><div>{d.name}</div><div className="cell-sub">{d.namespace}</div></td>
                  <td><Status value={d.available >= d.desired ? "ready" : "pending"} label={`${d.ready}/${d.desired}`} /></td>
                  <td className="mono-cell small">{d.images.join(", ")}</td>
                  <td className="num"><button className="btn ghost sm" onClick={() => restart(d)}><RotateCw size={14} /> Restart</button></td>
                </tr>
              ))}
            </tbody>
          </table>
      </Panel>
      <Panel title="Services" flush>
          <table className="table">
            <thead><tr><th>Service</th><th>Type</th><th>Cluster IP</th><th>Ports</th></tr></thead>
            <tbody>
              {(svcs.data || []).map((s) => (
                <tr key={`${s.namespace}/${s.name}`}>
                  <td><div>{s.name}</div><div className="cell-sub">{s.namespace}</div></td>
                  <td>{s.type}</td>
                  <td className="mono-cell">{s.cluster_ip}</td>
                  <td className="mono-cell small">{s.ports}</td>
                </tr>
              ))}
            </tbody>
          </table>
      </Panel>
    </>
  );
}

export default function Containers() {
  const [tab, setTab] = useState("docker");
  const [logView, setLogView] = useState(null);
  const [notify, toast] = useToast();
  return (
    <>
      <PageHeader title="Containers" description="Docker containers on this machine and workloads in your Kubernetes cluster.">
        <Tabs tabs={[{ id: "docker", label: "Docker" }, { id: "k8s", label: "Kubernetes" }]} active={tab} onChange={setTab} />
      </PageHeader>
      {tab === "docker" ? <Docker openLog={setLogView} notify={notify} /> : <Kubernetes openLog={setLogView} notify={notify} />}
      <LogDrawer view={logView} onClose={() => setLogView(null)} />
      {toast}
    </>
  );
}
