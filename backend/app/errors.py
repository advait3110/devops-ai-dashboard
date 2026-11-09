"""
Shared error type for integrations.

Every service raises IntegrationError when a tool is not configured or not
reachable. main.py converts it into a clean JSON response:

    {"detail": "Jenkins is not configured", "hint": "Set JENKINS_URL ..."}

The frontend shows the hint on screen, so the user always knows what to do
next instead of seeing a crash or fake data.
"""

from __future__ import annotations


class IntegrationError(Exception):
    def __init__(self, message: str, status_code: int = 503, hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.hint = hint


def status_payload(name: str, label: str, configured: bool, connected: bool,
                   detail: str = "", hint: str = "", **extra) -> dict:
    """Uniform shape used by every integration's status() method."""
    return {
        "name": name,
        "label": label,
        "configured": configured,
        "connected": connected,
        "detail": detail,
        "hint": hint,
        **extra,
    }
