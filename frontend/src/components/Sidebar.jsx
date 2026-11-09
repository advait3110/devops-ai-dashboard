import { Menu, X } from "lucide-react";
import { useState } from "react";
import { PAGES } from "../navigation";

export default function Sidebar({ active, onNavigate, alertSummary, host }) {
  const [open, setOpen] = useState(false);
  const firing = alertSummary?.firing || 0;
  const critical = alertSummary?.critical || 0;

  const go = (id) => {
    onNavigate(id);
    setOpen(false);
  };

  return (
    <>
      <div className="mobile-bar">
        <button className="btn ghost icon" onClick={() => setOpen(!open)} aria-label="Toggle navigation">
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
        <span className="brand-name">DevOps AI</span>
      </div>
      <nav className={`sidebar ${open ? "open" : ""}`} aria-label="Main">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="#16233a" />
            <polyline
              points="4,19 10,19 13,9 18,25 21,15 28,15"
              fill="none"
              stroke="#34c79a"
              strokeWidth="2.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <div>
            <div className="brand-name">DevOps AI</div>
            <div className="brand-host">{host || "connecting…"}</div>
          </div>
        </div>

        <ul className="nav">
          {PAGES.map(({ id, label, icon: Icon }) => (
            <li key={id}>
              <a
                href={`#/${id}`}
                className={`nav-item ${active === id ? "active" : ""}`}
                aria-current={active === id ? "page" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  go(id);
                }}
              >
                <Icon size={18} />
                <span>{label}</span>
                {id === "alerts" && firing > 0 && (
                  <span className={`nav-badge ${critical ? "crit" : "warn"}`}>{firing}</span>
                )}
              </a>
            </li>
          ))}
        </ul>

        <div className={`health-card ${critical ? "crit" : firing ? "warn" : "ok"}`}>
          <span className="dot" />
          <div>
            <strong>{critical ? "Critical issues" : firing ? "Needs attention" : "All quiet"}</strong>
            <p>{firing ? `${firing} alert${firing > 1 ? "s" : ""} firing` : "No alerts firing"}</p>
          </div>
        </div>
      </nav>
    </>
  );
}
