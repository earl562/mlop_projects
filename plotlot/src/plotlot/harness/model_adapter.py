"""Model adapter — wires AgentLoop to any LLM provider.

Provider-agnostic: OpenRouter (default, free models for testing), Anthropic direct,
OpenAI direct, Groq, or any OpenAI-compatible endpoint.

Usage:
    from plotlot.harness.model_adapter import create_model_caller

    call_model = create_model_caller(provider="openrouter", model="google/gemini-2.5-flash-lite:free")
    agent = AgentLoop(config=config, call_model=call_model, execute_tool=my_tools)
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from plotlot.harness.middleware import AgentState

# ---------------------------------------------------------------------------
# Provider configurations — env-var driven, zero-hardcoding
# ---------------------------------------------------------------------------

PROVIDER_CONFIGS: dict[str, dict[str, str]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_model": "google/gemini-2.5-flash-lite:free",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4.1",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": "meta-llama/llama-4-scout-17b-16e-instruct",
    },
    "anthropic": {
        "base_url": "",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-6",
    },
}

OPENROUTER_FREE_MODELS: list[str] = [
    "google/gemini-2.5-flash-lite:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "meta-llama/llama-4-maverick:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
]


def _detect_provider() -> tuple[str, str, str]:
    """Auto-detect provider from env vars. Priority: OpenRouter > OpenAI > Anthropic > Groq."""
    for name in ["openrouter", "openai", "anthropic", "groq"]:
        cfg = PROVIDER_CONFIGS[name]
        key = os.environ.get(cfg["api_key_env"])
        if key:
            model = os.environ.get(f"{name.upper()}_MODEL", cfg["default_model"])
            return name, model, key
    # Fallback: OpenRouter with no key (free models work without auth sometimes)
    return "openrouter", PROVIDER_CONFIGS["openrouter"]["default_model"], os.environ.get("OPENROUTER_API_KEY", "")


def create_model_caller(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> Callable[[AgentState, list[dict[str, Any]]], Awaitable[AgentState]]:
    """Create a call_model function for AgentLoop.

    Args:
        provider: "openrouter", "openai", "anthropic", "groq", or None (auto-detect)
        model: Model name or None (use provider default)
        api_key: API key or None (use env var)
        base_url: Override base URL or None (use provider default)
    """
    if provider is None:
        provider, model, api_key = _detect_provider()
    cfg = PROVIDER_CONFIGS.get(provider, PROVIDER_CONFIGS["openrouter"])
    model = model or cfg["default_model"]
    if api_key is None:
        api_key = os.environ.get(cfg["api_key_env"], "")
    api_base = base_url or cfg["base_url"]

    if provider == "anthropic":
        return _create_anthropic_caller(model, api_key)
    return _create_openai_compatible_caller(model, api_key, api_base, provider)


# ---------------------------------------------------------------------------
# OpenAI-compatible caller (OpenRouter, OpenAI, Groq)
# ---------------------------------------------------------------------------

def _create_openai_compatible_caller(
    model: str, api_key: str, base_url: str, provider: str
) -> Callable[[AgentState, list[dict[str, Any]]], Awaitable[AgentState]]:
    """Return an async call_model for OpenAI-compatible endpoints."""

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key or "sk-placeholder", base_url=base_url, timeout=120.0, max_retries=2)
    except ImportError:
        async def _noop(s: AgentState, tools: list[dict[str, Any]]) -> AgentState:
            s.add_message("assistant", "openai package not installed. pip install openai")
            s.should_stop = True
            s.stop_reason = "no_openai_sdk"
            return s
        return _noop

    async def _call(state: AgentState, tools: list[dict[str, Any]]) -> AgentState:
        messages = _build_messages(state)
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.1}
        if tools:
            kwargs["tools"] = _normalize_tools(tools)
            kwargs["tool_choice"] = "auto"
        if provider == "openrouter":
            kwargs["extra_headers"] = {"HTTP-Referer": "https://plotlot.ai", "X-Title": "PlotLot Agent Harness"}
        last_error = None
        for attempt in range(3):
            try:
                resp = await client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                msg = choice.message
                if msg.content:
                    state.add_message("assistant", msg.content)
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        state.add_tool_call(tc.function.name, args, tc.id)
                if choice.finish_reason == "stop" and not msg.tool_calls:
                    state.should_stop = True
                    state.stop_reason = "model_stopped"
                return state
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                retryable = any(kw in err_str for kw in ("rate", "timeout", "server", "overloaded", "capacity", "429", "503", "502"))
                if not retryable or attempt == 2:
                    break
                await asyncio.sleep(2 ** attempt)
        state.add_message("system", f"Model error after {attempt+1} attempts ({type(last_error).__name__}): {last_error}")
        state.should_stop = True
        state.stop_reason = f"model_error: {type(last_error).__name__}" if last_error else "model_error"
        return state
    return _call


# ---------------------------------------------------------------------------
# Anthropic direct caller
# ---------------------------------------------------------------------------

def _create_anthropic_caller(
    model: str, api_key: str
) -> Callable[[AgentState, list[dict[str, Any]]], Awaitable[AgentState]]:
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0, max_retries=2)
    except ImportError:
        async def _noop(s: AgentState, tools: list[dict[str, Any]]) -> AgentState:
            s.add_message("assistant", "anthropic package not installed. pip install anthropic")
            s.should_stop = True
            s.stop_reason = "no_anthropic_sdk"
            return s
        return _noop

    async def _call(state: AgentState, tools: list[dict[str, Any]]) -> AgentState:
        system, messages = _build_anthropic_messages(state)
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": 4096}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _normalize_tools_anthropic(tools)
        try:
            resp = await client.messages.create(**kwargs)
            for block in resp.content:
                if block.type == "text":
                    state.add_message("assistant", block.text)
                elif block.type == "tool_use":
                    state.add_tool_call(block.name, block.input or {}, block.id)
            if resp.stop_reason == "end_turn":
                state.should_stop = True
                state.stop_reason = "model_stopped"
        except Exception as e:
            state.add_message("system", f"Model error ({type(e).__name__}): {e}")
            state.should_stop = True
            state.stop_reason = f"model_error: {type(e).__name__}"
        return state
    return _call


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _build_messages(state: AgentState) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    for m in state.messages:
        role = m.get("role", "user")
        if role == "system":
            msgs.append({"role": "system", "content": m.get("content", "")})
        elif role == "assistant":
            msgs.append({"role": "assistant", "content": m.get("content", "")})
        else:
            msgs.append({"role": "user", "content": m.get("content", "")})
    return msgs


def _build_anthropic_messages(state: AgentState) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []
    for m in state.messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
        else:
            messages.append({"role": role, "content": content})
    return "\n".join(system_parts), messages


def _normalize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert tool schemas to OpenAI format."""
    result: list[dict[str, Any]] = []
    for t in tools:
        entry: dict[str, Any] = {"type": "function", "function": {"name": t.get("name", ""), "description": t.get("description", "")}}
        params = t.get("parameters") or t.get("input_schema") or {}
        if params:
            entry["function"]["parameters"] = params
        result.append(entry)
    return result


def _normalize_tools_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert tool schemas to Anthropic format."""
    result: list[dict[str, Any]] = []
    for t in tools:
        result.append({"name": t.get("name", ""), "description": t.get("description", ""), "input_schema": t.get("parameters") or t.get("input_schema") or {}})
    return result