"""Embedding generation via HuggingFace Inference API.

Uses BAAI/bge-base-en-v1.5 (768d) for zoning text embeddings.
Batches requests to stay within API limits.
"""

import logging

import httpx

from plotlot.config import settings

logger = logging.getLogger(__name__)

MODEL_ID = "BAAI/bge-base-en-v1.5"
HF_API_URL = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{MODEL_ID}"
BATCH_SIZE = 32


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts via HuggingFace Inference API.

    Returns:
        List of embedding vectors (768d each).
    """
    if not texts:
        return []

    headers = {"Authorization": f"Bearer {settings.hf_token}"}
    all_embeddings: list[list[float]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            resp = await client.post(
                HF_API_URL,
                json={"inputs": batch, "options": {"wait_for_model": True}},
                headers=headers,
            )
            resp.raise_for_status()
            embeddings = resp.json()
            all_embeddings.extend(embeddings)
            logger.debug("Embedded batch %d-%d", i, i + len(batch))

    return all_embeddings
