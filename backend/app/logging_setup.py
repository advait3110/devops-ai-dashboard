"""
Logging: console + rotating file (logs/app.log, 2 MB x 3 files max).

The rotating file is also the "app" source of the Log Analysis module, so
the dashboard can analyse its own errors.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return  # already configured (uvicorn --reload imports twice)
    root.setLevel(level)
    formatter = logging.Formatter(FORMAT)

    file_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000,
                                       backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(console)

    # uvicorn's access log is very noisy because the UI polls; keep warnings only.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
