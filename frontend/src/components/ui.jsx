/* Small presentational building blocks shared by every page. */
import { CircleAlert, RefreshCw } from "lucide-react";
import { statusLabel, timeAgo, tone } from "../utils/format";

export function PageHeader({ title, description, updatedAt, onRefresh, children }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      <div className="page-actions">
        {children}
        {updatedAt && <span className="updated">Updated {timeAgo(updatedAt)}</span>}
        {onRefresh && (
          <button className="btn ghost icon" onClick={onRefresh} title="Refresh now" aria-label="Refresh now">
            <RefreshCw size={16} />
          </button>
        )}
      </div>
    </header>
  );
}

export function Panel({ title, subtitle, actions, children, className = "", flush = false }) {
  return (
    <section className={`panel ${flush ? "flush" : ""} ${className}`}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p className="panel-sub">{subtitle}</p>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Status({ value, label }) {
  const t = tone(value);
  return (
    <span className={`status status-${t}`}>
      <span className="dot" aria-hidden="true" />
      {label ?? statusLabel(value)}
    </span>
  );
}

/** Shown when an integration is not configured / unreachable: says exactly what to do. */
export function Notice({ error, title }) {
  if (!error) return null;
  const notConfigured = error.status === 503;
  return (
    <div className={`notice ${notConfigured ? "notice-setup" : "notice-error"}`} role="status">
      <CircleAlert size={18} />
      <div>
        <strong>{title || error.message}</strong>
        {title && <p>{error.message}</p>}
        {error.hint && <p className="hint">{error.hint}</p>}
      </div>
    </div>
  );
}

export function Loading({ label = "Loading" }) {
  return <div className="loading">{label}…</div>;
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={active === t.id}
          className={`tab ${active === t.id ? "active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Meter({ value, max = 100, warn = 75, crit = 90 }) {
  const v = Math.max(0, Math.min(100, ((value || 0) / max) * 100));
  const t = v >= crit ? "crit" : v >= warn ? "warn" : "ok";
  return (
    <span className="meter" role="meter" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}>
      <span className={`meter-fill tone-${t}`} style={{ width: `${v}%` }} />
    </span>
  );
}

export function KeyValue({ items }) {
  return (
    <dl className="kv">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v ?? "-"}</dd>
        </div>
      ))}
    </dl>
  );
}
