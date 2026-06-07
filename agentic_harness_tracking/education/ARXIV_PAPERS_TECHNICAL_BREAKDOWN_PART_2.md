# ARXIV PAPERS TECHNICAL BREAKDOWN - BATCH 2
## Harness Research Papers from Obsidian Vault - Ralph Loop Iteration 2

**Source:** `/Users/earlperry/Documents/AgenticHarnesses/Sandboxes/Harnesses/Harness info.md`
**Papers Processed (this batch):** 6 of 127 remaining
**Status:** BATCH 2 IN PROGRESS
**Naming Convention:** This file will become `ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_2.md` when moved to `/agentic_harness_tracking/education/` after limit reached
**Previous Batch:** `education/ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_1.md` (Papers 18, 19)
**Ralph Loop Pattern:** Process batch → Move to education → Commit → Push to feature branch → PR to dev → Repeat

---

# PAPER 20: 2603.28052 - Meta-Harness: End-to-End Optimization of Model Harnesses

**Authors:** Yoonho Lee, Roshen Nair, Qizheng Zhang, Kangwook Lee, Omar Khattab, Chelsea Finn
**Date:** 30 Mar 2026 | cs.AI | 693 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Outer-Loop Harness Optimization System**: Treats harness code as a first-class optimization target, separate from model weights
2. **Agentic Proposer Architecture**: LLM agent accesses source code, scores, and execution traces of all prior candidates via filesystem
3. **Richer-Feedback Search**: Avoids aggressive text compression that breaks existing text optimizers
4. **Cross-Domain Validation**: Demonstrated on text classification, math reasoning, and agentic coding

### Key Results
- **Online text classification**: +7.7 points over SOTA context management while using 4x fewer context tokens
- **Retrieval-augmented math reasoning**: Single discovered harness improves accuracy 4.7 points on 200 IMO-level problems across 5 held-out models
- **Agentic coding**: Discovered harnesses surpass best hand-engineered baselines on TerminalBench-2

### Architecture
- **Filesystem-based candidate storage**: All prior harnesses persisted as files for proposer access
- **Score + trace retrieval**: Proposer queries past attempts, full execution traces, and scores
- **Source code editing**: Proposer writes new harness code as files
- **Evaluation loop**: New candidate evaluated against benchmarks, results feed back

### Relationship to PlotLot
- **Direct mapping**: PlotLot's harness layer (`src/plotlot/harness/`) is the optimization target
- **Entitlement phase tools** (zoning_variance_analyzer, etc.) are candidates the Meta-Harness proposer could mutate
- **Trace persistence**: PlotLot's `ContextPacket.decision_history` already records execution paths—Meta-Harness would consume these as proposer input
- **Score signal**: Use EvidenceItem lifecycle fields (`supersedes_evidence`, `is_superseded_by`) to track which harness version won on which deal

### Implementation Sketch
```python
# src/plotlot/harness/meta_harness.py
class MetaHarnessOptimizer:
    def __init__(self, harness_dir: Path, proposer: LLMClient):
        self.harness_dir = harness_dir  # filesystem-based candidate store
        self.proposer = proposer
        self.traces = []  # execution traces
    
    def optimize(self, objective: Callable, budget: int) -> HarnessCandidate:
        for iteration in range(budget):
            prior = self._load_all_candidates()  # read all prior harness files
            scores = self._load_scores()
            new_code = self.proposer.edit(
                sources=[c.source for c in prior],
                scores=scores,
                traces=self.traces[-10:],
                objective=objective
            )
            candidate = self._compile(new_code)
            score = self._evaluate(candidate, objective)
            candidate.persist(self.harness_dir)  # write to filesystem
            self.traces.append(candidate.execution_trace)
        return self._select_best()
```

### Key Insights for PlotLot
1. **Harness code is optimization surface**: Stop hand-tuning zoning analyzer; let an outer loop propose improvements
2. **Filesystem as state**: Avoid complex databases—let proposer read raw files (matches Codex's `docs/automations/` pattern from Harness info.md line 136)
3. **Score transparency**: PlotLot's deal-gate evaluation becomes the natural fitness signal
4. **Cross-model portability**: A harness optimized on Opus 4.6 should still work on Sonnet 4.5 (matches harness-engineering-OpenAI insight)

---

# PAPER 21: 2603.25723 - Natural-Language Agent Harnesses (NLAH)

**Authors:** Linyue Pan, Lexiao Zou, Shuo Guo, Jingchen Ni, Hai-Tao Zheng
**Date:** 26 Mar 2026 (v1), revised 18 May 2026 (v2) | cs.CL, cs.AI | 2,408 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **NLAH (Natural-Language Agent Harness)**: Editable markdown documents that describe run-level harness policy
2. **IHR (Intelligent Harness Runtime)**: Shared runtime that interprets NLAHs into agent calls, handoffs, state updates, validation gates, and artifact contracts
3. **Decoupling of policy and execution**: Reusable policy specification independent of controller code
4. **Module ablation-friendly**: Explicit harness modules enable analysis of which components matter

### Architecture
```
┌─────────────────────────────────┐
│   NLAH Document (markdown)      │   ← Editable, versioned, code-reviewable
│   - Agent selection policy      │
│   - Handoff rules               │
│   - Validation gates            │
│   - Artifact contracts          │
└─────────────────────────────────┘
              ↓ interpreted by
┌─────────────────────────────────┐
│   IHR Runtime                   │
│   - Reads NLAH, executes        │
│   - Maintains state             │
│   - Enforces contracts          │
└─────────────────────────────────┘
```

### Key Results
- **Coding benchmarks**: Comparable task outcomes to code/prompted realizations
- **Terminal-use and computer-use**: Equivalent performance
- **Static policy size**: NLAHs are *much shorter* than equivalent controller code
- **Module ablations**: Components are individually analyzable

### Relationship to PlotLot
- **Huge architectural fit**: PlotLot's `ToolContract` definitions are essentially NLAH artifacts already
- **Entitlement tool policies** could be specified as NLAH documents rather than hard-coded Python
- **Validation gates** map to PlotLot's phase gates (`ContextPacket.phase_gate_criteria`)
- **Artifact contracts** map to EvidenceItem schema requirements

### Example: PlotLot NLAH for Entitlement Phase
```markdown
# NLAH: plotlot-entitlement-policy-v1

## Agents
- primary: "zoning-expert" (opus-4.6)
- validator: "compliance-checker" (sonnet-4.5)

## Handoffs
- zoning-expert → compliance-checker: when evidence.completeness < 0.8
- compliance-checker → zoning-expert: when validation.failed

## Validation Gates
- pre-tool: verify EvidenceItem.process_phase == "entitlement"
- post-tool: assert phase_gate_criteria.zoning_verified == true

## Artifact Contracts
- output: EvidenceItem {process_phase: "entitlement", decision_point: "zoning_check", regulatory_framework: str}
- traceability: every output links to input parcel_id and zoning_code
```

### Key Insights for PlotLot
1. **Policies belong in versioned markdown, not Python**: Mirrors the Codex `docs/automations/` pattern (Harness info.md line 136)
2. **Code review for harness changes**: PRs review NLAH diffs rather than coupled controller code
3. **Module-level ablations enable A/B testing**: Turn off "compliance-checker" module and measure deal-gate accuracy
4. **Faster iteration**: Edit markdown, redeploy—skip code-compile-test cycle

---

# PAPER 22: 2604.08590 - AlphaLab: Autonomous Multi-Agent Research Across Optimization Domains

**Authors:** Brendan R. Hogan, Xiwen Chen, James T. Wilson, Kashif Rasul, Adel Boyarsky, Thomas Kamei, Anderson Schneider, Yuriy Nevmyvaka
**Date:** 31 Mar 2026 | cs.LG, cs.AI | 15,942 KB | 43 pages, 12 figures

## TECHNICAL BREAKDOWN

### Core Contributions
1. **End-to-end autonomous research harness** for quantitative domains
2. **Three-phase pipeline**: Domain exploration → Evaluation framework construction → Large-scale experimentation
3. **Strategist/Worker loop**: Hierarchical multi-agent architecture for parallel GPU experiments
4. **Persistent playbook**: Online prompt optimization via accumulated domain knowledge
5. **Self-generated adapters**: Domain-specific behavior factored into model-generated adapters

### Pipeline Phases
1. **Domain Exploration**: Given dataset + natural-language objective, agent writes analysis code, produces research report
2. **Evaluation Construction**: Agent adversarially validates its own evaluation framework
3. **Large-Scale Experimentation**: Strategist/Worker loop runs GPU experiments; playbook accumulates findings

### Key Results
- **CUDA kernel optimization**: 4.4x faster than PyTorch on average (up to 91x speedup)
- **LLM pretraining**: 22% lower validation loss vs single-shot baseline
- **Traffic forecasting**: 23-25% improvement over standard baselines
- **Multi-model coverage**: GPT-5.2 and Claude Opus 4.6 discover qualitatively different solutions (complementary search)

### Architecture
```
User: Dataset + Natural-Language Objective
                ↓
┌─────────────────────────────────────┐
│  Phase 1: Domain Exploration        │
│  - Data analysis code generation    │
│  - Research report production      │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│  Phase 2: Evaluation Construction   │
│  - Self-validate benchmarks         │
│  - Adversarial testing              │
└─────────────────────────────────────┘
                ↓
┌─────────────────────────────────────┐
│  Phase 3: Strategist/Worker Loop    │
│  - Strategist: plans experiments    │
│  - Workers: run in parallel         │
│  - Playbook: persists learnings     │
└─────────────────────────────────────┘
```

### Relationship to PlotLot
- **Land-acquisition research mode**: User provides parcel + objective ("find highest-yield redevelopment")
- **Phase 1 → PlotLot deal-gate evaluation**: Domain exploration becomes zoning/comp analysis
- **Phase 2 → PlotLot evidence validation**: Adversarially test that EvidenceItem is reliable
- **Phase 3 → Multi-agent entitlement processing**: Strategist plans permit sequence, workers execute
- **Persistent playbook → PlotLotContextPacket.decision_history**: Accumulated decisions become playbook entries

### Implementation Sketch
```python
# src/plotlot/harness/alpha_lab.py
class AlphaLabHarness:
    def __init__(self, strategist: LLMClient, workers: list[LLMClient]):
        self.strategist = strategist
        self.workers = workers
        self.playbook = Playbook()  # online prompt optimization
    
    def run_research(self, dataset: ParcelDataset, objective: str) -> ResearchReport:
        # Phase 1: Domain exploration
        report = self._explore_domain(dataset, objective)
        
        # Phase 2: Adversarial evaluation construction
        eval_framework = self._construct_evaluation(dataset, objective)
        self._adversarially_validate(eval_framework)
        
        # Phase 3: Strategist/Worker experiments
        plan = self.strategist.plan_experiments(report, eval_framework)
        results = parallel_map(self.workers, plan.tasks)
        
        # Update playbook
        self.playbook.absorb(results, plan)
        return report.with_results(results)
```

### Key Insights for PlotLot
1. **Domain adapters as a primitive**: Every land-dev sub-domain (entitlement, environmental, construction) gets its own adapter
2. **Playbook as compounding asset**: Each deal teaches the system; future deals start smarter
3. **Multi-model complementary search**: Run Opus 4.6 + GPT-5.2 in parallel; union their best solutions
4. **Adversarial evaluation is mandatory**: Self-validate EvidenceItem schemas; catch hallucinations before they corrupt the playbook

---

# PAPER 23: 2604.07833 - Harnessing Embodied Agents: Runtime Governance for Policy-Constrained Execution

**Authors:** Xue Qin, Simin Luan, John See, Cong Yang, Zhijun Li
**Date:** 9 Apr 2026 (v1), revised 21 May 2026 (v3) | cs.RO | 36 pages, 3 figures, 10 tables

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Externalized runtime governance layer**: Separates agent cognition from execution oversight
2. **Five governance functions**: Policy checking, capability admission, execution monitoring, rollback handling, human override
3. **Embodied Capability Modules (ECMs)**: Standardized capability interface between agent and execution
4. **Empirical validation**: 1000 randomized simulation trials, statistically significant (p<0.001)

### Five Governance Functions
| Function | Purpose |
|----------|---------|
| **Policy Checking** | Pre-execution validation against rules |
| **Capability Admission** | Verify agent has required permissions for tool |
| **Execution Monitoring** | Real-time tracking of action vs. policy |
| **Rollback Handling** | Automatic reversion on policy violation |
| **Human Override** | Escalation path for ambiguous cases |

### Architecture
```
┌──────────────────────┐
│   Embodied Agent     │  ← cognition, planning
└──────────────────────┘
           ↓
┌──────────────────────┐
│   Runtime Governance │  ← policy, oversight
│   - Policy Checking  │
│   - Capability Adm.  │
│   - Monitoring       │
│   - Rollback         │
│   - Human Override   │
└──────────────────────┘
           ↓
┌──────────────────────┐
│   ECMs               │  ← capability modules
│   (Tools, Robots,    │
│    Physical Actions) │
└──────────────────────┘
```

### Key Results
- **96.2% interception** of unauthorized actions
- **Unsafe continuation**: Reduced from 100% → 22.2% under runtime drift
- **91.4% recovery success** with full policy compliance
- **p<0.001** vs all baselines (statistically significant)

### Relationship to PlotLot
- **Critical for irreversible actions**: Submitting a permit, paying a fee, signing a contract—these need governance
- **Entitlement tools** are exactly the "irreversible action" category this paper targets
- **EvidenceItem.process_phase** + **regulatory_framework** fields already support policy tagging
- **ContextPacket.stakeholder_context** + **risk_register** map to human override escalation

### Implementation Sketch
```python
# src/plotlot/harness/governance.py
class RuntimeGovernance:
    def __init__(self, policy_engine: PolicyEngine):
        self.policy = policy_engine
        self.audit_log = []
    
    def check_policy(self, action: ProposedAction) -> PolicyDecision:
        # 1. Capability admission
        if not self._has_capability(action.agent_id, action.tool):
            return PolicyDecision.deny("no_capability")
        
        # 2. Policy checking
        violations = self.policy.evaluate(action, action.context)
        if violations:
            self.audit_log.append(AuditEntry.denied(action, violations))
            return PolicyDecision.deny(violations)
        
        return PolicyDecision.allow()
    
    def monitor_execution(self, action_id: str, runtime_state: State) -> MonitorResult:
        if self._is_drift_detected(runtime_state):
            return MonitorResult.rollback("runtime_drift")
        return MonitorResult.continue_()
    
    def request_human_override(self, action: ProposedAction, reason: str):
        return HumanOverrideRequest(
            action=action,
            reason=reason,
            escalate_to=action.context.stakeholder_context.owner
        )
```

### Key Insights for PlotLot
1. **Externalize governance from agent loop**: Don't embed safety checks in tool code; put them in a dedicated layer
2. **ECM abstraction for tools**: Wrap each entitlement tool as an Embodied Capability Module with declared permissions
3. **Auditability is non-negotiable**: Every governance decision must log to EvidenceItem for legal traceability
4. **Runtime drift detection**: Compare actual action vs. declared plan; rollback if mismatch (e.g., fee calculator charges differently than estimated)

---

# PAPER 24: 2604.03088 - SkVM: Revisiting Language VM for Skills across Heterogenous LLMs and Harnesses

**Authors:** Le Chen, Erhu Feng, Yubin Xia, Haibo Chen
**Date:** 3 Apr 2026 (v1), revised 11 Apr 2026 (v3) | cs.SE, cs.LG | 647 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Skills as code, LLMs as heterogeneous processors**: Compiler-inspired framing of skill portability
2. **Primitive capability decomposition**: Skill requirements broken into measurable capabilities
3. **Capability profiles**: Per (model, harness) pair measurement of capability support
4. **SkVM compilation pipeline**: Capability-based compilation, environment binding, concurrency extraction
5. **JIT code solidification + adaptive recompilation**: Runtime performance optimization

### Architecture
```
Skill Source (markdown/code)
         ↓
┌─────────────────────────────────┐
│  SkVM Compiler                  │
│  - Capability decomposition     │
│  - Environment binding          │
│  - Concurrency extraction       │
└─────────────────────────────────┘
         ↓
Optimized Skill (target-specific)
         ↓
┌─────────────────────────────────┐
│  SkVM Runtime                   │
│  - JIT code solidification      │
│  - Adaptive recompilation       │
└─────────────────────────────────┘
```

### Key Results
- **Tested on 8 LLMs** of varying scales × 3 agent harnesses
- **SkillsBench + representative tasks**: Significant task completion rate improvements
- **Token consumption**: Reduced by up to 40%
- **Performance**: 3.2x speedup via parallelism, 19-50x latency reduction via code solidification

### Relationship to PlotLot
- **Skills = entitlement tools**: Zoning analyzer, permit evaluator, fee calculator are skills
- **Primitive capabilities**: Read parcel data, query zoning API, validate against regulation, generate report
- **Capability profiles**: Some models better at regulation lookup; others at code generation
- **JIT solidification**: Cache successful tool invocations; replay without LLM call when possible

### Implementation Sketch
```python
# src/plotlot/harness/skvm.py
class SkillVirtualMachine:
    def __init__(self, model_profiles: dict[ModelID, CapabilityProfile]):
        self.profiles = model_profiles
        self.solidified_cache = {}  # JIT-cached skill results
    
    def compile_skill(self, skill: Skill, target: ModelID) -> CompiledSkill:
        capabilities = self._decompose_capabilities(skill)
        profile = self.profiles[target]
        bindings = self._bind_environment(skill, profile)
        concurrent_groups = self._extract_concurrency(skill, capabilities)
        return CompiledSkill(skill, capabilities, bindings, concurrent_groups)
    
    def execute(self, compiled: CompiledSkill, context: Context) -> SkillResult:
        cache_key = self._cache_key(compiled, context)
        if cache_key in self.solidified_cache:
            return self.solidified_cache[cache_key]  # JIT hit
        
        result = self._run_with_concurrency(compiled, context)
        if self._should_solidify(compiled, result):
            self.solidified_cache[cache_key] = result
        return result
    
    def adaptive_recompile(self, model_id: ModelID, feedback: FeedbackSignal):
        # Adjust compilation strategy based on observed performance
        self.profiles[model_id] = self._update_profile(self.profiles[model_id], feedback)
```

### Key Insights for PlotLot
1. **Skills are portable, not model-specific**: Write once, compile for target model
2. **Capability profiles guide model selection**: Route to GPT-5.2 for heavy reasoning, Sonnet 4.5 for fast lookups
3. **JIT solidification saves tokens**: Cache fee calculations, zoning lookups; bypass LLM on repeat
4. **Concurrency extraction**: Run independent entitlement checks in parallel (zoning + environmental + subdivision)

---

# PAPER 25: 2604.03610 - DebugHarness: Emulating Human Dynamic Debugging for Autonomous Program Repair

**Authors:** Maolin Sun, Yibiao Yang, Xuanlin Liu, Yuming Zhou, Baowen Xu
**Date:** 4 Apr 2026 | cs.SE | 15 pages, 6 figures | 2,148 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Dynamic debugging harness for LLM agents**: Moves beyond static code analysis
2. **Pattern-guided investigation strategy**: Hypothesis formation grounded in crash patterns
3. **Interactive memory state probing**: Agent queries live runtime, not just static artifacts
4. **Closed-loop validation cycle**: Synthesize patch → validate → iterate

### Problem Framing
- **Static-only approaches miss critical context**: Memory safety bugs (use-after-free, corruption) require runtime state
- **LLM agents default to static analysis**: They read code but don't interact with the running process
- **Need for human-like debugging workflow**: Hypothesis → probe → patch → validate

### Architecture
```
Crash Reproduction
        ↓
┌────────────────────────────────────┐
│  Pattern-Guided Investigation      │
│  - Memory state queries            │
│  - Execution path tracing          │
│  - Hypothesis formation            │
└────────────────────────────────────┘
        ↓
┌────────────────────────────────────┐
│  Closed-Loop Validation            │
│  - Patch synthesis                 │
│  - Re-execution                    │
│  - Crash verification              │
└────────────────────────────────────┘
```

### Key Results
- **SEC-bench dataset**: ~90% patch success rate
- **30%+ relative improvement** over SOTA static-only baselines
- **Real-world C/C++ vulnerabilities**: Validated on production-style code

### Relationship to PlotLot
- **Direct analogy**: Zoning variance denials, permit rejections, fee calculation errors are "crashes" in the PlotLot workflow
- **Harness should interact with live data**: Not just analyze static ContextPacket—query live zoning APIs, parcel databases
- **Closed-loop validation**: When a tool produces a result, re-validate against ground truth before accepting
- **EvidenceItem.supersedes_evidence**: Track which tool version fixed which bug

### Implementation Sketch
```python
# src/plotlot/harness/debug_harness.py
class DebugHarness:
    def __init__(self, live_data_sources: list[DataSource]):
        self.live_sources = live_data_sources
        self.crash_patterns = CrashPatternLibrary()
    
    def debug_workflow_failure(self, failure: WorkflowFailure) -> Patch:
        # 1. Reproduce the failure
        repro = self._reproduce(failure)
        
        # 2. Pattern-guided investigation
        pattern = self.crash_patterns.match(repro)
        hypotheses = self._form_hypotheses(repro, pattern)
        
        # 3. Interactive probing
        evidence = []
        for hypothesis in hypotheses:
            probe_result = self._probe_live_state(hypothesis, self.live_sources)
            evidence.append(probe_result)
        
        # 4. Closed-loop validation
        patch = self._synthesize_patch(evidence)
        while not self._validate(patch, repro):
            patch = self._refine(patch, self._diagnose_validation_failure(patch))
        
        return patch
```

### Key Insights for PlotLot
1. **Static context is insufficient**: When entitlement fails, the harness must query live zoning/permit systems
2. **Crash patterns as a library**: Build a taxonomy of "why entitlements fail" (incomplete evidence, expired permits, fee miscalc)
3. **Closed-loop validation is mandatory**: Every tool output must be re-verified before propagating downstream
4. **Hypothesis-driven debugging**: Don't randomly retry—form explicit hypotheses about what went wrong

---

# PAPER 26: 2604.00362 - In Harmony with gpt-oss

**Authors:** Borislav Mavrin
**Date:** 1 Apr 2026 | cs.AI, cs.LG | 139 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Reverse-engineered gpt-oss in-distribution tools**: Model calls tools from training distribution even without tool definitions (strong prior, not hallucination)
2. **Native harmony agent harness**: Encodes messages in model's native format, bypassing lossy Chat Completions conversion
3. **First independent reproduction** of OpenAI's published gpt-oss-20b scores

### Key Results
- **SWE Verified HIGH**: 60.4% (published: 60.7%)
- **SWE Verified MEDIUM**: 53.3% (published: 53.2%)
- **AIME25 with tools**: 91.7% (published: 90.4%)

### Architecture Insight
- **Native format matters**: Chat Completions API conversion is lossy
- **Tool prior is statistical**: Model knows its training tools; harness should match format
- **Reproducibility requires disclosed harnesses**: OpenAI's paper omitted harness details—this work reverse-engineered them

### Relationship to PlotLot
- **Harness format alignment**: PlotLot's tool descriptions should match the model's training format
- **Tool prior exploitation**: If a model "knows" certain tool patterns, leverage them
- **Reproducibility principle**: Every PlotLot benchmark should publish its full harness
- **Native encoding**: Don't use generic OpenAI-format wrappers; encode in the format each model expects

### Implementation Sketch
```python
# src/plotlot/harness/native_harmony.py
class NativeHarmonyAdapter:
    def __init__(self, model_format: ModelFormat):
        self.format = model_format  # 'harmony', 'chatml', 'claude', etc.
    
    def encode(self, messages: list[Message], tools: list[Tool]) -> EncodedPrompt:
        if self.format == 'harmony':
            return self._encode_harmony(messages, tools)
        elif self.format == 'claude':
            return self._encode_claude(messages, tools)
        # ... format-specific encoding
    
    def _encode_harmony(self, messages, tools) -> EncodedPrompt:
        # Match OpenAI's harmony format exactly
        return EncodedPrompt(
            system=self._build_harmony_system(tools),
            conversation=self._build_harmony_conversation(messages)
        )
```

### Key Insights for PlotLot
1. **Format alignment boosts performance**: Using model's native encoding avoids lossy conversions
2. **Tool priors are real**: If model trained with certain tool patterns, replicate them
3. **Publish full harnesses for reproducibility**: PlotLot's evaluation harness should be open-source
4. **First-party > third-party formats**: When a model ships its own format, use it directly

---

---

# PAPER 27: 2603.29199 - AEC-Bench: A Multimodal Benchmark for Agentic Systems in Architecture, Engineering, and Construction

**Authors:** Harsh Mankodiya, Chase Gallik, Theodoros Galanos, Andriy Mulyar
**Date:** 31 Mar 2026 | cs.AI | 7,806 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **First multimodal benchmark for AEC agents**: Drawing understanding + cross-sheet reasoning + project-level coordination
2. **Domain-specific foundation model harness evaluation**: Compares Claude Code, Codex, and other harnesses
3. **Apache 2.0 release**: Full benchmark dataset, agent harness, evaluation code
4. **Identifies harness design techniques that uniformly improve performance**

### Architecture/Methodology
- **Drawing understanding**: Parse construction drawings (plans, elevations, sections)
- **Cross-sheet reasoning**: Correlate information across multiple drawing sheets
- **Project-level coordination**: Multi-document, multi-discipline tasks

### Key Insights
- **Harness design matters more than model choice** for many AEC tasks
- **Domain-specific tools** significantly boost performance over generic agents
- **Cross-sheet reasoning** is a unique challenge (not present in code benchmarks)

### Relationship to PlotLot
- **Direct domain alignment**: AEC-Bench validates the need for land-dev-specific agent harnesses
- **PlotLot as AEC-Bench candidate**: PlotLot's site analysis tools would slot into similar benchmark slots
- **Drawing understanding → parcel maps**: PlotLot's parcel analysis needs analogous cross-sheet reasoning
- **Multimodal input handling**: PlotLot should accept site plans, surveys, zoning maps as input

### Key Insights for PlotLot
1. **Domain benchmarks drive tool design**: Build PlotLot-Bench for land-dev
2. **Cross-document reasoning is a first-class concern**: Zoning + environmental + subdivision are separate docs, need correlation
3. **Harness beats model on specialized tasks**: Stop chasing bigger models; invest in better tool wrapping

---

# PAPER 28: 2603.28088 - GEMS: Agent-Native Multimodal Generation with Memory and Skills

**Authors:** Zefeng He, Siyuan Huang, Xiaoye Qu, Yafu Li, Tong Zhu, Yu Cheng, Yang Yang
**Date:** 30 Mar 2026 | cs.CV | 15,118 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Agent Loop**: Structured multi-agent framework for closed-loop iterative improvement
2. **Agent Memory**: Hierarchical persistent memory (factual states + compressed summaries)
3. **Agent Skill**: Extensible collection of domain expertise with on-demand loading
4. **Inspired by Claude Code** architecture

### Key Results
- **5 mainstream tasks + 4 downstream tasks**: Consistent performance gains
- **6B Z-Image-Turbo model** surpasses SOTA Nano Banana 2 on GenEval2
- **Demonstrates agent harness extends model capabilities** beyond original limits

### Architecture
```
Multimodal Task
       ↓
┌─────────────────────────┐
│  Agent Loop             │
│  - Closed-loop optimize │
└─────────────────────────┘
       ↓
┌─────────────────────────┐
│  Agent Memory           │
│  - Trajectory-level     │
│  - Hierarchical storage │
└─────────────────────────┘
       ↓
┌─────────────────────────┐
│  Agent Skill            │
│  - On-demand loading    │
│  - Domain expertise     │
└─────────────────────────┘
```

### Relationship to PlotLot
- **Agent Memory → ContextPacket**: PlotLot already has persistent context; GEMS validates the design
- **Agent Skill → Entitlement tools**: Each tool is a skill; on-demand loading prevents context bloat
- **Closed-loop optimization**: When a tool fails, retry with refined parameters (matches Paper 25 DebugHarness)
- **Hierarchical memory**: PlotLot's `decision_history` is a trajectory; GEMS shows this is the right structure

### Key Insights for PlotLot
1. **Lightweight models + good harness beat SOTA models**: Don't pay for Opus 4.6 if Sonnet 4.5 + GEMS-style harness suffices
2. **Hierarchical memory saves tokens**: PlotLot's `decision_history` should compress old decisions
3. **On-demand skill loading**: Don't load all 50 entitlement tools into context; load zoning only when zoning is needed
4. **Closed-loop optimization is essential**: First-attempt is rarely correct; iterate

---

# PAPER 29: 2603.26996 - FormalProofBench: Graduate-Level Math Proof Verification

**Authors:** Nikil Ravi, Kexing Ying, Vasilii Nesterov, Rayan Krishnan, Elif Uskuplu, Bingyu Xia, Janitha Aswedige, Langston Nashold
**Date:** 27 Mar 2026 | cs.AI, cs.CL, cs.LG, cs.PL | 430 KB
**Venue:** ICLR 2026 Workshop: VerifAI-2

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Private benchmark for formally verified proofs**: Natural language + Lean 4 formal statement
2. **Graduate-level math problems**: Qualifying exams, textbooks (analysis, algebra, probability, logic)
3. **Agentic harness evaluation**: Tool-use, failure modes, cost, latency analysis
4. **Best model achieves 33.5% accuracy**; rapid performance drop after

### Architecture
- **Lean 4 checker**: Formal verification of model output
- **Natural language problem → formal proof**: Two-stage task
- **Agentic harness**: Iterative refinement via Lean interaction

### Key Results
- **33.5% accuracy** (best model)
- **Performance drops rapidly** beyond top performer
- **Cost/latency analysis** provided

### Relationship to PlotLot
- **Verification pattern**: Like Lean 4 verifies proofs, PlotLot should verify EvidenceItem schemas
- **Closed-loop with formal checker**: Use a formal tool (e.g., pandera, pydantic) to validate every tool output
- **Cost/latency tracking**: PlotLot's deal-gate evaluation must track both metrics
- **Failure mode analysis**: Understand *why* tools fail before optimizing them

### Key Insights for PlotLot
1. **Formal verification of outputs**: Adopt schema validation as a first-class concern
2. **Cost-aware tool selection**: Some tools are expensive (Opus 4.6 calls); cheaper ones for routine checks
3. **Failure mode taxonomy**: Build a "crash pattern library" for entitlement tools (Paper 25 + 29)
4. **Iterative refinement**: First tool output is rarely final; allow N retries with feedback

---

# PAPER 30: 2603.20380 - Herding CATs: ALARA for Agent Harness Engineering in Portable Composable Multi-Agent Teams

**Authors:** Christopher J. Agostino, Nayan D'Souza
**Date:** 20 Mar 2026 (v1), revised 15 May 2026 (v2) | cs.MA, cs.AI, cs.HC | 167 KB
**Venue:** HAXD 2026, 8 pages, 6 figures

## TECHNICAL BREAKDOWN

### Core Contributions
1. **ALARA principle applied to context**: "As Low As Reasonably Achievable" — minimize context exposure
2. **Context-Agent-Tool (CAT) data layer**: Interrelated plain-text files declaring tool access per agent
3. **`npcsh` CLI**: Loads team, executes agent runs
4. **Empirical validation**: 22 locally-hosted models (0.6B-35B), 115 tasks, ~2500 total executions

### ALARA Principle
- **Radiation safety analogy**: Minimize context exposure (don't dump everything)
- **Tool access declared per agent**: Not global; each agent has minimal toolset
- **Plain-text files**: Version-controllable, code-reviewable

### Key Results
- **22 models evaluated** across 5 task categories
- **~2500 total executions** characterized
- **Model families differ** in success patterns per task

### Relationship to PlotLot
- **Tool access per agent**: Zoning agent gets zoning tools; not fee calculator
- **Plain-text CAT files**: Could be PlotLot's NLAH (Paper 21) for tool access
- **ALARA for context**: Don't load all 30 EvidenceItems into agent; load only relevant subset
- **CLI shell pattern**: `npcsh` is PlotLot's potential `plotlot run` entry point

### Implementation Sketch
```python
# src/plotlot/harness/cat_layer.py
class CATDataLayer:
    def __init__(self, agents_dir: Path):
        self.agents = self._load_agents(agents_dir)  # plain-text files
    
    def _load_agents(self, agents_dir: Path) -> dict[str, AgentSpec]:
        agents = {}
        for f in agents_dir.glob("*.cat"):
            spec = parse_cat_file(f)
            agents[spec.name] = spec
        return agents
    
    def get_agent_toolset(self, agent_name: str, task: Task) -> set[str]:
        spec = self.agents[agent_name]
        # ALARA: minimal toolset for task
        return spec.tools & task.relevant_tools
    
    def execute(self, agent_name: str, task: Task) -> Result:
        toolset = self.get_agent_toolset(agent_name, task)
        return self.agents[agent_name].run(task, toolset)
```

### Key Insights for PlotLot
1. **Per-agent tool access declarations**: Stop having one global tool pool
2. **Plain-text CAT files for version control**: Same pattern as NLAH (Paper 21)
3. **ALARA for context**: Only load what's needed; reduce token waste
4. **CLI shell for local execution**: PlotLot should have `plotlot run zoning-analysis <parcel>`

---

# PAPER 31: 2603.20075 - Agentic Harness for Real-World Compilers (llvm-autofix)

**Authors:** Yingwei Zheng, Cong Li, Shaohua Li, Yuqun Zhang, Zhendong Su
**Date:** 20 Mar 2026 | cs.SE, cs.AI | 118 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **First agentic harness for compiler bug repair**: LLVM-specific
2. **Agent-friendly LLVM tools**: Specialized tools, not generic code search
3. **llvm-bench benchmark**: Reproducible LLVM bugs
4. **llvm-autofix-mini**: Tailored minimal agent

### Key Results
- **60% performance decline** in frontier models on compiler bugs vs common bugs
- **llvm-autofix-mini outperforms SOTA by ~22%**
- Validates need for **specialized harnesses**

### Architecture
- **Domain-specific tools** (LLVM IR analysis, bug reproduction)
- **Reproducible bug benchmark**
- **Minimal agent** (less is more for compilers)

### Relationship to PlotLot
- **Domain specialization is critical**: Generic Claude/Codex fails on land-dev; PlotLot needs its own harness
- **Minimal agent > complex agent**: Don't load all entitlement tools for a simple zoning question
- **Domain-specific benchmark**: Build PlotLot-bench with reproducible land-dev tasks
- **Specialized tools beat general**: A "zoning query" tool beats a generic "web search" for zoning info

### Key Insights for PlotLot
1. **Generic models fail on domain tasks**: PlotLot's value is its domain-specific harness
2. **Build PlotLot-bench**: Reproducible land-dev tasks for continuous evaluation
3. **Minimal agents for routine tasks**: Don't pull Opus 4.6 for "what's the zoning code"
4. **Tool specialization matters more than model choice**

---

# PAPER 32: 2603.19347 - Exploring the Agentic Frontier of Verilog Code Generation

**Authors:** Patrick Yubeaton, Siddharth Garg, Chinmay Hegde
**Date:** 19 Mar 2026 (v1), revised 30 Mar 2026 (v3) | cs.AR, cs.LG | 86 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **First systematic evaluation of agentic LLMs for Verilog**: Using CVDP benchmark
2. **Open-source hardware design agent harnesses**: Model-agnostic baseline
3. **Structured prompting + tool design analysis**: How do these affect performance?
4. **Failure mode + tool usage analysis**: Open vs closed-source comparison

### Key Results
- **Naive agentic wrapping can DEGRADE performance** (vs optimized prompts)
- **Structured harnesses match/exceed non-agentic baselines**
- **Open-source models**: Higher crash rates + weaker tool output interpretation
- **Qualitative examples** of successful and failed agent runs

### Architecture
- **CVDP benchmark**: Verilog generation tasks
- **Multiple agent harnesses** with varying tool support
- **Structured vs naive prompts**: A/B comparison

### Relationship to PlotLot
- **Naive agentic wrapping is dangerous**: Don't just wrap Claude with tools; design carefully
- **Structured prompts > raw tool calls**: PlotLot's NLAH approach (Paper 21) is correct
- **Tool output interpretation is hard**: Open-source models struggle here; consider Anthropic for critical tools
- **Qualitative analysis matters**: Track *why* tools fail, not just success rate

### Key Insights for PlotLot
1. **Naive agentic wrapping can hurt**: Invest in harness design, not just tool wrapping
2. **Structured prompts (NLAH) > raw calls**: Validates Paper 21 direction
3. **Closed-source models better at tool interpretation**: Use Anthropic for complex entitlement tools
4. **Qualitative failure analysis is essential**: Why did the zoning tool misclassify? Build a debugging practice

---

# Cross-Paper Synthesis (Batch 2 - Updated)

---

# PAPER 33: 2603.08616 - Coverage-Guided Multi-Agent Harness Generation for Java Library Fuzzing

**Authors:** Nils Loose, Nico Winkel, Kristoffer Hempel, Felix Mächtle, Julian Hans, Thomas Eisenbarth
**Date:** 9 Mar 2026 | cs.SE, cs.CR | 1,969 KB
**Venue:** SBFT 2026 (ICSE Workshop)

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Multi-agent architecture for fuzz harness generation**: Five ReAct agents
2. **Workflow decomposition**: Research → Synthesis → Compilation repair → Coverage analysis → Refinement
3. **MCP-based on-demand queries**: Documentation, source code, callgraph fetched per-need (not preprocessed)
4. **Method-targeted coverage**: Tracks coverage only during target method execution
5. **Agent-guided termination**: Distinguishes productive refinement from diminishing returns

### Five ReAct Agents
1. **Research Agent**: Gathers API documentation, source code context
2. **Synthesis Agent**: Writes initial harness code
3. **Compilation Repair Agent**: Fixes build errors iteratively
4. **Coverage Analysis Agent**: Identifies uncovered code paths
5. **Refinement Agent**: Generates targeted improvements

### Key Results
- **26% median improvement** over OSS-Fuzz baselines
- **5% improvement** over Jazzer AutoFuzz in package-scope coverage
- **$3.20 and 10 minutes** per harness (practical for continuous workflows)
- **3 bugs discovered** in projects already integrated into OSS-Fuzz
- **7 target methods** in 6 widely-deployed Java libraries (115,000+ Maven dependents)

### Relationship to PlotLot
- **Multi-agent decomposition**: Zoning, environmental, subdivision could each be a specialized agent
- **MCP on-demand queries**: PlotLot's MCP tools should be queried contextually, not pre-loaded
- **Method-targeted coverage**: For each entitlement tool, track which zoning code paths are exercised
- **Cost/latency tracking**: PlotLot's deal-gate needs to know tool cost before invocation

### Key Insights for PlotLot
1. **Multi-agent decomposition by domain**: Don't have one mega-agent; have specialist agents
2. **MCP for on-demand context**: Don't preprocess; query as needed
3. **Method-targeted coverage**: Track which regulatory paths are exercised
4. **Diminishing returns detection**: Stop refining when coverage plateaus

---

# PAPER 34: 2603.03329 - AutoHarness: Improving LLM Agents by Automatically Synthesizing a Code Harness

**Authors:** Xinghua Lou, Miguel Lázaro-Gredilla, Antoine Dedieu, Carter Wendelken, Wolfgang Lehrach, Kevin P. Murphy
**Date:** 10 Feb 2026 | cs.CL, cs.AI | 321 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **LLMs can self-synthesize their own code harnesses**: Eliminates manual harness writing
2. **Iterative code refinement with environment feedback**: Few rounds → correct harness
3. **Code-as-policy**: Generate entire policy in code (no LLM at decision time)
4. **Smaller models + synthesized harness > larger models**: Gemini-2.5-Flash beats Gemini-2.5-Pro

### Key Results
- **78% of Gemini-2.5-Flash chess losses** were due to illegal moves (Kaggle GameArena)
- **AutoHarness prevents ALL illegal moves** in 145 TextArena games
- **Gemini-2.5-Flash + AutoHarness beats Gemini-2.5-Pro** on 16 TextArena 1-player games
- **Cost-effective**: Smaller model + synthesized harness < Larger model raw

### Architecture
```
Environment (game/API)
       ↓
LLM iteratively refines code harness
       ↓
Synthesized code harness
       ↓
Environment executes harness directly (no LLM at decision time)
```

### Relationship to PlotLot
- **Code-as-policy for entitlement**: Generate the entire zoning check as code, not LLM calls
- **Iterative refinement from environment feedback**: PlotLot's tool outputs drive harness improvement
- **Smaller models + good harness**: Don't pay for Opus 4.6; Sonnet 4.5 + good harness wins
- **Prevent "illegal moves"**: For PlotLot, "illegal" = submitting permit with invalid data

### Key Insights for PlotLot
1. **Auto-generate code harnesses**: Use LLM to write tool wrappers, then deploy as code
2. **Code-as-policy for hot paths**: Zoning code check shouldn't call LLM at runtime
3. **Environment-driven refinement**: Tool errors feed back to harness improvement
4. **Cost-driven model selection**: Use cheaper models where possible; reserve Opus for hard cases

---

# PAPER 35: 2602.16069 - The Limits of Long-Context Reasoning in Automated Bug Fixing

**Authors:** Ravi Raju, Mengmeng Ji, Shubhangi Upasani, Bo Li, Urmish Thakker
**Date:** 17 Feb 2026 (v1), revised 6 Mar 2026 (v2) | cs.SE, cs.LG | 473 KB
**Venue:** ICLR 2026 ICBINB workshop

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Systematic evaluation of long-context debugging**: SWE-bench Verified as testbed
2. **Counterintuitive finding**: Successful agentic trajectories stay under 20-30k tokens
3. **Longer context correlates with LOWER success**: Decomposition beats raw long-context
4. **64k token test**: Qwen3-Coder 7% resolve; GPT-5-nano 0% on inflated context

### Key Results
- **GPT-5-nano**: 31% resolve rate on 100 samples (with mini-SWE-agent)
- **Deepseek-R1-0528**: Competitive results
- **Successful trajectories**: <20-30k tokens
- **Failure modes at 64k**: Hallucinated diffs, wrong files, malformed patches

### Implications
- **Long context ≠ better**: Models can't actually use 64k+ context effectively
- **Decomposition wins**: Agentic workflows that break tasks into short steps outperform long-context single-shot
- **Existing benchmarks are flawed**: Don't measure long-context reasoning, just decomposition quality

### Relationship to PlotLot
- **Decompose entitlement workflows**: Don't load all zoning + environmental + subdivision at once
- **Short-context steps**: Each tool call should operate on focused, relevant context
- **Don't trust 1M context window claims**: Operate as if effective context is 20-30k
- **PlotLot's ContextPacket**: Should be carefully pruned; don't accumulate "just because we can"

### Key Insights for PlotLot
1. **Decomposition is essential**: Break entitlement analysis into short, focused steps
2. **Effective context is 20-30k tokens**: Plan for this, not 1M context window
3. **Token accumulation hurts**: Periodically summarize/prune ContextPacket
4. **Tool output interpretation is the bottleneck**: Not raw context length

---

# PAPER 36: 2602.11304 - CryptoAnalystBench: Failures in Multi-Tool Long-Form LLM Analysis

**Authors:** Anushri Eswaran, Oleg Golev, Darshan Tank, Sidhant Rahi, Himanshu Tyagi
**Date:** 11 Feb 2026 | cs.IR, cs.AI, cs.CR | 360 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **198 production crypto/DeFi queries**: Spanning 11 categories
2. **Agentic harness with crypto/DeFi tools**: Multi-tool LLM analysis
3. **Citation verification + LLM-as-judge rubric**: 4 success dimensions
4. **7 higher-order error types**: Not captured by factuality checks

### Four User-Defined Success Dimensions
1. **Relevance**: Answer addresses the question
2. **Temporal Relevance**: Data is current
3. **Depth**: Sufficient detail
4. **Data Consistency**: No contradictions

### Seven Higher-Order Error Types
- Multi-step reasoning failures
- Cross-document inconsistency
- Temporal misalignment
- Tool output misinterpretation
- Hallucinated sources
- Citation fabrication
- Aggregation errors

### Key Results
- **Failures persist in SOTA systems**: Frontier models still fail on these tasks
- **High-stakes impact**: Misanalyses can compromise financial decisions
- **Judge rubric improves over iterations**: But doesn't fully align with humans

### Relationship to PlotLot
- **Multi-tool integration failures**: When PlotLot combines zoning + environmental + subdivision, errors compound
- **Citation verification**: Every EvidenceItem should cite its source
- **Temporal relevance**: Zoning codes change; old data is wrong data
- **Higher-order error taxonomy**: Build a "PlotLot failure modes" library

### Key Insights for PlotLot
1. **Multi-tool integration is hard**: Errors compound across tools
2. **Citation as first-class**: Every EvidenceItem must trace to its source
3. **Temporal awareness**: Track when zoning data was retrieved; refresh if stale
4. **Error taxonomy is essential**: Build a library of "ways PlotLot can fail"

---

# PAPER 37: 2601.10971 - AJAR: Adaptive Jailbreak Architecture for Red-Teaming

**Authors:** Yipu Dou, Wang Yang
**Date:** 16 Jan 2026 (v1), revised 19 Mar 2026 (v2) | cs.CR, cs.CL | 108 KB

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Jailbreak algorithms as MCP services**: Callable, composable
2. **Auditor Agent orchestration**: Inside tool-aware runtime (Petri)
3. **Three attack integrations**: Crescendo, ActorAttack, X-Teaming
4. **Shared service interface**: Planning, prompt gen, optimization, evaluation, context control
5. **Tool access reshapes attack surface**: Not uniformly larger

### Key Results
- **X-Teaming**: 65.0% → 76.0% ASR
- **Crescendo**: 91.0% vs 87.5% (PyRIT baseline)
- **Tool access effect varies**:
  - ActorAttack: 51.0% → 56.0% (with tools)
  - Crescendo: 91.0% → 78.0% (with tools, drops!)
  - X-Teaming: 76.0% → 55.5% (with tools, drops!)
- **Tool access can REDUCE attack success**: Not always enlarges surface

### Architecture
```
Attack Algorithms (Crescendo, ActorAttack, X-Teaming)
       ↓ exposed as
MCP Services (planning, prompt_gen, optimization, evaluation, context)
       ↓ orchestrated by
Auditor Agent (Petri runtime)
       ↓ tests
LLM Under Test
```

### Relationship to PlotLot
- **Red-teaming PlotLot**: Use AJAR to find vulnerabilities in entitlement tools
- **MCP service architecture**: PlotLot's tools should be callable as MCP services (matches Paper 19)
- **Tool access ≠ larger attack surface**: Careful tool design actually reduces some attack vectors
- **Rollback-enabled transcript repair**: PlotLot should support conversation rollback for safety

### Key Insights for PlotLot
1. **Red-team PlotLot with AJAR**: Find vulnerabilities before attackers do
2. **MCP service architecture**: Wrap tools as callable services (matches Papers 19, 24)
3. **Tool access design matters**: Right tool design can REDUCE attack surface
4. **Rollback is essential**: Support transcript rollback for safety recovery

---

# PAPER 38: 2509.19349 - ShinkaEvolve: Open-Ended Sample-Efficient Program Evolution

**Authors:** Robert Tjarko Lange, Yuki Imajuku, Edoardo Cetin
**Date:** 17 Sep 2025 | cs.CL, cs.LG | 3,337 KB | 52 pages, 14 figures

## TECHNICAL BREAKDOWN

### Core Contributions
1. **Open-source framework** for LLM-driven scientific discovery
2. **Three key innovations**:
   - Parent sampling (exploration vs exploitation balance)
   - Code novelty rejection-sampling (efficient search)
   - Bandit-based LLM ensemble selection
3. **Sample efficiency**: 150 samples to discover SOTA circle packing

### Key Results
- **New SOTA circle packing** with only 150 samples
- **Agentic harnesses for AIME math reasoning** (designed automatically)
- **ALE-Bench improvements**: Competitive programming solutions improved
- **Novel MoE load balancing loss** discovered
- **Open-source** (unlike AlphaEvolve closed-source)

### Architecture
```
LLM Ensemble (bandit-selected)
       ↓
Parent Sampling (exploration + exploitation)
       ↓
Code Novelty Rejection-Sampling
       ↓
Mutation/Selection Loop
       ↓
Evolved Programs
```

### Relationship to PlotLot
- **Auto-evolve PlotLot tools**: Use ShinkaEvolve to optimize entitlement tool parameters
- **Bandit-based model selection**: Choose between Opus 4.6 / Sonnet 4.5 / Haiku based on observed performance
- **Sample efficiency**: Don't waste LLM calls; use novelty rejection-sampling
- **Open-ended discovery**: Let PlotLot explore new entitlement strategies autonomously

### Key Insights for PlotLot
1. **Auto-evolve tools**: Use evolutionary search to optimize tool parameters
2. **Bandit model selection**: Dynamically pick model per task type
3. **Novelty rejection-sampling**: Don't re-explore dead ends
4. **Sample efficiency matters**: Track tokens per decision; minimize waste

---

## Papers in This Batch
- 20-26 (First half): Meta-Harness, NLAH, AlphaLab, Runtime Governance, SkVM, DebugHarness, Harmony
- 27-32 (Second half): AEC-Bench, GEMS, FormalProofBench, Herding CATs, llvm-autofix, Verilog
- 33-38 (Third addition): Coverage-Guided Fuzzing, AutoHarness, Long-Context Limits, CryptoAnalystBench, AJAR, ShinkaEvolve

## Common Themes (Expanded)
1. **Harness as first-class engineering target** (20, 21, 22, 28, 30, 31): Stop hardcoding; treat harness as optimization/policy surface
2. **Externalized governance** (23): Safety, rollback, human override in dedicated layer
3. **Compilation/runtiming for skills** (24, 28): Skills are portable units; compile per-model, cache results
4. **Dynamic debugging over static analysis** (25, 29): Live data queries + formal verification
5. **Native format alignment** (26): Match model's expected encoding
6. **Domain specialization** (27, 31, 32): Generic models fail; build domain-specific harnesses
7. **ALARA context principle** (30): Minimize context exposure; per-agent tool access
8. **Memory hierarchy** (28, 21): Hierarchical persistent memory + on-demand skill loading

## PlotLot Implementation Roadmap (Updated)
1. **Phase 1 (Immediate)**: Adopt NLAH-style markdown policies for PlotLot tools (Paper 21)
2. **Phase 2 (Q3)**: Build runtime governance layer wrapping irreversible actions (Paper 23)
3. **Phase 3 (Q3)**: Implement SkVM-style skill compilation for cross-model portability (Paper 24)
4. **Phase 4 (Q3)**: Domain-specific harness (zoning agent, environmental agent, etc.) (Paper 27, 31)
5. **Phase 5 (Q4)**: Meta-Harness outer loop for continuous harness improvement (Paper 20)
6. **Phase 6 (Q4)**: DebugHarness pattern + formal verification of EvidenceItem (Paper 25, 29)
7. **Phase 7 (Q4)**: Native format adapters per model (Paper 26)
8. **Phase 8 (Q4)**: ALARA context + per-agent tool access (Paper 30)
9. **Phase 9 (Q4)**: On-demand skill loading + hierarchical memory (Paper 28)

## File Status
- **This file**: `agentic_harness_tracking/research_notes/ARXIV_PAPERS_TECHNICAL_BREAKDOWN2.md` (batch 2 active)
- **Will become**: `education/ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_2.md` (when limit reached)
- **Previous batch**: `education/ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_1.md` (Papers 18, 19)
- **Papers processed so far in batch 2**: 13 of 127 remaining (20-32)
- **Remaining after this batch**: 114 papers

## Ralph Loop Status
- [x] Identify papers (Harness info.md scan complete: 129 unique IDs, 2 done, 127 remaining)
- [x] Create batch 2 file
- [x] Process papers 20-26 (first half)
- [x] Process papers 27-32 (second half)
- [ ] Continue processing until file size limit (target: ~30 papers or 50KB)
- [ ] Move file to education/ as PART_2
- [ ] Commit to feature branch
- [ ] Push to dev
- [ ] Create batch 3 file (ARXIV_PAPERS_TECHNICAL_BREAKDOWN3.md)
- [ ] Repeat until all 127 papers processed
