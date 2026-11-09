"""
Secret redaction.

Logs and CI output often contain credentials. Before ANY text is sent to an
external AI service we mask things that look like secrets. This is a
"defence in depth" measure - it is not perfect, but it removes the common cases.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PEM private keys
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED PRIVATE KEY]"),
    # AWS access key ids
    (re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    # GitHub tokens
    (re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    # Google API keys
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), "[REDACTED_GOOGLE_KEY]"),
    # Slack tokens
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    # JWTs
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED_JWT]"),
    # Authorization headers
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer|basic|token)\s+[^\s\"']+"), r"\1\2 [REDACTED]"),
    # key=value / key: value style secrets
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token)(\s*[:=]\s*)([\"']?)[^\s\"',;]+\3"),
     r"\1\2\3[REDACTED]\3"),
    # credentials inside URLs: https://user:pass@host
    (re.compile(r"(\w+://[^/\s:@]+):[^/\s@]+@"), r"\1:[REDACTED]@"),
]


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
