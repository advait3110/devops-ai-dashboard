/* Module 7 - Log Analysis: read real logs, filter them, find repeated errors, ask AI. */
import { useMemo, useState } from "react";
import { api, qs } from "../api";
import AiExplainPanel, { ExplainButton } from "../components/AiExplain";
import LogViewer from "../components/LogViewer";
import { Empty, Loading, Notice, PageHeader, Panel } from "../components/ui";
import usePolling from "../hooks/usePolling";

const LEVELS = ["critical", "error", "warning", "info", "debug"];

export default function Logs() {
  const sources = usePolling(() => api.get("/api/logs/sources"), 30000);
  const [source, setSource] = useState("app");
  const [target, setTarget] = useState("");
  const [tail, setTail] = useState(300);
  const [level, setLevel] = useState("all");
  const [search, setSearch] = useState("");
  const [follow, setFollow] = useState(true);
  const [explain, setExplain] = useState(null);

  const current = sources.data?.find((s) => s.id === source);
  const needsTarget = current && current.targets.length > 0;
  const ready = !needsTarget || target;

  const logs = usePolling(
    () => (ready ? api.get(`/api/logs?${qs({ source, target, tail, level, search })}`) : Promise.resolve(null)),
    follow ? 5000 : 0,
    [source, target, tail, level, search, follow, ready],
  );

  const errorText = useMemo(() => {
    const lines = logs.data?.lines || [];
    const bad = lines.filter((l) => ["error", "critical", "warning"].includes(l.level));
    return (bad.length ? bad : lines).map((l) => l.text).join("\n");
  }, [logs.data]);

  const a = logs.data?.analysis;
  const label = current ? `${current.label}${target ? `: ${target}` : ""}` : source;

  return (
    <>
      <PageHeader
        title="Logs"
        description="Real logs from this backend, whitelisted files, the operating system, Docker and Kubernetes."
        updatedAt={logs.updatedAt}
        onRefresh={logs.refresh}
      />

      <div className="filters">
        <label>
          Source
          <select value={source} onChange={(e) => { setSource(e.target.value); setTarget(""); }}>
            {(sources.data || [{ id: "app", label: "Dashboard backend" }]).map((s) => (
              <option key={s.id} value={s.id} disabled={s.available === false}>
                {s.label}{s.available === false ? " (not available)" : ""}
              </option>
            ))}
          </select>
        </label>
        {needsTarget && (
          <label>
            {source === "docker" ? "Container" : source === "kubernetes" ? "Pod" : "File"}
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose…</option>
              {current.targets.map((t) => (
                <option key={t.value} value={t.value} disabled={t.available === false}>{t.label}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          Level
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="all">All levels</option>
            {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <label>
          Lines
          <select value={tail} onChange={(e) => setTail(Number(e.target.value))}>
            {[100, 300, 1000, 2000].map((n) => <option key={n} value={n}>last {n}</option>)}
          </select>
        </label>
        <label className="grow">
          Search
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Text to find" />
        </label>
        <label className="switch">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
          <span>Follow</span>
        </label>
      </div>

      {!ready && <Empty>Choose a {source === "docker" ? "container" : source === "kubernetes" ? "pod" : "file"} to read its log.</Empty>}
      {ready && logs.error && <Notice error={logs.error} />}
      {ready && !logs.data && !logs.error && <Loading label="Reading log" />}

      {a && (
        <div className="grid log-layout">
          <Panel
            title={label}
            subtitle={`${logs.data.lines.length} of ${a.total_lines} lines shown`}
            actions={
              errorText && (
                <ExplainButton
                  label={a.levels.error + a.levels.critical > 0 ? "Explain errors with AI" : "Explain with AI"}
                  onClick={() => setExplain({ title: label, text: errorText, source: `${label} log`, context: `Log analysis: ${JSON.stringify(a.levels)}` })}
                />
              )
            }
            flush
          >
            <LogViewer lines={logs.data.lines} height={560} emptyText="No lines match the filters." />
          </Panel>

          <Panel title="Analysis">
            <div className="level-bars">
              {LEVELS.map((l) => (
                <button
                  key={l}
                  className={`level-row lvl-${l} ${level === l ? "active" : ""}`}
                  onClick={() => setLevel(level === l ? "all" : l)}
                  title={`Show only ${l} lines`}
                >
                  <span className="level-name">{l}</span>
                  <span className="level-track">
                    <span style={{ width: `${a.total_lines ? (a.levels[l] / a.total_lines) * 100 : 0}%` }} />
                  </span>
                  <span className="level-count">{a.levels[l]}</span>
                </button>
              ))}
            </div>
            <p className="muted small-text">{a.error_rate}% of lines are errors or critical.</p>
            <h3 className="sub-heading">Most frequent errors</h3>
            {a.top_errors.length === 0 ? (
              <p className="muted small-text">No errors in this window.</p>
            ) : (
              <ol className="top-errors">
                {a.top_errors.map((e) => (
                  <li key={e.pattern}>
                    <span className="count">{e.count}×</span>
                    <code title={e.example}>{e.example}</code>
                  </li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      )}

      <AiExplainPanel request={explain} onClose={() => setExplain(null)} />
    </>
  );
}
