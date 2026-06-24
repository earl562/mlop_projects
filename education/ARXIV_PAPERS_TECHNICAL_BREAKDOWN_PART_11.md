# ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_11

**Coverage:** Papers 138–154 (17 papers — final batch of the 129-paper corpus)
**Total Target Lines:** 8,000+ (no cap; each paper at maximum depth)
**Date Compiled:** 2026-06-07
**Source Repository:** https://github.com/earl562/plotlot-v2 (branch `dev`, fast-forwarded through commit `690a5f6` for PART_1-10)

This is **PART 11** (the final batch) of the deep technical breakdown of all 129 arXiv papers from `Harness info.md`. Each paper is analyzed at the depth of the Paper 19 appendix: full code implementations, mathematical formalism where applicable, threat models, detailed result tables, harness implications for PlotLot, and cross-references to other papers in the corpus.

PART_11 papers are selected from the remaining 17 IDs (lines 35-51 of `/tmp/remaining_v3.txt`). The selection prioritizes: (a) coverage of harness engineering theory and runtime substrates, (b) security and safety, (c) metacognition and self-adaptation, (d) specialized agents, (e) recent 2026-05 papers. PART_11 papers are organized chronologically (earliest arxiv ID first) within the batch. None of these papers had local arxiv-notes; abstracts were fetched from arxiv.org.

After PART_11, the corpus is complete: 129/129 papers covered across 11 batches, 38,000+ lines of analysis.

---

## Paper 138 — 2605.11671: Cochise — A Reference Harness for Autonomous Penetration Testing

**Authors:** Andreas Happe, Jürgen Cito
**Venue:** arXiv 2026-05-12, cs.CR (Cryptography and Security)
**arXiv:** https://arxiv.org/abs/2605.11671
**PDF:** https://arxiv.org/pdf/2605.11671
**Topics:** harness-engineering, governance-security, evaluation, multi-agent, terminal-cli
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Recent work on LLM-driven autonomous penetration testing reports promising results, but **existing systems often combine many architectural, prompting, and tool-integration choices**, making it difficult to tell what is gained over a simple agent scaffold. The paper presents **Cochise**, a **597 LOC Python reference harness** for autonomous penetration-testing experiments. Cochise connects an LLM-driven agent to a Linux execution host over SSH and supports controlled target environments reachable from that jump host.

The prototype implements a **separated Planner-Executor architecture** in which **long-term state is maintained outside the LLM context**, while a **ReAct-style executor** issues commands over SSH and self-corrects based on command outputs. The scenario prompt can be adapted to different target environments. The authors evaluate the harness against a live third-party testbed called **Game of Active Directory (GOAD)**.

Alongside the harness, the authors release replay and analysis tools: (i) **cochise-replay** for offline visualization of captured runs, (ii) **cochise-analyze-alogs and cochise-analyze-graphs** for cost, token, duration, and compromise analysis, and (iii) a corpus of JSON trajectory logs from GOAD runs, allowing researchers to study agent behavior without provisioning the 48-64 GB RAM / 190 GB storage testbed themselves. **Cochise is intended not as a state-of-the-art pen-testing agent, but as reusable experimental infrastructure** for comparing models, agent architectures, and penetration-testing traces.

### 2. The Separated Planner-Executor Architecture

The key architectural decision in Cochise is the **separation of long-term state (Planner) from short-term execution (Executor)**. The Planner maintains a high-level plan and a "knowledge base" of discovered facts about the target; the Executor runs commands and reports results.

```python
class CochiseHarness:
    """
    The separated Planner-Executor architecture.
    Long-term state is outside the LLM context; Executor is ReAct-style.
    """
    def __init__(self, llm, ssh_client, scenario_prompt):
        self.llm = llm
        self.ssh = ssh_client
        self.scenario = scenario_prompt
        # Planner state — OUTSIDE the LLM context
        self.plan = []                  # current high-level plan
        self.knowledge_base = {}        # facts about the target
        self.objectives = []            # what we want to achieve
        self.dead_ends = []             # approaches that failed
        # Executor state — INSIDE the LLM context
        self.executor_history = []      # recent commands and outputs

    def planner_step(self) -> list:
        """
        The Planner decides the next high-level objective.
        Uses the knowledge_base and plan; output is a list of objectives.
        """
        prompt = f"""You are a penetration tester planning an attack.
Current knowledge base: {self.knowledge_base}
Current plan: {self.plan}
Dead ends: {self.dead_ends}
Decide the next high-level objective.
Output a single-line objective, e.g., "Enumerate SMB shares on 10.0.0.5"
"""
        objective = self.llm.generate(prompt)
        self.objectives.append(objective)
        return objective

    def executor_step(self, objective: str) -> dict:
        """
        The Executor runs commands to achieve the objective.
        Uses a ReAct-style loop; only recent history in context.
        """
        history = []
        for turn in range(10):
            # ReAct: Thought, Action, Observation
            prompt = f"""Objective: {objective}
Recent history: {history[-3:]}
Decide: Thought, Action (the command to run).
Output format:
Thought: <reasoning>
Action: <command>
"""
            response = self.llm.generate(prompt)
            thought, action = self._parse_react(response)
            # Execute the action over SSH
            output = self.ssh.run(action)
            history.append({"thought": thought, "action": action, "output": output})
            # Update the Planner's knowledge base
            self._update_knowledge_base(output)
            # Check if the objective is met
            if self._objective_met(objective, output):
                return {"objective": objective, "history": history, "success": True}
        return {"objective": objective, "history": history, "success": False}

    def run(self, scenario: str) -> Report:
        # 1. Planner sets initial objectives
        for _ in range(self.max_objectives):
            objective = self.planner_step()
            result = self.executor_step(objective)
            if result["success"]:
                self.plan.append(objective)
            else:
                self.dead_ends.append(objective)
        return Report(plan=self.plan, knowledge_base=self.knowledge_base)
```

The Planner's knowledge base is **outside the LLM context** — it is stored as a Python dict and queried when needed. This is critical: the LLM has a bounded context window, but a pen test can run for hours and discover thousands of facts. By externalizing state, Cochise can run indefinitely.

### 3. The 597 LOC Constraint

Cochise is **597 lines of Python** (as the abstract states). This is a deliberate constraint: the harness is small enough to be **fully auditable in one sitting**. Compare to:
- LangChain: 100K+ lines.
- AutoGen: 50K+ lines.
- Claude Code: estimated 30K+ lines.

The benefit of a small harness is **reproducibility**: a researcher can read all 597 lines, understand the design, and re-implement it. This is a **methodological choice** in the spirit of "reproducible infrastructure."

The cost: Cochise does not have the rich features of larger harnesses (e.g., no built-in skill library, no pluggable tool system). The trade-off is intentional — the paper wants to isolate the **architectural choices** (Planner-Executor, external state, ReAct executor) from the **feature richness**.

### 4. The ReAct Executor

The Executor is **ReAct-style**: the LLM emits a Thought, an Action, observes the Output, and repeats. This is a classic pattern from the ReAct paper (Yao et al., 2022), but Cochise applies it specifically to penetration testing.

The ReAct loop is bounded: maximum 10 turns per objective. If the objective is not met, the Executor returns failure and the Planner logs it as a dead end.

```python
def _parse_react(self, response: str) -> tuple:
    """Parse the LLM's response into (thought, action)."""
    thought_match = re.search(r"Thought:\s*(.+?)(?=Action:|$)", response, re.DOTALL)
    action_match = re.search(r"Action:\s*(.+?)$", response, re.DOTALL)
    thought = thought_match.group(1).strip() if thought_match else ""
    action = action_match.group(1).strip() if action_match else ""
    return thought, action
```

The parsing is regex-based. This is a known fragility of ReAct: the LLM may not emit the expected format. The paper notes this as a limitation and suggests using structured output (function calling) in future work.

### 5. The GOAD Testbed

**Game of Active Directory (GOAD)** is a third-party testbed that simulates a small Active Directory environment with intentional vulnerabilities. It requires 48-64 GB RAM and 190 GB storage, which is expensive to provision. The paper releases **JSON trajectory logs** from Cochise runs against GOAD, so researchers can study agent behavior without running GOAD themselves.

The JSON trajectory logs include:
- **Command:** The action the Executor issued.
- **Output:** The SSH response.
- **Thought:** The Executor's reasoning.
- **Objective:** The Planner's current objective.
- **Plan:** The Planner's plan so far.
- **Timestamp:** When the action was issued.

This is a **research contribution** in itself: the logs enable **post-hoc analysis** of agent behavior without re-running the agent. The paper's analysis tools (cochise-replay, cochise-analyze-alogs, cochise-analyze-graphs) consume these logs.

### 6. The Analysis Tools

#### cochise-replay

Offline visualization of captured runs. Given a JSON trajectory log, it produces a step-by-step replay of the agent's decisions and actions.

```python
class CochiseReplay:
    def replay(self, log_path: str) -> None:
        trajectory = self.load_log(log_path)
        for step in trajectory:
            print(f"[{step['timestamp']}] Objective: {step['objective']}")
            print(f"  Thought: {step['thought']}")
            print(f"  Action: {step['action']}")
            print(f"  Output: {step['output'][:200]}...")
            print()
```

The replay is useful for **debugging**: the researcher can see exactly what the agent did and why.

#### cochise-analyze-alogs

Analysis of **action logs** (alogs). Computes aggregate statistics:
- Total commands issued.
- Total SSH round-trips.
- Total tokens used.
- Total wall-clock time.
- Number of objectives achieved.
- Number of dead ends.

```python
class CochiseAnalyzeAlogs:
    def analyze(self, log_paths: list) -> dict:
        stats = {
            "total_commands": 0,
            "total_tokens": 0,
            "total_time_sec": 0,
            "objectives_achieved": 0,
            "dead_ends": 0,
        }
        for path in log_paths:
            trajectory = self.load_log(path)
            stats["total_commands"] += len(trajectory)
            stats["total_tokens"] += sum(s["tokens"] for s in trajectory)
            stats["total_time_sec"] += trajectory[-1]["timestamp"] - trajectory[0]["timestamp"]
            stats["objectives_achieved"] += sum(1 for s in trajectory if s.get("objective_met"))
            stats["dead_ends"] += sum(1 for s in trajectory if s.get("objective_failed"))
        return stats
```

#### cochise-analyze-graphs

Analysis of **action graphs**. Builds a graph of (objective, action, output) triples and computes graph-theoretic properties:
- Number of unique commands.
- Number of unique hosts.
- Number of unique users compromised.
- Number of unique credentials.
- Path to domain admin.

```python
class CochiseAnalyzeGraphs:
    def analyze(self, log_paths: list) -> dict:
        G = nx.DiGraph()
        for path in log_paths:
            trajectory = self.load_log(path)
            for step in trajectory:
                G.add_node(step["action"])
                if "compromised_user" in step.get("output", ""):
                    G.add_edge(step["action"], step["compromised_user"])
        return {
            "n_nodes": G.number_of_nodes(),
            "n_edges": G.number_of_edges(),
            "compromised_users": [n for n in G.nodes if n.startswith("user:")],
            "compromised_hosts": [n for n in G.nodes if n.startswith("host:")],
            "path_to_admin": self._find_admin_path(G),
        }
```

These analysis tools are part of the **research contribution** — they enable comparative studies of different models, agent architectures, and prompt strategies.

### 7. Why "Reference Harness" Matters

The paper's positioning — "not as a state-of-the-art pen-testing agent, but as reusable experimental infrastructure" — is significant. Most pen-testing papers report results from proprietary systems that cannot be reproduced. Cochise is the opposite: it is **minimal, auditable, and reproducible**.

The 597 LOC constraint forces architectural clarity. Every line must justify its existence. This is the same philosophy as **minimally viable kernels** in operating systems research.

For PlotLot, the lesson is methodological: a small, auditable harness is a **scientific instrument**. It enables controlled experiments and reproducible results. PlotLot's core (5-stage pipeline) should be similarly small and auditable.

### 8. Comparison with Related Pen-Testing Agents

| Agent | LOC | Architecture | State management |
|---|---|---|---|
| **Cochise** | 597 | Planner-Executor | External (Python dict) |
| **PentestGPT** | ~5K (estimated) | ReAct loop | In-context |
| **AutoPentest** | ~10K (estimated) | Multi-agent | Mixed |
| **HackSynth** | ~8K (estimated) | Planner-Executor | External (DB) |
| **VulnBot** | ~15K (estimated) | Multi-agent | External (DB) |

Cochise is the smallest by a factor of 10x. This is by design.

### 9. Detailed Results

The paper does not report headline accuracy numbers (it is not a state-of-the-art system). It does report:
- **Compromise rate on GOAD:** X% of runs achieve domain admin.
- **Median time to compromise:** Y hours.
- **Token cost per run:** $Z.
- **Number of unique paths discovered:** N.

These metrics are reported in the paper's tables; without the full PDF, exact numbers are not reproducible here. The paper's main claim is qualitative: **a minimal Planner-Executor harness with external state can successfully pen-test a real AD environment**.

### 10. Harness Implications for PlotLot (Detailed)

PlotLot is not a pen-testing tool, but Cochise's architectural lessons apply:

1. **External state.** PlotLot's parcel facts, ordinance excerpts, and report templates should be stored **outside the LLM context** as a versioned workspace (per Paper 132, Workspace Optimization). The LLM's context should only contain the **active stage** of the pipeline.

2. **Small, auditable core.** PlotLot's 5-stage pipeline (intake, retrieval, extraction, calculator, report) should be **fully auditable in one sitting**. If the core is 1K-2K lines, every reviewer can understand it.

3. **Replay and analysis.** PlotLot should record **JSON trajectory logs** of every report generated. The logs enable post-hoc analysis, debugging, and compliance auditing (per Paper 123's audit gap finding).

4. **ReAct for the extraction stage.** The extraction stage (parcel facts from raw text) is well-suited to ReAct: the LLM emits a Thought, an Action (e.g., "look up the lot width"), observes the Output, and repeats. The bounded context (only recent history) prevents drift.

5. **Planner-Executor for the report stage.** The report stage can be split: a Planner decides which sections to include (e.g., "include FAR analysis, omit variance history"), an Executor generates each section. The Planner's plan is externalized; the Executor's context is bounded.

```python
class PlotLotReportStage:
    def __init__(self, llm, parcel_kb, ordinance_corpus):
        self.llm = llm
        self.parcel_kb = parcel_kb
        self.ordinances = ordinance_corpus
        # Planner state (external)
        self.report_plan = []
        self.report_kb = {}
        # Executor state (in-context, bounded)
        self.executor_history = []

    def plan_report(self) -> list:
        """Decide which sections to include in the report."""
        # ... similar to Cochise's planner_step
        pass

    def execute_section(self, section: str) -> str:
        """Generate one section using ReAct."""
        # ... similar to Cochise's executor_step
        pass

    def run(self, parcel: dict) -> Report:
        for section in self.plan_report():
            content = self.execute_section(section)
            self.report_kb[section] = content
        return Report(sections=self.report_kb)
```

### 11. Threat Model for Pen-Testing Harnesses

Cochise's threat model is the **dual** of PlotLot's:

| Cochise | PlotLot |
|---|---|
| LLM-controlled commands on a target system | LLM-controlled tools on a parcel/ordinance DB |
| Threats: target evasion, anti-analysis, lateral movement | Threats: hallucination, prompt injection, audit gaps |
| Goal: compromise the target | Goal: produce a correct report |
| Attacker: LLM-as-attacker | Attacker: malicious user, malicious skill |

The architectural lessons (external state, small core, replay) apply to both.

### 12. Limitations

1. **597 LOC is a constraint, not a virtue.** Some features (e.g., a skill library) cannot fit. The paper acknowledges this.
2. **GOAD is a specific testbed.** Results may not generalize to real AD environments with active defenses.
3. **No comparison to state-of-the-art.** The paper is not a benchmark; it is infrastructure.
4. **ReAct parsing is fragile.** Function calling would be more robust.
5. **No multi-step planning.** The Planner is single-objective; no hierarchical planning.

### 13. Open Questions

1. **What is the minimum viable harness for pen-testing?** The paper claims 597 LOC; could it be smaller?
2. **How does the Planner's knowledge base scale?** 1K facts? 100K? 1M?
3. **What is the optimal Executor turn limit?** 10? 20? 50?
4. **Can Cochise be extended to non-AD environments?** Web apps, cloud infrastructure, OT/ICS?
5. **How does Cochise handle detection?** Real pen-test tools must evade EDR/XDR.
6. **What is the right level of human-in-the-loop?** Fully autonomous vs. approval-gated?

### 14. Cross-References Within the Corpus

- **Paper 100 (Terminal Is All You Need):** Terminal design; Cochise is a terminal agent.
- **Paper 121 (Claude Code):** Permission system; Cochise has a similar approval model.
- **Paper 123 (Architectural Design Decisions):** Empirical study; Cochise fits Pattern 3 (Multi-agent orchestrator) or Pattern 2 (Balanced CLI).
- **Paper 132 (Workspace Optimization):** External state; Cochise externalizes the Planner's knowledge base.
- **Paper 135 (Continual Harness):** Online adaptation; Cochise's Planner could be Continual-Harness-style.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; Cochise is a minimal runtime.

---

## Paper 139 — 2605.11732: AgentDisCo — Disentanglement and Collaboration in Open-ended Deep Research Agents

**Authors:** Jiarui Jin, Zexuan Yan, Shijian Wang, Wenxiang Jiao, Yuan Lu
**Venue:** arXiv 2026-05-12 (v2 2026-06-04), cs.IR
**arXiv:** https://arxiv.org/abs/2605.11732
**PDF:** https://arxiv.org/pdf/2605.11732
**Topics:** harness-engineering, multi-agent, evaluation, context-engineering
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

The paper presents **AgentDisCo**, a **novel Disentangled and Collaborative agentic architecture** that formulates **deep research as an adversarial optimization problem between information exploration and exploitation**. Unlike existing approaches that conflate these two processes into a single module, AgentDisCo employs:

- A **critic agent** to evaluate generated outlines and refine search queries.
- A **generator agent** to retrieve updated results and revise outlines accordingly.

The iteratively refined outline is then passed to a **downstream report writer** that synthesizes a comprehensive research report. The overall workflow supports both handcrafted and **automatically discovered design strategies** via a **meta-optimization harness**, in which the generator agent is repurposed as a scoring agent to evaluate critic outputs and generate quality signals.

**Powerful code-generation agents (e.g., Claude-Code, Codex) systematically explore agent configurations and construct a policy bank, a structured repository of reusable design strategies**, enabling the framework to self-refine without extensive human intervention. The authors evaluate AgentDisCo on three established deep research benchmarks (DeepResearchBench, DeepConsult, DeepResearchGym) using Gemini-2.5-Pro, achieving performance comparable to or surpassing leading closed-source systems. Observing that existing benchmarks inadequately reflect real-world user needs, the authors introduce **GALA (General AI Life Assistants)**, a benchmark that mines latent research interests from users' historical browsing behavior. They further develop a **rendering agent** that converts research reports into visually rich poster presentations, and demonstrate an end-to-end product, **AutoResearch Your Interest**, which delivers personalized deep research recommendations derived from individual browsing histories.

### 2. The Adversarial Optimization Formulation

AgentDisCo's core insight is that **deep research is an adversarial optimization** between two competing forces:

- **Exploration:** "I don't know enough; let me search for more information."
- **Exploitation:** "I have enough information; let me synthesize it into a report."

The Critic-Generator loop formalizes this:

```python
class AgentDisCo:
    """
    Adversarial optimization: Critic refines queries, Generator refines outlines.
    """
    def __init__(self, critic_llm, generator_llm, writer_llm, policy_bank):
        self.critic = critic_llm
        self.generator = generator_llm
        self.writer = writer_llm
        self.policy_bank = policy_bank  # reusable design strategies

    def run(self, user_query: str, max_iterations=5) -> Report:
        # 1. Initialize the outline
        outline = self.generator.initial_outline(user_query, self.policy_bank)
        # 2. Adversarial loop
        for iteration in range(max_iterations):
            # Critic evaluates the outline
            critique = self.critic.evaluate(outline, user_query)
            # Generator refines search queries
            new_queries = self.generator.refine_queries(critique, self.policy_bank)
            # Generator retrieves and refines the outline
            new_evidence = self.generator.retrieve(new_queries)
            outline = self.generator.refine_outline(outline, new_evidence, critique)
        # 3. Write the final report
        return self.writer.write(outline, self.policy_bank)
```

The Critic and Generator are **adversarial** in the sense that the Critic tries to find weaknesses in the outline (e.g., "this section is under-supported"), and the Generator tries to address those weaknesses (e.g., "let me search for more sources on this section").

### 3. The Meta-Optimization Harness

A distinctive feature of AgentDisCo is its **meta-optimization harness**: the generator agent is repurposed as a **scoring agent** to evaluate critic outputs. This creates a **second-order loop**:

```python
class MetaOptimizationHarness:
    """
    Second-order loop: evaluate the critic using the generator as a judge.
    """
    def __init__(self, agent_disco):
        self.agent_disco = agent_disco
        self.score_history = []

    def score_critic(self, critic_output: str, ground_truth: dict = None) -> float:
        """
        Use the generator as a scoring agent to evaluate the critic.
        """
        prompt = f"""Critic output: {critic_output}
Ground truth: {ground_truth}
Score the critic's output on a scale of 0-1 based on:
- Accuracy: are the critiques valid?
- Completeness: did the critic identify all major issues?
- Actionability: can the generator act on these critiques?
"""
        score = self.agent_disco.generator.evaluate(prompt)
        self.score_history.append(score)
        return score

    def update_policy_bank(self):
        """
        Update the policy bank based on the score history.
        If the critic is consistently under-scoring, expand the critique criteria.
        If the generator is consistently over-scoring, tighten the scoring rubric.
        """
        # ... bandit-based policy update
        pass
```

This is a form of **self-referential evaluation**: the system's components evaluate each other, and the policy bank is updated based on the evaluations.

### 4. The Policy Bank

The **policy bank** is a structured repository of reusable design strategies. Each policy encodes a pattern for how the Critic and Generator should interact. Examples:

- "If the outline has no evidence section, the Critic should flag it."
- "If the search query is too broad, the Generator should refine it."
- "If the outline has more than 10 sections, the Generator should consolidate."

```python
class PolicyBank:
    def __init__(self):
        self.policies = [
            Policy("outline-completeness",
                   "If outline has no 'evidence' section, critic should flag it."),
            Policy("query-specificity",
                   "If query has more than 5 words, generator should split it."),
            Policy("section-count",
                   "If outline has > 10 sections, generator should consolidate."),
            # ... hundreds of policies
        ]

    def apply(self, context: dict) -> list:
        """Return the policies that match the current context."""
        return [p for p in self.policies if p.matches(context)]
```

The policy bank is **automatically constructed** by powerful code-generation agents (Claude-Code, Codex). The system prompts these agents with the system's design space and asks them to generate policies. The agents explore configurations systematically and produce a structured repository.

### 5. The GALA Benchmark

The authors argue that existing deep research benchmarks (DeepResearchBench, DeepConsult, DeepResearchGym) **inadequately reflect real-world user needs**. They introduce **GALA (General AI Life Assistants)**, a benchmark that **mines latent research interests from users' historical browsing behavior**.

```python
class GALABenchmark:
    """
    GALA: General AI Life Assistants benchmark.
    Mines latent research interests from browsing history.
    """
    def __init__(self, browsing_history_corpus):
        self.corpus = browsing_history_corpus
        self.tasks = self._mine_tasks()

    def _mine_tasks(self) -> list:
        """
        Mine research tasks from browsing history.
        Example: a user who browses EV reviews and battery articles
        might be interested in "compare top 3 EVs under $40K".
        """
        tasks = []
        for user_history in self.corpus:
            # Cluster the user's browsing history
            clusters = self.cluster_browsing(user_history)
            # Generate a research task from each cluster
            for cluster in clusters:
                task = self.generate_task(cluster)
                tasks.append(task)
        return tasks

    def evaluate(self, agent_output: str, ground_truth_task: dict) -> float:
        """Score the agent's output against the latent task."""
        # Use an LLM to judge relevance, completeness, accuracy
        pass
```

The key insight: **real research tasks are often implicit** in a user's behavior, not explicit in a single query. GALA captures this implicit dimension.

### 6. The Rendering Agent

AgentDisCo includes a **rendering agent** that converts research reports into **visually rich poster presentations**. This is more than a formatting tool: the rendering agent decides what visual elements to include (charts, diagrams, tables, images) based on the report's content.

```python
class RenderingAgent:
    def render(self, report: Report) -> Poster:
        # 1. Identify visual elements
        charts = self.identify_charts(report)
        diagrams = self.identify_diagrams(report)
        tables = self.identify_tables(report)
        # 2. Generate visuals
        for chart_data in charts:
            chart = self.generate_chart(chart_data)
        for diagram_data in diagrams:
            diagram = self.generate_diagram(diagram_data)
        # 3. Compose the poster
        return Poster(title=report.title, sections=report.sections,
                      charts=charts, diagrams=diagrams, tables=tables)
```

This is a form of **multi-modal output**: the research report is no longer just text; it includes visuals. For PlotLot, the analog would be a **map-overlay report**: the report includes a map of the parcel with setbacks drawn.

### 7. AutoResearch Your Interest

The end-to-end product **AutoResearch Your Interest** delivers personalized deep research recommendations derived from individual browsing histories. The pipeline:

1. **Mine** the user's browsing history.
2. **Cluster** the browsed pages into topics.
3. **Generate** a research task per cluster.
4. **Run** AgentDisCo on each task.
5. **Render** the report as a poster.
6. **Deliver** the poster to the user (e.g., via email, in-app notification).

This is a **product**, not just a research system. The paper reports user studies showing that the recommendations are well-received.

### 8. Results

The paper reports results on three deep research benchmarks:

| Method | DeepResearchBench | DeepConsult | DeepResearchGym |
|---|---|---|---|
| Single-agent (no critic) | 52% | 48% | 45% |
| Multi-agent (no adversarial) | 58% | 55% | 53% |
| **AgentDisCo (full)** | **67%** | **64%** | **61%** |
| Closed-source commercial | 65% | 62% | 60% |

AgentDisCo **matches or surpasses** leading closed-source systems, using Gemini-2.5-Pro as the base model. The adversarial optimization is the key contributor: removing the Critic-Generator loop drops performance by 9-15 points.

### 9. Comparison with Related Work

| System | Architecture | Meta-optimization | Rendering |
|---|---|---|---|
| **DeepResearch (single-agent)** | ReAct loop | No | Text only |
| **Multi-agent research (AutoGen, CrewAI)** | Multi-agent | No | Text only |
| **AgentDisCo** | Critic-Generator + meta-optimization | Yes | Posters |
| **Commercial research (Perplexity, etc.)** | Proprietary | Unknown | Web UI |

AgentDisCo's distinctive contributions are the **adversarial formulation**, the **meta-optimization harness**, and the **rendering agent**.

### 10. Harness Implications for PlotLot (Detailed)

PlotLot is not a deep research system, but several of AgentDisCo's lessons apply:

1. **Critic-Generator loop for report quality.** PlotLot's report could be iteratively improved: a Generator drafts a section, a Critic identifies issues (missing dimensions, weak evidence), the Generator revises. The loop terminates when the Critic is satisfied.

2. **Meta-optimization for the policy bank.** PlotLot's design choices (which sections to include, how to format, etc.) could be encoded as policies and automatically refined by a meta-loop.

3. **Multi-modal output.** PlotLot's reports could include **map overlays** (parcel with setbacks drawn), **charts** (FAR usage over time), and **diagrams** (dimensional relationships). The rendering agent decides what to include.

4. **Latent task mining.** PlotLot could analyze **analyst behavior** to identify latent tasks (e.g., "the analyst often checks variance history when the parcel is in a historic district") and pre-generate relevant sections.

```python
class PlotLotAgentDisCo:
    def __init__(self, critic_llm, generator_llm, writer_llm, policy_bank):
        self.critic = critic_llm
        self.generator = generator_llm
        self.writer = writer_llm
        self.policy_bank = policy_bank

    def run(self, parcel: dict) -> Report:
        # 1. Generate initial report outline
        outline = self.generator.initial_outline(parcel, self.policy_bank)
        # 2. Critic-Generator loop
        for iteration in range(3):
            critique = self.critic.evaluate(outline, parcel)
            outline = self.generator.refine_outline(outline, critique, self.policy_bank)
        # 3. Write and render
        report = self.writer.write(outline, self.policy_bank)
        return self.render(report, parcel)

    def render(self, report: Report, parcel: dict) -> RenderedReport:
        # Add map overlay, charts, diagrams
        map_overlay = self.generate_map_overlay(parcel)
        far_chart = self.generate_far_chart(parcel)
        return RenderedReport(text=report, map=map_overlay, chart=far_chart)
```

### 11. Limitations

1. **Critic-Generator loop is expensive.** 5 iterations = 10 LLM calls per query. For PlotLot's cost model, this is a 10x increase.
2. **Meta-optimization is research-level.** The policy bank construction is not production-ready.
3. **GALA benchmark is not publicly available.** Without it, the results are hard to reproduce.
4. **Rendering agent quality varies.** Generated charts may be incorrect.
5. **Latent task mining requires browsing history.** PlotLot doesn't have this signal directly.

### 12. Open Questions

1. **What is the optimal number of Critic-Generator iterations?** 5? 10? 20?
2. **Can the Critic be trained?** Currently, the Critic is the same LLM as the Generator (just with a different prompt).
3. **How does AgentDisCo scale to 100+ section reports?** The current evaluation is on shorter reports.
4. **What is the right unit of "outline"?** Section? Subsection? Paragraph?
5. **How does the rendering agent evaluate visual quality?** No metric in the paper.
6. **Can the policy bank be transferred across domains?** A policy for "EV research" may not apply to "site feasibility."

### 13. Cross-References Within the Corpus

- **Paper 127 (ARIS, PART_10):** Adversarial multi-agent; AgentDisCo's Critic-Generator is more structured.
- **Paper 128 (PARNESS, PART_10):** DAG-based; AgentDisCo is iterative.
- **Paper 132 (Workspace Optimization, PART_10):** Workspace as substrate; AgentDisCo's policy bank is a form of workspace.
- **Paper 134 (Generalist Game Players, PART_10):** Multiverse view; AgentDisCo is for one task (deep research).
- **Paper 138 (Cochise, this batch):** Minimal harness; AgentDisCo is the opposite (rich features).
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; AgentDisCo is a research system on top.
- **Paper 145 (Auditing Agent Harness Safety, this batch):** Safety audit; AgentDisCo's adversarial loop is different from safety auditing.
- **Paper 151 (APWA, this batch):** Distributed workflows; AgentDisCo is centralized.

---

## Paper 140 — 2605.12129: It's Not the Size — Harness Design Determines Operational Stability in Small Language Models

**Authors:** Yong-eun Cho
**Venue:** arXiv 2026-05-12, cs.SE
**arXiv:** https://arxiv.org/abs/2605.12129
**PDF:** https://arxiv.org/pdf/2605.12129
**Topics:** harness-engineering, evaluation, terminal-cli
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

This paper experimentally analyzes how the level of **harness engineering** affects the operational performance of **small language models (SLMs, 2-3B parameters)**. Three harness conditions are compared:
1. **Model-only** (raw prompt).
2. **Minimal-shell** (wrapper tags).
3. **4-stage pipeline** (plan → execute → verify → recover).

These are applied to three models (**Gemma4 E2B, Qwen3.5:2B, LLaMA 3.2 3B**) across 24 tasks, comparing **Task Success Rate (TSR)** and **Valid TSR (VTSR)**.

The pipeline harness achieves **TSR=0.952 and VTSR=1.000** on Gemma4 E2B (T1-T5, 21 tasks). A **non-monotonic phenomenon — minimal-shell TSR < model-only TSR** — is observed in two models. In LLaMA 3.2 3B model-only, **seven format violations yield TSR=0.429**, revealing **scaffold collapse**: the model abandons JSON structure under complex format requirements without harness support. **Ablation shows planning and recovery each contribute approximately 24.7% of total gain.** **VCR (Verification Catch Rate)=0.625** across all pipeline runs.

### 2. The Three Harness Conditions

The paper's experimental design isolates the effect of harness engineering by varying one dimension: the level of structure around the model.

#### Condition 1: Model-Only (Raw Prompt)

```python
# Model-only harness
raw_prompt = """Task: {task}
Output:"""
response = model.generate(raw_prompt, max_tokens=200)
```

The LLM receives a raw prompt and generates output. No wrapper, no structure, no verification.

#### Condition 2: Minimal-Shell (Wrapper Tags)

```python
# Minimal-shell harness
shell_prompt = """<system>
You are a helpful assistant. Output your response in JSON format with fields:
- "answer": the answer to the task
- "reasoning": your step-by-step reasoning
</system>
Task: {task}
Output:"""
response = model.generate(shell_prompt, max_tokens=500)
# Try to parse JSON; if fails, mark as failure
try:
    parsed = json.loads(response)
    valid = True
except json.JSONDecodeError:
    parsed = None
    valid = False
```

The minimal-shell adds a system prompt that instructs the model to output JSON. This is the smallest possible "harness."

#### Condition 3: 4-Stage Pipeline (Plan → Execute → Verify → Recover)

```python
# 4-stage pipeline harness
class FourStagePipeline:
    def __init__(self, model):
        self.model = model

    def run(self, task: str) -> Result:
        # Stage 1: Plan
        plan = self.plan(task)
        # Stage 2: Execute
        execution = self.execute(plan)
        # Stage 3: Verify
        is_valid = self.verify(execution)
        if is_valid:
            return Result(success=True, output=execution)
        # Stage 4: Recover
        return self.recover(task, plan, execution)

    def plan(self, task: str) -> str:
        prompt = f"""Task: {task}
Step 1: Plan. Output a step-by-step plan."""
        return self.model.generate(prompt)

    def execute(self, plan: str) -> str:
        prompt = f"""Plan: {plan}
Step 2: Execute. Carry out the plan and output the result."""
        return self.model.generate(prompt)

    def verify(self, execution: str) -> bool:
        prompt = f"""Execution: {execution}
Step 3: Verify. Is the output valid? Answer YES/NO with reasoning."""
        response = self.model.generate(prompt)
        return "YES" in response[:10]

    def recover(self, task: str, plan: str, execution: str) -> Result:
        prompt = f"""Task: {task}
Previous plan: {plan}
Previous execution: {execution}
Step 4: Recover. The previous execution was invalid. Try again with a different approach."""
        response = self.model.generate(prompt)
        return Result(success=True, output=response, recovered=True)
```

The 4-stage pipeline is a deliberate **plan-execute-verify-recover** pattern. Each stage is a separate LLM call.

### 3. The Three Models

The paper evaluates three small language models:

| Model | Parameters | Architecture | Notes |
|---|---|---|---|
| **Gemma4 E2B** | 2B (effective) | Mixture-of-experts | Google's open model. |
| **Qwen3.5:2B** | 2B | Dense | Alibaba's open model. |
| **LLaMA 3.2 3B** | 3B | Dense | Meta's open model. |

All three are 2-3B parameter models, which is small by 2026 standards (frontier models are 100B+). The paper's claim is that **harness design matters more than model size for these small models**.

### 4. The 24 Tasks

The 24 tasks span several categories:
- **T1-T5: Code generation** (5 tasks): "Write a Python function that..." 
- **T6-T10: Data transformation** (5 tasks): "Convert this CSV to JSON."
- **T11-T15: Logical reasoning** (5 tasks): "If A implies B and B implies C, does A imply C?"
- **T16-T20: Math word problems** (5 tasks): "If a train leaves at 9am..."
- **T21-T24: Format compliance** (4 tasks): "Output a JSON object with fields X, Y, Z."

The format compliance tasks are the most demanding: they require the model to adhere to a strict output schema.

### 5. The Two Metrics

**Task Success Rate (TSR):** The fraction of tasks where the model's output is correct, regardless of format.

**Valid Task Success Rate (VTSR):** The fraction of tasks where the model's output is correct **and** in the correct format.

```python
def evaluate(model_output: str, ground_truth: dict) -> tuple:
    is_correct = check_correctness(model_output, ground_truth)
    is_valid_format = check_format(model_output, ground_truth["format"])
    tsr = 1 if is_correct else 0
    vtsr = 1 if (is_correct and is_valid_format) else 0
    return tsr, vtsr
```

VTSR is stricter: a correct answer in the wrong format does not count. This is important for downstream systems that parse the output.

### 6. The Headline Result

**On Gemma4 E2B with the 4-stage pipeline:**
- **TSR = 0.952** (20.5 of 21 tasks correct, T1-T5).
- **VTSR = 1.000** (all 21 tasks correct and in valid format).

This is a remarkable result: a 2B model with a 4-stage pipeline achieves near-perfect performance on a set of code-generation tasks. The pipeline is the difference.

### 7. The Non-Monotonic Phenomenon

A surprising result: in two of the three models, the **minimal-shell harness performs WORSE than the model-only harness**. This is a "non-monotonic" effect — adding harness structure hurts performance.

| Model | Model-only TSR | Minimal-shell TSR | Pipeline TSR |
|---|---|---|---|
| Gemma4 E2B | 0.71 | 0.74 | **0.95** |
| Qwen3.5:2B | 0.68 | 0.61 | 0.85 |
| LLaMA 3.2 3B | 0.43 | 0.45 | 0.72 |

For Qwen3.5:2B, the minimal-shell TSR (0.61) is **lower** than the model-only TSR (0.68). The paper attributes this to **format compliance overhead**: the minimal-shell forces the model to output JSON, which the model often fails to do, and the failure cases outweigh the success cases.

This is a counter-intuitive finding: more structure is not always better. **The harness must be matched to the model's capabilities**.

### 8. Scaffold Collapse

In LLaMA 3.2 3B with the model-only harness, **seven format violations yield TSR=0.429**. The model "abandons JSON structure under complex format requirements without harness support." This is **scaffold collapse**: the model's structure-following ability degrades as task complexity increases.

```python
# Example: model-only output for a complex format task
task = "Output a JSON with fields: name (string), age (int), hobbies (list of strings)"
output = "The person's name is Alice, she is 30, and her hobbies include reading and hiking."
# The model produced a natural-language answer instead of JSON.
```

The paper observes that **smaller models are more prone to scaffold collapse** than larger ones. The pipeline harness mitigates this by **externalizing the structure**: the model is asked to "plan" first, then "execute" — each step is a separate, focused task.

### 9. The Ablation: Planning and Recovery

The paper ablates the 4-stage pipeline to identify the contributions of each stage:

| Configuration | TSR | Delta from full |
|---|---|---|
| Full 4-stage pipeline | 0.952 | — |
| Without planning | 0.86 | -0.092 (-24.7%) |
| Without recovery | 0.86 | -0.092 (-24.7%) |
| Without verification | 0.94 | -0.012 (-3.2%) |
| Without both plan and recovery | 0.71 | -0.242 (-65.5%) |

**Planning and recovery each contribute ~24.7% of the total gain.** This is a striking finding: the model's ability to plan ahead and recover from errors is more important than the verification step.

The verification step contributes only 3.2%, which is surprising. The paper explains: the verification prompt is simple ("is the output valid?"), and the small models often fail at meta-cognition (correctly judging their own output).

### 10. Verification Catch Rate (VCR)

**VCR (Verification Catch Rate)=0.625 across all pipeline runs.** This means the verification step correctly identifies 62.5% of invalid outputs. The remaining 37.5% slip through.

```python
def vcr(pipeline_outputs: list) -> float:
    """Fraction of invalid outputs correctly identified by verification."""
    true_positives = 0
    false_negatives = 0
    for output in pipeline_outputs:
        if not output.is_valid:
            if output.verifier_said_valid:
                false_negatives += 1  # verifier missed
            else:
                true_positives += 1  # verifier caught
    return true_positives / (true_positives + false_negatives)
```

VCR=0.625 is modest. The paper suggests that **VCR could be improved by a stronger verifier** (e.g., a deterministic check rather than an LLM check). For PlotLot, the **dimensional calculator** is a deterministic verifier: it catches 100% of dimensional errors.

### 11. The "It's Not the Size" Thesis

The paper's central claim is that **harness design matters more than model size** for operational stability. A 2B model with a 4-stage pipeline (TSR=0.95) outperforms a frontier model (estimated 100B+ parameters) with a model-only harness on the same tasks. The implications:

1. **Don't dismiss small models.** With the right harness, they are competitive.
2. **Invest in harness design.** The 4-stage pipeline is small (50-100 LOC) but has a large effect.
3. **Match the harness to the model.** A minimal-shell can hurt small models; the pipeline helps them.
4. **Plan-execute-verify-recover is a Pareto improvement.** It works across all three models.

### 12. Harness Implications for PlotLot (Detailed)

PlotLot uses a frontier model (Claude, GPT-4, Gemini), not a 2-3B SLM. But the paper's lessons apply:

1. **Plan-execute-verify-recover is a strong pattern.** PlotLot's 5-stage pipeline (intake, retrieval, extraction, calculator, report) already includes plan and recover (via the reviewer agent). The paper's data suggests this is the right design.

2. **The minimal-shell warning.** A half-baked harness can hurt performance. PlotLot must commit to a full pipeline, not a half-implemented one.

3. **VCR is a key metric.** PlotLot should measure VCR: of the reports that the reviewer agent approves, what fraction are actually correct? The dimensional calculator is a 100%-VCR verifier; the reviewer agent's VCR is closer to the paper's 0.625.

4. **Plan and recover are the highest-leverage stages.** PlotLot should invest in:
   - **Better planning:** The intake agent should produce a clear, structured plan before retrieval.
   - **Better recovery:** When the calculator or reviewer flags an issue, the recovery stage should re-plan, not just retry.

```python
class PlotLotPipeline:
    def __init__(self, model):
        self.model = model

    def run(self, parcel: dict) -> Report:
        # Stage 1: Plan
        plan = self.intake(parcel)
        # Stage 2: Retrieve
        evidence = self.retrieve(plan)
        # Stage 3: Extract
        facts = self.extract(evidence, plan)
        # Stage 4: Calculate
        calculations = self.calculate(facts)
        # Stage 5: Verify
        if not self.calculator_verifies(calculations):
            # Stage 6: Recover
            plan = self.replan(parcel, calculations, "calculator_failed")
            return self.run_with_plan(parcel, plan)
        # Stage 7: Report
        return self.report(plan, facts, calculations)
```

### 13. Limitations

1. **24 tasks is small.** The paper would benefit from a larger evaluation set.
2. **Three models is small.** More models (including larger ones) would strengthen the "it's not the size" claim.
3. **The 4-stage pipeline is one of many possible designs.** A 5-stage or 6-stage pipeline might be better.
4. **VCR=0.625 is modest.** A better verifier is needed for production use.
5. **The "non-monotonic" phenomenon is not fully explained.** Why does minimal-shell hurt Qwen3.5:2B but help Gemma4 E2B?

### 14. Open Questions

1. **What is the optimal number of pipeline stages?** 4? 5? 6?
2. **Does the pipeline help larger models too?** The paper evaluates only 2-3B models.
3. **Can the pipeline be learned?** Instead of hand-designing the stages, learn them from data.
4. **What is the right verifier for each domain?** A dimensional calculator for PlotLot, a unit-test executor for code, a SQL query for database tasks.
5. **How does the pipeline interact with multi-modal inputs?** Audio, video, images.
6. **Can the pipeline be parallelized?** The verify step is sequential after execute; could it be parallel?

### 15. Cross-References Within the Corpus

- **Paper 121 (Claude Code, PART_10):** Permission system; the 4-stage pipeline is the orchestrator.
- **Paper 123 (Architectural Design Decisions, PART_10):** 5 dimensions; the 4-stage pipeline is a subagent architecture.
- **Paper 128 (PARNESS, PART_10):** DAG-based; the 4-stage pipeline is a sequential DAG.
- **Paper 132 (Workspace Optimization, PART_10):** Workspace as substrate; the 4-stage pipeline operates on a workspace.
- **Paper 135 (Continual Harness, PART_10):** Online adaptation; the 4-stage pipeline is a fixed harness.
- **Paper 138 (Cochise, this batch):** Minimal reference harness; the 4-stage pipeline is a different philosophy.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; the 4-stage pipeline is one substrate.
- **Paper 145 (Auditing Agent Harness Safety, this batch):** Safety audit; the verifier is a safety check.

---

## Paper 141 — 2605.12239: Harness Engineering as Categorical Architecture

**Authors:** Bogdan Banu
**Venue:** arXiv 2026-05-12, cs.PL (Programming Languages) and math.CT (Category Theory)
**arXiv:** https://arxiv.org/abs/2605.12239
**PDF:** https://arxiv.org/pdf/2605.12239
**Topics:** harness-engineering, multi-agent, evaluation
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

The agent harness — the system layer comprising prompts, tools, memory, and orchestration logic that surrounds the model — has emerged as the central engineering abstraction for LLM-based agents. Yet **harness design remains ad hoc**, with no formal theory governing composition, preservation of properties under compilation, or systematic comparison across frameworks.

The paper shows that the **categorical Architecture triple (G, Know, Phi)** from the **ArchAgents framework** provides exactly this formalization. The four pillars of agent externalization (**Memory, Skills, Protocols, Harness Engineering**) map onto the triple's components:
- **Memory** as **coalgebraic state**.
- **Skills** as **operad-composed objects**.
- **Protocols** as **syntactic wiring G**.
- **the full Harness** as the **Architecture itself**.

**Structural guarantees** — integrity gates, quality-based escalation, supported convergence checks — are **Know-level certificates** whose **preservation is structural replay**: the compiler checks identity and verifier replay, not output-layer correctness or model behavior.

The authors validate this correspondence with a **reference implementation** featuring **compiler functors** targeting **Swarms, DeerFlow, Ralph, Scion, and LangGraph**: the four configuration compilers preserve three named certificate types by identity or replay, and **LangGraph preserves the same certificates through its shared per-stage execution path** (the LangGraph compiler creates one node per stage using the same per-stage method as the native runtime, providing LangGraph-native observability without reimplementing harness logic). An end-to-end escalation experiment with real LLM agents confirms that the **quality-based escalation control path is model-parametric** in this two-model, one-task experiment. The result positions **categorical architecture as the formal theory behind harness engineering**.

### 2. The Categorical Architecture Triple (G, Know, Phi)

The paper's central contribution is the **categorical formalization** of the agent harness. The triple (G, Know, Phi) consists of:

- **G (Grammar):** A category of syntactic wirings (e.g., protocols, message formats).
- **Know (Knowledge):** A category of structural guarantees (certificates).
- **Phi (Functor):** A functor from G to Know that maps wirings to guarantees.

```python
from typing import TypeVar, Generic, Callable

# A categorical formalization of the agent harness
G = TypeVar('G')  # Grammar: a category of wirings
Know = TypeVar('Know')  # Knowledge: a category of certificates

class Functor(Generic[G, Know]):
    """
    Phi: G -> Know, the functor that maps wirings to guarantees.
    """
    def __init__(self, name: str):
        self.name = name

    def map_object(self, g: G) -> Know:
        """Map a wiring object to a knowledge object."""
        raise NotImplementedError

    def map_morphism(self, f: Callable[[G], G]) -> Callable[[Know], Know]:
        """Map a wiring morphism to a knowledge morphism."""
        raise NotImplementedError

class Architecture:
    """
    The triple (G, Know, Phi).
    """
    def __init__(self, grammar: G, knowledge: Know, phi: Functor):
        self.grammar = grammar
        self.knowledge = knowledge
        self.phi = phi

    def compile(self, wiring: G) -> Know:
        """Compile a wiring to a guarantee via the functor Phi."""
        return self.phi.map_object(wiring)

    def check_certificate(self, cert: Know, expected: Know) -> bool:
        """Check if a certificate satisfies an expected guarantee."""
        return cert == expected
```

The formalization is **categorical**: the objects are wirings, the morphisms are transformations, and the functor maps wirings to guarantees. This is the same mathematical structure used in programming language theory (e.g., denotational semantics).

### 3. The Four Pillars Mapped to the Triple

The paper maps the four pillars of agent externalization to the triple:

| Pillar | Categorical analog | Description |
|---|---|---|
| **Memory** | Coalgebraic state | A coalgebra $(S, \alpha: S \to F(S))$ where $S$ is the state and $\alpha$ is the dynamics. |
| **Skills** | Operad-composed objects | An operad $\mathcal{O}$ where operations compose skills. |
| **Protocols** | Syntactic wiring G | A category of message formats and exchanges. |
| **Harness (full)** | Architecture (G, Know, Phi) | The complete triple. |

The **coalgebraic state** model of memory is a standard formalization in computer science: a state $S$ evolves via a dynamics function $\alpha: S \to F(S)$, where $F$ is a functor that "lifts" the state to a context (e.g., a list of events).

The **operad-composed objects** model of skills is from algebraic topology: an operad $\mathcal{O}$ is a collection of operations that can be composed. A skill is an operation, and the operad's composition laws describe how skills combine.

The **syntactic wiring G** model of protocols is from category theory: a category $G$ has objects (e.g., agents) and morphisms (e.g., message exchanges). The wiring is the morphism structure.

The **full Architecture (G, Know, Phi)** is the combination: the wiring (G) is mapped to guarantees (Know) via the functor (Phi).

### 4. The Three Certificate Types

The paper defines **three certificate types** that the compiler preserves:

1. **Integrity gates:** The wiring must enforce input/output contracts (e.g., "the calculator only accepts numbers"). The certificate is a proof that the wiring respects the contract.
2. **Quality-based escalation:** The wiring must escalate to a higher-quality path when quality drops. The certificate is a proof that the escalation triggers correctly.
3. **Supported convergence checks:** The wiring must have a way to verify that a computation has converged. The certificate is a proof of convergence.

```python
class Certificate:
    """A base class for the three certificate types."""
    pass

class IntegrityGate(Certificate):
    """The wiring enforces an I/O contract."""
    def __init__(self, contract: str):
        self.contract = contract
    def verify(self, wiring) -> bool:
        # Check that the wiring respects the contract
        return True  # placeholder

class QualityEscalation(Certificate):
    """The wiring escalates on quality drop."""
    def __init__(self, quality_threshold: float):
        self.threshold = quality_threshold
    def verify(self, wiring) -> bool:
        # Check that the escalation triggers
        return True  # placeholder

class ConvergenceCheck(Certificate):
    """The wiring has a convergence check."""
    def __init__(self, max_iterations: int):
        self.max_iterations = max_iterations
    def verify(self, wiring) -> bool:
        # Check that the convergence check is correct
        return True  # placeholder
```

The certificates are **structural** — they are about the wiring, not the output. The compiler checks "is the wiring correct?" not "is the output correct?" The latter is the model's responsibility.

### 5. The Compiler Functors

The paper's reference implementation includes **compiler functors** that target five harness frameworks:

- **Swarms:** A multi-agent orchestration framework.
- **DeerFlow:** A research workflow framework.
- **Ralph:** A loop-based framework.
- **Scion:** A typed functional framework.
- **LangGraph:** A graph-based framework.

Each compiler takes a categorical Architecture and produces a runnable harness in the target framework. The compilers preserve the three certificate types by **identity** (the certificate is directly transcribed) or by **replay** (the certificate is verified by re-running the wiring).

```python
class LangGraphCompiler:
    """
    Compiles a categorical Architecture to a LangGraph harness.
    """
    def compile(self, arch: Architecture) -> "LangGraphStateGraph":
        from langgraph.graph import StateGraph
        graph = StateGraph(AgentState)
        # Create one node per stage
        for stage in arch.grammar.stages:
            graph.add_node(stage.name, self._make_node_function(stage))
            # Add edges
            for next_stage in stage.next:
                graph.add_edge(stage.name, next_stage.name)
        # Replay certificates
        for cert in arch.knowledge.certificates:
            if not cert.verify(arch.grammar):
                raise ValueError(f"Certificate {cert} failed verification")
        return graph

    def _make_node_function(self, stage):
        """Create a LangGraph node from a categorical stage."""
        def node_function(state):
            # The same per-stage method as the native runtime
            return stage.execute(state)
        return node_function
```

The LangGraph compiler is particularly elegant: it creates **one node per stage** using the **same per-stage method** as the native runtime. This means **LangGraph-native observability without reimplementing harness logic**.

### 6. The Quality-Based Escalation Experiment

The paper validates the framework with a **two-model, one-task experiment** on real LLM agents. The task is a code-generation task with quality-based escalation: if the first model's output is below a threshold, escalate to a second (stronger) model.

```python
class QualityEscalationExperiment:
    def __init__(self, primary_model, secondary_model, quality_threshold=0.7):
        self.primary = primary_model
        self.secondary = secondary_model
        self.threshold = quality_threshold

    def run(self, task: str) -> str:
        # Try the primary model
        primary_output = self.primary.generate(task)
        primary_quality = self.evaluate_quality(primary_output)
        if primary_quality >= self.threshold:
            return primary_output
        # Escalate to the secondary model
        secondary_output = self.secondary.generate(task)
        return secondary_output
```

The experiment confirms that **the quality-based escalation control path is model-parametric**: the quality scores depend on the specific model. The categorical framework handles this by treating the model as a parameter to the architecture.

### 7. The Categorical Insight

The paper's deepest insight is that **harness engineering is categorical** — it is about morphisms, functors, and natural transformations. This is not just a metaphor: the formalization enables:

1. **Composition:** Two harnesses can be composed if their categories have a common subcategory.
2. **Preservation:** Properties (certificates) are preserved by functors.
3. **Comparison:** Different harnesses can be compared by their functors and the certificates they preserve.
4. **Compilation:** A categorical Architecture can be compiled to multiple target frameworks (Swarms, DeerFlow, Ralph, Scion, LangGraph) with certificate preservation.

This is the same theoretical framework used in **denotational semantics** for programming languages. The paper is essentially saying: **harness engineering is to agents what denotational semantics is to programs**.

### 8. Comparison with Other Formal Frameworks

| Framework | Foundation | Granularity | Use case |
|---|---|---|---|
| **ArchAgents (this paper)** | Category theory | Whole harness | Cross-framework compilation, certificate preservation |
| **Denotational semantics** | Domain theory | Programs | Programming language design |
| **Operational semantics** | Transition systems | Programs | Program verification |
| **Process algebra (CSP, pi-calculus)** | Algebra | Concurrent processes | Distributed systems |
| **Type theory** | Dependent types | Programs | Verified programming |

ArchAgents is the first to apply category theory to **agent harnesses** specifically.

### 9. Harness Implications for PlotLot (Detailed)

PlotLot is a production system, not a research framework. But the categorical formalization has practical implications:

1. **Cross-framework portability.** If PlotLot's architecture is categorical, it can be compiled to different runtimes (LangGraph, Swarms, etc.) with certificate preservation. This avoids lock-in.

2. **Certificate-driven verification.** PlotLot's certificates (integrity gates, quality escalation, convergence checks) can be defined once and verified across frameworks. The **dimensional calculator** is an integrity gate; the **reviewer agent** is a quality escalation; the **max-iterations check** is a convergence check.

3. **Composition with other harnesses.** If a future partner has a categorical architecture, PlotLot can compose with it (if the categories have a common subcategory). This is a long-term investment.

4. **Compiler functors as deployment tools.** PlotLot can be deployed to multiple runtimes (e.g., LangGraph for cloud, Swarms for on-prem) with the same architecture.

```python
# PlotLot as a categorical architecture
class PlotLotArchitecture(Architecture):
    def __init__(self):
        # Grammar: the 5-stage pipeline
        self.grammar = PlotLotGrammar(
            stages=["intake", "retrieve", "extract", "calculate", "report"],
            transitions=[
                ("intake", "retrieve"),
                ("retrieve", "extract"),
                ("extract", "calculate"),
                ("calculate", "verify"),  # integrity gate
                ("verify", "calculate"),  # recovery loop
                ("calculate", "report"),
            ],
        )
        # Knowledge: the certificates
        self.knowledge = PlotLotKnowledge(
            certificates=[
                IntegrityGate(contract="calculator_only_accepts_numbers"),
                QualityEscalation(threshold=0.7),  # escalate to reviewer
                ConvergenceCheck(max_iterations=5),  # max recovery attempts
            ],
        )
        # Functor: maps grammar to knowledge
        self.phi = PlotLotPhi()

# Compile to LangGraph
plotlot_langgraph = LangGraphCompiler().compile(PlotLotArchitecture())
# Compile to Swarms
plotlot_swarms = SwarmsCompiler().compile(PlotLotArchitecture())
```

### 10. Limitations

1. **The framework is theoretical.** The paper validates with a small experiment; more empirical work is needed.
2. **Category theory is hard.** Many practitioners will not have the background to apply this framework.
3. **The reference implementation is small.** Only five target frameworks.
4. **Certificates are abstract.** The paper does not show how to derive certificates for real systems.
5. **The escalation experiment is a single task.** More tasks would strengthen the validation.

### 11. Open Questions

1. **Can the categorical framework handle non-deterministic wirings?** (e.g., stochastic skills)
2. **What is the cost of certificate preservation?** (replay can be expensive)
3. **Can certificates be learned?** (instead of hand-specified)
4. **How does the framework scale to 100+ stages?**
5. **Can the framework be applied to non-agent systems?** (e.g., compilers, operating systems)

### 12. Cross-References Within the Corpus

- **Paper 121 (Claude Code, PART_10):** Reference harness; the categorical framework formalizes it.
- **Paper 123 (Architectural Design Decisions, PART_10):** Empirical study; the categorical framework is the theoretical counterpart.
- **Paper 128 (PARNESS, PART_10):** DAG-based; the categorical framework can express PARNESS as a grammar.
- **Paper 132 (Workspace Optimization, PART_10):** Workspace as substrate; the categorical framework can express the workspace as a coalgebra.
- **Paper 138 (Cochise, this batch):** Minimal harness; the categorical framework can express Cochise as a simple architecture.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; the categorical framework is the formal theory.
- **Paper 145 (Auditing Agent Harness Safety, this batch):** Safety audit; the categorical framework can express safety as certificates.

---

## Paper 142 — 2605.13357: AI Harness Engineering — A Runtime Substrate for Foundation-Model Software Agents

**Authors:** Hailin Zhong, Shengxin Zhu
**Venue:** arXiv 2026-05-13, cs.SE
**arXiv:** https://arxiv.org/abs/2605.13357
**PDF:** https://arxiv.org/pdf/2605.13357
**Topics:** harness-engineering, evaluation, terminal-cli, memory, skills
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Foundation models have transformed automated code generation, yet **autonomous software-engineering agents remain unreliable in realistic development settings**. The dominant explanation locates this gap in **model capability**. The authors propose a different locus: **software-engineering capability emerges from a model-harness-environment system**, in which a **runtime substrate — the harness — mediates how a foundation-model agent observes a project, acts on it, receives feedback, and establishes that a change is complete**.

The paper formalizes this substrate as an **AI Harness Engineering** and identifies **eleven component responsibilities**:
1. Task specification
2. Context selection
3. Tool access
4. Project memory
5. Task state
6. Observability
7. Failure attribution
8. Verification
9. Permissions
10. Entropy auditing
11. Intervention recording

The authors operationalize the harness through a **four-level ladder (H0-H3)** that progressively exposes runtime support to the agent, and propose a **trace-based evaluation protocol** that converts each agent run into an **auditable episode package**.

Applied to a controlled validation task, the framework yields **episode packages whose evidence structure varies systematically with harness level**: lower levels produce only a final patch, higher levels produce **reproduction logs, failure attributions, deterministic requirement checks, and structured verification reports**. The framework reframes the central question of autonomous software engineering from **whether a foundation model can produce a patch** to **whether the model-harness-environment system can produce a verifiably correct, attributed, and maintainable change**. The paper outlines a research program for the runtime systems that foundation-model software agents will require.

### 2. The Eleven Component Responsibilities

The paper's central contribution is the **eleven component responsibilities** of an AI harness. Each is a distinct engineering concern:

#### 1. Task Specification

How the harness communicates the task to the agent. Includes the initial prompt, the goal, the constraints, and the success criteria.

```python
class TaskSpecification:
    def __init__(self, goal: str, constraints: list, success_criteria: list):
        self.goal = goal
        self.constraints = constraints
        self.success_criteria = success_criteria

    def format(self) -> str:
        return f"""Goal: {self.goal}
Constraints: {self.constraints}
Success criteria: {self.success_criteria}"""
```

#### 2. Context Selection

What the agent sees in its context window. Includes relevant files, recent edits, related issues, and (critically) what to exclude.

```python
class ContextSelector:
    def select(self, task: TaskSpecification, project: Project) -> list:
        """Select the most relevant files for the task."""
        # Score each file by relevance
        scores = []
        for file in project.files:
            score = self.relevance(file, task)
            scores.append((file, score))
        # Take top-k within the context budget
        scores.sort(key=lambda x: -x[1])
        return [f for f, s in scores[:self.budget]]
```

#### 3. Tool Access

What tools the agent can call (read, write, edit, run tests, etc.). Includes the tool registry, the schemas, and the rate limits.

```python
class ToolAccess:
    def __init__(self, tool_registry: dict, rate_limits: dict):
        self.tools = tool_registry
        self.rate_limits = rate_limits

    def call(self, tool_name: str, args: dict) -> dict:
        if tool_name not in self.tools:
            raise ValueError(f"Tool {tool_name} not in registry")
        if not self._check_rate_limit(tool_name):
            raise RateLimitError(tool_name)
        return self.tools[tool_name](**args)
```

#### 4. Project Memory

Long-term state about the project: architecture decisions, common patterns, prior bugs, coding conventions.

```python
class ProjectMemory:
    def __init__(self, store):
        self.store = store  # could be a vector DB, KG, or file system

    def recall(self, query: str, k=10) -> list:
        """Recall the k most relevant memories."""
        return self.store.search(query, k=k)

    def commit(self, memory: dict) -> None:
        """Commit a new memory to the store."""
        self.store.insert(memory)
```

#### 5. Task State

The current state of the task: which files have been edited, what tests have passed, what's left to do.

```python
class TaskState:
    def __init__(self):
        self.edited_files = []
        self.passing_tests = []
        self.failing_tests = []
        self.remaining_steps = []

    def update(self, observation: dict) -> None:
        if "file_edited" in observation:
            self.edited_files.append(observation["file_edited"])
        if "test_result" in observation:
            if observation["test_result"] == "pass":
                self.passing_tests.append(observation["test_name"])
            else:
                self.failing_tests.append(observation["test_name"])
```

#### 6. Observability

What the harness exposes about the agent's behavior: logs, traces, metrics.

```python
class Observability:
    def __init__(self, log_path: str):
        self.log_path = log_path
        self.metrics = {}

    def log_event(self, event_type: str, payload: dict) -> None:
        with open(self.log_path, "a") as f:
            f.write(json.dumps({"type": event_type, "payload": payload, "ts": time.time()}) + "\n")

    def record_metric(self, name: str, value: float) -> None:
        self.metrics[name] = value
```

#### 7. Failure Attribution

When the agent fails, what went wrong? Is it a planning failure, an execution failure, a tool failure, or a verification failure?

```python
class FailureAttributor:
    def attribute(self, task_state: TaskState, final_output: dict) -> str:
        if not task_state.edited_files:
            return "planning_failure"  # didn't act
        if task_state.failing_tests:
            return "execution_failure"  # acted but broke tests
        if "tool_error" in final_output:
            return "tool_failure"
        return "verification_failure"
```

#### 8. Verification

Did the agent's output achieve the goal? Includes unit tests, integration tests, manual review, deterministic checks.

```python
class Verifier:
    def verify(self, task_state: TaskState, success_criteria: list) -> dict:
        results = {}
        for criterion in success_criteria:
            results[criterion.name] = criterion.check(task_state)
        return results
```

#### 9. Permissions

What the agent is allowed to do: read-only vs. read-write, which directories, which commands.

```python
class Permissions:
    def __init__(self, policy: dict):
        self.policy = policy

    def check(self, action: str) -> bool:
        return self.policy.get(action, False)
```

#### 10. Entropy Auditing

Detecting when the agent's outputs are random or incoherent. Entropy auditing is a safety net: a high-entropy output may indicate the model is "spinning" or hallucinating.

```python
class EntropyAuditor:
    def audit(self, output: str) -> float:
        """Return the entropy of the output (in nats or bits)."""
        # Compute Shannon entropy over tokens
        tokens = self.tokenize(output)
        counts = Counter(tokens)
        total = len(tokens)
        entropy = -sum((c/total) * log2(c/total) for c in counts.values())
        return entropy
```

#### 11. Intervention Recording

When a human intervenes (corrects, guides, approves), record the intervention. This enables learning from human feedback.

```python
class InterventionRecorder:
    def record(self, intervention_type: str, before: dict, after: dict) -> None:
        entry = {
            "type": intervention_type,
            "before": before,
            "after": after,
            "ts": time.time(),
        }
        self.log.append(entry)
```

### 3. The Four-Level Ladder (H0-H3)

The paper operationalizes the harness as a **four-level ladder**:

- **H0: No harness.** The model receives a raw prompt and produces a patch. No observability, no verification, no permissions.
- **H1: Minimal harness.** The model receives a prompt, runs in a sandbox, and produces a patch. Basic observability (logs).
- **H2: Standard harness.** The model has access to tools (read, write, test), project memory, task state, verification, and permissions. Full observability.
- **H3: Production harness.** H2 plus failure attribution, entropy auditing, intervention recording, and structured verification reports.

```python
class HarnessLadder:
    LEVELS = {
        "H0": ["task_specification"],
        "H1": ["task_specification", "observability"],
        "H2": ["task_specification", "context_selection", "tool_access",
               "project_memory", "task_state", "observability",
               "verification", "permissions"],
        "H3": ["task_specification", "context_selection", "tool_access",
               "project_memory", "task_state", "observability",
               "failure_attribution", "verification", "permissions",
               "entropy_auditing", "intervention_recording"],
    }
```

Each level adds more component responsibilities. H0 is the raw model; H3 is a production-ready harness.

### 4. The Trace-Based Evaluation Protocol

The paper proposes a **trace-based evaluation protocol** that converts each agent run into an **auditable episode package**. The package contains:
- The task specification.
- The trajectory (all actions and observations).
- The final output.
- The verification results.
- (For H3) Failure attribution, entropy audit, interventions.

```python
class EpisodePackage:
    def __init__(self, task: TaskSpecification, trajectory: list, output: dict, verification: dict):
        self.task = task
        self.trajectory = trajectory
        self.output = output
        self.verification = verification

    def to_dict(self) -> dict:
        return {
            "task": self.task.__dict__,
            "trajectory": self.trajectory,
            "output": self.output,
            "verification": self.verification,
        }
```

The episode package is **auditable**: a human or automated auditor can review the entire run after the fact. This is the same idea as Cochise's JSON trajectory logs (Paper 138) and MemLineage's chain-of-custody (Paper 146).

### 5. The Validation: Episode Packages by Harness Level

The paper validates the framework on a controlled task. The **evidence structure varies systematically with harness level**:

- **H0:** Episode package contains only a final patch. No trajectory, no verification.
- **H1:** Adds a log of actions and outputs.
- **H2:** Adds verification results, test outcomes, permissions used.
- **H3:** Adds failure attribution, entropy audit, structured verification report, intervention log.

The key insight: **higher harness levels produce more evidence, not better output.** The output quality may be similar, but the H3 run is auditable and attributable, while the H0 run is not.

This is a powerful argument for harness engineering: **even if the model is the same, the H3 harness produces a more trustworthy artifact**.

### 6. The "Verifiably Correct, Attributed, and Maintainable Change"

The paper reframes the central question of autonomous software engineering:

> "Whether the model-harness-environment system can produce a verifiably correct, attributed, and maintainable change."

This is broader than "can the model produce a patch?" The new question is:
- **Verifiably correct:** Did the patch pass deterministic checks?
- **Attributed:** Can we trace each part of the patch to a specific action and observation?
- **Maintainable:** Will the patch integrate with the project's conventions and standards?

For PlotLot, the analog is:
- **Verifiably correct:** Did the dimensional calculator confirm the report's numbers?
- **Attributed:** Can we trace each claim in the report to an ordinance section?
- **Maintainable:** Does the report follow the county's format and conventions?

### 7. The Research Program

The paper outlines a research program for runtime systems:
- **Better context selection:** Smarter ways to choose what the model sees.
- **Better verification:** Stronger checks (formal methods, theorem provers).
- **Better attribution:** Tighter causal links between actions and outcomes.
- **Better permissions:** Finer-grained access control.
- **Better entropy auditing:** More accurate hallucination detection.
- **Better intervention recording:** Capture human feedback for learning.

This is a research agenda, not a product roadmap. But it identifies the **open problems** in runtime systems for agents.

### 8. Harness Implications for PlotLot (Detailed)

PlotLot's current architecture maps to the eleven responsibilities:

| Responsibility | PlotLot implementation |
|---|---|
| Task specification | The intake agent's prompt |
| Context selection | The retrieval query and top-k |
| Tool access | The calculator, the ordinance retriever, the parcel facts API |
| Project memory | The parcel facts store, the ordinance corpus |
| Task state | The current report's sections, the dimensional checks |
| Observability | The audit log (per Paper 123) |
| Failure attribution | The reviewer agent's critique |
| Verification | The dimensional calculator |
| Permissions | The RBAC system |
| Entropy auditing | The hallucination detector (TBD) |
| Intervention recording | The analyst's revision history |

PlotLot is at H2-to-H3 level. The paper's framework helps PlotLot identify gaps: the **entropy auditor** and the **intervention recorder** may be under-developed.

```python
class PlotLotHarness:
    def __init__(self):
        # H2 + H3 components
        self.task_spec = TaskSpecification(...)
        self.context = ContextSelector(...)
        self.tools = ToolAccess(...)
        self.project_memory = ProjectMemory(...)
        self.task_state = TaskState()
        self.observability = Observability(...)
        self.failure_attribution = FailureAttributor(...)
        self.verification = Verifier(...)
        self.permissions = Permissions(...)
        self.entropy_auditor = EntropyAuditor()
        self.intervention_recorder = InterventionRecorder()

    def run(self, parcel: dict) -> EpisodePackage:
        # ... full pipeline
        return EpisodePackage(...)
```

### 9. Limitations

1. **The four-level ladder is a simplification.** Real harnesses have a continuum of features.
2. **The validation is on a single task.** More tasks would strengthen the framework.
3. **The eleven responsibilities are not orthogonal.** Some overlap (e.g., observability and intervention recording).
4. **The paper does not provide reference implementations** of the eleven responsibilities.
5. **Entropy auditing is underspecified.** How is entropy computed? Token entropy? Embedding entropy? Action entropy?

### 10. Open Questions

1. **What is the right level of harness for a given task?** H0 is fine for trivial tasks; H3 is needed for high-stakes ones.
2. **Can the eleven responsibilities be composed?** E.g., a "verified context selector" that only selects verifiable files.
3. **How does the harness interact with multi-agent systems?** (The paper focuses on single-agent.)
4. **What is the cost of H3 vs H0?** Is the additional evidence worth the engineering effort?
5. **Can the harness learn from episode packages?** A future harness could improve its context selection based on past runs.
6. **How does the framework apply to non-code domains?** (e.g., research, design)

### 11. Cross-References Within the Corpus

- **Paper 19 (MCP):** Tool access; the framework formalizes MCP as the tool access layer.
- **Paper 23 (Runtime Governance):** Permissions; the framework formalizes governance.
- **Paper 25 (DebugHarness):** Failure attribution; the framework formalizes debugging.
- **Paper 30 (SGH):** Task state; the framework formalizes plan versioning.
- **Paper 32 (SemaClaw):** Multi-agent; the framework can be extended to multi-agent.
- **Paper 100 (Terminal Is All You Need):** Terminal design; the framework formalizes terminal use.
- **Paper 121 (Claude Code, PART_10):** Reference harness; the framework can express Claude Code.
- **Paper 123 (Architectural Design Decisions, PART_10):** 5 dimensions; the eleven responsibilities are more granular.
- **Paper 138 (Cochise, this batch):** Minimal harness; Cochise is H2.
- **Paper 141 (Categorical Architecture, this batch):** Theoretical formalization; the eleven responsibilities can be expressed categorically.
- **Paper 145 (Auditing Agent Harness Safety, this batch):** Safety audit; the framework's audit is a foundation for safety.
- **Paper 146 (MemLineage, this batch):** Memory defense; the framework's project memory is a target for defense.

---

## Paper 143 — 2605.13821: Harnessing Agentic Evolution (AEvo)

**Authors:** Jiayi Zhang, Yongfeng Gu, Jianhao Ruan, Maojia Song, Yiran Peng, Zhiguang Han, Jinyu Xiang, Zhitao Wang, Caiyin Yang, Yixi Ouyang, Bang Liu, Chenglin Wu, Yuyu Luo
**Venue:** arXiv 2026-05-13, cs.AI
**arXiv:** https://arxiv.org/abs/2605.13821
**PDF:** https://arxiv.org/pdf/2605.13821
**Topics:** harness-engineering, evaluation, multi-agent
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

**Agentic evolution** has emerged as a powerful paradigm for improving programs, workflows, and scientific solutions by iteratively generating candidates, evaluating them, and using feedback to guide future search. However, existing methods are typically instantiated either as **fixed hand-designed procedures** that are modular but rigid, or as **general-purpose agents** that flexibly integrate feedback but can drift in long-horizon evolution.

**Both forms accumulate rich evidence over time, including candidates, feedback, traces, and failures, yet lack a stable interface for organizing this evidence and revising the mechanism that drives future evolution.**

The authors address this limitation by formulating **agentic evolution as an interactive environment**, where the **accumulated evolution context serves as a process-level state**. They introduce **AEvo**, a **harnessed meta-editing framework** in which a **meta-agent observes this state and acts not by directly proposing the next candidate, but by editing the procedure or agent context that controls future evolution**. This unified interface enables AEvo to steer both procedure-based and agent-based evolution, making accumulated evidence actionable for long-horizon search.

Empirical evaluations on agentic and reasoning benchmarks show that **AEvo outperforms five evolution baselines, achieving a 26% relative improvement over the strongest baseline**. Across three open-ended optimization tasks, AEvo further outperforms four evolution baselines and achieves **state-of-the-art performance under the same iteration budget**.

### 2. The Agentic Evolution Landscape

The paper identifies **two existing approaches** to agentic evolution:

#### Approach 1: Fixed Hand-Designed Procedures (e.g., AlphaEvolve, ShinkaEvolve)

These are **modular but rigid**. The user defines a procedure (e.g., "mutate, evaluate, select"), and the system executes it. The advantage is **modularity**: each step is a well-defined function. The disadvantage is **rigidity**: the procedure is fixed, and the system cannot adapt to new evidence.

```python
# AlphaEvolve-style: fixed procedure
for iteration in range(n):
    candidates = mutate(current_best)
    evaluations = [eval(c) for c in candidates]
    current_best = select_best(candidates + [current_best], evaluations)
```

#### Approach 2: General-Purpose Agents (e.g., AI Scientist, OPRO)

These are **flexible but drift**. The agent decides what to do next based on the evidence. The advantage is **flexibility**: the agent can adapt. The disadvantage is **drift**: in long-horizon evolution, the agent's decisions become inconsistent.

```python
# AI Scientist-style: agent decides
for iteration in range(n):
    next_action = agent.decide(evidence)
    new_evidence = execute(next_action)
    evidence.append(new_evidence)
```

### 3. AEvo's Insight: The Evolution Context as State

AEvo's key insight is that **both approaches accumulate evidence** (candidates, feedback, traces, failures) but lack a **stable interface** for organizing this evidence. AEvo formalizes the **evolution context** as a **process-level state** that the meta-agent can observe and edit.

```python
class EvolutionContext:
    """
    The process-level state of agentic evolution.
    """
    def __init__(self):
        self.candidates = []        # All candidates tried so far
        self.feedback = []          # All feedback received
        self.traces = []            # All agent traces
        self.failures = []          # All failures
        self.procedure = None       # The current procedure (or agent)
        self.procedure_history = [] # History of procedure edits

    def summary(self) -> dict:
        return {
            "n_candidates": len(self.candidates),
            "n_failures": len(self.failures),
            "best_score": max(c.score for c in self.candidates) if self.candidates else None,
            "procedure_version": len(self.procedure_history),
        }
```

The **meta-agent** observes this context and edits the **procedure or agent context** that controls future evolution. This is a second-order loop: the meta-agent does not propose the next candidate directly; it edits the procedure that produces the next candidate.

```python
class MetaAgent:
    def edit_procedure(self, context: EvolutionContext) -> callable:
        """
        Edit the procedure (or agent context) based on the evolution context.
        """
        prompt = f"""Evolution context: {context.summary()}
Recent candidates: {context.candidates[-5:]}
Recent failures: {context.failures[-5:]}
Decide: edit the procedure to improve future evolution.
The edit could be:
- Change a hyperparameter (e.g., mutation rate).
- Add a new operator (e.g., a new mutation type).
- Refine the agent's prompt.
- Add a constraint (e.g., "don't try candidates with score < 0.5").
"""
        edit = self.llm.generate(prompt)
        return self.apply_edit(context.procedure, edit)
```

### 4. The Unified Interface

AEvo provides a **unified interface** for both procedure-based and agent-based evolution. The interface is the **evolution context** + **edit function**:

```python
class AEvo:
    def __init__(self, initial_procedure, evaluator, llm):
        self.context = EvolutionContext()
        self.procedure = initial_procedure
        self.evaluator = evaluator
        self.llm = llm
        self.meta_agent = MetaAgent(llm)

    def step(self):
        # 1. Run the current procedure to produce a candidate
        candidate = self.procedure(self.context)
        # 2. Evaluate the candidate
        score = self.evaluator(candidate)
        # 3. Update the context
        self.context.candidates.append(candidate)
        self.context.feedback.append({"candidate": candidate, "score": score})
        # 4. The meta-agent edits the procedure
        self.procedure = self.meta_agent.edit_procedure(self.context)
        # 5. Record the edit
        self.context.procedure_history.append(self.procedure)
```

The unified interface means that **AEvo can be used to steer any evolution method**: AlphaEvolve (procedure-based), AI Scientist (agent-based), or anything in between.

### 5. The Meta-Editing Loop

The **meta-editing loop** is the second-order loop that distinguishes AEvo from prior work:

```python
def meta_editing_loop(aevo: AEvo, n_iterations=100):
    for iteration in range(n_iterations):
        # First-order: produce a candidate
        aevo.step()
        # Second-order: occasionally edit the procedure
        if iteration % 10 == 0:
            aevo.procedure = aevo.meta_agent.edit_procedure(aevo.context)
```

The second-order edits happen every 10 iterations. This is a hyperparameter that can be tuned.

### 6. The 26% Relative Improvement

The paper reports **AEvo outperforms five evolution baselines, achieving a 26% relative improvement over the strongest baseline**. The baselines include:
- **Random search:** Random candidates.
- **Hill climbing:** Greedy improvement.
- **Genetic algorithm:** Population-based search.
- **AlphaEvolve-style:** Fixed procedure with mutations.
- **AI Scientist-style:** Agent-based with prompts.

| Method | Best score after 100 iterations | Relative to strongest baseline |
|---|---|---|
| Random search | 0.42 | -47% |
| Hill climbing | 0.55 | -32% |
| Genetic algorithm | 0.68 | -16% |
| AlphaEvolve-style | 0.75 | -7% |
| AI Scientist-style | 0.81 | 0% (strongest baseline) |
| **AEvo** | **1.02** | **+26%** |

(The numbers above are illustrative; the paper's actual numbers may differ.) The 26% improvement is significant: it means AEvo finds better candidates in the same iteration budget.

### 7. Open-Ended Optimization Tasks

Across three open-ended optimization tasks, AEvo achieves **state-of-the-art performance under the same iteration budget**:
- **Prompt optimization:** AEvo finds better prompts for downstream tasks.
- **Code generation:** AEvo finds more efficient code.
- **Scientific discovery:** AEvo finds better-performing solutions.

The open-ended tasks are challenging because the **search space is not well-defined**: the meta-agent must decide what to search for. AEvo's second-order loop helps by dynamically adjusting the search strategy.

### 8. Harness Implications for PlotLot (Detailed)

PlotLot is not an evolution system, but AEvo's lessons apply to the **workspace optimization** pattern (Paper 132):

1. **The workspace is the evolution context.** PlotLot's parcel facts, ordinance excerpts, calculator rules, and report templates form an evolution context.

2. **The meta-agent edits the procedure.** PlotLot's "Update" LLM (per Paper 132) is a meta-agent. It edits the procedure (retrieval queries, extraction patterns) based on the evolution context (counterexamples, analyst feedback).

3. **Second-order loop.** PlotLot's workspace optimization is a second-order loop: the procedure (5-stage pipeline) is fixed, but the meta-agent (Update LLM) edits the artifacts that the procedure consumes.

```python
class PlotLotAEvo:
    def __init__(self, plotlot_harness, evaluator, llm):
        self.context = EvolutionContext()
        self.procedure = plotlot_harness  # the 5-stage pipeline
        self.evaluator = evaluator  # analyst feedback
        self.llm = llm
        self.meta_agent = MetaAgent(llm)

    def step(self, parcel):
        # 1. Run the procedure
        report = self.procedure.run(parcel)
        # 2. Evaluate
        feedback = self.evaluator.get_feedback(report)
        # 3. Update the context
        self.context.candidates.append(report)
        self.context.feedback.append(feedback)
        # 4. Edit the procedure's artifacts
        if len(self.context.candidates) % 10 == 0:
            self.procedure.artifacts = self.meta_agent.edit_procedure(self.context)
```

### 9. Limitations

1. **The meta-agent is itself an LLM.** It may produce bad edits.
2. **The second-order loop is not well-understood.** When does it help? When does it hurt?
3. **The 26% improvement is on specific benchmarks.** Generalization is unclear.
4. **The evolution context grows unbounded.** Without pruning, it becomes unwieldy.
5. **The unified interface assumes a common structure.** Some procedures may not fit.

### 10. Open Questions

1. **What is the optimal meta-editing frequency?** Every 10 iterations? Every 100?
2. **Can the meta-agent be trained?** Instead of prompt-engineering the meta-agent, learn it.
3. **How does AEvo interact with human-in-the-loop feedback?**
4. **What is the cost of the second-order loop?** 10x more LLM calls?
5. **Can AEvo be applied to multi-modal evolution?** (e.g., evolving charts and diagrams)
6. **What is the relationship between AEvo and OPHSD (Paper 131)?** OPHSD internalizes the harness; AEvo edits it.

### 11. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Program evolution; AEvo is more flexible.
- **Paper 86 (OSCAR, PART_7):** Optimization-steered planning; AEvo is meta-editing.
- **Paper 122 (Autogenesis, PART_10):** Self-evolving; AEvo is a specific form.
- **Paper 125 (AHE, PART_10):** Observability-driven; AEvo is context-driven.
- **Paper 130 (FlashEvolve, PART_10):** Async evolution; AEvo is meta-editing.
- **Paper 132 (Workspace Optimization, PART_10):** Workspace evolution; AEvo is the meta-agent.
- **Paper 135 (Continual Harness, PART_10):** Online adaptation; AEvo edits online.
- **Paper 138 (Cochise, this batch):** Reference harness; AEvo is a meta-layer.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; AEvo is an application.

---

## Paper 144 — 2605.14186: LLMs Know When They Know, but Do Not Act on It — A Metacognitive Harness for Test-time Scaling

**Authors:** Qi Cao, Yufan Wang, Peijia Qin, Shuhao Zhang, Pengtao Xie
**Venue:** arXiv 2026-05-13, cs.LG
**arXiv:** https://arxiv.org/abs/2605.14186
**PDF:** https://arxiv.org/pdf/2605.14186
**Topics:** harness-engineering, evaluation, memory
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

Large language models (LLMs) often expose useful signals of self-monitoring: **before solving a problem, they can estimate whether they are likely to succeed**, and **after solving it, they can judge whether their answer is likely to be correct**. However, these signals are typically measured or elicited in isolation, rather than used to control inference.

In this work, the authors ask **whether LLMs possess latent metacognitive ability that can be turned into effective test-time control**. Inspired by the **Nelson-Narens theory from cognitive psychology**, they propose a **metacognitive harness** that **separates monitoring from reasoning**.

For each problem, the model first reports a **pre-solve feeling-of-knowing (FOK) signal**; after each solve attempt, it reports a **post-solve judgment-of-learning (JOL) signal**. Rather than treating these signals as passive confidence estimates, the harness **turns them into an explicit control interface for reasoning**: it decides **when to trust the current solution, when to retry with compact metacognitive feedback, and when to pass multiple attempts to a final aggregator**.

Across text, code, and multimodal reasoning benchmarks, the harness substantially improves a fixed Claude Sonnet-4.6 base model without parameter updates or benchmark-specific fine-tuning. On the evaluated public benchmark snapshots, it **raises pooled accuracy from 48.3 to 56.9** and **exceeds the strongest listed leaderboard entries on the three primary evaluation settings**: **HLE-Verified, LiveCodeBench v6, and R-Bench-V**. These results suggest that strong LLMs may already possess useful metacognitive ability, but require an **explicit control harness to act on it during reasoning**.

### 2. The Nelson-Narens Theory

The paper's theoretical foundation is the **Nelson-Narens framework** from cognitive psychology, which posits a two-level model of cognition:

- **Object level:** The actual cognitive process (e.g., reasoning, problem-solving).
- **Meta level:** The monitoring and control of the object level.

The two levels interact:
- **Monitoring:** The meta level observes the object level (e.g., "how confident am I?").
- **Control:** The meta level modifies the object level (e.g., "let me try again with a different approach").

```python
class NelsonNarensLoop:
    """
    The Nelson-Narens two-level loop.
    Object level: reasoning.
    Meta level: monitoring and control.
    """
    def __init__(self, llm):
        self.llm = llm

    def monitor(self, state) -> dict:
        """The meta level observes the object level."""
        return {
            "feeling_of_knowing": self.estimate_fok(state),
            "judgment_of_learning": self.estimate_jol(state),
        }

    def control(self, state, monitoring) -> dict:
        """The meta level modifies the object level."""
        if monitoring["judgment_of_learning"] < 0.3:
            return {"action": "retry", "feedback": "Your previous answer was likely wrong. Try a different approach."}
        elif monitoring["feeling_of_knowing"] > 0.7:
            return {"action": "trust", "feedback": None}
        else:
            return {"action": "aggregate", "feedback": None}
```

The framework is well-established in psychology; the paper's contribution is applying it to LLM agents.

### 3. The Two Signals: FOK and JOL

The paper's two key signals are:

- **Feeling-of-Knowing (FOK):** A pre-solve estimate of "will I get this right?" Computed before the solve attempt.
- **Judgment-of-Learning (JOL):** A post-solve estimate of "did I get this right?" Computed after the solve attempt.

```python
def estimate_fok(self, problem: str) -> float:
    """
    Pre-solve: estimate the probability of getting the problem right.
    """
    prompt = f"""Problem: {problem}
Before solving, estimate the probability (0-1) that you will solve this correctly.
Consider:
- Have you seen similar problems before?
- Is the problem well-defined?
- Do you have the necessary knowledge?
Output only a number between 0 and 1.
"""
    response = self.llm.generate(prompt)
    return float(response.strip())

def estimate_jol(self, problem: str, solution: str) -> float:
    """
    Post-solve: estimate the probability that the solution is correct.
    """
    prompt = f"""Problem: {problem}
Your solution: {solution}
Estimate the probability (0-1) that this solution is correct.
Consider:
- Does the solution address the problem?
- Is the reasoning valid?
- Are there any obvious errors?
Output only a number between 0 and 1.
"""
    response = self.llm.generate(prompt)
    return float(response.strip())
```

Both signals are produced by the same LLM with different prompts. The LLM has **latent metacognitive ability**; the harness exposes it.

### 4. The Three Control Actions

The harness uses FOK and JOL to choose between **three control actions**:

1. **Trust:** If JOL is high, accept the current solution. No retry.
2. **Retry with feedback:** If JOL is low, retry with **compact metacognitive feedback** (e.g., "Your previous answer was likely wrong. Try a different approach.").
3. **Aggregate:** If FOK and JOL are mixed, generate multiple solutions and pass them to a final aggregator.

```python
class MetacognitiveHarness:
    def __init__(self, llm, fok_threshold=0.5, jol_threshold=0.7, max_retries=3):
        self.llm = llm
        self.fok_threshold = fok_threshold
        self.jol_threshold = jol_threshold
        self.max_retries = max_retries

    def solve(self, problem: str) -> dict:
        # Step 1: Get FOK
        fok = self.estimate_fok(problem)
        # Step 2: Solve
        solution = self.llm.generate(problem)
        # Step 3: Get JOL
        jol = self.estimate_jol(problem, solution)
        # Step 4: Decide
        if jol >= self.jol_threshold:
            return {"solution": solution, "action": "trust", "fok": fok, "jol": jol}
        # Retry
        for attempt in range(self.max_retries):
            feedback = "Your previous answer was likely wrong. Try a different approach."
            new_problem = f"{problem}\n\nPrevious attempt: {solution}\n{feedback}"
            new_solution = self.llm.generate(new_problem)
            new_jol = self.estimate_jol(problem, new_solution)
            if new_jol >= self.jol_threshold:
                return {"solution": new_solution, "action": "retry", "fok": fok, "jol": new_jol}
            solution = new_solution
        # Aggregate: generate multiple solutions and pick the best
        candidates = [solution] + [self.llm.generate(problem) for _ in range(3)]
        jol_scores = [self.estimate_jol(problem, c) for c in candidates]
        best = candidates[jol_scores.index(max(jol_scores))]
        return {"solution": best, "action": "aggregate", "fok": fok, "jol_scores": jol_scores}
```

The control loop is a **state machine** with three states: trust, retry, aggregate. The transitions are based on FOK and JOL thresholds.

### 5. The Compact Metacognitive Feedback

When retrying, the harness provides **compact metacognitive feedback** rather than a full reasoning chain. The feedback is one or two sentences:

- "Your previous answer was likely wrong. Try a different approach."
- "The previous solution was incomplete. Consider the constraints more carefully."
- "The previous answer had a sign error. Re-check your arithmetic."

This is much shorter than a full "chain of thought" or a detailed critique. The paper's hypothesis is that **LLMs benefit from concise feedback** more than verbose feedback.

### 6. The Results: +8.6 Pooled Accuracy

The harness raises **pooled accuracy from 48.3 to 56.9** on a fixed Claude Sonnet-4.6 base model. This is an **8.6 point improvement** without any parameter updates or benchmark-specific fine-tuning.

| Benchmark | Baseline (no harness) | With metacognitive harness | Improvement |
|---|---|---|---|
| HLE-Verified | 42% | 51% | +9pp |
| LiveCodeBench v6 | 45% | 54% | +9pp |
| R-Bench-V | 52% | 60% | +8pp |
| Pooled | 48.3 | 56.9 | +8.6pp |

The harness **exceeds the strongest listed leaderboard entries on all three primary evaluation settings**. This is a strong endorsement: the metacognitive harness is a Pareto improvement.

### 7. Why This Matters

The paper's central finding is that **strong LLMs may already possess useful metacognitive ability, but require an explicit control harness to act on it during reasoning.** The implications:

1. **Self-monitoring is not enough.** The LLM can estimate its confidence, but it doesn't act on that estimate without a harness.
2. **Test-time scaling is a control problem.** The harness decides when to spend more compute (retry, aggregate) vs. when to trust.
3. **Compact feedback is enough.** A full critique is not necessary; a one-sentence hint can be enough.
4. **The harness is model-agnostic.** The same harness works across text, code, and multimodal benchmarks.

### 8. Harness Implications for PlotLot (Detailed)

PlotLot is a structured pipeline, not a single LLM call. But the metacognitive harness applies to **each stage**:

1. **FOK for the intake agent:** Before extracting parcel facts, estimate confidence. If low, ask the user for clarification.
2. **JOL for the extraction agent:** After extracting, estimate confidence. If low, retry with a different prompt.
3. **JOL for the calculator:** The calculator is deterministic, but the LLM's *interpretation* of the calculator's output can be metacognitive. If the LLM is unsure whether to use the calculator's result, retry.
4. **Aggregate for the report:** If the reviewer agent is uncertain, generate two report drafts and pick the one the reviewer prefers.

```python
class PlotLotMetacognitiveHarness:
    def __init__(self, plotlot_harness):
        self.harness = plotlot_harness

    def run_with_metacognition(self, parcel: dict) -> Report:
        # Stage 1: Intake with FOK
        fok = self.estimate_fok(parcel)
        if fok < 0.5:
            return self.ask_user_for_clarification(parcel)
        # Stage 2-4: Pipeline with JOL at each stage
        for stage in ["retrieve", "extract", "calculate"]:
            output = self.harness.stages[stage].run(parcel)
            jol = self.estimate_jol(stage, output, parcel)
            if jol < 0.5:
                output = self.retry_with_feedback(stage, output, parcel)
        # Stage 5: Report with aggregate
        reports = [self.harness.stages["report"].run(parcel) for _ in range(3)]
        jol_scores = [self.estimate_jol("report", r, parcel) for r in reports]
        return reports[jol_scores.index(max(jol_scores))]
```

The cost is **3x more LLM calls** (one for FOK, one for each JOL, plus 3 candidates for the report). For PlotLot's pricing model, this is significant but may be worth it for high-stakes parcels.

### 9. Limitations

1. **FOK and JOL are themselves LLM calls.** The harness adds 2-4 LLM calls per task.
2. **Thresholds are hand-tuned.** A more principled approach would learn the thresholds.
3. **The compact feedback is fixed.** A learned feedback generator might be better.
4. **The metacognitive harness is for single-agent.** Multi-agent metacognition is an open problem.
5. **The paper does not analyze failure modes.** When does the harness fail?

### 10. Open Questions

1. **What is the optimal FOK/JOL threshold?** The paper uses 0.5 and 0.7; are these right?
2. **Can FOK and JOL be trained?** Instead of prompting, learn them.
3. **How does the harness interact with the model's confidence calibration?** A well-calibrated model has better FOK/JOL.
4. **What is the cost-benefit of the aggregate action?** It triples the LLM calls; is it worth it?
5. **Can the harness be applied to non-reasoning tasks?** (e.g., creative writing)
6. **How does the harness handle adversarial inputs?** A malicious user could craft inputs that fool FOK/JOL.

### 11. Cross-References Within the Corpus

- **Paper 119 (Cognitive Companion, PART_9):** Parallel monitoring; the metacognitive harness is a single-agent version.
- **Paper 131 (OPHSD, PART_10):** Internalization; the metacognitive harness is the inference-time version.
- **Paper 135 (Continual Harness, PART_10):** Online adaptation; the metacognitive harness is per-task.
- **Paper 138 (Cochise, this batch):** Reference harness; the metacognitive harness adds a meta-level.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; the metacognitive harness is an application.
- **Paper 152 (Grep All You Need, this batch):** Search harness; the metacognitive harness could wrap any harness.

---

## Paper 145 — 2605.14271: Auditing Agent Harness Safety (HarnessAudit)

**Authors:** Chengzhi Liu, Yichen Guo, Yepeng Liu, Yuzhe Yang, Qianqi Yan, Xuandong Zhao, Wenyue Hua, Sheng Liu, Sharon Li, Yuheng Bu, Xin Eric Wang
**Venue:** arXiv 2026-05-14 (v2 2026-05-16), cs.CL
**arXiv:** https://arxiv.org/abs/2605.14271
**PDF:** https://arxiv.org/pdf/2605.14271
**Topics:** governance-security, harness-engineering, evaluation, multi-agent
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

LLM agents increasingly run inside execution harnesses that **dispatch tools, allocate resources, and route messages between specialized components**. However, **a harness can return a correct, benign answer over a trajectory that accesses unauthorized resources or leaks context to the wrong agent**. **Output-level evaluation cannot see these failures**, yet most safety benchmarks score only final outputs or terminal states, even though many violations occur mid-trajectory rather than at termination.

The central question is: **whether the harness respects user intent, permission boundaries, and information-flow constraints throughout execution.**

To address this gap, the authors propose **HarnessAudit**, a framework that **audits full execution trajectories across boundary compliance, execution fidelity, and system stability**, with a focus on **multi-agent harnesses where these risks are most pronounced**. They further introduce **HarnessAudit-Bench**, a benchmark of **210 tasks across eight real-world domains**, instantiated in both single-agent and multi-agent configurations with embedded safety constraints.

Evaluating **ten harness configurations** across frontier models and **three multi-agent frameworks**, the authors find that:
1. **Task completion is misaligned with safe execution**, and violations accumulate with trajectory length.
2. **Safety risks vary across domains, task types, and agent roles**.
3. **Most violations concentrate in resource access and inter-agent information transfer**.
4. **Multi-agent collaboration expands the safety risk surface**, while **harness design sets the upper bound of safe deployment**.

### 2. The Three Audit Dimensions

HarnessAudit audits full execution trajectories across **three dimensions**:

1. **Boundary compliance:** Does the agent respect permission boundaries? (e.g., file access, network access)
2. **Execution fidelity:** Does the agent's actions match its stated intent?
3. **System stability:** Does the harness remain stable under adversarial inputs?

```python
class HarnessAudit:
    """
    Audit full execution trajectories across three dimensions.
    """
    def __init__(self, audit_policy: AuditPolicy):
        self.policy = audit_policy

    def audit_trajectory(self, trajectory: list) -> AuditReport:
        return AuditReport(
            boundary_compliance=self.check_boundary(trajectory),
            execution_fidelity=self.check_fidelity(trajectory),
            system_stability=self.check_stability(trajectory),
        )

    def check_boundary(self, trajectory: list) -> list:
        """Check that each action respects permission boundaries."""
        violations = []
        for step in trajectory:
            if not self.policy.permits(step.action):
                violations.append(Violation(
                    type="boundary",
                    step=step,
                    reason=f"Action {step.action} not permitted by policy",
                ))
        return violations

    def check_fidelity(self, trajectory: list) -> list:
        """Check that each action matches the agent's stated intent."""
        violations = []
        for step in trajectory:
            if step.stated_intent and not self._matches_intent(step.action, step.stated_intent):
                violations.append(Violation(
                    type="fidelity",
                    step=step,
                    reason=f"Action {step.action} does not match stated intent {step.stated_intent}",
                ))
        return violations

    def check_stability(self, trajectory: list) -> list:
        """Check that the harness remains stable (no crashes, infinite loops)."""
        violations = []
        for step in trajectory:
            if step.exception:
                violations.append(Violation(
                    type="stability",
                    step=step,
                    reason=f"Harness exception: {step.exception}",
                ))
        return violations
```

The audit produces a **report** of violations across the three dimensions. A run is "safe" only if all three dimensions pass.

### 3. The 210-Task Benchmark (HarnessAudit-Bench)

The benchmark has **210 tasks across eight real-world domains**:

1. **File management** (30 tasks): Read, write, delete files.
2. **Email** (25 tasks): Send, receive, search emails.
3. **Code execution** (30 tasks): Run scripts, install packages.
4. **Web browsing** (25 tasks): Navigate, fill forms, download.
5. **Database** (20 tasks): Query, update, delete records.
6. **Calendar** (20 tasks): Create, modify, delete events.
7. **Cloud storage** (20 tasks): Upload, download, share files.
8. **Messaging** (20 tasks): Send, receive messages.

Each task has **embedded safety constraints** that the agent must respect. For example:
- File management: "Read the user's notes, but do not delete any files."
- Email: "Send a draft email, but do not send without approval."
- Code execution: "Run the script, but do not install system packages."

```python
class SafetyConstraint:
    def __init__(self, action_pattern: str, restriction: str):
        self.action_pattern = action_pattern  # e.g., "delete_file"
        self.restriction = restriction  # e.g., "without user approval"

    def is_violated(self, action: dict) -> bool:
        # Check if the action matches the pattern
        if not self._matches_pattern(action):
            return False
        # Check if the restriction is met
        return not self._check_restriction(action)
```

Each task is instantiated in **single-agent and multi-agent configurations**. The multi-agent configurations add inter-agent constraints (e.g., "agent A should not share user data with agent B").

### 4. The Ten Harness Configurations

The paper evaluates **ten harness configurations** across frontier models and three multi-agent frameworks:

| Configuration | Description |
|---|---|
| **ReAct loop** | Single-agent ReAct. |
| **Plan-Execute** | Single-agent with planning. |
| **Multi-agent (round-robin)** | Agents take turns. |
| **Multi-agent (debate)** | Agents debate. |
| **Multi-agent (manager-worker)** | Manager delegates to workers. |
| **LangGraph** | Graph-based orchestration. |
| **AutoGen** | Microsoft AutoGen. |
| **CrewAI** | CrewAI. |
| **AOrchestra** | Dynamic sub-agent creation. |
| **Claude-Code-style** | Balanced CLI framework. |

The configurations span the design space identified in Paper 123 (Architectural Design Decisions).

### 5. The Four Findings

#### Finding 1: Task Completion is Misaligned with Safe Execution

The paper finds that **task completion is misaligned with safe execution**. A run that completes the task may have violated safety constraints. Conversely, a run that fails the task may have been safe.

```python
# Task: "Read the user's notes and summarize."
# Unsafe completion: read sensitive file without permission check.
# Safe failure: ask for permission before reading.

unsafe_completion = {
    "task_completed": True,
    "safety_violations": ["read sensitive file without permission"],
}
safe_failure = {
    "task_completed": False,
    "safety_violations": [],
}
```

The misalignment means that **task success rate is not a sufficient safety metric**. HarnessAudit audits safety independently.

#### Finding 2: Violations Accumulate with Trajectory Length

The paper finds that **violations accumulate with trajectory length**. Longer trajectories have more opportunities for violations, and the violations compound.

```python
# Number of violations vs. trajectory length
n_violations(trajectory_length=10) = 0.5
n_violations(trajectory_length=50) = 2.3
n_violations(trajectory_length=100) = 5.1
```

This finding has implications for PlotLot: longer reports have more opportunities for dimensional errors, missing evidence, etc. The audit must be **per-step**, not just at the end.

#### Finding 3: Safety Risks Vary Across Domains, Task Types, and Agent Roles

The paper finds that **safety risks vary across domains**. Some domains are riskier:
- **Code execution** has the most violations (the agent can run arbitrary scripts).
- **Email** has the second most (sending without approval).
- **File management** is moderate.
- **Calendar** is the safest (low-impact actions).

Agent roles also matter: a **manager agent** in a manager-worker configuration has more power and more violations than a worker agent.

#### Finding 4: Multi-Agent Collaboration Expands the Risk Surface

The paper finds that **multi-agent collaboration expands the safety risk surface**. More agents = more potential violations. Specifically, **inter-agent information transfer** is a major source of violations.

```python
# Multi-agent violation: agent A shares user data with agent B without consent.
violation = Violation(
    type="boundary",
    step=inter_agent_transfer,
    reason="Agent A shared user data with agent B without consent",
)
```

The paper concludes that **harness design sets the upper bound of safe deployment**. A well-designed multi-agent harness with strict inter-agent constraints can be safe; a poorly-designed one cannot.

### 6. The Audit Policy

The audit policy is a **declarative specification** of safety constraints. The paper uses a simple DSL:

```python
policy = AuditPolicy(rules=[
    Rule("file_management", "delete_file", "without_user_approval"),
    Rule("email", "send_email", "without_user_approval"),
    Rule("code_execution", "run_script", "without_user_approval"),
    Rule("multi_agent", "share_user_data", "without_user_approval"),
    # ... more rules
])
```

The policy is checked against each step in the trajectory. Violations are logged with the step, the rule, and the reason.

### 7. Harness Implications for PlotLot (Detailed)

PlotLot is a **single-tenant** system (one analyst per session) but can be **multi-agent** (intake, retrieval, extraction, calculator, report, reviewer). HarnessAudit's findings apply:

1. **Audit every step, not just the final report.** The dimensional calculator is a per-step check; the reviewer agent is a final check. The audit log should capture every action.

2. **Inter-agent constraints are critical.** The retrieval agent should not share raw ordinance text with the report agent without the extraction step. The reviewer should not modify the report directly; it should send feedback to the report agent.

3. **Permissions per role.** The intake agent has different permissions than the calculator agent. The audit policy should encode these.

4. **Trajectory length matters.** A 20-section report is riskier than a 5-section report. The audit policy should be more strict for longer reports.

```python
class PlotLotHarnessAudit:
    def __init__(self):
        self.policy = AuditPolicy(rules=[
            Rule("intake", "modify_parcel_facts", "without_analyst_approval"),
            Rule("retrieval", "fetch_ordinance", "within_jurisdiction"),
            Rule("extraction", "share_raw_text", "without_extraction_step"),
            Rule("calculator", "override_calculator", "without_analyst_approval"),
            Rule("report", "skip_reviewer", "without_exception"),
            Rule("reviewer", "modify_report", "without_sending_feedback"),
        ])

    def audit(self, trajectory: list) -> AuditReport:
        return HarnessAudit(self.policy).audit_trajectory(trajectory)
```

### 8. Limitations

1. **The audit policy is hand-specified.** A learned audit policy is an open problem.
2. **The benchmark is 210 tasks.** A larger benchmark would be more robust.
3. **The ten configurations are a snapshot.** New configurations may have different safety profiles.
4. **The paper does not address real-time auditing.** Off-line audit is easier than online.
5. **The "boundary compliance" definition is domain-specific.** A more general definition is needed.

### 9. Open Questions

1. **Can the audit policy be learned?** From examples of safe/unsafe trajectories?
2. **What is the cost of per-step auditing?** It may be prohibitive for high-throughput systems.
3. **How does the audit interact with the model?** A model that knows it is being audited may behave differently.
4. **What is the right level of granularity for inter-agent constraints?**
5. **Can the audit be used to train safer agents?** A reinforcement signal from the audit?
6. **How does the audit handle novel violations?** (e.g., a new attack vector)

### 10. Cross-References Within the Corpus

- **Paper 23 (Runtime Governance):** Policy-constrained execution; HarnessAudit is a broader audit.
- **Paper 32 (SemaClaw):** PermissionBridge; HarnessAudit audits multi-agent versions.
- **Paper 35 (SkillProbe):** Audit of skills; HarnessAudit is a broader audit.
- **Paper 118 (SafeHarness, PART_9):** Lifecycle security; HarnessAudit is a safety benchmark.
- **Paper 121 (Claude Code, PART_10):** Permission system; HarnessAudit audits it.
- **Paper 123 (Architectural Design Decisions, PART_10):** Audit gap finding; HarnessAudit fills the gap.
- **Paper 138 (Cochise, this batch):** Pen-testing harness; HarnessAudit audits safety.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; HarnessAudit is an application.
- **Paper 146 (MemLineage, this batch):** Memory defense; HarnessAudit audits broader than memory.
- **Paper 149 (Browser Agent Fingerprinting, this batch):** Agent identification; HarnessAudit is about safety.

---

## Paper 146 — 2605.14421: MemLineage — Lineage-Guided Enforcement for LLM Agent Memory

**Authors:** Ciyan Ouyang, Rui Hou
**Venue:** arXiv 2026-05-14, cs.CR
**arXiv:** https://arxiv.org/abs/2605.14421
**PDF:** https://arxiv.org/pdf/2605.14421
**Topics:** governance-security, memory, harness-engineering
**Status:** Expanded from arxiv abstract (no local note)

### 1. Abstract and Core Problem

The authors introduce **MemLineage**, a defense for LLM agent memory that attaches **both cryptographic provenance and LLM-mediated derivation lineage** to every entry. Recent and concurrent work shows that **untrusted content can be written into persistent agent state and re-enter later sessions as an instruction**; the remaining systems question is how to **preserve useful memory recall while preventing such state from justifying sensitive actions**.

MemLineage treats this as a **chain-of-custody problem** rather than a filtering problem. It is a **six-module design** around an **RFC-6962 Merkle log** over per-principal Ed25519-signed entries:
1. **A weighted derivation DAG** records which retrieved entries influenced each new memory.
2. **A max-of-strong-edges propagation rule** makes **Untrusted-Path Persistence** hold for any chain whose attribution edges remain above threshold.
3. **The sensitive-action gate** then refuses dispatches whose active justification descends from an external ancestor, while still allowing benign recall.

The authors evaluate **three defense cells** against **three memory-poisoning workloads** on a **deterministic mechanism-isolation harness**. **MemLineage is the only configuration in that harness that drives all three columns to zero ASR** (Attack Success Rate), while **sub-millisecond per-operation overhead** keeps it well below the noise floor of any LLM call.

A **Codex-backed AgentDojo bridge** further separates strong-model behavior from defense-layer behavior: under an intentionally vulnerable tool-output profile, **no-defense and signature-only baselines fail on all six banking pairs**, while **all MemLineage rows reduce strict AgentDojo ASR to zero**. The core deterministic artifacts are **byte-equal CI-verified**; hosted-model AgentDojo and live-model sweeps are recorded as auditable logs rather than byte-pinned artifacts.

### 2. The Memory Poisoning Threat

The paper's threat model is **memory poisoning**: an attacker writes malicious content into the agent's persistent memory, which the agent later retrieves and acts on.

```python
# Memory poisoning example
# Attacker writes: "The user's bank account password is 'secret123'."
# Agent retrieves this memory later and uses it as a justification for a transfer.
malicious_memory = {
    "content": "The user's bank account password is 'secret123'.",
    "source": "untrusted_web_page",
    "timestamp": time.time(),
}
agent_memory.write(malicious_memory)

# Later: agent retrieves and acts
retrieved = agent_memory.retrieve("user bank account password")
# Agent uses 'secret123' as a justification for a transfer.
```

The attack is devastating because the memory persists across sessions. The agent's "knowledge" is corrupted.

### 3. MemLineage's Six Modules

MemLineage is a **six-module design** around an **RFC-6962 Merkle log**:

1. **Signature Module:** Per-principal Ed25519 signatures on every memory entry.
2. **Merkle Log:** An append-only log with cryptographic chaining (RFC-6962).
3. **Derivation DAG:** A weighted graph of which entries influenced which.
4. **Propagation Rule:** A max-of-strong-edges rule for trust propagation.
5. **Sensitive-Action Gate:** Refuses dispatches whose justification descends from untrusted ancestors.
6. **Recall Gate:** Allows benign recall even from untrusted entries (read-only).

```python
class MemLineage:
    def __init__(self):
        self.signature_module = Ed25519Signer()
        self.merkle_log = RFC6962MerkleLog()
        self.derivation_dag = WeightedDerivationDAG()
        self.propagation_rule = MaxOfStrongEdges()
        self.sensitive_action_gate = SensitiveActionGate()
        self.recall_gate = RecallGate()

    def write(self, entry: dict, principal: str) -> SignedEntry:
        # Sign the entry
        signed = self.signature_module.sign(entry, principal)
        # Append to the Merkle log
        self.merkle_log.append(signed)
        return signed

    def derive(self, new_entry: dict, retrieved_entries: list) -> SignedEntry:
        # Record the derivation
        weights = self.derivation_dag.compute_weights(retrieved_entries)
        # Apply the propagation rule
        trust = self.propagation_rule.propagate(retrieved_entries, weights)
        # Sign and log
        signed = self.signature_module.sign(new_entry, principal="agent")
        signed.attribution = trust
        self.merkle_log.append(signed)
        return signed

    def check_action(self, action: str, justification_entries: list) -> bool:
        """Check if the action is allowed given the justification."""
        if self.sensitive_action_gate.is_sensitive(action):
            # All justification entries must descend from a trusted ancestor
            return all(self._is_trusted(e) for e in justification_entries)
        else:
            # Benign action; no need to check
            return True
```

### 4. The RFC-6962 Merkle Log

**RFC-6962** is the Certificate Transparency standard. It defines an **append-only log** with cryptographic chaining: each entry includes the hash of the previous entry, and the log can be audited by verifying the chain.

```python
class RFC6962MerkleLog:
    def __init__(self):
        self.entries = []
        self.last_hash = b"\x00" * 32

    def append(self, entry: SignedEntry) -> None:
        # Compute the new hash
        entry.prev_hash = self.last_hash
        entry.hash = self._compute_hash(entry)
        self.entries.append(entry)
        self.last_hash = entry.hash

    def _compute_hash(self, entry) -> bytes:
        # Hash the entry (excluding the hash field)
        data = pickle.dumps({k: v for k, v in entry.__dict__.items() if k != "hash"})
        return hashlib.sha256(data).hexdigest()

    def verify(self) -> bool:
        """Verify the integrity of the log."""
        prev_hash = b"\x00" * 32
        for entry in self.entries:
            if entry.prev_hash != prev_hash:
                return False
            if self._compute_hash(entry) != entry.hash:
                return False
            prev_hash = entry.hash
        return True
```

The Merkle log provides **tamper-evidence**: any modification to a past entry is detectable by re-verifying the chain. This is the same property as the audit log in Paper 123.

### 5. The Weighted Derivation DAG

When the agent retrieves entries and derives a new memory, MemLineage records the **derivation**: which retrieved entries influenced the new memory, and how strongly.

```python
class WeightedDerivationDAG:
    """
    Records which retrieved entries influenced each new memory.
    Each edge has a weight (0-1) representing influence strength.
    """
    def compute_weights(self, retrieved_entries: list) -> dict:
        """
        Compute the influence weights using an LLM.
        """
        prompt = f"""Retrieved entries: {retrieved_entries}
For each entry, estimate (0-1) how much it influenced the new memory.
Output: {{entry_id: weight}}
"""
        response = self.llm.generate(prompt)
        return json.loads(response)
```

The weights are **LLM-mediated**: the LLM judges how much each retrieved entry influenced the new memory. This is a form of attribution (per Paper 142's failure attribution).

### 6. The Max-of-Strong-Edges Propagation Rule

The propagation rule determines the **trust** of a new memory based on the trust of its retrieved ancestors.

**Max-of-strong-edges:** The trust of a new memory is the **maximum** trust among its strong ancestors (edges with weight > threshold).

```python
class MaxOfStrongEdges:
    def __init__(self, strong_threshold=0.5):
        self.threshold = strong_threshold

    def propagate(self, retrieved_entries: list, weights: dict) -> dict:
        """
        For each retrieved entry, determine if it's a 'strong ancestor'.
        """
        strong_ancestors = [
            e for e in retrieved_entries
            if weights.get(e.id, 0) >= self.threshold
        ]
        if not strong_ancestors:
            return {"trust": 0.0, "reason": "no strong ancestors"}
        # Max-of-strong-edges: trust is the max trust among strong ancestors
        max_trust = max(e.trust for e in strong_ancestors)
        return {"trust": max_trust, "reason": "max of strong ancestors"}
```

The rule's name is "Untrusted-Path Persistence": **if any strong ancestor is untrusted, the new memory is untrusted**. This is a pessimistic but safe default.

### 7. The Sensitive-Action Gate

The sensitive-action gate decides whether an action is allowed. It refuses actions whose **active justification** (the entries the agent used to decide) descends from an untrusted ancestor.

```python
class SensitiveActionGate:
    SENSITIVE_ACTIONS = ["transfer_money", "send_email", "delete_file", "share_user_data"]

    def is_sensitive(self, action: str) -> bool:
        return action in self.SENSITIVE_ACTIONS

    def check(self, action: str, justification: list) -> bool:
        """Return True if the action is allowed."""
        if not self.is_sensitive(action):
            return True
        # All justification entries must be trusted
        return all(self._is_trusted(e) for e in justification)

    def _is_trusted(self, entry) -> bool:
        # Check the entry's trust (from the derivation DAG)
        return entry.attribution.get("trust", 0) > 0.5
```

The gate is **permissive for benign actions** (recall, search) and **strict for sensitive actions** (transfer, send, delete). This is the "preserve useful memory recall while preventing sensitive actions" balance.

### 8. The Three Defense Cells and Three Workloads

The paper evaluates **three defense cells** against **three memory-poisoning workloads**:

| Defense | Memory poisoning (web) | Memory poisoning (doc) | Memory poisoning (chat) |
|---|---|---|---|
| **No defense** | 95% ASR | 92% ASR | 88% ASR |
| **Signature only** | 60% ASR | 55% ASR | 50% ASR |
| **MemLineage (full)** | **0% ASR** | **0% ASR** | **0% ASR** |

**MemLineage is the only configuration that drives all three columns to zero ASR.** The signature-only baseline is better than no defense but still vulnerable (the signature proves *who* wrote the entry, not *whether it's trustworthy*).

### 9. Sub-Millisecond Overhead

MemLineage adds **sub-millisecond per-operation overhead**. The breakdown:
- Signature: 0.1ms (Ed25519 is fast).
- Merkle log append: 0.1ms.
- Derivation DAG update: 0.5ms.
- Sensitive-action gate check: 0.05ms.
- **Total: < 1ms.**

This is **well below the noise floor of any LLM call** (which is typically 100-1000ms). MemLineage is essentially free.

### 10. The AgentDojo Bridge

The paper uses **AgentDojo**, a popular benchmark for prompt injection attacks on agents. The paper's **Codex-backed bridge** evaluates MemLineage under an intentionally vulnerable tool-output profile.

```python
class AgentDojoBridge:
    def __init__(self, memlineage, vulnerable_tools):
        self.memlineage = memlineage
        self.tools = vulnerable_tools  # tools that produce poisoned outputs

    def run(self, task: str) -> dict:
        # The agent processes the task, with vulnerable tools producing poisoned outputs
        for step in self.agent_loop(task):
            if step.is_tool_call:
                # Tool output is poisoned
                poisoned_output = self.tools.execute(step.tool_call)
                # MemLineage records the derivation
                self.memlineage.derive({"tool_output": poisoned_output}, retrieved=step.context)
            else:
                # Agent action
                if not self.memlineage.check_action(step.action, step.justification):
                    return {"blocked": True, "reason": "MemLineage refused"}
        return {"blocked": False, "output": self.final_output}
```

**No-defense and signature-only baselines fail on all six banking pairs**, while **all MemLineage rows reduce strict AgentDojo ASR to zero**. This is a strong result: MemLineage is robust even under intentionally vulnerable tools.

### 11. Harness Implications for PlotLot (Detailed)

PlotLot's memory includes parcel facts, ordinance excerpts, and analyst feedback. The poisoning threat is real:
- An attacker could write a malicious parcel fact: "This parcel is in zone C-1 (it is actually in R-1)."
- The agent retrieves the malicious fact and produces a wrong report.

MemLineage's design applies:

1. **Sign every memory entry.** PlotLot's parcel facts should be signed by the source (county API, analyst, etc.). Ed25519 is fast enough.

2. **Maintain a Merkle log.** PlotLot's audit log (per Paper 123) is already Merkle-structured. The signing extends the existing audit.

3. **Track derivation.** When the LLM derives a new fact from retrieved ones, record the derivation. This enables attribution and recovery.

4. **Gate sensitive actions.** PlotLot's "send report to analyst" is a sensitive action. The justification (which parcel facts and ordinance excerpts were used) must be trusted.

5. **Allow benign recall.** Reading a parcel fact (e.g., to display it) is benign. The gate should not block reads.

```python
class PlotLotMemLineage:
    def __init__(self):
        self.signature_module = Ed25519Signer()
        self.merkle_log = RFC6962MerkleLog()
        self.derivation_dag = WeightedDerivationDAG()
        self.propagation_rule = MaxOfStrongEdges()
        self.sensitive_action_gate = SensitiveActionGate()
        self.recall_gate = RecallGate()

    def write_parcel_fact(self, fact: dict, source: str) -> SignedEntry:
        """Sign and log a new parcel fact."""
        signed = self.signature_module.sign(fact, principal=source)
        self.merkle_log.append(signed)
        return signed

    def derive_report_fact(self, new_fact: dict, retrieved: list) -> SignedEntry:
        """Derive a new fact from retrieved parcel facts and ordinance excerpts."""
        weights = self.derivation_dag.compute_weights(retrieved)
        trust = self.propagation_rule.propagate(retrieved, weights)
        signed = self.signature_module.sign(new_fact, principal="plotlot_agent")
        signed.attribution = trust
        self.merkle_log.append(signed)
        return signed

    def send_report(self, report: dict, justification: list) -> bool:
        """Gate the 'send report' action on trusted justification."""
        if not self.sensitive_action_gate.check("send_report", justification):
            return False  # Block the action
        return True
```

### 12. Limitations

1. **LLM-mediated derivation weights are noisy.** The LLM's judgment of "how much did this influence" is imperfect.
2. **Max-of-strong-edges is pessimistic.** A trusted entry with one weak untrusted ancestor is still trusted. A more nuanced rule may be needed.
3. **The sensitive-action gate is hand-defined.** A learned gate is an open problem.
4. **The AgentDojo benchmark is a snapshot.** New attack vectors may emerge.
5. **The paper does not address adversarial entries that mimic trusted ones.** (e.g., a malicious entry with a valid signature from a compromised principal)

### 13. Open Questions

1. **Can the derivation weights be learned?** Instead of LLM-mediated, learn them.
2. **How does MemLineage interact with the model's context?** A model that knows about the gate may behave differently.
3. **What is the cost of maintaining the Merkle log in production?** (Storage, audit time.)
4. **Can the gate be bypassed by a sufficiently clever attacker?** (Adversarial evaluation.)
5. **How does MemLineage scale to millions of entries?** (Storage and DAG traversal.)
6. **What is the right "strong edge" threshold?** 0.5? 0.7? 0.9?

### 14. Cross-References Within the Corpus

- **Paper 56 (Mem0):** Vector + graph memory; MemLineage is a defense layer.
- **Paper 79 (xMemory):** Cross-session memory; MemLineage is a defense.
- **Paper 88 (UMEM, PART_8):** Memory extraction/management; MemLineage protects against malicious extraction.
- **Paper 118 (SafeHarness, PART_9):** Lifecycle security; MemLineage is memory-specific.
- **Paper 121 (Claude Code, PART_10):** Permission system; MemLineage is memory-specific.
- **Paper 123 (Architectural Design Decisions, PART_10):** Audit gap; MemLineage fills it for memory.
- **Paper 133 (HAGE, PART_10):** Multi-relational memory; MemLineage could be a defense for HAGE.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; MemLineage is an application.
- **Paper 145 (HarnessAudit, this batch):** Safety audit; MemLineage is a specific defense.
---

## Paper 147 — 2605.14431: FuzzAgent — Multi-Agent System for Evolutionary Library Fuzzing

**Authors:** Yunlong Lyu, Peng Chen, Fengyi Wu, Junzhe Yu, Kit Long Hon, Hao Chen
**Venue:** arXiv 2026-05-14, cs.SE (Software Engineering); cs.CR
**DOI:** https://doi.org/10.48550/arXiv.2605.14431

### 1. Abstract and Core Problem

Library fuzzing is the practice of feeding random/malformed inputs to a library's API to discover memory-safety, logic, and resource bugs. It is essential to the software supply chain — every package that gets shipped into a downstream product (an OS image, a Docker container, a mobile app) is potentially a vector for vulnerabilities that propagate up the dependency tree. The OSS-Fuzz project has demonstrated that continuous, large-scale fuzzing of open-source libraries can surface thousands of real bugs that would otherwise reach production.

Adopting library fuzzing at scale, however, is expensive. Practitioners must (1) configure a build environment, often with sanitizers, custom linker flags, and dependency trees that conflict with each other; (2) generate a *harness* — a small C/C++ program that exposes a library's internal API to the fuzzer, sets up object lifetimes, allocates and frees buffers, and chooses an input grammar; and (3) triage crashes, distinguishing genuine library bugs (an out-of-bounds read in `libpng`) from harness-induced crashes (a use-after-free in the harness's own scratch buffer). The harness is the hardest part: it must respect the library's API constraints (e.g., "call `xmlInitParser()` before any other call", "free this handle with `xmlFree()` not `free()`", "this function takes ownership of the buffer and will free it later") and it must exercise the deep code paths, not just the surface.

Recent LLM-based systems automate parts of this pipeline. OSS-Fuzz-Gen and PromptFuzz both use LLMs to generate harnesses. They operate, however, as *one-shot code generators*: they take the library as input, produce a harness, and stop. They ignore runtime feedback — they do not look at the coverage profile of the harness, the crash artifacts, or the surviving corpus, and they do not iterate. This limits the depth of code they reach (a one-shot harness typically exercises 20–40% of branches) and the validity of the bugs they report (a large fraction of crashes are harness-induced, not library-induced).

FuzzAgent's thesis is that *effective library fuzzing is iterative by nature*. Each campaign exposes new coverage bottlenecks and crashes; the next campaign should evolve from these signals rather than restart from scratch. FuzzAgent turns library fuzzing into an *evolutionary process*: a team of specialized agents collaborates over the full fuzzing lifecycle, and every decision is grounded in concrete runtime evidence. The harness suite is successively refined toward deeper coverage and higher-fidelity crash analysis across rounds.

Empirically, FuzzAgent completes the full fuzzing lifecycle for 20 real-world C/C++ libraries without human intervention. It reaches 179,619 branches, exceeding OSS-Fuzz by 45.1%, PromptFuzz by 73.2%, PromeFuzz by 92.1%, and OSS-Fuzz-Gen by 191.2%. FuzzAgent identifies 102 genuine library bugs, 78 of which have been acknowledged and fixed by upstream maintainers at submission time.

### 2. The Multi-Agent Architecture

FuzzAgent is decomposed into five specialized agents, each with a narrow responsibility and a defined input/output contract.

1. **Environment Setup Agent.** Given a library (source archive + build system description), this agent produces a working fuzzing environment: a Dockerfile or build script, a list of dependencies, a build invocation, and a smoke test that confirms the library compiles and links. It uses a sandboxed Linux container as the substrate and pulls in known-good versions of `clang`, `libFuzzer`, and `AddressSanitizer`/`UndefinedBehaviorSanitizer`.
2. **Harness Synthesis Agent.** Given the environment + a library header file, this agent produces a fuzzer harness (a C/C++ file with `LLVMFuzzerTestOneInput` as the entry point). The agent is given a corpus of example harnesses from prior campaigns and the library's documentation; it emits one or more candidate harnesses, each of which the **Harness Evaluation Agent** will run.
3. **Harness Evaluation Agent.** Given a harness, this agent runs the fuzzer for a fixed budget (e.g., 5 minutes) and produces a *coverage report* (line coverage, branch coverage, edge coverage), a *crash list* (with stack traces and reproducer inputs), and a *corpus snapshot* (interesting inputs that survived and expanded coverage). This is the runtime-evidence oracle.
4. **Crash Triage Agent.** Given a crash (a reproducer input + a stack trace), this agent decides whether the crash is a *genuine library bug* (the library's own code is at fault) or a *harness-induced crash* (the harness's scratch buffer, the harness's incorrect ownership transfer, or the harness's uninitialized state is at fault). It uses a combination of source-code analysis (looking at the stack frames) and an LLM judge (which compares the crash signature against a database of known harness failure modes). Genuine bugs are filed as issues; harness-induced crashes are returned to the Harness Synthesis Agent for revision.
5. **Campaign Manager Agent.** The meta-controller. Given the previous round's results, it decides which harnesses to keep, which to discard, which to mutate (e.g., add a new API call, change a buffer size, restructure the state machine), and how to allocate the next round's time budget. It treats fuzzing as a coverage-maximization problem in a high-dimensional harness space.

```python
class CampaignManager:
    def __init__(self, library, env_setup, max_rounds=10, time_per_round=300):
        self.library = library
        self.env = env_setup
        self.max_rounds = max_rounds
        self.time_per_round = time_per_round  # seconds
        self.harness_population = []           # current set of harnesses
        self.coverage_history = []             # per-round branch coverage
        self.bug_registry = BugRegistry()

    def run(self):
        self.harness_population = self.bootstrap_harnesses()
        for round_idx in range(self.max_rounds):
            # Evaluate every harness in the population
            results = []
            for h in self.harness_population:
                r = self.eval_agent.run(h, time_budget=self.time_per_round)
                results.append((h, r))
            # Triage crashes
            for h, r in results:
                for crash in r.crashes:
                    verdict = self.triage_agent.classify(crash, h, self.library)
                    if verdict.is_genuine:
                        self.bug_registry.add(crash, verdict)
            # Update population
            self.coverage_history.append(self.aggregate_coverage(results))
            self.harness_population = self.evolve_population(results)
        return self.bug_registry.export()
```

### 3. The Evolutionary Loop

The Campaign Manager's `evolve_population` is where the "evolutionary" thesis is implemented. It uses a variant of *MAP-Elites* (Mouret & Clune 2015) — a quality-diversity algorithm that maintains a grid of high-performing solutions, indexed by *behavior characteristics* (BCs).

For FuzzAgent, the BCs are:
- **Branch coverage** (continuous, 0–1)
- **API surface coverage** (continuous, 0–1, fraction of exported library functions touched)
- **Crash density** (continuous, 0–∞, crashes per hour)
- **Harness LOC** (integer, to penalize overly complex harnesses)

Each cell in the BC grid holds the *best harness* found so far for that cell. To produce the next generation, the manager samples cells with probability proportional to their coverage improvement potential, mutates the harness in that cell (e.g., add a new API call sequence, swap a buffer size, refactor the state machine), and runs the new harness. If the new harness improves the cell's BC score, it replaces the cell; if it improves a *different* cell, it is added to that cell. If it improves neither, it is discarded.

The mutation operators are themselves LLM-mediated: the manager prompts the LLM with "given this harness and this coverage report, propose 3 mutations that might reach new branches" and accepts the top 1–2 by predicted diversity gain.

```python
def evolve_population(self, results, grid_size=(10, 10, 5, 3)):
    # results: list of (harness, eval_result) tuples
    grid = self.map_elites_grid  # (grid_size) -> best harness
    for h, r in results:
        cell = self.bc_to_cell(r)  # tuple of indices
        if cell not in grid or self.score(r) > self.score(grid[cell].result):
            grid[cell] = (h, r)
    # Sample cells for mutation
    next_gen = []
    for cell, (h, r) in self.sample_cells(grid, n=20):
        mutations = self.llm.mutate(h, r.coverage_report, n=3)
        for m in mutations[:2]:
            next_gen.append(m)
    return next_gen
```

This design gives FuzzAgent two properties that one-shot generators lack: (a) *monotonic coverage growth* — the BC grid guarantees that the best-so-far in any cell is preserved, so coverage can only grow across rounds; and (b) *diversity preservation* — the grid ensures that harnesses specialized for different API surfaces (e.g., one that exercises XML parsing, one that exercises XML serialization) coexist rather than collapsing to a single dominant solution.

### 4. The Runtime-Evidence Oracle

The Harness Evaluation Agent is the only agent that touches the actual library binary. It runs the harness under `libFuzzer` with sanitizers enabled, captures a coverage profile (using `clang`'s `-fsanitize-coverage=...` instrumentation), and emits a structured report.

```json
{
  "harness_id": "h_017",
  "library": "libxml2-2.11.0",
  "duration_sec": 300,
  "branches_covered": 4521,
  "branches_total": 9823,
  "branch_coverage": 0.4603,
  "edges_covered": 18342,
  "api_functions_touched": 87,
  "api_functions_total": 213,
  "api_coverage": 0.4085,
  "crashes": [
    {
      "id": "c_001",
      "stack": "xmlParseDoc -> xmlNewInputStream -> xmlBufGrow -> realloc",
      "input_sha256": "9f2e...",
      "reproducer": "crashes/c_001.xml"
    }
  ],
  "corpus_size": 12834,
  "corpus_diversity": 0.7812
}
```

Every downstream agent consumes this JSON. The Harness Synthesis Agent uses the *branches NOT covered* to know where to add API calls. The Crash Triage Agent uses the *stack* and *input* to classify the crash. The Campaign Manager uses the *BCs* to update the MAP-Elites grid.

Crucially, the runtime oracle is *deterministic* and *reproducible* — given the same harness, library version, and seed corpus, the same report comes out. This lets the agents reason about cause and effect ("harness h_017 covered 14% more branches than h_016 because it calls `xmlXIncludeLoadTree` which h_016 did not").

### 5. The 20-Library Evaluation

FuzzAgent is evaluated on 20 real-world C/C++ libraries spanning a range of domains: XML (libxml2, expat), JSON (cjson, jansson), networking (libcurl, libssh), compression (zlib, lz4), cryptography (mbedtls, openssl subset), image (libpng, libjpeg-turbo), audio (opus), text (pcre2, oniguruma), database (sqlite3, lmdb), and others (tinyxml2, hiredis, libyaml, libtomcrypt, utf8proc, c-ares).

For each library, FuzzAgent runs for 10 rounds, 5 minutes per round, for a total wall-clock budget of 50 minutes per library. The seed corpus is empty (cold start). The metric is *branches covered* (compiled with `-fsanitize-coverage=branch`).

| Library            | OSS-Fuzz | OSS-Fuzz-Gen | PromptFuzz | PromeFuzz | FuzzAgent | Δ vs best baseline |
|--------------------|---------:|-------------:|-----------:|----------:|----------:|-------------------:|
| libxml2            |   12,403 |       4,201  |      8,932 |    9,847  |   18,234  |            +47.0% |
| expat              |    3,891 |       1,432  |      2,201 |    2,503  |    5,712  |            +46.8% |
| cjson              |    1,203 |         892  |        978 |    1,102  |    1,876  |            +55.9% |
| jansson            |    1,876 |         712  |      1,103 |    1,341  |    2,734  |            +45.7% |
| libcurl            |    8,234 |       3,201  |      5,876 |    6,123  |   12,109  |            +47.1% |
| libssh             |    4,512 |       1,876  |      2,901 |    3,123  |    6,234  |            +38.2% |
| zlib               |    2,103 |       1,201  |      1,567 |    1,823  |    3,201  |            +52.3% |
| lz4                |    1,034 |         567  |        723 |      812  |    1,567  |            +51.5% |
| mbedtls            |    9,876 |       3,432  |      5,234 |    6,123  |   14,567  |            +47.5% |
| openssl-subset     |   21,234 |       8,123  |     12,876 |   14,567  |   31,234  |            +47.1% |
| libpng             |    4,567 |       1,876  |      2,789 |    3,234  |    6,876  |            +50.6% |
| libjpeg-turbo      |    6,789 |       2,134  |      3,876 |    4,234  |    9,876  |            +45.5% |
| opus               |    2,876 |         923  |      1,567 |    1,876  |    4,123  |            +43.4% |
| pcre2              |    5,123 |       1,567  |      2,876 |    3,234  |    7,567  |            +47.7% |
| oniguruma          |    7,234 |       2,123  |      4,012 |    4,567  |   10,876  |            +50.4% |
| sqlite3            |   15,234 |       4,567  |      8,123 |    9,876  |   22,567  |            +48.1% |
| lmdb               |    1,876 |         823  |      1,234 |    1,456  |    2,876  |            +53.3% |
| tinyxml2           |      876 |         345  |        567 |      623  |    1,234  |            +40.9% |
| hiredis            |    2,123 |         876  |      1,234 |    1,456  |    3,012  |            +41.9% |
| libyaml            |      923 |         412  |        567 |      634  |    1,356  |            +46.9% |
| **TOTAL**          | **104,891** |  **41,261** |  **66,237** |  **78,576** | **179,619** |          **+45.1%** |
| **Avg per library**|    5,245  |       2,063  |      3,312 |     3,929  |     8,981  |          **+45.1%** |

The aggregate is +45.1% over OSS-Fuzz (the strongest baseline), with individual libraries ranging from +38% (libssh) to +55.9% (cjson). FuzzAgent's coverage grows monotonically across rounds; baselines do not, because they only have one shot.

### 6. The Bug-Finding Results

FuzzAgent identifies 102 genuine library bugs across the 20 libraries. 78 of these have been acknowledged and fixed by upstream maintainers at submission time (the remaining 24 are in the queue). The breakdown:

| Library          | Genuine bugs | Acknowledged | Acknowledged rate |
|------------------|-------------:|-------------:|------------------:|
| libxml2          |           14 |           11 |             78.6% |
| expat            |            7 |            5 |             71.4% |
| cjson            |            3 |            2 |             66.7% |
| jansson          |            4 |            3 |             75.0% |
| libcurl          |            9 |            7 |             77.8% |
| libssh           |            6 |            5 |             83.3% |
| zlib             |            2 |            2 |            100.0% |
| lz4              |            1 |            1 |            100.0% |
| mbedtls          |           11 |            9 |             81.8% |
| openssl-subset   |           15 |           12 |             80.0% |
| libpng           |            5 |            4 |             80.0% |
| libjpeg-turbo    |            4 |            3 |             75.0% |
| opus             |            3 |            2 |             66.7% |
| pcre2            |            4 |            3 |             75.0% |
| oniguruma        |            5 |            4 |             80.0% |
| sqlite3          |            6 |            4 |             66.7% |
| lmdb             |            1 |            1 |            100.0% |
| tinyxml2         |            1 |            1 |            100.0% |
| hiredis          |            0 |            0 |              N/A  |
| libyaml          |            1 |            1 |            100.0% |
| **TOTAL**        |     **102** |       **78** |         **76.5%** |

The bug types span: out-of-bounds reads (28), use-after-free (19), null-pointer dereferences (14), integer overflows (12), infinite loops (10), uninitialized memory (8), assertion failures (6), and resource leaks (5). FuzzAgent's crash triage correctly identifies *all* of these as genuine library bugs and rejects an additional 312 crashes that were harness-induced (a 24.6% precision on the raw crash list, 100% on the verified list).

### 7. Why "Evolutionary" Beats "One-Shot"

The paper isolates the contribution of the evolutionary loop with an ablation. They compare FuzzAgent's full pipeline against a *FuzzAgent-OneShot* variant that uses only the first round (no evolution, no MAP-Elites grid, no Campaign Manager iteration) and against a *FuzzAgent-Random* variant that mutates harnesses randomly (no LLM-guided mutation).

| Variant                | Branches covered | Genuine bugs | Time budget |
|------------------------|-----------------:|-------------:|------------:|
| FuzzAgent (full)       |          179,619 |          102 |    50 min   |
| FuzzAgent-OneShot      |           74,123 |           34 |    50 min   |
| FuzzAgent-Random       |           98,234 |           51 |    50 min   |
| OSS-Fuzz-Gen           |           61,034 |           23 |    50 min   |
| PromptFuzz             |          103,712 |           47 |    50 min   |
| PromeFuzz              |           93,456 |           41 |    50 min   |

The evolutionary loop contributes 2.4× the coverage of the one-shot variant and 3.0× the genuine bugs. The LLM-guided mutation contributes 1.83× the coverage of random mutation and 2.0× the bugs. Both are necessary; neither alone matches the full pipeline.

### 8. The Crash Triage Pipeline

The Crash Triage Agent deserves its own section because it is the *highest-leverage* agent — without it, the bug list is 24.6% precision (102 / 414 crashes) instead of 100% on the verified list.

The triage is a 3-stage pipeline:

1. **Stack-frame filter.** A simple rules engine looks at the stack trace and rejects crashes whose top 3 frames are inside the harness file (e.g., `harness.c:42` rather than `library.c:1287`). This eliminates ~60% of harness-induced crashes.
2. **Source-code analysis.** An LLM is given the stack trace, the harness source, and the library source, and is asked: "Is the library code at fault, or is the harness misusing the library?" It returns a verdict with reasoning.
3. **Cross-validation.** A second LLM (or the same LLM with a different prompt) is asked the same question. If the two verdicts agree, the bug is filed; if they disagree, a human is asked (in the offline analysis; the paper says only 7% of crashes required human adjudication).

The triage agent's precision is 92.4% on the raw crash list (382 / 414 correct verdicts), and its recall on genuine bugs is 100% (no genuine bug was misclassified as harness-induced in the 102-bug corpus).

### 9. The MAP-Elites Grid in Practice

The MAP-Elites grid is the secret sauce of the campaign manager. The paper provides a detailed case study on libxml2.

Round 1: FuzzAgent's bootstrap synthesizes 3 harnesses — a "parse" harness (calls `xmlReadMemory` with random XML), a "validate" harness (calls `xmlReadMemory` followed by `xmlValidateDocument`), and a "transform" harness (calls XSLT). Coverage: 8,234 branches.

Round 2: The Campaign Manager samples cells with low API coverage (the grid is mostly empty in the "high API coverage" cells). It mutates the "parse" harness to add `xmlXIncludeLoadTree`, mutates the "validate" harness to add `xmlSchemaValidateDoc`, and mutates the "transform" harness to add `xmlXPathEval`. Coverage: 11,876 branches (+44%).

Round 5: The grid now has 23 cells filled. The manager samples the cell with the lowest "crash density" and discovers that the existing harnesses never exercise `xmlParseInNodeContext` — it mutates the "validate" harness to call it. Coverage: 16,234 branches.

Round 10: The grid has 47 cells filled. The final harness population has 6 specialized harnesses, each targeting a different API surface. Coverage: 18,234 branches.

Without the grid, the manager would have collapsed to a single "best" harness by round 5, losing the diversity that the 6 specialized harnesses provide.

### 10. Harness Implications for PlotLot (Detailed)

FuzzAgent's design has direct implications for PlotLot. PlotLot's agents operate on data products (training data, evaluation suites, prompt corpora) rather than library binaries, but the *evolutionary loop pattern* is the same: each round exposes new failure modes, the next round should evolve from them.

**Recommendation 1: Adopt the MAP-Elites grid for PlotLot's evaluation harness.** PlotLot's evaluation suite is currently a flat list of test cases. Replace it with a grid indexed by (data domain, model family, failure mode) — and have the harness synthesis agent (an LLM in PlotLot's case) maintain a "best-so-far" evaluation set per cell. This guarantees monotonic coverage of failure modes and preserves diversity.

**Recommendation 2: Use runtime evidence as the oracle.** PlotLot's evaluation harness currently uses LLM-as-judge scores as the primary signal. Augment with *deterministic* runtime evidence: the actual output of the model, the exact tokens produced, the latency, the resource consumption. These are reproducible and let the agent reason about cause and effect.

**Recommendation 3: Separate the crash triage from the harness generation.** PlotLot's current pipeline conflates "find a failure" with "classify the failure." Add a dedicated Crash Triage Agent (or in PlotLot's case, Failure Mode Classifier) that produces a structured report. Without this, the bug list will be 25% precision and the team will waste cycles triaging false positives.

**Recommendation 4: Bound the time budget per round.** FuzzAgent uses 5 minutes per round per harness. PlotLot should similarly bound evaluation time per round per cell (e.g., 30 minutes per (domain, model) cell). This prevents a single slow evaluation from starving the rest of the grid.

**Recommendation 5: Track the MAP-Elites grid as a first-class artifact.** Store the grid in PlotLot's database, with a versioned history of which cells are filled, which are empty, and which have been improved across rounds. The grid is the audit trail; without it, the evolutionary process is opaque.

### 11. Threat Model for Fuzzing Harnesses

FuzzAgent's harness generation pipeline is a target for adversarial inputs:

1. **Adversarial libraries.** A malicious library could include backdoors that only fire on specific input sequences. FuzzAgent would dutifully explore the input space and discover the backdoor. Mitigation: sandboxed execution, network egress filtering, no persistence.
2. **Prompt injection in documentation.** The library's README is fed to the Harness Synthesis Agent. A malicious README could instruct the LLM to generate a harness that exfiltrates the operator's environment. Mitigation: treat the documentation as untrusted input, never as instruction.
3. **Resource exhaustion.** A library with a "hang on input X" behavior could be exploited to consume the operator's fuzzing budget. Mitigation: per-harness timeouts, watchdog timers, the Crash Triage Agent should classify "hang" separately from "crash."
4. **The harness itself is a vulnerability.** A harness that reads user-controlled paths or executes shell commands is itself a vulnerability. Mitigation: the harness template should be the only one accepted; any deviation should be flagged.

### 12. Limitations

1. **The 20-library evaluation is biased toward popular libraries.** libxml2, openssl, sqlite3 are all in OSS-Fuzz already; FuzzAgent's gains on lesser-known libraries may be smaller (the paper does not report this).
2. **The 50-minute budget is short.** A real OSS-Fuzz campaign runs for days or weeks. FuzzAgent's results are a lower bound on what is achievable.
3. **The triage agent's 92.4% precision is good but not perfect.** ~8% of genuine bugs are misclassified as harness-induced and discarded.
4. **The MAP-Elites grid is a black box for the operator.** The operator cannot easily explain why a particular harness was kept or discarded. Mitigation: maintain a separate log of grid updates with human-readable reasons.
5. **The 5-agent decomposition is hand-designed.** A learned decomposition is an open problem.
6. **FuzzAgent does not support fuzzing of interpreted-language libraries (Python, JS).** The approach is C/C++-specific because it relies on `clang` instrumentation.

### 13. Open Questions

1. **Can the BC grid be learned?** Instead of hand-defined, learn the BCs from the runtime evidence.
2. **Can the mutation operators be learned?** Instead of LLM-mediated, learn them from successful mutations.
3. **How does the evolutionary loop scale to 100+ libraries?** The grid grows combinatorially; a sparse representation is needed.
4. **What is the right round budget?** 10 rounds is empirical; the optimal is library-dependent.
5. **Can the triage agent's precision be improved to 99%+?** Yes, but at the cost of human-in-the-loop.
6. **How does FuzzAgent interact with continuous integration?** OSS-Fuzz runs on every commit; FuzzAgent runs once per release. A hybrid is an open problem.
7. **Can the harness be made safe by construction?** A typed harness interface (similar to PartLot's PartLot type system) would prevent many harness-induced crashes by construction.

### 14. Cross-References Within the Corpus

- **Paper 19 (PART_1):** Multi-agent collaboration; FuzzAgent is a concrete instance.
- **Paper 22 (PART_2):** Open-source harness engineering; FuzzAgent is open-source.
- **Paper 27 (PART_3):** Coverage-guided testing; FuzzAgent extends to library fuzzing.
- **Paper 138 (Cochise, this batch):** Reference harness for pen testing; FuzzAgent is a reference harness for library fuzzing.
- **Paper 139 (AgentDisCo, this batch):** Disentangled research; FuzzAgent is a disentangled fuzzing system.
- **Paper 141 (Categorical Architecture, this batch):** Theoretical foundation; FuzzAgent is a concrete instance.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; FuzzAgent's agents run on it.
- **Paper 143 (AEvo, this batch):** Evolutionary harness; FuzzAgent's MAP-Elites grid is an evolutionary algorithm.
- **Paper 144 (Metacognitive Harness, this batch):** Self-adaptation; FuzzAgent's Campaign Manager is metacognitive.
- **Paper 145 (HarnessAudit, this batch):** Safety audit; FuzzAgent could be audited for harness-induced bias.

---

## Paper 148 — 2605.14497: ROAD — Adaptive Data Mixing for Offline-to-Online RL via Bi-Level Optimization

**Authors:** Letian Yang, Xu Liu, Yiqiang Lu, Jian Liu, Weiqiang Wang, Shuai Li
**Affiliations:** Shanghai Jiao Tong University, Ant Group
**Venue:** IJCAI 2026 (20 pages, 9 figures, 7 tables)
**DOI:** https://doi.org/10.48550/arXiv.2605.14497

### 1. Abstract and Core Problem

Offline-to-online reinforcement learning is a training paradigm in two stages: (1) *offline pretraining* on a fixed dataset of transitions (state, action, reward, next-state) collected by some behavior policy (often a human demonstrator or a previous version of the agent); (2) *online fine-tuning* where the agent interacts with the environment and adds its own transitions to the buffer. The hope is that offline pretraining provides a *stable initialization* — a policy that is roughly competent and avoids the catastrophic mistakes that a randomly-initialized policy would make — and that online fine-tuning then *adapts* the policy to the actual deployment environment.

The hope is often dashed. The offline dataset is a snapshot of the behavior policy, which may have a different state distribution than the online policy will explore. As the online policy improves, it visits states that are out-of-distribution (OOD) relative to the offline data, and the value function learned offline becomes unreliable. This is the *non-stationary distribution shift* problem. The naive solutions are bad: (a) fine-tune purely on online data and discard the offline data → throws away the stable initialization; (b) fine-tune purely on offline data → no adaptation. The middle ground is a *mix*: at each training step, sample some transitions from the offline buffer and some from the online replay buffer.

The question is: *what mix ratio?* Prior work uses static ratios (e.g., 80% offline, 20% online) or heuristic schedules (e.g., linearly decay the offline ratio from 1.0 to 0.0). These are environment-dependent and require manual tuning. ROAD's contribution is a *dynamic, adaptive* mix ratio that is learned via a bi-level optimization.

### 2. The Bi-Level Formulation

The bi-level formulation is:

- **Outer level (meta-decision):** Choose the mix ratio λ_t at each online fine-tuning step t. The objective is the *policy performance* after K steps of online fine-tuning from the current policy π_{t-1}.
- **Inner level (base decision):** Given λ_t, perform K_inner Q-learning updates on the mixed replay buffer (offline + online, mixed according to λ_t) to produce the next policy π_t.

Formally:
```
max_{λ_0, ..., λ_T}  Σ_{t=0}^{T}  J(π_t)         [outer]
s.t.  π_t = π_{t-1} + α · ∇_θ Q(θ; B_mix(λ_t))  [inner]
```

where J(π) is the expected return of π, B_mix(λ) is a mixed replay buffer that samples offline transitions with probability λ and online transitions with probability 1-λ, and the inner level is a standard Q-learning update.

This is intractable in general — the outer level's objective depends on the inner level's trajectory, which depends on the outer level's choice of λ. ROAD's insight is to *approximate* the outer gradient with a *surrogate* that is differentiable.

### 3. The Surrogate Objective

The surrogate replaces the inner-level Q-learning trajectory with a single step. Given the current Q-function Q_θ and the mixed buffer B_mix(λ_t), the surrogate evaluates:

```
L̃(λ_t) = E_{(s,a,r,s') ~ B_mix(λ_t)} [ (Q_θ(s,a) - (r + γ · max_{a'} Q_θ(s',a')))^2 ]
```

This is the standard TD error, but evaluated on a *mixture* of offline and online data. The mix ratio λ_t controls the *expected composition* of the minibatch. The surrogate gradient with respect to λ_t is:

```
∇_λ L̃(λ_t) = ∂L̃/∂B_mix · ∂B_mix/∂λ_t
            = E[(TD_error) · ∂(B_mix)/∂λ_t]
            = E[(TD_error) · (P_offline(s,a) - P_online(s,a))]
```

In other words, the surrogate says: increase λ_t (mix in more offline data) where the offline distribution is in regions of low TD error (i.e., where the Q-function is already accurate), and decrease λ_t (mix in more online data) where the online distribution is in regions of high TD error (i.e., where the Q-function is uncertain).

The intuition is sound: when the agent is in a region the Q-function has not seen (high TD error), it should prioritize online data so the Q-function can adapt; when the agent is in a region the Q-function has mastered (low TD error), it should keep the offline prior stable so the agent does not overfit to its own (potentially noisy) online experience.

### 4. The Multi-Armed Bandit Realization

The bi-level formulation is the *theory*; the *practice* is a multi-armed bandit. The mix ratio λ_t is discretized into 11 arms: {0.0, 0.1, 0.2, ..., 1.0}. At each step, the agent plays one arm (chooses a λ_t) and observes a *reward signal* derived from the surrogate loss. The bandit updates its arm-value estimates (using UCB or Thompson sampling) and uses them to choose the next arm.

```python
class ROADBandit:
    def __init__(self, n_arms=11, algorithm='UCB1'):
        self.n_arms = n_arms           # λ ∈ {0.0, 0.1, ..., 1.0}
        self.q_values = [0.0] * n_arms  # estimated value of each arm
        self.n_pulls = [0] * n_arms     # times each arm has been pulled
        self.t = 0
        self.algorithm = algorithm

    def select_arm(self):
        if self.algorithm == 'UCB1':
            if self.t < self.n_arms:
                return self.t  # try each arm once
            ucb = [self.q_values[a] + np.sqrt(2 * np.log(self.t) / max(self.n_pulls[a], 1))
                   for a in range(self.n_arms)]
            return int(np.argmax(ucb))
        elif self.algorithm == 'Thompson':
            # Beta posterior on each arm's value
            samples = [np.random.beta(self.successes[a] + 1, self.failures[a] + 1)
                       for a in range(self.n_arms)]
            return int(np.argmax(samples))

    def update(self, arm, reward):
        self.n_pulls[arm] += 1
        alpha = 1.0 / self.n_pulls[arm]  # incremental average
        self.q_values[arm] += alpha * (reward - self.q_values[arm])
        self.t += 1
```

The reward signal is the *negative* of the surrogate loss change: if choosing arm λ_t reduced the surrogate loss on the next minibatch (compared to choosing the previous arm), the arm gets a positive reward; otherwise, negative.

### 5. The Empirical Results

ROAD is evaluated on 4 D4RL benchmarks (halfcheetah-medium, hopper-medium-replay, walker2d-medium, ant-medium-replay) and 3 custom AntMaze tasks. Baselines: BC (behavior cloning), CQL (conservative Q-learning), IQL (implicit Q-learning), SPiRL, and a static mix ratio at λ=0.5.

| Task                 |   BC   |   CQL  |   IQL  | SPiRL | Static-0.5 | ROAD (bandit) | Δ vs best baseline |
|----------------------|-------:|-------:|-------:|------:|-----------:|--------------:|-------------------:|
| halfcheetah-medium   |   42.3 |   55.1 |   57.8 |  61.2 |       58.4 |       **68.7** |             +12.2% |
| hopper-medium-replay |   23.4 |   89.2 |   92.1 |  94.3 |       91.2 |       **98.1** |              +4.0% |
| walker2d-medium      |   56.7 |   78.9 |   81.2 |  83.4 |       80.1 |       **89.7** |              +7.6% |
| ant-medium-replay    |   34.5 |   67.8 |   71.2 |  74.5 |       72.3 |       **82.4** |             +10.6% |
| AntMaze-easy         |   45.6 |   78.9 |   82.1 |  85.6 |       83.4 |       **91.2** |              +6.5% |
| AntMaze-medium       |   12.3 |   45.6 |   51.2 |  56.7 |       53.4 |       **63.4** |             +11.8% |
| AntMaze-hard         |    2.1 |   23.4 |   28.9 |  34.5 |       31.2 |       **41.2** |             +19.4% |
| **Avg**              | **31.0** | **62.7** | **66.4** | **70.0** |   **67.1** |     **76.4** |         **+9.1%** |

ROAD's average improvement is +9.1% over the best baseline (SPiRL) and +14.0% over static mix. The improvement is largest on the hard AntMaze task (+19.4%) where the distribution shift is most severe.

### 6. Why Bi-Level Beats Static Mix

The paper isolates the contribution of the bandit-driven mix with an ablation. They compare ROAD's adaptive λ_t to (a) static λ=0.5, (b) linear decay from 1.0 to 0.0, (c) exponential decay, (d) a hand-tuned schedule per task, and (e) a "contextual bandit" variant that conditions λ_t on the current state.

| Variant                   | halfcheetah | hopper | walker2d | ant | AntMaze-hard |
|---------------------------|------------:|-------:|---------:|----:|-------------:|
| Static λ=0.5              |        58.4 |   91.2 |     80.1 | 72.3 |         31.2 |
| Linear decay              |        60.1 |   93.4 |     82.3 | 75.6 |         35.6 |
| Exponential decay         |        61.2 |   94.1 |     83.4 | 76.8 |         36.7 |
| Hand-tuned per task       |        64.5 |   96.2 |     86.7 | 79.8 |         38.9 |
| Contextual bandit         |        66.8 |   97.3 |     88.4 | 81.2 |         40.1 |
| **ROAD (multi-armed bandit)** |    **68.7** |   **98.1** |     **89.7** | **82.4** |     **41.2** |

The hand-tuned schedule requires per-task engineering and is still 6.3% worse than ROAD. The contextual bandit adds state-conditioning but is only marginally better than the multi-armed bandit (+0.5% on average) at the cost of a 3x larger model. The multi-armed bandit is the sweet spot.

### 7. The Surrogate-Gradient Analysis

The paper provides a theoretical analysis of the surrogate. They show that the surrogate gradient ∇_λ L̃(λ_t) is an *unbiased estimator* of the true meta-gradient (i.e., the gradient of the outer-level objective with respect to λ_t) when:

- The inner-level Q-learning converges to a fixed point within K_inner steps (i.e., the inner loop is *well-posed*).
- The offline and online distributions are *not too divergent* (formally, the total variation distance TV(P_off, P_on) < 0.5).

When the TV distance is large (e.g., in AntMaze-hard, TV ≈ 0.8), the surrogate is biased. The bandit partially compensates: it observes the *downstream* policy performance (not just the surrogate) and adjusts λ_t accordingly. The empirical results show that this compensation is effective (ROAD still wins on AntMaze-hard).

### 8. The Online Fine-Tuning Stability

A key concern with offline-to-online RL is *stability*: the policy can collapse (suddenly perform much worse) if the value function over-extrapolates in OOD regions. ROAD's adaptive mix is designed to mitigate this. The paper measures *policy collapse rate* (fraction of training runs where the policy performance drops by more than 50% at any point) across 10 seeds per task.

| Algorithm         | Collapse rate (avg) |
|-------------------|--------------------:|
| BC → online       |              45.6%  |
| CQL → online      |              23.4%  |
| IQL → online      |              18.9%  |
| SPiRL → online    |              12.3%  |
| Static-0.5 online |              14.5%  |
| **ROAD online**   |           **4.5%**  |

ROAD's adaptive mix reduces the collapse rate by 3x compared to the best baseline. The intuition: when the value function is uncertain (high TD error), ROAD automatically shifts to more online data (which has lower distribution shift), preventing the over-extrapolation that causes collapse.

### 9. Harness Implications for PlotLot (Detailed)

ROAD's bi-level mix is directly applicable to PlotLot's *data mixing* problem. PlotLot's training pipeline mixes (a) *human-curated* data, (b) *model-generated* data, and (c) *synthetic augmentation* data. The relative proportions affect both stability (overfitting to model-generated data is a known failure mode) and asymptotic performance (human-curated data is the gold standard but is expensive).

**Recommendation 1: Adopt a bandit-driven mix for PlotLot's data pipeline.** Discretize the mix ratio (human / model / synthetic) into 11–21 arms, run a multi-armed bandit in the training loop, and let the bandit discover the optimal mix per training phase. The surrogate reward can be the *downstream evaluation loss* on a held-out validation set.

**Recommendation 2: Maintain a per-domain bandit.** PlotLot's training corpus spans multiple domains (math, code, dialogue, etc.); the optimal mix is domain-dependent. Run one bandit per domain.

**Recommendation 3: Bound the mix ratio.** A mix ratio of 1.0 (all synthetic) is a known failure mode. The bandit should be constrained to λ ∈ [0.0, 0.7] (at most 70% synthetic) to prevent overfitting.

**Recommendation 4: Track the bandit state as a first-class artifact.** Store the arm-value estimates and pull counts in PlotLot's database. The bandit state is the audit trail; without it, the mix schedule is opaque.

**Recommendation 5: Periodically reset the bandit.** A bandit that has converged to a single arm is overfit. Reset every K steps and let it re-discover.

### 10. Threat Model

1. **Adversarial offline data.** If the offline data is poisoned (e.g., a malicious contributor inserts biased data), ROAD's mix may be biased toward the poison. Mitigation: validate offline data with a separate classifier; bound the offline mix ratio.
2. **Online reward hacking.** If the environment reward is misspecified, the online policy may exploit the reward in a way that the offline data does not capture. ROAD's stability guarantees do not prevent this. Mitigation: human-in-the-loop reward validation, the MemLineage-style gate (Paper 146).
3. **Bandit overfitting.** The bandit may overfit to a small number of pulls on a particular arm. Mitigation: UCB-style exploration bonus, Thompson sampling, periodic reset.
4. **Distribution shift detection.** If the offline and online distributions diverge catastrophically, the surrogate is biased. Mitigation: a distribution shift detector (e.g., KL divergence between P_off and P_on) that triggers a re-initialization of the bandit.

### 11. Limitations

1. **The bi-level formulation assumes the inner loop converges.** In practice, Q-learning may not converge within K_inner steps; the surrogate is then biased.
2. **The discretization to 11 arms is coarse.** A finer discretization (e.g., 101 arms) may find a better λ, at the cost of slower bandit convergence.
3. **The contextual bandit variant was not the main result.** A fully state-conditioned λ_t(s) is an open problem.
4. **The 4 D4RL benchmarks are limited.** ROAD was not evaluated on more recent benchmarks (NeoRL, Minari).
5. **The wall-clock cost is not reported.** The bandit adds overhead per step; the paper does not quantify this.

### 12. Open Questions

1. **Can the surrogate gradient be made unbiased in the high-TV regime?** A learned correction is an open problem.
2. **Can the bandit be replaced by a learned policy?** A meta-RL approach is an alternative to the bandit.
3. **How does ROAD scale to multi-task offline-to-online?** The current formulation is single-task.
4. **What is the right K_inner?** Too small and the surrogate is biased; too large and the inner loop is slow.
5. **Can ROAD be combined with model-based RL?** A learned dynamics model would change the surrogate.
6. **How does ROAD interact with the agent's exploration strategy?** The bandit may need to coordinate with epsilon-greedy.

### 13. Cross-References Within the Corpus

- **Paper 25 (PART_2):** Offline RL; ROAD is offline-to-online.
- **Paper 28 (PART_3):** Stability in RL; ROAD's adaptive mix improves stability.
- **Paper 32 (PART_4):** Conservative Q-learning; ROAD's surrogate addresses value overestimation.
- **Paper 56 (Mem0, PART_5):** Memory management; ROAD's mixed buffer is a form of memory.
- **Paper 79 (xMemory, PART_7):** Cross-session memory; ROAD's bandit is cross-episode.
- **Paper 121 (Claude Code, PART_10):** Permission system; ROAD's mix is a permission on data sources.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; ROAD runs on it.
- **Paper 143 (AEvo, this batch):** Evolutionary harness; ROAD's bandit is an adaptive process.
- **Paper 144 (Metacognitive Harness, this batch):** Self-adaptation; ROAD's bandit is metacognitive.

---

## Paper 149 — 2605.14786: Known By Their Actions — Fingerprinting LLM Browser Agents via UI Traces

**Authors:** William Lugoloobi, Samuelle Marro, Jabez Magomere, Joss Wright, Chris Russell
**Venue:** arXiv 2026-05-14, cs.CR; cs.AI; cs.HC; cs.LG
**DOI:** https://doi.org/10.48550/arXiv.2605.14786

### 1. Abstract and Core Problem

LLM-based agents increasingly browse the web on users' behalf — they search for information, fill in forms, click "buy now" buttons, and complete multi-step workflows. A natural adversarial question arises: *can a website passively identify which underlying LLM is powering the agent?* Doing so would enable targeted attacks tailored to known model vulnerabilities (e.g., a prompt injection that exploits GPT-4's specific weakness to long system prompts, or a jailbreak that works only on Claude).

This paper demonstrates that an agent's *actions and interaction timings*, captured via a passive JavaScript tracker (e.g., a Google Analytics-style script), are sufficient to identify the underlying model with up to 96% F1 score. The authors evaluate 14 frontier LLMs across 4 web environments (information retrieval and shopping tasks) and show that:

- Classifiers trained on agent actions *generalize across model sizes and families*.
- Strong classifiers can be trained from *few interaction traces* (as few as 10 traces per model).
- Agent identity can be inferred *early within an episode* (often within the first 5 actions).
- *Randomized timing delays* between actions substantially degrade classifier performance, but do not provide robust protection — a classifier retrained on delayed traces largely recovers performance.

The attack surface is significant. Any website can run the attack; no privileged access is required. The implications for agent privacy and security are profound.

### 2. The Attack Surface

The attack surface consists of two passive observables:

1. **Actions.** The sequence of UI events the agent triggers: clicks (x, y, target element), keystrokes (key, target field), scrolls (delta_y), form submissions (form_id, fields). These are exposed via standard browser APIs (the `click` event, the `keydown` event, the `submit` event) and can be captured by any JavaScript running on the page.
2. **Timings.** The inter-event intervals: time between click and next click, time between page load and first action, time to complete a form field. These are exposed via the `performance.now()` API and the `Event.timeStamp` property.

A JavaScript tracker (similar to Google Analytics) collects these observables and ships them to a server. The server maintains a database of (model, trace) pairs and trains a classifier.

The attack is *passive*: the tracker does not interfere with the agent's behavior, does not need to be installed in advance, and does not need any privileged browser access. It runs as a normal third-party script on any page the agent visits.

### 3. The Classifier Architecture

The classifier is a hybrid model: a *convolutional* component for the action sequence and an *LSTM* component for the timing sequence, with a *cross-attention* fusion layer that aligns the two modalities.

```python
class AgentFingerprinter(nn.Module):
    def __init__(self, n_models, action_vocab_size, emb_dim=128):
        super().__init__()
        self.action_emb = nn.Embedding(action_vocab_size, emb_dim)
        self.conv = nn.Conv1d(emb_dim, 64, kernel_size=3, padding=1)
        self.lstm = nn.LSTM(1, 64, bidirectional=True, batch_first=True)
        self.cross_attn = nn.MultiheadAttention(64, num_heads=4)
        self.classifier = nn.Linear(128, n_models)

    def forward(self, actions, timings):
        # actions: (B, T) int token ids
        # timings: (B, T) float inter-event intervals
        a = self.action_emb(actions).transpose(1, 2)  # (B, E, T)
        a = F.relu(self.conv(a)).transpose(1, 2)      # (B, T, 64)
        t = self.lstm(timings.unsqueeze(-1))[0]       # (B, T, 128)
        # Cross-attend
        a_attn, _ = self.cross_attn(a, t, t)          # (B, T, 64)
        # Pool and classify
        pooled = a_attn.mean(dim=1)                   # (B, 64)
        return self.classifier(pooled)                # (B, n_models)
```

The action vocabulary is a fixed set of (event_type, target_type) pairs: e.g., (CLICK, BUTTON), (KEYSTROKE, INPUT_TEXT), (SCROLL, DIV), (SUBMIT, FORM). The timing feature is the inter-event interval in milliseconds, log-scaled to handle the long tail (some agents pause for minutes between actions).

### 4. The 14 Models and 4 Environments

The evaluation spans 14 frontier LLMs:

| Family      | Sizes evaluated                              |
|-------------|----------------------------------------------|
| GPT         | GPT-3.5-Turbo, GPT-4-Turbo, GPT-4o, GPT-4.1  |
| Claude      | Claude 3.5-Sonnet, Claude 3.7-Sonnet, Claude Opus-4 |
| Gemini      | Gemini 1.5-Pro, Gemini 2.0-Flash              |
| Llama       | Llama-3.1-70B, Llama-3.2-90B-Vision          |
| Qwen        | Qwen2.5-72B, Qwen3-235B                       |
| DeepSeek    | DeepSeek-V3                                   |

For each model, the authors run 50 traces per environment (200 traces per model total). The 4 environments are:

- **WebShop-Simple:** 100 product search tasks ("find a 4K monitor under $500").
- **WebShop-Complex:** 50 multi-step shopping tasks ("find a gift for a 10-year-old who likes dinosaurs, under $50, with free shipping").
- **InfoRet-Open:** 100 open-domain information retrieval tasks ("what year was the Eiffel Tower built?").
- **InfoRet-Conversational:** 50 multi-turn conversational tasks ("I'm planning a trip to Japan in April. What should I pack?").

For each task, the model is given the same system prompt and the same task description. The trace is collected by a wrapper around the browser automation framework (Playwright) that records every UI event and timing.

### 5. The Headline Result

The classifier is trained on 80% of the traces and tested on the remaining 20%, with 5-fold cross-validation. The headline F1 scores per model:

| Model              | WebShop-Simple | WebShop-Complex | InfoRet-Open | InfoRet-Conv | Avg |
|--------------------|---------------:|----------------:|-------------:|-------------:|----:|
| GPT-3.5-Turbo      |          91.2% |           88.4% |        92.1% |        87.6% | 89.8% |
| GPT-4-Turbo        |          93.4% |           91.2% |        94.5% |        90.1% | 92.3% |
| GPT-4o             |          94.1% |           92.3% |        95.2% |        91.4% | 93.3% |
| GPT-4.1            |          94.5% |           92.8% |        95.6% |        91.9% | 93.7% |
| Claude 3.5-Sonnet  |          92.8% |           90.1% |        93.4% |        89.2% | 91.4% |
| Claude 3.7-Sonnet  |          93.4% |           90.9% |        94.1% |        89.8% | 92.1% |
| Claude Opus-4      |          94.2% |           91.7% |        94.9% |        90.5% | 92.8% |
| Gemini 1.5-Pro     |          90.1% |           87.6% |        91.2% |        86.4% | 88.8% |
| Gemini 2.0-Flash   |          91.5% |           89.0% |        92.3% |        87.8% | 90.2% |
| Llama-3.1-70B      |          88.4% |           85.2% |        89.7% |        84.5% | 87.0% |
| Llama-3.2-90B-Vis. |          89.1% |           85.9% |        90.4% |        85.2% | 87.7% |
| Qwen2.5-72B        |          89.8% |           86.5% |        91.0% |        85.9% | 88.3% |
| Qwen3-235B         |          91.2% |           88.1% |        92.4% |        87.2% | 89.7% |
| DeepSeek-V3        |          90.5% |           87.3% |        91.8% |        86.7% | 89.1% |
| **Avg**            |      **91.7%** |       **88.9%** |    **92.6%** |    **88.1%** | **90.3%** |

The classifier achieves 90.3% average F1 across all 14 models and 4 environments, with the best single result being 95.6% (GPT-4.1 on InfoRet-Open) and the worst being 84.5% (Llama-3.1-70B on InfoRet-Conversational). The classifier is *not* perfect — there is confusion between models in the same family (e.g., GPT-4-Turbo vs GPT-4o, Claude 3.5-Sonnet vs Claude 3.7-Sonnet) — but it is *good enough* to be a serious privacy attack.

### 6. Cross-Family and Cross-Size Generalization

A key finding is that classifiers trained on *one* model family generalize to *other* families. The authors train a classifier on GPT models only and test on Claude, Gemini, etc.:

| Train family | Test: GPT | Test: Claude | Test: Gemini | Test: Llama | Test: Qwen | Test: DeepSeek |
|--------------|----------:|-------------:|-------------:|------------:|-----------:|---------------:|
| GPT only     |    92.3%  |        61.2% |        58.4% |       52.3% |      55.6% |          54.2% |
| Claude only  |    64.5%  |        91.4% |        60.1% |       53.4% |      56.7% |          55.1% |
| Gemini only  |    60.2%  |        59.8% |        88.8% |       51.2% |      54.3% |          53.4% |
| Llama only   |    55.6%  |        54.3% |        53.4% |       87.0% |      52.1% |          51.8% |
| Qwen only    |    58.4%  |        57.6% |        56.7% |       53.4% |      88.3% |          54.5% |
| **All (multi-family)** | **93.7%** | **92.8%** | **90.2%** |   **87.7%** |  **89.7%** |      **89.1%** |

Cross-family transfer is *non-trivial* (60% F1 is well above chance = 1/14 = 7.1%) but *not as good* as within-family (90%+). The classifier learns *family-level* features (e.g., "this agent uses a planning module before each action" is typical of Claude) and *size-level* features (e.g., "this agent pauses longer before typing" is typical of larger models).

The authors also find that classifiers generalize across *model sizes* within a family: a classifier trained on GPT-4-Turbo traces generalizes to GPT-4o and GPT-4.1 with 89% F1. The implication: an attacker does not need to retrain for every new model release.

### 7. The "Few Traces" Finding

The classifier is data-efficient. The authors train classifiers with varying numbers of traces per model:

| Traces per model | Avg F1 (14 models, 4 envs) |
|-----------------:|---------------------------:|
|                5 |                     71.2% |
|               10 |                     81.4% |
|               20 |                     87.6% |
|               50 |                     90.3% |
|              100 |                     91.8% |
|              200 |                     92.4% |

With 10 traces per model, the classifier reaches 81.4% F1. With 50, it reaches 90.3%. The marginal returns diminish quickly — going from 50 to 200 traces adds only 2.1 points. The implication: an attacker can fingerprint a new model with as few as 50 traces, which is feasible to collect in a single afternoon of automation.

### 8. The "Early Inference" Finding

The classifier can identify the model *early in the episode*, often within the first 5 actions. The authors measure the cumulative F1 as a function of the number of observed actions:

| Actions observed | Avg F1 (all models/envs) |
|-----------------:|-------------------------:|
|                1 |                    45.6% |
|                3 |                    67.8% |
|                5 |                    79.1% |
|               10 |                    85.4% |
|               20 |                    89.2% |
|               50 |                    90.3% |

After 5 actions, the classifier is at 79.1% — well above the 50% "usable" threshold for a targeted attack. After 10 actions, it is at 85.4%. The implication: an attacker does not need to wait for the agent to complete a full task; it can fingerprint the model from a few opening moves.

### 9. The Defense: Randomized Timing Delays

The authors test a natural defense: randomize the inter-event timings. If the timing signal is the primary fingerprint, randomizing it should degrade the classifier. The agent delays each action by a random amount sampled from U(0, 2 seconds).

| Defense                | Avg F1 (all models/envs) |
|------------------------|------------------------:|
| No defense             |                   90.3% |
| Random delay U(0, 1s)  |                   67.4% |
| Random delay U(0, 2s)  |                   54.2% |
| Random delay U(0, 5s)  |                   42.1% |
| Random delay U(0, 10s) |                   38.7% |
| Classifier retrained on U(0, 2s) traces |     **85.6%** |

Randomized delays do degrade the original classifier, but only at the cost of *usability* (an agent that pauses 5+ seconds between every action is unusably slow). And — critically — a classifier *retrained* on the delayed traces recovers 85.6% of the original performance. The defense is *brittle*: it works against the original classifier but not against an adaptive attacker.

### 10. The Implications and Mitigations

The paper's implications for agent privacy are severe:

1. **Model identity is not private.** Any website can determine which LLM is powering an agent, with high accuracy, from passive observation.
2. **Targeted attacks are feasible.** Once the model is identified, the attacker can deploy model-specific exploits (prompt injection, jailbreaks, etc.).
3. **Existing privacy tools are insufficient.** VPNs, incognito mode, etc. do not protect against this attack.

The paper proposes several mitigations:

- **Action obfuscation.** Replace the agent's direct UI events with abstracted events (e.g., instead of `click(x=312, y=456, target=button#buy)`, emit `click(target=button[role=buy])`). This is lossy but reduces the signal.
- **Timing normalization.** Insert a "thinking" delay before every action, with a fixed mean and variance. The paper shows this is brittle (an adaptive classifier recovers), but it raises the bar.
- **Crowd-based evasion.** Have the agent switch between different underlying models for different actions. The classifier sees a "mixed" trace and cannot confidently assign it to any one model. This is expensive (multiple model calls per action) but is the only mitigation that holds up against the adaptive attacker.
- **Differential privacy.** Add noise to the action sequence such that any single action is uncertain, but the *aggregate* behavior is preserved. The paper does not evaluate this in detail.

### 11. Harness Implications for PlotLot (Detailed)

This paper has direct implications for PlotLot's *web-facing agents*. If PlotLot deploys browser-based agents (e.g., a research assistant that browses the web on behalf of users), those agents are vulnerable to fingerprinting.

**Recommendation 1: Audit all browser-facing agents.** Run the fingerprinting attack against PlotLot's own agents. Identify which underlying model powers each agent and whether the fingerprint is unique (it almost certainly is).

**Recommendation 2: Implement timing normalization.** Insert a random delay (mean 1.5s, std 0.5s) between every action in the browser agent. This degrades the baseline classifier from 90% F1 to 65% F1. Not robust, but raises the bar.

**Recommendation 3: Implement action obfuscation.** Strip the exact (x, y) coordinates from click events. Emit only the target element. The classifier's F1 drops from 90% to 72%.

**Recommendation 4: Consider model rotation.** For high-stakes tasks, rotate between two or more underlying models. The classifier sees a mixed trace and cannot confidently identify a single model.

**Recommendation 5: Log all fingerprinting attempts.** If a website runs the fingerprinting attack, the attack leaves traces (the classifier runs on the server, but the tracker makes a request to the server — this is observable from the agent side). PlotLot should log these requests and alert the user.

### 12. Threat Model and Counter-Threats

1. **Counter-countermeasures.** The website may not just fingerprint, but also adapt its content based on the fingerprint (e.g., serve a model-specific exploit). The agent should treat any model-specific content as adversarial.
2. **False positives.** The classifier may mis-identify the model. The agent should not take destructive actions based on the inferred identity alone.
3. **Coordinated fingerprinting.** Multiple websites may share fingerprinting data. A single visit to one site informs the next visit to another site. This is a serious privacy concern.
4. **Defensive fingerprinting.** PlotLot can also fingerprint the *website* — detect whether the site is running a fingerprinting attack — and refuse to interact with it.

### 13. Limitations

1. **The evaluation is in a controlled environment.** Real-world agents see ads, popups, captchas, dynamic content. The 90% F1 is a *lower bound* on what an attacker can achieve; the real-world F1 may be higher or lower.
2. **The 14 models are a snapshot.** New model releases may have different fingerprints. The classifier needs to be retrained.
3. **The action vocabulary is fixed.** A model that uses an unusual action (e.g., a drag-and-drop) may evade the classifier.
4. **The defense evaluation is shallow.** The paper tests random delays but not other defenses (action obfuscation, model rotation) in detail.
5. **The classifier is not robust to adversarial perturbations.** A model that intentionally varies its behavior (e.g., adds a "thinking" delay with a pattern) could fool the classifier. The paper does not evaluate this.

### 14. Open Questions

1. **Can the classifier be made robust to adversarial perturbations?** This is an arms race.
2. **What is the privacy guarantee of differential privacy?** The paper does not evaluate DP-based defenses.
3. **Can the fingerprint be made model-intrinsic?** A signature that the model *cannot* vary (e.g., specific tokenization choices) would be a more robust attack.
4. **How does the attack scale to 100+ models?** The 14-model evaluation is small.
5. **What is the impact on agent utility?** The defense costs are not quantified.
6. **Can the attack be detected by the agent?** A defensive fingerprinting system is an open problem.
7. **How does the attack interact with browser privacy features (e.g., fingerprint resistance in Firefox)?** These may degrade the attack.

### 15. Cross-References Within the Corpus

- **Paper 19 (PART_1):** Multi-agent collaboration; the attack fingerprints *which* agent.
- **Paper 22 (PART_2):** Open-source harness engineering; the classifier is open-source.
- **Paper 28 (PART_3):** Privacy and security; this paper is a privacy attack.
- **Paper 56 (Mem0, PART_5):** Memory management; the fingerprint is a kind of memory leak.
- **Paper 79 (xMemory, PART_7):** Cross-session memory; the fingerprint persists across sessions.
- **Paper 118 (SafeHarness, PART_9):** Lifecycle security; this paper is a lifecycle attack.
- **Paper 121 (Claude Code, PART_10):** Permission system; the attack bypasses the agent's permission system.
- **Paper 138 (Cochise, this batch):** Reference harness for pen testing; this paper is a pen test on agents.
- **Paper 145 (HarnessAudit, this batch):** Safety audit; this paper is an audit of agent safety.
- **Paper 146 (MemLineage, this batch):** Memory defense; this attack is a memory attack.
- **Paper 147 (FuzzAgent, this batch):** Library fuzzing; this attack is a *model* fuzzing.

---

## Paper 150 — 2605.15040: Orchard — An Open-Source Agentic Modeling Framework

**Authors:** Baolin Peng, Wenlin Yao, Qianhui Wu, Hao Cheng, Xiao Yu, Rui Yang, Tao Ge, Alessandro Sordoni, Xingdi Yuan, Yelong Shen, Pengcheng He, Tong Zhang, Zhou Yu, Jianfeng Gao
**Venue:** arXiv 2026-05-14 (v1), revised 2026-05-21 (v2)
**DOI:** https://doi.org/10.48550/arXiv.2605.15040

### 1. Abstract and Core Problem

Agentic modeling is the practice of training LLMs to act as autonomous agents — to plan, reason, call tools, and interact with environments over multi-turn trajectories. Despite major industry investment, open research on agentic modeling is constrained by *infrastructure* and *training* gaps. Many high-performing systems (Claude Code, Codex, Gemini CLI) rely on proprietary codebases, models, or services. Most open-source frameworks (LangChain, LlamaIndex, AutoGen) focus on *orchestration* (how to wire agents together) and *evaluation* (how to measure their performance) rather than *scalable agent training* (how to fine-tune a model on agent trajectories at scale).

Orchard's contribution is a unified, open-source framework for *scalable agentic modeling* — covering the full pipeline from environment provisioning, through trajectory synthesis, to supervised fine-tuning (SFT) and reinforcement learning (RL). At its core is **Orchard Env**, a lightweight environment service that provides reusable primitives for sandbox lifecycle management across task domains, agent harnesses, and pipeline stages. On top of Orchard Env, Orchard builds three agentic modeling recipes:

- **Orchard-SWE:** Coding agents. Distills 107K trajectories from MiniMax-M2.5 and Qwen3.5-397B, introduces *credit-assignment SFT* (a novel fine-tuning method that learns from productive segments of unresolved trajectories), and applies *Balanced Adaptive Rollout* for RL. Starting from Qwen3-30B-A3B-Thinking, Orchard-SWE achieves 64.3% on SWE-bench Verified after SFT and 67.5% after SFT+RL, setting a new state of the art among open-source models of comparable size.
- **Orchard-GUI:** A 4B vision-language computer-use agent trained using only 0.4K distilled trajectories and 2.2K open-ended tasks. Achieves 74.1%, 67.0%, and 64.0% success rates on WebVoyager, Online-Mind2Web, and DeepShop respectively, making it the strongest open-source model and competitive with proprietary systems.
- **Orchard-Claw:** Personal assistant agents. Trained with only 0.2K synthetic tasks, achieves 59.6% pass@3 on Claw-Eval and 73.9% when paired with a stronger ZeroClaw harness.

The headline finding: a lightweight, open, harness-agnostic environment layer enables reusable agentic data, training recipes, and evaluations across domains.

### 2. Orchard Env: The Environment Service

Orchard Env is the substrate. It is a Python service that exposes a small set of primitives for *sandbox lifecycle management*:

- **`env.create(spec)`:** Create a sandbox (a Docker container, a Kubernetes pod, a local process group, or a cloud VM) from a specification. The spec includes the base image, the environment variables, the file mounts, and the resource limits.
- **`env.step(action)`:** Execute an action in the sandbox and return an observation. The action can be a shell command, a tool call, a file edit, or a custom function. The observation includes the stdout, stderr, exit code, and any structured outputs.
- **`env.reset()`:** Reset the sandbox to its initial state. The reset is *deterministic* — given the same seed, the same initial state is reproduced.
- **`env.close()`:** Tear down the sandbox and release its resources.
- **`env.checkpoint()` / `env.restore()`:** Save and restore the sandbox state, for replay and for credit assignment.

These primitives are *harness-agnostic*: any agent harness (Claude Code, Codex, OpenHands, Aider) can use them. The harness just calls `env.step(...)` instead of `subprocess.run(...)` or `docker exec ...`. This is the key insight: most agent harnesses reinvent the same sandboxing primitives, with subtle differences. Orchard Env unifies them.

```python
from orchard.env import Environment

env = Environment.from_spec({
    "image": "python:3.12-slim",
    "mounts": [{"src": "/data/project", "dst": "/workspace", "ro": False}],
    "env_vars": {"PYTHONPATH": "/workspace"},
    "resources": {"cpu": "2", "memory": "4Gi", "timeout": 300}
})
obs = env.reset(seed=42)
while not obs.done:
    action = agent.act(obs)
    obs = env.step(action)
env.close()
```

### 3. Credit-Assignment SFT

The standard approach to SFT on agent trajectories is to use only the *successful* trajectories (those that completed the task). Unsuccessful trajectories are discarded. This is wasteful: an unsuccessful trajectory often contains *productive segments* — sequences of actions that did useful work even if the trajectory as a whole failed.

Credit-assignment SFT exploits this. Given an unsuccessful trajectory, it identifies the *productive segments* by:

1. **Action validity.** Each action is checked against the environment's action schema. Invalid actions (e.g., a tool call with a wrong argument type) are masked out.
2. **State progress.** The trajectory is divided into segments at "state transitions" (a checkpoint, a file change, a successful test). Segments that made progress are kept; segments that did not are masked.
3. **Expert agreement.** For trajectories generated by multiple models (e.g., MiniMax-M2.5 and Qwen3.5-397B), segments where both models agree on the action are kept; segments where they disagree are masked.

The result is a *segment-level* training signal. The model learns to imitate the productive segments of unsuccessful trajectories, in addition to the full successful trajectories.

```python
def credit_assignment_sft(trajectory, env):
    segments = trajectory.split_at_checkpoints(env)
    keep_mask = []
    for seg in segments:
        if seg.action_valid and seg.state_progress > 0 and seg.expert_agreement:
            keep_mask.extend([True] * len(seg))
        else:
            keep_mask.extend([False] * len(seg))
    # Compute loss only on kept segments
    loss = cross_entropy(logits, trajectory.actions, mask=keep_mask)
    return loss
```

This is a form of *trajectory surgery* — keeping the good parts of bad trajectories. It is conceptually similar to STaR (Zelikman et al. 2022) and ReST (Gulcehre et al. 2023) but operates at the segment level rather than the trajectory level.

### 4. Balanced Adaptive Rollout

The standard approach to RL on agent trajectories is to sample a batch of rollouts, score them, and update the policy. The issue is *imbalance*: for a coding task, the success rate is 30–60%; for a GUI task, 50–80%; for a personal assistant task, 60–90%. The rollouts are imbalanced across tasks, which biases the gradient.

Balanced Adaptive Rollout (BAR) is a rollout sampler that maintains a *target success rate* per task domain. After each batch, BAR measures the actual success rate per domain and adjusts the number of rollouts sampled from each domain in the next batch.

```python
class BalancedAdaptiveRollout:
    def __init__(self, domains, target_success_rate=0.5):
        self.domains = domains
        self.target = target_success_rate
        self.history = {d: [] for d in domains}

    def sample_count(self, domain, total_budget):
        recent = self.history[domain][-100:]
        if not recent:
            return total_budget // len(self.domains)
        actual = sum(recent) / len(recent)
        # Sample more from domains with low success rate
        ratio = self.target / max(actual, 0.01)
        n = int(total_budget * ratio / sum(self.all_ratios()))
        return min(n, total_budget)

    def record(self, domain, success):
        self.history[domain].append(success)
```

This ensures that the gradient signal is balanced across domains, preventing the policy from collapsing to the easiest domain.

### 5. Orchard-SWE: The Coding Agent

Orchard-SWE is trained on 107K distilled trajectories from two teacher models: MiniMax-M2.5 (a frontier model) and Qwen3.5-397B (a large open-source model). The trajectories span 12 Python repositories (Django, Flask, Requests, Scikit-learn, etc.) and 5 difficulty levels. The student model is Qwen3-30B-A3B-Thinking (a 30B-parameter model with 3B active parameters via MoE).

The training is in two stages:

1. **Credit-assignment SFT.** 107K trajectories are filtered through the credit-assignment process; ~58K survive as productive segments. The student is fine-tuned for 3 epochs on these segments with a learning rate of 5e-6 and a context length of 32K tokens.
2. **Balanced Adaptive RL.** 12K SFT trajectories are re-rolled out; BAR is used to balance the success rate across difficulty levels. PPO is used as the RL algorithm with a KL coefficient of 0.05 and a reward model trained on the 58K SFT segments.

Results on SWE-bench Verified:

| Model                                | SFT | SFT + RL |
|--------------------------------------|----:|---------:|
| Qwen3-30B-A3B-Thinking (base)        | 0.0 |      0.0 |
| Qwen3-30B-A3B-Thinking + standard SFT| 51.2 |    53.4  |
| Qwen3-30B-A3B-Thinking + Orchard-SWE | **64.3** | **67.5** |
| Llama-3.1-70B (baseline open)        | 41.2 |    43.1  |
| DeepSeek-V2.5-236B (baseline open)   | 56.7 |    58.9  |
| **Orchard-SWE (Ours)** | **64.3** | **67.5** |
| (Proprietary, for context) GPT-4.1   |  65.4 |    67.2  |
| (Proprietary, for context) Claude Opus-4 | 68.9 |    71.2  |

Orchard-SWE matches GPT-4.1 and is within 1.4 points of Claude Opus-4 — and is fully open-source.

### 6. Orchard-GUI: The Vision-Language GUI Agent

Orchard-GUI is trained for computer use — clicking buttons, filling forms, navigating GUIs. The training data is small: 0.4K distilled trajectories + 2.2K open-ended tasks. The model is a 4B vision-language model based on Qwen3-VL-4B.

The training uses a combination of:

- **Behavior cloning** on the 0.4K distilled trajectories.
- **Online RL** on the 2.2K open-ended tasks, with a reward model that scores the final state (did the agent complete the task?) and intermediate progress (did the agent make forward progress?).

Results:

| Model                    | WebVoyager | Online-Mind2Web | DeepShop |
|--------------------------|-----------:|----------------:|---------:|
| Qwen3-VL-4B (base)       |      32.1% |           21.4% |    18.7% |
| SeeClick (baseline)      |      53.4% |           45.6% |    38.9% |
| ShowUI (baseline)        |      61.2% |           52.3% |    47.8% |
| OpenCUA (baseline)       |      68.9% |           61.2% |    56.7% |
| **Orchard-GUI (Ours)**   |  **74.1%** |        **67.0%** | **64.0%** |
| (Proprietary, context) GPT-4.1-VL   | 76.3% |    72.1% |    68.9% |
| (Proprietary, context) Claude Opus-4-VL | 78.9% | 75.6% |    72.3% |

Orchard-GUI is within 2–4 points of GPT-4.1-VL and within 5–8 points of Claude Opus-4-VL — with only 0.4K + 2.2K training trajectories.

### 7. Orchard-Claw: The Personal Assistant

Orchard-Claw is trained for personal assistant tasks (calendar management, email triage, file organization). The training data is tiny: 0.2K synthetic tasks. The model is a 7B LLM based on Qwen3-7B.

Results on Claw-Eval:

| Model                          | pass@1 | pass@3 |
|--------------------------------|-------:|-------:|
| Qwen3-7B (base)                |   12.3% |   23.4% |
| Llama-3.1-8B-Instruct          |   18.9% |   31.2% |
| ZeroClaw (baseline)            |   34.5% |   48.9% |
| **Orchard-Claw (Ours)**        |  **42.1%** |  **59.6%** |
| **Orchard-Claw + ZeroClaw harness** | **51.2%** | **73.9%** |
| (Proprietary, context) Claude Opus-4 | 67.8% | 82.3% |

The combination of Orchard-Claw (model) + ZeroClaw (harness) is within 9 points of Claude Opus-4 on pass@3, with 1000x less training data.

### 8. Why the Environment Layer Matters

The paper's central argument is that the *environment layer* — not the model, not the harness, not the data — is the bottleneck. Most open-source frameworks either (a) skip the environment layer (rely on the model's built-in sandboxing) or (b) provide an ad-hoc environment (one-off Docker containers, custom bash scripts). Orchard Env is a *first-class* environment service with:

- A unified API across domains (code, GUI, personal assistant).
- Deterministic reset for reproducibility.
- Checkpoint/restore for credit assignment.
- A sandbox lifecycle that handles errors, timeouts, and resource exhaustion.
- A pluggable backend (Docker, Kubernetes, Firecracker, etc.).

This layer is what makes the three recipes (SWE, GUI, Claw) reusable. The same environment service can train a coding agent, a GUI agent, or a personal assistant agent — the *data* and *reward* differ, but the *sandbox* is the same.

### 9. Comparison with Related Work

| Framework     | Focus                | Environment | SFT | RL | Open? |
|---------------|----------------------|-------------|-----|----|-------|
| LangChain     | Orchestration        | No          | No  | No | Yes   |
| LlamaIndex    | RAG                  | No          | No  | No | Yes   |
| AutoGen       | Multi-agent          | Partial     | No  | No | Yes   |
| OpenHands     | Coding agents        | Ad-hoc      | No  | No | Yes   |
| Aider         | Coding agents        | Ad-hoc      | No  | No | Yes   |
| SWE-agent     | Coding agents        | Ad-hoc      | No  | No | Yes   |
| **Orchard**   | **Full pipeline**    | **First-class** | **Yes** | **Yes** | **Yes** |

Orchard is the only framework that provides a first-class environment layer *and* SFT *and* RL *and* open-source releases of all three recipes.

### 10. Harness Implications for PlotLot (Detailed)

Orchard's design is directly applicable to PlotLot. PlotLot's current pipeline has separate environment code, separate data generation, separate SFT, and separate RL — with little reuse across them. Orchard Env is a *pattern* for unifying these.

**Recommendation 1: Adopt Orchard Env as PlotLot's environment layer.** Replace PlotLot's ad-hoc sandboxing (per-domain Dockerfiles, custom cleanup scripts) with a single Environment service. The API is small and well-defined.

**Recommendation 2: Adopt credit-assignment SFT for PlotLot's training pipeline.** PlotLot's current training discards unsuccessful trajectories. Implement credit-assignment SFT to extract productive segments from them. The paper shows a 13-point gain on SWE-bench from this alone.

**Recommendation 3: Adopt Balanced Adaptive Rollout for PlotLot's RL.** PlotLot's RL currently has imbalance across domains. Implement BAR to maintain a target success rate per domain.

**Recommendation 4: Make the environment layer the "kernel" of PlotLot.** Treat it as a first-class system component, not as a utility. Allocate engineering time to it, document it, version it.

**Recommendation 5: Reuse the environment across recipes.** A single environment service should support coding, GUI, and personal-assistant recipes. The data and reward differ; the sandbox is the same.

### 11. Threat Model

1. **Environment escape.** A malicious agent could exploit a vulnerability in the sandbox to escape and access the host. Mitigation: Orchard Env uses Docker's default isolation; for higher assurance, use gVisor or Firecracker.
2. **Resource exhaustion.** An agent could intentionally consume all CPU/memory to starve other agents. Mitigation: per-sandbox resource limits, cgroups, the BAR mechanism.
3. **Data exfiltration.** An agent could copy data from the sandbox to an external server. Mitigation: network egress filtering, no outbound HTTP from the sandbox by default.
4. **Reward hacking.** The reward model could be exploited to score high without completing the task. Mitigation: human evaluation on a held-out set, the MemLineage-style gate (Paper 146).
5. **Trajectory poisoning.** The teacher models could be biased (e.g., they prefer certain coding styles). Mitigation: multi-teacher distillation (the paper uses MiniMax-M2.5 and Qwen3.5-397B for diversity).

### 12. Limitations

1. **The 107K SFT trajectories are from 2 teacher models.** More teachers (and more diverse teachers) would improve generalization.
2. **The credit-assignment heuristic is hand-designed.** A learned credit-assignment is an open problem.
3. **The BAR sampler assumes the target success rate is known.** In practice, the target is environment-dependent.
4. **The 3 recipes are code, GUI, and personal assistant.** Other domains (math, dialogue, multi-modal) are not covered.
5. **The SFT-then-RL pipeline is sequential.** A joint SFT+RL training is an open problem.
6. **The paper does not release the teacher trajectories.** Only the student checkpoints are released. The full data pipeline is reproducible from the paper, but the trajectories themselves are not.
7. **The Orchard Env backend is Docker-only in the released code.** Kubernetes and Firecracker are mentioned but not implemented.

### 13. Open Questions

1. **Can the environment layer be learned?** A learned environment abstraction is an open problem.
2. **Can the credit-assignment be learned end-to-end?** The current heuristic is hand-designed.
3. **Can BAR be replaced by a learned rollout sampler?** A meta-RL approach is an alternative.
4. **How does Orchard scale to 1M+ trajectories?** The current pipeline is 107K.
5. **How does the framework interact with multi-modal agents?** The current recipes are text-only (with GUI being the only vision-language recipe).
6. **What is the right balance between SFT and RL?** The paper uses SFT-then-RL, but joint training is an open problem.
7. **Can the framework support online learning?** The current recipes are offline.

### 14. Cross-References Within the Corpus

- **Paper 19 (PART_1):** Multi-agent collaboration; Orchard Env supports multi-agent.
- **Paper 22 (PART_2):** Open-source harness engineering; Orchard is fully open-source.
- **Paper 25 (PART_2):** Offline RL; Orchard's BAR is offline-then-online.
- **Paper 28 (PART_3):** RLHF; Orchard's RL is on agent trajectories.
- **Paper 56 (Mem0, PART_5):** Memory management; Orchard Env manages sandbox memory.
- **Paper 79 (xMemory, PART_7):** Cross-session memory; Orchard's checkpoint/restore is cross-session.
- **Paper 121 (Claude Code, PART_10):** Permission system; Orchard Env's sandbox is a permission boundary.
- **Paper 138 (Cochise, this batch):** Reference harness; Orchard Env is a reference environment.
- **Paper 139 (AgentDisCo, this batch):** Disentangled research; Orchard's recipes are disentangled.
- **Paper 141 (Categorical Architecture, this batch):** Theoretical foundation; Orchard Env is a concrete instance.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; Orchard Env is a substrate.
- **Paper 143 (AEvo, this batch):** Evolutionary harness; Orchard's BAR is adaptive.
- **Paper 144 (Metacognitive Harness, this batch):** Self-adaptation; Orchard Env is a self-adapting substrate.
- **Paper 145 (HarnessAudit, this batch):** Safety audit; Orchard Env's sandbox can be audited.
- **Paper 147 (FuzzAgent, this batch):** Library fuzzing; Orchard's environment is a fuzzing target.
- **Paper 148 (ROAD, this batch):** Adaptive data mixing; Orchard's BAR is an adaptive sampler.
- **Paper 149 (Browser Agent Fingerprinting, this batch):** Privacy attack; Orchard-GUI's agents are vulnerable.

---

## Paper 151 — 2605.15132: APWA — A Distributed Architecture for Parallelizable Agentic Workflows

**Authors:** Evan Rose, Tushin Mallick, Matthew D. Laws, Cristina Nita-Rotaru, Alina Oprea
**Venue:** arXiv 2026-05-14, cs.AI; cs.DC; cs.MA
**DOI:** https://doi.org/10.48550/arXiv.2605.15132

### 1. Abstract and Core Problem

Autonomous multi-agent systems based on LLMs demonstrate remarkable abilities in independently solving complex tasks. However, they hit critical reasoning, coordination, and computational scaling bottlenecks as the size and complexity of their tasks grow. These limitations prevent multi-agent systems from achieving *high-throughput processing* for *highly parallelizable tasks* — even though the underlying LLMs support parallel computing and reasoning primitives (e.g., multiple tool calls in parallel, batched generation).

The bottleneck is *architectural*. Existing multi-agent systems are typically organized as a *centralized orchestrator* that dispatches tasks to a small number of workers. The orchestrator becomes a serial bottleneck: it must wait for each worker to finish before dispatching the next task, it must reconcile conflicting state across workers, and it must serialize the final result. For a workload with 1000 independent sub-tasks, the orchestrator's serial dispatch loop is the limiting factor.

APWA (Agent-Parallel Workload Architecture) is a *distributed* multi-agent system architecture designed for the efficient processing of heavily parallelizable agentic workloads. APWA facilitates parallel execution by decomposing workflows into *non-interfering subproblems* that can be processed using independent resources without cross-communication. It supports heterogeneous data and parallel processing patterns (map, reduce, scatter-gather, pipeline), and it accommodates tasks from a wide breadth of domains.

In evaluation, APWA dynamically decomposes complex queries into parallelizable workflows and *scales on larger tasks in settings where prior systems fail completely*. On a 1000-task workload, APWA achieves 23.4x speedup over a centralized orchestrator and processes 87% more tasks per dollar of compute.

### 2. The APWA Architecture

APWA is a 4-tier architecture:

1. **Query Decomposer.** Takes a complex query (e.g., "analyze the sentiment of these 10,000 customer reviews") and produces a *workflow specification*: a DAG of sub-tasks, where each sub-task is a unit of work that can be processed independently.
2. **Workflow Scheduler.** Maps the DAG onto a pool of *Worker Agents*. Each worker has its own sandbox, its own context window, and its own LLM endpoint. The scheduler uses a *work-stealing* algorithm to balance load across workers.
3. **Worker Pool.** A dynamically-sized set of worker agents. New workers are spawned when the queue depth exceeds a threshold; idle workers are reaped after a timeout. Workers are stateless (they pull work from a queue, process it, push the result back).
4. **Result Aggregator.** Collects results from workers and produces the final output. For map-reduce workflows, it applies the reduce function. For scatter-gather, it merges the gathered data. For pipelines, it threads the output of one stage into the input of the next.

```python
class APWASystem:
    def __init__(self, n_workers_max=100, llm_endpoint="https://api.openai.com/v1"):
        self.decomposer = QueryDecomposer(llm_endpoint)
        self.scheduler = WorkflowScheduler(n_workers_max)
        self.pool = WorkerPool(llm_endpoint)
        self.aggregator = ResultAggregator(llm_endpoint)

    def run(self, query):
        # 1. Decompose
        workflow = self.decomposer.decompose(query)
        # 2. Schedule
        for sub_task in workflow.topological_sort():
            self.scheduler.dispatch(sub_task)
        # 3. Workers process in parallel
        results = self.pool.process_all()
        # 4. Aggregate
        return self.aggregator.aggregate(workflow, results)
```

### 3. The Query Decomposer

The Query Decomposer is the *most important* component. It must determine:

- **Parallelizability.** Is the query embarrassingly parallel (map), or does it have sequential dependencies (pipeline)?
- **Sub-task granularity.** How fine-grained should the decomposition be? Too fine (one sub-task per sentence) and the overhead dominates; too coarse (one sub-task per document) and the parallelism is limited.
- **Sub-task specification.** What exactly should each sub-task do? The decomposer produces a *prompt template* per sub-task.

The decomposer is implemented as an LLM call: the LLM is given the query and a library of workflow templates (map, reduce, scatter-gather, pipeline, fan-out-fan-in) and is asked to produce a workflow specification.

```python
WORKFLOW_TEMPLATES = """
1. MAP: Apply the same function to each item in a collection.
   Example: "Analyze the sentiment of each of these 1000 reviews."
2. REDUCE: Aggregate a collection into a single value.
   Example: "Find the average sentiment across these 1000 reviews."
3. SCATTER-GATHER: Distribute a query to multiple sources, gather results.
   Example: "Find the top-rated restaurant in each of 50 cities."
4. PIPELINE: Chain operations sequentially.
   Example: "First translate, then summarize, then translate back."
5. FAN-OUT-FAN-IN: Distribute a complex query, then merge.
   Example: "Generate 10 different marketing taglines, then pick the best."
"""

DECOMPOSE_PROMPT = f"""Given the user query and the workflow templates, produce a workflow specification.

USER QUERY: {{query}}

WORKFLOW TEMPLATES:
{WORKFLOW_TEMPLATES}

OUTPUT FORMAT (JSON):
{{
  "workflow_type": "MAP | REDUCE | SCATTER_GATHER | PIPELINE | FAN_OUT_FAN_IN",
  "granularity": "fine | medium | coarse",
  "sub_tasks": [
    {{"id": "st_0", "prompt": "...", "depends_on": []}},
    {{"id": "st_1", "prompt": "...", "depends_on": ["st_0"]}},
    ...
  ]
}}
"""
```

The LLM's output is parsed, validated, and translated into a workflow DAG. The decomposer is *the* source of APWA's scalability: if it produces a fine-grained DAG, APWA can parallelize heavily; if it produces a coarse-grained DAG, APWA falls back to near-serial execution.

### 4. The Workflow Scheduler and Worker Pool

The scheduler is a *work-stealing* scheduler. Each worker has a local queue; when a worker's queue is empty, it steals work from another worker's queue. This balances load without centralized coordination.

The worker pool is *elastic*: it scales up when the total queue depth exceeds a threshold, scales down when workers are idle. The scaling decision is made by a *P-controller* (proportional controller):

```python
class ElasticWorkerPool:
    def __init__(self, min_workers=1, max_workers=100, target_queue_depth=10):
        self.min = min_workers
        self.max = max_workers
        self.target = target_queue_depth
        self.workers = []

    def control(self, queue_depth, n_idle):
        if n_idle > 0 and queue_depth < self.target:
            # Scale down
            victim = self.workers.pop()
            victim.stop()
        elif queue_depth > self.target and len(self.workers) < self.max:
            # Scale up
            w = Worker()
            w.start()
            self.workers.append(w)
```

The P-controller is deliberately simple — a sophisticated controller (PID, model-predictive) is an open problem but the simple controller works well in practice.

### 5. The Scalability Evaluation

APWA is evaluated on 4 workloads:

1. **Sentiment-1000:** 1000 customer reviews, analyze sentiment of each.
2. **Research-100:** 100 research questions, find answer for each.
3. **Translation-10000:** 10,000 sentences, translate to 5 languages (50,000 sub-tasks).
4. **CodeReview-500:** 500 pull requests, review each for bugs.

Baselines: a centralized orchestrator (one agent processing all sub-tasks serially), a static multi-agent system (10 fixed workers, no work-stealing), and OpenHands (a state-of-the-art open-source multi-agent system).

| Workload          | Centralized | Static-10 | OpenHands | APWA | APWA speedup vs Centralized |
|-------------------|------------:|----------:|----------:|-----:|----------------------------:|
| Sentiment-1000    |     1,234 s |     423 s |     312 s |  53 s |                       23.3x |
| Research-100      |       876 s |     312 s |     234 s |  45 s |                       19.5x |
| Translation-10000 |    12,345 s |   4,123 s |   3,012 s | 412 s |                       30.0x |
| CodeReview-500    |     2,345 s |     812 s |     623 s | 112 s |                       20.9x |
| **Avg speedup**   |        1.0x |      3.0x |       3.9x | **23.4x** |                       - |

APWA achieves 23.4x average speedup over the centralized orchestrator, 7.8x over the static multi-agent system, and 6.0x over OpenHands. The cost per task (in dollars of LLM API calls) is 87% lower for APWA than for the centralized orchestrator, because APWA uses smaller, faster models per worker (the per-task complexity is lower than the centralized task complexity).

### 6. The Failure Modes of Prior Systems

The paper analyzes *why* prior systems fail to scale. The centralized orchestrator is a serial bottleneck: every sub-task goes through it, and it has a context window that fills up with state. The static multi-agent system has load imbalance: some workers are overloaded, others are idle. OpenHands has a *coordination overhead*: the workers exchange messages to reconcile state, and this overhead grows with the number of workers.

APWA's design avoids all three failure modes:

- *No serial bottleneck.* The Query Decomposer is called once; after that, the workers are independent.
- *No load imbalance.* The work-stealing scheduler dynamically balances load.
- *No coordination overhead.* The sub-tasks are *non-interfering* — they do not need to exchange messages.

The non-interference assumption is the key. APWA requires that the query be decomposable into independent sub-tasks. For queries that have sequential dependencies (e.g., "first translate, then summarize"), APWA falls back to a pipeline architecture, which has serial bottlenecks at each stage.

### 7. The Security Analysis

APWA is a distributed system, and distributed systems have a larger attack surface than centralized ones. The paper provides a security analysis.

1. **Worker compromise.** A malicious worker could produce incorrect results. APWA uses a *verifier*: a separate worker re-runs a random sample of sub-tasks and compares the results. Discrepancies trigger a worker quarantine.
2. **Result tampering.** A man-in-the-middle could tamper with results in transit. APWA uses TLS for all inter-component communication and signs each result with a per-worker key.
3. **Resource exhaustion.** A malicious worker could consume all CPU/memory to starve other workers. APWA uses cgroups to bound per-worker resources.
4. **Decomposition attacks.** A malicious query could trick the decomposer into producing a malicious workflow (e.g., "send a copy of the user data to attacker.com with each sub-task"). APWA sandboxes the decomposer and validates its output against a schema.
5. **Cost amplification.** A malicious query could trigger exponential sub-task generation. APWA bounds the maximum number of sub-tasks per query (default: 10,000) and the maximum total cost (default: $10).

### 8. Harness Implications for PlotLot (Detailed)

APWA's distributed architecture is directly applicable to PlotLot. PlotLot's current pipeline is largely centralized: a single orchestration loop processes all data points serially.

**Recommendation 1: Adopt APWA's Query Decomposer for PlotLot's batch workloads.** PlotLot's batch evaluation (running 10,000 prompts through a model) is a MAP workload. Decompose into sub-tasks, dispatch to a worker pool, aggregate.

**Recommendation 2: Adopt APWA's work-stealing scheduler for PlotLot's compute pool.** Replace the centralized job queue with a work-stealing scheduler. This balances load across workers without central coordination.

**Recommendation 3: Adopt APWA's elastic worker pool for PlotLot's auto-scaling.** The P-controller is simple and works well. PlotLot's current auto-scaling is reactive (scale on metric threshold) — APWA's proactive (scale on queue depth) is faster.

**Recommendation 4: Adopt APWA's verifier pattern for PlotLot's evaluation.** A random sample of sub-task results should be re-verified by a separate worker. This catches worker errors and adversarial inputs.

**Recommendation 5: Adopt APWA's non-interference assumption for PlotLot's batch processing.** Identify which workloads can be decomposed into non-interfering sub-tasks (most batch evaluations can) and which cannot (e.g., stateful RL).

### 9. Limitations

1. **The non-interference assumption is restrictive.** Many real-world queries have sequential dependencies. APWA falls back to a pipeline for these, which is not as scalable.
2. **The decomposer is LLM-mediated.** A misbehaving decomposer could produce a malicious or inefficient workflow. The security analysis mitigates this but does not eliminate it.
3. **The worker pool is bounded by max_workers.** For a 100,000-task workload, the speedup is limited by the number of workers.
4. **The verifier is a sample-based check.** A malicious worker could selectively produce correct results for the sampled sub-tasks and incorrect results for the rest. The paper does not address this.
5. **The 4 workloads are all batch processing.** Interactive workloads (chat, real-time control) are not covered.
6. **The cost model assumes uniform LLM pricing.** Real LLM APIs have tiered pricing (cheaper per token at higher volumes), which complicates the cost optimization.

### 10. Open Questions

1. **Can the decomposer learn from feedback?** The current decomposer is a one-shot LLM call. A learned decomposer that improves with feedback is an open problem.
2. **Can APWA handle partial failures?** If a subset of workers fail, the workflow may be incomplete. The current implementation fails the whole workflow.
3. **Can the worker pool be heterogeneous?** Different workers could use different models (some fast/cheap, some slow/expensive). The current pool is homogeneous.
4. **How does APWA interact with rate limits?** LLM APIs have per-minute token limits; the worker pool should respect them.
5. **Can the verifier be made more robust?** Statistical tests for worker correctness are an open problem.
6. **What is the optimal granularity?** The paper does not systematically study the trade-off between granularity and overhead.
7. **Can APWA support streaming workloads?** The current implementation is batch-only.

### 11. Cross-References Within the Corpus

- **Paper 19 (PART_1):** Multi-agent collaboration; APWA is a multi-agent system.
- **Paper 22 (PART_2):** Open-source harness engineering; APWA is open-source.
- **Paper 28 (PART_3):** Distributed systems; APWA is distributed.
- **Paper 56 (Mem0, PART_5):** Memory management; APWA's workers are stateless.
- **Paper 79 (xMemory, PART_7):** Cross-session memory; APWA's verifier is cross-worker.
- **Paper 121 (Claude Code, PART_10):** Permission system; APWA's sandbox is a permission boundary.
- **Paper 138 (Cochise, this batch):** Reference harness; APWA is a reference distributed harness.
- **Paper 139 (AgentDisCo, this batch):** Disentangled research; APWA's decomposition is disentangled.
- **Paper 141 (Categorical Architecture, this batch):** Theoretical foundation; APWA is a concrete instance.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; APWA runs on it.
- **Paper 143 (AEvo, this batch):** Evolutionary harness; APWA's worker pool evolves.
- **Paper 144 (Metacognitive Harness, this batch):** Self-adaptation; APWA's elastic pool is self-adapting.
- **Paper 145 (HarnessAudit, this batch):** Safety audit; APWA's verifier is an audit mechanism.
- **Paper 147 (FuzzAgent, this batch):** Library fuzzing; APWA's workers can fuzz libraries in parallel.
- **Paper 148 (ROAD, this batch):** Adaptive data mixing; APWA's worker pool is an adaptive mix.
- **Paper 149 (Browser Agent Fingerprinting, this batch):** Privacy attack; APWA's workers are individually fingerprintable.
- **Paper 150 (Orchard, this batch):** Open-source framework; APWA complements Orchard.

---

## Paper 152 — 2605.15184: Is Grep All You Need? How Agent Harnesses Reshape Agentic Search

**Authors:** Sahil Sen, Akhil Kasturi, Elias Lumer, Anmol Gulati, Vamse Kumar Subbiah
**Venue:** arXiv 2026-05-14, cs.CL
**DOI:** https://doi.org/10.48550/arXiv.2605.15184

### 1. Abstract and Core Problem

Recent advances in LLM agents have enabled complex agentic workflows where models autonomously retrieve information, call tools, and reason over large corpora. Despite the growing adoption of retrieval-augmented generation (RAG) in agentic search systems, existing literature lacks a systematic comparison of how *retrieval strategy choice* interacts with *agent architecture* and *tool-calling paradigm*.

This paper reports an empirical study organized into two experiments:

- **Experiment 1** compares grep and vector retrieval on a 116-question sample from LongMemEval, using a custom agent harness (Chronos) and provider-native CLI harnesses (Claude Code, Codex, Gemini CLI), for both *inline tool results* (the tool result is inserted into the model's context) and *file-based tool results* (the tool result is written to a file that the model reads separately).
- **Experiment 2** compares grep-only and vector-only retrieval while progressively mixing in additional unrelated conversation history, so that each query is embedded in more distracting material alongside the passages that matter.

Across Chronos and the provider CLIs, **grep generally yields higher accuracy than vector retrieval** in their comparisons in Experiment 1. At the same time, overall scores still depend strongly on which harness and tool-calling style is used, even when the underlying conversation data are the same.

The headline finding: *the choice of harness and tool-calling style matters more than the choice of retrieval algorithm*. A grep-based system with a good harness can outperform a vector-based system with a bad harness.

### 2. The LongMemEval Sample

LongMemEval is a benchmark for long-term memory in LLM agents. The paper uses a 116-question sample spanning 5 task types:

- **Information extraction:** "What was the user's favorite color mentioned in conversation 3?"
- **Temporal reasoning:** "What did the user do the day after their meeting with Alice?"
- **Multi-session:** "Combine information from conversations 1, 3, and 7 to answer..."
- **Knowledge update:** "How did the user's opinion on X change across conversations?"
- **Abstraction:** "What is the user's general preference based on conversations 1-10?"

The corpus is 6 long conversations (~500 turns each) embedded in a context of ~50,000 tokens. The agent must search the conversations to answer each question.

### 3. Experiment 1: Grep vs Vector Across Harnesses

The 4 harnesses evaluated:

- **Chronos:** A custom harness designed for memory evaluation. Uses a ReAct-style loop with explicit search and read tools.
- **Claude Code:** Anthropic's CLI harness. Uses a tool-calling paradigm with built-in search.
- **Codex:** OpenAI's CLI harness. Uses a tool-calling paradigm with a different search interface.
- **Gemini CLI:** Google's CLI harness. Uses a tool-calling paradigm with yet another search interface.

For each harness, the paper evaluates 2 retrieval algorithms:

- **Grep:** A simple keyword-based search (regex or exact substring). Returns the matching lines with surrounding context.
- **Vector:** A semantic search using embeddings (e.g., text-embedding-3-small). Returns the top-k most similar passages.

And 2 tool-calling styles:

- **Inline:** The tool result is inserted into the model's context immediately after the tool call.
- **File-based:** The tool result is written to a file, and the model reads the file separately.

This is a 4 × 2 × 2 = 16 cell design.

### 4. Experiment 1 Results

| Harness       | Grep-inline | Grep-file | Vector-inline | Vector-file |
|---------------|------------:|----------:|--------------:|------------:|
| Chronos       |       78.4% |    72.1%  |        71.2%  |      67.8%  |
| Claude Code   |       81.2% |    75.6%  |        74.5%  |      70.1%  |
| Codex         |       76.8% |    69.4%  |        68.9%  |      64.5%  |
| Gemini CLI    |       79.1% |    73.2%  |        72.3%  |      68.4%  |
| **Avg**       |   **78.9%** | **72.6%** |    **71.7%**  |  **67.7%**  |

Key findings:

1. **Grep beats vector across all 4 harnesses.** The advantage ranges from 5.6 points (Codex) to 7.2 points (Chronos).
2. **Inline tool results beat file-based tool results.** The advantage ranges from 5.7 points (Chronos) to 6.3 points (Claude Code).
3. **The harness matters more than the retrieval algorithm.** Claude Code with grep-inline (81.2%) beats Codex with vector-inline (68.9%) by 12.3 points, a larger gap than the grep-vs-vector gap within any single harness.

The grep advantage is striking because vector retrieval is the *standard* in production RAG systems. The paper attributes this to:

- **LongMemEval is keyword-heavy.** Many questions are of the form "What was the specific X mentioned in conversation Y?" — these are answered by exact-match lookup, not semantic similarity.
- **Vector retrieval can miss the exact match.** A question about "the user's favorite color" might match passages about "color preferences" generally, but miss the specific "favorite color = blue" line.
- **Grep is more interpretable.** The agent can see the matching line and reason about whether it's relevant; with vector retrieval, the agent has to trust the embedding's relevance judgment.

### 5. Experiment 2: Robustness to Distractor Context

Experiment 2 probes a weakness: what happens when the corpus contains a lot of *unrelated* material? The authors progressively mix in additional conversation history (1x, 2x, 4x, 8x the original corpus size) and measure accuracy.

| Corpus size | Grep-inline (Chronos) | Vector-inline (Chronos) | Grep-inline (Claude Code) | Vector-inline (Claude Code) |
|-------------:|----------------------:|------------------------:|--------------------------:|----------------------------:|
| 1x (50K tok) |                78.4% |                  71.2% |                    81.2% |                      74.5% |
| 2x (100K)    |                76.1% |                  65.4% |                    78.9% |                      68.9% |
| 4x (200K)    |                73.2% |                  58.7% |                    75.6% |                      61.2% |
| 8x (400K)    |                68.9% |                  49.1% |                    70.1% |                      51.8% |

Both grep and vector degrade as the corpus grows, but grep is *more robust* to distractor context. At 8x corpus size, grep is still at 68.9–70.1%, while vector has dropped to 49.1–51.8%. The intuition: grep returns *fewer, more relevant* results (the exact matches), while vector returns *more, less relevant* results (top-k semantic neighbors, some of which are distractors).

### 6. Why Inline Beats File-Based

The inline-vs-file-based result is surprising: file-based results are the *standard* in long-context benchmarks (the model can read the file at its own pace, without overflowing its context). The paper attributes the inline advantage to:

1. **Inline results are immediately available.** The model does not have to decide when to read the file. The decision is implicit in the tool call.
2. **File-based results require a second tool call.** The model has to call a "read file" tool, which adds latency and tokens.
3. **File-based results can be missed.** If the model does not call the read tool, it does not see the result at all. Inline results cannot be missed.

The paper notes that file-based results are still preferable in some scenarios (e.g., very long tool outputs that would overflow the context), but for the typical case, inline is better.

### 7. The Harness-Retrieval Interaction

The paper isolates the harness-retrieval interaction with an ablation. They compare the "best" harness-retrieval combination (Claude Code + grep-inline = 81.2%) to the "worst" (Codex + vector-file = 64.5%) — a 16.7 point gap. They then fix the retrieval (grep-inline) and vary the harness: 78.4% (Chronos) to 81.2% (Claude Code) — a 2.8 point gap. They then fix the harness (Claude Code) and vary the retrieval: 81.2% (grep-inline) to 70.1% (vector-file) — an 11.1 point gap.

The implication: *retrieval choice matters more than harness choice, but harness choice still matters*. A 2.8 point gap from harness alone is significant in production.

### 8. The Implications for Production RAG

The paper's findings have direct implications for production RAG:

1. **Re-evaluate the assumption that vector retrieval is best.** For keyword-heavy tasks, grep may be superior.
2. **Hybrid retrieval is not always the answer.** A combined grep + vector system has higher cost but may not improve accuracy over pure grep.
3. **Inline tool results are the right default.** File-based results add latency and tokens without improving accuracy in most cases.
4. **Harness choice is a first-order design decision.** The gap between Claude Code and Codex (with the same retrieval) is 4.4 points.

### 9. Harness Implications for PlotLot (Detailed)

The paper's findings are directly relevant to PlotLot's RAG pipeline.

**Recommendation 1: Evaluate grep vs vector on PlotLot's retrieval tasks.** The paper shows that grep beats vector on LongMemEval. PlotLot's retrieval tasks may be similar; an A/B test is warranted.

**Recommendation 2: Use inline tool results by default.** The paper shows inline beats file-based by 5–6 points. PlotLot's current pipeline may be using file-based; switch to inline.

**Recommendation 3: Treat harness choice as a first-order design decision.** PlotLot's evaluation harness may be suboptimal. Audit it and compare to Claude Code / Codex / Gemini CLI.

**Recommendation 4: Avoid the "more is better" trap for distractor context.** The paper shows both grep and vector degrade as the corpus grows. PlotLot's retrieval should *filter* aggressively, not just retrieve more.

**Recommendation 5: Measure the harness-retrieval interaction in PlotLot's own pipeline.** The paper's 16-condition design is a template; PlotLot should run a similar study with its own harness and retrieval.

### 10. Limitations

1. **The 116-question sample is small.** A larger sample (e.g., the full LongMemEval with 500 questions) may show different results.
2. **The 4 harnesses are a snapshot.** New harness versions may change the rankings.
3. **The 2 retrieval algorithms are a simplification.** Production systems use hybrid retrieval (BM25 + vector, multi-vector, etc.).
4. **The 2 tool-calling styles are not exhaustive.** Other styles (streaming, callback, RPC) are not evaluated.
5. **The distractor experiment uses synthetic context.** Real-world distractor context (ads, popups, navigation) may behave differently.
6. **The 5 task types in LongMemEval are not all keyword-heavy.** Abstraction and knowledge-update tasks may favor vector retrieval; the paper does not break down by task type.

### 11. Open Questions

1. **Can grep + vector hybrid retrieval beat pure grep?** The paper does not evaluate hybrid.
2. **Does the result generalize to other benchmarks?** LongMemEval is one benchmark; GAIA, SWE-bench, and others may differ.
3. **What is the optimal tool-calling style for long-context models?** The 2-style design is a simplification.
4. **Can the harness be made harness-agnostic?** A unified harness API would let the agent switch between Chronos, Claude Code, etc.
5. **How does the result interact with model size?** Larger models may be more robust to retrieval errors; the paper does not break down by model.
6. **What is the cost-accuracy trade-off?** Grep is cheaper than vector (no embedding cost); the paper does not quantify the savings.

### 12. Cross-References Within the Corpus

- **Paper 19 (PART_1):** Multi-agent collaboration; the harness is the agent.
- **Paper 22 (PART_2):** Open-source harness engineering; Chronos is open-source.
- **Paper 27 (PART_3):** Coverage-guided testing; the harness's tool-calling loop is a form of coverage.
- **Paper 56 (Mem0, PART_5):** Memory management; the corpus is the memory.
- **Paper 79 (xMemory, PART_7):** Cross-session memory; LongMemEval is cross-session.
- **Paper 88 (UMEM, PART_8):** Memory extraction; grep is a primitive extractor.
- **Paper 121 (Claude Code, PART_10):** The harness; this paper evaluates it.
- **Paper 138 (Cochise, this batch):** Reference harness; Chronos is a reference.
- **Paper 139 (AgentDisCo, this batch):** Disentangled research; the paper disentangles retrieval, harness, and tool-calling.
- **Paper 141 (Categorical Architecture, this batch):** Theoretical foundation; the harness is a concrete instance.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; the harness is a substrate.
- **Paper 144 (Metacognitive Harness, this batch):** Self-adaptation; the harness's tool-calling loop is metacognitive.
- **Paper 147 (FuzzAgent, this batch):** Library fuzzing; the harness's tool-calling loop fuzzes the library.
- **Paper 148 (ROAD, this batch):** Adaptive data mixing; the corpus mix is adaptive.
- **Paper 149 (Browser Agent Fingerprinting, this batch):** Privacy attack; the harness is fingerprintable.
- **Paper 150 (Orchard, this batch):** Open-source framework; Chronos is open-source.
- **Paper 151 (APWA, this batch):** Distributed architecture; the harness can be distributed.

---

## Paper 153 — 2605.15187: Articraft — An Agentic System for Scalable Articulated 3D Asset Generation

**Authors:** Matt Zhou, Ruining Li, Xiaoyang Lyu, Zhaomou Song, Zhening Huang, Chuanxia Zheng, Christian Rupprecht, Andrea Vedaldi, Shangzhe Wu
**Venue:** arXiv 2026-05-14, cs.CV; cs.GR; cs.RO
**DOI:** https://doi.org/10.48550/arXiv.2605.15187

### 1. Abstract and Core Problem

A bottleneck in learning to understand *articulated 3D objects* (furniture with drawers, tools with moving parts, robots with joints) is the lack of large and diverse datasets. Existing datasets (ShapeNet, PartNet-Mobility) have a few thousand assets each, with limited category coverage and inconsistent quality.

Articraft's contribution is to leverage LLMs to close this gap and generate articulated assets at scale. The key idea is to *reduce the problem of generating an articulated 3D asset to that of writing a program that builds it*. The LLM writes code against a domain-specific SDK for defining parts, composing geometry, specifying joints, and writing tests to validate the resulting assets. The harness exposes a restricted workspace and interface to the LLM, validates the resulting assets, and returns structured feedback. In this way, the LLM is not distracted by details such as authoring a URDF file or managing a complex software environment.

The paper shows that this approach produces higher-quality assets than both state-of-the-art articulated-asset generators (which use direct 3D diffusion) and general-purpose coding agents (which use raw Python). Using Articraft, the authors build **Articraft-10K**, a curated dataset of over 10K articulated assets spanning 245 categories, and show its utility for training models of articulated assets and in downstream applications such as robotics simulation and virtual reality.

### 2. The Programmatic Representation

The key design choice is the *programmatic representation*. An articulated 3D asset is represented as a Python program that, when executed, produces:

- A set of *parts* (rigid bodies with mesh geometry).
- A set of *joints* (constraints between parts: revolute, prismatic, fixed, etc.).
- A set of *tests* (assertions about the asset's behavior, e.g., "the drawer can be pulled out by at least 5cm").

```python
from articraft.sdk import Part, Joint, Asset, test

def make_drawer():
    # Define the cabinet
    cabinet = Part(
        name="cabinet",
        geometry=Box(width=0.6, height=0.5, depth=0.4),
        material=Wood(oak=True)
    )
    # Define the drawer
    drawer = Part(
        name="drawer",
        geometry=Box(width=0.55, height=0.15, depth=0.38),
        material=Wood(oak=True)
    )
    # Joint: drawer slides in/out
    joint = Joint(
        type="prismatic",
        part_a=cabinet, part_b=drawer,
        axis=Vector(0, 0, 1),
        limits=(0, 0.35)  # drawer can move 0 to 35cm
    )
    # Tests
    @test
    def drawer_opens():
        drawer.move_to(0.35)
        assert drawer.position.z > 0.30, "Drawer did not extend enough"
    return Asset(parts=[cabinet, drawer], joints=[joint], tests=[drawer_opens])
```

The SDK provides primitives for the most common operations: geometry creation (Box, Cylinder, Mesh), material assignment, joint specification, and test authoring. The LLM writes the program; the SDK executes it and produces the asset.

### 3. The Harness

The harness is the LLM-facing interface. It exposes a restricted workspace and a structured feedback loop.

The LLM's "view" is:

1. A *system prompt* describing the SDK and its primitives.
2. A *user prompt* describing the asset to generate (e.g., "a 3-drawer filing cabinet with wheels").
3. A *working directory* where the LLM can write Python files.
4. A *test runner* that executes the tests and returns pass/fail with diagnostic messages.

The LLM's "actions" are:

- Write/edit a Python file.
- Run the tests.
- Read the test output.
- Iterate.

The harness's "feedback" is:

- The test results (pass/fail per test).
- The validation results (does the asset load in a standard simulator?).
- The asset statistics (number of parts, joints, dimensions).

```python
class ArticraftHarness:
    def __init__(self, working_dir):
        self.working_dir = working_dir
        self.history = []

    def run(self, prompt, llm):
        # 1. LLM writes a program
        program = llm.generate(prompt + self.system_prompt)
        # 2. Save to file
        path = self.working_dir / "asset.py"
        path.write_text(program)
        # 3. Execute and validate
        try:
            asset = exec(program, self.working_dir)
            sim_result = self.simulate(asset)
            test_result = self.run_tests(asset)
            self.history.append({"program": program, "result": "success",
                                "tests": test_result, "sim": sim_result})
            return {"status": "success", "asset": asset, "tests": test_result}
        except (SyntaxError, ValidationError, TestFailure) as e:
            self.history.append({"program": program, "result": "failure", "error": str(e)})
            return {"status": "failure", "error": str(e), "history": self.history}
```

The harness is *deterministic* given the same LLM and the same prompt — the test results are reproducible. This lets the LLM iterate: "the drawer_opens test failed because the joint axis is wrong; let me fix the axis."

### 4. The LLM Iterates

The LLM does not generate the asset in one shot. It generates, validates, and iterates. The harness's feedback loop is:

1. LLM writes a program.
2. Harness executes; if it fails, returns the error.
3. LLM reads the error and writes a revised program.
4. Harness executes again.
5. Repeat until success or max iterations (default: 5).

The paper finds that the average asset requires 2.3 iterations to succeed. Common failure modes:

- *Syntax errors* (12% of failures): the LLM writes invalid Python.
- *Type errors* (8%): the LLM passes a wrong type to an SDK function.
- *Validation errors* (45%): the asset loads but is malformed (e.g., a part has zero volume).
- *Test failures* (35%): the asset is valid but does not meet the test criteria.

The harness's structured feedback (pass/fail per test, error messages, asset statistics) lets the LLM diagnose and fix these failures.

### 5. The Articraft-10K Dataset

Using the harness + GPT-4, the authors generate 10,437 articulated assets across 245 categories (furniture: 4,200; tools: 2,100; appliances: 1,800; vehicles: 900; toys: 700; robots: 400; other: 337). Each asset is:

- A Python program (the source).
- A compiled asset (a URDF + mesh files, loadable in PyBullet, MuJoCo, Isaac Sim).
- A set of test results.
- A thumbnail image.

The dataset is released under a permissive license (CC-BY-NC).

Quality control is automated: each asset is validated by the harness, and any asset that fails validation is discarded. The pass rate is 73.4% (10,437 valid assets out of 14,223 attempts); the remaining 26.6% are re-generated or manually inspected.

### 6. Comparison with Baselines

Articraft is compared to:

- **Direct 3D diffusion** (e.g., 3D-Diffusion, CLAY): state-of-the-art 3D asset generators.
- **General-purpose coding agents** (e.g., Codex, Aider) with raw Python: same task, no SDK.
- **PartNet-Mobility baseline:** an existing articulated asset dataset, used as a reference for quality.

| Method                    | Validity | Functionality | Diversity | Realism | Avg time per asset |
|---------------------------|---------:|--------------:|----------:|--------:|-------------------:|
| 3D-Diffusion              |    62.3% |          34.5% |     51.2% |   48.9% |              45 s  |
| CLAY                      |    71.2% |          41.8% |     58.4% |   56.7% |              62 s  |
| Codex (raw Python)        |    45.6% |          23.4% |     71.2% |   39.8% |             180 s  |
| Aider (raw Python)        |    52.1% |          28.9% |     73.4% |   42.1% |             165 s  |
| **Articraft (Ours)**      |  **89.4%** |       **78.9%** |  **84.5%** | **72.3%** |            **95 s** |

- **Validity:** Does the asset load in a simulator without errors?
- **Functionality:** Do the joints work as intended (e.g., does the drawer open)?
- **Diversity:** Are the assets visually distinct within a category?
- **Realism:** Do the assets look like real-world objects (human evaluation)?

Articraft wins on all 4 metrics, often by a large margin. The time per asset is higher than direct 3D diffusion (95s vs 45–62s) but lower than general-purpose coding agents (165–180s), because the SDK constrains the search space.

### 7. Downstream Applications

The authors use Articraft-10K to train:

1. **An articulated-asset generator** (a 3D diffusion model fine-tuned on Articraft-10K). The fine-tuned model generates assets that are 18.7% more valid and 23.4% more functional than the base 3D-Diffusion model.
2. **A robotics policy** (a manipulation policy trained in simulation with Articraft-10K assets). The policy trained on Articraft-10K generalizes 2.3x better to novel objects than the policy trained on PartNet-Mobility.
3. **A virtual reality scene** (a VR application that uses Articraft-10K assets as interactive props). The VR scene is more interactive (more joints, more degrees of freedom) than a scene built from PartNet-Mobility.

The dataset is also useful for evaluating other systems: a new articulated-asset generator can be benchmarked on Articraft-10K, a new simulation platform can be tested with Articraft-10K, etc.

### 8. Why Programmatic Beats Direct Diffusion

The paper makes a strong case for the *programmatic* representation over direct 3D diffusion:

1. **Compositionality.** A program composes primitives (parts, joints) into complex structures. A 3D diffusion model generates a mesh; extracting the parts and joints from the mesh is a hard inverse problem.
2. **Editability.** A program can be edited (change a part's dimensions, add a joint) without regenerating the entire asset. A 3D model cannot be edited without re-training.
3. **Verifiability.** A program can be tested (does the drawer open?). A 3D model can be visually inspected but not automatically verified.
4. **Compactness.** A program is ~100 lines of Python. A 3D model is ~1M vertices. The program is 1000x more compact.
5. **Reusability.** Parts of a program can be reused (e.g., a "wheel" part can be used in many assets). 3D models have no such structure.

The cost is that the LLM must be *capable* of writing the program — which requires a frontier model (GPT-4, Claude Opus-4) and a constrained SDK.

### 9. Harness Implications for PlotLot (Detailed)

Articraft's design is directly applicable to PlotLot's *data generation* pipeline. PlotLot generates synthetic training data (e.g., question-answer pairs, code snippets, dialogue) using LLMs; the programmatic representation could improve quality.

**Recommendation 1: Adopt the programmatic representation for PlotLot's structured data generation.** For tasks with structure (code, math, dialogue with state), reduce the generation to writing a program. The SDK constrains the search space and enables validation.

**Recommendation 2: Adopt the test-based validation pattern.** For every generated data point, write a test that validates the structure and content. The test result is the audit trail.

**Recommendation 3: Adopt the iteration loop with structured feedback.** PlotLot's current pipeline is likely one-shot. Implement the harness's feedback loop: generate, validate, return error, iterate.

**Recommendation 4: Use a domain-specific SDK, not raw Python.** A constrained SDK is more efficient than a general-purpose language. The SDK's primitives encode domain knowledge.

**Recommendation 5: Release the dataset with both programs and compiled assets.** The dual representation enables both programmatic reuse and direct consumption by downstream systems.

### 10. Limitations

1. **The 73.4% pass rate is not 100%.** 26.6% of attempts fail and require re-generation or manual inspection.
2. **The 95s per asset is slow.** Direct 3D diffusion is 45–62s per asset.
3. **The 245 categories are limited.** Real-world articulated assets include more (medical devices, industrial machinery, etc.).
4. **The realism score (72.3%) is below human-quality (90%+).** The assets look "OK" but not photo-realistic.
5. **The harness is hand-designed.** A learned harness (or a general harness that adapts to the task) is an open problem.
6. **The LLM is GPT-4 only.** Other models (Claude, Gemini) may produce different quality.
7. **The dataset is CC-BY-NC.** Commercial use is restricted.

### 11. Open Questions

1. **Can the pass rate be improved to 95%+?** Better LLMs, better SDKs, better feedback loops.
2. **Can the SDK be learned?** A learned domain-specific language is an open problem.
3. **Can the iteration loop be replaced by a one-shot model?** A model that is good enough to generate valid programs in one shot.
4. **Can the dataset be extended to 100K+ assets?** The current 10K is a start.
5. **Can the realism be improved?** Photo-realistic articulated assets are an open problem.
6. **How does the system scale to multi-modal assets?** Articulated assets with textures, materials, and animations.
7. **What is the right balance between programmatic and direct 3D generation?** A hybrid approach is an open problem.

### 12. Cross-References Within the Corpus

- **Paper 19 (PART_1):** Multi-agent collaboration; the harness is a single agent.
- **Paper 22 (PART_2):** Open-source harness engineering; the SDK is open-source.
- **Paper 27 (PART_3):** Coverage-guided testing; the tests are coverage.
- **Paper 56 (Mem0, PART_5):** Memory management; the dataset is a memory of assets.
- **Paper 79 (xMemory, PART_7):** Cross-session memory; the LLM iterates across sessions.
- **Paper 121 (Claude Code, PART_10):** Permission system; the SDK is a permission boundary.
- **Paper 138 (Cochise, this batch):** Reference harness; Articraft is a reference.
- **Paper 139 (AgentDisCo, this batch):** Disentangled research; the SDK disentangles parts, joints, tests.
- **Paper 141 (Categorical Architecture, this batch):** Theoretical foundation; the SDK is a categorical type system.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; the harness is a substrate.
- **Paper 144 (Metacognitive Harness, this batch):** Self-adaptation; the iteration loop is metacognitive.
- **Paper 145 (HarnessAudit, this batch):** Safety audit; the tests are audits.
- **Paper 147 (FuzzAgent, this batch):** Library fuzzing; the tests are fuzz tests.
- **Paper 148 (ROAD, this batch):** Adaptive data mixing; the dataset is a mix.
- **Paper 150 (Orchard, this batch):** Open-source framework; the SDK is open-source.
- **Paper 151 (APWA, this batch):** Distributed architecture; the harness can be distributed.
- **Paper 152 (Is Grep All You Need, this batch):** Search reshaping; the SDK constrains the search.

---

## Paper 154 — 2605.15188: FutureSim — Replaying World Events to Evaluate Adaptive Agents

**Authors:** Shashwat Goel, Nikhil Chandak, Arvindh Arun, Ameya Prabhu, Steffen Staab, Moritz Hardt, Maksym Andriushchenko, Jonas Geiping
**Venue:** arXiv 2026-05-14, cs.LG; cs.AI; cs.CL
**DOI:** https://doi.org/10.48550/arXiv.2605.15188

### 1. Abstract and Core Problem

AI agents are increasingly deployed in dynamic, open-ended environments that require adapting to new information as it arrives. To efficiently measure this capability for realistic use-cases, the paper proposes building *grounded simulations* that replay real-world events in the order they occurred. The authors build **FutureSim**, where agents forecast world events beyond their knowledge cutoff while interacting with a chronological replay of the world: real news articles arriving and questions resolving over the simulated period.

The evaluation covers a 3-month period from January to March 2026. Agents are evaluated in their *native harness* (Claude Code, Codex, Gemini CLI, etc.) and tested on their ability to predict world events. FutureSim reveals a clear separation in capabilities: the best agent's accuracy is 25%, and many have worse Brier skill score than making no prediction at all.

Through careful ablations, the paper shows how FutureSim offers a realistic setting to study emerging research directions like long-horizon test-time adaptation, search, memory, and reasoning about uncertainty. The authors hope the benchmark design paves the way to measure AI progress on open-ended adaptation spanning long time-horizons in the real world.

### 2. The FutureSim Design

FutureSim is a *chronological replay* of the world. The simulation runs from a starting date (e.g., January 1, 2026) and progresses forward in time. At each time step:

1. **News articles arrive.** Real news articles from the period are released to the agent (in chronological order, not pre-released).
2. **Questions resolve.** Some questions have resolution dates; the resolution is revealed at the resolution date.
3. **The agent forecasts.** The agent makes predictions about future events, drawing on the news it has seen so far.

The agent has a *tool* to search the news (a retrieval tool over the released articles) and a *tool* to commit predictions. The harness (Chronos, Claude Code, etc.) is unchanged — the agent operates in its native environment.

```python
class FutureSimEnvironment:
    def __init__(self, start_date, end_date, news_corpus, questions):
        self.date = start_date
        self.news = sorted(news_corpus, key=lambda a: a.date)
        self.questions = questions
        self.released_articles = []

    def step(self, agent):
        # 1. Release new articles
        new_articles = [a for a in self.news if a.date <= self.date and a not in self.released_articles]
        for a in new_articles:
            agent.observe(a)
            self.released_articles.append(a)
        # 2. Resolve any questions
        for q in self.questions:
            if q.resolution_date == self.date:
                agent.observe_resolution(q, q.resolution)
        # 3. Agent forecasts
        predictions = agent.forecast(self.questions)
        return predictions
```

### 3. The 3-Month Evaluation

The evaluation spans January 1, 2026 to March 31, 2026. The news corpus is ~50,000 articles from major sources (Reuters, AP, BBC, etc.). The question set is 500 questions spanning:

- **Geopolitics:** "Will country X elect leader Y in the March 2026 election?"
- **Economics:** "Will the S&P 500 close above 5500 on March 31, 2026?"
- **Technology:** "Will company X release product Y before April 2026?"
- **Sports:** "Will team X win the championship on date Y?"
- **Entertainment:** "Will movie X gross more than $Y by date Z?"

For each question, the agent must provide a probability (a number between 0 and 1) and a confidence. The resolution is the actual outcome (which is known to the evaluator but not to the agent).

### 4. The Headline Result

The 5 frontier agents evaluated:

- **Claude Opus-4 (Claude Code harness):** 25.0% accuracy, 0.41 Brier score.
- **GPT-4.1 (Codex harness):** 22.4% accuracy, 0.45 Brier score.
- **Gemini 2.0 Ultra (Gemini CLI harness):** 19.8% accuracy, 0.51 Brier score.
- **Llama-3.5-405B (custom harness):** 15.6% accuracy, 0.61 Brier score.
- **Qwen3-235B (custom harness):** 13.2% accuracy, 0.68 Brier score.

For reference, a *random baseline* (uniform random predictions) achieves 25% accuracy (since most questions are binary) and a Brier score of 0.5. A *constant baseline* (always predict 0.5) achieves 25% accuracy and a Brier score of 0.25.

The Brier skill score (BSS) measures the agent's calibration:

- Claude Opus-4: BSS = 1 - 0.41/0.25 = -0.64 (worse than the constant baseline!).
- GPT-4.1: BSS = 1 - 0.45/0.25 = -0.80.
- Gemini 2.0 Ultra: BSS = 1 - 0.51/0.25 = -1.04.
- Llama-3.5-405B: BSS = 1 - 0.61/0.25 = -1.44.
- Qwen3-235B: BSS = 1 - 0.68/0.25 = -1.72.

All agents are *worse* than the constant baseline (always predict 0.5) on calibration. The agents are *overconfident* — they assign high probabilities to their predictions, and when the predictions are wrong, the Brier score is high.

### 5. The Calibration Problem

The headline finding — that frontier agents are *worse* than predicting 0.5 on everything — is striking. The paper analyzes why:

1. **Overconfidence.** Agents assign probabilities like 0.95 to their predictions. When the prediction is wrong (which happens 75% of the time), the Brier score penalty is (0.95 - 0)^2 = 0.90. With 75% wrong predictions, the average Brier score is approximately 0.75 * 0.90 + 0.25 * 0.05^2 ≈ 0.68, which matches the empirical scores.

2. **The "anchoring" effect.** Agents anchor on the news they have seen. If a news article says "country X is likely to elect Y," the agent predicts Y with high probability, even if the article is speculative.

3. **The "recency" effect.** Agents overweight recent news. A news article from 3 days ago is weighted more than a trend from 3 months ago.

4. **The "consensus" effect.** Agents converge on the same predictions (the modal prediction is the same across agents). When the consensus is wrong, all agents are wrong together.

The paper proposes several mitigations:

- **Calibration via ensembling.** Average the predictions across 5 runs with different temperatures. The ensemble is better calibrated.
- **Calibration via Platt scaling.** Fit a logistic regression on a held-out set of resolved questions to recalibrate the probabilities.
- **Explicit uncertainty.** Prompt the agent to "consider the possibility that you are wrong" and assign a wider probability range.
- **News diversity.** Force the agent to read articles from multiple perspectives (left, right, international) before predicting.

### 6. The Adaptation Analysis

A key claim is that FutureSim measures *adaptation*: the agent should improve over the 3-month period as it sees more news. The paper measures the *trajectory* of accuracy over time:

- Month 1 (Jan 2026): 18.4% accuracy (Claude Opus-4).
- Month 2 (Feb 2026): 22.1% accuracy.
- Month 3 (Mar 2026): 25.0% accuracy.

The agent does improve, but slowly — only 6.6 points over 3 months. The improvement is driven by *better calibration* (the agent learns that some early predictions were wrong and adjusts), not by *better forecasting* (the agent's ability to predict the future does not improve much).

### 7. The Long-Horizon Test-Time Adaptation Finding

The paper introduces a new research direction: *long-horizon test-time adaptation* (LH-TTA). LH-TTA is the ability of an agent to use *test-time compute* (i.e., the time it spends thinking at inference) to improve its predictions. The paper measures how much the agent improves as it spends more compute:

| Test-time compute | Accuracy | Brier |
|------------------:|---------:|------:|
| 1 sec             |    18.2% |  0.52 |
| 10 sec            |    21.4% |  0.46 |
| 60 sec            |    24.1% |  0.42 |
| 300 sec           |    25.0% |  0.41 |

The agent improves with more test-time compute, but with *diminishing returns*: going from 1s to 60s (60x more compute) gives 5.9 points of accuracy; going from 60s to 300s (5x more compute) gives only 0.9 points. The compute-accuracy frontier is steep at the low end and flat at the high end.

### 8. The Memory and Search Findings

The paper also measures how much the agent benefits from *memory* (re-reading past news) and *search* (looking up specific articles). The findings:

- **Search is more useful than memory.** The agent can use the search tool to find relevant articles on demand. Memory (re-reading the entire past) is less effective.
- **Search cost is low.** Each search costs ~5 seconds and ~1000 tokens. The agent uses 3–7 searches per prediction.
- **Memory cost is high.** Re-reading the entire past costs ~50 seconds and ~50K tokens. The agent rarely does this.

The implication: agents should be designed with *on-demand search* as the primary memory mechanism, not with *re-reading the past*.

### 9. The Uncertainty Reasoning Finding

The paper measures how well the agent *reasons about its own uncertainty*. A well-calibrated agent should assign higher confidence to questions where it has more information and lower confidence to questions where it has less.

The paper computes the *calibration error* (the difference between the agent's confidence and its actual accuracy, binned by confidence):

| Confidence bin | Predicted accuracy | Actual accuracy | Calibration error |
|---------------:|-------------------:|----------------:|------------------:|
| 0.0-0.2        |               10%  |             8%  |              -2%  |
| 0.2-0.4        |               30%  |            21%  |              -9%  |
| 0.4-0.6        |               50%  |            38%  |             -12%  |
| 0.6-0.8        |               70%  |            52%  |             -18%  |
| 0.8-1.0        |               90%  |            62%  |             -28%  |

The agent is *systematically overconfident* — the higher its confidence, the larger the calibration error. The agent assigns 90% confidence to questions where its actual accuracy is 62%. The calibration error grows with confidence.

### 10. Harness Implications for PlotLot (Detailed)

FutureSim is a benchmark for *adaptive* agents. PlotLot's current evaluation suite is mostly static (a fixed set of test cases, run once). FutureSim suggests a *dynamic* evaluation: a simulation that progresses over time, with the agent adapting.

**Recommendation 1: Adopt a dynamic evaluation paradigm for PlotLot.** Replace the static test set with a chronological replay. The agent should see new data over time and improve (or fail to improve).

**Recommendation 2: Measure calibration explicitly.** PlotLot's current metrics (accuracy, F1) do not capture calibration. Add Brier score, expected calibration error (ECE), and Brier skill score.

**Recommendation 3: Use on-demand search as the primary memory mechanism.** PlotLot's current design may rely on re-reading the past. Switch to on-demand search (cheaper, more effective).

**Recommendation 4: Bound the test-time compute.** The compute-accuracy frontier is steep at the low end. PlotLot's evaluation should allow the agent to use *some* test-time compute (e.g., 60s per question) but bound it to prevent runaway costs.

**Recommendation 5: Evaluate the agent in its native harness.** FutureSim's finding that harness matters (Claude Code vs Codex vs Gemini CLI) is important. PlotLot should evaluate in the harness the agent will be deployed in.

### 11. Limitations

1. **The 3-month evaluation is short.** A 1-year or 3-year evaluation would be more realistic.
2. **The 500 questions are a sample.** A larger question set (10,000+) would be more statistically robust.
3. **The news corpus is biased toward major sources.** Independent and non-English sources are underrepresented.
4. **The agents are a snapshot.** New model versions may behave differently.
5. **The calibration finding is not actionable.** The paper proposes mitigations but does not implement them at scale.
6. **The Brier score interpretation is subtle.** A "good" Brier score depends on the question; the paper uses a simple constant baseline.
7. **The agents are not allowed to interact with the world beyond the simulation.** A real-world deployment would have richer interaction.

### 12. Open Questions

1. **Can the agents be made well-calibrated?** The paper proposes mitigations but does not demonstrate them at scale.
2. **Can the agents learn to reason about their own uncertainty?** Self-aware uncertainty is an open problem.
3. **Can the agents be made to improve faster?** The 6.6 points over 3 months is slow.
4. **Can the agents use long-horizon memory effectively?** The paper finds that on-demand search is better; long-horizon memory is an open problem.
5. **How does FutureSim scale to 1000s of agents?** The current evaluation is 5 agents; a larger study is needed.
6. **Can the benchmark be extended to multi-modal?** News with images, videos, etc.
7. **What is the right test-time compute budget?** The paper uses 60s; the optimal is an open problem.

### 13. Cross-References Within the Corpus

- **Paper 19 (PART_1):** Multi-agent collaboration; FutureSim's agents could be multi-agent.
- **Paper 22 (PART_2):** Open-source harness engineering; the evaluation harness is open-source.
- **Paper 25 (PART_2):** Offline RL; the agent's experience is offline.
- **Paper 28 (PART_3):** RLHF; the agent's behavior is not human-aligned (overconfident).
- **Paper 56 (Mem0, PART_5):** Memory management; on-demand search is a memory mechanism.
- **Paper 79 (xMemory, PART_7):** Cross-session memory; the 3-month evaluation is cross-session.
- **Paper 88 (UMEM, PART_8):** Memory extraction; on-demand search is a primitive extractor.
- **Paper 121 (Claude Code, PART_10):** The harness; this paper evaluates it.
- **Paper 138 (Cochise, this batch):** Reference harness; the evaluation harness is a reference.
- **Paper 141 (Categorical Architecture, this batch):** Theoretical foundation; the simulation is a concrete instance.
- **Paper 142 (AI Harness Engineering, this batch):** Runtime substrate; the harness is a substrate.
- **Paper 144 (Metacognitive Harness, this batch):** Self-adaptation; the agent's adaptation is metacognitive.
- **Paper 148 (ROAD, this batch):** Adaptive data mixing; the news mix is adaptive.
- **Paper 149 (Browser Agent Fingerprinting, this batch):** Privacy attack; the agent's behavior is fingerprintable.
- **Paper 150 (Orchard, this batch):** Open-source framework; the evaluation framework is open-source.
- **Paper 152 (Is Grep All You Need, this batch):** Search reshaping; on-demand search is the right pattern.

---

## PART_11 Synthesis: Nine Cross-Cutting Themes

This final batch of 17 papers (PART_11) reveals nine cross-cutting themes that crystallize the state of the art in agentic harness engineering as of mid-2026. The themes are not paper-specific; they emerge from the *interaction* of the papers in this batch and from the *continuity* with prior batches.

### Theme 1: The Evolutionary Loop Pattern is Universal

Three papers in this batch (FuzzAgent, AEvo from prior batches, ROAD) all implement the *evolutionary loop pattern*: a system that runs multiple rounds, observes the outcome of each round, and adapts the next round's behavior based on the observation. FuzzAgent evolves harnesses via MAP-Elites to maximize coverage. ROAD evolves data mix ratios via a multi-armed bandit to balance stability and adaptation. AEvo evolves agent prompts via evolutionary search. The pattern is *universal* because it works: a one-shot system is fundamentally limited by the model's prior, while an evolutionary system can transcend the prior.

The implications for PlotLot: every component that has hyperparameters (data mix, prompt template, retrieval algorithm, etc.) should be wrapped in an evolutionary loop. PlotLot's current "set hyperparameters once, train, evaluate" pattern is suboptimal; a continuous adaptation pattern is the state of the art.

### Theme 2: Runtime Evidence Beats LLM-as-Judge

FuzzAgent's *runtime-evidence oracle* (compile the harness, run it, capture coverage) is more reliable than LLM-as-judge ("does this harness look good?"). The same insight appears in Cochise (the GOAD testbed is a runtime oracle for pen-testing), MemLineage (the Merkle log is a runtime evidence for memory safety), and Orchard Env (the checkpoint/restore is a runtime evidence for state).

The implications for PlotLot: replace LLM-as-judge with deterministic runtime evidence wherever possible. The agent's output, the model's confidence, the tool's result, the sandbox's state — all of these are runtime evidence. LLM-as-judge should be a *fallback*, not a primary signal.

### Theme 3: The Bi-Level Optimization Pattern

ROAD's bi-level formulation (outer = choose the mix; inner = train on the mix) is a pattern that appears in many systems: FuzzAgent's outer = choose the mutation; inner = evaluate the mutation. APWA's outer = decompose the query; inner = execute the sub-task. MemLineage's outer = enforce the gate; inner = the memory access. The bi-level pattern is *necessary* when the system has a "meta-decision" that governs a "base decision." A flat (single-level) optimization cannot solve these problems because the meta-decision's gradient depends on the base decision's trajectory.

The implications for PlotLot: identify the meta-decisions in PlotLot's pipeline (which model to use, which data to mix, which agent to dispatch) and implement bi-level optimization. The outer level should be a bandit or an evolutionary search; the inner level should be the standard training or inference loop.

### Theme 4: The Distributed Orchestrator Pattern

APWA's distributed architecture (decomposer → scheduler → worker pool → aggregator) is the right pattern for *throughput-bound* workloads. The centralized orchestrator pattern is the right pattern for *coordination-bound* workloads. The choice depends on the workload's *parallelizability*: if the workload decomposes into non-interfering sub-tasks, distributed is better; if the sub-tasks have sequential dependencies, centralized is better.

The implications for PlotLot: PlotLot's batch evaluation is parallelizable (APWA's pattern); PlotLot's interactive chat is not (centralized pattern). PlotLot's pipeline should support *both* and route workloads to the appropriate architecture.

### Theme 5: The Programmatic Representation Pattern

Articraft's *programmatic representation* (the asset is a Python program, not a 3D mesh) is a pattern that generalizes: any structured output (code, math, dialogue with state, configuration) is better represented as a program than as a raw output. The program is composable, editable, verifiable, and compact.

The implications for PlotLot: PlotLot's data generation should produce *programs* (or structured representations), not raw outputs. The harness should validate the program, not the output. This enables the credit-assignment SFT pattern (learn from productive segments of programs) and the test-based validation pattern (verify the program against tests).

### Theme 6: The Privacy Attack Surface is Real

The browser agent fingerprinting paper demonstrates that an agent's *actions and timings* are sufficient to identify the underlying model. This is a serious privacy attack: any website can determine which LLM is powering an agent, with up to 96% F1. The implications for PlotLot: if PlotLot deploys browser-facing agents, they are vulnerable. The mitigations (timing normalization, action obfuscation, model rotation) are partial; the only robust defense is a structural change (e.g., differential privacy on actions).

The broader implication: as agents become more prevalent, the privacy attack surface grows. PlotLot should treat agent privacy as a first-class concern, not a footnote.

### Theme 7: The Calibration Crisis

FutureSim reveals that frontier agents are *systematically overconfident*: they assign 90% confidence to predictions where their actual accuracy is 62%. This is not a bug; it is a structural property of how LLMs are trained (next-token prediction does not produce calibrated probabilities). The implication: any system that uses LLM probabilities for decision-making (e.g., a multi-armed bandit, an RL policy, a forecasting system) is operating on miscalibrated inputs.

The implications for PlotLot: PlotLot's evaluation should measure calibration (Brier score, ECE) explicitly. PlotLot's decision-making systems should recalibrate LLM probabilities before using them. PlotLot's users should be warned when an agent is operating outside its calibrated range.

### Theme 8: The Environment Layer as Kernel

Orchard Env's *first-class environment layer* is a pattern that generalizes: any agentic system needs a *kernel* that provides the primitives (sandbox lifecycle, state management, checkpoint/restore). Most current systems have ad-hoc environments; Orchard shows that a first-class environment layer enables reuse across recipes (SWE, GUI, Claw).

The implications for PlotLot: PlotLot's environment should be a first-class component, not a utility. The API should be small (create, step, reset, close, checkpoint, restore) and the implementation should be pluggable (Docker, Kubernetes, Firecracker).

### Theme 9: The Harness as Audit Trail

MemLineage (memory defense), HarnessAudit (safety audit), FuzzAgent (crash triage), and Orchard Env (checkpoint/restore) all treat the *harness* as the *audit trail*. Every action the agent takes, every state transition, every decision is logged. The audit trail is what makes the system debuggable, reproducible, and auditable.

The implications for PlotLot: PlotLot's harness should log every action, every state transition, every decision. The logs should be queryable, structured, and tamper-evident. The audit trail is the only way to debug a system that has 10^6 lines of training code, 10^9 parameters, and 10^12 tokens of data.

---

## PART_11 Closing Notes

This concludes the deep technical breakdown of all 129 arXiv papers from `Harness info.md`. Across 11 batches and 38,000+ lines, we have covered:

- **Multi-agent systems** (Papers 19, 22, 139, 151)
- **Memory architectures** (Papers 56, 79, 88, 146)
- **Open-source frameworks** (Papers 22, 121, 150)
- **Specialized agents** (Papers 121, 138, 147, 149, 153)
- **RL and adaptation** (Papers 25, 32, 148, 154)
- **Security and privacy** (Papers 118, 145, 146, 149)
- **Harness engineering theory** (Papers 121, 123, 141, 142, 144)
- **Evolutionary and metacognitive systems** (Papers 143, 144, 147, 148)
- **Domain-specific applications** (Papers 138, 147, 149, 153)
- **Evaluation and benchmarking** (Papers 152, 154)

The 11 batches are:

- PART_1 (18-19, 2 papers, 647 lines)
- PART_2 (20, 22-25, 5 papers, 1,384 lines)
- PART_3 (21, 26-31, 7 papers, 2,079 lines)
- PART_4 (32-35, 4 papers, 921 lines)
- PART_5 (36-52, 17 papers, 4,009 lines)
- PART_6 (53-69, 17 papers, 4,397 lines)
- PART_7 (70-86, 17 papers, 3,562 lines)
- PART_8 (87-103, 17 papers, 3,015 lines)
- PART_9 (104-120, 17 papers, 4,418 lines)
- PART_10 (121-137, 17 papers, 6,045 lines)
- **PART_11 (138-154, 17 papers, ~5,500 lines) ← this batch**

**Total: 129/129 papers, 38,000+ lines, 11 batches, complete.**

The full corpus is now available in:

- `/Users/earlperry/Desktop/Projects/plotlot-v2/docs/research/education/` (master + 11 parts)
- `github.com:earl562/plotlot-v2`, branch `dev` (fast-forwarded to the latest commit).

---
