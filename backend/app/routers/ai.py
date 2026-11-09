"""Module 6 - AI Assistant endpoints (Google Gemini)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import metrics, state
from ..context import build_live_context
from ..errors import IntegrationError

router = APIRouter(prefix="/api/ai", tags=["AI Assistant"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=50)
    use_live_data: bool = True


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200_000)
    source: str = Field("log", max_length=100)
    context: str = Field("", max_length=2_000)


@router.get("/status")
async def ai_status():
    return await state.gemini.status()


@router.get("/context")
async def ai_context():
    """Shows exactly what live data would be sent to Gemini (transparency)."""
    return {"context": await build_live_context()}


@router.post("/chat")
async def chat(req: ChatRequest):
    context = await build_live_context() if req.use_live_data else None
    try:
        result = await state.gemini.chat([m.model_dump() for m in req.messages], context)
        metrics.AI_REQUESTS.labels("chat", "ok").inc()
    except IntegrationError:
        metrics.AI_REQUESTS.labels("chat", "error").inc()
        raise
    return {"reply": result["text"], "model": result["model"], "used_live_data": context is not None}


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        result = await state.gemini.analyze(req.text, req.source, req.context)
        metrics.AI_REQUESTS.labels("analyze", "ok").inc()
    except IntegrationError:
        metrics.AI_REQUESTS.labels("analyze", "error").inc()
        raise
    return {"analysis": result["text"], "model": result["model"]}
