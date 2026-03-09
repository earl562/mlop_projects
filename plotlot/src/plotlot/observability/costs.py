"""Token cost tracking for LLM queries.

Tracks prompt/completion tokens and estimated costs per model.
Logs to MLflow metrics for dashboard visibility.

Production relevance: GetOnStack's costs went from $127/week to $47K/month
without cost tracking. Every production LLM system needs per-query cost
visibility. This module provides:
  1. Per-model cost estimation (cost per 1M tokens)
  2. MLflow metric logging for cost dashboards
  3. A single function to call from the pipeline after each LLM invocation
"""

import logging

from plotlot.observability.tracing import log_metrics as _log_metrics

logger = logging.getLogger(__name__)

# Cost per 1M tokens (approximate, as of 2025).
# Sources: NVIDIA NIM pricing, Moonshot AI pricing.
MODEL_COSTS: dict[str, dict[str, float]] = {
    "meta/llama-3.3-70b-instruct": {"prompt": 0.40, "completion": 0.40},
    "kimi-k2.5": {"prompt": 0.50, "completion": 0.50},
    "nvidia/nv-embedqa-e5-v5": {"prompt": 0.01, "completion": 0.0},
}

# Fallback cost for unknown models — conservative estimate
_DEFAULT_COST = {"prompt": 1.0, "completion": 1.0}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for a single LLM call.

    Args:
        model: Model identifier matching a key in MODEL_COSTS.
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.

    Returns:
        Estimated cost in USD.
    """
    costs = MODEL_COSTS.get(model, _DEFAULT_COST)
    return (prompt_tokens * costs["prompt"] + completion_tokens * costs["completion"]) / 1_000_000


def log_query_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Log token usage and cost to MLflow.

    Logs prompt_tokens, completion_tokens, total_tokens, and estimated_cost_usd
    as MLflow metrics within the active run. Safe to call outside an MLflow run
    (metrics are silently dropped via the tracing module's no-op behavior).

    Args:
        model: Model identifier matching a key in MODEL_COSTS.
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.

    Returns:
        Estimated cost in USD.
    """
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    try:
        _log_metrics({
            "prompt_tokens": float(prompt_tokens),
            "completion_tokens": float(completion_tokens),
            "total_tokens": float(prompt_tokens + completion_tokens),
            "estimated_cost_usd": cost,
        })
    except Exception:
        logger.debug("Failed to log cost metrics to MLflow", exc_info=True)
    return cost
