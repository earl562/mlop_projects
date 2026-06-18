"""LLM client backed by the official OpenAI Python SDK.

Supports three modes:
  1. Agentic tool-use: call_llm() returns tool_calls for the agent loop
  2. Direct analysis: analyze_zoning() for non-agentic one-shot analysis
  3. Streaming chat: call_llm_stream() yields tokens for conversational UI

Auth:
  - Primary (OpenAI):
      - OPENAI_API_KEY for direct API-key auth
      - OPENAI_ACCESS_TOKEN for OAuth-backed bearer tokens supplied by the caller
      - OPENAI_BASE_URL for gateway / proxy deployments
  - Fallback (Groq, OpenAI-compatible):
      - GROQ_API_KEY
      - GROQ_BASE_URL (defaults to https://api.groq.com/openai/v1)
      - GROQ_MODEL
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, cast

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError

from plotlot.config import settings
from plotlot.core.types import SearchResult, Setbacks, ZoningReport
from plotlot.observability.tracing import log_metrics, start_span, trace
from plotlot.oauth.openai_auth import get_valid_access_token, has_saved_tokens

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
BASE_DELAY = 1.0
DEFAULT_OPENAI_MODEL = "gpt-4.1"
OPENAI_TIMEOUT_SECONDS = 60.0
DEFAULT_GROQ_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


# ---------------------------------------------------------------------------
# Circuit Breaker — contain failures without thrashing the upstream gateway.
# ---------------------------------------------------------------------------


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker for LLM API calls."""

    failure_threshold: int = 5
    reset_seconds: int = 60
    _failure_count: int = field(default=0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)
    _state: str = field(default="closed", repr=False)  # closed, open, half_open

    @property
    def state(self) -> str:
        if self._state == "open":
            if time.monotonic() - self._last_failure_time >= self.reset_seconds:
                self._state = "half_open"
        return self._state

    def allow_request(self) -> bool:
        current = self.state
        if current == "closed":
            return True
        if current == "half_open":
            return True
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                "Circuit breaker OPEN after %d failures (reset in %ds)",
                self._failure_count,
                self.reset_seconds,
            )


# Module-level singletons so the health/debug endpoint can inspect state.
_breakers: dict[str, CircuitBreaker] = {}


# ---------------------------------------------------------------------------
# Tool format conversions preserved for compatibility with existing tests.
# ---------------------------------------------------------------------------


def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool definitions to Anthropic tool format."""
    anthropic_tools = []
    for tool in tools:
        fn = tool.get("function", {})
        anthropic_tools.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            }
        )
    return anthropic_tools


def _convert_tool_calls_from_anthropic(content_blocks: list) -> list[dict]:
    """Convert Claude-style tool_use blocks to OpenAI-style tool_calls."""
    tool_calls = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                }
            )
        elif hasattr(block, "type") and block.type == "tool_use":
            tool_calls.append(
                {
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(
                            block.input if isinstance(block.input, dict) else {}
                        ),
                    },
                }
            )
    return tool_calls


def _convert_messages_for_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    """Convert OpenAI-format messages to Anthropic-style messages."""
    system_prompt = ""
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system_prompt = msg.get("content", "")
            continue

        if role == "tool":
            anthropic_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": msg.get("content", ""),
                        }
                    ],
                }
            )
            continue

        if role == "assistant":
            content_parts = []
            text_content = msg.get("content", "")
            if text_content:
                content_parts.append({"type": "text", "text": text_content})

            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}
                content_parts.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args,
                    }
                )

            if content_parts:
                anthropic_messages.append({"role": "assistant", "content": content_parts})
            else:
                anthropic_messages.append({"role": "assistant", "content": ""})
            continue

        anthropic_messages.append({"role": "user", "content": msg.get("content", "")})

    return system_prompt, anthropic_messages


# ---------------------------------------------------------------------------
# OpenAI client helpers
# ---------------------------------------------------------------------------


def _has_openai_credentials() -> bool:
    """Whether PlotLot has any viable OpenAI auth path configured."""
    if settings.openai_api_key or settings.openai_access_token:
        return True
    if settings.use_codex_oauth:
        from pathlib import Path

        return has_saved_tokens(Path(settings.codex_auth_file).expanduser())
    if settings.nvidia_api_key:
        return True
    return False


def _using_nvidia_mainline() -> bool:
    return bool(settings.nvidia_api_key)


async def _get_codex_oauth_token() -> str:
    """Return a refreshable Codex OAuth access token when configured."""
    if not settings.use_codex_oauth or not settings.openai_oauth_client_id:
        return settings.openai_access_token

    from pathlib import Path

    return await get_valid_access_token(
        client_id=settings.openai_oauth_client_id,
        auth_file=Path(settings.codex_auth_file).expanduser(),
        token_url=settings.openai_oauth_token_url,
    )


def _get_openai_model() -> str:
    if _using_nvidia_mainline():
        return settings.nvidia_model or "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    return settings.openai_model or DEFAULT_OPENAI_MODEL


def _get_groq_token() -> str:
    if not getattr(settings, "groq_enabled_non_mainline", False):
        return ""
    return getattr(settings, "groq_api_key", "")


def _get_groq_model() -> str:
    return getattr(settings, "groq_model", "") or DEFAULT_GROQ_MODEL


def _usable_response(result: dict | None) -> bool:
    if not result:
        return False
    return bool(result.get("content") or result.get("tool_calls"))


def _get_openai_client() -> AsyncOpenAI:
    if _using_nvidia_mainline():
        api_key: str | Any = settings.nvidia_api_key
    elif settings.openai_api_key:
        api_key = settings.openai_api_key
    elif settings.use_codex_oauth:
        api_key = _get_codex_oauth_token
    else:
        api_key = settings.openai_access_token

    kwargs: dict = {
        "api_key": api_key,
        "timeout": OPENAI_TIMEOUT_SECONDS,
    }
    if _using_nvidia_mainline():
        kwargs["base_url"] = settings.nvidia_base_url
    elif settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if settings.openai_organization and not _using_nvidia_mainline():
        kwargs["organization"] = settings.openai_organization
    if settings.openai_project and not _using_nvidia_mainline():
        kwargs["project"] = settings.openai_project
    return AsyncOpenAI(**kwargs)


def _prepare_primary_messages(messages: list[dict]) -> list[dict]:
    if not _using_nvidia_mainline():
        return messages

    prepared = [dict(msg) for msg in messages]
    if prepared and prepared[0].get("role") == "system":
        content = (prepared[0].get("content") or "").strip()
        if "/no_think" not in content:
            prepared[0]["content"] = f"/no_think\n\n{content}" if content else "/no_think"
        return prepared

    prepared.insert(0, {"role": "system", "content": "/no_think"})
    return prepared


def _sanitize_primary_content(content: str | None) -> str:
    text = (content or "").strip()
    if not _using_nvidia_mainline():
        return text
    if text.startswith("<think>"):
        if "</think>" in text:
            return text.split("</think>", 1)[1].strip()
        return ""
    return text


def _get_groq_client() -> AsyncOpenAI:
    kwargs: dict = {
        "api_key": _get_groq_token(),
        "base_url": settings.groq_base_url,
        "timeout": OPENAI_TIMEOUT_SECONDS,
    }
    return AsyncOpenAI(**kwargs)


def _get_breaker(provider_name: str) -> CircuitBreaker:
    breaker = _breakers.get(provider_name)
    if breaker is None:
        breaker = CircuitBreaker()
        _breakers[provider_name] = breaker
    return breaker


def _message_to_tool_calls(message) -> list[dict]:
    tool_calls = []
    for call in message.tool_calls or []:
        tool_calls.append(
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
        )
    return tool_calls


# Some NIM/Llama models occasionally emit a tool call as TEXT in the content —
# `<tool_call>{"name": ..., "arguments": {...}}</tool_call>` — instead of a
# structured tool_call. The agent loop then sees no tool_calls and streams the raw
# JSON to the user (the tool never runs). This recovers those blobs.
_TEXT_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _recover_text_tool_calls(content: str) -> tuple[list[dict], str]:
    """Parse text-emitted ``<tool_call>`` blobs into structured tool_calls.

    Returns ``(tool_calls, cleaned_content)``. Only successfully-parsed blobs are
    stripped from the content; an unparseable blob is left in place rather than
    silently swallowed. ``([], content)`` when there is nothing to recover.
    """
    if not content or "<tool_call>" not in content:
        return [], content

    recovered: list[dict] = []
    spans: list[tuple[int, int]] = []
    for i, match in enumerate(_TEXT_TOOL_CALL_RE.finditer(content)):
        try:
            payload = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        name = payload.get("name")
        if not name:
            continue
        # Tolerate both OpenAI-style "arguments" and "parameters".
        args = payload.get("arguments", payload.get("parameters", {}))
        if not isinstance(args, str):
            args = json.dumps(args or {})
        recovered.append(
            {
                "id": f"call_recovered_{i}",
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
        spans.append(match.span())

    if not recovered:
        return [], content

    cleaned = content
    for start, end in reversed(spans):
        cleaned = cleaned[:start] + cleaned[end:]
    return recovered, cleaned.strip()


def _log_usage(provider_slug: str, usage) -> tuple[int, int]:
    prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
    if prompt_tokens or completion_tokens:
        log_metrics(
            {
                f"{provider_slug}_prompt_tokens": float(prompt_tokens),
                f"{provider_slug}_completion_tokens": float(completion_tokens),
                f"{provider_slug}_total_tokens": float(prompt_tokens + completion_tokens),
            }
        )
    return prompt_tokens, completion_tokens


# ---------------------------------------------------------------------------
# Core provider calls
# ---------------------------------------------------------------------------


async def _call_openai(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    response_format: dict | None = None,
    max_completion_tokens: int = 4000,
    temperature: float = 0.1,
    provider_name: str,
) -> dict | None:
    """Call Chat Completions via the official OpenAI SDK."""
    if not _has_openai_credentials():
        return None

    async def _call_model(model: str, active_provider_name: str) -> dict | None:
        breaker = _get_breaker(active_provider_name)
        if not breaker.allow_request():
            logger.info("Circuit breaker OPEN for %s — skipping", active_provider_name)
            return None

        prepared_messages = _prepare_primary_messages(messages)
        with start_span(
            name=f"llm_provider_{active_provider_name.lower()}",
            span_type="CHAT_MODEL",
        ) as span:
            span.set_inputs(
                {
                    "provider": active_provider_name,
                    "model": model,
                    "message_count": len(prepared_messages),
                }
            )
            retries_used = 0

            for attempt in range(MAX_RETRIES):
                try:
                    client = _get_openai_client()
                    kwargs: dict = {
                        "model": cast(Any, model),
                        "messages": cast(Any, prepared_messages),
                        "temperature": temperature,
                        "max_completion_tokens": max_completion_tokens,
                        "parallel_tool_calls": False,
                    }
                    if not _using_nvidia_mainline():
                        kwargs["reasoning_effort"] = cast(Any, settings.openai_reasoning_effort)
                    if tools:
                        kwargs["tools"] = tools
                        kwargs["tool_choice"] = "auto"
                    if response_format:
                        kwargs["response_format"] = response_format

                    response = await client.chat.completions.create(**kwargs)
                    message = response.choices[0].message
                    tool_calls = _message_to_tool_calls(message)
                    content = _sanitize_primary_content(message.content)
                    if not tool_calls:
                        # Recover a tool call the model printed as text instead of
                        # returning structurally (else it leaks raw JSON to the user).
                        recovered, content = _recover_text_tool_calls(content)
                        if recovered:
                            tool_calls = recovered
                    prompt_tokens, completion_tokens = _log_usage(
                        "nvidia" if _using_nvidia_mainline() else "openai",
                        response.usage,
                    )

                    span.set_outputs(
                        {
                            "has_content": bool(content),
                            "has_tool_calls": bool(tool_calls),
                            "retries": retries_used,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                        }
                    )

                    breaker.record_success()
                    return {
                        "content": content,
                        "tool_calls": tool_calls,
                    }
                except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                    retries_used += 1
                    delay = BASE_DELAY * (2**attempt)
                    logger.warning(
                        "%s transient error %s (attempt %d/%d), retrying in %.1fs",
                        active_provider_name,
                        type(exc).__name__,
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                except Exception as exc:
                    logger.error("%s failed: %s: %s", active_provider_name, type(exc).__name__, exc)
                    breaker.record_failure()
                    span.set_outputs(
                        {"error": f"{type(exc).__name__}: {exc}", "retries": retries_used}
                    )
                    return None

            breaker.record_failure()
            span.set_outputs({"error": "retry_exhausted", "retries": retries_used})
            return None

    primary_model = _get_openai_model()
    primary_result = await _call_model(primary_model, provider_name)
    if primary_result and (primary_result.get("content") or primary_result.get("tool_calls")):
        return primary_result

    if _using_nvidia_mainline() and settings.nvidia_fallback_model:
        fallback_model = settings.nvidia_fallback_model
        if fallback_model != primary_model:
            logger.warning(
                "Primary NVIDIA model %s returned no usable response; retrying %s",
                primary_model,
                fallback_model,
            )
            fallback_result = await _call_model(fallback_model, f"NVIDIA/{fallback_model}")
            if fallback_result and (
                fallback_result.get("content") or fallback_result.get("tool_calls")
            ):
                return fallback_result

    return primary_result


async def _call_groq(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    response_format: dict | None = None,
    max_completion_tokens: int = 4000,
    temperature: float = 0.1,
    provider_name: str,
) -> dict | None:
    """Call Chat Completions via Groq's OpenAI-compatible API."""

    if not _get_groq_token():
        return None

    breaker = _get_breaker(provider_name)
    if not breaker.allow_request():
        logger.info("Circuit breaker OPEN for %s — skipping", provider_name)
        return None

    with start_span(
        name=f"llm_provider_{provider_name.lower()}",
        span_type="CHAT_MODEL",
    ) as span:
        model = _get_groq_model()
        span.set_inputs(
            {
                "provider": provider_name,
                "model": model,
                "message_count": len(messages),
            }
        )
        retries_used = 0

        for attempt in range(MAX_RETRIES):
            try:
                client = _get_groq_client()
                kwargs: dict = {
                    "model": cast(Any, model),
                    "messages": cast(Any, messages),
                    "temperature": temperature,
                    "max_completion_tokens": max_completion_tokens,
                    # Avoid OpenAI-only parameters unless we know the upstream supports them.
                    "parallel_tool_calls": False,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                if response_format:
                    kwargs["response_format"] = response_format

                response = await client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                tool_calls = _message_to_tool_calls(message)
                content = message.content or ""
                if not tool_calls:
                    recovered, content = _recover_text_tool_calls(content)
                    if recovered:
                        tool_calls = recovered
                prompt_tokens, completion_tokens = _log_usage("groq", response.usage)

                span.set_outputs(
                    {
                        "has_content": bool(content),
                        "has_tool_calls": bool(tool_calls),
                        "retries": retries_used,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    }
                )

                breaker.record_success()
                return {
                    "content": content,
                    "tool_calls": tool_calls,
                }
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                retries_used += 1
                delay = BASE_DELAY * (2**attempt)
                logger.warning(
                    "%s transient error %s (attempt %d/%d), retrying in %.1fs",
                    provider_name,
                    type(exc).__name__,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
            except Exception as exc:
                logger.error("%s failed: %s: %s", provider_name, type(exc).__name__, exc)
                breaker.record_failure()
                span.set_outputs({"error": f"{type(exc).__name__}: {exc}", "retries": retries_used})
                return None

        breaker.record_failure()
        span.set_outputs({"error": "retry_exhausted", "retries": retries_used})
        return None


async def _call_openrouter(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    response_format: dict | None = None,
    max_completion_tokens: int = 4000,
    temperature: float = 0.1,
    provider_name: str,
) -> dict | None:
    """Backward-compatible fallback hook name.

    Earlier tests and deployments referred to the non-mainline fallback as
    OpenRouter.  The runtime now routes that fallback through the Groq
    OpenAI-compatible client, but keeping this seam stable lets tests and
    integrations patch the fallback without depending on the provider rename.
    """

    return await _call_groq(
        messages,
        tools=tools,
        response_format=response_format,
        max_completion_tokens=max_completion_tokens,
        temperature=temperature,
        provider_name=provider_name,
    )


async def _call_llm_with_fallback(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    response_format: dict | None = None,
    max_completion_tokens: int = 4000,
    temperature: float = 0.1,
    openai_provider_name: str,
    groq_provider_name: str,
) -> dict | None:
    """Try the primary provider first; fall back to Groq when the primary response is unusable."""

    result = await _call_openai(
        messages,
        tools=tools,
        response_format=response_format,
        max_completion_tokens=max_completion_tokens,
        temperature=temperature,
        provider_name=openai_provider_name,
    )
    if _usable_response(result):
        return result

    return await _call_openrouter(
        messages,
        tools=tools,
        response_format=response_format,
        max_completion_tokens=max_completion_tokens,
        temperature=temperature,
        provider_name=groq_provider_name,
    )


# ---------------------------------------------------------------------------
# Agentic mode: call_llm() — returns tool_calls for the agent loop
# ---------------------------------------------------------------------------


@trace(name="call_llm", span_type="CHAT_MODEL")
async def call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict | None:
    """Call the LLM with tool definitions and return the response."""
    clean_messages = _clean_messages_for_api(messages)
    return await _call_llm_with_fallback(
        clean_messages,
        tools=tools,
        max_completion_tokens=4000,
        temperature=0.1,
        openai_provider_name=f"{'NVIDIA' if _using_nvidia_mainline() else 'OpenAI'}/{_get_openai_model()}",
        groq_provider_name=f"Groq/{_get_groq_model()}",
    )


async def call_llm_stream(messages: list[dict]):
    """Stream LLM response tokens for conversational chat."""
    clean_messages = _prepare_primary_messages(_clean_messages_for_api(messages))

    async def _stream_with_client(client: AsyncOpenAI, *, model: str) -> Any:
        stream = await client.chat.completions.create(
            model=cast(Any, model),
            messages=cast(Any, clean_messages),
            temperature=0.3,
            max_completion_tokens=2000,
            stream=True,
        )
        async for chunk in stream:
            for choice in chunk.choices:
                delta = choice.delta.content
                if not delta:
                    continue
                if isinstance(delta, str):
                    yield delta
                    continue
                for part in delta:
                    text = getattr(part, "text", None)
                    if text:
                        yield text

    # Primary: OpenAI
    if _has_openai_credentials():
        provider_name = (
            f"{'NVIDIA' if _using_nvidia_mainline() else 'OpenAI'}/{_get_openai_model()}"
        )
        breaker = _get_breaker(provider_name)
        if breaker.allow_request():
            try:
                client = _get_openai_client()
                kwargs: dict[str, Any] = {
                    "model": cast(Any, _get_openai_model()),
                    "messages": cast(Any, clean_messages),
                    "temperature": 0.3,
                    "max_completion_tokens": 2000,
                    "stream": True,
                }
                if not _using_nvidia_mainline():
                    kwargs["reasoning_effort"] = cast(Any, settings.openai_reasoning_effort)
                stream = await client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    for choice in chunk.choices:
                        delta = choice.delta.content
                        if not delta:
                            continue
                        if isinstance(delta, str):
                            yield delta
                            continue
                        for part in delta:
                            text = getattr(part, "text", None)
                            if text:
                                yield text
                breaker.record_success()
                return
            except Exception as exc:
                breaker.record_failure()
                logger.error("OpenAI streaming failed: %s: %s", type(exc).__name__, exc)
        else:
            logger.error("Circuit breaker OPEN for %s — skipping stream", provider_name)

    # Fallback: Groq
    if not _get_groq_token():
        logger.error("LLM streaming requested with no configured credentials")
        return

    provider_name = f"Groq/{_get_groq_model()}"
    breaker = _get_breaker(provider_name)
    if not breaker.allow_request():
        logger.error("Circuit breaker OPEN for %s — skipping stream", provider_name)
        return

    try:
        client = _get_groq_client()
        async for text in _stream_with_client(client, model=_get_groq_model()):
            yield text
        breaker.record_success()
    except Exception as exc:
        breaker.record_failure()
        logger.error("Groq streaming failed: %s: %s", type(exc).__name__, exc)


def _clean_messages_for_api(messages: list[dict]) -> list[dict]:
    """Clean messages to be valid for OpenAI-compatible APIs."""
    cleaned = []
    for msg in messages:
        clean = {"role": msg["role"]}

        content = msg.get("content")
        if content is not None:
            clean["content"] = content
        elif msg["role"] == "assistant":
            clean["content"] = ""

        if msg.get("tool_calls"):
            clean["tool_calls"] = msg["tool_calls"]

        if msg["role"] == "tool":
            clean["tool_call_id"] = msg.get("tool_call_id", "")
            if "content" not in clean:
                clean["content"] = ""

        cleaned.append(clean)
    return cleaned


# ---------------------------------------------------------------------------
# Direct mode: analyze_zoning() — one-shot JSON extraction (legacy)
# ---------------------------------------------------------------------------

DIRECT_SYSTEM_PROMPT = """\
You are a zoning analyst. You extract structured zoning information from retrieved municipal \
ordinance text for any US municipality.

GROUNDING RULE: Every value you extract MUST be explicitly stated in the retrieved chunks. \
If a value is not found in the text, use empty string "" or empty array []. \
Do NOT use your training knowledge to fill gaps — wrong numbers cause real financial harm. \
Null/empty is always correct when the text does not state the value.

Given the zoning ordinance chunks retrieved for a municipality, extract and return a JSON object \
with the following fields. Use empty string "" for fields you cannot determine from the provided text. \
Use empty arrays [] for list fields you cannot determine.

Return ONLY valid JSON, no markdown fences, no explanation.

{
  "zoning_district": "The zoning district code (e.g. RS-4, T6-8, B-2)",
  "zoning_description": "Full name of the zoning district",
  "allowed_uses": ["List of permitted/allowed uses"],
  "conditional_uses": ["List of conditional/special exception uses"],
  "prohibited_uses": ["List of explicitly prohibited uses"],
  "setbacks": {
    "front": "Front setback requirement",
    "side": "Side setback requirement",
    "rear": "Rear setback requirement"
  },
  "max_height": "Maximum building height",
  "max_density": "Maximum density (units per acre)",
  "floor_area_ratio": "Maximum FAR",
  "lot_coverage": "Maximum lot coverage percentage",
  "min_lot_size": "Minimum lot size",
  "parking_requirements": "Parking requirements summary",
  "summary": "2-3 sentence plain-English summary of what can be built at this address",
  "confidence": "high, medium, or low — based on how much relevant data was found"
}\
"""


def _build_user_prompt(
    address: str,
    municipality: str,
    county: str,
    results: list[SearchResult],
) -> str:
    """Build the user prompt with address context and retrieved zoning chunks."""
    chunks_text = ""
    for i, r in enumerate(results, 1):
        chunks_text += f"\n--- Chunk {i}: {r.section} — {r.section_title} ---\n"
        if r.zone_codes:
            chunks_text += f"Zone codes mentioned: {', '.join(r.zone_codes)}\n"
        chunks_text += f"{r.chunk_text}\n"

    return (
        f"Property address: {address}\n"
        f"Municipality: {municipality}\n"
        f"County: {county}\n\n"
        f"Below are the relevant zoning ordinance sections retrieved for this municipality. "
        f"Analyze them and extract the structured zoning information.\n"
        f"{chunks_text}"
    )


def _parse_llm_content(content: str) -> dict:
    """Parse LLM response content, stripping markdown fences if present."""
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return json.loads(content.strip())  # type: ignore[no-any-return]


async def analyze_zoning(
    address: str,
    municipality: str,
    county: str,
    results: list[SearchResult],
) -> dict:
    """One-shot zoning analysis (non-agentic)."""
    if not results:
        logger.warning("No search results to analyze")
        return {}

    messages = [
        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(address, municipality, county, results)},
    ]

    result = await _call_llm_with_fallback(
        messages,
        response_format={"type": "json_object"},
        max_completion_tokens=2000,
        temperature=0.1,
        openai_provider_name=f"{'NVIDIA' if _using_nvidia_mainline() else 'OpenAI'}/{_get_openai_model()}",
        groq_provider_name=f"Groq/{_get_groq_model()}",
    )
    if not result or not result.get("content"):
        logger.error("LLM failed for analyze_zoning (primary provider + fallback)")
        return {}

    try:
        return _parse_llm_content(result["content"])
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse OpenAI response: %s", exc)
        return {}


def llm_response_to_report(
    raw: dict,
    address: str,
    formatted_address: str,
    municipality: str,
    county: str,
    lat: float | None,
    lng: float | None,
    sources: list[str],
) -> ZoningReport:
    """Convert raw LLM JSON response into a ZoningReport."""
    setbacks_raw = raw.get("setbacks", {})

    return ZoningReport(
        address=address,
        formatted_address=formatted_address,
        municipality=municipality,
        county=county,
        lat=lat,
        lng=lng,
        zoning_district=raw.get("zoning_district", ""),
        zoning_description=raw.get("zoning_description", ""),
        allowed_uses=raw.get("allowed_uses", []),
        conditional_uses=raw.get("conditional_uses", []),
        prohibited_uses=raw.get("prohibited_uses", []),
        setbacks=Setbacks(
            front=setbacks_raw.get("front", ""),
            side=setbacks_raw.get("side", ""),
            rear=setbacks_raw.get("rear", ""),
        ),
        max_height=raw.get("max_height", ""),
        max_density=raw.get("max_density", ""),
        floor_area_ratio=raw.get("floor_area_ratio", ""),
        lot_coverage=raw.get("lot_coverage", ""),
        min_lot_size=raw.get("min_lot_size", ""),
        parking_requirements=raw.get("parking_requirements", ""),
        summary=raw.get("summary", ""),
        sources=sources,
        confidence=raw.get("confidence", "low"),
    )
