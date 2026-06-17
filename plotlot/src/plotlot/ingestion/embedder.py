"""Embedding generation via NVIDIA NIM API.

Uses nvidia/nv-embedqa-e5-v5 (1024d) for zoning text embeddings.
OpenAI-compatible API with passage/query input type distinction.
Includes exponential backoff for resilience against rate limits.
"""

import asyncio
import logging

import httpx

from plotlot.config import settings
from plotlot.core.errors import NvidiaCreditsExhaustedError
from plotlot.observability.tracing import start_span

logger = logging.getLogger(__name__)

MODEL_ID = "nvidia/nv-embedqa-e5-v5"

# Module-level counter — tracks API calls across the current process lifetime.
# Each call to _embed_batch = 1 NVIDIA NIM API credit (32-chunk batch).
_api_calls_this_run: int = 0
_api_calls_lock: asyncio.Lock = asyncio.Lock()


def get_api_calls() -> int:
    """Return the number of NVIDIA embedding API calls made this process."""
    return _api_calls_this_run


def reset_api_calls() -> None:
    """Reset the call counter (useful for testing)."""
    global _api_calls_this_run
    _api_calls_this_run = 0


NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/embeddings"
EMBEDDING_DIM = 1024
BATCH_SIZE = 32
CONCURRENT_BATCHES = 2
MAX_RETRIES = 3
BASE_DELAY = 2.0  # seconds


async def _embed_batch(
    client: httpx.AsyncClient,
    batch: list[str],
    headers: dict,
    input_type: str,
) -> list[list[float]]:
    """Embed a single batch with exponential backoff."""
    global _api_calls_this_run
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post(
                NVIDIA_API_URL,
                json={
                    "input": batch,
                    "model": MODEL_ID,
                    "input_type": input_type,
                    "encoding_format": "float",
                    "truncate": "END",
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            async with _api_calls_lock:
                _api_calls_this_run += 1
            return [item["embedding"] for item in data["data"]]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 402:
                raise NvidiaCreditsExhaustedError() from e
            if e.response.status_code == 429 or e.response.status_code >= 500:
                delay = BASE_DELAY * (2**attempt)
                logger.warning(
                    "Embedding API %d (attempt %d/%d), retrying in %.1fs",
                    e.response.status_code,
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise
        except httpx.TimeoutException:
            delay = BASE_DELAY * (2**attempt)
            logger.warning(
                "Embedding API timeout (attempt %d/%d), retrying in %.1fs",
                attempt + 1,
                MAX_RETRIES,
                delay,
            )
            await asyncio.sleep(delay)

    # Final attempt — let it raise
    resp = await client.post(
        NVIDIA_API_URL,
        json={
            "input": batch,
            "model": MODEL_ID,
            "input_type": input_type,
            "encoding_format": "float",
            "truncate": "END",
        },
        headers=headers,
    )
    if resp.status_code == 402:
        raise NvidiaCreditsExhaustedError()
    resp.raise_for_status()
    data = resp.json()
    _api_calls_this_run += 1
    return [item["embedding"] for item in data["data"]]


async def embed_texts(
    texts: list[str],
    input_type: str = "passage",
) -> list[list[float]]:
    """Generate embeddings via NVIDIA NIM API.

    Args:
        texts: List of text strings to embed.
        input_type: "passage" for documents, "query" for search queries.

    Returns:
        List of embedding vectors (1024d each).
    """
    if not texts:
        return []

    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Content-Type": "application/json",
    }
    all_embeddings: list[list[float]] = []

    semaphore = asyncio.Semaphore(CONCURRENT_BATCHES)

    async def _run_batch(
        batch_idx: int,
        i: int,
    ) -> tuple[int, list[list[float]]]:
        batch = texts[i : i + BATCH_SIZE]
        batch = [t[:2000] for t in batch]

        async with semaphore:
            with start_span(
                name=f"embed_batch_{batch_idx}",
                span_type="EMBEDDING",
            ) as span:
                span.set_inputs({"batch_size": len(batch), "input_type": input_type})
                batch_embeddings = await _embed_batch(client, batch, headers, input_type)
                span.set_outputs(
                    {"embedding_dim": len(batch_embeddings[0]) if batch_embeddings else 0}
                )
            logger.debug(
                "Embedded batch %d-%d (%dd)",
                i,
                i + len(batch),
                EMBEDDING_DIM,
            )
        return batch_idx, batch_embeddings

    async with httpx.AsyncClient(timeout=60.0) as client:
        tasks = [
            _run_batch(batch_idx, i) for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE))
        ]
        results = await asyncio.gather(*tasks)

    # Sort by batch_idx to preserve original text ordering
    results.sort(key=lambda r: r[0])
    for _, batch_embeddings in results:
        all_embeddings.extend(batch_embeddings)

    return all_embeddings
