/* Module 5 - Infrastructure Monitoring: Prometheus metrics, Grafana dashboards, AWS. */
import { ExternalLink, Search } from "lucide-react";
import { useState } from "react";
import { api, qs } from "../api";
import { LineChart } from "../components/charts";
import { Empty, Loading, Notice, PageHeader, Panel, Status } from "../components/ui";
import usePolling from "../hooks/usePolling";
import { bytes, niceBytes, timeAgo } from "../utils/format";

const COLORS = ["#4c8dff", "#34c79a", "#f2b84b", "#ff6b6b", "#b48cff", "#5fd4e0"];

const seriesName = (metric) => {
  const { __name__, ...labels } = metric;
  const parts = Object.entries(labels).map(([k, v]) => `${k}=${v}`);
  return parts.join(", ") || __name__ || "value";
};

function formatterFor(unit) {
  if (unit === "%") return (v) => `${v.toFixed(0)}%`;
  if (unit === "B/s") return (v) => bytes(v, true);
  if (unit === "s") return (v) => `${(v * 1000).toFixed(0)} ms`;
  return (v) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2));
}

function QueryExplorer({ presets }) {
  const [active, setActive] = useState("node_cpu");
  const [custom, setCustom] = useState("");
  const [query, setQuery] = useState(presets.node_cpu?.query || "up");
  const [minutes, setMinutes] = useState(30);
  const unit = Object.values(presets).find((p) => p.query === query)?.unit || "";

  const result = usePolling(
    () => api.get(`/api/infra/prometheus/query_range?${qs({ q: query, minutes })}`),
    30000,
    [query, minutes],
  );

  const run = (e) => {
    e.preventDefault();
    if (custom.trim()) {
      setActive(null);
      setQuery(custom.trim());
    }
  };

  return (
    <Panel
      title="Metrics explorer"
      subtitle="PromQL queries against Prometheus. Pick a preset or write your own."
      actions={
        <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} aria-label="Time range">
          <option value={15}>15 min</option>
          <option value={30}>30 min</option>
          <option value={180}>3 hours</option>
          <option value={1440}>24 hours</option>
        </select>
      }
    >
      <div className="chip-row">
        {Object.entries(presets).map(([id, p]) => (
          <button
            key={id}
            className={`chip ${active === id ? "active" : ""}`}
            onClick={() => {
              setActive(id);
              setQuery(p.query);
              setCustom(p.query);
            }}
          >
            {p.label}
          </button>
        ))}
      </div>
      <form className="query-bar" onSubmit={run}>
        <input
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          placeholder='e.g. rate(node_cpu_seconds_total{mode="user"}[1m])'
          aria-label="PromQL query"
          spellCheck={false}
        />
        <button className="btn primary" type="submit"><Search size={15} /> Run query</button>
      </form>
      {result.error && <Notice error={result.error} />}
      {!result.error && !result.data && <Loading label="Querying Prometheus" />}
      {result.data && result.data.length === 0 && <Empty>The query returned no data. Is the exporter running?</Empty>}
      {result.data && result.data.length > 0 && (
        <LineChart
          height={240}
          area={result.data.length === 1}
          yFormat={formatterFor(unit)}
          yMax={unit === "%" ? 100 : undefined}
          yNice={unit === "B/s" ? niceBytes : undefined}
          series={result.data.slice(0, 6).map((s, i) => ({
            name: seriesName(s.metric),
            color: COLORS[i % COLORS.length],
            points: s.points,
          }))}
        />
      )}
    </Panel>
  );
}

function Prometheus() {
  const presets = usePolling(() => api.get("/api/infra/prometheus/presets"), 0);
  const targets = usePolling(() => api.get("/api/infra/prometheus/targets"), 15000);
  const alerts = usePolling(() => api.get("/api/infra/prometheus/alerts"), 15000);

  if (targets.error && !targets.data) return <Panel title="Prometheus"><Notice error={targets.error} /></Panel>;
  if (!targets.data || !presets.data) return <Loading />;

  const up = targets.data.filter((t) => t.health === "up").length;
  return (
    <>
      <QueryExplorer presets={presets.data} />
      <div className="grid two">
        <Panel title="Scrape targets" subtitle={`${up} of ${targets.data.length} up`} flush>
          <table className="table">
            <thead><tr><th>Job</th><th>Instance</th><th>Health</th><th>Last scrape</th></tr></thead>
            <tbody>
              {targets.data.map((t) => (
                <tr key={`${t.job}-${t.instance}`}>
                  <td>{t.job}</td>
                  <td className="mono-cell small">{t.instance}</td>
                  <td>
                    <Status value={t.health} />
                    {t.last_error && <div className="cell-sub tone-crit-text">{t.last_error}</div>}
                  </td>
                  <td className="muted">{timeAgo(t.last_scrape)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="Prometheus alert rules" subtitle="From monitoring/prometheus/alert_rules.yml" flush>
          {(alerts.data || []).length === 0 ? (
            <Empty>No rules are pending or firing.</Empty>
          ) : (
            <ul className="event-list">
              {alerts.data.map((a, i) => (
                <li key={i}>
                  <div><Status value={a.state === "firing" ? a.severity : "pending"} label={a.name} /> <span className="muted">{a.instance}</span></div>
                  <div className="cell-sub">{a.summary} (since {timeAgo(a.active_at)})</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}

function Grafana() {
  const { data, error } = usePolling(() => api.get("/api/infra/grafana"), 60000);
  const [embed, setEmbed] = useState(false);
  if (error) return <Notice error={error} />;
  if (!data) return null;
  if (!data.configured) {
    return (
      <Panel title="Grafana">
        <Notice error={{ message: "Grafana is not configured", hint: data.hint, status: 503 }} />
      </Panel>
    );
  }
  const dashUrl = `${data.url}${data.dashboard_path}`;
  return (
    <Panel
      title="Grafana"
      subtitle={data.connected ? `${data.detail}. The provisioned dashboard charts the same Prometheus data.` : data.detail}
      actions={
        <>
          <button className="btn ghost sm" onClick={() => setEmbed(!embed)}>{embed ? "Hide dashboard" : "Show dashboard here"}</button>
          <a className="btn primary sm" href={dashUrl} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open Grafana</a>
        </>
      }
    >
      {embed && <iframe className="grafana-frame" title="Grafana dashboard" src={`${dashUrl}?orgId=1&kiosk&refresh=30s&theme=dark`} />}
    </Panel>
  );
}

function AWS() {
  const status = usePolling(() => api.get("/api/integrations"), 0);
  const aws = status.data?.find((i) => i.name === "aws");
  const summary = usePolling(() => (aws?.configured ? api.get("/api/infra/aws") : Promise.resolve(null)), 60000, [aws?.configured]);
  if (!aws) return null;
  if (!aws.configured) {
    return (
      <Panel title="AWS">
        <Notice error={{ message: "AWS is optional and not enabled", hint: aws.hint, status: 503 }} />
      </Panel>
    );
  }
  const s = summary.data;
  return (
    <Panel title="AWS" subtitle={aws.detail} flush>
      {summary.error && <div className="pad"><Notice error={summary.error} /></div>}
      {!s && !summary.error && <Loading />}
      {s && (
        <>
          <table className="table">
            <thead><tr><th>EC2 instance</th><th>Type</th><th>State</th><th>Public IP</th><th>CPU (CloudWatch)</th></tr></thead>
            <tbody>
              {s.instances.length === 0 && <tr><td colSpan={5} className="muted">No instances in {s.region}.</td></tr>}
              {s.instances.map((i) => (
                <tr key={i.id}>
                  <td><div>{i.name || i.id}</div><div className="cell-sub">{i.id}, {i.az}</div></td>
                  <td>{i.type}</td>
                  <td><Status value={i.state === "running" ? "running" : i.state} /></td>
                  <td className="mono-cell">{i.public_ip || "-"}</td>
                  <td>{i.cpu_percent !== null ? `${i.cpu_percent}%` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pad split">
            <div><b>{s.buckets.length}</b> S3 buckets <span className="muted">{s.buckets.slice(0, 4).join(", ")}</span></div>
            <div>
              <b className={s.alarms.length ? "tone-crit-text" : ""}>{s.alarms.length}</b> CloudWatch alarms in ALARM state
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}

export default function Infrastructure() {
  return (
    <>
      <PageHeader
        title="Infrastructure"
        description="Prometheus scrapes node-exporter and this dashboard every 15 seconds. Grafana and AWS CloudWatch add longer-term views."
      />
      <Prometheus />
      <Grafana />
      <AWS />
    </>
  );
}
