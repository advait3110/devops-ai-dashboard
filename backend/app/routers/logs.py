"""Module 7 - Log Analysis endpoints."""

from fastapi import APIRouter, Query

from .. import state
from ..services.log_service import analyse, detect_level

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("/sources")
async def sources():
    return await state.logs.sources()


@router.get("")
async def read_logs(
    source: str = Query("app"),
    target: str = Query(""),
    tail: int = Query(300, ge=10, le=2000),
    level: str = Query("all", pattern="^(all|critical|error|warning|info|debug)$"),
    search: str = Query("", max_length=200),
):
    text = await state.logs.read(source, target, tail)
    all_lines = [line for line in text.splitlines() if line.strip()]
    lines = []
    for number, line in enumerate(all_lines, start=1):
        lvl = detect_level(line)
        if level != "all" and lvl != level:
            continue
        if search and search.lower() not in line.lower():
            continue
        lines.append({"n": number, "level": lvl, "text": line[:2000]})
    return {
        "source": source,
        "target": target,
        "analysis": analyse(all_lines),
        "lines": lines,
    }
