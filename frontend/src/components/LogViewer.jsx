import { useEffect, useRef } from "react";

// Same rules as the backend (log_service.py): an explicit level field wins,
// keywords are only a fallback for free text such as build output.
const EXPLICIT = /\b(CRITICAL|FATAL|PANIC|ERROR|ERR|WARNING|WARN|INFO|DEBUG|TRACE)\b|\[(crit|emerg|alert|error|warn|notice|info|debug)\]|level[=:]\s*"?(\w+)/i;
const MAP = { critical: "critical", fatal: "critical", panic: "critical", crit: "critical", emerg: "critical",
  alert: "critical", error: "error", err: "error", warning: "warning", warn: "warning", info: "info",
  notice: "info", debug: "debug", trace: "debug" };
const FALLBACK = [
  ["critical", /\b(fatal|panic)\b|OOMKilled|out of memory/i],
  ["error", /\b(error|exception|traceback|failed|failure|denied|refused)\b/i],
  ["warning", /\b(warn|warning|deprecated|retry|timeout)\b/i],
];

function lineLevel(text) {
  const m = EXPLICIT.exec(text.slice(0, 100));
  if (m && (!m[1] || m[1] === m[1].toUpperCase())) {
    const level = MAP[(m[1] || m[2] || m[3]).toLowerCase()];
    if (level) return level;
  }
  for (const [level, re] of FALLBACK) if (re.test(text)) return level;
  return "info";
}

/**
 * lines: [{ n, level, text }]  or a raw string.
 * Scrolls to the bottom so the newest lines are visible, like `tail -f`.
 */
export default function LogViewer({ lines, text, height = 420, emptyText = "No log lines." }) {
  const ref = useRef(null);
  const rows = lines || (text || "").split("\n").map((t, i) => ({ n: i + 1, level: lineLevel(t), text: t }));

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [rows.length]);

  if (!rows.length || (rows.length === 1 && !rows[0].text)) return <div className="empty">{emptyText}</div>;

  return (
    <div className="log-viewer" ref={ref} style={{ maxHeight: height }} tabIndex={0}>
      {rows.map((r) => (
        <div key={r.n} className={`log-line lvl-${r.level}`}>
          <span className="ln">{r.n}</span>
          <span className="lt">{r.text}</span>
        </div>
      ))}
    </div>
  );
}
