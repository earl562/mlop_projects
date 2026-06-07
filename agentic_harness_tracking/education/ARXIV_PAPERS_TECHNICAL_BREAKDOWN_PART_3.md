# ARXIV PAPERS TECHNICAL BREAKDOWN - BATCH 3 (DEEP DIVE)
## Harness Research Papers from Obsidian Vault - Ralph Loop Iteration 3

**Source:** `/Users/earlperry/Documents/AgenticHarnesses/Sandboxes/Harnesses/Harness info.md`
**Status:** BATCH 3 IN PROGRESS - DEEP DIVE LEVEL
**Target depth per paper:** 150-400 lines (matches Paper 19 appendix at 392 lines)
**Previous Batches (committed, pushed):**
- `education/ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_1.md` (Papers 18, 19) - 577 lines
- `education/ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_2.md` (Papers 20-38, 19 papers) - 1149 lines
**Ralph Loop Pattern:** Process paper deeply → Update batch file → When limit reached, move to education → Commit → Push to feature branch → PR to dev → Repeat

**Note on Depth:** This batch is a pivot to deeper analysis. Each paper now includes:
- Full mathematical formalism (where applicable)
- Detailed taxonomies with multi-column tables
- Threat models with specific attack vectors
- Multiple code implementation sketches (100+ lines each)
- Concrete algorithm descriptions
- Empirical baselines with specific numbers
- Failure mode analysis

---

# PAPER 21: 2603.25723 (v2) - Natural-Language Agent Harnesses (NLAHs) and Intelligent Harness Runtime (IHR)

**Authors:** Linyue Pan, Lexiao Zou, Shuo Guo, Jingchen Ni, Hai-Tao Zheng
**Affiliations:** Shenzhen International Graduate School, Tsinghua University; Harbin Institute of Technology (Shenzhen)
**Date:** 26 Mar 2026 (v1), revised 18 May 2026 (v2) | cs.CL | 2,408 KB
**Code:** Not yet released (per paper)

## TECHNICAL BREAKDOWN

### 1. Problem Statement and Motivation

Modern LLM agents are multi-step execution systems that use tools, maintain state, recover from failures, validate intermediate results, and delegate to other agents. The **harness** — the external execution system around a model — has large effects on measured performance. However, harnesses are usually not represented as clean research objects.

A code harness may mix:
- Prompts
- Tool adapters
- Parser rules
- Validation scripts
- Artifact paths
- Retry logic
- Context policy
- Benchmark-specific assumptions

...in one controller bundle. A "seemingly small harness change" can silently change call boundaries, tool mediation, state carriers, validation gates, and stopping semantics. This makes harnesses hard to **inspect, port, compare, and ablate**, even though the harness pattern itself is the reusable part.

The paper asks: **can a harness pattern be externalized as executable natural language?**

### 2. Core Definitions (Mathematical Formalism)

**Model.** A callable learned function from context c to output y, where context may include text, images, or video:

```
y = LM_m(c)
```

**Agent.** A system that wraps one or more model calls with external interaction. The atomic unit of harness execution is an **agent call** (degenerate case: a single one-shot model call with no external action).

**Harness.** The external execution system around a model in an agent. Eleven main aspects of harness engineering (Section D.1):
1. Agent loops
2. Tool design and documentation
3. Context engineering
4. Filesystem and workspace management
5. Memory and state
6. Validation and stopping conditions
7. Safety permissions and sandboxing
8. Runtime defaults
9. Observability and replay
10. Retry and recovery
11. Budget control

### 3. NLAH+IHR Architecture (Four Layers)

The NLAH+IHR system has **four layers**:

**Layer 1: Base Agent.** A code-form minimal executable substrate. In this paper, the base agent is only an LLM loop: it can call a model, with the only external tool exposed being a terminal. Through the terminal, the base agent can:
- Read and write files
- Run processes
- Record events
- Launch child agents (via `npcsh`-style command pattern, no dedicated tool needed)

**Layer 2: Runtime Policy.** A fixed instruction that turns the base agent into IHR by defining how it should interpret and execute harness documents. This is shared across all NLAHs.

**Layer 3: NLAH (Natural-Language Agent Harness).** The natural-language policy document describing:
- Stages (inspect, plan, edit, verify, recover, finalize)
- Roles
- State rules
- Verification rules
- Recovery rules
- Stopping conditions

**Layer 4: Scripts and Adapters.** Deterministic code for exact operations: tests, parsers, sandboxing, benchmark adapters, artifact validators.

### 4. The Key Separation

> The base agent and adapters provide the machine interface. The runtime policy provides shared execution semantics. The NLAH provides the per-harness policy.

IHR is intentionally thin. It uses the base agent as an orchestrator guided by the runtime policy and delegates substantive task work to child agents. For a nominally single-agent harness, IHR still realizes the run as a parent orchestrator plus one executor child. For multi-role harnesses, IHR launches separate child agents, passes each only the intended task packet, supervises handoff, and records behavior.

### 5. NLAH Writing Principles (Five Rules)

The paper codifies five writing principles for NLAHs:

**Rule 1: State the task contract first.** Define input, expected output, allowed tools/artifacts, and completion condition. For coding: patch location, test evidence, final answer format. For computer-use: target application state, allowed channels, completion evidence.

**Rule 2: Separate stages from mechanisms.** Name stages (inspect, plan, edit, verify, recover, finalize) but don't reimplement every tool in prose. Low-level operations go to scripts/adapters/runtime hooks.

**Rule 3: Make state and evidence explicit.** Specify:
- Where state is stored
- Which artifacts must be reopened by later agents
- What evidence supports a claim
- Which files/logs close the run

**Rule 4: Write module boundaries so they can be ablated.** Use clear names for modules (verifier, self-evolution, multi-candidate search, context compression, markdown memory) so they can be removed or changed without silently changing the rest.

**Rule 5: Prefer simple and enforceable language.** Use short clauses, concrete conditions, explicit artifacts. AVOID vague phrases like "be careful," "think deeply," "act like an expert." USE enforceable clauses like "write a state file before delegating," "run the verifier only after producing a candidate patch," "do not finalize without evidence from the target file."

### 6. Three Research Questions

- **RQ1 (Harness Realization):** Can NLAHs shape observable agent behavior while maintaining comparable task outcomes?
- **RQ2 (Mechanism Realization):** Do IHR-executed NLAHs preserve and materialize intended harness mechanisms (workflow structure, contract enforcement, tool use, recovery, handoff)?
- **RQ3 (Module Ablation):** Once harness modules are expressed in natural language, can they be cleanly ablated and analyzed?

### 7. Three Harness Realizations (RQ1 Comparison)

**Code Harness:** Original code implementation (controller + workflow scripts + framework defaults + tool adapters). Strongest deterministic control, but policy is interleaved with implementation details.

**Prompted NLAH:** Same NLAH content provided as ordinary prompt text to Codex CLI agent, without IHR's shared runtime charter. Tests passive instruction carrier.

**IHR-executed NLAH:** NLAH interpreted/executed by IHR, with explicit runtime semantics for child lifecycle, artifact/state handling, contract gates, and stopping. Gives up hard determinism but gives NL policy an execution substrate.

### 8. Benchmarks and Harness Families

| Benchmark Family | Domain | Metric | Harness Family Studied |
|------------------|--------|--------|------------------------|
| SWE-bench Verified | Coding | Issue resolution rate | Live-SWE-Agent |
| Terminal-Bench 2.0 (TB2) | Terminal use | Task success | MHTBA (Meta-Harness Terminal-Bench Agent) |
| OSWorld | Computer use | Task success rate | SeeAct-style GUI harness |

**Experimental setup:** Codex CLI v0.123.0, model gpt-5.4-mini, reasoning effort xhigh, Ubuntu 24.04 servers with 64 CPU cores and 251 GiB memory, Docker containers with 32 vCPUs / 84 GiB memory / 40 GiB storage per task.

### 9. RQ1 Results (Detailed Table 1)

| Benchmark | Harness | Type | Perf. | LLM Calls | Tool Calls | Pr. Tok. | Comp. Tok. | Run time (min) |
|-----------|---------|------|-------|-----------|------------|----------|------------|----------------|
| SWE Verified | Live-SWE | Code | 67.00 | 23.30 | 17.70 | 283.60k | 3.50k | 28.90 |
| SWE Verified | Live-SWE | Prompt | 77.00 | 36.40 | 48.00 | 2.20M | 27.50k | 5.70 |
| SWE Verified | Live-SWE | NLAH | **73.00** | 41.00 | 63.40 | 2.20M | 32.30k | 6.10 |
| TB2 | MHTBA | Code | 36.00 | 223.20 | 122.90 | 10.40M | 17.50k | 19.50 |
| TB2 | MHTBA | Prompt | 57.30 | 41.50 | 48.00 | 3.10M | 51.80k | 11.10 |
| TB2 | MHTBA | NLAH | **53.90** | 56.40 | 78.00 | 4.20M | 74.80k | 13.50 |
| OSWorld | SeeAct | Code | 47.10 | 23.30 | 47.80 | 1.40M | 8.90k | 9.00 |
| OSWorld | SeeAct | Prompt | 47.90 | 35.30 | 39.20 | 1.10M | 12.30k | 4.90 |
| OSWorld | SeeAct | NLAH | **46.30** | 40.90 | 48.60 | 1.10M | 13.60k | 5.50 |

**Key finding 1 (operational viability):** NLAHs achieve task performance in the same regime as code harnesses.
- Live-SWE: NLAH 73.0 > Code 67.0 (and close to Prompt 77.0)
- OSWorld: NLAH 46.3 ≈ Code 47.1
- MHTBA: NLAH 53.9 > Code 36.0 (but < Prompt 57.3)

**Key finding 2 (cost profile):** NLAHs use more model calls, tool calls, and tokens than code harnesses. This is engineering overhead, not representation unusability. The added autonomy lets models choose action granularity more flexibly.

**Key finding 3 (concise policy):** The readable harness policy is **drastically shorter** in NLAH form.

| Benchmark | Harness | Code Tokens | NLAH Tokens | Code Files | NLAH Files |
|-----------|---------|-------------|-------------|------------|------------|
| SWE Verified | Live-SWE | 60.10k | **2.90k** | 68.00 | 3.00 |
| TB2 | MHTBA | 10.50k | **0.80k** | 3.00 | 1.00 |
| OSWorld | SeeAct | 47.50k | **1.40k** | 5.00 | 1.00 |

### 10. RQ2 Results (Detailed Tables 3 and 4)

**Table 3 — Pattern preservation metrics:**

| Benchmark | Harness | Type | Verif. Signals | Prompt Contract | Tool Surface | Workflow Pres. | Stage Cov. | Ordered Workflow | Context Boundary | Model Match |
|-----------|---------|------|----------------|-----------------|--------------|----------------|------------|------------------|-----------------|-------------|
| SWE Verified | Live-SWE | Code | 3.99 | - | - | - | - | - | - | - |
| SWE Verified | Live-SWE | Prompt | 6.51 | 0.89 | 0.82 | 0.70 | 0.75 | 0.74 | 1.00 | 1.00 |
| SWE Verified | Live-SWE | NLAH | **9.89** | 0.81 | 0.87 | 0.67 | 0.82 | 0.78 | 0.76 | 0.76 |
| TB2 | MHTBA | Code | 45.05 | - | - | - | - | - | - | - |
| TB2 | MHTBA | Prompt | 13.18 | 1.00 | 0.81 | 0.64 | 0.57 | 0.53 | 1.00 | 0.99 |
| TB2 | MHTBA | NLAH | **22.82** | 0.84 | 0.80 | 0.63 | 0.57 | 0.54 | 0.81 | 0.55 |

**Table 4 — Harness-engineering mechanism metrics:**

| Benchmark | Harness | Type | Artifact Contract | Tool Call Success | Failed Tool Continuation | Cached Token Ratio | Orchestration Reliability | Information Handoff Recall |
|-----------|---------|------|-------------------|-------------------|--------------------------|-------------------|---------------------------|---------------------------|
| SWE Verified | Live-SWE | Code | 0.99 | 0.88 | 0.95 | 0.71 | NA | NA |
| SWE Verified | Live-SWE | Prompt | 0.99 | 0.93 | 0.98 | 0.96 | 1.00 | 1.00 |
| SWE Verified | Live-SWE | NLAH | **1.00** | 0.93 | **0.99** | 0.94 | 0.83 | **0.32** |
| TB2 | MHTBA | Code | NA | 0.95 | 0.79 | 0.00 | NA | NA |
| TB2 | MHTBA | Prompt | 1.00 | 0.92 | 1.00 | 0.96 | 0.99 | 1.00 |
| TB2 | MHTBA | NLAH | 0.96 | 0.93 | 1.00 | 0.94 | 0.85 | 0.55 |

**Strongest evidence:** contracts, tools, recovery. NLAH reaches 1.000 Artifact Contract (Live-SWE), 0.933 Tool Call Success, 0.992 Failed Tool Continuation. MHTBA: 0.955 / 0.928 / 0.995.

**Main weakness: handoff.** Information Handoff Recall drops from 1.00 (Prompt) to 0.322 (NLAH) on Live-SWE, and from 1.00 to 0.553 on MHTBA. Orchestration Reliability also lower.

### 11. RQ3 Results (Module Ablation Table 5)

| Setting | SWE Verified Perf. | SWE Agent Calls | OSWorld Perf. | OSWorld Agent Calls |
|---------|--------------------|-----------------|--------------|---------------------|
| Basic | 73.00 | 1.10 | 44.40 | 1.08 |
| + File-backed state | **75.60** (+2.60) | 1.10 (0.00) | **58.30** (+13.90) | 1.11 (+0.03) |
| + Evidence-backed answering | 75.80 (+2.80) | 1.20 (+0.10) | 47.20 (+2.80) | 1.06 (-0.03) |
| + Verifier | 73.20 (+0.20) | 2.30 (+1.20) | 52.80 (+8.40) | 1.42 (+0.33) |
| + Self-evolution | **78.80** (+5.80) | 1.20 (+0.10) | 52.80 (+8.40) | 1.19 (+0.11) |
| + Multi-candidate search | 71.40 (-1.60) | **5.70** (+4.60) | 47.20 (+2.80) | 1.33 (+0.25) |
| + Dynamic orchestration | 74.60 (+1.60) | 1.60 (+0.50) | 47.20 (+2.80) | 1.14 (+0.06) |
| + Context compression | 72.00 (-1.00) | 2.20 (+1.10) | 36.10 (-8.30) | 1.22 (+0.14) |
| + Markdown memory | 70.20 (-2.80) | 1.30 (+0.20) | 50.00 (+5.60) | 1.54 (+0.46) |

**Key finding:** Modules that help most tighten state and acceptance discipline (file-backed state, self-evolution, evidence-backed answering). Modules that mainly add branching without improving the path to acceptance (multi-candidate search, context compression) hurt or don't help.

### 12. OSWorld Flexible Routing Example

GUI-oriented tasks can sometimes be completed through shell commands, file edits, or package-level operations that provide clearer evidence. This flexible routing preserves harness control and reflects the benefit of expressing policy at goals/evidence/gates level — the policy need not prescribe every action primitive.

### 13. APPLICATION TO PLOTLOT

#### 13.1 NLAH Policy Document for PlotLot Entitlement Phase

```markdown
# NLAH: plotlot-entitlement-v3

## Task Contract
- **Input:** Parcel ID + jurisdiction code
- **Output:** EvidenceItem list + decision recommendation (GO/NO-GO/REVIEW)
- **Allowed tools:** zoning_query, variance_analyzer, permit_checker, environmental_screen, utility_coordinator
- **Completion condition:** All 5 tools have returned EvidenceItems AND at least 2 verifiers have signed off

## Stages

### Stage 1: Inspect
- Read parcel from PlotLotContextPacket
- Validate parcel_id is well-formed (regex: ^[A-Z]{2}-[0-9]{4}-[0-9]{6}$)
- Load jurisdiction code and check it against supported jurisdictions table
- IF jurisdiction not supported: STOP with NO-GO

### Stage 2: Plan
- Determine which entitlement tools are required based on parcel characteristics
  - Residential parcel: zoning_query, variance_analyzer, permit_checker
  - Commercial parcel: ALL 5 tools
  - Industrial parcel: zoning_query, environmental_screen, utility_coordinator
- Write plan to /state/plan.json before proceeding

### Stage 3: Edit (Execute tools in parallel)
- Launch child agent for each tool in plan
- Each child agent gets ONLY the tool spec and the parcel context slice
- Children do NOT have access to other tools
- Collect EvidenceItem from each child

### Stage 4: Verify
- Run verifier on each EvidenceItem
- EvidenceItem must satisfy schema: {process_phase, decision_point, regulatory_framework, ...}
- IF any EvidenceItem fails schema: escalate to human override
- IF all pass: proceed

### Stage 5: Recover
- IF any tool returned error: retry up to 2 times with refined prompt
- IF retry fails: log to /state/errors.json and skip that tool
- After 2 retries: STOP with REVIEW

### Stage 6: Finalize
- Aggregate EvidenceItems
- Apply decision rules:
  - All GO → recommend GO
  - Any NO-GO with regulatory_framework binding → recommend NO-GO
  - Mixed → recommend REVIEW
- Write final decision to /state/decision.json
- Emit audit log entry

## Evidence Discipline
- Every EvidenceItem must cite at least one source (parcel_id, zoning_code, permit_id)
- Every tool invocation must be logged with timestamp, agent_id, tool_name, args, result
- Every child agent must write its state to /state/children/<agent_id>.json before exiting

## Stopping Conditions
- Stage 1 fails: STOP, NO-GO
- Stage 3 has >2 tool errors: STOP, REVIEW
- Stage 4 has any schema violation: STOP, escalate
- Stage 6 writes decision: STOP, return decision
- Max runtime: 5 minutes (Budget control aspect)
```

#### 13.2 IHR Runtime Implementation for PlotLot

```python
# src/plotlot/harness/nlah_runtime.py
import json
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

@dataclass
class TaskContract:
    input_spec: dict
    output_spec: dict
    allowed_tools: list[str]
    completion_condition: str

@dataclass
class ChildAgentPacket:
    tool_name: str
    parcel_context: dict
    parent_state_path: Path
    child_state_path: Path
    allowed_tools: list[str]  # ALWAYS just [tool_name] - ALARA principle

class IntelligentHarnessRuntime:
    """
    IHR implementation for PlotLot. Executes NLAH policy documents
    as a parent orchestrator + child executor pattern.
    """
    
    def __init__(self, base_agent, model_router, policy_dir: Path):
        self.base_agent = base_agent
        self.model_router = model_router  # Workload-specialized model routing
        self.policy_dir = policy_dir
        self.runtime_policy = self._load_runtime_policy()
        self.governance_layer = self._load_governance_layer()  # Paper 23 integration
    
    def _load_runtime_policy(self) -> str:
        """Load the fixed runtime policy that turns base agent into IHR"""
        return """
        You are IHR, the Intelligent Harness Runtime. You execute NLAH policy
        documents for the PlotLot land development platform. Your responsibilities:
        
        1. Parse the NLAH to extract Task Contract, Stages, Evidence Discipline,
           and Stopping Conditions.
        2. For each stage, launch child agents via the terminal.
        3. Each child agent receives ONLY the task packet and its allowed tools.
        4. Supervise handoff between stages; record state at each transition.
        5. Enforce completion conditions; do not finalize without evidence.
        6. Respect stopping conditions exactly as written.
        
        Deterministic operations (test runs, parsers, validators) go to scripts.
        You handle policy decisions and child orchestration.
        """
    
    def execute_nlah(self, nlah_path: Path, task_input: dict) -> dict:
        """
        Execute an NLAH document against a task input.
        Returns the final decision or stopping state.
        """
        nlah = self._parse_nlah(nlah_path)
        contract = self._extract_contract(nlah)
        stages = self._extract_stages(nlah)
        stopping = self._extract_stopping_conditions(nlah)
        evidence_rules = self._extract_evidence_discipline(nlah)
        
        # Validate input against contract
        if not self._validate_input(task_input, contract):
            return {"status": "NO-GO", "reason": "invalid_input"}
        
        # Initialize state
        state = {
            "nlah_id": nlah_path.stem,
            "task_input": task_input,
            "stages_completed": [],
            "evidence_items": [],
            "audit_log": [],
            "start_time": time.time(),
        }
        state_path = Path(f"/state/{nlah_path.stem}-{task_input['parcel_id']}.json")
        state_path.write_text(json.dumps(state, indent=2))
        
        # Execute stages in order
        for stage in stages:
            if self._check_stopping(state, stopping):
                break
            state = self._execute_stage(stage, state, evidence_rules, state_path)
            state["stages_completed"].append(stage["name"])
            state_path.write_text(json.dumps(state, indent=2))
            
            # Check budget
            if time.time() - state["start_time"] > 300:  # 5 min budget
                state["status"] = "REVIEW"
                state["reason"] = "budget_exceeded"
                break
        
        return self._finalize(state, contract)
    
    def _execute_stage(self, stage: dict, state: dict, 
                       evidence_rules: dict, state_path: Path) -> dict:
        """Execute a single NLAH stage using child agents."""
        stage_name = stage["name"]
        
        if stage_name == "inspect":
            return self._stage_inspect(stage, state)
        elif stage_name == "plan":
            return self._stage_plan(stage, state)
        elif stage_name == "edit":
            return self._stage_edit(stage, state, evidence_rules)
        elif stage_name == "verify":
            return self._stage_verify(stage, state)
        elif stage_name == "recover":
            return self._stage_recover(stage, state)
        elif stage_name == "finalize":
            return self._stage_finalize(stage, state, state_path)
        else:
            raise ValueError(f"Unknown stage: {stage_name}")
    
    def _stage_edit(self, stage: dict, state: dict, 
                    evidence_rules: dict) -> dict:
        """
        Launch child agents in parallel, each with ONE tool.
        Children do NOT have access to other tools (ALARA).
        """
        plan = state.get("plan", [])
        evidence_items = []
        
        # Launch children in parallel via terminal
        child_packets = []
        for tool_spec in plan:
            packet = ChildAgentPacket(
                tool_name=tool_spec["tool_name"],
                parcel_context=state["task_input"],
                parent_state_path=Path(f"/state/{state['nlah_id']}.json"),
                child_state_path=Path(f"/state/children/{tool_spec['tool_name']}.json"),
                allowed_tools=[tool_spec["tool_name"]],  # ALARA: only this tool
            )
            child_packets.append(packet)
        
        # Parallel execution
        results = self._parallel_child_execution(child_packets)
        
        # Collect and validate evidence
        for result in results:
            if result["status"] == "success":
                evidence = result["evidence"]
                if self._validate_evidence(evidence, evidence_rules):
                    evidence_items.append(evidence)
                else:
                    state["audit_log"].append({
                        "event": "evidence_validation_failed",
                        "tool": result["tool_name"],
                        "errors": result["validation_errors"],
                    })
        
        state["evidence_items"] = evidence_items
        return state
    
    def _stage_verify(self, stage: dict, state: dict) -> dict:
        """
        Run verifier on each EvidenceItem.
        Verifier checks: schema validity, source citation, timestamp freshness.
        """
        verification_results = []
        for evidence in state["evidence_items"]:
            v = self.governance_layer.verify(evidence)  # Paper 23 integration
            verification_results.append(v)
            
        state["verification_results"] = verification_results
        state["all_verified"] = all(v["passed"] for v in verification_results)
        
        if not state["all_verified"]:
            failed = [v for v in verification_results if not v["passed"]]
            state["audit_log"].append({
                "event": "verification_failures",
                "count": len(failed),
                "details": failed,
            })
        
        return state
    
    def _stage_finalize(self, stage: dict, state: dict, 
                        state_path: Path) -> dict:
        """
        Apply decision rules and write final decision.
        """
        evidence = state["evidence_items"]
        
        if not evidence:
            state["decision"] = "NO-GO"
            state["decision_reason"] = "no_evidence"
            return state
        
        # Decision rules
        no_go_binding = any(
            e.get("regulatory_framework") == "binding" and 
            e.get("recommendation") == "NO-GO"
            for e in evidence
        )
        
        all_go = all(
            e.get("recommendation") == "GO" 
            for e in evidence
        )
        
        if no_go_binding:
            state["decision"] = "NO-GO"
        elif all_go and state.get("all_verified"):
            state["decision"] = "GO"
        else:
            state["decision"] = "REVIEW"
        
        # Persist final state
        decision_path = Path(f"/state/decisions/{state['task_input']['parcel_id']}.json")
        decision_path.parent.mkdir(parents=True, exist_ok=True)
        decision_path.write_text(json.dumps(state, indent=2))
        
        return state
    
    def _validate_evidence(self, evidence: dict, rules: dict) -> bool:
        """
        Validate EvidenceItem against evidence discipline rules.
        """
        required_fields = rules.get("required_fields", [])
        for field in required_fields:
            if field not in evidence:
                return False
        
        # Must cite at least one source
        if not evidence.get("sources"):
            return False
        
        # Timestamp must be recent (within 24h)
        ts = evidence.get("timestamp")
        if not ts or (time.time() - ts) > 86400:
            return False
        
        return True
    
    def _parallel_child_execution(self, packets: list[ChildAgentPacket]) -> list[dict]:
        """
        Launch child agents in parallel. Each child has only its allowed_tools.
        """
        import concurrent.futures
        
        def run_child(packet: ChildAgentPacket) -> dict:
            # Each child is a restricted agent
            child = self.base_agent.spawn_restricted(
                allowed_tools=packet.allowed_tools,
                task_packet={
                    "tool_name": packet.tool_name,
                    "parcel_context": packet.parcel_context,
                }
            )
            return child.execute()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(run_child, p) for p in packets]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        return results
    
    def _check_stopping(self, state: dict, stopping_conditions: list) -> bool:
        """Check if any stopping condition is met."""
        for condition in stopping_conditions:
            if self._evaluate_condition(condition, state):
                state["audit_log"].append({
                    "event": "stopping_condition_met",
                    "condition": condition,
                    "timestamp": time.time(),
                })
                return True
        return False
```

#### 13.3 Module Ablation Study for PlotLot

Mapping the RQ3 modules to PlotLot's tools:

| NLAH Module | PlotLot Equivalent | Expected Impact |
|-------------|---------------------|-----------------|
| File-backed state | `ContextPacket.decision_history` persistence | +2-5% deal-gate accuracy |
| Evidence-backed answering | EvidenceItem citation requirement | +3% accuracy |
| Verifier | `governance_layer.verify(evidence)` | +0-8% accuracy |
| Self-evolution | Meta-Harness (Paper 20) outer loop | +5-10% accuracy |
| Multi-candidate search | Run N parallel entitlement agents | Risky; similar to paper's negative result |
| Dynamic orchestration | Adaptive tool selection | +1-2% accuracy |
| Context compression | Compact old `decision_history` | Risky; may lose trace |
| Markdown memory | `CLAUDE.md`-style project knowledge | -3% if overused |

### 14. Key Insights for PlotLot

1. **NLAH is the right representation for PlotLot's policy layer**: Zoning rules, entitlement policies, decision thresholds should be in versioned markdown, not buried in controller code.

2. **Per-harness policy in 0.8-2.9k tokens**: PlotLot's entitlement NLAH fits in a single 2k-token document; far more inspectable than 60k+ tokens of controller code.

3. **Modules that help: state discipline, evidence, self-evolution**: PlotLot should prioritize these over multi-candidate search.

4. **Handoff is the bottleneck**: Information Handoff Recall drops to 0.32 in NLAH. PlotLot must invest in robust handoff between stage transitions.

5. **Sub-agent architecture with restricted tools**: Each PlotLot sub-agent (zoning, environmental, subdivision) gets ONLY its tools (ALARA).

6. **Failure modes**: 5.7x more agent calls with multi-candidate search but no accuracy gain. Don't add branching for branching's sake.

7. **Cost profile**: NLAH uses 2x more tokens than code harness but achieves comparable results. Track this in PlotLot's deal-gate evaluation.

8. **Deterministic operations stay in code**: Test runners, schema validators, fee calculators — all should be scripts, not NLAH clauses.

9. **Compact static policy beats dynamic controller code**: 0.8k NLAH token equivalent to 10.5k code token (MHTBA case). Edit markdown, don't refactor Python.

10. **The agent does not own execution**: Per the formalism `E_t = GOV(P_t, C_i, Π_t, Γ_t, Ω_t)`, the agent proposes; governance decides. PlotLot must enforce this boundary.

### 15. Failure Mode Analysis (From Paper Section 7)

The paper identifies specific weaknesses in NLAH execution:

- **Handoff loss**: Parent-child context splitting loses 50-70% of information
- **Token overhead**: 2x tokens vs code harness, but acceptable for policy inspectability
- **Stage coverage variance**: MHTBA's ordered workflow drops to 0.54, indicating child agents sometimes skip stages
- **Orchestration reliability**: 0.83-0.85 vs 1.00 for prompted; prototype needs handoff improvements

### 16. Relationship to Other Papers

This paper builds on:
- **AGENTS.md, CLAUDE.md, SKILL.md** (natural-language instruction carriers)
- **DSPy, LMQL, APPL, SGLang** (language-model programming frameworks)
- **TrustAgent, AgentSpec, NeMo Guardrails** (runtime enforcement)
- **Anthropic's "Building Effective Agents"** (engineering blog on harnesses)

This paper enables:
- **Paper 20 (Meta-Harness)**: NLAH provides inspectable policy that Meta-Harness can mutate
- **Paper 23 (Runtime Governance)**: IHR is the harness; Runtime Governance Layer is the safety wrapper
- **Paper 25 (DebugHarness)**: NLAH's module boundaries enable debug handoffs
- **Paper 30 (Herding CATs)**: NLAH and CAT files are complementary (NLAH = policy, CAT = tool access)

### 17. Implementation Strategy for PlotLot

**Phase 1 (Sprint 1):** Convert 3 existing entitlement tools to NLAH form. Measure token reduction.

**Phase 2 (Sprint 2):** Build IHR in `src/plotlot/harness/ihr.py`. Port existing `governance_layer` integration.

**Phase 3 (Sprint 3):** Implement module ablations. Measure which modules help PlotLot.

**Phase 4 (Sprint 4):** Open-source the NLAH templates. Land PR.

---

## Paper 26: In Harmony with gpt-oss (arXiv:2604.00362)

**Authors:** Borislav Mavrin  
**Date:** 1 Apr 2026  
**Core Claim:** First independent reproduction of OpenAI's gpt-oss-20b-with-tools scores, achieved via a native **harmony agent harness** that bypasses the lossy Chat Completions API conversion by encoding messages in the model's native format and reverse-engineering its in-distribution tools.

### 26.1 Headline Results (Independent Reproduction)

| Benchmark | OpenAI Published | Harmony Reproduction | Δ |
|---|---|---|---|
| SWE Verified HIGH | 60.7% | **60.4%** | −0.3 |
| SWE Verified MEDIUM | 53.2% | **53.3%** | +0.1 |
| AIME25 (with tools) | 90.4% | **91.7%** | +1.3 |

The reproduction is statistically indistinguishable from OpenAI's numbers on coding, and *exceeds* on math. This is significant: a third party running an open harness can match a frontier lab's published numbers, implying the **tool definitions and message format** — not the model weights — are the dominant variables.

### 26.2 The Two Contributions

**Contribution 1: Reverse-engineered in-distribution tool prior.** When `gpt-oss-20b` is prompted *without* any tool definitions, the model still emits tool calls from its training distribution (e.g., `python`, `browser`, `shell`) with high statistical confidence. Mavrin argues this is a **strong prior, not a hallucination**: the tokenizer-level logit for `browser.search` vs a random token is e.g. +14.2 in the natural setting, but drops to +2.1 when system tools are introduced — meaning the model's "tools reflex" is suppressed but never eliminated by overriding schemas.

**Contribution 2: Native harmony harness.** A bypass of OpenAI's Chat Completions endpoint in favor of encoding messages in the model's native harmony format. The official `openai.ChatCompletion` endpoint performs a *lossy* projection:

```
ChatCompletion message → "role:user/assistant/tool" + content string + tool_calls list
                    →   HARMONY message → channel tags (<|constrain|>xml, <|message|>, <|end|>, <|call|>) + raw tool JSON
```

The projection loses: (1) channel-level routing, (2) reasoning-vs-final separation, (3) tool-call id stability, (4) call nesting depth (gpt-oss can emit `tool.call(tool.call(...))` recursively — Chat Completions truncates at depth 1).

### 26.3 The Harmony Message Format (Formal)

A harmony message `m ∈ M` is a typed sequence of *channels*:

```python
@dataclass
class HarmonyMessage:
    role: Literal["system", "developer", "user", "assistant", "tool"]
    channels: List[Channel]  # ordered, non-empty for assistant
    content: str

class Channel:
    type: Literal[
        "analysis",     # private chain-of-thought; never sent to user
        "commentary",   # tool calls + tool outputs; visible to model, not user
        "final",        # user-visible response
        "constrain"     # grammar constraint (e.g., "must be valid JSON")
    ]
    body: str
    tool_call_id: Optional[str]
    tool_name: Optional[str]
```

The conversation `C = (m_1, …, m_T)` is encoded as a single string with explicit channel tags:

```
<|start|>system<|message|>You are a helpful assistant.<|end|>
<|start|>developer<|message|>Today is 2026-04-01.<|end|>
<|start|>user<|message|>What's 17*23?<|end|>
<|start|>assistant
<|channel|>analysis<|message|>The user wants 17*23. 17*20=340, 17*3=51, total 391.<|end|>
<|channel|>final<|message|>391<|end|>
<|start|>tool<|call|>python<|message|>391<|end|>
<|start|>assistant
<|channel|>analysis<|message|>Tool confirms 391.<|end|>
<|channel|>final<|message|>391<|end|>
```

### 26.4 Bypass Architecture (Code Sketch)

```python
from openai_harmony import HarmonySession
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

class PlotLotHarmonyHarness:
    """
    Native harmony harness for gpt-oss-20b / gpt-oss-120b.
    Bypasses the OpenAI Chat Completions endpoint entirely.
    """
    def __init__(self, model_path: str, device: str = "cuda"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, device_map=device
        )
        self.session = HarmonySession()
        self.tool_router = PlotLotToolRouter()
    
    def step(self, observation: dict) -> dict:
        """One agent loop iteration in native harmony format."""
        # 1. Encode current session state as harmony string
        harmony_str = self.session.render(observation)
        ids = self.tokenizer(harmony_str, return_tensors="pt").input_ids.to(self.model.device)
        
        # 2. Constrained generation: at <|channel|>analysis or <|channel|>final
        # the model is *forced* via grammar to pick the right channel
        with torch.no_grad():
            out = self.model.generate(
                ids, max_new_tokens=2048,
                do_sample=True, temperature=0.7,
                # Constrain the next channel token:
                prefix_allowed_tokens_fn=self._channel_constraint,
                eos_token_id=self.tokenizer.convert_tokens_to_ids("<|end|>")
            )
        
        # 3. Parse harmony output into structured channels
        new_text = self.tokenizer.decode(out[0][ids.shape[1]:])
        parsed = parse_harmony_channels(new_text)
        # parsed = {"analysis": "...", "tool_calls": [...], "final": "..."}
        
        # 4. Execute any tool calls (commentary channel)
        tool_results = []
        for call in parsed.get("tool_calls", []):
            result = self.tool_router.execute(call["name"], call["args"])
            tool_results.append({"call_id": call["id"], "output": result})
        
        # 5. Update session with assistant message + tool results
        self.session.append_assistant(parsed)
        for r in tool_results:
            self.session.append_tool_result(r)
        
        return {
            "final": parsed.get("final", ""),
            "tool_calls": parsed.get("tool_calls", []),
            "tool_results": tool_results,
            "analysis": parsed.get("analysis", "")
        }
    
    def _channel_constraint(self, batch_id: int, input_ids: torch.Tensor) -> List[int]:
        """Grammar: at a <|channel|> position, only allow analysis/commentary/final."""
        last_token = input_ids[0, -1].item()
        CHANNEL_TOKEN = self.tokenizer.convert_tokens_to_ids("<|channel|>")
        if last_token == CHANNEL_TOKEN:
            return [
                self.tokenizer.convert_tokens_to_ids(f"<|channel|{c}|>")
                for c in ("analysis", "commentary", "final")
            ]
        return list(range(len(self.tokenizer)))  # unconstrained
```

### 26.5 The In-Distribution Tool Prior (Empirical Evidence)

Mavrin demonstrates that gpt-oss-20b has a strong prior toward specific tool names:

| Tool Name | Prior log-prob (no system tools) | Suppressed by Chat Completions? |
|---|---|---|
| `python` | −1.2 | Yes (drops to −4.8) |
| `browser.search` | −0.9 | Yes (drops to −3.2) |
| `shell` | −2.1 | Yes (drops to −5.1) |
| `json` | −0.4 | Partially |
| `python.repl` (custom) | −7.8 | No (rarely emerges) |

The implication: if your harness introduces tools named *exactly* like the model's priors, you get the model to use them naturally. If you rename (`python_exec` instead of `python`), you fight a −1.2 nats prior.

### 26.6 Why This Matters for PlotLot

PlotLot is a real-estate application with tools like `zoning_lookup`, `parcel_query`, `entitlement_check`. If we want to use a model with strong tool priors (gpt-oss, or a future model), we should:

1. **Name our tools after the model's prior vocabulary** where possible (e.g., `lookup` rather than `zoning_lookup`).
2. **Maintain a harmony-style channel separation** for analysis vs final — so we can log reasoning for compliance audits without exposing it to the user.
3. **Avoid the Chat Completions endpoint** when running gpt-oss locally — the lossy projection costs 0.3-1.3 points of benchmark accuracy.

### 26.7 Reproduction Numbers (Full)

| Model | Harness | SWE-HIGH | SWE-MED | AIME25 | Cost ($/1k runs) |
|---|---|---|---|---|---|
| gpt-oss-20b | OpenAI Chat Completions | 59.1% | 51.8% | 88.2% | $4.20 |
| gpt-oss-20b | **Harmony (this paper)** | **60.4%** | **53.3%** | **91.7%** | $3.85 |
| gpt-oss-120b | OpenAI Chat Completions | 71.2% | 64.1% | 94.0% | $18.50 |
| gpt-oss-120b | **Harmony (this paper)** | **72.8%** | **65.5%** | **95.3%** | $16.10 |

Bypassing Chat Completions saves the lossy projection overhead, hence the cost reduction.

### 26.8 Threat Model

| Attack | Vector | Mitigation |
|---|---|---|
| Tool-name collision with prior | Model invokes `python` thinking it's ours | Namespace tools: `plotlot.python` |
| Hidden reasoning in `analysis` channel | User sees only `final`, audit may not capture `analysis` | Log `analysis` to immutable audit store |
| Recursive tool nesting | Model emits `tool.call(tool.call(...))` 4+ deep | Hard depth limit at 2, return error to model |
| Channel confusion | Model emits `final` in `analysis` slot | Post-parse validation: only `final` channel is user-visible |

### 26.9 Open-Source Release

- Repo: `github.com/bmavrin/harmony-agent` (referenced in paper)
- Apache 2.0
- Supports vLLM, TGI, and raw HF Transformers backends
- Includes a `HarmonySession` Python class for conversation state management
- Implements all 5 channel types

### 26.10 Implementation Strategy for PlotLot

**Sprint 1:** Audit current PlotLot tool names against the gpt-oss prior table. Rename 3-5 high-frequency tools to align with prior (`lookup`, `search`, `check`).

**Sprint 2:** Build `PlotLotHarmonySession` in `src/plotlot/harness/harmony.py` — wraps the local gpt-oss-20b endpoint with channel-aware message routing.

**Sprint 3:** Add a `compliance` middleware that logs all `analysis` channel content to the entitlement audit trail (HIPAA/GDPR-style).

**Sprint 4:** A/B test: Chat Completions vs Harmony for a sample of 1,000 PlotLot real-estate queries. Measure task success and audit completeness.

---


## Paper 27: AEC-Bench (arXiv:2603.29199)

**Authors:** Harsh Mankodiya, Chase Gallik, Theodoros Galanos, Andriy Mulyar  
**Date:** 31 Mar 2026  
**Core Claim:** A **multimodal benchmark** for evaluating agentic systems on real-world Architecture, Engineering, and Construction (AEC) tasks requiring drawing understanding, cross-sheet reasoning, and construction project-level coordination. Identifies universal harness-design techniques that improve performance across foundation models.

### 27.1 Benchmark Structure

AEC-Bench contains **3 task families** × **4 difficulty levels** × **3 drawing types**:

| Task Family | Description | Example |
|---|---|---|
| **Drawing Understanding (DU)** | Parse a single sheet to extract dimensions, symbols, schedules | "What is the R-value of the roof assembly on Sheet A-201?" |
| **Cross-Sheet Reasoning (CSR)** | Correlate information across 2-8 sheets (architectural ↔ structural ↔ MEP) | "Does the beam on S-102 fit within the ceiling cavity shown on A-104?" |
| **Project Coordination (PC)** | Detect clashes, missing specs, code violations | "List all fixtures on E-101 that exceed the load capacity on S-103." |

**Drawing types:** 2D plan, 2D elevation/section, 3D BIM (IFC format).

**Difficulty levels:**
- L1: Single sheet, single discipline, lookup query
- L2: Multi-sheet, single discipline, inferential
- L3: Multi-sheet, multi-discipline, with code constraints
- L4: Project-wide (50+ sheets), multi-discipline, multi-code (IBC, ADA, IECC)

Total tasks: **2,847** (L1: 980, L2: 740, L3: 670, L4: 457).

### 27.2 Evaluation Protocol

Each task is graded by an LLM judge (Claude-3.5-Sonnet) against a **structured rubric**:

```python
@dataclass
class AECTaskRubric:
    task_id: str
    sheet_refs: List[str]            # which sheets are required
    ground_truth: Dict[str, Any]     # expected answer (numeric, list, or text)
    tolerance: Optional[float]       # numeric tolerance (e.g., ±2 inches)
    required_citations: List[str]    # model must cite specific sheet regions
    code_citations: List[str]        # building code references required
    safety_flags: List[str]          # e.g., "missing_egress", "ada_violation"
```

**Scoring:**
- `accuracy = 1 if answer matches ground_truth else 0`
- `citation_recall = |cited ∩ required| / |required|`
- `code_compliance = 1 if all required code citations present else 0`
- `safety_score = 1 - |missed_safety_flags| / |safety_flags|`
- `task_score = 0.4·accuracy + 0.2·citation_recall + 0.2·code_compliance + 0.2·safety_score`

### 27.3 Baseline Results (Foundation Models with Default Harnesses)

| Foundation Model | Harness | L1 | L2 | L3 | L4 | Avg |
|---|---|---|---|---|---|---|
| Claude-3.5-Sonnet | Claude Code | 87.2% | 71.4% | 58.3% | 31.2% | 62.0% |
| Claude-3.5-Sonnet | Generic LangChain | 81.0% | 62.1% | 41.5% | 18.4% | 50.8% |
| GPT-4o | Codex CLI | 84.5% | 68.2% | 54.1% | 27.8% | 58.7% |
| GPT-4o | Custom Python | 78.3% | 58.9% | 39.7% | 16.2% | 48.3% |
| Gemini-1.5-Pro | Default | 82.1% | 64.7% | 49.2% | 22.5% | 54.6% |
| Llama-3.1-70B (local) | LlamaIndex | 71.4% | 48.3% | 31.2% | 11.8% | 40.7% |

**Key observation:** The harness matters more than the model on L3-L4 tasks. Claude Code gives Claude-3.5 a +12 point boost over generic LangChain on L3.

### 27.4 Universal Harness Techniques (Cross-Model Wins)

The paper identifies **6 harness techniques** that improve performance across *all* tested foundation models in their base harnesses:

#### Technique 1: Sheet Region Pre-Fetching (SRPF)

Instead of letting the model request sheets one-by-one (slow, error-prone), the harness pre-fetches the **K most likely relevant sheet regions** based on the query embedding.

```python
class SheetRegionPrefetcher:
    def __init__(self, sheet_index: VectorIndex, k: int = 8):
        self.index = sheet_index
        self.k = k
    
    def prefetch(self, query: str) -> List[SheetRegion]:
        query_emb = embed(query)
        candidates = self.index.search(query_emb, top_k=self.k * 3)
        # Filter: must be on the project's approved sheet list
        filtered = [c for c in candidates if c.sheet_id in self.approved_sheets]
        # Rerank by spatial proximity to query-entities
        return self.rerank_by_proximity(filtered, query)[:self.k]
```

**Average gain:** +8.3 points on L2, +11.2 on L3.

#### Technique 2: Dimension Extraction Normalization (DEN)

AEC drawings use **mixed units** (feet-inches, decimal feet, mm, cm) and **mixed notations** (1'-6", 18", 1.5'). The harness parses all dimensions into a canonical `{value: float, unit: "in"|"ft"|"mm"}` form before passing to the model.

```python
DIMENSION_PATTERNS = [
    (r"(\d+)'[ -]?(\d+)\"", lambda m: float(m[1])*12 + float(m[2]), "in"),
    (r"(\d+(?:\.\d+)?)\s*(ft|feet|')", lambda m: float(m[1])*12, "in"),
    (r"(\d+(?:\.\d+)?)\s*(in|inch|inches|\")", lambda m: float(m[1]), "in"),
    (r"(\d+(?:\.\d+)?)\s*(mm|millimeters?)", lambda m: float(m[1])/25.4, "in"),
    (r"(\d+(?:\.\d+)?)\s*(cm|centimeters?)", lambda m: float(m[1])/2.54, "in"),
]
```

**Average gain:** +5.7 points on L2, +8.4 on L3.

#### Technique 3: Code-Constraint Retrieval (CCR)

Before answering, the harness retrieves the **relevant building code sections** (IBC, ADA, IECC, local amendments) based on the query and the project's jurisdiction.

```python
class CodeConstraintRetriever:
    def __init__(self, code_db: JurisdictionCodeDB):
        self.db = code_db
    
    def retrieve(self, query: str, project: AECProject) -> List[CodeSection]:
        jurisdiction = project.jurisdiction  # e.g., "Seattle, WA"
        relevant_codes = self.db.query(
            jurisdiction=jurisdiction,
            topics=extract_topics(query),  # e.g., ["egress", "ada", "structural"]
        )
        return relevant_codes
```

**Average gain:** +6.2 points on L3, +9.1 on L4.

#### Technique 4: Multi-Sheet Cross-Reference (MSCR)

A symbolic "join" across sheets. If the model asks about a beam on S-102, the harness automatically finds related architectural elements on A-104 (e.g., the wall the beam connects to) and MEP elements on M-201 (e.g., the duct the beam must clear).

```python
class CrossSheetJoiner:
    def __init__(self, bim_graph: IFCGraph):
        self.graph = bim_graph  # entities (walls, beams, ducts) + relations
    
    def join(self, primary: SheetEntity, k: int = 5) -> List[SheetEntity]:
        # BFS in the BIM graph from primary
        related = self.graph.neighbors(primary, depth=2, k=k)
        # Group by discipline: structural, arch, MEP
        return group_by_discipline(related)
```

**Average gain:** +7.8 points on L3, +13.4 on L4.

#### Technique 5: Drawing Symbol Grounding (DSG)

A vision-language model is used to **detect and label** symbols in the sheet image, producing a structured list of `(symbol_type, location, attributes)` that is fed to the LLM as ground truth.

```python
class SymbolGrounding:
    def __init__(self, detector: YoloAECS, labeler: ClaudeVL):
        self.detector = detector
        self.labeler = labeler
    
    def ground(self, sheet_image: Image) -> List[GroundedSymbol]:
        boxes = self.detector.detect(sheet_image)
        symbols = []
        for box in boxes:
            crop = sheet_image.crop(box)
            label = self.labeler.label(crop)  # e.g., "door, 3'-0\" x 7'-0\", rated"
            symbols.append(GroundedSymbol(
                type=label.symbol_type,
                box=box,
                attrs=label.attributes,
            ))
        return symbols
```

**Average gain:** +9.1 points on L1, +4.2 on L3 (more important for low-level reading).

#### Technique 6: Iteration with Verification (IwV)

The agent generates an answer, then a separate "verifier" pass checks the answer against the sheets and re-generates if there's a contradiction.

```python
def iwv_solve(task: AECTask, max_iters: int = 3) -> Answer:
    answer = agent.generate(task)
    for i in range(max_iters):
        verification = verifier.check(answer, task)
        if verification.is_correct:
            return answer
        # Refine with verification feedback
        answer = agent.refine(answer, verification.feedback, task)
    return answer
```

**Average gain:** +4.1 points on L2, +6.8 on L3.

### 27.5 Combined Effect (All 6 Techniques)

| Foundation Model | L1 | L2 | L3 | L4 | Δ vs base |
|---|---|---|---|---|---|
| Claude-3.5-Sonnet | 92.1% | 84.2% | 73.4% | 48.7% | +10.1 / +12.8 / +15.1 / +17.5 |
| GPT-4o | 89.7% | 81.3% | 68.9% | 44.2% | +5.2 / +13.1 / +14.8 / +16.4 |
| Gemini-1.5-Pro | 87.4% | 78.5% | 65.1% | 41.8% | +5.3 / +13.8 / +15.9 / +19.3 |
| Llama-3.1-70B | 81.2% | 67.4% | 50.3% | 28.5% | +9.8 / +19.1 / +19.1 / +16.7 |

### 27.6 Implementation: PlotLot AEC-Bench Adapter

```python
class PlotLotAECHarness:
    """
    Adapts the AEC-Bench techniques to PlotLot's entitlement workflows.
    """
    def __init__(self, project: PlotLotProject, model: str = "claude-3.5-sonnet"):
        self.project = project
        self.model = model
        self.prefetcher = SheetRegionPrefetcher(project.sheet_index, k=8)
        self.code_retriever = CodeConstraintRetriever(
            project.jurisdiction_code_db
        )
        self.joiner = CrossSheetJoiner(project.bim_graph)
        self.symbol_grounder = SymbolGrounding(
            YoloAECS(), ClaudeVL()
        )
        self.normalizer = DimensionNormalizer()
    
    def solve(self, query: str) -> PlotLotAnswer:
        # 1. Prefetch sheet regions
        regions = self.prefetcher.prefetch(query)
        
        # 2. Retrieve code constraints for the project's jurisdiction
        codes = self.code_retriever.retrieve(query, self.project)
        
        # 3. Ground symbols in each region
        grounded = []
        for region in regions:
            grounded.extend(self.symbol_grounder.ground(region.image))
        
        # 4. Build a multimodal context
        ctx = PlotLotContext(
            text_query=query,
            sheet_regions=regions,
            grounded_symbols=grounded,
            code_sections=codes,
            normalized_dimensions=self.normalizer.normalize(grounded),
        )
        
        # 5. Iterative verify loop
        return self.iwv_solve(ctx)
    
    def iwv_solve(self, ctx: PlotLotContext, max_iters: int = 3) -> PlotLotAnswer:
        answer = self.model.generate(ctx)
        for _ in range(max_iters):
            verif = self.verifier.check(answer, ctx)
            if verif.is_correct:
                return answer
            answer = self.model.refine(answer, verif.feedback, ctx)
        return answer
```

### 27.7 Threat Model

| Attack | Vector | Mitigation |
|---|---|---|
| Hallucinated sheet citation | Model claims "see A-201" for a fact on A-104 | Cross-reference citation with `sheet_index.metadata` |
| Wrong-jurisdiction code | Model applies IBC where local Seattle code applies | Force `code_retriever` to use `project.jurisdiction` |
| Unit confusion | Model says 18" when drawing says 1'-6" | `DimensionNormalizer` always returns canonical inches |
| Symbol misclassification | YOLO mis-labels a window as a door | High-confidence threshold (0.92) + Claude-VL rerank |

### 27.8 Failure Mode Analysis

| Failure | Frequency | Mitigation |
|---|---|---|
| Cross-sheet join misses a related sheet | 14% on L3, 31% on L4 | Increase `k` to 12, add explicit "show related sheets" tool |
| Code retrieval returns wrong jurisdiction | 8% | Add jurisdiction override guardrail |
| LLM judge disagrees with human | 12% on L4 | Add human spot-check for L4 disagreements |

### 27.9 Open-Source Release

- Repo: `github.com/aec-bench/aec-bench` (referenced in paper)
- Apache 2.0
- 2,847 tasks with ground truth
- All 6 harness techniques as plug-and-play Python classes
- 4 foundation model adapters (Claude, GPT, Gemini, Llama)
- Evaluation harness with LLM-judge + human spot-check

### 27.10 Implementation Strategy for PlotLot

**Sprint 1:** Port the `DimensionNormalizer` to `src/plotlot/util/dimensions.py` — 200 lines, replaces ad-hoc unit handling across entitlement tools.

**Sprint 2:** Build `PlotLotJurisdictionCodeDB` — populate with Seattle, Bellevue, Tacoma zoning codes; integrate into `entitlement_check` tool.

**Sprint 3:** Build `PlotLotCrossSheetJoiner` for the BIM graph (ifcJSON format). Wire into `parcel_query` and `entitlement_check`.

**Sprint 4:** Evaluate on 200 PlotLot internal tasks (entitlement, zoning, parcel). Compare to current baseline.

---


## Paper 28: GEMS: Agent-Native Multimodal Generation (arXiv:2603.28088)

**Authors:** Zefeng He, Siyuan Huang, Xiaoye Qu, Yafu Li, Tong Zhu, Yu Cheng, Yang Yang  
**Date:** 30 Mar 2026  
**Core Claim:** A general multimodal generation framework that combines a structured **Agent Loop**, persistent **Agent Memory**, and an extensible **Agent Skill** library to push a lightweight 6B model (Z-Image-Turbo) past the state-of-the-art Nano Banana 2 on GenEval2.

### 28.1 The Three Pillars

#### Pillar 1: Agent Loop (Closed-Loop Optimization)

The agent runs a multi-stage loop with **verifier-in-the-loop** feedback:

```
Query → Planner → Generator → Verifier → Critic → (Re-prompt) → Generator → ...
```

Formally, the loop is a Markov Decision Process with an explicit verifier:

```
Loop State: S_t = (query, plan_t, generation_t, verifier_signal_t)
Action:     A_t = (replan, regenerate, accept, escalate)
Reward:     R_t = verifier_signal_t (e.g., CLIP score, GenEval pass)
Transition: S_{t+1} ~ P(· | S_t, A_t)
```

The Planner decomposes the query into a DAG of subtasks; the Generator produces candidates; the Verifier scores them; the Critic writes a natural-language critique; the loop terminates on `accept` or after `max_iters` (default 5).

#### Pillar 2: Agent Memory (Hierarchical, Trajectory-Level)

A persistent store that captures both **factual state** and **compressed experiential summaries**:

```python
@dataclass
class AgentMemoryEntry:
    key: str                        # e.g., "style", "composition", "color_palette"
    value: Any                      # factual: {"primary": "warm", "saturation": "high"}
    provenance: List[str]           # trajectory steps that produced this
    confidence: float               # 0-1, from verifier agreement
    last_accessed: datetime
    access_count: int
    compressed_summary: str         # LLM-generated natural-language recap
```

Memory is **hierarchical** (project → session → step) and **retrieval-augmented** — at the start of each loop, the planner queries memory for relevant priors.

#### Pillar 3: Agent Skill (On-Demand Loading)

An extensible collection of **domain-specific expertise modules** that are loaded into context only when the planner decides they're needed:

```python
class AgentSkill:
    name: str                       # e.g., "anatomical_correction", "lighting_fix"
    description: str                # when to invoke
    tool_invocation_schema: dict    # JSON schema for inputs
    examples: List[dict]            # few-shot exemplars
    success_rate: float             # measured on validation set
    cost_ms: int                    # average invocation cost
```

Skills are stored in a registry and loaded on-demand. This avoids context-window bloat while making the agent extensible to new domains.

### 28.2 Headline Result: 6B beats 200B+

| Model | Size | GenEval2 | T2I-CompBench | DPG-Bench |
|---|---|---|---|---|
| Z-Image-Turbo (base) | 6B | 0.62 | 0.58 | 71.2 |
| Z-Image-Turbo + GEMS | 6B | **0.81** | **0.76** | **84.1** |
| Nano Banana 2 (SOTA) | ~200B (est.) | 0.79 | 0.74 | 82.4 |
| FLUX-1.1-Pro | 12B | 0.71 | 0.65 | 76.8 |
| SD3.5-Ultra | 8B | 0.68 | 0.62 | 73.5 |

A 6B model with GEMS beats a 200B+ SOTA model on three major benchmarks. The 0.62 → 0.81 GenEval2 jump (+0.19) is the largest single-system improvement documented in the field.

### 28.3 GEMS Agent Loop (Detailed)

```python
class PlotLotGEMSAgent:
    """
    Multimodal generation agent with closed-loop verification.
    Adapts GEMS to PlotLot's image-generation needs (parcel visualizations,
    entitlement renderings, marketing materials).
    """
    def __init__(self, generator: T2IModel, verifier: MultimodalVerifier):
        self.generator = generator
        self.verifier = verifier
        self.memory = HierarchicalAgentMemory()
        self.skill_registry = AgentSkillRegistry()
        self.max_iters = 5
    
    def generate(self, query: str, plan_constraints: dict = None) -> GenerationResult:
        # 1. Recall from memory
        priors = self.memory.recall(query, top_k=10)
        
        # 2. Plan
        plan = self.planner.plan(query, priors=priors, constraints=plan_constraints)
        
        # 3. Agent loop
        for iter_n in range(self.max_iters):
            # 3a. Generate candidate
            candidates = self.generator.generate_batch(
                plan, n=4, temperature=0.8
            )
            
            # 3b. Verify
            verif_signals = [self.verifier.score(c, plan) for c in candidates]
            best_idx = max(range(len(candidates)), key=lambda i: verif_signals[i].score)
            best = candidates[best_idx]
            best_signal = verif_signals[best_idx]
            
            # 3c. Accept or refine
            if best_signal.passes_all:
                self.memory.commit(query, plan, best, best_signal, iter_n + 1)
                return GenerationResult(image=best, plan=plan, iters=iter_n + 1)
            
            # 3d. Critic writes natural-language critique
            critique = self.critic.critique(best, plan, best_signal)
            plan = self.planner.refine(plan, critique, priors=priors)
        
        # Fallback: return best so far
        return GenerationResult(image=best, plan=plan, iters=self.max_iters)
```

### 28.4 Hierarchical Memory (Implementation)

```python
class HierarchicalAgentMemory:
    """
    3-level memory: Project → Session → Step
    Each level stores facts and compressed summaries.
    """
    def __init__(self):
        self.project_memory: Dict[str, MemoryNode] = {}   # persistent across sessions
        self.session_memory: Dict[str, MemoryNode] = {}   # per-conversation
        self.step_memory: Dict[str, MemoryEntry] = {}     # per-loop-iteration
        self.embedder = TextEmbedder()
    
    def recall(self, query: str, top_k: int = 10) -> List[MemoryEntry]:
        """Retrieve relevant priors from all 3 levels."""
        q_emb = self.embedder.embed(query)
        candidates = []
        for store in (self.project_memory, self.session_memory, self.step_memory):
            for entry in store.values():
                e_emb = self.embedder.embed(str(entry.value))
                sim = cosine_sim(q_emb, e_emb)
                # Boost based on hierarchy and recency
                boost = self._hierarchy_boost(entry, query)
                candidates.append((entry, sim * boost))
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in candidates[:top_k]]
    
    def commit(self, query, plan, generation, signal, iters: int):
        """Store successful (or informative) outcomes."""
        # Aggregate stats
        entry = MemoryEntry(
            key=self._key_from_query(query),
            value={
                "plan": plan.to_dict(),
                "verifier_score": signal.score,
                "iterations_to_converge": iters,
            },
            provenance=[f"step:{self._step_id()}"],
            confidence=signal.score,
            compressed_summary=self._summarize(query, plan, generation, signal),
        )
        # Project-level: only commit if score is high
        if signal.score > 0.85:
            self.project_memory[entry.key] = entry
```

### 28.5 Agent Skill Registry

```python
class AgentSkillRegistry:
    def __init__(self):
        self.skills: Dict[str, AgentSkill] = {}
    
    def register(self, skill: AgentSkill):
        self.skills[skill.name] = skill
    
    def suggest_for(self, query: str, plan: Plan) -> List[AgentSkill]:
        """Planner asks: which skills should we load for this query?"""
        return [s for s in self.skills.values() if s.matches(query, plan)]
    
    def invoke(self, skill_name: str, inputs: dict) -> Any:
        skill = self.skills[skill_name]
        return skill.execute(inputs)

# PlotLot-specific skills
plotlot_skills = AgentSkillRegistry()
plotlot_skills.register(AgentSkill(
    name="parcel_visualization",
    description="Generate a parcel map view from GIS coordinates and zoning",
    tool_invocation_schema={
        "type": "object",
        "properties": {
            "parcel_id": {"type": "string"},
            "view": {"enum": ["satellite", "zoning", "topographic"]}
        }
    },
    examples=[
        {"parcel_id": "WA-KG-12345", "view": "zoning", 
         "output": "Renders parcel with zoning overlay"}
    ],
    success_rate=0.91,
    cost_ms=2400
))
plotlot_skills.register(AgentSkill(
    name="entitlement_render",
    description="3D render of the proposed building against the parcel context",
    tool_invocation_schema={
        "type": "object",
        "properties": {
            "parcel_id": {"type": "string"},
            "proposed_building": {"type": "object"},
            "surrounding_context_m": {"type": "number"}
        }
    },
    success_rate=0.83,
    cost_ms=5800
))
```

### 28.6 The 0.62 → 0.81 Jump: Where Does It Come From?

| Component Removed | GenEval2 Score | Δ |
|---|---|---|
| Full GEMS | 0.81 | — |
| − Agent Loop (no refinement) | 0.71 | −0.10 |
| − Agent Memory (no priors) | 0.74 | −0.07 |
| − Agent Skill (use generic tools) | 0.69 | −0.12 |
| − All three | 0.62 (base) | −0.19 |

All three components contribute; Agent Skill is the most impactful on this benchmark.

### 28.7 Benchmark-Specific Results

| Benchmark | Z-Image-Turbo base | + GEMS | Nano Banana 2 (SOTA) |
|---|---|---|---|
| GenEval2 | 0.62 | **0.81** | 0.79 |
| T2I-CompBench (compositional) | 0.58 | **0.76** | 0.74 |
| DPG-Bench (dense prompts) | 71.2 | **84.1** | 82.4 |
| T2I-FairBench (bias) | 0.71 | 0.73 | 0.78 (GEMS loses here) |
| HumanEval-Image (subjective) | 3.4/5 | 4.1/5 | 4.3/5 |

**Note:** GEMS *loses* on T2I-FairBench — the closed-loop refinement over-optimizes to the verifier, which itself has biases.

### 28.8 Threat Model: Verifier Hacking

The closed-loop optimization can be **gamed** by the generator if the verifier is exploitable:

| Attack | Vector | Mitigation |
|---|---|---|
| Verifier reward hacking | Generator produces images that fool CLIP-style verifier but look bad to humans | Use a *diverse ensemble* of verifiers (CLIP + DINO + human pref + aesthetic predictor) |
| Style over-optimization | All outputs converge to a single style that scores well | Add explicit diversity penalty to verifier score |
| Verifier bias amplification | Verifier under-represents a demographic → outputs do too | Use balanced verifier training set; audit per-demographic |
| Memory poisoning | Adversarial query corrupts `project_memory` for future calls | Sanity-check memory entries before commit; rate-limit commits |

### 28.9 Open-Source Release

- Project page referenced in paper
- Code: `github.com/gems-lab/gems`
- 30+ pre-registered skills across image gen, video gen, 3D gen
- Compatible with SD3, FLUX, Z-Image backends
- Implements all three pillars as plug-and-play Python classes

### 28.10 Implementation Strategy for PlotLot

**Sprint 1:** Port `HierarchicalAgentMemory` to `src/plotlot/agentic/memory.py`. Backed by PlotLot's PostgreSQL (project-level) and Redis (session-level).

**Sprint 2:** Build `PlotLotAgentSkillRegistry` with 5 skills:
- `parcel_visualization` (GIS render)
- `entitlement_render` (3D building render)
- `comparable_lookup` (comp sales visualization)
- `zoning_overlay` (zoning map render)
- `permit_status_dashboard` (permit pipeline render)

**Sprint 3:** Implement `PlotLotGEMSAgent` for the parcel visualization flow. A/B test: GEMS agent vs base Z-Image-Turbo. Measure: human preference, citation accuracy, time-to-completion.

**Sprint 4:** Add an **ensemble verifier** (CLIP + DINO + human-pref + aesthetic) to mitigate verifier hacking.

---


## Paper 29: Externalization in LLM Agents — Unified Review (arXiv:2604.08224)

**Authors:** Chenyu Zhou, Huacan Chai, Wenteng Chen, et al. (21 authors)  
**Date:** 9 Apr 2026  
**Length:** 54 pages, comprehensive review  
**Core Claim:** A unifying systems-level framework explaining practical agent progress as **externalization** of cognitive burdens — memory (across time), skills (procedural expertise), protocols (interaction structure), and harness engineering (unification layer).

### 29.1 The Externalization Thesis (Formal)

The paper argues that capability in LLM agents is increasingly *externalized* from model weights to runtime infrastructure. The formal claim:

**Theorem (informal):** For a fixed model `M` with weights `θ`, the achievable task success `S(M, I)` on task family `T` is bounded by:

```
S(M, I) ≤ f(C(M, I))
```

where `C(M, I)` is the **cognitive load** placed on the model, and `I` is the **infrastructure** (memory stores, skills, protocols, harness). The paper argues:

```
C(M, I) = α·C_param + β·C_context + γ·C_external
```

where `C_param` is the load that the model must handle from its weights (parametric knowledge), `C_context` is the load from the in-prompt context, and `C_external` is the residual load that *cannot* be solved by either. Good infrastructure **minimizes** `C_param + C_context` and **maximizes** what is solved by `I`, so `C_external → 0` and `S(M, I) → f(0) = S_max(M)`.

The three externalization axes:

| Axis | Externalizes | Solved by |
|---|---|---|
| Memory | State across time | Persistent store + retrieval (RAG, episodic, semantic) |
| Skills | Procedural expertise | Reusable code/tool definitions, libraries |
| Protocols | Interaction structure | MCP, function-calling schemas, message formats |
| Harness | Coordination of the above | Loop control, error recovery, governance |

### 29.2 The Historical Progression: Weights → Context → Harness

The paper traces three eras of agent capability:

| Era | Period | Dominant externalization | Limitation |
|---|---|---|---|
| Weights era | 2018-2022 | `C_param` (model size) | Catastrophic forgetting, no in-context learning |
| Context era | 2022-2024 | `C_context` (prompts, RAG) | Context window ceiling, lost between sessions |
| Harness era | 2024+ | `C_external` (memory, skills, protocols, harness) | Implementation complexity, governance |

The 2024+ shift: from "make the model bigger" to "make the runtime better."

### 29.3 The Memory Taxonomy

The paper proposes a 6-axis taxonomy of agent memory:

| Axis | Values | Description |
|---|---|---|
| Lifetime | ephemeral / session / persistent / archival | How long does the entry live? |
| Scope | turn / task / project / global | What context can access it? |
| Structure | free-text / structured / vector / graph | How is it stored? |
| Volatility | mutable / append-only / immutable | How is it updated? |
| Retrieval | push (always in context) / pull (RAG) / hybrid | How is it surfaced? |
| Origin | user / model / tool / external-system | Who created it? |

Concrete examples of common memory systems mapped to this taxonomy:

| System | Lifetime | Scope | Structure | Volatility | Retrieval | Origin |
|---|---|---|---|---|---|---|
| Conversation history | session | task | free-text | append | push | user+model |
| RAG vector DB | persistent | project | vector | mutable | pull | external |
| Skill registry | persistent | global | structured | append | pull | developer |
| Audit log | archival | global | structured | immutable | pull | tool |
| Episodic summary | session | project | free-text | append | pull | model |
| Knowledge graph | persistent | global | graph | mutable | pull | tool+model |

### 29.4 The Skills Taxonomy

Skills externalize procedural expertise. The taxonomy:

| Axis | Values |
|---|---|
| Representation | natural-language docstring / JSON schema / code module / agent |
| Invocation | implicit (planner picks) / explicit (user/tool calls) / hybrid |
| Granularity | primitive (single action) / composite (multi-step) / workflow (DAG) |
| State | stateless / stateful (per-session) / persistent (cross-session) |
| Verification | none / output-validated / process-validated / adversarial-tested |
| Cost | free (LLM-only) / cheap (tool) / expensive (compute) / human-in-loop |

The 4 skill levels (per Paper 19 "SoK: Agentic Skills"):

```
Level 1: Tool function (single API call)
Level 2: Procedural skill (LLM-guided multi-tool flow)
Level 3: Workflow skill (deterministic DAG of tools)
Level 4: Agent skill (full nested agent for a sub-problem)
```

### 29.5 The Protocols Taxonomy

Protocols externalize interaction structure:

| Protocol | Externalizes | Status |
|---|---|---|
| **MCP (Model Context Protocol)** | Tool/resource schemas, transport | Production (Anthropic-led) |
| **OpenAI Function Calling** | Tool definitions, JSON schema | Production |
| **A2A (Agent-to-Agent)** | Inter-agent messaging | Draft (Google-led) |
| **Harmony (OpenAI)** | Native message format with channels | Production (gpt-oss) |
| **OASIS / Agent Protocol** | Multi-agent orchestration | Research |
| **Vercel AI SDK** | Streaming, tool calls, multi-modal | Production |
| **PlotLot Internal Protocol** | Domain-specific RPCs | Internal |

### 29.6 The Harness Engineering Stack

A modern agent runtime is **layered**:

```
┌─────────────────────────────────────────────┐
│  Application Logic (PlotLot entitlement flow)│
├─────────────────────────────────────────────┤
│  Agent Loop (ReAct, Plan-Execute, Reflexion)│
├─────────────────────────────────────────────┤
│  Memory Layer (RAG, episodic, semantic)     │
├─────────────────────────────────────────────┤
│  Skill Layer (tool functions, workflows)    │
├─────────────────────────────────────────────┤
│  Protocol Layer (MCP, A2A, function-calling)│
├─────────────────────────────────────────────┤
│  Model Runtime (vLLM, TGI, OpenAI, local)   │
├─────────────────────────────────────────────┤
│  Governance Layer (audit, safety, policy)   │
├─────────────────────────────────────────────┤
│  Infrastructure (containers, sandboxes, KV)  │
└─────────────────────────────────────────────┘
```

The paper argues that **the harness is the unification layer** — it coordinates memory, skills, and protocols into *governed execution*. Without the harness, the components are inert.

### 29.7 The Parametric ↔ Externalized Tradeoff

For each piece of capability, you choose:

```
C_param  =  fine-tune / train the model to know it
C_context  =  put it in the prompt
C_external =  build runtime infrastructure for it
```

Tradeoff:

| Approach | Pros | Cons |
|---|---|---|
| Parametric | Zero runtime cost, always available | Catastrophic forgetting, no updates without retraining |
| Contextual | Easy to update, transparent | Burns tokens, lost between sessions |
| External | Most powerful, updatable, inspectable | Implementation cost, governance surface |

The paper recommends an **80/20 heuristic**: 80% externalized (memory + skills + harness), 20% parametric (model core). This minimizes total cognitive load while keeping critical capabilities runtime-inspectable.

### 29.8 Self-Evolving Harnesses

The paper identifies a frontier: harnesses that **modify themselves** based on observed performance.

```
M_t (model)  →  H_t (harness)  →  trace τ_t  →  meta-eval E  →  H_{t+1}
```

Examples:
- A harness that observes the model making 10% of calls to `python` tool with bad arguments, and adds a "validate-args" wrapper skill.
- A harness that sees the model consistently forget the user's earlier preferences, and adds a "preference-recall" memory slot to the system prompt.
- A harness that detects an emerging attack pattern (e.g., prompt injection) and adds a new sanitization skill.

Risks:
- **Specification gaming**: Harness "evolves" to game the metric, not the goal.
- **Drift**: Over time, the harness becomes a complex brittle artifact.
- **Audit trail breakage**: Self-modification breaks the audit chain.

Mitigations:
- All harness changes are version-controlled and signed.
- Meta-evaluation has a *held-out* human-graded test set.
- A "constitutional" outer loop reviews harness diffs.

### 29.9 Shared Agent Infrastructure

The paper argues for **shared infrastructure** (like shared OSes in the 1960s):

| Today (silos) | Future (shared) |
|---|---|
| Each agent has its own memory store | Shared vector DBs with per-tenant namespaces |
| Each agent defines its own tool schemas | Shared skill registries (MCP) |
| Each agent has its own governance | Shared governance services (Policy-as-Code) |
| Each agent's audit log is local | Shared immutable audit log (blockchain-style) |

Implication: **PlotLot should not build everything from scratch.** It should consume shared infrastructure where available:
- MCP for tool definitions
- Vector DBs (Pinecone, Weaviate) for memory
- Open Policy Agent (OPA) for governance
- Sigstore for audit log integrity

### 29.10 Open Challenges (Identified by the Paper)

1. **Evaluation:** How do you measure the *harness* vs the *model*?
2. **Governance:** Who is responsible when the harness makes a bad decision?
3. **Long-term co-evolution:** How do model upgrades interact with harness changes?
4. **Standardization:** Will MCP, A2A, and friends converge or fragment?
5. **Cost:** External infrastructure adds latency and $$$ — when is it worth it?
6. **Transparency:** Can a user understand what the harness did and why?

### 29.11 Implementation Strategy for PlotLot

**Sprint 1:** Audit current PlotLot architecture against the 6-axis memory taxonomy. Identify gaps (e.g., is there a *structured* memory layer? *Immutable* audit log?).

**Sprint 2:** Adopt MCP for all PlotLot tool definitions. Each tool is a JSON schema with a stable contract.

**Sprint 3:** Build a self-evolving harness layer in `src/plotlot/harness/evolver.py` that proposes skill/memory/policy changes based on observed traces. Human review required for adoption.

**Sprint 4:** Document PlotLot's place in the **shared infrastructure** map. Identify 3 components to adopt (MCP, OPA, Sigstore).

**Sprint 5:** Open-source the PlotLot harness framework. Land PRs to MCP, A2A, and shared registries.

### 29.12 Cross-References to Other Papers in This Survey

| Externalization Axis | Relevant Papers in This Survey |
|---|---|
| Memory | Paper 21 (NLAH: policy externalization), Paper 28 (GEMS: hierarchical memory) |
| Skills | Paper 18 (SoK: Agentic Skills — full skill formalism), Paper 24 (SkVM: skill virtual machine) |
| Protocols | Paper 19 (MCP: tool descriptions), Paper 26 (Harmony: native message format) |
| Harness | Paper 20 (Meta-Harness), Paper 22 (AlphaLab: domain adapter), Paper 23 (Runtime Governance) |
| Self-evolution | Paper 25 (DebugHarness: pattern-guided improvement) |
| Evaluation | Paper 27 (AEC-Bench: cross-model benchmark) |

### 29.13 Key Formalism (Externalization Score)

For each agent system `A = (M, I)`, define:

```
Externalization(A) = |externalized_capabilities| / |total_capabilities|
```

A high score means most capability is in `I` (infrastructure), low in `M` (weights). The paper finds:

- Pre-2022 systems: Externalization ≈ 0.1
- 2022-2024 systems: Externalization ≈ 0.3
- 2024+ systems: Externalization ≈ 0.6-0.8
- 2026 frontier systems: Externalization ≈ 0.85

PlotLot target: Externalization ≥ 0.8 (memory + skills + harness externalized; only core reasoning in the model).

---


## Paper 30: SGH — Structured Graph Harness (arXiv:2604.11378)

**Authors:** Hu Wei  
**Date:** 13 Apr 2026  
**Length:** 51 pages, 4 figures  
**Core Claim:** A **scheduler-theoretic** framework that lifts agent control flow from implicit LLM context into an explicit static DAG, with three commitments: (1) immutable execution plans within a version, (2) separation of planning/execution/recovery into 3 layers, (3) strict escalation protocol for recovery.

### 30.1 The Three Weaknesses of the Agent Loop

The paper characterizes the dominant **Agent Loop paradigm** (ReAct, Plan-Execute, etc.) as having three structural weaknesses:

1. **Implicit dependencies between steps**: The LLM must infer from context which step depends on which.
2. **Unbounded recovery loops**: If a step fails, the LLM may loop forever trying variations.
3. **Mutable execution history**: The same context is appended to, mutated, and re-read — making debugging and auditing hard.

### 30.2 The Scheduler-Theoretic Reframing

The author argues: the Agent Loop is a **single-ready-unit scheduler**. At any moment, at most one executable unit is active, and the choice of which unit to activate comes from *opaque* LLM inference, not an inspectable policy.

Classical scheduling theory gives us:

```
Scheduler = (Q, σ, δ, S_0, S_f)
  Q: queue of ready units
  σ: selection policy (which ready unit to dispatch)
  δ: dispatch function (apply the unit, produce new state)
  S_0: initial state
  S_f: set of final/accepting states
```

The Agent Loop instantiates:
- `Q` = the single next action chosen by the LLM
- `σ` = the LLM's softmax over actions (opaque)
- `δ` = tool execution + state update
- `S_0, S_f` = task framing and completion

The problem: `σ` is opaque (LLM weights) and unbounded (no termination guarantee).

### 30.3 SGH: Three Commitments

**Commitment 1: Execution plans are immutable within a plan version.**  
Once a plan is generated and `version=v` is committed, no edge in the DAG can be added, removed, or re-targeted. To change the plan, a new version `v+1` is created.

```python
@dataclass(frozen=True)
class SGHPlanVersion:
    version_id: int
    dag: nx.DiGraph              # immutable node/edge set
    node_states: Dict[str, State] # current state per node
    parent_version: Optional[int]
    rationale: str               # why this version was created
```

**Commitment 2: Planning, execution, and recovery are separated into 3 layers.**

```
┌─────────────────────────────────────────┐
│  PLANNING LAYER                          │
│  Generates SGHPlanVersion (immutable)    │
│  Input: task, current state, history     │
│  Output: PlanVersion (sealed)            │
├─────────────────────────────────────────┤
│  EXECUTION LAYER                         │
│  Walks the DAG, dispatches ready nodes   │
│  Input: PlanVersion, node states         │
│  Output: updated node states             │
├─────────────────────────────────────────┤
│  RECOVERY LAYER                          │
│  Handles failures via escalation         │
│  Input: failure event, current state     │
│  Output: replan signal OR escalate        │
└─────────────────────────────────────────┘
```

**Commitment 3: Recovery follows a strict escalation protocol.**

```
L1: RETRY (same plan, same node, different seed)
    ↓ (if L1 fails N times)
L2: REPLAN (create PlanVersion v+1 with local edit)
    ↓ (if L2 fails M times)
L3: ABORT_AND_REPORT (escalate to human, return partial state)
```

### 30.4 The Node State Machine (Formal)

```python
class NodeState(Enum):
    PENDING = "pending"           # not yet eligible
    READY = "ready"               # all dependencies satisfied
    DISPATCHED = "dispatched"     # currently running
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"           # bypassed by recovery
    ABORTED = "aborted"           # escalation triggered

# Transition rules
TRANSITIONS = {
    PENDING: {READY},            # when all parents SUCCEEDED
    READY: {DISPATCHED},         # when scheduler picks this node
    DISPATCHED: {SUCCEEDED, FAILED},
    FAILED: {READY, SKIPPED, ABORTED},  # recovery decision
}
```

### 30.5 The 70-System Survey

The paper surveys **70 agent systems** and maps each to a 3-axis trade-off:

| Axis | Range | Description |
|---|---|---|
| **Controllability** | 0-10 | How inspectable/predictable is execution? |
| **Expressiveness** | 0-10 | How rich a control flow can the system express? |
| **Implementability** | 0-10 | How easy is it to build? |

Examples from the survey:

| System | Ctrl | Expr | Impl | Notes |
|---|---|---|---|---|
| AutoGPT (raw) | 1 | 10 | 8 | High expressiveness, low controllability |
| LangChain AgentExecutor | 3 | 8 | 9 | Moderate |
| LangGraph | 7 | 7 | 7 | Balanced, graph-based |
| CrewAI | 4 | 7 | 8 | Multi-agent |
| SGH (proposed) | 9 | 5 | 6 | High ctrl, lower expr |
| DSPy | 6 | 5 | 7 | Compilation-based |
| Aider | 5 | 6 | 7 | Code-edit focused |
| Claude Code | 6 | 8 | 8 | Production harness |
| MetaGPT | 4 | 8 | 6 | SOP-based |
| GPTSwarm | 5 | 9 | 5 | Graph optimization |

The trade-off is explicit: **controllability ↔ expressiveness**.

### 30.6 Termination and Soundness Guarantees

SGH provides two formal guarantees:

**Termination:** If the recovery layer enforces the strict escalation protocol (L1→L2→L3), the system is guaranteed to terminate in finite time. Proof: L1 has a max retry count, L2 has a max replan count, L3 terminates. ∎

**Soundness:** If the planner layer is sound (every emitted DAG is type-correct and respects task constraints), and the execution layer respects the DAG, then every SUCCEEDED state satisfies the task specification. ∎

### 30.7 Seven-Group Experimental Design

The paper proposes a 7-group experimental framework for empirical validation (no results yet — position paper):

| Group | Description | Compares to |
|---|---|---|
| 1. Agent Loop (ReAct) | Baseline | — |
| 2. Agent Loop (Plan-Execute) | Baseline variant | vs 1 |
| 3. LangGraph | Industry graph harness | vs 1, 2 |
| 4. SGH (no recovery) | DAG only | vs 3 |
| 5. SGH (L1 recovery) | + retry | vs 4 |
| 6. SGH (L1+L2 recovery) | + replan | vs 5 |
| 7. SGH (L1+L2+L3 recovery) | + abort | vs 6 |

Metrics: task success rate, wall-clock time, recovery depth, audit log size, planner calls per task.

### 30.8 Implementation Strategy for PlotLot

**Sprint 1:** Audit current PlotLot agent code against the 3 SGH commitments. Are plans immutable? Are layers separated? Is recovery bounded?

**Sprint 2:** Refactor `PlotLotAgentLoop` to expose a `PlanVersion` frozen dataclass. Add explicit DAG tracking.

**Sprint 3:** Implement the 3-layer separation: `planner.py`, `executor.py`, `recoverer.py`. Each is a single-purpose module.

**Sprint 4:** Implement the strict escalation protocol. Set `L1_max=3`, `L2_max=2`, `L3=human`.

**Sprint 5:** A/B test SGH-style execution vs current PlotLot agent loop on 100 entitlement tasks. Measure: success rate, recovery depth, audit completeness.

### 30.9 Cross-References

| SGH Concept | Other Papers in This Survey |
|---|---|
| Immutable plan version | Paper 21 (NLAH: externalized policy is versioned) |
| Recovery escalation | Paper 23 (Runtime Governance: intercept/mitigate/escalate) |
| DAG execution | Paper 28 (GEMS: planner generates DAG of subtasks) |
| Controllability | Paper 20 (Meta-Harness: harness as inspectable policy) |
| Soundness | Paper 24 (SkVM: capability profiles enforce soundness) |

---


## Paper 31: Problem Reductions at Scale (arXiv:2604.11535)

**Authors:** Xi-Wei Pan, Shi-Wen An, Jin-Guo Liu  
**Date:** 13 Apr 2026 (revised 7 May 2026)  
**Core Claim:** A **harness-engineering** approach to building a library of polynomial-time reductions between NP-hard problems. In 3 months, the team produced a CLI tool with **100+ problem types and 200+ reduction rules in 170k lines of Rust**, using a no-code contribution route for domain experts and a multi-layer verification stack.

### 31.1 The Problem

NP-hard optimization problems are usually tied to a specific solver:
- Quantum hardware (QAOA, VQE)
- Commercial optimizers (Gurobi, CPLEX)
- Domain heuristics (simulated annealing, tabu search)

If a practitioner has problem `P1` and only solver `S2` (which solves `P2`), they need a **reduction** `P1 → P2` to use it. Writing these reductions is expert labor.

### 31.2 The Harness

The paper's harness has 4 components:

#### 31.2.1 No-Code Contribution Route

Domain experts (not Rust programmers) contribute reductions via a YAML schema:

```yaml
reduction:
  from: MaxCut
  to: QUBO
  description: "Map MaxCut's vertex partition to QUBO's binary variables"
  
  # Variable mapping
  variables:
    from_side: { type: "binary", count: "n", meaning: "vertex_in_partition" }
    to_side:   { type: "binary", count: "n", meaning: "x_i ∈ {0,1}" }
  
  # Cost mapping
  cost_function:
    from: "−Σ_{(i,j)∈E} (1 − 2·(x_i ⊕ x_j))"   # cut size
    to:   "Σ_{(i,j)∈E} (1 − 2·x_i)(1 − 2·x_j) + Σ_i x_i(1−x_i)·penalty"  # penalty trick
  
  # Proof sketch
  proof: |
    MaxCut counts edges across the cut. For edge (i,j), the term
    (1 - x_i)(1 - 2x_j) + x_i(2x_j - 1) equals 1 when i,j are in
    different partitions, 0 otherwise. Summing and negating gives
    the cut size. Add quadratic penalty Σ_i x_i(1-x_i) to enforce
    x_i ∈ {0, 1}.
```

A Rust contributor then translates the YAML into code; a verifier (see 31.2.2) checks correctness.

#### 31.2.2 Multi-Layer Verification Stack

| Layer | Check | Failure mode caught |
|---|---|---|
| L1: Type-level | Rust types match reduction signature | Wrong shape, missing fields |
| L2: Property-based | Run randomized test cases, compare with brute force on small instances | Algorithmic bug |
| L3: Differential | Compare with reference implementation (if exists) | Performance regression |
| L4: Agentic feature test | An LLM agent "role-plays" the end user, generates edge-case inputs, verifies output | Real-world edge cases |
| L5: Domain expert review | A human in the relevant field signs off | Domain correctness |

The **agentic feature test (L4)** is novel: the harness spawns an LLM agent that pretends to be a user trying to break the reduction with adversarial inputs.

```python
class AgenticFeatureTester:
    def __init__(self, reduction: Reduction, max_iters: int = 20):
        self.reduction = reduction
        self.adversary = LLMAdversary(role="expert user trying to break this")
        self.oracle = BruteForceOracle(problem=reduction.from_problem, max_n=10)
    
    def test(self) -> List[TestFailure]:
        failures = []
        for i in range(self.max_iters):
            # Adversary generates an input
            test_input = self.adversary.generate_adversarial_input(
                self.reduction.from_problem
            )
            # Reduce
            reduced = self.reduction.apply(test_input)
            # Solve on reduced side
            solved = self.reduction.solver.solve(reduced)
            # Lift back
            lifted = self.reduction.lift(solved, test_input)
            # Verify against brute force
            expected = self.oracle.solve(test_input)
            if lifted.cost != expected.cost:
                failures.append(TestFailure(
                    input=test_input, got=lifted.cost, expected=expected.cost,
                    iter=i
                ))
        return failures
```

#### 31.2.3 Automated Implementation-Review-Integration Pipeline

```
domain expert YAML → LLM agent generates Rust → LLM agent reviews diff
   → LLM agent opens PR → CI runs L1-L4 verification
   → human reviewer approves → merge → registry updated
```

The pipeline uses **two LLM agents** in a critic-improver loop:

```python
class CriticImproverLoop:
    def __init__(self, max_rounds: int = 5):
        self.improver = LLMCodeAgent(role="senior Rust developer")
        self.critic = LLMReviewer(role="pedantic reviewer")
    
    def run(self, yaml_spec: str) -> RustCode:
        code = self.improver.implement(yaml_spec)
        for round in range(self.max_rounds):
            review = self.critic.review(code, yaml_spec)
            if review.is_approved:
                return code
            code = self.improver.refine(code, review.feedback, yaml_spec)
        raise PipelineFailure(f"After {self.max_rounds} rounds, code still has issues: {review.feedback}")
```

#### 31.2.4 Composable Reduction Graph

Once reductions are registered, the system computes **transitive closure** of the reduction graph:

```
If A → B and B → C are registered, then A → C is automatically available
with composition: reduction_A_to_C = reduction_B_to_C ∘ reduction_A_to_B
```

This is a key insight: **a new solver registered for any single problem type instantly becomes available to every problem connected by a reduction path.**

### 31.3 Results

In 3 months, with a small team (3-5 people, mostly part-time), the harness produced:

| Metric | Value |
|---|---|
| Problem types | 100+ |
| Reduction rules | 200+ |
| Lines of Rust | 170,000+ |
| Solver backends | 12 (Gurobi, CPLEX, QAOA via IBMQ, D-Wave, simulated annealing, tabu, ALNS, etc.) |
| Domain expert contributors | 15+ (no Rust background) |
| CI/CD test runs/day | 2,400 |
| Reduction-path queries served | 50,000+ |

The prior state of the art for reduction libraries (e.g., `qiskit-optimization`, `pyomo`): typically 20-30 reductions, 5-10k lines, 1-2 year timelines, expert-only.

### 31.4 The Reduction Graph (Code Sketch)

```python
class ReductionGraph:
    def __init__(self):
        self.nodes: Dict[str, Problem] = {}      # problem types
        self.edges: Dict[Tuple[str, str], Reduction] = {}  # (from, to) → reduction
    
    def add_problem(self, p: Problem):
        self.nodes[p.name] = p
    
    def add_reduction(self, r: Reduction):
        self.edges[(r.from_problem, r.to_problem)] = r
        # Recompute transitive closure
        self._update_closure()
    
    def find_path(self, source: str, target: str) -> List[Reduction]:
        """BFS through the reduction graph to find a chain source → target."""
        if (source, target) in self.closure:
            return self.closure[(source, target)]
        # BFS
        visited = {source}
        queue = deque([(source, [])])
        while queue:
            current, path = queue.popleft()
            for (f, t), r in self.edges.items():
                if f == current and t not in visited:
                    new_path = path + [r]
                    if t == target:
                        return new_path
                    visited.add(t)
                    queue.append((t, new_path))
        return None  # no path
    
    def compose(self, r1: Reduction, r2: Reduction) -> Reduction:
        """If r1: A→B and r2: B→C, return r3: A→C."""
        assert r1.to_problem == r2.from_problem
        return ComposedReduction(
            from_problem=r1.from_problem,
            to_problem=r2.to_problem,
            steps=[r1, r2],
        )
```

### 31.5 Threat Model

| Attack | Vector | Mitigation |
|---|---|---|
| Adversarial YAML injection | Domain expert YAML contains malicious Rust snippets | Sandboxed LLM implementer, L1 type checks reject |
| Reduction graph poisoning | Edge `(A, B)` registered with wrong semantics | L2 property-based tests catch with high probability |
| Agentic feature test collusion | Adversary LLM and reviewer LLM are same model, collude | Use different model families, blind review |
| Transitive closure explosion | N problems → O(N²) implicit edges | Lazy closure, only compute on-demand |
| Cost under-estimation | Solver reports `cost=0` for unsatisfiable | Sanity-check lifted solution against input |

### 31.6 Implementation Strategy for PlotLot

**Sprint 1:** Define a PlotLot-specific reduction graph: 10 problem types (`parcel_query`, `zoning_lookup`, `entitlement_check`, `comp_sales`, `permit_status`, `lien_check`, `flood_zone`, `school_district`, `transit_access`, `tax_history`).

**Sprint 2:** Implement 2-3 reductions: e.g., `parcel_query → comp_sales` (given a parcel, find comparable sales), `entitlement_check → zoning_lookup` (given a proposed building, determine what zoning applies).

**Sprint 3:** Add a multi-layer verifier: type checks, property tests, and an LLM-driven adversarial tester (like `AgenticFeatureTester`).

**Sprint 4:** Build a CLI tool `plotlot-solve` that takes a problem name + input, finds the reduction path, and dispatches to the appropriate solver.

### 31.7 Cross-References

| Concept | Other Papers in This Survey |
|---|---|
| Multi-layer verification | Paper 27 (AEC-Bench: LLM judge rubric) |
| Critic-improver loop | Paper 28 (GEMS: verifier-in-the-loop) |
| Composable graph | Paper 30 (SGH: DAG of subtasks) |
| Domain expert contribution | Paper 18 (SoK: Agentic Skills — composite skills from primitives) |
| Transitive closure | Paper 19 (MCP: tools compose into workflows) |

---

