/* Module 2 - System Monitoring (psutil): CPU, memory, disk, network, processes. */
import { useState } from "react";
import { api } from "../api";
import { Gauge, LineChart } from "../components/charts";
import { KeyValue, Loading, Meter, Notice, PageHeader, Panel, Tabs } from "../components/ui";
import usePolling from "../hooks/usePolling";
import { bytes, duration, niceBytes, toDate } from "../utils/format";

const RANGES = [
  { id: 5, label: "5 min" },
  { id: 15, label: "15 min" },
  { id: 60, label: "1 hour" },
];

export default function SystemMonitoring() {
  const [minutes, setMinutes] = useState(15);
  const [sort, setSort] = useState("cpu");

  const metrics = usePolling(() => api.get("/api/system/metrics"), 5000);
  const history = usePolling(() => api.get(`/api/system/history?minutes=${minutes}`), 5000, [minutes]);
  const info = usePolling(() => api.get("/api/system/info"), 60000);
  const disks = usePolling(() => api.get("/api/system/disks"), 60000);
  const procs = usePolling(() => api.get(`/api/system/processes?limit=12&sort=${sort}`), 5000, [sort]);

  if (metrics.error && !metrics.data) return <Notice error={metrics.error} />;
  if (!metrics.data || !info.data) return <Loading />;

  const m = metrics.data;
  const h = info.data;
  const pts = history.data?.points || [];
  const series = (key, name, color) => ({ name, color, points: pts.map((p) => [p.timestamp, p[key]]) });

  return (
    <>
      <PageHeader
        title="System"
        description="Measured on this machine with psutil every few seconds. History is kept in memory for one hour."
        updatedAt={metrics.updatedAt}
        onRefresh={metrics.refresh}
      />

      <div className="gauges">
        <Gauge label="CPU" value={m.cpu_percent} detail={`load ${m.load_avg.join(" / ")}`} />
        <Gauge label="Memory" value={m.memory_percent} detail={`${m.memory_used_gb} / ${m.memory_total_gb} GB`} />
        <Gauge label="Disk" value={m.disk_percent} warn={80} detail={`${m.disk_used_gb} / ${m.disk_total_gb} GB`} />
        <Gauge label="Swap" value={m.swap_percent} warn={50} crit={80} detail="paging to disk" />
      </div>

      <Panel
        title="CPU and memory"
        actions={<Tabs tabs={RANGES} active={minutes} onChange={setMinutes} />}
      >
        <LineChart
          yMax={100}
          yFormat={(v) => `${v.toFixed(0)}%`}
          series={[series("cpu_percent", "CPU", "#4c8dff"), series("memory_percent", "Memory", "#34c79a")]}
        />
      </Panel>

      <div className="grid two">
        <Panel title="Network" subtitle={`${bytes(m.net_rx_bps, true)} in, ${bytes(m.net_tx_bps, true)} out`}>
          <LineChart
            height={150}
            yFormat={(v) => bytes(v, true)}
            yNice={niceBytes}
            series={[series("net_rx_bps", "Received", "#7aa7ff"), series("net_tx_bps", "Sent", "#f2b84b")]}
          />
        </Panel>
        <Panel title="Disk activity" subtitle={`${bytes(m.disk_read_bps, true)} read, ${bytes(m.disk_write_bps, true)} write`}>
          <LineChart
            height={150}
            yFormat={(v) => bytes(v, true)}
            yNice={niceBytes}
            series={[series("disk_read_bps", "Read", "#34c79a"), series("disk_write_bps", "Write", "#ff6b6b")]}
          />
        </Panel>
      </div>

      <div className="grid two">
        <Panel title="Host">
          <KeyValue
            items={[
              ["Hostname", h.hostname],
              ["Operating system", `${h.os} ${h.os_release}`],
              ["Architecture", h.architecture],
              ["CPU", `${h.cpu_physical_cores ?? "?"} cores, ${h.cpu_logical_cores} threads${h.cpu_freq_mhz ? `, ${h.cpu_freq_mhz} MHz` : ""}`],
              ["Booted", toDate(h.boot_time)?.toLocaleString()],
              ["Uptime", duration(h.uptime_seconds)],
              ["Processes", m.process_count],
              ["Python", h.python_version],
            ]}
          />
        </Panel>
        <Panel title="Disks" flush>
          <table className="table">
            <thead>
              <tr><th>Mount</th><th>Type</th><th>Used</th><th className="num">Free</th></tr>
            </thead>
            <tbody>
              {(disks.data || []).map((d) => (
                <tr key={d.mountpoint}>
                  <td className="mono-cell">{d.mountpoint}</td>
                  <td>{d.fstype}</td>
                  <td>
                    <div className="meter-row"><Meter value={d.percent} warn={80} /> {d.percent}%</div>
                  </td>
                  <td className="num">{d.free_gb} GB</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>

      <Panel
        title="Top processes"
        subtitle="CPU is shown as a share of the whole machine."
        actions={
          <Tabs
            tabs={[{ id: "cpu", label: "By CPU" }, { id: "memory", label: "By memory" }]}
            active={sort}
            onChange={setSort}
          />
        }
        flush
      >
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>PID</th><th>Name</th><th>User</th><th>CPU</th><th>Memory</th><th className="num">RSS</th></tr>
            </thead>
            <tbody>
              {(procs.data || []).map((p) => (
                <tr key={p.pid}>
                  <td className="num-left">{p.pid}</td>
                  <td>{p.name}</td>
                  <td className="muted">{p.user || "-"}</td>
                  <td><div className="meter-row"><Meter value={p.cpu_percent} warn={50} crit={80} /> {p.cpu_percent}%</div></td>
                  <td><div className="meter-row"><Meter value={p.memory_percent} warn={25} crit={50} /> {p.memory_percent}%</div></td>
                  <td className="num">{p.memory_mb} MB</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
