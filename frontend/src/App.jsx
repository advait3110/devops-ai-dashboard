/*
 * App shell.
 * Routing uses the URL hash (#/logs, #/alerts ...). This needs no router
 * library, survives a page refresh and works behind any static web server.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import Sidebar from "./components/Sidebar";
import { PAGES } from "./navigation";
import usePolling from "./hooks/usePolling";
import Alerts from "./pages/Alerts";
import Assistant from "./pages/Assistant";
import CICD from "./pages/CICD";
import Containers from "./pages/Containers";
import Dashboard from "./pages/Dashboard";
import Infrastructure from "./pages/Infrastructure";
import Logs from "./pages/Logs";
import SystemMonitoring from "./pages/SystemMonitoring";

const COMPONENTS = {
  dashboard: Dashboard,
  system: SystemMonitoring,
  cicd: CICD,
  containers: Containers,
  infrastructure: Infrastructure,
  assistant: Assistant,
  logs: Logs,
  alerts: Alerts,
};

const pageFromHash = () => {
  const id = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  return PAGES.some((p) => p.id === id) ? id : "dashboard";
};

/** Shows a desktop notification for every NEW firing alert (if the user allowed it). */
function useAlertNotifications(alerts) {
  const seen = useRef(null);
  useEffect(() => {
    if (!alerts) return;
    const firing = alerts.filter((a) => a.status === "firing");
    if (seen.current === null) {
      seen.current = new Set(firing.map((a) => a.id)); // don't notify for old alerts on page load
      return;
    }
    for (const a of firing) {
      if (seen.current.has(a.id)) continue;
      seen.current.add(a.id);
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification(`${a.severity === "critical" ? "Critical" : "Alert"}: ${a.title}`, {
          body: a.message || "",
          tag: `alert-${a.id}`,
        });
      }
    }
  }, [alerts]);
}

export default function App() {
  const [page, setPage] = useState(pageFromHash);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = useCallback((id) => {
    window.location.hash = `/${id}`;
    setPage(id);
  }, []);

  const { data: summary } = usePolling(() => api.get("/api/alerts/summary"), 15000);
  const { data: firing } = usePolling(() => api.get("/api/alerts?status=firing&limit=50"), 15000);
  const { data: info } = usePolling(() => api.get("/api/system/info"), 0);
  useAlertNotifications(firing);

  const Page = COMPONENTS[page];
  return (
    <div className="app">
      <Sidebar active={page} onNavigate={navigate} alertSummary={summary} host={info?.hostname} />
      <main className="main" id="main">
        <Page navigate={navigate} />
      </main>
    </div>
  );
}
