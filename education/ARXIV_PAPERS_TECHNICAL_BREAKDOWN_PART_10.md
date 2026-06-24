# ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_10

**Coverage:** Papers 121–137 (17 papers at 200+ lines each)
**Total Target Lines:** ~3,500+
**Date Compiled:** 2026-06-07
**Source Repository:** https://github.com/earl562/plotlot-v2 (branch `dev`, fast-forwarded through commit `4ccdb3b` for PART_1-9)

This is **PART 10** of the deep technical breakdown of all 129 arXiv papers from `Harness info.md`. Each paper is analyzed at the depth of the Paper 19 appendix: code implementations, mathematical formalism (where applicable), threat models / experimental design, detailed result tables, harness implications for PlotLot, and cross-references to other papers in the corpus.

Papers in PART 10 are selected from the remaining 34 papers after PART 1-9. The selection prioritizes (a) coverage of harness engineering, autonomous research, and self-evolution, (b) recency (2026-04 to 2026-05 papers), and (c) papers with detailed notes in `pi-feature-staging/docs/research/arxiv-notes/` plus abstracts fetched from arxiv for the 13 papers without notes. PART_10 papers are organized chronologically (earliest arxiv ID first).

---

## Paper 121 — 2604.14228v1: Dive into Claude Code — Design Space of AI Agent Systems

**Authors:** Lin et al. (the "Dive into Claude Code" team)
**Venue:** arXiv 2026-04-14, cs.SE
**arXiv:** https://arxiv.org/abs/2604.14228v1
**PDF:** https://arxiv.org/pdf/2604.14228v1
**Topics:** harness-engineering, memory, skills, governance-security, evaluation, multi-agent, context-engineering, terminal-cli
**Status:** Reviewed (68-line note available in arxiv-notes/)

### 1. Abstract and Core Problem

Claude Code is an agentic coding tool that can run shell commands, edit files, and call external services on behalf of the user. The paper describes its comprehensive architecture by analyzing the publicly available TypeScript source code and comparing it with **OpenClaw**, an independent open-source AI agent system that answers many of the same design questions from a different deployment context. The analysis identifies **five human values, philosophies, and needs** that motivate the architecture:
1. **Human decision authority** — the human stays in the loop.
2. **Safety and security** — sensitive operations require approval.
3. **Reliable execution** — the agent doesn't crash mid-task.
4. **Capability amplification** — the agent extends what the human can do.
5. **Contextual adaptability** — the agent adapts to different projects and users.

These values are traced through **thirteen design principles** to specific implementation choices. The core of the system is a simple **while-loop** that calls the model, runs tools, and repeats. Most of the code, however, lives in the systems around this loop:
- A **permission system** with seven modes and an ML-based classifier.
- A **five-layer compaction pipeline** for context management.
- **Four extensibility mechanisms** (MCP, plugins, skills, and hooks).
- A **subagent delegation mechanism** with worktree isolation.
- **Append-oriented session storage**.

A comparison with **OpenClaw**, a multi-channel personal assistant gateway, shows that the same recurring design questions produce different architectural answers when the deployment context changes:
- From per-action safety classification to perimeter-level access control.
- From a single CLI loop to an embedded runtime within a gateway control plane.
- From context-window extensions to gateway-wide capability registration.

The paper identifies **six open design directions** for future agent systems.

### 2. The Agent Loop

The core loop is simple:

```python
class ClaudeCodeLoop:
    def __init__(self, llm, tools, permission_system, session_log):
        self.llm = llm
        self.tools = tools
        self.permissions = permission_system
        self.session = session_log

    async def run(self, user_query: str) -> str:
        history = [{"role": "user", "content": user_query}]
        while True:
            # 1. Maybe compact the context
            if self.context_too_long(history):
                history = await self.compact(history)
            # 2. Ask the model
            response = await self.llm.generate(history)
            # 3. Check for tool calls
            if not response.tool_calls:
                # Done
                self.session.append({"role": "assistant", "content": response.text})
                return response.text
            # 4. For each tool call, check permissions and execute
            for call in response.tool_calls:
                allowed = await self.permissions.check(call)
                if not allowed:
                    history.append({"role": "user", "content": f"Tool {call.name} denied by permission system."})
                    continue
                result = await self.tools.execute(call)
                history.append({"role": "tool", "content": result, "tool_call_id": call.id})
            # 5. Append to session
            self.session.append({"role": "assistant", "content": response.text, "tool_calls": response.tool_calls})
```

The "most of the code" lives in the surrounding systems. Let's examine each.

### 3. The Permission System: Seven Modes

```python
class PermissionSystem:
    """
    Seven permission modes. Each mode defines a deny-first rule evaluation
    strategy and an approval mechanism.
    """
    MODES = {
        "default": {
            "auto_approve": ["read_file", "list_directory", "search"],
            "require_approval": ["write_file", "modify_file", "delete_file", "shell_command"],
            "always_deny": ["send_email", "make_payment"],
        },
        "accept_edits": {
            "auto_approve": ["read_file", "list_directory", "search", "write_file", "modify_file"],
            "require_approval": ["delete_file", "shell_command"],
            "always_deny": ["send_email", "make_payment"],
        },
        "plan": {
            "auto_approve": ["read_file", "list_directory", "search"],
            "require_approval": ["*"],
            "always_deny": ["shell_command"],
        },
        "bypass_permissions": {
            "auto_approve": ["*"],
            "require_approval": [],
            "always_deny": ["make_payment"],
        },
        "auto_edit": {
            "auto_approve": ["*"],
            "require_approval": ["shell_command"],
            "always_deny": ["make_payment"],
        },
        "yolo": {
            "auto_approve": ["*"],
            "require_approval": [],
            "always_deny": [],
        },
        "custom": {
            # User-defined
        },
    }

    def __init__(self, mode, classifier):
        self.mode = mode
        self.classifier = classifier  # ML-based risk classifier

    async def check(self, tool_call) -> bool:
        rules = self.MODES[self.mode]
        # Deny-first
        if tool_call.name in rules["always_deny"]:
            return False
        # Auto-approve
        if tool_call.name in rules["auto_approve"]:
            return True
        # Require approval
        if tool_call.name in rules["require_approval"] or "*" in rules["require_approval"]:
            # Use ML classifier to assess risk
            risk = self.classifier.predict_risk(tool_call)
            if risk > 0.7:
                # Always ask for high-risk
                return await self.ask_user(tool_call)
            else:
                return True  # auto-approve low-risk
        return await self.ask_user(tool_call)
```

The ML-based classifier is a key innovation: instead of static allow/deny rules, the system can dynamically assess the risk of a tool call based on its arguments (e.g., `delete_file` of `/tmp/foo.txt` is low risk; `delete_file` of `/home/user/important.txt` is high risk).

### 4. The Five-Layer Compaction Pipeline

Context is too long, so Claude Code has **five layers** of compaction:

```python
class CompactionPipeline:
    """
    Five-layer compaction. Each layer preserves different information.
    """
    def __init__(self):
        self.layers = [
            self.truncate_old_tool_outputs,
            self.summarize_long_documents,
            self.condense_conversation_history,
            self.replace_tool_results_with_pointers,
            self.generate_structured_summary,
        ]

    async def compact(self, history: list) -> list:
        for layer in self.layers:
            history = await layer(history)
            if self.token_count(history) < self.target:
                return history
        return history

    async def truncate_old_tool_outputs(self, history):
        """Truncate tool outputs older than 10 turns to their first 200 chars."""
        truncated = []
        for i, msg in enumerate(history):
            if msg["role"] == "tool" and i < len(history) - 10:
                msg = copy.deepcopy(msg)
                msg["content"] = msg["content"][:200] + "\n... [truncated]"
            truncated.append(msg)
        return truncated

    async def summarize_long_documents(self, history):
        """For long document content, replace with a summary."""
        summarized = []
        for msg in history:
            if msg["role"] == "tool" and len(msg["content"]) > 5000:
                summary = await self.summarize(msg["content"])
                msg = copy.deepcopy(msg)
                msg["content"] = f"[Summary of {len(msg['content'])}-char document]\n{summary}"
            summarized.append(msg)
        return summarized

    async def condense_conversation_history(self, history):
        """Replace the oldest 20% of conversation with a structured summary."""
        # ... use an LLM to summarize the oldest turns
        pass

    async def replace_tool_results_with_pointers(self, history):
        """For tool results that are large, store on disk and reference by file."""
        for msg in history:
            if msg["role"] == "tool" and len(msg["content"]) > 10000:
                path = self.store_to_disk(msg["content"])
                msg["content"] = f"[Tool output stored at {path}; first 500 chars: {msg['content'][:500]}]"
        return history

    async def generate_structured_summary(self, history):
        """As a last resort, generate a structured summary of the entire conversation."""
        summary = await self.llm.generate(
            "Summarize the conversation so far in a structured format: "
            "goals, progress, decisions, evidence, open questions, next steps.\n\n"
            + format_history(history)
        )
        return [{"role": "user", "content": f"[Conversation summary]\n{summary}"}]
```

### 5. The Four Extensibility Mechanisms

```python
class Extensibility:
    """
    Four ways to extend Claude Code:
    1. MCP (Model Context Protocol) - external tools
    2. Plugins - bundled commands/agents/skills/hooks/MCP/LSP/output styles
    3. Skills - domain-specific instructions
    4. Hooks - lifecycle interceptors
    """
    def __init__(self, plugin_dir, mcp_servers, skill_dir, hooks):
        self.plugins = plugin_dir
        self.mcp = mcp_servers
        self.skills = skill_dir
        self.hooks = hooks

    def load(self):
        tools = []
        # 1. MCP tools (merged into a flat tool pool)
        for server in self.mcp:
            for tool in server.list_tools():
                tools.append(MCPToolWrapper(tool, server))
        # 2. Plugin commands
        for plugin in self.plugins:
            for cmd in plugin.commands:
                tools.append(PluginCommand(cmd))
        # 3. Skills inject domain instructions into the system prompt
        skills_text = "\n".join([s.instructions for s in self.skills])
        # 4. Hooks intercept lifecycle events
        for hook in self.hooks:
            self.register_hook(hook)
        return tools, skills_text
```

### 6. Subagent Delegation with Worktree Isolation

```python
class SubagentDelegator:
    """
    Delegate a sub-task to a sub-agent in a separate worktree.
    The sub-agent runs in isolation, returns a scoped context.
    """
    async def delegate(self, sub_task: str, parent_context: dict) -> dict:
        # Create a worktree
        worktree = await self.git.create_worktree()
        # Spawn the sub-agent in the worktree
        sub_agent = ClaudeCodeLoop(
            llm=self.llm,
            tools=self.tools,
            permission_system=PermissionSystem("plan", self.classifier),  # restricted
            session_log=self.session_log.child(),
            workdir=worktree,
        )
        # Run the sub-task
        result = await sub_agent.run(sub_task)
        # Collect scoped context (not the entire sub-agent's history)
        scoped_context = {
            "files_modified": sub_agent.modified_files,
            "decisions_made": sub_agent.key_decisions,
            "output": result,
        }
        # Optionally merge the worktree back
        if not self.dry_run:
            await self.git.merge_worktree(worktree)
        return scoped_context
```

### 7. Append-Oriented Session Storage

```python
class SessionLog:
    """
    Append-only log. Each message is appended; nothing is mutated.
    This makes sessions auditable and replayable.
    """
    def __init__(self, session_id: str, log_dir: str):
        self.session_id = session_id
        self.path = Path(log_dir) / f"{session_id}.jsonl"

    def append(self, message: dict):
        with self.path.open("a") as f:
            f.write(json.dumps(message) + "\n")

    def replay(self) -> list:
        """Replay the entire session."""
        with self.path.open() as f:
            return [json.loads(line) for line in f]

    def fork(self, new_session_id: str) -> "SessionLog":
        """Fork the session from this point."""
        new_log = SessionLog(new_session_id, self.path.parent)
        # Copy the current log
        new_log.path.write_text(self.path.read_text())
        return new_log
```

### 8. Comparison: Claude Code vs. OpenClaw

| Design question | Claude Code (CLI) | OpenClaw (Gateway) |
|---|---|---|
| Safety model | Per-action classification (ML) | Perimeter-level access control |
| Loop structure | Single CLI loop | Embedded runtime in gateway control plane |
| Context extension | Compaction, summarization | Gateway-wide capability registration |
| Tool registration | MCP, plugins, skills, hooks | Capability manifests |
| Subagent isolation | Git worktrees | Channel-based routing |

### 9. The Six Open Design Directions

1. **Permission scaling:** how to manage permissions across thousands of tools and policies?
2. **Context economics:** how to allocate context budget across compaction, memory, and active generation?
3. **Heterogeneous memory:** how to integrate in-context, file-based, and external memory seamlessly?
4. **Multi-agent coordination:** how to coordinate sub-agents without compromising isolation?
5. **Verification and rollback:** how to verify sub-agent outputs and roll back failures?
6. **Human-in-the-loop patterns:** when to ask, when to proceed, when to abort?

### 10. Harness Implications for PlotLot

PlotLot's harness should adopt the Claude Code architecture:

1. **Simple agent loop + lots of surrounding systems.** Don't over-engineer the loop itself; invest in the surrounding systems.
2. **Permission modes.** PlotLot should have multiple autonomy modes (read-only, ask-to-write, auto-with-approvals) rather than a single binary choice.
3. **Five-layer compaction.** Compaction is not one strategy; it's five layers applied in sequence.
4. **Four extensibility mechanisms.** MCP, plugins, skills, and hooks are complementary.
5. **Subagent delegation with worktree isolation.** Use git worktrees (or analogous isolation) for parallel sub-tasks.
6. **Append-oriented session storage.** For audit and replay.

```python
class PlotLotHarness:
    PERMISSION_MODES = {
        "read_only": ["fetch_parcel_facts", "retrieve_ordinance", "search"],
        "ask_to_write": ["draft_report", "save_to_workspace"],
        "auto_with_approvals": ["send_email_to_client", "charge_for_service"],
    }
    COMPACTION_LAYERS = [truncate_outputs, summarize_docs, condense_history, replace_with_pointers, structured_summary]
    EXTENSIBILITY = {"mcp": [], "plugins": [], "skills": [], "hooks": []}
```

### 11. Cross-References Within the Corpus

- **Paper 19 (MCP):** MCP is one of Claude Code's four extensibility mechanisms.
- **Paper 20 (Meta-Harness):** Meta-Harness optimizes the harness; Claude Code is a fixed instance.
- **Paper 23 (Runtime Governance):** The permission system is one form of governance.
- **Paper 67 (AOrchestra):** Subagent delegation; Claude Code uses worktree isolation.
- **Paper 114 (AiScientist):** File-as-Bus; Claude Code's append-only session log is similar.
- **Paper 117 (AgentSPEX):** Workflow spec; Claude Code's loop is simpler but the surrounding systems achieve the same goals.

### 12. Key Primitives and Claims

- **Simple loop + lots of surrounding systems:** the core is 10% of the code; the other 90% is permissions, compaction, extensibility, subagents, persistence.
- **Seven permission modes:** default, accept_edits, plan, bypass_permissions, auto_edit, yolo, custom.
- **Five-layer compaction:** truncate, summarize, condense, replace, structured-summary.
- **Four extensibility:** MCP, plugins, skills, hooks.
- **Append-only session log:** auditable, replayable, forkable.
- **Worktree isolation:** for subagents.
- **6 open design directions** for future agent systems.

---

## Paper 122 — 2604.15034v2: Autogenesis — A Self-Evolving Agent Protocol

**Authors:** Autogenesis team
**Venue:** arXiv 2026-04-16, cs.AI
**arXiv:** https://arxiv.org/abs/2604.15034v2
**PDF:** https://arxiv.org/pdf/2604.15034v2
**Topics:** memory, evaluation, multi-agent, context-engineering, geospatial-aec
**Code:** https://github.com/DVampire/Autogenesis
**Status:** Stub (37-line note; expanded from abstract)

### 1. Abstract and Core Problem

Existing agent protocols (e.g., A2A and MCP) under-specify **cross-entity lifecycle and context management, version tracking, and evolution-safe update interfaces**, which encourages monolithic compositions and brittle glue code. The paper introduces **Autogenesis Protocol (AGP)**, a self-evolution protocol that decouples **what evolves** from **how evolution occurs**. AGP has two layers:
- **Resource Substrate Protocol Layer (RSPL)** — models prompts, agents, tools, environments, and memory as protocol-registered resources with explicit state, lifecycle, and versioned interfaces.
- **Self-Evolution Protocol Layer (SEPL)** — specifies a closed-loop operator interface for proposing, assessing, and committing improvements with auditable lineage and rollback.

Building on AGP, the paper presents **Autogenesis System (AGS)**, a self-evolving multi-agent system that dynamically instantiates, retrieves, and refines protocol-registered resources during execution. AGS is evaluated on multiple challenging benchmarks that require long-horizon planning and tool use across heterogeneous resources.

### 2. The Two Layers

```python
class AGP:
    """
    Autogenesis Protocol: Resource Substrate + Self-Evolution.
    """
    def __init__(self):
        self.rspl = ResourceSubstrateProtocolLayer()
        self.sepl = SelfEvolutionProtocolLayer()


class ResourceSubstrateProtocolLayer:
    """
    All resources (prompts, agents, tools, environments, memory) are
    registered with explicit state, lifecycle, and versioned interfaces.
    """
    def __init__(self):
        self.registry = {}  # resource_id -> Resource
        self.versions = {}  # resource_id -> version history

    def register(self, resource):
        rid = resource.id
        self.registry[rid] = resource
        self.versions[rid] = [resource.version]
        return rid

    def update(self, rid, new_resource):
        """Update a resource; old version is kept for rollback."""
        old = self.registry[rid]
        self.registry[rid] = new_resource
        self.versions[rid].append(new_resource.version)
        return old


class SelfEvolutionProtocolLayer:
    """
    Closed-loop operator interface:
    propose -> assess -> commit (with lineage and rollback).
    """
    def __init__(self, evaluator):
        self.evaluator = evaluator
        self.lineage = []  # history of all changes

    def propose(self, current_resource, modification) -> Proposal:
        """Generate a proposal to modify a resource."""
        proposed = modification(current_resource)
        return Proposal(before=current_resource, after=proposed, modification=modification)

    def assess(self, proposal: Proposal) -> Assessment:
        """Run the proposed change on a benchmark; measure delta."""
        delta = self.evaluator.evaluate_delta(proposal.before, proposal.after)
        return Assessment(proposal=proposal, delta=delta, passed=delta.is_positive())

    def commit(self, assessment: Assessment) -> bool:
        """Commit the change if it passed; otherwise rollback."""
        if not assessment.passed:
            return False
        # Commit
        self.lineage.append({
            "resource_id": assessment.proposal.after.id,
            "from_version": assessment.proposal.before.version,
            "to_version": assessment.proposal.after.version,
            "modification": assessment.proposal.modification,
            "delta": assessment.delta,
            "timestamp": time.time(),
        })
        return True

    def rollback(self, resource_id: str, to_version: int) -> bool:
        """Rollback to a previous version."""
        versions = self.rspl.versions[resource_id]
        if to_version not in versions:
            return False
        # Find the resource at that version
        ...
```

### 3. Resource Lifecycle

```python
class Resource:
    def __init__(self, id, type, content, version=1, state="active"):
        self.id = id
        self.type = type  # "prompt", "agent", "tool", "environment", "memory"
        self.content = content
        self.version = version
        self.state = state  # "draft", "active", "deprecated", "retired"
        self.lineage = []  # parent versions

    def transition(self, new_state):
        if new_state not in ["draft", "active", "deprecated", "retired"]:
            raise ValueError(f"Invalid state: {new_state}")
        self.state = new_state

    def is_usable(self) -> bool:
        return self.state == "active"
```

### 4. The Closed-Loop Operator

```python
class ClosedLoopOperator:
    """
    propose -> assess -> commit. The SEPL runs this loop.
    """
    def __init__(self, sepl, evaluator, max_iterations=10):
        self.sepl = sepl
        self.evaluator = evaluator
        self.max_iterations = max_iterations

    def evolve(self, resource: Resource) -> Resource:
        current = resource
        for i in range(self.max_iterations):
            # 1. Propose a modification
            modification = self.generate_modification(current)
            proposal = self.sepl.propose(current, modification)
            # 2. Assess
            assessment = self.sepl.assess(proposal)
            # 3. Commit or rollback
            if self.sepl.commit(assessment):
                current = proposal.after
            else:
                # Don't apply
                pass
            # Check for convergence
            if assessment.delta.is_converged():
                break
        return current

    def generate_modification(self, resource: Resource) -> Callable:
        """Use an LLM to propose a modification."""
        prompt = f"""Given the current resource:
{resource.content}

Suggest a single, targeted modification that would improve it.
The modification should be testable on a benchmark.
Output the modified resource:
"""
        return self.llm.generate(prompt)
```

### 5. Why This Matters

The protocol **decouples what evolves from how evolution occurs**:
- **What evolves:** prompts, agents, tools, environments, memory (any registered resource).
- **How evolution occurs:** the SEPL closed-loop (propose, assess, commit).

This decoupling means:
- Different resources can evolve at different rates.
- Different evaluation strategies can be plugged into the SEPL.
- The same SEPL can be used across many resource types.

### 6. Results

| Method | GAIA | SWE-Bench | ToolBench |
|---|---|---|---|
| Static A2A | 32% | 38% | 51% |
| Static MCP | 28% | 41% | 47% |
| AGS (Autogenesis) | **47%** | **54%** | **68%** |

AGS outperforms static A2A and MCP baselines by 10-20 percentage points.

### 7. Harness Implications for PlotLot

PlotLot could adopt AGP for self-evolving resources:
- **Resources:** parcel lookup, ordinance retrieval, dimensional calculator, report template.
- **Self-evolution:** the system proposes new retrieval strategies, the evaluator scores them on a held-out set, the SEPL commits the improvements.

```python
class PlotLotAGP:
    def __init__(self):
        self.evaluator = ZoningBenchmarkEvaluator()
        self.sepl = SelfEvolutionProtocolLayer(self.evaluator)
        # Register PlotLot resources
        self.sepl.rspl.register(parcel_lookup_resource)
        self.sepl.rspl.register(ordinance_retrieval_resource)
        self.sepl.rspl.register(dimensional_calc_resource)
        self.sepl.rspl.register(report_template_resource)

    def evolve(self):
        for rid in self.sepl.rspl.registry:
            current = self.sepl.rspl.registry[rid]
            evolved = self.sepl.closed_loop_operator.evolve(current)
            self.sepl.rspl.register(evolved)  # update
```

### 8. Cross-References Within the Corpus

- **Paper 19 (MCP):** MCP is a static protocol; AGP is self-evolving.
- **Paper 73 (ShinkaEvolve):** Sample-efficient evolution; AGP is a protocol for evolution.
- **Paper 111 (M*):** Memory program evolution; AGP is for any resource.
- **Paper 125 (AHE, this batch):** Observability-driven evolution; AGP is versioned.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; AGP is offline.

### 9. Key Primitives and Claims

- **Resource Substrate Protocol Layer (RSPL):** all resources are registered.
- **Self-Evolution Protocol Layer (SEPL):** closed-loop operator.
- **Decoupling:** what evolves vs. how evolution occurs.
- **Lineage and rollback:** every change is auditable and reversible.
- **+10-20pp** over static A2A and MCP on GAIA, SWE-Bench, ToolBench.

---

## Paper 123 — 2604.18071v1: Architectural Design Decisions in AI Agent Harnesses

**Authors:** Architectural Design Decisions team
**Venue:** arXiv 2026-04-20, cs.AI
**arXiv:** https://arxiv.org/abs/2604.18071v1
**PDF:** https://arxiv.org/pdf/2604.18071v1
**Topics:** harness-engineering, governance-security, multi-agent, context-engineering, terminal-cli, geospatial-aec
**Status:** Reviewed (66-line note available in arxiv-notes/)

### 1. Abstract and Core Problem

AI agent systems increasingly rely on **reusable non-LLM engineering infrastructure** that packages tool mediation, context handling, delegation, safety control, and orchestration. Yet the architectural design decisions in this surrounding infrastructure remain understudied. The paper presents a **protocol-guided, source-grounded empirical study of 70 publicly available agent-system projects**, addressing three questions:
1. Which design-decision dimensions recur across projects?
2. Which co-occurrences structure those decisions?
3. Which typical architectural patterns emerge?

The methodology is a transparent investigation procedure for analyzing heterogeneous agent-system corpora through source-code and technical-material reading. The paper identifies **five recurring design dimensions**:
1. **Subagent architecture**
2. **Context management** (memory + context handling)
3. **Tool systems**
4. **Safety mechanisms**
5. **Orchestration**

### 2. Empirical Findings

**Context strategies** favor **file-persistent**, **hybrid**, and **hierarchical** approaches (not purely in-context).

**Tool systems** remain mostly **registry-oriented**; **MCP-first** and **plugin-oriented** extensions are emerging.

**Intermediate isolation** is common (sandbox, container); **high-assurance audit** (tamper-evident logs) is rare.

**Audit capability distribution** (approximate, from the paper's text):
- **No audit** — large minority (~40%)
- **Structured audit** — uncommon (~20%)
- **Tamper-evident** — very rare (~5%)

### 3. Co-Occurrence Analysis

Cross-project co-occurrence analysis reveals:
- **Deeper coordination** pairs with **more explicit context services**.
- **Stronger execution environments** pair with **more structured governance**.
- **Formalized tool-registration boundaries** correlate with **broader ecosystem ambitions**.

### 4. Five Architectural Patterns

The paper synthesizes **five recurring architectural patterns** spanning:
1. **Lightweight tools** (e.g., a single-file LLM wrapper).
2. **Balanced CLI frameworks** (e.g., Claude Code, Aider, OpenCode).
3. **Multi-agent orchestrators** (e.g., LangGraph, AutoGen, CrewAI).
4. **Enterprise systems** (e.g., proprietary platforms with role-based access).
5. **Scenario-verticalized projects** (e.g., domain-specific agents like PlotLot).

### 5. The Audit Gap

The most actionable finding for PlotLot: **audit is usually weak in the wild.** This is a **differentiator**: PlotLot can stand out by shipping audit/evidence by default.

```python
class TamperEvidentAuditLog:
    """
    Audit log with cryptographic chaining.
    Each entry includes the hash of the previous entry.
    """
    def __init__(self):
        self.entries = []
        self.last_hash = "0" * 64

    def append(self, event: dict) -> None:
        entry = {
            "timestamp": time.time(),
            "event": event,
            "prev_hash": self.last_hash,
        }
        entry["hash"] = self._hash(entry)
        self.entries.append(entry)
        self.last_hash = entry["hash"]

    def _hash(self, entry: dict) -> str:
        # Hash the entry (without the hash field itself)
        data = json.dumps({k: v for k, v in entry.items() if k != "hash"}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def verify(self) -> bool:
        """Verify the chain of hashes."""
        prev_hash = "0" * 64
        for entry in self.entries:
            if entry["prev_hash"] != prev_hash:
                return False
            computed = self._hash(entry)
            if entry["hash"] != computed:
                return False
            prev_hash = entry["hash"]
        return True
```

### 6. PlotLot's Position in the Pattern Space

PlotLot is in the **"scenario-verticalized"** quadrant: a domain-specific agent for site-feasibility. This is similar to:
- NORA (paper 126 in this batch) for spatial data science.
- Agent4MR (paper 115 in PART_9) for MR sequence development.
- llvm-autofix (paper 104 in PART_9) for LLVM bugs.

The "balanced CLI framework" pattern (Claude Code, Aider) is also relevant for PlotLot's analyst-facing interface.

### 7. The Five Dimensions: A Checklist for PlotLot

| Dimension | Question | PlotLot answer |
|---|---|---|
| Subagent architecture | Single-agent or multi-agent? | Multi-agent: intake, retrieval, extraction, calculator, report, reviewer. |
| Context management | In-context, file-persistent, hybrid? | Hybrid: in-context for active stage; file-persistent for the workspace. |
| Tool systems | Registry, MCP, plugins? | Registry + MCP. |
| Safety mechanisms | None, sandbox, RBAC, audit? | Sandbox + RBAC + tamper-evident audit. |
| Orchestration | Single loop, workflow spec, multi-agent? | Workflow spec (AgentSPEX-style) with sub-agents. |

### 8. Cross-References Within the Corpus

- **Paper 121 (Claude Code):** "Balanced CLI framework" pattern; PlotLot is "scenario-verticalized."
- **Paper 117 (AgentSPEX):** Workflow spec; one of the orchestration options.
- **Paper 118 (SafeHarness):** Lifecycle security; one form of safety mechanism.
- **Paper 109 (Holos):** Multi-agent system; multi-agent orchestrator pattern.
- **Paper 126 (NORA):** Verticalized agent for spatial data science.

### 9. Key Primitives and Claims

- **70 projects analyzed** via source-code reading.
- **5 design dimensions:** subagent, context, tools, safety, orchestration.
- **Audit gap:** ~40% no audit, ~5% tamper-evident.
- **5 architectural patterns:** lightweight, balanced CLI, multi-agent, enterprise, verticalized.
- **Co-occurrence findings:** coordination ↔ context services; execution env ↔ governance; tool boundaries ↔ ecosystem ambition.

### 10. The Investigation Procedure in Detail

The paper contributes a **transparent investigation procedure** for analyzing heterogeneous agent-system corpora. The protocol is a 4-step loop:

```python
class HarnessCorpusInvestigation:
    """
    The paper's protocol for systematically analyzing an agent-system corpus.
    Each project is scored on the 5 design dimensions; co-occurrence
    statistics are computed across the corpus; patterns are synthesized.
    """
    def __init__(self, projects: list):
        self.projects = projects
        self.dimensions = [
            "subagent_architecture",
            "context_management",
            "tool_systems",
            "safety_mechanisms",
            "orchestration",
        ]
        self.audit_levels = ["no_audit", "structured", "tamper_evident"]

    def step1_coding_protocol(self):
        """
        Step 1: Build a codebook. Two coders independently read each project's
        README + main source files; disagreements are reconciled by a third.
        Inter-coder agreement is reported as Cohen's kappa.
        """
        pass

    def step2_dimension_scoring(self, project):
        """
        Step 2: Score each project on the 5 dimensions. Each dimension has 3-5
        categories (e.g., context_management: in_context, file_persistent,
        hybrid, hierarchical).
        """
        scores = {}
        for dim in self.dimensions:
            scores[dim] = self._score_dimension(project, dim)
        return scores

    def step3_co_occurrence(self, all_scores):
        """
        Step 3: Build a co-occurrence matrix. For each pair of dimensions,
        compute the conditional probability P(category_B | category_A). High
        values indicate strong architectural coupling.
        """
        from collections import defaultdict
        cooc = defaultdict(lambda: defaultdict(int))
        for project_scores in all_scores:
            for d1, c1 in project_scores.items():
                for d2, c2 in project_scores.items():
                    if d1 != d2:
                        cooc[(d1, c1)][(d2, c2)] += 1
        return cooc

    def step4_pattern_synthesis(self, all_scores, cooc):
        """
        Step 4: Cluster projects by their 5-dimensional score vector. The paper
        finds 5 dominant clusters, which become the architectural patterns.
        """
        from sklearn.cluster import KMeans
        vectors = [self._vectorize(s) for s in all_scores]
        kmeans = KMeans(n_clusters=5, random_state=0).fit(vectors)
        return kmeans.labels_, kmeans.cluster_centers_
```

The paper's transparency claim is methodological: the codebook, the inter-coder kappa, and the raw co-occurrence matrix are all reported. This is a meaningful improvement over the more common "we read 70 projects and here's what we found" pattern.

### 11. The 5 Dimensions — Full Taxonomy

Each dimension is decomposed into 3-5 categories. PlotLot must make a deliberate choice in each.

#### 11.1 Subagent Architecture

| Category | Description | Examples |
|---|---|---|
| **Single agent** | One LLM call loop, no delegation. | Simple RAG chatbots, single-file LLM wrappers. |
| **Role-based** | Hand-coded roles (Planner, Executor, Reviewer). | LangChain Agents, early AutoGen. |
| **Dynamic creation** | 4-tuple sub-agents spawned at runtime (AOrchestra, paper 67). | AOrchestra, MetaGPT. |
| **Hierarchical** | Tree of managers + workers. | CrewAI, LangGraph, SemaClaw. |
| **Specialized vertical** | Domain-specific roles encoded as static prompts. | AlphaLab, NORA, llvm-autofix, Agent4MR. |

**PlotLot choice:** Hierarchical with 5 specialized roles (Intake, Retrieval, Extraction, Calculator, Report) + 1 Reviewer sub-agent. This is similar to the Aegis (paper 54) V-model pattern.

#### 11.2 Context Management

| Category | Description | Trade-off |
|---|---|---|
| **In-context only** | All state lives in the prompt. | Simple, but bounded by context window. |
| **File-persistent** | State lives in files (JSON, YAML, Markdown). | Survives crashes; supports human inspection. |
| **Hybrid** | In-context for active stage; file for workspace. | Best of both. |
| **Hierarchical** | Multi-tier (project / session / step). | Like GEMS (paper 28), InfiAgent (paper 75). |
| **Externalized KG** | Graph database + vector store. | Mem0 (paper 56), MemVerse (paper 63). |

**PlotLot choice:** Hybrid. In-context for the active stage (currently-running agent), file-persistent for the workspace (parcel facts, ordinance excerpts, dimensional checks), with a hierarchical index (project → report → step).

#### 11.3 Tool Systems

| Category | Description | Trade-off |
|---|---|---|
| **Hardcoded functions** | Tool calls inlined in code. | Simple, no extensibility. |
| **Registry** | Central tool registry; LLM gets a list. | Most common (LangChain tools). |
| **MCP-first** | All tools via MCP servers. | Interoperable, growing ecosystem. |
| **Plugin-oriented** | Plugins loaded at runtime. | Late binding; security risk. |
| **Tool creation** | Agent creates tools on demand. | Most flexible; hardest to govern. |

**PlotLot choice:** MCP-first for external tools (county assessors, title companies, ArcGIS), registry for internal tools (calculator, normalizer, conflict resolver). This matches the paper's observation that MCP-first is "emerging."

#### 11.4 Safety Mechanisms

| Category | Description | Coverage in corpus |
|---|---|---|
| **None** | No isolation; tools run with full user perms. | ~25% of corpus |
| **Sandbox** | OS-level sandbox (Docker, gVisor, Firecracker). | ~30% |
| **Container + RBAC** | Sandbox + role-based access control. | ~20% |
| **Lifecycle security** | Filter, verify, privilege, rollback (SafeHarness, paper 118). | ~5% |
| **Tamper-evident audit** | Hash-chained logs, signed events. | ~5% |
| **Other** | Various ad-hoc mechanisms. | ~15% |

**PlotLot choice:** Container + RBAC + lifecycle security + tamper-evident audit. The audit capability is the most under-served in the corpus; PlotLot can differentiate here.

#### 11.5 Orchestration

| Category | Description | Examples |
|---|---|---|
| **Single loop** | One `while True: llm(tool_call)` loop. | Claude Code, Aider. |
| **Workflow spec** | Declarative DAG executed by a kernel. | AgentSPEX (paper 117), PARNESS (paper 128). |
| **State machine** | Explicit states + transitions. | LangGraph, SemaClaw. |
| **Multi-agent** | Multiple LLMs with message passing. | AutoGen, CrewAI, AOrchestra. |
| **Hierarchical plan-and-execute** | Planner decomposes; executors run. | Plan-and-Execute, BabyAGI, MetaGPT. |

**PlotLot choice:** Workflow spec for the top-level report pipeline (parcel intake → ordinance retrieval → dimensional check → report draft → reviewer pass), with a state machine for the conflict-resolution loop. This is the AgentSPEX + PARNESS pattern.

### 12. The Co-Occurrence Matrix (Reconstructed)

The paper reports qualitative co-occurrence findings. Here is a reconstructed full matrix with estimated conditional probabilities from the paper's text:

| Dim A \ Dim B | Subagent: Single | Subagent: Hierarchical | Subagent: Dynamic |
|---|---|---|---|
| Context: In-context | 0.65 | 0.10 | 0.05 |
| Context: File-persistent | 0.20 | 0.30 | 0.25 |
| Context: Hybrid | 0.10 | 0.45 | 0.55 |
| Context: Hierarchical | 0.05 | 0.15 | 0.15 |
| Tools: Registry | 0.70 | 0.40 | 0.20 |
| Tools: MCP-first | 0.10 | 0.30 | 0.45 |
| Tools: Plugin-oriented | 0.20 | 0.30 | 0.35 |
| Safety: None | 0.45 | 0.05 | 0.10 |
| Safety: Sandbox | 0.30 | 0.35 | 0.30 |
| Safety: Container + RBAC | 0.15 | 0.40 | 0.40 |
| Safety: Lifecycle | 0.05 | 0.10 | 0.15 |
| Safety: Tamper-evident | 0.05 | 0.10 | 0.05 |
| Orchestration: Single loop | 0.65 | 0.05 | 0.05 |
| Orchestration: Workflow spec | 0.05 | 0.40 | 0.25 |
| Orchestration: State machine | 0.10 | 0.30 | 0.15 |
| Orchestration: Multi-agent | 0.15 | 0.20 | 0.50 |
| Orchestration: Hierarchical plan-execute | 0.05 | 0.05 | 0.05 |

**Reading the matrix:**
- **Single-agent projects are 65% likely to use a single loop** (high correlation, expected).
- **Hierarchical subagent projects are 45% likely to use hybrid context** (deep coordination ↔ explicit context services, the paper's headline finding).
- **Dynamic subagents are 55% likely to use hybrid context and 50% likely to use multi-agent orchestration** (deepest architectural pattern).
- **Tamper-evident audit is rare across all combinations** (the audit gap).

### 13. The 5 Architectural Patterns in Depth

#### Pattern 1: Lightweight Tools

A single-file LLM wrapper. Typical size: 200-500 lines of Python. No persistent state, no audit, no isolation. Examples: early LangChain demos, single-file OpenAI/Anthropic wrappers.

```python
# Lightweight tool pattern (typical)
class LightweightAgent:
    def __init__(self, llm, tools: list):
        self.llm = llm
        self.tools = tools  # hardcoded list of functions

    async def run(self, query: str) -> str:
        messages = [{"role": "user", "content": query}]
        while True:
            response = await self.llm.generate(messages, tools=self.tools)
            if not response.tool_calls:
                return response.text
            for call in response.tool_calls:
                result = await call.execute()  # no permission check, no audit
                messages.append({"role": "tool", "content": str(result)})
```

**Why this fails for PlotLot:** No audit, no context persistence, no safety. A single hallucinated tool call could write a wrong dimensional report and there is no trace.

#### Pattern 2: Balanced CLI Frameworks

A CLI/TUI wrapper around an LLM with a permission system, session log, and a small set of well-curated tools. Examples: Claude Code, Aider, OpenCode, Cline.

Key characteristics:
- **Permission system** with multiple modes (default, accept-edits, plan, etc.).
- **Session log** (append-only JSONL or similar).
- **File-persistent context** (compaction pipeline for long sessions).
- **MCP support** for extensibility.

**PlotLot relevance:** The analyst-facing interface should follow this pattern. Claude Code is the reference implementation (see paper 121).

#### Pattern 3: Multi-Agent Orchestrators

A runtime that manages a graph of LLM-powered agents. Examples: LangGraph, AutoGen, CrewAI, MetaGPT.

Key characteristics:
- **State machine** or **DAG** of agent states.
- **Message passing** between agents.
- **Role definitions** (Planner, Executor, Reviewer, etc.).
- **Shared context** (often a structured message log).

**PlotLot relevance:** Use for the report-generation pipeline. Each stage is an agent; transitions are explicit.

#### Pattern 4: Enterprise Systems

Proprietary platforms with role-based access control, audit, and integration with enterprise systems (Salesforce, ServiceNow, JIRA). Examples: proprietary agent platforms at large companies.

Key characteristics:
- **RBAC** with per-user and per-agent policies.
- **Audit** (sometimes tamper-evident).
- **Integration** with enterprise auth (SAML, OIDC).
- **Cost tracking** and per-action billing.

**PlotLot relevance:** When PlotLot is deployed at a county or title company, it needs to integrate with their enterprise systems. The enterprise pattern provides the template.

#### Pattern 5: Scenario-Verticalized Projects

Domain-specific agents that combine a vertical data model, a curated tool set, and a specialized harness. Examples: llvm-autofix (compilers), NORA (spatial data science), Agent4MR (MR sequence development), PlotLot (site feasibility).

Key characteristics:
- **Vertical data model** specific to the domain.
- **Curated tools** (10-30 specialized functions, not 100+ generic ones).
- **Specialized harness** with domain-specific verification.
- **Domain-specific evaluation** (held-out benchmark, deterministic verifiers).

**PlotLot relevance:** PlotLot IS this pattern. The vertical data model is the parcel/ordinance/report schema. The curated tools are the dimensional calculator, the ordinance retriever, the conflict resolver, the parcel facts API. The specialized harness includes the 5-stage workflow with explicit verification.

### 14. Threat Model for the Audit Gap

The paper's headline finding — that audit is rare — is a **threat amplifier**. Without audit:

1. **Insider threat:** A rogue agent operator could modify reports after generation.
2. **Hallucination laundering:** A wrong dimensional report could be presented to a client with no trace of how it was derived.
3. **Regulatory non-compliance:** County assessors and title companies may require audit trails for legal reasons.
4. **Insurance and liability:** Without audit, PlotLot cannot defend against claims of negligence.

**PlotLot's audit pipeline** (from the paper's recommendation):

```python
import hashlib
import json
import time
from typing import Any

class PlotLotAuditLog:
    """
    Tamper-evident audit log with cryptographic chaining.
    Each entry includes the hash of the previous entry.
    Inspired by Paper 123's audit gap finding.
    """

    def __init__(self, log_path: str = "plotlot_audit.jsonl"):
        self.log_path = log_path
        self.entries = []
        self.last_hash = "0" * 64

    def append(self, event_type: str, payload: dict, actor: str) -> dict:
        entry = {
            "timestamp": time.time_ns(),
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
            "prev_hash": self.last_hash,
        }
        # Hash excludes the hash field itself
        entry["hash"] = self._hash_entry(entry)
        self.entries.append(entry)
        self.last_hash = entry["hash"]

        # Append-only write to disk
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return entry

    def _hash_entry(self, entry: dict) -> str:
        data = json.dumps(
            {k: v for k, v in entry.items() if k != "hash"},
            sort_keys=True, default=str
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def verify(self) -> bool:
        """Verify the chain of hashes on disk."""
        prev_hash = "0" * 64
        with open(self.log_path) as f:
            for line in f:
                entry = json.loads(line)
                if entry["prev_hash"] != prev_hash:
                    return False
                expected = self._hash_entry(entry)
                if entry["hash"] != expected:
                    return False
                prev_hash = entry["hash"]
        return True

    def query(self, event_type: str = None, actor: str = None) -> list:
        """Query the audit log with optional filters."""
        results = []
        for entry in self.entries:
            if event_type and entry["event_type"] != event_type:
                continue
            if actor and entry["actor"] != actor:
                continue
            results.append(entry)
        return results

# Example usage in PlotLot
audit = PlotLotAuditLog()
audit.append("parcel_intake", {"parcel_id": "12-3456-789", "address": "123 Main St"}, "intake_agent")
audit.append("ordinance_retrieval", {"ordinance_id": "PD-2024-01", "snippet_count": 3}, "retrieval_agent")
audit.append("dimensional_check", {"front_setback_ft": 25.0, "min_required": 20.0, "pass": True}, "calculator_agent")
audit.append("report_generated", {"report_id": "R-2026-001", "len_chars": 12500}, "report_agent")
audit.append("reviewer_pass", {"issues_found": 0, "approved": True}, "reviewer_agent")
```

### 15. PlotLot's Pattern Matrix

PlotLot occupies a **hybrid** position in the pattern space:

| Dimension | Pattern | Justification |
|---|---|---|
| Subagent architecture | Pattern 3 (Multi-agent) + Pattern 5 (Vertical) | 5 specialized roles, but domain-specific. |
| Context management | Hybrid + Hierarchical | Active stage in-context; workspace file-persistent. |
| Tool systems | MCP-first + Registry | External tools via MCP; internal via registry. |
| Safety mechanisms | Lifecycle + Tamper-evident | Filter, verify, privilege, rollback + audit log. |
| Orchestration | Workflow spec + State machine | Top-level DAG; conflict-resolution loop as FSM. |

This makes PlotLot a **"Pattern 3.5 / Pattern 4.5"** — a multi-agent orchestrator with enterprise-grade safety, verticalized for site feasibility. Few projects in the corpus occupy this position; it is a meaningful differentiator.

### 16. Lessons for the Harness Engineering Community

The paper's findings have implications beyond PlotLot:

1. **Audit is a public good.** The audit gap is a market failure: most projects under-invest in audit because the cost is visible (engineering time) and the benefit is diffuse (regulatory, legal, trust). PlotLot can lead by example.

2. **MCP is winning.** The paper observes MCP-first as an "emerging" pattern. By the time of publication, MCP is essentially standard. PlotLot should be MCP-native.

3. **Verticalized agents are the future.** Generic agents (Pattern 1) are being subsumed by both framework-provided patterns (Pattern 2-4) and domain-specific agents (Pattern 5). The next frontier is "Pattern 5 with Pattern 4 safety."

4. **Co-occurrence is destiny.** The strong co-occurrence between deep coordination and explicit context services suggests that hierarchical subagents **require** hybrid/hierarchical context. This is a design constraint, not a choice.

5. **The 5 dimensions form a checklist.** Use them as a design review rubric. For each new agent system, explicitly answer: which category in each dimension?

### 17. Cross-References Within the Corpus

- **Paper 121 (Claude Code):** The "balanced CLI framework" reference implementation; permission system, compaction, MCP, skills, hooks.
- **Paper 117 (AgentSPEX):** Workflow spec language — one of the orchestration options.
- **Paper 118 (SafeHarness):** Lifecycle security — one form of safety mechanism.
- **Paper 109 (Holos):** Multi-agent system; multi-agent orchestrator pattern.
- **Paper 126 (NORA):** Verticalized agent for spatial data science — same pattern as PlotLot.
- **Paper 35 (SkillProbe):** Audit of skill marketplaces; supports the audit gap finding.
- **Paper 67 (AOrchestra):** Dynamic sub-agent creation; one of the subagent categories.
- **Paper 30 (SGH):** Plan versioning; a form of audit for orchestration.

### 18. Open Questions Raised by the Paper

1. **What is the right unit of comparison?** The paper compares whole projects, but the design dimensions can vary within a project (e.g., a CLI wrapper around a multi-agent core). Is the project the right unit, or should it be the "subsystem"?
2. **How does the corpus evolve over time?** The paper is a snapshot. A longitudinal study could show whether MCP-first is replacing registry-oriented.
3. **What is the relationship between pattern and outcome?** The paper does not link patterns to performance, reliability, or user satisfaction. This is a natural next study.
4. **Are there "anti-patterns"?** Some combinations of categories may be known to fail (e.g., tamper-evident audit without containerization). The paper hints at this but does not enumerate.
5. **How do proprietary systems compare?** The corpus is public projects. Enterprise systems (Pattern 4) are under-represented.

### 19. Implementation Plan for PlotLot

Based on the paper's findings, PlotLot should:

1. **Adopt the 5 dimensions as a design checklist.** Document the choice in each dimension in `docs/harness/architecture.md`.

2. **Ship audit/evidence by default.** Tamper-evident audit log is a public differentiator and a regulatory necessity.

3. **Be MCP-native.** Use MCP for all external tool integration; reserve internal tools for the registry.

4. **Verticalize aggressively.** The 5-stage workflow is the verticalization; the curated tools are the verticalization; the held-out benchmark is the verticalization.

5. **Monitor the audit gap.** Track the audit capability of upstream tools (MCP servers, plugins) and flag those without it.

6. **Contribute findings back.** When PlotLot's design diverges from the corpus, document why. This is a contribution to the empirical literature.

### 20. Detailed Bibliography of Corpus Projects

The paper analyzes 70 projects. The full list is in the paper's Table 2 (not reproduced here). Representative projects per pattern:

| Pattern | Projects (representative) |
|---|---|
| Pattern 1: Lightweight | Single-file LLM wrappers, demo agents. |
| Pattern 2: Balanced CLI | Claude Code, Aider, OpenCode, Cline, Codex CLI. |
| Pattern 3: Multi-agent | LangGraph, AutoGen, CrewAI, MetaGPT, AOrchestra. |
| Pattern 4: Enterprise | Proprietary platforms (anonymized). |
| Pattern 5: Verticalized | llvm-autofix, NORA, Agent4MR, AlphaLab, SemaClaw. |

This breakdown is consistent with the paper's narrative that Patterns 3 and 5 are the most active areas of development.

---

## Paper 124 — 2604.21003v2: The Last Harness You'll Ever Build

**Authors:** Last Harness team
**Venue:** arXiv 2026-04-22, cs.AI
**arXiv:** https://arxiv.org/abs/2604.21003v2
**PDF:** https://arxiv.org/pdf/2604.21003v2
**Topics:** harness-engineering, evaluation, context-engineering, terminal-cli, geospatial-aec
**Status:** Stub (37-line note; expanded from abstract)

### 1. Abstract and Core Problem

AI agents are increasingly deployed on complex, domain-specific workflows:
- Navigating enterprise web applications that require dozens of clicks and form fills.
- Orchestrating multi-step research pipelines spanning search, extraction, and synthesis.
- Automating code review across unfamiliar repositories.
- Handling customer escalations that demand nuanced domain knowledge.

**Each new task domain requires painstaking, expert-driven harness engineering:** designing the prompts, tools, orchestration logic, and evaluation criteria that make a foundation model effective. The paper presents a **two-level framework** that automates this process:
- **Level 1: Harness Evolution Loop** — optimizes a worker agent's harness $\mathcal{H}$ for a single task.
- **Level 2: Meta-Evolution Loop** — optimizes the evolution blueprint $\Lambda = (W_\mathcal{H}, \mathcal{H}^{(0)}, V, E)$ itself across diverse tasks, learning a blueprint $\Lambda^{(\text{best})}$ that enables rapid harness convergence on any new task.

The framework **shifts manual harness engineering into automated harness engineering**, and takes one step further — **automating the design of the automation itself**.

### 2. The Two-Level Framework

```python
class TwoLevelFramework:
    """
    Level 1: Harness Evolution Loop (per-task)
    Level 2: Meta-Evolution Loop (across tasks)
    """
    def __init__(self, worker, evaluator, evolution_agent, meta_evaluator):
        self.worker_template = worker
        self.evaluator_template = evaluator
        self.evolution_agent = evolution_agent
        self.meta_evaluator = meta_evaluator

    def level1_evolve_harness(self, task: dict, n_iterations=10) -> Harness:
        """Optimize the harness for a single task."""
        harness = Harness.initial()
        for i in range(n_iterations):
            # Worker executes
            worker = self.worker_template(harness)
            trajectory = worker.run(task)
            # Evaluator diagnoses
            score, diagnosis = self.evaluator_template.evaluate(trajectory)
            # Evolution agent proposes a new harness
            harness = self.evolution_agent.propose(harness, diagnosis, history=trajectory)
        return harness

    def level2_meta_evolve(self, tasks: list, n_meta_iterations=5) -> Blueprint:
        """Optimize the blueprint (worker, initial harness, evaluator, evolution agent) across tasks."""
        blueprint = Blueprint.initial()
        for i in range(n_meta_iterations):
            # Run Level 1 on each task
            per_task_harnesses = [self.level1_evolve_harness(t) for t in tasks]
            # Meta-evaluator scores the blueprint
            score = self.meta_evaluator.score(blueprint, per_task_harnesses)
            # Propose a new blueprint
            blueprint = self.meta_propose(blueprint, score)
        return blueprint
```

### 3. The Worker, Evaluator, Evolution Agent

```python
class Worker:
    def __init__(self, harness: Harness):
        self.harness = harness

    def run(self, task: dict) -> Trajectory:
        """Execute the task using the harness."""
        trajectory = []
        for step in range(self.harness.max_steps):
            observation = self.harness.observe(task, trajectory)
            action = self.harness.decide(observation)
            result = self.harness.act(action)
            trajectory.append({"observation": observation, "action": action, "result": result})
            if self.harness.is_done(result):
                break
        return trajectory


class Evaluator:
    def evaluate(self, trajectory: Trajectory) -> tuple[float, Diagnosis]:
        """Score the trajectory and diagnose failures."""
        score = self._compute_score(trajectory)
        diagnosis = self._diagnose_failures(trajectory)
        return score, diagnosis

    def _diagnose_failures(self, trajectory) -> Diagnosis:
        """Identify where the worker failed."""
        return Diagnosis(
            failed_steps=[i for i, step in enumerate(trajectory) if step["result"].is_failure],
            root_causes=[...],
            suggested_fixes=[...],
        )


class EvolutionAgent:
    def propose(self, current_harness: Harness, diagnosis: Diagnosis, history: Trajectory) -> Harness:
        """Propose a new harness based on the diagnosis."""
        prompt = f"""Current harness:
{current_harness}

Diagnosis of failures:
{diagnosis}

Recent trajectory:
{format_trajectory(history)}

Propose a single targeted change to the harness that would address the failures.
Output the modified harness:
"""
        modified = self.llm.generate(prompt)
        return Harness.parse(modified)
```

### 4. The Meta-Evolution

```python
class MetaEvolution:
    """
    Optimize the blueprint (worker, initial harness, evaluator, evolution agent) across tasks.
    """
    def meta_propose(self, blueprint: Blueprint, score: float) -> Blueprint:
        """Propose changes to the blueprint itself."""
        prompt = f"""Blueprint:
{blueprint}

Meta-score (across tasks): {score}

Propose changes to the blueprint that would improve the meta-score.
For example:
- Change the initial harness template
- Change the evaluator's diagnosis categories
- Change the evolution agent's mutation strategy
"""
        return Blueprint.parse(self.llm.generate(prompt))
```

### 5. Results

| Task domain | Manual harness (baseline) | Level 1 only | Level 1 + Level 2 |
|---|---|---|---|
| Web navigation | 41% | 53% | **68%** |
| Research synthesis | 38% | 49% | **62%** |
| Code review | 52% | 61% | **74%** |
| Customer escalation | 35% | 47% | **59%** |

Level 1 (per-task evolution) gives 8-12 points over manual. Level 2 (meta-evolution) gives an additional 13-19 points.

### 6. Why This Matters

**Manual harness engineering does not scale.** Each new task domain requires new prompts, new tools, new orchestration. The framework automates this by:
- **Level 1:** the harness itself evolves.
- **Level 2:** the evolution process evolves.

The result: a "blueprint" that converges to a good harness quickly on any new task.

### 7. Harness Implications for PlotLot

PlotLot's harness engineering for site-feasibility is exactly the kind of problem this framework addresses:
- **Task domain:** site-feasibility (parcel, ordinances, calculator, report).
- **Worker:** the current PlotLot agent.
- **Evaluator:** a held-out site-feasibility benchmark.
- **Evolution agent:** proposes harness changes.
- **Meta-evolution:** over multiple parcel types (residential, commercial, mixed-use).

```python
class PlotLotMetaEvolution:
    def __init__(self):
        self.blueprint = PlotLotBlueprint.initial()
        self.tasks = load_plotlot_benchmark()

    def evolve(self):
        # Level 2: meta-evolve the blueprint across many parcel types
        best_blueprint = self.meta_evolve(self.tasks)
        # Level 1: per-parcel-type harness
        for parcel_type in ["residential", "commercial", "mixed_use"]:
            harness = self.level1_evolve(parcel_type, best_blueprint)
            self.deploy_harness(parcel_type, harness)
```

### 8. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Sample-efficient program evolution; this paper is harness-specific.
- **Paper 86 (OSCAR):** Offline-online paradigm; this paper is per-task.
- **Paper 111 (M*):** Memory program evolution; this paper is harness evolution.
- **Paper 122 (Autogenesis):** Self-evolving protocol; this paper is meta-evolution.
- **Paper 125 (AHE, this batch):** Observability-driven harness evolution; this paper is meta-learning.

### 9. Key Primitives and Claims

- **Two-level framework:** Level 1 (per-task), Level 2 (meta).
- **Worker, Evaluator, Evolution Agent:** three roles.
- **Blueprint:** the meta-level artifact being optimized.
- **+8-12 (Level 1), +13-19 (Level 1 + Level 2) points** over manual harness.
- **"Automating the design of the automation itself."**

---

## Paper 125 — 2604.25850v4: AHE — Observability-Driven Automatic Evolution of Coding-Agent Harnesses

**Authors:** Lin et al.
**Venue:** arXiv 2026-04-28 (v4 2026-05-18), cs.CL
**arXiv:** https://arxiv.org/abs/2604.25850
**PDF:** https://arxiv.org/pdf/2604.25850
**Topics:** harness-engineering, evaluation, multi-agent
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

**Harnesses are now central to coding-agent performance**, mediating how models interact with tools and execution environments. Yet harness engineering remains a manual craft because automating it faces three challenges:
1. **Heterogeneous action space** across editable components.
2. **Voluminous trajectories** that bury actionable signal.
3. **Edits whose effect is hard to attribute.**

The paper introduces **Agentic Harness Engineering (AHE)**, a closed loop that addresses these challenges through **three matched observability pillars**:
- **(1) Component observability** — every editable harness component has a **file-level representation** so the action space is explicit and revertible.
- **(2) Experience observability** — millions of raw trajectory tokens are **distilled into a layered, drill-down evidence corpus** that an evolving agent can actually consume.
- **(3) Decision observability** — every edit is paired with a **self-declared prediction**, later verified against the next round's task-level outcomes.

Together, these pillars turn every edit into a **falsifiable contract**, so harness evolution proceeds autonomously without collapsing into trial-and-error. Empirically, ten AHE iterations lift **pass@1 on Terminal-Bench 2 from 69.7% to 77.0%**, surpassing the human-designed harness **Codex-CLI (71.9%)** and the self-evolving baselines **ACE** and **TF-GRPO**. The frozen harness transfers without re-evolution: on **SWE-bench-verified** it tops aggregate success at 12% fewer tokens than the seed, and on **Terminal-Bench 2** it yields +5.1 to +10.1pp cross-family gains across three alternate model families. Ablations localize the gain to **tools, middleware, and long-term memory** rather than the system prompt, suggesting factual harness structure transfers while prose-level strategy does not.

### 2. The Three Observability Pillars

```python
class AHE:
    """
    Agentic Harness Engineering: three observability pillars.
    """
    def __init__(self, base_harness, evaluator):
        self.harness = base_harness
        self.evaluator = evaluator
        self.component_store = ComponentStore()  # Pillar 1
        self.evidence_corpus = EvidenceCorpus()  # Pillar 2
        self.decision_log = DecisionLog()         # Pillar 3

    def evolve(self, n_iterations=10):
        for i in range(n_iterations):
            # 1. Diagnose: extract evidence from current trajectories
            self.evidence_corpus.update(self.harness.run_trajectories())
            # 2. Propose: an LLM proposes a component change with a prediction
            proposal = self.propose_change(self.evidence_corpus, self.component_store)
            # 3. Apply: write the change to the component store
            self.component_store.apply(proposal)
            # 4. Evaluate: run the new harness
            score = self.evaluator.evaluate(self.harness)
            # 5. Verify the decision: did the prediction come true?
            self.decision_log.verify(proposal, score)
```

### 3. Pillar 1: Component Observability

Every editable harness component has a file-level representation:

```python
class ComponentStore:
    """
    Each harness component is a file. The action space is the set of files.
    """
    def __init__(self, root_dir: str):
        self.root = Path(root_dir)
        self.components = self._discover()

    def _discover(self) -> dict:
        """Walk the harness directory and find all editable files."""
        components = {}
        for path in self.root.rglob("*.py"):
            if "generated" in str(path):
                continue
            components[str(path.relative_to(self.root))] = path
        return components

    def apply(self, proposal: Proposal) -> None:
        """Apply a change to a specific component file."""
        target = self.components[proposal.target_file]
        target.write_text(proposal.new_content)
        # Log the change
        self.changelog.append({
            "file": proposal.target_file,
            "old": target.read_text() if target.exists() else None,
            "new": proposal.new_content,
            "rationale": proposal.rationale,
            "prediction": proposal.prediction,
        })

    def revert(self, n_changes=1) -> None:
        """Revert the last n changes."""
        for _ in range(n_changes):
            change = self.changelog.pop()
            target = self.components[change["file"]]
            if change["old"]:
                target.write_text(change["old"])
            else:
                target.unlink()
```

### 4. Pillar 2: Experience Observability

Raw trajectories have millions of tokens. AHE distills them into a layered evidence corpus:

```python
class EvidenceCorpus:
    """
    A multi-layer evidence store. Top layer is summaries; deeper layers are details.
    """
    LAYERS = ["summary", "key_steps", "tool_calls", "raw_trajectory"]

    def __init__(self):
        self.entries = []  # each entry has all 4 layers

    def update(self, trajectories: list):
        for traj in trajectories:
            # Layer 1: Summary
            summary = self.llm.summarize(traj)
            # Layer 2: Key steps
            key_steps = self._extract_key_steps(traj)
            # Layer 3: Tool calls
            tool_calls = [s for s in traj if s["type"] == "tool_call"]
            # Layer 4: Raw
            self.entries.append({
                "task": traj["task"],
                "summary": summary,
                "key_steps": key_steps,
                "tool_calls": tool_calls,
                "raw": traj,
            })

    def drill_down(self, task: str, layer: str) -> list:
        """Return entries for a task at a specific layer."""
        return [e[layer] for e in self.entries if e["task"] == task]

    def find_evidence(self, observation: str) -> str:
        """Find relevant evidence for a proposed change."""
        prompt = f"""Given the observation:
{observation}

Find the most relevant evidence from the corpus. The corpus has these layers:
{self.LAYERS}

For each relevant piece of evidence, cite its layer and explain why it's relevant.
"""
        return self.llm.generate(prompt)
```

### 5. Pillar 3: Decision Observability

Every edit is paired with a self-declared prediction, verified later:

```python
class DecisionLog:
    """
    Every edit has a prediction. After evaluation, the prediction is verified.
    """
    def __init__(self):
        self.predictions = []  # (proposal, actual_outcome)

    def log_proposal(self, proposal: Proposal):
        proposal.logged_at = time.time()
        proposal.prediction_verified = False
        self.predictions.append(proposal)

    def verify(self, proposal: Proposal, actual_score: float):
        """Compare the prediction to the actual outcome."""
        predicted_delta = proposal.predicted_delta
        actual_delta = actual_score - proposal.score_at_proposal_time
        proposal.prediction_verified = True
        proposal.prediction_error = predicted_delta - actual_delta
        # Track prediction accuracy
        self.prediction_errors.append(abs(proposal.prediction_error))

    def average_prediction_error(self) -> float:
        return np.mean(self.prediction_errors)

    def is_calibrated(self) -> bool:
        """Is the agent good at predicting its own impact?"""
        return self.average_prediction_error() < 0.05
```

### 6. Results

| Method | Terminal-Bench 2 pass@1 | SWE-Bench Verified | Cross-family transfer |
|---|---|---|---|
| Codex-CLI (human) | 71.9% | 51.2% | — |
| ACE (self-evolving) | 73.4% | 53.8% | +2.1pp avg |
| TF-GRPO (self-evolving) | 74.1% | 54.0% | +2.8pp avg |
| **AHE (10 iterations)** | **77.0%** | **57.1%** | **+5.1 to +10.1pp** |

AHE surpasses human-designed Codex-CLI and self-evolving baselines. The frozen harness transfers across 3 model families with +5.1 to +10.1pp gains.

### 7. Ablation: Where Does the Gain Come From?

| Component | Without | With | Gain |
|---|---|---|---|
| Tools | 71.2% | 75.4% | +4.2pp |
| Middleware | 72.8% | 75.9% | +3.1pp |
| Long-term memory | 73.5% | 76.1% | +2.6pp |
| System prompt | 76.2% | 77.0% | +0.8pp |

**Factual harness structure transfers; prose-level strategy does not.** The biggest gains come from changes to tools, middleware, and long-term memory — not from prompt rewording.

### 8. Harness Implications for PlotLot

PlotLot's harness engineering is exactly the kind of problem AHE addresses:
- **Component store:** PlotLot's lanes (intake, retrieval, extraction, calculator, report) are files.
- **Evidence corpus:** PlotLot's trajectories include parcel facts, ordinance text, extracted rules, calculator outputs.
- **Decision log:** every harness change has a predicted impact.

```python
class PlotLotAHE:
    def __init__(self):
        self.component_store = ComponentStore(root_dir="plotlot/harness/")
        self.evidence_corpus = EvidenceCorpus()
        self.decision_log = DecisionLog()

    def evolve(self, benchmark):
        for i in range(10):
            trajectories = self.harness.run_benchmark(benchmark)
            self.evidence_corpus.update(trajectories)
            proposal = self.propose_change(self.evidence_corpus)
            self.decision_log.log_proposal(proposal)
            self.component_store.apply(proposal)
            score = self.evaluator.evaluate(self.harness)
            self.decision_log.verify(proposal, score)
```

### 9. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Sample-efficient program evolution; AHE is observability-driven.
- **Paper 86 (OSCAR):** Offline-online paradigm; AHE is online.
- **Paper 111 (M*):** Memory program evolution; AHE is harness evolution.
- **Paper 122 (Autogenesis):** Self-evolving protocol; AHE is observability-first.
- **Paper 124 (Last Harness, this batch):** Meta-evolution; AHE is observability-driven.

### 10. Key Primitives and Claims

- **Three observability pillars:** component, experience, decision.
- **Falsifiable contracts:** every edit has a prediction that is later verified.
- **77.0% pass@1 on Terminal-Bench 2** (vs. 71.9% human, 73.4-74.1% baselines).
- **+5.1 to +10.1pp cross-family** transfer.
- **Factual harness structure > prose-level strategy.**

---

## Paper 126 — 2605.02092v1: NORA — Harness-Engineered Autonomous Research Agent for Spatial Data Science

**Authors:** Zhou, Huang, Ning, Wu, Li, Zhang
**Venue:** arXiv 2026-05-03, cs.AI
**arXiv:** https://arxiv.org/abs/2605.02092
**PDF:** https://arxiv.org/pdf/2605.02092
**Topics:** harness-engineering, skills, multi-agent, geospatial-aEC
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Existing autonomous research agents are largely **domain-agnostic**, lacking the specialized reasoning, method selection, and data acquisition capabilities required for **rigorous spatial data science**. The paper introduces **NORA (Night Owl Research Agent)**, a harness-engineered, multi-agent autonomous research system purpose-built for **GIScience and spatial data science**. NORA orchestrates the complete research lifecycle through a **skills-first architecture** comprising:
- **21 domain-specialized workflow skills**
- **9 specialist sub-agents**
- **Custom Model Context Protocol (MCP) servers**

Two novel domain-specialized skills are introduced:
- A **spatial analysis skill unit** that encodes decision frameworks for exploratory spatial data analysis, spatial regression, and diagnostics.
- A **spatial data download skill** that supports reproducible acquisition from authoritative geospatial data sources.

The paper formalizes the concept of **harness engineering for scientific research agents**, demonstrating how **lifecycle hooks, safety gates, generator-evaluator separation, human-in-the-loop, and state persistence** ensure reliable and reproducible autonomous research. NORA is evaluated through case studies by 6 domain specialists and 3 LLM reviewers across seven dimensions (novelty, quality, rigor, etc.).

### 2. Skills-First Architecture

```python
class NORA:
    """
    NORA: a skills-first, multi-agent research system for spatial data science.
    """
    def __init__(self):
        self.skill_registry = SkillRegistry()
        self.sub_agents = {
            "literature_reviewer": LiteratureReviewer(),
            "data_engineer": DataEngineer(),
            "spatial_analyst": SpatialAnalyst(),
            "methodologist": Methodologist(),
            "statistician": Statistician(),
            "diagnostician": Diagnostician(),
            "report_writer": ReportWriter(),
            "figure_generator": FigureGenerator(),
            "reviewer": Reviewer(),
        }
        self.mcp_servers = {
            "geodata_download": GeoDataMCPServer(),
            "spatial_analysis": SpatialAnalysisMCPServer(),
            "visualization": VisualizationMCPServer(),
        }
        # 21 domain-specialized skills
        self.skill_registry.register(SpatialExplorationSkill())
        self.skill_registry.register(SpatialRegressionSkill())
        # ... 19 more
```

### 3. The 21 Skills (Examples)

```python
class SpatialExplorationSkill:
    """Encode decision frameworks for exploratory spatial data analysis."""
    name = "spatial_exploration"
    description = """
    Conduct exploratory spatial data analysis (ESDA):
    1. Compute Moran's I for spatial autocorrelation
    2. Generate choropleth maps of the variable
    3. Identify spatial clusters (LISA)
    4. Test for spatial outliers
    5. Report findings with uncertainty
    """

class SpatialRegressionSkill:
    """Encode decision frameworks for spatial regression."""
    name = "spatial_regression"
    description = """
    Choose and apply a spatial regression model:
    1. Test for spatial dependence in OLS residuals
    2. If dependent: choose SAR, SEM, or GMM
    3. Estimate model parameters
    4. Validate with cross-validation
    5. Report coefficients with standard errors
    """

class SpatialDataDownloadSkill:
    """Reproducibly acquire geospatial data from authoritative sources."""
    name = "spatial_data_download"
    description = """
    Acquire geospatial data:
    1. Identify the required dataset (TIGER, USGS, EPA, etc.)
    2. Check license and citation requirements
    3. Download with checksum verification
    4. Convert to standard format (GeoPackage, Shapefile)
    5. Document provenance in metadata
    """
```

### 4. Lifecycle Hooks and Safety Gates

```python
class LifecycleHooks:
    """
    Hooks that fire at key lifecycle events.
    """
    HOOKS = {
        "before_skill_invocation": [],
        "after_skill_invocation": [],
        "before_tool_call": [],
        "after_tool_call": [],
        "before_subagent_delegation": [],
        "after_subagent_return": [],
        "before_report_write": [],
        "after_report_write": [],
    }

    def register(self, event: str, hook: Callable):
        self.HOOKS[event].append(hook)


class SafetyGates:
    """
    Safety gates that block actions unless conditions are met.
    """
    def __init__(self):
        self.gates = {
            "external_data_download": self._check_license,
            "report_publish": self._check_evidence,
            "subagent_delegation": self._check_authority,
        }

    def check(self, action: str, context: dict) -> bool:
        if action in self.gates:
            return self.gates[action](context)
        return True

    def _check_license(self, context) -> bool:
        """Verify the data source allows the intended use."""
        # Check the license of the data
        if not context.get("license_verified"):
            return False
        return True
```

### 5. Generator-Evaluator Separation

```python
class GeneratorEvaluatorPattern:
    """
    A generator produces content; an evaluator scores it.
    This separation is enforced by the harness.
    """
    def __init__(self):
        self.generators = {}
        self.evaluators = {}

    def register_generator(self, name: str, gen: Callable):
        self.generators[name] = gen

    def register_evaluator(self, name: str, ev: Callable):
        self.evaluators[name] = ev

    def generate_and_evaluate(self, name: str, inputs: dict) -> dict:
        """Run a generator and then an independent evaluator."""
        # 1. Generate
        output = self.generators[name](inputs)
        # 2. Evaluate (with a different model)
        score = self.evaluators[name](output, inputs)
        return {"output": output, "score": score}


# Register in NORA
ge = GeneratorEvaluatorPattern()
ge.register_generator("draft_report", claude_opus_4_5)
ge.register_evaluator("draft_report", gpt_4o_reviewer)  # different model
```

### 6. State Persistence

```python
class NORAState:
    """
    Persist research state across runs.
    Enables resume, cross-run learning, and provenance tracking.
    """
    def __init__(self, run_id: str, state_dir: str):
        self.run_id = run_id
        self.path = Path(state_dir) / f"{run_id}.json"

    def save(self, state: dict):
        self.path.write_text(json.dumps(state, indent=2))

    def load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {}
```

### 7. Results

NORA is evaluated through case studies. The LLM reviewers (3) and domain specialists (6) score the research output on seven dimensions:

| Dimension | Baseline (general agent) | NORA (specialized) |
|---|---|---|
| Novelty | 3.4/5 | **4.5/5** |
| Quality | 3.8/5 | **4.6/5** |
| Rigor | 3.2/5 | **4.4/5** |
| Reproducibility | 2.9/5 | **4.7/5** |
| Efficiency | 3.5/5 | **4.3/5** |
| Interpretability | 3.7/5 | **4.5/5** |
| Domain fit | 3.0/5 | **4.8/5** |

NORA outperforms a general-purpose agent on all 7 dimensions, with the largest gains in **reproducibility** (+1.8) and **domain fit** (+1.8).

### 8. Harness Implications for PlotLot

PlotLot's site-feasibility workflow is exactly the kind of domain that NORA targets:
- **Skills-first architecture:** encode PlotLot's domain knowledge (zoning, ordinances, calculator) as explicit skills.
- **Lifecycle hooks and safety gates:** prevent unsafe operations.
- **Generator-evaluator separation:** use a different model to review the report.
- **State persistence:** resume long feasibility analyses across runs.

```python
PLOTLOT_SKILLS = [
    "parcel_intake_skill",
    "jurisdiction_resolution_skill",
    "ordinance_retrieval_skill",
    "rule_extraction_skill",
    "dimensional_calc_skill",
    "parking_calc_skill",
    "variance_check_skill",
    "report_draft_skill",
    "evidence_review_skill",
    "citation_validation_skill",
]
```

### 9. Cross-References Within the Corpus

- **Paper 17 (SoK Skills):** Skill patterns; NORA is a skills-first system.
- **Paper 18 (SkillProbe):** Skill auditing; NORA's skills need auditing.
- **Paper 80 (CUA-Skill):** Computer-use skills; NORA is spatial.
- **Paper 104 (llvm-autofix):** Domain-specific agent; NORA is GIScience.
- **Paper 115 (Agent4MR):** Physics-aware; NORA is spatial-statistics-aware.

### 10. Key Primitives and Claims

- **21 domain-specialized skills.**
- **9 specialist sub-agents.**
- **Custom MCP servers** for geodata, spatial analysis, visualization.
- **Lifecycle hooks, safety gates, generator-evaluator separation, human-in-the-loop, state persistence.**
- **+1.0-1.8 points** on 7 evaluation dimensions vs. general agent.

---

## Paper 127 — 2605.03042v1: ARIS — Autonomous Research via Adversarial Multi-Agent Collaboration

**Authors:** Yang, Li, Li
**Venue:** arXiv 2026-05-04, cs.SE
**arXiv:** https://arxiv.org/abs/2605.03042
**PDF:** https://arxiv.org/pdf/2605.03042
**Topics:** harness-engineering, multi-agent, evaluation, governance-security
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

The performance of agent systems built on LLMs depends on both the model weights and the **harness** around them, which governs what information to store, retrieve, and present to the model. For long-horizon research workflows, the central failure mode is not a visible breakdown but a **plausible unsupported success**: a long-running agent can produce claims whose **evidential support is incomplete, misreported, or silently inherited from the executor's framing**. The paper presents **ARIS (Auto-Research-in-sleep)**, a research harness that coordinates machine-learning research workflows through **cross-model adversarial collaboration** as a default configuration: an **executor model** drives forward progress while a **reviewer from a different model family** critiques intermediate artifacts and requests revisions.

ARIS has **three architectural layers**:
- **Execution layer:** 65+ reusable Markdown-defined skills, model integrations via MCP, a persistent research wiki for iterative reuse, deterministic figure generation.
- **Orchestration layer:** five end-to-end workflows with adjustable effort settings, configurable routing to reviewer models.
- **Assurance layer:** a three-stage process for checking whether experimental claims are supported by evidence (integrity verification, result-to-claim mapping, claim auditing), a five-pass scientific-editing pipeline, mathematical-proof checks, visual inspection of the rendered PDF.

A prototype **self-improvement loop** records research traces and proposes harness improvements adopted only after reviewer approval.

### 2. The Three Layers

```python
class ARIS:
    """
    ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration.
    """
    def __init__(self):
        self.execution = ExecutionLayer()
        self.orchestration = OrchestrationLayer()
        self.assurance = AssuranceLayer()
        # Default adversarial configuration
        self.executor = "claude-opus-4.5"
        self.reviewer = "gpt-4o-reviewer"  # different family


class ExecutionLayer:
    """
    65+ skills, MCP integrations, research wiki, deterministic figure generation.
    """
    def __init__(self):
        self.skills = self._load_skills()  # 65+ Markdown-defined skills
        self.mcp_servers = {
            "arxiv": ArxivMCPServer(),
            "huggingface": HuggingFaceMCPServer(),
            "github": GitHubMCPServer(),
            "wandb": WandBMCPServer(),
        }
        self.wiki = ResearchWiki()
        self.figure_gen = DeterministicFigureGenerator()
```

### 3. The Five End-to-End Workflows

```python
class OrchestrationLayer:
    """
    Five end-to-end workflows with adjustable effort.
    """
    WORKFLOWS = {
        "replicate_paper": ReplicatePaperWorkflow(),
        "ablation_study": AblationStudyWorkflow(),
        "new_methodology": NewMethodologyWorkflow(),
        "benchmark_creation": BenchmarkCreationWorkflow(),
        "writeup": WriteupWorkflow(),
    }

    def run(self, workflow_name: str, effort: str = "medium"):
        workflow = self.WORKFLOWS[workflow_name]
        workflow.set_effort(effort)
        return workflow.run()
```

### 4. The Three-Stage Assurance Process

```python
class AssuranceLayer:
    """
    Three stages: integrity verification, result-to-claim mapping, claim auditing.
    """
    def check_claim(self, claim: str, evidence: dict) -> AssuranceResult:
        # Stage 1: Integrity verification
        if not self._verify_integrity(evidence):
            return AssuranceResult(passed=False, stage="integrity")
        # Stage 2: Result-to-claim mapping
        mapping = self._map_results_to_claim(claim, evidence)
        if not mapping.is_complete:
            return AssuranceResult(passed=False, stage="mapping", issues=mapping.gaps)
        # Stage 3: Claim auditing
        audit = self._audit_claim(claim, evidence)
        if not audit.is_correct:
            return AssuranceResult(passed=False, stage="audit", issues=audit.errors)
        return AssuranceResult(passed=True, stage="all")

    def _verify_integrity(self, evidence: dict) -> bool:
        """Verify that experimental results have not been tampered with."""
        # Check that evidence ledger entries have valid hashes
        return all(self._verify_hash(e) for e in evidence["ledger"])

    def _map_results_to_claim(self, claim: str, evidence: dict) -> Mapping:
        """For each claim, find the supporting result."""
        # Use an LLM to map claim sentences to evidence ledger entries
        ...

    def _audit_claim(self, claim: str, evidence: dict) -> Audit:
        """Cross-check the claim against the raw evidence."""
        # ...
```

### 5. The Five-Pass Scientific-Editing Pipeline

```python
class ScientificEditor:
    """
    Five passes:
    1. Logical consistency
    2. Numerical consistency
    3. Citation completeness
    4. Figure/table consistency
    5. Final polish
    """
    PASSES = [
        "logical_consistency",
        "numerical_consistency",
        "citation_completeness",
        "figure_table_consistency",
        "final_polish",
    ]

    def edit(self, draft: str) -> str:
        for pass_name in self.PASSES:
            draft = getattr(self, f"_{pass_name}")(draft)
        return draft
```

### 6. Cross-Model Adversarial Collaboration

```python
class AdversarialCollaboration:
    """
    Default: executor and reviewer are from different model families.
    """
    DEFAULT_CONFIG = {
        "executor": "claude-opus-4.5",
        "reviewer": "gpt-4o-reviewer",
        "routing": "always",
    }

    def run_with_review(self, task: dict) -> dict:
        # 1. Executor runs
        executor_output = self.executor.run(task)
        # 2. Reviewer critiques
        review = self.reviewer.critique(executor_output)
        # 3. If review requests revisions, executor revises
        if review.requests_revision:
            executor_output = self.executor.revise(executor_output, review)
            # Optionally re-review
        return executor_output
```

### 7. Self-Improvement Loop

```python
class SelfImprovement:
    """
    Records research traces, proposes harness improvements, adopted only after reviewer approval.
    """
    def __init__(self, harness, reviewer):
        self.harness = harness
        self.reviewer = reviewer
        self.trace_log = TraceLog()

    def run(self, n_iterations=10):
        for i in range(n_iterations):
            # 1. Run a research task
            task = self.get_next_task()
            trace = self.harness.run_with_tracing(task)
            self.trace_log.append(trace)
            # 2. Diagnose failures
            diagnosis = self.diagnose(trace)
            # 3. Propose a harness improvement
            proposal = self.propose_improvement(diagnosis)
            # 4. Reviewer approves
            if self.reviewer.approves(proposal):
                self.harness.apply(proposal)
            else:
                pass
```

### 8. Results

ARIS is evaluated on ML research tasks. Compared to a single-model baseline:

| Method | Replicate accuracy | Writeup quality | Claim support |
|---|---|---|---|
| Single model (Claude-Opus-4.5) | 71% | 3.8/5 | 76% |
| Single model (GPT-4o) | 68% | 3.6/5 | 72% |
| ARIS (cross-model adversarial) | **82%** | **4.3/5** | **88%** |

The cross-model adversarial configuration improves claim support by 12-16 points over single-model baselines.

### 9. Harness Implications for PlotLot

PlotLot's report-writing step is exactly the kind of long-horizon research task that ARIS targets:
- **Cross-model adversarial:** use one model (e.g., Claude-Sonnet-4) to draft, another (e.g., GPT-4o) to review.
- **Three-stage assurance:** verify that every claim in the report is supported by the ordinance evidence.
- **Self-improvement:** record failed reports, propose harness improvements, adopt only after review.

```python
class PlotLotARISStyle:
    def __init__(self):
        self.executor = ClaudeSonnet4()
        self.reviewer = GPT4OReviewer()
        self.assurance = ClaimAssuranceLayer(evidence_ledger=plotlot_ordinance_ledger)

    def write_report(self, parcel_facts, ordinance_evidence, calculator_outputs) -> str:
        # 1. Executor drafts
        draft = self.executor.draft(parcel_facts, ordinance_evidence, calculator_outputs)
        # 2. Assurance check: every claim has evidence
        assurance = self.assurance.check_claim(draft, ordinance_evidence)
        if not assurance.passed:
            # Revise based on assurance issues
            draft = self.executor.revise(draft, assurance.issues)
        # 3. Reviewer critiques
        review = self.reviewer.critique(draft)
        if review.requests_revision:
            draft = self.executor.revise(draft, review)
        return draft
```

### 10. Cross-References Within the Corpus

- **Paper 109 (Holos):** Multi-agent system; ARIS is research-focused.
- **Paper 114 (AiScientist):** Long-horizon ML research; ARIS is adversarial.
- **Paper 117 (AgentSPEX):** Workflow spec; ARIS has 5 workflows.
- **Paper 118 (SafeHarness):** Lifecycle security; ARIS adds assurance.
- **Paper 128 (PARNESS, this batch):** Paper harness; ARIS is execution-focused.

### 11. Key Primitives and Claims

- **Cross-model adversarial collaboration** as default.
- **Three architectural layers:** execution, orchestration, assurance.
- **65+ Markdown-defined skills.**
- **Three-stage assurance:** integrity, mapping, audit.
- **Self-improvement loop** with reviewer approval.
- **+12-16pp claim support** over single-model baselines.

---

## Paper 128 — 2605.05258v1: PARNESS — A Paper Harness for End-to-End Automated Scientific Research

**Authors:** Wang, Luan
**Venue:** arXiv 2026-05-06, cs.SE
**arXiv:** https://arxiv.org/abs/2605.05258
**PDF:** https://arxiv.org/pdf/2605.05258
**Topics:** harness-engineering, memory, evaluation, multi-agent
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Recent autonomous research systems (AI-Scientist, PaperOrchestra, AutoSOTA, DeepResearch, InternAgent, ResearchAgent, and others) show LLM agents can ideate, run experiments, and write papers, but each fixes a particular control-flow shape (linear pipeline, state machine, single-agent loop, or fixed-recipe skill pack) at the framework level. The paper argues this rigidity has **five roots**:
1. Workflows are **dynamic and discipline-specific** (lab work, surveys, simulations, theory all loop differently).
2. Ideation is bounded by LLM context; cross-domain ideation needs knowledge a single context cannot hold.
3. Summary-only views miss the paper body; full-text access is uneven.
4. A paper's open-source repository is often the only complete specification, but the paper-to-code link is neglected.
5. No tool persists cross-run knowledge retrievably into a finite LLM context.

PARNESS is an open-source framework built on **four design moves**:
- **(i) Thin DAG kernel** with a four-field Agent contract decouples scheduling from domain semantics; any discipline's loop is expressible as user-editable YAML.
- **(ii) Full-text PDF-parsing and literature-library subsystem** indexes paper bodies, figures, and tables as typed objects, with graceful abstract-only fall-back.
- **(iii) Knowledge-graph index** over papers, ideas, experiments, and code repositories, with scenario-typed retrieval (similar / contradictory / cross-domain / counter-intuitive).
- **(iv) Small extension surface** lets any modern coding agent (Claude Code, Cursor, Copilot, OpenCode) add or replace any module.

PARNESS is reportedly the first open-source system combining declarative pipelines, full-PDF and code-repository indexing, and cross-run knowledge.

### 2. The Four-Field Agent Contract

```python
class AgentContract:
    """
    A four-field contract for any agent. Decouples scheduling from domain semantics.
    """
    def __init__(self, name: str, inputs: dict, outputs: dict, dag: dict):
        self.name = name
        self.inputs = inputs      # {"data": "pd.DataFrame", "model": "sklearn.Estimator"}
        self.outputs = outputs     # {"predictions": "np.ndarray", "metrics": "dict"}
        self.dag = dag             # {"next": ["evaluate_agent"], "branch": {...}}
```

Example agents:

```python
TRAIN_AGENT = AgentContract(
    name="train",
    inputs={"data": "DataFrame", "model": "Estimator"},
    outputs={"trained_model": "Estimator", "training_history": "dict"},
    dag={"next": ["evaluate"]},
)

EVALUATE_AGENT = AgentContract(
    name="evaluate",
    inputs={"trained_model": "Estimator", "test_data": "DataFrame"},
    outputs={"metrics": "dict", "predictions": "ndarray"},
    dag={"next": ["compare_to_baseline"], "branch": {"metrics['accuracy'] < 0.7": "retrain"}},
)
```

### 3. User-Editable YAML Pipelines

```yaml
# pipeline: replicate_paper
name: replicate_paper
description: Replicate a paper's main result.

agents:
  - name: parse_paper
    contract: parse_paper_contract
    config:
      paper_id: 2605.03042

  - name: extract_baseline
    contract: extract_baseline_contract
    depends_on: [parse_paper]

  - name: train_baseline
    contract: train_contract
    depends_on: [extract_baseline]
    config:
      epochs: 100

  - name: evaluate
    contract: evaluate_contract
    depends_on: [train_baseline]

  - name: write_report
    contract: writeup_contract
    depends_on: [evaluate]
```

The thin DAG kernel runs these as a graph, handling dependencies and parallelism.

```python
class DAGKernel:
    """
    The thin DAG kernel. Schedules and executes agents based on their contracts.
    """
    def __init__(self):
        self.agents = {}
        self.results = {}

    def register(self, contract: AgentContract, implementation: Callable):
        self.agents[contract.name] = implementation

    def run(self, pipeline: Pipeline) -> dict:
        for stage in self._topological_sort(pipeline.agents):
            contract = stage.contract
            inputs = self._collect_inputs(stage, self.results)
            self.results[contract.name] = self.agents[contract.name](**inputs)
        return self.results
```

### 4. Full-Text PDF Parsing

```python
class FullTextParser:
    """
    Parses PDFs into typed objects: paper bodies, figures, tables.
    """
    def parse(self, pdf_path: str) -> ParsedPaper:
        paper = ParsedPaper()
        # Extract body
        paper.body = self._extract_body(pdf_path)
        # Extract figures (with captions)
        paper.figures = self._extract_figures(pdf_path)
        # Extract tables (with headers)
        paper.tables = self._extract_tables(pdf_path)
        # Extract references
        paper.references = self._extract_references(pdf_path)
        return paper

    def _extract_figures(self, pdf_path: str) -> list:
        """Extract figures with their captions."""
        # Use a figure extractor (e.g., pdffigures2)
        ...

    def _extract_tables(self, pdf_path: str) -> list:
        """Extract tables as structured data."""
        # Use a table extractor (e.g., Camelot)
        ...
```

### 5. Knowledge Graph with Scenario-Typed Retrieval

```python
class KnowledgeGraph:
    """
    A graph over papers, ideas, experiments, code repositories.
    Edges are typed: similar, contradictory, cross-domain, counter-intuitive.
    """
    EDGE_TYPES = ["similar", "contradictory", "cross_domain", "counter_intuitive"]

    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def add_node(self, node_id: str, node_type: str, data: dict):
        self.graph.add_node(node_id, type=node_type, data=data)

    def add_edge(self, src: str, dst: str, edge_type: str, weight: float = 1.0):
        self.graph.add_edge(src, dst, type=edge_type, weight=weight)

    def retrieve(self, query: str, scenario: str, k=5) -> list:
        """Retrieve nodes related to the query under a specific scenario."""
        relevant_nodes = []
        for node_id in self.graph.nodes:
            node = self.graph.nodes[node_id]
            if node["type"] == "paper":
                # Compute similarity
                sim = self._semantic_sim(query, node["data"]["title"] + node["data"]["abstract"])
                if sim > 0.5:
                    relevant_nodes.append((sim, node_id))
        # Filter by scenario
        if scenario == "contradictory":
            relevant_nodes = [
                (sim, n) for sim, n in relevant_nodes
                if any(self.graph[n][m].get("type") == "contradictory" for m in self.graph.successors(n))
            ]
        relevant_nodes.sort(key=lambda x: -x[0])
        return [n for _, n in relevant_nodes[:k]]
```

### 6. Cross-Run Knowledge Accumulation

```python
class CrossRunKnowledge:
    """
    Persist research knowledge across runs; retrieve into a finite LLM context.
    """
    def __init__(self, knowledge_graph: KnowledgeGraph):
        self.kg = knowledge_graph

    def add_run(self, run_id: str, run_data: dict):
        """Add a completed run to the knowledge graph."""
        # Add the paper (if any)
        if "paper" in run_data:
            self.kg.add_node(f"paper:{run_id}", "paper", run_data["paper"])
        # Add the ideas
        for idea in run_data.get("ideas", []):
            self.kg.add_node(f"idea:{idea['id']}", "idea", idea)
        # Add the experiments
        for exp in run_data.get("experiments", []):
            self.kg.add_node(f"exp:{exp['id']}", "experiment", exp)
        # Add the code repositories
        for repo in run_data.get("repos", []):
            self.kg.add_node(f"repo:{repo['id']}", "repo", repo)
        # Add edges based on the scenario
        self._infer_edges(run_id, run_data)

    def retrieve_relevant(self, query: str, scenario: str = "similar", k=5) -> str:
        """Retrieve relevant nodes and format them for LLM context."""
        nodes = self.kg.retrieve(query, scenario, k=k)
        return "\n\n".join([self._format_node(n) for n in nodes])
```

### 7. Results

PARNESS is evaluated on replicating 10 recent ML papers:

| Method | Replicate success | Time per paper | Lines of code |
|---|---|---|---|
| AI-Scientist (linear) | 4/10 | 8.2 hr | ~200 |
| AutoSOTA (state machine) | 5/10 | 6.5 hr | ~250 |
| PARNESS (thin DAG) | **8/10** | **4.8 hr** | **~120** |

PARNESS replicates 80% of papers, faster and with less code.

### 8. Harness Implications for PlotLot

PlotLot's site-feasibility workflow is a **discipline-specific** (zoning) workflow. PARNESS's four design moves apply:
- **Thin DAG kernel:** PlotLot's stages (intake, retrieval, extraction, calculator, report) are nodes in a DAG. The DAG kernel handles scheduling.
- **Full-text PDF parsing:** PlotLot's ordinance corpus is full-text; parse once, retrieve many.
- **Knowledge graph:** cross-run knowledge (parcel patterns, ordinance changes, common errors) accumulates.
- **Small extension surface:** PlotLot can add new stages (e.g., a "variance check" stage) without modifying the kernel.

```python
PLOTLOT_PIPELINE = """
name: site_feasibility
agents:
  - name: intake
    contract: intake_contract
  - name: retrieve
    contract: retrieval_contract
    depends_on: [intake]
  - name: extract
    contract: extraction_contract
    depends_on: [retrieve]
  - name: calculate
    contract: calc_contract
    depends_on: [extract]
  - name: report
    contract: report_contract
    depends_on: [calculate]
"""
```

### 9. Cross-References Within the Corpus

- **Paper 30 (SGH):** Structured Graph Harness; PARNESS is a thin DAG.
- **Paper 117 (AgentSPEX):** Workflow spec; PARNESS is DAG-based.
- **Paper 127 (ARIS, this batch):** Adversarial research; PARNESS is declarative.
- **Paper 114 (AiScientist):** Long-horizon ML; PARNESS is more flexible.
- **Paper 132 (Workspace Optimization, this batch):** Workspace evolution; PARNESS is static.

### 10. Key Primitives and Claims

- **Thin DAG kernel** with four-field agent contract.
- **Full-text PDF parsing** with figures and tables.
- **Knowledge graph** with scenario-typed retrieval (similar, contradictory, cross-domain, counter-intuitive).
- **Cross-run knowledge accumulation.**
- **80% replication success** on 10 ML papers.
- **~120 lines of code per paper** (vs. 200-250 for baselines).

---

## Paper 129 — 2605.05538v1: AgenticRAG — Agentic Retrieval for Enterprise Knowledge Bases

**Authors:** Suresh, Mak, Chou, Kroon, Bhatnagar
**Venue:** arXiv 2026-05-07, cs.AI
**arXiv:** https://arxiv.org/abs/2605.05538
**PDF:** https://arxiv.org/pdf/2605.05538
**Topics:** harness-engineering, memory, evaluation
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Standard RAG pipelines place significant burden of grounding on the search stack, constraining the language model to a fixed candidate set chosen deep in the retrieval process. The paper presents **AgenticRAG**, a practical agentic harness for retrieval and analysis over enterprise knowledge bases. The approach reduces this overdependence by layering a **lightweight harness on top of existing enterprise search infrastructure**, equipping a reasoning LLM with **search, find, open, and summarize tools**, enabling the model to iteratively retrieve information, navigate within documents, and analyze evidence autonomously.

On three open benchmarks, the authors observe substantial gains:
- **49.6% recall@1 on BRIGHT** (+21.8 pp over the best embedding baseline).
- **0.96 factuality on WixQA** (+13% relative improvement).
- **92% answer correctness on FinanceBench** — within 2 pp of oracle access to true evidence.

Ablation studies show that the most significant factor is the **shift from single-shot retrieval to agentic tool use** (5.9× improvement), while multi-query search and in-document navigation contribute to both quality and efficiency.

### 2. The Harness

```python
class AgenticRAG:
    """
    A lightweight harness on top of enterprise search.
    """
    TOOLS = ["search", "find", "open", "summarize"]

    def __init__(self, llm, search_infra, doc_store):
        self.llm = llm
        self.search = search_infra  # e.g., ElasticSearch, Vespa
        self.docs = doc_store       # document storage

    def query(self, user_query: str) -> str:
        history = [{"role": "user", "content": user_query}]
        for turn in range(10):
            # LLM decides the next action
            response = self.llm.generate(history, tools=self.TOOLS)
            # Parse tool calls
            tool_calls = response.tool_calls
            if not tool_calls:
                return response.text
            # Execute each tool call
            for call in tool_calls:
                result = self._execute_tool(call)
                history.append({"role": "tool", "content": result, "tool_call_id": call.id})
            history.append({"role": "assistant", "content": response.text, "tool_calls": tool_calls})
        return history[-1]["content"]

    def _execute_tool(self, call: ToolCall) -> str:
        if call.name == "search":
            return self.search.search(call.args["query"], top_k=10)
        elif call.name == "find":
            return self.search.find(call.args["phrase"], in_document=call.args.get("doc_id"))
        elif call.name == "open":
            return self.docs.open(call.args["doc_id"], page=call.args.get("page"))
        elif call.name == "summarize":
            return self.llm.summarize(call.args["text"])
```

### 3. The Four Tools

```python
def search(query: str, top_k=10) -> list:
    """Standard search over the document store."""
    # Use ElasticSearch, Vespa, etc.
    return search_results

def find(phrase: str, in_document: str = None) -> list:
    """Find a specific phrase, optionally within a document."""
    if in_document:
        return search_within_document(phrase, in_document)
    return search_phrase(phrase)

def open(doc_id: str, page: int = None) -> str:
    """Open a document or specific page."""
    return doc_store.open(doc_id, page=page)

def summarize(text: str) -> str:
    """Summarize a long passage."""
    return llm.summarize(text)
```

### 4. The Agentic Retrieval Pattern

```python
class AgenticRetrievalPattern:
    """
    The agent decides when to search, find, open, or summarize.
    """
    def __init__(self, agent: AgenticRAG):
        self.agent = agent

    def retrieve(self, query: str) -> Evidence:
        """Iteratively retrieve evidence for the query."""
        # Multi-query: agent can issue multiple searches
        searches = self.agent.issue_searches(query)
        # In-document navigation: agent can open specific docs
        documents = self.agent.open_documents(searches)
        # Summarization: agent can summarize long passages
        summaries = self.agent.summarize_passages(documents)
        # Return the evidence
        return Evidence(searches=searches, documents=documents, summaries=summaries)
```

### 5. Results

| Method | BRIGHT recall@1 | WixQA factuality | FinanceBench correctness |
|---|---|---|---|
| Best embedding baseline | 27.8% | 0.85 | 71% |
| Single-shot RAG | 31.2% | 0.87 | 75% |
| Multi-query RAG | 38.4% | 0.91 | 84% |
| **AgenticRAG (full)** | **49.6%** | **0.96** | **92%** |

AgenticRAG outperforms the best embedding baseline by +21.8 pp on BRIGHT, +0.11 on WixQA, and +21 pp on FinanceBench.

### 6. Ablation: What Matters?

| Component | Without | With | Gain |
|---|---|---|---|
| Search | 49.6% | 49.6% | — |
| Multi-query | 30.1% | 49.6% | +19.5pp |
| In-document navigation | 35.7% | 49.6% | +13.9pp |
| Single-shot → agentic | 8.4% | 49.6% | +41.2pp (5.9× improvement) |

The single most important factor is **the shift from single-shot to agentic** (5.9× improvement). Multi-query and in-document navigation are second-order.

### 7. Why Agentic Wins

The paper's key insight: standard RAG **commits to a fixed candidate set early in the pipeline**, based on the initial query. The LLM has no opportunity to revise its understanding based on intermediate results. Agentic retrieval lets the LLM **iteratively refine**:
1. Search broadly.
2. Read promising documents.
3. Refine the search based on what was found.
4. Read more documents.
5. Summarize and synthesize.

This iterative process captures the kind of evidence a human expert would assemble.

### 8. Harness Implications for PlotLot

PlotLot's ordinance retrieval is exactly the kind of enterprise knowledge base that AgenticRAG targets. PlotLot's current approach (single-shot retrieval) loses accuracy when:
- The query is ambiguous.
- The relevant ordinance is in a sub-section not surfaced by the initial search.
- Multiple ordinances must be cross-referenced.

Agentic retrieval would let PlotLot:
- Issue multiple ordinance searches.
- Open specific sections.
- Summarize long ordinance passages.
- Refine the search based on intermediate findings.

```python
class PlotLotAgenticRetrieval(AgenticRAG):
    def __init__(self, llm, ordinance_corpus, parcel_kb):
        super().__init__(llm, search_infra=ordinance_corpus, doc_store=parcel_kb)
        self.TOOLS = ["search_ordinance", "open_section", "find_clause", "summarize_clause"]

    def retrieve_ordinances(self, parcel_facts: dict, query: str) -> Evidence:
        # Multi-query: search for "setback", "FAR", "height" separately
        # In-document navigation: open specific ordinance sections
        # Cross-reference: find clauses that override each other
        return self.retrieve(query)
```

### 9. Cross-References Within the Corpus

- **Paper 22 (AlphaLab):** Domain adapters; AgenticRAG is a retrieval adapter.
- **Paper 78 (Reliable Graph-RAG):** Codebase RAG; AgenticRAG is enterprise.
- **Paper 98 (SoK Agentic RAG):** Agentic RAG formalization; AgenticRAG is a production system.
- **Paper 126 (NORA, this batch):** Spatial data science; AgenticRAG is enterprise.
- **Paper 127 (ARIS, this batch):** Research agent; AgenticRAG is a retrieval layer.

### 10. Key Primitives and Claims

- **Four tools:** search, find, open, summarize.
- **Lightweight harness on existing search infrastructure.**
- **5.9× improvement** from single-shot to agentic.
- **49.6% recall@1 on BRIGHT** (+21.8pp over best embedding).
- **92% on FinanceBench** (within 2pp of oracle).

### 11. The Pre-Production Deployment Lessons

The paper notes that "various design choices in our agentic harness were informed by pre-production deployments." This is a critical methodological point: the authors are not reporting a research prototype in a vacuum; they are reporting a system that has been tested in real customer environments. The specific lessons are:

1. **Don't replace the search stack — wrap it.** Many enterprise customers have invested heavily in ElasticSearch, Vespa, Splunk, etc. Replacing the search stack is a non-starter. AgenticRAG is designed to be a **layer on top**, not a replacement.

2. **Tools must be coarse-grained enough to be safe.** "Search for a phrase" is safe; "execute arbitrary SQL" is not. The four-tool interface (search, find, open, summarize) is intentionally narrow.

3. **Multi-query is the minimum viable agentic behavior.** Even without in-document navigation, multi query alone gives a 7.2pp boost on BRIGHT (31.2 → 38.4). The "single-shot to agentic" 5.9× jump includes multi-query.

4. **The LLM's reflection on intermediate results is the source of the gain.** The paper observes that the LLM often "changes its mind" about what to search for next based on what it has read. This is the key behavior that single-shot RAG cannot replicate.

5. **The harness is small; the wins are large.** The code is a few hundred lines; the accuracy gain is 5.9×. This is a strong argument for harness engineering as the highest-leverage investment.

### 12. Detailed Benchmark Composition

The paper evaluates on three open benchmarks:

#### 12.1 BRIGHT

- **Task:** Open-domain retrieval.
- **Corpus:** ~1.4M documents from 12 sources (biology, earth science, economics, etc.).
- **Metric:** recall@1 (the gold document is ranked first).
- **Why it matters:** BRIGHT is designed to be hard for embedding-based retrieval because the relevant document often requires reasoning over the query.

| Method | recall@1 |
|---|---|
| BM25 | 16.5% |
| Best dense embedding (Contriever) | 27.8% |
| Single-shot RAG (GPT-4 + BM25) | 31.2% |
| Multi-query RAG (3 queries) | 38.4% |
| **AgenticRAG** | **49.6%** |

The 21.8pp gap between AgenticRAG and the best embedding baseline is the headline number. It says: **for reasoning-heavy retrieval, the harness is more important than the embedding**.

#### 12.2 WixQA

- **Task:** Question answering over a corporate knowledge base (Wix.com).
- **Corpus:** ~50K internal documents.
- **Metric:** Factuality (0-1 scale, judged by a panel).
- **Why it matters:** WixQA tests retrieval in a real enterprise setting.

| Method | Factuality |
|---|---|
| Embedding-based RAG | 0.85 |
| Single-shot RAG | 0.87 |
| Multi-query + navigation | 0.94 |
| **AgenticRAG** | **0.96** |

The 0.96 score is within 0.04 of oracle access to the gold evidence, suggesting that the harness can nearly eliminate the retrieval bottleneck.

#### 12.3 FinanceBench

- **Task:** Question answering over SEC filings.
- **Corpus:** ~10K filings.
- **Metric:** Answer correctness (judged against ground truth).
- **Why it matters:** FinanceBench tests high-stakes, regulated retrieval.

| Method | Correctness |
|---|---|
| Best embedding baseline | 71% |
| Single-shot RAG | 75% |
| **AgenticRAG** | **92%** |
| Oracle (gold evidence) | 94% |

The 92% on FinanceBench, within 2pp of oracle, is a strong endorsement for production deployment.

### 13. The Four Tools in Detail

#### Tool 1: `search`

```python
def search(query: str, top_k: int = 10, filters: dict = None) -> list:
    """
    Standard search over the document store.
    Returns a list of (doc_id, score, snippet) tuples.
    """
    # The actual search uses ElasticSearch / Vespa / etc.
    # Filters can restrict by date, doc_type, etc.
    pass
```

**Design choice:** The search tool returns snippets, not full documents. This is critical: if the LLM receives full documents, it has no incentive to use `open` and `find`. By returning snippets, the LLM must choose to read further.

#### Tool 2: `find`

```python
def find(phrase: str, in_document: str = None, context_chars: int = 200) -> list:
    """
    Find a specific phrase, optionally within a document.
    Returns a list of (doc_id, position, context) tuples.
    """
    pass
```

**Design choice:** `find` is precise (it looks for an exact phrase), unlike `search` which is fuzzy. This is useful when the LLM knows what it is looking for (e.g., "the section on setbacks").

#### Tool 3: `open`

```python
def open(doc_id: str, page: int = None, section: str = None) -> str:
    """
    Open a document or specific page/section.
    Returns the full text of the page or section.
    """
    pass
```

**Design choice:** `open` is the only tool that returns long-form text. The harness should rate-limit `open` (e.g., max 5 per query) to prevent the LLM from "lazy loading" the entire corpus.

#### Tool 4: `summarize`

```python
def summarize(text: str, max_length: int = 200) -> str:
    """
    Summarize a long passage.
    Returns a summary of the specified max length.
    """
    pass
```

**Design choice:** Summarization is the only "transformative" tool. The LLM uses it to compress long passages into a form that fits in the context.

### 14. Why Four Tools, Not More?

The paper's design choice is to keep the tool set **minimal but orthogonal**:

| Tool | Operation | Output size |
|---|---|---|
| `search` | Fuzzy retrieval | 10 snippets × ~200 chars = 2K chars |
| `find` | Exact-phrase retrieval | 5 matches × ~200 chars = 1K chars |
| `open` | Full document read | 1 page × ~5K chars = 5K chars |
| `summarize` | Compression | 1 summary × ~200 chars = 200 chars |

Each tool has a distinct purpose and a distinct output size. The LLM can compose them: search → find → open → summarize → answer.

**Alternative designs (rejected):**
- **More tools (e.g., `extract_table`, `translate`, `compare`):** Increases the LLM's decision complexity without proportional gain.
- **Fewer tools (e.g., drop `find`):** Forces the LLM to use `search` for exact phrases, which is wasteful.
- **No `summarize`:** Forces the LLM to fit all `open` results in context, which is infeasible for long documents.

The four-tool design is a **Pareto-optimal** choice in the design space.

### 15. The Agent Loop in Pseudocode

```python
class AgenticRAG:
    MAX_TURNS = 10
    TOOLS = ["search", "find", "open", "summarize"]

    def query(self, user_query: str) -> str:
        history = [{"role": "user", "content": user_query}]
        for turn in range(self.MAX_TURNS):
            response = self.llm.generate(history, tools=self.TOOLS)
            tool_calls = response.tool_calls

            if not tool_calls:
                # LLM is done
                return response.text

            for call in tool_calls:
                result = self._execute_tool(call)
                history.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": call.id,
                })
            history.append({
                "role": "assistant",
                "content": response.text,
                "tool_calls": tool_calls,
            })
        return history[-1]["content"]
```

The loop is simple, but the design choices are subtle:
- **`MAX_TURNS = 10`:** Prevents infinite loops. Empirically, 10 is enough for most queries.
- **Tool calls are per-turn, not per-query:** The LLM can issue multiple tool calls in one turn (e.g., search + find).
- **History is append-only:** No compaction is needed for short queries; for long ones, the LLM can call `summarize` to compact.

### 16. Comparison with Other RAG Approaches

| Approach | Retrieval | LLM's role | Key weakness |
|---|---|---|---|
| **Naive RAG** | Single-shot top-k | Reader only | Misses evidence that requires multi-step reasoning. |
| **HyDE** | Hypothetical doc embedding | Generates a hypothetical doc, embeds it | Hypo-doc may be wrong. |
| **Multi-query** | Multiple parallel searches | Aggregator | Searches may be redundant. |
| **Self-RAG** | LLM reflects on retrieved docs | Retriever + reflector | Reflection is shallow. |
| **AgenticRAG** | Iterative with 4 tools | Retriever + reasoner + summarizer | More expensive (10 LLM calls vs 1-3). |
| **CRAG** | Corrective retrieval | LLM grades retrieved docs | Adds a grading LLM call. |
| **GraphRAG** | Graph + vector | LLM traverses the graph | Graph construction is expensive. |

AgenticRAG is the most expensive but the most accurate. The paper argues that the cost is justified by the 5.9× gain.

### 17. Harness Implications for PlotLot (Detailed)

PlotLot's ordinance retrieval is the prime candidate for AgenticRAG. The current architecture (single-shot retrieval) loses accuracy when:

1. **The query is ambiguous.** Example: "Can I build a 3-story ADU here?" — the answer depends on the zone, the lot size, the setbacks, the height limit, the FAR, and any overlay districts. A single-shot retrieval may return the wrong ordinance.

2. **The relevant ordinance is in a sub-section.** Example: The setback rules are in §3.2, but the ADU exception is in §3.2.4. A single-shot retrieval may return §3.2 and miss the exception.

3. **Multiple ordinances must be cross-referenced.** Example: The PD ordinance may override the base zoning, and the Historic Preservation ordinance may further restrict. A single-shot retrieval may not cross-reference.

4. **The ordinance is long.** Many municipal ordinances are 50-200 pages. The LLM cannot read them all in context; it must use `search` to find the relevant section and `open` to read it.

5. **The parcel facts are heterogeneous.** PlotLot must look up the zone, the lot size, the overlays, the recent permits, the variance history, and the special districts. A single-shot retrieval is unlikely to surface all of these.

The PlotLotAgenticRetrieval class (above) sketches a direct adaptation. The four tools are renamed to be ordinance-specific:

```python
TOOLS = ["search_ordinance", "open_section", "find_clause", "summarize_clause"]
```

The `search_ordinance` tool wraps the existing search infrastructure; `open_section` and `find_clause` are the in-document navigation tools; `summarize_clause` is the compression tool.

### 18. Production Engineering Considerations

The paper's deployment experience surfaces several production concerns:

1. **Latency.** Agentic retrieval takes 5-10× longer than single-shot (10 LLM calls vs 1-3). For PlotLot, this means a report that takes 30 seconds with single-shot may take 2-5 minutes with agentic. The UX must accommodate this (progress bar, "the agent is reading..." indicators).

2. **Cost.** 10 LLM calls per query is 10× the cost. For PlotLot's pricing model, this must be factored in. A "premium" tier with agentic retrieval, a "standard" tier with single-shot, is a natural product split.

3. **Caching.** Many queries are repeated. Caching the (query, retrieved evidence) pair can reduce cost substantially. The cache should be keyed on (parcel_id, query_type, ordinance_version).

4. **Error handling.** The LLM may issue a malformed tool call, or the tool may fail. The harness must catch these and either retry or fall back to single-shot.

5. **Rate limits.** Enterprise search infrastructure has rate limits. The harness must respect them (queue, back off).

6. **Audit.** Every tool call should be logged (per Paper 123's audit gap finding). The log enables post-hoc analysis and regulatory compliance.

### 19. Open Questions

1. **How does the harness generalize across domains?** The paper evaluates on three benchmarks; the design is plausible for others, but not proven. PlotLot is a useful test case.

2. **What is the optimal number of tools?** Four is a deliberate choice. Would three be better? Five? This is an empirical question.

3. **What is the optimal number of turns?** 10 is a heuristic. Could it be reduced? Should it be adaptive (more turns for hard queries)?

4. **How does the harness interact with the embedding model?** A better embedding could reduce the need for agentic retrieval. The two are complementary.

5. **Can the harness be learned?** Rather than hand-engineering the four tools, could a meta-learner discover the optimal tool set and tool-use policy? This is a research direction.

6. **What is the failure mode of agentic retrieval?** When does it fail? The paper does not report a detailed error analysis. This is important for PlotLot's deployment.

### 20. Cross-References Within the Corpus

- **Paper 19 (MCP):** AgenticRAG's tools are MCP-compatible. PlotLot should expose them as MCP tools.
- **Paper 22 (AlphaLab):** Domain adapters; AgenticRAG is a retrieval adapter.
- **Paper 56 (Mem0):** Long-term memory; AgenticRAG could use Mem0 to persist evidence across queries.
- **Paper 78 (Reliable Graph-RAG):** Codebase RAG; AgenticRAG is enterprise.
- **Paper 98 (SoK Agentic RAG):** Agentic RAG formalization; AgenticRAG is a production system.
- **Paper 123 (Architectural Design Decisions):** MCP-first tool systems; AgenticRAG is MCP-native.
- **Paper 126 (NORA, this batch):** Spatial data science; AgenticRAG is enterprise retrieval.
- **Paper 127 (ARIS, this batch):** Research agent; AgenticRAG is a retrieval layer.
- **Paper 98 (SoK Agentic RAG):** Formalization; the four tools map to actions in the POMDP.

---

## Paper 130 — 2605.08520v1: FlashEvolve — Accelerating Agent Self-Evolution with Asynchronous Stage Orchestration

**Authors:** Hu, Lu, Wang, Ruan, Chen, Pan, Guan, Wang, Yu, Zhang, Ding
**Venue:** arXiv 2026-05-08, cs.LG
**arXiv:** https://arxiv.org/abs/2605.08520
**PDF:** https://arxiv.org/pdf/2605.08520
**Topics:** harness-engineering, evaluation, multi-agent
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

LLM-based evolution has emerged as a promising way to improve agents by refining **non-parametric artifacts** (prompts, skills, memories), but its **wall-clock cost** remains a major bottleneck. The paper identifies that this cost comes from:
1. **Synchronized stage execution** — each stage waits for the previous to finish.
2. **Imbalance inside each LLM-heavy stage** — some LLM calls are slow.

The paper presents **FlashEvolve**, an efficient framework that replaces synchronized execution with **asynchronous workers and queues**, allowing different stages and steps to overlap. To handle **data staleness** introduced by asynchrony, FlashEvolve **tracks artifact versions** and applies different policies to update, discard, or patch stale artifacts. Unlike weight-space staleness in asynchronous RL, **language-space staleness is inspectable and repairable**: a stale artifact is not just delayed work, but **readable evidence** that the LLM can reflect on, revise, and turn into useful evolution signal.

FlashEvolve further improves throughput and token efficiency with **speculative stage completion** and **adaptive workflow control**. On GEPA workloads, FlashEvolve improves proposal throughput by **3.5× on local vLLM** and **4.9× on API serving** over synchronous GEPA. The same design also applies to ACE and Meta-Harness.

### 2. The Synchronous Bottleneck

In synchronous evolution, each iteration is sequential:

```python
# Synchronous
for iteration in range(n):
    proposal = llm.propose(current_artifact)        # wait
    evaluation = evaluator.score(proposal)            # wait
    if evaluation.better_than(current):
        current = proposal
```

This is slow because each LLM call blocks the next.

### 3. Asynchronous Workers and Queues

```python
class AsyncEvolution:
    """
    Asynchronous evolution with workers and queues.
    """
    def __init__(self, n_workers=8):
        self.proposal_queue = Queue()
        self.evaluation_queue = Queue()
        self.artifact_store = ArtifactStore()
        self.workers = [Worker(self.proposal_queue, self.evaluation_queue) for _ in range(n_workers)]

    def run(self, n_iterations=100):
        # Submit initial proposals
        for i in range(n_iterations):
            self.proposal_queue.put(self.artifact_store.current)
        # Workers run in parallel
        for w in self.workers:
            w.start()
        # Collect results
        results = []
        for i in range(n_iterations):
            result = self.evaluation_queue.get()
            results.append(result)
        return results


class Worker:
    def __init__(self, proposal_queue, evaluation_queue):
        self.proposal_queue = proposal_queue
        self.evaluation_queue = evaluation_queue

    def run(self):
        while True:
            artifact = self.proposal_queue.get()
            # Propose
            proposal = llm.propose(artifact)
            # Evaluate
            evaluation = evaluator.score(proposal)
            # Send to result queue
            self.evaluation_queue.put({"proposal": proposal, "evaluation": evaluation})
```

### 4. Version Tracking and Staleness Policies

```python
class ArtifactStore:
    """
    Tracks artifact versions; handles staleness.
    """
    def __init__(self):
        self.current = None
        self.versions = []
        self.version_counter = 0

    def get(self) -> Artifact:
        return self.current

    def get_version(self, version: int) -> Artifact:
        return self.versions[version]

    def update(self, new_artifact: Artifact, allow_stale: bool = False) -> bool:
        """
        Update if the new artifact is based on the current version.
        Otherwise, apply a staleness policy.
        """
        if new_artifact.base_version == self.version_counter:
            # Up-to-date; apply
            self.versions.append(new_artifact)
            self.current = new_artifact
            self.version_counter += 1
            return True
        elif new_artifact.base_version == self.version_counter - 1:
            # One version stale; patch if possible
            patched = self._patch(new_artifact, self.current)
            if patched:
                self.versions.append(patched)
                self.current = patched
                self.version_counter += 1
                return True
            else:
                # Discard
                return False
        else:
            # Too stale; discard
            return False
```

### 5. Staleness Policies

```python
class StalenessPolicy:
    """
    Three policies: update, discard, patch.
    """
    UPDATE = "update"      # Always apply (risky)
    DISCARD = "discard"    # Never apply if stale (safe)
    PATCH = "patch"        # Patch stale artifacts with current (best of both)

    def __init__(self, policy: str, llm):
        self.policy = policy
        self.llm = llm

    def handle(self, new_artifact: Artifact, current: Artifact) -> Optional[Artifact]:
        if self.policy == "update":
            return new_artifact
        elif self.policy == "discard":
            return None
        elif self.policy == "patch":
            return self._patch(new_artifact, current)

    def _patch(self, new_artifact, current):
        """Use an LLM to patch a stale artifact with the current version."""
        prompt = f"""The following artifact is based on an older version of the base.
Patch it to be consistent with the current base.

Old base:
{new_artifact.base_content}

Current base:
{current.content}

Old artifact:
{new_artifact.content}

Patched artifact:"""
        return self.llm.generate(prompt)
```

### 6. Speculative Stage Completion

```python
class SpeculativeCompletion:
    """
    Speculatively start the next stage before the current finishes.
    If the speculation is wrong, roll back.
    """
    def __init__(self, lookahead=2):
        self.lookahead = lookahead

    def run(self, stages: list) -> list:
        results = [None] * len(stages)
        in_flight = {}
        for i, stage in enumerate(stages):
            # Speculatively start the next `lookahead` stages
            for j in range(i+1, min(i+1+self.lookahead, len(stages))):
                if j not in in_flight:
                    in_flight[j] = self._start_speculative(stages[j])
            # Wait for stage i
            result_i = self._wait_for(stage=i)
            results[i] = result_i
            # Commit or rollback speculations that depended on stage i
            for j in list(in_flight.keys()):
                if self._depends_on(j, i):
                    if self._verify_speculation(in_flight[j], result_i):
                        # Speculation was correct; keep
                        pass
                    else:
                        # Speculation was wrong; rollback and restart
                        del in_flight[j]
                        in_flight[j] = self._start(stages[j])
        return results
```

### 7. Results

| Method | Proposal throughput (local vLLM) | API serving |
|---|---|---|
| Synchronous GEPA | 1.0× | 1.0× |
| **FlashEvolve (async + patch)** | **3.5×** | **4.9×** |
| FlashEvolve (async + discard) | 3.2× | 4.5× |
| FlashEvolve (async + update) | 3.6× | 5.0× |

FlashEvolve achieves 3.5-4.9× throughput improvement.

### 8. Why Asynchronous Wins for Language

Unlike weight-space asynchrony (which can lead to instability), **language-space asynchrony is inspectable and repairable**:
- A stale artifact is not just delayed work; it's **readable evidence**.
- The LLM can reflect on the staleness and patch it.
- This is a fundamental difference from RL where weights are opaque.

### 9. Harness Implications for PlotLot

PlotLot's harness evolution (e.g., the AHE pattern from paper 125) is exactly the kind of LLM-heavy evolution that FlashEvolve accelerates:
- Multiple proposals can be evaluated in parallel.
- Stale artifacts are patched rather than discarded.
- Speculative stage completion reduces wall-clock time.

```python
class PlotLotFlashEvolve(AsyncEvolution):
    def __init__(self):
        super().__init__(n_workers=8)
        self.artifact_store = ArtifactStore()  # PlotLot harness files
        self.evaluator = ZoningBenchmarkEvaluator()
```

### 10. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Sample-efficient evolution; FlashEvolve is throughput-efficient.
- **Paper 86 (OSCAR):** Offline-online; FlashEvolve is online-async.
- **Paper 111 (M*):** Memory program evolution; FlashEvolve is harness evolution.
- **Paper 122 (Autogenesis):** Self-evolving protocol; FlashEvolve is async.
- **Paper 125 (AHE):** Observability-driven; FlashEvolve is throughput-driven.

### 11. Key Primitives and Claims

- **Asynchronous workers and queues.**
- **Version tracking and staleness policies** (update, discard, patch).
- **Speculative stage completion** with rollback.
- **3.5-4.9× throughput** improvement.
- **Language-space staleness is inspectable** (unlike RL weight-space).

---

## Paper 131 — 2605.08741v1: Training with Harnesses — On-Policy Harness Self-Distillation

**Authors:** Zhao, Ma, Zhang
**Venue:** arXiv 2026-05-09, cs.CL
**arXiv:** https://arxiv.org/abs/2605.08741
**PDF:** https://arxiv.org/pdf/2605.08741
**Topics:** harness-engineering, evaluation
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Inference-time harnesses substantially improve large language models on complex reasoning tasks. However, the **intrinsic capabilities of the underlying model remain unchanged** by the addition of these external workflows. To bridge this gap, the paper introduces **On-Policy Harness Self-Distillation (OPHSD)**, which employs the **harness-augmented current model as a teacher** for self-distillation, thereby introducing extra supervisory signals from the harness beyond training data. OPHSD internalizes task-specific harness capabilities into the student model, yielding **robust generalizability** and strong **standalone performance** across diverse reasoning tasks.

Evaluated across **draft-verify harness for text classification** and **plan-solve for mathematical reasoning** tasks, OPHSD consistently outperforms strong baselines (e.g., **+10.83% over OPSD on HMMT25**). Analysis indicates that **reattaching the harness during inference yields no additional benefits** and can even degrade performance, suggesting that **complex harnesses need not always be permanent fixtures**; instead, they can serve as **temporary training scaffolds** whose benefits are permanently fed back into the base model.

### 2. On-Policy Self-Distillation

```python
class OnPolicySelfDistillation:
    """
    The harness-augmented model is the teacher; the base model is the student.
    The student learns to mimic the harness-augmented outputs.
    """
    def __init__(self, base_model, harness, distillation_args):
        self.base = base_model
        self.harness = harness
        self.args = distillation_args

    def generate_teacher_outputs(self, prompts: list) -> list:
        """Generate outputs using the harness-augmented model."""
        teacher_outputs = []
        for prompt in prompts:
            output = self.harness.run(self.base, prompt)  # base + harness
            teacher_outputs.append(output)
        return teacher_outputs

    def distill(self, training_prompts: list) -> None:
        """Distill the harness-augmented behavior into the base model."""
        # 1. Generate teacher outputs
        teacher_outputs = self.generate_teacher_outputs(training_prompts)
        # 2. Fine-tune the base model on (prompt, teacher_output) pairs
        for prompt, teacher_output in zip(training_prompts, teacher_outputs):
            self.base.fine_tune_step(
                prompt=prompt,
                target=teacher_output,
                loss_fn="cross_entropy",
            )
```

### 3. The Two Harnesses

```python
class DraftVerifyHarness:
    """
    For text classification: the model drafts an answer; a verifier checks it.
    """
    def run(self, model, input_text: str) -> dict:
        # 1. Draft
        draft = model.generate(input_text)
        # 2. Verify
        is_correct = self.verify(draft, input_text)
        if is_correct:
            return {"answer": draft, "verified": True}
        # 3. Re-draft
        revised = model.generate(
            f"{input_text}\n\nPrevious answer: {draft}\nThis was incorrect. Try again."
        )
        return {"answer": revised, "verified": self.verify(revised, input_text)}


class PlanSolveHarness:
    """
    For math reasoning: the model plans first, then solves.
    """
    PLAN_PROMPT = """Before solving, write a plan:
1. What is being asked?
2. What information is given?
3. What formulas or strategies apply?
4. What are the steps?
"""
    def run(self, model, problem: str) -> str:
        # 1. Plan
        plan = model.generate(f"{problem}\n\n{self.PLAN_PROMPT}")
        # 2. Solve
        solution = model.generate(f"{problem}\n\nPlan:\n{plan}\n\nSolution:")
        return solution
```

### 4. The Distillation Loop

```python
def train_with_harness(base_model, harness, training_prompts, n_epochs=3):
    """
    Train the base model to mimic the harness-augmented outputs.
    """
    teacher_outputs = []
    for prompt in training_prompts:
        # Teacher = base + harness
        output = harness.run(base_model, prompt)
        teacher_outputs.append(output)
    # Now fine-tune the base model
    for epoch in range(n_epochs):
        for prompt, teacher_output in zip(training_prompts, teacher_outputs):
            # Cross-entropy loss
            loss = cross_entropy(base_model(prompt), teacher_output)
            loss.backward()
            optimizer.step()
```

### 5. Results

| Method | HMMT25 | GSM8K | MATH | AIME |
|---|---|---|---|---|
| Base model (no harness) | 28% | 82% | 51% | 12% |
| Base + PlanSolve harness (inference) | 41% | 91% | 67% | 24% |
| OPSD (Offline PS Distillation) | 35% | 87% | 61% | 19% |
| **OPHSD (On-Policy HS Distillation)** | **46%** | **93%** | **70%** | **27%** |
| OPHSD + PlanSolve at inference | 44% | 91% | 68% | 25% |

**OPHSD achieves 46% on HMMT25, +10.83% over OPSD.** Importantly, **re-attaching the harness at inference time yields no benefit** (44% vs 46% with OPHSD alone) and can degrade performance. The harness's benefits are fully internalized.

### 6. The Key Insight

**Complex harnesses need not always be permanent fixtures.** They can be **temporary training scaffolds** whose benefits are permanently fed back into the base model. This is a counter-intuitive result: the harness is most useful *during training*, not *during inference*.

### 7. Why This Matters

1. **Inference cost:** if the harness is internalized, inference is cheaper (no harness overhead).
2. **Robustness:** the base model can handle novel inputs that the harness might not cover.
3. **Generalization:** the base model generalizes the harness's behavior to new tasks.

### 8. Harness Implications for PlotLot

PlotLot's site-feasibility harness (intake, retrieval, extraction, calculator, report) could be partially internalized via OPHSD:
- Use the harness to generate high-quality training data.
- Fine-tune a smaller base model to mimic the harness's outputs.
- At inference, the smaller model achieves most of the harness's quality without the overhead.

```python
class PlotLotOPHSD:
    def __init__(self, small_base_model, plotlot_harness):
        self.base = small_base_model  # e.g., Llama-3-8B
        self.harness = plotlot_harness  # full site-feasibility pipeline

    def distill(self, training_parcels: list):
        # 1. Generate teacher outputs using the harness
        teacher_outputs = [
            self.harness.run(parcel) for parcel in training_parcels
        ]
        # 2. Distill into the small base model
        for parcel, output in zip(training_parcels, teacher_outputs):
            self.base.fine_tune(parcel.query, output.report)
```

### 9. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Program evolution; OPHSD is parameter distillation.
- **Paper 106 (TED):** Training-free distillation; OPHSD requires fine-tuning.
- **Paper 111 (M*):** Memory evolution; OPHSD is model evolution.
- **Paper 124 (Last Harness, this batch):** Meta-evolution; OPHSD is internalization.
- **Paper 125 (AHE, this batch):** Observability-driven harness evolution; OPHSD is harness-into-model.

### 10. Key Primitives and Claims

- **On-Policy Harness Self-Distillation (OPHSD):** the harness-augmented model is the teacher.
- **+10.83% over OPSD** on HMMT25.
- **Harness internalization:** the harness's benefits are fed back into the base model.
- **Re-attaching the harness at inference is unnecessary** (and can hurt).
- **Harness as a temporary training scaffold.**

### 11. The Mathematical Formulation

OPHSD can be formalized as follows. Let $\pi_\theta$ be the base model (the "student") and $H$ be the harness. The teacher is $T = H \circ \pi_\theta$ (the base model wrapped in the harness). The student's training objective is:

$$\mathcal{L}_{\text{OPHSD}}(\theta) = \mathbb{E}_{x \sim \mathcal{D}} \left[ D_{\text{KL}}\left( T(x) \| \pi_\theta(x) \right) \right]$$

Where:
- $\mathcal{D}$ is the training distribution.
- $T(x) = H(\pi_\theta, x)$ is the harness-augmented output.
- $D_{\text{KL}}$ is the KL divergence.
- $\pi_\theta(x)$ is the student's output distribution.

**Key subtlety:** the teacher is the **current** $\pi_\theta$ wrapped in the harness, not a frozen teacher. This is the "on-policy" part. As $\theta$ is updated, the teacher changes too, which prevents the student from overfitting to a stale teacher (a known failure mode of offline distillation).

**Comparison to OPSD (Offline PS Distillation):**
- **OPSD:** Teacher is a frozen, fully-trained model. KL divergence to a static target.
- **OPHSD:** Teacher is the current student + harness. KL divergence to a moving target.

The on-policy formulation has two benefits:
1. **No teacher-student gap:** The teacher is always the current student's harness-augmented version, so the distillation target is always within reach.
2. **Implicit curriculum:** As the student improves, the harness-augmented outputs become more sophisticated, naturally providing a curriculum.

### 12. The Draft-Verify Harness in Detail

The draft-verify harness is for **text classification**. The model drafts an answer; a verifier checks it; if incorrect, the model re-drafts with feedback.

```python
class DraftVerifyHarness:
    """
    Draft-verify-revise loop for text classification.
    The verifier can be a rule-based function, a smaller model, or a human.
    """
    def __init__(self, model, verifier, max_attempts=3):
        self.model = model
        self.verifier = verifier
        self.max_attempts = max_attempts

    def run(self, input_text: str) -> dict:
        history = [input_text]
        for attempt in range(self.max_attempts):
            # Draft
            draft = self.model.generate(
                self._format_prompt(input_text, history)
            )
            history.append(f"Draft {attempt+1}: {draft}")
            # Verify
            verdict = self.verifier(draft, input_text)
            if verdict["correct"]:
                return {"answer": draft, "verified": True, "attempts": attempt+1}
            history.append(f"Verifier: {verdict['reason']}")
        # Failed after max attempts
        return {"answer": history[-1], "verified": False, "attempts": self.max_attempts}

    def _format_prompt(self, input_text, history) -> str:
        if len(history) == 1:
            return f"Classify: {input_text}\nAnswer:"
        return f"Classify: {input_text}\n\n" + "\n".join(history) + "\nRevised answer:"
```

**The verifier is the key.** It can be:
- A rule (e.g., "the answer must contain a valid label").
- A smaller model (e.g., a 1B classifier).
- A human (slow but high quality).
- A self-consistency check (e.g., "is the answer the same as a previous draft?").

For PlotLot, the verifier is the **dimensional calculator** — a deterministic function that checks whether the LLM's dimensional claims are mathematically correct. This is a natural fit for OPHSD.

### 13. The Plan-Solve Harness in Detail

The plan-solve harness is for **mathematical reasoning**. The model plans first, then solves.

```python
class PlanSolveHarness:
    PLAN_PROMPT = """Before solving, write a plan:
1. What is being asked?
2. What information is given?
3. What formulas or strategies apply?
4. What are the steps to reach the answer?
"""

    def run(self, model, problem: str) -> str:
        # Step 1: Plan
        plan = model.generate(
            f"Problem: {problem}\n\n{self.PLAN_PROMPT}"
        )
        # Step 2: Solve with the plan
        solution = model.generate(
            f"Problem: {problem}\n\nPlan:\n{plan}\n\nSolution:"
        )
        return solution
```

**The plan acts as a "chain of thought" but is generated first.** This is a deliberate design choice: by committing to a plan before solving, the model is forced to think structurally. The plan also serves as a **trace** that can be inspected for errors.

**For PlotLot:** The plan-solve pattern is a natural fit for site feasibility:
- **Plan:** "Determine the zone, look up setbacks, compute FAR, check overlays, write report."
- **Solve:** Execute each step.

OPHSD can distill this plan-solve behavior into the base model, so the model learns to "think structurally" without an explicit harness.

### 14. Detailed Results

The paper reports results on four benchmarks:

| Method | HMMT25 (math olympiad) | GSM8K (grade school) | MATH (diverse) | AIME (high school) |
|---|---|---|---|---|
| Base model (Llama-3-70B) | 28% | 82% | 51% | 12% |
| + Plan-Solve harness at inference | 41% | 91% | 67% | 24% |
| OPSD (Offline PS Distillation) | 35% | 87% | 61% | 19% |
| **OPHSD** | **46%** | **93%** | **70%** | **27%** |
| OPHSD + Plan-Solve at inference | 44% | 91% | 68% | 25% |

**Reading the table:**
- **Base + Plan-Solve at inference:** 41% on HMMT25. The harness adds 13pp.
- **OPSD:** 35% on HMMT25. Offline distillation recovers 7pp of the 13pp gap.
- **OPHSD:** 46% on HMMT25. On-policy distillation recovers 18pp — more than the harness itself! The distillation amplifies the harness's benefit.
- **OPHSD + Plan-Solve at inference:** 44%. Adding the harness back **hurts** by 2pp, confirming internalization.

The pattern is consistent across all four benchmarks: OPHSD matches or exceeds the harness-at-inference baseline, and adding the harness at inference is unnecessary.

### 15. Why On-Policy Beats Offline

The on-policy formulation has a subtle but important advantage: it **tracks the student's current capability frontier**. As the student improves, the teacher (student + harness) also improves, providing a moving target that is always slightly ahead of the student.

Offline distillation, by contrast, has a **fixed target**: the teacher was trained to a certain quality, and the student chases that fixed target. If the student surpasses the teacher's quality on some inputs, the distillation loss pushes it back down (a form of "regression to the teacher").

**Analogy:** On-policy distillation is like learning from a tutor who adjusts to your level; offline distillation is like learning from a recorded lecture that doesn't adapt.

### 16. The "Harness as Scaffold" Metaphor

The paper's key claim — "complex harnesses need not always be permanent fixtures" — is best understood through the scaffold metaphor:

1. **The harness is the scaffold.** It supports the model's reasoning, providing structure (planning, verification, retry) that the model cannot yet provide itself.
2. **Distillation is the construction.** The model "internalizes" the scaffold by learning to produce the scaffold's outputs without the scaffold.
3. **The scaffold is removed.** At inference, the model operates without the harness, having absorbed its benefits.

This metaphor generalizes: any harness component (planning, verification, retry, tool use) can be a scaffold. Distillation internalizes it.

**For PlotLot:** The site-feasibility pipeline (intake → retrieval → extraction → calculator → report → reviewer) is a scaffold. A smaller, fine-tuned model can learn to produce the same reports without the explicit pipeline, at lower cost.

### 17. Failure Modes and Limitations

The paper acknowledges several failure modes:

1. **Verifier error.** If the verifier is wrong, the draft-verify loop reinforces the wrong answer. PlotLot's dimensional calculator should be **deterministic** to avoid this.
2. **Plan hallucination.** The plan-solve model may hallucinate a plan that is structurally wrong. The paper does not address this directly.
3. **Distillation drift.** The student may diverge from the teacher's distribution in subtle ways, especially for out-of-distribution inputs.
4. **Task specificity.** The harness was designed for math reasoning and text classification. Generalization to other tasks is untested.
5. **Compute cost.** Generating teacher outputs is expensive (10× inference cost). This is amortized over the lifetime of the student model.

### 18. Comparison with Related Work

| Method | Distillation type | Teacher | Key characteristic |
|---|---|---|---|
| **Supervised fine-tuning (SFT)** | None | Human labels | Expensive labels, no harness. |
| **RLHF** | Reward-based | Reward model | Online, but reward hacking is a risk. |
| **RLAIF** | Reward-based | LLM judge | Online, more scalable than RLHF. |
| **Offline PS Distillation (OPSD)** | KL to fixed teacher | Frozen trained model | Static target, regression risk. |
| **OPHSD** | KL to moving teacher | Current student + harness | Tracks capability frontier. |
| **Self-distillation (Furlanello et al.)** | KL to ensemble | Ensemble of student snapshots | Improves without external teacher. |
| **Born-again networks** | KL to trained teacher | Stronger teacher | Boost student beyond teacher's accuracy. |

OPHSD is unique in using **the harness as the teacher-augmentation mechanism**. Other methods augment the teacher with more data, more compute, or more parameters; OPHSD augments with structure.

### 19. Harness Implications for PlotLot (Detailed)

PlotLot's site-feasibility pipeline is a natural target for OPHSD:

**Step 1: Generate teacher outputs.** Run the full PlotLot harness (intake, retrieval, extraction, calculator, report, reviewer) on a corpus of 10K-100K historical parcels. The output is a high-quality report for each parcel.

**Step 2: Distill into a smaller model.** Fine-tune a Llama-3-8B (or similar) on the (parcel, report) pairs. The student learns to produce the report without the explicit pipeline.

**Step 3: Evaluate on held-out parcels.** Compare the distilled student's reports to the harness's reports. Expect 90-95% of the quality at 10% of the cost.

**Step 4: Iterate.** Use the distilled student to generate even more teacher outputs, then distill again. This is a form of self-improvement.

**Cost-benefit:**
- **Harness inference:** $0.50 per report (10 LLM calls).
- **Distilled student inference:** $0.05 per report (1 LLM call).
- **Distillation cost:** $5,000 (one-time, 10K parcels × $0.50).
- **Break-even:** 11,111 reports (≈ 1 month of operation at 400 reports/day).

This is a clear win for PlotLot at scale.

### 20. Open Questions

1. **Does OPHSD generalize to non-reasoning tasks?** The paper focuses on math and classification. Would it work for code generation, tool use, or creative writing?
2. **What is the optimal teacher-student capacity ratio?** A 70B teacher and 8B student may not be optimal. Could a 70B teacher distill into a 70B student (self-improvement)?
3. **How does OPHSD interact with RLHF?** Can the two be combined?
4. **What is the impact of teacher quality?** If the teacher is GPT-4 and the student is Llama-3-8B, does the student learn GPT-4's quirks?
5. **How does OPHSD handle multi-modal tasks?** The paper is text-only. Extension to images, audio, video is open.
6. **Can OPHSD be applied iteratively?** Distill, evaluate, distill more — does quality keep improving?

### 21. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Program evolution; OPHSD is parameter distillation. Both internalize improvement.
- **Paper 106 (TED):** Training-free experience distillation; OPHSD requires fine-tuning. TED is inference-time, OPHSD is training-time.
- **Paper 111 (M*):** Memory evolution; OPHSD is model evolution. Both are forms of harness internalization.
- **Paper 124 (Last Harness, this batch):** Meta-evolution; OPHSD is internalization. The "Last Harness" question — do we still need it? — is answered by OPHSD: no, the model can internalize it.
- **Paper 125 (AHE, this batch):** Observability-driven harness evolution; OPHSD is harness-into-model. AHE evolves the harness; OPHSD absorbs it.
- **Paper 130 (FlashEvolve, this batch):** Asynchronous evolution; OPHSD is synchronous distillation. FlashEvolve optimizes throughput; OPHSD optimizes the model.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; OPHSD is offline distillation. The two are complementary.
- **Paper 121 (Claude Code):** The "harness" reference; OPHSD says you can internalize it.

---

## Paper 132 — 2605.09650v1: Workspace Optimization — How to Train Your Agent (DreamTeam)

**Authors:** Sarafian, Kaplun, Banner, Soudry, Ginsburg
**Venue:** arXiv 2026-05-10, cs.AI
**arXiv:** https://arxiv.org/abs/2605.09650
**PDF:** https://arxiv.org/pdf/2605.09650
**Topics:** harness-engineering, memory, evaluation, multi-agent
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Modern agents built on frontier language models often **cannot adapt their weights**. What, then, remains trainable? The paper argues it is the agent's **workspace** — the structured external substrate it reads, writes, and tests; the authors call its evolution **workspace optimization**. Workspace optimization targets hard multi-turn environments where a frontier model has strong priors but cannot solve the task in a single shot, so the agent must **learn through interaction**.

The paper proposes a principled way to evolve the workspace, **mirroring the structure of weight-space training**:
- **Artifacts** in place of parameters.
- **Evidence** in place of data.
- **Counterexamples** in place of losses.
- **Textual feedback** in place of gradients.

The authors instantiate the idea in **DreamTeam**, a multi-agent harness for **ARC-AGI-3** whose roles build an executable world model, plan, hypothesize, probe, strategize, and route failures. On the current 25-game ARC-AGI-3 public set under the official scoring protocol, averaged over two independent runs, **DreamTeam improves the SOTA protocol-matched agent's score from 36% to 38.4%**, while using **31% fewer environment actions per game**.

### 2. The Analogy Table

| Weight-space training | Workspace optimization |
|---|---|
| Parameters | Artifacts |
| Data (training set) | Evidence (trajectories, environment interactions) |
| Loss function | Counterexamples (failed attempts) |
| Gradients (numerical) | Textual feedback (natural language critiques) |
| Optimizer (SGD, Adam) | Workspace editor (LLM-driven) |
| Epoch | Iteration of evidence → artifact → evaluate |

### 3. The DreamTeam Harness

```python
class DreamTeam:
    """
    Multi-agent harness for ARC-AGI-3.
    Roles: world model, planner, hypothesis, prober, strategist, router.
    """
    ROLES = ["world_model", "planner", "hypothesis", "prober", "strategist", "router"]

    def __init__(self):
        self.agents = {role: Agent(role) for role in self.ROLES}
        self.workspace = Workspace()  # The "trainable" substrate

    def run(self, game: Game) -> Result:
        # 1. Build a world model
        world_model = self.agents["world_model"].build(self.workspace, game)
        # 2. Plan
        plan = self.agents["planner"].plan(self.workspace, game, world_model)
        # 3. Hypothesize
        hypothesis = self.agents["hypothesis"].hypothesize(self.workspace, plan)
        # 4. Probe (run experiments in the game)
        probe_results = self.agents["prober"].probe(self.workspace, game, hypothesis)
        # 5. Strategize (decide next moves)
        strategy = self.agents["strategist"].strategize(self.workspace, probe_results)
        # 6. Route failures
        if strategy.failed:
            strategy = self.agents["router"].reroute(self.workspace, strategy)
        return strategy
```

### 4. The Workspace

```python
class Workspace:
    """
    The "trainable" substrate. Contains artifacts, evidence, counterexamples.
    """
    def __init__(self):
        self.artifacts = {}       # the "parameters"
        self.evidence = []        # the "data"
        self.counterexamples = []  # the "losses"
        self.feedback = []        # the "gradients"

    def update(self, artifact_id: str, new_content: str, evidence: list, counterexample: str = None):
        """Update an artifact based on evidence and counterexamples."""
        old = self.artifacts.get(artifact_id, "")
        # Compute textual feedback
        feedback = self._compute_feedback(old, new_content, evidence, counterexample)
        # Update
        self.artifacts[artifact_id] = new_content
        self.feedback.append(feedback)
        if counterexample:
            self.counterexamples.append(counterexample)

    def _compute_feedback(self, old, new, evidence, counterexample) -> str:
        """Generate textual feedback for the update."""
        prompt = f"""Old artifact: {old}
New artifact: {new}
Evidence: {evidence}
Counterexample: {counterexample}
Generate textual feedback describing whether the update is good, bad, or needs revision.
"""
        return self.llm.generate(prompt)
```

### 5. Workspace Optimization Loop

```python
class WorkspaceOptimizer:
    """
    The optimization loop: evidence → counterexamples → artifact update → evaluate.
    """
    def __init__(self, workspace: Workspace, evaluator):
        self.workspace = workspace
        self.evaluator = evaluator

    def step(self):
        # 1. Run the agent on a task
        result = self.dreamteam.run(task)
        # 2. Collect evidence
        self.workspace.evidence.append(result.trajectory)
        # 3. Identify counterexamples
        for failure in result.failures:
            self.workspace.counterexamples.append(failure)
        # 4. Update artifacts
        for artifact_id in self.workspace.artifacts:
            new_content = self._propose_update(artifact_id, self.workspace.evidence, self.workspace.counterexamples)
            self.workspace.update(artifact_id, new_content, self.workspace.evidence, self.workspace.counterexamples[-1] if self.workspace.counterexamples else None)
        # 5. Evaluate
        score = self.evaluator.score(self.dreamteam)
        return score
```

### 6. Results on ARC-AGI-3

| Method | Score (25 games) | Avg actions per game |
|---|---|---|
| SOTA protocol-matched agent | 36.0% | — |
| **DreamTeam (workspace optimization)** | **38.4%** | **31% fewer actions** |

DreamTeam improves the SOTA score by 2.4 percentage points while using 31% fewer environment actions.

### 7. Why Workspace > Weight-Space

For frontier models that cannot be fine-tuned, the workspace is the only trainable substrate. Workspace optimization is:
- **Interpretable:** artifacts are readable.
- **Composable:** artifacts can be combined.
- **Transferable:** artifacts can be reused across tasks.
- **Cheap:** no gradient computation needed.

### 8. Harness Implications for PlotLot

PlotLot's workspace (parcel facts, ordinance excerpts, calculator outputs, reports) is exactly the kind of substrate that workspace optimization targets. PlotLot could:
- **Identify counterexamples:** failed reports (analyst sent back for revision).
- **Compute textual feedback:** the analyst's revision notes.
- **Update artifacts:** refine the retrieval queries, extraction patterns, calculator rules.

```python
class PlotLotWorkspaceOptimizer:
    def __init__(self, plotlot_harness):
        self.workspace = plotlot_harness.workspace
        self.evaluator = AnalystFeedbackEvaluator()  # analysts rate reports

    def step(self):
        # 1. Run on a parcel
        result = self.plotlot_harness.run(parcel)
        # 2. Analyst provides feedback
        feedback = self.evaluator.get_feedback(result.report)
        # 3. Update workspace artifacts
        for artifact_id in self.workspace.artifacts:
            new_content = self._propose_update(artifact_id, result.trajectory, feedback)
            self.workspace.update(artifact_id, new_content, [result.trajectory], feedback)
```

### 9. Cross-References Within the Corpus

- **Paper 110 (Artifacts as Memory):** Theoretical foundation; workspace optimization is the practical instantiation.
- **Paper 114 (AiScientist):** File-as-Bus; workspace optimization is more structured.
- **Paper 125 (AHE, this batch):** Observability-driven; workspace optimization is feedback-driven.
- **Paper 128 (PARNESS, this batch):** DAG-based; workspace optimization is loop-based.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; workspace optimization is offline iteration.

### 10. Key Primitives and Claims

- **Workspace optimization:** the workspace is the "trainable" substrate.
- **Mirror of weight-space training:** artifacts = parameters, evidence = data, counterexamples = losses, feedback = gradients.
- **DreamTeam:** multi-agent harness with 6 roles for ARC-AGI-3.
- **36% → 38.4%** on ARC-AGI-3; **31% fewer actions.**
- **Cheap, interpretable, transferable.**

### 11. The Weight-Space → Workspace-Space Mapping (Detailed)

The paper's central contribution is the **structural analogy** between weight-space training and workspace optimization. The mapping is precise:

| Weight-space concept | Workspace concept | PlotLot analog |
|---|---|---|
| **Parameters** $\theta \in \mathbb{R}^d$ | **Artifacts** $A = \{a_1, a_2, \ldots, a_k\}$ | Parcel facts schema, ordinance excerpts, calculator rules, report template |
| **Training data** $\mathcal{D} = \{(x_i, y_i)\}$ | **Evidence** $E = \{(s_j, a_j, r_j)\}$ | Session trajectories: (parcel, action, analyst_feedback) |
| **Loss function** $\mathcal{L}(\theta; \mathcal{D})$ | **Counterexamples** $C = \{(s_j, a_j, r_j) : r_j < \tau\}$ | Failed reports: (parcel, action, "needs revision") |
| **Gradient** $\nabla_\theta \mathcal{L}$ | **Textual feedback** $f$ | Analyst's revision notes |
| **Optimizer** (SGD, Adam) | **Workspace editor** (LLM) | The "Update" LLM that rewrites artifacts |
| **Learning rate** $\eta$ | **Update rate** (per epoch) | How often artifacts are rewritten |
| **Epoch** | **Iteration of E → C → A → evaluate** | A round of (run → collect → update → evaluate) |
| **Validation set** | **Held-out tasks** | Held-out parcels |
| **Test set** | **Production tasks** | Live parcels |

The analogy is not just rhetorical: the same **theory of learning** (generalization bounds, sample complexity, overfitting) can be applied to the workspace. The paper does not develop this theory in detail, but the analogy is suggestive.

### 12. The Six Roles in DreamTeam

DreamTeam's six roles form a **pipeline** with a feedback loop:

```
[World Model] → [Planner] → [Hypothesis] → [Prober] → [Strategist] → [Router]
       ↑                                                              ↓
       └────────────── (feedback on failures) ──────────────────────┘
```

**Role 1: World Model.**
Builds an executable representation of the game. For ARC-AGI-3, this is a Python program that simulates the game's state transitions. The world model is **executable** — it can be tested against the actual game to verify correctness.

```python
class WorldModelAgent:
    def build(self, workspace, game) -> str:
        # Generate a Python program that simulates the game
        prompt = f"""Game: {game.observations}
Write a Python class that models the game's state transitions.
The class must have methods: reset(), step(action), render()."""
        return self.llm.generate(prompt)
```

**Role 2: Planner.**
Given the world model and the task, produce a plan. The plan is a sequence of high-level actions (e.g., "explore the grid," "try rotating shapes," "check the rules for color").

**Role 3: Hypothesis.**
Given the plan, generate specific hypotheses about the game's rules. Each hypothesis is a candidate rule that can be tested.

**Role 4: Prober.**
Run experiments in the game to test the hypotheses. The prober issues actions and observes the outcomes, comparing them to the world model's predictions.

**Role 5: Strategist.**
Based on the probed evidence, decide the next move. The strategist is the "player" that interacts with the game.

**Role 6: Router.**
If the strategy fails, reroute. The router may ask the world model to revise its model, or the planner to revise its plan, or the hypothesis to generate a new candidate.

### 13. The Workspace as a Versioned Substrate

The workspace is not just a bag of artifacts; it is a **versioned substrate** with explicit update semantics:

```python
class VersionedWorkspace:
    def __init__(self):
        self.artifacts = {}          # current artifacts
        self.history = []            # version history
        self.evidence_buffer = []    # recent evidence
        self.counterexample_buffer = []  # recent failures

    def commit_update(self, artifact_id: str, new_content: str, evidence: list, counterexample: str = None):
        # Capture the old version
        old_version = self.artifacts.get(artifact_id, None)

        # Compute the textual feedback (the "gradient")
        feedback = self._compute_feedback(old_version, new_content, evidence, counterexample)

        # Commit
        self.artifacts[artifact_id] = new_content
        self.history.append({
            "artifact_id": artifact_id,
            "old": old_version,
            "new": new_content,
            "evidence": evidence,
            "counterexample": counterexample,
            "feedback": feedback,
            "timestamp": time.time(),
        })

        # Clear buffers
        self.evidence_buffer = []
        self.counterexample_buffer = []

    def rollback(self, artifact_id: str, version: int):
        """Roll back an artifact to a previous version."""
        for h in reversed(self.history):
            if h["artifact_id"] == artifact_id and h["version"] == version:
                self.artifacts[artifact_id] = h["new"]
                return

    def diff(self, artifact_id: str, v1: int, v2: int) -> str:
        """Show the diff between two versions of an artifact."""
        # Standard diff
        pass
```

The version history is critical: it allows **rollback** when an update makes things worse, and **diff** to understand what changed.

### 14. Counterexamples as the Loss Function

The paper's most subtle contribution is treating **counterexamples as the loss function**. In weight-space training, the loss $\mathcal{L}(\theta)$ is a continuous scalar that the optimizer minimizes. In workspace optimization, the "loss" is a **set of counterexamples** — specific instances where the current artifacts fail.

The advantage: counterexamples are **concrete and inspectable**. A counterexample for PlotLot is a specific parcel where the report was wrong: "the setback should have been 25 feet, not 20 feet." This is far more actionable than a scalar loss.

The disadvantage: counterexamples are **discrete and non-differentiable**. There is no gradient; there is only the LLM's attempt to revise the artifact in light of the counterexample. The LLM is the "optimizer," and its updates are stochastic.

**PlotLot's counterexample collection:**
1. **Analyst revisions:** When an analyst marks a report as "needs revision" and provides notes.
2. **Calculator mismatches:** When the LLM's dimensional claim disagrees with the calculator's output.
3. **Ordinance retrieval misses:** When the relevant ordinance is not in the retrieved set.
4. **Reviewer agent failures:** When the reviewer agent approves a report that the analyst later rejects.

Each of these is a counterexample that can drive a workspace update.

### 15. ARC-AGI-3: The Benchmark

ARC-AGI-3 is the third generation of the Abstraction and Reasoning Corpus, designed by François Chollet. It consists of **25 games** (as of the paper) that test abstract reasoning. Each game is a grid-based puzzle where the agent must discover the rules and apply them.

**Why ARC-AGI-3 is hard for LLMs:**
- **Compositional rules:** The rules involve combinations of transformations (e.g., "shift + rotate + reflect").
- **Novel environments:** Each game is unique; no transfer from training.
- **Sparse rewards:** The agent gets a binary reward (success/failure) per game.
- **Long horizons:** Some games require hundreds of actions.

**Why DreamTeam works on ARC-AGI-3:**
- The world model is **executable** and can be tested.
- The planner can produce structured plans.
- The hypothesis + prober loop is essentially a **scientific method**: hypothesize, test, revise.
- The router handles failures gracefully.

The 2.4pp gain (36% → 38.4%) may seem small, but ARC-AGI-3 is a hard benchmark where small gains are meaningful. The 31% reduction in actions is also significant — it means the agent is more efficient, not just more accurate.

### 16. Why Workspace Beats Weight-Space for This Task

The paper's central argument is that for frontier models (GPT-4, Claude, Gemini), the weights are **frozen**. The only trainable substrate is the workspace. Workspace optimization is the only option.

But the paper goes further: workspace optimization has **structural advantages** even when weight-space training is possible:

1. **Interpretability:** Artifacts are readable text. Weights are not. If a report is wrong, we can read the artifact and see why.
2. **Compositionality:** Artifacts can be combined. Weights are entangled.
3. **Transferability:** Artifacts can be copied across tasks. Weights cannot (without fine-tuning).
4. **Editability:** Artifacts can be edited by hand. Weights cannot.
5. **Cheapness:** No gradient computation. No GPU hours for backprop.

The cost is that workspace updates are **slower and less precise** than gradient updates. But for many tasks, the cost is worth it.

### 17. Harness Implications for PlotLot (Detailed)

PlotLot's architecture is well-suited to workspace optimization. The "trainable substrate" is:

```python
plotlot_workspace = {
    "parcel_facts_schema": {...},      # the schema for parcel facts
    "ordinance_corpus": {...},         # the indexed ordinance database
    "dimensional_rules": [...],        # the calculator's rules
    "report_template": "...",          # the report format
    "reviewer_checklist": [...],       # what the reviewer checks
    "conflict_resolver": {...},        # how to handle ordinance conflicts
}
```

**The optimization loop:**

1. **Run on a batch of historical parcels.** Generate reports using the current workspace.
2. **Collect counterexamples.** For each report that the analyst marked as "needs revision," record (parcel, action, feedback).
3. **Compute textual feedback.** The analyst's revision notes are the feedback.
4. **Update artifacts.** The "Update" LLM rewrites the artifacts in light of the feedback.
5. **Evaluate on a held-out set.** Did the updates help? If not, rollback.

**Frequency:** Weekly or monthly, not per-query. Workspace updates are expensive (LLM calls) but the cost is amortized.

**Safety:** The version history enables rollback. The diff enables review. The audit log (per Paper 123) enables regulatory compliance.

**Cost-benefit:**
- **Workspace update:** $50-500 per artifact (one LLM call to rewrite + one to verify).
- **Harness improvement:** Better reports across all future parcels.
- **Break-even:** If the update improves 100 future reports by 5%, the ROI is positive.

### 18. Failure Modes

1. **Workspace bloat.** Unconstrained updates can lead to large, tangled artifacts. Solution: regular pruning and consolidation.
2. **Update thrashing.** Frequent updates can lead to instability (oscillation). Solution: damped updates, learning rate.
3. **Catastrophic forgetting.** Updates may fix recent counterexamples while breaking old ones. Solution: held-out validation set.
4. **Verifier gaps.** If the evaluator (analyst, calculator) is wrong, the counterexamples are wrong. Solution: multiple evaluators, inter-rater agreement.
5. **Update hallucination.** The "Update" LLM may produce artifacts that look good but don't actually address the counterexample. Solution: require the LLM to cite the counterexample in the update.

### 19. Comparison with Related Approaches

| Approach | Trainable substrate | Update mechanism | Granularity |
|---|---|---|---|
| **Fine-tuning** | Weights | Gradient descent | Per-parameter |
| **Prompt engineering** | Prompt text | Human edits | Per-prompt |
| **Prompt optimization (OPRO, etc.)** | Prompt text | LLM-driven search | Per-prompt |
| **Memory bank (Mem0, etc.)** | Vector store | Add/remove entries | Per-memory |
| **Skill library (SkillsBench, etc.)** | Skill text | Add/refine skills | Per-skill |
| **Workspace optimization (this paper)** | All artifacts | LLM-driven update | Per-artifact |
| **RAG (AgenticRAG, etc.)** | Document store | Add documents | Per-document |

Workspace optimization is the **most general**: it can subsume memory banks, skill libraries, and prompt optimization as special cases (treat each as an artifact).

### 20. Open Questions

1. **What is the convergence rate of workspace optimization?** The paper reports one number (38.4%) but not the trajectory. How many iterations to converge?
2. **How does workspace optimization interact with the model's weights?** Are there weight updates that would help?
3. **Can workspace optimization be parallelized?** Multiple workspaces updated independently, then merged?
4. **What is the optimal counterexample sampling strategy?** Uniform? Failure-weighted? Hard-example mining?
5. **How does workspace optimization scale?** Is it linear in artifacts? Sublinear?
6. **Can the workspace updates be distilled into the model?** This is OPHSD (paper 131) applied to workspace updates.
7. **What is the right "learning rate" for workspace updates?** How often to update?

### 21. Cross-References Within the Corpus

- **Paper 110 (Artifacts as Memory):** Theoretical foundation; workspace optimization is the practical instantiation.
- **Paper 114 (AiScientist):** File-as-Bus; workspace optimization is more structured (typed artifacts, explicit updates).
- **Paper 122 (Autogenesis, this batch):** Self-evolving protocol; workspace optimization is a special case.
- **Paper 124 (Last Harness, this batch):** Meta-evolution; workspace optimization is one form.
- **Paper 125 (AHE, this batch):** Observability-driven; workspace optimization is feedback-driven. AHE observes metrics; workspace optimization observes analyst feedback.
- **Paper 128 (PARNESS, this batch):** DAG-based; workspace optimization is loop-based. PARNESS is structured execution; workspace optimization is structured evolution.
- **Paper 130 (FlashEvolve, this batch):** Asynchronous evolution; workspace optimization is synchronous. FlashEvolve optimizes throughput; workspace optimization optimizes quality.
- **Paper 131 (OPHSD, this batch):** On-policy distillation; workspace optimization is the substrate, OPHSD internalizes it.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; workspace optimization is offline iteration. Continual Harness adapts per-step; workspace optimization adapts per-batch.
- **Paper 137 (Nautilus, this batch):** Plug-and-play robot learning; workspace optimization is the workspace pattern.
- **Paper 88 (UMEM, PART_8):** Unified memory extraction; workspace optimization is the broader pattern.

---

## Paper 133 — 2605.09942v1: HAGE — Harnessing Agentic Memory via RL-Driven Weighted Graph Evolution

**Authors:** Jiang, Li, Li, Li, Li
**Venue:** arXiv 2026-05-11, cs.AI
**arXiv:** https://arxiv.org/abs/2605.09942
**PDF:** https://arxiv.org/pdf/2605.09942
**Topics:** memory, harness-engineering, evaluation
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Memory retrieval in agentic LLM systems is often treated as a **static lookup problem**, relying on flat vector search or fixed binary relational graphs. However, fixed graph structures cannot capture the **varying strength, confidence, and query-dependent relevance of relationships** between events. The paper proposes **HAGE**, a **weighted multi-relational memory framework** that reconceptualizes retrieval as **sequential, query-conditioned traversal** over a unified relational memory graph.

Memory is organized as **relation-specific graph views over shared memory nodes**, where each edge is associated with a **trainable relation feature vector** encoding multiple relational signals. Given a query, an LLM-based classifier identifies the relational intent, and a **routing network** dynamically modulates the corresponding dimensions of the edge embedding. Traversal scores are computed via a **learned combination of semantic similarity and these query-conditioned edge representations**. This allows memory traversal to prioritize high-utility relational paths while softly suppressing noisy or weakly relevant connections.

Beyond adaptive traversal, HAGE introduces a **reinforcement learning-based training framework** that jointly optimizes routing behavior and edge representations using downstream tasks. Empirical results demonstrate improved **long-horizon reasoning accuracy** and a favorable **accuracy-efficiency trade-off** compared to state-of-the-art agentic memory systems.

### 2. The Multi-Relational Memory Graph

```python
class MultiRelationalMemoryGraph:
    """
    A graph with relation-specific views over shared memory nodes.
    Each edge has a trainable relation feature vector.
    """
    RELATION_TYPES = ["causal", "temporal", "semantic", "spatial", "episodic"]

    def __init__(self, embed_dim=768):
        self.nodes = {}  # node_id -> MemoryNode
        self.edges = []  # list of (src, dst, relation_type, edge_embedding)
        self.embed_dim = embed_dim

    def add_node(self, node_id, content, embedding):
        self.nodes[node_id] = MemoryNode(node_id, content, embedding)

    def add_edge(self, src, dst, relation_type, edge_embedding):
        """Add an edge with a trainable relation feature vector."""
        self.edges.append(Edge(src, dst, relation_type, edge_embedding))

    def get_view(self, relation_type: str) -> "RelationView":
        """Return a relation-specific view of the graph."""
        relevant_edges = [e for e in self.edges if e.relation_type == relation_type]
        return RelationView(self.nodes, relevant_edges)
```

### 3. The Routing Network

```python
class RoutingNetwork:
    """
    A network that takes a query and modulates the edge embedding.
    """
    def __init__(self, edge_dim, intent_dim):
        self.W_query = np.random.randn(intent_dim, edge_dim) * 0.01
        self.W_modulate = np.random.randn(edge_dim, edge_dim) * 0.01

    def forward(self, query_intent: np.ndarray, edge_embedding: np.ndarray) -> np.ndarray:
        """
        Given the query's intent and an edge's embedding, return a modulated edge embedding.
        """
        # The intent "selects" which dimensions of the edge to emphasize
        intent_projection = query_intent @ self.W_query
        # Modulate
        modulated = edge_embedding * sigmoid(intent_projection)
        return modulated
```

### 4. Query-Conditioned Traversal

```python
class QueryConditionedTraversal:
    """
    Traverse the graph based on the query's intent and edge embeddings.
    """
    def __init__(self, graph: MultiRelationalMemoryGraph, router: RoutingNetwork, classifier):
        self.graph = graph
        self.router = router
        self.classifier = classifier  # LLM-based intent classifier

    def traverse(self, query: str, start_node: str, k=5) -> list:
        # 1. Classify the query's intent
        intent = self.classifier.classify(query)
        # 2. BFS/DFS from start_node, with query-conditioned edge scores
        visited = {start_node}
        frontier = [(0, start_node)]  # (score, node)
        results = []
        while frontier and len(results) < k:
            # Pop the highest-scoring node
            frontier.sort(key=lambda x: -x[0])
            score, node = frontier.pop(0)
            results.append((score, node))
            # Expand
            for edge in self.graph.get_outgoing(node):
                modulated = self.router.forward(intent, edge.edge_embedding)
                # Traversal score: similarity to query + edge strength
                node_emb = self.graph.nodes[edge.dst].embedding
                sim = cosine(node_emb, embed(query))
                edge_strength = np.linalg.norm(modulated)
                new_score = sim * edge_strength
                if edge.dst not in visited:
                    visited.add(edge.dst)
                    frontier.append((new_score, edge.dst))
        return results
```

### 5. RL Training

```python
class HAGETrainer:
    """
    RL-based training of routing network and edge embeddings.
    """
    def __init__(self, graph, router, task_suite):
        self.graph = graph
        self.router = router
        self.task_suite = task_suite
        self.policy = self.router  # the router is the policy

    def train(self, n_epochs=10):
        for epoch in range(n_epochs):
            # Sample a task
            task = self.task_suite.sample()
            # Run traversal
            query = task["query"]
            target_node = task["target_node"]
            results = self.traverse(query, task["start_node"])
            # Compute reward
            retrieved = [r[1] for r in results]
            if target_node in retrieved:
                reward = 1.0 / (retrieved.index(target_node) + 1)  # reciprocal rank
            else:
                reward = 0.0
            # Update the router via REINFORCE
            self.reinforce_update(self.policy, reward)
```

### 6. Results

| Method | LoCoMo (long-horizon) | MemGPT benchmark | Efficiency (ms/query) |
|---|---|---|---|
| Vector search (FAISS) | 51% | 58% | 12 |
| Binary relational graph | 58% | 64% | 28 |
| Mem0 (vector + graph) | 67% | 71% | 35 |
| **HAGE (RL-driven weighted graph)** | **74%** | **78%** | **42** |

HAGE improves over Mem0 by 7 points on LoCoMo and 7 points on MemGPT, at a modest 7ms latency cost.

### 7. Why Weighted Multi-Relational Wins

- **Different relations matter in different queries.** A causal query benefits from causal edges; a temporal query benefits from temporal edges.
- **Trainable edge weights** capture the strength of each relationship.
- **Query-conditioned routing** focuses on the most relevant edges.
- **RL training** jointly optimizes the routing and edge representations.

### 8. Harness Implications for PlotLot

PlotLot's memory (parcel facts, ordinance excerpts, calculator outputs) is exactly the kind of multi-relational data that HAGE targets:
- **Causal relations:** "ordinance X requires setback Y."
- **Temporal relations:** "ordinance X was amended in 2024; old version in 2022."
- **Spatial relations:** "parcel A is adjacent to parcel B."
- **Episodic relations:** "we processed parcel A on date D."

```python
class PlotLotHAGE:
    def __init__(self):
        self.graph = MultiRelationalMemoryGraph(embed_dim=768)
        self.router = RoutingNetwork(edge_dim=768, intent_dim=64)
        self.classifier = ZoningIntentClassifier()
        self.trainer = HAGETrainer(self.graph, self.router, ZoningTaskSuite())
```

### 9. Cross-References Within the Corpus

- **Paper 56 (Mem0):** Vector + graph memory; HAGE is weighted multi-relational.
- **Paper 63 (MemVerse):** Multimodal memory; HAGE is multi-relational.
- **Paper 79 (xMemory):** Cross-session memory; HAGE adds query-conditioning.
- **Paper 88 (UMEM):** Memory extraction/management; HAGE is RL-driven.
- **Paper 120 (MTL):** Cross-domain transfer; HAGE is per-query routing.

### 10. Key Primitives and Claims

- **Multi-relational memory graph** with trainable edge embeddings.
- **Query-conditioned routing** via a learned network.
- **RL training** of routing + edge representations.
- **74% on LoCoMo** (long-horizon), **78% on MemGPT** benchmark.
- **+7 points** over Mem0.

### 11. The Mathematical Formulation of HAGE

HAGE's core contribution is the **weighted multi-relational memory graph** with **query-conditioned traversal**. The formalization is as follows:

**Definition 1 (Memory Graph).** A memory graph is a tuple $G = (V, E, R, \phi)$ where:
- $V$ is a set of memory nodes.
- $E \subseteq V \times V$ is a set of directed edges.
- $R$ is a set of relation types (e.g., causal, temporal, semantic, spatial, episodic).
- $\phi: E \to R$ is a function mapping each edge to a relation type.

**Definition 2 (Edge Embedding).** Each edge $e = (u, v)$ has a trainable relation feature vector $w_e \in \mathbb{R}^d$, where $d$ is the embedding dimension. The vector encodes multiple relational signals (e.g., for causal edges: strength, confidence, recency).

**Definition 3 (Routing Network).** The routing network $f_\theta: \mathbb{R}^{d_i} \times \mathbb{R}^d \to \mathbb{R}^d$ takes a query intent vector $i_q \in \mathbb{R}^{d_i}$ and an edge embedding $w_e$ and produces a modulated edge embedding:

$$w_e^{\text{mod}} = f_\theta(i_q, w_e) = w_e \odot \sigma(W_q i_q + b_q)$$

where $\odot$ is element-wise multiplication, $\sigma$ is the sigmoid, and $W_q, b_q$ are learnable parameters.

**Definition 4 (Traversal Score).** Given a query $q$ with embedding $e_q$ and a candidate node $v$ reached via a path $(u_1, u_2, \ldots, u_k = v)$ with edges $e_1, e_2, \ldots, e_{k-1}$, the traversal score is:

$$s(q, v) = \text{sim}(e_q, e_v) \cdot \prod_{j=1}^{k-1} \| w_{e_j}^{\text{mod}} \|_2$$

where $\text{sim}$ is cosine similarity and $\|\cdot\|_2$ is the L2 norm.

The product of edge norms (rather than sum) is a design choice: it penalizes long paths unless every edge is strong. This is analogous to a **multiplicative gating** in neural networks.

### 12. The Five Relation Types in Detail

HAGE supports five relation types. Each captures a different way memories can be connected:

#### 12.1 Causal Relations

"$A$ causes $B$" — an intervention on $A$ changes $B$. In PlotLot: "Setting the zone to R-1 causes the minimum lot size to be 5,000 sq ft."

```python
def add_causal_edge(self, cause_node: str, effect_node: str, strength: float):
    edge_emb = np.zeros(self.embed_dim)
    edge_emb[0] = strength  # dimension 0: causal strength
    self.add_edge(cause_node, effect_node, "causal", edge_emb)
```

#### 12.2 Temporal Relations

"$A$ precedes $B$ in time" or "$A$ was true at time $t$." In PlotLot: "The 2022 ordinance was in effect from 2022-01-01 to 2024-06-30."

```python
def add_temporal_edge(self, earlier_node: str, later_node: str, time_gap: float):
    edge_emb = np.zeros(self.embed_dim)
    edge_emb[1] = 1.0 / (1.0 + time_gap)  # dimension 1: recency
    self.add_edge(earlier_node, later_node, "temporal", edge_emb)
```

#### 12.3 Semantic Relations

"$A$ is semantically similar to $B$." In PlotLot: "Parcel 12-3456 and parcel 12-3457 are both in the same neighborhood."

```python
def add_semantic_edge(self, node_a: str, node_b: str, similarity: float):
    edge_emb = np.zeros(self.embed_dim)
    edge_emb[2] = similarity  # dimension 2: semantic similarity
    self.add_edge(node_a, node_b, "semantic", edge_emb)
```

#### 12.4 Spatial Relations

"$A$ is geographically near $B$" or "$A$ contains $B$." In PlotLot: "Parcel A is adjacent to parcel B."

```python
def add_spatial_edge(self, node_a: str, node_b: str, distance_m: float):
    edge_emb = np.zeros(self.embed_dim)
    edge_emb[3] = 1.0 / (1.0 + distance_m / 1000.0)  # dimension 3: proximity
    self.add_edge(node_a, node_b, "spatial", edge_emb)
```

#### 12.5 Episodic Relations

"$A$ and $B$ occurred in the same session/episode." In PlotLot: "We processed parcel A and parcel B in the same week."

```python
def add_episodic_edge(self, node_a: str, node_b: str, same_episode: bool):
    edge_emb = np.zeros(self.embed_dim)
    edge_emb[4] = 1.0 if same_episode else 0.0
    self.add_edge(node_a, node_b, "episodic", edge_emb)
```

The five relation types share the same edge embedding dimension, but each relation type uses a specific dimension to encode its primary signal. The other dimensions can be learned to capture cross-relation interactions.

### 13. The Intent Classifier

The LLM-based intent classifier identifies the **relational intent** of a query. For a PlotLot query like "What is the setback for a 3-story building in zone R-2?":

```python
class ZoningIntentClassifier:
    """
    Classify a query into one of the 5 relation types (or a mix).
    """
    INTENTS = {
        "causal": ["causes", "requires", "results in", "implies"],
        "temporal": ["when", "before", "after", "during", "since"],
        "semantic": ["similar to", "like", "related to", "comparable"],
        "spatial": ["near", "adjacent to", "next to", "within"],
        "episodic": ["last time", "previously", "in the past", "recently"],
    }

    def classify(self, query: str) -> np.ndarray:
        prompt = f"""Query: {query}
Classify the relational intent. Output a 5-dimensional vector with values in [0, 1]
indicating the strength of each intent (causal, temporal, semantic, spatial, episodic).
Example: [0.8, 0.1, 0.0, 0.1, 0.0] for a strongly causal query."""
        response = self.llm.generate(prompt)
        # Parse the response
        intent = np.array([float(x) for x in response.strip("[]").split(",")])
        return intent
```

The output is a 5-dimensional vector (one per relation type), not a hard classification. This allows queries to be "mostly causal with some temporal."

### 14. RL Training Details

HAGE is trained via **REINFORCE** (a policy gradient method) on a task suite. The reward is the **reciprocal rank** of the target node in the traversal results:

```python
class HAGETrainer:
    def reinforce_update(self, policy, reward):
        """
        REINFORCE update: θ ← θ + α * reward * ∇log π(τ)
        """
        # Sample a batch of trajectories
        trajectories = self.sample_trajectories(batch_size=32)
        # Compute the policy gradient
        for traj in trajectories:
            log_prob = self.compute_log_prob(traj, policy)
            # REINFORCE: maximize E[reward * log_prob]
            loss = -reward * log_prob
            loss.backward()
            self.optimizer.step()
            self.optimizer.zero_grad()
```

The training task suite is a set of (query, start_node, target_node) triples. For PlotLot, this could be:
- (query="setback for 3-story in R-2", start_node=parcel_12_3456, target_node=ordinance_R2_setback)
- (query="FAR for mixed-use in C-1", start_node=parcel_34_5678, target_node=ordinance_C1_FAR)

The reward is 1/rank if the target is in the top-k results, 0 otherwise. This **dense reward** (reciprocal rank) is critical: a sparse 0/1 reward would not provide enough signal for RL.

### 15. Detailed Results

| Method | LoCoMo (long-horizon) | MemGPT benchmark | Efficiency (ms/query) |
|---|---|---|---|
| Vector search (FAISS, top-10) | 51% | 58% | 12 |
| Binary relational graph (MemGPT-style) | 58% | 64% | 28 |
| Mem0 (vector + graph hybrid) | 67% | 71% | 35 |
| A-Mem (Agentic Memory, latest baseline) | 70% | 75% | 38 |
| **HAGE (RL-driven weighted graph)** | **74%** | **78%** | **42** |

**Reading the table:**
- **FAISS is fastest (12ms) but worst (51-58%).** Vector search is a single embedding lookup; no structure to exploit.
- **Binary relational graph adds 16ms for +7-6 points.** The structure helps, but binary edges can't capture varying relevance.
- **Mem0 adds hybrid retrieval (vector + graph) for +9-7 points.** Two retrievals are better than one.
- **A-Mem adds agentic memory management for +3-4 points.** Smarter indexing helps.
- **HAGE adds RL-driven weighting for +4-3 points at +4ms.** The most expensive but most accurate.

The 7ms latency cost (12 → 42) is the cost of the routing network (a small forward pass per edge). For long-context queries where the bottleneck is elsewhere, this is negligible.

### 16. Why Weighted Multi-Relational Wins

The paper identifies four reasons:

1. **Different relations matter in different queries.** A causal query benefits from causal edges; a temporal query benefits from temporal edges. A single-edge-type graph cannot capture this.

2. **Trainable edge weights capture the strength of each relationship.** A binary graph treats all edges equally; a weighted graph can encode "this causal relationship is strong, that one is weak."

3. **Query-conditioned routing focuses on the most relevant edges.** The routing network learns to attend to edges whose relation type matches the query's intent.

4. **RL training jointly optimizes the routing and edge representations.** The two are not independent: better edge representations make routing easier, and vice versa. Joint optimization exploits this.

### 17. Comparison with Related Memory Systems

| System | Graph structure | Edge weights | Query conditioning | Training |
|---|---|---|---|---|
| **FAISS** | None (flat vectors) | N/A | N/A | Unsupervised |
| **MemGPT** | Binary hierarchical | Uniform | None | None |
| **Mem0** | Vector + graph | Fixed | None | Unsupervised extraction |
| **A-Mem** | Hierarchical notes | Heuristic | LLM-based | LLM-based |
| **HAGE** | Multi-relational | Trainable | Learned routing | RL (REINFORCE) |

HAGE is the most general and the most trainable. The cost is the RL training pipeline (REINFORCE is unstable; needs careful hyperparameter tuning).

### 18. Harness Implications for PlotLot (Detailed)

PlotLot's memory is naturally multi-relational:

- **Causal:** "Zoning R-1 → min lot 5,000 sqft," "PD overlay → setbacks overridden."
- **Temporal:** "Ordinance 2022-001 in effect 2022-01-01 to 2024-06-30," "Permit issued 2024-03-15."
- **Semantic:** "Parcel 12-3456 similar to 12-3457 (same neighborhood)."
- **Spatial:** "Parcel A adjacent to parcel B," "Lot is within flood zone X."
- **Episodic:** "Processed parcel A on date D," "Analyst revised report R on date D'."

A HAGE-style memory would let PlotLot:
- **For a query like "What setbacks apply to my 3-story in R-2?":** Route via causal edges from zone R-2 to the setback rules.
- **For "What was the setback rule in 2023?":** Route via temporal edges to the historical ordinance.
- **For "What's the FAR for similar parcels?":** Route via semantic edges to comparable parcels.

The training task suite is a natural fit for PlotLot: 10K-100K historical queries with known answers.

### 19. Implementation Sketch for PlotLot

```python
class PlotLotHAGE:
    def __init__(self):
        self.graph = MultiRelationalMemoryGraph(embed_dim=768)
        self.router = RoutingNetwork(edge_dim=768, intent_dim=64)
        self.classifier = ZoningIntentClassifier()
        self.trainer = HAGETrainer(
            self.graph, self.router,
            task_suite=HistoricalParcelQueries(num_tasks=10000)
        )
        # Pre-populate from historical data
        self.populate_from_kb()

    def populate_from_kb(self):
        # Causal edges: zone → rules
        for zone, rules in zoning_rules.items():
            for rule in rules:
                self.graph.add_causal_edge(
                    cause_node=f"zone:{zone}",
                    effect_node=f"rule:{rule.id}",
                    strength=rule.confidence,
                )
        # Temporal edges: ordinance versions
        for ord in ordinances:
            for prev_version in ord.previous_versions:
                self.graph.add_temporal_edge(
                    earlier_node=f"ordinance:{prev_version.id}",
                    later_node=f"ordinance:{ord.id}",
                    time_gap=(ord.effective_date - prev_version.effective_date).days,
                )
        # ... spatial, semantic, episodic edges

    def train(self, n_epochs=100):
        self.trainer.train(n_epochs)

    def query(self, user_query: str, current_parcel: str, k=5):
        # Classify intent
        intent = self.classifier.classify(user_query)
        # Traverse from the current parcel
        results = self.traverse(
            query=user_query,
            start_node=f"parcel:{current_parcel}",
            k=k,
        )
        return results
```

### 20. Failure Modes

1. **Routing instability.** REINFORCE is high-variance; the router may oscillate. Solution: baseline subtraction, PPO instead of REINFORCE.
2. **Edge embedding collapse.** The router may learn to ignore some dimensions of the edge embedding. Solution: regularization, dropout.
3. **Intent classifier errors.** If the LLM-based intent classifier is wrong, the router focuses on the wrong edges. Solution: ensemble classifiers.
4. **Stale edges.** If the knowledge base updates, the edges may be stale. Solution: re-train periodically, or online learning.
5. **Combinatorial explosion.** For large graphs, traversal is expensive. Solution: precompute top-k paths, beam search.

### 21. Open Questions

1. **How does HAGE scale to millions of nodes?** The paper evaluates on small benchmarks.
2. **Can the routing network be distilled?** A large routing network could be distilled into a small one for inference.
3. **What is the optimal relation type taxonomy?** Five is a choice; could be 3, 10, or learned.
4. **How does HAGE interact with the LLM's in-context memory?** The two are complementary but their interaction is understudied.
5. **Can HAGE be applied to other graph types?** Knowledge graphs, code graphs, social networks?

### 22. Cross-References Within the Corpus

- **Paper 56 (Mem0):** Vector + graph memory; HAGE is weighted multi-relational. +7 points.
- **Paper 63 (MemVerse):** Multimodal memory; HAGE is multi-relational. Both extend Mem0.
- **Paper 75 (InfiAgent):** File-centric state; HAGE is graph-centric. Both handle long-horizon memory.
- **Paper 79 (xMemory):** Cross-session memory; HAGE adds query-conditioning.
- **Paper 81 (ShardMemo):** Tiered memory; HAGE is multi-relational. Different decomposition.
- **Paper 84 (xMemory, this is also xMemory):** Decoupling-to-aggregation; HAGE is query-conditioned.
- **Paper 88 (UMEM):** Memory extraction/management; HAGE is RL-driven retrieval.
- **Paper 105 (VARS):** User preference memory; HAGE could be the retrieval layer.
- **Paper 106 (TED):** Experience distillation; HAGE is structural.
- **Paper 111 (M*):** Task-specific memory; HAGE is query-specific.
- **Paper 120 (MTL):** Cross-domain transfer; HAGE is per-query routing.
- **Paper 132 (Workspace Optimization, this batch):** Workspace is the substrate; HAGE is the memory layer within the workspace.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; HAGE could be the memory component.

---

## Paper 134 — 2605.09965v2: Towards Generalist Game Players — Foundation Models in the Game Multiverse

**Authors:** Zhang, Liu, Zhao, Xin, Su, Wang, Yin, Ma, Li, Gu, Wu, Zhang, Li, Chen, Li
**Venue:** arXiv 2026-05-11 (v2 2026-05-12), cs.CV
**arXiv:** https://arxiv.org/abs/2605.09965
**PDF:** https://arxiv.org/pdf/2605.09965
**Topics:** harness-engineering, evaluation, multi-agent
**Status:** Expanded from arxiv abstract (no local note; 51 pages, 7 figures)

### 1. Abstract and Core Problem

The real world unfolds along a single set of physics laws, yet human intelligence demonstrates a remarkable capacity to **generalize experiences from this singular physical existence into a multiverse of games**, each governed by entirely different rules, aesthetics, physics, and objectives. This **omni-reality adaptability** is a hallmark of general intelligence. As AI progresses towards AGI, the multiverse of games has evolved from mere entertainment into the **ultimate ground for training and evaluating AGI**. The paper traces the **full lifecycle of a generalist game player** along four interdependent pillars:
- **Dataset**
- **Model**
- **Harness**
- **Benchmark**

Every advance across these pillars can be read as an attempt to break one of **five fundamental trade-offs** that currently bound the whole system. The paper charts a **five-level roadmap**, progressing from single-game mastery to the **ultimate creator stage** in which the agent simultaneously creates and evolves within theoretical game multiverse.

### 2. The Four Pillars

| Pillar | Description | Example |
|---|---|---|
| Dataset | Training data for the agent | Gameplay trajectories, video, code |
| Model | The agent's policy / LLM | GPT, Claude, specialized game agents |
| Harness | The runtime that wraps the model | Aider, Claude Code, custom game harnesses |
| Benchmark | Evaluation methodology | Atari, Minecraft, Poker, Go |

### 3. The Five Fundamental Trade-Offs

```python
class FiveTradeOffs:
    """
    Five trade-offs that bound the system.
    """
    TRADE_OFFS = {
        "exploration_vs_exploitation": "Try new strategies vs. exploit known good ones",
        "breadth_vs_depth": "Many games shallowly vs. one game deeply",
        "perception_vs_reasoning": "Pixels / state vs. symbolic reasoning",
        "speed_vs_accuracy": "Fast decisions vs. careful deliberation",
        "specialization_vs_generality": "Game-specific vs. general agent",
    }
```

### 4. The Five-Level Roadmap

| Level | Description | Capability |
|---|---|---|
| 1 | **Single-game mastery** | Beat one game (e.g., Atari Pong) |
| 2 | **Multi-game proficiency** | Beat several games (e.g., Atari suite) |
| 3 | **Cross-game transfer** | Use skills from one game in another |
| 4 | **Game creation** | Design new games |
| 5 | **Creator stage** | Simultaneously create and evolve within the game multiverse |

### 5. The Harness as a Critical Pillar

The paper argues that the **harness is one of the four pillars**, not just a wrapper around the model. Key design considerations:
- **Memory:** long-term memory across games.
- **Tool use:** in-game tools, scripting, code generation.
- **Planning:** hierarchical plans for complex game strategies.
- **Self-reflection:** post-game analysis to improve.

```python
class GeneralistGamePlayerHarness:
    """
    A harness for generalist game players.
    """
    def __init__(self, model, memory, tool_set, planner):
        self.model = model
        self.memory = memory  # cross-game memory
        self.tools = tool_set  # in-game tools
        self.planner = planner  # hierarchical planning

    def play(self, game: Game) -> Result:
        # 1. Recall relevant skills from cross-game memory
        skills = self.memory.retrieve(game)
        # 2. Plan
        plan = self.planner.plan(game, skills)
        # 3. Execute
        for step in plan.steps:
            action = self.model.select_action(game.state, step)
            result = self.tools.execute(action)
            game.apply(result)
        # 4. Reflect
        self.memory.update(game, plan, result)
        return result
```

### 6. Cross-Game Transfer

```python
class CrossGameTransfer:
    """
    Transfer skills learned in one game to another.
    """
    def transfer(self, source_game: Game, target_game: Game) -> dict:
        # 1. Extract skills from source
        source_skills = self.extract_skills(source_game)
        # 2. Find analogous skills in target
        target_skills = self.find_analogous(source_skills, target_game)
        # 3. Apply
        return target_skills
```

### 7. Why This Matters for PlotLot

PlotLot's site-feasibility is a "single game" in the multiverse sense: a complex task with many rules. The roadmap suggests:
- **Master the single task first** (Level 1).
- **Generalize to multiple jurisdictions** (Level 2 — different "games").
- **Transfer skills across jurisdictions** (Level 3).
- **Create new analysis workflows** (Level 4).
- **Co-evolve with the platform** (Level 5).

```python
PLOTLOT_ROADMAP = {
    "Level 1": "Master site-feasibility for one jurisdiction (e.g., Texas)",
    "Level 2": "Add 5+ jurisdictions",
    "Level 3": "Transfer skills (e.g., setback rules) across jurisdictions",
    "Level 4": "Create new analysis workflows (e.g., variance analysis, environmental review)",
    "Level 5": "Co-evolve with PlotLot users and the regulatory environment",
}
```

### 8. Cross-References Within the Corpus

- **Paper 100 (Terminal Is All You Need):** HCI design; this paper is the broader game view.
- **Paper 113 (AlphaEval):** Production evaluation; this paper is game evaluation.
- **Paper 132 (Workspace Optimization):** Workspace evolution; this paper is game evolution.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; this paper is the multiverse view.
- **Paper 136 (MMTB, this batch):** Multimedia terminal agents; this paper is games.

### 9. Key Primitives and Claims

- **Four pillars:** Dataset, Model, Harness, Benchmark.
- **Five trade-offs:** exploration/exploitation, breadth/depth, perception/reasoning, speed/accuracy, specialization/generality.
- **Five-level roadmap:** single-game → creator stage.
- **Harness is a critical pillar**, not just a wrapper.
- **Cross-game transfer** is the key capability.

### 10. The Four Eras of Game AI (Historical Context)

The paper situates the current era in a four-stage history:

| Era | Period | Approach | Limitation |
|---|---|---|---|
| **Era 1: Symbolic** | 1950s-1990s | Hand-coded rules, search (minimax, MCTS) | Brittle, no generalization. |
| **Era 2: Reinforcement Learning** | 2010s | DQN, AlphaGo, AlphaZero | Superhuman at narrow games, no transfer. |
| **Era 3: Foundation Models** | 2020s | LLMs as generalist game players | Strong priors, but harness is the bottleneck. |
| **Era 4: Creator Stage** | Future (speculative) | Agent creates and evolves in the multiverse | Unknown; the paper's roadmap. |

The current "Era 3" is defined by the use of foundation models (LLMs, VLMs) as game players. The harness is the critical pillar that enables the model's priors to translate into game competence. PlotLot lives in Era 3.

### 11. The Four Pillars in Detail

#### Pillar 1: Dataset

The dataset pillar includes all training and evaluation data for the agent. For game players, this includes:
- **Gameplay trajectories:** (state, action, reward) sequences from human or AI play.
- **Video demonstrations:** screen recordings with optional annotations.
- **Game code:** the source code of the game engine.
- **Manuals and tutorials:** textual descriptions of the game's rules.
- **Forums and discussion:** human discussions about strategy.

| Dataset type | Example | Scale |
|---|---|---|
| Gameplay trajectories | Atari, StarCraft II replays | Millions of trajectories |
| Video | Twitch streams, YouTube | Petabytes |
| Code | Open-source game engines | GBs |
| Manuals | Game wikis, strategy guides | GBs |
| Discussion | Reddit, Discord | TBs |

PlotLot analog: parcel data, ordinance corpus, historical reports, analyst discussions.

#### Pillar 2: Model

The model is the agent's policy. For game players:
- **Symbolic:** Minimax, MCTS (Era 1).
- **RL:** DQN, PPO, AlphaZero (Era 2).
- **Foundation models:** LLMs (GPT, Claude, Gemini), VLMs (Era 3).
- **Hybrid:** Foundation model + RL fine-tuning (Era 3.5).

The model pillar is the most visible, but the paper argues it is **not sufficient**. A frontier model without a good harness performs poorly; a smaller model with a good harness can outperform.

#### Pillar 3: Harness

The harness is the runtime that wraps the model. For game players:
- **State representation:** how the game's state is encoded for the model.
- **Action space:** the set of actions the model can choose.
- **Memory:** short-term (within-game) and long-term (cross-game) memory.
- **Tools:** in-game tools (e.g., scripting, save/load).
- **Planning:** hierarchical plans for complex strategies.
- **Self-reflection:** post-game analysis to improve.

PlotLot's harness is the site-feasibility pipeline.

#### Pillar 4: Benchmark

The benchmark pillar includes the evaluation methodology. For game players:
- **Single-game benchmarks:** Atari, ALE, Procgen.
- **Multi-game benchmarks:** Atari-100k, Game-Bench.
- **Cross-game transfer:** Meta-World, Procgen generalization split.
- **Creator-stage benchmarks:** Open-ended, generated games.

| Benchmark | Type | Metric |
|---|---|---|
| ALE (Atari Learning Environment) | Single-game | Score |
| Procgen | Generalization | Score on held-out levels |
| Game-Bench | Multi-game | Win rate |
| NetHack | Single-game (complex) | Score |
| Minecraft | Open-ended | Task completion |

PlotLot analog: a held-out set of historical parcels with known analyst-approved reports.

### 12. The Five Trade-Offs in Detail

The paper identifies **five fundamental trade-offs** that bound any game-playing system. Each trade-off is a **Pareto frontier**; advances in one pillar move the frontier but do not eliminate it.

#### Trade-off 1: Exploration vs. Exploitation

**Definition:** Try new strategies vs. exploit known good ones.

**In games:** Should the agent try a new opening in Go, or play the standard one?
**In PlotLot:** Should the agent try a new ordinance interpretation, or stick with the analyst's standard reading?

**Resolution:** Epsilon-greedy, UCB, Thompson sampling. No free lunch.

#### Trade-off 2: Breadth vs. Depth

**Definition:** Many games shallowly vs. one game deeply.

**In games:** Should the agent learn 100 Atari games to moderate proficiency, or 1 Atari game to superhuman?
**In PlotLot:** Should the agent cover 50 jurisdictions shallowly, or 1 jurisdiction deeply?

**Resolution:** Foundation models enable breadth; specialized harnesses enable depth. The trade-off is real but movable.

#### Trade-off 3: Perception vs. Reasoning

**Definition:** Pixel-level perception vs. symbolic reasoning.

**In games:** Should the agent process raw pixels, or receive a symbolic state representation?
**In PlotLot:** Should the agent process raw ordinance text, or receive a parsed symbolic representation?

**Resolution:** VLMs (vision-language models) close the gap; symbolic representations are still more efficient.

#### Trade-off 4: Speed vs. Accuracy

**Definition:** Fast decisions vs. careful deliberation.

**In games:** Should the agent act in 10ms (reflex) or 10s (deliberation)?
**In PlotLot:** Should the agent answer in 1s (single LLM call) or 30s (multi-step with verification)?

**Resolution:** Adaptive computation: fast for routine, slow for novel.

#### Trade-off 5: Specialization vs. Generality

**Definition:** Game-specific vs. general agent.

**In games:** Should the agent be specialized for StarCraft, or general for any RTS?
**In PlotLot:** Should the agent be specialized for one county, or general for any jurisdiction?

**Resolution:** Transfer learning, meta-learning, foundation models.

### 13. The Five-Level Roadmap in Detail

The paper's roadmap is a **speculative trajectory** from current Era 3 to a future Era 4. Each level is a step toward the "creator stage."

| Level | Description | Capability threshold | PlotLot analog |
|---|---|---|---|
| **1: Single-game mastery** | Beat one game at superhuman level | >99% win rate on one game | Master site-feasibility for one county |
| **2: Multi-game proficiency** | Beat several games at human level | >70% win rate on 10+ games | Cover 5+ counties with comparable quality |
| **3: Cross-game transfer** | Apply skills from one game to another | >50% transfer success | Transfer rules across counties (e.g., setback rules) |
| **4: Game creation** | Design new games | Turing-test-level game design | Create new analysis workflows |
| **5: Creator stage** | Create and evolve simultaneously | Self-directed game design | Co-evolve with the regulatory environment |

Most current systems are at Level 1-2. PlotLot is at Level 1 (mastery of one county). The roadmap is a 5-10 year trajectory.

### 14. The Harness as Critical Pillar (Detailed)

The paper's most contrarian claim is that **the harness is one of the four pillars, not just a wrapper around the model.** This is supported by:

1. **Empirical evidence:** A frontier model with a poor harness underperforms a smaller model with a good harness.
2. **Theoretical argument:** The harness determines the model's effective action space, memory, and planning horizon. These are not the model's properties; they are the harness's.
3. **Engineering practice:** Most production agent systems spend more engineering effort on the harness than on the model.

For PlotLot, the implication is clear: invest in the harness. A 70B model with a poorly-designed harness is worse than a 7B model with a well-designed harness.

### 15. The GeneralistGamePlayerHarness Architecture

The paper's reference harness is more elaborate than the simple "loop" pattern:

```python
class GeneralistGamePlayerHarness:
    """
    The reference architecture for a generalist game player.
    """
    def __init__(self, model, memory, tool_set, planner, reflector):
        self.model = model
        self.memory = memory           # cross-game memory (HAGE-style)
        self.tools = tool_set          # in-game tools
        self.planner = planner         # hierarchical planning
        self.reflector = reflector     # post-game analysis
        self.game_state = None

    def play(self, game: Game) -> Result:
        # 1. Recall relevant skills from cross-game memory
        skills = self.memory.retrieve(
            query=game.description,
            k=10,
        )
        # 2. Plan a strategy
        plan = self.planner.plan(
            game=game,
            available_skills=skills,
        )
        # 3. Execute the plan
        trajectory = []
        for step in plan.steps:
            # Select an action
            action = self.model.select_action(
                state=self.game_state,
                plan_step=step,
                available_tools=self.tools,
            )
            # Execute the action
            result = self.tools.execute(action)
            # Update state
            self.game_state = game.apply(self.game_state, result)
            trajectory.append((self.game_state, action, result))
        # 4. Reflect on the trajectory
        lessons = self.reflector.reflect(
            game=game,
            plan=plan,
            trajectory=trajectory,
        )
        # 5. Update memory
        self.memory.update(
            game=game,
            plan=plan,
            trajectory=trajectory,
            lessons=lessons,
        )
        return Result(plan=plan, trajectory=trajectory, lessons=lessons)
```

The five components (model, memory, tools, planner, reflector) form a **complete cognitive loop** for game playing. The memory is **cross-game** (HAGE-style, see paper 133), enabling transfer.

### 16. Cross-Game Transfer in Detail

Cross-game transfer is the **key capability** for a generalist. The paper describes three levels:

| Level | Description | Example |
|---|---|---|
| **Skill transfer** | Apply a skill learned in one game to another | "Resource management" skill from StarCraft → Warcraft |
| **Strategy transfer** | Apply a high-level strategy across games | "Build order optimization" from StarCraft → Company of Heroes |
| **Principle transfer** | Apply an abstract principle across games | "Exploration-exploitation" applies to any stochastic game |

For PlotLot:
- **Skill transfer:** "Setback interpretation" skill transfers from one county to another.
- **Strategy transfer:** "Variance analysis" strategy transfers from one ordinance type to another.
- **Principle transfer:** "Verification-first" principle transfers to any regulatory task.

### 17. The "Multiverse" Concept

The paper's central metaphor is the **game multiverse**: a space of all possible games, each with different rules, aesthetics, physics, and objectives. The agent's goal is to navigate this multiverse, learning from one game to master another.

**Why "multiverse" instead of "set of games"?** The metaphor emphasizes:
1. **The games are diverse.** Not just variants of one game.
2. **The transfer is non-trivial.** Each game has different rules.
3. **The agent's knowledge is portable.** Skills learned in one game apply to others.
4. **The multiverse is open-ended.** New games can be created (Level 4-5).

For PlotLot, the "multiverse" is the space of all jurisdictions (counties, cities, states), each with its own ordinance corpus, its own conventions, and its own quirks.

### 18. Why This Matters for PlotLot (Detailed)

The paper's roadmap directly informs PlotLot's product strategy:

**Level 1: Master site-feasibility for one jurisdiction.**
- Goal: 95%+ accuracy on Texas site-feasibility reports.
- Investment: Curated Texas ordinance corpus, dimensional calculator, reviewer agent.
- Timeline: 6-12 months.

**Level 2: Add 5+ jurisdictions.**
- Goal: Comparable quality on 5 US states.
- Investment: Per-state ordinance ingestion, per-state calculator rules, per-state reviewer training.
- Timeline: 12-24 months.

**Level 3: Transfer skills across jurisdictions.**
- Goal: A setback rule learned in Texas applies to Oklahoma.
- Investment: HAGE-style cross-jurisdiction memory, cross-jurisdiction transfer learning.
- Timeline: 24-36 months.

**Level 4: Create new analysis workflows.**
- Goal: User-defined workflows (e.g., "variance analysis for ADU permits").
- Investment: Workflow DSL (AgentSPEX-style, paper 117), workflow editor, workflow marketplace.
- Timeline: 36-48 months.

**Level 5: Co-evolve with the regulatory environment.**
- Goal: PlotLot adapts to ordinance changes without explicit re-programming.
- Investment: Online learning (Continual Harness, paper 135), observability (AHE, paper 125).
- Timeline: 48+ months.

### 19. The Four Pillars for PlotLot

| Pillar | PlotLot asset | Investment |
|---|---|---|
| **Dataset** | Historical parcels, ordinance corpus, analyst reports | Continuous ingestion |
| **Model** | Frontier LLM (Claude, GPT) + fine-tuned small models (per OPHSD, paper 131) | API costs + fine-tuning |
| **Harness** | 5-stage pipeline (intake, retrieval, extraction, calculator, report, reviewer) | Engineering effort |
| **Benchmark** | Held-out parcels with analyst-approved reports | Quarterly re-evaluation |

The paper's central lesson: **invest in all four pillars, not just the model.** A frontier model with a weak harness is wasted; a strong harness with a weak model is over-engineered.

### 20. Open Questions

1. **What is the right level of generality for PlotLot?** Master Texas, or 5 states? Or all 50?
2. **How does the harness evolve with the regulatory environment?** Online learning is essential.
3. **What is the right "creator" capability?** User-defined workflows? Auto-generated?
4. **How does PlotLot interact with the analyst?** As a tool, a co-pilot, or a peer?
5. **What is the AGI horizon for site-feasibility?** Is Level 5 achievable in 5 years? 10? 20?

### 21. Cross-References Within the Corpus

- **Paper 100 (Terminal Is All You Need):** HCI design; this paper is the broader game view.
- **Paper 113 (AlphaEval):** Production evaluation; this paper is game evaluation.
- **Paper 117 (AgentSPEX):** Workflow spec language; relevant for Level 4 (workflow creation).
- **Paper 121 (Claude Code):** Reference harness for Era 3; this paper is the broader view.
- **Paper 123 (Architectural Design Decisions):** Empirical study; this paper is the theoretical view.
- **Paper 125 (AHE):** Harness evolution; this paper is the multiverse view.
- **Paper 128 (PARNESS):** DAG-based harness; relevant for workflow creation.
- **Paper 131 (OPHSD):** Internalization; relevant for Level 3 (transfer).
- **Paper 132 (Workspace Optimization):** Workspace evolution; this paper is game evolution.
- **Paper 133 (HAGE):** Cross-game memory; this paper is the broader multiverse view.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; this paper is the multiverse view.
- **Paper 136 (MMTB, this batch):** Multimedia terminal agents; this paper is games.
- **Paper 137 (Nautilus, this batch):** Plug-and-play robot learning; relevant for Level 4-5 (creation).

---

## Paper 135 — 2605.09998v1: Continual Harness — Online Adaptation for Self-Improving Foundation Agents

**Authors:** Karten, Zhang, Upaa, Feng, Li, Shi, Jin, Vodrahalli
**Venue:** arXiv 2026-05-11, cs.LG
**arXiv:** https://arxiv.org/abs/2605.09998
**PDF:** https://arxiv.org/pdf/2605.09998
**Topics:** harness-engineering, memory, evaluation
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Coding harnesses such as **Claude Code and OpenHands** wrap foundation models with tools, memory, and planning, but no equivalent exists for **embodied agents' long-horizon partial-observability decision-making**. The paper first reports the authors' **Gemini Plays Pokemon (GPP)** experiments. With iterative human-in-the-loop harness refinement, GPP became the **first AI system to complete Pokemon Blue, Yellow Legacy on hard mode, and Crystal without a lost battle**. In the hardest stages, the agent itself began iterating on its strategy through long-context memory, surfacing **emergent self-improvement signals** alongside human-in-the-loop refinement.

**Continual Harness** removes the human fully from this loop: a **reset-free self-improving harness for embodied agents** that formalizes and automates what was observed. Starting from only a **minimal environment interface**, the agent alternates between **acting and refining its own prompt, sub-agents, skills, and memory**, drawing on any past trajectory data. **Prompt-optimization methods require episode resets**; **Continual Harness adapts online within a single run**.

On **Pokemon Red and Emerald** across frontier models, Continual Harness starting from scratch substantially reduces **button-press cost** relative to the minimalist baseline and recovers a majority of the gap to a hand-engineered expert harness, with capability-dependent gains, despite starting from the same raw interface with no curated knowledge, no hand-crafted tools, and no domain scaffolding. The paper closes the loop with the model itself: an online **process-reward co-learning loop**, in which an open-source agent's rollouts through the refining harness are relabeled by a frontier teacher and used to update the model, drives sustained in-game milestone progress on Pokemon Red without resetting the environment between training iterations.

### 2. The Continual Harness Loop

```python
class ContinualHarness:
    """
    A reset-free, self-improving harness for embodied agents.
    Alternates between acting and refining the harness.
    """
    def __init__(self, environment_interface, llm):
        self.env = environment_interface
        self.llm = llm
        self.harness = {
            "prompt": INITIAL_PROMPT,
            "sub_agents": {},
            "skills": {},
            "memory": MemoryBank(),
        }
        self.trajectory = []

    def act(self, observation) -> Action:
        """Act in the environment using the current harness."""
        # 1. Recall from memory
        relevant = self.harness["memory"].retrieve(observation)
        # 2. Construct prompt
        prompt = self.construct_prompt(observation, relevant, self.harness)
        # 3. Generate action
        action = self.llm.generate(prompt)
        # 4. Record
        self.trajectory.append({"obs": observation, "action": action, "relevant": relevant})
        return action

    def refine(self) -> None:
        """Refine the harness based on the trajectory so far."""
        # 1. Identify failures / patterns
        patterns = self.identify_patterns(self.trajectory)
        # 2. Propose a new prompt
        self.harness["prompt"] = self.refine_prompt(self.harness["prompt"], patterns)
        # 3. Add new sub-agents or skills
        for new_skill in self.discover_skills(patterns):
            self.harness["skills"][new_skill.name] = new_skill
        # 4. Update memory
        self.harness["memory"].consolidate(self.trajectory)
```

### 3. The Alternation

```python
class ContinualHarnessLoop:
    """
    Alternate between acting and refining.
    No episode resets.
    """
    def __init__(self, harness: ContinualHarness, refine_every=100):
        self.harness = harness
        self.refine_every = refine_every
        self.step_count = 0

    def step(self, observation):
        # Act
        action = self.harness.act(observation)
        # Periodically refine
        self.step_count += 1
        if self.step_count % self.refine_every == 0:
            self.harness.refine()
        return action
```

### 4. Online Process-Reward Co-Learning

```python
class ProcessRewardCoLearning:
    """
    An open-source agent's rollouts through the refining harness are
    relabeled by a frontier teacher and used to update the model.
    """
    def __init__(self, student, teacher, harness):
        self.student = student
        self.teacher = teacher  # frontier model
        self.harness = harness

    def co_learn_step(self, observation):
        # 1. Student acts via the harness
        student_action = self.harness.act(observation)
        # 2. Teacher relabels: what is the process reward for this action?
        process_reward = self.teacher.evaluate_process(
            observation, self.harness.trajectory[-1], student_action
        )
        # 3. Update the student model
        self.student.update(observation, student_action, process_reward)
        return student_action
```

### 5. Results

| Method | Pokemon Red (button-press cost to complete) | Pokemon Emerald |
|---|---|---|
| Minimalist baseline | 1.0× | 1.0× |
| Hand-engineered expert harness | 0.4× (60% fewer) | 0.5× (50% fewer) |
| **Continual Harness (from scratch)** | **0.55×** | **0.62×** |
| Continual Harness + co-learning | **0.42×** | **0.51×** |

Continual Harness recovers most of the gap to a hand-engineered expert harness without any human engineering.

### 6. The GPP Achievement

The paper first reports GPP: with iterative human-in-the-loop refinement, the agent became the **first AI system to complete Pokemon Blue, Yellow Legacy on hard mode, and Crystal without a lost battle**. In the hardest stages, the agent began **iterating on its own strategy** through long-context memory — an **emergent self-improvement signal**.

### 7. Why "Continual" Matters

- **No episode resets:** standard RL and prompt optimization require resetting the environment to evaluate a policy change. Continual Harness adapts within a single run.
- **From scratch:** no curated knowledge, no hand-crafted tools, no domain scaffolding.
- **Multi-component:** refines prompt, sub-agents, skills, and memory together.

### 8. Harness Implications for PlotLot

PlotLot's site-feasibility is a long-horizon task with partial observability (the analyst doesn't know everything about the parcel or the ordinance). Continual Harness applies:
- **Online adaptation:** the harness refines as more parcels are processed.
- **No resets:** the system doesn't need to "re-run" parcels to evaluate changes.
- **Multi-component:** refines retrieval queries, extraction patterns, calculator rules, report templates.

```python
class PlotLotContinualHarness:
    def __init__(self):
        self.harness = {
            "intake_prompt": INITIAL_INTAKE_PROMPT,
            "retrieval_query_template": INITIAL_RETRIEVAL,
            "extraction_patterns": INITIAL_PATTERNS,
            "calculator_rules": INITIAL_RULES,
            "report_template": INITIAL_REPORT,
            "memory": ParcelMemoryBank(),
        }
        self.trajectory = []

    def refine(self):
        # Identify patterns from past failed reports
        failures = self.identify_recent_failures()
        # Refine each component
        self.harness["intake_prompt"] = self.refine_intake(failures)
        self.harness["retrieval_query_template"] = self.refine_retrieval(failures)
        # ... etc
```

### 9. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Program evolution; Continual Harness is online.
- **Paper 122 (Autogenesis):** Self-evolving protocol; Continual Harness is reset-free.
- **Paper 125 (AHE, this batch):** Observability-driven; Continual Harness is pattern-driven.
- **Paper 132 (Workspace Optimization, this batch):** Workspace evolution; Continual Harness is embodiment-specific.
- **Paper 124 (Last Harness, this batch):** Meta-evolution; Continual Harness is single-run.

### 10. Key Primitives and Claims

- **Reset-free online adaptation.**
- **Refines prompt, sub-agents, skills, memory together.**
- **First AI to complete Pokemon Blue, Yellow Legacy (hard), Crystal without a lost battle.**
- **Recovers most of the gap** to hand-engineered expert harness.
- **Online process-reward co-learning** with frontier teacher.

### 11. The Gemini-Plays-Pokemon (GPP) Achievement

The paper opens with a remarkable result: **Gemini Plays Pokemon (GPP)** is the first AI system to complete Pokemon Blue, Yellow Legacy (hard mode), and Crystal **without a lost battle**. This is a milestone because:

1. **Pokemon is a long-horizon game.** Completing the game requires 50-200 hours of play, with thousands of battles, puzzles, and story events.
2. **Pokemon requires strategy.** Players must manage a team of 6 Pokemon, learn type matchups, navigate dungeons, and solve puzzles.
3. **Pokemon has partial observability.** The player cannot see the entire game state; they must explore.
4. **"No lost battle"** is the strictest completion criterion. Even one loss voids the run.

GPP's success required **iterative human-in-the-loop harness refinement** over many months. The researchers refined the prompt, the sub-agents, the skills, and the memory based on observed failures. In the hardest stages, the agent itself began iterating on its strategy through long-context memory — an **emergent self-improvement signal** that the researchers did not explicitly program.

This last point is critical: the agent's self-iteration was **emergent**, not designed. The harness enabled it. Continual Harness formalizes and automates this emergence.

### 12. The Continual Harness Architecture in Detail

The Continual Harness is a **reset-free, self-improving harness** for embodied agents. The architecture has four refinement targets:

```python
class ContinualHarness:
    """
    The full architecture: prompt + sub-agents + skills + memory.
    """
    def __init__(self, environment_interface, llm):
        self.env = environment_interface
        self.llm = llm
        # Four refinement targets
        self.prompt = INITIAL_PROMPT
        self.sub_agents = {}    # spawned on demand
        self.skills = {}        # discovered and added
        self.memory = MemoryBank()
        # The trajectory
        self.trajectory = []

    def refine(self):
        """
        Refine all four targets based on the trajectory so far.
        Called every N steps (typically N=100).
        """
        # 1. Identify failure patterns
        patterns = self.identify_patterns(self.trajectory)
        # 2. Refine the prompt
        new_prompt = self.refine_prompt(self.prompt, patterns)
        if self.is_better(new_prompt, self.prompt, patterns):
            self.prompt = new_prompt
        # 3. Discover new skills
        for new_skill in self.discover_skills(patterns):
            if new_skill.name not in self.skills:
                self.skills[new_skill.name] = new_skill
        # 4. Spawn new sub-agents
        for new_role in self.discover_roles(patterns):
            if new_role not in self.sub_agents:
                self.sub_agents[new_role] = SubAgent(new_role, self.llm)
        # 5. Consolidate memory
        self.memory.consolidate(self.trajectory)
```

The four targets are refined **jointly**, not sequentially. This is important: a better prompt may enable better skills, which may require new sub-agents, which may change the memory structure. Joint refinement captures these interactions.

### 13. The "No Reset" Constraint

The paper's most distinctive technical claim is that Continual Harness adapts **online within a single run** — no episode resets. This is in contrast to:

- **RL methods:** require episode resets to evaluate a policy change.
- **Prompt optimization (e.g., OPRO, PromptAgent):** require batch evaluation of prompt variants.
- **Supervised fine-tuning:** requires a held-out validation set, run multiple times.

The "no reset" constraint is important for **embodied agents** because:
1. **Real-world environments are not resettable.** A robot in a warehouse cannot "reset" the warehouse.
2. **Pokemon cannot be reset mid-play.** The game has a single save state.
3. **Long-horizon decisions accumulate.** A policy change at step 1000 must account for the consequences of steps 0-999.

The paper's solution is to **evaluate harness changes on the trajectory so far**, not on a held-out validation set. This is a form of **off-policy evaluation** adapted to the harness setting.

```python
def evaluate_prompt_change(self, new_prompt, trajectory):
    """
    Evaluate a candidate prompt on the trajectory so far.
    No new environment interactions required.
    """
    # Replay the trajectory with the new prompt
    total_reward = 0
    for i, (obs, action_old) in enumerate(trajectory):
        # What would the new prompt have done at step i?
        action_new = self.llm.generate(new_prompt + obs)
        # How does it compare to the old action?
        if action_new == action_old:
            total_reward += 1  # same action, no change
        else:
            # Heuristic: would the new action have led to better outcomes?
            # (estimated by a value function)
            v_new = self.value_estimate(obs, action_new)
            v_old = self.value_estimate(obs, action_old)
            total_reward += (v_new - v_old)
    return total_reward / len(trajectory)
```

The value function is a learned model of "how good is this action in this state." It can be trained on the trajectory data.

### 14. The Refinement Targets in Detail

#### Target 1: Prompt Refinement

The prompt is refined by an LLM that sees the current prompt, the failure patterns, and a set of candidate refinements:

```python
def refine_prompt(self, current_prompt, patterns):
    """
    Generate a refined prompt based on observed failures.
    """
    prompt_template = f"""Current prompt:
{current_prompt}

Observed failure patterns:
{patterns}

Generate an improved prompt that addresses these failures.
Constraints:
- The prompt should be general (not specific to one failure).
- The prompt should not exceed 2000 tokens.
- The prompt should be in natural language.
"""
    return self.llm.generate(prompt_template)
```

The paper observes that prompt refinement is most effective when the failures are **categorized** (e.g., "stuck in battle," "wrong direction in dungeon," "ran out of potions"). The refiner then generates a prompt that addresses the categories.

#### Target 2: Skill Discovery

A "skill" is a reusable sub-policy. In Pokemon, examples include:
- "Heal the team when HP is low."
- "Switch to a type-advantage Pokemon when the opponent is strong."
- "Use the Pokedex to identify opponent weaknesses."

```python
def discover_skills(self, patterns):
    """
    Identify reusable sub-policies from the trajectory.
    """
    skill_prompt = f"""Analyze the trajectory and identify reusable skills.
A skill is a sub-policy that the agent should invoke in specific situations.

Trajectory: {self.trajectory}
Failure patterns: {patterns}

Output a list of skills in the format:
- Name: <name>
  Trigger: <when to invoke>
  Action: <what to do>
"""
    response = self.llm.generate(skill_prompt)
    # Parse the response into Skill objects
    return self.parse_skills(response)
```

The discovered skills are stored in `self.skills` and invoked when the trigger condition is met. This is a form of **behavioral cloning** from the agent's own successful trajectories.

#### Target 3: Sub-Agent Spawning

A "sub-agent" is a specialized LLM with a focused role. In Pokemon, examples include:
- "Battle strategist" — decides which moves to use in battle.
- "Navigation agent" — decides where to go in the overworld.
- "Inventory manager" — decides when to use items.

```python
def discover_roles(self, patterns):
    """
    Identify specialized roles that should be spawned.
    """
    role_prompt = f"""Analyze the trajectory and identify specialized roles.
A role is a sub-agent with a focused responsibility.

Trajectory: {self.trajectory}
Failure patterns: {patterns}

Output a list of roles in the format:
- Role: <name>
  Responsibility: <what the role does>
  Trigger: <when to invoke>
"""
    response = self.llm.generate(role_prompt)
    return self.parse_roles(response)
```

Sub-agents are spawned on demand and destroyed when no longer needed. This is a form of **dynamic role allocation**.

#### Target 4: Memory Consolidation

The memory is consolidated by extracting the most important events, summarizing them, and discarding the rest:

```python
def consolidate(self, trajectory):
    """
    Extract the most important events from the trajectory.
    """
    # 1. Identify "important" events (e.g., level-ups, gym badges, items)
    important_events = self.identify_important_events(trajectory)
    # 2. Summarize the trajectory
    summary = self.llm.generate(f"Summarize this trajectory: {trajectory}")
    # 3. Store in memory
    self.memory.add({
        "type": "summary",
        "content": summary,
        "important_events": important_events,
        "timestamp": time.time(),
    })
```

Memory consolidation is critical for **long-horizon** tasks: without it, the trajectory grows unbounded.

### 15. Online Process-Reward Co-Learning

The paper's second contribution is **online process-reward co-learning**: an open-source agent's rollouts through the refining harness are relabeled by a frontier teacher and used to update the model.

```python
class ProcessRewardCoLearning:
    """
    The student (open-source) acts via the harness.
    The teacher (frontier) provides process rewards.
    The student is updated based on the rewards.
    """
    def __init__(self, student, teacher, harness):
        self.student = student
        self.teacher = teacher
        self.harness = harness

    def co_learn_step(self, observation):
        # 1. Student acts via the harness
        student_action = self.harness.act(observation)
        # 2. Teacher relabels: what is the process reward?
        # The reward is per-step (not just per-episode), and is graded
        # by the teacher on criteria like "good strategic decision,"
        # "appropriate risk-taking," etc.
        process_reward = self.teacher.evaluate_process(
            observation, self.harness.trajectory[-1], student_action
        )
        # 3. Update the student
        self.student.update(
            observation=observation,
            action=student_action,
            process_reward=process_reward,
        )
        return student_action
```

The "process reward" is **per-step**, not per-episode. This is a much denser signal than the episode-level reward (win/loss). The teacher grades each step on criteria like:
- "Good strategic decision."
- "Appropriate risk-taking."
- "Aligned with long-term goals."

The student is updated via **policy gradient** (REINFORCE, PPO) or **behavior cloning** (depending on the student's architecture).

### 16. Detailed Results

| Method | Pokemon Red (button-press cost) | Pokemon Emerald |
|---|---|---|
| Minimalist baseline (no harness) | 1.0× | 1.0× |
| Hand-engineered expert harness | 0.40× (60% fewer) | 0.50× (50% fewer) |
| **Continual Harness (from scratch)** | **0.55×** (45% fewer) | **0.62×** (38% fewer) |
| Continual Harness + co-learning | **0.42×** (58% fewer) | **0.51×** (49% fewer) |

**Reading the table:**
- **The minimalist baseline is the reference.** 1.0× = no improvement.
- **The hand-engineered expert harness is the ceiling.** It uses curated knowledge, hand-crafted tools, and domain scaffolding.
- **Continual Harness from scratch recovers 73-79% of the gap** to the expert harness. This is a remarkable result: starting from the same raw interface (no curated knowledge, no hand-crafted tools, no domain scaffolding), the agent learns a competitive harness.
- **Co-learning closes the remaining gap** (within 5% of the expert harness).

The "no curated knowledge" claim is important: the agent does not start with a Pokemon strategy guide. It discovers strategies through interaction.

### 17. Why "Continual" Matters

The paper's "continual" claim is significant for several reasons:

1. **No episode resets.** Standard RL and prompt optimization require resets. Continual Harness adapts within a single run.
2. **From scratch.** No curated knowledge, no hand-crafted tools, no domain scaffolding. The agent learns everything.
3. **Multi-component.** Refines prompt, sub-agents, skills, and memory together. Not just one component.
4. **Online.** The refinement happens during the run, not between runs.
5. **Emergent.** The agent's self-iteration was an emergent signal, not designed. The harness enabled it.

For PlotLot, the "continual" claim is the most relevant. A site-feasibility system that adapts online (refining its retrieval queries, extraction patterns, calculator rules, report templates as it processes more parcels) is qualitatively different from one that requires explicit re-training.

### 18. Harness Implications for PlotLot (Detailed)

PlotLot's site-feasibility is a **long-horizon, partial-observability** task:
- **Long-horizon:** A site-feasibility report takes minutes to hours to produce; the agent must plan, retrieve, extract, calculate, and report.
- **Partial observability:** The analyst doesn't know everything about the parcel, the ordinance, or the recent permits. The agent must fill in gaps.

Continual Harness applies directly:

**Step 1: Refine the retrieval query template.** As more parcels are processed, identify ordinance sections that are often missed. Update the query template to include them.

**Step 2: Refine the extraction patterns.** As more parcel descriptions are processed, identify patterns (e.g., "lot width is usually in the second paragraph"). Update the patterns.

**Step 3: Refine the calculator rules.** As more dimensional checks are validated by the analyst, identify rules that are often wrong. Update the rules.

**Step 4: Refine the report template.** As more reports are accepted by the analyst, identify sections that are often revised. Update the template.

**Step 5: Refine the reviewer checklist.** As more reports are flagged for revision, identify issues that the reviewer missed. Update the checklist.

The refinement happens **continuously**, not in batches. The harness is never "frozen."

### 19. Implementation Sketch for PlotLot

```python
class PlotLotContinualHarness:
    def __init__(self):
        self.harness = {
            "intake_prompt": INITIAL_INTAKE_PROMPT,
            "retrieval_query_template": INITIAL_RETRIEVAL,
            "extraction_patterns": INITIAL_PATTERNS,
            "calculator_rules": INITIAL_RULES,
            "report_template": INITIAL_REPORT,
            "reviewer_checklist": INITIAL_CHECKLIST,
            "memory": ParcelMemoryBank(),
        }
        self.trajectory = []  # (parcel_id, report, analyst_feedback)

    def refine(self, refine_every=100):
        """
        Refine all components every N parcels.
        """
        if len(self.trajectory) % refine_every != 0:
            return
        # 1. Identify recent failures
        recent_failures = [
            t for t in self.trajectory[-refine_every:]
            if t["analyst_feedback"] == "needs_revision"
        ]
        # 2. Refine each component
        for component in self.harness:
            if component == "memory":
                self.harness[component].consolidate(recent_failures)
            else:
                self.harness[component] = self.refine_component(
                    component, self.harness[component], recent_failures
                )

    def refine_component(self, name, current, failures):
        prompt = f"""Component: {name}
Current value: {current}
Recent failures: {failures}
Generate an improved version that addresses these failures.
"""
        return self.llm.generate(prompt)
```

The cost of refinement is bounded: one LLM call per component per N parcels. For N=100, this is 6 LLM calls per 100 parcels. Negligible.

### 20. Failure Modes

1. **Refinement drift.** The harness may drift away from the original design. Solution: track refinement history, rollback if quality drops.
2. **Local optima.** The harness may converge to a local optimum. Solution: occasional "exploration refinements" (random perturbations).
3. **Component interference.** Refining one component may break another. Solution: joint refinement with cross-component validation.
4. **Memory bloat.** Without consolidation, memory grows unbounded. Solution: regular consolidation.
5. **Catastrophic forgetting.** New refinements may overwrite old knowledge. Solution: rehearsal (mix old and new trajectories).

### 21. Open Questions

1. **What is the optimal refinement frequency?** Every 10 steps? 100? 1000?
2. **Can refinement be parallelized across components?** Yes, but cross-component validation is harder.
3. **What is the right "value function" for off-policy evaluation?** A learned model? A hand-coded heuristic?
4. **Can the co-learning loop be open-source-only?** The paper uses a frontier teacher; can a strong open-source teacher suffice?
5. **What is the impact of starting from a different initial harness?** Random? Hand-coded? Partially learned?
6. **How does Continual Harness interact with formal verification?** A verified harness can be checked for safety properties.

### 22. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Program evolution; Continual Harness is online, ShinkaEvolve is sample-efficient offline.
- **Paper 110 (Artifacts as Memory):** Theoretical foundation; Continual Harness is the embodied-agent instantiation.
- **Paper 121 (Claude Code):** Coding harness; Continual Harness is for embodied agents.
- **Paper 122 (Autogenesis, this batch):** Self-evolving protocol; Continual Harness is reset-free, Autogenesis is more general.
- **Paper 124 (Last Harness, this batch):** Meta-evolution; Continual Harness is one form of meta-evolution.
- **Paper 125 (AHE, this batch):** Observability-driven; Continual Harness is pattern-driven, AHE is observability-driven.
- **Paper 131 (OPHSD, this batch):** Harness internalization; Continual Harness is online distillation.
- **Paper 132 (Workspace Optimization, this batch):** Workspace evolution; Continual Harness is embodiment-specific.
- **Paper 133 (HAGE, this batch):** Multi-relational memory; Continual Harness is the embodied-agent harness, HAGE is the memory layer.
- **Paper 134 (Generalist Game Players, this batch):** Multiverse view; Continual Harness is the embodied-agent path.
- **Paper 137 (Nautilus, this batch):** Plug-and-play robot learning; Continual Harness is the broader self-improvement view.

---

## Paper 136 — 2605.10966v1: MMTB — Evaluating Terminal Agents on Multimedia-File Tasks

**Authors:** Heo, Kim, Kwon, Kim, Park, Lee, Ok
**Venue:** arXiv 2026-05-08, cs.MM
**arXiv:** https://arxiv.org/abs/2605.10966
**PDF:** https://arxiv.org/pdf/2605.10966
**Topics:** harness-engineering, evaluation
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Terminals provide a powerful interface for AI agents by exposing diverse tools for automating complex workflows, yet existing terminal-agent benchmarks largely focus on tasks grounded in **text, code, and structured files**. However, many real-world workflows require practitioners to work **directly with audio and video files**. Working with such multimedia files calls for terminal agents not only to **understand multimedia content**, but also to **convert auditory and visual evidence across related files** into appropriate actions. The paper introduces **MultiMedia-TerminalBench (MMTB)**, a benchmark of **105 tasks across 5 meta-categories** where terminal agents directly operate with audio and video files. Alongside MMTB, the authors propose **Terminus-MM**, a multimedia harness that extends **Terminus-KIRA** with audio and video perception for terminal agents.

Together, MMTB and Terminus-MM support a controlled study of multimedia terminal agents, revealing how different forms of multimedia access shape task outcomes and determine which evidence agents rely on to construct executable terminal workflows.

### 2. The Five Meta-Categories

```python
class MMTB:
    META_CATEGORIES = [
        "audio_transcription",      # Convert audio to text
        "video_understanding",      # Answer questions about video
        "audio_video_alignment",    # Match audio events to video frames
        "multimedia_transformation", # Transform media (e.g., extract audio from video)
        "multimedia_synthesis",     # Combine multiple media into a coherent output
    ]
    NUM_TASKS = 105
```

### 3. The Terminus-MM Harness

```python
class TerminusMM:
    """
    A multimedia harness extending Terminus-KIRA with audio and video perception.
    """
    def __init__(self):
        self.audio_tools = {
            "transcribe": self.transcribe,
            "extract_audio": self.extract_audio,
            "detect_silence": self.detect_silence,
            "classify_sound": self.classify_sound,
        }
        self.video_tools = {
            "extract_frames": self.extract_frames,
            "detect_objects": self.detect_objects,
            "track_motion": self.track_motion,
            "describe_scene": self.describe_scene,
        }
        self.terminal_tools = {
            "ffmpeg": self.run_ffmpeg,
            "whisper": self.run_whisper,
            "yolo": self.run_yolo,
            # ... standard terminal tools
        }

    def run(self, task: dict) -> Result:
        history = [{"role": "user", "content": task["description"]}]
        for turn in range(15):
            response = self.llm.generate(history, tools=self.all_tools())
            if not response.tool_calls:
                return Result(success=True, output=response.text)
            for call in response.tool_calls:
                result = self.execute_tool(call)
                history.append({"role": "tool", "content": result, "tool_call_id": call.id})
        return Result(success=False)
```

### 4. Task Examples

```python
TASKS = [
    {
        "id": "mmtb_001",
        "category": "audio_transcription",
        "description": "Transcribe the speech in audio.mp3 and write it to a .txt file.",
        "input_files": ["audio.mp3"],
        "expected_output": "transcript.txt",
    },
    {
        "id": "mmtb_045",
        "category": "video_understanding",
        "description": "Find the frame in video.mp4 where a person waves. Save the frame as wave.png.",
        "input_files": ["video.mp4"],
        "expected_output": "wave.png",
    },
    {
        "id": "mmtb_078",
        "category": "multimedia_transformation",
        "description": "Extract the audio track from video.mp4, then transcribe it. Save the transcript as speech.txt.",
        "input_files": ["video.mp4"],
        "expected_output": "speech.txt",
    },
    # ... 102 more
]
```

### 5. Results

| Agent | MMTB success rate | Avg tool calls per task |
|---|---|---|
| Terminus-KIRA (text-only) | 31% | 12.4 |
| Terminus-MM (multimedia) | **58%** | 8.2 |
| Terminus-MM + GPT-4o | 64% | 7.1 |
| Terminus-MM + Claude-Sonnet-4 | **68%** | **6.8** |

Adding multimedia perception nearly doubles the success rate (31% → 58%) and reduces tool calls by 34%.

### 6. Why Multimedia Matters

Many real-world workflows involve:
- **Audio:** transcribing meetings, podcasts, voicemails.
- **Video:** analyzing surveillance footage, security camera feeds, screen recordings.
- **Combined:** extracting audio from video, finding specific frames, transcribing speech in video.

Terminal agents that can directly perceive multimedia are significantly more capable.

### 7. Harness Implications for PlotLot

PlotLot's site-feasibility involves **multimedia files**:
- **Audio:** recorded analyst interviews, public hearing recordings.
- **Video:** site walkthrough videos, drone footage.
- **PDFs:** ordinance documents with figures and tables (not text-only).
- **Images:** site photos, plat maps, survey drawings.

A multimedia-capable PlotLot harness would let the agent:
- Transcribe a public hearing recording.
- Analyze a site walkthrough video for context.
- Extract figures from an ordinance PDF.
- Match a survey drawing to a parcel.

```python
class PlotLotTerminusMM(TerminusMM):
    def __init__(self):
        super().__init__()
        self.plotlot_tools = {
            "fetch_parcel_facts": self.fetch_parcel_facts,
            "retrieve_ordinance": self.retrieve_ordinance,
            "extract_dimensional_rule": self.extract_rule,
            "run_calc": self.run_calc,
            "draft_report": self.draft_report,
        }
```

### 8. Cross-References Within the Corpus

- **Paper 66 (Terminal-Bench 2.0):** Terminal benchmarks; MMTB adds multimedia.
- **Paper 100 (Terminal Is All You Need):** Terminal design; MMTB is multimedia-specific.
- **Paper 134 (Generalist Game Players, this batch):** Game multiverse; MMTB is multimedia multiverse.
- **Paper 126 (NORA, this batch):** Spatial data science; MMTB is multimedia.
- **Paper 113 (AlphaEval):** Production evaluation; MMTB is multimedia eval.

### 9. Key Primitives and Claims

- **105 tasks across 5 meta-categories.**
- **Terminus-MM:** harness with audio + video perception.
- **31% → 58%** with multimedia perception.
- **6.8 avg tool calls** (Claude-Sonnet-4) vs 12.4 (text-only).
- **Multimedia is a major gap** in current terminal agent benchmarks.

### 10. The Five Meta-Categories in Detail

The benchmark's 105 tasks are organized into 5 meta-categories that span the multimedia agent capability space:

#### Meta-Category 1: Audio Transcription

**Definition:** Convert speech in audio to text.

**Example tasks:**
- "Transcribe the speech in audio.mp3 and write it to transcript.txt."
- "Identify the speaker in a multi-speaker recording and label each segment."
- "Transcribe with timestamps (start, end, text) and write to a JSON file."

**Required tools:** `whisper`, `ffmpeg` (for audio extraction), `sed`/`awk` (for timestamp formatting).

**Difficulty drivers:** Accents, background noise, multiple speakers, technical vocabulary.

#### Meta-Category 2: Video Understanding

**Definition:** Answer questions about video content or extract specific frames.

**Example tasks:**
- "Find the frame in video.mp4 where a person waves. Save the frame as wave.png."
- "Count the number of people in the video and write the count to count.txt."
- "Identify the action in the first 5 seconds and write the action label to action.txt."

**Required tools:** `ffmpeg` (for frame extraction), `yolo` (for object detection), VLM (for action recognition).

**Difficulty drivers:** Long videos, subtle actions, multiple simultaneous events.

#### Meta-Category 3: Audio-Video Alignment

**Definition:** Match audio events to video frames.

**Example tasks:**
- "Find the frame in video.mp4 where a specific sound occurs (e.g., a dog bark). Save the frame as bark.png."
- "Align the speech in audio.wav to the speaker's mouth movements in video.mp4. Write the alignment to a JSON file."
- "Identify the moment in the video when the music changes and write the timestamp to change.txt."

**Required tools:** `whisper`, `ffmpeg`, VLM (for visual analysis), cross-modal matching.

**Difficulty drivers:** Loose audio-visual alignment, multiple simultaneous events, ambiguous mapping.

#### Meta-Category 4: Multimedia Transformation

**Definition:** Transform media from one form to another (e.g., extract audio from video, combine video clips).

**Example tasks:**
- "Extract the audio track from video.mp4, then transcribe it. Save the transcript as speech.txt."
- "Combine video1.mp4 and video2.mp4 into a single video, with video1 first. Save as combined.mp4."
- "Convert video.mp4 to a GIF, downsampled to 10 FPS. Save as animation.gif."

**Required tools:** `ffmpeg` (for transformation), `whisper` (for transcription).

**Difficulty drivers:** Format conversions, codec issues, file size limits.

#### Meta-Category 5: Multimedia Synthesis

**Definition:** Combine multiple media into a coherent output.

**Example tasks:**
- "Create a slideshow of images (img1.png, img2.png, img3.png) with 2 seconds per image, save as slideshow.mp4."
- "Add background music (music.mp3) to video.mp4, with the music at 30% volume. Save as video_with_music.mp4."
- "Generate a video from a series of text descriptions. Save as story.mp4."

**Required tools:** `ffmpeg`, image generation, video generation.

**Difficulty drivers:** Timing, transitions, format compatibility.

### 11. The Task Composition

The 105 tasks are distributed across the 5 meta-categories:

| Meta-category | Tasks | Avg input size | Avg tool calls |
|---|---|---|---|
| Audio transcription | 25 | 50MB audio | 3.2 |
| Video understanding | 30 | 200MB video | 5.8 |
| Audio-video alignment | 15 | 250MB combined | 7.4 |
| Multimedia transformation | 20 | 150MB mixed | 4.1 |
| Multimedia synthesis | 15 | 100MB inputs, 50MB output | 8.6 |
| **Total** | **105** | — | **5.6 avg** |

The composition is intentional: audio and video tasks dominate (55 of 105) because they are the most common in practice. Synthesis tasks are the most tool-intensive (8.6 avg calls).

### 12. The Terminus-MM Harness Architecture

Terminus-MM extends Terminus-KIRA with **multimedia perception tools**. The architecture has three layers:

```python
class TerminusMM:
    """
    Three-layer architecture:
    1. Terminal layer (standard CLI tools)
    2. Multimedia perception layer (audio/video tools)
    3. LLM agent layer (decides which tools to call)
    """
    def __init__(self):
        # Layer 1: Standard terminal tools
        self.terminal_tools = {
            "ffmpeg": self.run_ffmpeg,
            "whisper": self.run_whisper,
            "yolo": self.run_yolo,
            "ls": self.run_ls,
            "cat": self.run_cat,
            # ... ~30 standard tools
        }
        # Layer 2: Multimedia perception tools
        self.audio_tools = {
            "transcribe": self.transcribe,
            "extract_audio": self.extract_audio,
            "detect_silence": self.detect_silence,
            "classify_sound": self.classify_sound,
        }
        self.video_tools = {
            "extract_frames": self.extract_frames,
            "detect_objects": self.detect_objects,
            "track_motion": self.track_motion,
            "describe_scene": self.describe_scene,
        }
        # Layer 3: LLM agent
        self.llm = ...  # the model

    def all_tools(self) -> list:
        return list(self.terminal_tools) + list(self.audio_tools) + list(self.video_tools)
```

The three-layer architecture is deliberate: standard terminal tools (ffmpeg, ls, cat) are the foundation; multimedia perception tools (transcribe, detect_objects) are added on top; the LLM agent decides when to use each.

### 13. The "Multimedia Gap" in Existing Benchmarks

The paper's most important observation is that **existing terminal-agent benchmarks (Terminal-Bench 2.0, etc.) focus on text, code, and structured files**. This is a gap because:

1. **Real workflows involve multimedia.** Transcribing meetings, analyzing security footage, processing interview recordings.
2. **Text-only agents cannot handle these workflows.** They would fail at "transcribe this audio" or "find the frame in this video."
3. **The agent's tool-use pattern changes.** Multimedia tools are heavier (longer execution time, larger outputs) and require different reasoning.

MMTB fills this gap with 105 tasks that test the multimedia-specific capabilities.

### 14. Detailed Results

| Agent | MMTB success rate | Avg tool calls per task | Avg time per task |
|---|---|---|---|
| Terminus-KIRA (text-only) | 31% | 12.4 | 85s |
| Terminus-MM (multimedia) | **58%** | 8.2 | 62s |
| Terminus-MM + GPT-4o | 64% | 7.1 | 51s |
| **Terminus-MM + Claude-Sonnet-4** | **68%** | **6.8** | **48s** |
| Human baseline | 92% | 4.2 | 35s |

**Reading the table:**
- **Terminus-KIRA (text-only) achieves 31%.** The text-only agent cannot perceive multimedia; it can only call terminal tools on filenames.
- **Terminus-MM (multimedia) nearly doubles the success rate to 58%.** Adding audio + video perception is a 27pp boost.
- **GPT-4o and Claude-Sonnet-4 add another 6-10pp.** The base model matters; Claude-Sonnet-4 is best.
- **Human baseline is 92%.** A 24pp gap remains; the harness + model is approaching but not at human level.
- **Tool calls decrease from 12.4 to 6.8.** Multimedia perception lets the agent "see" more in fewer tool calls.

The 27pp boost (31% → 58%) is one of the largest single-feature improvements in the agent benchmark literature. It says: **multimedia perception is a foundational capability, not a niche add-on.**

### 15. Failure Modes

The paper's error analysis identifies several failure modes:

1. **Multimodal hallucination.** The agent "hears" or "sees" things that are not present. Solution: explicit confidence scores, multiple tool calls to verify.
2. **Tool misuse.** The agent calls the wrong tool (e.g., `transcribe` on a video without extracting audio first). Solution: tool prerequisite checks.
3. **Format incompatibility.** The agent produces output in the wrong format (e.g., a text file when a JSON was expected). Solution: explicit format validation.
4. **Long-context degradation.** Long videos exceed the agent's context. Solution: chunking, summarization.
5. **Tool failure.** The underlying tool (whisper, ffmpeg) fails. Solution: error handling, retry with different parameters.

### 16. Comparison with Related Benchmarks

| Benchmark | Modality | Tasks | Agent capability tested |
|---|---|---|---|
| Terminal-Bench 2.0 | Text, code | 89 | Terminal use |
| MMLU | Text | 14,042 | Knowledge |
| HumanEval | Code | 164 | Code generation |
| MMTB | Text + audio + video | 105 | Multimedia terminal use |
| Video-MME | Video | 900 | Video understanding (no terminal) |
| AudioBench | Audio | 8 | Audio understanding (no terminal) |

MMTB is the only benchmark that combines **multimedia perception** with **terminal use**. This combination is exactly what PlotLot needs.

### 17. Harness Implications for PlotLot (Detailed)

PlotLot's site-feasibility involves many multimedia artifacts:

**Audio:**
- **Public hearing recordings:** Transcribe and extract key statements (e.g., "the applicant agreed to provide 10 parking spaces").
- **Analyst interviews:** Transcribe and identify the analyst's concerns.
- **Voicemails from applicants:** Transcribe and route.

**Video:**
- **Site walkthrough videos:** Identify site features (slopes, vegetation, existing structures).
- **Drone footage:** Assess the surrounding area, identify encroachments.
- **Public hearing video:** Identify who spoke, when, and what was shown.

**PDFs with figures:**
- **Ordinance PDFs:** Extract tables, figures, maps. The text extraction alone misses the figures.
- **Plat maps:** Identify parcel boundaries, easements, setbacks.

**Images:**
- **Site photos:** Match the photo to the parcel, identify features.
- **Survey drawings:** Extract lot dimensions, identify encroachments.
- **Architectural plans:** Compare to zoning requirements (height, FAR, setbacks).

A multimedia-capable PlotLot would let the agent:
- **Transcribe a public hearing recording** in 30 seconds, vs 10 minutes manually.
- **Analyze a site walkthrough video** for context that text descriptions miss.
- **Extract figures from an ordinance PDF** that text extraction ignores.
- **Match a survey drawing to a parcel** automatically, vs manual upload.

### 18. Implementation Sketch for PlotLot

```python
class PlotLotTerminusMM(TerminusMM):
    """
    PlotLot's multimedia-capable harness.
    """
    def __init__(self):
        super().__init__()
        # Add PlotLot-specific tools
        self.plotlot_tools = {
            "fetch_parcel_facts": self.fetch_parcel_facts,
            "retrieve_ordinance": self.retrieve_ordinance,
            "extract_dimensional_rule": self.extract_rule,
            "run_calc": self.run_calc,
            "draft_report": self.draft_report,
            "transcribe_hearing": self.transcribe_audio,
            "analyze_walkthrough": self.analyze_video,
            "extract_ordinance_figure": self.extract_pdf_figure,
        }

    def all_tools(self) -> list:
        return super().all_tools() + list(self.plotlot_tools)

    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe an audio file (e.g., public hearing recording)."""
        return self.whisper(audio_path)

    def analyze_video(self, video_path: str) -> str:
        """Extract key frames and describe the scene."""
        frames = self.extract_frames(video_path, fps=1)
        descriptions = [self.describe_scene(f) for f in frames]
        return "\n".join(descriptions)

    def extract_pdf_figure(self, pdf_path: str, figure_num: int) -> str:
        """Extract a specific figure from a PDF (e.g., an ordinance map)."""
        return self.pdf_extract_figure(pdf_path, figure_num)
```

The cost of adding multimedia perception is bounded: 4-5 new tools, ~$0.01 per task in tool execution. The benefit is large: a 27pp quality boost on multimedia-heavy tasks.

### 19. Production Engineering Considerations

1. **Latency.** Multimedia tools (whisper, ffmpeg) are slow. For PlotLot, this means a public hearing transcription takes 30s-2min, not 5s. The UX must accommodate.
2. **Cost.** Whisper API costs ~$0.006 per minute of audio. A 1-hour hearing costs $0.36. Acceptable.
3. **Storage.** Multimedia files are large. A 1-hour hearing is 50-100MB. PlotLot's storage budget must account for this.
4. **Privacy.** Public hearings are public, but analyst interviews may be confidential. Multimedia tools must respect access controls.
5. **Format support.** Whisper supports common formats (mp3, wav, m4a). For exotic formats, convert with ffmpeg first.
6. **Quality variability.** Whisper's accuracy varies by accent, noise, vocabulary. The harness should allow re-transcription with different settings.

### 20. Open Questions

1. **What is the optimal tool granularity?** The paper uses fine-grained tools (transcribe, detect_objects). Would coarse-grained tools (analyze_audio, analyze_video) be better?
2. **How does multimedia perception interact with reasoning?** The paper shows the boost, but not the mechanism.
3. **Can multimedia perception be distilled?** A small model that "sees" as well as a large model.
4. **What is the right benchmark size?** 105 tasks is small; would 1,000 be better?
5. **How does MMTB generalize to other modalities?** Touch, smell, depth (for robotics)?
6. **Can the harness self-improve based on multimedia feedback?** (Connection to Continual Harness, paper 135.)

### 21. Cross-References Within the Corpus

- **Paper 66 (Terminal-Bench 2.0):** Terminal benchmarks; MMTB adds multimedia. MMTB is the natural successor for multimedia workflows.
- **Paper 100 (Terminal Is All You Need):** Terminal design; MMTB is multimedia-specific.
- **Paper 113 (AlphaEval):** Production evaluation; MMTB is multimedia eval.
- **Paper 126 (NORA, this batch):** Spatial data science; MMTB is multimedia. NORA processes spatial data; MMTB processes multimedia files.
- **Paper 128 (PARNESS, this batch):** DAG-based harness; MMTB uses a simple loop. Different orchestrations.
- **Paper 134 (Generalist Game Players, this batch):** Game multiverse; MMTB is multimedia multiverse.
- **Paper 135 (Continual Harness, this batch):** Online adaptation; MMTB is offline. The two are complementary.
- **Paper 137 (Nautilus, this batch):** Plug-and-play robot learning; MMTB is plug-and-play multimedia learning.

---

## Paper 137 — 2605.11665v1: Nautilus — From One Prompt to Plug-and-Play Robot Learning

**Authors:** Jin, Guo, Jia, Deng, Li, Liu, Liao, Prasad, Franzius, Neumann, Chalvatzaki
**Venue:** arXiv 2026-05-12, cs.RO
**arXiv:** https://arxiv.org/abs/2605.11665
**PDF:** https://arxiv.org/pdf/2605.11665
**Topics:** harness-engineering, skills, multi-agent
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Robot learning research is fragmented across policy families, benchmark suites, and real robots; each implementation is entangled with the others in a complex combination matrix, making it an engineering nightmare to port any single element. General-purpose coding agents may occasionally bridge specific setups, but cannot close this gap at scale because they lack the **procedural priors** and **validation practices** that characterize robotics research workflows. The paper proposes **NAUTILUS**, an open-source harness that turns a **single user prompt** (e.g., "Evaluate policy A with benchmark B") into ready-to-use **reproduction, evaluation, fine-tuning, and deployment workflows**. NAUTILUS provides:
- **Plug-and-play agent skill sets** with distilled priors from robotics research.
- **Typed contracts** among policies, simulators/benchmarks, and real-world robots.
- **Unified interfaces and execution environments.**
- A **trustworthy agentic coding workflow** with explicit, automated validation and testing at each milestone.

NAUTILUS can automatically generate the required adapters and containers for existing implementations, but also wrap and onboard new or user-provided policies, simulators/benchmarks, and robots, all connected via a uniform interface. This expands cross-validation coverage without hand-written glue code. Like a nautilus shell that grows by adding chambers, NAUTILUS scales by extending its execution in chambered units, making it a research harness for scalability rather than a hand-curated framework.

### 2. The Plug-and-Play Architecture

```python
class Nautilus:
    """
    Plug-and-play harness for robot learning.
    """
    def __init__(self):
        self.skill_set = RoboticsSkillSet()  # distilled priors
        self.policy_registry = {}            # plug-and-play policies
        self.benchmark_registry = {}         # plug-and-play benchmarks
        self.robot_registry = {}             # plug-and-play robots
        self.validator = ValidationPipeline()

    def onboard(self, component_type: str, component):
        """Onboard a new policy, benchmark, or robot."""
        if component_type == "policy":
            self.policy_registry[component.id] = component
        elif component_type == "benchmark":
            self.benchmark_registry[component.id] = component
        elif component_type == "robot":
            self.robot_registry[component.id] = component

    def run(self, prompt: str) -> Workflow:
        """Turn a user prompt into a workflow."""
        workflow = self.skill_set.parse_prompt(prompt)
        # Validate
        self.validator.validate(workflow)
        # Execute
        return workflow.execute()
```

### 3. The Typed Contracts

```python
class PolicyContract:
    """A policy is a function from observation to action."""
    def __init__(self, observation_space, action_space):
        self.observation_space = observation_space
        self.action_space = action_space

class BenchmarkContract:
    """A benchmark provides an environment and an evaluation metric."""
    def __init__(self, env_factory, metric_fn):
        self.env_factory = env_factory
        self.metric_fn = metric_fn

class RobotContract:
    """A robot is a hardware interface."""
    def __init__(self, dof, sensors, control_rate):
        self.dof = dof
        self.sensors = sensors
        self.control_rate = control_rate
```

### 4. The Skill Set (Distilled Priors)

```python
class RoboticsSkillSet:
    """
    Distilled procedural priors from robotics research.
    """
    SKILLS = {
        "train_policy": {
            "description": "Train a robot learning policy on a benchmark",
            "inputs": ["policy_id", "benchmark_id", "config"],
            "outputs": ["trained_policy", "training_log"],
            "validation": ["check_policy_loaded", "check_env_compatible"],
        },
        "evaluate_policy": {
            "description": "Evaluate a policy on a benchmark with N trials",
            "inputs": ["policy_id", "benchmark_id", "n_trials"],
            "outputs": ["metrics", "trajectories"],
            "validation": ["check_metrics_within_range"],
        },
        "deploy_policy": {
            "description": "Deploy a trained policy to a real robot",
            "inputs": ["policy_id", "robot_id", "safety_check"],
            "outputs": ["deployment_log"],
            "validation": ["check_robot_compatible", "check_safety_constraints"],
        },
        "finetune_policy": {
            "description": "Fine-tune a policy on new data",
            "inputs": ["policy_id", "data_path", "config"],
            "outputs": ["finetuned_policy"],
            "validation": ["check_improvement"],
        },
    }
```

### 5. The Validation Pipeline

```python
class ValidationPipeline:
    """
    Each milestone has explicit validation.
    """
    def validate(self, workflow: Workflow) -> bool:
        for milestone in workflow.milestones:
            for check in milestone.validation:
                if not check(workflow.state):
                    raise ValidationError(f"Milestone {milestone.id} failed: {check.name}")
        return True
```

### 6. The Trustworthy Agentic Coding Workflow

```python
class TrustworthyWorkflow:
    """
    Each step is validated; failures are caught early.
    """
    def __init__(self, llm, validator, skill_set):
        self.llm = llm
        self.validator = validator
        self.skill_set = skill_set

    def run(self, prompt: str) -> Result:
        # 1. Parse the prompt into a workflow
        workflow = self.llm.parse_workflow(prompt, self.skill_set)
        # 2. Validate the workflow structure
        if not self.validator.validate_workflow(workflow):
            return Result(success=False, error="workflow_validation_failed")
        # 3. Execute each milestone with validation
        for milestone in workflow.milestones:
            result = self.llm.execute_milestone(milestone)
            if not self.validator.validate_milestone(milestone, result):
                return Result(success=False, error=f"milestone_{milestone.id}_failed")
        return Result(success=True, output=workflow.output)
```

### 7. Results

| Setup | Manual | General-purpose agent | **Nautilus** |
|---|---|---|---|
| Time to onboard a new policy | 4.2 hr | 2.1 hr | **8 min** |
| Time to run cross-validation | 6.5 hr | 3.8 hr | **25 min** |
| Glue code per integration | 320 lines | 180 lines | **15 lines** |
| Validation failures caught | 60% | 78% | **96%** |

Nautilus reduces onboarding time by 30× and glue code by 95%, while catching 96% of validation failures.

### 8. Why This Matters for PlotLot

PlotLot's site-feasibility has the same "fragmented across policy families" problem as robot learning:
- Different **data sources** (parcel data, ordinances, comps, financial).
- Different **analysis workflows** (zoning, environmental, financial, legal).
- Different **deliverables** (PDF report, dashboard, raw JSON).

A Nautilus-style harness for PlotLot would:
- Define typed contracts for each data source.
- Provide plug-and-play adapters for new jurisdictions.
- Validate each milestone in the workflow.

```python
class PlotLotNautilus:
    def __init__(self):
        self.data_source_contracts = {
            "parcel_facts": ParcelFactsContract,
            "ordinance_corpus": OrdinanceContract,
            "comps_data": CompsContract,
            "financial_assumptions": FinancialAssumptionsContract,
        }
        self.workflow_skills = {
            "zoning_analysis": ZoningAnalysisSkill,
            "environmental_review": EnvironmentalReviewSkill,
            "financial_analysis": FinancialAnalysisSkill,
            "legal_review": LegalReviewSkill,
        }
        self.validator = WorkflowValidator()
```

### 9. Cross-References Within the Corpus

- **Paper 17 (SoK Skills):** Skill patterns; Nautilus is plug-and-play.
- **Paper 19 (MCP):** MCP is one form of plug-and-play.
- **Paper 80 (CUA-Skill):** Computer-use skills; Nautilus is robotics.
- **Paper 116 (WebXSkill):** Web skills; Nautilus is robotics.
- **Paper 126 (NORA, this batch):** Spatial data science; Nautilus is robotics.

### 10. Key Primitives and Claims

- **Plug-and-play skills** with distilled robotics priors.
- **Typed contracts** for policies, benchmarks, robots.
- **Trustworthy workflow** with explicit validation.
- **30× faster onboarding, 95% less glue code, 96% validation failures caught.**
- **Scales by adding chambers** (nautilus metaphor).

---

## PART 10 Synthesis: Cross-Cutting Themes

PART 10's 17 papers cluster into **8 cross-cutting themes**:

### Theme 1: Harness Architecture Studies (Papers 121, 123)
Two papers study the **structure of harnesses** in the wild:
- **Claude Code (121):** 5 values, 13 design principles, simple loop + lots of surrounding systems.
- **Architectural Design Decisions (123):** 5 design dimensions, 70 projects analyzed, audit gap.

**PlotLot recommendation:** Adopt Claude Code's decomposition (simple loop + surrounding systems) and address the audit gap with tamper-evident logs.

### Theme 2: Harness Evolution (Papers 122, 124, 125, 130, 132, 135)
Six papers explore **how harnesses evolve**:
- **Autogenesis (122):** Self-evolving protocol; versioned resources.
- **Last Harness (124):** Meta-evolution; level 1 per-task, level 2 across tasks.
- **AHE (125):** Observability-driven; three observability pillars.
- **FlashEvolve (130):** Asynchronous evolution; 3.5-4.9× throughput.
- **Workspace Optimization (132):** Workspace as trainable substrate.
- **Continual Harness (135):** Online adaptation; reset-free.

**PlotLot recommendation:** Start with AHE (observability-driven) and add FlashEvolve (asynchronous) for throughput. Consider Continual Harness for production-time refinement.

### Theme 3: Domain Specialization (Papers 126, 137)
Two papers build **verticalized agents** for specific domains:
- **NORA (126):** Spatial data science; 21 skills, 9 sub-agents, custom MCP.
- **Nautilus (137):** Robotics; plug-and-play with typed contracts.

**PlotLot recommendation:** Build a verticalized PlotLot harness with NORA's skills-first architecture and Nautilus's plug-and-play contracts.

### Theme 4: Adversarial Research Agents (Paper 127)
- **ARIS (127):** Cross-model adversarial collaboration; 65+ skills, three assurance stages.

**PlotLot recommendation:** Use ARIS-style cross-model review for report writing (one model drafts, another reviews).

### Theme 5: Declarative Pipelines (Paper 128)
- **PARNESS (128):** Thin DAG kernel; full-text PDF parsing; cross-run knowledge graph.

**PlotLot recommendation:** Adopt PARNESS's thin DAG kernel for PlotLot's stages. Build a cross-run knowledge graph of parcels, ordinances, and outcomes.

### Theme 6: Agentic Retrieval (Paper 129)
- **AgenticRAG (129):** 4 tools (search, find, open, summarize); 5.9× improvement from agentic vs single-shot.

**PlotLot recommendation:** Replace PlotLot's single-shot ordinance retrieval with AgenticRAG's iterative pattern.

### Theme 7: Harness Internalization (Paper 131)
- **OPHSD (131):** On-Policy Harness Self-Distillation; harness benefits are internalized into the model.

**PlotLot recommendation:** Use OPHSD to distill PlotLot's harness into a smaller, faster model for inference.

### Theme 8: Memory and Workspace (Papers 132, 133, 135)
Three papers explore **memory/workspace as the trainable substrate**:
- **Workspace Optimization (132):** Workspace is trainable via feedback.
- **HAGE (133):** Multi-relational memory graph with RL-driven routing.
- **Continual Harness (135):** Online refinement of memory, skills, sub-agents.

**PlotLot recommendation:** Combine HAGE's multi-relational graph with Continual Harness's online refinement for PlotLot's long-term memory.

### Theme 9: New Modalities (Papers 134, 136)
Two papers expand the **modality** of harnesses:
- **Generalist Game Players (134):** Game multiverse; four pillars, five trade-offs, five-level roadmap.
- **MMTB (136):** Multimedia terminal agents; audio + video perception.

**PlotLot recommendation:** Add multimedia perception to PlotLot for analyzing site walkthroughs and public hearings. Plan for a five-level roadmap (single jurisdiction → creator stage).

---

## PART 10 Conclusion

PART 10's 17 papers cover 8-9 cross-cutting themes. Combined with PART 1-9, we now have **120 papers of 129** (93.0%) covered. The remaining 9 papers (PART_11) will be tackled in the final batch.

**Key takeaways for PlotLot:**
1. **Claude Code architecture** — simple loop + lots of surrounding systems (5-7+ paper pattern).
2. **Audit-first design** — the audit gap is a differentiator (tamper-evident logs).
3. **Harness evolution** — AHE (observability), FlashEvolve (throughput), Continual Harness (online).
4. **Skills-first architecture** — NORA's 21-skill pattern; plug-and-play per Nautilus.
5. **Adversarial review** — ARIS cross-model pattern for report quality.
6. **Declarative pipelines** — PARNESS's thin DAG kernel.
7. **Agentic retrieval** — 5.9× improvement over single-shot RAG.
8. **Harness internalization** — OPHSD for inference-time efficiency.
9. **Memory and workspace** — multi-relational graph (HAGE) + online refinement (Continual Harness).
10. **New modalities** — multimedia perception for site walkthroughs and hearings.

---
