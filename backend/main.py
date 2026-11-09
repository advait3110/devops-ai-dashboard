"""
Backwards-compatible entry point.

The application now lives in the `app` package. Both commands work:
    uvicorn app.main:app --reload --port 8000
    uvicorn main:app --reload --port 8000
"""

from app.main import app  # noqa: F401
