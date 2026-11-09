export function bytes(value, perSecond = false) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Math.abs(value);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}${perSecond ? "/s" : ""}`;
}

export const pct = (v) => (v === null || v === undefined ? "-" : `${Number(v).toFixed(1)}%`);

/** Accepts unix seconds, milliseconds or ISO strings. */
export function toDate(value) {
  if (!value) return null;
  if (typeof value === "number") return new Date(value > 1e12 ? value : value * 1000);
  return new Date(value);
}

export function timeAgo(value) {
  const d = toDate(value);
  if (!d || Number.isNaN(d.getTime())) return "-";
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function duration(seconds) {
  if (seconds === null || seconds === undefined) return "-";
  const s = Math.round(seconds);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

export const clockTime = (value) => {
  const d = toDate(value);
  return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "-";
};

/** Maps any status word from any tool onto 4 visual tones. */
export function tone(status) {
  const s = String(status || "").toLowerCase();
  if (["success", "running", "ok", "up", "healthy", "ready", "resolved", "succeeded", "completed", "connected"].includes(s))
    return "ok";
  if (["failed", "critical", "down", "exited", "crashloopbackoff", "error", "imagepullbackoff", "errimagepull",
       "oomkilled", "unhealthy", "notready", "dead"].includes(s))
    return "crit";
  if (["unstable", "warning", "restarting", "pending", "queued", "paused", "terminating", "starting",
       "containercreating", "cancelled"].includes(s))
    return "warn";
  return "neutral";
}

export const statusLabel = (s) =>
  String(s || "unknown").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Rounds a byte value up to 1, 2, 4, 8 ... x 1024^n so chart ticks are readable. */
export function niceBytes(v) {
  const unit = 1024 ** Math.floor(Math.log(Math.max(v, 1)) / Math.log(1024));
  const steps = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024];
  return (steps.find((x) => x >= v / unit) || 1024) * unit;
}
