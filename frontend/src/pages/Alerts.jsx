/* Module 8 - Alerts and Notifications. */
import { BellRing, Check, CheckCheck, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import AiExplainPanel, { ExplainButton } from "../components/AiExplain";
import { Empty, KeyValue, Loading, Notice, PageHeader, Panel, Status, Tabs } from "../components/ui";
import usePolling from "../hooks/usePolling";
import useToast from "../hooks/useToast";
import { duration, timeAgo } from "../utils/format";

export default function Alerts() {
  const [filter, setFilter] = useState("firing");
  const list = usePolling(() => api.get(`/api/alerts${filter === "all" ? "" : `?status=${filter}`}`), 5000, [filter]);
  const summary = usePolling(() => api.get("/api/alerts/summary"), 5000);
  const rules = usePolling(() => api.get("/api/alerts/rules"), 0);
  const [explain, setExplain] = useState(null);
  const [notify, toast] = useToast();
  const [permission, setPermission] = useState(() => ("Notification" in window ? Notification.permission : "unsupported"));

  const call = async (fn, message) => {
    try {
      await fn();
      notify(message);
      list.refresh();
      summary.refresh();
    } catch (e) {
      notify(e.message, "error");
    }
  };

  const enableBrowser = async () => {
    if (!("Notification" in window)) return;
    setPermission(await Notification.requestPermission());
  };

  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Alerts"
        description="Raised when a threshold is breached for several samples in a row, or when a tool reports a failure."
        updatedAt={list.updatedAt}
        onRefresh={list.refresh}
      >
        <Tabs
          tabs={[
            { id: "firing", label: "Firing", count: s?.firing },
            { id: "resolved", label: "Resolved" },
            { id: "all", label: "All" },
          ]}
          active={filter}
          onChange={setFilter}
        />
      </PageHeader>

      {s && (
        <div className="summary-strip">
          <div><b className={s.critical ? "tone-crit-text" : ""}>{s.critical}</b> critical</div>
          <div><b className={s.warning ? "tone-warn-text" : ""}>{s.warning}</b> warning</div>
          <div><b>{s.info}</b> info</div>
          <div className="muted">{s.last_24h} raised in the last 24 hours</div>
        </div>
      )}

      <div className="grid alerts-layout">
        <Panel flush>
          {list.error && <div className="pad"><Notice error={list.error} /></div>}
          {!list.data && !list.error && <Loading />}
          {list.data && list.data.length === 0 && (
            <Empty>{filter === "firing" ? "Nothing is firing. All checks are passing." : "No alerts recorded yet."}</Empty>
          )}
          {list.data && list.data.length > 0 && (
            <ul className="alert-cards">
              {list.data.map((a) => (
                <li key={a.id} className={`alert-card sev-${a.status === "firing" ? a.severity : "resolved"} ${a.acknowledged ? "acked" : ""}`}>
                  <div className="alert-main">
                    <div className="alert-title">{a.title}</div>
                    <div className="alert-msg">{a.message}</div>
                    <div className="alert-meta">
                      <Status value={a.status === "firing" ? a.severity : "resolved"} label={a.status === "firing" ? a.severity : "resolved"} />
                      <span>{a.source}</span>
                      <span>started {timeAgo(a.started_at)}</span>
                      {a.resolved_at && <span>lasted {duration(a.resolved_at - a.started_at)}</span>}
                      {a.acknowledged ? <span>acknowledged</span> : null}
                    </div>
                  </div>
                  <div className="alert-actions">
                    <ExplainButton
                      small
                      label="Explain"
                      onClick={() =>
                        setExplain({
                          title: a.title,
                          text: `${a.title}\n${a.message}\nSource: ${a.source}\nSeverity: ${a.severity}`,
                          source: `${a.source} alert`,
                          context: "An alert raised by the DevOps dashboard. Explain likely causes and how to investigate.",
                        })
                      }
                    />
                    {a.status === "firing" && !a.acknowledged && (
                      <button className="btn ghost sm" onClick={() => call(() => api.post(`/api/alerts/${a.id}/ack`), "Acknowledged")}>
                        <Check size={14} /> Acknowledge
                      </button>
                    )}
                    {a.status === "firing" && (
                      <button className="btn ghost sm" onClick={() => call(() => api.post(`/api/alerts/${a.id}/resolve`), "Marked as resolved")}>
                        <CheckCheck size={14} /> Resolve
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="stack">
          <Panel title="Notifications">
            <div className="stack-sm">
              <div className="split">
                <span>Browser pop-ups</span>
                {permission === "granted" ? (
                  <Status value="ok" label="On" />
                ) : permission === "unsupported" ? (
                  <span className="muted">Not supported</span>
                ) : (
                  <button className="btn ghost sm" onClick={enableBrowser}>Turn on</button>
                )}
              </div>
              <div className="split">
                <span>Slack / Discord webhook</span>
                {rules.data?.webhook_configured ? <Status value="ok" label={rules.data.webhook_format} /> : <span className="muted">Set ALERT_WEBHOOK_URL</span>}
              </div>
              <button className="btn ghost sm" onClick={() => call(() => api.post("/api/alerts/test"), "Test notification sent")}>
                <BellRing size={14} /> Send test notification
              </button>
              {filter !== "firing" && (
                <button className="btn ghost sm" onClick={() => call(() => api.del("/api/alerts/resolved"), "Resolved alerts cleared")}>
                  <Trash2 size={14} /> Clear resolved history
                </button>
              )}
            </div>
          </Panel>
          {rules.data && (
            <Panel title="Rules">
              <KeyValue
                items={[
                  ...rules.data.threshold_rules.map((r) => [r.label, `≥ ${r.threshold}% (${r.severity})`]),
                  ["Must last", `${rules.data.for_samples} samples, about ${rules.data.for_samples * rules.data.sample_interval_seconds}s`],
                  ["Tool checks", `every ${rules.data.integration_poll_seconds}s`],
                ]}
              />
              <p className="muted small-text">Change thresholds in backend/.env (ALERT_CPU_THRESHOLD and others).</p>
            </Panel>
          )}
        </div>
      </div>

      <AiExplainPanel request={explain} onClose={() => setExplain(null)} />
      {toast}
    </>
  );
}
