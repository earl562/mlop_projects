# Obsidian Harness KG arXiv Deep Analysis

Total reviewed paper notes covered: 35

This report expands every reviewed arXiv note found in the Obsidian Harness Engineering KG. Each entry includes the sections preserved in the note: key primitives, domain implications, evaluation ideas, deltas, KG connections, current synthesis, and quotes when available.

## Coverage inventory
- 2408.01667v2 — Automated Phishing Detection Using URLs and Webpages
- 2505.02279v2 — A survey of agent interoperability protocols: Model Context Protocol (MCP), Agent Communication Protocol (ACP), Agent-to-Agent Protocol (A2A), and Agent Network Protocol (ANP)
- 2507.11633 — General Modular Harness for LLM Agents in Multi-Turn Gaming Environments
- 2509.21766 — UltraHorizon: Benchmarking Agent Capabilities in Ultra Long-Horizon Scenarios
- 2512.16301v3 — Adaptation of Agentic AI: A Survey of Post-Training, Memory, and Skills
- 2601.10338v1 — Agent Skills in the Wild: An Empirical Study of Security Vulnerabilities at Scale
- 2601.10971v2 — AJAR: Adaptive Jailbreak Architecture for Red-teaming
- 2602.02474v1 — MemSkill: Learning and Evolving Memory Skills for Self-Evolving Agents
- 2602.06025v1 — Learning Query-Aware Budget-Tier Routing for Runtime Agent Memory
- 2602.12430v3 — Agent Skills for Large Language Models: Architecture, Acquisition, Security, and the Path Forward
- 2602.16069v2 — The Limits of Long-Context Reasoning in Automated Bug Fixing
- 2602.19672v1 — SkillOrchestra: Learning to Route Agents via Skill Transfer
- 2602.20867v1 — SoK: Agentic Skills -- Beyond Tool Use in LLM Agents
- 2602.22480 — VeRO: An Evaluation Harness for Agents to Optimize Agents
- 2603.03329v1 — AutoHarness: improving LLM agents by automatically synthesizing a code harness
- 2603.07670v1 — Memory for Autonomous LLM Agents:Mechanisms, Evaluation, and Emerging Frontiers
- 2603.18829v9 — Agent Control Protocol: Admission Control for Agent Actions
- 2603.20380v1 — ALARA for Agents: Least-Privilege Context Engineering Through Portable Composable Multi-Agent Teams
- 2603.21019v1 — SkillProbe: Security Auditing for Emerging Agent Skill Marketplaces via Multi-Agent Collaboration
- 2603.22148v1 — OpenEarth-Agent: From Tool Calling to Tool Creation for Open-Environment Earth Observation
- 2603.25723v1 — Natural-Language Agent Harnesses
- 2603.28052v1 — Meta-Harness: End-to-End Optimization of Model Harnesses
- 2603.29199v1 — AEC-Bench: A Multimodal Benchmark for Agentic Systems in Architecture, Engineering, and Construction
- 2604.03610v1 — DebugHarness: Emulating Human Dynamic Debugging for Autonomous Program Repair
- 2604.07833v2 — Harnessing Embodied Agents: Runtime Governance for Policy-Constrained Execution
- 2604.08224v1 — Externalization in LLM Agents: A Unified Review of Memory, Skills, Protocols and Harness Engineering
- 2604.11378v1 — From Agent Loops to Structured Graphs:A Scheduler-Theoretic Framework for LLM Agent Execution
- 2604.11548v1 — SemaClaw: A Step Towards General-Purpose Personal AI Agents through Harness Engineering
- 2604.13018v1 — Toward Autonomous Long-Horizon Engineering for ML Research
- 2604.13151v1 — Exploration and Exploitation Errors Are Measurable for Language Model Agents
- 2604.13346v1 — AgentSPEX: An Agent SPecification and EXecution Language
- 2604.13630v1 — SafeHarness: Lifecycle-Integrated Security Architecture for LLM-based Agent Deployment
- 2604.14228v1 — Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems
- 2604.18071v1 — Architectural Design Decisions in AI Agent Harnesses
- 2604.20779v1 — SWE-chat: Coding Agent Interactions From Real Users in the Wild

## Paper 1: 2408.01667v2 — Automated Phishing Detection Using URLs and Webpages
### Key primitives
- The paper is valuable for harness engineering because it isolates where a static-reference pipeline fails before proposing a better model loop:
  - missing or wrong logo extraction causes early blindness
  - representation validation bottlenecks knowledge expansion
  - brittle Google-result filtering suppresses true positives even when the right brand is present
- It decomposes the replacement system (GEPAgent) into a clean four-stage harness:
  1. capture explicit artifacts from the webpage (`URL`, screenshot, HTML)
  2. run **static signal translation** in preprocessing (HTML reduction, logo crop, Google Logo Detector, GPT4-V)
  3. run **budgeted dynamic reference expansion** with Google Search and Google Image Search (up to 5 tool calls)
  4. run **entity-to-authority verification** with a domain checker over top-level and second-level domains
- The paper’s strongest first-principles distinction is **explicit vs implicit information**:
  - explicit = text, images, URLs directly seen on the page
  - implicit = the higher-order meaning/brand associations needed for correct classification
  - the harness should translate explicit artifacts into implicit signals before the main agent loop spends retrieval budget
- It makes a useful tool-boundary decision:
  - **Google Logo Detector + GPT4-V** belong to preprocessing because they transform static artifacts
  - **Google Search + Google Image Search** belong inside the agent toolkit because they expand knowledge during execution
- The domain checker removes dependence on a fully curated knowledge base:
  - query the raw predicted brand name in quotes
  - collect search-result display links
  - match using both top-level and second-level domains to absorb domain variants
  - using 10 candidate domains outperformed 5 in false-positive reduction
- Empirical results from the full paper are strong enough to matter for harness design:
  - brand recognition: **190/200** correct for GPT-4-turbo vs **182/200** for GPT-3.5-turbo
  - phishing true positives: **194/200** for GPT-4-turbo
  - final GPT-4 agent metrics: **precision 0.9238**, **recall 0.97**, **accuracy 0.945**, **F1 0.9463**
  - baseline DynaPhish metrics in the same evaluation: **recall 0.3616**, **accuracy 0.4999**, **F1 0.5131**
- The paper also quantifies the latency/quality tradeoff the harness must manage:
  - Google Logo Detector is only about **70%** accurate on cropped logos
  - average runtime is about **20 seconds/sample**
  - limiting the agent to **5 rounds** can still bottleneck ambiguous cases

### PlotLot implications
- Treat municipality and source discovery the same way this paper treats brand discovery:
  - do **not** assume PlotLot can maintain an exhaustive static registry of official parcel, zoning, overlay, and ordinance hosts for every jurisdiction
  - let the harness dynamically discover the governing authority and official document/source set from parcel and jurisdiction cues
- Add a preprocessing lane that converts explicit artifacts into implicit signals before the main reasoning loop:
  - normalize parcel facts and jurisdiction names
  - extract zoning-code candidates from ordinance text and maps
  - OCR tables, legends, and dimensional matrices
  - fingerprint source provenance before any LLM synthesis
- Introduce an authority-verification step analogous to the paper’s brand-to-domain check:
  - after the model predicts the governing city/county/ordinance authority, verify that the cited source resolves to an official municipal, county, ArcGIS, or Municode domain
  - reject or down-rank consultant PDFs, mirrors, blog posts, and unofficial reposts even if their text looks plausible
- Preserve the paper’s tooling split:
  - cheap deterministic transforms stay outside the expensive agent loop
  - active browse/search calls are reserved for ambiguity the preprocessor could not resolve
  - this is directly useful for PlotLot because ordinance retrieval and evidence review can easily become slow, noisy, and token-heavy
- Use verified official runs to grow reusable memory:
  - the paper suggests safe knowledge-base growth from benign samples
  - PlotLot analogue: only cache jurisdiction portals, ordinance hosts, and extraction heuristics after official-source verification succeeds
- Direct product consequence for the land-use/site-feasibility harness:
  - the harness should first answer **which authority governs this parcel and which sources are official?**
  - only after that should it trust extracted setbacks, lot coverage, FAR, height, density, or parking numbers enough to drive calculators and investment outputs

### Evaluation ideas
- **Unknown-jurisdiction discovery benchmark**
  - hide any preconfigured provider/domain mapping
  - measure whether the harness can still discover the correct parcel, zoning, and ordinance authorities for a site
- **Authority-verification benchmark**
  - mix official ordinance hosts with mirrors, newsletters, consultant PDFs, and scraped reposts
  - score false-authority rate separately from numeric extraction quality
- **Preprocessing ablation**
  - compare raw ordinance text only vs text + OCR/table extraction vs text + OCR + map/legend extraction
  - evaluate citation resolution, unit normalization, and deterministic calculator correctness
- **Tool-budget ablation**
  - compare 0/1/3/5 active retrieval turns
  - measure evidence coverage, latency, contradiction resolution, and analyst acceptance
- **Domain-variant analogue test**
  - use jurisdictions with legacy domains, subdomains, ArcGIS-hosted assets, and third-party code publishers
  - require the harness to prove official-source matching before downstream calculators accept extracted values

### Deltas
- Relative to previously reviewed governance papers, this is the clearest concrete example of harness value coming from **dynamic reference acquisition**, not from a larger model or a longer prompt.
- It adds a missing upstream layer to the current KG: **explicit-to-implicit translation** before context brokering and workflow execution.
- It sharpens verification from “is this extracted claim internally consistent?” to “have we first resolved the official authority boundary for this claim?”
- It also provides a caution for PlotLot:
  - the primitive is useful
  - the exact Google-centric implementation is brittle, latency-heavy, and externally dependent
  - PlotLot should keep the architecture pattern while replacing narrow phishing-specific components with domain-specific parsers, authority checks, and caches

### KG connections
- [[Explicit-to-Implicit Translation]]
- [[Dynamic Reference Expansion]]
- [[Entity-to-Authority Verification]]
- [[Budgeted Tool Loop]]
- [[Context Broker]]
- [[Evidence Ledger]]

### Current synthesis
- The paper matters less for phishing per se than for its harness decomposition: static signal translation -> budgeted discovery -> authority verification.
- Its most transferable primitive for PlotLot is replacing exhaustive prior registries with on-run reference expansion backed by official-source verification.
- Its main warning is operational: dynamic discovery improved accuracy dramatically but paid ~20s/sample and depended on brittle external services, so PlotLot needs caching, fallback routes, and strict retrieval budgets.

### Quotes
> “Webpage content can be categorized into two types: explicit and implicit information.”

> “The Google Logo Detector and GPT4-V are introduced during preprocessing … Google Search and Google Image Search are included in the agent’s toolkit …”

> “The average runtime for analyzing a single sample is approximately 20 seconds …”

---

## Paper 2: 2505.02279v2 — A survey of agent interoperability protocols: Model Context Protocol (MCP), Agent Communication Protocol (ACP), Agent-to-Agent Protocol (A2A), and Agent Network Protocol (ANP)
### Key primitives
- Survey/comparison of 4 interoperability protocols (tooling + agent comms + discovery):
  - **MCP (Model Context Protocol)**: JSON-RPC client/server for tools, resources, prompts, and (server-controlled) sampling.
  - **ACP (Agent Communication Protocol)**: HTTP/REST agent invocation with MIME-typed multipart messages; sessions; sync/async; discovery via runtime APIs/manifests; mentions RBAC/DIDs.
  - **A2A (Agent-to-Agent)**: peer delegation using capability-based **Agent Cards**; JSON-RPC; supports async/evented transport (e.g., SSE).
  - **ANP (Agent Network Protocol)**: open network discovery + collaboration using **W3C DIDs** + JSON-LD graphs; decentralized marketplace orientation.
- Provides comparison dimensions:
  - interaction modes (sync/async)
  - discovery mechanisms
  - communication patterns
  - security models
- Proposes phased adoption roadmap: start with **MCP** (tool access) → add **ACP** (structured session-aware messaging) → **A2A** (collaborative task delegation) → **ANP** (decentralized discovery/marketplace).
- Highlights lifecycle security issues (examples from tables/sections): name collisions/impersonation, manifest spoofing, version drift, signing and drift detection.

### PlotLot implications
- Aligns with current PlotLot stance (backend authoritative; clients are shells):
  - Use **MCP** as the primary tool adapter boundary (typed interfaces + explicit tool registry).
  - Use **ACP-like** HTTP session semantics internally for agent runs (job IDs, streaming events, multipart artifacts).
- If/when PlotLot supports multi-agent delegation across services, A2A concepts map well:
  - **Agent Cards** as capability manifests for internal agents/services.
- ANP is likely “later” (only if PlotLot participates in open agent discovery/marketplaces).

### Evaluation ideas
- Protocol hardening tests:
  - MCP tool name-collision handling and allow/deny policy invariants
  - signature verification for manifests/Agent Cards
  - version drift / downgrade resistance (pin + verify)
  - replay protection for async/evented messages

---

## Paper 3: 2507.11633 — General Modular Harness for LLM Agents in Multi-Turn Gaming Environments
### Key primitives
- The paper decomposes a general-purpose agent harness into **perception**, **memory**, and **reasoning** modules around one shared backbone model, so scaffold effects can be isolated instead of hidden inside a monolith.
- The **perception module** has three modes: deterministic backend-to-text state tables, vision-only descriptions, and a combined mode with image overlays plus structured text; the key claim is that state translation reduces raw perception errors.
- The **memory module** keeps a bounded history of recent states/actions plus a short reflection on the latest transition, using local state change as an internal reward-style signal to avoid repetitive or invalid moves.
- Module value is **task-conditioned** rather than universal: perception helps spatial/geometric tasks most, memory helps long-horizon tasks most, and the strongest results usually come from combining both.
- Across the paper's four-game suite, the full harness beats the no-harness baseline with statistically significant gains: **Candy Crush +217.50**, **Sokoban +1.97**, **2048 +17.81**, and **Tetris +5.60** (paired t-tests, *p* < 0.05).
- The paper also shows that **prompt variance can swamp module comparisons**; their empirical + DSPy/SIMBA prompt-standardization pass improves average performance and lowers variance across models/games.

### PlotLot implications
- PlotLot should split the land-use/site-feasibility harness into three explicit vertical layers:
  - **state translation / perception** for parcel, GIS, ordinance, and site-plan artifacts
  - **reflective working memory** for recent retrieval/extraction/calculation deltas
  - **reasoning/controller** for stage selection and next-action choice
- The perception analogue for PlotLot is: convert parcel pages, zoning tables, ordinance sections, plats, and GIS screenshots into **deterministic structured state** first, then let the model reason over that representation instead of raw artifact noise.
- The memory analogue is: keep the last few retrieval/extraction/calculation steps plus a short reflection on what changed, what failed, and which evidence gaps remain, so the harness can self-correct before it repeats a bad lane.
- PlotLot should **not** use one uniform scaffold for every subtask:
  - map/site-plan/table extraction should get perception-heavy support
  - ordinance cross-reference, exception handling, and contradiction resolution should get memory-heavy support
  - final analyst-facing synthesis should get both
- The main operational lesson is cost discipline: if deterministic state translation already resolves a subtask, do not pay unnecessary memory/tool/context tax just because the full harness exists.

### Evaluation ideas
- Build a PlotLot ablation matrix over real site-feasibility subtasks:
  - controller only
  - + deterministic state translation
  - + reflective working memory
  - + both
- Group benchmark cases by dominant difficulty:
  - map/site-plan interpretation
  - noisy zoning/dimensional table extraction
  - long ordinance cross-reference chains
  - iterative calculator/report revision
- Track business-relevant analogues of “invalid moves”:
  - unsupported zoning claims
  - uncited dimensional numbers
  - contradictory ordinance interpretations
  - repeated low-yield retrieval loops
- Standardize prompts and eval budgets before comparing module mixes, otherwise PlotLot may mistake prompt luck for a real harness improvement.

### Deltas
- Reviewed from the full local cache text in `docs/research/_cache/arxiv/2507.11633.txt`.
- Added PlotLot-specific guidance around deterministic state translation, reflective working memory, and task-conditioned scaffolding.

### KG connections
- [[Workflow Module Interface]]
- [[Explicit-to-Implicit Translation]]
- [[Reflective Working Memory]]
- [[Task-Conditioned Scaffolding]]
- [[Harness Runtime]]

### Current synthesis
- This is the clearest reviewed source so far on splitting a general-purpose harness into perception, memory, and reasoning layers while holding the backbone model constant.
- For PlotLot, its biggest architectural lesson is task-conditioned scaffolding: use deterministic state translation for map/table/document-heavy subtasks and reflective working memory for long multi-step ordinance reasoning.
- Its main warning is evaluation hygiene: prompt variance is large enough to distort module comparisons, so PlotLot should compare scaffold mixes under fixed prompts and budgets rather than anecdotal one-off runs.

### Quotes
> “memory dominates in long-horizon puzzles while perception is critical in vision-noisy arcades.”
>
> “Perception is most beneficial in spatially structured environments like Sokoban and Tetris, whereas memory is crucial for games requiring long-term planning, such as 2048 and Candy Crush.”

---

## Paper 4: 2509.21766 — UltraHorizon: Benchmarking Agent Capabilities in Ultra Long-Horizon Scenarios
### Key primitives
- **Ultra-long-horizon eval harness**: three partially observable environments force sustained exploration, hypothesis testing, memory management, and tool use instead of short closed-book answers.
- **CRNR scaling**: *Context Refresh with Notes Recall* clears old dialogue near the context limit, keeps the system prompt, and rebuilds working state from self-maintained notes.
- **Two-level failure diagnosis**: separate root causes (**in-context locking** vs **foundational capability gaps**) from trajectory manifestations like repetitive looping, premature convergence, memory issues, uncontrolled experiments, and environment mis-modeling.
- **Step budget alone is not a strategy**: more turns often increase tool calls and context load without improving outcomes; humans still outperform frontier agents on these tasks.

### PlotLot implications
- Add **long-horizon site-feasibility evals** that require multi-stage authority discovery, ordinance retrieval, exception checking, calculator verification, and report revision over dozens of tool calls.
- Treat **notes/evidence ledgers** as the state backbone for long runs, then use CRNR-style context refresh instead of dragging one bloated transcript through the whole analysis.
- Instrument PlotLot traces with **failure tags** from this paper: premature convergence on the first zoning theory, uncontrolled experiments across conflicting ordinances, memory loss on prior parcel facts, and repetitive low-yield retrieval loops.
- Require an **evidence threshold before commit** so the harness cannot terminate early without enough cited ordinance support.

### Evaluation ideas
- Build a small UltraHorizon-style PlotLot suite where crucial facts are distributed across parcel pages, zoning maps, overlay rules, and ordinance sections.
- Compare **naive long-context runs** against **context-refresh + notes recall** runs on the same cases; measure citation coverage, tool-call efficiency, and final calculator agreement.
- Label failed traces with the paper's manifestation taxonomy and track rates of premature convergence, memory issues, and uncontrolled experimentation over time.
- Vary horizon budgets per case to find where PlotLot agents stop benefiting from extra steps and start accumulating context debt.

### Deltas
- Newly ingested from Paperclip-backed discovery and reviewed from full text cache.
- Added long-horizon evaluation guidance for PlotLot's site-feasibility harness.

### KG connections
- [[Context Refresh + Notes Recall]]
- [[Failure Manifestation Catalog]]
- [[Context Broker]]
- [[Evidence Ledger]]
- [[Workflow Verification]]

### Current synthesis
- UltraHorizon is the clearest newly ingested paper so far on how long-horizon agent failures compound as trajectories, tool calls, and partial observability increase.
- Its most transferable primitive for PlotLot is CRNR: reset active context and rebuild from durable notes/evidence instead of trusting one swollen transcript.
- Its biggest warning for PlotLot is evaluation realism: more steps alone do not solve hard site-feasibility cases unless the harness also enforces evidence thresholds and controlled hypothesis testing.

### Quotes
> "Once the accumulated interaction history approaches the model's context window limit, all prior dialogue turns are cleared except for the system prompt. Then, the agent is instructed to review its self-maintained notes..."

---

## Paper 5: 2512.16301v3 — Adaptation of Agentic AI: A Survey of Post-Training, Memory, and Skills
### Key primitives
- **Four-paradigm adaptation matrix**: the most useful systems distinction in the paper is not “memory vs skills” but **what gets adapted** and **what signal supervises it**:
- **A1** = adapt the agent with dense **tool-execution** signals.
- **A2** = adapt the agent with sparse **final-output** signals.
- **T1** = train agent-agnostic tools once, then reuse them.
- **T2** = freeze the backbone and adapt tools/subagents/memory under that backbone’s supervision.
- **T2 is the runtime-native path for memory and skills**: the paper explicitly frames most external memory systems, reflective databases, knowledge graphs, skill libraries, and lightweight planners/searchers as **tool adaptation**, not weight adaptation. That matters because it shifts the product surface from “better base model” to “better surrounding system.”
- **Skill memory hierarchy**: the paper synthesizes memory into **case-based → strategy-based → skill-based** accumulation. Raw trajectories are not the end state; mature systems distill them into reusable procedures and then executable capabilities.
- **Procedural memory lifecycle**: skills are described as a lifecycle of **acquisition → representation → invocation → refinement**. For harness design, that means skills need storage, interfaces, retrieval rules, and update policies—not just prompt snippets.
- **Graduation path**: a narrow expert learned under A1/A2 can later be **frozen and redeployed as a T1 tool**. The paper calls out this “graduated subagent” pattern explicitly (e.g. learned search/code specialists becoming reusable modules).
- **Federation path**: the survey’s strongest systems claim is that mature agent architectures trend toward **frozen foundation models at the center with evolving T1/T2 specialists around them**, because this preserves modularity and limits forgetting.
- **Adaptation-signal design is a first-class systems choice**:
- Dense execution signals are causal and diagnostic, but narrow.
- Holistic output signals reflect user value, but hide credit assignment.
- Good systems need both, because high A1 scores can still fail synthesis and high A2 scores can still hide shortcutting.
- **Evaluation must be dynamics-aware, not endpoint-only**: the paper argues for tracking sample efficiency, interaction efficiency, entropy/collapse, forgetting, reward hacking, and cost/safety/alignment trajectories—not just final accuracy.
- **T2 benchmark gap**: the survey makes a useful negative claim: we still lack standardized evaluations that cleanly compare “adapt the agent” vs “adapt the tool” on matched tasks and matched backbones.

### PlotLot implications
- PlotLot should adopt **T2 as the default adaptation posture** for its agentic vertical:
- keep the main orchestrator stable,
- evolve peripheral specialists for ordinance search, zoning extraction, evidence review, and memory curation.
- Treat PlotLot’s most valuable agent components as **trainable peripherals, not monolithic prompt changes**:
- `ordinance_searcher`
- `section_ranker`
- `dimensional_rule_extractor`
- `conflict_resolver`
- `evidence_reviewer`
- `feasibility_report_reviewer`
- Build a deliberate **graduation pipeline**:
- experimental specialist starts as a prompt lane,
- once it is measurable and reliable, train/refine it with narrow feedback,
- then freeze it behind a typed workflow/tool interface.
- Use the paper’s signal split to engineer PlotLot’s harness:
- **A1-style signals** for mechanistic lanes: citation resolution, ordinance section retrieval quality, parser/schema correctness, deterministic calculator reproducibility.
- **A2/T2-style signals** for end-to-end outputs: feasibility memo usefulness, conflict resolution quality, recommendation quality, analyst acceptance.
- The survey strengthens the case for an **evidence-centered harness**: if T2 modules are optimized to serve a frozen agent, the interface between them must be explicit. For PlotLot that interface should be typed evidence packets, not free-form transcript sprawl.
- For land-use/site-feasibility specifically, the best long-term architecture is:
- stable planner/orchestrator,
- repo-owned workflow modules,
- evolving retrieval/memory/review specialists,
- deterministic calculators as execution oracles.

### Evaluation ideas
- Build a **signal-ladder eval suite** for PlotLot:
- Level 1: ordinance retrieval Recall@k / section-hit rate
- Level 2: extraction schema validity / citation grounding / unit normalization
- Level 3: deterministic feasibility recomputation from stored evidence
- Level 4: final report quality / analyst preference / revision rate
- Run an **A2 vs T2 architecture study** for the same vertical tasks:
- monolithic report-writing agent with giant context
- frozen orchestrator + specialized retrieval/extraction/review subagents
- compare accuracy, token cost, edit distance after human review, and failure localization.
- Measure **graduation readiness** for specialist modules:
- stability across model backbones,
- interface adherence,
- marginal utility when swapped into the main harness,
- failure-rate reduction after freezing as a reusable tool.
- Add **dynamics metrics** to the harness eval stack:
- interaction count per run
- unsupported-claim rate over time
- replay consistency
- stale-memory carryover
- approval-trigger frequency
- cost-conditioned accuracy
- Add a **T2 counterfactual evaluation**: hold the orchestrator fixed and compare baseline vs adapted ordinance searcher / evidence reviewer / memory writer so the marginal value of each tool module is measurable.

### Deltas
- Compared with **Memory for Autonomous LLM Agents (2603.07670v1)**, this paper is broader and more architectural: it explains where memory sits in the overall adaptation design space instead of only how memory itself is structured.
- Compared with **Externalization in LLM Agents (2604.08224v1)**, this survey adds a sharper optimization taxonomy. Externalization explains *why* the runtime matters; this paper explains *which component you should update* and *what supervision signal should drive it*.
- Compared with **MemSkill (2602.02474v1)**, this paper is less mechanistic but more useful for harness planning: it places learned memory operations inside a wider T2 systems strategy.
- Compared with **AgentSPEX (2604.13346v1)**, this paper is weaker on workflow representation but stronger on adaptation strategy selection. AgentSPEX says how to encode workflows; this survey says where ongoing improvement should live once the workflow exists.

### KG connections
- [[Agent-Supervised Tool Adaptation]]
- [[Adaptation Signal Design]]
- [[Graduated Subagent]]
- [[Workflow Module Interface]]
- [[Evidence Ledger]]

### Current synthesis
- This is the clearest reviewed paper so far on where adaptation should live in an agentic system.
- For PlotLot, its most important consequence is strategic: freeze the orchestrator, and improve the surrounding retrieval, memory, review, and evidence modules.
- Use dense execution signals wherever possible inside the land-use harness, and reserve holistic judging for truly end-to-end synthesis quality.

### Quotes
> “Memory and skills are thus two facets of the same adaptation mechanism. Memory provides the storage substrate and organizational structure; skills provide the executable, composable content that makes that storage actionable for future tasks.”

> “The prevailing design trend thus points toward hybrid systems: frozen foundation models at the center, surrounded by a modular set of T1/T2 subagents trained for specific procedural roles...”

---

## Paper 6: 2601.10338v1 — Agent Skills in the Wild: An Empirical Study of Security Vulnerabilities at Scale
### Key primitives
- Large-scale security measurement of agent skills:
  - collected **42,447** skills; analyzed **31,132** deduped skills.
- Finds **26.1%** of skills contain ≥1 vulnerability across **14 patterns** in 4 categories:
  - prompt injection
  - data exfiltration
  - privilege escalation
  - supply-chain risks
- Prevalence highlights (from abstract): data exfiltration and privilege escalation are most prevalent; **5.2%** high-severity patterns suggest malicious intent.
- Risk factor: skills bundling executable scripts are **~2.12×** more likely to be vulnerable.
- Introduces **SkillScan** detection framework:
  - multi-stage pipeline combining static scanning + LLM semantic classification.
  - reported performance: **86.7% precision**, **82.5% recall** on manually annotated ground truth.

### PlotLot implications
- If PlotLot supports skills/plugins beyond core repo, treat this paper as a hard warning:
  - default posture should be **deny-by-default + least privilege**.
- Apply SkillScan-like gates to PlotLot components:
  - skills (runbooks)
  - connector adapters
  - any sandbox scripts
- Strongly separate tool scopes:
  - zoning/site analysis agents should not have email/CRM write tools.
  - external-write tools require explicit approvals and manifests.
- Prefer “hybrid skill” design:
  - NL runbook + deterministic scripts + strict IO schemas
  - keep script execution behind sandbox and tiered trust.

### Evaluation ideas
- Build a PlotLot “skill/connector SAST” suite:
  - detect exfil patterns (secrets reads, env var dumps, curl/post to unknown hosts)
  - detect privilege escalation patterns (sudo, broad filesystem enumeration)
  - detect prompt-injection patterns in referenced docs
- Maintain a “vulnerability taxonomy” adapted to PlotLot tool surface and log prevalence over time.

---

## Paper 7: 2601.10971v2 — AJAR: Adaptive Jailbreak Architecture for Red-teaming
### Key primitives
- Frames modern safety as **action security** (persistent state + tools + autonomous loops), not just content moderation.
- Identifies a gap: jailbreak frameworks are often monolithic scripts, while agent harnesses lack runtime primitives for **rollback**, **tool simulation**, **strategy switching**, and **branch pruning**.
- Proposes **AJAR**: a red-teaming framework that exposes multi-turn jailbreak algorithms as **callable MCP services**, orchestrated by an **Auditor Agent** inside a tool-aware runtime (Petri).
- Integrates 3 attacks under a shared service interface:
  - **Crescendo** (gradual semantic escalation)
  - **ActorAttack** (actor-role chains)
  - **X-Teaming** (layered search: plan → optimize question → revise plan)
- Key runtime primitives used by the Auditor:
  - transcript **rollback** (e.g., rollback after refusal / transcript repair)
  - branch pruning / candidate management
  - synthetic tool injection / environment alteration
- Reports behavior-level outcomes (per abstract + text):
  - improves X-Teaming ASR on HarmBench validation split
  - gains depend heavily on **rollback_conversation** events
  - tools reshape attack surface non-monotonically (some attacks degrade due to tool interruptions)

### PlotLot implications
- PlotLot needs **agent-native security evaluation** because it will ingest untrusted inputs:
  - ordinance text (prompt injection risk)
  - Gmail/CRM content (malicious instructions)
  - Drive PDFs (hidden prompts)
- Add a “red-team skill” (dev-only) that can:
  - simulate tool calls
  - inject adversarial content
  - test whether governance gates block unsafe actions
- Adopt AJAR’s runtime primitives conceptually:
  - **tool simulation** mode for tests
  - **rollback / transcript repair** for evaluation runs
  - strategy switching (different defenses) and branch pruning

### Evaluation ideas
- Build PlotLot security suites that mirror AJAR’s methodology:
  - multi-turn attacks that attempt to cause `send_email`, `update_crm`, or `export_report` without approval
  - injection attacks embedded in ordinance chunks and emails
  - measure interception rate, unsafe continuation under policy drift, and recovery success
- Add tooling to record "security trajectories" (tool calls + policy decisions) as artifacts.

---

## Paper 8: 2602.02474v1 — MemSkill: Learning and Evolving Memory Skills for Self-Evolving Agents
### Key primitives
- Reframes agent memory ops (extract/consolidate/prune) as **learnable, evolvable “memory skills”** instead of a fixed hand-coded pipeline.
- Architecture:
  - **Controller** selects a small Top-K set of memory skills conditioned on current span + retrieved memories.
  - **Executor (LLM)** applies selected skills to produce structured memory updates.
  - **Designer** periodically mines hard cases where memory updates were wrong/incomplete and proposes skill refinements + new skills.
- Closed-loop improvement:
  - controller trained with RL (reported PPO-style), designer updates skill bank, snapshots + rollback to prevent regressions.
  - uses a hard-case buffer to focus evolution on failure modes.

### PlotLot implications
- PlotLot shouldn’t have “one memory system”; it should have **typed memory skills**, e.g.:
  - `jurisdiction_quirk_capture` (ArcGIS field mismatch, municipal overlay gotchas)
  - `evidence_conflict_digest` (GIS vs ordinance disagreement)
  - `user_preference_update` (asset type, risk tolerance)
  - `project_state_compaction` (shortlist/eliminations/open questions)
- Start manual/heuristic selection, then evolve toward a controller:
  - simple routing rules first (by skill + workflow stage)
  - later: learned selection over a skill bank using eval feedback.
- Adopt the paper’s “designer loop” as your **failure-ratchet process**:
  - collect hard cases from real runs → refine memory write rules → add new memory skills.

### Evaluation ideas
- Memory evals specific to PlotLot:
  - follow-up Q/A across sessions (did we retain jurisdiction quirks?)
  - correction retention (does a human correction persist and prevent repeats?)
  - compaction stability (do summaries preserve decision-relevant state?)
- Create a hard-case buffer from:
  - mis-zoned parcels
  - missing overlays
  - conflicting ordinance excerpts
  - stale source citations

---

## Paper 9: 2602.06025v1 — Learning Query-Aware Budget-Tier Routing for Runtime Agent Memory
### Key primitives
- Introduces **BudgetMem**: a runtime agent-memory framework that makes the performance↔cost trade-off explicit.
- Organizes memory as **modules**, each available at **Low/Mid/High** budget tiers.
- Adds a lightweight **router** that performs **query-aware budget-tier routing** (trained with RL) to select which tiers to run.
- Studies three ways to realize “tiers”:
  - **Implementation**: method complexity (cheap heuristics vs expensive pipelines)
  - **Reasoning**: inference behavior (light vs deep reasoning)
  - **Capacity**: model size for memory operations
- Reports improved accuracy-cost frontiers vs baselines on long-memory benchmarks.

### PlotLot implications
- PlotLot needs explicit **context/memory budgets** per request and per stage:
  - LOW: quick follow-up, show current project summary + last evidence
  - MID: add relevant jurisdiction/site memories + top ordinance chunks
  - HIGH: full retrieval + rerank + conflict checks + report validator + reviewer pass
- Implement budget routing in the **ContextBroker**:
  - route by intent (router → lane), risk level, and user tier
  - route by workflow stage (site search vs final memo)
- This gives predictable latency/cost and enables OSS/local models to be competitive by using them in LOW/MID tiers.

### Evaluation ideas
- For each skill (zoning_research, site_selection, outreach_ops), measure **accuracy vs cost frontier**:
  - accuracy proxies: zoning field correctness, citation coverage, unsupported-claim rate
  - cost: tokens, tool calls, elapsed time
- Add tests for router correctness:
  - simple prompts must select LOW/MID
  - final report generation must select HIGH

---

## Paper 10: 2602.12430v3 — Agent Skills for Large Language Models: Architecture, Acquisition, Security, and the Path Forward
### Key primitives
- Skills are **composable packages** (SKILL.md + scripts + references/assets) loaded via **progressive disclosure**.
- Skills and MCP are **orthogonal layers**:
  - Skills = “what to do” (procedure, interpretation, fallbacks)
  - MCP = “connectivity” (standardized access to tools/data)
- Highlights empirical security findings:
  - **26.1%** of community-contributed skills contain ≥1 vulnerability.
  - skills bundling executable scripts are **~2.12×** more likely to contain vulnerabilities.
- Proposes **Skill Trust & Lifecycle Governance Framework** with:
  - **Verification gates (G1–G4)**
    - G1: static pattern matching + dependency scanning
    - G2: LLM-based intent mismatch / semantic classification
    - G3: behavioral sandbox execution + side-effect audit
    - G4: validate a permission manifest (declared vs observed capabilities)
  - **Trust tiers (T1–T4)** mapped to permissions (least privilege):
    - T1: unvetted → instructions-only, no tool access
    - T2: community-reviewed → read-only tools / user confirm, no code exec
    - T3: org-vetted → declared tools only, scoped files, no network
    - T4: vendor-certified → full capabilities (tools + code exec + network)
  - **Lifecycle trust evolution** (monitor → promote/demote/revoke)
- Open challenges called out include: cross-platform portability, skill routing at scale, composition/orchestration, capability-based permissions, testing/verification, and evaluation methodology for skill ecosystems.

### PlotLot implications
- Treat PlotLot skills as **first-class, repo-owned artifacts** (runbooks + scripts), and keep MCP as an adapter layer.
- Implement “Skill Trust Tiers” for PlotLot’s internal/external skills:
  - internal skills (T3/T4) can access expensive tools/sandbox
  - external/community skills (if ever allowed) start at T1/T2 with strict isolation
- Add **capability manifests** for skills/tools:
  - required connectors
  - allowed file paths
  - network egress requirements
  - write scopes (internal vs external)
- For user-facing governance, mirror the tier behavior with **approval modes**:
  - zoning/site research: read-only by default
  - outreach (Gmail/Calendar/CRM) requires explicit approvals and manifests

### Evaluation ideas
- Security evals:
  - prompt-injection via SKILL.md / referenced docs
  - hidden “do not ask again” / permission escalation patterns
  - tool exfiltration attempts
- Skill quality metrics (beyond task completion):
  - reusability, composability, maintainability, portability across model gateways
- CI gates for skills (PlotLot version of G1–G4):
  - static linting of skill manifests
  - sandbox execution of scripts
  - permission manifest validation

---

## Paper 11: 2602.16069v2 — The Limits of Long-Context Reasoning in Automated Bug Fixing
### Key primitives
- Empirical claim: agentic performance improvements often come from **short-context decomposition**, not true long-context reasoning.
- In SWE-bench Verified:
  - successful trajectories usually stay under ~**20k–30k tokens**.
  - longer accumulated context correlates with **lower success rates**.
- Even with “perfect recall” (relevant files injected to inflate context to 64k), single-shot patch generation **degrades sharply**.
- Observed failure modes under long context include:
  - hallucinated diffs
  - wrong file targets
  - malformed patch headers
- Conclusion: nominal context length ≠ usable context capacity; benchmarks may not test long-context reasoning meaningfully.

### PlotLot implications
- Do not build PlotLot workflows that rely on dumping:
  - all ordinance chunks
  - all emails/CRM notes
  - all prior runs
  into one prompt.
- Implement strict **context brokerage**:
  - select only the minimum evidence needed for the current stage
  - compress prior runs into structured state (shortlist, risks, open questions)
  - isolate subagents with role-specific context
- Prefer retrieval + staged workflows:
  - zoning: retrieve a handful of relevant sections → extract structured fields → validate
  - site selection: per-site deep dives in parallel, then synthesize

### Evaluation ideas
- Add a “context budget” regression suite:
  - tests should fail if prompts exceed intended budgets without measurable gains.
- Measure token counts per stage and correlate with success:
  - flag workflows that grow context without improving accuracy/citation coverage.

---

## Paper 12: 2602.19672v1 — SkillOrchestra: Learning to Route Agents via Skill Transfer
### Key primitives
- **Skill Handbook** is the core abstraction: an explicit routing artifact containing
  1) mode-level execution insights,
  2) a fine-grained skill registry, and
  3) per-agent profiles with competence, routing signals, and cost.
- A **skill** is represented as a natural-language capability description plus contextual indicators for when it applies; this separates capability requirements from specific model identities.
- **Agent profiles** store per-skill success estimates, mode-specific cost, and routing notes; the paper models competence with Beta posteriors and routes on competence-minus-cost utility.
- **Inference-time routing** is two-stage and stateful:
  - choose the next operational mode (`search`, `code`, `answer`, etc.)
  - infer active skills for the current state, then choose the agent with the best expected competence/cost trade-off.
- **Skill discovery is contrastive**: the handbook is learned from execution traces by comparing successful vs failed trajectories at the same mode and abstracting the missing capability into a reusable skill.
- **Skill refinement matters**: they split skills when performance variance suggests hidden subskills, and merge skills when agent-performance profiles are statistically indistinguishable.
- **Granularity-aware handbook selection** is a key systems claim: more skills are not always better; the best handbook depends on what the orchestrator can reliably distinguish under a cost budget.
- Empirical claims from full-paper results:
  - up to **+22.5** absolute accuracy over Router-R1 in model-routing tasks
  - about **700x** lower learning cost than Router-R1 and **300x** lower than ToolOrchestra
  - on FRAMES agent orchestration, **84.3%** accuracy at **$72.7** vs ToolOrchestra’s **76.3%** at **$92.7**
  - trained in a **low-data regime** (`k < 50` samples per dataset for handbook construction, plus `k` for validation/retrieval)
- The paper directly measures and reduces **routing collapse**: RL routers overuse one expensive model, while handbook-guided routing spreads calls across specialized models/tools.
- The learned handbook is **transferable across orchestrator backbones without retraining**, which is more practical than repeatedly RL-tuning a router when the model pool changes.

### PlotLot implications
- PlotLot should route on **capabilities**, not on one global “best model” heuristic. The relevant unit is a site-feasibility skill lane: authority discovery, ordinance retrieval, OCR/table extraction, dimensional normalization, conflict arbitration, deterministic calculation, and report synthesis.
- The direct PlotLot analogue to the paper’s Skill Handbook is a repo-owned **land-use routing handbook** with:
  - mode-selection rules for what to do next,
  - reusable skill definitions for each stage,
  - per-agent/per-tool performance and cost stats grounded in eval traces.
- We do **not** need RL to start. We can learn useful routing priors from replayed PlotLot traces and eval failures:
  - successful vs failed ordinance retrieval runs
  - successful vs failed zoning extraction runs
  - successful vs failed citation/review runs
- The paper’s strongest warning for PlotLot: **more granularity can hurt** if the orchestrator cannot reliably classify the active skill. Start with a coarse handbook, then split only when evidence shows that a finer distinction improves accuracy or cost.
- PlotLot should treat **routing collapse** as a first-class failure mode:
  - same expensive model used for nearly every step
  - same extractor used even when confidence is low
  - same retrieval path used despite poor citation yield
- Agent profiles map cleanly to PlotLot’s vertical:
  - `jurisdiction_resolver`
  - `ordinance_locator`
  - `table_extractor`
  - `dimensional_normalizer`
  - `conflict_reviewer`
  - `report_synthesizer`
  Each should accumulate skill-conditioned success/failure and cost signals.

### Evaluation ideas
- Reproduce the paper’s ablations for PlotLot routing:
  - no handbook
  - handbook without refinement
  - handbook without selection
  - handbook without fine-grained skills
- Add a **routing-collapse dashboard** for the land-use harness:
  - agent/model selection ratio by stage
  - expensive-agent share of calls
  - cost per successful cited extraction
- Build **contrastive trace pairs** from eval replays:
  - same parcel/jurisdiction, successful vs failed retrieval
  - same ordinance section, accurate vs inaccurate extraction
  - same report task, cited vs unsupported synthesis
- Score agent profiles with vertical metrics, not only final answer quality:
  - citation coverage
  - unsupported-claim rate
  - unit-normalization correctness
  - deterministic calculator agreement
  - wall-clock cost by stage
- Test handbook transfer by keeping the same routing handbook while swapping orchestrators or specialist models.

### KG connections
- [[Skill Handbook]]
- [[Competence-Cost Agent Profile]]
- [[Contrastive Skill Discovery]]
- [[Granularity-Aware Handbook Selection]]
- [[Harness Runtime]]

### Current synthesis
- This is the clearest reviewed paper so far on replacing end-to-end router training with an explicit, reusable routing knowledge base.
- For PlotLot, its biggest architectural consequence is to route by capability lanes backed by trace-derived evidence, not by one static default model per stage.
- Its most important warning is granularity: a richer skill taxonomy only helps if the orchestrator can reliably classify active skills and use the distinction to improve cost or accuracy.

### Quotes
> “More skills are not always better; optimal performance-cost trade-offs require refining and selecting skills to match the orchestrator’s capability.”

---

## Paper 13: 2602.20867v1 — SoK: Agentic Skills -- Beyond Tool Use in LLM Agents
### Key primitives
- Defines **agentic skills** as reusable callable modules packaging:
  - procedural knowledge
  - applicability conditions
  - execution policies
  - termination criteria
  - reusable interfaces
- Covers full lifecycle: discovery → practice → distillation → storage → composition → evaluation → update.
- Introduces 2 complementary taxonomies:
  1) **Seven design patterns** for how skills are packaged/executed (e.g., metadata-driven progressive disclosure, executable code skills, self-evolving libraries, marketplace distribution).
  2) **Representation × scope** taxonomy:
     - representation: natural language, code, policy, hybrid
     - scope: web, OS, software engineering, robotics, etc.
- Security/governance focus:
  - supply-chain risks, prompt injection via skill payloads, trust-tiered execution.
  - case study: **ClawHavoc** marketplace compromise (~1,200 malicious skills) exfiltrating API keys, wallets, browser creds.
- Evaluation note: curated skills can improve pass rates substantially; self-generated skills can degrade reliability.

### PlotLot implications
- Treat “skills” as a formal layer in PlotLot (not just prompts):
  - each skill has activation conditions + termination + output schema.
- Adopt **trust tiers** for any skill content:
  - PlotLot internal skills (reviewed) vs external skill packs (if ever) with strict sandbox + no external writes.
- Use the representation×scope framing:
  - PlotLot should bias toward **hybrid skills**: NL runbook + deterministic scripts + typed outputs.
- If PlotLot ever supports a skill marketplace/registry, ClawHavoc implies:
  - signed distributions
  - dependency scanning
  - behavioral sandboxing
  - runtime monitoring + rapid revocation.

### Evaluation ideas
- Build PlotLot “skill quality” evals (separate from overall task completion):
  - reusability across jurisdictions
  - composability (zoning + environment + utility)
  - maintainability under source drift
  - security compliance (no tool escalation)
- Compare curated vs generated skill components:
  - do generated prompts/scripts increase unsupported-claim rate?
  - do curated runbooks reduce tool misuse?

---

## Paper 14: 2602.22480 — VeRO: An Evaluation Harness for Agents to Optimize Agents
### Key primitives
- **Versioned agent snapshots**: every optimizer change should become a discrete, diffable version so the trajectory can be replayed, compared, and rolled back instead of treated as one opaque “latest prompt.”
- **Budget-gated evaluation**: evaluation calls are a first-class budgeted resource; the harness must enforce limits rather than trusting the optimizer to self-police compute.
- **Structured observation interface**: optimizers need per-sample traces with inputs, outputs, intermediate behavior, errors, and scores presented through a consistent interface across scaffolds.
- **Instruction sensitivity is real**: simple target agents benefited from more prescriptive optimizer guidance, while stronger agents often did better with lighter instructions; the harness should expect optimizer-template variance, not one universally best prompt.
- **Prompt edits dominate by default**: current optimizers mostly tweak prompts instead of making tool/workflow changes, so a harness should explicitly surface when optimization collapses into shallow edits.

### PlotLot implications
- Treat every site-feasibility eval run as a **versioned artifact**: capture git commit, prompt versions, dataset slice, thresholds, and resulting metrics so zoning-quality regressions are attributable.
- Add **budget contracts** to offline evals and future optimization loops: case-count limits today, then tool/runtime/token caps as the vertical harness matures.
- Preserve **structured per-case observations** for parcel facts, ordinance citations, calculator outputs, and failure labels so future optimizer loops can improve retrieval/extraction/review modules from evidence instead of anecdotes.
- Avoid over-prescribing optimization for already-capable flows; evaluate prompt-only tweaks separately from structural retrieval/calculator/report changes and measure cross-jurisdiction transfer.

### Evaluation ideas
- Split the land-use/site-feasibility goldset into train/validation/holdout jurisdictions and compare prompt-only, retrieval, and calculator changes under identical budgets.
- Track whether an optimization improved one case family (e.g. Miami 21 or overlay-heavy parcels) while regressing on easier suburban zoning cases.
- Tag optimization phases by **prompt**, **tool**, **workflow**, or **review** changes to detect collapse into superficial prompt churn.
- Pair quality metrics with efficiency metrics so a “better” harness that doubles runtime or tool cost is visible as a tradeoff, not a silent win.

### Deltas
- Newly ingested from Paperclip-backed discovery and reviewed from full text cache.
- Findings translated into VeRO-style eval reproducibility for PlotLot’s site-feasibility harness.

### KG connections
- [[Versioned Agent Snapshot]]
- [[Budget-Gated Evaluator]]
- [[Structured Observation Interface]]
- [[Workflow Verification]]
- [[Replayable Trajectory]]

### Current synthesis
- VeRO is the clearest newly ingested paper so far on what an optimization-ready eval harness must preserve: versioning, budgets, permissions, reproducibility, and trace visibility.
- For PlotLot, its most immediate consequence is operational rather than model-centric: make every site-feasibility quality run attributable to an exact harness state and evidence slice.
- Its main warning is that optimizer behavior collapses toward prompt edits unless the harness exposes richer structural signals and compares changes under identical budgets.

### Quotes
> "All modifications to the target agent must be captured as discrete snapshots (e.g., Git commits), yielding the sequence A0, A1, . . . , AT. This enables rollback, diff inspection, and trajectory analysis."

---

## Paper 15: 2603.03329v1 — AutoHarness: improving LLM agents by automatically synthesizing a code harness
### Key primitives
- **Synthesized constraint harness**: instead of hand-writing every guardrail, the paper learns executable code around a base model. In the default setup, the harness has two functions: `propose_action(board)` and `is_legal_action(board, action)`, turning prompt-only “be valid” instructions into a deterministic accept/reject gate.
- **Execution-feedback harness refinement**: harness generation is framed as tree search over programs. The system keeps multiple code hypotheses, uses Thompson sampling to pick which one to refine next, and feeds failed environment steps plus critic feedback back into the refiner.
- **Learn the boundary, not just the policy**: the most transferable idea is that many agent failures come from violating environment constraints, so improving the executable boundary around the model can matter more than upgrading the model itself.
- **Per-environment specialist synthesis**: on 145 structured TextArena games, the learned action-verifier harness reached **100% legal-action success rate** for every game. Training ended after **14.5 search iterations on average**, and **19/32** eval games converged in fewer than 10 iterations.
- **Smaller model + better harness can beat larger model**: Gemini-2.5-Flash with the learned harness achieved **0.745** average reward on 16 1-player games vs **0.707** for Gemini-2.5-Pro and **0.673** for vanilla Flash. On 16 2-player games, the harnessed Flash beat Pro overall (**56.3%** win rate vs **38.2%**).
- **Compiled deterministic specialist**: in the stronger harness-as-policy setting, the paper synthesizes the whole policy in code. That code-only policy reached **0.870** average reward on 16 1-player games, beating GPT-5.2-High (**0.844**) with near-zero test-time cost after training.
- **Scope limitation matters**: the result is strongest for bounded environments with crisp legality feedback. The paper excludes 9 free-form dialog games, learns one harness per game, and mostly demonstrates legality filtering and narrow policy compilation rather than open-ended workflow orchestration.

### PlotLot implications
- Use AutoHarness as a pattern for **narrow land-use specialists**, not for the whole site-feasibility workflow. The best fit is bounded lanes with crisp failure signals: citation parsing, unit normalization, ordinance table extraction, allowed-use eligibility checks, setback/FAR calculator inputs, and schema validation.
- Turn recurring analyst-reviewed failures into **synthesis targets**. If PlotLot repeatedly sees the same failure class—bad citation formatting, wrong unit conversion, unsupported dimensional claim—that failure log should become repair data for a deterministic wrapper or verifier.
- Add **constraint code in front of expensive synthesis**. Before a report claim survives, run synthesized or hand-frozen verifiers that check official-source provenance, citation resolvability, unit compatibility, and calculator reproducibility.
- Treat successful narrow specialists as **compiled modules**. Once a verifier/parser/calculator is stable enough, freeze it behind a typed interface and stop paying LLM inference cost for that subproblem.
- Keep the scope disciplined: unlike games, land-use analysis has ambiguous language, conflicting authorities, and soft interpretation. So PlotLot should synthesize code around **well-bounded subproblems** and keep the open-ended orchestration, ambiguity handling, and analyst collaboration in the main harness.

### Evaluation ideas
- Create an **AutoHarness-style failure corpus** from PlotLot traces: unsupported claim, bad ordinance citation, wrong jurisdiction, malformed dimension extraction, unit mismatch, calculator non-reproducibility.
- Compare **prompt-only vs verifier-wrapped extraction** for a few narrow lanes, e.g. raw LLM setback extraction vs LLM + executable citation/unit/schema validator.
- Run a **compiled-specialist ablation**: for stable tasks such as FAR math, density math, unit conversion, and ordinance table normalization, measure quality/cost before and after replacing live LLM reasoning with frozen deterministic modules.
- Track whether synthesized specialists improve **output survival**: do more generated claims survive analyst review into the final site-feasibility memo when the harness inserts narrow deterministic checks first?
- Measure **specialist transfer limits** across jurisdictions. The paper learns one harness per game; PlotLot should test whether a compiled rule parser transfers across code publishers or whether it needs publisher-specific / jurisdiction-family-specific variants.

### Deltas
- Compared with **AgentSPEX (2604.13346v1)**, AutoHarness is much less about authoring an explicit workflow language and much more about synthesizing executable guardrail code from failure traces.
- Compared with **SafeHarness (2604.13630v1)** and **ALARA (2603.20380v1)**, this paper is weaker on permissions and policy semantics but stronger on automatically constructing narrow deterministic enforcement logic around a model.
- Compared with **Adaptation of Agentic AI (2512.16301v3)**, AutoHarness provides a concrete mechanism for adaptation at the periphery: improve the system by learning specialized wrappers/modules instead of retraining the backbone.
- Compared with **Meta-Harness (2603.28052v1)**, AutoHarness searches over much narrower code objects. Meta-Harness optimizes whole harnesses; AutoHarness is strongest when compiling local validity logic or small policies.

### KG connections
- [[Synthesized Constraint Harness]]
- [[Compiled Deterministic Specialist]]
- [[Workflow Verification]]
- [[Agent-Supervised Tool Adaptation]]
- [[Graduated Subagent]]

### Current synthesis
- AutoHarness is the clearest reviewed paper so far on turning repeated invalid-action failures into executable code constraints instead of stronger prompt admonitions.
- For PlotLot, its best use is synthesizing narrow deterministic wrappers—citation, unit, schema, and calculator verifiers—around unstable LLM lanes rather than synthesizing the whole site-feasibility workflow.
- Its main limitation is scope: one harness per environment with crisp legality feedback, so it says more about bounded specialist compilation than about full-product autonomy.

### Quotes
> “In this work, we propose ‘code as harness’, a framework where the LLM itself completes the agent by coding its own harness.”

> “The harness can be seen as a control loop that calls the LLM and rejects unacceptable answers. The definition of what is acceptable is itself learned.”

---

## Paper 16: 2603.07670v1 — Memory for Autonomous LLM Agents:Mechanisms, Evaluation, and Emerging Frontiers
### Key primitives
- Formalizes agent memory as a **write–manage–read loop** embedded in the agent cycle:
  - read function `R(M_t, x_t)` and update/manage function `U(M_t, x_t, a_t, o_t, r_t)`.
- Proposes 5 design objectives (often in tension): **utility**, **efficiency**, **adaptivity**, **faithfulness**, **governance**.
- Unified taxonomy along 3 orthogonal axes:
  - **Temporal scope**: working / episodic / semantic / procedural memory.
  - **Representational substrate**: context-resident text; vector-indexed stores; structured stores (SQL/KV/KG); executable repositories (skills/code); hybrids.
  - **Control policy**: heuristic control; prompted self-control (memory ops as tools); learned control (memory ops as RL actions).
- Surveys 5 mechanism families:
  - context-resident compression/compaction
  - retrieval-augmented memory stores
  - reflective self-improvement
  - hierarchical virtual context (paging-style)
  - policy-learned memory management
- Evaluation:
  - argues classical IR metrics (Precision@k/nDCG) are insufficient for agent memory.
  - highlights newer benchmarks: **LoCoMo**, **MemBench**, **MemoryAgentBench**, **MemoryArena**.
  - proposes a practical **4-layer metric stack** culminating in governance (privacy leakage, deletion compliance, access-scope violations).
- Engineering realities emphasized:
  - write-path filtering thresholds
  - staleness/contradictions/drift
  - latency/token budgets
  - privacy governance
  - multi-agent shared-memory boundaries + concurrent-write consistency
  - tool/API memory needs versioning (schema drift)

### PlotLot implications
- PlotLot should treat memory as an explicit subsystem, not “long context”:
  - hybrid memory store (structured DB + embeddings + file artifacts) with an inspectable audit trail.
- Map the paper’s temporal scope to PlotLot state:
  - working: current run context window
  - episodic: tool-call logs + intermediate artifacts + evidence ledger events
  - semantic: stabilized project facts (parcel attributes, constraints, assumptions)
  - procedural: reviewed skills/runbooks for feasibility workflows
- Implement governance as first-class memory requirements:
  - write-path filtering (only store facts with evidence pointers)
  - deletion + access-scope controls per workspace/client
  - contradiction handling (do not silently overwrite; keep competing claims with provenance)
- For multi-agent delegation (planner → specialists), adopt role-based access to shared memory (summary vs raw documents).

### Evaluation ideas
- Build PlotLot memory evals aligned to the proposed stack:
  - task effectiveness: feasibility accuracy/coverage
  - memory quality: stale/contradictory recall rate; evidence coverage
  - efficiency: token + latency overhead of memory ops
  - governance: privacy leakage checks; deletion compliance; access-scope violations
- Benchmark scenarios:
  - multi-session project evolution (requirements change; zoning updates)
  - schema drift (data source/API changes) and “memory invalidation” behavior
  - selective forgetting (remove outdated assumptions and ensure they stop influencing decisions)

---

## Paper 17: 2603.18829v9 — Agent Control Protocol: Admission Control for Agent Actions
### Key primitives
- Problem: agents can produce **harmful behavioral patterns over time** even when each individual request/tool call is “valid”; per-request stateless policy engines can’t enforce trace-level properties.
- Proposes **ACP (Agent Control Protocol)**: **temporal admission control** for agent actions.
  - Combines **static risk scoring** with **stateful signals** (pattern/anomaly accumulation, denial rate, cooldown timers).
  - Enforces deterministic, history-aware blocking (hard boundary), not advisory anomaly alerts.
- Introduces **LedgerQuerier** abstraction: separates decision logic from state backend (enables backend swap; keeps decision function stateless).
- Addresses **cross-context state mixing** by scoping signals to **PatternKey(agentID, capability, resource)** (ACP-RISK-3.0).
- Adds **BAR-Monitor (Boundary Activation Monitoring)** to detect regime shifts / deviation collapse earlier.
- Strong “systems” posture:
  - high throughput/low latency admission decisions
  - formal spec + invariants/temporal properties (TLA+) + conformance vectors

### PlotLot implications
- Implement ACP-like admission control in PlotLot’s **tool governance layer**, especially for side-effectful tools:
  - Gmail send
  - Calendar create/update
  - CRM writes
  - bulk parcel searches
  - sandbox execution
  - report publishing/export
- Use a **ledger** keyed by (workspace_id, project_id, agent_role/skill, tool_name, resource) to avoid state mixing across projects.
- Add **cooldown / escalation** behavior:
  - after repeated denied actions or policy boundary probes, temporarily block further external writes
  - force human approval / “review mode”
- Make admission control deterministic and inspectable:
  - each denial records the risk factors + trace context
  - users can see why a tool is blocked (trust + auditability)

### Evaluation ideas
- Reproduce the paper’s core claim in PlotLot terms:
  - create a workload where each tool call is individually “allowed”, but the sequence is risky (e.g., repeated outreach or repeated attempts to export sensitive docs)
  - show stateless policy approves all; ACP-like control blocks after threshold
- Regression tests for state mixing:
  - high-volume safe tool calls in one project should not elevate risk for another project when PatternKey scoping is correct
- Governance metrics:
  - denial escalation curves
  - cooldown activation correctness
  - false rejection rate (“over-blocking”)

---

## Paper 18: 2603.20380v1 — ALARA for Agents: Least-Privilege Context Engineering Through Portable Composable Multi-Agent Teams
### Key primitives
- Introduces a **declarative Context–Agent–Tool (CAT) data layer**: filesystem-organized config that *structurally* scopes each agent’s **context** + **tool access** to the minimum required (ALARA principle applied to agent context).
- Implements CAT via **npcsh** (shell + API server + desktop app) and “Jinx lists” (tool catalogs/permission sets).
- Central argument: behavioral specs are fragmented across prose prompts + framework configs + MCP servers; CAT makes them **portable, versionable, enforceable**.
- **Structural enforcement beats interpretive prompts**: tools not present in schema “do not exist” for the agent, reducing prompt injection / privilege escalation risk.
- Empirical results across **22 local models** (0.6B–35B) and **2,530 task executions**:
  - Tool-use reliability is a distinct capability; models trained for tool use can outperform larger untrained models.
  - **Tool call volume** correlates strongly with agentic performance (reported as stronger predictor than duration/attempt count).
  - ~80% of successes happen on first attempt; retries help unevenly across task categories; delegation is hardest.

### PlotLot implications
- Treat **agent manifests** (context + tool allowlist) as first-class repo assets:
  - `docs/agents/zoning_analyst.yaml`, `environmental_analyst.yaml`, `outreach_agent.yaml`, etc.
- Enforce least-privilege structurally:
  - zoning/env agents should not even have Gmail/CRM-write tools available.
  - outreach agent should not have ordinance extraction tools.
- Keep tool catalogs small per role (paper reports performance degradation as tool catalog size grows).
- Use CAT-like files to make PlotLot’s harness behavior **shareable across teams** and **stable across model swaps**.

### Evaluation ideas
- Create PlotLot “CAT compliance” tests:
  - prove restricted agents cannot invoke disallowed tools (even with prompt injection).
- Track the paper’s suggested leading indicators:
  - first-attempt success rate vs retry gain by task category
  - tool-call volume vs success for each workflow (zoning lookup, site screen, outreach)
- Explicitly test delegation/subagent workflows (paper flags delegation as hardest across models).

---

## Paper 19: 2603.21019v1 — SkillProbe: Security Auditing for Emerging Agent Skill Marketplaces via Multi-Agent Collaboration
### Key primitives
- Motivation: skill marketplaces introduce new risks:
  - **semantic–behavioral inconsistency** (declared purpose vs actual behavior)
  - **inter-skill combinatorial risks** (benign skills combine into malicious behavior)
- Proposes **SkillProbe**: multi-stage **security auditing** framework using **multi-agent collaboration**.
- “**Skills-for-Skills**” paradigm: each auditing phase is packaged as a standardized skill module (Markdown prompts + scripts), enabling extensibility without changing core framework.
- Architecture layers:
  - Input layer (ingest/preprocess)
  - Agent layer (lead orchestrator + specialists)
  - Skill layer modules (Gatekeeper admission filtering; Alignment intent/behavior checks; combinatorial simulation)
  - Output layer (structured security reports)
- Large-scale audit results (ClawHub top 2,500 skills):
  - popularity is not a security proxy; high download counts still fail audits
  - only ~10% fully “clean” in their reported breakdown
  - high-risk skills form a **giant connected component** → cascaded risk is systemic

### PlotLot implications
- Even without a public skill marketplace, PlotLot has a similar surface:
  - internal skills + connector adapters + (future) partner tools
- Adopt SkillProbe ideas for PlotLot governance:
  - **admission filtering** for new connectors/skills (static checks + manifests)
  - **intent/behavior alignment**: does a tool/skill do what it claims?
  - **combinatorial simulation**: test multi-skill workflows for emergent bad outcomes (e.g., zoning + outreach)
  - provenance and trust tiers (do not equate usage with safety)
- Treat connectors as “skills” that must pass gates before being enabled in production workspaces.

### Evaluation ideas
- Build a PlotLot “skill/connector audit suite”:
  - manifest consistency (declared scopes vs observed tool calls)
  - cross-skill scenario tests (combinatorial): ensure no chain results in unsafe external writes without approvals
  - popularity-security paradox tests: do not skip checks based on “trusted” labels

---

## Paper 20: 2603.22148v1 — OpenEarth-Agent: From Tool Calling to Tool Creation for Open-Environment Earth Observation
### Key primitives
- Problem framing: open-environment Earth Observation has **heterogeneous data + tasks**; fixed tool catalogs don’t generalize.
- Introduces **OpenEarth-Agent**: a **tool-creation** agent framework (not just tool-calling).
  - Uses adaptive workflow planning + tool creation to handle unseen data/tasks.
  - Integrates multi-stage tools + cross-domain knowledge bases.
- Introduces **OpenEarth-Bench**: 596 real-world full-pipeline cases across 7 domains, designed to test adaptive planning + tool creation.
- Key reported result: tool-creating agent with a small essential model set can match/beat tool-calling agents that depend on large predefined tool catalogs; created tools can be more robust to anomalies.

### PlotLot implications
- PlotLot’s “open environment” analogue is **new counties/jurisdictions with novel GIS schemas**.
  - A fixed set of hand-written adapters will not scale.
- Implement a **Connector Adapter Factory**:
  - discover candidate parcel/zoning datasets (ArcGIS Hub)
  - generate a mapping/adapter in a sandbox
  - validate against gold fixtures
  - promote only with admin approval
- Keep “tool creation” constrained:
  - generated adapters are code artifacts, not model guesses
  - require evidence + provenance and a rollback path

### Evaluation ideas
- Build a PlotLot version of OpenEarth-Bench:
  - “open county” cases where the system must discover datasets + map fields + return parcel+zoning correctly.
  - measure: adapter success rate, time-to-adapter, false positives, evidence quality.
- Compare:
  - fixed adapters only vs discovery-only vs discovery+generated adapters.

---

## Paper 21: 2603.25723v1 — Natural-Language Agent Harnesses
### Key primitives
- Proposes **Natural-Language Agent Harnesses (NLAHs)**: harness control logic expressed as editable natural language, intended to be portable/inspectable instead of buried in controller code.
- Proposes **Intelligent Harness Runtime (IHR)** that *executes* NLAHs using:
  1) an **in-loop LLM** interpreter (reads harness + state + environment + charter),
  2) a **backend** (tools + multi-agent interface),
  3) a **runtime charter** (shared semantics: contracts/state/orchestration/child lifecycle).
- Makes harness patterns explicit as first-class modules:
  - **Contracts** (required IO, validation gates, permission boundaries, retry/stop rules)
  - **Roles** (solver/verifier/researcher/orchestrator)
  - **Stage structure** (plan → execute → verify → repair)
  - **Adapters/scripts** (deterministic hooks: tests, verifiers, retrieval, parsing)
  - **State semantics** (durable artifacts/ledgers; path-addressable; compaction-stable)
  - **Failure taxonomy** (named failure modes driving recovery)
- Studies a **file-backed state module** to stabilize long-horizon runs: externalized, path-addressable, compaction-stable artifacts.

### PlotLot implications
- Encode PlotLot’s “harness logic” as **repo-owned runbooks** (skills) + a small “runtime charter”:
  - `skills/zoning_research/SKILL.md` (lane logic)
  - `skills/site_selection/SKILL.md`
  - `harness/charter.md` (global semantics: budgets, evidence requirements, approval rules)
- Treat zoning/site-feasibility workflows as explicit **stage graphs**:
  - gather facts → retrieve ordinance → extract rules → validate/evidence → compute → report → reviewer
- Make durable artifacts the primary interface:
  - evidence ledger, run logs, scorecards, report versions
- Add explicit failure taxonomy to reduce “mushy retries”:
  - geocode_failed, parcel_not_found, ordinance_no_hits, extraction_low_confidence, conflicting_sources, tool_timeout

### Evaluation ideas
- Do controlled ablations like the paper:
  - with/without file-backed state
  - with/without explicit verifier/reviewer stage
  - with/without failure taxonomy
- “Migration” eval: can PlotLot’s current hardcoded pipeline be represented as a skill/runbook with equivalent behavior?

---

## Paper 22: 2603.28052v1 — Meta-Harness: End-to-End Optimization of Model Harnesses
### Key primitives
- Thesis: LLM system performance depends on **weights + harness code** (what to store/retrieve/present, how to orchestrate tools/loops).
- Introduces **Meta-Harness**: an **outer-loop search** over harness *code*.
  - Uses an agentic **coding proposer** with access to a filesystem containing prior candidates’ **source code + scores + execution traces**.
  - The proposer decides what to inspect (grep/cat) and makes algorithmic edits (retrieval/memory/prompt/orchestration), not just prompt tweaks.
  - Each candidate harness logs: prompts, tool calls, model outputs, state updates.
  - Search objective can be **multi-objective** (e.g., accuracy vs context cost), reported via Pareto frontier.
- Key finding (per abstract): harness search can improve accuracy while using fewer context tokens; raw trace access matters more than lossy summaries.

### PlotLot implications
- PlotLot should treat **harness iteration** as a productized engineering loop:
  - store run traces (tool runs, evidence, report validation outcomes)
  - keep harness code + configs versioned
  - run eval suites after every change
- Build the minimal prerequisites for Meta-Harness-style improvement:
  - deterministic eval harness + gold sets
  - structured traces (agent steps, tool args/results, evidence coverage)
  - parameterized context broker (budgets, retrieval policies) that can be tuned.
- This is basically the “Ralph loop” but **grounded in traces + eval scores**.

### Evaluation ideas
- Define PlotLot harness objectives:
  - zoning extraction accuracy
  - citation/evidence coverage
  - unsupported-claim rate
  - runtime/cost
- Run controlled harness variants (manual first):
  - different retrieval + rerank strategies
  - different memory budgets (low/mid/high)
  - different report validators (strict vs lenient)
  - different subagent decompositions
- Later: implement an automated proposer loop (CI job) that proposes safe diffs to context broker/skill prompts and validates against gold sets.

---

## Paper 23: 2603.29199v1 — AEC-Bench: A Multimodal Benchmark for Agentic Systems in Architecture, Engineering, and Construction
### Key primitives
- Defines **AEC-Bench**: a multimodal benchmark for agentic systems in Architecture/Engineering/Construction.
- Task families include:
  - drawing understanding
  - cross-sheet reasoning
  - project-level coordination
- Emphasizes **harness effects**: evaluates not just models, but model+base-harness combos (e.g., Claude Code, Codex) and identifies tools/harness techniques that improve across models.
- Releases dataset + harness + evaluation code for replicability.

### PlotLot implications
- PlotLot needs a **domain benchmark** analogous to AEC-Bench but focused on:
  - parcels + zoning + overlays
  - site feasibility scoring
  - document/survey/site-plan interpretation
  - evidence-backed report generation
  - outreach workflow correctness (email/calendar/CRM)
- Benchmark should be **multimodal** (PDF plats, surveys, zoning letters, GIS screenshots), not just text.
- Use the benchmark to compare:
  - different harness designs (skills vs monolith)
  - different context broker strategies
  - different model gateways

### Evaluation ideas
- Create `plotlot-bench/` with suites:
  - `parcel_lookup.jsonl`
  - `zoning_extraction.jsonl`
  - `overlay_conflict.jsonl`
  - `report_citation_validation.jsonl`
  - `doc_understanding_multimodal.jsonl`
- Measure harness-improving “universal techniques”:
  - structured tool IO
  - verifier/reviewer stages
  - evidence ledger enforcement
  - sandbox isolation

---

## Paper 24: 2604.03610v1 — DebugHarness: Emulating Human Dynamic Debugging for Autonomous Program Repair
### Key primitives
- **Signature-driven initialization / playbooks**: parse an incident signature (e.g., crash/vuln class) and inject error-class-specific troubleshooting guidelines + explicit “rules of engagement” (e.g., require hypothesis + dynamic verification before edits).
- **Interactive state introspection**: treat runtime state as first-class context (debugger queries, memory/heap inspection), not just static docs/code.
- **Deterministic replay / time-travel debugging**: reversible execution (e.g., `rr`) to locate the origin of corruption and avoid expensive restarts.
- **Static↔dynamic bridge**: map runtime frames/symbols → source locations via LSP/clangd for precise navigation.
- **Context compaction**: debuggers produce huge outputs; use structured distillation (and optionally sandboxed scripts over raw output) to extract signal while keeping context bounded.
- **Closed-loop patching/validation**: patch → rebuild → rerun PoC + tests; feed failures back into the loop.
- **Deterministic patch correction**: auto-repair malformed diffs to avoid wasted LLM iterations.
- **Tool abstraction + guardrails**: standardized tool protocol (e.g., MCP/JSON-RPC) + command validation to reduce hallucinated tool calls.

### PlotLot implications
- **Incident-class playbooks for land-use workflows**: treat “case type” as a signature (e.g., zoning research vs site screening vs outreach) and load the smallest, strictest runbook/tools for that case.
- **Interactive evidence introspection**: mirror “debugger queries” with **evidence queries** (pull ordinance sections, GIS attributes, prior tool runs) and require evidence-backed claims before report writing.
- **Deterministic replay for analysis runs**: persist tool inputs/outputs so a run can be replayed, diffed, and audited (helps evidence ledger + regression tests).
- **Context compaction as a core service**: ordinance/GIS payloads will be huge; we need first-class compaction that produces: (a) citations, (b) extracted rule candidates, (c) open questions.
- **Closed-loop verification**: every analysis skill should end with deterministic checks (schema validation, citation completeness, scoring reproducibility) analogous to “rebuild + tests”.

### Evaluation ideas
- **Harness eval**: given a known zoning question + corpus, does the agent (a) retrieve the right ordinance sections, (b) extract rules into a schema, (c) attach citations, and (d) refuse to claim facts without evidence?
- **Replay/regression**: record a full analysis run (tool traces + evidence) and ensure future code/model changes reproduce the same extracted structured rules (within tolerance).
- **Context compaction quality**: measure whether compaction preserves required fields/citations while reducing tokens.

### Quotes
>

---

## Paper 25: 2604.07833v2 — Harnessing Embodied Agents: Runtime Governance for Policy-Constrained Execution
### Key primitives
- Argues **runtime governance** is a first-class systems problem once agents can execute actions.
- Proposes a separation of concerns:
  - **Agent cognition**: understand task, plan, propose capability invocations.
  - **Runtime governance layer**: *capability admission*, *policy checking*, *execution monitoring/watchers*, *intervention*, *rollback/recovery*, *human override*, *audit logging*.
- Key design move: governance layer mediates **structured capability invocation requests** (not free-form text) and decides what may execute “now”, under environment-specific policy profiles.
- Intervention outputs include `{continue, pause, stop, rollback, handover}` (conceptually), enabling recoverable long-horizon execution.
- Empirical simulation results (per abstract): high interception of unauthorized actions; reduced unsafe continuation under drift; high recovery success with policy compliance.

### PlotLot implications
- Implement PlotLot tool execution as **policy-constrained execution**:
  - Model can *propose* tool calls; runtime decides admission/approval.
  - Treat every external connector action (Gmail/Calendar/CRM) as a “capability” with:
    - required scopes
    - risk level
    - rollback semantics (often none)
    - environment profile (dev vs prod; sandboxed vs live)
- Add watcher-style controls:
  - budgets (token/tool call), timeouts, rate limits, max breadth for bulk searches
  - “drift” detection: if sources conflict (GIS vs ordinance) or data is stale, pause and request human review.
- Require **audit trails** for every tool call + decision (approved/blocked/rolled back) and store in evidence ledger.

### Evaluation ideas
- Build governance tests similar to the paper’s dimensions:
  - unauthorized tool calls should be intercepted (e.g., zoning analyst attempting `send_email`).
  - drift cases: changing policy mid-run (e.g., turn off external writes) should halt unsafe continuation.
  - recovery: simulate connector failures/timeouts and verify fallback + safe termination.
  - over-blocking: measure false-rejection rate for legitimate tool calls.

---

## Paper 26: 2604.08224v1 — Externalization in LLM Agents: A Unified Review of Memory, Skills, Protocols and Harness Engineering
### Key primitives
- **Externalization lens**: agent progress increasingly comes from reorganizing the *runtime* around models (externalizing cognitive burdens into **Memory**, **Skills**, **Protocols**, coordinated by the **Harness**).
- **Harness as cognitive environment** (not “plumbing”): the harness is the designed environment that makes externalized modules jointly effective.
- **Six harness dimensions** (Figure 7):
  - Externalization modules: **Memory** (state persistence, cross-session context), **Skills** (reusable routines, staged loading, failure-driven revision), **Protocols** (structured invocation, schemas/contracts)
  - Operational surfaces: **Permission** (sandboxing, filesystem/network restrictions), **Control** (step/recursion bounds, cost ceilings, timeouts), **Observability** (structured logs, traces, aggregate metrics)
- **Protocols are first-class**: they externalize interaction discipline; memory/skills only become operational when actions cross boundaries via inspectable/auditable/recoverable contracts.
- **Control flow matters**: production harnesses bound recursion/tool loops (max steps, depth, budgets) to avoid runaway trajectories.
- **Sandboxing is more than security**: isolation simplifies the environment, improves reproducibility/rollback, and reduces irrelevant state exposure.

### PlotLot implications
- Use this paper’s “six dimensions” as the **checklist for PlotLot’s harness runtime**:
  - Memory: workspace/project/site/jurisdiction memories + retrieval policies
  - Skills: repo-owned runbooks + staged loading
  - Protocols: typed tool IO + evidence contracts + (later) MCP adapter
  - Permission: approval gates + sandbox for risky/heavy ops (PDF parsing, bulk GIS joins)
  - Control: max turns, timeouts, cost budgets, recursion depth, batch limits
  - Observability: tool/model run traces, evidence lineage, evaluation metrics
- Treat “protocol discipline” as why we should build an **Ordinance Intelligence API** (search/get_section/extract_rules/validate_claim), rather than letting models browse Municode.
- Design the web/CLI UI as an **execution dashboard** (status, evidence count, open questions, approvals), not just chat.

### Evaluation ideas
- Harness ablations: compare
  - (A) pure RAG chat vs (B) skills + evidence ledger vs (C) skills + evidence + governance + sandbox.
- Metrics aligned to the six dimensions:
  - Permission: tool-denial/approval rate, policy violations intercepted
  - Control: runaway loop rate, time-to-completion, cost per run
  - Observability: citation coverage %, unsupported-claim rate, trace completeness
  - Memory: retrieval hit rate, correction retention, stale-memory incidents

---

## Paper 27: 2604.11378v1 — From Agent Loops to Structured Graphs:A Scheduler-Theoretic Framework for LLM Agent Execution
### Key primitives
- Frames the typical **agent loop** as a **single-ready-unit scheduler**:
  - at any moment only one executable unit is active
  - “which unit runs next” is chosen by opaque LLM inference rather than an inspectable scheduling policy
- Identifies 3 structural weaknesses of agent loops:
  - **implicit dependencies** between steps
  - **unbounded recovery loops** (retry/replan can spin indefinitely)
  - **mutable execution history** (harder debugging/attribution)
- Proposes **SGH (Structured Graph Harness)**: lift control flow into an explicit **static DAG** with 3 commitments:
  1) **Plan-version immutability** (the (V,E) structure is fixed for the duration of a plan version)
  2) **Three-layer separation** (planning vs execution vs recovery)
  3) **Bounded recovery** via a strict **escalation protocol** (cannot skip levels)
- Provides a formal spec:
  - per-node state machine
  - termination + soundness guarantees under explicit assumptions
- Positions the work as a design/position paper (protocol + evaluation design), not a production implementation.

### PlotLot implications
- For PlotLot’s vertical (land-use/site feasibility), SGH maps well to reproducible multi-step workflows:
  - plan: declare DAG of subtasks (parcel facts → zoning extraction → constraints → max units → risk flags → outputs)
  - execute: deterministic scheduler drives ready nodes; parallelize independent checks (zoning vs env vs utilities)
  - recover: structured retry/patch/replan ladder avoids “agent spirals” and supports auditability
- Adopt **immutable plan versions** as the backbone for:
  - replay/debug (why did we claim X?)
  - evidence linkage (which source supported which node output)
  - governance (policy checks at node boundaries)
- Treat “planner quality” as a first-class concern:
  - if planner degenerates to a linear chain, you still get escalation + audit, but lose parallelism benefits
  - add a “plan quality validator” (e.g., must expose at least N parallelizable nodes when applicable)

### Evaluation ideas
- Compare loop vs SGH-style execution on PlotLot tasks:
  - controllability: bounded retries, max wall-clock, max tool calls
  - debuggability: can we attribute a wrong claim to a node + evidence?
  - reproducibility: replay the same plan version and compare deltas
  - utility/cost: success rate vs latency/token/tool-call budget
- Failure-injection tests for recovery escalation:
  - poisoned tool output (prompt injection in ordinance text)
  - missing/contradictory zoning sections
  - API timeouts and schema drift

---

## Paper 28: 2604.11548v1 — SemaClaw: A Step Towards General-Purpose Personal AI Agents through Harness Engineering
### Key primitives
- Argues “**harness engineering**” (not prompt engineering) is the differentiator for production agents at OpenClaw scale.
- **Two-layer architecture**:
  - `sema-code-core`: reusable event-driven agent runtime (context lifecycle, tool orchestration, isolation)
  - `semaclaw`: application framework on top of the runtime
- **DAG Teams**: a two-phase hybrid orchestration approach:
  - phase 1: an orchestrator agent emits an explicit **DAG** of subtasks (agentName, prompt, dependsOn) via a single structured call
  - phase 2: a deterministic scheduler (**DispatchBridge**) executes the DAG (dependency checks, timeouts, failure isolation)
  - emphasizes “LLM decides who” but binding is deterministic (exact string match to registered agents) for auditability
- **PermissionBridge** behavioral safety system:
  - unified pause/approve mechanism for (a) tool permission requests and (b) agent-asked user questions
  - **two-tier tool policy**: internal tools pre-authorized; external tools require per-invocation consent (least privilege)
  - bridge is globally scoped across concurrent sessions; multiplexes approvals by request id
- **Three-tier context management** (plus knowledge infra):
  - working memory: in-context history + **automatic compaction** (triggered at 75% of context; emits compact events; truncation fallback)
  - external memory: persistent MEMORY.md + rolling daily logs; **hybrid retrieval** (FTS5 BM25 + vectors) with degradation fallback
  - structured injection: persona partitioning (SOUL.md “who the agent is” vs workspace context “what this task is”)
  - adds a **wiki-based user-owned knowledge layer** (Markdown tree + YAML) to persist distilled knowledge beyond logs
- Practical engineering details worth copying:
  - retrieval exposed as MCP tool (`memory_search`) under agent control
  - hybrid retrieval scoring and graceful degradation when vector search unavailable
  - scheduled tasks stratified into 4 execution modes (notification, script, agent, hybrid script+agent)

### PlotLot implications
- Architecture: strongly supports PlotLot’s stance (backend authoritative, shells as channels):
  - a reusable runtime core (job runner + context + tool mediation) + app-specific “skills/workflows”.
- Orchestration: adopt the **plan (declare DAG) → run (deterministic scheduler)** split for multi-step feasibility:
  - parallelize specialist agents (zoning, env, utilities, comps) with explicit dependencies and reproducible runs.
- Governance: PermissionBridge maps cleanly to PlotLot tool governance:
  - treat internal reads (DB/query) as pre-authorized
  - require approval for external writes (email, CRM, file changes in regulated workspaces)
- Context: mirror the three-tier model:
  - working context + compaction (with reinjection of constraints)
  - external memory store (hybrid retrieval) for project history + evidence ledger
  - structured injection for project/workspace rules (jurisdiction profiles, client constraints)
- Knowledge: the wiki layer suggests a PlotLot “jurisdiction + parcel knowledge base”:
  - human-legible, versionable artifacts (Markdown/JSON) that agents can retrieve and cite.

### Evaluation ideas
- DAG Teams evaluation:
  - debuggability (can we replay a run and reproduce subtask boundaries?)
  - failure isolation (downstream behavior when an upstream task errors)
  - context growth (orchestrator context should not balloon with worker traces)
- PermissionBridge evaluation:
  - friction vs safety: approval rate, denial recovery quality, timeouts
  - policy invariants: no external write without explicit approval
- Context/memory evaluation:
  - compaction correctness (constraint reinjection, summary drift)
  - hybrid retrieval quality + degradation fallbacks
  - staleness/contradiction handling in persistent memory

---

## Paper 29: 2604.13018v1 — Toward Autonomous Long-Horizon Engineering for ML Research
### Key primitives
- Long-horizon agent performance is framed as a **systems problem**, not just a reasoning problem: agents need both **structured orchestration** and **durable state continuity**.
- The paper’s core mechanism is a **permission-scoped File-as-Bus workspace** where agents coordinate through files instead of lossy conversational handoffs.
- AiScientist separates **thin control over thick state**:
  - the top-level orchestrator carries only concise summaries plus a compact workspace map
  - specialists re-ground on durable artifacts like paper analyses, plans, code, logs, and experiment outputs
- The workspace is explicitly split into role-aligned regions:
  - `paper_analysis/` for structured paper understanding
  - `submission/` for the runnable repo and setup scripts
  - `agent/` for plans, implementation logs, experiment logs, and detailed run outputs
- Results are strong on both replication and iterative-improvement benchmarks:
  - on PaperBench, AiScientist beats the best matched baseline by about **10–11 points** on average
  - on MLE-Bench Lite, it reaches **81.82 Any Medal%**
- The critical ablation is File-as-Bus removal:
  - **-6.41** PaperBench points
  - **-31.82** Any Medal points on MLE-Bench Lite
- The paper’s strongest mechanistic claim is that durable artifacts matter most for **later-round refinement**, not just for getting to a minimally valid first submission.
- Hierarchical specialization still matters after ablating File-as-Bus, so the takeaway is **artifact continuity + specialist orchestration**, not “just add more turns.”

### PlotLot implications
- PlotLot should treat site-feasibility as a **long-horizon engineering workflow** with durable case state, not as a single chat session.
- Adopt a File-as-Bus analogue for each parcel/project:
  - intake + parcel facts
  - jurisdiction/authority resolution
  - ordinance retrieval artifacts
  - extraction outputs
  - deterministic calculator outputs
  - review notes
  - final report artifacts
- Keep orchestrator context thin:
  - stage summary
  - open questions
  - workspace map
  - current evidence gaps
  instead of dragging full transcript history through every step.
- Use specialist lanes for PlotLot’s actual vertical work:
  - authority discovery
  - ordinance retrieval
  - extraction/normalization
  - deterministic dimensional calculations
  - conflict arbitration
  - evidence-backed report review
- Permission-scoped writes matter for governance: retrieval agents should not silently mutate report conclusions, and report-writing agents should not be the source of raw evidence.
- The paper supports designing PlotLot around **later-round refinement**: once a case is runnable end-to-end, most value will come from preserving intermediate evidence and iterating on weak stages rather than restarting analysis from scratch.

### Evaluation ideas
- Build a held-out site-feasibility benchmark with long-horizon cases that require: official-source discovery, ordinance retrieval, extraction, calculator execution, and contradiction resolution.
- Run an ablation like the paper:
  - full PlotLot harness
  - same harness without durable case workspace/state
  - simpler single-agent baseline
- Measure not just “valid report produced” but later-round quality metrics:
  - citation completeness
  - contradiction resolution rate
  - deterministic calculator agreement
  - revision quality after failed first-pass analyses
- Add a resume-from-artifacts test: kill the active context mid-run, restart from saved workspace artifacts, and verify the case can continue without replaying the whole conversation.

### KG connections
- [[File-as-Bus Workspace]]
- [[Progressive Disclosure Workspace Map]]
- [[Harness Runtime]]
- [[Evidence Ledger]]
- [[Replayable Trajectory]]

### Current synthesis
- AiScientist is the clearest reviewed paper so far on durable state continuity as the backbone of long-horizon engineering work.
- Its most transferable PlotLot pattern is a parcel-centric artifact bus: preserve evolving evidence, plans, code/calculator outputs, and review notes so hard cases can be resumed and refined instead of restarted.
- Its biggest warning is operational: later-round refinement collapses without saved intermediate state, so transcript-only case handling will underperform exactly where difficult site-feasibility work gets interesting.

### Quotes
> “strong long-horizon performance requires both structured orchestration and durable state continuity.”

---

## Paper 30: 2604.13151v1 — Exploration and Exploitation Errors Are Measurable for Language Model Agents
### Key primitives
- The paper contributes a **policy-agnostic error metric** that classifies action failures from trajectories alone, without needing the agent’s internal policy or one reference path.
- In their environment, **exploration error** is far more predictive of success than exploitation error:
  - success vs exploration error: **R² = 0.947**
  - success vs exploitation error: **R² = 0.006**
- Their main empirical claim is simple and important: in partially observed tasks, agents often fail because they **do not discover enough of the problem space**, not because they only exploit poorly.
- A lightweight harness that externalizes state acts like an **explicit memory system**. The injected summary includes:
  - visited cells
  - reachable frontier cells
  - obstacle cells
  - discovered states and prerequisites
  - activated states
  - currently activatable states
- That explicit state summary materially improves performance:
  - Gemini 3.1 Flash Lite success rises **51.9% → 88.9%**
  - GPT-4.1 success rises **63.0% → 92.6%**
  - both models also reduce exploration/exploitation error and successful-path length
- The paper also shows that **semantic priors are not uniformly helpful**: the same semantic information can improve one model’s exploration while biasing another toward premature exploitation.
- The most transferable harness lesson is that open-ended agent evaluation should score **behavioral failure modes**, not just final task success.

### PlotLot implications
- PlotLot should explicitly separate **exploration failures** from **exploitation failures** in site-feasibility runs.
  - exploration failure = the harness keeps searching low-yield sources, misses the governing authority, or never discovers the decisive ordinance section
  - exploitation failure = the harness has enough evidence in hand but still makes the wrong synthesis, misses a dependency, or commits a conclusion before prerequisites are satisfied
- Add a PlotLot memory summary patterned after the paper’s harness:
  - official sources already verified
  - authority/frontier sources still worth checking
  - ordinance sections already discovered
  - unresolved dimensional questions
  - facts whose prerequisites are satisfied and are ready for deterministic calculation or report inclusion
- Treat “activatable state” in PlotLot as a claim whose prerequisites are complete:
  - official source verified
  - citation captured
  - units normalized
  - conflicting evidence resolved enough for downstream calculation/reporting
- The paper strengthens the case for **frontier-aware retrieval** in land-use analysis: the harness should know what it has already searched, what remains plausible, and when exploration is exhausted.
- Do not trust semantic priors like “this looks like a residential lot” or “this ordinance section is probably the right one” without evidence gates; the paper shows semantics can also push agents into myopic behavior.

### Evaluation ideas
- Add trace labels to PlotLot evals:
  - redundant retrieval loop
  - missed authority discovery
  - premature conclusion before evidence prerequisites
  - wrong conflict-resolution path despite sufficient evidence
- Score each case with separate metrics for:
  - authority/source exploration quality
  - evidence frontier coverage
  - exploitation quality once decisive evidence is available
  - end-to-end report correctness
- Benchmark a memory-summary ablation:
  - baseline transcript-only agent
  - agent with explicit frontier/evidence summary
  - agent with frontier summary + activatable-claims checklist
- Create partially observed jurisdiction tasks where the decisive ordinance host is not obvious from parcel metadata, then test whether the harness can explore enough before synthesizing.

### KG connections
- [[Exploration-vs-Exploitation Error Ledger]]
- [[Frontier + Activatable-State Summary]]
- [[Workflow Verification]]
- [[Failure Manifestation Catalog]]
- [[Context Broker]]

### Current synthesis
- This paper is the clearest reviewed source so far on separating discovery failures from synthesis failures in partially observed agent tasks.
- For PlotLot, its most practical consequence is to maintain an explicit frontier/ready-state summary so the harness knows which sources still need discovery and which claims are mature enough for downstream calculation or reporting.
- Its biggest warning is that semantic intuition is unreliable: domain priors can help some models and hurt others, so PlotLot must gate conclusions on evidence completeness rather than plausibility.

### Quotes
> “Low exploration error rates are a strong predictor of success.”

---

## Paper 31: 2604.13346v1 — AgentSPEX: An Agent SPecification and EXecution Language
### Key primitives
- **Executable workflow spec, not controller code**: AgentSPEX moves harness logic into YAML with explicit control flow and a small typed vocabulary (`task`, `step`, `if/switch`, `while`, `for_each`, `call`, `parallel/gather`, `set_variable`, `increment`, `input`, `return`). The paper’s core claim is that many long-horizon agent patterns can be expressed declaratively without editing Python orchestration code.
- **Explicit context scoping**: the paper’s most important primitive is the `task` vs `step` split. `task` starts a fresh conversation; `step` continues a persistent conversation. Combined with `save_as` variables and Mustache templating, this makes context injection an explicit harness decision instead of an emergent property of one growing transcript.
- **Unified workflow modules**: skills and agents are both represented as workflows, callable via `call` with parameters and return values. That collapses the “tool vs subagent vs skill” distinction into one reusable interface.
- **Interpreter + executor split**: the harness has an interpreter that validates workflow structure, resolves templates, manages nesting/scope, and assigns hierarchical step IDs; a separate executor runs the multi-turn LLM/tool loop for each `task`/`step` and mediates tool calls via MCP.
- **Durable execution**: checkpoints are saved after each completed step with completed step IDs, context variables, step metrics, and sandbox state. The paper also adds **selective trace replay**, so developers can change a downstream instruction without rerunning unchanged upstream work.
- **Sandboxed execution environment**: each workflow runs inside a Docker-based sandbox with browser, filesystem, and 50+ tools. This is useful, but the governance model is mostly allowlist/sandbox-oriented rather than policy-rich.
- **Verification as a harness affordance**: because control flow and variable dependencies are explicit, the paper argues that workflows can support static pre/post-condition checks and dynamic trajectory verification. Appendix C demonstrates this on a citation-extraction module using checks like `isValidFilePath`, `isValidBibtex`, and JSON-schema validation.
- **Measured gains come from enforced structure, not just better prompts**: across 7 benchmarks, AgentSPEX beats CoT/ReAct baselines, with notable gains on long-context or multi-step tasks (ChemBench **83.3%** vs ReAct **77.8%** / CoT **78.9%**; ELAIPBench **43.7%** vs CoT **37.2%** / ReAct **33.8%**). The important claim is that *executing* the workflow step-by-step outperforms merely pasting the workflow into a ReAct prompt.
- **Model-version robustness matters**: on SWE-Bench Verified, AgentSPEX averages **77.1%** and is much stabler across Claude-Opus-4.5/4.6 (**77.2% → 77.0%**, −0.2) than Live-SWE-agent (**78.0% → 71.2%**, −6.8), supporting the idea that decoupled workflow specs are easier to keep stable across model changes.
- **Interpretability tradeoff**: in the 23-person user study, AgentSPEX was preferred for readability and prompt clarity, but LangGraph was still preferred for some complex multi-step workflows. So the paper shows accessibility wins, not that DSLs automatically beat code for every advanced orchestration case.

### PlotLot implications
- Treat the land-use/site-feasibility harness as an **executable spec**: parcel intake → zoning retrieval → ordinance chunk selection → rule extraction → deterministic calculator → evidence validation → report synthesis → reviewer. This should live in repo-owned workflow artifacts, not be scattered across Python prompts and route handlers.
- Adopt **step-bounded context** aggressively. PlotLot should not carry the entire parcel record, ordinance corpus, comps context, and financial assumptions through one transcript. Use `task`-like fresh contexts for bounded extraction jobs and `step`-like continuity only inside a tightly scoped lane.
- Standardize every sub-agent as a **workflow module with typed IO**: `fetch_parcel_facts`, `retrieve_zoning_sections`, `extract_dimensional_rules`, `resolve_conflicts`, `run_feasibility_calc`, `draft_report`, `review_evidence`. This is a direct fit for the paper’s `call` abstraction.
- Add **checkpoint + replay** at stage boundaries. For PlotLot, replay should let us regenerate the extraction/review/report stages from saved parcel facts + ordinance evidence without redoing geocoding, GIS queries, or municipality retrieval.
- Recast formal verification into **site-feasibility verification**: preconditions like parcel geometry exists / jurisdiction identified / ordinance citation present; postconditions like extracted values are unit-normalized, every reported constraint has a citation, and calculator outputs are reproducible from evidence.
- The paper is weaker on governance than ACP / ALARA / SafeHarness, so PlotLot should combine AgentSPEX-style workflow specs with our stronger policy layer: read-only vs side-effecting tools, budget ceilings, evidence thresholds, and approval gates for external actions.
- The visual editor idea is useful for portfolio/product UX: a future operator console could expose PlotLot’s harness graph so analysts can inspect where a run failed (retrieval, extraction, verification, or valuation) instead of reading raw logs.

### Evaluation ideas
- Run an **AgentSPEX-style ablation** on PlotLot’s vertical: same prompts/tools, but compare (a) reactive single-loop orchestration vs (b) explicit staged execution with enforced step boundaries.
- Measure **context-boundary payoff**: extraction accuracy, token cost, and latency when ordinance retrieval/extraction gets only selected sections vs the whole ordinance transcript.
- Add **replay-resume benchmarks**: when a downstream prompt changes, measure how much work can be reused from checkpoints and whether the regenerated report stays consistent with the saved evidence ledger.
- Define **trajectory verification checks** for land-use runs: every numeric constraint must pass schema/unit validation, every cited ordinance section must resolve, and every density/output number must be recomputable by deterministic code.
- Track **model-version robustness** on the same harness spec across Sonnet/Gemini/Kimi routing changes. The paper’s SWE-Bench stability result is directly relevant to keeping PlotLot dependable as model providers shift.

### Deltas
- Compared with **Natural-Language Agent Harnesses (2603.25723v1)**, AgentSPEX is less free-form and more operationally concrete: it gives a small DSL, explicit state variables, and first-class loops/parallelism instead of relying on natural-language harness interpretation alone.
- Compared with **From Agent Loops to Structured Graphs (2604.11378v1)**, AgentSPEX is more authoring-oriented: it focuses on a human-editable workflow language and editor rather than primarily a scheduler-theoretic execution model.
- Compared with **SafeHarness (2604.13630v1)** and **ALARA (2603.20380v1)**, AgentSPEX contributes weaker policy/governance ideas. Its strengths are workflow specification, replayability, and context control—not least-privilege enforcement.
- Compared with **Architectural Design Decisions in AI Agent Harnesses (2604.18071v1)**, this paper is prescriptive rather than descriptive: it proposes one concrete harness architecture and shows that explicit workflow specs can improve both performance and maintainability.

### KG connections
- [[Executable Specification]]
- [[Step-Bounded Context]]
- [[Workflow Module Interface]]
- [[Replayable Trajectory]]
- [[Workflow Verification]]

### Current synthesis
- AgentSPEX is the clearest reviewed paper so far on converting harness logic into an executable, human-editable workflow spec.
- Its strongest contribution for PlotLot is not the YAML syntax itself, but the combination of explicit context boundaries, checkpointed execution, and replayable downstream experimentation.
- Its main gap relative to other reviewed governance papers is weak policy language; PlotLot should pair this workflow style with stronger approval and least-privilege controls.

### Quotes
> “A task starts a fresh conversation with no prior history, while a step accumulates conversation history across turns.”

> “With selective trace replay, the executor can load a specified number of steps from a prior trace and resume live execution, allowing developers to isolate the effect of a prompt or control-flow change on downstream behavior while holding upstream context constant.”

---

## Paper 32: 2604.13630v1 — SafeHarness: Lifecycle-Integrated Security Architecture for LLM-based Agent Deployment
### Key primitives
- Thesis: the **harness** is a high-value attack surface because it orchestrates tools/context/state; harness-level compromise cascades.
- Proposes **SafeHarness**: lifecycle-integrated security architecture with **4 defense layers** mapped to the agent lifecycle:
  1) **Adversarial context filtering** at input processing (L1)
  2) **Tiered causal verification** at decision making (L2)
  3) **Privilege-separated tool control** at action execution (L3)
  4) **Safe rollback + adaptive degradation** at state update (L4)
- Cross-layer mechanisms tie layers together:
  - escalate verification rigor under sustained anomalies
  - trigger rollbacks
  - tighten tool privileges dynamically
- Evaluates across diverse harness configurations + multiple attack scenarios.
- Uses explicit security/utility metrics:
  - UBR (unsafe behavior rate)
  - ASR (attack success rate)
  - utility metrics (task completion, utility under attack) + blocked actions

### PlotLot implications
- PlotLot should implement security as a **lifecycle system**, not a single “prompt filter”:
  - L1: input/tool-output filtering (prompt-injection scanning of ordinance text, emails, PDFs, web results)
  - L2: evidence-based claim verification (tie findings to evidence ledger; downgrade/flag unsupported claims)
  - L3: tool privilege separation (read-only vs external-write; capability manifests; ACP-style admission control)
  - L4: rollback + degradation (revert state changes; switch to safer mode; require human approval)
- Use “anomaly accumulation” signals to tighten policies (matches ACP + runtime governance papers):
  - repeated denied tool attempts
  - conflicting sources
  - stale evidence

### Evaluation ideas
- Implement SafeHarness-style attack scenarios for PlotLot:
  - context poisoning (task-level injection)
  - indirect injection (poisoned tool outputs)
  - tool tampering (argument escalation)
  - memory injection (fabricated history)
  - composite attacks
- Track UBR/ASR analogs in PlotLot:
  - unsafe external writes attempted
  - successful policy bypasses
  - blocked actions vs task utility

---

## Paper 33: 2604.14228v1 — Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems
### Key primitives
- An architecture study of **Claude Code** based on public TypeScript source, contrasted with OpenClaw.
- Core claim: agent systems are “simple loop + lots of surrounding systems”. The agent loop is a **while-loop**: call model → run tools → repeat.
- Identifies major surrounding subsystems:
  - **Permission system**: deny-first rule evaluation + **7 modes** + **ML-based classifier** + hook interception.
  - **Compaction pipeline**: **five-layer** context shaping; no single compaction strategy suffices.
  - **Extensibility**: 4 mechanisms — **MCP**, plugins, skills, hooks.
  - **Subagents**: delegation with **worktree isolation** and scoped context returns.
  - **State/persistence**: append-oriented session storage.
- Extensibility details:
  - MCP tools are merged into a flat tool pool; deny rules apply; built-ins win on name collisions.
  - plugins can bundle commands/agents/skills/hooks/MCP servers/LSP servers/output styles/etc.
  - skills inject domain instructions; hooks intercept lifecycle (pre/post tool use, compaction, etc.)
- Comparison insight: different deployment contexts drive different answers (per-action safety classification vs perimeter-level access control; CLI loop vs gateway control plane).

### PlotLot implications
- Treat this as a blueprint for PlotLot’s **CLI/TUI harness UX**:
  - show tool calls as first-class events (timeline/cards)
  - make approvals and permission mode explicit
  - show compaction and evidence state
- Adopt the same decomposition:
  - simple agent loop + strong surrounding systems (governance, compaction, extensibility, subagents, persistence)
- Permission system translation:
  - PlotLot should implement multiple “autonomy modes” for tools (read-only, ask-to-write, auto-with-approvals, etc.).
  - For PlotLot, external-write tools (Gmail/Calendar/CRM) should be highest-friction.
- Extensibility translation:
  - keep skills as repo-owned runbooks
  - use MCP as an adapter for external tool ecosystems
  - use hooks/middleware for policy + evidence enforcement

### Evaluation ideas
- Permission correctness:
  - block/approve matrix by mode
  - policy drift tests (runtime governance changes mid-run)
- Compaction quality:
  - token budgets per stage
  - summary preservation of key state (shortlist, risks, open questions)
- Extensibility safety:
  - ensure plugin/skill additions cannot bypass tool policies

---

## Paper 34: 2604.18071v1 — Architectural Design Decisions in AI Agent Harnesses
### Key primitives
- Empirical, source-grounded study of **70** public agent-system projects to surface recurring harness design decisions.
- Identifies **5 recurring design dimensions**:
  1) subagent architecture
  2) context management ("memory" + context handling)
  3) tool systems
  4) safety mechanisms
  5) orchestration
- Reported corpus trends:
  - context strategies favor **file-persistent**, **hybrid**, and **hierarchical** approaches (not purely in-context).
  - tool systems remain mostly **registry-oriented**; **MCP-first** and **plugin-oriented** extensions are emerging.
  - **intermediate isolation** is common; **high-assurance audit** (tamper-evident) is rare.
- Codes audit capability levels (approx distribution from text):
  - “No audit” is a large minority (~40%)
  - “Structured audit” is uncommon (~20%)
  - “Tamper-evident” is very rare (~5%)
- Co-occurrence findings (qualitative): deeper coordination pairs with explicit context services; stronger execution environments pair with structured governance; formal tool boundaries correlate with broader ecosystem ambition.
- Synthesizes 5 recurring architectural patterns (from lightweight tools → balanced CLI frameworks → multi-agent orchestrators → enterprise systems → verticalized projects).

### PlotLot implications
- Confirms PlotLot should prioritize non-LLM harness engineering:
  - explicit context service + persistence
  - strong tool registration boundary (MCP-first + internal registry)
  - structured audit logs as a first-class requirement (not an afterthought)
- PlotLot likely fits the “balanced CLI framework” / “scenario-verticalized” hybrid:
  - CLI/TUI for operators
  - backend job orchestration + evidence store
  - vertical domain constraints (land-use feasibility)
- Take the paper’s warning seriously: audit is usually weak in the wild → PlotLot can differentiate by shipping audit/evidence by default.

### Evaluation ideas
- Build an internal “harness decision checklist” aligned to the 5 dimensions; require explicit choices and tests for:
  - context persistence + compaction
  - tool boundary + discovery model
  - isolation level
  - audit capability (structured → tamper-evident)
  - orchestration style (single loop vs workflow)

---

## Paper 35: 2604.20779v1 — SWE-chat: Coding Agent Interactions From Real Users in the Wild
### Key primitives
- **In-the-wild trajectory corpus**: SWE-chat pairs real user prompts, full tool-use traces, checkpoints, and line-level human-vs-agent code attribution across ~6,000 sessions, 63,000 prompts, 355,000 tool calls, and 200+ public repos.
- **Real workflows are broader than patch generation**: understanding existing code is the top specific user intent (19.0%); create-code and git tasks are both 13.4%; agents spend roughly one third of tool calls in bash and another large share in read/edit/search loops.
- **Coding behavior is bimodal, not smoothly mixed**: 22.7% of sessions are human-only, 36.5% collaborative, and 40.8% vibe coding; vibe coding doubled over the three-month observation window.
- **Acceptance matters more than raw generation**: only 44.3% of total agent-authored code survives into commits, with the largest waste coming from human deletions and overwrites rather than successful direct landing.
- **Autonomy is expensive and safety-sensitive**: vibe coding reaches 59.0% coding efficiency / 64.6% survival rate, but costs ~204K tokens and $0.13 per 100 committed LOC, takes 12.6 minutes per 100 committed LOC, and introduces 0.76 Semgrep vulnerabilities per 1K LOC vs. 0.14 collaborative and 0.08 human-only.
- **Users provide the missing oversight**: agents ask clarifying questions in only 1.1%–2.6% of turns, while users interrupt 3.3%–6.0% of turns and push back after 39% of turns through corrections, rejections, and failure reports.

### PlotLot implications
- PlotLot should log **full analyst-agent trajectories**, not only final answers: parcel facts seen, ordinance/tool calls, intermediate claims, review events, and which claims/citations survive into the final feasibility memo.
- Add a **claim-survival layer** to the evidence ledger: measure whether agent-produced zoning claims are accepted, edited, overwritten, or deleted by analysts during review.
- Prefer **collaborative, evidence-gated operation** over pure vibe-style autonomy for site-feasibility work; the paper suggests fully autonomous output is currently costlier and riskier exactly where correctness matters.
- Install **clarification gates**: when authority resolution is incomplete, citations conflict, or extracted dimensional rules are under-specified, the harness should stop and ask for analyst input instead of pushing speculative conclusions forward.
- Treat analyst corrections, interruptions, and rejection reasons as **first-class telemetry** for improving PlotLot’s land-use specialists and review policies.

### Evaluation ideas
- Track **final-report survival** for every generated claim/citation/calculation: survived unchanged, agent self-rewrite, analyst overwrite, analyst deletion.
- Build a **pushback taxonomy dashboard** for PlotLot review loops: correction, rejection, failure report, interruption, and unsupported-claim flags by workflow stage.
- Compare **collaborative vs. high-autonomy** harness modes on acceptance rate, time-to-verified-report, and unsupported-claim rate across the same parcel set.
- Run a **Semgrep-style safety lane for feasibility outputs**: missing citation, non-official source, unit mismatch, unstated assumption, and unsupported zoning conclusion per report.

### KG connections
- [[Output Survival Metric]]
- [[User Pushback Telemetry]]
- [[Clarification Gate]]
- [[Structured Observation Interface]]
- [[Workflow Verification]]

### Current synthesis
- SWE-chat is the clearest reviewed source so far on how real users supervise, interrupt, correct, and partially accept coding-agent work in the wild.
- For PlotLot, its most transferable primitive is acceptance telemetry: measure which generated claims and citations survive analyst review, then learn from the deletions, overwrites, and pushback events.
- Its biggest warning is that more autonomy can raise cost and safety risk while the agent still asks for clarification too rarely, so site-feasibility runs should stay collaborative and evidence-gated.

### Quotes
> “Less than half of all agent-produced code survives into user commits.”

> “Agents like Claude Code stop to ask users a clarifying question in only 1.4% of turns. Users, on the other hand, interrupt and push back frequently, in roughly 44% of turns.”

---
