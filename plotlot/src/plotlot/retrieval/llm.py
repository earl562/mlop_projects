"""LLM client — NVIDIA NIM primary, OpenRouter fallback.

Supports three modes:
  1. Agentic tool-use: call_llm() returns tool_calls for the agent loop
  2. Direct analysis: analyze_zoning() for non-agentic one-shot analysis
  3. Streaming chat: call_llm_stream() yields tokens for conversational UI

Both APIs are OpenAI-compatible chat completions endpoints.
NVIDIA NIM (Kimi K2.5) is the default. Google Gemini is fallback.
"""

import asyncio
import json
import logging

import httpx

# Granular timeouts: fail fast on connect, generous on read (LLM generation)
LLM_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)

from plotlot.config import settings
from plotlot.observability.tracing import start_span, trace
from plotlot.core.types import SearchResult, Setbacks, ZoningReport

logger = logging.getLogger(__name__)

# Provider configs
NVIDIA_CHAT_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = "moonshotai/kimi-k2.5"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODEL = "gemini-2.5-flash"

MAX_RETRIES = 2
BASE_DELAY = 1.0


# ---------------------------------------------------------------------------
# Core provider call (shared by agentic and direct modes)
# ---------------------------------------------------------------------------

async def _call_provider_raw(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    payload: dict,
    provider_name: str,
) -> dict | None:
    """Call a provider and return the raw message dict (content + tool_calls)."""
    with start_span(
        name=f"llm_provider_{provider_name.lower()}", span_type="CHAT_MODEL",
    ) as span:
        span.set_inputs({
            "provider": provider_name,
            "model": payload.get("model", ""),
            "message_count": len(payload.get("messages", [])),
        })
        retries_used = 0

        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                logger.info("LLM response from %s (model=%s)", provider_name, payload.get("model"))
                span.set_outputs({
                    "has_content": bool(message.get("content")),
                    "has_tool_calls": bool(message.get("tool_calls")),
                    "retries": retries_used,
                })
                return message

            except httpx.HTTPStatusError as e:
                retries_used += 1
                if e.response.status_code == 429 or e.response.status_code >= 500:
                    delay = BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "%s %d (attempt %d/%d), retrying in %.1fs",
                        provider_name, e.response.status_code,
                        attempt + 1, MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "%s error %d: %s",
                        provider_name, e.response.status_code,
                        e.response.text[:200] if hasattr(e.response, 'text') else str(e),
                    )
                    span.set_outputs({"error": f"http_{e.response.status_code}", "retries": retries_used})
                    return None
            except (KeyError, IndexError) as e:
                logger.error("Unexpected %s response structure: %s", provider_name, e)
                span.set_outputs({"error": f"parse_error: {e}", "retries": retries_used})
                return None
            except httpx.TimeoutException:
                retries_used += 1
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "%s timeout (attempt %d/%d), retrying in %.1fs",
                    provider_name, attempt + 1, MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)

        # Final attempt
        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            span.set_outputs({
                "has_content": bool(message.get("content")),
                "has_tool_calls": bool(message.get("tool_calls")),
                "retries": retries_used,
            })
            return message
        except Exception as e:
            logger.error("%s failed after all retries: %s", provider_name, e)
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

    Used by the agentic pipeline. The response may contain tool_calls
    that the agent loop needs to execute.

    Returns:
        Dict with 'content' (str) and 'tool_calls' (list), or None on failure.
    """
    # Clean messages for API — remove None content, ensure proper format
    clean_messages = _clean_messages_for_api(messages)

    payload: dict = {
        "messages": clean_messages,
        "temperature": 0.1,
        "max_tokens": 4000,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        # Primary: NVIDIA NIM
        if settings.nvidia_api_key:
            nvidia_headers = {
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
            }
            nvidia_payload = {**payload, "model": NVIDIA_MODEL}
            message = await _call_provider_raw(
                client, NVIDIA_CHAT_URL, nvidia_headers, nvidia_payload, "NVIDIA",
            )
            if message:
                return {
                    "content": message.get("content") or "",
                    "tool_calls": message.get("tool_calls") or [],
                }
            logger.warning("NVIDIA NIM failed, falling back to Gemini")

        # Fallback: Google Gemini (free tier, OpenAI-compatible)
        if settings.gemini_api_key:
            gemini_headers = {
                "Authorization": f"Bearer {settings.gemini_api_key}",
                "Content-Type": "application/json",
            }
            gemini_payload = {**payload, "model": GEMINI_MODEL}
            message = await _call_provider_raw(
                client, GEMINI_URL, gemini_headers, gemini_payload, "Gemini",
            )
            if message:
                return {
                    "content": message.get("content") or "",
                    "tool_calls": message.get("tool_calls") or [],
                }

    logger.error("All LLM providers failed")
    return None


async def call_llm_stream(messages: list[dict]):
    """Stream LLM response tokens for conversational chat.

    Yields string chunks as they arrive from the provider.
    Uses the same NVIDIA primary / OpenRouter fallback pattern.
    """
    clean_messages = _clean_messages_for_api(messages)
    payload = {
        "messages": clean_messages,
        "temperature": 0.3,
        "max_tokens": 2000,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        # Primary: NVIDIA NIM
        if settings.nvidia_api_key:
            headers = {
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
            }
            try:
                async for chunk in _stream_provider(
                    client, NVIDIA_CHAT_URL, headers,
                    {**payload, "model": NVIDIA_MODEL}, "NVIDIA",
                ):
                    yield chunk
                return
            except Exception as e:
                logger.warning("NVIDIA streaming failed: %s, falling back", e)

        # Fallback: Google Gemini
        if settings.gemini_api_key:
            headers = {
                "Authorization": f"Bearer {settings.gemini_api_key}",
                "Content-Type": "application/json",
            }
            try:
                async for chunk in _stream_provider(
                    client, GEMINI_URL, headers,
                    {**payload, "model": GEMINI_MODEL}, "Gemini",
                ):
                    yield chunk
                return
            except Exception as e:
                logger.error("Gemini streaming failed: %s", e)

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
    return json.loads(content.strip())


async def analyze_zoning(
    address: str,
    municipality: str,
    county: str,
    results: list[SearchResult],
) -> dict:
    """One-shot zoning analysis (non-agentic). NVIDIA primary, OpenRouter fallback."""
    if not results:
        logger.warning("No search results to analyze")
        return {}

    messages = [
        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(address, municipality, county, results)},
    ]

    payload_base: dict = {
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        # Primary: NVIDIA NIM
        if settings.nvidia_api_key:
            nvidia_headers = {
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Content-Type": "application/json",
            }
            message = await _call_provider_raw(
                client, NVIDIA_CHAT_URL, nvidia_headers,
                {**payload_base, "model": NVIDIA_MODEL}, "NVIDIA",
            )
            if message and message.get("content"):
                try:
                    return _parse_llm_content(message["content"])
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse NVIDIA response: %s", e)

        # Fallback: Google Gemini
        if settings.gemini_api_key:
            gemini_headers = {
                "Authorization": f"Bearer {settings.gemini_api_key}",
                "Content-Type": "application/json",
            }
            message = await _call_provider_raw(
                client, GEMINI_URL, gemini_headers,
                {**payload_base, "model": GEMINI_MODEL}, "Gemini",
            )
            if message and message.get("content"):
                try:
                    return _parse_llm_content(message["content"])
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse Gemini response: %s", e)

    logger.error("All LLM providers failed")
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
