"""Prompt-injection scanning helpers for external text.

This module is intentionally conservative: it does not block content by itself.
It only emits warnings so upstream code can degrade safely (e.g., avoid treating
scraped content as instructions).
"""

from __future__ import annotations

import re


_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_previous_instructions", re.compile(r"\bignore (all|any|the) (previous|prior) instructions\b", re.I)),
    ("disregard_instructions", re.compile(r"\bdisregard (all|any|the) (previous|prior) instructions\b", re.I)),
    ("system_prompt_exfiltration", re.compile(r"\b(system prompt|developer message|hidden instructions)\b", re.I)),
    ("role_override", re.compile(r"\b(you are (now|no longer)|act as)\b", re.I)),
    ("tool_coercion", re.compile(r"\b(call|invoke|run) (the )?(tool|function)\b", re.I)),
)


def detect_prompt_injection(text: str) -> list[str]:
    """Return warning strings when text looks like prompt-injection content."""

    normalized = " ".join((text or "").split())
    if not normalized:
        return []

    warnings: list[str] = []
    for label, pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized):
            warnings.append(f"Possible prompt injection pattern detected: {label}")
    return warnings

