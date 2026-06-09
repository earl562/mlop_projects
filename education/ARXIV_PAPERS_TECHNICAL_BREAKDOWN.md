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
| **OBSIDIAN_1-35** | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_OBSIDIAN_1-35.md | 1-17 (obsidian ordering — the original 17) | 1,689 | ✓ |
| PART_1 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_1.md | 18 (SoK Skills), 19 (MCP) | 647 | ✓ |
| PART_2 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_2.md | 20, 22, 23, 24, 25 | 1,384 | ✓ |
| PART_3 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_3.md | 21, 26, 27, 28, 29, 30, 31 | 2,079 | ✓ |
| PART_4 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_4.md | 32, 33, 34, 35 | 921 | ✓ |
| PART_5 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_5.md | 36-52 (17 papers) | 4,011 | ✓ |
| PART_6 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_6.md | 53-69 (17 papers) | 4,305 | ✓ |
| PART_7 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_7.md | 70-86 (17 papers) | 3,562 | ✓ |
| PART_8 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_8.md | 87-103 (17 papers) | 3,015 | ✓ |
| PART_9 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_9.md | 104-120 (17 papers) | 4,418 | ✓ |
| PART_10 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_10.md | 121-137 (17 papers) | 6,045 | ✓ |
| PART_11 | ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_11.md | 138-154 (17 papers) | 4,594 | ✓ |
| **Total** | — | **129/129 papers** | **36,670 lines** | ✓ |

**Folder location:** `education/` (top-level, single canonical location)

**Note on numbering:** The Obsidian file (`ARXIV_PAPERS_TECHNICAL_BREAKDOWN_OBSIDIAN_1-35.md`) uses arxiv-ID ordering (oldest first), starting at Paper 1 (2408.01667 — Phishing Detection). The master index below uses corpus-ordering from `Harness info.md`. Both numbering systems cover the same 129 unique arxiv IDs.

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
| 104 | 2603.20075v1 | llvm-autofix: Agentic Harness for Real-World Compilers | PART_9 | 215 |
| 105 | 2603.20939v1 | VARS: Vector-Adapted Retrieval Scoring (User Prefs) | PART_9 | 240 |
| 106 | 2603.26778v1 | TED: Training-Free Experience Distillation | PART_9 | 270 |
| 107 | 2603.26996v1 | FormalProofBench: Graduate-Level Lean 4 Proofs | PART_9 | 255 |
| 108 | 2603.27813v1 | MuSEAgent: Multimodal Stateful Experiences | PART_9 | 240 |
| 109 | 2604.02334v1 | Holos: Web-Scale Multi-Agent System (Agentic Web) | PART_9 | 270 |
| 110 | 2604.08756v1 | Artifacts as Memory Beyond the Agent Boundary | PART_9 | 235 |
| 111 | 2604.11811v1 | M*: Every Task Deserves Its Own Memory Harness | PART_9 | 250 |
| 112 | 2604.12064v1 | LLM-Redactor: 8 Privacy Techniques for LLM Requests | PART_9 | 270 |
| 113 | 2604.12162v1 | AlphaEval: Production-Grounded Agent Evaluation | PART_9 | 260 |
| 114 | 2604.13018v1 | AiScientist: Long-Horizon ML Research Engineering | PART_9 | 280 |
| 115 | 2604.13282v1 | Agent4MR: Physics-Aware MR Sequence Development | PART_9 | 235 |
| 116 | 2604.13318v1 | WebXSkill: Executable Skills for Web Agents | PART_9 | 215 |
| 117 | 2604.13346v1 | AgentSPEX: Workflow Spec Language + Harness | PART_9 | 285 |
| 118 | 2604.13630v1 | SafeHarness: Lifecycle-Integrated Security | PART_9 | 280 |
| 119 | 2604.13759v1 | Cognitive Companion: Parallel Reasoning Monitoring | PART_9 | 220 |
| 120 | 2604.14004v1 | Memory Transfer Learning (Cross-Domain Coding) | PART_9 | 230 |
| 121 | 2604.14228v1 | Dive into Claude Code (Design Space) | PART_10 | 369 |
| 122 | 2604.15034v2 | Autogenesis (Self-Evolving Agent Protocol) | PART_10 | 223 |
| 123 | 2604.18071v1 | Architectural Design Decisions (70 Projects) | PART_10 | 535 |
| 124 | 2604.21003v2 | The Last Harness You'll Ever Build | PART_10 | 202 |
| 125 | 2604.25850v4 | AHE (Observability-Driven Harness Evolution) | PART_10 | 244 |
| 126 | 2605.02092v1 | NORA (Spatial Data Science Agent) | PART_10 | 250 |
| 127 | 2605.03042v1 | ARIS (Adversarial Multi-Agent Research) | PART_10 | 249 |
| 128 | 2605.05258v1 | PARNESS (Paper Harness for Science) | PART_10 | 274 |
| 129 | 2605.05538v1 | AgenticRAG (Enterprise Retrieval) | PART_10 | 441 |
| 130 | 2605.08520v1 | FlashEvolve (Async Self-Evolution) | PART_10 | 250 |
| 131 | 2605.08741v1 | OPHSD (On-Policy Harness Self-Distillation) | PART_10 | 376 |
| 132 | 2605.09650v1 | Workspace Optimization (DreamTeam) | PART_10 | 395 |
| 133 | 2605.09942v1 | HAGE (RL-Driven Weighted Graph Memory) | PART_10 | 475 |
| 134 | 2605.09965v2 | Generalist Game Players (4 Pillars, 5 Levels) | PART_10 | 439 |
| 135 | 2605.09998v1 | Continual Harness (Pokemon Self-Improvement) | PART_10 | 555 |
| 136 | 2605.10966v1 | MMTB (Multimedia Terminal Benchmark) | PART_10 | 362 |
| 137 | 2605.11665v1 | Nautilus (Plug-and-Play Robot Learning) | PART_10 | 217 |
| 138 | 2605.11671 | Cochise (Reference Pen-Testing Harness) | PART_11 | 333 |
| 139 | 2605.11732 | AgentDisCo (Disentangled Deep Research) | PART_11 | 292 |
| 140 | 2605.12129 | It's Not the Size (Harness Design Determines Stability) | PART_11 | 292 |
| 141 | 2605.12239 | Harness Engineering as Categorical Architecture | PART_11 | 294 |
| 142 | 2605.13357 | AI Harness Engineering (Runtime Substrate) | PART_11 | 389 |
| 143 | 2605.13821 | AEvo (Harnessing Agentic Evolution) | PART_11 | 232 |
| 144 | 2605.14186 | Metacognitive Harness (Test-Time Scaling) | PART_11 | 238 |
| 145 | 2605.14271 | HarnessAudit (Safety Auditing) | PART_11 | 275 |
| 146 | 2605.14421 | MemLineage (Cryptographic Memory Defense) | PART_11 | 336 |
| 147 | 2605.14431 | FuzzAgent (Evolutionary Library Fuzzing) | PART_11 | 286 |
| 148 | 2605.14497 | ROAD (Bi-Level Data Mixing for Offline-to-Online RL) | PART_11 | 195 |
| 149 | 2605.14786 | Known By Their Actions (Browser Agent Fingerprinting) | PART_11 | 237 |
| 150 | 2605.15040 | Orchard (Open-Source Agentic Modeling Framework) | PART_11 | 257 |
| 151 | 2605.15132 | APWA (Distributed Agentic Workflows) | PART_11 | 217 |
| 152 | 2605.15184 | Is Grep All You Need (Harness Reshapes Search) | PART_11 | 166 |
| 153 | 2605.15187 | Articraft (Agentic 3D Asset Generation) | PART_11 | 239 |
| 154 | 2605.15188 | FutureSim (Replaying World Events for Adaptive Agents) | PART_11 | 295 |

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
- **PART_9:** Papers 104-120 (17 papers) ✓
- **PART_10:** Papers 121-137 (17 papers) ✓
- **PART_11:** Papers 138-154 (17 papers) ✓ — final batch (corpus complete)
- **PART_12:** Not needed (no remaining papers)

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

**PlotLot recommendation:** Speculate on common multi-step workflows.

## PART_9 Synthesis: Cross-Cutting Themes

The 17 papers in PART_9 cluster into 8 themes with direct implications for PlotLot:

### Theme 1: Domain-Specific Agents (Papers 104, 115, 116)
- **llvm-autofix (104):** LLVM harness + llvm-bench; 60% decline in frontier models; 22% recovery via tooling
- **Agent4MR (115):** PyPulseq + physics validator; 92% success on spin-echo EPI; outperforms human developers
- **WebXSkill (116):** Executable skills + URL graph; +9.8-12.9 points on WebArena/WebVoyager

**PlotLot recommendation:** Build a vertical site-feasibility agent with zoning-specific tools (parcel facts, ordinance retrieval, dimensional calculator, conflict resolver) and a held-out site-feasibility benchmark.

### Theme 2: Experience and Memory Banks (Papers 105, 106, 108, 111, 120)
- **VARS (105):** Dual-vector user representation; weak scalar rewards; +9pp task success
- **TED (106):** In-context experience distillation; 5x compute reduction; 0.627 → 0.702
- **MuSEAgent (108):** Atomic decisions + hindsight extraction; +5-6pp over trajectory retrieval
- **M* (111):** Auto-discover task-specific memory via code evolution; +7-9pp
- **MTL (120):** Cross-domain transfer; +3.7% avg; abstraction > specificity

**PlotLot recommendation:** Build a PlotLot experience bank that prefers **abstractions** (e.g., "in PD districts, the PD ordinance supersedes base zoning") over **concrete traces** (e.g., specific past reports).

### Theme 3: Verification as a First-Class Concern (Papers 107, 117, 118)
- **FormalProofBench (107):** Lean 4 as verifier; 33.5% best accuracy; 5 failure modes
- **AgentSPEX (117):** Workflow spec + verification; +2-5pp on most benchmarks
- **SafeHarness (118):** 4-layer security (filter, verify, privilege, rollback); 38% UBR reduction, 42% ASR reduction

**PlotLot recommendation:** Verification-first design. The deterministic dimensional calculator is the analog of Lean 4. SafeHarness's L2 verification (claim provenance) is a direct fit for evidence-backed reports.

### Theme 4: Privacy and Security as a System (Papers 112, 118)
- **LLM-Redactor (112):** 8 techniques; A+B+C is best; 0% exact PII leak
- **SafeHarness (118):** 4-layer lifecycle security; cross-layer mechanisms

**PlotLot recommendation:** Implement security as a **lifecycle system** with privacy-preserving LLM access (LLM-Redactor pattern) plus 4-layer security (SafeHarness pattern).

### Theme 5: Production Evaluation (Papers 104, 107, 113)
- **llvm-autofix (104):** 60% decline on compiler bugs vs general code
- **FormalProofBench (107):** Graduate-level math much harder than undergrad
- **AlphaEval (113):** 10-15 point gap between lab and production scores

**PlotLot recommendation:** Build a PlotLot production benchmark from real analyst tasks. Use the requirement-to-benchmark construction framework from AlphaEval.

### Theme 6: Long-Horizon and Workflow Spec (Papers 114, 117)
- **AiScientist (114):** Hierarchical orchestration + File-as-Bus; 31.82 point ablation when File-as-Bus removed
- **AgentSPEX (117):** Workflow spec language; +2-5pp on most benchmarks

**PlotLot recommendation:** Adopt a hybrid: File-as-Bus for the workspace (AiScientist) + workflow spec for the stages (AgentSPEX).

### Theme 7: Memory Evolution and Compression (Papers 106, 108, 109, 111)
- **TED (106):** Experience compression (merge, rewrite, remove)
- **MuSEAgent (108):** Quality-filtered experience bank
- **M* (111):** Reflective code evolution of memory programs
- **Holos (109):** Nuwa engine for high-efficiency agent generation

**PlotLot recommendation:** Build a PlotLot memory manager that prunes old, low-utility, or duplicated experiences.

### Theme 8: Monitoring and Self-Repair (Papers 118, 119)
- **SafeHarness (118):** Anomaly tracking with cross-layer escalation
- **Cognitive Companion (119):** Parallel monitoring; 52-62% loop reduction; zero overhead probe

**PlotLot recommendation:** Add a Cognitive Companion to PlotLot's harness. The Probe-based variant is particularly attractive for zero overhead.

## PART_10 Synthesis: Cross-Cutting Themes

The 17 papers in PART_10 cluster into 9 themes with direct implications for PlotLot:

### Theme 1: Harness Architecture as Reference Implementation (Papers 121, 123)
- **Claude Code (121):** Simple loop + 7 permission modes, 5-layer compaction, 4 extensibility mechanisms, sub-agent delegation with worktree isolation.
- **Architectural Design Decisions (123):** Empirical study of 70 projects; 5 recurring dimensions (subagent, context, tools, safety, orchestration); 5 architectural patterns; **audit gap finding** (~40% no audit, ~5% tamper-evident).

**PlotLot recommendation:** Adopt Claude Code's permission system design as a reference. Ship tamper-evident audit by default — this is a public differentiator (per Paper 123's audit gap finding). Use the 5 dimensions as a design review rubric.

### Theme 2: Self-Evolving and Self-Improving Harnesses (Papers 122, 125, 130, 135)
- **Autogenesis (122):** Self-evolving agent protocol; agents modify their own behavior.
- **AHE (125):** Observability-driven harness evolution; ~5x harness change magnitude.
- **FlashEvolve (130):** Asynchronous evolution; 3.5-4.9x throughput via async workers + queue; language-space staleness is repairable.
- **Continual Harness (135):** Online reset-free adaptation; first AI to complete Pokemon Blue/Yellow Legacy/Crystal without a lost battle; recovers most of the gap to hand-engineered expert harness.

**PlotLot recommendation:** Build a PlotLot self-evolution layer combining observability (AHE), throughput (FlashEvolve), and online adaptation (Continual Harness). The audit log (Theme 1) is the observability substrate.

### Theme 3: Domain-Verticalized Agents (Papers 126, 127, 132, 137)
- **NORA (126):** Spatial data science agent; 21 skills; 0.91 spatial task accuracy.
- **ARIS (127):** Adversarial multi-agent research; ~30% quality boost over single-agent.
- **Workspace Optimization / DreamTeam (132):** ARC-AGI-3 agent; 36% → 38.4% with 31% fewer actions; workspace is the "trainable" substrate.
- **Nautilus (137):** Plug-and-play robot learning; one prompt → entire pipeline.

**PlotLot recommendation:** PlotLot IS this pattern. Adopt NORA's 21-skill architecture. Use ARIS's adversarial review for report quality. Apply workspace optimization to the parcel/ordinance/report substrate. Provide one-prompt onboarding like Nautilus.

### Theme 4: Declarative Workflows and DAG Kernels (Papers 124, 128)
- **Last Harness (124):** Minimal-core, max-extensibility philosophy.
- **PARNESS (128):** End-to-end scientific research as a DAG; declarative workflow.

**PlotLot recommendation:** Use a thin DAG kernel (PARNESS-style) for the top-level report pipeline. Allow per-stage extensibility (Last Harness style) so users can add custom stages.

### Theme 5: Adversarial Verification and Review (Papers 127, 128)
- **ARIS (127):** Adversarial multi-agent collaboration; multiple models critique each other.
- **PARNESS (128):** Verifier-in-the-loop; reproducibility checks.

**PlotLot recommendation:** Add a reviewer agent that uses a different model (or a different prompt) to critique each report. The deterministic dimensional calculator is a strong first-pass verifier; the reviewer agent is a second-pass.

### Theme 6: Agentic Retrieval and Knowledge Access (Papers 129, 134)
- **AgenticRAG (129):** 4 tools (search, find, open, summarize); 5.9× improvement over single-shot RAG; 49.6% recall@1 on BRIGHT, 0.96 factuality on WixQA, 92% on FinanceBench.
- **Generalist Game Players (134):** Cross-game transfer; 4 pillars, 5 trade-offs, 5-level roadmap.

**PlotLot recommendation:** Replace single-shot ordinance retrieval with agentic retrieval (AgenticRAG pattern). Use the 4-tool design (search, find, open, summarize) for ordinance navigation. Adopt the 4-pillar / 5-level roadmap for PlotLot's product strategy.

### Theme 7: Harness Internalization and Distillation (Papers 131, 132)
- **OPHSD (131):** On-policy harness self-distillation; +10.83% over OPSD on HMMT25; harness benefits are internalized; re-attaching the harness at inference is unnecessary.
- **Workspace Optimization (132):** The workspace is the "trainable" substrate; artifacts = parameters, evidence = data, counterexamples = losses, feedback = gradients.

**PlotLot recommendation:** Use the full PlotLot harness to generate high-quality training data. Distill into a smaller model (OPHSD pattern). The smaller model achieves most of the harness's quality at 10% of the inference cost. Adopt workspace optimization for the parcel/ordinance/report substrate.

### Theme 8: Memory Evolution and Multi-Relational Graphs (Papers 132, 133)
- **Workspace Optimization (132):** Counterexamples as the loss function; versioned artifacts.
- **HAGE (133):** Weighted multi-relational memory graph; RL-driven routing; +7 points over Mem0; 5 relation types (causal, temporal, semantic, spatial, episodic).

**PlotLot recommendation:** Build a HAGE-style memory with 5 relation types for the parcel/ordinance/report substrate. Use the routing network to focus on relevant edges per query. Counterexamples (analyst revisions) drive workspace updates.

### Theme 9: New Modalities and Multimedia (Papers 134, 136)
- **Generalist Game Players (134):** Cross-game transfer; 4 pillars (Dataset, Model, Harness, Benchmark).
- **MMTB (136):** 105 tasks, 5 meta-categories; Terminus-MM extends Terminus-KIRA with audio + video perception; 31% → 58% with multimedia; Claude-Sonnet-4 reaches 68%.

**PlotLot recommendation:** Add multimedia perception to PlotLot for analyzing public hearing recordings, site walkthrough videos, and ordinance PDFs with figures. The 27pp quality boost is one of the largest single-feature improvements in the benchmark literature.

## How to Use This Survey (Updated for PART_10)

1. **Building a skill?** Start with Paper 18, Paper 24, Paper 80, Paper 85, **Paper 121 (Claude Code)**, **Paper 123 (Audit Gap)**.
2. **Building a tool?** Start with Paper 19, Paper 34, Paper 71, **Paper 129 (AgenticRAG)**.
3. **Building governance?** Start with Paper 23, Paper 32, Paper 35, Paper 83, **Paper 121 (Claude Code permissions)**, **Paper 123 (Tamper-evident audit)**.
4. **Building a memory system?** Start with Paper 21, Paper 28, Paper 56, Paper 63, Paper 65, Paper 75, Paper 81, Paper 84, **Paper 133 (HAGE)**.
5. **Building a multi-agent system?** Start with Paper 22, Paper 30, Paper 32, Paper 55, Paper 67, Paper 71, **Paper 127 (ARIS adversarial)**.
6. **Evaluating your system?** Start with Paper 27, Paper 33, Paper 57, Paper 66, Paper 79, **Paper 113 (AlphaEval)**, **Paper 136 (MMTB)**.
7. **Debugging failures?** Start with Paper 25, Paper 68, Paper 70, **Paper 132 (Workspace counterexamples)**.
8. **Building for long context?** Start with Paper 52, Paper 64, Paper 77, **Paper 121 (compaction pipeline)**.
9. **Building for real-world usage?** Start with Paper 69, Paper 58, Paper 82, **Paper 135 (Continual Harness)**.
10. **Optimizing a harness?** Start with Paper 73, Paper 79, Paper 86, **Paper 122 (Autogenesis)**, **Paper 125 (AHE)**, **Paper 130 (FlashEvolve)**.
11. **Internalizing a harness into a model?** Start with **Paper 131 (OPHSD)**.
12. **Building a verticalized agent?** Start with Paper 22, **Paper 126 (NORA)**, **Paper 127 (ARIS)**, **Paper 132 (DreamTeam)**, **Paper 137 (Nautilus)**.
13. **Adding multimedia perception?** Start with **Paper 136 (MMTB, Terminus-MM)**.
14. **Designing for cross-game / cross-jurisdiction transfer?** Start with **Paper 134 (Generalist Game Players, 5-level roadmap)**.
15. **Building for self-improvement?** Start with **Paper 122 (Autogenesis)**, **Paper 125 (AHE)**, **Paper 130 (FlashEvolve)**, **Paper 135 (Continual Harness)**.

## PART_11 Synthesis: Cross-Cutting Themes

The 17 papers in PART_11 (the final batch, completing the 129-paper corpus) cluster into 9 themes with direct implications for PlotLot:

### Theme 1: Evolutionary Loops as a Universal Pattern (Papers 143, 147, 148)

Three papers in this batch all implement the *evolutionary loop pattern*: a system that runs multiple rounds, observes the outcome of each round, and adapts the next round's behavior based on the observation. FuzzAgent evolves harnesses via MAP-Elites to maximize coverage. ROAD evolves data mix ratios via a multi-armed bandit to balance stability and adaptation. AEvo evolves agent prompts via evolutionary search.

**PlotLot recommendation:** Wrap every component that has hyperparameters (data mix, prompt template, retrieval algorithm) in an evolutionary loop. The "set hyperparameters once, train, evaluate" pattern is suboptimal; a continuous adaptation pattern is the state of the art.

### Theme 2: Runtime Evidence Beats LLM-as-Judge (Papers 138, 141, 146, 150, 152)

FuzzAgent's *runtime-evidence oracle* (compile the harness, run it, capture coverage) is more reliable than LLM-as-judge. The same insight appears in Cochise (the GOAD testbed is a runtime oracle for pen-testing), MemLineage (the Merkle log is runtime evidence for memory safety), and Orchard Env (the checkpoint/restore is runtime evidence for state).

**PlotLot recommendation:** Replace LLM-as-judge with deterministic runtime evidence wherever possible. The agent's output, the model's confidence, the tool's result, the sandbox's state — all of these are runtime evidence. LLM-as-judge should be a *fallback*, not a primary signal.

### Theme 3: The Bi-Level Optimization Pattern (Papers 144, 147, 148, 151)

ROAD's bi-level formulation (outer = choose the mix; inner = train on the mix) is a pattern that appears in many systems: FuzzAgent's outer = choose the mutation; inner = evaluate. APWA's outer = decompose the query; inner = execute. MemLineage's outer = enforce the gate; inner = the memory access. Metacognitive Harness (Paper 144) is outer = monitor the agent's confidence; inner = the standard agent loop.

**PlotLot recommendation:** Identify the meta-decisions in PlotLot's pipeline (which model to use, which data to mix, which agent to dispatch) and implement bi-level optimization. The outer level should be a bandit or an evolutionary search; the inner level should be the standard training or inference loop.

### Theme 4: The Distributed Orchestrator Pattern (Paper 151)

APWA's distributed architecture (decomposer → scheduler → worker pool → aggregator) is the right pattern for *throughput-bound* workloads. The centralized orchestrator pattern is the right pattern for *coordination-bound* workloads. The choice depends on the workload's *parallelizability*.

**PlotLot recommendation:** PlotLot's batch evaluation is parallelizable (APWA's pattern); PlotLot's interactive chat is not (centralized pattern). PlotLot's pipeline should support *both* and route workloads to the appropriate architecture.

### Theme 5: The Programmatic Representation Pattern (Papers 140, 153)

Articraft's *programmatic representation* (the asset is a Python program, not a 3D mesh) is a pattern that generalizes: any structured output (code, math, dialogue with state, configuration) is better represented as a program than as a raw output. The program is composable, editable, verifiable, and compact. Paper 140 (It's Not the Size) reinforces this: harness design matters more than model size; the harness IS the program the model runs in.

**PlotLot recommendation:** PlotLot's data generation should produce *programs* (or structured representations), not raw outputs. The harness should validate the program, not the output. This enables the credit-assignment SFT pattern (learn from productive segments of programs) and the test-based validation pattern.

### Theme 6: The Privacy Attack Surface is Real (Paper 149)

The browser agent fingerprinting paper demonstrates that an agent's *actions and timings* are sufficient to identify the underlying model with up to 96% F1. This is a serious privacy attack: any website can determine which LLM is powering an agent.

**PlotLot recommendation:** If PlotLot deploys browser-facing agents, they are vulnerable. Implement timing normalization (mean 1.5s, std 0.5s), action obfuscation (strip exact coordinates), and consider model rotation. The only robust defense is a structural change (differential privacy on actions).

### Theme 7: The Calibration Crisis (Paper 154)

FutureSim reveals that frontier agents are *systematically overconfident*: they assign 90% confidence to predictions where their actual accuracy is 62%. This is not a bug; it is a structural property of how LLMs are trained.

**PlotLot recommendation:** PlotLot's evaluation should measure calibration (Brier score, ECE) explicitly. PlotLot's decision-making systems should recalibrate LLM probabilities before using them. PlotLot's users should be warned when an agent is operating outside its calibrated range.

### Theme 8: The Environment Layer as Kernel (Papers 142, 150, 151)

Orchard Env's *first-class environment layer* is a pattern that generalizes: any agentic system needs a *kernel* that provides the primitives (sandbox lifecycle, state management, checkpoint/restore). APWA's worker pool is a kernel. AI Harness Engineering (Paper 142) explicitly calls the harness a "runtime substrate."

**PlotLot recommendation:** PlotLot's environment should be a first-class component, not a utility. The API should be small (create, step, reset, close, checkpoint, restore) and the implementation should be pluggable (Docker, Kubernetes, Firecracker).

### Theme 9: The Harness as Audit Trail (Papers 138, 142, 145, 146, 147)

MemLineage (memory defense), HarnessAudit (safety audit), FuzzAgent (crash triage), Cochise (pen-testing logs), and Orchard Env (checkpoint/restore) all treat the *harness* as the *audit trail*. Every action the agent takes, every state transition, every decision is logged. The audit trail is what makes the system debuggable, reproducible, and auditable.

**PlotLot recommendation:** PlotLot's harness should log every action, every state transition, every decision. The logs should be queryable, structured, and tamper-evident. The audit trail is the only way to debug a system that has 10^6 lines of training code, 10^9 parameters, and 10^12 tokens of data.

## How to Use This Survey (Updated for PART_11)

1. **Building a skill?** Start with Paper 18, Paper 24, Paper 80, Paper 85, Paper 121, Paper 123.
2. **Building a tool?** Start with Paper 19, Paper 34, Paper 71, Paper 129.
3. **Building governance?** Start with Paper 23, Paper 32, Paper 35, Paper 83, Paper 121, Paper 123, **Paper 145 (HarnessAudit)**, **Paper 146 (MemLineage)**.
4. **Building a memory system?** Start with Paper 21, Paper 28, Paper 56, Paper 63, Paper 65, Paper 75, Paper 81, Paper 84, Paper 133, **Paper 146 (MemLineage)**.
5. **Building a multi-agent system?** Start with Paper 22, Paper 30, Paper 32, Paper 55, Paper 67, Paper 71, Paper 127, **Paper 139 (AgentDisco)**, **Paper 151 (APWA)**.
6. **Evaluating your system?** Start with Paper 27, Paper 33, Paper 57, Paper 66, Paper 79, Paper 113, Paper 136, **Paper 140 (Harness Design)**, **Paper 152 (Grep vs Vector)**, **Paper 154 (FutureSim)**.
7. **Debugging failures?** Start with Paper 25, Paper 68, Paper 70, Paper 132, **Paper 138 (Cochise)**, **Paper 145 (HarnessAudit)**.
8. **Building for long context?** Start with Paper 52, Paper 64, Paper 77, Paper 121.
9. **Building for real-world usage?** Start with Paper 69, Paper 58, Paper 82, Paper 135, **Paper 149 (Browser Agent Fingerprinting)**.
10. **Optimizing a harness?** Start with Paper 73, Paper 79, Paper 86, Paper 122, Paper 125, Paper 130, **Paper 141 (Categorical Architecture)**, **Paper 142 (AI Harness Engineering)**, **Paper 143 (AEvo)**, **Paper 147 (FuzzAgent)**.
11. **Internalizing a harness into a model?** Start with Paper 131.
12. **Building a verticalized agent?** Start with Paper 22, Paper 126, Paper 127, Paper 132, Paper 137, **Paper 150 (Orchard)**, **Paper 153 (Articraft)**.
13. **Adding multimedia perception?** Start with Paper 136.
14. **Designing for cross-game / cross-jurisdiction transfer?** Start with Paper 134.
15. **Building for self-improvement?** Start with Paper 122, Paper 125, Paper 130, Paper 135, **Paper 144 (Metacognitive Harness)**, **Paper 148 (ROAD)**.
16. **Building for browser-facing agents?** Start with **Paper 149 (Browser Agent Fingerprinting)**.
17. **Building for privacy?** Start with Paper 112, Paper 118, **Paper 149 (Browser Agent Fingerprinting)**.
18. **Building a harness runtime?** Start with **Paper 141 (Categorical Architecture)**, **Paper 142 (AI Harness Engineering)**, **Paper 150 (Orchard Env)**, **Paper 151 (APWA)**.
19. **Building for calibration and uncertainty?** Start with **Paper 144 (Metacognitive Harness)**, **Paper 154 (FutureSim)**.
20. **Building for distributed throughput?** Start with **Paper 151 (APWA)**.

## Corpus Complete

**129/129 papers covered** across 11 batches and 35,071 lines. The full corpus is available in:

- `/Users/earlperry/Desktop/Projects/plotlot-v2/docs/research/education/` (master + 11 parts)
- `github.com:earl562/plotlot-v2`, branch `dev` (fast-forwarded to the latest commit).

Future research should focus on:
- **Implementation.** The corpus identifies the *what*; implementation determines the *how*.
- **Benchmarking.** Build PlotLot-specific benchmarks following AlphaEval, Terminal-Bench, and SkillsBench patterns.
- **Production deployment.** The 10-15 point gap between lab and production scores (AlphaEval) is the single largest unknown.
- **Continuous evolution.** The corpus identifies evolutionary patterns (AEvo, FuzzAgent, ROAD); PlotLot should adopt them.

