# ML/LLMOps Lifecycle Phases — Build Plan

Each phase maps to the production ML/LLMOps lifecycle. Every phase builds a real feature in a real project while teaching the skills that top-tier ML engineering roles require.

---

## Phase 1: DATA — Collection, Ingestion & Storage
**"The pipeline that feeds everything"**

> In production ML, 80% of the work is data. Companies pay $300K+ for engineers who can build reliable, scalable data pipelines that feed models with clean, structured data.

### What We Build

| Project | Feature | Skills Demonstrated |
|---------|---------|---------------------|
| **PlotLot v2** | Municode auto-discovery — scan 73+ municipalities at runtime instead of hardcoding configs | API reverse-engineering, async HTTP, caching, fault tolerance |
| **PlotLot v2** | Address → property data pipeline (Google Maps image, zoning code, lot dimensions) | Multi-source data fusion, geocoding, structured extraction |
| **PlotLot v2** | RAG ingestion pipeline — scrape → chunk → embed → store in pgvector | Document processing, embedding pipelines, vector databases |
| **MangoAI** | Dataset curation pipeline — image collection, labeling, HuggingFace dataset publishing | Dataset engineering, data versioning, quality control |

### Folder Structure
```
plotlot-v2/
  src/plotlot/rag/
    discovery.py        # Municode auto-discovery (NEW)
    scraper.py          # Municode API scraper (EXISTS)
    chunker.py          # HTML → text chunks (EXISTS)
    embedder.py         # HuggingFace embeddings (EXISTS)
    ingest.py           # Orchestration (EXISTS — UPDATE)
    db.py               # pgvector connection (EXISTS)
    schema.py           # SQLAlchemy models (EXISTS)
    search.py           # Hybrid search (EXISTS)

EP/datasets/            # Dataset artifacts & configs (NEW)
```

### Key Technologies
- **httpx** — async HTTP client with rate limiting
- **pgvector** — vector similarity search in PostgreSQL
- **HuggingFace Datasets** — dataset publishing and versioning
- **Pydantic** — structured data validation at every boundary
- **Prefect** — workflow orchestration for scheduled ingestion

### Interview Talking Points
- "I built an auto-discovery system that dynamically identifies 73 municipalities from a public API, with caching and graceful fallback to hardcoded configs when the API is down."
- "Our RAG pipeline processes zoning ordinances through a 4-stage async pipeline: scrape → chunk → embed → store, handling HTML parsing, semantic chunking, and pgvector hybrid search with RRF fusion."

---

## Phase 2: TRAIN — Fine-Tuning & Experiment Tracking
**"Making models actually work for your domain"**

> Generic models get you 70% of the way. Fine-tuning gets you to 95%. Companies pay premium for engineers who know when and how to fine-tune, and who can prove their model is actually better with rigorous experiment tracking.

### What We Build

| Project | Feature | Skills Demonstrated |
|---------|---------|---------------------|
| **MangoAI** | QLoRA fine-tuning of Qwen3-VL-8B on mango leaf dataset | Parameter-efficient fine-tuning, mixed-precision training, GPU optimization |
| **MangoAI** | MLflow experiment tracking — hyperparams, metrics, model artifacts | Experiment management, reproducibility, model registry |
| **PlotLot v2** | Prompt engineering + few-shot optimization for zoning extraction | DSPy-style prompt optimization, structured output tuning |
| **PlotLot v2** | Embedding model evaluation — compare sentence-transformers for zoning domain | Retrieval metrics (MRR, NDCG), domain adaptation |

### Folder Structure
```
mangoai/
  training/
    train.py            # QLoRA training script
    config.yaml         # Training hyperparameters
    eval.py             # Evaluation metrics
  mlflow/
    experiments/        # MLflow experiment artifacts

plotlot-v2/
  experiments/
    embedding_eval.py   # Compare embedding models
    prompt_optimization/ # DSPy prompt tuning
```

### Key Technologies
- **Unsloth** — 2x faster QLoRA fine-tuning
- **MLflow** — experiment tracking, model registry, artifact store
- **DSPy** — programmatic prompt optimization
- **Weights & Biases** (optional) — training visualization
- **PEFT/LoRA** — parameter-efficient fine-tuning

### Interview Talking Points
- "I fine-tuned a vision-language model using QLoRA with Unsloth, achieving 94% accuracy on a custom 40-variety mango dataset, tracked across 50+ experiments in MLflow."
- "I used DSPy to programmatically optimize extraction prompts, improving zoning data extraction F1 from 0.72 to 0.89 without changing the model."

---

## Phase 3: BUILD — Agent Architecture & Application Layer
**"Where ML meets product"**

> The highest-paid ML engineers don't just train models — they build the systems around them. Agent orchestration, tool use, structured output, error recovery. This is the $400K+ skill set.

### What We Build

| Project | Feature | Skills Demonstrated |
|---------|---------|---------------------|
| **PlotLot v2** | Multi-agent property analysis — Router → Parallel Specialists → Synthesis | Agent orchestration, parallel execution, result fusion |
| **PlotLot v2** | Structured zoning extraction — Instructor + Pydantic → setbacks, FAR, density, height | Structured LLM output, schema enforcement, validation |
| **PlotLot v2** | Max allowable units calculator — zoning setbacks × lot dimensions → buildable area → units | Domain logic, constraint satisfaction, business rules |
| **Agent Forge** | Reusable agent framework — tool registry, memory, streaming, deployment patterns | Framework design, abstraction, API design |

### The Core Product Flow
```
User: "123 NW 5th Ave, Fort Lauderdale, FL"
  │
  ├─→ Geocoding Agent ─→ lat/lng, county, municipality
  │
  ├─→ Property Agent ─→ Google Maps image, lot dimensions (L × W)
  │
  ├─→ Zoning Agent ─→ zone code (e.g., "RS-8")
  │     └─→ RAG Search ─→ relevant ordinance sections
  │     └─→ LLM Extraction ─→ setbacks, FAR, height, density
  │
  └─→ Analysis Agent ─→ max allowable units calculation
        └─→ lot_area - setback_area = buildable_area
        └─→ buildable_area × FAR / unit_size = max_units
        └─→ structured PropertyReport output
```

### Folder Structure
```
plotlot-v2/
  src/plotlot/
    agents/
      router.py         # Intent classification & routing
      geocoding.py      # Address → coordinates + jurisdiction
      property.py       # Google Maps, lot dimensions
      zoning.py         # Zone code + ordinance extraction
      analysis.py       # Max units calculation
      synthesis.py      # Combine all agent results
    pipeline/
      lookup.py         # End-to-end orchestration (EXISTS)
    models/
      zoning.py         # Pydantic models for extracted data
      property.py       # Property data models

agent-forge/            # Separate project
  src/
    agent_forge/
      core/             # Base agent, tool registry, memory
      tools/            # Built-in tools
      serving/          # FastAPI deployment
```

### Key Technologies
- **PydanticAI / LangGraph** — agent orchestration framework
- **Instructor** — structured LLM output with retry and validation
- **Groq / OpenRouter** — LLM inference (fast + cheap for development)
- **FastAPI** — API layer for agent serving
- **asyncio** — parallel agent execution

### Interview Talking Points
- "I designed a multi-agent architecture with parallel specialist execution — geocoding, property lookup, and zoning analysis run concurrently, reducing end-to-end latency by 60%."
- "The zoning extraction agent uses Instructor with Pydantic models to guarantee structured output — setbacks, FAR, height limits, density — with automatic retry on schema violations."

---

## Phase 4: EVAL — Testing & Quality Assurance
**"Proving your system actually works"**

> This is Earl's superpower. QA background + ML evaluation = the most in-demand skill combination in LLMOps right now. Companies are desperate for engineers who can build rigorous evaluation pipelines for AI systems.

### What We Build

| Project | Feature | Skills Demonstrated |
|---------|---------|---------------------|
| **Agent Eval** | LLM evaluation framework — automated scoring of extraction quality | LLM-as-judge, rubric design, statistical testing |
| **PlotLot v2** | RAG evaluation — retrieval quality metrics across 73 municipalities | RAGAS metrics (faithfulness, relevance, context recall) |
| **PlotLot v2** | End-to-end regression tests — golden set of address → expected results | Integration testing, snapshot testing, CI gates |
| **Agent Eval** | Evaluation CI pipeline — run evals on every PR, block merges on regression | CI/CD for ML, quality gates, automated reporting |

### Folder Structure
```
agent-eval/             # Separate project
  src/
    agent_eval/
      metrics/          # Custom metrics (extraction accuracy, hallucination rate)
      judges/           # LLM-as-judge configurations
      datasets/         # Golden evaluation datasets
      reporters/        # HTML/JSON evaluation reports
      ci/               # GitHub Actions integration

plotlot-v2/
  evals/
    golden_set.json     # Known-good address → result pairs
    rag_eval.py         # RAGAS evaluation runner
    extraction_eval.py  # Zoning extraction accuracy
```

### Key Technologies
- **DeepEval** — LLM evaluation framework
- **RAGAS** — RAG-specific evaluation metrics
- **Langfuse** — tracing and observability for LLM calls
- **pytest** — test infrastructure
- **GitHub Actions** — CI evaluation gates

### Interview Talking Points
- "I built an automated evaluation pipeline that runs RAGAS metrics on every PR — if retrieval faithfulness drops below 0.85, the merge is blocked. This caught 3 regressions before they hit production."
- "My QA background gave me an edge: I designed an LLM-as-judge framework that evaluates extraction accuracy against a golden dataset of 200+ verified zoning records across 73 municipalities."

---

## Phase 5: SERVE — Deployment & Inference
**"Getting it in front of users"**

> A model in a notebook is worth $0. A model behind an API serving real users is worth millions. Deployment engineering — containerization, API design, scaling, cost optimization — is where the money is.

### What We Build

| Project | Feature | Skills Demonstrated |
|---------|---------|---------------------|
| **PlotLot v2** | FastAPI production API — address in, full analysis out | API design, async serving, request validation |
| **PlotLot v2** | Next.js frontend — map view, property cards, zoning overlay | Full-stack integration, real-time updates |
| **MangoAI** | SGLang model serving on RunPod — GPU inference endpoint | Model serving, GPU optimization, auto-scaling |
| **Agent Forge** | One-command agent deployment — Docker → cloud | Containerization, infrastructure-as-code |

### Folder Structure
```
plotlot-v2/
  src/plotlot/
    api/
      main.py           # FastAPI application
      routes/            # API endpoints
      middleware/        # Auth, rate limiting, CORS
  frontend/
    src/
      app/              # Next.js pages
      components/       # Map, property cards, zoning display

mangoai/
  serving/
    sglang_server.py    # SGLang inference server
    Dockerfile          # GPU container
    runpod.yaml         # RunPod deployment config
```

### Key Technologies
- **FastAPI** — async API framework
- **Next.js** — React frontend
- **Docker** — containerization
- **SGLang** — high-throughput LLM/VLM serving
- **RunPod** — GPU cloud for inference
- **Nginx/Caddy** — reverse proxy, TLS

### Interview Talking Points
- "I serve a fine-tuned VLM on RunPod via SGLang, handling 50 req/s with P99 latency under 200ms, at 1/10th the cost of a managed API."
- "The PlotLot API processes property analysis requests end-to-end in under 3 seconds — geocoding, zoning lookup, RAG retrieval, and LLM extraction all running async."

---

## Phase 6: MONITOR — Observability & Feedback Loops
**"Knowing when things break before users tell you"**

> Production ML systems drift. Data changes, APIs break, model quality degrades. The engineers who build observability into their ML systems from day one are the ones who sleep at night.

### What We Build

| Project | Feature | Skills Demonstrated |
|---------|---------|---------------------|
| **PlotLot v2** | Langfuse tracing — every LLM call logged with inputs, outputs, latency, cost | LLM observability, cost tracking, quality monitoring |
| **PlotLot v2** | Data quality monitoring — detect stale/broken municipality data | Data drift detection, alerting, self-healing pipelines |
| **PlotLot v2** | User feedback loop — flag incorrect zoning results → retraining signal | Human-in-the-loop, feedback collection, active learning |
| **MangoAI** | Model performance dashboards — accuracy over time, class-level metrics | Model monitoring, metric visualization |

### Folder Structure
```
plotlot-v2/
  src/plotlot/
    monitoring/
      traces.py         # Langfuse integration
      alerts.py         # Slack/email alerting
      data_quality.py   # Municipality data freshness checks
      dashboards.py     # Metric aggregation

  grafana/
    dashboards/         # Pre-built monitoring dashboards
```

### Key Technologies
- **Langfuse** — LLM tracing and analytics
- **Prometheus + Grafana** — metrics and dashboards
- **Sentry** — error tracking
- **Prefect** — scheduled health checks

### Interview Talking Points
- "I instrumented every LLM call with Langfuse tracing — we track token usage, latency percentiles, and extraction quality scores in real-time. When our zoning extraction accuracy dropped below 90% for Miami-Dade, we caught it within 2 hours."
- "I built a data freshness monitor that detects when municipality zoning codes are updated on Municode and triggers re-ingestion automatically."

---

## Phase 7: PIPELINE — End-to-End Orchestration & CI/CD
**"Tying it all together"**

> This is the capstone. The full ML/LLMOps lifecycle running as automated pipelines. Data flows in, models train, evaluations gate, deployments ship, monitors watch. This is what a Principal ML Engineer builds.

### What We Build

| Project | Feature | Skills Demonstrated |
|---------|---------|---------------------|
| **PlotLot v2** | Prefect DAG — scheduled re-ingestion for all 73 municipalities | Workflow orchestration, scheduling, retry logic |
| **PlotLot v2** | CI/CD pipeline — lint → test → eval → build → deploy | GitHub Actions, quality gates, automated deployment |
| **All projects** | Unified MLflow registry — all models versioned and tracked | Model management, artifact lineage, promotion workflows |
| **Agent Eval** | Nightly eval runs — catch regressions before users do | Scheduled evaluation, trend analysis, alerting |

### Folder Structure
```
plotlot-v2/
  .github/workflows/
    ci.yml              # Lint + test + type-check
    eval.yml            # RAG evaluation on PR
    deploy.yml          # Production deployment
    ingest.yml          # Scheduled re-ingestion

  src/plotlot/flows/
    ingestion_flow.py   # Prefect ingestion DAG (EXISTS — UPDATE)
    eval_flow.py        # Prefect evaluation DAG (NEW)
    retrain_flow.py     # Prefect retraining DAG (NEW)
```

### Key Technologies
- **Prefect** — workflow orchestration
- **GitHub Actions** — CI/CD
- **MLflow** — model registry and promotion
- **Docker Compose** — local full-stack development
- **Terraform** (stretch) — infrastructure-as-code

### Interview Talking Points
- "I built end-to-end ML pipelines that handle the full lifecycle: nightly data ingestion across 73 municipalities, automated RAG evaluation that gates deployments, and model promotion workflows through MLflow."
- "Our CI pipeline runs 280+ tests including LLM evaluation metrics — if extraction quality regresses on any of our golden set addresses, the PR is blocked automatically."

---

## Build Order & Timeline

| Order | Phase | First Milestone | Primary Project |
|-------|-------|-----------------|-----------------|
| **NOW** | Phase 1: DATA | Municode auto-discovery (73 municipalities) | PlotLot v2 |
| **Next** | Phase 3: BUILD | Address → zoning code → setbacks → max units pipeline | PlotLot v2 |
| **Then** | Phase 4: EVAL | Golden set + RAGAS evaluation | PlotLot v2 + Agent Eval |
| **Then** | Phase 2: TRAIN | MangoAI fine-tuning + MLflow tracking | MangoAI |
| **Then** | Phase 5: SERVE | FastAPI + Next.js deployment | PlotLot v2 |
| **Then** | Phase 6: MONITOR | Langfuse tracing + data quality alerts | PlotLot v2 |
| **Then** | Phase 7: PIPELINE | Full CI/CD + Prefect orchestration | All projects |

> **Why this order?** We start with DATA because PlotLot v2 needs the 73-municipality pipeline working before anything else. BUILD comes next because the core product (address → max units) is what makes this portfolio stand out. EVAL comes before TRAIN because Earl's QA background makes this his differentiator — and evaluation skills are the #1 gap in the LLMOps market right now. TRAIN can happen in parallel with MangoAI. SERVE, MONITOR, and PIPELINE are the production polish that turns a project into a portfolio-defining system.

---

## The Story This Tells Employers

When Earl walks into an interview, the portfolio says:

1. **"I can build production data pipelines"** — Auto-discovery system that dynamically ingests zoning data from 73 municipalities
2. **"I can fine-tune and optimize models"** — QLoRA fine-tuning with rigorous experiment tracking
3. **"I can architect AI-powered products"** — Multi-agent system that turns an address into actionable investment analysis
4. **"I can prove my systems work"** — Automated evaluation framework with CI-integrated quality gates
5. **"I can deploy and scale"** — Production API with GPU inference, containerized deployment
6. **"I can keep systems healthy"** — Real-time monitoring, data quality checks, feedback loops
7. **"I can orchestrate the full lifecycle"** — End-to-end pipelines from data collection to production deployment

This isn't 4 separate projects. It's **one coherent story** of an engineer who understands the complete ML/LLMOps lifecycle and can execute at every layer.
