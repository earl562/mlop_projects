# ARXIV PAPERS TECHNICAL BREAKDOWN — MASTER FILE

**Project:** PlotLot Harness Engineering
**Source:** `/Users/earlperry/Documents/AgenticHarnesses/Sandboxes/Harnesses/Harness info.md`
**Total papers in vault:** 129 unique arXiv IDs
**Status:** Deep-dive analysis at Paper 19 appendix depth (~200-400 lines per paper)

## Conventions

Each paper breakdown includes:
- **Mathematical formalism** (where applicable)
- **Detailed tables** (taxonomies, comparisons, empirical baselines)
- **Multiple code implementation sketches** (PlotLot-specific, runnable)
- **Threat models** with attack vectors and mitigations
- **Concrete algorithm descriptions** (not just "the paper does X")
- **Empirical baselines** (numbers from the paper)
- **Harness implications for PlotLot** (actionable for the platform)
- **Cross-references** to other papers in this survey

## Coverage

| Batch | File | Papers | Lines | Pushed |
|---|---|---|---|---|
| PART_1 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_1.md | 18 (SoK Skills), 19 (MCP) | 647 | ✓ |
| PART_2 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_2.md | 20, 22, 23, 24, 25 | 1,384 | ✓ |
| PART_3 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_3.md | 21, 26, 27, 28, 29, 30, 31 | 2,079 | ✓ |
| PART_4 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_4.md | 32, 33, 34, 35 | 921 | ✓ |
| PART_5 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_5.md | 36-52 (17 papers) | 4,009 | ✓ |
| PART_6 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_6.md | 53-69 (17 papers) | 4,397 | ✓ |
| PART_7 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_7.md | 70-86 (17 papers) | 3,562 | ✓ |
| PART_8 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_8.md | 87-103 (17 papers) | 3,015 | ✓ |
| **Total** | — | **86 papers** | **20,014 lines** | ✓ |

**Remaining:** 43 papers (next batches: PART_9, PART_10)

## Master Index — All 52 Papers

| # | arXiv ID | Title (abbreviated) | File | Lines |
|---|---|---|---|---|
| 18 | 2602.20867 | SoK: Agentic Skills | PART_1 | 246 |
| 19 | 2602.14878 | MCP Tool Descriptions Are Smelly | PART_1 | 390 |
| 20 | 2603.28052 | Meta-Harness: End-to-End Optimization | PART_2 | 431 |
| 21 | 2603.25723 | Natural-Language Agent Harnesses (NLAH+IHR) | PART_3 | 612 |
| 22 | 2604.08590 | AlphaLab: Autonomous Multi-Agent Research | PART_2 | 219 |
| 23 | 2604.07833 | Runtime Governance for Policy-Constrained Execution | PART_2 | 251 |
| 24 | 2604.03088 | SkVM: Language VM for Skills | PART_2 | 213 |
| 25 | 2604.03610 | DebugHarness: Human Dynamic Debugging | PART_2 | 245 |
| 26 | 2604.00362 | In Harmony with gpt-oss | PART_3 | 202 |
| 27 | 2603.29199 | AEC-Bench: Multimodal Benchmark for AEC | PART_3 | 287 |
| 28 | 2603.28088 | GEMS: Agent-Native Multimodal Generation | PART_3 | 283 |
| 29 | 2604.08224 | Externalization in LLM Agents (Review) | PART_3 | 244 |
| 30 | 2604.11378 | SGH: Structured Graph Harness | PART_3 | 208 |
| 31 | 2604.11535 | Problem Reductions at Scale | PART_3 | 220 |
| 32 | 2604.11548 | SemaClaw: General-Purpose Personal AI Agents | PART_4 | 219 |
| 33 | 2604.11784 | ClawGUI: Unified Framework for GUI Agents | PART_4 | 232 |
| 34 | 2603.22148 | OpenEarth-Agent: Tool Creation for EO | PART_4 | 239 |
| 35 | 2603.21019 | SkillProbe: Security Auditing for Marketplaces | PART_4 | 223 |
| 36 | 2408.01667 | GEPAgent: Phishing Detection (Authority Discovery) | PART_5 | 217 |
| 37 | 2505.02279 | Agent Interoperability Survey (MCP/ACP/A2A/ANP) | PART_5 | 221 |
| 38 | 2507.11633 | General Modular Harness (Gaming) | PART_5 | 209 |
| 39 | 2509.21766 | UltraHorizon: Long-Horizon Benchmark | PART_5 | 210 |
| 40 | 2512.16301 | Adaptation of Agentic AI Survey | PART_5 | 205 |
| 41 | 2602.02474 | MemSkill | PART_5 | 223 |
| 42 | 2602.06025 | BudgetMem (Budget-Tier Routing) | PART_5 | 216 |
| 43 | 2602.12430 | Agent Skills Survey | PART_5 | 236 |
| 44 | 2601.10338 | Agent Skills in the Wild (Security) | PART_5 | 221 |
| 45 | 2601.10971 | AJAR (Adaptive Jailbreak) | PART_5 | 201 |
| 46 | 2602.19672 | SkillOrchestra | PART_5 | 248 |
| 47 | 2603.07670 | Memory for Autonomous LLM Agents | PART_5 | 238 |
| 48 | 2602.22480 | VeRO: Eval Harness for Agent Optimization | PART_5 | 293 |
| 49 | 2603.20380 | ALARA for Agents (Least-Privilege CAT) | PART_5 | 239 |
| 50 | 2603.18829 | Agent Control Protocol (ACP) | PART_5 | 298 |
| 51 | 2603.03329 | AutoHarness (Synthesized Code Harness) | PART_5 | 244 |
| 52 | 2602.16069 | Limits of Long-Context Reasoning | PART_5 | 276 |
| 53 | 2311.02018v1 | Conan: Active Reasoning in Open-World | PART_6 | 250 |
| 54 | 2410.12475 | Aegis: Multi-Agent Functional Safety | PART_6 | 285 |
| 55 | 2503.13577 | When Should We Orchestrate Multiple Agents? | PART_6 | 295 |
| 56 | 2504.19413v1 | Mem0: Scalable Long-Term Memory | PART_6 | 229 |
| 57 | 2506.08119v2 | SOP-Bench: Industrial SOPs for LLM Agents | PART_6 | 216 |
| 58 | 2507.23361v2 | SWE-Exp: Experience-Driven Issue Resolution | PART_6 | 247 |
| 59 | 2508.00828v1 | Finance Agent Benchmark (SEC Filings) | PART_6 | 227 |
| 60 | 2509.23206v3 | PARL-MT: Progress-Aware Multi-Turn FC | PART_6 | 264 |
| 61 | 2511.07568v1 | HTN Procedural Knowledge for LLM Workflows | PART_6 | 245 |
| 62 | 2512.03420v3 | HarnessAgent: Tool-Augmented Fuzz Harness | PART_6 | 279 |
| 63 | 2512.03627v1 | MemVerse: Multimodal Lifelong Memory | PART_6 | 221 |
| 64 | 2512.24601v1 | Recursive Language Models (RLMs) | PART_6 | 205 |
| 65 | 2601.03192v2 | MemRL: Runtime RL on Episodic Memory | PART_6 | 213 |
| 66 | 2601.11868v1 | Terminal-Bench 2.0 (89 Hard Tasks) | PART_6 | 214 |
| 67 | 2602.03786v2 | AOrchestra: Dynamic Sub-Agent Creation | PART_6 | 311 |
| 68 | 2604.13151v1 | Exploration/Exploitation Errors Measurable | PART_6 | 244 |
| 69 | 2604.20779v1 | SWE-chat: Real-World Coding Agent Usage | PART_6 | 225 |
| 70 | 2507.18755v1 | Engineering Agent (Neuro-Symbolic Test Repair) | PART_7 | 246 |
| 71 | 2508.00007v1 | Agent Network Protocol (ANP) | PART_7 | 227 |
| 72 | 2508.20465v1 | On the Possibility of Deep Alignment | PART_7 | 116 |
| 73 | 2509.19349v1 | ShinkaEvolve: Sample-Efficient Program Evolution | PART_7 | 184 |
| 74 | 2512.04535v2 | GTM: Generalist Tool Model (Tool Simulator) | PART_7 | 195 |
| 75 | 2601.03204v1 | InfiAgent: Infinite-Horizon State Externalization | PART_7 | 191 |
| 76 | 2601.07372v1 | Engram: Conditional Memory via Scalable Lookup | PART_7 | 175 |
| 77 | 2601.08670v1 | Pced: Parallel Context-of-Experts Decoding | PART_7 | 188 |
| 78 | 2601.08773v1 | Reliable Graph-RAG for Codebases (AST vs LLM) | PART_7 | 195 |
| 79 | 2601.20412v1 | Cognitive Load Framework (ToolLoad-Bench) | PART_7 | 196 |
| 80 | 2601.21123v2 | CUA-Skill: Computer-Using Agent Skill Base | PART_7 | 195 |
| 81 | 2601.21545v1 | ShardMemo: Masked MoE for Sharded Memory | PART_7 | 200 |
| 82 | 2601.21684v1 | RSE: Recycling Search Experience | PART_7 | 198 |
| 83 | 2601.22773v3 | Safety Case Construction for AI Systems | PART_7 | 195 |
| 84 | 2602.02007v3 | xMemory: Beyond RAG for Agent Memory | PART_7 | 198 |
| 85 | 2602.08004v1 | Agent Skills Marketplace Analysis (40K skills) | PART_7 | 199 |
| 86 | 2602.08603v1 | OSCAR: Optimization-Steered Agentic Planning | PART_7 | 198 |
| 87 | 2602.10498v1 | When Skills Lie: Hidden-Comment Injection | PART_8 | 175 |
| 88 | 2602.10652v1 | UMEM: Unified Memory Extraction/Management | PART_8 | 205 |
| 89 | 2602.11304v1 | CryptoAnalystBench: Multi-Tool Analyst Failures | PART_8 | 205 |
| 90 | 2602.12670v3 | SkillsBench: How Well Agent Skills Work | PART_8 | 210 |
| 91 | 2602.19008v1 | Canonical Path Deviation (Reliability Failures) | PART_8 | 215 |
| 92 | 2602.22680v2 | Personalized LLM-Powered Agents (Survey) | PART_8 | 180 |
| 93 | 2603.01493v1 | PhotoBench: Personalized Intent Retrieval | PART_8 | 185 |
| 94 | 2603.02176v1 | AgentSkillOS: Skill Orchestration at Scale | PART_8 | 200 |
| 95 | 2603.02239v1 | ERI Benchmark: Engineering Reasoning | PART_8 | 195 |
| 96 | 2603.03212v1 | NeuroSkill: BCI-Based State of Mind Skills | PART_8 | 165 |
| 97 | 2603.05344v3 | OPENDEV: Terminal AI Coding Agent | PART_8 | 200 |
| 98 | 2603.07379v1 | SoK: Agentic RAG (POMDP Formalization) | PART_8 | 205 |
| 99 | 2603.08616v1 | Coverage-Guided Multi-Agent Fuzz Harness (Java) | PART_8 | 210 |
| 100 | 2603.10664v1 | Terminal Is All You Need (HCI Design) | PART_8 | 175 |
| 101 | 2603.12658v1 | Continual Learning in LLMs (Survey) | PART_8 | 190 |
| 102 | 2603.18897v1 | PASTE: Pattern-Aware Speculative Tool Execution | PART_8 | 175 |
| 103 | 2603.19347v3 | Agentic Frontier of Verilog Code Generation | PART_8 | 195 |

## Theme Clusters

### Cluster A: Skill Layer (Papers 18, 24, 28, 32)
Skills as the unit of reuse, composition, and evolution.
- **18 (SoK):** Formal skill tuple `(C, π, T, R)`, 7 design patterns, ClawHavoc case study
- **24 (SkVM):** Skills as code, capability profiles, JIT solidification (40% token reduction, 3.2× speedup, 19-50× latency)
- **28 (GEMS):** Agent Skill library with on-demand loading
- **32 (SemaClaw):** DAG-based 2-phase orchestration, PermissionBridge, 3-tier context

### Cluster B: Harness / Runtime (Papers 19, 20, 22, 23, 30, 32, 67)
The runtime that orchestrates the agent.
- **19 (MCP):** Tool descriptions as the interface contract
- **20 (Meta-Harness):** Filesystem-based harness optimization, Pareto frontier
- **22 (AlphaLab):** Domain adapters as primitive, 3-phase pipeline
- **23 (Runtime Governance):** Policy-constrained execution, 96.2% interception
- **30 (SGH):** Scheduler-theoretic framework, immutable plan versions
- **32 (SemaClaw):** Open-source multi-agent framework
- **67 (AOrchestra):** Dynamic 4-tuple sub-agent creation, 16.28% gain

### Cluster C: Policy & Memory (Papers 21, 23, 28, 29, 30, 56, 63, 65)
Externalized cognition, memory, and governance.
- **21 (NLAH+IHR):** Natural-language policy harness, 5 writing principles
- **23 (Runtime Governance):** Policy enforcement layer
- **28 (GEMS):** Hierarchical agent memory (project/session/step)
- **29 (Externalization):** Unifying review of memory/skills/protocols
- **30 (SGH):** Plan versioning for auditability
- **56 (Mem0):** Vector + graph memory, 91% lower latency
- **63 (MemVerse):** Three-tier multimodal memory
- **65 (MemRL):** RL-trained retrieval over frozen LLM

### Cluster D: Debugging & Verification (Papers 25, 27, 28, 31, 62, 68)
Closed-loop validation, testing, evaluation.
- **25 (DebugHarness):** Pattern-guided investigation, 90% patch success
- **27 (AEC-Bench):** Standardized rubric, 6 universal harness techniques
- **28 (GEMS):** Verifier-in-the-loop generation
- **31 (Reductions):** Multi-layer verification, 100+ problem types, 200+ rules in 170K Rust LoC
- **62 (HarnessAgent):** Error triage, hybrid retrieval, self-hack detection
- **68 (Exp/Exp Errors):** Policy-agnostic error metrics

### Cluster E: Security & Governance (Papers 23, 32, 35, 54, 69)
Threat models, supply-chain attacks, audit pipelines.
- **23 (Runtime Governance):** Behavioral policy enforcement
- **32 (SemaClaw):** PermissionBridge, 4-stage safety check
- **35 (SkillProbe):** 3-stage audit, 90% of popular skills fail audit, popularity-security paradox
- **54 (Aegis):** V-model lifecycle, Self-RAG reflection
- **69 (SWE-chat):** 8.7x vulnerability rate for vibe-coded code

### Cluster F: Protocol & Model-Specific (Papers 19, 26, 33, 34)
Model harnesses, message formats, deployment.
- **19 (MCP):** Standard tool-calling protocol
- **26 (Harmony):** Native OpenAI message format (bypasses Chat Completions)
- **33 (ClawGUI):** 17-action GUI space, Android/HarmonyOS/iOS
- **34 (OpenEarth-Agent):** Tool creation (vs calling) for open environments

### Cluster G: Orchestration & Multi-Turn (Papers 54, 55, 60, 67)
Multi-agent coordination and progress tracking.
- **54 (Aegis):** Three specialized agents, V-model lifecycle
- **55 (Orchestration):** When-to-orchestrate, "App" metric, Rogers' Paradox
- **60 (PARL-MT):** Progress awareness, PAG-RL training
- **67 (AOrchestra):** 4-tuple sub-agent creation, mixed model routing

### Cluster H: Evaluation & Benchmarks (Papers 57, 59, 66, 68)
Rigorous agent evaluation methodology.
- **57 (SOP-Bench):** 2,000 industrial SOPs, 12 domains
- **59 (Finance Agent Benchmark):** Grounded citation, 9 task categories
- **66 (Terminal-Bench 2.0):** 89 hard tasks, 3-reviewer verification
- **68 (Exp/Exp Errors):** Policy-agnostic error metrics

### Cluster I: Long-Context & Code Generation (Papers 53, 58, 62, 64, 69)
Reasoning, software engineering, long context.
- **53 (Conan):** Active reasoning, Bayesian EIG, "clarify-then-recommend"
- **58 (SWE-Exp):** Multi-faceted experience bank, 73% Pass@1
- **62 (HarnessAgent):** Tool-augmented, error triage, self-hack detection
- **64 (RLMs):** Recursive decomposition, 100x context size
- **69 (SWE-chat):** 44% survival rate, real-world usage data

## How to Use This Survey

1. **Building a skill?** Start with Paper 18 (formal definition), Paper 24 (compilation).
2. **Building a tool?** Start with Paper 19 (MCP schema), Paper 34 (tool creation).
3. **Building governance?** Start with Paper 23 (policy), Paper 32 (PermissionBridge), Paper 35 (audit).
4. **Building a memory system?** Start with Paper 21 (NLAH), Paper 28 (GEMS), Paper 56 (Mem0), Paper 63 (MemVerse), Paper 65 (MemRL).
5. **Building a multi-agent system?** Start with Paper 22 (AlphaLab), Paper 30 (SGH), Paper 32 (SemaClaw), Paper 55 (Orchestration), Paper 67 (AOrchestra).
6. **Evaluating your system?** Start with Paper 27 (AEC-Bench), Paper 33 (ClawGUI-Eval), Paper 57 (SOP-Bench), Paper 66 (Terminal-Bench).
7. **Debugging failures?** Start with Paper 25 (DebugHarness), Paper 68 (Exp/Exp Errors).
8. **Building for long context?** Start with Paper 52, Paper 64 (RLMs).
9. **Building for real-world usage?** Start with Paper 69 (SWE-chat), Paper 58 (SWE-Exp).

## Next Batches

- **PART_7:** Papers 70-86 (17 papers) ✓
- **PART_8:** Papers 87-103 (17 papers) ✓
- **PART_9:** Papers 104-120 (17 papers)
- **PART_10:** Papers 121-129 (9 papers)

## PART_6 Synthesis: Cross-Cutting Themes

The 17 papers in PART_6 cluster into 6 themes with direct implications for PlotLot:

### Theme 1: Memory Architectures (Papers 56, 63, 65)
Three different approaches to the "LLMs can't remember" problem:
- **Mem0** — Vector + graph, extraction/consolidation, 91% lower latency
- **MemVerse** — Three-tier (short-term + hierarchical KG + parametric distillation)
- **MemRL** — Frozen LLM + learned retrieval policy on episodic memory

**PlotLot recommendation:** Hybrid of Mem0 + MemVerse; learn retrieval with MemRL.

### Theme 2: Multi-Agent Orchestration (Papers 54, 55, 60, 67)
The "should we use multiple agents" question with different answers:
- **Aegis** — V-model with three specialized agents (safety-critical)
- **Orchestration** — Empirical "App" metric decides
- **PARL-MT** — Progress awareness for multi-turn
- **AOrchestra** — Dynamic 4-tuple sub-agent creation (16.28% gain)

**PlotLot recommendation:** AOrchestra's 4-tuple pattern, with Paper 55's "App" metric as the routing signal.

### Theme 3: Evaluation Methodology (Papers 57, 59, 66, 68)
Rigorous agent evaluation with different strengths:
- **SOP-Bench** — 2,000 industrial SOPs, 12 domains
- **Finance Agent Benchmark** — Grounded citation, 9 categories
- **Terminal-Bench 2.0** — 89 hard tasks, 3-reviewer verification
- **Exp/Exp Errors** — Policy-agnostic error metrics

**PlotLot recommendation:** Stratified internal benchmark following Terminal-Bench's verification process.

### Theme 4: Procedural Knowledge (Paper 61)
HTNs as procedural knowledge — 20B + HTN beats 120B without. The "constraints beat capabilities" principle in concrete form.

**PlotLot recommendation:** Encode zoning expertise as an HTN — the highest-leverage structural investment.

### Theme 5: Long-Context and Code Generation (Papers 62, 64, 69)
- **HarnessAgent** — Tool-augmented code gen, error triage, self-hack detection
- **RLMs** — Recursive decomposition, 100x context size
- **SWE-chat** — Real-world usage, 44% survival rate, 8.7x vulnerability rate

**PlotLot recommendation:** Long-context + tool-augmentation + adversarial audit. Expect 44% survival rate; plan for revision.

### Theme 6: Active Reasoning and Error Analysis (Papers 53, 68)
- **Conan** — Bayesian active reasoning with EIG
- **Exp/Exp Errors** — Diagnostic metrics for reasoning process

**PlotLot recommendation:** "Clarify-then-recommend" UX with EIG-based questioning. Track exploration/exploitation errors in production.

## PART_7 Synthesis: Cross-Cutting Themes

The 17 papers in PART_7 cluster into 7 themes with direct implications for PlotLot:

### Theme 1: Harness Optimization as a Search Problem (Papers 73, 79, 86)
Three approaches to optimizing the harness itself:
- **ShinkaEvolve (73):** Evolutionary search with LLM mutations; 30× sample efficiency
- **Cognitive Load (79):** Parametric load adjustment; capability boundary mapping
- **OSCAR (86):** Offline-online paradigm with MILP-derived optimal trajectories; 10× data efficiency

**PlotLot recommendation:** Build a harness optimization layer combining load-aware routing (79), evolutionary search (73), and golden library steering (86).

### Theme 2: Memory Architectures (Papers 75, 76, 81, 84)
Four different memory designs:
- **InfiAgent (75):** File-centric state, bounded context; 20B competitive with proprietary
- **Engram (76):** N-gram lookup at model level; +12.8pp on NIAH
- **ShardMemo (81):** Tiered memory, masked MoE routing; +6.87 F1 with 20% latency reduction
- **xMemory (84):** Decoupling-to-aggregation; +8.5 F1 with 27% token reduction

**PlotLot recommendation:** Hybrid memory: InfiAgent file state + ShardMemo tiers + xMemory hierarchy.

### Theme 3: RAG and Retrieval Innovations (Papers 77, 78)
- **Pced (77):** Per-document forward pass, contrastive decoding; recovers most joint quality
- **Graph-RAG (78):** AST-derived KG beats LLM-extracted; 6pp correctness, 50× cost

**PlotLot recommendation:** Replace long-context RAG with Pced parallel per-source forward. Build DKB via Tree-sitter for codebase queries.

### Theme 4: Skills at Scale (Papers 80, 85)
- **CUA-Skill (80):** Large-scale skill library; 57.5% on WindowsAgentArena; +15.7pp over vanilla
- **Agent Skills Marketplace (85):** 40,285 skills analyzed; 70% intent-level redundancy; 38% SWE supply vs 24% adoption

**PlotLot recommendation:** Build PlotLot skill library per CUA-Skill design. Target under-served categories from Marketplace analysis.

### Theme 5: Multi-Agent Communication (Paper 71)
- **ANP (71):** Three-layer protocol with DID-based identity and meta-protocol negotiation

**PlotLot recommendation:** Use ANP for external agent integration (county assessors, title companies); MCP for internal.

### Theme 6: Governance and Safety (Papers 72, 83)
- **Deep Alignment (72):** Theoretical; three-level constraint hierarchy (reward, enforcement, endogenous)
- **Safety Case (83):** GSN-based templates; claim/argument/evidence structures

**PlotLot recommendation:** Build safety case per Paper 83 templates. Use Paper 23 runtime governance for level 2 constraints.

### Theme 7: Test-Time Compute (Paper 82)
- **RSE (82):** Experience bank for positive/negative recycling; +7.5pp on HMMT24

**PlotLot recommendation:** Add experience bank to reasoning layer for cumulative search.

## How to Use This Survey (Updated)

1. **Building a skill?** Start with Paper 18 (formal definition), Paper 24 (compilation), Paper 80 (CUA-Skill library), Paper 85 (marketplace strategy).
2. **Building a tool?** Start with Paper 19 (MCP schema), Paper 34 (tool creation), Paper 71 (ANP for external).
3. **Building governance?** Start with Paper 23 (policy), Paper 32 (PermissionBridge), Paper 35 (audit), Paper 83 (safety case).
4. **Building a memory system?** Start with Paper 21 (NLAH), Paper 28 (GEMS), Paper 56 (Mem0), Paper 63 (MemVerse), Paper 65 (MemRL), Paper 75 (InfiAgent), Paper 81 (ShardMemo), Paper 84 (xMemory).
5. **Building a multi-agent system?** Start with Paper 22 (AlphaLab), Paper 30 (SGH), Paper 32 (SemaClaw), Paper 55 (Orchestration), Paper 67 (AOrchestra), Paper 71 (ANP).
6. **Evaluating your system?** Start with Paper 27 (AEC-Bench), Paper 33 (ClawGUI-Eval), Paper 57 (SOP-Bench), Paper 66 (Terminal-Bench), Paper 79 (Cognitive Load).
7. **Debugging failures?** Start with Paper 25 (DebugHarness), Paper 68 (Exp/Exp Errors), Paper 70 (Engineering Agent's symbolic feedback).
8. **Building for long context?** Start with Paper 52, Paper 64 (RLMs), Paper 77 (Pced).
9. **Building for real-world usage?** Start with Paper 69 (SWE-chat), Paper 58 (SWE-Exp), Paper 82 (RSE).
10. **Optimizing a harness?** Start with Paper 73 (ShinkaEvolve), Paper 79 (Cognitive Load), Paper 86 (OSCAR).

## PART_8 Synthesis: Cross-Cutting Themes

The 17 papers in PART_8 cluster into 7 themes with direct implications for PlotLot:

### Theme 1: Skill Security and Supply Chain (Papers 87, 90, 94)
- **Hidden-Comment Injection (87):** Markdown attack surface; 73% → 4% with defensive prompt
- **SkillsBench (90):** +16.2pp from curated skills; 16/84 negative deltas
- **AgentSkillOS (94):** Capability tree + DAG; +18-26 quality

**PlotLot recommendation:** Structured skill library (AgentSkillOS) with curated expert skills (SkillsBench) defended against injection (Hidden-Comment).

### Theme 2: Memory Evolution (Papers 88, 91, 101, 102)
- **UMEM (88):** Joint extraction-management; +10.67% on multi-turn
- **Canonical Path (91):** Stochastic drift; +8.8pp from monitor
- **Continual Learning (101):** Three methods (rehearsal, regularization, architecture)
- **PASTE (102):** Speculative tool execution; 48.5% latency reduction

**PlotLot recommendation:** Memory that learns (UMEM), monitors drift (Canonical Path), updates without forgetting (Continual Learning), speculates (PASTE).

### Theme 3: Multi-Tool and Multi-Source Reasoning (Papers 89, 93, 98)
- **CryptoAnalystBench (89):** 7 higher-order error types
- **PhotoBench (93):** Modality gap + source fusion paradox
- **SoK Agentic RAG (98):** POMDP; 4 systemic risks

**PlotLot recommendation:** Multi-source as POMDP (SoK). Detect 7 error types (CryptoAnalystBench). Multi-source profiling (PhotoBench).

### Theme 4: Harness Structure (Papers 97, 99, 100, 103)
- **OPENDEV (97):** Dual-agent; adaptive compaction
- **Java Fuzz (99):** 5 specialized agents; MCP; +26% coverage
- **Terminal (100):** Three design properties
- **Verilog (103):** Structured > naive wrapping

**PlotLot recommendation:** Structured harness with explicit phases. 5-agent pattern (99) for complex, dual-agent (97) for simple.

### Theme 5: Domain Benchmarks (Papers 89, 90, 95)
- **CryptoAnalystBench (89):** 198 queries, 11 categories
- **SkillsBench (90):** 86 tasks, 11 domains
- **ERI (95):** 57,750 records, 9 fields

**PlotLot recommendation:** Build PlotLot-specific benchmark with 200+ queries, 5-10 domains, deterministic verifiers, multi-judge.

### Theme 6: Personalization and State (Papers 92, 96)
- **PLA Survey (92):** Four capabilities
- **NeuroSkill (96):** State of mind + skills

**PlotLot recommendation:** Implement four PLA capabilities. Use behavior signals for coarse state-aware skill triggers.

### Theme 7: Test-Time Compute (Paper 102)
- **PASTE (102):** Speculative tool execution; 48.5% latency reduction

**PlotLot recommendation:** Speculate on common multi-step workflows.

