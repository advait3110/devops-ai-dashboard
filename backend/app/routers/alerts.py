"""Module 8 - Alerts and Notifications endpoints."""

from fastapi import APIRouter, Query

from .. import state
from ..config import settings
from ..errors import IntegrationError

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.get("")
async def list_alerts(status: str | None = Query(None, pattern="^(firing|resolved)$"),
                      limit: int = Query(100, ge=1, le=500)):
    return state.alerts.list(status, limit)


@router.get("/summary")
async def summary():
    return state.alerts.summary()


@router.get("/rules")
async def rules():
    return {
        "threshold_rules": [r.__dict__ for r in state.alerts.rules],
        "for_samples": state.alerts.for_samples,
        "sample_interval_seconds": settings.sample_interval,
        "integration_poll_seconds": settings.integration_poll_interval,
        "webhook_configured": bool(settings.alert_webhook_url),
        "webhook_format": settings.alert_webhook_format,
    }


@router.post("/{alert_id}/ack")
async def acknowledge(alert_id: int):
    if not state.alerts.acknowledge(alert_id):
        raise IntegrationError("Alert not found", 404)
    return {"acknowledged": alert_id}


@router.post("/{alert_id}/resolve")
async def resolve(alert_id: int):
    alert = state.alerts.get(alert_id)
    if not alert:
        raise IntegrationError("Alert not found", 404)
    state.alerts.resolve(alert["key"])
    return {"resolved": alert_id}


@router.delete("/resolved")
async def clear_resolved():
    return {"deleted": state.alerts.clear_resolved()}


@router.post("/test")
async def test_alert():
    """Fires a test alert to check the notification channels end to end."""
    state.alerts.resolve("test:notification")
    state.alerts.fire("test:notification", "test", "info", "Test notification",
                      "If you can read this, alert notifications work.")
    await state.alerts.flush_notifications()
    return {"sent": True, "webhook": bool(settings.alert_webhook_url)}
