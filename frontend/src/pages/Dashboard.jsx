/* Module 1 - Overview: one screen that answers "is everything OK right now?" */
import { api } from "../api";
import { LineChart } from "../components/charts";
import { Empty, Loading, Notice, PageHeader, Panel, Status } from "../components/ui";
import usePolling from "../hooks/usePolling";
import { bytes, duration, timeAgo } from "../utils/format";

const TOOL_PAGE = {
  gemini: "assistant",
  docker: "containers",
  kubernetes: "containers",
  jenkins: "cicd",
  github: "cicd",
  prometheus: "infrastructure",
  grafana: "infrastructure",
  aws: "infrastructure",
};

function Readout({ label, value, unit, sub, toneClass }) {
  return (
    <div className="readout">
      <div className="readout-label">{label}</div>
      <div className={`readout-value ${toneClass || ""}`}>
        {value}
        <span className="readout-unit">{unit}</span>
      </div>
      {sub && <div className="readout-sub">{sub}</div>}
    </div>
  );
}

const levelTone = (v, warn = 75, crit = 90) => (v >= crit ? "tone-crit-text" : v >= warn ? "tone-warn-text" : "");

export default function Dashboard({ navigate }) {
  const { data, error, loading, refresh, updatedAt } = usePolling(() => api.get("/api/overview"), 5000);

  if (loading && !data) return <Loading label="Collecting the first metrics" />;
  if (error && !data) return <Notice error={error} title="The dashboard cannot reach its backend" />;

  const s = data.system;
  const host = data.host;
  const points = data.history || [];
  const integrations = data.integrations || [];
  const connected = integrations.filter((i) => i.connected).length;

  return (
    <>
      <PageHeader
        title="Overview"
        description="Live health of this machine and every connected DevOps tool."
        updatedAt={updatedAt}
        onRefresh={refresh}
      />

      <section className="pulse" aria-label="Live system pulse">
        <div className="pulse-meta">
          <div className="pulse-host">
            <span className="live-dot" aria-hidden="true" />
            {host.hostname}
          </div>
          <div className="pulse-os">
            {host.os} {host.os_release}, up {duration(host.uptime_seconds)}
          </div>
          <div className="readouts">
            <Readout label="CPU" value={s.cpu_percent.toFixed(0)} unit="%" toneClass={levelTone(s.cpu_percent)}
              sub={`${host.cpu_logical_cores} logical cores`} />
            <Readout label="Memory" value={s.memory_percent.toFixed(0)} unit="%" toneClass={levelTone(s.memory_percent)}
              sub={`${s.memory_used_gb} of ${s.memory_total_gb} GB`} />
            <Readout label="Disk" value={s.disk_percent.toFixed(0)} unit="%" toneClass={levelTone(s.disk_percent, 80, 90)}
              sub={`${s.disk_used_gb} of ${s.disk_total_gb} GB`} />
            <Readout label="Network" value={bytes(s.net_rx_bps).split(" ")[0]} unit={` ${bytes(s.net_rx_bps).split(" ")[1]}/s in`}
              sub={`${bytes(s.net_tx_bps, true)} out`} />
          </div>
        </div>
        <div className="pulse-chart">
          <LineChart
            height={230}
            yMax={100}
            yFormat={(v) => `${v.toFixed(0)}%`}
            label="CPU and memory over the last 15 minutes"
            series={[
              { name: "CPU", color: "#4c8dff", points: points.map((p) => [p.timestamp, p.cpu_percent]) },
              { name: "Memory", color: "#34c79a", points: points.map((p) => [p.timestamp, p.memory_percent]) },
            ]}
          />
        </div>
      </section>

      <div className="grid two">
        <Panel title="Tools" subtitle={`${connected} of ${integrations.length} connected`}>
          <ul className="tool-list">
            {integrations.map((i) => (
              <li key={i.name}>
                <button className="tool-row" onClick={() => navigate(TOOL_PAGE[i.name] || "dashboard")}>
                  <Status value={i.connected ? "ok" : i.configured ? "down" : "neutral"} label={i.label} />
                  <span className="tool-detail">{i.connected ? i.detail : i.configured ? i.detail : "Not set up yet"}</span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title="Alerts"
          subtitle={`${data.alerts.firing} firing, ${data.alerts.last_24h} in the last 24 hours`}
          actions={<button className="btn ghost sm" onClick={() => navigate("alerts")}>Open alerts</button>}
        >
          {data.recent_alerts.length === 0 ? (
            <Empty>No alerts yet. Thresholds and tool checks run in the background.</Empty>
          ) : (
            <ul className="alert-list">
              {data.recent_alerts.map((a) => (
                <li key={a.id} className={`sev-${a.status === "firing" ? a.severity : "resolved"}`}>
                  <div className="alert-title">{a.title}</div>
                  <div className="alert-meta">
                    {a.status === "firing" ? a.severity : "resolved"} from {a.source}, {timeAgo(a.updated_at)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid three">
        <Panel title="Docker" actions={<button className="btn ghost sm" onClick={() => navigate("containers")}>Containers</button>}>
          {data.docker ? (
            <div className="mini-stats">
              <div><b>{data.docker.running}</b> running</div>
              <div><b>{data.docker.stopped}</b> stopped</div>
              <div><b className={data.docker.unhealthy ? "tone-crit-text" : ""}>{data.docker.unhealthy}</b> unhealthy</div>
            </div>
          ) : (
            <Empty>Docker is not connected.</Empty>
          )}
        </Panel>
        <Panel title="Kubernetes" actions={<button className="btn ghost sm" onClick={() => navigate("containers")}>Workloads</button>}>
          {data.kubernetes ? (
            <div className="mini-stats">
              <div><b>{data.kubernetes.nodes_ready}/{data.kubernetes.nodes}</b> nodes ready</div>
              <div><b>{data.kubernetes.pods_running}/{data.kubernetes.pods}</b> pods healthy</div>
              <div><b>{data.kubernetes.deployments}</b> deployments</div>
            </div>
          ) : (
            <Empty>Kubernetes is not connected.</Empty>
          )}
        </Panel>
        <Panel title="Latest pipelines" actions={<button className="btn ghost sm" onClick={() => navigate("cicd")}>Pipelines</button>}>
          {data.pipelines.length ? (
            <ul className="pipe-list">
              {data.pipelines.slice(0, 5).map((p) => (
                <li key={`${p.tool}-${p.name}-${p.number}`}>
                  <Status value={p.status} label="" />
                  <span className="pipe-name" title={p.name}>{p.name}</span>
                  <span className="muted">#{p.number}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>Connect Jenkins or GitHub Actions to see builds.</Empty>
          )}
        </Panel>
      </div>
    </>
  );
}
