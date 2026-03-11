"""LLM client — three-provider fallback chain.

Supports three modes:
  1. Agentic tool-use: call_llm() returns tool_calls for the agent loop
  2. Direct analysis: analyze_zoning() for non-agentic one-shot analysis
  3. Streaming chat: call_llm_stream() yields tokens for conversational UI

Provider chain (Stripe "contain, verify, restrict" pattern):
  1. Claude Sonnet 4.6 (primary — best tool use, Anthropic Max plan)
  2. Google Gemini 2.5 Flash (secondary — fast, OpenAI-compatible endpoint)
  3. NVIDIA NIM (tertiary — existing Llama/Kimi chain)

Per-provider circuit breakers prevent wasting retries on failing providers.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from plotlot.config import settings
from plotlot.core.types import SearchResult, Setbacks, ZoningReport
from plotlot.observability.tracing import log_metrics, start_span, trace

# Granular timeouts: fail fast on connect, generous on read (LLM generation)
LLM_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)

logger = logging.getLogger(__name__)

# Provider configs
NVIDIA_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODELS = [
    "meta/llama-3.3-70b-instruct",  # Fast, reliable tool use
    "moonshotai/kimi-k2.5",  # Strong reasoning, sometimes slow
]
NVIDIA_MODEL = NVIDIA_MODELS[0]  # Default primary

GEMINI_CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODELS = ["gemini-2.5-flash"]

CLAUDE_MODEL = "claude-sonnet-4-6"

MAX_RETRIES = 2
BASE_DELAY = 1.0


# ---------------------------------------------------------------------------
# Circuit Breaker — Stripe "contain, verify, restrict" pattern
# Prevents wasting retries on a provider that's already failing.
# States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)
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
        """Check if a request should be allowed through."""
        current = self.state
        if current == "closed":
            return True
        if current == "half_open":
            return True  # Allow one test request
        return False  # open — skip this provider

    def record_success(self) -> None:
        """Record a successful call — reset to closed."""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Record a failed call — may trip to open."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                "Circuit breaker OPEN after %d failures (reset in %ds)",
                self._failure_count,
                self.reset_seconds,
            )


# Per-provider circuit breakers (module-level singletons)
_breakers: dict[str, CircuitBreaker] = {
    "Claude": CircuitBreaker(),
    "Gemini/gemini-2.5-flash": CircuitBreaker(),
    "NVIDIA/llama-3.3-70b-instruct": CircuitBreaker(),
    "NVIDIA/kimi-k2.5": CircuitBreaker(),
}


# ---------------------------------------------------------------------------
# Tool format conversion — Claude ↔ OpenAI
# ---------------------------------------------------------------------------


def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool definitions to Anthropic tool format.

    OpenAI: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    Anthropic: {"name": ..., "description": ..., "input_schema": ...}
    """
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
    """Convert Claude's tool_use content blocks to OpenAI-format tool_calls.

    Claude: {"type": "tool_use", "id": ..., "name": ..., "input": {...}}
    OpenAI: {"id": ..., "type": "function", "function": {"name": ..., "arguments": "..."}}
    """
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
    """Convert OpenAI-format messages to Anthropic format.

    Returns (system_prompt, messages) — Claude requires system as a separate param.
    Also converts tool result messages to Anthropic format.
    """
    system_prompt = ""
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            system_prompt = msg.get("content", "")
            continue

        if role == "tool":
            # Anthropic uses role="user" with tool_result content blocks
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

            # Convert tool_calls to tool_use blocks
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

        # user messages
        anthropic_messages.append(
            {
                "role": "user",
                "content": msg.get("content", ""),
            }
        )

    return system_prompt, anthropic_messages


# ---------------------------------------------------------------------------
# Claude provider (primary)
# ---------------------------------------------------------------------------


async def _call_claude(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict | None:
    """Call Claude Sonnet 4.6 via the Anthropic SDK.

    Returns same interface as _call_provider_raw:
        {"content": str, "tool_calls": list} or None on failure.
    """
    if not settings.anthropic_api_key:
        return None

    breaker = _breakers.get("Claude")
    if breaker and not breaker.allow_request():
        logger.info("Circuit breaker OPEN for Claude — skipping")
        return None

    with start_span(name="llm_provider_claude", span_type="CHAT_MODEL") as span:
        span.set_inputs(
            {
                "provider": "Claude",
                "model": CLAUDE_MODEL,
                "message_count": len(messages),
            }
        )

        try:
            import anthropic

            client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                timeout=60.0,
            )

            system_prompt, anthropic_messages = _convert_messages_for_anthropic(messages)

            kwargs: dict = {
                "model": CLAUDE_MODEL,
                "max_tokens": 4000,
                "messages": anthropic_messages,
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            if tools:
                kwargs["tools"] = _convert_tools_to_anthropic(tools)
                kwargs["tool_choice"] = {"type": "auto"}

            response = await client.messages.create(**kwargs)

            # Extract text content
            text_content = ""
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    text_content = block.text

            # Extract tool calls
            tool_calls = _convert_tool_calls_from_anthropic(response.content)

            # Log token usage
            usage = response.usage
            prompt_tokens = usage.input_tokens if usage else 0
            completion_tokens = usage.output_tokens if usage else 0

            span.set_outputs(
                {
                    "has_content": bool(text_content),
                    "has_tool_calls": bool(tool_calls),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            )
            if prompt_tokens or completion_tokens:
                log_metrics(
                    {
                        "claude_prompt_tokens": float(prompt_tokens),
                        "claude_completion_tokens": float(completion_tokens),
                        "claude_total_tokens": float(prompt_tokens + completion_tokens),
                    }
                )

            if breaker:
                breaker.record_success()

            logger.info(
                "Claude response: text=%d chars, tool_calls=%d",
                len(text_content),
                len(tool_calls),
            )

            return {
                "content": text_content,
                "tool_calls": tool_calls,
            }

        except Exception as e:
            logger.error("Claude failed: %s: %s", type(e).__name__, e)
            if breaker:
                breaker.record_failure()
            span.set_outputs({"error": f"{type(e).__name__}: {e}"})
            return None


async def _stream_claude(messages: list[dict]):
    """Stream tokens from Claude for conversational chat."""
    if not settings.anthropic_api_key:
        raise RuntimeError("No Anthropic API key")

    breaker = _breakers.get("Claude")
    if breaker and not breaker.allow_request():
        raise RuntimeError("Claude circuit breaker OPEN")

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=60.0,
        )

        system_prompt, anthropic_messages = _convert_messages_for_anthropic(messages)

        kwargs: dict = {
            "model": CLAUDE_MODEL,
            "max_tokens": 2000,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

        if breaker:
            breaker.record_success()

    except Exception as e:
        logger.warning("Claude streaming failed: %s", e)
        if breaker:
            breaker.record_failure()
        raise


# ---------------------------------------------------------------------------
# Core provider call (shared by Gemini and NVIDIA — OpenAI-compatible)
# ---------------------------------------------------------------------------


async def _call_provider_raw(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    payload: dict,
    provider_name: str,
) -> dict | None:
    """Call a provider and return the raw message dict (content + tool_calls).

    Integrates circuit breaker (skip providers that are failing) and
    token usage extraction (log to MLflow for cost tracking).
    """
    # Auto-create breakers for new provider/model combos
    if provider_name not in _breakers:
        _breakers[provider_name] = CircuitBreaker()
    breaker = _breakers[provider_name]
    if not breaker.allow_request():
        logger.info("Circuit breaker OPEN for %s — skipping", provider_name)
        return None

    with start_span(
        name=f"llm_provider_{provider_name.lower()}",
        span_type="CHAT_MODEL",
    ) as span:
        span.set_inputs(
            {
                "provider": provider_name,
                "model": payload.get("model", ""),
                "message_count": len(payload.get("messages", [])),
            }
        )
        retries_used = 0

        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]

                # --- Kimi K2.5 fix: content may be null with reasoning in separate field ---
                if not message.get("content"):
                    # Check reasoning_content (Kimi K2.5) or reasoning (other models)
                    reasoning = message.get("reasoning_content") or message.get("reasoning")
                    if reasoning:
                        message["content"] = reasoning
                        logger.info(
                            "%s: used reasoning_content field (content was null)",
                            provider_name,
                        )

                logger.info("LLM response from %s (model=%s)", provider_name, payload.get("model"))

                # Extract token usage for cost tracking
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                span.set_outputs(
                    {
                        "has_content": bool(message.get("content")),
                        "has_tool_calls": bool(message.get("tool_calls")),
                        "retries": retries_used,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    }
                )
                if prompt_tokens or completion_tokens:
                    log_metrics(
                        {
                            f"{provider_name.lower()}_prompt_tokens": float(prompt_tokens),
                            f"{provider_name.lower()}_completion_tokens": float(completion_tokens),
                            f"{provider_name.lower()}_total_tokens": float(
                                prompt_tokens + completion_tokens
                            ),
                        }
                    )

                if breaker:
                    breaker.record_success()
                return message  # type: ignore[no-any-return]

            except httpx.HTTPStatusError as e:
                retries_used += 1
                if e.response.status_code == 429 or e.response.status_code >= 500:
                    delay = BASE_DELAY * (2**attempt)
                    logger.warning(
                        "%s %d (attempt %d/%d), retrying in %.1fs",
                        provider_name,
                        e.response.status_code,
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "%s error %d: %s",
                        provider_name,
                        e.response.status_code,
                        e.response.text[:200] if hasattr(e.response, "text") else str(e),
                    )
                    if breaker:
                        breaker.record_failure()
                    span.set_outputs(
                        {"error": f"http_{e.response.status_code}", "retries": retries_used}
                    )
                    return None
            except (KeyError, IndexError) as e:
                logger.error("Unexpected %s response structure: %s", provider_name, e)
                if breaker:
                    breaker.record_failure()
                span.set_outputs({"error": f"parse_error: {e}", "retries": retries_used})
                return None
            except httpx.TimeoutException:
                retries_used += 1
                delay = BASE_DELAY * (2**attempt)
                logger.warning(
                    "%s timeout (attempt %d/%d), retrying in %.1fs",
                    provider_name,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)

        # Final attempt
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]

            # Kimi fix on final attempt too
            if not message.get("content"):
                reasoning = message.get("reasoning_content") or message.get("reasoning")
                if reasoning:
                    message["content"] = reasoning

            usage = data.get("usage", {})
            span.set_outputs(
                {
                    "has_content": bool(message.get("content")),
                    "has_tool_calls": bool(message.get("tool_calls")),
                    "retries": retries_used,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                }
            )
            if breaker:
                breaker.record_success()
            return message  # type: ignore[no-any-return]
        except Exception as e:
            logger.error("%s failed after all retries: %s", provider_name, e)
            if breaker:
                breaker.record_failure()
            span.set_outputs({"error": str(e), "retries": retries_used})
            return None


# ---------------------------------------------------------------------------
# Agentic mode: call_llm() — returns tool_calls for the agent loop
# ---------------------------------------------------------------------------


@trace(name="call_llm", span_type="CHAT_MODEL")
async def call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
) -> dict | None:
    """Call the LLM with tool definitions and return the response.

    Three-provider fallback chain: Claude → Gemini → NVIDIA NIM.
    Each provider has its own circuit breaker.

    Returns:
        Dict with 'content' (str) and 'tool_calls' (list), or None on failure.
    """
    # Clean messages for API — remove None content, ensure proper format
    clean_messages = _clean_messages_for_api(messages)

    # --- Provider 1: Claude Sonnet 4.6 (primary) ---
    result = await _call_claude(clean_messages, tools=tools)
    if result:
        return result
    logger.warning("Claude failed, trying Gemini")

    # --- Provider 2: Gemini (secondary — OpenAI-compatible) ---
    payload: dict = {
        "messages": clean_messages,
        "temperature": 0.1,
        "max_tokens": 4000,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        if settings.google_api_key:
            gemini_headers = {
                "Authorization": f"Bearer {settings.google_api_key}",
                "Content-Type": "application/json",
            }
            for model in GEMINI_MODELS:
                gemini_payload = {**payload, "model": model}
                message = await _call_provider_raw(
                    client,
                    GEMINI_CHAT_URL,
                    gemini_headers,
                    gemini_payload,
                    f"Gemini/{model}",
                )
                if message:
                    return {
                        "content": message.get("content") or "",
                        "tool_calls": message.get("tool_calls") or [],
                    }
                logger.warning("Gemini %s failed, trying next", model)
        logger.warning("Gemini failed, trying NVIDIA NIM")

        # --- Provider 3: NVIDIA NIM (tertiary) ---
        if settings.nvidia_api_key:
            nvidia_headers = {
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
            }
            for model in NVIDIA_MODELS:
                nvidia_payload = {**payload, "model": model}
                message = await _call_provider_raw(
                    client,
                    NVIDIA_CHAT_URL,
                    nvidia_headers,
                    nvidia_payload,
                    f"NVIDIA/{model.split('/')[-1]}",
                )
                if message:
                    return {
                        "content": message.get("content") or "",
                        "tool_calls": message.get("tool_calls") or [],
                    }
                logger.warning("NVIDIA %s failed, trying next model", model)

    logger.error("All LLM providers failed (Claude → Gemini → NVIDIA)")
    return None


async def call_llm_stream(messages: list[dict]):
    """Stream LLM response tokens for conversational chat.

    Yields string chunks as they arrive from the provider.
    Three-provider fallback: Claude → Gemini → NVIDIA NIM.
    """
    clean_messages = _clean_messages_for_api(messages)

    # --- Provider 1: Claude streaming ---
    if settings.anthropic_api_key:
        try:
            async for chunk in _stream_claude(clean_messages):
                yield chunk
            return
        except Exception as e:
            logger.warning("Claude streaming failed: %s, trying Gemini", e)

    # --- Provider 2: Gemini streaming ---
    payload = {
        "messages": clean_messages,
        "temperature": 0.3,
        "max_tokens": 2000,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        if settings.google_api_key:
            headers = {
                "Authorization": f"Bearer {settings.google_api_key}",
                "Content-Type": "application/json",
            }
            for model in GEMINI_MODELS:
                try:
                    async for chunk in _stream_provider(
                        client,
                        GEMINI_CHAT_URL,
                        headers,
                        {**payload, "model": model},
                        f"Gemini/{model}",
                    ):
                        yield chunk
                    return
                except Exception as e:
                    logger.warning("Gemini %s streaming failed: %s, trying next", model, e)

        # --- Provider 3: NVIDIA NIM streaming ---
        if settings.nvidia_api_key:
            headers = {
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
            }
            for model in NVIDIA_MODELS:
                try:
                    async for chunk in _stream_provider(
                        client,
                        NVIDIA_CHAT_URL,
                        headers,
                        {**payload, "model": model},
                        f"NVIDIA/{model.split('/')[-1]}",
                    ):
                        yield chunk
                    return
                except Exception as e:
                    logger.warning("NVIDIA %s streaming failed: %s, trying next", model, e)

    logger.error("All LLM providers failed for streaming")


async def _stream_provider(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    payload: dict,
    provider_name: str,
):
    """Stream tokens from an OpenAI-compatible provider."""
    async with client.stream("POST", url, json=payload, headers=headers) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:].strip()
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content")
                if content:
                    yield content
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def _clean_messages_for_api(messages: list[dict]) -> list[dict]:
    """Clean messages to be valid for OpenAI-compatible APIs."""
    cleaned = []
    for msg in messages:
        clean = {"role": msg["role"]}

        # Handle content
        content = msg.get("content")
        if content is not None:
            clean["content"] = content
        elif msg["role"] == "assistant":
            clean["content"] = ""

        # Handle tool_calls on assistant messages
        if msg.get("tool_calls"):
            clean["tool_calls"] = msg["tool_calls"]

        # Handle tool results
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
You are a zoning analysis expert for South Florida real estate. You analyze municipal zoning \
ordinance text and extract structured zoning information for a given property address.

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
    """One-shot zoning analysis (non-agentic).

    Three-provider fallback: Claude → Gemini → NVIDIA NIM.
    """
    if not results:
        logger.warning("No search results to analyze")
        return {}

    messages = [
        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(address, municipality, county, results)},
    ]

    # --- Provider 1: Claude ---
    result = await _call_claude(messages)
    if result and result.get("content"):
        try:
            return _parse_llm_content(result["content"])
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response: %s", e)

    # --- Provider 2: Gemini, Provider 3: NVIDIA ---
    payload_base: dict = {
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        # Gemini
        if settings.google_api_key:
            gemini_headers = {
                "Authorization": f"Bearer {settings.google_api_key}",
                "Content-Type": "application/json",
            }
            for model in GEMINI_MODELS:
                message = await _call_provider_raw(
                    client,
                    GEMINI_CHAT_URL,
                    gemini_headers,
                    {**payload_base, "model": model},
                    f"Gemini/{model}",
                )
                if message and message.get("content"):
                    try:
                        return _parse_llm_content(message["content"])
                    except json.JSONDecodeError as e:
                        logger.error("Failed to parse Gemini %s response: %s", model, e)

        # NVIDIA NIM
        if settings.nvidia_api_key:
            nvidia_headers = {
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
            }
            for model in NVIDIA_MODELS:
                message = await _call_provider_raw(
                    client,
                    NVIDIA_CHAT_URL,
                    nvidia_headers,
                    {**payload_base, "model": model},
                    f"NVIDIA/{model.split('/')[-1]}",
                )
                if message and message.get("content"):
                    try:
                        return _parse_llm_content(message["content"])
                    except json.JSONDecodeError as e:
                        logger.error("Failed to parse NVIDIA %s response: %s", model, e)

    logger.error("All LLM providers failed for analyze_zoning")
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
