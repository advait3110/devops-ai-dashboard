"""Finds which Gemini models actually answer with YOUR API key.
Usage (inside backend, venv active):  python check_gemini.py"""
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
KEY = os.getenv("GEMINI_API_KEY", "").strip()
BASE = os.getenv("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

CANDIDATES = [
    "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash",
    "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite",
]
QUESTION = "In one sentence: what does the command 'docker ps -a' show?"


def main() -> None:
    if not KEY:
        sys.exit("GEMINI_API_KEY is empty. Put your key in backend\\.env first.")
    with httpx.Client(timeout=60, headers={"x-goog-api-key": KEY}) as client:
        resp = client.get(f"{BASE}/models", params={"pageSize": 200})
        if resp.status_code != 200:
            sys.exit(f"Could not list models (HTTP {resp.status_code}): {resp.text[:300]}")
        visible = {m["name"].removeprefix("models/") for m in resp.json().get("models", [])
                   if "generateContent" in m.get("supportedGenerationMethods", [])}
        print(f"Your key can see {len(visible)} text models.\n")

        working = []
        for model in CANDIDATES:
            if visible and model not in visible:
                print(f"  -    {model:28s} not available to this key")
                continue
            body = {"contents": [{"role": "user", "parts": [{"text": QUESTION}]}],
                    "generationConfig": {"maxOutputTokens": 2048}}
            r = client.post(f"{BASE}/models/{model}:generateContent", json=body)
            if r.status_code == 200:
                parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                if text:
                    working.append(model)
                    print(f"  OK   {model:28s} {text[:90]}")
                    continue
                print(f"  ?    {model:28s} answered with empty text")
            elif r.status_code == 429:
                print(f"  -    {model:28s} quota exceeded / not free for this key (429)")
            else:
                msg = r.json().get("error", {}).get("message", r.text) if r.content else ""
                print(f"  -    {model:28s} HTTP {r.status_code}: {msg[:80]}")

    print()
    if not working:
        sys.exit("No model answered. Check the key at https://aistudio.google.com/apikey")
    print("Put these two lines in backend\\.env, then restart the backend:")
    print(f"  GEMINI_MODEL={working[0]}")
    print(f"  GEMINI_FALLBACK_MODEL={working[1] if len(working) > 1 else working[0]}")


if __name__ == "__main__":
    main()