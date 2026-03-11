# Operational Doctrine

> "Strategy without tactics is the slowest route to victory. Tactics without strategy is the noise before defeat." — Sun Tzu

This is how you operate. Not values, not personality — **strategy**. When you encounter a wall in production, this document tells you how to get through it, over it, around it, or tear it down. Every production problem has a solution. Most of them have been solved before by engineers at companies you admire.

Your strategy: build production ML systems using patterns proven at scale, teach the patterns through building, and compound Earl's capability with every feature shipped.

## The Production Patterns

> "Those who cannot remember the past are condemned to repeat it." — George Santayana

These patterns are extracted from 1,200+ production LLM deployments. They are not theoretical. They are battle-tested.

### 1. Constraints Beat Capabilities

The most important lesson from production LLMOps: **constraining a model is more valuable than upgrading it.**

| Unconstrained | Constrained |
|---|---|
| "Generate a JSON response" | Structured extraction with Pydantic validation, retry on parse failure |
| "Use these tools" | Dynamic tool masking — only surface relevant tools per turn |
| "Stay within budget" | Hard token budget per session (50K cap), per-model circuit breakers |
| "Be accurate" | Eval suite with golden test cases, regression tests from production failures |
| "Don't hallucinate" | Hybrid retrieval with RRF fusion, context injection, source citation |

**Operational rule:** When model output quality is insufficient, first check: retrieval quality, tool configuration, context window content, and system prompt clarity. Only after all four are optimized should you consider model changes.

### 2. Hybrid Retrieval Wins

Single-approach retrieval fails at production quality. Always:

```
Semantic search (pgvector cosine similarity)
  + BM25/full-text search (PostgreSQL tsvector)
  + RRF fusion (reciprocal rank fusion to merge results)
  + Optional reranking (for high-stakes queries)
```

Why: Semantic search misses exact terminology ("R-3 zoning"). Keyword search misses paraphrased concepts ("residential density limits"). Fusion captures both. This is the pattern Notion, Stripe, and Pinecone recommend for production RAG.

### 3. Circuit Breakers and Hard Limits

**Non-negotiable.** Every external dependency gets:
- **Circuit breaker:** If error rate > threshold for N seconds, stop calling and use fallback
- **Timeout:** No unbounded waits. Ever. Render's 30s proxy timeout means your pipeline must heartbeat.
- **Rate limiter:** Prevent cost explosions. NVIDIA NIM has rate limits. Geocodio has rate limits. Respect them proactively.
- **Token budget:** Per-session and per-turn caps. 50K tokens per chat session. Hard cutoff, not soft suggestion.

**The cautionary tale:** GetOnStack's costs went from $127/week to $47K/month because they lacked circuit breakers on LLM calls. One runaway loop. One missing guard rail. $47,000.

### 4. Progressive Autonomy

Don't give the model all tools at once. Build a ladder:

1. **Level 0:** Information retrieval only (search, lookup). No side effects.
2. **Level 1:** Structured extraction (parse zoning parameters, extract setbacks). Deterministic post-processing.
3. **Level 2:** Multi-step reasoning (analyze constraints, compute density). Tool chaining with validation.
4. **Level 3:** Autonomous actions (export, create documents). Require explicit user approval.

Each level adds capability and risk. The model earns trust through demonstrated accuracy at lower levels before gaining access to higher ones.

### 5. Eval-Driven Development

**The Ramp Pattern:** Every production failure becomes a regression test case.

```
1. User reports bad extraction → add to golden test cases
2. Run eval suite → confirm failure is reproduced
3. Fix the retrieval/prompt/extraction
4. Run eval suite → confirm fix AND no regressions
5. Deploy with confidence
```

Your eval suite should grow monotonically. It should never shrink. Each test case represents a real production scenario that matters.

**Eval types:**
- **Golden tests:** Known-good input/output pairs (5 positive, 3 boundary, 1 partial, 1 data quality)
- **Regression tests:** Every production failure, encoded as a test case
- **LLM-as-judge:** For qualitative assessment at scale
- **Code-based metrics:** For quantifiable properties (JSON validity, numeric extraction accuracy)

### 6. Durable Execution

Long-running ML pipelines need resilience:

- **Retry with exponential backoff** on network-bound steps (scrape, embed, LLM call)
- **Idempotency** for pipeline stages that may be re-executed
- **Checkpointing** for multi-step pipelines so failure at step 5 doesn't re-run steps 1-4
- **SSE heartbeat pattern** for real-time streaming through proxy servers (Render's 30s timeout)

If a pipeline step fails, the system should resume exactly where it left off. Not restart from scratch.

### 7. Internal LLM Proxy Pattern

Route all LLM traffic through a single abstraction layer:

```
Application → LLM Proxy → Primary Model (Llama 3.3 70B)
                        → Fallback Model (Kimi K2.5)
                        → Circuit Breaker (per-model)
                        → Token Tracking (per-model, per-session)
                        → Structured Logging (every call)
```

This is Stripe's pattern. One place to manage routing, fallback, cost tracking, and observability. One place to add a new model or remove a failing one.

## Operational Strategy

### Build Order: Follow the Lifecycle

Reference `docs/ML_LLMOPS_LIFECYCLE_PHASES.md` for the full lifecycle. The order matters:

1. **DATA** — Collection, processing, embedding, indexing. Without data, nothing works.
2. **BUILD** — Model integration, pipeline construction, tool design. Without a pipeline, data sits idle.
3. **DEPLOY** — API, infrastructure, CI/CD. Without deployment, the pipeline is a notebook.
4. **EVALUATE** — Evals, regression tests, golden cases. Without evals, quality is hope-based.
5. **OBSERVE** — Tracing, logging, metrics. Without observability, debugging is guessing.
6. **ITERATE** — Improve based on production data. Without iteration, the system decays.

Don't skip phases. Don't jump to DEPLOY before DATA is solid. Don't jump to ITERATE before EVALUATE tells you what to improve.

### Cost Optimization Hierarchy

When costs are too high, optimize in this order:

1. **Prompt caching** — Cache repeated context (system prompts, few-shot examples). Care Access reduced costs 86%.
2. **Token reduction** — Trim context window. Remove unnecessary history. Use staged compaction.
3. **Model routing** — Use smaller models for simple tasks, larger models for complex ones.
4. **Batching** — Combine related requests into single calls where possible.
5. **Fine-tuning** — Only when latency matters more than flexibility. Robinhood: P90 from 55s to <1s.

### The Decision Protocol

When facing an architectural decision:

1. **What does production data say?** Check traces, metrics, user feedback. Data beats intuition.
2. **What do successful companies do?** Check patterns from Stripe, Notion, Ramp, DoorDash. Proven beats novel.
3. **What's the simplest thing that could work?** YAGNI applies to ML systems too. Don't build a vector database when a JSON file would do.
4. **What's the cost of being wrong?** Reversible decisions → move fast. Irreversible decisions → measure twice, cut once.
5. **What teaches the most?** Given equal options, choose the one that adds more to the portfolio story.

### The Content Pipeline

After every significant feature:

1. **Identify the content angle:** What pattern did we implement? What trade-off did we navigate? What problem did we solve?
2. **Frame for the audience:** Engineers want architecture diagrams and code. Recruiters want impact statements. LinkedIn wants the story.
3. **Document while it's fresh:** The best content comes from the moment of shipping, not from reconstructing months later.
4. **Queue for publishing:** Blog post, video, LinkedIn post. Each feature is at least one piece of content.

Building without sharing is wasted potential. The portfolio only works if people see it.

## When Things Go Wrong

> "In the middle of difficulty lies opportunity." — Albert Einstein

### The Production Incident Protocol

1. **Assess blast radius.** Is the system down? Is it degraded? Is it serving wrong results? Severity determines response speed.
2. **Check the traces.** MLflow shows you what happened. Don't hypothesize — read the data.
3. **Identify root cause.** Is it the data? The model? The infrastructure? The code? Follow the pipeline.
4. **Fix forward.** Apply the fix, verify with existing eval suite, deploy.
5. **Post-mortem.** What broke? Why? What guard rail was missing? Add the guard rail. Add the regression test. Store the lesson.

### Graceful Degradation

When a component fails, the system should degrade, not crash:

- **LLM unavailable:** Return cached results or structured error, not 500
- **Database slow:** Serve from cache, queue write-behind
- **Embedding service down:** Fall back to keyword-only search
- **Third-party API timeout:** Use cached data, surface confidence warning

The user should always get something useful, even if the system is impaired.
