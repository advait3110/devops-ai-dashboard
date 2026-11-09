"""
Module 8 - Alerts and Notifications.

How an alert works (same idea as Prometheus' "for:" clause):

    value >= threshold for N consecutive samples  ->  FIRING   (notify once)
    value <  threshold - hysteresis               ->  RESOLVED (notify once)

* N samples (ALERT_FOR_SAMPLES) avoids alerting on a 1-second spike.
* Hysteresis (5 %) avoids "flapping" when a value hovers around the line.
* A unique `key` per problem means the same problem never creates duplicates.

Sources of alerts:
  system       psutil thresholds (CPU, memory, disk)
  docker       containers that crashed (non-zero exit), restart loops, unhealthy
  kubernetes   CrashLoopBackOff / ImagePullBackOff pods, NotReady nodes
  jenkins      jobs whose last build failed
  github       workflows whose latest run failed
  prometheus   alerts firing from monitoring/prometheus/alert_rules.yml

Storage: SQLite (built into Python) so history survives restarts with zero
setup. Notifications: in-app, browser notifications (frontend), and an
optional Slack / Discord / generic webhook.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("alerts")

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class ThresholdRule:
    key: str
    metric: str
    label: str
    threshold: float
    severity: str = "warning"
    hysteresis: float = 5.0


class AlertManager:
    def __init__(self, db_path: Path, rules: list[ThresholdRule], for_samples: int = 3,
                 webhook_url: str = "", webhook_format: str = "slack") -> None:
        self.rules = rules
        self.for_samples = for_samples
        self.webhook_url = webhook_url
        self.webhook_format = webhook_format
        self._breaches: dict[str, int] = {}
        self._lock = threading.Lock()
        self._pending_notifications: list[dict[str, Any]] = []
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                key          TEXT NOT NULL,
                source       TEXT NOT NULL,
                severity     TEXT NOT NULL,
                title        TEXT NOT NULL,
                message      TEXT,
                status       TEXT NOT NULL DEFAULT 'firing',
                acknowledged INTEGER NOT NULL DEFAULT 0,
                value        REAL,
                started_at   REAL NOT NULL,
                updated_at   REAL NOT NULL,
                resolved_at  REAL
            )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_alerts_key_status ON alerts(key, status)")
        self.db.commit()

    # ------------------------------------------------------------------ #
    # core state machine
    # ------------------------------------------------------------------ #
    def _active(self, key: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM alerts WHERE key=? AND status='firing'", (key,)).fetchone()

    def fire(self, key: str, source: str, severity: str, title: str, message: str = "",
             value: float | None = None) -> bool:
        """Create the alert if it is not already firing. Returns True if new."""
        now = time.time()
        with self._lock:
            row = self._active(key)
            if row:
                self.db.execute("UPDATE alerts SET value=?, message=?, severity=?, updated_at=? WHERE id=?",
                                (value, message, severity, now, row["id"]))
                self.db.commit()
                return False
            cur = self.db.execute(
                "INSERT INTO alerts (key, source, severity, title, message, value, started_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (key, source, severity, title, message, value, now, now))
            self.db.commit()
            alert = dict(self.db.execute("SELECT * FROM alerts WHERE id=?", (cur.lastrowid,)).fetchone())
        log.warning("ALERT FIRING [%s] %s - %s", severity, title, message)
        self._pending_notifications.append(alert)
        return True

    def resolve(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            row = self._active(key)
            if not row:
                return False
            self.db.execute("UPDATE alerts SET status='resolved', resolved_at=?, updated_at=? WHERE id=?",
                            (now, now, row["id"]))
            self.db.commit()
            alert = dict(self.db.execute("SELECT * FROM alerts WHERE id=?", (row["id"],)).fetchone())
        log.info("ALERT RESOLVED %s", alert["title"])
        self._pending_notifications.append(alert)
        return True

    # ------------------------------------------------------------------ #
    # evaluators
    # ------------------------------------------------------------------ #
    def evaluate_system(self, sample: dict[str, Any]) -> None:
        for rule in self.rules:
            value = sample.get(rule.metric)
            if value is None:
                continue
            if value >= rule.threshold:
                self._breaches[rule.key] = self._breaches.get(rule.key, 0) + 1
                if self._breaches[rule.key] >= self.for_samples:
                    self.fire(rule.key, "system", rule.severity,
                              f"High {rule.label}",
                              f"{rule.label} is {value:.1f}% (threshold {rule.threshold:.0f}%)",
                              value)
            else:
                self._breaches[rule.key] = 0
                if value < rule.threshold - rule.hysteresis:
                    self.resolve(rule.key)

    def sync_source(self, source: str, problems: dict[str, dict[str, Any]]) -> None:
        """
        problems = {key: {"severity", "title", "message"}} currently detected for `source`.
        Fires new ones and resolves alerts of that source that disappeared.
        """
        for key, p in problems.items():
            self.fire(key, source, p.get("severity", "warning"), p["title"], p.get("message", ""))
        rows = self.db.execute("SELECT key FROM alerts WHERE source=? AND status='firing'", (source,)).fetchall()
        for row in rows:
            if row["key"] not in problems:
                self.resolve(row["key"])

    # ------------------------------------------------------------------ #
    # queries
    # ------------------------------------------------------------------ #
    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM alerts", []
        if status in ("firing", "resolved"):
            sql += " WHERE status=?"
            args.append(status)
        sql += " ORDER BY (status='firing') DESC, updated_at DESC LIMIT ?"
        args.append(max(1, min(limit, 500)))
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def summary(self) -> dict[str, Any]:
        rows = self.db.execute(
            "SELECT severity, COUNT(*) AS n FROM alerts WHERE status='firing' GROUP BY severity").fetchall()
        by_sev = {r["severity"]: r["n"] for r in rows}
        last24 = self.db.execute("SELECT COUNT(*) FROM alerts WHERE started_at > ?",
                                 (time.time() - 86400,)).fetchone()[0]
        return {
            "firing": sum(by_sev.values()),
            "critical": by_sev.get("critical", 0),
            "warning": by_sev.get("warning", 0),
            "info": by_sev.get("info", 0),
            "last_24h": last24,
        }

    def acknowledge(self, alert_id: int) -> bool:
        with self._lock:
            cur = self.db.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))
            self.db.commit()
        return cur.rowcount > 0

    def get(self, alert_id: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
        return dict(row) if row else None

    def clear_resolved(self) -> int:
        with self._lock:
            cur = self.db.execute("DELETE FROM alerts WHERE status='resolved'")
            self.db.commit()
        return cur.rowcount

    # ------------------------------------------------------------------ #
    # notifications
    # ------------------------------------------------------------------ #
    async def flush_notifications(self) -> None:
        """Called by the background loop: sends queued notifications to the webhook."""
        pending, self._pending_notifications = self._pending_notifications, []
        if not self.webhook_url or not pending:
            return
        async with httpx.AsyncClient(timeout=10) as client:
            for alert in pending:
                icon = "\U0001F534" if alert["status"] == "firing" else "✅"
                text = (f"{icon} [{alert['severity'].upper()}] {alert['title']} "
                        f"({alert['status']}) - {alert.get('message') or ''}")
                if self.webhook_format == "discord":
                    payload: dict[str, Any] = {"content": text}
                elif self.webhook_format == "generic":
                    payload = {"text": text, "alert": alert}
                else:
                    payload = {"text": text}
                try:
                    await client.post(self.webhook_url, json=payload)
                except httpx.HTTPError as exc:
                    log.error("Webhook notification failed: %s", exc)
