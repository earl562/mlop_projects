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
| **Total** | — | **18 papers** | **5,031 lines** | ✓ |

**Remaining:** 111 papers (next batches: PART_5, PART_6, etc., in groups of 17)

## Master Index — All 18 Papers

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

## Theme Clusters

### Cluster A: Skill Layer (Papers 18, 24, 28, 32)
Skills as the unit of reuse, composition, and evolution.
- **18 (SoK):** Formal skill tuple `(C, π, T, R)`, 7 design patterns, ClawHavoc case study
- **24 (SkVM):** Skills as code, capability profiles, JIT solidification (40% token reduction, 3.2× speedup, 19-50× latency)
- **28 (GEMS):** Agent Skill library with on-demand loading
- **32 (SemaClaw):** DAG-based 2-phase orchestration, PermissionBridge, 3-tier context

### Cluster B: Harness / Runtime (Papers 19, 20, 22, 23, 30, 32)
The runtime that orchestrates the agent.
- **19 (MCP):** Tool descriptions as the interface contract
- **20 (Meta-Harness):** Filesystem-based harness optimization, Pareto frontier
- **22 (AlphaLab):** Domain adapters as primitive, 3-phase pipeline
- **23 (Runtime Governance):** Policy-constrained execution, 96.2% interception
- **30 (SGH):** Scheduler-theoretic framework, immutable plan versions
- **32 (SemaClaw):** Open-source multi-agent framework

### Cluster C: Policy & Memory (Papers 21, 23, 28, 29, 30)
Externalized cognition, memory, and governance.
- **21 (NLAH+IHR):** Natural-language policy harness, 5 writing principles
- **23 (Runtime Governance):** Policy enforcement layer
- **28 (GEMS):** Hierarchical agent memory (project/session/step)
- **29 (Externalization):** Unifying review of memory/skills/protocols
- **30 (SGH):** Plan versioning for auditability

### Cluster D: Debugging & Verification (Papers 25, 27, 28, 31)
Closed-loop validation, testing, evaluation.
- **25 (DebugHarness):** Pattern-guided investigation, 90% patch success
- **27 (AEC-Bench):** Standardized rubric, 6 universal harness techniques
- **28 (GEMS):** Verifier-in-the-loop generation
- **31 (Reductions):** Multi-layer verification, 100+ problem types, 200+ rules in 170K Rust LoC

### Cluster E: Security & Governance (Papers 23, 32, 35)
Threat models, supply-chain attacks, audit pipelines.
- **23 (Runtime Governance):** Behavioral policy enforcement
- **32 (SemaClaw):** PermissionBridge, 4-stage safety check
- **35 (SkillProbe):** 3-stage audit, 90% of popular skills fail audit, popularity-security paradox

### Cluster F: Protocol & Model-Specific (Papers 19, 26, 33, 34)
Model harnesses, message formats, deployment.
- **19 (MCP):** Standard tool-calling protocol
- **26 (Harmony):** Native OpenAI message format (bypasses Chat Completions)
- **33 (ClawGUI):** 17-action GUI space, Android/HarmonyOS/iOS
- **34 (OpenEarth-Agent):** Tool creation (vs calling) for open environments

## How to Use This Survey

1. **Building a skill?** Start with Paper 18 (formal definition), Paper 24 (compilation).
2. **Building a tool?** Start with Paper 19 (MCP schema), Paper 34 (tool creation).
3. **Building governance?** Start with Paper 23 (policy), Paper 32 (PermissionBridge), Paper 35 (audit).
4. **Building a memory system?** Start with Paper 21 (NLAH), Paper 28 (GEMS), Paper 29 (Externalization).
5. **Building a multi-agent system?** Start with Paper 22 (AlphaLab), Paper 30 (SGH), Paper 32 (SemaClaw).
6. **Evaluating your system?** Start with Paper 27 (AEC-Bench), Paper 33 (ClawGUI-Eval).
7. **Debugging failures?** Start with Paper 25 (DebugHarness).

## Next Batches

- **PART_5:** Papers 36-52 (next 17)
- **PART_6:** Papers 53-69
- **PART_7:** Papers 70-86
- **PART_8:** Papers 87-103
- **PART_9:** Papers 104-120
- **PART_10:** Papers 121-129 (final 9)

