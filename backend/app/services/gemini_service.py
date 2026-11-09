"""
Module 6 - AI Assistant (Google Gemini API).

Why the REST API instead of an SDK?
* The model runs on Google's servers, so the laptop needs no GPU/RAM/disk
  for a local model (the reason we chose Gemini over Ollama).
* Calling the REST endpoint with httpx (already a dependency) avoids
  installing the large google SDK + gRPC stack.

Endpoint:
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  Header: x-goog-api-key: <GEMINI_API_KEY>

Three features use it:
  1. chat()     natural-language DevOps assistant, optionally grounded with
                LIVE data from this dashboard (metrics, alerts, containers...)
  2. analyze()  explains an error / log / failed build and suggests fixes
  3. everything sent is passed through redact() first, so secrets in logs
                are not sent to a third party.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from ..errors import IntegrationError, status_payload
from ..utils.redact import redact

API_BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
HINT = ("Create a free API key at https://aistudio.google.com/apikey and set "
        "GEMINI_API_KEY in backend/.env, then restart the backend.")

MAX_INPUT_CHARS = 14_000  # keeps requests fast and inside free-tier limits

ASSISTANT_PROMPT = """You are "DevOps AI", the assistant built into a DevOps monitoring dashboard.
You help developers and DevOps engineers with Linux, Windows, Docker, Kubernetes (Minikube),
Jenkins, GitHub Actions, Prometheus, Grafana, Nginx, Terraform and AWS (EC2, S3, IAM, CloudWatch).

Rules:
- Be practical and concise. Prefer numbered steps and exact commands in fenced code blocks.
- When LIVE DASHBOARD DATA is provided, base your answer on it and quote the relevant numbers.
  Never invent metrics, container names or pod names that are not in the data.
- If information is missing, say what command the user should run to get it.
- Warn before destructive commands (rm -rf, kubectl delete, terraform destroy, docker system prune).
- Use Markdown formatting."""

ANALYZE_PROMPT = """You are a senior Site Reliability Engineer doing incident troubleshooting.
Analyse the error / log / build output provided by the user and answer in Markdown with exactly
these sections:

### Summary
One or two sentences: what failed.
### Root cause
The most likely cause, referencing the specific log lines. Mention alternatives if unsure.
### Fix
Numbered steps with exact commands or config changes in code blocks.
### Prevention
1-3 bullet points to stop it happening again (tests, alerts, limits, CI checks).

Severity: end with a line "**Severity:** low | medium | high | critical" choosing one.
Do not invent details that are not in the input."""

_ERROR_HINT = re.compile(r"(?i)(error|exception|traceback|fail|fatal|panic|denied|refused|"
                         r"timeout|timed out|not found|crashloop|oomkilled|exit code|errno|warn)")


def smart_excerpt(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    """
    Long logs are trimmed intelligently instead of cut blindly:
    keep every error-looking line with 2 lines of context + the last 60 lines.
    """
    if len(text) <= limit:
        return text
    lines = text.splitlines()
    keep: set[int] = set(range(max(0, len(lines) - 60), len(lines)))
    for i, line in enumerate(lines):
        if _ERROR_HINT.search(line):
            keep.update(range(max(0, i - 2), min(len(lines), i + 3)))
    picked, prev = [], -2
    for i in sorted(keep):
        if i != prev + 1:
            picked.append("... [lines omitted] ...")
        picked.append(lines[i][:500])
        prev = i
    excerpt = "\n".join(picked)
    return excerpt[-limit:]


class GeminiService:
    name = "gemini"
    label = "Google Gemini"

    def __init__(self, api_key: str, model: str, fallback_model: str, timeout: float = 60) -> None:
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.timeout = timeout
        self.active_model = model

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def status(self) -> dict[str, Any]:
        # We do not call the API here (it would spend quota); a real call
        # happens on the first question.
        if not self.configured:
            return status_payload(self.name, self.label, False, False, "No API key", HINT)
        return status_payload(self.name, self.label, True, True, f"Model {self.active_model}",
                              model=self.active_model)

    async def _generate(self, model: str, system: str, contents: list[dict], temperature: float) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": 4096},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(f"{API_BASE}/models/{model}:generateContent",
                                         headers={"x-goog-api-key": self.api_key}, json=body)
            except httpx.TimeoutException as exc:
                raise IntegrationError("Gemini took too long to answer - try again", 504) from exc
            except httpx.HTTPError as exc:
                raise IntegrationError(f"Cannot reach Gemini API: {exc.__class__.__name__}", 503) from exc

        if resp.status_code == 404:
            raise _ModelNotFound(model)
        if resp.status_code in (400, 403) and "API key" in resp.text:
            raise IntegrationError("Gemini rejected the API key", 502, HINT)
        if resp.status_code == 429:
            raise IntegrationError("Gemini rate limit / free-tier quota reached. Wait a minute and retry.", 429)
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                msg = resp.text
            raise IntegrationError(f"Gemini error {resp.status_code}: {msg[:300]}", 502)

        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            reason = data.get("promptFeedback", {}).get("blockReason", "no answer returned")
            raise IntegrationError(f"Gemini returned no answer ({reason})", 502)
        parts = candidates[0].get("content", {}).get("parts", [])
        # Skip internal "thought" parts that thinking models may return.
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise IntegrationError(
                f"Gemini returned an empty answer (finishReason={candidates[0].get('finishReason')})", 502)
        return text.strip()

    async def generate(self, system: str, contents: list[dict], temperature: float = 0.4) -> dict[str, str]:
        if not self.configured:
            raise IntegrationError("Gemini API key is not configured", 503, HINT)
        models = [self.active_model] + [m for m in (self.model, self.fallback_model)
                                        if m and m != self.active_model]
        for model in models:
            try:
                text = await self._generate(model, system, contents, temperature)
                self.active_model = model  # remember the model that works
                return {"text": text, "model": model}
            except _ModelNotFound:
                continue
        raise IntegrationError(f"None of the configured Gemini models are available: {', '.join(models)}. "
                               "Set GEMINI_MODEL to a current model name.", 502, HINT)

    # ------------------------------------------------------------------ #
    async def chat(self, messages: list[dict[str, str]], live_context: str | None = None) -> dict[str, str]:
        """messages: [{"role": "user"|"assistant", "content": "..."}] (last 12 kept)."""
        contents = []
        for m in messages[-12:]:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": redact(m.get("content", ""))[:MAX_INPUT_CHARS]}]})
        if not contents or contents[-1]["role"] != "user":
            raise IntegrationError("The last message must come from the user", 400)
        if live_context:
            question = contents[-1]["parts"][0]["text"]
            contents[-1]["parts"][0]["text"] = (
                f"LIVE DASHBOARD DATA (collected just now):\n{redact(live_context)}\n\n"
                f"USER QUESTION:\n{question}")
        return await self.generate(ASSISTANT_PROMPT, contents, temperature=0.4)

    async def analyze(self, text: str, source: str = "log", context: str = "") -> dict[str, str]:
        if not text.strip():
            raise IntegrationError("Nothing to analyse", 400)
        prompt = f"Source: {source}\n"
        if context:
            prompt += f"Context: {context}\n"
        prompt += f"\n```\n{smart_excerpt(redact(text))}\n```"
        return await self.generate(ANALYZE_PROMPT, [{"role": "user", "parts": [{"text": prompt}]}],
                                   temperature=0.2)


class _ModelNotFound(Exception):
    pass
