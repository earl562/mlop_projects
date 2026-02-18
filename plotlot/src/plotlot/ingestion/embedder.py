"""Embedding generation via NVIDIA NIM API.

Uses nvidia/nv-embedqa-e5-v5 (1024d) for zoning text embeddings.
OpenAI-compatible API with passage/query input type distinction.
Includes exponential backoff for resilience against rate limits.
"""

import asyncio
import logging

import httpx
import mlflow
from mlflow.entities import SpanType

from plotlot.config import settings

logger = logging.getLogger(__name__)

MODEL_ID = "nvidia/nv-embedqa-e5-v5"
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/embeddings"
EMBEDDING_DIM = 1024
BATCH_SIZE = 32
MAX_RETRIES = 3
BASE_DELAY = 2.0  # seconds


async def _embed_batch(
    client: httpx.AsyncClient,
    batch: list[str],
    headers: dict,
    input_type: str,
) -> list[list[float]]:
    """Embed a single batch with exponential backoff."""
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
            return [item["embedding"] for item in data["data"]]

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 or e.response.status_code >= 500:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Embedding API %d (attempt %d/%d), retrying in %.1fs",
                    e.response.status_code, attempt + 1, MAX_RETRIES, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise
        except httpx.TimeoutException:
            delay = BASE_DELAY * (2 ** attempt)
            logger.warning(
                "Embedding API timeout (attempt %d/%d), retrying in %.1fs",
                attempt + 1, MAX_RETRIES, delay,
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
    resp.raise_for_status()
    data = resp.json()
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

    async with httpx.AsyncClient(timeout=60.0) as client:
        for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE)):
            batch = texts[i : i + BATCH_SIZE]
            batch = [t[:2000] for t in batch]

            with mlflow.start_span(
                name=f"embed_batch_{batch_idx}", span_type=SpanType.EMBEDDING,
            ) as span:
                span.set_inputs({"batch_size": len(batch), "input_type": input_type})
                batch_embeddings = await _embed_batch(client, batch, headers, input_type)
                all_embeddings.extend(batch_embeddings)
                span.set_outputs({"embedding_dim": len(batch_embeddings[0]) if batch_embeddings else 0})
            logger.debug(
                "Embedded batch %d-%d (%dd)", i, i + len(batch), EMBEDDING_DIM,
            )

    return all_embeddings
