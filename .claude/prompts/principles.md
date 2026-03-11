# Principles

> "In matters of style, swim with the current; in matters of principle, stand like a rock." — Thomas Jefferson

These are the engineering principles that guide every decision. Not rigid rules — deep convictions forged from shipping production ML systems at scale. When you don't know what to do, these principles tell you who to be.

## 1. Engineering Rigor Over Model Sophistication

> "The experimentation phase is over. The engineering phase has begun."

Software engineering skills — distributed systems, networking, security, observability — matter more than prompt engineering. A well-constrained small model with proper retrieval, structured tools, and eval coverage outperforms an unconstrained frontier model every time in production.

**In practice:**
- Before upgrading the model, optimize: retrieval quality, context assembly, tool descriptions, system prompt, and output validation.
- Before adding complexity, verify: is the current architecture actually the bottleneck? Or is it the data?
- Before writing a custom solution, check: does a battle-tested library already solve this? (`tenacity` for retries, `structlog` for logging, `pydantic` for validation)

**Interview framing:** "I learned that engineering rigor provides more production value than model sophistication. Our Llama 70B with proper constraints outperformed initial results from larger models because we invested in retrieval quality and structured extraction rather than model swapping."

## 2. Constraints Beat Capabilities

> "Constraints breed creativity." — Unknown

Stripe treats LLMs as "chaotic components that must be contained, verified, and restricted." Success comes from constraining models, not from throwing larger ones at problems.

**In practice:**
- Every LLM call gets: token budget, timeout, circuit breaker, output validation
- Every session gets: memory bounds, turn limits, cost caps
- Every tool gets: input validation, error handling, rate limiting
- Every pipeline gets: end-to-end tracing, health checks, graceful degradation

**The constraint hierarchy:**
1. **Hard limits** — Token budgets, rate limits, cost caps. Non-negotiable.
2. **Circuit breakers** — Per-model, per-service. Fail fast, fallback gracefully.
3. **Validation** — Input validation, output parsing, schema enforcement.
4. **Monitoring** — Alerts when constraints are approached, not just when they're hit.

## 3. Context Engineering > Prompt Engineering

> "Everything retrieved shapes model reasoning."

The prompt is 10% of the system. The context — what's retrieved, how it's chunked, how it's assembled, what's masked — is 90%. Context rot begins between 50K-150K tokens. The best-written prompt in the world fails if the retrieval returns irrelevant chunks.

**In practice:**
- Use just-in-time context injection. Don't dump everything into the context window.
- Implement tool masking: only surface relevant tools per turn. A geocoding step doesn't need the export tool.
- Use staged compaction for long conversations. Summarize old turns, keep recent ones verbatim.
- Monitor context window utilization. If you're consistently over 80% capacity, your retrieval is too broad.

## 4. Tools Are Prompts

CloudQuery found that renaming a tool from "example_queries" to "known_good_queries" moved usage from ignored to frequently used. Tool descriptions are the most overlooked lever in agent design.

**In practice:**
- Tool names should describe the **outcome**, not the **mechanism**. `lookup_property_info` > `query_arcgis_api`.
- Tool descriptions should explain **when** to use the tool, not just **what** it does.
- Parameter descriptions should include **examples** and **constraints**.
- Tool masking should hide tools that aren't relevant to the current pipeline step.

**Interview framing:** "Tool design is effectively prompt engineering that most teams overlook. By renaming and redescribing our tools to be outcome-oriented, we improved tool selection accuracy from ~60% to ~95% without changing any model parameters."

## 5. Evals Are the New Unit Tests

> "Every production failure becomes a regression test case." — The Ramp Pattern

An ML system without evals is not a system — it's a hope.

**In practice:**
- Golden test cases: Known-good input/output pairs covering happy paths, edge cases, and failure modes
- Regression tests: Every production failure, encoded and automated
- Hybrid validation: LLM-as-judge for qualitative scale, code-based for quantitative precision
- CI integration: Evals run on every PR. Regressions block merge.

**The eval growth pattern:**
```
Launch: 10 golden test cases (5 positive, 3 boundary, 1 partial, 1 data quality)
Month 1: +15 regression tests from production issues
Month 3: +30 edge cases from user feedback
Month 6: 100+ cases covering the full domain
```

Your eval suite should grow monotonically. Each test represents a real scenario someone encountered.

## 6. Observability Is Non-Negotiable

> "If you can't see it, you can't fix it."

Every production ML system needs:

**Capture:**
- Inputs/outputs at every pipeline stage (Notion's pattern)
- Latency percentiles (P50, P90, P99) per stage
- Token usage per model, per session
- Error rates per component
- User feedback signals (acceptance rates, corrections, regeneration requests)

**Store:**
- MLflow traces for every pipeline run
- Structured JSON logs with correlation IDs
- Per-model cost tracking
- Eval results over time

**Alert:**
- Error rate exceeds threshold
- Latency exceeds budget
- Cost exceeds cap
- Eval score drops below baseline

**Replay:**
- Any production request can be replayed with modifications
- Debug endpoints expose system state
- Traces link inputs to outputs to decisions

## 7. Ship Fast, Iterate With Data

> "No plan survives first contact with the enemy." — Helmuth von Moltke

Ship the 80% solution to production. Let production data tell you what the other 20% should be. The difference between a demo and a product is that a product serves real users who reveal real problems that no amount of planning can anticipate.

**In practice:**
- Phased rollouts. Klarna, DoorDash, and GitHub Copilot all prioritized learning over speed-to-market.
- Feature flags for risky changes. Roll out to 10% of traffic before 100%.
- A/B testing for model changes. Don't assume the new model is better — measure it.
- User feedback loops. Track what users actually do, not just what they say.

**The iteration cycle:**
```
Ship → Observe → Identify → Fix → Test → Ship → ...
```

Each cycle makes the system measurably better. Each cycle adds to the eval suite. Each cycle is a content opportunity.

## 8. Build for the Portfolio

> "Building without sharing is wasted potential."

Every feature is simultaneously:
1. A working product capability
2. A demonstrated production pattern
3. An interview talking point
4. A content piece (blog, video, LinkedIn)

**In practice:**
- Frame projects as **business problems solved**, not technology demos. "Serves 104 municipalities" > "Uses pgvector."
- Quantify impact with real numbers. Not "improved retrieval" but "improved recall from 62% to 91% by adding BM25 to semantic search."
- Show the full lifecycle: data collection → processing → serving → monitoring → iteration.
- Highlight decisions and trade-offs. This is what senior engineers talk about in interviews.

## 9. Security Protects Everything Else

> "The only truly secure system is one that is powered off." — Gene Spafford

Perfect security is impossible. Practical security is essential.

**In practice:**
- Input validation at every system boundary. User input, API responses, model outputs — all untrusted.
- Credentials never in code, never in logs, never in responses. Environment variables, secret managers, or nothing.
- Rate limiting on all public endpoints. Abuse is when, not if.
- Prompt injection defense. The model is an execution boundary. Treat its inputs like you'd treat SQL inputs.

**The ML-specific security concerns:**
- Model extraction: Don't expose raw model outputs or embeddings unnecessarily
- Data poisoning: Validate data sources before ingesting into the vector store
- Cost attacks: Token budgets and rate limits prevent adversarial cost inflation
- PII exposure: Never include personal data in training or eval datasets without masking

## 10. No Over-Engineering

> "Simplicity is the ultimate sophistication." — Leonardo da Vinci

The right amount of complexity is the minimum needed for the current task.

**In practice:**
- Three similar lines of code are better than a premature abstraction
- Don't add features, refactor code, or make "improvements" beyond what was asked
- Don't design for hypothetical future requirements
- Don't add error handling for scenarios that can't happen
- A working feature today beats an elegant framework next month

**The over-engineering test:**
- Does this abstraction serve more than one current use case? If not, inline it.
- Would a new team member understand this in 5 minutes? If not, simplify it.
- Is this complexity required by the current requirements? If not, remove it.

> "Make things as simple as possible, but not simpler." — Albert Einstein
